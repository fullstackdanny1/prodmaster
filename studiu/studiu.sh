#!/usr/bin/env bash
# Lansatorul aplicației Studiu.
# Prima rulare: creează mediul virtual, instalează dependențele, config.toml și configurația AI comună.
#
# Opțiuni:
#   --fara-browser             nu deschide browserul automat
#   --instaleaza-transcriere   instalează transcrierea locală (faster-whisper)
#   --instaleaza-serviciu      pornire automată cu systemd (serviciu de utilizator)
#   --instaleaza-sistem        instalează utilitarele opționale (ffmpeg, ocrmypdf, tesseract)
#                              [--distro debian|fedora|arch] [--da]
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

PY="${PYTHON:-python3}"
AI_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/ai"

need_python() {
    if ! command -v "$PY" >/dev/null 2>&1; then
        echo "Lipsește Python 3. Instalează python3 (3.11 sau mai nou) din managerul de pachete al distribuției." >&2
        exit 2
    fi
    if ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
        echo "Studiu are nevoie de Python 3.11 sau mai nou (ai $("$PY" -V 2>&1))." >&2
        exit 2
    fi
}

ensure_venv() {
    if [ ! -x .venv/bin/python ]; then
        echo "Creez mediul virtual..."
        if ! "$PY" -m venv .venv 2>/dev/null; then
            rm -rf .venv
            echo "Modulul venv lipsește. Pe Ubuntu/Debian se instalează separat:" >&2
            "$PY" -m app.system --venv "$@" >&2 || echo "  sudo apt install python3-venv" >&2
            exit 2
        fi
    fi
    if [ ! -f .venv/.instalat ] || [ requirements.txt -nt .venv/.instalat ]; then
        echo "Instalez dependențele..."
        .venv/bin/pip install -q --upgrade pip
        .venv/bin/pip install -q -r requirements.txt
        touch .venv/.instalat
    fi
}

ensure_config() {
    [ -f config.toml ] || cp config.example.toml config.toml
    # Configurația AI comună cu Unelte: creată doar dacă lipsește, niciodată suprascrisă.
    mkdir -p "$AI_DIR"
    [ -f "$AI_DIR/ai.toml" ] || cp ai.example.toml "$AI_DIR/ai.toml"
    if [ ! -f "$AI_DIR/.env" ]; then
        (umask 077 && printf '# Cheile AI (NUME=valoare). Exemplu:\n# GEMINI_API_KEY=cheia-din-google-ai-studio\n' > "$AI_DIR/.env")
    fi
    chmod 600 "$AI_DIR/.env"
}

install_service() {
    local unit_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
    mkdir -p "$unit_dir"
    cat > "$unit_dir/studiu.service" <<EOF
[Unit]
Description=Studiu

[Service]
WorkingDirectory=$DIR
ExecStart=$DIR/studiu.sh --fara-browser
Restart=on-failure

[Install]
WantedBy=default.target
EOF
    systemctl --user daemon-reload
    systemctl --user enable --now studiu
    echo "Serviciul a fost instalat: $unit_dir/studiu.service"
    echo "Stare: systemctl --user status studiu · Oprire: systemctl --user disable --now studiu"
}

case "${1:-}" in
    --instaleaza-transcriere)
        need_python; ensure_venv
        echo "Instalez transcrierea locală (poate dura câteva minute)..."
        .venv/bin/pip install -r requirements-transcriere.txt
        echo "Gata. Modelul de transcriere se descarcă la primul import audio/video."
        exit 0 ;;
    --instaleaza-serviciu)
        need_python; ensure_venv; ensure_config
        install_service
        exit 0 ;;
    --instaleaza-sistem)
        need_python
        shift
        exec "$PY" -m app.system --instaleaza "$@" ;;
esac

need_python
ensure_venv
ensure_config
exec .venv/bin/python -m app "$@"
