#!/usr/bin/env bash
#
# start-npa.sh — Startet den NPA (Next Policy Agent) Server
#
# Verwendung:
#   ./start-npa.sh [Optionen]
#
# Optionen:
#   --addr ADDR          Adresse und Port (Standard: 0.0.0.0:8443)
#   --config-file FILE   Konfigurationsdatei (YAML/JSON)
#   --no-tls             TLS deaktivieren
#   --bundle PATH        Bundle-Pfad (mehrfach verwendbar)
#   --log-level LEVEL    Log-Level (debug, info, warning, error)
#   --tls-cert FILE      TLS-Zertifikat
#   --tls-key FILE       TLS-Schlüssel
#   --pid-file FILE      PID-Datei (Standard: npa.pid)
#   --log-file FILE      Log-Datei (Standard: npa.log)
#   --foreground          Im Vordergrund starten (blockiert)
#   --help               Diese Hilfe anzeigen
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ----- INI-Datei laden -----

INI_FILE="npa.ini"

# Liest einen Wert aus einer INI-Datei: ini_get <section> <key> [default]
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

# Defaults (aus INI oder fest)
ADDR=""
CONFIG_FILE=""
NO_TLS=false
BUNDLES=()
LOG_LEVEL=""
TLS_CERT=""
TLS_KEY=""
PID_FILE=""
LOG_FILE=""
FOREGROUND=false

# ----- Farben -----
GREEN='\033[0;32m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

status()  { echo -e "${CYAN}[NPA]${NC} $*"; }
ok()      { echo -e "${GREEN}[NPA]${NC} $*"; }
err()     { echo -e "${RED}[NPA]${NC} $*" >&2; }

# ----- Argumente parsen -----
while [[ $# -gt 0 ]]; do
    case "$1" in
        --ini-file)       INI_FILE="$2"; shift 2 ;;
        --addr)           ADDR="$2"; shift 2 ;;
        --config-file)    CONFIG_FILE="$2"; shift 2 ;;
        --no-tls)         NO_TLS=true; shift ;;
        --bundle)         BUNDLES+=("$2"); shift 2 ;;
        --log-level)      LOG_LEVEL="$2"; shift 2 ;;
        --tls-cert)       TLS_CERT="$2"; shift 2 ;;
        --tls-key)        TLS_KEY="$2"; shift 2 ;;
        --pid-file)       PID_FILE="$2"; shift 2 ;;
        --log-file)       LOG_FILE="$2"; shift 2 ;;
        --foreground)     FOREGROUND=true; shift ;;
        --help|-h)
            head -25 "$0" | grep '^#' | sed 's/^# \?//'
            exit 0
            ;;
        *)
            err "Unbekannte Option: $1"
            exit 1
            ;;
    esac
done

# ----- INI-Defaults anwenden (CLI überschreibt) -----

if [[ -f "${SCRIPT_DIR}/${INI_FILE}" ]]; then
    status "Konfiguration geladen: ${SCRIPT_DIR}/${INI_FILE}"
fi

if [[ -z "$ADDR" ]]; then
    _ini_addr=$(ini_get server addr)
    _ini_port=$(ini_get server port)
    [[ -n "$_ini_addr" && -n "$_ini_port" ]] && ADDR="${_ini_addr}:${_ini_port}"
fi
[[ -z "$LOG_LEVEL" ]]   && LOG_LEVEL=$(ini_get logging level)
[[ -z "$TLS_CERT" ]]    && TLS_CERT=$(ini_get tls cert_file)
[[ -z "$TLS_KEY" ]]     && TLS_KEY=$(ini_get tls key_file)
[[ -z "$PID_FILE" ]]    && PID_FILE=$(ini_get process pid_file "npa.pid")
[[ -z "$LOG_FILE" ]]    && LOG_FILE=$(ini_get logging log_file "npa.log")

if [[ "$NO_TLS" == false ]]; then
    _tls_enabled=$(ini_get tls enabled "true")
    [[ "$_tls_enabled" == "false" ]] && NO_TLS=true
fi
if [[ "$FOREGROUND" == false ]]; then
    _fg=$(ini_get process foreground "false")
    [[ "$_fg" == "true" ]] && FOREGROUND=true
