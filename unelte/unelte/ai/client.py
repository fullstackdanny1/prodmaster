"""Stratul AI comun: rezolvarea modelului, ritm, reîncercări, JSON validat, consum, buget.

Codul aplicațiilor cere doar o sarcină:
    rezultat = ai.ruleaza("carduri", mesaje, schema=SCHEMA, la_progres=print)
iar configurația (~/.config/ai/ai.toml) decide furnizorul și modelul.
"""
from __future__ import annotations

import json
import math
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

from . import config as cfgmod
from .adaptoare import (ADAPTOARE, CerereChat, ProviderHTTPError, ProviderNetworkError,
                        ProviderSettings, RaspunsChat)
from .schema import SchemaError, describe, extract_json, validate


class AIError(Exception):
    """Eroare cu mesaj în română, gata de afișat utilizatorului."""


RATE_LIMIT_PAUSES = (5, 15, 45, 90)
SERVER_ERROR_PAUSES = (3, 10)

# Ce aplicație scrie consumul și ce comandă listează modelele (setate de fiecare aplicație).
_app = {"name": "necunoscut", "models_cmd": "python -m ai modele {furnizor}"}
_clock = time.monotonic
_sleep = time.sleep
_rate_lock = threading.Lock()
_last_call: dict[str, float] = {}
_schema_rejected: set[str] = set()   # furnizori care au respins response_format (până la repornire)


def set_application(name: str, models_cmd: str | None = None) -> None:
    _app["name"] = name
    if models_cmd:
        _app["models_cmd"] = models_cmd


@dataclass
class Rezultat:
    text: str
    date: object = None              # JSON-ul decodat și validat, dacă s-a cerut schemă
    furnizor: str = ""
    model: str = ""
    intrare: int = 0
    iesire: int = 0
    estimat: bool = False
    cost_usd: float = 0.0


@dataclass
class Diagnostic:
    ok: bool
    furnizor: str = ""
    model: str = ""
    mesaj: str = ""
    durata_s: float = 0.0
    note: list[str] = field(default_factory=list)


# ---------- configurație și rezolvare ----------

def load_config() -> cfgmod.AIConfig:
    return cfgmod.load()


def resolve(sarcina: str, model: str | None = None, cfg: cfgmod.AIConfig | None = None):
    """Alegerea explicită → [sarcini] → implicit. Întoarce (cfg, Provider, model)."""
    cfg = cfg or load_config()
    ref = model or cfg.tasks.get(sarcina) or cfg.implicit
    try:
        provider, name = cfgmod.resolve_ref(cfg, ref)
    except cfgmod.ConfigError as e:
        raise AIError(str(e)) from e
    return cfg, cfg.providers[provider], name


def check_model_ref(model: str, cfg: cfgmod.AIConfig | None = None) -> None:
    """Validează o referință aleasă de utilizator; ridică AIError cu modelele configurate."""
    cfg = cfg or load_config()
    try:
        cfgmod.resolve_ref(cfg, model)
    except cfgmod.ConfigError as e:
        known = ", ".join(sorted(cfg.aliases)) or "niciun alias"
        raise AIError(f"{e} Modele configurate: {known} (sau furnizor:model).") from e


def _adaptor(cfg: cfgmod.AIConfig, p: cfgmod.Provider, need_key: bool = True):
    key = cfgmod.key_value(p, cfg)
    if need_key and p.cheie and not key:
        raise AIError(
            f"Lipsește cheia pentru furnizorul «{p.name}»: adaugă {p.cheie}=... în {cfg.env_path}."
        )
    cls = ADAPTOARE.get(p.tip)
    if cls is None:
        raise AIError(f"Adaptorul «{p.tip}» al furnizorului «{p.name}» nu există.")
    return cls(ProviderSettings(name=p.name, base_url=p.base_url, key=key, timeout_s=p.timeout_s))


def modele_configurate() -> dict:
    cfg = load_config()

    def res(ref):
        try:
            prov, model = cfgmod.resolve_ref(cfg, ref)
            return f"{prov}:{model}"
        except cfgmod.ConfigError as e:
            return f"eroare: {e}"

    return {
        "fisier": str(cfg.path),
        "fisier_chei": str(cfg.env_path),
        "implicit": {"ref": cfg.implicit, "rezolvat": res(cfg.implicit)},
        "aliasuri": {k: {"ref": v, "rezolvat": res(k)} for k, v in cfg.aliases.items()},
        "sarcini": {k: {"ref": v, "rezolvat": res(v)} for k, v in cfg.tasks.items()},
        "furnizori": {
            name: {
                "tip": p.tip,
                "base_url": p.base_url,
                "cheie": p.cheie,
                "cheie_prezenta": bool(cfgmod.key_value(p, cfg)) if p.cheie else None,
                "local": p.local,
                "gratuit": p.free,
                "context_max": p.context_max,
            }
            for name, p in cfg.providers.items()
        },
        "buget_lunar_usd": cfg.monthly_budget,
        "erori": list(cfg.errors),
    }


