"""Lucrul cu folderul de notițe: arbore, citire, scriere, antet (frontmatter).

Convenții:
- Fiecare folder e o materie / un topic / un subtopic, pe oricâte niveluri.
- Fiecare fișier .md e o notiță (lecție, curs, seminar).
- Un prefix numeric în nume ("01 Curs 1.md", "02-Seminar.md") stabilește ordinea
  și nu se afișează.
- Fișierele și folderele care încep cu "." sunt ignorate.
- Antetul opțional, între linii "---", poate conține:
      titlu: Titlu afișat
      sursa: ai          (notiță generată de AI)
      verificat: false   (încă nerevizuită de tine)
"""
import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path

import yaml

from . import storage
from .config import CFG

_FM = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.S)
_PREFIX = re.compile(r"^\d+[\s._-]+(?=\S)")
_H1 = re.compile(r"^#[ \t]+(.+?)[ \t]*#*[ \t]*$", re.M)
_BAD_NAME = re.compile(r'[/\\\x00]')


class NotFound(Exception):
    pass


class Conflict(Exception):
    pass


def root() -> Path:
    return CFG.notes_dir


# ---------- antet ----------

def split_frontmatter(text: str):
    m = _FM.match(text)
    if not m:
        return {}, text
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return {}, text
    if not isinstance(meta, dict):
        return {}, text
    return meta, text[m.end():]


def join_frontmatter(meta: dict, body: str) -> str:
    if not meta:
        return body
    head = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False)
    return f"---\n{head}---\n\n{body.lstrip(chr(10))}"


def _truthy(v) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in {"true", "da", "yes", "1"}


def is_unverified(meta: dict) -> bool:
    """De revizuit: generată de AI și neverificată (rezumatele zilnice nu se revizuiesc)."""
    if is_summary(meta):
        return False
    return str(meta.get("sursa", "")).strip().lower() == "ai" and not _truthy(meta.get("verificat", False))


def is_summary(meta: dict) -> bool:
    return str(meta.get("tip", "")).strip().lower() == "rezumat"


def is_usable(meta: dict) -> bool:
    """Utilizabilă pentru carduri: nu e AI sau e verificată; rezumatele nu se folosesc."""
    if is_summary(meta):
        return False
    if str(meta.get("sursa", "")).strip().lower() != "ai":
        return True
    return _truthy(meta.get("verificat", False))


_ID_RE = re.compile(r"^[a-z0-9]{8}$")


def valid_id(value) -> bool:
    return isinstance(value, str) and bool(_ID_RE.match(value))


def jsonable(meta: dict) -> dict:
    return json.loads(json.dumps(meta, default=str))


# ---------- nume și titluri ----------

def display_name(name: str) -> str:
    stem = name[:-3] if name.lower().endswith(".md") else name
    return _PREFIX.sub("", stem) or stem


def natural_key(name: str):
    return [int(t) if t.isdigit() else t.casefold() for t in re.split(r"(\d+)", name)]


def title_of(meta: dict, body: str, filename: str) -> str:
    if meta.get("titlu"):
        return str(meta["titlu"])
    m = _H1.search(body)
    if m:
        return m.group(1).strip()
    return display_name(filename)


def has_h1(body: str) -> bool:
    return bool(_H1.search(body))


# ---------- căi sigure ----------

def resolve(rel: str) -> Path:
    """Transformă o cale relativă într-una absolută, doar în interiorul folderului de notițe."""
    rel = (rel or "").strip()
    if rel.startswith(("/", "\\", "~")):
        raise NotFound("Căile absolute nu sunt permise")
    rel = rel.strip("/")
    if any(part.startswith(".") for part in Path(rel).parts):
        raise NotFound("Cale invalidă")
    base = root().resolve()
    p = (base / rel).resolve()
    if p != base and base not in p.parents:
        raise NotFound("Cale în afara folderului de notițe")
    return p


def rel_of(p: Path) -> str:
    return p.resolve().relative_to(root().resolve()).as_posix()


def clean_name(name: str) -> str:
    name = (name or "").strip()
    if not name or name.startswith(".") or _BAD_NAME.search(name):
        raise ValueError("Nume invalid. Nu folosi '/', '\\' și nu începe cu '.'.")
    return name


