#!/bin/bash
# Instala (o pone al día) One TV con un solo comando, en una Mac, en Linux (Ubuntu, Debian y otros con apt) o en un NAS.
#
#   Mac:          curl -fsSL https://raw.githubusercontent.com/julai1433/one-tv/main/instalar.sh | bash
#   Linux o NAS:  wget -qO- https://raw.githubusercontent.com/julai1433/one-tv/main/instalar.sh | bash
#
# En un NAS (Synology, Unraid, TrueNAS SCALE, QNAP u OpenMediaVault) instala con Docker en vez de directo (ver «NAS con
# Docker», más abajo). En otro Linux también se puede pedir Docker:  … | bash -s -- --docker
#
# Qué hace (Mac y Linux):
# 1. Baja One TV (sin git) a la carpeta «One TV» de tu usuario (en Linux, «one-tv»). Si ya estaba, lo pone al día:
#    tu configuración (config.json), lo que ya viste y lo que se bajó para One TV se quedan.
# 2. Revisa que estén Python (3.9 o más nuevo) y ffmpeg (en la Mac, 7 o más nuevo) y usa los que ya tengas (por
#    ejemplo, los de Homebrew). En la Mac, si faltan, los baja solo para One TV, dentro de su carpeta («programas»),
#    sin tocar nada más ni pedir contraseña: Python de python-build-standalone y ffmpeg de martin-riedl.de, con la
#    versión y la suma de verificación (sha256) fijas aquí abajo; si lo que llega no coincide, no se instala. En
#    Linux los instala con apt (te pide tu contraseña y dice para qué).
# 3. Deja el servidor corriendo y arrancando solo con la computadora (lo mismo que «./cine autoarranque») y abre el
#    navegador en la bienvenida, que termina la configuración: http://localhost:8765/bienvenida.
#
# Qué hace en un NAS (o con --docker):
# 1. Revisa que esté Docker. En Unraid y TrueNAS SCALE ya viene (si está apagado, dice dónde prenderlo); en Synology y
#    QNAP se instala desde la tienda de apps del NAS (lo dice y pide volver a correr el comando); en OpenMediaVault y
#    otros Linux lo instala con el instalador oficial de Docker (get.docker.com), pidiendo la contraseña una vez.
# 2. Baja la imagen de One TV y crea el contenedor «one-tv»: red «host» (para encontrar la TV), arranque con el NAS,
#    el chip de video (/dev/dri) si lo hay, los datos en una carpeta clara del NAS (por ejemplo docker/one-tv) y TODAS
#    las carpetas compartidas montadas de solo lectura, en la misma ruta que en el NAS: así el asistente del navegador
#    deja elegir las de videos y música sin volver a crear el contenedor. Volver a correrlo lo pone al día.
# 3. Espera a que responda y dice la dirección para abrir el asistente desde otro aparato
#    (http://<ip-del-nas>:8765/bienvenida).
#
# Para probarlo sin tocar la computadora: ONE_TV_DIR (otra carpeta), ONE_TV_FUENTE (otro .tar.gz de One TV, una
# dirección o una carpeta), ONE_TV_SIN_AUTOARRANQUE=1 (sin servicio de arranque: el servidor queda de fondo),
# ONE_TV_PUERTO (otro puerto, si todavía no hay config.json), CINE_NO_BROWSER=1 (sin abrir el navegador) y
# ONE_TV_LUGARES="" (en la Mac, no buscar Python ni ffmpeg fuera del PATH: como una Mac sin Homebrew). Con Docker:
# ONE_TV_RAIZ (un sistema de archivos falso para reconocer el NAS), ONE_TV_IMAGEN (otra imagen), ONE_TV_IMAGEN_ARCHIVO
# (cargarla de un archivo de «docker save» en vez de bajarla), ONE_TV_DOCKER=1 (como --docker) y ONE_TV_DOCKER_OFICIAL
# (otro instalador de Docker).
# Con ONE_TV_SOLO_FUNCIONES=1 y «source instalar.sh» solo se cargan las funciones (pruebas/test_instalador.py).

REPO="julai1433/one-tv"
FUENTE="https://codeload.github.com/$REPO/tar.gz/refs/heads/main"

# En un NAS: la imagen de Docker que publica .github/workflows/imagen-docker.yml y el nombre del contenedor.
IMAGEN="${ONE_TV_IMAGEN:-ghcr.io/julai1433/one-tv:latest}"
CONTENEDOR=one-tv
RAIZ="${ONE_TV_RAIZ:-}"   # (pruebas: un sistema de archivos falso, para reconocer el NAS y sus carpetas)

# Python para la Mac (si no tiene uno que sirva): python-build-standalone, https://github.com/astral-sh/python-build-standalone
PY_BASE="https://github.com/astral-sh/python-build-standalone/releases/download"
PY_VERSION="3.12.15"
PY_FECHA="20261003"
PY_MB=25
PY_SHA_arm64="ad8d0c637c0a36b967b310e2c07254f4d2ca8cabaa7699e55ed6290aceb481a2"
PY_SHA_x86_64="562c30864ece2cb1d3e0ad66a1acd498611a47e5a10ce81b99158bef1ccbd355"

# ffmpeg para la Mac (si no tiene uno de la 7 en adelante): las versiones estáticas firmadas de
# https://ffmpeg.martin-riedl.de (con VideoToolbox, el chip de video de la Mac), una para cada chip.
FFMPEG_BASE="https://ffmpeg.martin-riedl.de/download/macos"
FFMPEG_VERSION="9.0.2"
FFMPEG_MINIMO=7
FFMPEG_MAC_MINIMO=12   # esas versiones piden macOS 12 (Monterey) o más nuevo
FFMPEG_MB_arm64=56
FFMPEG_MB_x86_64=67
FFMPEG_DIR_arm64="arm64/1789931890_9.0.2"
FFMPEG_DIR_x86_64="amd64/1789931006_9.0.2"
FFMPEG_SHA_arm64="c8ed4c4e6978a03c485edbfe4e0a5dc2380f8a30bba5150531b31b094492d924"
FFPROBE_SHA_arm64="fcbe839537485eaee7a7a8bc5cbc0f90d53617e80943e8a5b2e31cb851197ea6"
# Dónde más buscar Python y ffmpeg en la Mac, aunque no estén en el PATH: Homebrew (chip de Apple e Intel), MacPorts y
# el Python de python.org.
LUGARES_MAC="${ONE_TV_LUGARES-/opt/homebrew/bin /usr/local/bin /opt/local/bin /Library/Frameworks/Python.framework/Versions/Current/bin}"
FFMPEG_SHA_x86_64="7c6b4125b191cbf773832dc51f424cf2b6bb7da43007d1e066f95909e47cacd4"
FFPROBE_SHA_x86_64="2322438ed2f6319a691291b247d09c69dcaa3a982460d1f269a7e1af335cfdfd"

