#!/bin/bash
# El instalador de verdad (instalar.sh) con Docker, en un Ubuntu 24.04 con systemd dentro de Docker (que se borra al
# terminar) y SIN Docker instalado:
# 1. Como un usuario normal, con --docker: instala Docker con el instalador oficial (get.docker.com: necesita
#    internet), crea el contenedor «one-tv» (red host, arranque solo, carpetas de solo lectura) y /bienvenida responde.
# 2. Como si fuera un Synology (/etc/synoinfo.conf y /volume1, sin --docker): lo reconoce, pone al día el contenedor
#    con /volume1 de solo lectura y los datos en /volume1/docker/one-tv; One TV ve tus videos y no puede escribirles.
# 3. Con un contenedor «one-tv» que no creó el instalador: no lo toca.
# La imagen de One TV sale de este repositorio (Dockerfile), no de GitHub. No busca ninguna TV. Puerto 8808.
# Uso: pruebas/instalador_nas.sh     (borra al terminar el contenedor, su volumen y las imágenes que construyó)
set -uo pipefail
DIR="$(cd "$(dirname "$0")/.." && pwd)"
PUERTO=8808
CASA="$(mktemp -d /tmp/one-tv-instalador-nas.XXXXXX)"
NOMBRE=one-tv-prueba-nas
IMG_ONE_TV=one-tv-prueba-nas:local
IMG_UBUNTU=one-tv-prueba-nas-systemd
VOLUMEN=one-tv-prueba-nas-docker
VOLUMEN2=one-tv-prueba-nas-containerd
fallas=0
paso() { if [ "$1" = 0 ]; then echo "  ✓ $2"; else echo "  ✗ $2"; fallas=$((fallas + 1)); fi; }
limpiar() {
  docker rm -f "$NOMBRE" >/dev/null 2>&1
  docker volume rm "$VOLUMEN" "$VOLUMEN2" >/dev/null 2>&1
  docker rmi "$IMG_ONE_TV" "$IMG_UBUNTU" >/dev/null 2>&1
  rm -rf "$CASA"
}
trap limpiar EXIT

echo "== Preparando (la imagen de One TV de este repositorio y un Ubuntu con systemd, sin Docker)"
docker build -q -t "$IMG_ONE_TV" "$DIR" >/dev/null || exit 1
docker save -o "$CASA/imagen.tar" "$IMG_ONE_TV" || exit 1
docker build -q -t "$IMG_UBUNTU" -f "$DIR/pruebas/ubuntu/Dockerfile.systemd" "$DIR/pruebas/ubuntu" >/dev/null || exit 1
cp "$DIR/instalar.sh" "$CASA/instalar.sh"
docker rm -f "$NOMBRE" >/dev/null 2>&1
# /var/lib/docker y /var/lib/containerd en volúmenes: el Docker de adentro no puede guardar sus imágenes encima del
# sistema de archivos del contenedor (overlay sobre overlay).
docker run -d --name "$NOMBRE" --privileged --cgroupns=host -v /sys/fs/cgroup:/sys/fs/cgroup:rw --tmpfs /run \
  --tmpfs /run/lock -v "$VOLUMEN":/var/lib/docker -v "$VOLUMEN2":/var/lib/containerd -v "$CASA":/casa:ro "$IMG_UBUNTU" \
  >/dev/null || exit 1
for _ in $(seq 1 90); do
  case "$(docker exec "$NOMBRE" systemctl is-system-running 2>/dev/null)" in running | degraded) break ;; esac
  sleep 1
done
docker exec "$NOMBRE" bash -c 'apt-get update -q >/dev/null && DEBIAN_FRONTEND=noninteractive apt-get install -y -q \
  sudo wget ca-certificates >/dev/null && echo "ana ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/ana' || exit 1
docker exec "$NOMBRE" sh -c '! command -v docker' >/dev/null; paso $? "el Ubuntu de prueba no tiene Docker"
como_ana() { docker exec "$NOMBRE" su - ana -c "$1"; }
VARIABLES="ONE_TV_IMAGEN=$IMG_ONE_TV ONE_TV_IMAGEN_ARCHIVO=/casa/imagen.tar ONE_TV_PUERTO=$PUERTO"
adentro() { docker exec "$NOMBRE" "$@"; }

