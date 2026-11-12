#!/usr/bin/env bash
# Startet Server, kopfloses Chromium und die Halte-Verbindung (412 × 860).
#   starten.sh <arbeitsordner> [app-port] [cdp-port] [breite] [hoehe]
# <arbeitsordner>: ein Ordner im Scratchpad der Sitzung — darin daten/ (Test-DB), chrom/,
# die Logs und pids. Testdaten vorher anlegen (TRAININGSAPP_DATA_DIR=<arbeitsordner>/daten).
set -euo pipefail
ORDNER=$(realpath -m "$1"); APP=${2:-8591}; CDP=${3:-9391}; BREITE=${4:-412}; HOEHE=${5:-860}
HIER=$(cd "$(dirname "$0")" && pwd)
PROJEKT=$(cd "$HIER/../../../.." && pwd)
mkdir -p "$ORDNER/daten" "$ORDNER/chrom"
for p in "$APP" "$CDP"; do
  if ss -ltn | grep -q ":$p "; then
    echo "Port $p ist belegt — ein alter Server zeigte alten Code. Erst beenden.sh oder andere Ports." >&2
    exit 1
  fi
done
cd "$PROJEKT"
# fastapi steht nicht in uv.lock; flet-web 1.0.3 verträgt die neueste nicht („openapi_prefix“) —
# darum die passende nur für diesen Aufruf, ohne Eingriff ins .venv
TRAININGSAPP_DATA_DIR="$ORDNER/daten" PYTHONUNBUFFERED=1 setsid nohup \
  uv run --with "fastapi==0.143.2" python "$HIER/server.py" "$APP" > "$ORDNER/server.log" 2>&1 &
for _ in $(seq 120); do ss -ltn | grep -q ":$APP " && break; sleep 0.5; done
ss -ltn | grep -q ":$APP " || { echo "Server kam nicht hoch:" >&2; tail -20 "$ORDNER/server.log" >&2; exit 1; }
setsid nohup chromium-browser --headless=new --remote-debugging-port="$CDP" \
  --user-data-dir="$ORDNER/chrom" --window-size="$BREITE,$HOEHE" --enable-unsafe-swiftshader \
  --use-fake-device-for-media-stream --use-fake-ui-for-media-stream \
  about:blank > "$ORDNER/chrom.log" 2>&1 &
for _ in $(seq 40); do ss -ltn | grep -q ":$CDP " && break; sleep 0.5; done
uv run python "$HIER/cdp.py" "$CDP" frisch "http://127.0.0.1:$APP/" > /dev/null
setsid nohup uv run python "$HIER/halten.py" "$CDP" "$BREITE" "$HOEHE" > "$ORDNER/halten.log" 2>&1 &
sleep 2
echo "$APP $CDP" > "$ORDNER/ports"
echo "bereit: App http://127.0.0.1:$APP  CDP $CDP  Breite $(uv run python "$HIER/cdp.py" "$CDP" js window.innerWidth)"
