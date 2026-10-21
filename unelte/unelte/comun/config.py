"""Configurația Unelte: ~/.config/unelte/config.toml, cu valori implicite pentru tot.

Un fișier lipsă sau gol funcționează. UNELTE_CONFIG_DIR și UNELTE_STATE pot indica alte
foldere (folosite în teste).
"""
from __future__ import annotations

import copy
import os
import tomllib
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parents[2]

DEFAULTS: dict = {
    "general": {"limba": "ro", "notificari": True, "distro": "auto"},
    "module": {"cv": False, "buget": False},
    "backup": {"interval": "1h", "fisier_max_mb": 50, "repo": [],
               "zotero": {"activ": False, "date": "~/Zotero", "destinatie": "~/Backup/zotero", "copii_pastrate": 10}},
    "organizeaza": {"surse": ["~/Descărcări", "~/Downloads"], "asteapta_minute": 2,
                    "ignora": ["*.part", "*.crdownload", "*.tmp"], "regula": []},
    "ocr": {"limbi": "ron+eng", "captura": "auto"},
    "documente": {"profil_implicit": "facultate", "bibliografie": "~/Documente/Bibliografie/biblioteca.bib"},
    "corecteaza": {"server": "http://127.0.0.1:8081", "limba": "ro-RO", "reguli_ignorate": []},
    "traduce": {},
    "rezumat": {"ora": "07:30", "iesire": "~/Notite/Rezumate", "interese": "", "max_pe_subiect": 5,
                "text_complet": False, "subiect": []},
}


class EroareUtilizare(Exception):
    """Eroare de utilizare sau de mediu: mesaj clar, cod de ieșire 2."""


def config_dir() -> Path:
    env = os.environ.get("UNELTE_CONFIG_DIR")
    if env:
        return Path(os.path.expanduser(env))
    return Path(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")) / "unelte"


def state_dir() -> Path:
    env = os.environ.get("UNELTE_STATE")
    if env:
        return Path(os.path.expanduser(env))
    return Path(os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")) / "unelte"


def config_file() -> Path:
    return config_dir() / "config.toml"


def _merge(base: dict, extra: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load(path: Path | None = None) -> dict:
    path = path or config_file()
    raw: dict = {}
    if path.exists():
        try:
            with path.open("rb") as f:
                raw = tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            raise EroareUtilizare(f"{path} nu e un fișier TOML valid: {e}") from e
    return _merge(DEFAULTS, raw)


def cale(value: str | os.PathLike) -> Path:
    return Path(os.path.expanduser(str(value)))
