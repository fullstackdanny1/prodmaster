"""Pașii lui install.sh scriși în Python (doar biblioteca standard):

    python -m unelte.instalare config            # fișierele de configurare (fără suprascriere)
    python -m unelte.instalare lansatoare DIR     # scripturile din ~/.local/bin
    python -m unelte.instalare unitati DIR        # unitățile systemd de utilizator
    python -m unelte.instalare pachete [--distro X] [--da]
    python -m unelte.instalare languagetool [--da]
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import stat
import subprocess
import sys
import tomllib
import urllib.request
import zipfile
from pathlib import Path

from .comun import config, sistem

REPO = config.REPO_DIR
COMMANDS = ["backup", "organizeaza", "ocr-ecran", "converteste", "verifica-format", "corecteaza", "traduce",
            "rezumat", "unelte"]
DEFERRED = ["cv", "buget"]
TIMERS = ["unelte-backup.timer", "unelte-organizeaza.timer", "unelte-rezumat.timer"]
SERVICES = ["unelte-languagetool.service"]
NEEDED = {   # program → comenzile care au nevoie de el
    "git": "backup", "pandoc": "converteste", "soffice": "converteste --pdf", "tesseract": "ocr-ecran",
    "notify-send": "notificări", "java": "corecteaza",
}


def ai_dir() -> Path:
    env = os.environ.get("AI_CONFIG")
    if env:
        return Path(env).parent
    return Path(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")) / "ai"


def lt_dir() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")) / "unelte" / "languagetool"


def _copy_if_missing(src: Path, dest: Path, mode: int | None = None) -> bool:
    if dest.exists():
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)
    if mode is not None:
        dest.chmod(mode)
    return True


def _write_if_missing(dest: Path, text: str, mode: int | None = None) -> bool:
    if dest.exists():
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode or 0o644)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    return True


def setup_config() -> list[str]:
    """Creează fișierele de configurare care lipsesc. Nu suprascrie niciodată."""
    made = []
    cd = config.config_dir()
    if _copy_if_missing(REPO / "config.example.toml", cd / "config.toml"):
        made.append(str(cd / "config.toml"))
    if _write_if_missing(cd / "dictionar.txt", "# Dicționarul personal pentru corecteaza: un cuvânt pe linie.\n"):
        made.append(str(cd / "dictionar.txt"))
    if _write_if_missing(cd / "glosar.toml", "# Glosarul pentru traduce: o secțiune per limbă țintă.\n"
                         "# [en]\n# \"active circulante\" = \"current assets\"\n"):
        made.append(str(cd / "glosar.toml"))
    ad = ai_dir()
    if _copy_if_missing(REPO / "ai.example.toml", ad / "ai.toml"):
        made.append(str(ad / "ai.toml"))
    env = ad / ".env"
    if _write_if_missing(env, "# Cheile AI (NUME=valoare), comune pentru Studiu și Unelte. Exemplu:\n"
                         "# GEMINI_API_KEY=cheia-din-google-ai-studio\n", 0o600):
        made.append(str(env))
    env.chmod(0o600)
    return made


def launchers(bindir: Path, python: str) -> list[str]:
    cfg = config.load()
    bindir.mkdir(parents=True, exist_ok=True)
    wanted = COMMANDS + [c for c in DEFERRED if cfg["module"].get(c)]
    made = []
    for name in wanted:
        sub = "" if name == "unelte" else f" {name}"
        text = f'#!/bin/sh\n# Generat de install.sh (Unelte)\nexec "{python}" -m unelte{sub} "$@"\n'
        p = bindir / name
        if p.exists() and p.read_text(errors="replace") == text:
            continue
        if p.exists() and "Generat de install.sh (Unelte)" not in p.read_text(errors="replace"):
            print(f"Atenție: {p} există și nu e un lansator Unelte; nu îl înlocuiesc.", file=sys.stderr)
            continue
        p.write_text(text, encoding="utf-8")
        p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        made.append(name)
    for name in DEFERRED:
        p = bindir / name
        if not cfg["module"].get(name) and p.exists() and "Generat de install.sh (Unelte)" in p.read_text(errors="replace"):
            p.unlink()
    return made


def calendar(interval: str) -> str:
    """„30m” → *:0/30, „1h” → hourly, „2h” → 0/2:00, „1d” → daily."""
    m = re.fullmatch(r"\s*(\d+)\s*([mhd])\s*", interval or "1h")
    if not m:
        raise config.EroareUtilizare(f"[backup].interval = «{interval}» nu e valid (exemple: 30m, 1h, 2h, 1d).")
    n, unit = int(m.group(1)), m.group(2)
    if unit == "m":
        return f"*:0/{n}" if n < 60 else calendar(f"{n // 60}h")
    if unit == "h":
        return "hourly" if n == 1 else f"0/{n}:00"
    return "daily" if n == 1 else f"*-*-1/{n} 00:00"


def units(dest: Path, python: str) -> list[str]:
    cfg = config.load()
    ora = str(cfg["rezumat"].get("ora", "07:30"))
    if not re.fullmatch(r"\d{1,2}:\d{2}", ora):
        raise config.EroareUtilizare(f"[rezumat].ora = «{ora}» nu e validă (de exemplu 07:30).")
    values = {"@PYTHON@": python, "@REPO@": str(REPO), "@BACKUP_CALENDAR@": calendar(cfg["backup"].get("interval", "1h")),
              "@REZUMAT_ORA@": ora, "@JAVA@": shutil.which("java") or "/usr/bin/java", "@LT_DIR@": str(lt_dir() / "current")}
    dest.mkdir(parents=True, exist_ok=True)
    changed = []
    for src in sorted((REPO / "systemd").iterdir()):
        text = src.read_text(encoding="utf-8")
        for k, v in values.items():
            text = text.replace(k, v)
        out = dest / src.name
        if not out.exists() or out.read_text(encoding="utf-8") != text:
            out.write_text(text, encoding="utf-8")
            changed.append(src.name)
    return changed


def missing_programs() -> dict[str, str]:
    return {p: why for p, why in NEEDED.items() if not sistem.exista(p)}


def capture_programs() -> list[str]:
    env = sistem.mediu_grafic(preferinta=config.load()["ocr"].get("captura", "auto"))
    tool = env["captura"]
    progs = list(sistem.CAPTURE_TOOLS.get(tool, {}).get("programe", []))
    if env["clipboard"]:
        progs.append(env["clipboard"])
    return [p for p in progs if not sistem.exista(p)]


def packages(distro: str | None, yes: bool) -> int:
    distro = distro or sistem.distro()
    if not distro:
        print("Nu recunosc distribuția. Rulează din nou cu --distro debian|fedora|arch.", file=sys.stderr)
        return 2
    missing = missing_programs()
    for p in capture_programs():
        missing.setdefault(p, "ocr-ecran")
    if not missing:
        print("Toate programele de sistem sunt instalate.")
        return 0
    groups: dict[str, list[str]] = {}
    for prog, cmd in missing.items():
        groups.setdefault(cmd, []).append(prog)
    print("Programe de sistem lipsă:")
    for cmd, progs in groups.items():
        print(f"  {cmd:<22} {', '.join(progs)}")
    command = sistem.install_command(list(missing), distro)
    if not command:
        return 0
    print(f"\nComanda de instalare ({distro}):\n  {command}")
    if not yes:
        if not sys.stdin.isatty():
            print("(rulează-o manual sau ./install.sh --da)")
            return 0
        try:
            if input("Rulez comanda acum? [d/N] ").strip().lower() not in ("d", "da", "y", "yes"):
                return 0
        except EOFError:
            return 0
    return subprocess.call(command.split())


def languagetool(yes: bool) -> int:
    with (REPO / "languagetool.toml").open("rb") as f:
        lt = tomllib.load(f)
    version, url, expected = lt["versiune"], lt["url"], (lt.get("sha256") or "").strip().lower()
    base = lt_dir()
    target = base / version
    current = base / "current"
    if (target / "languagetool-server.jar").exists():
        if not current.exists() or current.resolve() != target.resolve():
            if current.is_symlink() or current.exists():
                current.unlink()
            current.symlink_to(target)
        print(f"LanguageTool {version} e deja instalat.")
        return 0
    if not sistem.exista("java"):
        cmd = sistem.install_command(["java"], sistem.distro())
        print("LanguageTool are nevoie de Java." + (f" Instalează-l cu: {cmd}" if cmd else ""), file=sys.stderr)
    base.mkdir(parents=True, exist_ok=True)
    archive = base / f"LanguageTool-{version}.zip"
    print(f"Descarc LanguageTool {version} (~250 MB)…")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Unelte-install"})
        with urllib.request.urlopen(req, timeout=60) as r, archive.open("wb") as f:
            shutil.copyfileobj(r, f, 1024 * 1024)
    except (OSError, ValueError) as e:
        archive.unlink(missing_ok=True)
        print(f"Nu am putut descărca LanguageTool: {e}. Reîncearcă mai târziu cu ./install.sh.", file=sys.stderr)
        return 1
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    if expected and digest != expected:
        archive.unlink()
        print(f"Suma de control nu corespunde (așteptat {expected}, primit {digest}). Arhiva a fost ștearsă.",
              file=sys.stderr)
        return 1
    if not expected:
        print(f"SHA-256 al arhivei descărcate: {digest}")
        print("languagetool.toml nu are o sumă fixată. Compar-o cu cea publicată și copiaz-o în languagetool.toml.")
        if not yes:
            try:
                ok = sys.stdin.isatty() and input("Folosesc arhiva? [d/N] ").strip().lower() in ("d", "da", "y", "yes")
            except EOFError:
                ok = False
            if not ok:
                archive.unlink()
                print("Anulat (arhiva a fost ștearsă).")
                return 1
    tmp = base / f".{version}.tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    with zipfile.ZipFile(archive) as z:
        z.extractall(tmp)
    inner = next((p for p in tmp.iterdir() if p.is_dir() and (p / "languagetool-server.jar").exists()), tmp)
    shutil.rmtree(target, ignore_errors=True)
    inner.rename(target)
    shutil.rmtree(tmp, ignore_errors=True)
    archive.unlink()
    if current.is_symlink() or current.exists():
        current.unlink()
    current.symlink_to(target)
    print(f"LanguageTool {version} instalat în {target}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m unelte.instalare")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("config")
    l_ = sub.add_parser("lansatoare")
    l_.add_argument("dir", type=Path)
    l_.add_argument("--python", default=sys.executable)
    u = sub.add_parser("unitati")
    u.add_argument("dir", type=Path)
    u.add_argument("--python", default=sys.executable)
    p = sub.add_parser("pachete")
    p.add_argument("--distro", choices=["debian", "fedora", "arch"])
    p.add_argument("--da", action="store_true")
    t = sub.add_parser("languagetool")
    t.add_argument("--da", action="store_true")
    sub.add_parser("timere")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "config":
            for f in setup_config():
                print(f"Creat: {f}")
            return 0
        if a.cmd == "lansatoare":
            made = launchers(a.dir, a.python)
            if made:
                print(f"Lansatoare în {a.dir}: {', '.join(made)}")
            return 0
        if a.cmd == "unitati":
            for n in units(a.dir, a.python):
                print(f"Unitate systemd: {n}")
            return 0
        if a.cmd == "timere":
            print(" ".join(TIMERS))
            return 0
        if a.cmd == "pachete":
            return packages(a.distro, a.da)
        return languagetool(a.da)
    except config.EroareUtilizare as e:
        print(f"Eroare: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
