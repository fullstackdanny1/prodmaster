"""Jurnal per comandă în ~/.local/state/unelte/<comanda>.log, rotit (1 MB × 3)."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from . import config


def logger(comanda: str) -> logging.Logger:
    log = logging.getLogger(f"unelte.{comanda}")
    if log.handlers:
        return log
    log.setLevel(logging.INFO)
    log.propagate = False
    try:
        d = config.state_dir()
        d.mkdir(parents=True, exist_ok=True)
        h = RotatingFileHandler(d / f"{comanda}.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        log.addHandler(h)
    except OSError:
        log.addHandler(logging.NullHandler())
    return log
