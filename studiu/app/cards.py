"""Cardurile: .studiu/carduri/<id-notita>.json (sursa de adevăr) + tabela cards din cache.

- carduri manuale extrase din notiță (Q:/A: și {{c1::...}}), cost zero;
- carduri generate cu AI pe secțiuni (doar notițe utilizabile);
- carduri orfane când secțiunea sursă se schimbă sau dispare.
"""
import hashlib
import json
import logging
import re
import threading

from . import ai, cache, index, jobs, library, prompts, scheme, sections, storage
from .config import CFG

log = logging.getLogger("studiu.cards")
_lock = threading.RLock()

MIN_SECTION_CHARS = 150
REASON_CHANGED = "secțiunea a fost modificată"
REASON_GONE = "secțiunea a fost ștearsă sau redenumită"
EDITABLE = ("intrebare", "raspuns", "variante", "corect", "explicatie")


class CardError(ValueError):
    pass


# ---------- fișierele JSON ----------

def file_of(note_id: str):
    return storage.path("carduri", f"{note_id}.json")


def load_file(note_id: str) -> dict:
    data = storage.read_json(file_of(note_id))
    if not isinstance(data, dict):
        data = {"versiune": 1, "notita_id": note_id, "notita_cale": None, "carduri": []}
    data.setdefault("carduri", [])
    return data


def save_file(note_id: str, data: dict) -> None:
    data["versiune"] = 1
    data["notita_id"] = note_id
    storage.write_json(file_of(note_id), data)


# ---------- sintaxa manuală ----------

_Q = re.compile(r"^\s*Q:\s*(.+)$")
_A = re.compile(r"^\s*A:\s*(.*)$")
_CLOZE = re.compile(r"\{\{c(\d+)::(.*?)(?:::(.*?))?\}\}", re.S)
_FENCE = re.compile(r"^\s*(```|~~~)")


def manual_id(note_id: str, question: str) -> str:
    h = hashlib.sha256(f"{note_id}\n{sections.normalize(question)}".encode("utf-8")).hexdigest()
    return "m" + h[:7]


def _cloze_question(text: str, n: str) -> str:
    """Păstrează golul cN, iar celelalte goluri devin text normal."""
    return _CLOZE.sub(lambda m: m.group(0) if m.group(1) == n else m.group(2), text)


def cloze_answer(text: str) -> str:
    return _CLOZE.sub(lambda m: m.group(2), text)


def extract_manual(note_id: str, body: str) -> list[dict]:
    cards = []
    for sec in sections.split(body):
        lines = sec.text.split("\n")
        in_code = False
        para: list[str] = []
        i = 0

        def flush():
            text = "\n".join(para).strip()
            para.clear()
            if not text or not _CLOZE.search(text):
                return
            for n in sorted({m.group(1) for m in _CLOZE.finditer(text)}, key=int):
                q = _cloze_question(text, n)
                cards.append(_manual_card(note_id, sec, "completare", q, cloze_answer(text)))

        while i < len(lines):
            line = lines[i]
            if _FENCE.match(line):
                flush()
                in_code = not in_code
                i += 1
                continue
            if in_code:
                i += 1
                continue
            q = _Q.match(line)
            if q and i + 1 < len(lines) and _A.match(lines[i + 1]):
                flush()
                answer = [_A.match(lines[i + 1]).group(1)]
                j = i + 2
                while j < len(lines) and lines[j].strip() and not _Q.match(lines[j]):
                    answer.append(lines[j].strip())
                    j += 1
                text = "\n".join(answer).strip()
                if text:
                    cards.append(_manual_card(note_id, sec, "intrebare", q.group(1).strip(), text))
                i = j
                continue
            if not line.strip():
                flush()
            else:
                para.append(line)
            i += 1
        flush()
    unique = {}
    for c in cards:
        unique.setdefault(c["id"], c)
    return list(unique.values())