# ---------------------------------------------------------------- mensajes

paso() { printf '· %s\n' "$*"; }
ok() { printf '✓ %s\n' "$*"; }
aviso() { printf '⚠ %s\n' "$*"; }
falla() { printf '✗ %s\n' "$*" >&2; }

# ---------------------------------------------------------------- bajar y revisar

bajar() {   # bajar DIRECCIÓN ARCHIVO: con curl o, si no hay (Ubuntu con escritorio), con wget
  if command -v curl >/dev/null 2>&1; then
    curl -fL --retry 3 --connect-timeout 30 -sS -o "$2" "$1"
  elif command -v wget >/dev/null 2>&1; then
    wget -q --tries=3 -O "$2" "$1"
  else
    falla "Para bajar One TV hace falta «curl» o «wget», y esta computadora no tiene ninguno."
    return 1
  fi
}

suma() {   # la suma de verificación (sha256) de un archivo
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | cut -d ' ' -f 1
  else
    sha256sum "$1" | cut -d ' ' -f 1
  fi
}

verificar() {   # verificar ARCHIVO SUMA_ESPERADA NOMBRE: si no coincide, no se usa
  local tiene
  tiene="$(suma "$1" 2>/dev/null)"
  if [ -z "$2" ] || [ "$tiene" != "$2" ]; then
    falla "Lo que bajó de $3 no es lo que esperaba (su suma de verificación no coincide), así que no lo instalo."
    falla "  Puede ser una descarga cortada: vuelve a correr el instalador. Si se repite, avísanos en"
    falla "  https://github.com/$REPO/issues"
    return 1
  fi
}

# ---------------------------------------------------------------- qué computadora es

arquitectura() {   # arm64 (chip de Apple) o x86_64 (Intel), aunque esta Terminal corra con Rosetta
  local m
  m="$(uname -m)"
  if [ "$m" = x86_64 ] && [ "$(sysctl -n sysctl.proc_translated 2>/dev/null)" = 1 ]; then
    m=arm64
  fi
  echo "$m"
}

version_mac() {   # 14 para macOS 14.5
  local v
  v="$(sw_vers -productVersion 2>/dev/null)"
  echo "${v%%.*}"
}

# ---------------------------------------------------------------- Python

python_sirve() {   # python_sirve RUTA: ¿es Python 3.9 o más nuevo, con lo que hace falta para instalar yt-dlp aparte?
  [ -n "$1" ] && [ -x "$1" ] || return 1
  "$1" -c 'import sys, venv, ensurepip; sys.exit(sys.version_info < (3, 9))' >/dev/null 2>&1 </dev/null
}

xcode_listo() {   # /usr/bin/python3 de la Mac solo es Python de verdad con las herramientas de Xcode instaladas
  local d
  d="$(xcode-select -p 2>/dev/null)" && [ -x "$d/usr/bin/python3" ]
}

python_propio() { echo "$DEST/programas/python/bin/python3"; }
python_propio_al_dia() { [ "$(cat "$DEST/programas/python/.version-one-tv" 2>/dev/null)" = "$PY_VERSION+$PY_FECHA" ]; }

buscar_python_mac() {   # la ruta del Python que sirve (primero el de One TV, luego el de la Mac), o nada
  local c lugar candidatos=("$(python_propio)" "$(command -v python3 2>/dev/null)")
  for lugar in $LUGARES_MAC; do candidatos+=("$lugar/python3"); done
  for c in "${candidatos[@]}"; do
    [ -n "$c" ] || continue
    if [ "$c" = /usr/bin/python3 ] && ! xcode_listo; then
      continue   # sin las herramientas de Xcode, usarlo abriría su instalador: como si no estuviera
    fi
    if python_sirve "$c"; then
      echo "$c"
      return 0
    fi
  done
  return 1
}

python_para() {   # python_para ARQUITECTURA: «dirección suma» del Python de One TV para esa Mac
  local arq="$1" nombre sha
  case "$arq" in
    arm64) nombre=aarch64; sha="$PY_SHA_arm64" ;;
    x86_64) nombre=x86_64; sha="$PY_SHA_x86_64" ;;
    *) return 1 ;;
  esac
  echo "$PY_BASE/$PY_FECHA/cpython-$PY_VERSION%2B$PY_FECHA-$nombre-apple-darwin-install_only_stripped.tar.gz $sha"
}

instalar_python_mac() {   # instalar_python_mac ARQUITECTURA: lo baja, lo revisa y lo deja en programas/python
  local datos url sha
  datos="$(python_para "$1")" || { falla "No hay Python para este tipo de Mac ($1)."; return 1; }
  url="${datos% *}"
  sha="${datos##* }"
  paso "Bajando Python $PY_VERSION para One TV (unos $PY_MB MB; solo para One TV, no cambia nada más de la Mac)…"
  bajar "$url" "$TMP/python.tar.gz" || { falla "No pude bajar Python. ¿Hay internet? Vuelve a correr el instalador."; return 1; }
  verificar "$TMP/python.tar.gz" "$sha" "Python" || return 1
  rm -rf "$TMP/python" && mkdir -p "$TMP/python" &&
    tar -xzf "$TMP/python.tar.gz" -C "$TMP/python" || { falla "No pude abrir lo que bajó de Python."; return 1; }
  if ! python_sirve "$TMP/python/python/bin/python3"; then
    falla "El Python que bajó no arranca en esta Mac."
    return 1
  fi
  mkdir -p "$DEST/programas" && rm -rf "$DEST/programas/python" &&
    mv "$TMP/python/python" "$DEST/programas/python" &&
    echo "$PY_VERSION+$PY_FECHA" > "$DEST/programas/python/.version-one-tv" || { falla "No pude guardar Python en $DEST/programas."; return 1; }
  ok "Python $PY_VERSION listo (en $DEST/programas/python)"
}

# ---------------------------------------------------------------- ffmpeg

