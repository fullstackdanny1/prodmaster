"""Cache-ul SQLite din data/cache.db: doar date derivate, poate fi șters oricând.

Schema e versionată cu PRAGMA user_version; la o versiune diferită, cache-ul se
șterge și se reconstruiește (fără migrări).
"""
import sqlite3
import threading
from contextlib import contextmanager

from .config import CFG

SCHEMA_VERSION = 3
_init_lock = threading.Lock()

_FTS = "tokenize='unicode61 remove_diacritics 2'"

SCHEMA = f"""
CREATE TABLE files(id INTEGER PRIMARY KEY, path TEXT UNIQUE, mtime REAL, size INTEGER,
    title TEXT, unverified INTEGER, note_id TEXT, kind TEXT, usable INTEGER, source_id TEXT);
CREATE INDEX files_note_id ON files(note_id);
CREATE VIRTUAL TABLE notes_fts USING fts5(title, body, {_FTS});
CREATE TABLE sections(id INTEGER PRIMARY KEY, file_id INTEGER, note_id TEXT, path TEXT, ord INTEGER,
    anchor TEXT, title TEXT, hash TEXT, text TEXT);
CREATE INDEX sections_file ON sections(file_id);
CREATE VIRTUAL TABLE sections_fts USING fts5(title, text, {_FTS});
CREATE TABLE card_files(name TEXT PRIMARY KEY, mtime REAL, size INTEGER);
CREATE TABLE cards(id TEXT PRIMARY KEY, file TEXT, note_id TEXT, note_path TEXT, folder TEXT,
    section TEXT, section_hash TEXT, tip TEXT, question TEXT, answer TEXT, choices TEXT,
    correct INTEGER, explanation TEXT, origin TEXT, state TEXT, reason TEXT,
    modified_manual INTEGER, created_at TEXT);
CREATE INDEX cards_note ON cards(note_id);
CREATE INDEX cards_folder ON cards(folder);
CREATE TABLE review_files(name TEXT PRIMARY KEY, mtime REAL, size INTEGER);
CREATE TABLE card_state(card TEXT PRIMARY KEY, due TEXT, stability REAL, difficulty REAL,
    state INTEGER, step INTEGER, last_review TEXT, reps INTEGER, lapses INTEGER,
    first_review TEXT);
CREATE TABLE source_files(id TEXT PRIMARY KEY, mtime REAL, size INTEGER);
CREATE TABLE source_chunks(id INTEGER PRIMARY KEY, source_id TEXT, ord INTEGER, text TEXT);
CREATE VIRTUAL TABLE sources_fts USING fts5(text, {_FTS});
CREATE TABLE jobs(id TEXT PRIMARY KEY, tip TEXT, parametri TEXT, stare TEXT, progres INTEGER,
    mesaj TEXT, rezultat TEXT, eticheta TEXT, creat_la TEXT, actualizat_la TEXT);
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
"""


def db_path():
    return CFG.data_dir / "cache.db"


def _init(con: sqlite3.Connection) -> None:
    if con.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION:
        return
    tables = [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
        "AND name NOT LIKE '%_data' AND name NOT LIKE '%_idx' AND name NOT LIKE '%_content' "
        "AND name NOT LIKE '%_docsize' AND name NOT LIKE '%_config'")]
    for t in tables:
        con.execute(f'DROP TABLE IF EXISTS "{t}"')
    con.executescript(SCHEMA)
    con.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
    con.commit()


@contextmanager
def connect():
    CFG.data_dir.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db_path()), timeout=30)
    con.row_factory = sqlite3.Row
    try:
        with _init_lock:
            if con.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
                con.execute("PRAGMA journal_mode=WAL")
                _init(con)
        yield con
        con.commit()
    except BaseException:
        con.rollback()
        raise
    finally:
        con.close()


def reset() -> None:
    """Șterge cache-ul (va fi reconstruit la următoarea sincronizare)."""
    path = db_path()
    for suffix in ("", "-wal", "-shm"):
        p = path.with_name(path.name + suffix)
        if p.exists():
            p.unlink()


def like_prefix(folder: str) -> str:
    folder = folder.strip("/")
    return folder.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "/%"
