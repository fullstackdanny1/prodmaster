"""Scriere atomică, nume fără suprascriere, potrivire fără diacritice."""
from __future__ import annotations

import os
import tempfile
import unicodedata
from pathlib import Path


def nume_liber(cale: str | os.PathLike) -> Path:
    """„nume.ext” sau, dacă există, „nume (2).ext”, „nume (3).ext” etc."""
    p = Path(cale)
    if not p.exists():
        return p
    i = 2
    while True:
        cand = p.with_name(f"{p.stem} ({i}){p.suffix}")
        if not cand.exists():
            return cand
        i += 1


def scrie_atomic(cale: str | os.PathLike, continut: str | bytes) -> Path:
    p = Path(cale)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=f".{p.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb" if isinstance(continut, bytes) else "w",
                       **({} if isinstance(continut, bytes) else {"encoding": "utf-8"})) as f:
            f.write(continut)
        os.replace(tmp, p)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return p


def fara_diacritice(text: str) -> str:
    norm = unicodedata.normalize("NFKD", text)
    return "".join(c for c in norm if not unicodedata.combining(c)).casefold()


def rezultat(sursa: Path, sufix: str, ext: str | None = None) -> Path:
    """Calea unui fișier rezultat lângă sursă: raport.md → raport.corectat.md (fără suprascriere)."""
    ext = ext if ext is not None else sursa.suffix
    return nume_liber(sursa.with_name(f"{sursa.stem}.{sufix}{ext}"))