def listeaza_modele(furnizor: str) -> list[str]:
    cfg = load_config()
    p = cfg.providers.get(furnizor)
    if p is None:
        raise AIError(f"Furnizorul «{furnizor}» nu e declarat în {cfg.path}.")
    try:
        return _adaptor(cfg, p).modele()
    except ProviderHTTPError as e:
        raise AIError(_http_message(p, "", e)) from e
    except ProviderNetworkError as e:
        raise AIError(_network_message(p, e)) from e


# ---------- estimări ----------

def estimeaza_tokeni(text: str) -> int:
    return math.ceil(len(text or "") / 3.5)


def estimeaza_cost(sarcina: str, tokeni_intrare: int, tokeni_iesire: int, model: str | None = None) -> float | None:
    try:
        _cfg, p, _m = resolve(sarcina, model)
    except AIError:
        return None
    return _cost(p, tokeni_intrare, tokeni_iesire)


def _cost(p: cfgmod.Provider, tin: int, tout: int) -> float:
    if p.free:
        return 0.0
    return (tin * p.pret_intrare_1m + tout * p.pret_iesire_1m) / 1_000_000


def info_model(sarcina: str, model: str | None = None) -> dict:
    """Pentru interfețe: ce model execută sarcina și dacă e gratuit/local."""
    cfg, p, name = resolve(sarcina, model)
    return {"furnizor": p.name, "model": name, "gratuit": p.free, "local": p.local,
            "context_max": p.context_max}


def max_chunk_chars(sarcina: str, wanted: int, model: str | None = None) -> int:
    """Cel mult jumătate din contextul modelului pentru textul trimis (dacă e cunoscut)."""
    try:
        _cfg, p, _m = resolve(sarcina, model)
    except AIError:
        return wanted
    if p.context_max > 0:
        return max(1000, min(wanted, int(p.context_max / 2 * 3.5)))
    return wanted


# ---------- consum și buget ----------

def _usage_dir():
    return cfgmod.state_dir() / "consum"


def consum(luna: str | None = None) -> list[dict]:
    luna = luna or datetime.now().strftime("%Y-%m")
    path = _usage_dir() / f"{luna}.jsonl"
    rows = []
    try:
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except OSError:
        pass
    return rows


def rezumat_consum(luna: str | None = None) -> dict:
    rows = consum(luna)
    out = {"luna": luna or datetime.now().strftime("%Y-%m"), "apeluri": len(rows),
           "intrare": 0, "iesire": 0, "cost_usd": 0.0,
           "aplicatii": {}, "sarcini": {}, "modele": {}}
    for r in rows:
        tin, tout, cost = int(r.get("intrare", 0)), int(r.get("iesire", 0)), float(r.get("cost_usd", 0))
        out["intrare"] += tin
        out["iesire"] += tout
        out["cost_usd"] += cost
        for group, key in (("aplicatii", r.get("aplicatie")), ("sarcini", r.get("sarcina")),
                           ("modele", f"{r.get('furnizor')}:{r.get('model')}")):
            g = out[group].setdefault(str(key), {"apeluri": 0, "intrare": 0, "iesire": 0, "cost_usd": 0.0})
            g["apeluri"] += 1
            g["intrare"] += tin
            g["iesire"] += tout
            g["cost_usd"] += cost
    out["buget_lunar_usd"] = load_config().monthly_budget
    return out


def _record(sarcina: str, p: cfgmod.Provider, model: str, r: RaspunsChat, cost: float) -> None:
    d = _usage_dir()
    d.mkdir(parents=True, exist_ok=True)
    line = {
        "t": datetime.now().astimezone().isoformat(timespec="seconds"),
        "aplicatie": _app["name"], "sarcina": sarcina, "furnizor": p.name, "model": model,
        "intrare": r.tokeni_intrare, "iesire": r.tokeni_iesire, "estimat": r.estimat,
        "cost_usd": round(cost, 6),
    }
    with (d / f"{datetime.now().strftime('%Y-%m')}.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")


