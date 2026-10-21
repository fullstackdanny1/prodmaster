"""converteste – Markdown → Word (și PDF prin LibreOffice) cu șablonul profilului.

PDF-ul se face din .docx cu LibreOffice, ca să arate exact ca documentul Word (fără LaTeX).
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from . import verifica_format
from .cli import parser
from .comun import config, fisiere, jurnal, profil, sistem

log = jurnal.logger("converteste")


def has_lock(dest: Path) -> bool:
    """Fișier deschis în LibreOffice (.~lock.<nume>#) sau Word (~$<nume>)?"""
    d, n = dest.parent, dest.name
    return (d / f".~lock.{n}#").exists() or (d / f"~${n}").exists() or (d / f"~${n[2:]}").exists()


def output_path(src: Path, ext: str) -> Path:
    dest = src.with_suffix(ext)
    return fisiere.nume_liber(dest) if has_lock(dest) else dest


def pandoc_args(src: Path, dest: Path, prof: profil.Profil, meta: dict, bib: Path | None,
                cited: bool, title_page: bool) -> list[str]:
    r = prof.reguli
    args = ["pandoc", str(src), "--from", "markdown", "--to", "docx", "--output", str(dest),
            "--resource-path", str(src.parent.resolve()),
            "--metadata", "lang=ro-RO",
            "--metadata", f"reference-section-title={r['citari'].get('titlu_bibliografie', 'Bibliografie')}",
            "--metadata", "toc-title=Cuprins"]
    if prof.reference.is_file():
        args += ["--reference-doc", str(prof.reference)]
    if cited and bib is not None:
        args += ["--citeproc", "--bibliography", str(bib)]
        if prof.csl.is_file():
            args += ["--csl", str(prof.csl)]
    if title_page and prof.filtru_titlu.is_file():
        args += ["--lua-filter", str(prof.filtru_titlu)]       # filtrul pune și cuprinsul după pagina de titlu
    elif meta.get("cuprins") is True:
        args += ["--toc"]
    if r["titluri"].get("numerotate"):
        args += ["--number-sections"]
    return args


MACRO = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE script:module PUBLIC "-//OpenOffice.org//DTD OfficeDocument 1.0//EN" "module.dtd">
<script:module xmlns:script="http://openoffice.org/2000/script" script:name="Module1" script:language="StarBasic">
Sub ExportPdf(sIn As String, sOut As String)
  Dim args(0) As New com.sun.star.beans.PropertyValue
  args(0).Name = &quot;Hidden&quot;
  args(0).Value = True
  oDoc = StarDesktop.loadComponentFromURL(ConvertToURL(sIn), &quot;_blank&quot;, 0, args())
  oIdx = oDoc.getDocumentIndexes()
  For i = 0 To oIdx.getCount() - 1
    oIdx.getByIndex(i).update()
  Next
  Dim f(0) As New com.sun.star.beans.PropertyValue
  f(0).Name = &quot;FilterName&quot;
  f(0).Value = &quot;writer_pdf_Export&quot;
  oDoc.storeToURL(ConvertToURL(sOut), f())
  oDoc.close(True)
End Sub
</script:module>
"""


def to_pdf(docx: Path) -> Path:
    """PDF din .docx cu LibreOffice, într-un profil temporar (nu intră în conflict cu o instanță
    deschisă). Un macro actualizează întâi cuprinsul; dacă nu reușește, conversie simplă."""
    soffice = sistem.necesita("soffice")
    dest = output_path(docx, ".pdf")
    with tempfile.TemporaryDirectory(prefix="unelte-lo-") as tmp:
        prof_url = f"-env:UserInstallation=file://{tmp}/profil"
        produced = Path(tmp) / f"{docx.stem}.pdf"
        base = [soffice, "--headless", "--norestore", prof_url]
        init = sistem.ruleaza(base + ["--terminate_after_init"], timeout=120)
        module = Path(tmp) / "profil" / "user" / "basic" / "Standard" / "Module1.xba"
        if init.returncode == 0 and module.parent.is_dir():
            module.write_text(MACRO, encoding="utf-8")
            sistem.ruleaza(base + [f'macro:///Standard.Module1.ExportPdf("{docx.resolve()}","{produced}")'],
                           timeout=300)
        if not produced.exists():
            outdir = Path(tmp) / "out"
            r = sistem.ruleaza(base + ["--convert-to", "pdf", "--outdir", str(outdir), str(docx)], timeout=300)
            produced = outdir / f"{docx.stem}.pdf"
            if r.returncode != 0 or not produced.exists():
                raise config.EroareUtilizare(
                    f"LibreOffice nu a putut crea PDF-ul: {(r.stderr or r.stdout).strip()[-300:]}")
        shutil.move(str(produced), str(dest))
    return dest


def convert(src: Path, prof: profil.Profil, cfg: dict, pdf: bool = False, no_title: bool = False,
            verify: bool = True, out=print) -> tuple[Path, Path | None, verifica_format.Report | None]:
    if not src.is_file():
        raise config.EroareUtilizare(f"Fișierul {src} nu există.")
    sistem.necesita("pandoc")
    text = src.read_text(encoding="utf-8", errors="replace")
    meta, body = verifica_format.split_front_matter(text)
    keys = verifica_format.citation_keys(body)
    bib = config.cale(meta.get("bibliography") or cfg["documente"].get("bibliografie", ""))
    if keys:
        if not bib.is_file():
            out(f"Atenție: documentul are {len(keys)} citări, dar bibliografia {bib} nu există; "
                "pandoc le va marca cu „???”.")
        else:
            missing = [k for k in keys if k not in verifica_format.bib_keys(bib)]
            if missing:
                out(f"Atenție: citări fără intrare în bibliografie ({len(missing)}): " + ", ".join(missing))
    title_page = bool(prof.reguli["pagina_titlu"].get("activa")) and not no_title
    if title_page:
        aliases = {"titlu": ("titlu", "title"), "autor": ("autor", "author")}
        absent = [f for f in prof.reguli["pagina_titlu"].get("campuri", [])
                  if not any(meta.get(k) for k in aliases.get(f, (f,)))]
        if absent:
            out("Atenție: antetul nu are câmpurile paginii de titlu: " + ", ".join(absent))
    dest = output_path(src, ".docx")
    args = pandoc_args(src, dest, prof, meta, bib if bib.is_file() else None, bool(keys), title_page)
    log.info("pandoc %s", " ".join(args[1:]))
    r = sistem.ruleaza(args, timeout=300)
    if r.returncode != 0:
        raise config.EroareUtilizare(f"pandoc a eșuat: {(r.stderr or '').strip()[-500:]}")
    for line in (r.stderr or "").splitlines():
        if line.strip():
            out(f"pandoc: {line.strip()}")
    out(f"Scris: {dest}")
    if meta.get("cuprins") is True:
        out("Cuprinsul din .docx se completează în Word cu clic dreapta → „Actualizare câmp” "
            "(în PDF e completat automat).")
    pdf_path = to_pdf(dest) if pdf else None
    if pdf_path:
        out(f"Scris: {pdf_path}")
    rep = None
    if verify:
        rep = verifica_format.check_docx(dest, prof)
        out(rep.summary() + (f" (detalii: verifica-format {dest.name})" if rep.problems else ""))
    return dest, pdf_path, rep


def main(argv=None) -> int:
    ap = parser("converteste", "Convertește un document Markdown în Word (și PDF) cu șablonul profilului.",
                "Exemple:\n  converteste lucrare.md                 # → lucrare.docx\n"
                "  converteste lucrare.md --pdf           # → lucrare.docx și lucrare.pdf\n"
                "  converteste lucrare.md --profil licenta\n  converteste notita.md --fara-pagina-titlu\n\n"
                "Antetul YAML (titlu, autor, coordonator, universitate, facultate, oras, an, cuprins: true)\n"
                "completează pagina de titlu; citările se scriu [@cheie] sau [@cheie, p. 12].")
    ap.add_argument("fisier", type=Path)
    ap.add_argument("--pdf", action="store_true", help="creează și PDF-ul (cu LibreOffice)")
    ap.add_argument("--profil", help="numele profilului (implicit din [documente].profil_implicit)")
    ap.add_argument("--fara-pagina-titlu", action="store_true", help="fără pagina de titlu")
    ap.add_argument("--fara-verificare", action="store_true", help="nu rula verifica-format la final")
    a = ap.parse_args(argv)
    cfg = config.load()
    prof = profil.incarca(a.profil, cfg)
    convert(a.fisier, prof, cfg, pdf=a.pdf, no_title=a.fara_pagina_titlu, verify=not a.fara_verificare)
    return 0
