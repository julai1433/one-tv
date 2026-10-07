#!/bin/bash
# Captura de pantalla de la app de desarrollo del Roku
# La contraseña del modo desarrollador y la IP del Roku salen de config.json (no se guardan en el repositorio).
# Si roku_ip está vacío, se busca el Roku en la red (mac/roku.py, discover()).
DIR="$(cd "$(dirname "$0")/.." && pwd)"
OUT=${1:-/tmp/captura_tele.jpg}
PASS=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("roku_password", ""))' "$DIR/config.json")
IP=$(python3 -c '
import json, sys
sys.path.insert(0, sys.argv[2] + "/mac")
from roku import discover
ip = json.load(open(sys.argv[1])).get("roku_ip", "") or discover()
print(ip or "")' "$DIR/config.json" "$DIR")
[ -n "$IP" ] || { echo "No encontré el Roku: pon su IP en config.json (roku_ip)." >&2; exit 1; }
html=$(curl -s --digest -u "rokudev:$PASS" -F mysubmit=Screenshot -F archive= -F passwd= http://$IP/plugin_inspect)
path=$(echo "$html" | grep -o 'pkgs/dev\.[a-z]*?time=[0-9]*' | head -1)
curl -s --digest -u "rokudev:$PASS" "http://$IP/$path" -o "$OUT" && echo "$OUT"
