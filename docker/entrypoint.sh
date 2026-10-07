#!/bin/bash
# Arranque del contenedor de One TV: crea el usuario PUID/PGID (como piden las imágenes para NAS), le da su carpeta de
# datos y el acceso al chip de video (/dev/dri), y arranca el servidor sin ser «root». No usa systemd ni nada de la Mac.
set -e

PUID="${PUID:-1000}"
PGID="${PGID:-1000}"
DATOS="${ONE_TV_DATOS:-/datos}"
export HOME="$DATOS" ONE_TV_CONTENEDOR=1

SERVIDOR=(python3 /app/mac/cine.py servir)

if [ "$(id -u)" != "0" ]; then   # ya lo arrancaron como otro usuario (opción «user:» de compose): nada que preparar
  if ! mkdir -p "$DATOS" 2>/dev/null || ! [ -w "$DATOS" ]; then
    echo "✗ No puedo escribir en $DATOS. Dale permiso de escritura a ese usuario, o usa PUID y PGID." >&2
    exit 1
  fi
  exec "${SERVIDOR[@]}"
fi

mkdir -p "$DATOS"
if [ "$PUID" = "0" ]; then
  exec "${SERVIDOR[@]}"
fi

# Usuario y grupo con esos números (sin importar el nombre).
getent group "$PGID" >/dev/null || groupadd -g "$PGID" onetv
getent passwd "$PUID" >/dev/null || useradd -u "$PUID" -g "$PGID" -d "$DATOS" -M -s /usr/sbin/nologin onetv

# Acceso al chip de video: los grupos dueños de /dev/dri/* del NAS (render, video…), sea cual sea su número.
GRUPOS=""
for dev in /dev/dri/*; do
  [ -e "$dev" ] || continue
  gid="$(stat -c %g "$dev")"
  [ "$gid" = "0" ] && continue
  getent group "$gid" >/dev/null || groupadd -g "$gid" "gpu$gid"
  case ",$GRUPOS," in *",$gid,"*) ;; *) GRUPOS="${GRUPOS:+$GRUPOS,}$gid" ;; esac
done

# Que la carpeta de datos sea de ese usuario (solo se recorre entera si no lo era, para no tardar en cada arranque).
if [ "$(stat -c %u:%g "$DATOS")" != "$PUID:$PGID" ]; then
  chown -R "$PUID:$PGID" "$DATOS"
fi

if [ -z "$(ls -A /biblioteca 2>/dev/null)" ]; then
  echo "⚠ /biblioteca está vacía: monta ahí la carpeta de tus películas y series (ver docker-compose.yml)."
fi

if [ -n "$GRUPOS" ]; then
  exec setpriv --reuid="$PUID" --regid="$PGID" --groups="$GRUPOS" "${SERVIDOR[@]}"
fi
exec setpriv --reuid="$PUID" --regid="$PGID" --clear-groups "${SERVIDOR[@]}"
