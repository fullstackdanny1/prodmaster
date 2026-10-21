"""Quiz, examen și statistici, calculate din carduri și din istoricul răspunsurilor.

Examenele se scriu în .studiu/examene/<id>.json încă de la început (fără stare în
procesul web); un examen fără „terminat” nu apare în istoric.
"""
import random
import re
from collections import defaultdict
from datetime import datetime, timedelta

from . import cards, index, library, reviews, srs, storage
from .config import CFG

_CLOZE = re.compile(r"\{\{c(\d+)::(.*?)(?:::(.*?))?\}\}", re.S)


class QuizError(ValueError):
    pass


def display_question(c: dict) -> str:
    """Pentru carduri completare, golul apare ca [...] (sau [indiciu])."""
    if c["tip"] != "completare":
        return c["question"]
    return _CLOZE.sub(lambda m: f"[{m.group(3)}]" if m.group(3) else "[...]", c["question"])


def correct_answer(c: dict) -> str:
    if c["tip"] == "completare":
        gaps = [m.group(2) for m in _CLOZE.finditer(c["question"])]
        if gaps:
            return " … ".join(gaps)
    return c["answer"]


def _distractors(c: dict, pool: list[dict], n: int, rng: random.Random) -> list[str]:
    """Răspunsurile altor carduri din același folder, apoi din folderele părinte, cu lungimi apropiate."""
    right = correct_answer(c)
    seen = {right.strip().casefold()}
    folder = c["folder"]
    levels = []
    while True:
        levels.append(folder)
        if not folder:
            break
        folder = folder.rpartition("/")[0]
    out: list[str] = []
    for level in levels:
        cands = []
        for o in pool:
            if o["id"] == c["id"] or (o["folder"] != level and not o["folder"].startswith(level + "/") and level):
                continue
            if (o["tip"] == "completare") != (c["tip"] == "completare"):
                continue
            a = correct_answer(o).strip()
            if a and a.casefold() not in seen:
                cands.append(a)
        rng.shuffle(cands)
        cands.sort(key=lambda a: abs(len(a) - len(right)))
        for a in cands:
            if a.casefold() not in seen:
                seen.add(a.casefold())
                out.append(a)
            if len(out) >= n:
                return out
    return out


def build_question(c: dict, pool: list[dict], rng: random.Random, kind: str = "variante") -> dict:
    q = {"card": c["id"], "intrebare": display_question(c), "raspuns": correct_answer(c),
         "explicatie": c.get("explanation") or "", "notita": c["path"], "sectiune": c.get("section") or "",
         "notita_titlu": c.get("note_title") or "", "tip": "scris"}
    if kind == "scris":
        return q
    if c.get("choices") and c["tip"] == "intrebare" and isinstance(c.get("correct"), int):
        options = list(enumerate(c["choices"]))
        rng.shuffle(options)
        q["variante"] = [t for _i, t in options]
        q["corect"] = next(k for k, (i, _t) in enumerate(options) if i == c["correct"])
        q["tip"] = "variante"
        return q
    wrong = _distractors(c, pool, CFG.quiz_choices - 1, rng)
    if len(wrong) < 1:
        return q          # nu sunt destule răspunsuri pentru variante: întrebare scrisă
    options = [q["raspuns"]] + wrong
    rng.shuffle(options)
    q["variante"] = options
    q["corect"] = options.index(q["raspuns"])
    q["tip"] = "variante"
    return q


def make_quiz(scope: str, count: int, kind: str = "variante", seed: str | None = None) -> list[dict]:
    pool = cards.query(scope)
    if not pool:
        raise QuizError("Nu există carduri active în acest folder. Generează sau scrie carduri întâi.")
    rng = random.Random(seed)
    chosen = rng.sample(pool, min(count, len(pool)))
    everyone = cards.query("")
    return [build_question(c, everyone, rng, kind) for c in chosen]


def record_answer(card: str, correct: bool, ms: int | None, mode: str, exam: str | None = None) -> None:
    if mode not in ("quiz", "examen"):
        raise QuizError("Mod necunoscut (quiz sau examen).")
    if not cards.get(card):
        raise library.NotFound("Cardul nu există")
    ev = {"card": card, "corect": bool(correct), "ms": int(ms or 0), "mod": mode}
    if exam:
        ev["examen"] = exam
    reviews.record(ev)


