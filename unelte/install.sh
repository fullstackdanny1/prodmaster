#!/usr/bin/env bash
# Instalarea și actualizarea suitei Unelte. Idempotent: rulat de mai multe ori dă același rezultat
# și nu suprascrie niciodată configurația existentă.
#
# Opțiuni:
#   --distro debian|fedora|arch   distribuția (implicit detectată din /etc/os-release)
#   --da                          rulează comanda de instalare a pachetelor fără să mai întrebe
#   --fara-systemd                nu instala unitățile systemd de utilizator
#   --fara-languagetool           nu descărca LanguageTool
#   --servicii                    pornește Stirling-PDF, Excalidraw și ChartDB (Docker sau Podman)
#   --dezinstaleaza               oprește și elimină unitățile systemd și lansatoarele (config și date rămân)
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

DISTRO=""
YES=0
SYSTEMD=1
LANGTOOL=1
SERVICES=0
UNINSTALL=0
while [ $# -gt 0 ]; do
    case "$1" in
        --distro) DISTRO="${2:-}"; shift ;;
        --distro=*) DISTRO="${1#*=}" ;;
        --da) YES=1 ;;
        --fara-systemd) SYSTEMD=0 ;;
        --fara-languagetool) LANGTOOL=0 ;;
        --servicii) SERVICES=1 ;;
        --dezinstaleaza) UNINSTALL=1 ;;
        -h|--help) sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "Opțiune necunoscută: $1 (vezi ./install.sh --help)" >&2; exit 2 ;;
    esac
    shift
done
case "$DISTRO" in ""|debian|fedora|arch) ;; *) echo "--distro trebuie să fie debian, fedora sau arch." >&2; exit 2 ;; esac

BIN="$HOME/.local/bin"
UNITS="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
PY="${PYTHON:-python3}"
VENV="$DIR/.venv"
DISTRO_ARGS=()
[ -n "$DISTRO" ] && DISTRO_ARGS=(--distro "$DISTRO")
have() { command -v "$1" >/dev/null 2>&1; }
have_systemd() { have systemctl && systemctl --user show-environment >/dev/null 2>&1; }

# ---------------------------------------------------------------- dezinstalare
if [ "$UNINSTALL" = 1 ]; then
    if have_systemd; then
        for u in unelte-backup.timer unelte-organizeaza.timer unelte-rezumat.timer unelte-languagetool.service; do
            systemctl --user disable --now "$u" >/dev/null 2>&1 || true
        done
    fi
    rm -f "$UNITS"/unelte-*.service "$UNITS"/unelte-*.timer
    have_systemd && systemctl --user daemon-reload || true
    for c in backup organizeaza ocr-ecran converteste verifica-format corecteaza traduce rezumat unelte cv buget; do
        if [ -f "$BIN/$c" ] && grep -q "Generat de install.sh (Unelte)" "$BIN/$c"; then rm -f "$BIN/$c"; fi
    done
    echo "Unitățile systemd și lansatoarele au fost eliminate. Configurația și datele au rămas."
    exit 0
fi

# ---------------------------------------------------------------- 1. Python
if ! have "$PY"; then
    echo "Lipsește Python 3 (3.11 sau mai nou). Instalează-l din managerul de pachete al distribuției." >&2
    exit 2
fi
if ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
    echo "Unelte are nevoie de Python 3.11 sau mai nou (ai $("$PY" -V 2>&1))." >&2
    exit 2
fi

# ---------------------------------------------------------------- 2. mediul virtual
if [ ! -x "$VENV/bin/python" ]; then
    echo "Creez mediul virtual..."
    if ! "$PY" -m venv "$VENV" >/dev/null 2>&1; then
        rm -rf "$VENV"
        echo "Modulul venv lipsește. Instalează-l cu:" >&2
        PYTHONPATH="$DIR" "$PY" -c "
from unelte.comun import sistem
d = '${DISTRO}' or sistem.detect_distro()
print('  ' + (sistem.install_command(['venv'], d) or 'pachetul python3-venv al distribuției'))" >&2
        exit 2
    fi
fi
REQ_SUM="$(sha256sum requirements.txt | cut -d' ' -f1)"
if [ ! -f "$VENV/.unelte-requirements" ] || [ "$(cat "$VENV/.unelte-requirements")" != "$REQ_SUM" ]; then
    echo "Instalez dependențele Python..."
    "$VENV/bin/pip" install -q --upgrade pip
    "$VENV/bin/pip" install -q -r requirements.txt
    echo "$REQ_SUM" > "$VENV/.unelte-requirements"
fi
VPY="$VENV/bin/python"
run_py() { (cd "$DIR" && "$VPY" -m "$@"); }

# ---------------------------------------------------------------- 3. configurația
run_py unelte.instalare config

# ---------------------------------------------------------------- 4. lansatoarele
run_py unelte.instalare lansatoare "$BIN" --python "$VPY"
case ":$PATH:" in
    *":$BIN:"*) ;;
    *) echo "Atenție: $BIN nu e în PATH. Adaugă în ~/.bashrc (sau ~/.profile): export PATH=\"\$HOME/.local/bin:\$PATH\"" ;;
esac

# ---------------------------------------------------------------- 5. systemd
if [ "$SYSTEMD" = 1 ]; then
    if have_systemd; then
        run_py unelte.instalare unitati "$UNITS" --python "$VPY"
        systemctl --user daemon-reload
        for t in $(run_py unelte.instalare timere); do
            systemctl --user enable --now "$t" >/dev/null 2>&1 || echo "Atenție: nu am putut activa $t"
        done
    else
        echo "systemd de utilizator nu e disponibil; sar peste timer-e (sau folosește --fara-systemd)."
    fi
fi

# ---------------------------------------------------------------- 6. programele de sistem
run_py unelte.instalare pachete "${DISTRO_ARGS[@]}" $([ "$YES" = 1 ] && echo --da) || true

# ---------------------------------------------------------------- 7. LanguageTool
if [ "$LANGTOOL" = 1 ]; then
    if run_py unelte.instalare languagetool $([ "$YES" = 1 ] && echo --da); then
        if [ "$SYSTEMD" = 1 ] && have_systemd && [ -f "$UNITS/unelte-languagetool.service" ]; then
            systemctl --user enable unelte-languagetool.service >/dev/null 2>&1 || true
            systemctl --user restart unelte-languagetool.service >/dev/null 2>&1 \
                || echo "Atenție: serviciul LanguageTool nu a pornit (Java instalat?)."
        fi
    fi
fi

# ---------------------------------------------------------------- servicii (opțional)
if [ "$SERVICES" = 1 ]; then
    mkdir -p "$HOME/.local/share/unelte/stirling/configs" "$HOME/.local/share/unelte/stirling/logs"
    if have docker && docker compose version >/dev/null 2>&1; then
        docker compose -f servicii/compose.yml up -d
    elif have podman; then
        if podman compose version >/dev/null 2>&1; then
            podman compose -f servicii/compose.yml up -d
        elif have podman-compose; then
            podman-compose -f servicii/compose.yml up -d
        else
            echo "Podman e instalat, dar lipsește „podman compose” (pachetul podman-compose)."
        fi
        # containerele rootless pornesc după repornire doar cu podman-restart.service
        have_systemd && systemctl --user enable --now podman-restart.service >/dev/null 2>&1 || true
    else
        echo "Pentru servicii e nevoie de Docker (cu compose) sau de Podman. Continui fără ele."
    fi
fi

# ---------------------------------------------------------------- 8. diagnoza
echo
run_py unelte doctor --fara-retea || true
