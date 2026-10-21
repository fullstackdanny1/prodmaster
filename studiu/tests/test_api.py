"""Câte un test de integrare per grup de rute, cu TestClient."""
import json

from conftest import write

from app import jobs, storage

NOTE = "# Bilanț\n\n## Activele\n\nActivele circulante includ stocurile, creanțele și disponibilitățile. " \
       "Ele se transformă în bani în mai puțin de un an și sunt baza lichidității firmei pe termen scurt.\n\n" \
       "Q: Ce includ activele circulante?\nA: Stocuri, creanțe, disponibilități.\n\n" \
       "Q: În cât timp devin bani?\nA: Sub un an.\n"


def test_biblioteca(client, notes):
    write(notes, "Fin/01 Bilanț.md", NOTE)
    tree = client.get("/api/arbore").json()["tree"]
    assert tree["children"][0]["name"] == "Fin"
    n = client.get("/api/notita", params={"path": "Fin/01 Bilanț.md"}).json()
    assert 'id="activele"' in n["html"] and n["meta"]["id"]
    # editorul trimite textul fără id → id-ul e păstrat, iar răspunsul conține textul nou
    r = client.put("/api/notita", json={"path": "Fin/01 Bilanț.md", "content": NOTE + "\nmai mult\n", "mtime": n["mtime"]})
    assert r.status_code == 200 and n["meta"]["id"] in r.json()["raw"]
    assert client.put("/api/notita", json={"path": "Fin/01 Bilanț.md", "content": "x", "mtime": 1.0}).status_code == 409
    assert client.post("/api/folder", json={"parent": "", "name": "Alt"}).status_code == 200
    m = client.post("/api/notita/mutare", json={"path": "Fin/01 Bilanț.md", "destinatie": "Alt/01 Bilanț"})
    assert m.json()["path"] == "Alt/01 Bilanț.md"
    assert client.get("/api/cautare", params={"q": "creante"}).json()["results"][0]["path"] == "Alt/01 Bilanț.md"
    assert client.post("/api/notita/stergere", json={"path": "Alt"}).json()["cos"].startswith(".studiu/cos/")
    assert client.get("/api/notita", params={"path": "../x.md"}).status_code == 404
    assert client.post("/api/randare", json={"content": "---\na: 1\n---\n$x$"}).json()["html"].count("math") == 1


def test_carduri_repetitie_quiz_examen(client, notes, fake_ai):
    write(notes, "Fin/01 Bilanț.md", NOTE)
    client.get("/api/arbore")
    c = client.get("/api/carduri", params={"notita": "Fin/01 Bilanț.md"}).json()
    assert c["utilizabila"] and len(c["carduri"]) == 2
    est = client.post("/api/carduri/generare", json={"path": "Fin/01 Bilanț.md"}).json()["estimare"]
    assert est["sectiuni"] == 1 and est["gratuit"]
    assert client.post("/api/carduri/generare", json={"path": "Fin/01 Bilanț.md", "model": "nimic"}).status_code == 400
    fake_ai.reply_json({"carduri": [{"tip": "intrebare", "intrebare": "Ce sunt activele circulante?",
                                     "raspuns": "Bunuri care devin bani sub un an."}]})
    job = client.post("/api/carduri/generare", json={"path": "Fin/01 Bilanț.md", "confirmat": True}).json()["sarcina"]
    jobs.wait_idle()
    s = client.get("/api/sarcini").json()
    assert s["terminate"][0]["id"] == job and s["terminate"][0]["stare"] == "gata"
    cards = client.get("/api/carduri", params={"notita": "Fin/01 Bilanț.md"}).json()["carduri"]
    assert len(cards) == 3
    ai_card = next(x for x in cards if x["origine"] == "ai")
    r = client.put(f"/api/carduri/{ai_card['id']}", json={"raspuns": "Bunuri pe termen scurt."})
    assert r.json()["modificat_manual"]
    assert client.post(f"/api/carduri/{ai_card['id']}/stare", json={"stare": "suspendat"}).json()["card"]["stare"] == "suspendat"

    q = client.get("/api/repetitie/azi").json()
    assert q["noi"] == 2 and set(q["carduri"][0]["intervale"]) == {"1", "2", "3", "4"}
    assert client.post("/api/repetitie/raspuns", json={"card": q["carduri"][0]["id"], "nota": 3, "ms": 900}).json()["ok"]
    assert client.post("/api/repetitie/raspuns", json={"card": "nimic", "nota": 3}).status_code == 404
    lines = next(storage.path("repetitii").glob("*.jsonl")).read_text().splitlines()
    assert json.loads(lines[0])["nota"] == 3

    qz = client.post("/api/quiz", json={"scope": "Fin", "numar": 5, "tip": "variante"}).json()["intrebari"]
    assert len(qz) == 2
    assert client.post("/api/quiz/raspuns", json={"card": qz[0]["card"], "corect": False, "mod": "quiz"}).json()["ok"]
    ex = client.post("/api/examen", json={"scope": "Fin", "numar": 5, "minute": 1}).json()
    res = client.post(f"/api/examen/{ex['id']}/final", json={"raspunsuri": [{"card": ex["intrebari"][0]["card"], "ales": 0}]}).json()
    assert res["scor"]["total"] == 2
    assert client.post(f"/api/examen/{ex['id']}/final", json={"raspunsuri": []}).status_code == 400
    assert client.get("/api/examene").json()["examene"][0]["id"] == ex["id"]
    assert client.get(f"/api/examen/{ex['id']}").json()["scor"]["total"] == 2
    st = client.get("/api/statistici").json()
    assert sum(d["raspunsuri"] for d in st["pe_zile"]) == 4


