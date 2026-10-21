"""verifica-format – verifică un .docx (sau citările unui .md) după regulile unui profil.

Formatarea efectivă a fiecărui paragraf se calculează în ordinea: proprietățile run-ului →
proprietățile paragrafului → stilul paragrafului și lanțul based_on → docDefaults.
Problemele repetate se comprimă într-o singură linie.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .cli import parser
from .comun import config, fisiere, profil

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
A_NS = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
M_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"
EMU_PER_CM = 360000
TWIPS_PER_CM = 566.929
PAGE_SIZES = {"A4": (21.0, 29.7), "A5": (14.8, 21.0), "Letter": (21.59, 27.94)}
ALIGN_NAMES = {"both": "justify", "distribute": "justify", "left": "left", "start": "left", "center": "center",
               "right": "right", "end": "right"}
ALIGN_RO = {"justify": "justificat", "left": "la stânga", "center": "centrat", "right": "la dreapta"}
NOT_BODY = re.compile(r"heading|titlu|title|subtitle|caption|legend|toc|cuprins|bibliograph|footnote|"
                      r"endnote|list|compact|source|code|quote|block|table|tabel|header|footer|author|date|"
                      r"abstract|figure|pagina titlu|definition|term|frontispiciu", re.I)
MARGIN_TOL_CM = 0.05


# ---------- probleme și raport ----------

@dataclass
class Problem:
    category: str
    where: str            # „§12 «primele cuvinte»” sau „secțiunea 1”
    found: str
    expected: str
    key: str = ""         # problemele cu aceeași cheie se comprimă

    def line(self) -> str:
        return f"{self.where}: {self.found}; cerut: {self.expected}"


@dataclass
class Report:
    file: str
    problems: list[Problem] = field(default_factory=list)
    info: list[str] = field(default_factory=list)

    def add(self, category, where, found, expected, key=""):
        self.problems.append(Problem(category, where, found, expected, key or f"{category}|{found}|{expected}"))

    def grouped(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = defaultdict(list)
        groups: dict[str, list[Problem]] = defaultdict(list)
        order = []
        for p in self.problems:
            if p.key not in groups:
                order.append(p.key)
            groups[p.key].append(p)
        for k in order:
            ps = groups[k]
            p = ps[0]
            if len(ps) == 1:
                out[p.category].append(p.line())
            else:
                out[p.category].append(f"{_count(len(ps), _plural_unit(p.category))} au {p.found} în loc de {p.expected} "
                                       f"(primul: {p.where})")
        return out

    def text(self, markdown: bool = False) -> str:
        lines = []
        if markdown:
            lines.append(f"# Verificarea formatării: {Path(self.file).name}\n")
        if not self.problems:
            lines.append("Nicio problemă găsită." if not markdown else "Nicio problemă găsită.\n")
        for cat, items in self.grouped().items():
            lines.append(f"## {cat}\n" if markdown else f"{cat}:")
            for it in items:
                lines.append(f"- {it}" if markdown else f"  - {it}")
            lines.append("")
        for i in self.info:
            lines.append(f"> {i}" if markdown else f"Info: {i}")
        return "\n".join(lines).rstrip() + "\n"

    def summary(self) -> str:
        if not self.problems:
            return "verifica-format: nicio problemă"
        cats = self.grouped()
        return (f"verifica-format: {len(self.problems)} probleme ("
                + ", ".join(f"{k.lower()}: {len(v)}" for k, v in cats.items()) + ")")


def _count(n: int, unit: str) -> str:
    """În română, de la 20 în sus (și la 0 sau 100, 101…) numeralul cere „de”: 140 de paragrafe."""
    return f"{n} de {unit}" if n % 100 >= 20 or n % 100 == 0 else f"{n} {unit}"


def _plural_unit(category: str) -> str:
    return {"Titluri": "titluri", "Pagina": "secțiuni", "Figuri": "figuri"}.get(category, "paragrafe")


def where(index: int, text: str) -> str:
    t = " ".join(text.split())
    return f"§{index} «{t[:60]}{'…' if len(t) > 60 else ''}»"


# ---------- rezolvarea formatării efective ----------

class Styles:
    """Proprietățile stilurilor, cu lanțul based_on și docDefaults."""

    def __init__(self, doc):
        self.doc = doc
        root = doc.styles.element
        self.by_id = {s.get(f"{W}styleId"): s for s in root.findall(f"{W}style")}
        dd = root.find(f"{W}docDefaults")
        self.default_rpr = dd.find(f"{W}rPrDefault/{W}rPr") if dd is not None else None
        self.default_ppr = dd.find(f"{W}pPrDefault/{W}pPr") if dd is not None else None
        self.default_para = next((s.get(f"{W}styleId") for s in self.by_id.values()
                                  if s.get(f"{W}type") == "paragraph" and s.get(f"{W}default") in ("1", "true")),
                                 None)
        self.theme_fonts = self._theme_fonts()

    def _theme_fonts(self) -> dict:
        fonts = {}
        try:
            part = self.doc.part.part_related_by(
                "http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme")
        except KeyError:
            return fonts
        from lxml import etree
        root = etree.fromstring(part.blob)
        for kind in ("major", "minor"):
            el = root.find(f".//{A_NS}{kind}Font/{A_NS}latin")
            if el is not None:
                fonts[kind] = el.get("typeface")
        return fonts

    def chain(self, style_id: str | None) -> list:
        out, seen = [], set()
        sid = style_id or self.default_para
        while sid and sid in self.by_id and sid not in seen:
            seen.add(sid)
            st = self.by_id[sid]
            out.append(st)
            based = st.find(f"{W}basedOn")
            sid = based.get(f"{W}val") if based is not None else None
        return out

    def name(self, style_id: str | None) -> str:
        st = self.by_id.get(style_id or self.default_para)
        if st is None:
            return style_id or ""
        n = st.find(f"{W}name")
        return n.get(f"{W}val") if n is not None else style_id

    def _font_from_rpr(self, rpr):
        if rpr is None:
            return None
        f = rpr.find(f"{W}rFonts")
        if f is None:
            return None
        theme = f.get(f"{W}asciiTheme") or f.get(f"{W}hAnsiTheme")
        if theme:
            return self.theme_fonts.get("major" if theme.startswith("major") else "minor")
        return f.get(f"{W}ascii") or f.get(f"{W}hAnsi")

    @staticmethod
    def _size_from_rpr(rpr):
        if rpr is None:
            return None
        sz = rpr.find(f"{W}sz")
        return int(sz.get(f"{W}val")) / 2 if sz is not None and sz.get(f"{W}val") else None

    def run_value(self, rprs: list, getter):
        for rpr in rprs:
            v = getter(rpr)
            if v is not None:
                return v
        return None

    def rpr_chain(self, style_id):
        """rPr din lanțul stilului paragrafului, apoi docDefaults."""
        return [st.find(f"{W}rPr") for st in self.chain(style_id)] + [self.default_rpr]

    def ppr_chain(self, style_id):
        return [st.find(f"{W}pPr") for st in self.chain(style_id)] + [self.default_ppr]


def _ppr_attr(pprs: list, child: str, attr: str):
    for ppr in pprs:
        if ppr is None:
            continue
        el = ppr.find(f"{W}{child}")
        if el is not None and el.get(f"{W}{attr}") is not None:
            return el.get(f"{W}{attr}")
    return None


@dataclass
class Effective:
    font: str | None
    size: float | None
    line_spacing: float | None     # multiplu (lineRule auto) sau None
    align: str
    first_indent_cm: float


def effective(p, styles: Styles) -> Effective:
    """Formatarea efectivă: run → paragraf → stil (based_on) → docDefaults."""
    ppr = p._p.pPr
    sid = None
    if ppr is not None and ppr.find(f"{W}pStyle") is not None:
        sid = ppr.find(f"{W}pStyle").get(f"{W}val")
    pprs = [ppr] + styles.ppr_chain(sid)
    style_rprs = styles.rpr_chain(sid)

    # textul paragrafului: fontul și mărimea dominante (după numărul de caractere)
    fonts: dict = defaultdict(int)
    sizes: dict = defaultdict(int)
    for r in p._p.findall(f"{W}r") + p._p.findall(f"{W}hyperlink/{W}r"):
        text = "".join(t.text or "" for t in r.findall(f"{W}t"))
        if not text.strip():
            continue
        rpr = r.find(f"{W}rPr")
        rprs = [rpr]
        rstyle = rpr.find(f"{W}rStyle") if rpr is not None else None
        if rstyle is not None:
            rprs += [st.find(f"{W}rPr") for st in styles.chain(rstyle.get(f"{W}val"))]
        rprs += style_rprs
        fonts[styles.run_value(rprs, styles._font_from_rpr)] += len(text)
        sizes[styles.run_value(rprs, styles._size_from_rpr)] += len(text)
    font = max(fonts, key=fonts.get) if fonts else styles.run_value(style_rprs, styles._font_from_rpr)
    size = max(sizes, key=sizes.get) if sizes else styles.run_value(style_rprs, styles._size_from_rpr)
    size = size if size is not None else 10.0      # valoarea implicită Word când nu e definită nicăieri

    line, rule = _ppr_attr(pprs, "spacing", "line"), _ppr_attr(pprs, "spacing", "lineRule")
    spacing = int(line) / 240 if line and (rule in (None, "auto")) else None
    jc = _ppr_attr(pprs, "jc", "val") or "left"
    first = _ppr_attr(pprs, "ind", "firstLine")
    hanging = _ppr_attr(pprs, "ind", "hanging")
    indent = int(first) / TWIPS_PER_CM if first else (-int(hanging) / TWIPS_PER_CM if hanging else 0.0)
    return Effective(font, size, spacing, ALIGN_NAMES.get(jc, jc), indent)


# ---------- verificări ----------

def _heading_level(name: str) -> int | None:
    m = re.match(r"(?:heading|titlu)\s*(\d)$", name.strip(), re.I)
    return int(m.group(1)) if m else None


def _has_drawing(p) -> bool:
    return bool(p._p.findall(f".//{W}drawing") or p._p.findall(f".//{W}pict"))


def _only_math(p) -> bool:
    has_math = bool(p._p.findall(f".//{M_NS}oMath") or p._p.findall(f".//{M_NS}oMathPara"))
    text = "".join(t.text or "" for t in p._p.findall(f"{W}r/{W}t"))
    return has_math and not text.strip()


def _is_list(p) -> bool:
    ppr = p._p.pPr
    return ppr is not None and ppr.find(f"{W}numPr") is not None


def _footer_has_page(section) -> bool:
    for footer in (section.footer, section.first_page_footer, section.even_page_footer):
        try:
            el = footer._element
        except Exception:  # noqa: BLE001 - subsol inexistent
            continue
        if el is None:
            continue
        for f in el.iter(f"{W}fldSimple"):
            if re.search(r"\bPAGE\b", f.get(f"{W}instr", "")):
                return True
        if any(re.search(r"\bPAGE\b", t.text or "") for t in el.iter(f"{W}instrText")):
            return True
    return False


def check_page(doc, rules: dict, rep: Report) -> None:
    pg = rules["pagina"]
    want_w, want_h = PAGE_SIZES.get(pg.get("format", "A4"), PAGE_SIZES["A4"])
    margins = pg.get("margini_cm", {})
    names = {"sus": ("top_margin", "sus"), "jos": ("bottom_margin", "jos"),
             "stanga": ("left_margin", "stânga"), "dreapta": ("right_margin", "dreapta")}
    for i, s in enumerate(doc.sections, 1):
        loc = f"secțiunea {i}"
        if s.page_width and s.page_height:
            w, h = s.page_width / EMU_PER_CM, s.page_height / EMU_PER_CM
            if abs(min(w, h) - want_w) > 0.1 or abs(max(w, h) - want_h) > 0.1:
                rep.add("Pagina", loc, f"format {w:.1f}×{h:.1f} cm", f"{pg.get('format', 'A4')} ({want_w}×{want_h} cm)")
        for key, (attr, ro) in names.items():
            if key not in margins:
                continue
            val = getattr(s, attr)
            if val is None:
                continue
            cm = val / EMU_PER_CM
            if abs(cm - float(margins[key])) > MARGIN_TOL_CM:
                rep.add("Pagina", loc, f"marginea {ro} {cm:.2f} cm", f"{float(margins[key]):.2f} cm")
        if pg.get("numerotare") and not _footer_has_page(s):
            rep.add("Pagina", loc, "fără număr de pagină în subsol", "câmp PAGE în subsol")


def _fmt_font(font, size) -> str:
    return f"{font or 'font nedefinit'} {size:g}"


def check_paragraphs(doc, rules: dict, rep: Report, styles: Styles) -> None:
    t = rules["text"]
    want_font, want_size = t.get("font"), float(t.get("marime_pt", 12))
    want_spacing = float(t.get("spatiere_rand", 1.5))
    want_align = t.get("aliniere", "justify")
    want_indent = float(t.get("indent_prima_linie_cm", 0))
    heads = rules["titluri"]
    h_font, h_sizes = heads.get("font", want_font), heads.get("marimi_pt", [])
    last_level = 0
    paragraphs = doc.paragraphs
    for i, p in enumerate(paragraphs, 1):
        text = p.text
        sid = None
        if p._p.pPr is not None and p._p.pPr.find(f"{W}pStyle") is not None:
            sid = p._p.pPr.find(f"{W}pStyle").get(f"{W}val")
        sname = styles.name(sid)
        level = _heading_level(sname)
        if level:
            if not text.strip():
                continue
            e = effective(p, styles)
            if last_level and level > last_level + 1:
                rep.add("Titluri", where(i, text), f"Heading {level} după Heading {last_level}",
                        f"cel mult Heading {last_level + 1}", key=f"ierarhie|{i}")
            last_level = level
            if level <= len(h_sizes):
                want = f"{h_font} {float(h_sizes[level - 1]):g}"
                got = _fmt_font(e.font, e.size)
                if (h_font and e.font != h_font) or abs((e.size or 0) - float(h_sizes[level - 1])) > 0.01:
                    rep.add("Titluri", where(i, text), f"Heading {level} cu {got}", want)
            continue
        if not text.strip() or NOT_BODY.search(sname) or _is_list(p) or _only_math(p) or _has_drawing(p):
            continue
        e = effective(p, styles)
        found_font = _fmt_font(e.font, e.size)
        want_txt = f"{want_font} {want_size:g}"
        if (want_font and e.font != want_font) or abs((e.size or 0) - want_size) > 0.01:
            rep.add("Text", where(i, text), found_font, want_txt)
        if e.line_spacing is None or abs(e.line_spacing - want_spacing) > 0.01:
            got = f"spațiere {e.line_spacing:g}" if e.line_spacing else "spațiere fixă sau nedefinită"
            rep.add("Text", where(i, text), got, f"spațiere {want_spacing:g}")
        if e.align != want_align:
            rep.add("Text", where(i, text), f"aliniere {ALIGN_RO.get(e.align, e.align)}",
                    f"aliniere {ALIGN_RO.get(want_align, want_align)}")
        if abs(e.first_indent_cm - want_indent) > MARGIN_TOL_CM:
            rep.add("Text", where(i, text), f"indent {e.first_indent_cm:.2f} cm", f"indent {want_indent:.2f} cm")


def check_figures(doc, rules: dict, rep: Report, styles: Styles) -> None:
    if not rules["figuri"].get("legenda_obligatorie"):
        return
    ps = doc.paragraphs
    for i, p in enumerate(ps):
        if not _has_drawing(p):
            continue
        nxt = next((q for q in ps[i + 1:] if q.text.strip() or _has_drawing(q)), None)
        ok = False
        if nxt is not None and not _has_drawing(nxt):
            sid = nxt._p.pPr.find(f"{W}pStyle").get(f"{W}val") if (
                nxt._p.pPr is not None and nxt._p.pPr.find(f"{W}pStyle") is not None) else None
            name = styles.name(sid).lower()
            ok = "caption" in name or "legend" in name or nxt.text.strip().lower().startswith(("figura", "fig."))
        if not ok:
            rep.add("Figuri", where(i + 1, p.text or "(imagine)"), "imagine fără legendă",
                    "o legendă imediat după imagine (stil Caption sau „Figura …”)", key="figura-fara-legenda")


def check_citations(doc, rules: dict, rep: Report, styles: Styles) -> None:
    body = doc.element.body
    xml_text = " ".join((t.text or "") for t in body.iter(f"{W}instrText"))
    xml_text += " ".join(f.get(f"{W}instr", "") for f in body.iter(f"{W}fldSimple"))
    if "ADDIN ZOTERO_ITEM" in xml_text:
        if "ADDIN ZOTERO_BIBL" not in xml_text:
            rep.add("Citări", "document", "citări Zotero fără bibliografie",
                    "câmpul de bibliografie Zotero (Add/Edit Bibliography)")
        return
    cit = rules["citari"]
    if not cit.get("bibliografie_obligatorie"):
        return
    title = str(cit.get("titlu_bibliografie", "Bibliografie")).strip().casefold()
    ps = doc.paragraphs
    for i, p in enumerate(ps):
        sid = p._p.pPr.find(f"{W}pStyle").get(f"{W}val") if (
            p._p.pPr is not None and p._p.pPr.find(f"{W}pStyle") is not None) else None
        heading = re.sub(r"^\d+(?:\.\d+)*\.?\s+", "", p.text.strip()).casefold()   # fără „2 ” de la numerotare
        if _heading_level(styles.name(sid)) and heading == title:
            entries = []
            for q in ps[i + 1:]:
                qsid = q._p.pPr.find(f"{W}pStyle").get(f"{W}val") if (
                    q._p.pPr is not None and q._p.pPr.find(f"{W}pStyle") is not None) else None
                if _heading_level(styles.name(qsid)):
                    break
                if q.text.strip():
                    entries.append(q)
            if not entries:
                rep.add("Citări", where(i + 1, p.text), "titlul bibliografiei fără nicio intrare",
                        "cel puțin o intrare după titlu")
            return
    rep.add("Citări", "document", "lipsește bibliografia", f"un titlu „{cit.get('titlu_bibliografie')}” urmat de intrări")


def check_docx(path: Path, prof: profil.Profil) -> Report:
    from docx import Document
    try:
        doc = Document(str(path))
    except Exception as e:  # noqa: BLE001 - fișier stricat sau alt format
        raise config.EroareUtilizare(f"Nu pot deschide {path} ca document Word: {e}") from e
    rep = Report(str(path))
    styles = Styles(doc)
    check_page(doc, prof.reguli, rep)
    check_paragraphs(doc, prof.reguli, rep, styles)
    check_figures(doc, prof.reguli, rep, styles)
    check_citations(doc, prof.reguli, rep, styles)
    return rep


# ---------- Markdown și bibliografie ----------

_BIB_ENTRY = re.compile(r"@\s*(\w+)\s*[{(]\s*([^,\s]+)\s*,")
_CODE_FENCE = re.compile(r"^(```|~~~).*?^\1\s*$", re.S | re.M)
_INLINE_CODE = re.compile(r"`[^`\n]*`")
_CITE = re.compile(r"(?<![\w.@])-?@([A-Za-z0-9_][\w:.#$%&+?<>~/-]*)")


def bib_keys(path: Path) -> set[str]:
    """Parser BibTeX minimal: doar cheile intrărilor."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        raise config.EroareUtilizare(f"Nu pot citi bibliografia {path}: {e}") from e
    return {m.group(2) for m in _BIB_ENTRY.finditer(text)
            if m.group(1).lower() not in ("comment", "string", "preamble")}


