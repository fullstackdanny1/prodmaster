"""Secțiunile unei notițe: un bloc începe cu un titlu ## și ține până la următorul ##.

Ancora e luată din tokenii randării (aceeași funcție ca în HTML), deci linkul
notita#ancora duce exact la secțiune. Titlurile ## din blocurile de cod sunt ignorate.
"""
import hashlib
import re
from dataclasses import dataclass

from .render import parse


@dataclass
class Section:
    ord: int
    anchor: str          # "" pentru introducere
    title: str
    text: str
    hash: str


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def text_hash(text: str) -> str:
    return hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()[:16]


def split(body: str, intro_title: str = "Introducere") -> list[Section]:
    lines = body.split("\n")
    tokens = parse(body)
    heads = []
    for i, t in enumerate(tokens):
        if t.type == "heading_open" and t.tag == "h2" and t.map:
            title = tokens[i + 1].content if i + 1 < len(tokens) else ""
            heads.append((t.map[0], t.attrGet("id") or "", title.strip()))
    out: list[Section] = []
    starts = [h[0] for h in heads] + [len(lines)]
    intro = "\n".join(lines[: starts[0]])
    if normalize(intro):
        out.append(Section(0, "", intro_title, intro.strip("\n"), text_hash(intro)))
    for k, (start, anchor, title) in enumerate(heads):
        text = "\n".join(lines[start: starts[k + 1]])
        out.append(Section(len(out), anchor, title, text.strip("\n"), text_hash(text)))
    return out


def plain(text: str) -> str:
    """Textul secțiunii fără sintaxa Markdown cea mai zgomotoasă (pentru prompturi și căutare)."""
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.M)
    return text.strip()