def _manual_card(note_id, sec, tip, question, answer) -> dict:
    return {
        "id": manual_id(note_id, question), "tip": tip, "sectiune": sec.anchor, "sectiune_hash": sec.hash,
        "intrebare": question, "raspuns": answer, "origine": "manual", "stare": "activ",
        "creat_la": storage.now_iso(), "modificat_manual": False,
    }


# ---------- sincronizare cu notițele ----------

def sync_notes(changed_paths: list[str]) -> None:
    """Pentru notițele modificate: cardurile manuale și detectarea orfanilor."""
    for rel in changed_paths:
        try:
            p = library.resolve(rel)
        except library.NotFound:
            continue
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        meta, body = library.split_frontmatter(text)
        note_id = meta.get("id") if library.valid_id(meta.get("id")) else None
        usable = library.is_usable(meta)
        manual = []
        if usable and ("Q:" in body or "{{c" in body):
            manual = extract_manual(note_id or "", body)
            if manual and not note_id:
                note_id = library.ensure_id(rel)
                manual = extract_manual(note_id, body)
        if not note_id:
            continue
        if not manual and not file_of(note_id).exists():
            continue
        _reconcile(note_id, rel, body, manual if usable else [])


def _reconcile(note_id: str, rel: str, body: str, manual: list[dict]) -> None:
    secs = sections.split(body)
    hashes = {s.hash for s in secs}
    anchors = {s.anchor: s for s in secs}
    with _lock:
        data = load_file(note_id)
        before = json.dumps(data, sort_keys=True, ensure_ascii=False)
        data["notita_cale"] = rel
        current = {c["id"]: c for c in data["carduri"]}
        manual_ids = {c["id"] for c in manual}
        kept = []
        for c in data["carduri"]:
            if c.get("origine") == "manual":
                if c["id"] not in manual_ids:
                    continue          # întrebarea a dispărut din notiță
                fresh = next(m for m in manual if m["id"] == c["id"])
                c.update({k: fresh[k] for k in ("tip", "sectiune", "sectiune_hash", "intrebare", "raspuns")})
                kept.append(c)
                continue
            if c.get("origine") == "ai" and c.get("sectiune_hash"):
                if c["sectiune_hash"] in hashes:
                    if c.get("stare") == "orfan":
                        c["stare"] = "activ"
                        c.pop("motiv", None)
                elif c.get("stare") in ("activ", "orfan"):
                    c["stare"] = "orfan"
                    c["motiv"] = REASON_CHANGED if c.get("sectiune") in anchors else REASON_GONE
            kept.append(c)
        for m in manual:
            if m["id"] not in current:
                kept.append(m)
        data["carduri"] = kept
        if json.dumps(data, sort_keys=True, ensure_ascii=False) != before:
            save_file(note_id, data)


def sync_cache() -> None:
    """Copiază cardurile din JSON în tabela cards (incremental, după mtime)."""
    d = storage.path("carduri")
    with _lock, cache.connect() as con:
        known = {r["name"]: r for r in con.execute("SELECT name, mtime, size FROM card_files")}
        seen = set()
        for p in sorted(d.glob("*.json")) if d.is_dir() else []:
            st = p.stat()
            seen.add(p.name)
            row = known.get(p.name)
            if row and row["mtime"] == st.st_mtime and row["size"] == st.st_size:
                continue
            data = storage.read_json(p, {}) or {}
            con.execute("DELETE FROM cards WHERE file=?", (p.name,))
            for c in data.get("carduri", []):
                _insert(con, p.name, data, c)
            con.execute("INSERT OR REPLACE INTO card_files(name, mtime, size) VALUES(?,?,?)",
                        (p.name, st.st_mtime, st.st_size))
        for name in set(known) - seen:
            con.execute("DELETE FROM cards WHERE file=?", (name,))
            con.execute("DELETE FROM card_files WHERE name=?", (name,))