def split_front_matter(text: str) -> tuple[dict, str]:
    """Antet YAML simplu (cheie: valoare, liste pe un rând) – suficient pentru câmpurile paginii de titlu."""
    m = re.match(r"\A---[ \t]*\r?\n(.*?)\r?\n(?:---|\.\.\.)[ \t]*(?:\r?\n|\Z)", text, re.S)
    if not m:
        return {}, text
    meta: dict = {}
    key = None
    for line in m.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        kv = re.match(r"^([A-Za-z_][\w-]*)\s*:\s*(.*)$", line)
        if kv:
            key, val = kv.group(1), kv.group(2).strip()
            if val.startswith(("'", '"')) and val.endswith(val[0]) and len(val) >= 2:
                val = val[1:-1]
            low = val.lower()
            meta[key] = True if low in ("true", "da", "yes") else False if low in ("false", "nu", "no") else val
        elif key and line.startswith((" ", "\t")):
            item = line.strip().lstrip("- ").strip()
            prev = meta.get(key)
            meta[key] = (prev + " " if isinstance(prev, str) and prev else "") + item if not isinstance(prev, bool) else item
    return meta, text[m.end():]


def citation_keys(md: str) -> list[str]:
    body = _INLINE_CODE.sub("", _CODE_FENCE.sub("", md))
    body = re.sub(r"\$\$.*?\$\$|\$[^$\n]+\$", "", body, flags=re.S)
    keys = []
    for m in _CITE.finditer(body):
        k = m.group(1).rstrip(".:;,")
        if k not in keys:
            keys.append(k)
    return keys


