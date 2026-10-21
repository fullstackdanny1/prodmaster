import json

import pytest
from conftest import write

from app import ai, cards, index, library, storage
from app.main import refresh

NOTE = """---
titlu: Lichiditate
---

# Rate de lichiditate

## Lichiditatea curentă

Lichiditatea curentă arată capacitatea firmei de a-și acoperi datoriile curente din activele circulante.
Se calculează ca raport între activele circulante și datoriile curente; o valoare în jur de 2 e confortabilă.

## Lichiditatea rapidă

Lichiditatea rapidă (testul acid) exclude stocurile, care se transformă mai greu în numerar, din activele
circulante. O valoare în jur de 1 e considerată acceptabilă pentru majoritatea firmelor din comerț.
"""

AI_CARDS = {"carduri": [
    {"tip": "intrebare", "intrebare": "Ce măsoară lichiditatea curentă?", "raspuns": "Acoperirea datoriilor curente.",
     "variante": ["Acoperirea datoriilor curente.", "Rentabilitatea.", "Îndatorarea.", "Rotația stocurilor."],
     "corect": 0, "explicatie": "Active circulante / datorii curente."},
    {"tip": "intrebare", "intrebare": "Ce valoare e confortabilă?", "raspuns": "În jur de 2.",
     "variante": ["În jur de 2.", "În jur de 2."], "corect": 0},
]}


def test_carduri_manuale(notes):
    body = """## S1

Q: Ce e lichiditatea?
A: Capacitatea de plată
pe termen scurt.

Q: Fără răspuns
text

Lichiditatea curentă = {{c1::Active circulante}} / {{c2::Datorii curente}}

```
Q: în cod
A: ignorat
```
"""
    got = cards.extract_manual("k7m2q9xa", body)
    qa = [c for c in got if c["tip"] == "intrebare"]
    cz = [c for c in got if c["tip"] == "completare"]
    assert len(qa) == 1 and qa[0]["raspuns"] == "Capacitatea de plată\npe termen scurt."
    assert len(cz) == 2
    assert "{{c1::Active circulante}}" in cz[0]["intrebare"] and "Datorii curente" in cz[0]["intrebare"]
    assert "{{c2::" not in cz[0]["intrebare"]
    assert cz[1]["raspuns"] == "Lichiditatea curentă = Active circulante / Datorii curente"
    # id determinist: aceeași notiță + aceeași întrebare = același id
    again = cards.extract_manual("k7m2q9xa", "## Alt titlu\n\nQ: Ce e lichiditatea?\nA: altceva\n")
    assert again[0]["id"] == qa[0]["id"]
    assert cards.extract_manual("altnotit", body)[0]["id"] != qa[0]["id"]


def test_sincronizare_carduri_manuale(notes):
    write(notes, "M/01 a.md", "# A\n\nQ: Doi plus doi?\nA: Patru\n")
    write(notes, "M/02 ai.md", "---\nsursa: ai\nverificat: false\n---\n\nQ: Nu se extrage?\nA: Nu\n")
    refresh()
    meta, _ = library.split_frontmatter((notes / "M/01 a.md").read_text())
    assert library.valid_id(meta["id"])                       # id adăugat pentru cardurile manuale
    got = cards.query("M")
    assert [c["question"] for c in got] == ["Doi plus doi?"]
    write(notes, "M/01 a.md", (notes / "M/01 a.md").read_text().replace("Patru", "4"))
    refresh()
    assert cards.query("M")[0]["answer"] == "4"
    write(notes, "M/01 a.md", (notes / "M/01 a.md").read_text().replace("Q: Doi plus doi?\nA: 4\n", ""))
    refresh()
    assert cards.query("M") == []


