"""rezumat – rezumatul zilnic din sursele RSS / Atom, ca notiță Markdown.

Cereri condiționate (ETag, Last-Modified), cel mult o descărcare pe zi per sursă, elementele
văzute reținute 60 de zile. Fără AI, notița conține doar titlurile și linkurile.
"""
from __future__ import annotations

import email.utils
import json
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path

from . import __version__, ai
from .cli import parser
from .comun import Progres, config, fisiere, jurnal, prompturi, sistem

USER_AGENT = f"Unelte-rezumat/{__version__} (cititor RSS personal, o cerere pe zi)"
MAX_FEED_BYTES = 5 * 1024 * 1024
KEEP_DAYS = 60
DESC_CHARS = 1000
ATOM = "{http://www.w3.org/2005/Atom}"
SCHEMA = {
    "type": "object",
    "required": ["elemente"],
    "properties": {"elemente": {"type": "array", "items": {
        "type": "object", "required": ["id", "relevanta", "rezumat"],
        "properties": {"id": {"type": "integer"}, "relevanta": {"type": "number"},
                       "rezumat": {"type": "string", "minLength": 5}}}}},
}
log = jurnal.logger("rezumat")


@dataclass
class Item:
    id: str
    title: str
    link: str
    text: str
    published: datetime | None
    source: str


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "nav", "footer", "header"):
            self.skip += 1
        elif tag in ("p", "br", "li", "div", "h1", "h2", "h3"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "nav", "footer", "header") and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def html_to_text(s: str) -> str:
    p = _Text()
    try:
        p.feed(s or "")
    except Exception:  # noqa: BLE001 - HTML stricat: textul brut e suficient
        return re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n\n", "".join(p.parts))).strip()


# ---------- stare ----------

def state_path() -> Path:
    return config.state_dir() / "rezumat.json"