def _insert(con, fname: str, data: dict, c: dict) -> None:
    if not c.get("id") or not c.get("intrebare"):
        return
    note_path = data.get("notita_cale") or ""
    con.execute(
        "INSERT OR REPLACE INTO cards(id, file, note_id, note_path, folder, section, section_hash, tip, "
        "question, answer, choices, correct, explanation, origin, state, reason, modified_manual, created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (c["id"], fname, data.get("notita_id"), note_path, note_path.rpartition("/")[0],
         c.get("sectiune"), c.get("sectiune_hash"), c.get("tip", "intrebare"), c.get("intrebare", ""),
         c.get("raspuns", ""), json.dumps(c["variante"], ensure_ascii=False) if c.get("variante") else None,
         c.get("corect"), c.get("explicatie", ""), c.get("origine", "ai"), c.get("stare", "activ"),
         c.get("motiv", ""), int(bool(c.get("modificat_manual"))), c.get("creat_la", "")))


# ---------- interogări ----------

def _row(r) -> dict:
    d = dict(r)
    d["choices"] = json.loads(d["choices"]) if d.get("choices") else None
    path = d.get("path") or d.get("note_path") or ""
    d["path"] = path
    d["folder"] = path.rpartition("/")[0]
    return d


_SELECT = ("SELECT c.*, COALESCE(f.path, c.note_path) AS path, f.title AS note_title FROM cards c "
           "LEFT JOIN files f ON f.note_id = c.note_id ")


def query(scope: str = "", states=("activ",), note_id: str | None = None) -> list[dict]:
    where, args = [], []
    if states:
        where.append(f"c.state IN ({','.join('?' * len(states))})")
        args += list(states)
    if note_id:
        where.append("c.note_id=?")
        args.append(note_id)
    scope = (scope or "").strip("/")
    if scope:
        where.append("(COALESCE(f.path, c.note_path) LIKE ? ESCAPE '\\' OR COALESCE(f.path, c.note_path)=?)")
        args += [cache.like_prefix(scope), scope]
    sql = _SELECT + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY path, c.created_at"
    with cache.connect() as con:
        return [_row(r) for r in con.execute(sql, args)]


def get(card_id: str) -> dict | None:
    with cache.connect() as con:
        r = con.execute(_SELECT + "WHERE c.id=?", (card_id,)).fetchone()
    return _row(r) if r else None


def public(c: dict) -> dict:
    """Forma pentru API (câmpurile în română, ca în fișierul JSON)."""
    return {
        "id": c["id"], "tip": c["tip"], "sectiune": c.get("section"), "intrebare": c["question"],
        "raspuns": c["answer"], "variante": c.get("choices"), "corect": c.get("correct"),
        "explicatie": c.get("explanation") or "", "origine": c["origin"], "stare": c["state"],
        "motiv": c.get("reason") or "", "modificat_manual": bool(c.get("modified_manual")),
        "notita": c.get("path") or "", "notita_titlu": c.get("note_title") or "",
    }


def for_note(rel: str) -> dict:
    p = library.resolve(rel)
    meta, _body = library.split_frontmatter(p.read_text(encoding="utf-8"))
    note_id = meta.get("id") if library.valid_id(meta.get("id")) else None
    cards = query(states=(), note_id=note_id) if note_id else []
    return {"notita_id": note_id, "utilizabila": library.is_usable(meta),
            "carduri": [public(c) for c in cards]}


# ---------- modificări ----------

def _locate(card_id: str):
    c = get(card_id)
    if not c:
        raise library.NotFound("Cardul nu există")
    data = load_file(c["note_id"])
    for card in data["carduri"]:
        if card["id"] == card_id:
            return c["note_id"], data, card
    raise library.NotFound("Cardul nu există")


