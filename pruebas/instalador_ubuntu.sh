#!/bin/bash
# El instalador de verdad (instalar.sh) en Ubuntu 24.04, en contenedores de Docker que se borran al terminar:
# 1. Un Ubuntu recién instalado, sin Python ni ffmpeg ni curl (solo wget y sudo), como un usuario normal: instala con
#    apt lo que falta, baja One TV y, como ahí no hay systemd, deja el servidor de fondo; /bienvenida responde y la
#    página principal manda ahí; otra vez el mismo comando pone al día sin perder config.json.
# 2. Un Ubuntu que arranca con systemd (como una computadora de verdad), entrando por SSH: deja el servicio de systemd
#    del usuario, con «linger» (arranca al encender la computadora); otra vez el mismo comando lo pone al día.
# One TV sale de este repositorio (lo confirmado y lo cambiado, como el .tar.gz de GitHub). No busca ninguna TV.
# Uso: pruebas/instalador_ubuntu.sh       (la imagen «one-tv-pruebas-systemd» queda: docker rmi one-tv-pruebas-systemd)
set -uo pipefail
DIR="$(cd "$(dirname "$0")/.." && pwd)"
PORT=8803
CASA="$(mktemp -d /tmp/one-tv-instalador-ubuntu.XXXXXX)"
NAME=one-tv-pruebas-instalador
fallas=0
paso() { if [ "$1" = 0 ]; then echo "  ✓ $2"; else echo "  ✗ $2"; fallas=$((fallas + 1)); fi; }
trap 'docker rm -f "$NAME" >/dev/null 2>&1; rm -rf "$CASA"' EXIT
ref="$(git -C "$DIR" stash create 2>/dev/null)"
git -C "$DIR" archive --format=tar.gz --prefix=one-tv-main/ -o "$CASA/one-tv.tar.gz" "${ref:-HEAD}" || exit 1
cp "$DIR/instalar.sh" "$CASA/instalar.sh"
REVISAR='
import json, sys, urllib.request
class Sin(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k): return None
abrir = urllib.request.build_opener(Sin()).open
def pedir(ruta):
    try:
        r = abrir("http://127.0.0.1:%s%s" % (sys.argv[1], ruta), timeout=10); return r.status, r.headers.get("Location"), r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Location"), ""
s, _, html = pedir("/bienvenida"); print("bienvenida", s, "One TV está listo" in html)
s, donde, _ = pedir("/"); print("principal", s, donde)
'

echo "== 1. Ubuntu recién instalado (sin Python, ffmpeg ni curl; sin systemd)"
docker rm -f "$NAME" >/dev/null 2>&1
docker run -d --name "$NAME" -v "$CASA":/casa:ro ubuntu:24.04 sleep 3600 >/dev/null || exit 1
docker exec "$NAME" bash -c 'apt-get update -q >/dev/null && DEBIAN_FRONTEND=noninteractive apt-get install -y -q \
  sudo wget ca-certificates >/dev/null && useradd -m -s /bin/bash ana && echo "ana ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/ana'
como_ana() { docker exec "$NAME" su - ana -c "$1"; }
como_ana "ONE_TV_FUENTE=/casa/one-tv.tar.gz ONE_TV_PUERTO=$PORT bash < /casa/instalar.sh" 2>&1 | tee "$CASA/salida1.txt" | sed 's/^/    /'
paso $? "el instalador terminó bien"
grep -q "Instalando python3 python3-venv ffmpeg con apt" "$CASA/salida1.txt"; paso $? "instaló con apt python3, python3-venv y ffmpeg"
grep -q "Te voy a pedir tu contraseña" "$CASA/salida1.txt"; paso $? "explicó para qué pide la contraseña"
grep -q "lo dejo corriendo de fondo" "$CASA/salida1.txt"; paso $? "sin systemd lo dice y lo deja de fondo"
grep -q "Desde el teléfono u otro aparato de la casa:  http://.*:$PORT/bienvenida" "$CASA/salida1.txt"
paso $? "dice la dirección para abrir desde otro aparato"
grep -q "no tiene pantalla" "$CASA/salida1.txt"; paso $? "sin pantalla, dice que se abra desde otro aparato"
revision="$(docker exec "$NAME" python3 -c "$REVISAR" "$PORT")"
echo "$revision" | sed 's/^/    /'
echo "$revision" | grep -q "^bienvenida 200 True$"; paso $? "/bienvenida responde"
echo "$revision" | grep -q "^principal 302 /bienvenida$"; paso $? "la página principal manda a /bienvenida"
como_ana "test -f ~/one-tv/cine && test -d ~/Videos/Biblioteca && grep -q '\"bienvenida_hecha\": false' ~/one-tv/config.json"
paso $? "One TV en ~/one-tv, la biblioteca en ~/Videos/Biblioteca y config.json sin preguntas"
como_ana "python3 - <<'EOF'
import json; p = '/home/ana/one-tv/config.json'; c = json.load(open(p)); c['roku_password'] = 'de-prueba'; json.dump(c, open(p, 'w'))
EOF"
como_ana "ONE_TV_FUENTE=/casa/one-tv.tar.gz bash < /casa/instalar.sh" > "$CASA/salida2.txt" 2>&1
paso $? "otra vez el mismo comando (poner al día)"
grep -q "Python y ffmpeg: uso los que ya tienes" "$CASA/salida2.txt" && ! grep -q "contraseña" "$CASA/salida2.txt"
paso $? "no volvió a instalar nada ni pidió la contraseña"
como_ana "grep -q de-prueba ~/one-tv/config.json"; paso $? "config.json se quedó"
docker exec "$NAME" python3 -c "$REVISAR" "$PORT" | grep -q "^bienvenida 200 True$"; paso $? "responde después de ponerlo al día"
docker rm -f "$NAME" >/dev/null 2>&1

