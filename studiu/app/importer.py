"""Importul de materiale → notițe Markdown: articole web, PDF (cu OCR), audio și video.

Toate importurile rulează ca sarcini (jobs). Rezultatele parțiale (bucățile deja
transformate) stau în data/sarcini/<id>/, deci o sarcină reluată nu le reface.
"""
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

from . import ai, jobs, library, prompts, storage, system, transcriere
from .config import CFG

USER_AGENT = "Studiu/0.2 (aplicație personală de notițe; +https://github.com)"
MAX_DOWNLOAD = 10 * 1024 * 1024
MIN_ARTICLE_CHARS = 200
MIN_CHARS_PER_PAGE = 50
PDF_EXT = {".pdf"}
MEDIA_EXT = transcriere.AUDIO_EXT | transcriere.VIDEO_EXT


class ImportError_(jobs.JobError):
    pass


def kind_of(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext in PDF_EXT:
        return "pdf"
    if ext in MEDIA_EXT:
        return "media"
    raise ImportError_(f"Tip de fișier nesuportat: «{ext or filename}». Poți importa PDF, audio sau video.")


def work_dir(job_id: str) -> Path:
    return CFG.data_dir / "sarcini" / job_id


def upload_dir() -> Path:
    return CFG.data_dir / "incarcari"


def store_upload(filename: str, data: bytes) -> dict:
    """Salvează fișierul încărcat: în .studiu/surse/ (dacă se păstrează sursele) sau în data/incarcari/."""
    kind = kind_of(filename)
    sid = storage.new_id()
    ext = Path(filename).suffix.lower()
    target = storage.path("surse", f"{sid}{ext}") if CFG.keep_sources else upload_dir() / f"{sid}{ext}"
    storage.write_bytes(target, data)
    return {"sursa": sid, "fisier": str(target), "tip": kind, "nume_original": filename}


# ---------- articol web ----------

def fetch(url: str) -> str:
    if not re.match(r"^https?://", url or ""):
        raise ImportError_("Linkul trebuie să înceapă cu http:// sau https://.")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read(MAX_DOWNLOAD + 1)
            charset = r.headers.get_content_charset() or "utf-8"
    except urllib.error.HTTPError as e:
        raise ImportError_(f"Pagina a răspuns cu HTTP {e.code}.") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ImportError_(f"Nu pot descărca pagina: {getattr(e, 'reason', e)}") from e
    if len(raw) > MAX_DOWNLOAD:
        raise ImportError_("Pagina are peste 10 MB.")
    return raw.decode(charset, errors="replace")


def extract_article(html: str, url: str = "") -> tuple[str, str]:
    import trafilatura
    text = trafilatura.extract(html, url=url or None, output_format="markdown", include_tables=True,
                               include_links=True, include_formatting=True, favor_precision=True) or ""
    meta = trafilatura.extract_metadata(html, default_url=url or None)
    title = (meta.title if meta and meta.title else "") or ""
    if len(text.strip()) < MIN_ARTICLE_CHARS:
        raise ImportError_("Pagina nu are un articol care poate fi extras sau necesită autentificare.")
    return title.strip(), text.strip()


def import_article(html: str, url: str, folder: str, name: str = "") -> str:
    title, text = extract_article(html, url)
    title = title or name or "Articol"
    body = text if text.lstrip().startswith("# ") else f"# {title}\n\n{text}"
    meta = {"id": storage.new_id(), "titlu": title, "sursa": "web", "sursa_url": url,
            "generat_la": storage.now_iso()}
    return library.write_new_note(folder, name or title, meta, body.rstrip() + "\n")


@jobs.handler("import_web")
def _job_web(job: jobs.Job) -> dict:
    p = job.params
    job.progress(10, "Descarc pagina")
    html = fetch(p["url"])
    job.progress(60, "Extrag articolul")
    return {"path": import_article(html, p["url"], p.get("folder", ""), p.get("nume", ""))}


# ---------- PDF ----------

def pdf_pages(path: Path) -> tuple[list[str], dict]:
    import pymupdf
    try:
        doc = pymupdf.open(str(path))
    except Exception as e:  # noqa: BLE001 - PyMuPDF ridică tipuri variate pentru fișiere stricate
        raise ImportError_(f"PDF-ul nu poate fi citit: {e}") from e
    with doc:
        if doc.needs_pass:
            raise ImportError_("PDF-ul e protejat cu parolă.")
        pages = [page.get_text("text") for page in doc]
        meta = dict(doc.metadata or {})
    return pages, meta


def is_scanned(pages: list[str]) -> bool:
    if not pages:
        return True
    return sum(len(p.strip()) for p in pages) / len(pages) < MIN_CHARS_PER_PAGE


def ocr_missing_message() -> str:
    distro = system.detect_distro()
    cmd = system.install_command(["ocrmypdf", "tesseract"], distro) if distro else None
    return ("PDF-ul pare scanat (nu conține text). Pentru OCR e nevoie de ocrmypdf și tesseract cu limba română. "
            + (f"Instalează-le cu: {cmd}" if cmd else "Instalează pachetele ocrmypdf și tesseract (cu limba română).")
            + (" Apoi încearcă din nou." if CFG.ocr else " Activează și [import].ocr = true în config.toml."))


def run_ocr(src: Path, dest: Path) -> None:
    if not CFG.ocr or not shutil.which("ocrmypdf"):
        raise ImportError_(ocr_missing_message())
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["ocrmypdf", "-l", "ron+eng", "--force-ocr", "--output-type", "pdf", str(src), str(dest)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise ImportError_(f"OCR-ul a eșuat: {r.stderr.strip()[-300:]}")


def split_text(units: list[str], limit: int) -> list[str]:
    """Bucăți de cel mult ~limit caractere, tăiate la granițe de pagină sau de paragraf."""
    pieces: list[str] = []
    for u in units:
        u = u.strip()
        if not u:
            continue
        if len(u) <= limit:
            pieces.append(u)
            continue
        cur = ""
        for para in re.split(r"\n\s*\n", u):
            if cur and len(cur) + len(para) + 2 > limit:
                pieces.append(cur)
                cur = ""
            while len(para) > limit:
                cut = para.rfind(" ", 0, limit)
                cut = cut if cut > limit // 2 else limit
                pieces.append(para[:cut])
                para = para[cut:].lstrip()
            cur = f"{cur}\n\n{para}" if cur else para
        if cur:
            pieces.append(cur)
    chunks, cur = [], ""
    for piece in pieces:
        if cur and len(cur) + len(piece) + 2 > limit:
            chunks.append(cur)
            cur = ""
        cur = f"{cur}\n\n{piece}" if cur else piece
    if cur:
        chunks.append(cur)
    return chunks


def chunk_limit(model: str | None) -> int:
    return ai.max_chunk_chars("notite", CFG.chunk_chars, model)


def estimate_text(units: list[str], model: str | None) -> dict:
    chunks = split_text(units, chunk_limit(model))
    template = prompts.load("notite_din_text")
    tin = sum(ai.estimeaza_tokeni(template + c) for c in chunks)
    tout = sum(ai.estimeaza_tokeni(c) for c in chunks) // 2
    out = {"bucati": len(chunks), "tokeni_intrare": tin, "tokeni_iesire": tout}
    try:
        info = ai.info_model("notite", model)
        out["model"] = f"{info['furnizor']}:{info['model']}"
        out["gratuit"] = info["gratuit"] or info["local"]
        out["cost_usd"] = ai.estimeaza_cost("notite", tin, tout, model)
    except ai.AIError as e:
        out["eroare_ai"] = str(e)
    return out


def estimate_file(path: Path, model: str | None = None) -> dict:
    kind = kind_of(path.name)
    if kind == "pdf":
        pages, _meta = pdf_pages(path)
        out = {"tip": "pdf", "pagini": len(pages), "scanat": is_scanned(pages)}
        if out["scanat"]:
            out["avertisment"] = ("PDF-ul pare scanat: va fi trecut prin OCR." if CFG.ocr and shutil.which("ocrmypdf")
                                  else ocr_missing_message())
            # estimare aproximativă: ~1800 de caractere pe pagină după OCR
            out.update(estimate_text(["x" * 1800] * len(pages), model))
        else:
            out.update(estimate_text(pages, model))
        return out
    secs = transcriere.duration_seconds(path)
    out = {"tip": "media", "durata_s": secs}
    if transcriere.needs_conversion(path) and not shutil.which("ffmpeg"):
        out["avertisment"] = transcriere.ffmpeg_missing_message()
    # vorbire: ~140 de cuvinte pe minut, ~7 caractere pe cuvânt
    chars = int((secs or 600) / 60 * 140 * 7)
    out.update(estimate_text(["x" * chars], model))
    return out


def _notes_from_text(job: jobs.Job, units: list[str], title: str, folder: str, start: float) -> str:
    model = job.params.get("model")
    chunks = split_text(units, chunk_limit(model))
    if not chunks:
        raise ImportError_("Nu am găsit text de transformat în notițe.")
    wd = work_dir(job.id)
    wd.mkdir(parents=True, exist_ok=True)
    subject = library.display_name(folder.split("/")[0]) if folder else ""
    parts = []
    for k, chunk in enumerate(chunks):
        cached = wd / f"bucata-{k:03d}.md"
        pct = start + (100 - start - 2) * k / len(chunks)
        if cached.exists():
            parts.append(cached.read_text(encoding="utf-8"))
            continue
        job.progress(pct, f"Scriu notițele: bucata {k + 1} din {len(chunks)}")
        msgs = prompts.render("notite_din_text", materie=subject, titlu=title, bucata=k + 1,
                              numar_bucata=k + 1, total_bucati=len(chunks), text=chunk)
        r = ai.ruleaza("notite", msgs, model=model, la_progres=job.message)
        text = re.sub(r"^```(?:markdown|md)?\s*\n(.*?)\n```\s*$", r"\1", r.text.strip(), flags=re.S)
        storage.write_text(cached, text.strip() + "\n")
        parts.append(text.strip() + "\n")
    return f"# {title}\n\n" + "\n\n".join(p.strip() for p in parts) + "\n"


def _finish_note(job: jobs.Job, body: str, title: str, sid: str) -> dict:
    p = job.params
    meta = {"id": storage.new_id(), "titlu": title, "sursa": "ai", "verificat": False,
            "sursa_fisier": sid, "generat_la": storage.now_iso()}
    rel = library.write_new_note(p.get("folder", ""), p.get("nume") or title, meta, body)
    shutil.rmtree(work_dir(job.id), ignore_errors=True)
    if not CFG.keep_sources:
        Path(p["fisier"]).unlink(missing_ok=True)
    return {"path": rel}


def _title_from(meta_title: str, original: str) -> str:
    t = (meta_title or "").strip()
    if t and not re.fullmatch(r"(untitled|microsoft word.*|document\d*|.*\.(docx?|pptx?))", t, re.I):
        return t
    return library.display_name(Path(original).stem) or "Material importat"


@jobs.handler("import_pdf")
def _job_pdf(job: jobs.Job) -> dict:
    p = job.params
    src = Path(p["fisier"])
    if not src.exists():
        raise ImportError_("Fișierul încărcat nu mai există. Importă-l din nou.")
    job.progress(2, "Citesc PDF-ul")
    pages, meta = pdf_pages(src)
    if is_scanned(pages):
        job.progress(5, "PDF scanat: rulez OCR (poate dura câteva minute)")
        ocr_out = work_dir(job.id) / "ocr.pdf"
        if not ocr_out.exists():
            run_ocr(src, ocr_out)
        pages, _m = pdf_pages(ocr_out)
        if is_scanned(pages):
            raise ImportError_("Nici după OCR PDF-ul nu conține text lizibil.")
    sid = p["sursa"]
    storage.write_text(storage.path("surse", f"{sid}.txt"),
                       "\n\n".join(f"[pagina {i}]\n{t.strip()}" for i, t in enumerate(pages, 1)) + "\n")
    title = _title_from(meta.get("title", ""), p.get("nume_original", src.name))
    body = _notes_from_text(job, pages, title, p.get("folder", ""), 10)
    return _finish_note(job, body, title, sid)


@jobs.handler("import_media")
def _job_media(job: jobs.Job) -> dict:
    p = job.params
    src = Path(p["fisier"])
    if not src.exists():
        raise ImportError_("Fișierul încărcat nu mai există. Importă-l din nou.")
    wd = work_dir(job.id)
    sid = p["sursa"]
    txt = storage.path("surse", f"{sid}.txt")
    if not txt.exists():
        audio = src
        if transcriere.needs_conversion(src):
            job.progress(2, "Extrag sunetul cu ffmpeg")
            audio = wd / "audio.wav"
            if not audio.exists():
                try:
                    transcriere.to_wav(src, audio)
                except transcriere.TranscriptionError as e:
                    raise ImportError_(str(e)) from e
        try:
            text = transcriere.transcribe(audio, wd / "segmente",
                                          lambda pct, msg: job.progress(5 + pct * 0.45, msg))
        except transcriere.TranscriptionError as e:
            raise ImportError_(str(e)) from e
        if not text.strip():
            raise ImportError_("Transcrierea nu conține text (înregistrare fără vorbire?).")
        storage.write_text(txt, text)
    text = txt.read_text(encoding="utf-8")
    title = _title_from("", p.get("nume_original", src.name))
    body = _notes_from_text(job, re.split(r"\n\s*\n", text), title, p.get("folder", ""), 50)
    return _finish_note(job, body, title, sid)
