"""Dispecerul de comenzi: `python -m unelte <comanda> [opțiuni]` sau lansatoarele din ~/.local/bin."""
from __future__ import annotations

import argparse
import importlib
import sys

from . import ai
from .comun.config import EroareUtilizare

ai.set_application("unelte", "unelte ai modele {furnizor}")

# Textele argparse în română (--help și mesajele de eroare).
_RO = {
    "usage: ": "utilizare: ",
    "positional arguments": "argumente",
    "options": "opțiuni",
    "optional arguments": "opțiuni",
    "show this help message and exit": "afișează acest ajutor și iese",
    "the following arguments are required: %s": "lipsesc argumentele: %s",
    "%(prog)s: error: %(message)s\n": "%(prog)s: eroare: %(message)s\n",
    "unrecognized arguments: %s": "argumente necunoscute: %s",
    "expected one argument": "aștept o valoare",
    "invalid choice: %(value)r (choose from %(choices)s)": "valoare invalidă: %(value)r (alege dintre %(choices)s)",
    "not allowed with argument %s": "nu se poate folosi împreună cu %s",
    "argument %(argument_name)s: %(message)s": "argumentul %(argument_name)s: %(message)s",
    "invalid %(type)s value: %(value)r": "valoare invalidă pentru %(type)s: %(value)r",
}
argparse._ = lambda text: _RO.get(text, text)

COMMANDS = {
    "backup": ("unelte.backup", "commit și push automat pentru folderele importante"),
    "organizeaza": ("unelte.organizeaza", "mută fișierele descărcate după reguli"),
    "ocr-ecran": ("unelte.ocr_ecran", "text dintr-o zonă a ecranului, direct în clipboard"),
    "converteste": ("unelte.converteste", "Markdown → Word/PDF cu șablonul facultății"),
    "verifica-format": ("unelte.verifica_format", "verifică un document după regulile profilului"),
    "corecteaza": ("unelte.corecteaza", "gramatică și ortografie locale (LanguageTool), stil prin AI"),
    "traduce": ("unelte.traduce", "traducere prin AI cu păstrarea formatării"),
    "rezumat": ("unelte.rezumat", "rezumatul zilnic din sursele RSS"),
    "doctor": ("unelte.doctor", "verifică instalarea și starea fiecărei comenzi"),
    "ai": ("unelte.ai.__main__", "test, modele, sarcini și consum pentru stratul AI"),
}


class HelpFormatter(argparse.RawDescriptionHelpFormatter):
    pass


def parser(prog: str, description: str, epilog: str = "") -> argparse.ArgumentParser:
    """Un ArgumentParser cu textele argparse în română."""
    ap = argparse.ArgumentParser(prog=prog, description=description, epilog=epilog,
                                 formatter_class=HelpFormatter, add_help=False)
    ap.add_argument("-h", "--help", action="help", help="afișează acest ajutor și iese")
    return ap


def usage() -> str:
    lines = ["Unelte – comenzile instalate:", ""]
    width = max(len(k) for k in COMMANDS)
    for name, (_mod, desc) in COMMANDS.items():
        lines.append(f"  {name:<{width}}  {desc}")
    lines += ["", "Fiecare comandă are --help, cu exemple. Verificarea instalării: unelte doctor"]
    return "\n".join(lines)


def run(name: str, argv: list[str]) -> int:
    if name not in COMMANDS:
        print(f"Comandă necunoscută: {name}\n\n{usage()}", file=sys.stderr)
        return 2
    module = importlib.import_module(COMMANDS[name][0])
    try:
        if name == "ai":
            return module.main(argv, prog="unelte ai")
        return int(module.main(argv) or 0)
    except EroareUtilizare as e:
        print(f"Eroare: {e}", file=sys.stderr)
        return 2
    except ai.AIError as e:
        print(f"Eroare AI: {e}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nOprit.", file=sys.stderr)
        return 130


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(usage())
        return 0
    return run(argv[0], argv[1:])
