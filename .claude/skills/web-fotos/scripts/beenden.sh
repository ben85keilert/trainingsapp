#!/usr/bin/env bash
# Beendet Server und Chromium eines Arbeitsordners — über die Ports, nie über Namen
# (pkill -f träfe die eigene Shell).
#   beenden.sh <arbeitsordner>
set -u
read -r APP CDP < "$(realpath -m "$1")/ports" || { echo "keine ports-Datei" >&2; exit 1; }
fuser -k "$CDP/tcp" > /dev/null 2>&1
fuser -k "$APP/tcp" > /dev/null 2>&1
sleep 1
ss -ltn | grep -E ":($APP|$CDP) " && echo "läuft noch" >&2 || echo "beendet"