echo "== 2. Ubuntu con systemd, por SSH (el servicio de verdad)"
IMG=one-tv-pruebas-systemd
docker build -q -t "$IMG" -f "$DIR/pruebas/ubuntu/Dockerfile.systemd" "$DIR/pruebas/ubuntu" >/dev/null || exit 1
docker run -d --name "$NAME" --privileged --cgroupns=host -v /sys/fs/cgroup:/sys/fs/cgroup:rw --tmpfs /run \
  --tmpfs /run/lock -v "$CASA":/casa:ro "$IMG" >/dev/null || exit 1
for _ in $(seq 1 90); do
  case "$(docker exec "$NAME" systemctl is-system-running 2>/dev/null)" in running|degraded) break ;; esac
  sleep 1
done
por_ssh() { docker exec "$NAME" ssh -o StrictHostKeyChecking=no -o LogLevel=ERROR ana@localhost "$@"; }
por_ssh "ONE_TV_FUENTE=/casa/one-tv.tar.gz ONE_TV_PUERTO=$PORT bash /casa/instalar.sh" 2>&1 | tee "$CASA/salida3.txt" | sed 's/^/    /'
paso $? "el instalador terminó bien"
grep -q "arranca solo con la computadora" "$CASA/salida3.txt"; paso $? "dice que arranca solo con la computadora"
por_ssh "systemctl --user is-enabled cine-roku.service && systemctl --user is-active cine-roku.service" >/dev/null
paso $? "servicio de systemd del usuario activado y corriendo"
docker exec "$NAME" test -e /var/lib/systemd/linger/ana; paso $? "linger activado (arranca sin iniciar sesión)"
docker exec "$NAME" python3 -c "$REVISAR" "$PORT" | grep -q "^principal 302 /bienvenida$"; paso $? "la página principal manda a /bienvenida"
docker exec "$NAME" python3 -c "
import json, urllib.request
r = urllib.request.Request('http://127.0.0.1:$PORT/api/bienvenida', data=b'{\"hecha\": true}', headers={'Content-Type': 'application/json'})
print(json.loads(urllib.request.urlopen(r, timeout=10).read()))" | grep -q "'ok': True"
paso $? "la bienvenida se termina desde el navegador (lo guarda el servicio)"
por_ssh "ONE_TV_FUENTE=/casa/one-tv.tar.gz bash /casa/instalar.sh" > "$CASA/salida4.txt" 2>&1
paso $? "otra vez el mismo comando (pone al día el servicio)"
grep -q "Ábrelo en el navegador:  http://localhost:$PORT\$" "$CASA/salida4.txt"; paso $? "ya no manda a la bienvenida"
por_ssh "grep -q '\"bienvenida_hecha\": true' ~/one-tv/config.json"; paso $? "lo guardado desde el navegador llegó a ~/one-tv/config.json"
docker exec "$NAME" python3 -c "$REVISAR" "$PORT" | grep -q "^principal 200 None$"; paso $? "la página principal abre directo"

[ "$fallas" = 0 ] && echo "Todo bien." || echo "$fallas cosa(s) fallaron."
exit $((fallas > 0))