def edit(card_id: str, fields: dict) -> dict:
    with _lock:
        note_id, data, card = _locate(card_id)
        if card.get("origine") == "manual":
            raise CardError("Cardurile manuale se editează direct în notiță (Q:/A: sau {{c1::...}}).")
        for k in EDITABLE:
            if k in fields and fields[k] is not None:
                card[k] = fields[k]
        if not str(card.get("intrebare", "")).strip() or not str(card.get("raspuns", "")).strip():
            raise CardError("Întrebarea și răspunsul nu pot fi goale.")
        if card.get("variante"):
            card["variante"] = [str(v).strip() for v in card["variante"] if str(v).strip()]
            if len(set(card["variante"])) != len(card["variante"]) or len(card["variante"]) < 2:
                raise CardError("Variantele trebuie să fie cel puțin două și diferite între ele.")
            if not isinstance(card.get("corect"), int) or not 0 <= card["corect"] < len(card["variante"]):
                raise CardError("Indicele variantei corecte e în afara listei.")
        else:
            card.pop("variante", None)
            card.pop("corect", None)
        card["modificat_manual"] = True
        save_file(note_id, data)
    sync_cache()
    return public(get(card_id))


def set_state(card_id: str, action: str) -> dict | None:
    with _lock:
        note_id, data, card = _locate(card_id)
        if action in ("activ", "suspendat"):
            card["stare"] = action
            card.pop("motiv", None)
        elif action == "sters":
            data["carduri"] = [c for c in data["carduri"] if c["id"] != card_id]
            card["sters_la"] = storage.now_iso()
            data.setdefault("sterse", []).append(card)
        elif action == "pastreaza":
            note = index.note_by_id(note_id)
            secs = {s["anchor"]: s for s in index.note_sections(note["path"])} if note else {}
            sec = secs.get(card.get("sectiune"))
            card["sectiune_hash"] = sec["hash"] if sec else None   # fără secțiune: nu mai devine orfan
            if not sec:
                card["sectiune"] = None
            card["stare"] = "activ"
            card.pop("motiv", None)
        else:
            raise CardError("Acțiune necunoscută (activ, suspendat, sters, pastreaza).")
        save_file(note_id, data)
    sync_cache()
    return None if action == "sters" else public(get(card_id))


def orphans() -> list[dict]:
    return [public(c) for c in query(states=("orfan",))]


# ---------- generare cu AI ----------

def _plan(rel: str, only_anchor: str | None = None) -> dict:
    p = library.resolve(rel)
    if not p.is_file():
        raise library.NotFound("Notița nu există")
    meta, body = library.split_frontmatter(p.read_text(encoding="utf-8"))
    if not library.is_usable(meta):
        raise CardError("Notița e generată de AI și nu a fost verificată. Verific-o întâi.")
    title = library.title_of(meta, body, p.name)
    note_id = meta.get("id") if library.valid_id(meta.get("id")) else None
    existing = load_file(note_id)["carduri"] if note_id else []
    have = {c.get("sectiune_hash") for c in existing if c.get("origine") == "ai" and c.get("stare") == "activ"}
    todo = []
    for s in sections.split(body, title):
        if only_anchor is not None and s.anchor != only_anchor:
            continue
        if len(sections.normalize(s.text)) < MIN_SECTION_CHARS:
            continue
        if only_anchor is None and s.hash in have:
            continue
        todo.append(s)
    return {"title": title, "sections": todo, "note_id": note_id}


def estimate(rel: str, model: str | None = None) -> dict:
    plan = _plan(rel)
    template = prompts.load("carduri_din_sectiune")
    tin = sum(ai.estimeaza_tokeni(template + s.text) for s in plan["sections"]) + 300 * len(plan["sections"])
    tout = 90 * CFG.cards_max * len(plan["sections"])
    return _estimate_dict("carduri", tin, tout, model, sectiuni=len(plan["sections"]))


