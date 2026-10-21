import subprocess
from datetime import datetime

from conftest import needs, set_config

from unelte import backup

pytestmark = needs("git")


def sh(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout


def make(tmp_path, name="notite"):
    remote = tmp_path / f"{name}.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    work = tmp_path / name
    work.mkdir()
    sh(work, "init", "-q", "-b", "main")
    sh(work, "remote", "add", "origin", str(remote))
    return work, remote


def cfg_for(env, tmp_path, *repos, max_mb=50, zotero=""):
    text = f"[backup]\nfisier_max_mb = {max_mb}\n"
    for name, path in repos:
        text += f'[[backup.repo]]\nnume = "{name}"\ncale = "{path}"\n'
    set_config(env, text + zotero)


def test_commit_si_push(env, tmp_path):
    work, remote = make(tmp_path)
    (work / "a.md").write_text("# A\n")
    cfg_for(env, tmp_path, ("notite", work))
    assert backup.main([]) == 0
    log = sh(remote, "log", "--format=%s%n%b", "main")
    assert log.startswith("backup automat ") and "a.md" in log
    assert backup.main([]) == 0                         # nimic nou: fără commit gol
    assert sh(remote, "rev-list", "--count", "main").strip() == "1"
    st = backup.load_state()["notite"]
    assert st["remote"]["origin"]["ultimul_succes"]
    assert backup.main(["--stare"]) == 0


def test_fisier_mare_si_secrete_refuzate(env, tmp_path, monkeypatch):
    work, remote = make(tmp_path)
    notes = []
    monkeypatch.setattr(backup.sistem, "notifica", lambda t, m, urgent=False, cfg=None: notes.append((t, urgent)))
    cfg_for(env, tmp_path, ("notite", work), max_mb=0.001)
    (work / "mare.bin").write_bytes(b"x" * 5000)
    assert backup.main([]) == 1
    assert "mare.bin" in backup.load_state()["notite"]["ultima_eroare"]["mesaj"]
    (work / "mare.bin").unlink()
    cfg_for(env, tmp_path, ("notite", work))
    (work / ".env").write_text("GEMINI_API_KEY=abc123456\n")
    assert backup.main([]) == 1 and notes[-1] == ("Backup: erori", True)
    (work / ".env").unlink()
    (work / "config.txt").write_text("SECRET=supersecret\n")
    assert backup.main([]) == 1
    (work / "config.txt").write_text("-----BEGIN OPENSSH PRIVATE KEY-----\nabc\n")
    assert backup.main([]) == 1
    (work / "config.txt").write_text("API_KEY=\n# fără valoare\n")
    assert backup.main([]) == 0
    assert sh(remote, "rev-list", "--count", "main").strip() == "1"


def test_conflict_fara_push_fortat(env, tmp_path, monkeypatch):
    work, remote = make(tmp_path)
    monkeypatch.setattr(backup.sistem, "notifica", lambda *a, **k: None)
    (work / "a.md").write_text("unu\n")
    cfg_for(env, tmp_path, ("notite", work))
    assert backup.main([]) == 0
    other = tmp_path / "alt"
    subprocess.run(["git", "clone", "-q", str(remote), str(other)], check=True)
    (other / "a.md").write_text("doi\n")
    sh(other, "commit", "-qam", "altundeva")
    sh(other, "push", "-q")
    (work / "a.md").write_text("trei\n")
    assert backup.main([]) == 1
    assert "conflict" in backup.load_state()["notite"]["remote"]["origin"]["ultima_eroare"]["mesaj"]
    assert sh(remote, "log", "-1", "--format=%s", "main").strip() == "altundeva"   # nimic suprascris
    assert sh(work, "log", "-1", "--format=%s").startswith("backup automat")       # commit-ul local rămâne
    assert backup.in_progress(work) is None                                        # rebase anulat


def test_repo_care_nu_e_git_si_initializare(env, tmp_path, capsys):
    plain = tmp_path / "simplu"
    plain.mkdir()
    (plain / "x.md").write_text("x")
    cfg_for(env, tmp_path, ("simplu", plain))
    assert backup.main([]) == 1
    assert "--initializeaza simplu" in capsys.readouterr().out
    assert backup.main(["--initializeaza", "simplu"]) == 0
    assert (plain / ".gitignore").exists() and sh(plain, "log", "--format=%s").startswith("backup automat")


def test_zotero_rotatie_si_pornit(env, tmp_path, monkeypatch):
    z = tmp_path / "Zotero"
    z.mkdir()
    (z / "zotero.sqlite").write_bytes(b"db")
    (z / "better-bibtex.sqlite").write_bytes(b"bb")
    dest = tmp_path / "copii"
    conf = {"activ": True, "date": str(z), "destinatie": str(dest), "copii_pastrate": 3}
    monkeypatch.setattr(backup.sistem, "proces_ruleaza", lambda n: False)
    for i in range(5):
        backup.backup_zotero(conf, datetime(2026, 10, 1 + i, 12, 0))
    copies = sorted(p.name for p in dest.iterdir())
    assert copies == ["2026-10-03_1200", "2026-10-04_1200", "2026-10-05_1200"]
    assert (dest / "2026-10-05_1200" / "better-bibtex.sqlite").read_bytes() == b"bb"
    monkeypatch.setattr(backup.sistem, "proces_ruleaza", lambda n: True)
    assert "rulează" in backup.backup_zotero(conf, datetime(2026, 10, 9, 12, 0))
    assert len(list(dest.iterdir())) == 3