version_ffmpeg() {   # el número grande de la versión de ese ffmpeg (9 para la 9.0.2), 99 si es de desarrollo, o nada
  local v
  v="$("$1" -version 2>/dev/null </dev/null | head -n 1)"
  case "$v" in
    "ffmpeg version N-"* | "ffmpeg version git-"*) echo 99 ;;
    "ffmpeg version "*)
      v="${v#ffmpeg version }"
      v="${v#n}"
      v="${v%%[!0-9]*}"
      [ -n "$v" ] && echo "$v"
      ;;
  esac
}

ffmpeg_sirve() {   # ffmpeg_sirve RUTA: ffmpeg de la 7 en adelante, con su ffprobe al lado
  local m
  [ -n "$1" ] && [ -x "$1" ] && [ -x "$(dirname "$1")/ffprobe" ] || return 1
  m="$(version_ffmpeg "$1")"
  [ -n "$m" ] && [ "$m" -ge "$FFMPEG_MINIMO" ]
}

ffmpeg_propio_al_dia() { [ "$(cat "$DEST/programas/bin/.ffmpeg-one-tv" 2>/dev/null)" = "$FFMPEG_VERSION" ]; }

buscar_ffmpeg_mac() {   # la ruta del ffmpeg que sirve (primero el de One TV, luego el de la Mac), o nada
  local c lugar candidatos=("$DEST/programas/bin/ffmpeg" "$(command -v ffmpeg 2>/dev/null)")
  for lugar in $LUGARES_MAC; do candidatos+=("$lugar/ffmpeg"); done
  for c in "${candidatos[@]}"; do
    [ -n "$c" ] || continue
    if ffmpeg_sirve "$c"; then
      echo "$c"
      return 0
    fi
  done
  return 1
}

ffmpeg_para() {   # ffmpeg_para ARQUITECTURA: «dirección-ffmpeg suma dirección-ffprobe suma» para esa Mac
  local dir sha_ffmpeg sha_ffprobe
  case "$1" in
    arm64) dir="$FFMPEG_DIR_arm64"; sha_ffmpeg="$FFMPEG_SHA_arm64"; sha_ffprobe="$FFPROBE_SHA_arm64" ;;
    x86_64) dir="$FFMPEG_DIR_x86_64"; sha_ffmpeg="$FFMPEG_SHA_x86_64"; sha_ffprobe="$FFPROBE_SHA_x86_64" ;;
    *) return 1 ;;
  esac
  echo "$FFMPEG_BASE/$dir/ffmpeg.zip $sha_ffmpeg $FFMPEG_BASE/$dir/ffprobe.zip $sha_ffprobe"
}

instalar_ffmpeg_mac() {   # instalar_ffmpeg_mac ARQUITECTURA: ffmpeg y ffprobe en programas/bin
  local datos programa url sha mb
  datos="$(ffmpeg_para "$1")" || { falla "No hay ffmpeg para este tipo de Mac ($1)."; return 1; }
  if [ "$(version_mac)" -lt "$FFMPEG_MAC_MINIMO" ] 2>/dev/null; then
    falla "El ffmpeg que trae One TV pide macOS $FFMPEG_MAC_MINIMO (Monterey) o más nuevo, y esta Mac tiene macOS $(sw_vers -productVersion)."
    falla "  Instala ffmpeg con Homebrew (https://brew.sh:  brew install ffmpeg) y vuelve a correr el instalador."
    return 1
  fi
  eval "mb=\$FFMPEG_MB_$1"
  paso "Bajando ffmpeg $FFMPEG_VERSION para One TV (unos $mb MB; prepara los videos para la TV)…"
  rm -rf "$TMP/ffmpeg" && mkdir -p "$TMP/ffmpeg"
  set -- $datos
  for programa in ffmpeg ffprobe; do
    url="$1"
    sha="$2"
    shift 2
    bajar "$url" "$TMP/$programa.zip" || { falla "No pude bajar $programa. ¿Hay internet? Vuelve a correr el instalador."; return 1; }
    verificar "$TMP/$programa.zip" "$sha" "$programa" || return 1
    unzip -o -q "$TMP/$programa.zip" -d "$TMP/ffmpeg" && [ -f "$TMP/ffmpeg/$programa" ] ||
      { falla "No pude abrir lo que bajó de $programa."; return 1; }
    chmod +x "$TMP/ffmpeg/$programa"
  done
  if ! ffmpeg_sirve "$TMP/ffmpeg/ffmpeg"; then
    falla "El ffmpeg que bajó no arranca en esta Mac."
    return 1
  fi
  mkdir -p "$DEST/programas/bin" &&
    mv -f "$TMP/ffmpeg/ffmpeg" "$TMP/ffmpeg/ffprobe" "$DEST/programas/bin/" &&
    echo "$FFMPEG_VERSION" > "$DEST/programas/bin/.ffmpeg-one-tv" || { falla "No pude guardar ffmpeg en $DEST/programas."; return 1; }
  ok "ffmpeg $FFMPEG_VERSION listo (en $DEST/programas/bin)"
}

enlazar_ffmpeg() {   # un ffmpeg de un lugar que el servidor de fondo no mira (MacPorts…): se enlaza en programas/bin
  local dir
  dir="$(dirname "$1")"
  case "$dir" in
    "$DEST/programas/bin" | /opt/homebrew/bin | /usr/local/bin | /usr/bin | /bin) return 0 ;;
  esac
  mkdir -p "$DEST/programas/bin" && ln -sf "$1" "$DEST/programas/bin/ffmpeg" && ln -sf "$dir/ffprobe" "$DEST/programas/bin/ffprobe"
}

# ---------------------------------------------------------------- One TV

carpeta_de_one_tv() {   # ¿esa carpeta es de One TV (o está vacía, o no existe)? Para nunca pisar algo tuyo.
  [ ! -e "$1" ] && return 0
  [ -d "$1" ] || return 1
  [ -f "$1/cine" ] && [ -d "$1/mac" ] && return 0
  [ -z "$(ls -A "$1" 2>/dev/null)" ]
}

