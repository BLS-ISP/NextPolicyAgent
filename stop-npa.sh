#!/usr/bin/env bash
#
# stop-npa.sh — Stoppt den NPA (Next Policy Agent) Server
#
# Verwendung:
#   ./stop-npa.sh [Optionen]
#
# Optionen:
#   --pid-file FILE   PID-Datei (Standard: npa.pid)
#   --force           Sofortiges Beenden ohne Graceful Shutdown
#   --timeout SECS    Wartezeit für Graceful Shutdown (Standard: 10)
#   --help            Diese Hilfe anzeigen
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ----- INI-Datei laden -----

INI_FILE="npa.ini"

ini_get() {
    local section="$1" key="$2" default="${3:-}"
    local ini_path="${SCRIPT_DIR}/${INI_FILE}"
    [[ -f "$ini_path" ]] || { echo "$default"; return; }
    local in_section=false
    while IFS= read -r line || [[ -n "$line" ]]; do
        line="$(echo "$line" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
        [[ -z "$line" || "$line" == \;* || "$line" == \#* ]] && continue
        if [[ "$line" =~ ^\[(.+)\]$ ]]; then
            [[ "${BASH_REMATCH[1]}" == "$section" ]] && in_section=true || in_section=false
            continue
        fi
        if $in_section && [[ "$line" =~ ^([^=]+)=(.*)$ ]]; then
            local k v
            k="$(echo "${BASH_REMATCH[1]}" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
            v="$(echo "${BASH_REMATCH[2]}" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
            if [[ "$k" == "$key" && -n "$v" ]]; then
                echo "$v"
                return
            fi
        fi
    done < "$ini_path"
    echo "$default"
}

# Defaults
PID_FILE=""
FORCE=false
TIMEOUT=0

# ----- Farben -----
GREEN='\033[0;32m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

status()  { echo -e "${CYAN}[NPA]${NC} $*"; }
ok()      { echo -e "${GREEN}[NPA]${NC} $*"; }
err()     { echo -e "${RED}[NPA]${NC} $*" >&2; }

# ----- Hilfe -----
show_help() {
    sed -n '2,/^$/s/^#\( \{0,1\}\)//p' "$0"
    exit 0
}

# ----- Argumente parsen -----
while [[ $# -gt 0 ]]; do
    case "$1" in
        --ini-file)
            INI_FILE="$2"; shift 2 ;;
        --pid-file)
            PID_FILE="$2"; shift 2 ;;
        --force)
            FORCE=true; shift ;;
        --timeout)
            TIMEOUT="$2"; shift 2 ;;
        --help|-h)
            show_help ;;
        *)
            err "Unbekannte Option: $1"
            show_help ;;
    esac
done

# ----- INI-Defaults anwenden (CLI überschreibt) -----

if [[ -f "${SCRIPT_DIR}/${INI_FILE}" ]]; then
    status "Konfiguration geladen: ${SCRIPT_DIR}/${INI_FILE}"
fi

[[ -z "$PID_FILE" || "$PID_FILE" == "" ]]  && PID_FILE=$(ini_get process pid_file "npa.pid")
[[ "$TIMEOUT" -eq 0 ]]                      && TIMEOUT=$(ini_get process shutdown_timeout "10")

# ----- PID lesen -----

PID_PATH="${SCRIPT_DIR}/${PID_FILE}"

if [[ ! -f "$PID_PATH" ]]; then
    err "PID-Datei nicht gefunden ($PID_PATH). NPA scheint nicht zu laufen."
    exit 1
fi

NPA_PID="$(cat "$PID_PATH" | tr -d '[:space:]')"

if ! [[ "$NPA_PID" =~ ^[0-9]+$ ]]; then
    err "Ungültige PID in $PID_PATH: '$NPA_PID'"
    rm -f "$PID_PATH"
    exit 1
fi

# ----- Prozess prüfen -----

if ! kill -0 "$NPA_PID" 2>/dev/null; then
    status "Prozess $NPA_PID existiert nicht mehr. Räume PID-Datei auf."
    rm -f "$PID_PATH"
    ok "Aufgeräumt."
    exit 0
fi

status "NPA-Prozess gefunden (PID $NPA_PID)"

# ----- Force Kill -----

if [[ "$FORCE" == true ]]; then
    status "Force-Stop angefordert..."
    kill -9 "$NPA_PID" 2>/dev/null || true
    sleep 0.5
    rm -f "$PID_PATH"
    ok "NPA wurde beendet (Force-Kill)."
    exit 0
fi

# ----- Graceful Shutdown -----

status "Sende Shutdown-Signal an NPA (PID $NPA_PID)..."

# SIGTERM an die Prozessgruppe senden (erfasst auch Kindprozesse)
kill -TERM "$NPA_PID" 2>/dev/null || true

# Warten auf Beendigung
status "Warte auf Beendigung (max. ${TIMEOUT}s)..."
WAITED=0
STOPPED=false

while [[ $WAITED -lt $TIMEOUT ]]; do
    sleep 1
    WAITED=$((WAITED + 1))

    if ! kill -0 "$NPA_PID" 2>/dev/null; then
        STOPPED=true
        break
    fi
    printf "."
done
echo ""

if [[ "$STOPPED" == false ]]; then
    status "Graceful Shutdown fehlgeschlagen. Erzwinge Beendigung..."
    # SIGKILL an die Prozessgruppe
    kill -9 "$NPA_PID" 2>/dev/null || true
    # Kindprozesse auch beenden (per Prozessgruppe)
    pkill -9 -P "$NPA_PID" 2>/dev/null || true
    sleep 0.5
fi

# ----- Aufräumen -----

rm -f "$PID_PATH"

# Prüfe ob wirklich gestoppt
if kill -0 "$NPA_PID" 2>/dev/null; then
    err "WARNUNG: Prozess $NPA_PID konnte nicht beendet werden!"
    exit 1
else
    ok "NPA wurde erfolgreich gestoppt."
fi
