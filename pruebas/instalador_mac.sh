#!/bin/bash
# El instalador de verdad (instalar.sh) en esta Mac, como si fuera una Mac sin Homebrew, sin Python y sin las
# herramientas de Xcode: HOME falso en /tmp (no toca tu carpeta personal, ni tus servicios, ni el puerto 8765), PATH
# sin Homebrew, sin arranque automático (el servidor queda de fondo en otro puerto) y sin poder hablarle a ninguna TV
# (sandbox-exec no deja salir nada a la búsqueda SSDP ni a los puertos del Roku). Baja de verdad Python y ffmpeg
# (unos 80 MB). One TV sale de este repositorio (lo confirmado y lo cambiado, como el .tar.gz de GitHub).
# Revisa: que baja y verifica Python y ffmpeg, que el servidor arranca con ellos, que /bienvenida responde y la página
# principal manda ahí, que ffmpeg tiene VideoToolbox, que yt-dlp se instala con ese Python, y que volver a correrlo
# pone al día sin bajar nada otra vez ni perder config.json ni los datos. Al final apaga el servidor y borra todo.
# Uso: pruebas/instalador_mac.sh [puerto]      (por omisión 8803)
set -uo pipefail
DIR="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${1:-8803}"
[ "$PORT" = 8765 ] && { echo "✗ El 8765 es el del servidor de verdad: usa otro puerto."; exit 1; }
[ "$(uname -s)" = Darwin ] || { echo "✗ Esta prueba es para macOS."; exit 1; }
CASA="$(mktemp -d /tmp/one-tv-instalador-mac.XXXXXX)"
mkdir -p "$CASA/casa" "$CASA/tmp"
DEST="$CASA/casa/One TV"
SERVICIO="$CASA/casa/Library/Application Support/cine-roku"
fallas=0
paso() { if [ "$1" = 0 ]; then echo "  ✓ $2"; else echo "  ✗ $2"; fallas=$((fallas + 1)); fi; }
apagar() {
  local pid
  pid="$(cat "$SERVICIO/servidor-suelto.pid" 2>/dev/null)"
  [ -n "$pid" ] && kill "$pid" 2>/dev/null
  sleep 1
  pkill -f "$CASA" 2>/dev/null   # y lo que haya quedado de esta prueba (ffmpeg, yt-dlp)
  rm -rf "$CASA"
}
trap apagar EXIT

ref="$(git -C "$DIR" stash create 2>/dev/null)"
git -C "$DIR" archive --format=tar.gz --prefix=one-tv-main/ -o "$CASA/one-tv.tar.gz" "${ref:-HEAD}" || exit 1
SANDBOX='(version 1)(allow default)
(deny network-outbound (remote ip "*:1900"))
(deny network-outbound (remote ip "*:8060"))
(deny network-outbound (remote ip "*:80"))'
instalar() {
  sandbox-exec -p "$SANDBOX" env -i HOME="$CASA/casa" USER="$USER" LOGNAME="$USER" TMPDIR="$CASA/tmp" \
    PATH=/usr/bin:/bin:/usr/sbin:/sbin LANG=es_MX.UTF-8 DEVELOPER_DIR=/no-hay-xcode ONE_TV_LUGARES= \
    ONE_TV_FUENTE="$CASA/one-tv.tar.gz" ONE_TV_SIN_AUTOARRANQUE=1 ONE_TV_PUERTO="$PORT" CINE_NO_BROWSER=1 \
    bash < "$DIR/instalar.sh" 2>&1 | tee "$CASA/salida.txt" | sed 's/^/    /'
}
http() { curl -s -o /dev/null -w '%{http_code} %{redirect_url}' "http://127.0.0.1:$PORT$1"; }