echo "== 1. Linux común con --docker: instala Docker y One TV"
como_ana "$VARIABLES bash /casa/instalar.sh --docker" 2>&1 | tee "$CASA/salida1.txt" | sed 's/^/    /'
paso $? "el instalador terminó bien"
grep -q "Lo instalo con el instalador oficial de Docker" "$CASA/salida1.txt"; paso $? "dijo que instala Docker con el oficial"
grep -q "Docker instalado" "$CASA/salida1.txt"; paso $? "Docker instalado"
grep -qE "http://[0-9.]+:$PUERTO/bienvenida" "$CASA/salida1.txt"; paso $? "dio la dirección de /bienvenida"
adentro systemctl is-enabled docker >/dev/null 2>&1; paso $? "Docker arranca con el equipo"
[ "$(adentro docker inspect -f '{{.HostConfig.NetworkMode}} {{.HostConfig.RestartPolicy.Name}}' one-tv)" = "host unless-stopped" ]
paso $? "contenedor con red host y arranque solo"
adentro docker inspect -f '{{range .Mounts}}{{.Destination}}:{{.RW}} {{end}}' one-tv | grep -q "/home:false"
paso $? "/home montada de solo lectura"
s="$(adentro wget -q -O - "http://127.0.0.1:$PUERTO/bienvenida" 2>/dev/null)"
echo "$s" | grep -qi "<html"; paso $? "/bienvenida responde"
adentro docker logs one-tv 2>&1 | grep -q "Carpetas del NAS que One TV puede leer (de solo lectura): /home"
paso $? "el registro dice qué carpetas puede leer"

echo "== 2. Como un Synology (sin --docker): lo reconoce y pone al día el contenedor"
adentro bash -c 'touch /etc/synoinfo.conf && mkdir -p /volume1/docker /volume1/video && echo hola > "/volume1/video/Película (2020).mkv"'
como_ana "$VARIABLES bash /casa/instalar.sh" 2>&1 | tee "$CASA/salida2.txt" | sed 's/^/    /'
paso $? "el instalador terminó bien"
grep -q "en tu Synology con Docker" "$CASA/salida2.txt"; paso $? "reconoció el Synology"
grep -q "Sus datos quedan en /volume1/docker/one-tv" "$CASA/salida2.txt"; paso $? "datos en /volume1/docker/one-tv"
adentro docker exec one-tv ls /volume1/video | grep -q "Película (2020).mkv"; paso $? "One TV ve los videos de /volume1"
escribir="$(adentro docker exec one-tv touch /volume1/video/escribir 2>&1)"
echo "$escribir" | grep -q "Read-only file system" && ! adentro test -e /volume1/video/escribir
paso $? "y no puede escribir en ellos"
[ -n "$escribir" ] && echo "    ($escribir)"
adentro test -f /volume1/docker/one-tv/config.json; paso $? "config.json en la carpeta de datos del NAS"
[ "$(adentro docker ps -a --filter name=one-tv --format '{{.Names}}' | wc -l | tr -d ' ')" = 1 ]; paso $? "un solo contenedor one-tv"
adentro wget -q -O /dev/null "http://127.0.0.1:$PUERTO/bienvenida"; paso $? "/bienvenida responde"

echo "== 3. Un contenedor «one-tv» ajeno no se toca"
adentro docker rm -f one-tv >/dev/null
adentro docker run -d --name one-tv --entrypoint sleep "$IMG_ONE_TV" 600 >/dev/null
como_ana "$VARIABLES bash /casa/instalar.sh" > "$CASA/salida3.txt" 2>&1
[ $? != 0 ] && grep -q "no creó este instalador" "$CASA/salida3.txt"; paso $? "lo dice y termina sin tocarlo"
[ "$(adentro docker inspect -f '{{.Config.Entrypoint}}' one-tv)" = "[sleep]" ]; paso $? "el contenedor ajeno sigue igual"

[ "$fallas" = 0 ] && echo "Todo bien." || echo "$fallas cosa(s) fallaron."
exit $((fallas > 0))
