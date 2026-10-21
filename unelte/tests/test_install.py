import os
import shutil
import stat
import subprocess
import sys

from conftest import ROOT

from unelte import instalare


def make_repo(tmp_path):
    repo = tmp_path / "unelte"
    shutil.copytree(ROOT, repo, ignore=shutil.ignore_patterns(".venv", "__pycache__", ".pytest_cache", "tests"))
    venv = repo / ".venv" / "bin"
    venv.mkdir(parents=True)
    (venv / "python").write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
    (venv / "pip").write_text("#!/bin/sh\nexit 0\n")                 # fără rețea: dependențele există deja
    for f in ("python", "pip"):
        (venv / f).chmod(0o755)
    return repo


def run_install(repo, home, *args):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("UNELTE_", "AI_", "XDG_"))}
    env.update(HOME=str(home), PATH=f"{home}/.local/bin:{os.environ['PATH']}")
    return subprocess.run(["bash", str(repo / "install.sh"), "--fara-systemd", "--fara-languagetool", *args],
                          cwd=repo, env=env, capture_output=True, text=True, timeout=300)


def test_de_doua_ori_fara_suprascriere(tmp_path):
    repo = make_repo(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    r1 = run_install(repo, home)
    assert r1.returncode == 0, r1.stderr
    cfg = home / ".config/unelte/config.toml"
    env_file = home / ".config/ai/.env"
    assert cfg.exists() and (home / ".config/unelte/dictionar.txt").exists()
    assert (home / ".config/unelte/glosar.toml").exists() and (home / ".config/ai/ai.toml").exists()
    assert stat.S_IMODE(env_file.stat().st_mode) == 0o600
    for c in ("backup", "organizeaza", "ocr-ecran", "converteste", "verifica-format", "corecteaza", "traduce",
              "rezumat", "unelte"):
        p = home / ".local/bin" / c
        assert p.exists() and os.access(p, os.X_OK), c
    assert not (home / ".local/bin/cv").exists()                        # modul amânat, dezactivat
    assert "Comandă" in r1.stdout                                       # doctor la final
    cfg.write_text("# configurația mea\n[general]\nnotificari = false\n")
    env_file.write_text("GEMINI_API_KEY=secret\n")
    r2 = run_install(repo, home)
    assert r2.returncode == 0, r2.stderr
    assert cfg.read_text() == "# configurația mea\n[general]\nnotificari = false\n"
    assert env_file.read_text() == "GEMINI_API_KEY=secret\n"
    out = subprocess.run([str(home / ".local/bin/unelte")], capture_output=True, text=True,
                         env={**os.environ, "HOME": str(home)})
    assert "comenzile instalate" in out.stdout
    r3 = subprocess.run(["bash", str(repo / "install.sh"), "--dezinstaleaza"], cwd=repo, capture_output=True,
                        text=True, env={**os.environ, "HOME": str(home)})
    assert r3.returncode == 0 and not (home / ".local/bin/backup").exists() and cfg.exists()


def test_calendar_timer():
    assert instalare.calendar("1h") == "hourly"
    assert instalare.calendar("30m") == "*:0/30"
    assert instalare.calendar("2h") == "0/2:00"
    assert instalare.calendar("1d") == "daily"


def test_unitati_systemd(env, tmp_path):
    (env / "config.toml").write_text('[backup]\ninterval = "30m"\n[rezumat]\nora = "06:45"\n')
    instalare.units(tmp_path / "units", "/opt/venv/bin/python")
    timer = (tmp_path / "units/unelte-backup.timer").read_text()
    assert "OnCalendar=*:0/30" in timer and "Persistent=true" in timer
    assert "OnCalendar=*-*-* 06:45:00" in (tmp_path / "units/unelte-rezumat.timer").read_text()
    svc = (tmp_path / "units/unelte-backup.service").read_text()
    assert "ExecStart=/opt/venv/bin/python -m unelte backup" in svc and "@" not in svc
    lt = (tmp_path / "units/unelte-languagetool.service").read_text()
    assert "--port 8081" in lt and "--public" not in lt.split("ExecStart")[1]
