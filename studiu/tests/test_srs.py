from datetime import datetime, timedelta, timezone

from conftest import write

from app import cache, quiz, reviews, srs
from app import config as appcfg
from app.main import refresh

T0 = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)


def ev(card, minutes, rating):
    return srs.ReviewEvent(T0 + timedelta(minutes=minutes), card, rating)


def test_replay_determinist():
    events = [ev("a", 0, 3), ev("b", 1, 1), ev("a", 60 * 24 * 3, 4), ev("b", 5, 3), ev("a", 60 * 24 * 10, 2)]
    s1 = srs.replay(events)
    s2 = srs.replay(list(reversed(events)))
    assert {k: v.to_row() for k, v in s1.items()} == {k: v.to_row() for k, v in s2.items()}
    assert s1["a"].reps == 3


def test_examen_gresit_si_corect():
    base = srs.replay([ev("a", 0, 3), ev("a", 60 * 24 * 4, 3)])
    assert srs.replay([ev("a", 0, 3), ev("a", 60 * 24 * 4, 3), ev("a", 60 * 24 * 5, None)])["a"].due == base["a"].due
    wrong = srs.replay([ev("a", 0, 3), ev("a", 60 * 24 * 4, 3), ev("a", 60 * 24 * 5, 1)])
    assert wrong["a"].due < base["a"].due
    assert wrong["a"].lapses == 1


def test_granita_zilei_la_4():
    local = datetime(2026, 10, 2, 2, 30).astimezone()          # 02:30 aparține zilei precedente
    assert srs.study_day(local) == datetime(2026, 10, 1).date()
    assert srs.study_day(datetime(2026, 10, 2, 4, 1).astimezone()) == datetime(2026, 10, 2).date()


def test_limita_cardurilor_noi_si_cache(notes, monkeypatch):
    lines = "\n\n".join(f"Q: Întrebarea {i}?\nA: R{i}" for i in range(30))
    write(notes, "M/01 a.md", lines + "\n")
    cfg = notes.parent / "config.toml"
    cfg.write_text("[repetitie]\ncarduri_noi_pe_zi = 5\n")
    appcfg.replace(appcfg.load(cfg))
    refresh()
    q = reviews.today_queue()
    assert q["noi"] == 5 and q["scadente"] == 0
    first = q["carduri"][0]["id"]
    reviews.record({"card": first, "nota": 1, "ms": 100, "mod": "repetitie"})
    reviews.record({"card": q["carduri"][1]["id"], "nota": 4, "ms": 100, "mod": "repetitie"})
    q2 = reviews.today_queue()
    assert q2["noi_ramase_azi"] == 3
    assert first in [c["id"] for c in q2["carduri"]]           # „Din nou” revine azi
    before = {k: v.to_row() for k, v in reviews.states().items()}
    cache.reset()                                              # ștergerea cache-ului...
    refresh()
    after = {k: v.to_row() for k, v in reviews.states().items()}
    assert before == after                                     # ...reproduce aceleași scadențe


def test_quiz_examen_statistici(notes):
    write(notes, "Fin/Sub1/01 a.md", "## A\n\n" + "\n\n".join(f"Q: Fin {i}?\nA: Răspuns financiar {i}" for i in range(6)))
    write(notes, "Fin/Sub2/01 b.md", "## B\n\n" + "\n\n".join(f"Q: Alt {i}?\nA: Altceva {i}" for i in range(4)))
    refresh()
    qs = quiz.make_quiz("Fin", 10, seed="x")
    assert len(qs) == 10
    assert all(q["tip"] == "variante" and len(q["variante"]) == 4 for q in qs)
    q0 = qs[0]
    assert q0["variante"][q0["corect"]] == q0["raspuns"]
    ex = quiz.start_exam("Fin", 10, 30)
    assert "corect" not in ex["intrebari"][0]
    from app import storage
    data = storage.read_json(storage.path("examene", f"{ex['id']}.json"))
    answers = []
    for q in data["intrebari"]:
        c = __import__("app.cards", fromlist=["get"]).get(q["card"])
        wrong = "Sub1" in c["path"]
        answers.append({"card": q["card"], "ales": (q["corect"] + 1) % 4 if wrong else q["corect"], "ms": 1000})
    res = quiz.finish_exam(ex["id"], answers)
    assert res["scor"]["total"] == 10 and res["scor"]["corecte"] == 4
    assert res["pe_subtopicuri"][0]["subtopic"] == "Sub1"         # cel mai slab primul
    assert res["pe_subtopicuri"][0]["sectiuni"][0]["sectiune"] == "a"
    assert len(res["greseli"]) == 6
    assert quiz.history("Fin")[0]["procent"] == 40
    st = quiz.statistics()
    assert st["pe_zile"][-1]["raspunsuri"] == 10
    assert st["topicuri_slabe"][0]["procent"] == 0
    assert len(st["prognoza"]) == 7
    # răspunsurile greșite din examen aduc cardul la repetiție
    assert reviews.today_queue()["scadente"] >= 6