bajar_one_tv() {   # baja One TV y lo pone en $DEST; lo que no viene en el proyecto (config.json, programas) se queda
  local fuente="${ONE_TV_FUENTE:-$FUENTE}" origen nombre
  if [ -d "$DEST/.git" ]; then   # una copia hecha con git (la guía de antes): se pone al día con git
    paso "$DEST es una copia hecha con git: la pongo al día con «git pull»."
    if command -v git >/dev/null 2>&1 && git -C "$DEST" pull --ff-only -q </dev/null; then
      ok "One TV al día"
    else
      aviso "No pude ponerla al día con git (¿cambios tuyos sin guardar?). Sigo con lo que hay."
    fi
    return 0
  fi
  if ! carpeta_de_one_tv "$DEST"; then
    falla "Ya existe la carpeta $DEST y no es de One TV. Para no tocar lo tuyo, no sigo:"
    falla "  cámbiale el nombre (o bórrala si no la usas) y vuelve a correr el instalador."
    return 1
  fi
  if [ -e "$DEST/cine" ]; then paso "Poniendo al día One TV…"; else paso "Bajando One TV…"; fi
  rm -rf "$TMP/one-tv" && mkdir -p "$TMP/one-tv"
  if [ -d "$fuente" ]; then   # (pruebas: una carpeta con el proyecto)
    (cd "$fuente" && tar --exclude=.git --exclude=config.json --exclude=programas -cf - .) | tar -xf - -C "$TMP/one-tv" ||
      { falla "No pude copiar One TV desde $fuente."; return 1; }
    origen="$TMP/one-tv"
  else
    if [ -f "$fuente" ]; then
      cp "$fuente" "$TMP/one-tv.tar.gz"
    else
      bajar "$fuente" "$TMP/one-tv.tar.gz"
    fi || { falla "No pude bajar One TV. ¿Hay internet? Vuelve a correr el instalador."; return 1; }
    tar -xzf "$TMP/one-tv.tar.gz" -C "$TMP/one-tv" || { falla "No pude abrir lo que bajó de One TV."; return 1; }
    origen="$(find "$TMP/one-tv" -mindepth 1 -maxdepth 1 -type d | head -n 1)"   # one-tv-main/
  fi
  if [ ! -f "$origen/cine" ] || [ ! -f "$origen/mac/cine.py" ]; then
    falla "Lo que bajó no parece One TV. Vuelve a correr el instalador."
    return 1
  fi
  mkdir -p "$DEST" || { falla "No pude crear la carpeta $DEST."; return 1; }
  # Se cambia cada cosa del proyecto por la nueva (así se va lo que se borró dentro de mac/, roku/…); lo que no viene
  # en el proyecto (config.json, programas/) no se toca.
  local ruta
  for ruta in "$origen"/* "$origen"/.[!.]*; do   # (también lo que empieza con punto; los nombres pueden tener espacios)
    [ -e "$ruta" ] || continue
    nombre="${ruta##*/}"
    case "$nombre" in config.json | programas) continue ;; esac
    rm -rf "${DEST:?}/$nombre" && mv "$ruta" "$DEST/$nombre" ||
      { falla "No pude copiar $nombre a $DEST."; return 1; }
  done
  chmod +x "$DEST/cine" 2>/dev/null
  ok "One TV en $DEST"
}

# ---------------------------------------------------------------- cada sistema

programas_mac() {   # deja PY y FFMPEG listos (los de la Mac si sirven; si no, los de One TV)
  local arq
  arq="$(arquitectura)"
  PY="$(buscar_python_mac)"
  if [ -z "$PY" ] || { [ "$PY" = "$(python_propio)" ] && ! python_propio_al_dia; }; then
    instalar_python_mac "$arq" || return 1
    PY="$(python_propio)"
  else
    ok "Python: uso el que ya tienes ($PY)"
  fi
  FFMPEG="$(buscar_ffmpeg_mac)"
  if [ -z "$FFMPEG" ] || { [ "$FFMPEG" = "$DEST/programas/bin/ffmpeg" ] && [ ! -L "$FFMPEG" ] && ! ffmpeg_propio_al_dia; }; then
    instalar_ffmpeg_mac "$arq" || return 1
    FFMPEG="$DEST/programas/bin/ffmpeg"
  else
    ok "ffmpeg: uso el que ya tienes ($FFMPEG)"
    enlazar_ffmpeg "$FFMPEG"
  fi
}

con_permiso() {   # con_permiso COMANDO…: como administrador (sudo), o tal cual si ya lo eres
  if [ "$(id -u)" = 0 ]; then "$@"; else sudo "$@"; fi
}

