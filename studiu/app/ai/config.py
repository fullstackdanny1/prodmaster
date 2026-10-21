"""Configurația AI comună: ~/.config/ai/ai.toml și cheile din ~/.config/ai/.env.

Un fișier lipsă sau gol funcționează: valorile implicite folosesc Gemini (free tier).
Variabila de mediu AI_CONFIG poate indica alt fișier (folosită în teste); în acest caz
.env se caută lângă el. AI_STATE poate indica alt folder pentru consum.
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_MODEL = "gemini:gemini-3.8-flash"
MAX_ALIAS_DEPTH = 3

DEFAULT_PROVIDERS: dict[str, dict] = {
    "gemini": {
        "tip": "openai",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "cheie": "GEMINI_API_KEY",
        "timeout_s": 180,
    },
    "ollama": {
        "tip": "openai",
        "base_url": "http://127.0.0.1:11434/v1",
        "cheie": "",
        "timeout_s": 900,
        "context_max": 8192,
    },
}


class ConfigError(Exception):
    pass


@dataclass
class Provider:
    name: str
    tip: str = "openai"
    base_url: str = ""
    cheie: str = ""              # numele variabilei din .env, nu cheia
    cereri_pe_minut: float = 0
    timeout_s: float = 180
    schema_json: str = "auto"    # auto | da | nu
    context_max: int = 0
    max_iesire: int = 8192
    pret_intrare_1m: float = 0.0
    pret_iesire_1m: float = 0.0

    @property
    def free(self) -> bool:
        return not self.pret_intrare_1m and not self.pret_iesire_1m

    @property
    def local(self) -> bool:
        url = self.base_url.lower()
        return any(h in url for h in ("://127.", "://localhost", "://[::1]", "://0.0.0.0"))


@dataclass
class AIConfig:
    path: Path
    env_path: Path
    implicit: str = DEFAULT_MODEL
    aliases: dict[str, str] = field(default_factory=dict)
    tasks: dict[str, str] = field(default_factory=dict)
    monthly_budget: float = 0.0
    providers: dict[str, Provider] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)   # probleme găsite la încărcare


def config_path() -> Path:
    env = os.environ.get("AI_CONFIG")
    if env:
        return Path(os.path.expanduser(env))
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / "ai" / "ai.toml"


def env_path() -> Path:
    return config_path().parent / ".env"


def state_dir() -> Path:
    env = os.environ.get("AI_STATE")
    if env:
        return Path(os.path.expanduser(env))
    base = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    return Path(base) / "ai"


def read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return values
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        k, v = line.split("=", 1)
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        values[k.strip()] = v
    return values


def key_value(provider: Provider, cfg: AIConfig) -> str:
    """Cheia furnizorului: variabilele de mediu setate au prioritate față de .env."""
    if not provider.cheie:
        return ""
    return os.environ.get(provider.cheie) or read_env_file(cfg.env_path).get(provider.cheie, "")


def _provider(name: str, raw: dict) -> Provider:
    p = Provider(name=name)
    for k, v in raw.items():
        if hasattr(p, k) and k != "name":
            setattr(p, k, type(getattr(p, k))(v) if not isinstance(getattr(p, k), str) else str(v))
    p.base_url = p.base_url.rstrip("/")
    p.schema_json = p.schema_json.lower()
    return p


def load() -> AIConfig:
    path = config_path()
    raw: dict = {}
    errors: list[str] = []
    if path.exists():
        try:
            with path.open("rb") as f:
                raw = tomllib.load(f)
        except (tomllib.TOMLDecodeError, OSError) as e:
            errors.append(f"Nu pot citi {path}: {e}")
    cfg = AIConfig(path=path, env_path=path.parent / ".env")
    cfg.implicit = str(raw.get("implicit") or DEFAULT_MODEL)
    cfg.aliases = {str(k): str(v) for k, v in (raw.get("aliasuri") or {}).items()}
    cfg.tasks = {str(k): str(v) for k, v in (raw.get("sarcini") or {}).items()}
    try:
        cfg.monthly_budget = float((raw.get("buget") or {}).get("lunar_usd", 0) or 0)
    except (TypeError, ValueError):
        errors.append("[buget].lunar_usd trebuie să fie un număr.")
    merged = {k: dict(v) for k, v in DEFAULT_PROVIDERS.items()}
    for name, values in (raw.get("furnizori") or {}).items():
        if not isinstance(values, dict):
            errors.append(f"[furnizori.{name}] trebuie să fie un tabel.")
            continue
        merged.setdefault(name, {}).update(values)
    for name, values in merged.items():
        try:
            cfg.providers[name] = _provider(name, values)
        except (TypeError, ValueError) as e:
            errors.append(f"[furnizori.{name}]: valoare invalidă ({e}).")
    cfg.errors = errors + validate(cfg)
    return cfg


def split_ref(ref: str) -> tuple[str, str]:
    provider, _, model = ref.partition(":")
    return provider.strip(), model.strip()


def resolve_ref(cfg: AIConfig, ref: str) -> tuple[str, str]:
    """Referință (alias sau furnizor:model) → (furnizor, model). Ridică ConfigError."""
    seen = []
    current = (ref or "").strip()
    while ":" not in current:
        if not current:
            raise ConfigError("Referință de model goală.")
        if current in seen:
            chain = " → ".join(seen + [current])
            raise ConfigError(f"Ciclu de aliasuri: {chain}.")
        if current not in cfg.aliases:
            raise ConfigError(f"Modelul sau aliasul «{current}» nu e definit în {cfg.path}.")
        if len(seen) >= MAX_ALIAS_DEPTH:
            raise ConfigError(f"Aliasul «{ref}» trimite prin prea multe aliasuri (maximum {MAX_ALIAS_DEPTH}).")
        seen.append(current)
        current = cfg.aliases[current].strip()
    provider, model = split_ref(current)
    if provider not in cfg.providers:
        raise ConfigError(f"Furnizorul «{provider}» (din «{ref}») nu e declarat în [furnizori] din {cfg.path}.")
    if not model:
        raise ConfigError(f"Referința «{current}» nu conține numele modelului (format: furnizor:model).")
    return provider, model


def validate(cfg: AIConfig) -> list[str]:
    errors = []
    for name, p in cfg.providers.items():
        if p.tip not in ("openai", "anthropic"):
            errors.append(f"[furnizori.{name}].tip = «{p.tip}» nu e cunoscut (openai | anthropic).")
        if not p.base_url:
            errors.append(f"[furnizori.{name}] nu are base_url.")
        if p.schema_json not in ("auto", "da", "nu"):
            errors.append(f"[furnizori.{name}].schema_json trebuie să fie auto, da sau nu.")
    refs = [("implicit", cfg.implicit)]
    refs += [(f"[aliasuri].{k}", k) for k in cfg.aliases]
    refs += [(f"[sarcini].{k}", v) for k, v in cfg.tasks.items()]
    for where, ref in refs:
        try:
            resolve_ref(cfg, ref)
        except ConfigError as e:
            errors.append(f"{where}: {e}")
    return errors
