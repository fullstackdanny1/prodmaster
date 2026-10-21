"""Programe de sistem, distribuția, mediul grafic, notificări și rularea proceselor.

`ruleaza` e singurul punct prin care se pornesc procese externe, ca testele să-l poată
înlocui și să verifice argumentele.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tomllib
from pathlib import Path

from . import config

FAMILIES = {
    "ubuntu": "debian", "debian": "debian", "linuxmint": "debian", "pop": "debian",
    "elementary": "debian", "zorin": "debian",
    "fedora": "fedora", "rhel": "fedora", "centos": "fedora", "rocky": "fedora", "almalinux": "fedora",
    "arch": "arch", "manjaro": "arch", "endeavouros": "arch", "garuda": "arch",
}


def parse_os_release(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def detect_distro(os_release: Path = Path("/etc/os-release")) -> str | None:
    try:
        info = parse_os_release(os_release.read_text(encoding="utf-8"))
    except OSError:
        return None
    for c in [info.get("ID", "")] + info.get("ID_LIKE", "").split():
        fam = FAMILIES.get(c.lower())
        if fam:
            return fam
    return None


def distro(cfg: dict | None = None) -> str | None:
    chosen = str(((cfg or config.load()).get("general") or {}).get("distro", "auto"))
    return chosen if chosen in ("debian", "fedora", "arch") else detect_distro()


def packages(path: Path | None = None) -> dict:
    with (path or config.REPO_DIR / "distro.toml").open("rb") as f:
        return tomllib.load(f)


def install_command(programs, distro_name: str | None, data: dict | None = None) -> str | None:
    if not distro_name:
        return None
    data = data or packages()
    pkgs: list[str] = []
    for prog in programs:
        for p in data["programe"].get(prog, {}).get(distro_name, []):
            if p not in pkgs:
                pkgs.append(p)
    if not pkgs:
        return None
    return f"{data['manageri'][distro_name]} {' '.join(pkgs)}"


def exista(program: str) -> bool:
    return shutil.which(program) is not None


def necesita(program: str) -> str:
    """Calea programului sau EroareUtilizare cu comanda de instalare pentru distribuția ta."""
    path = shutil.which(program)
    if path:
        return path
    cmd = install_command([program], distro())
    hint = f" Instalează-l cu: {cmd}" if cmd else " Instalează-l din managerul de pachete al distribuției."
    raise config.EroareUtilizare(f"Lipsește programul «{program}».{hint}")


def ruleaza(args: list[str], *, input: str | bytes | None = None, check: bool = False,
            capture: bool = True, cwd: str | os.PathLike | None = None, env: dict | None = None,
            timeout: float | None = None, text: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(args, input=input, check=check, capture_output=capture, cwd=cwd, env=env,
                          timeout=timeout, text=text)


def notifica(titlu: str, mesaj: str, urgent: bool = False, cfg: dict | None = None) -> None:
    """notify-send; ignorat silențios dacă lipsește sau dacă notificările sunt oprite."""
    try:
        if not (cfg or config.load())["general"].get("notificari", True):
            return
    except config.EroareUtilizare:
        return
    if not exista("notify-send"):
        return
    args = ["notify-send", "-a", "Unelte"] + (["-u", "critical"] if urgent else []) + [titlu, mesaj[:300]]
    try:
        ruleaza(args, timeout=10)
    except (OSError, subprocess.SubprocessError):
        pass


def proces_ruleaza(name: str) -> bool:
    """Există un proces cu acest nume (citit din /proc, fără dependențe)?"""
    proc = Path("/proc")
    if not proc.is_dir():
        return False
    for d in proc.iterdir():
        if not d.name.isdigit():
            continue
        try:
            comm = (d / "comm").read_text().strip()
        except OSError:
            continue
        if comm == name or comm.startswith(name):
            return True
    return False


# ---------- mediul grafic ----------

CAPTURE_TOOLS = {
    "grim": {"programe": ["slurp", "grim"], "clipboard": "wl-copy"},
    "gnome": {"programe": ["gnome-screenshot"], "clipboard": "wl-copy"},
    "spectacle": {"programe": ["spectacle"], "clipboard": "wl-copy"},
    "maim": {"programe": ["maim"], "clipboard": "xclip"},
}


def mediu_grafic(env: dict | None = None, preferinta: str = "auto") -> dict:
    """Alege metoda de captură și clipboard-ul după XDG_SESSION_TYPE, XDG_CURRENT_DESKTOP, SWAYSOCK."""
    env = dict(os.environ if env is None else env)
    session = env.get("XDG_SESSION_TYPE", "").lower()
    desktop = env.get("XDG_CURRENT_DESKTOP", "").lower()
    wayland = session == "wayland" or bool(env.get("WAYLAND_DISPLAY")) or bool(env.get("SWAYSOCK"))
    if wayland:
        if "gnome" in desktop or "ubuntu" in desktop:
            kind, tool = "Wayland, GNOME", "gnome"
        elif "kde" in desktop or "plasma" in desktop:
            kind, tool = "Wayland, KDE Plasma", "spectacle"
        else:
            name = "sway" if env.get("SWAYSOCK") else (desktop or "wlroots")
            kind, tool = f"Wayland, {name}", "grim"
    elif session == "x11" or env.get("DISPLAY"):
        kind, tool = "X11", "maim"
    else:
        kind, tool = "fără mediu grafic", None
    if preferinta and preferinta != "auto":
        tool = preferinta
    clip = CAPTURE_TOOLS[tool]["clipboard"] if tool in CAPTURE_TOOLS else None
    if tool == "maim" or (preferinta == "auto" and kind == "X11"):
        clip = "xclip"
    return {"mediu": kind, "captura": tool, "clipboard": clip}