def test_generare_ai_si_orfani(notes, fake_ai):
    write(notes, "Fin/01 Lichiditate.md", NOTE)
    refresh()
    fake_ai.reply_json(AI_CARDS).reply_json(AI_CARDS)
    r = cards.generate("Fin/01 Lichiditate.md")
    assert r["sectiuni"] == 2 and r["carduri_noi"] == 4
    got = cards.query("Fin")
    assert len(got) == 4
    by_q = {c["question"]: c for c in got}
    assert by_q["Ce măsoară lichiditatea curentă?"]["choices"][0] == "Acoperirea datoriilor curente."
    assert by_q["Ce valoare e confortabilă?"]["choices"] is None     # variante invalide: eliminate
    # a doua generare nu reface secțiunile neschimbate
    before = len(fake_ai.chat_requests)
    assert cards.generate("Fin/01 Lichiditate.md")["sectiuni"] == 0
    assert len(fake_ai.chat_requests) == before

    # editarea manuală a unui card
    first = [c for c in got if c["section"] == "lichiditatea-curentă"][0]
    cards.edit(first["id"], {"raspuns": "Plata datoriilor curente."})

    # modificarea unei secțiuni → doar cardurile ei devin orfane
    p = notes / "Fin/01 Lichiditate.md"
    p.write_text(p.read_text().replace("o valoare în jur de 2", "o valoare în jur de 1,5"))
    refresh()
    orphans = cards.orphans()
    assert {o["sectiune"] for o in orphans} == {"lichiditatea-curentă"}
    assert all(o["motiv"] == cards.REASON_CHANGED for o in orphans)
    assert all(c["section"] == "lichiditatea-rapidă" for c in cards.query("Fin"))

    # regenerarea secțiunii nu înlocuiește cardul editat manual
    fake_ai.reply_json(AI_CARDS)
    cards.generate("Fin/01 Lichiditate.md", only_anchor="lichiditatea-curentă")
    data = cards.load_file(first["note_id"])
    ids = {c["id"]: c for c in data["carduri"]}
    assert first["id"] in ids and ids[first["id"]]["stare"] == "orfan"
    assert ids[first["id"]]["raspuns"] == "Plata datoriilor curente."
    new_curent = [c for c in data["carduri"] if c["sectiune"] == "lichiditatea-curentă" and c["stare"] == "activ"]
    assert len(new_curent) == 2
    assert any(c.get("motiv_stergere") == "regenerat" for c in data["sterse"])

    # „Păstrează” actualizează hash-ul; ștergerea mută cardul în „sterse”
    cards.set_state(first["id"], "pastreaza")
    assert cards.get(first["id"])["state"] == "activ"
    cards.set_state(first["id"], "sters")
    assert cards.get(first["id"]) is None
    # secțiune ștearsă / redenumită
    p.write_text(p.read_text().replace("## Lichiditatea rapidă", "## Testul acid"))
    refresh()
    assert {o["motiv"] for o in cards.orphans()} >= {cards.REASON_GONE}


def test_reincercare_la_json_invalid(notes, fake_ai):
    write(notes, "Fin/01 L.md", NOTE)
    refresh()
    fake_ai.reply("nu e json").reply_json(AI_CARDS).reply_json(AI_CARDS)
    assert cards.generate("Fin/01 L.md")["carduri_noi"] == 4


def test_notita_nerevizuita_refuzata(notes):
    write(notes, "x.md", "---\nsursa: ai\nverificat: false\n---\n" + NOTE.split("---\n", 2)[2])
    refresh()
    with pytest.raises(cards.CardError, match="nu a fost verificată"):
        cards.estimate("x.md")


def test_cardurile_manuale_nu_se_editeaza_din_panou(notes):
    write(notes, "a.md", "Q: Unu?\nA: 1\n")
    refresh()
    c = cards.query("")[0]
    with pytest.raises(cards.CardError):
        cards.edit(c["id"], {"raspuns": "x"})
    cards.set_state(c["id"], "suspendat")
    assert cards.query("") == []
    refresh()                                     # sincronizarea păstrează starea
    assert cards.query("", states=("suspendat",))


def test_format_fisier(notes, fake_ai):
    write(notes, "Fin/01 L.md", NOTE)
    refresh()
    fake_ai.reply_json(AI_CARDS).reply_json(AI_CARDS)
    cards.generate("Fin/01 L.md")
    nid = index.note_by_id(library.split_frontmatter((notes / "Fin/01 L.md").read_text())[0]["id"])
    assert nid["path"] == "Fin/01 L.md"
    f = next(storage.path("carduri").glob("*.json"))
    data = json.loads(f.read_text())
    assert data["versiune"] == 1 and data["notita_cale"] == "Fin/01 L.md"
    c = data["carduri"][0]
    assert {"id", "tip", "sectiune", "sectiune_hash", "intrebare", "raspuns", "origine", "stare", "creat_la",
            "modificat_manual"} <= set(c)
    assert ai.estimeaza_tokeni("abcdefg") == 2
