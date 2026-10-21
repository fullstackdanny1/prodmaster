"""Profilurile de documente: ~/.config/unelte/profiluri/<nume>/, apoi profiluri/<nume>/ din repo."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from . import config

DEFAULTS = {
    "pagina": {"format": "A4", "margini_cm": {"sus": 2.5, "jos": 2.5, "stanga": 3.0, "dreapta": 2.0},
               "numerotare": True},
    "text": {"font": "Times New Roman", "marime_pt": 12, "spatiere_rand": 1.5, "aliniere": "justify",
             "indent_prima_linie_cm": 1.25},
    "titluri": {"font": "Times New Roman", "marimi_pt": [16, 14, 12], "numerotate": False},
    "figuri": {"legenda_obligatorie": True},
    "citari": {"stil": "stil.csl", "bibliografie_obligatorie": False, "titlu_bibliografie": "Bibliografie"},
    "pagina_titlu": {"activa": False, "campuri": []},
}


@dataclass
class Profil:
    nume: str
    dir: Path
    reguli: dict

    def fisier(self, rel: str) -> Path:
        return self.dir / rel

    @property
    def reference(self) -> Path:
        return self.dir / "reference.docx"

    @property
    def csl(self) -> Path:
        return self.dir / self.reguli["citari"].get("stil", "stil.csl")

    @property
    def filtru_titlu(self) -> Path:
        return self.dir / "pagina-titlu.lua"


def gaseste(nume: str) -> Path:
    for base in (config.config_dir() / "profiluri", config.REPO_DIR / "profiluri"):
        d = base / nume
        if (d / "profil.toml").is_file():
            return d
    raise config.EroareUtilizare(
        f"Profilul «{nume}» nu există (caut în {config.config_dir() / 'profiluri'} și în profiluri/ din repo).")


def incarca(nume: str | None = None, cfg: dict | None = None) -> Profil:
    cfg = cfg or config.load()
    nume = nume or cfg["documente"].get("profil_implicit", "facultate")
    d = gaseste(nume)
    try:
        with (d / "profil.toml").open("rb") as f:
            raw = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise config.EroareUtilizare(f"{d / 'profil.toml'} nu e TOML valid: {e}") from e
    reguli = {k: {**v, **raw.get(k, {})} if isinstance(v, dict) else raw.get(k, v) for k, v in DEFAULTS.items()}
    reguli["pagina"]["margini_cm"] = {**DEFAULTS["pagina"]["margini_cm"],
                                      **raw.get("pagina", {}).get("margini_cm", {})}
    reguli["nume"] = raw.get("nume", nume)
    return Profil(nume=nume, dir=d, reguli=reguli)