programas_linux() {   # instala con apt lo que falte (Python, su «venv» y ffmpeg) y deja «linger» de systemd
  local falta=() para=() linger=""
  if ! command -v python3 >/dev/null 2>&1; then
    falta+=(python3 python3-venv)
  elif ! python_sirve "$(command -v python3)"; then
    falta+=(python3-venv)   # sin esto no se puede instalar yt-dlp (YouTube) en su entorno aparte
  fi
  if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
    falta+=(ffmpeg)
  fi
  # Que arranque al encender la computadora aunque nadie inicie sesión (un servidor): «linger» de systemd.
  if [ -z "${ONE_TV_SIN_AUTOARRANQUE:-}" ] && [ -d /run/systemd/system ] && command -v loginctl >/dev/null 2>&1 &&
      [ "$(id -u)" != 0 ] && [ ! -e "/var/lib/systemd/linger/$(id -un)" ]; then
    linger=1
    # En un escritorio, cada quien puede activarlo para sí sin contraseña: primero así. Si no se puede, con sudo (y,
    # si tampoco hay sudo, lo vuelve a intentar ./cine, que dice el comando si no pudo).
    if loginctl enable-linger --no-ask-password "$(id -un)" </dev/null >/dev/null 2>&1 &&
        [ -e "/var/lib/systemd/linger/$(id -un)" ]; then
      linger=""
    elif ! command -v sudo >/dev/null 2>&1; then
      linger=""
    fi
  fi
  [ ${#falta[@]} -gt 0 ] && para+=("instalar ${falta[*]} (los programas que One TV necesita)")
  [ -n "$linger" ] && para+=("que One TV arranque al encender la computadora, aunque nadie inicie sesión")
  if [ ${#falta[@]} -gt 0 ] && ! command -v apt-get >/dev/null 2>&1; then
    falla "Faltan programas que One TV necesita: ${falta[*]}."
    falla "  Instálalos con el instalador de programas de tu sistema y vuelve a correr este comando."
    return 1
  fi
  if [ ${#para[@]} -gt 0 ] && [ "$(id -u)" != 0 ]; then
    local p permiso=1
    if command -v sudo >/dev/null 2>&1; then
      paso "Te voy a pedir tu contraseña (la de tu usuario de esta computadora) una sola vez, solo para:"
      for p in "${para[@]}"; do printf '    - %s\n' "$p"; done
      sudo -v || permiso=""
    else
      permiso=""
    fi
    if [ -z "$permiso" ] && [ ${#falta[@]} -gt 0 ]; then
      falla "Sin permiso de administrador no puedo instalar ${falta[*]}. Vuelve a correr el instalador cuando quieras,"
      falla "  o instálalos a mano: sudo apt update && sudo apt install -y ${falta[*]}"
      return 1
    fi
    if [ -z "$permiso" ]; then
      linger=""   # (lo vuelve a intentar ./cine y, si no puede, dice el comando)
    fi
  fi
  if [ ${#falta[@]} -gt 0 ]; then
    paso "Instalando ${falta[*]} con apt (puede tardar unos minutos)…"
    con_permiso env DEBIAN_FRONTEND=noninteractive apt-get update -q </dev/null >/dev/null &&
      con_permiso env DEBIAN_FRONTEND=noninteractive apt-get install -y -q "${falta[@]}" </dev/null >/dev/null ||
      { falla "apt no pudo instalar ${falta[*]}. Prueba a mano: sudo apt update && sudo apt install -y ${falta[*]}"; return 1; }
    ok "Instalado: ${falta[*]}"
  else
    ok "Python y ffmpeg: uso los que ya tienes"
  fi
  if [ -n "$linger" ]; then
    con_permiso loginctl enable-linger "$(id -un)" </dev/null && ok "Arrancará al encender la computadora" ||
      aviso "No pude dejarlo arrancando al encender la computadora (sí cuando inicies sesión)."
  fi
  PY="$(command -v python3)"
  if ! python_sirve "$PY"; then
    falla "One TV necesita Python 3.9 o más nuevo (tienes $("$PY" --version 2>&1))."
    return 1
  fi
}

# ---------------------------------------------------------------- NAS con Docker

que_nas() {   # synology, unraid, qnap, truenas u omv (OpenMediaVault); nada si no es un NAS conocido
  if [ -e "$RAIZ/etc/synoinfo.conf" ]; then
    echo synology
  elif [ -e "$RAIZ/etc/unraid-version" ]; then
    echo unraid
  elif [ -e "$RAIZ/etc/config/qpkg.conf" ]; then
    echo qnap
  elif [ -x "$RAIZ/usr/bin/midclt" ] || [ -d "$RAIZ/usr/lib/python3/dist-packages/middlewared" ] ||
      grep -qis truenas "$RAIZ/etc/version" "$RAIZ/etc/os-release" 2>/dev/null; then
    echo truenas
  elif [ -d "$RAIZ/etc/openmediavault" ]; then
    echo omv
  fi
}

nombre_equipo() {   # cómo se le dice al equipo en los mensajes
  case "$1" in
    synology) echo "tu Synology" ;;
    unraid) echo "tu Unraid" ;;
    qnap) echo "tu QNAP" ;;
    truenas) echo "tu TrueNAS" ;;
    omv) echo "tu OpenMediaVault" ;;
    *) echo "este equipo" ;;
  esac
}

sin_raiz() { echo "${1#"$RAIZ"}"; }

carpetas_nas() {   # las carpetas compartidas del NAS (una por línea), tal como se ven en el NAS
  local d
  case "$1" in
    synology)   # cada volumen (/volume1, /volume2…) y los discos USB (/volumeUSB1)
      for d in "$RAIZ"/volume[0-9]* "$RAIZ"/volumeUSB[0-9]*; do [ -d "$d" ] && sin_raiz "$d"; done ;;
    unraid)     # las carpetas compartidas y los discos de «Unassigned Devices»
      for d in /mnt/user /mnt/disks /mnt/remotes; do [ -d "$RAIZ$d" ] && echo "$d"; done ;;
    qnap)       # /share tiene cada carpeta compartida (y los discos USB, en /share/external)
      [ -d "$RAIZ/share" ] && echo /share ;;
    truenas)    # cada «pool» (/mnt/tanque…); /mnt/.ix-apps, de las apps, no
      for d in "$RAIZ"/mnt/*; do [ -d "$d" ] && sin_raiz "$d"; done ;;
    omv)        # cada disco (/srv/dev-disk-by-…, /srv/mergerfs/…); /srv/salt y /srv/pillar son del sistema
      for d in "$RAIZ"/srv/*; do
        case "${d##*/}" in salt | pillar) continue ;; esac
        [ -d "$d" ] && sin_raiz "$d"
      done ;;
    *)          # otro Linux: donde suelen estar los discos y las carpetas de cada quien
      for d in /home /mnt /media /srv; do [ -d "$RAIZ$d" ] && [ -n "$(ls -A "$RAIZ$d" 2>/dev/null)" ] && echo "$d"; done ;;
  esac
}

casa_real() {   # la carpeta de tu usuario, aunque el comando corra con sudo
  local casa=""
  if [ "$(id -u)" = 0 ] && [ -n "${SUDO_USER:-}" ]; then
    casa="$(awk -F: -v u="$SUDO_USER" '$1 == u { print $6 }' /etc/passwd 2>/dev/null)"
  fi
  echo "${casa:-$HOME}"
}

datos_nas() {   # dónde guarda One TV sus datos en el NAS (una carpeta clara, junto a las de otras apps de Docker)
  local d primera
  case "$1" in
    synology)   # la carpeta compartida «docker» que crea Container Manager
      for d in $(carpetas_nas synology); do [ -d "$RAIZ$d/docker" ] && { echo "$d/docker/one-tv"; return; }; done
      primera="$(carpetas_nas synology | head -n 1)"
      echo "${primera:-/volume1}/docker/one-tv" ;;
    unraid) echo /mnt/user/appdata/one-tv ;;
    qnap)       # la carpeta compartida «Container» que crea Container Station
      if [ -d "$RAIZ/share/Container" ]; then
        echo /share/Container/one-tv
      else
        primera="$(cd "$RAIZ/share" 2>/dev/null && ls -d CACHEDEV*_DATA 2>/dev/null | head -n 1)"
        echo "/share/${primera:-CACHEDEV1_DATA}/docker/one-tv"
      fi ;;
    truenas | omv)
      primera="$(carpetas_nas "$1" | head -n 1)"
      if [ -n "$primera" ]; then echo "$primera/docker/one-tv"; else echo "$(casa_real)/docker/one-tv"; fi ;;
    *) echo "$(casa_real)/docker/one-tv" ;;
  esac
}

