import pytest
from conftest import ROOT, write

from app import importer, jobs, library, storage, system, transcriere

ARTICLE = """<html><head><title>Rata lichidității explicată</title></head><body>
<nav>Meniu Acasă Contact</nav>
<article><h1>Rata lichidității explicată</h1>
<p>Lichiditatea curentă arată dacă o firmă își poate plăti datoriile pe termen scurt din activele circulante.
Indicatorul se calculează împărțind activele circulante la datoriile curente ale firmei.</p>
<p>O valoare în jur de 2 este considerată confortabilă, iar una sub 1 sugerează posibile dificultăți de plată.
Analiștii o compară cu media sectorului și cu evoluția din anii anteriori.</p>
<ul><li>Active circulante: stocuri, creanțe, numerar.</li><li>Datorii curente: furnizori, salarii, taxe.</li></ul>
</article><footer>© 2026</footer></body></html>"""


def test_articol_din_html_local(notes):
    (notes / "Fin").mkdir()
    rel = importer.import_article(ARTICLE, "https://exemplu.ro/articol", "Fin")
    text = (notes / rel).read_text()
    meta, body = library.split_frontmatter(text)
    assert meta["sursa"] == "web" and meta["sursa_url"] == "https://exemplu.ro/articol"
    assert library.valid_id(meta["id"]) and library.is_usable(meta) and not library.is_unverified(meta)
    assert "activele circulante" in body and "Meniu" not in body
    assert rel.startswith("Fin/01 ")


def test_articol_prea_scurt(notes):
    with pytest.raises(importer.ImportError_, match="nu are un articol"):
        importer.extract_article("<html><body><p>Autentifică-te.</p></body></html>")


def _pdf(path, pages):
    import pymupdf
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        if text:
            page.insert_text((72, 72), text)
    doc.set_metadata({"title": "Curs 3 - Bilanțul"})
    doc.save(str(path))


def test_pdf_mic_devine_notita(notes, fake_ai, tmp_path):
    (notes / "Fin").mkdir()
    pdf = tmp_path / "curs.pdf"
    _pdf(pdf, ["Bilantul contabil cuprinde activele si pasivele firmei la o anumita data. " * 2,
               "Activele circulante includ stocurile, creantele si disponibilitatile banesti. " * 2])
    est = importer.estimate_file(pdf)
    assert est["pagini"] == 2 and not est["scanat"] and est["bucati"] == 1 and est["gratuit"]
    stored = importer.store_upload("curs.pdf", pdf.read_bytes())
    fake_ai.reply("## Bilanțul\n\n- active și pasive")
    job_id = jobs.submit("import_pdf", {**stored, "folder": "Fin", "nume": ""}, "curs.pdf")
    jobs.wait_idle()
    job = jobs.get(job_id)
    assert job["stare"] == "gata", job["mesaj"]
    rel = job["rezultat"]["path"]
    meta, body = library.split_frontmatter((notes / rel).read_text())
    assert meta["sursa"] == "ai" and meta["verificat"] is False and meta["sursa_fisier"] == stored["sursa"]
    assert body.lstrip().startswith("# Curs 3 - Bilanțul\n") and "## Bilanțul" in body
    assert storage.path("surse", f"{stored['sursa']}.txt").read_text().startswith("[pagina 1]")
    prompt = fake_ai.chat_requests[0]["json"]["messages"][-1]["content"]
    assert "bucata 1 din 1" in prompt and "Bilantul contabil" in prompt


def test_pdf_fara_text_cere_ocr(notes, tmp_path, monkeypatch):
    pdf = tmp_path / "scan.pdf"
    _pdf(pdf, ["", ""])
    monkeypatch.setattr(importer.shutil, "which", lambda name: None)
    est = importer.estimate_file(pdf)
    assert est["scanat"] and "OCR" in est["avertisment"]
    stored = importer.store_upload("scan.pdf", pdf.read_bytes())
    job_id = jobs.submit("import_pdf", {**stored, "folder": ""}, "scan.pdf")
    jobs.wait_idle()
    job = jobs.get(job_id)
    assert job["stare"] == "eroare" and "ocrmypdf" in job["mesaj"]