def check_markdown(path: Path, prof: profil.Profil, cfg: dict) -> Report:
    text = path.read_text(encoding="utf-8", errors="replace")
    meta, body = split_front_matter(text)
    rep = Report(str(path))
    keys = citation_keys(body)
    bib = config.cale(meta.get("bibliography") or cfg["documente"].get("bibliografie", ""))
    if keys:
        if not bib.is_file():
            rep.add("Citări", "document", f"{len(keys)} citări, dar bibliografia {bib} nu există",
                    "[documente].bibliografie spre exportul Better BibTeX")
        else:
            known = bib_keys(bib)
            missing = [k for k in keys if k not in known]
            for k in missing:
                rep.add("Citări", f"@{k}", "cheie inexistentă în bibliografie", f"o intrare în {bib.name}",
                        key=f"cheie|{k}")
            used = [k for k in keys if k in known]
            rep.info.append(f"Intrări din bibliografie folosite ({len(used)}): " + (", ".join(used) or "niciuna"))
            if missing:
                rep.info.append(f"Chei lipsă ({len(missing)}): " + ", ".join(missing))
    pt = prof.reguli["pagina_titlu"]
    if pt.get("activa"):
        aliases = {"titlu": ("titlu", "title"), "autor": ("autor", "author")}
        for f in pt.get("campuri", []):
            if not any(meta.get(k) for k in aliases.get(f, (f,))):
                rep.add("Pagina de titlu", "antet", f"lipsește câmpul «{f}»", "toate câmpurile din pagina_titlu.campuri",
                        key=f"camp|{f}")
    return rep


