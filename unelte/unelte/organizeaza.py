"""organizeaza – mută fișierele descărcate după reguli. Implicit doar arată planul.

Fiecare mutare se scrie în ~/.local/state/unelte/organizeaza.jsonl, sursa pentru --anuleaza.
"""
from __future__ import annotations

import fnmatch
import json
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .cli import parser
from .comun import config, fisiere, jurnal, sistem

log = jurnal.logger("organizeaza")


@dataclass
class Move:
    src: Path
    dest: Path
    rule: str


def history_path() -> Path:
    return config.state_dir() / "organizeaza.jsonl"


def _words_match(words: list[str], text: str) -> bool:
    t = fisiere.fara_diacritice(text)
    return any(fisiere.fara_diacritice(w) in t for w in words)


def _first_page_text(p: Path) -> str:
    """Textul primei pagini a unui PDF, cu pdftotext dacă există (fără dependență Python)."""
    if p.suffix.lower() != ".pdf" or not sistem.exista("pdftotext"):
        return ""
    try:
        r = sistem.ruleaza(["pdftotext", "-l", "1", "-q", str(p), "-"], timeout=30)
        return r.stdout or ""
    except (OSError, subprocess.SubprocessError):
        return ""


def rule_matches(rule: dict, p: Path) -> bool:
    ext = p.suffix.lower().lstrip(".")
    exts = [e.lower().lstrip(".") for e in rule.get("extensii", [])]
    if exts and ext not in exts:
        return False
    words = rule.get("cuvinte") or []
    if words and not _words_match(words, p.name):
        return False
    content = rule.get("cuvinte_continut") or []
    if content and not _words_match(content, _first_page_text(p)):
        return False
    return bool(exts or words or content)


def destination(rule: dict, p: Path) -> Path:
    mt = datetime.fromtimestamp(p.stat().st_mtime)
    pattern = str(rule["destinatie"])
    folder = pattern.format(an=f"{mt:%Y}", luna=f"{mt:%m}", zi=f"{mt:%d}", extensie=p.suffix.lower().lstrip("."))
    return config.cale(folder)


def plan(cfg: dict, only_auto: bool = False, now: float | None = None) -> tuple[list[Move], list[Path], list[Path]]:
    """(mutări, fișiere fără regulă, fișiere prea recente)."""
    o = cfg["organizeaza"]
    now = now or time.time()
    wait = float(o.get("asteapta_minute", 2)) * 60
    ignore = o.get("ignora", [])
    rules = [r for r in o.get("regula", []) if r.get("destinatie")]
    moves, unmatched, recent = [], [], []
    for src_dir in o.get("surse", []):
        d = config.cale(src_dir)
        if not d.is_dir():
            continue
        for p in sorted(d.iterdir()):
            if p.name.startswith(".") or not p.is_file() or p.is_symlink():
                continue
            if any(fnmatch.fnmatch(p.name, pat) for pat in ignore):
                continue
            if now - p.stat().st_mtime < wait:
                recent.append(p)
                continue
            rule = next((r for r in rules if rule_matches(r, p)), None)
            if rule is None:
                unmatched.append(p)
                continue
            if only_auto and not rule.get("automat"):
                continue
            dest_dir = destination(rule, p)
            if dest_dir.resolve() == p.parent.resolve():
                continue
            moves.append(Move(p, dest_dir / p.name, rule.get("nume", "?")))
    return moves, unmatched, recent


def apply(moves: list[Move]) -> list[dict]:
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    done = []
    for m in moves:
        m.dest.parent.mkdir(parents=True, exist_ok=True)
        dest = fisiere.nume_liber(m.dest)
        shutil.move(str(m.src), str(dest))
        rec = {"rulare": run_id, "t": datetime.now().astimezone().isoformat(timespec="seconds"),
               "din": str(m.src), "in": str(dest), "regula": m.rule}
        history_path().parent.mkdir(parents=True, exist_ok=True)
        with history_path().open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        log.info("%s → %s (%s)", m.src, dest, m.rule)
        done.append(rec)
    return done


def history() -> list[dict]:
    out = []
    try:
        for line in history_path().read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError:
        pass
    return out


def undo_last() -> tuple[int, list[str]]:
    recs = [r for r in history() if not r.get("anulat")]
    if not recs:
        return 0, []
    last = recs[-1]["rulare"]
    restored, skipped = 0, []
    for r in reversed([r for r in recs if r["rulare"] == last]):
        src, dest = Path(r["din"]), Path(r["in"])
        if not dest.exists():
            skipped.append(f"{dest} nu mai e la destinație")
            continue
        if src.exists():
            skipped.append(f"{src} există deja (nu suprascriu)")
            continue
        src.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(dest), str(src))
        restored += 1
    with history_path().open("a", encoding="utf-8") as f:
        f.write(json.dumps({"rulare": last, "anulat": True,
                            "t": datetime.now().astimezone().isoformat(timespec="seconds")}) + "\n")
    return restored, skipped


def print_plan(moves, unmatched, recent) -> None:
    if not moves and not unmatched:
        print("Nimic de organizat.")
    for m in moves:
        print(f"{m.src.name}\n    → {m.dest.parent}   [{m.rule}]")
    if unmatched:
        print(f"\nFără regulă ({len(unmatched)}):")
        for p in unmatched:
            print(f"    {p}")
    if recent:
        print(f"\nSărite, modificate prea recent ({len(recent)}): " + ", ".join(p.name for p in recent))


def main(argv=None) -> int:
    ap = parser("organizeaza", "Mută fișierele din folderele de descărcări după reguli. Fără opțiuni doar arată planul.",
                "Exemple:\n  organizeaza              # planul, fără nicio mutare\n  organizeaza --aplica\n"
                "  organizeaza --anuleaza   # readuce fișierele din ultima rulare\n  organizeaza --istoric")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--aplica", action="store_true", help="execută mutările din plan")
    g.add_argument("--automat", action="store_true", help="(timer) aplică doar regulile cu automat = true")
    g.add_argument("--anuleaza", action="store_true", help="mută înapoi fișierele din ultima rulare")
    g.add_argument("--istoric", action="store_true", help="ultimele rulări")
    a = ap.parse_args(argv)
    cfg = config.load()
    if a.istoric:
        runs: dict[str, dict] = {}
        for r in history():
            e = runs.setdefault(r["rulare"], {"n": 0, "t": r.get("t", ""), "anulat": False})
            if r.get("anulat"):
                e["anulat"] = True
            else:
                e["n"] += 1
        if not runs:
            print("Nicio rulare încă.")
        for rid, e in list(runs.items())[-15:]:
            print(f"{rid}  {e['t'][:16].replace('T', ' ')}  {e['n']} fișiere{'  (anulată)' if e['anulat'] else ''}")
        return 0
    if a.anuleaza:
        restored, skipped = undo_last()
        print(f"Readuse: {restored} fișiere.")
        for s in skipped:
            print(f"  sărit: {s}")
        return 1 if skipped else 0
    if not cfg["organizeaza"].get("regula"):
        print(f"Nicio regulă definită. Adaugă [[organizeaza.regula]] în {config.config_file()}.")
        return 0
    moves, unmatched, recent = plan(cfg, only_auto=a.automat)
    if a.aplica or a.automat:
        done = apply(moves)
        if not a.automat or done:
            print(f"Mutate: {len(done)} fișiere." + (" Anulare: organizeaza --anuleaza" if done else ""))
        return 0
    print_plan(moves, unmatched, recent)
    if moves:
        print("\nPentru a muta: organizeaza --aplica")
    return 0
