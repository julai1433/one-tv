#!/bin/bash
# Prueba la imagen de Docker de One TV (Dockerfile): la construye, arranca un contenedor con una biblioteca de ejemplo
# montada de solo lectura y revisa que el servidor responda, que convierta video con libx264, que no escriba en la
# biblioteca, que los datos sobrevivan a recrear el contenedor y que no corra como «root».
# El Roku se apunta a 127.0.0.1 (el contenedor mismo) y va en red puente: no busca ni toca ninguna TV.
# Uso: pruebas/docker.sh [puerto]      (por omisión 8802). Borra el contenedor, el volumen y la carpeta temporal al
#                                      terminar; la imagen «one-tv-prueba-docker» queda (docker rmi la borra).
set -euo pipefail
DIR="$(cd "$(dirname "$0")/.." && pwd)"
PUERTO="${1:-8802}"
[ "$PUERTO" = "8765" ] && { echo "✗ El 8765 es el del servidor de verdad: usa otro puerto."; exit 1; }
IMG=one-tv-prueba-docker
CONT=one-tv-prueba-docker-$$
VOL=one-tv-prueba-datos-$$
TMP="$(mktemp -d)"
LIB="$TMP/biblioteca"
BASE="http://127.0.0.1:$PUERTO"
FALLAS=0
mkdir -p "$LIB"

limpiar() {
  docker rm -f "$CONT" >/dev/null 2>&1 || true
  docker volume rm "$VOL" >/dev/null 2>&1 || true
  chmod -R u+w "$TMP" 2>/dev/null || true
  rm -rf "$TMP"
}
trap limpiar EXIT

paso() {  # paso <0|1> texto
  if [ "$1" = "1" ]; then echo "  ✓ $2"; else echo "  ✗ $2"; FALLAS=$((FALLAS + 1)); fi
}
ok() { if "$@" >/dev/null 2>&1; then echo 1; else echo 0; fi; }

echo "== Imagen"
docker build -q -t "$IMG" "$DIR" >/dev/null
echo "  $(docker image inspect "$IMG" --format '{{.Architecture}} · {{.Size}} bytes')"

echo "== Videos de prueba (con el ffmpeg de la propia imagen)"
SRC=(-f lavfi -i "testsrc2=size=426x240:rate=24:duration=160" -f lavfi -i "sine=frequency=440:duration=160")
H264=(-c:v libx264 -preset ultrafast -pix_fmt yuv420p -g 48)
ff() { docker run --rm --entrypoint ffmpeg -v "$LIB":/salida "$IMG" -v error -y "$@"; }
ff "${SRC[@]}" "${H264[@]}" -c:a aac -shortest "/salida/Prueba Directa (2020).mp4"
ff "${SRC[@]}" "${H264[@]}" -c:a ac3 -ac 6 -shortest "/salida/Prueba Copia (2019).mkv"
ff "${SRC[@]}" -c:v libx265 -preset ultrafast -pix_fmt yuv420p10le -x265-params pools=none:log-level=none -c:a aac -shortest \
   "/salida/Prueba HEVC (2021).mkv"
chmod -R a+rX "$LIB"
ANTES="$(cd "$LIB" && find . -type f -exec stat -f '%N %z %m' {} + 2>/dev/null || find . -type f -printf '%p %s %T@\n' | sort)"

arrancar() {
  docker rm -f "$CONT" >/dev/null 2>&1 || true
  docker run -d --name "$CONT" -p "$PUERTO:8765" -e PUID=1000 -e PGID=1000 -e TZ=America/Mexico_City \
    -e ROKU_IP=127.0.0.1 -v "$LIB":/biblioteca:ro -v "$VOL":/datos "$IMG" >/dev/null
  for _ in $(seq 1 90); do
    curl -fs "$BASE/api/status" >/dev/null 2>&1 && return 0
    [ "$(docker inspect -f '{{.State.Running}}' "$CONT")" = "true" ] || return 1
    sleep 1
  done
  return 1
}

json() { python3 -c "import sys, json; d = json.load(sys.stdin); $1"; }

echo "== Servidor"
T0=$(date +%s)
if arrancar; then paso 1 "responde /api/status ($(( $(date +%s) - T0 )) s)"; else paso 0 "responde /api/status"; docker logs "$CONT" | tail -20; exit 1; fi

