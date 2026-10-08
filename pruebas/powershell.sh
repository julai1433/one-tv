#!/bin/bash
# Los guiones de PowerShell de Windows, revisados sin Windows: corre pruebas/test_red_windows.py en un contenedor de
# Ubuntu con PowerShell 7 (pwsh). No toca nada fuera del contenedor y lo borra al terminar.
# Uso: pruebas/powershell.sh     La imagen «one-tv-pruebas-pwsh» queda para la próxima vez (docker rmi one-tv-pruebas-pwsh).
set -euo pipefail
DIR="$(cd "$(dirname "$0")/.." && pwd)"
IMG=one-tv-pruebas-pwsh
docker build -q -t "$IMG" "$DIR/pruebas/pwsh" >/dev/null
docker run --rm -v "$DIR":/src:ro "$IMG" bash -c '
  set -e
  mkdir ~/one-tv && tar -C /src --exclude=.git --exclude=config.json -cf - mac pruebas windows | tar -C ~/one-tv -xf - && cd ~/one-tv
  echo "== $(pwsh -NoProfile -Command "\"PowerShell \" + \$PSVersionTable.PSVersion") · $(python3 --version)"
  python3 -m unittest -v pruebas.test_red_windows 2>&1 | grep -E "GuionesDePowerShell|^(Ran|OK|FAILED|ERROR:|FAIL:)"
'