zona_horaria() {   # la zona horaria del equipo (America/Mexico_City), para la hora del registro; nada si no se sabe
  local z
  z="$(readlink "$RAIZ/etc/localtime" 2>/dev/null)"
  case "$z" in */zoneinfo/?*) echo "${z#*/zoneinfo/}"; return ;; esac
  z="$(head -n 1 "$RAIZ/etc/timezone" 2>/dev/null)"
  case "$z" in ?*/?*) echo "$z"; return ;; esac
  if [ -z "$RAIZ" ] && command -v timedatectl >/dev/null 2>&1; then
    z="$(timedatectl show -p Timezone --value 2>/dev/null)"
    case "$z" in ?*/?*) echo "$z" ;; esac
  fi
}

ip_de_la_red() {   # la dirección del equipo en la red de la casa (192.168.1.20), para abrir One TV desde otro aparato
  local ip
  ip="$(ip -4 route get 1.1.1.1 2>/dev/null | sed -n 's/.* src \([0-9.]*\).*/\1/p' | head -n 1)"
  [ -n "$ip" ] || ip="$(hostname -I 2>/dev/null | awk '{ print $1 }')"
  [ -n "$ip" ] || ip="$(ifconfig 2>/dev/null | sed -n 's/.*inet \(addr:\)\{0,1\}\([0-9.]*\).*/\2/p' | grep -v '^127\.' | head -n 1)"
  echo "${ip:-IP-DEL-NAS}"
}

pedir_permiso() {   # pedir_permiso PARA_QUÉ: la contraseña una sola vez (si no eres ya administrador)
  [ "$(id -u)" = 0 ] && return 0
  command -v sudo >/dev/null 2>&1 || return 1
  if ! sudo -n true 2>/dev/null; then
    paso "Te voy a pedir tu contraseña (la de tu usuario de $EQUIPO) una sola vez, $1."
    sudo -v || return 1
  fi
  if [ -z "${PERMISO_PID:-}" ]; then   # que no la vuelva a pedir a la mitad (bajar One TV puede tardar)
    (while sudo -n true 2>/dev/null && kill -0 "$$" 2>/dev/null; do sleep 50; done) >/dev/null 2>&1 &
    PERMISO_PID=$!
  fi
}