# ---------- examen ----------

def _exam_path(exam_id: str):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}(-\d+)?", exam_id or ""):
        raise library.NotFound("Examenul nu există")
    return storage.path("examene", f"{exam_id}.json")


def start_exam(scope: str, count: int, minutes: int) -> dict:
    questions = make_quiz(scope, count, "variante")
    now = datetime.now().astimezone()
    exam_id = now.strftime("%Y-%m-%dT%H-%M-%S")
    p = storage.path("examene", f"{exam_id}.json")
    i = 2
    while p.exists():
        exam_id = now.strftime("%Y-%m-%dT%H-%M-%S") + f"-{i}"
        p = storage.path("examene", f"{exam_id}.json")
        i += 1
    data = {
        "versiune": 1, "inceput": now.isoformat(timespec="seconds"), "terminat": None,
        "scop": scope, "durata_limita_min": int(minutes),
        "intrebari": [{"card": q["card"], "ales": None, "corect": q.get("corect"),
                       "variante": q.get("variante"), "ms": 0} for q in questions],
        "scor": None,
    }
    storage.write_json(p, data)
    public = [{k: v for k, v in q.items() if k not in ("corect", "raspuns", "explicatie")} for q in questions]
    return {"id": exam_id, "inceput": data["inceput"], "durata_limita_min": int(minutes), "intrebari": public}


def finish_exam(exam_id: str, answers: list[dict]) -> dict:
    p = _exam_path(exam_id)
    data = storage.read_json(p)
    if not data:
        raise library.NotFound("Examenul nu există")
    if data.get("terminat"):
        raise QuizError("Examenul a fost deja trimis.")
    by_card = {a.get("card"): a for a in answers}
    correct_n = 0
    for q in data["intrebari"]:
        a = by_card.get(q["card"], {})
        q["ales"] = a.get("ales") if isinstance(a.get("ales"), int) else None
        q["ms"] = int(a.get("ms") or 0)
        ok = q["ales"] is not None and q["ales"] == q["corect"]
        correct_n += ok
        if cards.get(q["card"]):
            reviews.record({"card": q["card"], "corect": ok, "ms": q["ms"], "mod": "examen", "examen": exam_id})
    data["terminat"] = datetime.now().astimezone().isoformat(timespec="seconds")
    data["scor"] = {"corecte": correct_n, "total": len(data["intrebari"])}
    storage.write_json(p, data)
    return analysis(exam_id, data)


def _topic_of(path: str, scope: str) -> str:
    folder = path.rpartition("/")[0]
    rest = folder[len(scope):].strip("/") if scope and folder.startswith(scope) else folder
    if not rest:
        return library.display_name(path.rpartition("/")[2]) if path else "(fără notiță)"
    return " / ".join(library.display_name(x) for x in rest.split("/"))


def analysis(exam_id: str, data: dict | None = None) -> dict:
    data = data or storage.read_json(_exam_path(exam_id))
    if not data:
        raise library.NotFound("Examenul nu există")
    scope = data.get("scop") or ""
    topics: dict[str, dict] = defaultdict(lambda: {"corecte": 0, "total": 0, "sectiuni": {}})
    mistakes = []
    sec_titles = index.section_titles()
    for q in data["intrebari"]:
        c = cards.get(q["card"])
        path = c["path"] if c else ""
        t = topics[_topic_of(path, scope)]
        ok = q.get("ales") is not None and q["ales"] == q.get("corect")
        t["total"] += 1
        t["corecte"] += ok
        if c and not ok:
            sec = c.get("section") or ""
            t["sectiuni"][f"{path}#{sec}"] = {"notita": path, "sectiune": sec, "titlu": c.get("note_title") or path,
                                              "titlu_sectiune": sec_titles.get((path, sec), "")}
            variants = q.get("variante") or []
            mistakes.append({
                "card": q["card"], "intrebare": display_question(c),
                "ales": variants[q["ales"]] if q.get("ales") is not None and q["ales"] < len(variants) else None,
                "raspuns": variants[q["corect"]] if isinstance(q.get("corect"), int) and q["corect"] < len(variants)
                else correct_answer(c),
                "explicatie": c.get("explanation") or "", "notita": path, "sectiune": sec,
            })
    rows = [{"subtopic": k, "corecte": v["corecte"], "total": v["total"],
             "procent": round(100 * v["corecte"] / v["total"]) if v["total"] else 0,
             "sectiuni": list(v["sectiuni"].values())} for k, v in topics.items()]
    rows.sort(key=lambda r: (r["procent"], -r["total"]))
    return {"id": exam_id, "scop": scope, "inceput": data.get("inceput"), "terminat": data.get("terminat"),
            "scor": data.get("scor"), "pe_subtopicuri": rows, "greseli": mistakes}


