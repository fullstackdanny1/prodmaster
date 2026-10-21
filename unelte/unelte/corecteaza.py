"""corecteaza – gramatică și ortografie cu LanguageTool local; stilul prin AI, doar la cerere.

Pentru Markdown, porțiunile care nu sunt text natural (antet, cod, formule, URL-uri, sintaxa
linkurilor) sunt înlocuite cu spații de aceeași lungime, ca pozițiile raportate să corespundă
exact textului original. Rezultatele merg în fișiere noi, niciodată peste original.
"""
from __future__ import annotations

import difflib
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from . import ai
from .cli import parser
from .comun import Progres, config, fisiere, prompturi

CHUNK_LIMIT = 20000
STYLE_CHUNK = 8000


@dataclass
class Match:
    offset: int
    length: int
    message: str
    rule: str
    issue: str = ""
    replacements: list[str] = field(default_factory=list)
    paragraph: int | None = None       # pentru .docx


# ---------- mascare ----------

def _blank(chars: list[str], start: int, end: int) -> None:
    for i in range(start, end):
        if chars[i] != "\n":
            chars[i] = " "


_FRONT = re.compile(r"\A---[ \t]*\n.*?\n(?:---|\.\.\.)[ \t]*(?:\n|\Z)", re.S)
_FENCE = re.compile(r"^([ \t]*)(```+|~~~+)[^\n]*\n.*?^\1\2[ \t]*$", re.S | re.M)
_INDENTED = re.compile(r"(?:(?<=\n\n)|\A)((?:(?: {4}|\t)[^\n]*\n?)+)")
_DISPLAY_MATH = re.compile(r"\$\$.*?\$\$", re.S)
_INLINE_MATH = re.compile(r"(?<![\\$])\$(?!\s)[^$\n]+?(?<!\s)\$(?!\d)")
_INLINE_CODE = re.compile(r"(`+)(?!`).+?(?<!`)\1(?!`)", re.S)
_IMAGE_OR_LINK = re.compile(r"(!?\[)([^\]\n]*)(\]\([^)\n]*\))")
_REF_LINK = re.compile(r"^\s*\[[^\]\n]+\]:\s*\S+.*$", re.M)
_AUTOLINK = re.compile(r"<(?:https?|mailto|ftp):[^>\s]+>")
_URL = re.compile(r"\bhttps?://[^\s)>\]]+|\bwww\.[^\s)>\]]+")
_HTML = re.compile(r"</?[A-Za-z][^>\n]*>")


def mask_markdown(text: str) -> str:
    chars = list(text)
    for rx in (_FRONT, _FENCE, _DISPLAY_MATH, _INLINE_CODE, _INLINE_MATH, _REF_LINK, _AUTOLINK, _HTML):
        for m in rx.finditer("".join(chars)):
            _blank(chars, m.start(), m.end())
    cur = "".join(chars)
    for m in _INDENTED.finditer(cur):
        _blank(chars, m.start(1), m.end(1))
    cur = "".join(chars)
    for m in _IMAGE_OR_LINK.finditer(cur):
        _blank(chars, m.start(1), m.end(1))            # „[” sau „![”
        _blank(chars, m.start(3), m.end(3))            # „](url)”
    cur = "".join(chars)
    for m in _URL.finditer(cur):
        _blank(chars, m.start(), m.end())
    out = "".join(chars)
    assert len(out) == len(text)
    return out


# ---------- împărțire în bucăți ----------

def chunks(text: str, limit: int = CHUNK_LIMIT) -> list[tuple[int, str]]:
    """(poziția de start, bucata), tăiate la granițe de paragraf."""
    out, start = [], 0
    while start < len(text):
        if len(text) - start <= limit:
            out.append((start, text[start:]))
            break
        window = text[start:start + limit]
        cut = window.rfind("\n\n")
        if cut < limit // 4:
            cut = window.rfind("\n")
        if cut < limit // 4:
            cut = window.rfind(" ")
        cut = limit if cut <= 0 else cut + 1
        out.append((start, text[start:start + cut]))
        start += cut
    return out


