"""Pornește aplicația: python -m app [--fara-browser]"""
import sys
import threading
import webbrowser

import uvicorn

from .config import CFG


def main():
    url = f"http://{CFG.host}:{CFG.port}"
    print(f"Studiu rulează la {url}")
    print(f"Notițe: {CFG.notes_dir}")
    for w in CFG.warnings:
        print(f"Atenție: {w}")
    print("Oprire: Ctrl+C")
    if "--fara-browser" not in sys.argv:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    uvicorn.run("app.main:app", host=CFG.host, port=CFG.port, log_level="warning")


if __name__ == "__main__":
    main()