def history(scope: str = "") -> list[dict]:
    out = []
    d = storage.path("examene")
    for p in sorted(d.glob("*.json")) if d.is_dir() else []:
        data = storage.read_json(p)
        if not data or not data.get("terminat") or not data.get("scor"):
            continue
        s = (data.get("scop") or "").strip("/")
        if scope and not (s == scope or s.startswith(scope + "/")):
            continue
        sc = data["scor"]
        out.append({"id": p.stem, "inceput": data.get("inceput"), "scop": s, "corecte": sc["corecte"],
                    "total": sc["total"], "procent": round(100 * sc["corecte"] / sc["total"]) if sc["total"] else 0})
    return out


# ---------- statistici ----------

def statistics(scope: str = "", now: datetime | None = None) -> dict:
    now = now or datetime.now().astimezone()
    all_cards = {c["id"]: c for c in cards.query(scope, states=())}
    today = srs.study_day(now)
    days = {today - timedelta(days=i): 0 for i in range(89, -1, -1)}
    per_subject: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    per_topic: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    per_section: dict[tuple, list[int]] = defaultdict(lambda: [0, 0])
    for e in reviews.events():
        c = all_cards.get(e.get("card"))
        if not c:
            continue
        try:
            t = reviews.parse_time(e["t"])
        except (KeyError, ValueError):
            continue
        d = srs.study_day(t)
        if d in days:
            days[d] += 1
        if e.get("mod", "repetitie") == "repetitie":
            ok = (e.get("nota") or 0) >= 2
        else:
            ok = bool(e.get("corect"))
        parts = (c["path"] or "").split("/")
        subject = library.display_name(parts[0]) if len(parts) > 1 else "(fără materie)"
        topic = " / ".join(library.display_name(x) for x in parts[:-1]) or "(fără materie)"
        for bucket in (per_subject[subject], per_topic[topic], per_section[(c["path"], c.get("section") or "")]):
            bucket[0] += ok
            bucket[1] += 1
    rate = lambda v: round(100 * v[0] / v[1]) if v[1] else 0  # noqa: E731
    weak = []
    sec_titles = index.section_titles()
    for (path, sec), v in per_section.items():
        if v[1] >= 5:
            weak.append({"notita": path, "sectiune": sec, "titlu_sectiune": sec_titles.get((path, sec), ""),
                         "corecte": v[0], "total": v[1], "procent": rate(v),
                         "titlu": next((c.get("note_title") for c in all_cards.values() if c["path"] == path), path)})
    weak.sort(key=lambda r: (r["procent"], -r["total"]))
    return {
        "pe_zile": [{"zi": d.isoformat(), "raspunsuri": n} for d, n in days.items()],
        "pe_materii": [{"materie": k, "corecte": v[0], "total": v[1], "procent": rate(v)}
                       for k, v in sorted(per_subject.items())],
        "pe_subtopicuri": [{"subtopic": k, "corecte": v[0], "total": v[1], "procent": rate(v)}
                           for k, v in sorted(per_topic.items())],
        "topicuri_slabe": weak[:10],
        "prognoza": reviews.forecast(7, scope, now),
        "carduri": {"active": sum(1 for c in all_cards.values() if c["state"] == "activ"),
                    "suspendate": sum(1 for c in all_cards.values() if c["state"] == "suspendat"),
                    "orfane": sum(1 for c in all_cards.values() if c["state"] == "orfan")},
    }