# ---------- LanguageTool ----------

def lt_check(server: str, text: str, language: str, disabled: list[str]) -> list[Match]:
    data = {"text": text, "language": language}
    if disabled:
        data["disabledRules"] = ",".join(disabled)
    req = urllib.request.Request(server.rstrip("/") + "/v2/check", data=urllib.parse.urlencode(data).encode(),
                                 headers={"Content-Type": "application/x-www-form-urlencoded",
                                          "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            res = json.load(r)
    except urllib.error.HTTPError as e:
        raise config.EroareUtilizare(f"LanguageTool a răspuns cu HTTP {e.code}: "
                                     f"{e.read().decode(errors='replace')[:200]}") from e
    except (urllib.error.URLError, OSError) as e:
        raise config.EroareUtilizare(
            f"Serverul LanguageTool local ({server}) nu răspunde. Pornește-l cu: "
            "systemctl --user start unelte-languagetool") from e
    out = []
    for m in res.get("matches", []):
        rule = m.get("rule") or {}
        out.append(Match(offset=int(m["offset"]), length=int(m["length"]), message=m.get("message", ""),
                         rule=str(rule.get("id", "")), issue=str(rule.get("issueType", "")),
                         replacements=[r.get("value", "") for r in m.get("replacements", [])][:9]))
    return out


def check_text(text: str, cfg: dict, language: str, ignored: set[str], words: set[str],
               masked: bool = True) -> list[Match]:
    c = cfg["corecteaza"]
    source = mask_markdown(text) if masked else text
    found: list[Match] = []
    disabled = sorted(set(c.get("reguli_ignorate", [])) | ignored)
    for start, piece in chunks(source):
        if not piece.strip():
            continue
        for m in lt_check(c.get("server", "http://127.0.0.1:8081"), piece, language, disabled):
            m.offset += start
            found.append(m)
    return filter_matches(found, text, set(disabled), words)


def is_spelling(m: Match) -> bool:
    return m.issue == "misspelling" or "MORFOLOGIK" in m.rule or "HUNSPELL" in m.rule or "SPELL" in m.rule


def filter_matches(matches: list[Match], text: str, ignored: set[str], words: set[str]) -> list[Match]:
    out = []
    lowered = {w.casefold() for w in words}
    for m in matches:
        if m.rule in ignored:
            continue
        if is_spelling(m) and text[m.offset:m.offset + m.length].casefold() in lowered:
            continue
        out.append(m)
    return out


# ---------- dicționar personal ----------

def dict_path() -> Path:
    return config.config_dir() / "dictionar.txt"


def load_words() -> set[str]:
    try:
        return {ln.strip() for ln in dict_path().read_text(encoding="utf-8").splitlines()
                if ln.strip() and not ln.startswith("#")}
    except OSError:
        return set()


def add_word(word: str) -> bool:
    word = word.strip()
    if not word or word in load_words():
        return False
    dict_path().parent.mkdir(parents=True, exist_ok=True)
    with dict_path().open("a", encoding="utf-8") as f:
        f.write(word + "\n")
    return True


# ---------- raport ----------

def line_col(text: str, offset: int) -> tuple[int, int]:
    line = text.count("\n", 0, offset) + 1
    col = offset - (text.rfind("\n", 0, offset) + 1) + 1
    return line, col


def context(text: str, m: Match, width: int = 40, color: bool = False) -> str:
    a = max(0, m.offset - width)
    b = min(len(text), m.offset + m.length + width)
    before = text[a:m.offset].replace("\n", " ")
    bad = text[m.offset:m.offset + m.length]
    after = text[m.offset + m.length:b].replace("\n", " ")
    mark = f"\033[1;31m{bad}\033[0m" if color else f"[{bad}]"
    return f"{'…' if a else ''}{before}{mark}{after}{'…' if b < len(text) else ''}"


def report(text: str, matches: list[Match], color: bool, para_texts: list[str] | None = None) -> str:
    lines = []
    for m in matches:
        if para_texts is not None and m.paragraph is not None:
            loc = f"§{m.paragraph + 1}"
            ctx = context(para_texts[m.paragraph], m, color=color)
        else:
            ln, col = line_col(text, m.offset)
            loc = f"{ln}:{col}"
            ctx = context(text, m, color=color)
        sugg = f" → {', '.join(m.replacements[:5])}" if m.replacements else ""
        lines.append(f"{loc}  {m.message}{sugg}\n      {ctx}   ({m.rule})")
    return "\n".join(lines)


# ---------- .docx ----------

def check_docx(path: Path, cfg: dict, language: str, ignored: set[str], words: set[str]):
    from docx import Document
    doc = Document(str(path))
    paras = [p.text for p in doc.paragraphs]
    joined, starts = "", []
    for t in paras:
        starts.append(len(joined))
        joined += t + "\n\n"
    found = check_text(joined, cfg, language, ignored, words, masked=False)
    import bisect
    for m in found:
        k = bisect.bisect_right(starts, m.offset) - 1
        m.paragraph = k
        m.offset -= starts[k]
    return paras, found


# ---------- interactiv ----------

def interactive(text: str, matches: list[Match], words_cb=add_word, ask=None, color: bool = True) -> str:
    """Treci prin fiecare problemă. 1–9 aplică sugestia, s sare, i ignoră regula,
    a adaugă cuvântul în dicționar, q termină. Întoarce textul corectat."""
    ask = ask or input
    out = text
    delta = 0
    ignored_rules: set[str] = set()
    added: set[str] = set()
    for idx, m in enumerate(sorted(matches, key=lambda x: x.offset)):
        if m.rule in ignored_rules:
            continue
        start = m.offset + delta
        word = out[start:start + m.length]
        if word.casefold() in {w.casefold() for w in added}:
            continue
        print(f"\n[{idx + 1}/{len(matches)}] {m.message}  ({m.rule})")
        print("   " + context(out, Match(start, m.length, "", ""), color=color))
        for k, r in enumerate(m.replacements[:9], 1):
            print(f"   {k}) {r}")
        while True:
            try:
                choice = ask("Alege [1-9 / s=sari / i=ignoră regula / a=adaugă în dicționar / q=gata]: ").strip().lower()
            except EOFError:
                choice = "q"
            if choice.isdigit() and 1 <= int(choice) <= len(m.replacements[:9]):
                rep = m.replacements[int(choice) - 1]
                out = out[:start] + rep + out[start + m.length:]
                delta += len(rep) - m.length
                break
            if choice in ("s", ""):
                break
            if choice == "i":
                ignored_rules.add(m.rule)
                break
            if choice == "a":
                words_cb(word)
                added.add(word)
                break
            if choice == "q":
                return out
    return out


# ---------- stil ----------

def style_rewrite(text: str, model: str | None) -> str:
    progres = Progres()
    pieces = []
    try:
        limit = ai.max_chunk_chars("stil", STYLE_CHUNK, model)
        parts = chunks(text, limit)
        for k, (_s, piece) in enumerate(parts, 1):
            if not piece.strip():
                pieces.append(piece)
                continue
            if len(parts) > 1:
                progres(f"Stil: bucata {k} din {len(parts)}")
            r = ai.ruleaza("stil", prompturi.mesaje("stil", text=piece), model=model, la_progres=progres)
            out = re.sub(r"^```(?:markdown|md)?\s*\n(.*?)\n```\s*$", r"\1", r.text.strip(), flags=re.S)
            trailing = piece[len(piece.rstrip()):]
            pieces.append(out.strip() + trailing)
    finally:
        progres.gata()
    return "".join(pieces)


def word_diff(a: str, b: str, limit: int = 30) -> list[str]:
    wa, wb = a.split(), b.split()
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=wa, b=wb, autojunk=False).get_opcodes():
        if op == "equal":
            continue
        old, new = " ".join(wa[i1:i2]), " ".join(wb[j1:j2])
        out.append(f"- {old}  →  {new}" if old and new else (f"+ {new}" if new else f"- {old}"))
        if len(out) >= limit:
            break
    return out


# ---------- comanda ----------

def main(argv=None) -> int:
    ap = parser("corecteaza", "Gramatică și ortografie cu LanguageTool local; stil prin AI, la cerere.",
                "Exemple:\n  corecteaza text.md                  # raport cu greșelile\n"
                "  corecteaza text.md --interactiv     # alegi corectura pentru fiecare greșeală\n"
                "  corecteaza text.md --stil           # + rescriere de stil prin AI (text.stil.md)\n"
                "  corecteaza lucrare.docx             # doar raport\n"
                "  echo \"text\" | corecteaza -\n  corecteaza --adauga-cuvant Studiu\n\n"
                "Cod de ieșire: 0 = fără greșeli, 1 = greșeli găsite, 2 = eroare.")
    ap.add_argument("fisier", nargs="?", help="fișierul (.md, .txt, .docx) sau - pentru intrarea standard")
    ap.add_argument("--interactiv", action="store_true", help="treci prin fiecare greșeală (.md și .txt)")
    ap.add_argument("--stil", action="store_true", help="rescriere de stil prin AI, în <nume>.stil.md")
    ap.add_argument("--limba", help="limba LanguageTool (implicit din config, ro-RO)")
    ap.add_argument("--model", help="alias sau furnizor:model pentru --stil")
    ap.add_argument("--adauga-cuvant", metavar="CUVANT", help="adaugă un cuvânt în dicționarul personal")
    a = ap.parse_args(argv)
    if a.adauga_cuvant:
        print("Adăugat." if add_word(a.adauga_cuvant) else "Cuvântul era deja în dicționar.")
        return 0
    if not a.fisier:
        ap.error("lipsește fișierul (sau - pentru intrarea standard)")
    if a.model:
        ai.check_model_ref(a.model)
    cfg = config.load()
    language = a.limba or cfg["corecteaza"].get("limba", "ro-RO")
    words = load_words()
    color = sys.stdout.isatty()

    if a.fisier == "-":
        text = sys.stdin.read()
        matches = check_text(text, cfg, language, set(), words)
        if matches:
            print(report(text, matches, color))
        if a.stil:
            print("\n--- stil ---\n" + style_rewrite(text, a.model))
        return 1 if matches else 0

    path = Path(a.fisier)
    if not path.is_file():
        raise config.EroareUtilizare(f"Fișierul {path} nu există.")
    if path.suffix.lower() == ".docx":
        if a.interactiv or a.stil:
            print("Pentru .docx se face doar raportul (fără modificări în document).")
        paras, matches = check_docx(path, cfg, language, set(), words)
        print(report("", matches, color, paras) if matches else "Nicio greșeală găsită.")
        return 1 if matches else 0

    text = path.read_text(encoding="utf-8")
    is_md = path.suffix.lower() in (".md", ".markdown")
    matches = check_text(text, cfg, language, set(), words, masked=is_md)
    corrected = text
    if a.interactiv and matches:
        corrected = interactive(text, matches, color=color)
        if corrected != text:
            dest = fisiere.rezultat(path, "corectat")
            fisiere.scrie_atomic(dest, corrected)
            print(f"\nScris: {dest}")
        else:
            print("\nNicio corectură aplicată.")
    elif matches:
        print(report(text, matches, color))
        print(f"\n{len(matches)} probleme. Pentru corectură: corecteaza {path.name} --interactiv")
    else:
        print("Nicio greșeală găsită.")
    if a.stil:
        styled = style_rewrite(corrected, a.model)
        dest = fisiere.rezultat(path, "stil", ".md")
        fisiere.scrie_atomic(dest, styled)
        changes = word_diff(corrected, styled)
        print(f"\nStil: {dest}" + (f" ({len(changes)}{'+' if len(changes) >= 30 else ''} modificări)" if changes else
                                  " (nicio modificare)"))
        for c in changes:
            print("  " + c)
    return 1 if matches and corrected == text else 0
