"""Comenzile de test ale stratului AI:
    python -m <pachet>.ai test [model]
    python -m <pachet>.ai modele <furnizor>
    python -m <pachet>.ai sarcini
    python -m <pachet>.ai consum [AAAA-LL]
"""
from __future__ import annotations

import argparse
import sys

from . import client


def cmd_test(model: str | None) -> int:
    d = client.testeaza(model)
    label = f"{d.furnizor}:{d.model}" if d.furnizor else (model or "implicit")
    print(f"{'OK' if d.ok else 'EROARE'}  {label}  ({d.durata_s} s)")
    print(f"  {d.mesaj}")
    for n in d.note:
        print(f"  Notă: {n}")
    return 0 if d.ok else 2


def cmd_models(provider: str) -> int:
    try:
        names = client.listeaza_modele(provider)
    except client.AIError as e:
        print(f"Eroare: {e}", file=sys.stderr)
        return 2
    cfg = client.modele_configurate()
    used = {v["rezolvat"] for v in cfg["sarcini"].values()} | {cfg["implicit"]["rezolvat"]}
    for n in names:
        mark = "  ← folosit" if f"{provider}:{n}" in used else ""
        print(f"{n}{mark}")
    missing = sorted(u.split(":", 1)[1] for u in used if u.startswith(provider + ":")
                     and u.split(":", 1)[1] not in names)
    for m in missing:
        print(f"Atenție: modelul configurat «{m}» nu apare în listă.", file=sys.stderr)
    return 0


def cmd_tasks() -> int:
    cfg = client.modele_configurate()
    print(f"Configurație: {cfg['fisier']}")
    print(f"Chei:         {cfg['fisier_chei']}\n")
    rows = [("(implicit)", cfg["implicit"]["ref"], cfg["implicit"]["rezolvat"])]
    rows += [(k, v["ref"], v["rezolvat"]) for k, v in sorted(cfg["sarcini"].items())]
    w1 = max(len(r[0]) for r in rows)
    w2 = max(len(r[1]) for r in rows)
    print(f"{'Sarcină':<{w1}}  {'Setare':<{w2}}  Model")
    for a, b, c in rows:
        print(f"{a:<{w1}}  {b:<{w2}}  {c}")
    print("\nFurnizori:")
    for name, p in cfg["furnizori"].items():
        key = "fără cheie" if p["cheie_prezenta"] is None else (
            f"{p['cheie']} prezentă" if p["cheie_prezenta"] else f"{p['cheie']} LIPSEȘTE")
        extra = ", local" if p["local"] else ""
        extra += ", gratuit" if p["gratuit"] else ""
        print(f"  {name:<12} {p['tip']:<10} {key}{extra}")
    if cfg["erori"]:
        print("\nProbleme în configurație:")
        for e in cfg["erori"]:
            print(f"  - {e}")
        return 2
    return 0


def cmd_usage(month: str | None) -> int:
    s = client.rezumat_consum(month)
    budget = s["buget_lunar_usd"]
    print(f"Consum {s['luna']}: {s['apeluri']} apeluri, {s['intrare']} tokeni intrare, "
          f"{s['iesire']} tokeni ieșire, {s['cost_usd']:.4f} USD"
          + (f" ({s['cost_usd'] / budget * 100:.0f}% din bugetul de {budget:g} USD)" if budget else ""))
    for group, title in (("aplicatii", "Pe aplicații"), ("sarcini", "Pe sarcini"), ("modele", "Pe modele")):
        if s[group]:
            print(f"\n{title}:")
            for k, v in sorted(s[group].items()):
                print(f"  {k:<36} {v['apeluri']:>5} apeluri  {v['intrare'] + v['iesire']:>9} tokeni  "
                      f"{v['cost_usd']:.4f} USD")
    return 0


def main(argv: list[str] | None = None, prog: str | None = None) -> int:
    ap = argparse.ArgumentParser(prog=prog, description="Testează și inspectează configurația AI comună.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("test", help="un apel minim către modelul ales (implicit: modelul implicit)")
    t.add_argument("model", nargs="?")
    m = sub.add_parser("modele", help="modelele raportate de un furnizor")
    m.add_argument("furnizor")
    sub.add_parser("sarcini", help="tabelul sarcină → model rezolvat")
    c = sub.add_parser("consum", help="consumul unei luni, pe aplicații, sarcini și modele")
    c.add_argument("luna", nargs="?", help="AAAA-LL (implicit luna curentă)")
    a = ap.parse_args(argv)
    if a.cmd == "test":
        return cmd_test(a.model)
    if a.cmd == "modele":
        return cmd_models(a.furnizor)
    if a.cmd == "sarcini":
        return cmd_tasks()
    return cmd_usage(a.luna)


if __name__ == "__main__":
    sys.exit(main())