def _estimate_dict(task: str, tin: int, tout: int, model: str | None, **extra) -> dict:
    out = {"tokeni_intrare": tin, "tokeni_iesire": tout, **extra}
    try:
        info = ai.info_model(task, model)
        out["model"] = f"{info['furnizor']}:{info['model']}"
        out["gratuit"] = info["gratuit"] or info["local"]
        cost = ai.estimeaza_cost(task, tin, tout, model)
        out["cost_usd"] = cost
    except ai.AIError as e:
        out["eroare_ai"] = str(e)
    return out


def _clean(raw: dict, choices: int) -> dict | None:
    q = str(raw.get("intrebare", "")).strip()
    a = str(raw.get("raspuns", "")).strip()
    if not q or not a:
        return None
    tip = raw.get("tip") if raw.get("tip") in ("intrebare", "completare") else "intrebare"
    if tip == "completare" and not _CLOZE.search(q):
        tip = "intrebare"
    card = {"tip": tip, "intrebare": q, "raspuns": a}
    variants = [str(v).strip() for v in raw.get("variante") or [] if str(v).strip()]
    corect = raw.get("corect")
    if tip == "intrebare" and variants:
        ok = (len(variants) == choices and len(set(v.casefold() for v in variants)) == choices
              and isinstance(corect, int) and 0 <= corect < choices)
        if ok:
            card["variante"] = variants
            card["corect"] = corect
    if str(raw.get("explicatie", "")).strip():
        card["explicatie"] = str(raw["explicatie"]).strip()
    return card


def _subject_of(rel: str) -> str:
    parts = rel.split("/")
    return library.display_name(parts[0]) if len(parts) > 1 else ""


def generate(rel: str, model: str | None = None, job: jobs.Job | None = None,
             only_anchor: str | None = None) -> dict:
    note_id = library.ensure_id(rel)
    index.sync()
    plan = _plan(rel, only_anchor)
    total = len(plan["sections"])
    made = 0
    for k, s in enumerate(plan["sections"]):
        if job:
            job.progress(k / max(total, 1) * 100, f"Secțiunea {k + 1} din {total}: {s.title}")
        msgs = prompts.render("carduri_din_sectiune", materie=_subject_of(rel), titlu_notita=plan["title"],
                              titlu_sectiune=s.title, text=s.text, min=CFG.cards_min, max=CFG.cards_max,
                              variante=CFG.quiz_choices)
        r = ai.ruleaza("carduri", msgs, model=model, schema=scheme.CARDURI,
                       la_progres=job.message if job else None)
        new = [c for c in (_clean(x, CFG.quiz_choices) for x in r.date.get("carduri", [])) if c]
        new = new[: CFG.cards_max]
        with _lock:
            data = load_file(note_id)
            data["notita_cale"] = rel
            keep, removed = [], []
            for c in data["carduri"]:
                # Doar la regenerarea unei secțiuni se înlocuiesc cardurile ei (nu și cele editate manual).
                replace = (only_anchor is not None and c.get("origine") == "ai"
                           and not c.get("modificat_manual")
                           and (c.get("sectiune_hash") == s.hash or c.get("sectiune") == s.anchor))
                (removed if replace else keep).append(c)
            for c in removed:
                c["sters_la"] = storage.now_iso()
                c["motiv_stergere"] = "regenerat"
            if removed:
                data.setdefault("sterse", []).extend(removed)
            for c in new:
                keep.append({"id": storage.new_id(), **c, "sectiune": s.anchor, "sectiune_hash": s.hash,
                             "origine": "ai", "stare": "activ", "creat_la": storage.now_iso(),
                             "modificat_manual": False})
            data["carduri"] = keep
            save_file(note_id, data)
        made += len(new)
    sync_cache()
    return {"path": rel, "carduri_noi": made, "sectiuni": total}


@jobs.handler("carduri")
def _job(job: jobs.Job) -> dict:
    p = job.params
    return generate(p["path"], p.get("model"), job, p.get("sectiune"))
