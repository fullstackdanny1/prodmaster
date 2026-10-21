"""Citește config.toml (sau config.example.toml dacă nu există încă).

Un config.toml gol funcționează: fiecare opțiune are o valoare implicită.
AI-ul se configurează în fișierul comun ~/.config/ai/ai.toml (vezi app/ai/).
"""
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
PROJECT_DIR = APP_DIR.parent
VERSION = "0.2.0"

OLD_AI_KEYS = ("base_url", "model", "api_key_env", "cereri_pe_minut", "timeout_s")


@dataclass
class Config:
    notes_dir: Path
    data_dir: Path
    host: str = "127.0.0.1"
    port: int = 8765
    keep_sources: bool = True
    version_sources: bool = False
    chunk_chars: int = 12000
    ocr: bool = True
    transcription_mode: str = "local"      # local | api | dezactivat
    transcription_model: str = "small"
    transcription_language: str = "ro"
    transcription_api_model: str = "openai:whisper-1"
    cards_min: int = 2
    cards_max: int = 6
    quiz_choices: int = 4
    new_per_day: int = 20
    desired_retention: float = 0.9
    warnings: list = field(default_factory=list)

    @property
    def studiu_dir(self) -> Path:
        return self.notes_dir / ".studiu"


def _path(value: str) -> Path:
    p = Path(os.path.expanduser(value))
    return (p if p.is_absolute() else PROJECT_DIR / p).resolve()


def config_file() -> Path:
    path = Path(os.environ.get("STUDIU_CONFIG", PROJECT_DIR / "config.toml"))
    if not path.exists():
        path = PROJECT_DIR / "config.example.toml"
    return path


def load(path: Path | None = None) -> Config:
    path = path or config_file()
    raw = {}
    if path.exists():
        with path.open("rb") as f:
            raw = tomllib.load(f)
    sec = lambda name: raw.get(name) or {}  # noqa: E731
    notite, server, imp = sec("notite"), sec("server"), sec("import")
    tr, cards, rep = sec("transcriere"), sec("carduri"), sec("repetitie")
    warnings = []
    old = [k for k in OLD_AI_KEYS if k in sec("ai")]
    if old:
        warnings.append(
            f"Cheile vechi din [ai] ({', '.join(old)}) din {path.name} sunt ignorate: "
            "AI-ul se configurează acum în ~/.config/ai/ai.toml."
        )
    mode = str(tr.get("mod", "local"))
    if mode not in ("local", "api", "dezactivat"):
        warnings.append(f"[transcriere].mod = «{mode}» nu e cunoscut; folosesc «local».")
        mode = "local"
    return Config(
        notes_dir=_path(os.environ.get("STUDIU_NOTITE", notite.get("cale", "~/Notite"))),
        data_dir=_path(os.environ.get("STUDIU_DATE", notite.get("date", "data"))),
        host=str(server.get("host", "127.0.0.1")),
        port=int(server.get("port", 8765)),
        keep_sources=bool(imp.get("pastreaza_sursele", True)),
        version_sources=bool(imp.get("versioneaza_sursele", False)),
        chunk_chars=max(2000, int(imp.get("caractere_per_bucata", 12000))),
        ocr=bool(imp.get("ocr", True)),
        transcription_mode=mode,
        transcription_model=str(tr.get("model_local", "small")),
        transcription_language=str(tr.get("limba", "ro")),
        transcription_api_model=str(tr.get("model_api", "openai:whisper-1")),
        cards_min=max(1, int(cards.get("per_sectiune_min", 2))),
        cards_max=max(1, int(cards.get("per_sectiune_max", 6))),
        quiz_choices=min(6, max(2, int(cards.get("variante_quiz", 4)))),
        new_per_day=max(0, int(rep.get("carduri_noi_pe_zi", 20))),
        desired_retention=min(0.99, max(0.7, float(rep.get("retentie_dorita", 0.9)))),
        warnings=warnings,
    )


CFG = load()


def replace(new: Config) -> None:
    """Înlocuiește configurația pe loc (obiectul CFG rămâne același; folosit în teste)."""
    CFG.__dict__.update(new.__dict__)
