"""unelte doctor – starea fiecărei comenzi și a instalării."""
from __future__ import annotations

import socket
import tempfile
import urllib.request
from pathlib import Path

from . import ai, backup
from .cli import parser
from .comun import config, profil, sistem

OK, MISSING, UNCONFIGURED = "gata", "lipsește", "neconfigurat"
COMPOSE_PORTS = {"Stirling-PDF": 8090, "Excalidraw": 8091, "ChartDB": 8092}
AI_TASKS = {"ocr-ecran": "corectura_ocr", "corecteaza": "stil", "traduce": "traducere", "rezumat": "rezumat"}


def port_open(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket() as s:
        s.settimeout(1)
        return s.connect_ex((host, port)) == 0


def lt_ok(server: str) -> bool:
    try:
        with urllib.request.urlopen(server.rstrip("/") + "/v2/languages", timeout=3) as r:
            return r.status == 200
    except OSError:
        return False


def _miss(*progs: str) -> list[str]:
    return [p for p in progs if not sistem.exista(p)]


def command_status(cfg: dict, env: dict, lt_running: bool) -> list[tuple[str, str, str]]:
    rows = []
    m = _miss("git")
    rows.append(("backup", MISSING if m else OK if cfg["backup"].get("repo") else UNCONFIGURED,
                 f"lipsește {', '.join(m)}" if m else f"{len(cfg['backup'].get('repo', []))} repo-uri"
                 if cfg["backup"].get("repo") else "adaugă [[backup.repo]]"))
    rules = cfg["organizeaza"].get("regula", [])
    rows.append(("organizeaza", OK if rules else UNCONFIGURED, f"{len(rules)} reguli" if rules else
                 "adaugă [[organizeaza.regula]]"))
    tool = env["captura"]
    progs = ["tesseract"] + list(sistem.CAPTURE_TOOLS.get(tool, {}).get("programe", [])) + (
        [env["clipboard"]] if env["clipboard"] else [])
    m = _miss(*progs)
    rows.append(("ocr-ecran", MISSING if m or not tool else OK,
                 f"lipsește {', '.join(m)}" if m else (f"captură {tool}, clipboard {env['clipboard']}" if tool
                                                     else "fără mediu grafic; merge --fisier")))
    m = _miss("pandoc")
    pdf = "" if sistem.exista("soffice") else " (fără --pdf: lipsește LibreOffice)"
    rows.append(("converteste", MISSING if m else OK, f"lipsește {', '.join(m)}" if m else "pandoc" + pdf))
    try:
        import docx  # noqa: F401
        prof = profil.incarca(cfg=cfg)
        rows.append(("verifica-format", OK, f"profil «{prof.nume}»"))
    except ImportError:
        rows.append(("verifica-format", MISSING, "lipsește python-docx (rulează ./install.sh)"))
    except config.EroareUtilizare as e:
        rows.append(("verifica-format", UNCONFIGURED, str(e)))
    rows.append(("corecteaza", OK if lt_running else MISSING,
                 "LanguageTool răspunde" if lt_running else "LanguageTool nu răspunde: "
                 "systemctl --user start unelte-languagetool"))
    rows.append(("traduce", OK, "AI (vezi mai jos)"))
    subj = cfg["rezumat"].get("subiect", [])
    rows.append(("rezumat", OK if subj else UNCONFIGURED, f"{len(subj)} subiecte" if subj else
                 "adaugă [[rezumat.subiect]]"))
    return rows


def ai_section(no_network: bool) -> tuple[list[str], bool]:
    lines, ok = [], True
    try:
        info = ai.modele_configurate()
    except Exception as e:  # noqa: BLE001 - un ai.toml stricat nu trebuie să oprească diagnoza
        return [f"  ai.toml: eroare: {e}"], False
    lines.append(f"  configurație: {info['fisier']}" + ("" if Path(info["fisier"]).exists() else " (lipsă: valori implicite)"))
    for e in info["erori"]:
        lines.append(f"  problemă: {e}")
        ok = False
    used: dict[str, str] = {}
    for cmd, task in AI_TASKS.items():
        ref = info["sarcini"].get(task, {}).get("rezolvat") or info["implicit"]["rezolvat"]
        lines.append(f"  {cmd:<12} sarcina {task:<14} → {ref}")
        if not ref.startswith("eroare"):
            used.setdefault(ref.split(":", 1)[0], ref)
    for name, ref in used.items():
        p = info["furnizori"].get(name, {})
        key = "fără cheie" if p.get("cheie_prezenta") is None else (
            f"{p['cheie']} prezentă" if p["cheie_prezenta"] else f"{p['cheie']} LIPSEȘTE în {info['fisier_chei']}")
        if p.get("cheie_prezenta") is False:
            ok = False
        test = ""
        if not no_network and p.get("cheie_prezenta") is not False:
            d = ai.testeaza(ref)
            test = f"; test: {'OK' if d.ok else 'EROARE – ' + d.mesaj}"
            ok = ok and d.ok
        lines.append(f"  furnizor {name}: {key}{test}")
    return lines, ok


def timers() -> list[str]:
    if not sistem.exista("systemctl"):
        return ["  systemctl lipsește"]
    out = []
    for t in ("unelte-backup.timer", "unelte-organizeaza.timer", "unelte-rezumat.timer",
              "unelte-languagetool.service"):
        r = sistem.ruleaza(["systemctl", "--user", "show", t, "-p", "ActiveState", "-p", "LastTriggerUSec",
                            "-p", "LoadState"], timeout=10)
        props = dict(line.split("=", 1) for line in (r.stdout or "").splitlines() if "=" in line)
        if r.returncode != 0 or props.get("LoadState") in (None, "not-found"):
            out.append(f"  {t:<30} neinstalat")
            continue
        last = props.get("LastTriggerUSec", "")
        last = "" if last in ("", "n/a", "0") else f", ultima rulare {last}"
        out.append(f"  {t:<30} {props.get('ActiveState', '?')}{last}")
    return out


def profile_coherence(cfg: dict) -> str:
    """Convertește un document de test cu profilul implicit și îl verifică."""
    if not sistem.exista("pandoc"):
        return "nu pot verifica (lipsește pandoc)"
    from . import converteste
    try:
        prof = profil.incarca(cfg=cfg)
    except config.EroareUtilizare as e:
        return str(e)
    if not prof.reference.is_file():
        return f"lipsește {prof.reference}"
    with tempfile.TemporaryDirectory() as tmp:
        md = Path(tmp) / "test.md"
        fields = "\n".join(f"{f}: Test" for f in prof.reguli["pagina_titlu"].get("campuri", []))
        md.write_text(f"---\n{fields}\n---\n\n# Introducere\n\nUn paragraf de test, suficient de lung pentru "
                      "a verifica fontul, spațierea și alinierea textului.\n\n## Secțiune\n\nAlt paragraf.\n\n"
                      f"# {prof.reguli['citari'].get('titlu_bibliografie', 'Bibliografie')} {{-}}\n\nO intrare.\n",
                      encoding="utf-8")
        try:
            _d, _p, rep = converteste.convert(md, prof, cfg, out=lambda s: None)
        except config.EroareUtilizare as e:
            return f"conversia de test a eșuat: {e}"
    if rep and rep.problems:
        first = next(iter(rep.grouped().values()))[0]
        n = len(rep.problems)
        return f"reference.docx nu corespunde cu profil.toml ({n} {'problemă' if n == 1 else 'probleme'}; de exemplu: {first})"
    return "reference.docx corespunde cu profil.toml"


def main(argv=None) -> int:
    ap = parser("unelte doctor", "Verifică instalarea: comenzile, AI-ul, LanguageTool, timer-ele, serviciile.")
    ap.add_argument("--fara-retea", action="store_true", help="fără apelul de test către furnizorii AI")
    a = ap.parse_args(argv)
    cfg = config.load()
    distro = sistem.distro(cfg)
    env = sistem.mediu_grafic(preferinta=cfg["ocr"].get("captura", "auto"))
    lt_running = lt_ok(cfg["corecteaza"].get("server", "http://127.0.0.1:8081"))
    problems = 0

    print(f"Distribuția: {distro or 'nerecunoscută (setează [general].distro)'}")
    print(f"Mediul grafic: {env['mediu']}; captura pentru ocr-ecran: {env['captura'] or '—'}\n")
    rows = command_status(cfg, env, lt_running)
    w = max(len(r[0]) for r in rows)
    print(f"{'Comandă':<{w}}  {'Stare':<12} Detalii")
    for name, status, detail in rows:
        problems += status == MISSING
        print(f"{name:<{w}}  {status:<12} {detail}")
    missing = sorted({p for p in sistem.packages()["programe"] if p in ("git", "pandoc", "tesseract", "soffice")
                      and not sistem.exista(p)})
    cmd = sistem.install_command(missing, distro) if missing else None
    if cmd:
        print(f"\nInstalare pentru ce lipsește: {cmd}")

    print("\nAI:")
    lines, ai_ok = ai_section(a.fara_retea)
    print("\n".join(lines))
    problems += not ai_ok

    print("\nTimer-e și servicii systemd:")
    print("\n".join(timers()))

    print("\nBackup:")
    state = backup.load_state()
    if not cfg["backup"].get("repo"):
        print("  niciun repo configurat")
    for r in cfg["backup"].get("repo", []):
        last = state.get(r.get("nume", ""), {}).get("ultimul_succes")
        print(f"  {r.get('nume')}: {('ultimul succes ' + last[:16].replace('T', ' ')) if last else 'niciun backup reușit încă'}")

    compose = config.REPO_DIR / "servicii" / "compose.yml"
    if compose.exists() and (sistem.exista("docker") or sistem.exista("podman")):
        print("\nServicii locale:")
        for name, port in COMPOSE_PORTS.items():
            print(f"  {name:<13} 127.0.0.1:{port}  {'răspunde' if port_open(port) else 'oprit (./install.sh --servicii)'}")

    print(f"\nProfilul implicit: {profile_coherence(cfg)}")
    return 1 if problems else 0