ITEMS="$(curl -fs "$BASE/api/library")"
N=$(echo "$ITEMS" | json 'print(len(d["items"]))')
MODOS=$(echo "$ITEMS" | json 'print(" ".join(sorted(i["mode"] for i in d["items"].values())))')
paso $([ "$N" = "3" ] && echo 1 || echo 0) "/api/library: $N videos ($MODOS)"
paso $([ "$MODOS" = "copy direct full" ] && echo 1 || echo 0) "uno directo, uno con copia de video y uno con conversión completa"

FULL=$(echo "$ITEMS" | json 'print(next(i for i in d["items"].values() if i["mode"] == "full")["audio"][0]["hls"])')
COPY=$(echo "$ITEMS" | json 'print(next(i for i in d["items"].values() if i["mode"] == "copy")["audio"][0]["hls"])')
POSTER=$(echo "$ITEMS" | json 'print(next(i for i in d["items"].values() if i["mode"] == "full")["poster"])')
MAGIA=$(curl -fs "$BASE$POSTER" | head -c 3 | od -An -tx1 | tr -d ' ')
paso $([ "$MAGIA" = "ffd8ff" ] && echo 1 || echo 0) "póster JPEG ($POSTER)"

for par in "full:$FULL" "copy:$COPY"; do
  modo="${par%%:*}"; hls="${par#*:}"
  LISTA="$(curl -fs "$BASE$hls")"
  paso $(echo "$LISTA" | grep -q '^#EXTM3U' && echo "$LISTA" | grep -q 'seg0.ts' && echo 1 || echo 0) \
       "lista HLS ($modo): $(echo "$LISTA" | grep -c '#EXTINF') trozos"
  T1=$(date +%s)
  curl -fs --max-time 90 "$BASE${hls/index.m3u8/seg1.ts}" -o "$TMP/trozo-$modo.ts"
  TAM=$(wc -c < "$TMP/trozo-$modo.ts" | tr -d ' ')
  CODEC=$(docker run --rm --entrypoint ffprobe -v "$TMP":/t:ro "$IMG" -v error -select_streams v:0 \
          -show_entries stream=codec_name -of csv=p=0 "/t/trozo-$modo.ts" | head -1)
  paso $([ "$TAM" -gt 10000 ] && [ "$CODEC" = "h264" ] && echo 1 || echo 0) \
       "trozo convertido ($modo): $TAM bytes, video $CODEC, $(( $(date +%s) - T1 )) s"
done

REG="$(docker logs "$CONT" 2>&1)"
paso $(echo "$REG" | grep -qi 'libx264' && echo 1 || echo 0) "el registro dice que convierte con libx264"

echo "== Usuario y permisos"
UID_SERV=$(docker exec "$CONT" sh -c 'ps -o uid= -C python3 | head -1 | tr -d " "')
paso $([ "$UID_SERV" = "1000" ] && echo 1 || echo 0) "el servidor corre como usuario 1000, no como root (uid $UID_SERV)"
paso $(ok docker exec -u 1000 "$CONT" test -w /datos) "puede escribir en /datos"
paso $([ "$(ok docker exec -u 1000 "$CONT" touch /biblioteca/escribir)" = "0" ] && echo 1 || echo 0) "no puede escribir en /biblioteca"
DESPUES="$(cd "$LIB" && find . -type f -exec stat -f '%N %z %m' {} + 2>/dev/null || find . -type f -printf '%p %s %T@\n' | sort)"
paso $([ "$ANTES" = "$DESPUES" ] && echo 1 || echo 0) "la biblioteca quedó igual (mismos archivos, tamaños y fechas)"
paso $([ "$(echo "$REG" | grep -c 'Traceback')" = "0" ] && echo 1 || echo 0) "sin errores (Traceback) en el registro"

echo "== Los datos sobreviven"
CLAVE1="$(docker exec "$CONT" sha256sum /datos/datos/clave_enlaces | cut -d' ' -f1)"
docker exec "$CONT" sh -c 'echo "{\"prueba\": 1}" > /datos/datos/marca.json'
arrancar && paso 1 "contenedor nuevo arriba con el mismo volumen" || paso 0 "contenedor nuevo arriba"
CLAVE2="$(docker exec "$CONT" sha256sum /datos/datos/clave_enlaces | cut -d' ' -f1)"
paso $([ -n "$CLAVE1" ] && [ "$CLAVE1" = "$CLAVE2" ] && echo 1 || echo 0) "la clave de los enlaces es la misma"
paso $(ok docker exec "$CONT" test -f /datos/datos/marca.json) "el archivo que se dejó en /datos sigue ahí"

echo
if [ "$FALLAS" = "0" ]; then echo "Todo bien."; else echo "$FALLAS cosa(s) fallaron."; docker logs "$CONT" 2>&1 | tail -30; exit 1; fi
