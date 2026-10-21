"""Distribuția Linux, utilitarele de sistem opționale și comenzile de instalare.

Maparea programelor pe pachete stă în distro.toml (nu în cod).
Rulat direct, afișează sau rulează comanda de instalare:
    python -m app.system [--distro debian|fedora|arch] [--instaleaza] [--da]
"""
import argparse
import importlib.util
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

from .config import PROJECT_DIR

FAMILIES = {
    "ubuntu": "debian", "debian": "debian", "linuxmint": "debian", "pop": "debian",
    "elementary": "debian", "zorin": "debian",
    "fedora": "fedora", "rhel": "fedora", "centos": "fedora", "rocky": "fedora", "almalinux": "fedora",
    "arch": "arch", "manjaro": "arch", "endeavouros": "arch", "garuda": "arch",
}
OPTIONAL_TOOLS = ("ffmpeg", "ocrmypdf", "tesseract")


def parse_os_release(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def detect_distro(os_release: Path = Path("/etc/os-release")) -> str | None:
    """debian | fedora | arch sau None dacă distribuția nu e recunoscută."""
    try:
        info = parse_os_release(os_release.read_text(encoding="utf-8"))
    except OSError:
        return None
    candidates = [info.get("ID", "")] + info.get("ID_LIKE", "").split()
    for c in candidates:
        fam = FAMILIES.get(c.lower())
        if fam:
            return fam
    return None


def load_packages(path: Path | None = None) -> dict:
    with (path or PROJECT_DIR / "distro.toml").open("rb") as f:
        return tomllib.load(f)


def install_command(programs, distro: str, data: dict | None = None) -> str | None:
    data = data or load_packages()
    pkgs = []
    for prog in programs:
        for p in data["programe"].get(prog, {}).get(distro, []):
            if p not in pkgs:
                pkgs.append(p)
    if not pkgs or distro not in data["manageri"]:
        return None
    return f"{data['manageri'][distro]} {' '.join(pkgs)}"


def has_faster_whisper() -> bool:
    return importlib.util.find_spec("faster_whisper") is not None


def tools() -> dict:
    """Ce utilitare există, plus comenzile de instalare pentru ce lipsește."""
    distro = detect_distro()
    found = {t: shutil.which(t) is not None for t in OPTIONAL_TOOLS}
    missing = [t for t, ok in found.items() if not ok]
    data = load_packages()
    return {
        "distributie": distro,
        "programe": {t: {"disponibil": ok, "rol": data["programe"].get(t, {}).get("rol", ""),
                         "instalare": None if ok or not distro else install_command([t], distro, data)}
                     for t, ok in found.items()},
        "faster_whisper": has_faster_whisper(),
        "comanda_instalare": install_command(missing, distro, data) if missing and distro else None,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="studiu.sh --instaleaza-sistem",
                                 description="Instalează utilitarele opționale (ffmpeg, ocrmypdf, tesseract).")
    ap.add_argument("--distro", choices=["debian", "fedora", "arch"])
    ap.add_argument("--instaleaza", action="store_true", help="rulează comanda (după confirmare)")
    ap.add_argument("--da", action="store_true", help="nu mai cere confirmare")
    ap.add_argument("--venv", action="store_true", help="doar comanda pentru modulul venv")
    a = ap.parse_args(argv)
    distro = a.distro or detect_distro()
    if not distro:
        print("Nu recunosc distribuția. Rulează din nou cu --distro debian|fedora|arch.", file=sys.stderr)
        return 2
    wanted = ["venv"] if a.venv else [t for t in OPTIONAL_TOOLS if shutil.which(t) is None]
    cmd = install_command(wanted, distro)
    if not cmd:
        print("Toate utilitarele opționale sunt deja instalate.")
        return 0
    print(f"Comanda de instalare pentru {distro}:\n  {cmd}")
    if not a.instaleaza:
        return 0
    if not a.da:
        try:
            if input("Rulez comanda? [d/N] ").strip().lower() not in ("d", "da", "y", "yes"):
                print("Anulat.")
                return 0
        except EOFError:
            return 0
    return subprocess.call(cmd.split())


if __name__ == "__main__":
    sys.exit(main())
