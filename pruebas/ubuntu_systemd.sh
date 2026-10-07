#!/bin/bash
# ./cine autoarranque en Ubuntu 24.04 con systemd de verdad (un contenedor de Docker que arranca como una computadora).
# Entra por SSH como un usuario normal y revisa: ./cine configurar, ./cine autoarranque (el servicio de systemd y
# «linger»), que el servidor responda, que se levante solo si se cae, que arranque al reiniciar la computadora sin que
# nadie inicie sesión y ./cine quitar-autoarranque. No busca ninguna TV (la IP del Roku es 127.0.0.1).
# Necesita Docker con contenedores «privileged» (systemd dentro de un contenedor). Borra el contenedor al terminar; la
# imagen «one-tv-pruebas-systemd» queda (docker rmi one-tv-pruebas-systemd).
set -uo pipefail
DIR="$(cd "$(dirname "$0")/.." && pwd)"
IMG=one-tv-pruebas-systemd
NAME=one-tv-pruebas-systemd
PORT=8794
fallas=0
paso() { if [ "$1" = 0 ]; then echo "  ✓ $2"; else echo "  ✗ $2"; fallas=$((fallas + 1)); fi; }
como_ana() { docker exec "$NAME" ssh -o StrictHostKeyChecking=no -o LogLevel=ERROR ana@localhost "$@"; }
arrancado() {   # espera a que systemd termine de arrancar el contenedor
  for _ in $(seq 1 90); do
    case "$(docker exec "$NAME" systemctl is-system-running 2>/dev/null)" in running|degraded) return 0 ;; esac
    sleep 1
  done
  return 1
}
responde() {   # espera hasta 60 s a que el servidor conteste
  docker exec "$NAME" python3 -c "
import json, time, urllib.request
for _ in range(60):
    try:
        print(json.loads(urllib.request.urlopen('http://127.0.0.1:$PORT/api/status', timeout=2).read())['items'], 'videos'); break
    except OSError: time.sleep(1)
else: raise SystemExit(1)"
}

docker build -q -t "$IMG" -f "$DIR/pruebas/ubuntu/Dockerfile.systemd" "$DIR/pruebas/ubuntu" >/dev/null || exit 1
docker rm -f "$NAME" >/dev/null 2>&1
trap 'docker rm -f "$NAME" >/dev/null 2>&1' EXIT
docker run -d --name "$NAME" --privileged --cgroupns=host -v /sys/fs/cgroup:/sys/fs/cgroup:rw --tmpfs /run \
  --tmpfs /run/lock -v "$DIR":/src:ro "$IMG" >/dev/null || exit 1
arrancado || exit 1
docker exec "$NAME" bash -c 'mkdir /home/ana/one-tv && tar -C /src --exclude=.git --exclude=config.json -cf - . | tar -C /home/ana/one-tv -xf -
  chown -R ana:ana /home/ana/one-tv'

echo "== ./cine configurar (Enter, Enter, IP 127.0.0.1, sin música) y un video de prueba"
como_ana "cd one-tv && printf '\n\n127.0.0.1\nno\n' | ./cine configurar >/dev/null && python3 -c \"
import json; c = json.load(open('config.json')); c['puerto'] = $PORT; json.dump(c, open('config.json', 'w'))\" &&
  ffmpeg -v error -f lavfi -i testsrc2=size=426x240:rate=24:duration=160 -f lavfi -i sine=duration=160 -c:v libx264 \
    -preset ultrafast -c:a ac3 -shortest ~/Videos/Biblioteca/'Prueba (2020).mkv'"
paso $? "config.json en ~/one-tv y la biblioteca en ~/Videos/Biblioteca"

echo "== ./cine autoarranque"
como_ana "cd one-tv && ./cine autoarranque" | sed 's/^/    /'
paso $? "./cine autoarranque"
como_ana "systemctl --user is-enabled cine-roku.service && systemctl --user is-active cine-roku.service" >/dev/null
paso $? "servicio de systemd del usuario activado y corriendo"
docker exec "$NAME" test -e /var/lib/systemd/linger/ana
paso $? "linger activado (arranca sin iniciar sesión)"
responde >/dev/null
paso $? "el servidor responde"

echo "== Se cae y se levanta solo (a los 30 s)"
antes=$(como_ana "systemctl --user show -p MainPID --value cine-roku.service")
como_ana "kill -9 $antes"
sleep 35
despues=$(como_ana "systemctl --user show -p MainPID --value cine-roku.service")
[ "$despues" != "0" ] && [ "$despues" != "$antes" ]
paso $? "proceso $antes → $despues"

echo "== Reiniciar la computadora (el contenedor) sin que nadie inicie sesión"
docker restart "$NAME" >/dev/null
arrancado
responde >/dev/null
paso $? "el servidor responde tras el reinicio"
sesiones=$(docker exec "$NAME" loginctl list-sessions --no-legend)
[ -z "$sesiones" ]
paso $? "sin ninguna sesión abierta $sesiones"

echo "== ./cine (actualiza y muestra el estado) y ./cine estado"
como_ana "cd one-tv && ./cine && ./cine estado" | sed 's/^/    /'
paso $? "./cine y ./cine estado"

echo "== ./cine quitar-autoarranque"
como_ana "cd one-tv && ./cine quitar-autoarranque && ! systemctl --user is-active cine-roku.service && test ! -e ~/.config/systemd/user/cine-roku.service" >/dev/null
paso $? "servicio quitado y detenido"

[ "$fallas" = 0 ] && echo "Todo bien." || echo "$fallas cosa(s) fallaron."
exit $((fallas > 0))