# ---------- parcurgere ----------

def iter_notes():
    """Toate notițele: (cale absolută, cale relativă)."""
    base = root()
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for f in filenames:
            if f.startswith(".") or not f.lower().endswith(".md"):
                continue
            p = Path(dirpath) / f
            yield p, p.relative_to(base).as_posix()


def tree(meta_by_path: dict) -> dict:
    """Arborele complet. meta_by_path vine din index (titlu, nerevizuit, mtime)."""
    base = root()

    def walk(d: Path, rel: str) -> dict:
        dirs, notes = [], []
        try:
            entries = sorted(os.scandir(d), key=lambda e: natural_key(e.name))
        except OSError:
            entries = []
        for e in entries:
            if e.name.startswith("."):
                continue
            erel = f"{rel}/{e.name}" if rel else e.name
            if e.is_dir(follow_symlinks=False):
                dirs.append(walk(Path(e.path), erel))
            elif e.is_file() and e.name.lower().endswith(".md"):
                m = meta_by_path.get(erel, {})
                notes.append({
                    "type": "note",
                    "path": erel,
                    "title": m.get("title") or display_name(e.name),
                    "unverified": bool(m.get("unverified")),
                    "mtime": m.get("mtime", 0),
                })
        return {
            "type": "dir",
            "path": rel,
            "name": display_name(d.name) if rel else "Notițe",
            "children": dirs + notes,
            "count": len(notes) + sum(c["count"] for c in dirs),
            "unverified": sum(n["unverified"] for n in notes) + sum(c["unverified"] for c in dirs),
        }

    return walk(base, "")


# ---------- citire și scriere ----------

def crumbs(rel: str):
    parts = rel.split("/")[:-1]
    return [{"name": display_name(p), "path": "/".join(parts[: i + 1])} for i, p in enumerate(parts)]


def read_note(rel: str, render) -> dict:
    p = resolve(rel)
    if not p.is_file() or p.suffix.lower() != ".md":
        raise NotFound("Notița nu există")
    text = p.read_text(encoding="utf-8", errors="replace")
    meta, body = split_frontmatter(text)
    return {
        "path": rel_of(p),
        "title": title_of(meta, body, p.name),
        "has_h1": has_h1(body),
        "meta": jsonable(meta),
        "unverified": is_unverified(meta),
        "raw": text,
        "html": render(body),
        "mtime": p.stat().st_mtime,
        "crumbs": crumbs(rel_of(p)),
    }


def _atomic_write(p: Path, text: str):
    storage.write_text(p, text)


def save_note(rel: str, content: str, base_mtime: float | None, force: bool) -> float:
    p = resolve(rel)
    if not p.is_file():
        raise NotFound("Notița nu există")
    if not force and base_mtime is not None and abs(p.stat().st_mtime - base_mtime) > 1e-6:
        raise Conflict("Fișierul a fost modificat în altă parte între timp.")
    _atomic_write(p, content)
    return p.stat().st_mtime


def create_note(folder: str, name: str) -> str:
    d = resolve(folder)
    if not d.is_dir():
        raise NotFound("Folderul nu există")
    name = clean_name(name)
    if not name.lower().endswith(".md"):
        name += ".md"
    p = d / name
    if p.exists():
        raise ValueError("Există deja o notiță cu acest nume.")
    _atomic_write(p, f"# {display_name(name)}\n\n")
    return rel_of(p)


def create_folder(parent: str, name: str) -> str:
    d = resolve(parent)
    if not d.is_dir():
        raise NotFound("Folderul părinte nu există")
    p = d / clean_name(name)
    if p.exists():
        raise ValueError("Există deja un folder cu acest nume.")
    p.mkdir()
    return rel_of(p)


def set_verified(rel: str) -> float:
    p = resolve(rel)
    if not p.is_file():
        raise NotFound("Notița nu există")
    meta, body = split_frontmatter(p.read_text(encoding="utf-8"))
    meta["verificat"] = True
    _atomic_write(p, join_frontmatter(meta, body))
    return p.stat().st_mtime


