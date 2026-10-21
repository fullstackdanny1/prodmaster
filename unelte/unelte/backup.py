"""backup – commit și push automat cu Git pentru folderele importante, plus copiile Zotero.

Nu face niciodată push forțat; la conflict lasă commit-ul local și trimite o notificare.
"""
from __future__ import annotations

import fnmatch
import json
import re
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from .cli import parser
from .comun import config, fisiere, jurnal, sistem

SECRET_NAMES = (".env", "*.pem", "id_rsa*", "id_ed25519*", "id_ecdsa*", "*.p12", "*.pfx", "*.key")
SECRET_NAME_OK = (".env.example", ".env.sample", ".env.template", "*.pub")
SECRET_CONTENT = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----|\b[A-Z0-9_]*(?:API_KEY|SECRET)\s*=\s*['\"]?[^\s'\"#]{4,}")
GITIGNORE = """# Generat de `backup --initializeaza`
.DS_Store
*.tmp
*.swp
*~
.~lock.*#
~$*
__pycache__/
.venv/
node_modules/
.env
*.pem
id_rsa*
"""

log = jurnal.logger("backup")


def state_path() -> Path:
    return config.state_dir() / "backup-stare.json"


def load_state() -> dict:
    try:
        return json.loads(state_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(state: dict) -> None:
    fisiere.scrie_atomic(state_path(), json.dumps(state, ensure_ascii=False, indent=2) + "\n")


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def git(repo: Path, *args: str, check: bool = False):
    return sistem.ruleaza(["git", "-C", str(repo), *args], check=check)


class RepoSkipped(Exception):
    pass


def is_repo(repo: Path) -> bool:
    r = git(repo, "rev-parse", "--show-toplevel")
    return r.returncode == 0 and Path(r.stdout.strip()).resolve() == repo.resolve()


def in_progress(repo: Path) -> str | None:
    for name, what in (("MERGE_HEAD", "un merge"), ("rebase-merge", "un rebase"), ("rebase-apply", "un rebase"),
                       ("CHERRY_PICK_HEAD", "un cherry-pick")):
        p = git(repo, "rev-parse", "--git-path", name).stdout.strip()
        if p and (repo / p if not Path(p).is_absolute() else Path(p)).exists():
            return what
    return None


def changed_files(repo: Path) -> list[str]:
    r = git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    parts = r.stdout.split("\0")
    out, i = [], 0
    while i < len(parts):
        entry = parts[i]
        i += 1
        if len(entry) < 4:
            continue
        status, path = entry[:2], entry[3:]
        if "R" in status or "C" in status:
            i += 1                      # numele vechi urmează separat
        if "D" in status and not (repo / path).exists():
            continue
        out.append(path)
    return out


def _secret_name(name: str) -> bool:
    if any(fnmatch.fnmatch(name, p) for p in SECRET_NAME_OK):
        return False
    return any(fnmatch.fnmatch(name, p) for p in SECRET_NAMES) or name.startswith(".env.")


def safety_problems(repo: Path, files: list[str], max_mb: float) -> list[str]:
    problems = []
    for rel in files:
        p = repo / rel
        if not p.is_file():
            continue
        size = p.stat().st_size
        if size > max_mb * 1024 * 1024:
            problems.append(f"{rel}: {size / 1048576:.1f} MB (peste limita de {max_mb:g} MB)")
            continue
        if _secret_name(p.name):
            problems.append(f"{rel}: pare un fișier cu secrete (după nume)")
            continue
        if size <= 1024 * 1024:
            try:
                head = p.read_bytes()
            except OSError:
                continue
            if b"\0" in head[:8000]:
                continue
            if SECRET_CONTENT.search(head.decode("utf-8", errors="ignore")):
                problems.append(f"{rel}: conține ceva ce pare o cheie sau un secret")
    return problems


def _identity_args(repo: Path) -> list[str]:
    if git(repo, "config", "user.email").stdout.strip():
        return []
    return ["-c", "user.name=Unelte backup", "-c", "user.email=backup@localhost"]


def commit(repo: Path, files: list[str]) -> bool:
    git(repo, "add", "-A", check=True)
    if git(repo, "diff", "--cached", "--quiet").returncode == 0:
        return False
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    staged = git(repo, "diff", "--cached", "--name-status").stdout.strip().splitlines()
    body = staged[:20] + ([f"… și încă {len(staged) - 20} fișiere"] if len(staged) > 20 else [])
    msg = f"backup automat {stamp}\n\n" + "\n".join(body)
    sistem.ruleaza(["git", "-C", str(repo), *_identity_args(repo), "commit", "-q", "-m", msg], check=True)
    return True


def branch(repo: Path) -> str | None:
    r = git(repo, "symbolic-ref", "--short", "-q", "HEAD")
    return r.stdout.strip() or None


def sync_remote(repo: Path, remote: str, br: str) -> tuple[bool, str]:
    """pull --rebase --autostash, apoi push. Niciodată push forțat."""
    has_remote_branch = git(repo, "ls-remote", "--exit-code", "--heads", remote, br).returncode == 0
    if has_remote_branch:
        r = sistem.ruleaza(["git", "-C", str(repo), *_identity_args(repo), "pull", "--rebase", "--autostash",
                            "-q", remote, br])
        if r.returncode != 0:
            if in_progress(repo):
                git(repo, "rebase", "--abort")
                return False, f"conflict la sincronizarea cu {remote}; commit-ul local a rămas, fără push"
            return False, f"pull de la {remote} a eșuat: {(r.stderr or r.stdout).strip()[-300:]}"
    r = git(repo, "push", "-q", remote, br if has_remote_branch else f"HEAD:refs/heads/{br}")
    if r.returncode != 0:
        return False, f"push spre {remote} a eșuat: {(r.stderr or r.stdout).strip()[-300:]}"
    if not has_remote_branch:
        git(repo, "branch", "-q", f"--set-upstream-to={remote}/{br}")
    return True, "ok"


def backup_repo(name: str, path: Path, max_mb: float, state: dict) -> list[str]:
    """Întoarce lista erorilor (goală = succes)."""
    entry = state.setdefault(name, {"cale": str(path), "remote": {}})
    entry["cale"] = str(path)
    errors: list[str] = []

    def fail(msg):
        errors.append(msg)
        entry["ultima_eroare"] = {"t": _now(), "mesaj": msg}
        log.error("%s: %s", name, msg)

    if not path.is_dir():
        fail(f"folderul {path} nu există")
        return errors
    if not is_repo(path):
        msg = f"{path} nu e repo Git; rulează: backup --initializeaza {name}"
        print(f"  {name}: sărit – {msg}")
        fail(msg)
        return errors
    what = in_progress(path)
    if what:
        fail(f"repo-ul e în mijlocul unui {what.split(' ', 1)[1]}; termină-l manual")
        return errors
    files = changed_files(path)
    problems = safety_problems(path, files, max_mb)
    if problems:
        fail("refuzat din motive de siguranță:\n    " + "\n    ".join(problems))
        print(f"  {name}: sărit – fișiere refuzate:\n    " + "\n    ".join(problems))
        return errors
    try:
        made = commit(path, files)
    except Exception as e:  # noqa: BLE001 - mesajul git ajunge la utilizator
        fail(f"commit eșuat: {getattr(e, 'stderr', '') or e}")
        return errors
    br = branch(path)
    remotes = [r for r in git(path, "remote").stdout.split() if r]
    if not remotes:
        print(f"  {name}: {'commit nou' if made else 'nimic nou'}; nu are remote (git remote add origin …)")
    if remotes and not br:
        fail("HEAD detașat; nu știu ce ramură să trimit")
        return errors
    for remote in remotes:
        ok, msg = sync_remote(path, remote, br)
        rstate = entry["remote"].setdefault(remote, {})
        if ok:
            rstate["ultimul_succes"] = _now()
            print(f"  {name} → {remote}: {'trimis' if made else 'la zi'}")
        else:
            rstate["ultima_eroare"] = {"t": _now(), "mesaj": msg}
            fail(msg)
            print(f"  {name} → {remote}: EROARE – {msg}")
    if not errors:
        entry["ultimul_succes"] = _now()
    return errors


# ---------- Zotero ----------

def backup_zotero(z: dict, now: datetime | None = None) -> str | None:
    """Copie a bazei Zotero dacă aplicația nu rulează. Întoarce mesajul sau None."""
    if not z.get("activ"):
        return None
    src = config.cale(z.get("date", "~/Zotero"))
    db = src / "zotero.sqlite"
    if not db.exists():
        return f"Zotero: nu găsesc {db}"
    if sistem.proces_ruleaza("zotero"):
        log.info("Zotero rulează; copia se face la rularea următoare")
        return "Zotero rulează: copia se face la rularea următoare"
    now = now or datetime.now()
    dest_root = config.cale(z.get("destinatie", "~/Backup/zotero"))
    dest = fisiere.nume_liber(dest_root / now.strftime("%Y-%m-%d_%H%M"))
    dest.mkdir(parents=True)
    for name in ("zotero.sqlite", "better-bibtex.sqlite"):
        if (src / name).exists():
            shutil.copy2(src / name, dest / name)
    keep = max(1, int(z.get("copii_pastrate", 10)))
    copies = sorted(d for d in dest_root.iterdir() if d.is_dir() and re.match(r"\d{4}-\d{2}-\d{2}_\d{4}", d.name))
    for old in copies[:-keep]:
        shutil.rmtree(old)
    return f"Zotero: copie în {dest}"


# ---------- comenzi ----------

def repos(cfg: dict) -> list[dict]:
    return [r for r in cfg["backup"].get("repo", []) if r.get("nume") and r.get("cale")]


def show_state(cfg: dict) -> int:
    state = load_state()
    limit = datetime.now().astimezone() - timedelta(hours=24)
    rows = []
    bad = 0
    for r in repos(cfg):
        e = state.get(r["nume"], {})
        targets = list(e.get("remote", {}).items()) or [("(local)", e)]
        for remote, s in targets:
            last = s.get("ultimul_succes")
            old = not last or datetime.fromisoformat(last) < limit
            bad += old
            err = (s.get("ultima_eroare") or {}).get("mesaj", "")
            rows.append((r["nume"], remote, last[:16].replace("T", " ") if last else "niciodată",
                         "  ← peste 24 h" if old else "", err.splitlines()[0][:60] if err and old else ""))
    if not rows:
        print("Niciun repo configurat în [backup] (vezi [[backup.repo]] în config.toml).")
        return 0
    w0 = max(len(x[0]) for x in rows)
    w1 = max(len(x[1]) for x in rows)
    print(f"{'Repo':<{w0}}  {'Remote':<{w1}}  Ultimul backup reușit")
    for a, b, c, d, e in rows:
        print(f"{a:<{w0}}  {b:<{w1}}  {c}{d}" + (f"  ({e})" if e else ""))
    return 1 if bad else 0


def initialize(cfg: dict, name: str) -> int:
    match = [r for r in repos(cfg) if r["nume"] == name]
    if not match:
        raise config.EroareUtilizare(f"Nu există [[backup.repo]] cu nume = \"{name}\" în {config.config_file()}.")
    path = config.cale(match[0]["cale"])
    sistem.necesita("git")
    path.mkdir(parents=True, exist_ok=True)
    if is_repo(path):
        print(f"{path} e deja un repo Git.")
        return 0
    git(path, "init", "-q", "-b", "main", check=True)
    gi = path / ".gitignore"
    if not gi.exists():
        fisiere.scrie_atomic(gi, GITIGNORE)
    problems = safety_problems(path, changed_files(path), float(cfg["backup"].get("fisier_max_mb", 50)))
    if problems:
        print("Repo-ul a fost creat, dar primul commit nu s-a făcut. Fișiere refuzate:\n  " + "\n  ".join(problems))
        return 1
    commit(path, [])
    print(f"Repo creat în {path}, cu primul commit.")
    print("Adaugă destinația (o singură dată), de exemplu:")
    print(f"  git -C {path} remote add origin git@github.com:<utilizator>/{name}.git")
    print("Apoi backup-ul o folosește automat. Mai târziu, pentru serverul privat:")
    print(f"  git -C {path} remote add privat <adresa-serverului>")
    return 0


def run_backup(cfg: dict, only: str | None = None) -> int:
    sistem.necesita("git")
    max_mb = float(cfg["backup"].get("fisier_max_mb", 50))
    state = load_state()
    selected = [r for r in repos(cfg) if not only or r["nume"] == only]
    if only and not selected:
        raise config.EroareUtilizare(f"Nu există [[backup.repo]] cu nume = \"{only}\".")
    if not selected and not cfg["backup"]["zotero"].get("activ"):
        print("Niciun repo configurat. Adaugă [[backup.repo]] în " + str(config.config_file()))
        return 0
    all_errors = []
    for r in selected:
        all_errors += [f"{r['nume']}: {e}" for e in backup_repo(r["nume"], config.cale(r["cale"]), max_mb, state)]
    save_state(state)
    if not only:
        msg = backup_zotero(cfg["backup"].get("zotero", {}))
        if msg:
            print(f"  {msg}")
    if all_errors:
        sistem.notifica("Backup: erori", "\n".join(e.splitlines()[0] for e in all_errors), urgent=True, cfg=cfg)
        return 1
    return 0


def main(argv=None) -> int:
    ap = parser("backup", "Pune folderele importante sub Git și le trimite la toate remote-urile lor.",
                "Exemple:\n  backup                     # toate repo-urile din config\n"
                "  backup --doar notite\n  backup --stare\n  backup --initializeaza notite")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--stare", action="store_true", help="ultimul backup reușit pentru fiecare repo și remote")
    g.add_argument("--initializeaza", metavar="NUME", help="git init, .gitignore și primul commit")
    g.add_argument("--doar", metavar="NUME", help="un singur repo")
    a = ap.parse_args(argv)
    cfg = config.load()
    if a.stare:
        return show_state(cfg)
    if a.initializeaza:
        return initialize(cfg, a.initializeaza)
    return run_backup(cfg, a.doar)
