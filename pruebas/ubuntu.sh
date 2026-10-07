#!/bin/bash
# Corre en Ubuntu 24.04 (un contenedor de Docker) todas las pruebas, con el mismo «faulthandler» que en GitHub, y la
# prueba de humo del servidor (pruebas/humo_servidor.py). No toca nada fuera del contenedor y lo borra al terminar.
# Uso: pruebas/ubuntu.sh        La imagen «one-tv-pruebas-ubuntu» queda para la próxima vez
#                               (se borra con: docker rmi one-tv-pruebas-ubuntu).
set -euo pipefail
DIR="$(cd "$(dirname "$0")/.." && pwd)"
IMG=one-tv-pruebas-ubuntu
docker build -q -t "$IMG" "$DIR/pruebas/ubuntu" >/dev/null
docker run --rm -v "$DIR":/src:ro "$IMG" bash -c '
  set -e
  mkdir ~/one-tv && tar -C /src --exclude=.git --exclude=config.json -cf - . | tar -C ~/one-tv -xf - && cd ~/one-tv
  echo "== $(. /etc/os-release; echo "$PRETTY_NAME") · $(python3 --version) · $(ffmpeg -version | head -1 | cut -d" " -f1-3)"
  echo "== Pruebas"
  python3 -X faulthandler -c "import faulthandler, unittest; faulthandler.dump_traceback_later(180, exit=True);
unittest.main(module=None, argv=[\"pruebas\", \"discover\", \"-s\", \"pruebas\", \"-p\", \"test_*.py\"])" 2>&1 \
    | grep -E "^(Ran|OK|FAILED|ERROR:|FAIL:)" || true
  echo "== Prueba de humo"
  python3 pruebas/humo_servidor.py --puerto 8794
'
