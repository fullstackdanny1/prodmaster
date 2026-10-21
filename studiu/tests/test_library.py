import pytest
from conftest import write

from app import cache, index, library, render, sections, storage


def test_antet_pastreaza_campurile_necunoscute(notes):
    write(notes, "A/01 x.md", "---\ntitlu: X\nalt_camp: [1, 2]\nsursa: ai\nverificat: false\n---\n\n# X\n")
    library.set_verified("A/01 x.md")
    text = (notes / "A/01 x.md").read_text()
    meta, body = library.split_frontmatter(text)
    assert list(meta) == ["titlu", "alt_camp", "sursa", "verificat"]
    assert meta["alt_camp"] == [1, 2] and meta["verificat"] is True
    assert body.lstrip().startswith("# X")


def test_id_adaugat_o_singura_data(notes):
    write(notes, "n.md", "---\ntitlu: T\n---\ntext\n")
    a = library.ensure_id("n.md")
    b = library.ensure_id("n.md")
    assert a == b and library.valid_id(a)
    meta, _ = library.split_frontmatter((notes / "n.md").read_text())
    assert list(meta)[0] == "id" and meta["titlu"] == "T"


@pytest.mark.parametrize("bad", ["../x.md", "/etc/passwd", "A/../../x", ".studiu/carduri"])
def test_cai_sigure(notes, bad):
    with pytest.raises(library.NotFound):
        library.resolve(bad)


def test_utilizabila():
    assert library.is_usable({})
    assert library.is_usable({"sursa": "web"})
    assert not library.is_usable({"sursa": "ai"})
    assert library.is_usable({"sursa": "ai", "verificat": "da"})
    assert not library.is_usable({"tip": "rezumat"})
    assert not library.is_unverified({"tip": "rezumat", "sursa": "ai", "verificat": False})


def test_creare_mutare_cos(notes):
    (notes / "Mat").mkdir()
    rel = library.create_note("Mat", "01 Curs")
    assert rel == "Mat/01 Curs.md"
    with pytest.raises(ValueError):
        library.create_note("Mat", "01 Curs")
    library.create_folder("", "Alt")
    moved = library.move(rel, "Alt/02 Curs mutat")
    assert moved == "Alt/02 Curs mutat.md" and (notes / moved).exists()
    write(notes, "Alt/x.md", "x")
    with pytest.raises(ValueError):
        library.move("Alt/x.md", "Alt/02 Curs mutat.md")
    with pytest.raises(ValueError):
        library.move("Alt", "Alt/sub")
    where = library.trash("Alt")
    assert not (notes / "Alt").exists()
    assert (notes / where / "x.md").exists() and where.startswith(".studiu/cos/")


def test_conflict_la_salvare(notes):
    p = write(notes, "n.md", "a")
    m = p.stat().st_mtime
    library.save_note("n.md", "b", m, False)
    with pytest.raises(library.Conflict):
        library.save_note("n.md", "c", m - 10, False)
    library.save_note("n.md", "c", m - 10, True)
    assert p.read_text() == "c"


def test_nume_nou_fara_suprascriere(notes):
    write(notes, "M/01 a.md", "x")
    write(notes, "M/02 b.md", "x")
    assert library.new_note_path("M", "Curs").name == "03 Curs.md"
    write(notes, "M/07 Curs.md", "x")
    assert library.new_note_path("M", "07 Curs").name == "07 Curs (2).md"
    assert library.safe_filename('a/b:c?') == "a b c"


def test_index_incremental_si_cautare(notes):
    write(notes, "Fin/01 Lichiditate.md", "# Rate de lichiditate\n\nFuncția financiară a lichidității.\n")
    write(notes, "BD/01 Norm.md", "# Normalizare\n\nForma normală.\n")
    assert len(index.sync()) == 2
    assert index.sync() == []                                   # nimic schimbat
    assert index.search("functia")["results"][0]["path"] == "Fin/01 Lichiditate.md"   # fără diacritice
    r = index.search("lichiditatea")
    assert r["relaxed"] and r["results"]                         # forme apropiate
    assert index.search("normala", "Fin")["results"] == []       # restrânsă la folder
    assert index.search("normala", "BD")["results"]
    write(notes, "BD/01 Norm.md", "# Normalizare\n\nAlt text, mai lung.\n")
    assert index.sync() == ["BD/01 Norm.md"]


def test_cache_poate_fi_sters(notes):
    write(notes, "a.md", "# A\n")
    index.sync()
    cache.reset()
    assert index.sync() == ["a.md"]


def test_sectiuni_si_ancore():
    body = "# T\n\nintro\n\n## Lichiditatea curentă\n\ntext\n\n```\n## nu\n```\n\n## Lichiditatea curentă\n\nalt\n"
    secs = sections.split(body)
    assert [s.anchor for s in secs] == ["", "lichiditatea-curentă", "lichiditatea-curentă-1"]
    html = render.render(body)
    for s in secs[1:]:
        assert f'id="{s.anchor}"' in html
    again = sections.split(body.replace("text\n", "text   \n"))
    assert again[1].hash == secs[1].hash                         # hash stabil la spații
    assert sections.split(body.replace("text", "altceva"))[1].hash != secs[1].hash


def test_randare_mermaid_si_cloze():
    html = render.render("```mermaid\ngraph TD; A-->B<script>\n```\n\n```python\nx<1\n```\n\nA = {{c1::B}}\n")
    assert '<div class="mermaid">graph TD; A--&gt;B&lt;script&gt;' in html
    assert '<pre><code class="language-python">x&lt;1' in html
    assert '<span class="cloze" data-c="1">B</span>' in html


def test_gitignore_surse(notes):
    storage.ensure()
    gi = (notes / ".studiu/.gitignore").read_text()
    assert "surse/*.pdf" in gi
