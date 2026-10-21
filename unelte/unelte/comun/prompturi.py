"""Prompturile: implicite în prompturi/<nume>.md, personalizate în
~/.config/unelte/prompturi/<nume>.md (au prioritate).

Substituția înlocuiește doar {nume_simplu}; cheile lipsă devin șir gol, iar alte
acolade (JSON) rămân neatinse. Textul de dinaintea liniei „---user---” e mesajul system.
"""
from __future__ import annotations

import re

from . import config

_VAR = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


def citeste(nume: str) -> str:
    custom = config.config_dir() / "prompturi" / f"{nume}.md"
    p = custom if custom.is_file() else config.REPO_DIR / "prompturi" / f"{nume}.md"
    return p.read_text(encoding="utf-8")


def completeaza(text: str, valori: dict) -> str:
    return _VAR.sub(lambda m: str(valori.get(m.group(1), "")), text)


def mesaje(nume: str, **valori) -> list[dict]:
    text = completeaza(citeste(nume), valori)
    if "\n---user---\n" in text:
        system, user = text.split("\n---user---\n", 1)
        return [{"role": "system", "content": system.strip()}, {"role": "user", "content": user.strip()}]
    return [{"role": "user", "content": text.strip()}]
