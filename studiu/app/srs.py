"""Repetiția spațiată: învelișul peste pachetul fsrs (versiune fixată).

Interfața e stabilă; dacă API-ul fsrs se schimbă, doar acest fișier se modifică.
Starea cardurilor nu se salvează în fișiere: se obține reluând istoricul (replay).
Fuzzing-ul e dezactivat, ca același istoric să dea mereu aceleași scadențe.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

import fsrs

from .config import CFG

DAY_STARTS_AT = 4          # ziua de studiu se termină la 04:00, ora locală
LEARN_AHEAD = timedelta(minutes=20)
REVIEW = fsrs.State.Review.value


@dataclass
class ReviewEvent:
    t: datetime
    card: str
    rating: int | None       # 1–4; None = răspuns corect în quiz/examen (nu schimbă programarea)


@dataclass
class CardState:
    due: datetime
    stability: float | None
    difficulty: float | None
    state: int
    step: int | None
    last_review: datetime | None
    reps: int = 0
    lapses: int = 0
    first_review: datetime | None = None

    def to_row(self) -> dict:
        d = asdict(self)
        for k in ("due", "last_review", "first_review"):
            d[k] = d[k].isoformat() if d[k] else None
        return d

    @classmethod
    def from_row(cls, r) -> "CardState":
        g = lambda k: datetime.fromisoformat(r[k]) if r[k] else None  # noqa: E731
        return cls(due=g("due"), stability=r["stability"], difficulty=r["difficulty"], state=r["state"],
                   step=r["step"], last_review=g("last_review"), reps=r["reps"] or 0,
                   lapses=r["lapses"] or 0, first_review=g("first_review"))


_scheduler: fsrs.Scheduler | None = None
_scheduler_retention: float | None = None


def scheduler() -> fsrs.Scheduler:
    global _scheduler, _scheduler_retention
    if _scheduler is None or _scheduler_retention != CFG.desired_retention:
        _scheduler = fsrs.Scheduler(desired_retention=CFG.desired_retention, enable_fuzzing=False)
        _scheduler_retention = CFG.desired_retention
    return _scheduler


def _utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return dt.astimezone(timezone.utc)


def schedule(state: CardState | None, rating: int, at: datetime) -> CardState:
    at = _utc(at)
    if state is None:
        card = fsrs.Card(card_id=0, due=at)
        reps = lapses = 0
        first = at
    else:
        card = fsrs.Card(card_id=0, state=fsrs.State(state.state), step=state.step,
                         stability=state.stability, difficulty=state.difficulty,
                         due=_utc(state.due), last_review=_utc(state.last_review) if state.last_review else None)
        reps, lapses, first = state.reps, state.lapses, state.first_review or at
    was_review = card.state == fsrs.State.Review
    card, _log = scheduler().review_card(card, fsrs.Rating(rating), review_datetime=at)
    if was_review and rating == 1:
        lapses += 1
    return CardState(due=card.due, stability=card.stability, difficulty=card.difficulty,
                     state=card.state.value, step=card.step, last_review=card.last_review,
                     reps=reps + 1, lapses=lapses, first_review=first)


def replay(events: Iterable[ReviewEvent], now: datetime | None = None) -> dict[str, CardState]:
    states: dict[str, CardState] = {}
    for ev in sorted(events, key=lambda e: _utc(e.t)):
        if now is not None and _utc(ev.t) > _utc(now):
            continue
        if ev.rating is None:
            continue
        states[ev.card] = schedule(states.get(ev.card), ev.rating, ev.t)
    return states


def study_day(dt: datetime):
    local = dt.astimezone() if dt.tzinfo else dt
    return (local - timedelta(hours=DAY_STARTS_AT)).date()


def is_due(state: CardState, now: datetime) -> bool:
    if state.state == REVIEW:
        return study_day(state.due) <= study_day(now)
    return _utc(state.due) <= _utc(now) + LEARN_AHEAD


def due(states: dict[str, CardState], now: datetime) -> list[str]:
    items = [(s.due, cid) for cid, s in states.items() if is_due(s, now)]
    return [cid for _d, cid in sorted(items)]


def preview(state: CardState | None, now: datetime) -> dict[int, timedelta]:
    """Intervalul următor pentru fiecare notă (afișat sub butoane)."""
    return {r: schedule(state, r, now).due - _utc(now) for r in (1, 2, 3, 4)}


def human(delta: timedelta) -> str:
    s = max(0, delta.total_seconds())
    if s < 3600:
        m = max(1, round(s / 60))
        return f"{m} min"
    if s < 86400:
        return f"{round(s / 3600)} h"
    days = round(s / 86400)
    if days < 31:
        return "1 zi" if days == 1 else f"{days} zile"
    if days < 365:
        months = round(days / 30)
        return "1 lună" if months == 1 else f"{months} luni"
    years = round(days / 365, 1)
    return f"{years:g} ani" if years != 1 else "1 an"
