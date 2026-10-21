"""Chat cu notițele, fără embeddings: cuvinte cheie (AI) → căutare FTS5 în secțiuni și în
textul surselor → răspuns (AI) din fragmentele numerotate, cu citări [n]."""
import re
import threading

from . import ai, cache, index, library, prompts, scheme, storage
from .render import render

MAX_FRAGMENTS = 8
MAX_CONTEXT_TOKENS = 6000
CHUNK_CHARS = 1200
_lock = threading.Lock()


# ---------- textul surselor în cache ----------

def _chunks(text: str) -> list[str]:
    out, cur = [], ""
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        if cur and len(cur) + len(para) > CHUNK_CHARS:
            out.append(cur)
            cur = ""
        while len(para) > CHUNK_CHARS * 2:
            out.append(para[:CHUNK_CHARS])
            para = para[CHUNK_CHARS:]
        cur = f"{cur}\n\n{para}" if cur else para
    if cur:
        out.append(cur)
    return out


def sync_sources() -> None:
    d = storage.path("surse")
    with _lock, cache.connect() as con:
        known = {r["id"]: r for r in con.execute("SELECT id, mtime, size FROM source_files")}
        seen = set()
        for p in sorted(d.glob("*.txt")) if d.is_dir() else []:
            sid = p.stem
            st = p.stat()
            seen.add(sid)
            row = known.get(sid)
            if row and row["mtime"] == st.st_mtime and row["size"] == st.st_size:
                continue
            _drop(con, sid)
            for k, chunk in enumerate(_chunks(p.read_text(encoding="utf-8", errors="replace"))):
                cid = con.execute("INSERT INTO source_chunks(source_id, ord, text) VALUES(?,?,?)",
                                  (sid, k, chunk)).lastrowid
                con.execute("INSERT INTO sources_fts(rowid, text) VALUES(?,?)", (cid, chunk))
            con.execute("INSERT OR REPLACE INTO source_files(id, mtime, size) VALUES(?,?,?)",
                        (sid, st.st_mtime, st.st_size))
        for sid in set(known) - seen:
            _drop(con, sid)
            con.execute("DELETE FROM source_files WHERE id=?", (sid,))


def _drop(con, sid: str) -> None:
    ids = [r[0] for r in con.execute("SELECT id FROM source_chunks WHERE source_id=?", (sid,))]
    con.executemany("DELETE FROM sources_fts WHERE rowid=?", [(i,) for i in ids])
    con.execute("DELETE FROM source_chunks WHERE source_id=?", (sid,))


# ---------- regăsire ----------

def retrieve(keywords: list[str], scope: str = "") -> list[dict]:
    terms = [t for k in keywords for t in re.findall(r"\w+", k) if len(t) > 1]
    if not terms:
        return []
    query = " OR ".join(dict.fromkeys(f'"{t[: max(4, len(t) - 3)] if len(t) > 6 else t}"*' for t in terms))
    like = cache.like_prefix(scope) if scope.strip("/") else ""
    with cache.connect() as con:
        secs = con.execute(
            "SELECT s.path, s.anchor, s.title, s.text, f.title AS note_title, bm25(sections_fts, 3.0, 1.0) AS score "
            "FROM sections_fts JOIN sections s ON s.id = sections_fts.rowid JOIN files f ON f.id = s.file_id "
            "WHERE sections_fts MATCH ? AND f.kind != 'rezumat' AND (? = '' OR s.path LIKE ? ESCAPE '\\') "
            "ORDER BY score LIMIT 20", (query, like, like)).fetchall()
        srcs = con.execute(
            "SELECT c.source_id, c.text, f.path, f.title AS note_title, bm25(sources_fts) AS score "
            "FROM sources_fts JOIN source_chunks c ON c.id = sources_fts.rowid "
            "LEFT JOIN files f ON f.source_id = c.source_id "
            "WHERE sources_fts MATCH ? AND (? = '' OR f.path LIKE ? ESCAPE '\\') "
            "ORDER BY score LIMIT 10", (query, like, like)).fetchall()
    found = [{"tip": "notita", "path": r["path"], "anchor": r["anchor"], "titlu": r["note_title"],
              "sectiune": r["title"], "text": r["text"], "score": r["score"]} for r in secs]
    found += [{"tip": "sursa", "sursa": r["source_id"], "path": r["path"], "anchor": "",
               "titlu": r["note_title"] or "Sursă importată", "sectiune": "text original",
               "text": r["text"], "score": r["score"] * 0.8} for r in srcs]
    found.sort(key=lambda f: f["score"])
    out, used = [], 0
    for f in found:
        cost = ai.estimeaza_tokeni(f["text"])
        if used + cost > MAX_CONTEXT_TOKENS and out:
            continue
        out.append(f)
        used += cost
        if len(out) >= MAX_FRAGMENTS:
            break
    return out


# ---------- răspuns ----------

def ask(question: str, scope: str = "", history: list[dict] | None = None, model: str | None = None) -> dict:
    question = (question or "").strip()
    if not question:
        raise ValueError("Scrie o întrebare.")
    index.sync()
    sync_sources()
    kw = ai.ruleaza("cuvinte_cheie", prompts.render("chat_cuvinte_cheie", intrebare=question),
                    model=model, schema=scheme.CUVINTE_CHEIE, temperatura=0)
    keywords = [str(k) for k in kw.date["cuvinte"]] + re.findall(r"\w{4,}", question)
    fragments = retrieve(keywords, scope)
    context = "\n\n".join(
        f"[{i}] ({f['titlu']} — {f['sectiune']})\n{f['text']}" for i, f in enumerate(fragments, 1)
    ) or "(niciun fragment găsit)"
    msgs = prompts.render("chat_raspuns", intrebare=question, context=context)
    past = []
    for h in (history or [])[-3:]:
        if h.get("intrebare") and h.get("raspuns"):
            past += [{"role": "user", "content": str(h["intrebare"])},
                     {"role": "assistant", "content": str(h["raspuns"])}]
    msgs = msgs[:1] + past + msgs[1:]
    r = ai.ruleaza("chat", msgs, model=model)
    sources = [{"n": i, "tip": f["tip"], "notita": f["path"], "sectiune": f["anchor"], "titlu": f["titlu"],
                "titlu_sectiune": f["sectiune"], "sursa": f.get("sursa")} for i, f in enumerate(fragments, 1)]
    return {"raspuns": r.text, "raspuns_html": render(r.text), "surse": sources, "cuvinte_cheie": keywords[:12]}


def save_as_note(question: str, answer: str, sources: list[dict], folder: str) -> str:
    lines = [f"# {question.strip()}", "", answer.strip(), "", "## Surse", ""]
    for s in sources:
        if not s.get("notita"):
            continue
        base = folder.strip("/")
        target = s["notita"]
        rel = _relative(base, target)
        anchor = f"#{s['sectiune']}" if s.get("sectiune") else ""
        lines.append(f"{s.get('n', '-')}. [{s.get('titlu') or target} — {s.get('titlu_sectiune') or ''}]"
                     f"(<{rel}{anchor}>)")
    meta = {"id": storage.new_id(), "sursa": "ai", "verificat": False, "generat_la": storage.now_iso()}
    return library.write_new_note(folder, question[:80], meta, "\n".join(lines) + "\n")


def _relative(from_dir: str, target: str) -> str:
    a = [x for x in from_dir.split("/") if x]
    b = target.split("/")
    k = 0
    while k < len(a) and k < len(b) - 1 and a[k] == b[k]:
        k += 1
    return "/".join([".."] * (len(a) - k) + b[k:])
