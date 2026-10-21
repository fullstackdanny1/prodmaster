"""Prompturile stau ca fișiere text: app/prompts/<nume>.md, cu suprascrieri în
<notițe>/.studiu/prompturi/<nume>.md (au prioritate, deci supraviețuiesc actualizărilor).

Substituția înlocuiește doar {nume_simplu}; cheile lipsă devin șir gol, iar alte acolade
(JSON, {{c1::...}}) rămân neatinse.
"""
import re

from . import storage
from .config import APP_DIR

_VAR = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


def path_of(name: str):
    custom = storage.path("prompturi", f"{name}.md")
    return custom if custom.is_file() else APP_DIR / "prompts" / f"{name}.md"


def load(name: str) -> str:
    return path_of(name).read_text(encoding="utf-8")


def fill(template: str, values: dict) -> str:
    return _VAR.sub(lambda m: str(values.get(m.group(1), "")), template)


def render(name: str, **values) -> list[dict]:
    """Promptul ca mesaje: textul de dinaintea liniei „---user---” e mesajul system."""
    text = fill(load(name), values)
    if "\n---user---\n" in text:
        system, user = text.split("\n---user---\n", 1)
        return [{"role": "system", "content": system.strip()}, {"role": "user", "content": user.strip()}]
    return [{"role": "user", "content": text.strip()}]
