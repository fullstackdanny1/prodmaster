"""Serverul web al aplicației Studiu (rulează doar local).

Toată logica stă în backend, expusă prin API JSON; interfața web e doar un client.
"""
import logging
import shutil
import tempfile
import threading
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import (ai, cache, cards, chat, importer, index, jobs, library, quiz, reviews, srs, storage,
               system)
from .config import APP_DIR, CFG, VERSION
from .render import render

FILE_TYPES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".pdf"}
log = logging.getLogger("studiu")
_refresh_lock = threading.Lock()


def setup_logging() -> None:
    CFG.data_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger("studiu")
    if any(isinstance(h, RotatingFileHandler) for h in root.handlers):
        return
    h = RotatingFileHandler(CFG.data_dir / "studiu.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(h)
    root.setLevel(logging.INFO)


def refresh() -> None:
    """Sincronizează cache-ul cu fișierele: notițe, secțiuni, carduri, istoricul repetițiilor."""
    with _refresh_lock:
        changed = index.sync()
        if changed:
            cards.sync_notes(changed)
            index.sync()            # id-urile adăugate pentru cardurile manuale
        cards.sync_cache()


def startup() -> None:
    setup_logging()
    for w in CFG.warnings:
        log.warning(w)
    cfg = ai.load_config()
    for e in cfg.errors:
        log.warning("ai.toml: %s", e)
    CFG.notes_dir.mkdir(parents=True, exist_ok=True)
    storage.ensure()
    refresh()
    reviews.sync()
    n = jobs.mark_interrupted()
    if n:
        log.warning("%d sarcini întrerupte la oprirea anterioară", n)


@asynccontextmanager
async def lifespan(_app):
    startup()
    yield


app = FastAPI(title="Studiu", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")


def _guard(fn, *args, **kw):
    try:
        return fn(*args, **kw)
    except library.NotFound as e:
        raise HTTPException(404, str(e))
    except library.Conflict as e:
        raise HTTPException(409, str(e))
    except ai.AIError as e:
        raise HTTPException(502, str(e))
    except (jobs.JobError, ValueError) as e:
        raise HTTPException(400, str(e))
    except KeyError:
        raise HTTPException(404, "Nu există")


def _check_model(model: str | None) -> str | None:
    model = (model or "").strip() or None
    if model:
        try:
            ai.check_model_ref(model)
        except ai.AIError as e:
            raise HTTPException(400, str(e))
    return model


@app.get("/")
def home():
    return FileResponse(APP_DIR / "static" / "index.html")


# ---------- bibliotecă ----------

@app.get("/api/arbore")
def arbore():
    refresh()
    return {"tree": library.tree(index.meta_by_path()), "root": str(CFG.notes_dir)}


@app.get("/api/notita")
def get_note(path: str):
    refresh()
    return _guard(library.read_note, path, render)


class SaveBody(BaseModel):
    path: str
    content: str
    mtime: float | None = None
    force: bool = False


def _keep_id(rel: str, content: str) -> str:
    """Editorul nu poate pierde id-ul notiței: îl păstrăm de pe disc dacă lipsește din text."""
    p = library.resolve(rel)
    old_meta, _ = library.split_frontmatter(p.read_text(encoding="utf-8", errors="replace"))
    if not library.valid_id(old_meta.get("id")):
        return content
    meta, body = library.split_frontmatter(content)
    if library.valid_id(meta.get("id")):
        return content
    return library.join_frontmatter({"id": old_meta["id"], **meta}, body)


@app.put("/api/notita")
def put_note(b: SaveBody):
    content = _guard(_keep_id, b.path, b.content)
    _guard(library.save_note, b.path, content, b.mtime, b.force)
    refresh()
    p = library.resolve(b.path)
    raw = p.read_text(encoding="utf-8")
    return {"ok": True, "mtime": p.stat().st_mtime, "raw": raw if raw != b.content else None}


class CreateBody(BaseModel):
    parent: str = ""
    name: str


@app.post("/api/notita")
def new_note(b: CreateBody):
    rel = _guard(library.create_note, b.parent, b.name)
    refresh()
    return {"path": rel}


@app.post("/api/folder")
def new_folder(b: CreateBody):
    return {"path": _guard(library.create_folder, b.parent, b.name)}


class PathBody(BaseModel):
    path: str


@app.post("/api/notita/verificat")
def verify(b: PathBody):
    mtime = _guard(library.set_verified, b.path)
    refresh()
    return {"ok": True, "mtime": mtime}


class MoveBody(BaseModel):
    path: str
    destinatie: str


@app.post("/api/notita/mutare")
def move(b: MoveBody):
    rel = _guard(library.move, b.path, b.destinatie)
    refresh()
    return {"path": rel}


@app.post("/api/notita/stergere")
def delete(b: PathBody):
    where = _guard(library.trash, b.path)
    refresh()
    return {"ok": True, "cos": where}


class RenderBody(BaseModel):
    content: str


@app.post("/api/randare")
def preview(b: RenderBody):
    _meta, body = library.split_frontmatter(b.content)
    return {"html": render(body)}


@app.get("/api/cautare")
def cautare(q: str, scope: str = ""):
    refresh()
    return index.search(q, scope)


@app.get("/api/fisier")
def fisier(path: str):
    p = _guard(library.resolve, path)
    if not p.is_file() or p.suffix.lower() not in FILE_TYPES:
        raise HTTPException(404, "Fișier indisponibil")
    return FileResponse(p, headers={"Content-Security-Policy": "sandbox"})


@app.get("/api/sursa/{sid}")
def source_text(sid: str):
    if not library.valid_id(sid):
        raise HTTPException(404, "Sursa nu există")
    p = storage.path("surse", f"{sid}.txt")
    if not p.is_file():
        raise HTTPException(404, "Sursa nu există")
    return {"id": sid, "text": p.read_text(encoding="utf-8", errors="replace")}


@app.get("/api/revizuit")
def to_review():
    refresh()
    return {"notite": index.unverified_notes(), "carduri_orfane": cards.orphans()}


# ---------- import ----------

async def _import_input(request: Request) -> dict:
    ctype = request.headers.get("content-type", "")
    if ctype.startswith("multipart/form-data"):
        form = await request.form()
        upload = form.get("fisier")
        fields = {k: str(v) for k, v in form.items() if k != "fisier"}
        if upload is None or not getattr(upload, "filename", ""):
            if fields.get("url"):
                return fields
            raise HTTPException(400, "Alege un fișier sau scrie un link.")
        fields["_upload"] = upload
        return fields
    try:
        return await request.json()
    except ValueError:
        raise HTTPException(400, "Cerere invalidă.")


@app.post("/api/import/estimare")
async def import_estimate(request: Request):
    data = await _import_input(request)
    model = _check_model(data.get("model"))
    if data.get("url") and "_upload" not in data:
        return {"tip": "web", "tokeni_intrare": 0, "tokeni_iesire": 0, "cost_usd": 0, "gratuit": True,
                "nota": "Articolele web se importă fără AI."}
    upload = data["_upload"]
    _guard(importer.kind_of, upload.filename)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / Path(upload.filename).name
        with path.open("wb") as f:
            shutil.copyfileobj(upload.file, f)
        return _guard(importer.estimate_file, path, model)


@app.post("/api/import")
async def import_start(request: Request):
    data = await _import_input(request)
    model = _check_model(data.get("model"))
    folder = (data.get("folder") or "").strip("/")
    if folder:
        d = _guard(library.resolve, folder)
        if not d.is_dir():
            raise HTTPException(404, "Folderul destinație nu există")
    name = (data.get("nume") or "").strip()
    if data.get("url") and "_upload" not in data:
        job_id = jobs.submit("import_web", {"url": data["url"].strip(), "folder": folder, "nume": name},
                             label=data["url"].strip())
        return {"sarcina": job_id}
    upload = data["_upload"]
    kind = _guard(importer.kind_of, upload.filename)
    stored = _guard(importer.store_upload, upload.filename, await upload.read())
    params = {**stored, "folder": folder, "nume": name, "model": model}
    job_id = jobs.submit(f"import_{kind}", params, label=upload.filename)
    return {"sarcina": job_id}


# ---------- sarcini ----------

@app.get("/api/sarcini")
def sarcini():
    return jobs.listing()


@app.post("/api/sarcini/{job_id}/anulare")
def cancel_job(job_id: str):
    _guard(jobs.cancel, job_id)
    return {"ok": True}


@app.post("/api/sarcini/{job_id}/reluare")
def resume_job(job_id: str):
    _guard(jobs.resume, job_id)
    return {"ok": True}


# ---------- carduri ----------

@app.get("/api/carduri")
def get_cards(notita: str):
    refresh()
    return _guard(cards.for_note, notita)


class GenerateBody(BaseModel):
    path: str
    confirmat: bool = False
    model: str | None = None
    sectiune: str | None = None


@app.post("/api/carduri/generare")
def generate_cards(b: GenerateBody):
    model = _check_model(b.model)
    refresh()
    if not b.confirmat:
        return {"estimare": _guard(cards.estimate, b.path, model)}
    job_id = jobs.submit("carduri", {"path": b.path, "model": model, "sectiune": b.sectiune},
                         label=f"Carduri: {b.path}")
    return {"sarcina": job_id}


class CardBody(BaseModel):
    intrebare: str | None = None
    raspuns: str | None = None
    variante: list[str] | None = None
    corect: int | None = None
    explicatie: str | None = None


@app.put("/api/carduri/{card_id}")
def edit_card(card_id: str, b: CardBody):
    refresh()
    fields = b.model_dump(exclude_unset=True)
    return _guard(cards.edit, card_id, fields)


class StateBody(BaseModel):
    stare: str


@app.post("/api/carduri/{card_id}/stare")
def card_state(card_id: str, b: StateBody):
    refresh()
    return {"card": _guard(cards.set_state, card_id, b.stare)}


# ---------- repetiție ----------

@app.get("/api/repetitie/azi")
def review_today(scope: str = ""):
    refresh()
    return reviews.today_queue(scope)


class ReviewBody(BaseModel):
    card: str
    nota: int
    ms: int = 0


@app.post("/api/repetitie/raspuns")
def review_answer(b: ReviewBody):
    if b.nota not in (1, 2, 3, 4):
        raise HTTPException(400, "Nota trebuie să fie între 1 și 4.")
    if not cards.get(b.card):
        raise HTTPException(404, "Cardul nu există")
    reviews.record({"card": b.card, "nota": b.nota, "ms": max(0, b.ms), "mod": "repetitie"})
    st = reviews.states().get(b.card)
    return {"ok": True, "scadent": st.due.isoformat() if st else None}


# ---------- quiz și examen ----------

class QuizBody(BaseModel):
    scope: str = ""
    numar: int = 10
    tip: str = "variante"


@app.post("/api/quiz")
def make_quiz(b: QuizBody):
    refresh()
    if b.tip not in ("variante", "scris"):
        raise HTTPException(400, "Tipul trebuie să fie «variante» sau «scris».")
    return {"intrebari": _guard(quiz.make_quiz, b.scope, max(1, min(100, b.numar)), b.tip)}


class QuizAnswer(BaseModel):
    card: str
    corect: bool
    ms: int = 0
    mod: str = "quiz"
    examen: str | None = None


@app.post("/api/quiz/raspuns")
def quiz_answer(b: QuizAnswer):
    _guard(quiz.record_answer, b.card, b.corect, b.ms, b.mod, b.examen)
    return {"ok": True}


class ExamBody(BaseModel):
    scope: str = ""
    numar: int = 20
    minute: int = 30


@app.post("/api/examen")
def new_exam(b: ExamBody):
    refresh()
    return _guard(quiz.start_exam, b.scope, max(1, min(100, b.numar)), max(1, min(600, b.minute)))


class ExamFinal(BaseModel):
    raspunsuri: list[dict] = []


@app.post("/api/examen/{exam_id}/final")
def finish_exam(exam_id: str, b: ExamFinal):
    return _guard(quiz.finish_exam, exam_id, b.raspunsuri)


@app.get("/api/examen/{exam_id}")
def exam_result(exam_id: str):
    return _guard(quiz.analysis, exam_id)


@app.get("/api/examene")
def exams(scope: str = ""):
    return {"examene": quiz.history(scope)}


@app.get("/api/statistici")
def stats(scope: str = ""):
    refresh()
    return quiz.statistics(scope)


# ---------- chat ----------

class ChatBody(BaseModel):
    intrebare: str
    scope: str = ""
    istoric: list[dict] = []
    model: str | None = None


@app.post("/api/chat")
def ask(b: ChatBody):
    model = _check_model(b.model)
    refresh()
    return _guard(chat.ask, b.intrebare, b.scope, b.istoric, model)


class SaveChatBody(BaseModel):
    intrebare: str
    raspuns: str
    surse: list[dict] = []
    folder: str = ""


@app.post("/api/chat/salvare")
def save_chat(b: SaveChatBody):
    rel = _guard(chat.save_as_note, b.intrebare, b.raspuns, b.surse, b.folder)
    refresh()
    return {"path": rel}


# ---------- setări și diagnoză ----------

@app.get("/api/stare")
def status():
    tools = system.tools()
    usage = ai.rezumat_consum()
    return {
        "versiune": VERSION,
        "versiune_strat_ai": ai.AI_LAYER_VERSION,
        "notite": str(CFG.notes_dir),
        "date": str(CFG.data_dir),
        "config": str(Path(__file__).resolve().parent.parent / "config.toml"),
        "avertismente": list(CFG.warnings),
        "utilitare": tools,
        "ai": ai.modele_configurate(),
        "consum": usage,
        "transcriere": {"mod": CFG.transcription_mode, "model_local": CFG.transcription_model},
        "repetitie": {"carduri_noi_pe_zi": CFG.new_per_day, "retentie_dorita": CFG.desired_retention,
                      "ziua_incepe_la": f"{srs.DAY_STARTS_AT:02d}:00"},
    }


@app.get("/api/ai/modele")
def ai_models():
    cfg = ai.modele_configurate()
    tasks = ("notite", "carduri", "chat", "cuvinte_cheie")
    implicit = {}
    for t in tasks:
        try:
            info = ai.info_model(t)
            implicit[t] = f"{info['furnizor']}:{info['model']}"
        except ai.AIError as e:
            implicit[t] = f"eroare: {e}"
    return {**cfg, "implicit_sarcini": implicit}


@app.get("/api/ai/modele/{furnizor}")
def ai_provider_models(furnizor: str):
    return {"modele": _guard(ai.listeaza_modele, furnizor)}


class TestBody(BaseModel):
    model: str | None = None


@app.post("/api/ai/test")
def ai_test(b: TestBody):
    d = ai.testeaza((b.model or "").strip() or None)
    return {"ok": d.ok, "furnizor": d.furnizor, "model": d.model, "mesaj": d.mesaj, "durata_s": d.durata_s,
            "note": d.note}


@app.post("/api/cache/reconstruire")
def rebuild_cache():
    with _refresh_lock:
        active = jobs.listing()["active"]
        if active:
            raise HTTPException(409, "Așteaptă să se termine sarcinile în curs.")
        cache.reset()
    refresh()
    reviews.sync()
    return {"ok": True}