def test_sarcina_intrerupta_poate_fi_reluata(notes, fake_ai, tmp_path):
    pdf = tmp_path / "c.pdf"
    _pdf(pdf, ["Text de curs suficient de lung pentru a nu fi considerat scanat de aplicatie."])
    stored = importer.store_upload("c.pdf", pdf.read_bytes())
    from app import cache
    with cache.connect() as con:
        con.execute("INSERT INTO jobs(id, tip, parametri, stare, progres, mesaj, eticheta, creat_la, actualizat_la) "
                    "VALUES('j1','import_pdf',?,'in_lucru',40,'','c.pdf','t','t')",
                    (__import__("json").dumps({**stored, "folder": ""}),))
    assert jobs.mark_interrupted() == 1
    assert jobs.get("j1")["mesaj"] == jobs.INTERRUPTED
    fake_ai.reply("## Notițe")
    jobs.resume("j1")
    jobs.wait_idle()
    assert jobs.get("j1")["stare"] == "gata"


def test_nume_fara_suprascriere(notes):
    write(notes, "M/01 Curs.md", "x")
    a = library.write_new_note("M", "Curs", {"sursa": "web"}, "# A\n")
    b = library.write_new_note("M", "02 Curs", {"sursa": "web"}, "# B\n")
    assert a == "M/02 Curs.md" and b == "M/02 Curs (2).md"


def test_tip_nesuportat():
    with pytest.raises(importer.ImportError_):
        importer.kind_of("x.docx")
    assert importer.kind_of("a.MP4") == "media" and importer.kind_of("b.pdf") == "pdf"


def test_impartire_in_bucati():
    pages = ["a" * 5000, "b" * 5000, "c" * 5000]
    chunks = importer.split_text(pages, 12000)
    assert len(chunks) == 2 and chunks[0].count("a") == 5000
    big = importer.split_text(["cuvant " * 5000], 12000)
    assert all(len(c) <= 12000 for c in big) and len(big) == 3


def test_transcriere_paragrafe():
    segs = [(0, 5, "Bună ziua."), (30, 40, "Azi vorbim despre bilanț."), (65, 70, "Primul capitol."),
            (80, 90, "Al doilea.")]
    out = transcriere.paragraphs(segs)
    assert out.startswith("[00:00] Bună ziua.") and "\n\n[01:20] Al doilea." in out


def test_fara_ffmpeg(monkeypatch, tmp_path):
    monkeypatch.setattr(transcriere.shutil, "which", lambda n: None)
    with pytest.raises(transcriere.TranscriptionError, match="ffmpeg"):
        transcriere.to_wav(tmp_path / "x.mp4", tmp_path / "x.wav")


@pytest.mark.parametrize("text,expected", [
    ('ID=ubuntu\nID_LIKE=debian\n', "debian"),
    ('ID=fedora\n', "fedora"),
    ('ID=arch\n', "arch"),
    ('ID=linuxmint\nID_LIKE="ubuntu debian"\n', "debian"),
    ('ID=endeavouros\nID_LIKE=arch\n', "arch"),
    ('ID=gentoo\n', None),
])
def test_distributii(tmp_path, text, expected):
    f = tmp_path / "os-release"
    f.write_text(text)
    assert system.detect_distro(f) == expected


def test_comenzi_din_distro_toml():
    data = system.load_packages(ROOT / "distro.toml")
    assert system.install_command(["ffmpeg", "tesseract"], "fedora", data) == \
        "sudo dnf install ffmpeg-free tesseract tesseract-langpack-ron"
    assert system.install_command(["ocrmypdf"], "arch", data) == "sudo pacman -S --needed ocrmypdf"
    assert system.install_command(["venv"], "debian", data) == "sudo apt install python3-venv"
    assert system.install_command(["venv"], "arch", data) is None
