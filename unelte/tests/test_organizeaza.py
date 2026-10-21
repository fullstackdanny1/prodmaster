import os
import time

from conftest import set_config

from unelte import organizeaza
from unelte.comun import config


def setup(env, tmp_path):
    src = tmp_path / "Descărcări"
    src.mkdir()
    set_config(env, f"""
[organizeaza]
surse = ["{src}", "{tmp_path / 'nu-exista'}"]
asteapta_minute = 2
[[organizeaza.regula]]
nume = "Cursuri management"
extensii = ["pdf", "docx"]
cuvinte = ["management", "antreprenor"]
destinatie = "{tmp_path}/Facultate/Management/{{an}}"
[[organizeaza.regula]]
nume = "Imagini"
extensii = ["png", "jpg"]
destinatie = "{tmp_path}/Imagini/{{an}}-{{luna}}"
automat = true
""")
    return src


def old(p, text="x"):
    p.write_text(text)
    t = time.time() - 3600
    os.utime(p, (t, t))
    return p


def test_plan_aplica_anuleaza(env, tmp_path):
    src = setup(env, tmp_path)
    old(src / "Curs 3 ANTREPRENORIAT.pdf")
    old(src / "Managementul_proiectelor.docx")
    old(src / "poza.png")
    old(src / "altceva.zip")
    old(src / ".ascuns.pdf")
    (src / "in-curs.pdf").write_text("x")                       # recent
    old(src / "x.pdf.part")
    (src / "folder").mkdir()
    cfg = config.load()
    moves, unmatched, recent = organizeaza.plan(cfg)
    assert {m.src.name: m.rule for m in moves} == {
        "Curs 3 ANTREPRENORIAT.pdf": "Cursuri management", "Managementul_proiectelor.docx": "Cursuri management",
        "poza.png": "Imagini"}
    assert [p.name for p in unmatched] == ["altceva.zip"] and [p.name for p in recent] == ["in-curs.pdf"]
    assert (src / "poza.png").exists()                         # planul nu mută nimic
    year = time.strftime("%Y")
    # fără suprascriere la destinație
    (tmp_path / f"Facultate/Management/{year}").mkdir(parents=True)
    (tmp_path / f"Facultate/Management/{year}/Curs 3 ANTREPRENORIAT.pdf").write_text("vechi")
    planned = {(m.src.name, str(m.dest.parent)) for m in moves}
    assert organizeaza.main(["--aplica"]) == 0
    moved = organizeaza.history()
    assert {(os.path.basename(r["din"]), os.path.dirname(r["in"])) for r in moved} == planned   # plan = realitate
    assert (tmp_path / f"Facultate/Management/{year}/Curs 3 ANTREPRENORIAT (2).pdf").exists()
    assert (tmp_path / f"Facultate/Management/{year}/Curs 3 ANTREPRENORIAT.pdf").read_text() == "vechi"
    assert organizeaza.main(["--anuleaza"]) == 0
    assert sorted(p.name for p in src.iterdir() if p.is_file() and not p.name.startswith(".")) == [
        "Curs 3 ANTREPRENORIAT.pdf", "Managementul_proiectelor.docx", "altceva.zip", "in-curs.pdf", "poza.png",
        "x.pdf.part"]


def test_automat_doar_regulile_automate(env, tmp_path):
    src = setup(env, tmp_path)
    old(src / "management.pdf")
    old(src / "poza.jpg")
    assert organizeaza.main(["--automat"]) == 0
    assert (src / "management.pdf").exists() and not (src / "poza.jpg").exists()


def test_potrivire_fara_diacritice():
    rule = {"extensii": ["pdf"], "cuvinte": ["științe", "ECONOMIE"]}
    from pathlib import Path
    p = Path("/tmp/Stiinte economice.pdf")
    assert organizeaza.rule_matches(rule, p)
    assert organizeaza.rule_matches({"cuvinte": ["economie"]}, Path("/tmp/Economíe.txt"))
    assert not organizeaza.rule_matches(rule, Path("/tmp/Stiinte.docx"))