def check(path: Path, prof: profil.Profil, cfg: dict) -> Report:
    ext = path.suffix.lower()
    if ext == ".docx":
        return check_docx(path, prof)
    if ext in (".md", ".markdown"):
        return check_markdown(path, prof, cfg)
    raise config.EroareUtilizare(f"Pot verifica doar .docx și .md (nu «{ext}»).")


def main(argv=None) -> int:
    ap = parser("verifica-format", "Verifică formatarea unui document după regulile profilului.",
                "Exemple:\n  verifica-format lucrare.docx\n  verifica-format lucrare.docx --profil licenta\n"
                "  verifica-format lucrare.md            # citările față de bibliografie\n"
                "  verifica-format lucrare.docx --raport raport.md\n\n"
                "Cod de ieșire: 0 = fără probleme, 1 = probleme găsite, 2 = eroare.")
    ap.add_argument("fisier", type=Path)
    ap.add_argument("--profil", help="numele profilului (implicit din [documente].profil_implicit)")
    ap.add_argument("--raport", type=Path, help="scrie raportul și în acest fișier Markdown")
    a = ap.parse_args(argv)
    if not a.fisier.is_file():
        raise config.EroareUtilizare(f"Fișierul {a.fisier} nu există.")
    cfg = config.load()
    prof = profil.incarca(a.profil, cfg)
    rep = check(a.fisier, prof, cfg)
    print(rep.text(), end="")
    if a.raport:
        dest = fisiere.nume_liber(a.raport) if a.raport.resolve() == a.fisier.resolve() else a.raport
        fisiere.scrie_atomic(dest, rep.text(markdown=True))
        print(f"Raport scris în {dest}")
    return 1 if rep.problems else 0