def load_state() -> dict:
    try:
        data = json.loads(state_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    data.setdefault("surse", {})
    data.setdefault("vazute", {})
    return data


def save_state(state: dict, today: date) -> None:
    limit = (today - timedelta(days=KEEP_DAYS)).isoformat()
    state["vazute"] = {k: v for k, v in state["vazute"].items() if v >= limit}
    fisiere.scrie_atomic(state_path(), json.dumps(state, ensure_ascii=False, indent=1) + "\n")


# ---------- descărcare și citire ----------

def fetch(url: str, src_state: dict, timeout: float = 30) -> bytes | None:
    """Conținutul feed-ului sau None dacă nu s-a schimbat (304)."""
    headers = {"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.5"}
    if src_state.get("etag"):
        headers["If-None-Match"] = src_state["etag"]
    if src_state.get("last_modified"):
        headers["If-Modified-Since"] = src_state["last_modified"]
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read(MAX_FEED_BYTES + 1)
            if r.headers.get("ETag"):
                src_state["etag"] = r.headers["ETag"]
            if r.headers.get("Last-Modified"):
                src_state["last_modified"] = r.headers["Last-Modified"]
    except urllib.error.HTTPError as e:
        if e.code == 304:
            return None
        raise
    if len(data) > MAX_FEED_BYTES:
        raise ValueError("feed-ul are peste 5 MB")
    return data


def _date(s: str | None) -> datetime | None:
    if not s:
        return None
    s = s.strip()
    try:
        d = email.utils.parsedate_to_datetime(s)
    except (TypeError, ValueError):
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _t(el, tag: str) -> str:
    x = el.find(tag)
    return (x.text or "").strip() if x is not None and x.text else ""


def parse_feed(data: bytes, source: str) -> list[Item]:
    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        raise ValueError(f"nu e un feed XML valid ({e})") from e
    items: list[Item] = []
    if root.tag == f"{ATOM}feed":
        for e in root.findall(f"{ATOM}entry"):
            link = ""
            for ln in e.findall(f"{ATOM}link"):
                if ln.get("rel", "alternate") == "alternate":
                    link = ln.get("href", "")
                    break
            content = _t(e, f"{ATOM}summary") or _t(e, f"{ATOM}content")
            items.append(Item(id=_t(e, f"{ATOM}id") or link, title=html_to_text(_t(e, f"{ATOM}title")), link=link,
                              text=html_to_text(content), source=source,
                              published=_date(_t(e, f"{ATOM}updated") or _t(e, f"{ATOM}published"))))
        return items
    channel = root.find("channel")
    if root.tag not in ("rss", "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}RDF") or channel is None:
        raise ValueError("nu e un feed RSS sau Atom")
    for it in channel.findall("item") or root.findall("item"):
        link = _t(it, "link")
        desc = _t(it, "description") or _t(it, "{http://purl.org/rss/1.0/modules/content/}encoded")
        items.append(Item(id=_t(it, "guid") or link or _t(it, "title"), title=html_to_text(_t(it, "title")),
                          link=link, text=html_to_text(desc), source=source,
                          published=_date(_t(it, "pubDate") or _t(it, "{http://purl.org/dc/elements/1.1/}date"))))
    return items


def full_text(url: str) -> str:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read(MAX_FEED_BYTES).decode(r.headers.get_content_charset() or "utf-8", errors="replace")
    except (urllib.error.URLError, OSError, ValueError):
        return ""
    return html_to_text(raw)


def collect(cfg: dict, state: dict, today: date, force: bool = False):
    """(elemente noi pe subiect, surse eșuate)."""
    r = cfg["rezumat"]
    new: dict[str, list[Item]] = {}
    failed: list[tuple[str, str]] = []
    for subj in r.get("subiect", []):
        name = subj.get("nume", "Diverse")
        bucket = new.setdefault(name, [])
        for url in subj.get("surse", []):
            st = state["surse"].setdefault(url, {})
            if st.get("ultima_descarcare") == today.isoformat() and not force:
                continue
            st["ultima_descarcare"] = today.isoformat()     # și o încercare eșuată contează ca cerere
            try:
                data = fetch(url, st)
                if data is None:
                    continue
                items = parse_feed(data, re.sub(r"^https?://(www\.)?", "", url).split("/")[0])
            except (urllib.error.URLError, OSError, ValueError) as e:
                failed.append((url, str(getattr(e, "reason", e))))
                log.warning("%s: %s", url, e)
                continue
            for it in items:
                if it.id and it.id not in state["vazute"] and all(x.id != it.id for x in bucket):
                    if r.get("text_complet") and it.link:
                        it.text = full_text(it.link) or it.text
                    bucket.append(it)
    return new, failed


# ---------- rezumare ----------

def summarize(subject: str, items: list[Item], cfg: dict, model: str | None, progres) -> list[tuple[Item, str]]:
    r = cfg["rezumat"]
    n = max(1, int(r.get("max_pe_subiect", 5)))
    listing = "\n\n".join(
        f"[{i}] {it.title}\nSursa: {it.source}\n{(it.text or '')[:DESC_CHARS]}" for i, it in enumerate(items))
    msgs = prompturi.mesaje("rezumat", subiect=subject, interese=r.get("interese", ""), maxim=n, elemente=listing)
    res = ai.ruleaza("rezumat", msgs, model=model, schema=SCHEMA, la_progres=progres)
    picked = []
    for e in sorted(res.date["elemente"], key=lambda x: -float(x.get("relevanta", 0))):
        i = int(e["id"])
        if 0 <= i < len(items) and all(p[0] is not items[i] for p in picked):
            picked.append((items[i], str(e["rezumat"]).strip()))
        if len(picked) >= n:
            break
    return picked


def _newest_first(items: list[Item]) -> list[Item]:
    return sorted(items, key=lambda it: it.published or datetime.min.replace(tzinfo=timezone.utc), reverse=True)


def render(today: date, sections: list[tuple[str, list[tuple[Item, str | None]]]], failed, with_ai: bool) -> str:
    total = sum(len(x) for _s, x in sections)
    lines = ["---", "tip: rezumat", f"titlu: Rezumatul zilei {today.isoformat()}",
             f"sursa: {'ai' if with_ai else 'manual'}", f"generat_la: {datetime.now().astimezone().isoformat(timespec='seconds')}",
             "---", "", f"# Rezumatul zilei – {today.strftime('%d.%m.%Y')}", ""]
    if not total:
        lines.append("Niciun articol nou azi.\n")
    if not with_ai and total:
        lines.append("*Fără AI: doar titlurile și linkurile, cele mai noi primele.*\n")
    for subject, items in sections:
        if not items:
            continue
        lines += [f"## {subject}", ""]
        for it, summary in items:
            title = it.title.replace("[", "(").replace("]", ")") or it.link
            lines.append(f"- [{title}]({it.link}) — *{it.source}*" if it.link else f"- {title} — *{it.source}*")
            if summary:
                lines.append(f"  {summary}")
        lines.append("")
    if failed:
        lines += ["## Surse care nu au răspuns", ""] + [f"- {u}: {e}" for u, e in failed] + [""]
    return "\n".join(lines).rstrip() + "\n"


def run(cfg: dict, no_ai: bool = False, model: str | None = None, force: bool = False,
        today: date | None = None) -> Path | None:
    today = today or date.today()
    r = cfg["rezumat"]
    if not r.get("subiect"):
        print(f"Nicio sursă configurată. Adaugă [[rezumat.subiect]] în {config.config_file()}.")
        return None
    state = load_state()
    new, failed = collect(cfg, state, today, force)
    with_ai = not no_ai
    sections = []
    progres = Progres()
    for subject, items in new.items():
        items = _newest_first(items)
        chosen: list[tuple[Item, str | None]]
        if with_ai and items:
            try:
                chosen = summarize(subject, items, cfg, model, progres)
            except ai.AIError as e:
                print(f"AI indisponibil ({e}); notița conține doar titlurile.")
                log.warning("AI: %s", e)
                with_ai = False
                chosen = [(it, None) for it in items]
        else:
            chosen = [(it, None) for it in items]
        sections.append((subject, chosen))
    progres.gata()
    if not with_ai:
        # fără AI (sau dacă a căzut la un subiect) se listează toate elementele noi, cele mai noi primele
        sections = [(s, [(it, None) for it in _newest_first(new[s])]) for s in new]
    out_dir = config.cale(r.get("iesire", "~/Notite/Rezumate"))
    dest = fisiere.nume_liber(out_dir / f"{today.isoformat()}.md")
    fisiere.scrie_atomic(dest, render(today, sections, failed, with_ai))
    for items in new.values():
        for it in items:
            state["vazute"][it.id] = today.isoformat()
    save_state(state, today)
    total = sum(len(v) for v in new.values())
    print(f"Scris: {dest} ({total} articole noi)")
    sistem.notifica("Rezumatul zilei", f"{total} articole noi", cfg=cfg)
    return dest


def check_sources(cfg: dict) -> int:
    bad = 0
    for subj in cfg["rezumat"].get("subiect", []):
        for url in subj.get("surse", []):
            try:
                data = fetch(url, {})
                items = parse_feed(data or b"", url)
                print(f"OK      {url}  ({len(items)} elemente)")
            except (urllib.error.URLError, OSError, ValueError) as e:
                bad += 1
                print(f"EROARE  {url}  {getattr(e, 'reason', e)}")
    if not cfg["rezumat"].get("subiect"):
        print("Nicio sursă configurată.")
    return 1 if bad else 0


def main(argv=None) -> int:
    ap = parser("rezumat", "Rezumatul zilnic din sursele tale RSS/Atom, scris ca notiță Markdown.",
                "Exemple:\n  rezumat                 # rulează acum\n  rezumat --fara-ai       # doar titluri și linkuri\n"
                "  rezumat --surse         # verifică fiecare sursă")
    ap.add_argument("--surse", action="store_true", help="verifică sursele și raportează cele care nu răspund")
    ap.add_argument("--fara-ai", action="store_true", help="fără rezumate AI")
    ap.add_argument("--model", help="alias sau furnizor:model")
    ap.add_argument("--forteaza", action="store_true", help="descarcă din nou sursele deja descărcate azi")
    a = ap.parse_args(argv)
    cfg = config.load()
    if a.surse:
        return check_sources(cfg)
    if a.model:
        ai.check_model_ref(a.model)
    run(cfg, no_ai=a.fara_ai, model=a.model, force=a.forteaza)
    return 0