def ensure_id(rel: str) -> str:
    """Adaugă un id în antet dacă lipsește (nu se mai schimbă niciodată). Întoarce id-ul."""
    p = resolve(rel)
    if not p.is_file():
        raise NotFound("Notița nu există")
    meta, body = split_frontmatter(p.read_text(encoding="utf-8"))
    if valid_id(meta.get("id")):
        return meta["id"]
    meta = {"id": storage.new_id(), **{k: v for k, v in meta.items() if k != "id"}}
    _atomic_write(p, join_frontmatter(meta, body))
    return meta["id"]


# ---------- nume noi ----------

_NUM = re.compile(r"^(\d+)[\s._-]+")


def next_prefix(folder: Path) -> str:
    """Prefixul numeric următor celui mai mare din folder („03” dacă există 01 și 02)."""
    nums = []
    width = 2
    try:
        for e in os.scandir(folder):
            m = _NUM.match(e.name)
            if m:
                nums.append(int(m.group(1)))
                width = max(width, len(m.group(1)))
    except OSError:
        pass
    return str(max(nums, default=0) + 1).zfill(width)


def free_path(p: Path) -> Path:
    """Nu suprascrie: „nume (2).md”, „nume (3).md” etc."""
    if not p.exists():
        return p
    stem, suffix = p.stem, p.suffix
    i = 2
    while True:
        cand = p.with_name(f"{stem} ({i}){suffix}")
        if not cand.exists():
            return cand
        i += 1


_UNSAFE = re.compile(r'[/\\\x00-\x1f:*?"<>|]+')


def safe_filename(name: str, fallback: str = "Notiță") -> str:
    name = _UNSAFE.sub(" ", name or "").strip().strip(".")
    name = re.sub(r"\s+", " ", name)[:120].strip()
    return name or fallback


def new_note_path(folder: str, name: str) -> Path:
    """Calea unei notițe noi: prefix numeric următor, fără suprascriere."""
    d = resolve(folder)
    d.mkdir(parents=True, exist_ok=True)
    name = safe_filename(name)
    if name.lower().endswith(".md"):
        name = name[:-3]
    if not _NUM.match(name):
        name = f"{next_prefix(d)} {name}"
    return free_path(d / f"{name}.md")


def write_new_note(folder: str, name: str, meta: dict, body: str) -> str:
    p = new_note_path(folder, name)
    _atomic_write(p, join_frontmatter(meta, body))
    return rel_of(p)


# ---------- mutare și coș ----------

def move(src: str, dest: str) -> str:
    """Redenumește sau mută o notiță sau un folder. dest = calea nouă completă."""
    s = resolve(src)
    if s == root().resolve():
        raise ValueError("Folderul de notițe nu poate fi mutat.")
    if not s.exists():
        raise NotFound("Notița sau folderul nu există")
    dest = (dest or "").strip().strip("/")
    if not dest:
        raise ValueError("Destinația lipsește.")
    if s.is_file() and not dest.lower().endswith(".md"):
        dest += ".md"
    for part in Path(dest).parts:
        clean_name(part)
    d = resolve(dest)
    if d.exists():
        raise ValueError("La destinație există deja un fișier sau un folder cu acest nume.")
    if s.is_dir() and (d == s or s in d.parents):
        raise ValueError("Un folder nu poate fi mutat în el însuși.")
    if not d.parent.is_dir():
        raise NotFound("Folderul destinație nu există")
    os.rename(s, d)
    return rel_of(d)


def trash(rel: str) -> str:
    """Mută notița sau folderul în .studiu/cos/<timestamp>/<cale originală>. Nu șterge nimic."""
    p = resolve(rel)
    if p == root().resolve():
        raise ValueError("Folderul de notițe nu poate fi șters.")
    if not p.exists():
        raise NotFound("Notița sau folderul nu există")
    stamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    target = storage.path("cos", stamp, rel_of(p))
    target.parent.mkdir(parents=True, exist_ok=True)
    target = free_path(target)
    shutil.move(str(p), str(target))
    return target.relative_to(root()).as_posix()
