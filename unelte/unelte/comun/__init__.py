"""Utilitare comune tuturor comenzilor."""
from __future__ import annotations

import sys

from ..ai import AIError, ruleaza  # noqa: F401
from .config import EroareUtilizare  # noqa: F401


class Progres:
    """Mesajele la_progres ale stratului AI, pe o singură linie actualizată în terminal."""

    def __init__(self, stream=sys.stderr):
        self.stream = stream
        self.width = 0

    def __call__(self, mesaj: str) -> None:
        if not self.stream.isatty():
            print(mesaj, file=self.stream)
            return
        line = mesaj[:120]
        self.stream.write("\r" + line.ljust(self.width))
        self.stream.flush()
        self.width = len(line)

    def gata(self) -> None:
        if self.width and self.stream.isatty():
            self.stream.write("\r" + " " * self.width + "\r")
            self.stream.flush()
        self.width = 0
