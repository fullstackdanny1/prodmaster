"""Datele aplicației din <notițe>/.studiu/: fișiere JSON și JSONL, scrise atomic.

Tot ce contează stă aici (versionabil cu Git); data/ e doar cache.
"""
import json
import os
import secrets
import string
import tempfile
from datetime import datetime
from pathlib import Path

from .config import CFG

SUBDIRS = ("carduri", "repetitii", "examene", "surse", "prompturi", "cos")
BINARY_SOURCE_PATTERNS = ("surse/*.pdf", "surse/*.mp3", "surse/*.mp4", "surse/*.m4a", "surse/*.wav",
                          "surse/*.ogg", "surse/*.opus", "surse/*.webm", "surse/*.mkv", "surse/*.mov",
                          "surse/*.avi", "surse/*.flac", "surse/*.aac")
_ID_CHARS = string.ascii_lowercase + string.digits


def root() -> Path:
    return CFG.studiu_dir


def path(*parts: str) -> Path:
    return root().joinpath(*parts)


def new_id(n: int = 8) -> str:
    return "".join(secrets.choice(_ID_CHARS) for _ in range(n))


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def ensure() -> None:
    """Creează .studiu/ și subfolderele; actualizează .gitignore după [import]."""
    for d in SUBDIRS:
        path(d).mkdir(parents=True, exist_ok=True)
    lines = ["# Generat de Studiu. Fișierele temporare nu se versionează.", ".studiu-*.tmp"]
    if not CFG.version_sources:
        lines += ["# [import].versioneaza_sursele = false: sursele binare nu intră în Git."]
        lines += list(BINARY_SOURCE_PATTERNS)
    text = "\n".join(lines) + "\n"
    gi = path(".gitignore")
    try:
        current = gi.read_text(encoding="utf-8")
    except OSError:
        current = None
    if current != text:
        write_text(gi, text)


def write_text(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".studiu-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, p)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def write_bytes(p: Path, data: bytes) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".studiu-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, p)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def write_json(p: Path, value) -> None:
    write_text(p, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def read_json(p: Path, default=None):
    try:
        with p.open(encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def append_jsonl(p: Path, value: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n"
    with p.open("a", encoding="utf-8") as f:
        f.write(line)
        f.flush()
        os.fsync(f.fileno())


def read_jsonl(p: Path) -> list[dict]:
    out = []
    try:
        with p.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue       # o linie stricată (de exemplu un conflict Git) nu oprește restul
    except OSError:
        pass
    return out