buscar_docker() {   # la ruta del programa docker (también donde lo dejan Synology y QNAP), o nada
  local c
  for c in "$(command -v docker 2>/dev/null)" "$RAIZ/usr/local/bin/docker" "$RAIZ/usr/bin/docker" \
      "$RAIZ/var/packages/ContainerManager/target/usr/bin/docker" "$RAIZ/var/packages/Docker/target/usr/bin/docker" \
      "$RAIZ"/share/*/.qpkg/container-station/bin/docker; do
    if [ -n "$c" ] && [ -x "$c" ] && [ ! -d "$c" ]; then
      case "$c" in "${ONE_TV_SOLO_DOCKER_EN:-}"*) ;; *) continue ;; esac   # en las pruebas: solo el Docker de mentira
      echo "$c"
      return 0
    fi
  done
  return 1
}

preparar_docker() {   # deja en DOCKER cómo llamar a Docker (con sudo si hace falta). 0 listo, 2 no está, 3 no responde,
  local d             # 4 sin permiso
  d="$(buscar_docker)" || return 2
  if "$d" info >/dev/null 2>&1 </dev/null; then
    DOCKER=("$d")
    return 0
  fi
  [ "$(id -u)" = 0 ] && return 3
  pedir_permiso "para que Docker pueda crear el contenedor de One TV" || return 4
  if sudo "$d" info >/dev/null 2>&1 </dev/null; then
    DOCKER=(sudo "$d")
    return 0
  fi
  return 3
}

arrancar_docker() {   # que Docker arranque ahora y al encender el equipo (en un Linux común)
  if [ -d "$RAIZ/run/systemd/system" ] && command -v systemctl >/dev/null 2>&1; then
    con_permiso systemctl enable --now docker </dev/null >/dev/null 2>&1
  elif command -v service >/dev/null 2>&1; then
    con_permiso service docker start </dev/null >/dev/null 2>&1
  fi
}

instalar_docker() {   # en OpenMediaVault y otros Linux: con el instalador oficial de Docker (get.docker.com)
  paso "Falta Docker, el programa con el que One TV corre en $EQUIPO. Lo instalo con el instalador oficial de Docker."
  if ! pedir_permiso "para instalar Docker"; then
    falla "Sin permiso de administrador no puedo instalar Docker. Vuelve a correr este comando cuando quieras."
    return 1
  fi
  bajar "${ONE_TV_DOCKER_OFICIAL:-https://get.docker.com}" "$TMP/instalar-docker.sh" ||
    { falla "No pude bajar el instalador de Docker. ¿Hay internet? Vuelve a correr este comando."; return 1; }
  paso "Instalando Docker (tarda unos minutos)…"
  if ! con_permiso sh "$TMP/instalar-docker.sh" </dev/null >"$TMP/docker.txt" 2>&1; then
    falla "No pude instalar Docker. Lo último que dijo su instalador:"
    tail -n 5 "$TMP/docker.txt" | sed 's/^/    /' >&2
    falla "  Instálalo a mano (https://docs.docker.com/engine/install/) y vuelve a correr este comando."
    return 1
  fi
  arrancar_docker
  ok "Docker instalado"
}

docker_falta() {   # docker_falta NAS ESTADO: qué hacer cuando Docker no está (2) o no responde (3) y no se instala desde aquí
  case "$1:$2" in
    synology:2)
      falla "Falta Docker. En tu Synology, abre el «Centro de paquetes», busca «Container Manager» e instálalo." ;;
    synology:*)
      falla "Docker no responde. Abre «Container Manager» en tu Synology (si está detenido, inícialo en el «Centro de paquetes»)." ;;
    qnap:2)
      falla "Falta Docker. En tu QNAP, abre el «App Center», busca «Container Station», instálala y ábrela una vez." ;;
    qnap:*)
      falla "Docker no responde. Abre «Container Station» en tu QNAP (la primera vez termina de prepararse)." ;;
    unraid:*)
      falla "Docker está apagado. En Unraid: Settings (Configuración) → Docker → «Enable Docker»: Yes → Apply." ;;
    truenas:*)
      falla "Docker todavía no está listo. En TrueNAS: Apps → Configuration → Choose Pool, y elige dónde guardar las apps"
      falla "  (pide TrueNAS SCALE 24.10 o más nuevo)." ;;
    *)
      falla "Docker está instalado pero no responde. Reinicia el equipo y vuelve a correr este comando."
      return ;;
  esac
  falla "  Luego vuelve a correr este mismo comando."
}

GUARDAR_VARIABLES="ROKU_PASSWORD ROKU_IP NOMBRE PUERTO CODIFICADOR TZ"

contenedor_de_antes() {   # «nuestro» (lo creó este instalador), «ajeno» (otro: un proyecto de Container Manager…) o nada
  "${DOCKER[@]}" container inspect "$CONTENEDOR" >/dev/null 2>&1 </dev/null || return 0
  if [ "$("${DOCKER[@]}" container inspect -f '{{index .Config.Labels "one-tv.instalador"}}' "$CONTENEDOR" \
      2>/dev/null </dev/null)" = 1 ]; then
    echo nuestro
  else
    echo ajeno
  fi
}

variables_de_antes() {   # lo que se le puso al contenedor de antes y vale la pena conservar (ROKU_PASSWORD=…, uno por línea)
  local linea v
  "${DOCKER[@]}" container inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$CONTENEDOR" 2>/dev/null </dev/null |
    while IFS= read -r linea; do
      for v in $GUARDAR_VARIABLES; do
        case "$linea" in "$v="?*) echo "$linea" ;; esac
      done
    done
}

armar_docker() {   # armar_docker DATOS COMPARTIDA…: deja en ARGS_DOCKER lo que va después de «docker» para crear el
  local datos="$1" c v lista="" tz puestas=" PUID PGID ONE_TV_COMPARTIDAS "   # contenedor (VARIABLES_DE_ANTES: las de antes)
  shift
  for c in "$@"; do lista="${lista:+$lista:}$c"; done
  # PUID=0: One TV lee como administrador, para poder abrir cualquier carpeta compartida que elijas (Synology y TrueNAS
  # las cuidan con permisos propios); las carpetas van de solo lectura (:ro), así que no puede cambiar ni borrar nada.
  ARGS_DOCKER=(run -d --name "$CONTENEDOR" --label one-tv.instalador=1 --network host --restart unless-stopped
    -e PUID=0 -e PGID=0 -e "ONE_TV_COMPARTIDAS=$lista")
  tz="$(zona_horaria)"
  if [ -n "$tz" ]; then ARGS_DOCKER+=(-e "TZ=$tz"); puestas="$puestas TZ "; fi
  if [ -n "${ONE_TV_PUERTO:-}" ]; then ARGS_DOCKER+=(-e "PUERTO=$ONE_TV_PUERTO"); puestas="$puestas PUERTO "; fi
  while IFS= read -r v; do
    [ -n "$v" ] || continue
    case "$puestas" in *" ${v%%=*} "*) continue ;; esac
    ARGS_DOCKER+=(-e "$v")
  done <<EOF
${VARIABLES_DE_ANTES:-}
EOF
  ARGS_DOCKER+=(-v "$datos:/datos")
  for c in "$@"; do ARGS_DOCKER+=(-v "$c:$c:ro"); done
  [ -e "$RAIZ/dev/dri" ] && ARGS_DOCKER+=(--device /dev/dri:/dev/dri)   # el chip de video, si lo hay
  ARGS_DOCKER+=("$IMAGEN")
}

bajar_imagen() {
  paso "Bajando One TV (la primera vez tarda unos minutos)…"
  if [ -n "${ONE_TV_IMAGEN_ARCHIVO:-}" ]; then   # (pruebas: la imagen recién construida, en un archivo de «docker save»)
    "${DOCKER[@]}" load -q -i "$ONE_TV_IMAGEN_ARCHIVO" </dev/null >/dev/null 2>"$TMP/imagen.txt" && ok "One TV al día" ||
      { falla "No pude cargar $ONE_TV_IMAGEN_ARCHIVO."; return 1; }
  elif "${DOCKER[@]}" pull -q "$IMAGEN" </dev/null >/dev/null 2>"$TMP/imagen.txt"; then
    ok "One TV al día"
  elif "${DOCKER[@]}" image inspect "$IMAGEN" >/dev/null 2>&1 </dev/null; then
    aviso "No pude bajar la versión nueva de One TV (¿hay internet?): sigo con la que ya tenías."
  else
    falla "No pude bajar One TV. ¿Hay internet? Vuelve a correr este comando."
    head -n 3 "$TMP/imagen.txt" | sed 's/^/    /' >&2
    return 1
  fi
}

preparar_datos() {   # preparar_datos CARPETA: la crea y, la primera vez, deja pendiente el asistente del navegador
  local config='{
  "bienvenida_hecha": false
}'
  if [ ! -d "$RAIZ$1" ]; then
    mkdir -p "$RAIZ$1" 2>/dev/null || con_permiso mkdir -p "$RAIZ$1" || { falla "No pude crear la carpeta $1."; return 1; }
  fi
  [ -e "$RAIZ$1/config.json" ] && return 0
  if [ -w "$RAIZ$1" ]; then
    echo "$config" > "$RAIZ$1/config.json"
  else
    echo "$config" | con_permiso tee "$RAIZ$1/config.json" >/dev/null
  fi || { falla "No pude escribir en la carpeta $1."; return 1; }
}

pedir_estado() {   # pedir_estado PUERTO: ¿responde One TV? (lo que dice queda en $TMP/estado.json)
  if command -v curl >/dev/null 2>&1; then
    curl -fsS --max-time 3 -o "$TMP/estado.json" "http://127.0.0.1:$1/api/status" 2>/dev/null
  else
    wget -q -T 3 -t 1 -O "$TMP/estado.json" "http://127.0.0.1:$1/api/status" 2>/dev/null
  fi
}

esperar_one_tv() {   # esperar_one_tv PUERTO: hasta 3 minutos a que responda (o hasta que el contenedor se detenga)
  local i=0
  while [ "$i" -lt "${ONE_TV_ESPERA:-180}" ]; do
    pedir_estado "$1" && return 0
    [ "$("${DOCKER[@]}" container inspect -f '{{.State.Running}}' "$CONTENEDOR" 2>/dev/null </dev/null)" = true ] ||
      return 1
    sleep 1
    i=$((i + 1))
  done
  return 1
}

instalar_con_docker() {   # instalar_con_docker NAS (o nada: otro Linux con --docker)
  local nas="$1" estado datos compartidas=() c puerto direccion lista
  EQUIPO="$(nombre_equipo "$nas")"
  preparar_docker
  estado=$?
  if [ "$estado" = 4 ]; then
    falla "Sin permiso de administrador no puedo usar Docker. Vuelve a correr este comando cuando quieras."
    return 1
  fi
  if [ "$estado" != 0 ]; then
    case "$nas:$estado" in
      synology:* | qnap:* | unraid:* | truenas:*) docker_falta "$nas" "$estado"; return 1 ;;
      *:2) instalar_docker || return 1 ;;
      *) arrancar_docker ;;
    esac
    preparar_docker || { docker_falta "$nas" 3; return 1; }
  fi
  ok "Docker listo"

  case "$(contenedor_de_antes)" in
    ajeno)
      falla "Ya hay un contenedor «${CONTENEDOR}» que no creó este instalador (por ejemplo, un proyecto de la app de Docker"
      falla "  de tu NAS). Para no romperlo, no lo toco: ponlo al día desde esa app, o bórralo y vuelve a correr este comando."
      return 1 ;;
    nuestro) VARIABLES_DE_ANTES="$(variables_de_antes)" ;;
    *) VARIABLES_DE_ANTES="" ;;
  esac

  bajar_imagen || return 1
  while IFS= read -r c; do [ -n "$c" ] && compartidas+=("$c"); done <<EOF
$(carpetas_nas "$nas")
EOF
  datos="$(datos_nas "$nas")"
  preparar_datos "$datos" || return 1
  armar_docker "$datos" "${compartidas[@]}"

  paso "Arrancando One TV…"
  "${DOCKER[@]}" rm -f "$CONTENEDOR" >/dev/null 2>&1 </dev/null   # (el de antes, si había: los datos se quedan)
  if ! "${DOCKER[@]}" "${ARGS_DOCKER[@]}" </dev/null >/dev/null 2>"$TMP/contenedor.txt"; then
    falla "Docker no pudo crear el contenedor de One TV. Lo que dijo:"
    head -n 5 "$TMP/contenedor.txt" | sed 's/^/    /' >&2
    return 1
  fi
  puerto="${ONE_TV_PUERTO:-}"
  [ -n "$puerto" ] || puerto="$(echo "$VARIABLES_DE_ANTES" | sed -n 's/^PUERTO=//p' | head -n 1)"
  puerto="${puerto:-8765}"
  if ! esperar_one_tv "$puerto"; then
    falla "One TV no arrancó. Lo último que dijo:"
    "${DOCKER[@]}" logs --tail 15 "$CONTENEDOR" </dev/null 2>&1 | sed 's/^/    /' >&2
    falla "  Vuelve a correr este comando; si sigue igual, avísanos en https://github.com/$REPO/issues"
    return 1
  fi

  direccion="http://$(ip_de_la_red):$puerto"
  grep -q '"bienvenida_pendiente": *true' "$TMP/estado.json" 2>/dev/null && direccion="$direccion/bienvenida"
  echo
  ok "One TV quedó corriendo en $EQUIPO, y arranca solo cada vez que se enciende."
  echo
  echo "Ábrelo en el navegador de la computadora o del teléfono (en la misma red de la casa):"
  echo
  echo "    $direccion"
  echo
  case "$direccion" in */bienvenida) echo "Ahí eliges tus carpetas de videos y de música, y la TV." ;; esac
  if [ ${#compartidas[@]} -gt 0 ]; then
    lista="${compartidas[0]}"
    for c in "${compartidas[@]:1}"; do lista="$lista, $c"; done
    echo "One TV puede ver tus carpetas ($lista) solo para leerlas: no cambia ni borra nada."
  fi
  echo "Sus datos quedan en $datos. Para ponerlo al día, vuelve a correr este mismo comando."
}

# ---------------------------------------------------------------- todo junto

main() {
  set -o pipefail
  local sistema nas="" con_docker="${ONE_TV_DOCKER:-}" a
  for a in "$@"; do
    case "$a" in --docker) con_docker=1 ;; esac
  done
  sistema="$(uname -s)"
  case "$sistema" in
    Darwin) DEST="${ONE_TV_DIR:-$HOME/One TV}" ;;
    Linux)
      DEST="${ONE_TV_DIR:-$HOME/one-tv}"
      nas="$(que_nas)"
      ;;
    FreeBSD)
      falla "Este equipo no tiene Docker (¿TrueNAS CORE?): One TV pide TrueNAS SCALE 24.10 o más nuevo, Mac, Windows o Linux."
      return 1
      ;;
    *)
      falla "Este instalador es para Mac y Linux. En Windows, en PowerShell:"
      falla "  irm https://raw.githubusercontent.com/$REPO/main/windows/instalar.ps1 | iex"
      return 1
      ;;
  esac
  TMP="$(mktemp -d "${TMPDIR:-/tmp}/one-tv.XXXXXX")" || { falla "No pude crear una carpeta temporal."; return 1; }
  trap 'rm -rf "$TMP"; [ -n "${PERMISO_PID:-}" ] && kill "$PERMISO_PID" 2>/dev/null' EXIT

  if [ -n "$nas" ] || { [ "$sistema" = Linux ] && [ "$con_docker" = 1 ]; }; then   # un NAS: con Docker
    echo "One TV: instalando (o poniendo al día) en $(nombre_equipo "$nas") con Docker. Tarda unos minutos; no cierres esta ventana."
    echo
    instalar_con_docker "$nas"
    return
  fi

  echo "One TV: instalando (o poniendo al día) en esta computadora. Tarda unos minutos; no cierres esta ventana."
  echo

  bajar_one_tv || return 1
  if [ "$sistema" = Darwin ]; then
    programas_mac || return 1
  else
    programas_linux || return 1
  fi

  echo
  paso "Arrancando One TV…"
  # Con el Python y el ffmpeg elegidos primero en el PATH: ./cine usa los mismos (y los de One TV, si los hay).
  local camino="$(dirname "$PY")"
  [ -d "$DEST/programas/bin" ] && camino="$DEST/programas/bin:$camino"
  if ! PATH="$camino:$PATH" "$DEST/cine" instalador </dev/null; then
    echo
    falla "One TV quedó instalado en $DEST, pero no pudo arrancar (arriba dice por qué)."
    falla "  Vuelve a correr el instalador; si sigue igual, avísanos en https://github.com/$REPO/issues"
    return 1
  fi
  echo
  echo "Para ponerlo al día cuando quieras, vuelve a correr este mismo comando (tu configuración se queda)."
}

if [ "${ONE_TV_SOLO_FUNCIONES:-}" != 1 ]; then
  main "$@"
fi