def test_import_web_si_estimare(client, notes, monkeypatch):
    from app import importer
    from test_import import ARTICLE
    monkeypatch.setattr(importer, "fetch", lambda url: ARTICLE)
    e = client.post("/api/import/estimare", json={"url": "https://exemplu.ro/a"}).json()
    assert e["tip"] == "web" and e["cost_usd"] == 0
    j = client.post("/api/import", json={"url": "https://exemplu.ro/a", "folder": ""}).json()["sarcina"]
    jobs.wait_idle()
    job = jobs.get(j)
    assert job["stare"] == "gata"
    assert client.get("/api/notita", params={"path": job["rezultat"]["path"]}).json()["meta"]["sursa"] == "web"
    r = client.post("/api/import/estimare", files={"fisier": ("x.docx", b"abc")})
    assert r.status_code == 400 and "nesuportat" in r.json()["detail"]
    assert client.post("/api/import", json={"url": "https://x.ro", "folder": "nu-exista"}).status_code == 404


def test_chat(client, notes, fake_ai):
    write(notes, "Fin/01 Bilanț.md", NOTE)
    client.get("/api/arbore")
    fake_ai.reply_json({"cuvinte": ["active circulante", "stocuri", "lichiditate"]})
    fake_ai.reply("Activele circulante includ stocurile și creanțele [1].")
    r = client.post("/api/chat", json={"intrebare": "Ce includ activele circulante?", "scope": "", "istoric": []}).json()
    assert r["surse"][0]["notita"] == "Fin/01 Bilanț.md" and r["surse"][0]["sectiune"] == "activele"
    sent = fake_ai.chat_requests[1]["json"]["messages"][-1]["content"]
    assert "[1]" in sent and "Activele circulante includ stocurile" in sent
    # o întrebare fără răspuns în notițe: contextul trimis e gol
    fake_ai.reply_json({"cuvinte": ["fotosinteza", "clorofila"]})
    fake_ai.reply("Nu găsesc în notițe informații despre asta.")
    r2 = client.post("/api/chat", json={"intrebare": "Ce e fotosinteza?"}).json()
    assert r2["surse"] == [] and "niciun fragment" in fake_ai.chat_requests[3]["json"]["messages"][-1]["content"]
    saved = client.post("/api/chat/salvare", json={"intrebare": "Ce includ activele?", "raspuns": r["raspuns"],
                                                   "surse": r["surse"], "folder": "Fin"}).json()["path"]
    text = (notes / saved).read_text()
    assert "sursa: ai" in text and "(<01 Bilanț.md#activele>)" in text
    assert client.get("/api/revizuit").json()["notite"][0]["path"] == saved


def test_stare_si_ai(client, fake_ai):
    s = client.get("/api/stare").json()
    assert s["ai"]["furnizori"]["fals"]["cheie_prezenta"] is True
    assert "ffmpeg" in s["utilitare"]["programe"]
    assert client.post("/api/ai/test", json={}).json()["ok"]
    assert client.get("/api/ai/modele/fals").json()["modele"] == ["model-mare", "model-test"]
    assert client.get("/api/ai/modele").json()["implicit_sarcini"]["carduri"] == "fals:model-test"
    assert client.post("/api/cache/reconstruire", json={}).json()["ok"]


def test_fara_cheie_restul_merge(client, notes):
    write(notes, "a.md", "Q: Unu?\nA: 1\n")
    assert client.get("/api/arbore").status_code == 200
    assert client.get("/api/repetitie/azi").json()["noi"] == 1
    r = client.post("/api/chat", json={"intrebare": "x"})
    assert r.status_code == 502 and "GEMINI_API_KEY" in r.json()["detail"]
