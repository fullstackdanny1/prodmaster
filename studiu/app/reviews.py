"""Istoricul răspunsurilor: .studiu/repetitii/AAAA-LL.jsonl, doar adăugare.

Starea de programare (card_state din cache) se obține din istoric prin srs.replay; după
fiecare răspuns se actualizează incremental, cu același algoritm, deci rezultatul e
identic cu o reconstruire de la zero.
"""
import random
import threading
from datetime import datetime, timedelta

from . import cache, cards, srs, storage
from .config import CFG

_lock = threading.RLock()


def _dir():
    return storage.path("repetitii")


def parse_time(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.astimezone()


def events() -> list[dict]:
    out = []
    d = _dir()
    for p in sorted(d.glob("*.jsonl")) if d.is_dir() else []:
        out += storage.read_jsonl(p)
    return out


def to_review_event(e: dict) -> srs.ReviewEvent | None:
    try:
        t = parse_time(e["t"])
        card = str(e["card"])
    except (KeyError, ValueError, TypeError):
        return None
    if e.get("mod", "repetitie") == "repetitie":
        nota = e.get("nota")
        return srs.ReviewEvent(t, card, int(nota)) if nota in (1, 2, 3, 4) else None
    # quiz și examen: greșit = „Din nou”, corect = fără schimbare
    return srs.ReviewEvent(t, card, None if e.get("corect") else 1)


def _files_signature(con) -> tuple[dict, dict]:
    d = _dir()
    current = {}
    for p in d.glob("*.jsonl") if d.is_dir() else []:
        st = p.stat()
        current[p.name] = (st.st_mtime, st.st_size)
    known = {r["name"]: (r["mtime"], r["size"]) for r in con.execute("SELECT name, mtime, size FROM review_files")}
    return current, known


def sync() -> bool:
    """Reconstruiește card_state dacă istoricul s-a schimbat pe disc. True dacă a reluat."""
    with _lock, cache.connect() as con:
        current, known = _files_signature(con)
        if current == known:
            return False
        evs = [x for x in (to_review_event(e) for e in events()) if x]
        states = srs.replay(evs)
        con.execute("DELETE FROM card_state")
        for cid, s in states.items():
            _save_state(con, cid, s)
        con.execute("DELETE FROM review_files")
        con.executemany("INSERT INTO review_files(name, mtime, size) VALUES(?,?,?)",
                        [(k, *v) for k, v in current.items()])
        return True


def _save_state(con, cid: str, s: srs.CardState) -> None:
    r = s.to_row()
    con.execute("INSERT OR REPLACE INTO card_state(card, due, stability, difficulty, state, step, last_review, "
                "reps, lapses, first_review) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (cid, r["due"], r["stability"], r["difficulty"], r["state"], r["step"], r["last_review"],
                 r["reps"], r["lapses"], r["first_review"]))


def states() -> dict[str, srs.CardState]:
    sync()
    with cache.connect() as con:
        return {r["card"]: srs.CardState.from_row(r) for r in con.execute("SELECT * FROM card_state")}


def record(event: dict) -> None:
    """Adaugă un răspuns în istoric și actualizează starea cardului."""
    event = {"t": storage.now_iso(), **event}
    t = parse_time(event["t"])
    with _lock:
        sync()     # întâi se preiau eventualele modificări venite din alt loc
        p = _dir() / f"{t.strftime('%Y-%m')}.jsonl"
        storage.append_jsonl(p, event)
        ev = to_review_event(event)
        with cache.connect() as con:
            if ev and ev.rating is not None:
                row = con.execute("SELECT * FROM card_state WHERE card=?", (ev.card,)).fetchone()
                prev = srs.CardState.from_row(row) if row else None
                _save_state(con, ev.card, srs.schedule(prev, ev.rating, ev.t))
            st = p.stat()
            con.execute("INSERT OR REPLACE INTO review_files(name, mtime, size) VALUES(?,?,?)",
                        (p.name, st.st_mtime, st.st_size))


# ---------- coada zilei ----------

def today_queue(scope: str = "", now: datetime | None = None) -> dict:
    now = now or datetime.now().astimezone()
    all_states = states()
    active = cards.query(scope)
    by_id = {c["id"]: c for c in active}
    today = srs.study_day(now)
    due_ids = [cid for cid in srs.due({k: v for k, v in all_states.items() if k in by_id}, now)]
    introduced = sum(1 for s in all_states.values() if s.first_review and srs.study_day(s.first_review) == today)
    budget = max(0, CFG.new_per_day - introduced)
    new_ids = [c["id"] for c in active if c["id"] not in all_states][:budget]
    order = _interleave(due_ids, new_ids)
    per_subject: dict[str, dict] = {}
    for cid in order:
        subject = (by_id[cid]["path"] or "").split("/")[0] or "(fără materie)"
        g = per_subject.setdefault(subject, {"scadente": 0, "noi": 0})
        g["noi" if cid in new_ids else "scadente"] += 1
    return {
        "carduri": [{**cards.public(by_id[cid]), "nou": cid in new_ids,
                     "intervale": {str(k): srs.human(v) for k, v in srs.preview(all_states.get(cid), now).items()}}
                    for cid in order],
        "scadente": len(due_ids), "noi": len(new_ids), "noi_ramase_azi": budget,
        "pe_materii": per_subject,
    }


def _interleave(due_ids: list[str], new_ids: list[str]) -> list[str]:
    if not new_ids:
        return list(due_ids)
    if not due_ids:
        return list(new_ids)
    step = max(1, len(due_ids) // (len(new_ids) + 1))
    out, n = [], list(new_ids)
    for i, cid in enumerate(due_ids, 1):
        out.append(cid)
        if i % step == 0 and n:
            out.append(n.pop(0))
    return out + n


def forecast(days: int = 7, scope: str = "", now: datetime | None = None) -> list[dict]:
    now = now or datetime.now().astimezone()
    ids = {c["id"] for c in cards.query(scope)}
    today = srs.study_day(now)
    counts = {today + timedelta(days=i): 0 for i in range(days)}
    for cid, s in states().items():
        if cid not in ids:
            continue
        d = max(srs.study_day(s.due), today)
        if d in counts:
            counts[d] += 1
    return [{"zi": d.isoformat(), "carduri": n} for d, n in counts.items()]


def shuffle_seed(seed: str | None = None) -> random.Random:
    return random.Random(seed)
