import subprocess

import pytest
from conftest import ROOT

from unelte import ocr_ecran
from unelte.comun import sistem


def test_curatare_text():
    raw = ("Lichiditatea curentă arată\ncapacitatea  firmei de a-și\nachita datoriile.\n"
           "Al doilea rând începe\ncu literă mare? Nu.\n\n- primul punct\n- al doilea\n\n"
           "cuvân-\ntul despărțit.\f")
    out = ocr_ecran.clean(raw)
    assert out.startswith("Lichiditatea curentă arată capacitatea firmei de a-și achita datoriile.\n")
    assert "Al doilea rând începe cu literă mare? Nu." in out
    assert "\n\n- primul punct\n- al doilea\n\n" in out
    assert "cuvântul despărțit." in out and "  " not in out


class Recorder:
    def __init__(self, responses):
        self.calls = []
        self.responses = responses

    def __call__(self, args, **kw):
        self.calls.append((args, kw))
        out = self.responses.get(args[0], ("", 0))
        if callable(out):
            out = out(args)
        return subprocess.CompletedProcess(args, out[1], stdout=out[0], stderr="")


def test_anularea_selectiei_iese_cu_0(env, monkeypatch):
    rec = Recorder({"slurp": ("", 1)})
    monkeypatch.setattr(sistem, "ruleaza", rec)
    monkeypatch.setattr(sistem, "necesita", lambda p: p)
    monkeypatch.setattr(sistem, "mediu_grafic", lambda **k: {"mediu": "sway", "captura": "grim", "clipboard": "wl-copy"})
    assert ocr_ecran.main([]) == 0
    assert [c[0][0] for c in rec.calls] == ["slurp"]
    rec2 = Recorder({"maim": ("", 1)})
    monkeypatch.setattr(sistem, "ruleaza", rec2)
    monkeypatch.setattr(sistem, "mediu_grafic", lambda **k: {"mediu": "X11", "captura": "maim", "clipboard": "xclip"})
    assert ocr_ecran.main([]) == 0


def test_flux_complet_cu_procese_false(env, monkeypatch):
    def grim(args):
        open(args[-1], "wb").write(b"\x89PNG\r\n\x1a\n" + b"\0" * 8 + (500).to_bytes(4, "big") + b"\0" * 8)
        return ("", 0)
    rec = Recorder({"slurp": ("10,10 400x100\n", 0), "grim": grim,
                    "tesseract": ("Text de pe\nslide în română.\n", 0), "wl-copy": ("", 0)})
    monkeypatch.setattr(sistem, "ruleaza", rec)
    monkeypatch.setattr(sistem, "necesita", lambda p: p)
    monkeypatch.setattr(sistem, "notifica", lambda *a, **k: None)
    monkeypatch.setattr(sistem, "mediu_grafic", lambda **k: {"mediu": "sway", "captura": "grim", "clipboard": "wl-copy"})
    assert ocr_ecran.main([]) == 0
    grim_args = next(c[0] for c in rec.calls if c[0][0] == "grim")
    assert grim_args[1:3] == ["-s", "2"]                       # zonă mică: captură mărită
    tess = next(c[0] for c in rec.calls if c[0][0] == "tesseract")
    assert tess[3:5] == ["-l", "ron+eng"]
    clip = next(c for c in rec.calls if c[0][0] == "wl-copy")
    assert clip[1]["input"] == "Text de pe slide în română.\n"


@pytest.mark.parametrize("envvars,expected", [
    ({"XDG_SESSION_TYPE": "wayland", "SWAYSOCK": "/run/sway"}, ("grim", "wl-copy")),
    ({"XDG_SESSION_TYPE": "wayland", "XDG_CURRENT_DESKTOP": "Hyprland"}, ("grim", "wl-copy")),
    ({"XDG_SESSION_TYPE": "wayland", "XDG_CURRENT_DESKTOP": "ubuntu:GNOME"}, ("gnome", "wl-copy")),
    ({"XDG_SESSION_TYPE": "wayland", "XDG_CURRENT_DESKTOP": "KDE"}, ("spectacle", "wl-copy")),
    ({"XDG_SESSION_TYPE": "x11", "DISPLAY": ":0"}, ("maim", "xclip")),
    ({}, (None, None)),
])
def test_alegerea_uneltei_de_captura(envvars, expected):
    g = sistem.mediu_grafic(envvars)
    assert (g["captura"], g["clipboard"]) == expected


def test_captura_fortata_din_config():
    assert sistem.mediu_grafic({"XDG_SESSION_TYPE": "wayland", "SWAYSOCK": "x"}, "gnome")["captura"] == "gnome"


@pytest.mark.parametrize("text,expected", [
    ('NAME="Ubuntu"\nID=ubuntu\nID_LIKE=debian\n', "debian"),
    ('ID=fedora\nVERSION_ID=42\n', "fedora"),
    ('ID=arch\n', "arch"),
    ('ID=linuxmint\nID_LIKE="ubuntu debian"\n', "debian"),
    ('ID=nixos\n', None),
])
def test_distributii(tmp_path, text, expected):
    f = tmp_path / "os-release"
    f.write_text(text)
    assert sistem.detect_distro(f) == expected


def test_comenzi_din_distro_toml():
    data = sistem.packages(ROOT / "distro.toml")
    assert sistem.install_command(["pandoc", "soffice"], "debian", data) == "sudo apt install pandoc libreoffice-writer libreoffice-math"
    assert sistem.install_command(["tesseract"], "fedora", data) == \
        "sudo dnf install tesseract tesseract-langpack-ron tesseract-langpack-eng"
    assert sistem.install_command(["soffice", "java"], "arch", data) == \
        "sudo pacman -S --needed libreoffice-fresh jre-openjdk-headless"
    assert sistem.install_command(["venv"], "fedora", data) is None


def test_necesita_mesaj_cu_comanda(monkeypatch, env):
    monkeypatch.setattr(sistem, "distro", lambda cfg=None: "fedora")
    monkeypatch.setattr(sistem.shutil, "which", lambda p: None)
    with pytest.raises(sistem.config.EroareUtilizare, match="sudo dnf install pandoc"):
        sistem.necesita("pandoc")