def _check_budget(cfg: cfgmod.AIConfig, p: cfgmod.Provider) -> None:
    if cfg.monthly_budget <= 0 or p.free:
        return
    spent = sum(float(r.get("cost_usd", 0)) for r in consum())
    if spent >= cfg.monthly_budget:
        raise AIError(
            f"Bugetul lunar de {cfg.monthly_budget:g} USD a fost atins (consumat: {spent:.2f} USD). "
            f"Îl poți mări în {cfg.path}, la [buget].lunar_usd."
        )


# ---------- ritm și reîncercări ----------

def _wait_rate(p: cfgmod.Provider) -> None:
    if p.cereri_pe_minut <= 0:
        return
    gap = 60.0 / p.cereri_pe_minut
    with _rate_lock:
        last = _last_call.get(p.name)
        now = _clock()
        if last is not None and now - last < gap:
            _sleep(gap - (now - last))
            now = _clock()
        _last_call[p.name] = now


def _mentions(body: str, *words: str) -> bool:
    low = (body or "").lower()
    return any(w in low for w in words)


def _is_schema_rejection(e: ProviderHTTPError) -> bool:
    return e.status in (400, 422) and _mentions(e.body, "response_format", "json_schema", "schema",
                                                 "response format", "structured")


def _http_message(p: cfgmod.Provider, model: str, e: ProviderHTTPError) -> str:
    if e.status in (401, 403):
        return (f"Cheia pentru «{p.name}» a fost respinsă (HTTP {e.status}). "
                f"Verifică {p.cheie or 'cheia'} în {cfgmod.env_path()}.")
    if e.status == 404 or (e.status == 400 and _mentions(e.body, "model")
                           and not _mentions(e.body, "context", "too long", "token")):
        cmd = _app["models_cmd"].format(furnizor=p.name)
        return (f"Modelul «{model}» nu există sau nu mai e disponibil la «{p.name}». "
                f"Vezi modelele disponibile cu: {cmd}")
    if e.status in (400, 413) and _mentions(e.body, "context", "too long", "maximum", "token"):
        return (f"Textul e prea lung pentru contextul modelului «{model}» ({p.name}). "
                f"Împarte-l în bucăți mai mici sau alege un model cu context mai mare.")
    if e.status == 429:
        return f"Limita de rată la «{p.name}» a fost depășită și după reîncercări. Încearcă mai târziu."
    if e.status >= 500:
        return f"Furnizorul «{p.name}» are probleme (HTTP {e.status}). Încearcă mai târziu."
    detail = e.body.strip().replace("\n", " ")[:300]
    return f"Furnizorul «{p.name}» a refuzat cererea (HTTP {e.status}): {detail}"


def _network_message(p: cfgmod.Provider, e: Exception) -> str:
    if p.local:
        hint = " Ollama nu rulează? Pornește-l cu «ollama serve»." if "11434" in p.base_url else \
            " Serverul local nu rulează?"
        return f"Furnizorul local «{p.name}» nu răspunde la {p.base_url}.{hint}"
    return f"Nu pot contacta furnizorul «{p.name}» ({p.base_url}): {e}"


def _call(adaptor, p: cfgmod.Provider, cerere: CerereChat, progress) -> RaspunsChat:
    rate_tries = server_tries = 0
    while True:
        _wait_rate(p)
        try:
            return adaptor.chat(cerere)
        except ProviderHTTPError as e:
            if e.status == 429 and rate_tries < len(RATE_LIMIT_PAUSES):
                pause = e.retry_after if e.retry_after is not None else RATE_LIMIT_PAUSES[rate_tries]
                rate_tries += 1
                if progress:
                    progress(f"Limită de rată la {p.name}, reiau în {math.ceil(pause)} s")
                _sleep(pause)
                continue
            if e.status >= 500 and server_tries < len(SERVER_ERROR_PAUSES):
                pause = SERVER_ERROR_PAUSES[server_tries]
                server_tries += 1
                if progress:
                    progress(f"Eroare la {p.name} (HTTP {e.status}), reiau în {pause} s")
                _sleep(pause)
                continue
            raise
        except ProviderNetworkError:
            if server_tries < len(SERVER_ERROR_PAUSES) and not p.local:
                pause = SERVER_ERROR_PAUSES[server_tries]
                server_tries += 1
                if progress:
                    progress(f"Nu pot contacta {p.name}, reiau în {pause} s")
                _sleep(pause)
                continue
            raise


def _with_json_instruction(mesaje: list[dict], schema: dict) -> list[dict]:
    instr = ("Răspunde DOAR cu JSON valid, fără alt text și fără blocuri de cod, "
             "conform acestei scheme JSON:\n" + describe(schema))
    out = [dict(m) for m in mesaje]
    for m in out:
        if m["role"] == "system":
            m["content"] = f"{m['content']}\n\n{instr}"
            return out
    return [{"role": "system", "content": instr}] + out