echo "== Primera vez (una Mac sin Python ni ffmpeg)"
inicio=$SECONDS
instalar
paso $? "el instalador terminó bien ($((SECONDS - inicio)) s)"
grep -q "Bajando Python 3.12.15" "$CASA/salida.txt"; paso $? "bajó Python"
grep -q "Bajando ffmpeg 9.0.2" "$CASA/salida.txt"; paso $? "bajó ffmpeg"
[ -x "$DEST/programas/python/bin/python3" ] && [ -x "$DEST/programas/bin/ffmpeg" ] && [ -x "$DEST/programas/bin/ffprobe" ]
paso $? "Python, ffmpeg y ffprobe en $DEST/programas"
"$DEST/programas/bin/ffmpeg" -hide_banner -encoders 2>/dev/null | grep -q h264_videotoolbox
paso $? "ffmpeg con VideoToolbox (el chip de video de la Mac)"
[ "$(http /bienvenida)" = "200 " ]; paso $? "/bienvenida responde"
curl -s "http://127.0.0.1:$PORT/bienvenida" | grep -q "One TV está listo"; paso $? "y dice «One TV está listo»"
[ "$(http /)" = "302 http://127.0.0.1:$PORT/bienvenida" ]; paso $? "la página principal manda a /bienvenida"
pid="$(cat "$SERVICIO/servidor-suelto.pid")"
ps -p "$pid" -o command= | grep -q "$DEST/programas/python/bin/python3"; paso $? "el servidor corre con el Python de One TV"
python3 -c "import json,sys; c=json.load(open(sys.argv[1])); sys.exit(not (c['bienvenida_hecha'] is False and c['puerto'] == $PORT))" \
  "$DEST/config.json"; paso $? "config.json sin preguntas: bienvenida pendiente, puerto $PORT"
[ "$(stat -f %Lp "$DEST/config.json")" = 600 ]; paso $? "config.json solo para su dueño (600)"
[ -d "$CASA/casa/Movies/Biblioteca" ]; paso $? "la carpeta de películas y series quedó creada"
for _ in $(seq 1 120); do [ -x "$SERVICIO/ytdlp/bin/yt-dlp" ] && break; sleep 2; done
"$SERVICIO/ytdlp/bin/yt-dlp" --version >/dev/null 2>&1; paso $? "yt-dlp instalado con ese Python (entorno aparte, por https)"
grep -q "Video:" "$CASA/casa/Library/Logs/cine-roku.log" && grep "Video:" "$CASA/casa/Library/Logs/cine-roku.log" | head -1 | sed 's/^/    /'
! grep -qE "Traceback|✗" "$CASA/casa/Library/Logs/cine-roku.log"; paso $? "el registro del servidor sin errores"

echo "== Se termina la bienvenida y se agregan datos; luego, otra vez el mismo comando (poner al día)"
curl -s -X POST -H 'Content-Type: application/json' -d '{"hecha": true}' "http://127.0.0.1:$PORT/api/bienvenida" >/dev/null
mkdir -p "$SERVICIO/datos" && echo "lo visto" > "$SERVICIO/datos/marca-de-prueba.txt"
inicio=$SECONDS
instalar
paso $? "el instalador terminó bien otra vez ($((SECONDS - inicio)) s)"
! grep -q "Bajando Python\|Bajando ffmpeg" "$CASA/salida.txt"; paso $? "no volvió a bajar Python ni ffmpeg"
grep -q "Poniendo al día One TV" "$CASA/salida.txt"; paso $? "puso al día One TV"
grep -q "Ábrelo en el navegador:  http://localhost:$PORT\$" "$CASA/salida.txt"; paso $? "ya no manda a la bienvenida"
python3 -c "import json,sys; c=json.load(open(sys.argv[1])); sys.exit(not c['bienvenida_hecha'])" "$DEST/config.json"
paso $? "config.json conservó lo del navegador"
[ -f "$SERVICIO/datos/marca-de-prueba.txt" ]; paso $? "los datos (lo visto) se quedaron"
nuevo="$(cat "$SERVICIO/servidor-suelto.pid")"
[ "$nuevo" != "$pid" ] && ! kill -0 "$pid" 2>/dev/null; paso $? "el servidor de antes se cambió por el nuevo ($pid → $nuevo)"
[ "$(http /)" = "200 " ]; paso $? "la página principal abre directo"

[ "$fallas" = 0 ] && echo "Todo bien." || echo "$fallas cosa(s) fallaron."
exit $((fallas > 0))