fi
if [[ ${#BUNDLES[@]} -eq 0 ]]; then
    _ini_bundles=$(ini_get bundles paths)
    if [[ -n "$_ini_bundles" ]]; then
        IFS=',' read -ra BUNDLES <<< "$_ini_bundles"
        BUNDLES=("${BUNDLES[@]## }")
        BUNDLES=("${BUNDLES[@]%% }")
    fi
fi

# ----- Python finden -----
find_python() {
    # venv im Projektverzeichnis
    for vdir in "$SCRIPT_DIR/.venv" "$SCRIPT_DIR/venv"; do
        if [[ -x "$vdir/bin/python" ]]; then
            echo "$vdir/bin/python"
            return
        fi
    done
    # System-Python
    for cmd in python3 python; do
        if command -v "$cmd" &>/dev/null; then
            echo "$cmd"
            return
        fi
    done
    return 1
}

PYTHON=$(find_python) || { err "Python nicht gefunden. Bitte Python 3.12+ installieren."; exit 1; }
status "Python: $PYTHON"

# ----- Bereits laufend? -----
PID_PATH="$SCRIPT_DIR/$PID_FILE"

if [[ -f "$PID_PATH" ]]; then
    OLD_PID=$(cat "$PID_PATH" 2>/dev/null | tr -d '[:space:]')
    if [[ -n "$OLD_PID" ]] && kill -0 "$OLD_PID" 2>/dev/null; then
        err "NPA läuft bereits (PID $OLD_PID). Bitte zuerst mit stop-npa.sh stoppen."
        exit 1
    else
        # Verwaiste PID-Datei aufräumen
        rm -f "$PID_PATH"
    fi
fi

# ----- Argumente aufbauen -----
NPA_ARGS=("-m" "npa" "run")

[[ -n "$ADDR" ]]        && NPA_ARGS+=("--addr" "$ADDR")
[[ -n "$CONFIG_FILE" ]] && NPA_ARGS+=("--config-file" "$CONFIG_FILE")
[[ "$NO_TLS" == true ]] && NPA_ARGS+=("--no-tls")
[[ -n "$LOG_LEVEL" ]]   && NPA_ARGS+=("--log-level" "$LOG_LEVEL")
[[ -n "$TLS_CERT" ]]    && NPA_ARGS+=("--tls-cert-file" "$TLS_CERT")
[[ -n "$TLS_KEY" ]]     && NPA_ARGS+=("--tls-private-key-file" "$TLS_KEY")
for b in "${BUNDLES[@]+"${BUNDLES[@]}"}"; do
    NPA_ARGS+=("--bundle" "$b")
done

# ----- Port für Health-Check -----
SCHEME="https"
PORT=8443

if [[ -n "$ADDR" ]] && [[ "$ADDR" =~ :([0-9]+)$ ]]; then
    PORT="${BASH_REMATCH[1]}"
fi
if [[ "$NO_TLS" == true ]]; then
    SCHEME="http"
    [[ "$PORT" == "8443" ]] && PORT=8181
fi

# ----- Starten -----
LOG_PATH="$SCRIPT_DIR/$LOG_FILE"

if [[ "$FOREGROUND" == true ]]; then
    status "Starte NPA im Vordergrund..."
    status "Befehl: $PYTHON ${NPA_ARGS[*]}"

    cd "$SCRIPT_DIR"

    # PID-Datei schreiben und bei Exit aufräumen
    trap 'rm -f "$PID_PATH"' EXIT INT TERM
    "$PYTHON" "${NPA_ARGS[@]}" &
    NPA_PID=$!
    echo -n "$NPA_PID" > "$PID_PATH"
    ok "NPA gestartet (PID $NPA_PID)"
    wait "$NPA_PID"
    exit $?
fi

# Hintergrund-Start
status "Starte NPA im Hintergrund..."
status "Befehl: $PYTHON ${NPA_ARGS[*]}"

cd "$SCRIPT_DIR"
nohup "$PYTHON" "${NPA_ARGS[@]}" > "$LOG_PATH" 2>&1 &
NPA_PID=$!
disown "$NPA_PID" 2>/dev/null || true
echo -n "$NPA_PID" > "$PID_PATH"

ok "NPA gestartet (PID $NPA_PID)"
status "Log-Datei: $LOG_PATH"
status "PID-Datei: $PID_PATH"

# ----- Health-Check -----
status "Warte auf Server-Bereitschaft..."

MAX_WAIT=$(ini_get process health_check_timeout "15")
WAITED=0
READY=false
CURL_OPTS=(-s -o /dev/null -w "%{http_code}" --max-time 2)

if [[ "$SCHEME" == "https" ]]; then
    CURL_OPTS+=(-k)  # Selbstsignierte Zertifikate akzeptieren
fi

while [[ $WAITED -lt $MAX_WAIT ]]; do
    sleep 1
    WAITED=$((WAITED + 1))

    # Prozess noch am Leben?
    if ! kill -0 "$NPA_PID" 2>/dev/null; then
        err "NPA-Prozess ist unerwartet beendet worden."
        err "Siehe Log: $LOG_PATH"
        rm -f "$PID_PATH"
        exit 1
    fi

    # Health-Endpoint prüfen
    HTTP_CODE=$(curl "${CURL_OPTS[@]}" "${SCHEME}://127.0.0.1:${PORT}/health" 2>/dev/null) || true
    if [[ "$HTTP_CODE" == "200" ]]; then
        READY=true
        break
    fi

    printf "."
done
echo ""

if [[ "$READY" == true ]]; then
    ok "NPA ist bereit! ${SCHEME}://127.0.0.1:${PORT}"
    ok "Dashboard: ${SCHEME}://127.0.0.1:${PORT}/ui/"
else
    err "Health-Check fehlgeschlagen nach ${MAX_WAIT}s — Server antwortet nicht."
    status "Prüfe Log-Datei: $LOG_PATH"
    status "Prozess läuft noch (PID $NPA_PID) — ggf. manuell stoppen."
fi