# ---------- API public ----------

def ruleaza(sarcina: str, mesaje: list[dict], *, model: str | None = None,
            schema: dict | None = None, temperatura: float = 0.3,
            la_progres: Callable[[str], None] | None = None) -> Rezultat:
    cfg, p, model_name = resolve(sarcina, model)
    adaptor = _adaptor(cfg, p)
    _check_budget(cfg, p)

    msgs = _with_json_instruction(mesaje, schema) if schema is not None else [dict(m) for m in mesaje]
    if p.context_max > 0:
        need = sum(estimeaza_tokeni(m["content"]) for m in msgs)
        if need > p.context_max:
            raise AIError(
                f"Textul e prea lung pentru contextul modelului «{model_name}» ({p.name}): "
                f"~{need} tokeni, maximum {p.context_max}."
            )

    def send_schema() -> dict | None:
        if schema is None or not adaptor.accepta_schema or p.schema_json == "nu":
            return None
        if p.schema_json == "auto" and p.name in _schema_rejected:
            return None
        return schema

    def once(messages) -> RaspunsChat:
        cerere = CerereChat(model=model_name, mesaje=messages, temperatura=temperatura,
                            max_iesire=p.max_iesire, schema=send_schema())
        try:
            r = _call(adaptor, p, cerere, la_progres)
        except ProviderHTTPError as e:
            if cerere.schema is not None and p.schema_json == "auto" and _is_schema_rejection(e):
                _schema_rejected.add(p.name)
                cerere.schema = None
                try:
                    r = _call(adaptor, p, cerere, la_progres)
                except ProviderHTTPError as e2:
                    raise AIError(_http_message(p, model_name, e2)) from e2
                except ProviderNetworkError as e2:
                    raise AIError(_network_message(p, e2)) from e2
            else:
                raise AIError(_http_message(p, model_name, e)) from e
        except ProviderNetworkError as e:
            raise AIError(_network_message(p, e)) from e
        if r.estimat:
            r.tokeni_intrare = r.tokeni_intrare or sum(estimeaza_tokeni(m["content"]) for m in messages)
            r.tokeni_iesire = r.tokeni_iesire or estimeaza_tokeni(r.text)
        cost = _cost(p, r.tokeni_intrare, r.tokeni_iesire)
        _record(sarcina, p, model_name, r, cost)
        totals["in"] += r.tokeni_intrare
        totals["out"] += r.tokeni_iesire
        totals["cost"] += cost
        totals["est"] = totals["est"] or r.estimat
        return r

    totals = {"in": 0, "out": 0, "cost": 0.0, "est": False}
    r = once(msgs)
    data = None
    if schema is not None:
        try:
            data = extract_json(r.text)
            validate(data, schema)
        except SchemaError as first:
            retry = msgs + [
                {"role": "assistant", "content": r.text},
                {"role": "user", "content": (
                    f"Răspunsul anterior nu e valid: {first}. "
                    "Trimite din nou răspunsul complet, doar JSON corect conform schemei.")},
            ]
            r = once(retry)
            try:
                data = extract_json(r.text)
                validate(data, schema)
            except SchemaError as second:
                raise AIError(f"Modelul «{model_name}» nu a întors JSON valid nici a doua oară: {second}") from second
    return Rezultat(text=r.text, date=data, furnizor=p.name, model=model_name,
                    intrare=totals["in"], iesire=totals["out"], estimat=totals["est"],
                    cost_usd=totals["cost"])


def testeaza(model: str | None = None) -> Diagnostic:
    start = time.monotonic()
    try:
        cfg, p, name = resolve("test", model)
    except AIError as e:
        return Diagnostic(ok=False, mesaj=str(e))
    d = Diagnostic(ok=False, furnizor=p.name, model=name)
    if "googleapis.com" in p.base_url and p.free:
        d.note.append("Pe free tier-ul Gemini, datele trimise pot fi folosite de Google pentru "
                      "îmbunătățirea produselor (cu excepții regionale, vezi termenii lor).")
    try:
        r = ruleaza("test", [{"role": "user", "content": "Răspunde doar cu: OK"}], model=f"{p.name}:{name}",
                    temperatura=0)
        d.ok = True
        d.mesaj = f"Funcționează. Răspuns: {r.text.strip()[:80]!r}"
    except AIError as e:
        d.mesaj = str(e)
    d.durata_s = round(time.monotonic() - start, 2)
    return d
