#!/bin/bash
# Arranque del contenedor de One TV: crea el usuario PUID/PGID (como piden las imágenes para NAS), le da su carpeta de
# datos y el acceso al chip de video (/dev/dri), y arranca el servidor sin ser «root». No usa systemd ni nada de la Mac.
#
# Sin PUID ni PGID, usa el dueño de la carpeta de videos montada en /biblioteca (o de /musica): así lee tus archivos
# sin configurar nada. Si con ese usuario no puede leer una carpeta, prueba sumándole el grupo de la carpeta; si aun
# así no puede, lo dice en el registro con qué hacer (y la web también lo muestra).
#
# ONE_TV_COMPARTIDAS (lo pone el instalador para NAS, instalar.sh, y los docker-compose de docs/INSTALAR-DOCKER.md): las
# carpetas compartidas del NAS montadas de solo lectura en la misma ruta (por ejemplo «/volume1» o «/mnt/user:/mnt/disks»,
# separadas con «:»). Entonces no hace falta /biblioteca: las carpetas de videos y música se eligen en el asistente del
# navegador (/bienvenida), entre esas.
set -e

DATOS="${ONE_TV_DATOS:-/datos}"
export HOME="$DATOS" ONE_TV_CONTENEDOR=1
CARPETAS=(/biblioteca /musica)
COMPARTIDAS=()
IFS=: read -r -a COMPARTIDAS <<< "${ONE_TV_COMPARTIDAS:-}"

SERVIDOR=(python3 /app/mac/cine.py servir)

nombre_carpeta() {   # cómo se le dice a cada carpeta en el registro
  case "$1" in /biblioteca) echo "tu carpeta de videos" ;; /musica) echo "tu carpeta de música" ;; *) echo "$1" ;; esac
}

aviso_sin_permiso() {   # aviso_sin_permiso carpeta usuario
  echo "⚠ No puedo leer $1 ($(nombre_carpeta "$1")) con el usuario $2. Pon en PUID y PGID el usuario dueño de" \
       "$(nombre_carpeta "$1") (en el NAS, el comando «id» lo muestra), o dale permiso de lectura."
}

montada() {   # ¿hay algo montado ahí? (la imagen trae /biblioteca y /musica vacías y de «root»)
  [ -d "$1" ] && { [ "$(stat -c %u "$1")" != "0" ] || [ -n "$(ls -A "$1" 2>/dev/null)" ]; }
}

if [ "$(id -u)" != "0" ]; then   # ya lo arrancaron como otro usuario (opción «user:» de compose): nada que preparar
  if ! mkdir -p "$DATOS" 2>/dev/null || ! [ -w "$DATOS" ]; then
    echo "✗ No puedo escribir en $DATOS. Dale permiso de escritura a ese usuario, o usa PUID y PGID." >&2
    exit 1
  fi
  for c in "${CARPETAS[@]}" "${COMPARTIDAS[@]}"; do
    if [ -d "$c" ] && ! ls "$c" >/dev/null 2>&1; then aviso_sin_permiso "$c" "$(id -u):$(id -g)"; fi
  done
  exec "${SERVIDOR[@]}"
fi

if [ ${#COMPARTIDAS[@]} -gt 0 ]; then
  echo "· Carpetas del NAS que One TV puede leer (de solo lectura): ${ONE_TV_COMPARTIDAS//:/, }"
  for c in "${COMPARTIDAS[@]}"; do
    [ -d "$c" ] || echo "⚠ No encuentro $c dentro del contenedor: móntala de solo lectura (-v $c:$c:ro)."
  done
fi

# Quién lee las carpetas. Sin PUID ni PGID: el dueño de la carpeta de videos (o de la de música) montada; si es de
# «root», el usuario 1000 con el grupo de la carpeta. Con uno solo de los dos, el otro queda en 1000, como siempre.
ELEGIDO=""
if [ -z "${PUID:-}" ] && [ -z "${PGID:-}" ]; then
  for c in "${CARPETAS[@]}"; do
    montada "$c" || continue
    if [ "$(stat -c %u "$c")" != "0" ]; then
      PUID="$(stat -c %u "$c")"
      PGID="$(stat -c %g "$c")"
      ELEGIDO="el dueño de $c"
      break
    fi
    if [ -z "${PGID:-}" ] && [ "$(stat -c %g "$c")" != "0" ]; then
      PGID="$(stat -c %g "$c")"
    fi
  done
fi
PUID="${PUID:-1000}"
PGID="${PGID:-1000}"

mkdir -p "$DATOS"
if [ "$PUID" = "0" ]; then
  exec "${SERVIDOR[@]}"
fi

# Usuario y grupo con esos números (sin importar el nombre).
getent group "$PGID" >/dev/null || groupadd -g "$PGID" onetv
getent passwd "$PUID" >/dev/null || useradd -u "$PUID" -g "$PGID" -d "$DATOS" -M -s /usr/sbin/nologin onetv

GRUPOS=""
sumar_grupo() {   # sumar_grupo número: un grupo más para el usuario (si no es «root» ni el suyo, y sin repetir)
  [ "$1" = "0" ] || [ "$1" = "$PGID" ] && return 0
  getent group "$1" >/dev/null || groupadd -g "$1" "grupo$1"
  case ",$GRUPOS," in *",$1,"*) ;; *) GRUPOS="${GRUPOS:+$GRUPOS,}$1" ;; esac
}

como_usuario() {   # corre algo con el usuario, el grupo y los grupos de ahora
  if [ -n "$GRUPOS" ]; then
    setpriv --reuid="$PUID" --regid="$PGID" --groups="$GRUPOS" "$@"
  else
    setpriv --reuid="$PUID" --regid="$PGID" --clear-groups "$@"
  fi
}

# Acceso al chip de video: los grupos dueños de /dev/dri/* del NAS (render, video…), sea cual sea su número.
for dev in /dev/dri/*; do
  [ -e "$dev" ] || continue
  sumar_grupo "$(stat -c %g "$dev")"
done

# Que pueda leer tus carpetas: si no puede, prueba sumándole el grupo de la carpeta; si aun así no, lo dice.
for c in "${CARPETAS[@]}" "${COMPARTIDAS[@]}"; do
  [ -d "$c" ] || continue
  como_usuario ls "$c" >/dev/null 2>&1 && continue
  sumar_grupo "$(stat -c %g "$c")"
  como_usuario ls "$c" >/dev/null 2>&1 || aviso_sin_permiso "$c" "$PUID:$PGID"
done
if [ -n "$ELEGIDO" ]; then
  echo "· Uso el usuario $PUID:$PGID ($ELEGIDO). Para usar otro, pon PUID y PGID."
fi

# Que la carpeta de datos sea de ese usuario (solo se recorre entera si no lo era, para no tardar en cada arranque).
if [ "$(stat -c %u:%g "$DATOS")" != "$PUID:$PGID" ]; then
  chown -R "$PUID:$PGID" "$DATOS"
fi

if [ -z "$(ls -A /biblioteca 2>/dev/null)" ] && [ ${#COMPARTIDAS[@]} -eq 0 ]; then
  echo "⚠ /biblioteca está vacía: monta ahí la carpeta de tus películas y series (ver docker-compose.yml)."
fi

if [ -n "$GRUPOS" ]; then
  exec setpriv --reuid="$PUID" --regid="$PGID" --groups="$GRUPOS" "${SERVIDOR[@]}"
fi
exec setpriv --reuid="$PUID" --regid="$PGID" --clear-groups "${SERVIDOR[@]}"
