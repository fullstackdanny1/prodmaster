"""Sarcini de durată (import, generare de carduri): un singur fir de lucru, o coadă.

Starea sarcinilor stă în tabela jobs din cache. La pornire, sarcinile rămase in_lucru
sunt marcate eroare și pot fi reluate. Interfața urmărește progresul prin polling.
"""
import json
import logging
import queue
import threading
import traceback
from typing import Callable

from . import ai, cache
from .storage import new_id, now_iso

log = logging.getLogger("studiu.jobs")

ACTIVE = ("in_asteptare", "in_lucru")
INTERRUPTED = "Aplicația a fost oprită în timpul procesării"


class Cancelled(Exception):
    pass


class JobError(Exception):
    """Eroare cu mesaj pentru utilizator."""


class Job:
    def __init__(self, row: dict):
        self.id = row["id"]
        self.kind = row["tip"]
        self.params = json.loads(row["parametri"] or "{}")
        self._progress = 0

    def progress(self, pct: float | None = None, message: str | None = None) -> None:
        if self.cancelled():
            raise Cancelled()
        fields = {}
        if pct is not None:
            self._progress = max(0, min(100, int(pct)))
            fields["progres"] = self._progress
        if message is not None:
            fields["mesaj"] = message
        update(self.id, **fields)

    def message(self, text: str) -> None:
        """Pentru la_progres din stratul AI (de exemplu pauzele la limita de rată)."""
        update(self.id, mesaj=text)

    def cancelled(self) -> bool:
        return self.id in _cancel


HANDLERS: dict[str, Callable[[Job], dict | None]] = {}
_queue: "queue.Queue[str]" = queue.Queue()
_cancel: set[str] = set()
_worker: threading.Thread | None = None
_lock = threading.Lock()


def handler(kind: str):
    def deco(fn):
        HANDLERS[kind] = fn
        return fn
    return deco


def update(job_id: str, **fields) -> None:
    if not fields:
        return
    fields["actualizat_la"] = now_iso()
    cols = ", ".join(f"{k}=?" for k in fields)
    with cache.connect() as con:
        con.execute(f"UPDATE jobs SET {cols} WHERE id=?", (*fields.values(), job_id))


def get(job_id: str) -> dict | None:
    with cache.connect() as con:
        row = con.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    return _public(row) if row else None


def _public(row) -> dict:
    d = dict(row)
    d["parametri"] = json.loads(d.get("parametri") or "{}")
    d["rezultat"] = json.loads(d["rezultat"]) if d.get("rezultat") else None
    return d


def listing(limit_done: int = 20) -> dict:
    with cache.connect() as con:
        active = con.execute("SELECT * FROM jobs WHERE stare IN ('in_asteptare','in_lucru') "
                             "ORDER BY creat_la").fetchall()
        done = con.execute("SELECT * FROM jobs WHERE stare NOT IN ('in_asteptare','in_lucru') "
                           "ORDER BY actualizat_la DESC LIMIT ?", (limit_done,)).fetchall()
    return {"active": [_public(r) for r in active], "terminate": [_public(r) for r in done]}


def submit(kind: str, params: dict, label: str = "") -> str:
    if kind not in HANDLERS:
        raise ValueError(f"Tip de sarcină necunoscut: {kind}")
    job_id = new_id(10)
    t = now_iso()
    with cache.connect() as con:
        con.execute("INSERT INTO jobs(id, tip, parametri, stare, progres, mesaj, rezultat, eticheta, "
                    "creat_la, actualizat_la) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (job_id, kind, json.dumps(params, ensure_ascii=False), "in_asteptare", 0,
                     "În așteptare", None, label, t, t))
    _queue.put(job_id)
    start_worker()
    return job_id


def cancel(job_id: str) -> None:
    job = get(job_id)
    if not job:
        raise KeyError(job_id)
    if job["stare"] == "in_asteptare":
        update(job_id, stare="anulat", mesaj="Anulată")
    elif job["stare"] == "in_lucru":
        _cancel.add(job_id)
        update(job_id, mesaj="Se anulează…")


def resume(job_id: str) -> None:
    job = get(job_id)
    if not job:
        raise KeyError(job_id)
    if job["stare"] not in ("eroare", "anulat"):
        raise ValueError("Doar sarcinile oprite cu eroare sau anulate pot fi reluate.")
    update(job_id, stare="in_asteptare", progres=0, mesaj="În așteptare", rezultat=None)
    _queue.put(job_id)
    start_worker()


def mark_interrupted() -> int:
    with cache.connect() as con:
        cur = con.execute("UPDATE jobs SET stare='eroare', mesaj=?, actualizat_la=? WHERE stare='in_lucru'",
                          (INTERRUPTED, now_iso()))
        pending = [r["id"] for r in con.execute("SELECT id FROM jobs WHERE stare='in_asteptare' ORDER BY creat_la")]
    for job_id in pending:
        _queue.put(job_id)
    if pending:
        start_worker()
    return cur.rowcount


def run_one(job_id: str) -> None:
    with cache.connect() as con:
        row = con.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not row or row["stare"] != "in_asteptare":
        return
    job = Job(dict(row))
    update(job_id, stare="in_lucru", mesaj="Pornită", progres=0)
    try:
        result = HANDLERS[job.kind](job)
        update(job_id, stare="gata", progres=100, mesaj="Gata",
               rezultat=json.dumps(result or {}, ensure_ascii=False))
    except Cancelled:
        update(job_id, stare="anulat", mesaj="Anulată")
    except (JobError, ai.AIError, ValueError) as e:
        update(job_id, stare="eroare", mesaj=str(e))
    except Exception as e:  # noqa: BLE001 - orice eroare neașteptată ajunge în listă, nu oprește firul
        log.error("Sarcina %s a eșuat:\n%s", job_id, traceback.format_exc())
        update(job_id, stare="eroare", mesaj=f"Eroare neașteptată: {e}")
    finally:
        _cancel.discard(job_id)


def _loop() -> None:
    while True:
        job_id = _queue.get()
        try:
            run_one(job_id)
        finally:
            _queue.task_done()


def start_worker() -> None:
    global _worker
    with _lock:
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_loop, name="studiu-jobs", daemon=True)
            _worker.start()


def wait_idle() -> None:
    """Așteaptă până se golește coada (folosit în teste)."""
    _queue.join()
