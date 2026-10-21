"""Indexul notițelor din cache: metadate, secțiuni și căutarea full-text (FTS5).

Indexul se actualizează incremental (după mtime și dimensiune): la fiecare cerere sunt
recitite doar fișierele modificate, deci poți edita notițele și din alt editor.
Căutarea ignoră diacriticele: „functie” găsește și „funcție”.
"""
import html
import re
import threading

from . import cache, library, sections
from .config import CFG

_lock = threading.Lock()


def sync() -> list[str]:
    """Aduce indexul la zi cu fișierele de pe disc. Întoarce căile notițelor modificate."""
    changed = []
    with _lock, cache.connect() as con:
        known = {r["path"]: r for r in con.execute("SELECT id, path, mtime, size FROM files")}
        seen = set()
        for p, rel in library.iter_notes():
            try:
                st = p.stat()
            except OSError:
                continue
            seen.add(rel)
            row = known.get(rel)
            if row and row["mtime"] == st.st_mtime and row["size"] == st.st_size:
                continue
            text = p.read_text(encoding="utf-8", errors="replace")
            meta, body = library.split_frontmatter(text)
            title = library.title_of(meta, body, p.name)
            note_id = meta.get("id") if library.valid_id(meta.get("id")) else None
            values = (st.st_mtime, st.st_size, title, int(library.is_unverified(meta)), note_id,
                      str(meta.get("tip", "")), int(library.is_usable(meta)),
                      str(meta.get("sursa_fisier") or "") or None)
            if row:
                fid = row["id"]
                con.execute("UPDATE files SET mtime=?, size=?, title=?, unverified=?, note_id=?, kind=?, "
                            "usable=?, source_id=? WHERE id=?", (*values, fid))
                _drop_note(con, fid)
            else:
                fid = con.execute("INSERT INTO files(path, mtime, size, title, unverified, note_id, kind, usable, "
                                  "source_id) VALUES(?,?,?,?,?,?,?,?,?)", (rel, *values)).lastrowid
            con.execute("INSERT INTO notes_fts(rowid, title, body) VALUES(?,?,?)", (fid, title, body))
            for s in sections.split(body, title):
                sid = con.execute("INSERT INTO sections(file_id, note_id, path, ord, anchor, title, hash, text) "
                                  "VALUES(?,?,?,?,?,?,?,?)",
                                  (fid, note_id, rel, s.ord, s.anchor, s.title, s.hash, s.text)).lastrowid
                con.execute("INSERT INTO sections_fts(rowid, title, text) VALUES(?,?,?)",
                            (sid, s.title, sections.plain(s.text)))
            changed.append(rel)
        for rel in set(known) - seen:
            fid = known[rel]["id"]
            _drop_note(con, fid)
            con.execute("DELETE FROM files WHERE id=?", (fid,))
            changed.append(rel)
    return changed


def _drop_note(con, fid: int) -> None:
    con.execute("DELETE FROM notes_fts WHERE rowid=?", (fid,))
    ids = [r[0] for r in con.execute("SELECT id FROM sections WHERE file_id=?", (fid,))]
    con.executemany("DELETE FROM sections_fts WHERE rowid=?", [(i,) for i in ids])
    con.execute("DELETE FROM sections WHERE file_id=?", (fid,))


def meta_by_path() -> dict:
    with cache.connect() as con:
        return {
            r["path"]: {"title": r["title"], "unverified": bool(r["unverified"]), "mtime": r["mtime"]}
            for r in con.execute("SELECT path, title, unverified, mtime FROM files")
        }


def note_by_id(note_id: str) -> dict | None:
    with cache.connect() as con:
        r = con.execute("SELECT path, title, usable FROM files WHERE note_id=?", (note_id,)).fetchone()
    return dict(r) if r else None


def note_sections(path: str) -> list[dict]:
    with cache.connect() as con:
        return [dict(r) for r in con.execute(
            "SELECT anchor, title, hash, text, ord FROM sections WHERE path=? ORDER BY ord", (path,))]


def section_titles() -> dict:
    """(cale, ancoră) → titlul secțiunii."""
    with cache.connect() as con:
        return {(r["path"], r["anchor"]): r["title"] for r in con.execute("SELECT path, anchor, title FROM sections")}


def unverified_notes() -> list[dict]:
    with cache.connect() as con:
        return [dict(r) for r in con.execute(
            "SELECT path, title FROM files WHERE unverified=1 ORDER BY path")]


def fts_query(q: str, relaxed: bool = False, joiner: str = " ") -> str:
    tokens = re.findall(r"\w+", q)
    if relaxed:
        # Forme apropiate: „lichidității” -> „lichidit*”, găsește și „lichiditate”, „lichiditatea”.
        tokens = [t[: max(4, len(t) - 3)] if len(t) > 5 else t for t in tokens]
    return joiner.join(f'"{t}"*' for t in tokens)


def _mark(s: str) -> str:
    return html.escape(s or "").replace("\x01", "<mark>").replace("\x02", "</mark>")


def search(q: str, scope: str = "", limit: int = 50) -> dict:
    """Caută exact (cu prefix); dacă nu găsește nimic, încearcă forme apropiate ale cuvintelor."""
    results = _search(fts_query(q), scope, limit)
    if results:
        return {"results": results, "relaxed": False}
    relaxed_query = fts_query(q, relaxed=True)
    if relaxed_query == fts_query(q):
        return {"results": [], "relaxed": False}
    return {"results": _search(relaxed_query, scope, limit), "relaxed": True}


def _search(query: str, scope: str, limit: int) -> list[dict]:
    if not query:
        return []
    like = cache.like_prefix(scope) if scope.strip("/") else ""
    sql = (
        "SELECT f.path, f.unverified, "
        "highlight(notes_fts, 0, char(1), char(2)) AS t, "
        "snippet(notes_fts, 1, char(1), char(2), '…', 18) AS s "
        "FROM notes_fts JOIN files f ON f.id = notes_fts.rowid "
        "WHERE notes_fts MATCH ? AND (? = '' OR f.path LIKE ? ESCAPE '\\') "
        "ORDER BY bm25(notes_fts, 8.0, 1.0) LIMIT ?"
    )
    with cache.connect() as con:
        rows = con.execute(sql, (query, like, like, limit)).fetchall()
    return [
        {
            "path": r["path"],
            "title_html": _mark(r["t"]),
            "snippet_html": _mark(r["s"]),
            "unverified": bool(r["unverified"]),
            "crumbs": library.crumbs(r["path"]),
        }
        for r in rows
    ]


def notes_dir_exists() -> bool:
    return CFG.notes_dir.is_dir()
