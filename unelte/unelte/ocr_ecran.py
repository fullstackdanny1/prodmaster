"""ocr-ecran – text dintr-o zonă a ecranului, direct în clipboard.

Captura folosește unealta potrivită mediului grafic (grim/slurp, gnome-screenshot,
spectacle sau maim); anularea selecției (Esc) iese cu cod 0, fără mesaj.
"""
from __future__ import annotations

import re
import shutil
import struct
import tempfile
from datetime import datetime
from pathlib import Path

from . import ai
from .cli import parser
from .comun import Progres, config, fisiere, prompturi, sistem

SMALL_WIDTH = 1000


class Cancelled(Exception):
    pass


def png_width(p: Path) -> int | None:
    try:
        head = p.read_bytes()[:24]
    except OSError:
        return None
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">I", head[16:20])[0]
    return None


def capture(method: str, dest: Path) -> Path:
    if method == "grim":
        sistem.necesita("slurp")
        sistem.necesita("grim")
        sel = sistem.ruleaza(["slurp"])
        geom = (sel.stdout or "").strip()
        if sel.returncode != 0 or not geom:
            raise Cancelled()
        m = re.search(r"(\d+)x(\d+)", geom)
        scale = ["-s", "2"] if m and int(m.group(1)) < SMALL_WIDTH else []
        r = sistem.ruleaza(["grim", *scale, "-g", geom, str(dest)])
        if r.returncode != 0:
            raise config.EroareUtilizare(f"grim a eșuat: {r.stderr.strip()}")
    elif method == "gnome":
        sistem.necesita("gnome-screenshot")
        sistem.ruleaza(["gnome-screenshot", "-a", "-f", str(dest)])
    elif method == "spectacle":
        sistem.necesita("spectacle")
        sistem.ruleaza(["spectacle", "-r", "-b", "-n", "-o", str(dest)])
    elif method == "maim":
        sistem.necesita("maim")
        r = sistem.ruleaza(["maim", "-s", str(dest)])
        if r.returncode != 0:
            raise Cancelled()
    else:
        raise config.EroareUtilizare(
            "Nu am găsit o metodă de captură pentru acest mediu grafic. Fă o captură cu unealta sistemului "
            "și rulează: ocr-ecran --fisier captura.png")
    if not dest.exists() or dest.stat().st_size == 0:
        raise Cancelled()
    return dest


def ocr(image: Path, langs: str) -> str:
    sistem.necesita("tesseract")
    args = ["tesseract", str(image), "stdout", "-l", langs]
    w = png_width(image)
    if w and w < SMALL_WIDTH:
        args += ["--dpi", "300"]          # textul mic e recunoscut mai bine cu o rezoluție declarată mai mare
    r = sistem.ruleaza(args)
    if r.returncode != 0:
        err = (r.stderr or "").strip()
        if "Failed loading language" in err or "Error opening data file" in err:
            cmd = sistem.install_command(["tesseract"], sistem.distro())
            raise config.EroareUtilizare(f"Lipsesc limbile «{langs}» pentru Tesseract."
                                         + (f" Instalează-le cu: {cmd}" if cmd else ""))
        raise config.EroareUtilizare(f"tesseract a eșuat: {err[-300:]}")
    return r.stdout


_END = re.compile(r"[.!?:;…)\]»\"]$")
_LIST = re.compile(r"^\s*([-•*–]|\d+[.)])\s+")


def clean(text: str) -> str:
    """Unește rândurile rupte în mijlocul propoziției, păstrează paragrafele, elimină spațiile duble."""
    text = text.replace("\f", "\n").replace("\r", "")
    paragraphs = re.split(r"\n\s*\n", text)
    out = []
    for para in paragraphs:
        lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in para.split("\n")]
        lines = [ln for ln in lines if ln]
        if not lines:
            continue
        merged: list[str] = []
        for ln in lines:
            if not merged or _LIST.match(ln):
                merged.append(ln)
                continue
            prev = merged[-1]
            if prev.endswith("-") and len(prev) > 1 and prev[-2].isalpha() and ln[:1].islower():
                merged[-1] = prev[:-1] + ln                     # cuvânt despărțit în silabe
            elif not _END.search(prev) or ln[:1].islower():
                merged[-1] = f"{prev} {ln}"
            else:
                merged.append(ln)
        out.append("\n".join(merged))
    return "\n\n".join(out).strip() + "\n" if out else ""


def to_clipboard(text: str, tool: str | None) -> None:
    if tool == "wl-copy":
        sistem.necesita("wl-copy")
        sistem.ruleaza(["wl-copy"], input=text)
    elif tool == "xclip":
        sistem.necesita("xclip")
        sistem.ruleaza(["xclip", "-selection", "clipboard"], input=text)
    else:
        raise config.EroareUtilizare("Nu știu ce clipboard folosește acest mediu grafic.")


def correct_with_ai(text: str, model: str | None) -> str:
    progres = Progres()
    try:
        r = ai.ruleaza("corectura_ocr", prompturi.mesaje("ocr_corectare", text=text), model=model,
                       temperatura=0, la_progres=progres)
    finally:
        progres.gata()
    return r.text.strip() + "\n"


def main(argv=None) -> int:
    ap = parser("ocr-ecran", "Selectezi o zonă a ecranului, iar textul ei ajunge în clipboard.",
                "Exemple:\n  ocr-ecran\n  ocr-ecran --ai             # corectează erorile tipice de OCR\n"
                "  ocr-ecran --fisier slide.png > text.txt\n  ocr-ecran --salveaza")
    ap.add_argument("--fisier", type=Path, help="OCR pe o imagine existentă; textul la ieșirea standard")
    ap.add_argument("--brut", action="store_true", help="fără curățarea textului")
    ap.add_argument("--ai", action="store_true", help="corectează textul prin AI (fără a schimba sensul)")
    ap.add_argument("--model", help="alias sau furnizor:model pentru --ai")
    ap.add_argument("--salveaza", action="store_true", help="păstrează și captura în ~/Imagini/ocr/")
    ap.add_argument("--limbi", help="limbile Tesseract (implicit din config, ron+eng)")
    a = ap.parse_args(argv)
    cfg = config.load()
    langs = a.limbi or cfg["ocr"].get("limbi", "ron+eng")
    if a.model:
        ai.check_model_ref(a.model)

    if a.fisier:
        if not a.fisier.is_file():
            raise config.EroareUtilizare(f"Fișierul {a.fisier} nu există.")
        text = ocr(a.fisier, langs)
        text = text if a.brut else clean(text)
        if a.ai and text.strip():
            text = correct_with_ai(text, a.model)
        print(text, end="")
        return 0

    env = sistem.mediu_grafic(preferinta=cfg["ocr"].get("captura", "auto"))
    with tempfile.TemporaryDirectory(prefix="ocr-ecran-") as tmp:
        shot = Path(tmp) / "captura.png"
        try:
            capture(env["captura"], shot)
        except Cancelled:
            return 0
        text = ocr(shot, langs)
        text = text if a.brut else clean(text)
        if a.ai and text.strip():
            text = correct_with_ai(text, a.model)
        if a.salveaza:
            dest = fisiere.nume_liber(Path.home() / "Imagini" / "ocr" / f"{datetime.now():%Y-%m-%d_%H%M%S}.png")
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(shot, dest)
    if not text.strip():
        sistem.notifica("OCR", "Nu am găsit text în zona selectată.", cfg=cfg)
        print("Nu am găsit text în zona selectată.")
        return 1
    to_clipboard(text, env["clipboard"])
    preview = " ".join(text.split())[:80]
    sistem.notifica("Text copiat", preview, cfg=cfg)
    print(f"Copiat în clipboard: {preview}{'…' if len(' '.join(text.split())) > 80 else ''}")
    return 0
