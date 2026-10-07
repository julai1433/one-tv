# One TV en un contenedor (Docker): el servidor de mac/ con Python 3 y ffmpeg, para un NAS o cualquier Linux con Docker.
# Guía: docs/INSTALAR-DOCKER.md. Ejemplo de uso: docker-compose.yml.
#
# Es Ubuntu 24.04, el mismo sistema en el que se prueba el servidor (pruebas/ubuntu.sh): su ffmpeg 6.1 trae VAAPI y
# Quick Sync (chips de video de Intel, los de casi todos los NAS) y su Python 3.12 trae «venv», que el servidor usa
# para instalar yt-dlp en un entorno aparte. Para amd64 y arm64.
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8 PYTHONUNBUFFERED=1 PYTHONUTF8=1 \
    ONE_TV_CONTENEDOR=1 HOME=/datos TZ=UTC CINE_NO_BROWSER=1

# - python3 y python3-venv, ffmpeg: lo que pide ./cine en Linux.
# - tini: cierra bien el servidor y recoge los ffmpeg que queden vivos.
# - tzdata y ca-certificates: la hora de la casa (variable TZ) y las conexiones seguras (YouTube, metadatos).
# - mesa-va-drivers, intel-media-va-driver, libmfx-gen1.2 y vainfo: el chip de video de Intel (VAAPI y Quick Sync) y el
#   de AMD. En una computadora sin chip de video no estorban: el servidor lo prueba al arrancar y, si no sirve, usa el
#   procesador (libx264). En arm64 (Intel no existe) solo se instalan los de Mesa.
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-venv ffmpeg tini tzdata ca-certificates util-linux \
 && if [ "$(dpkg --print-architecture)" = "amd64" ]; then \
      apt-get install -y --no-install-recommends mesa-va-drivers intel-media-va-driver libmfx-gen1.2 vainfo; \
    else \
      apt-get install -y --no-install-recommends mesa-va-drivers; \
    fi \
 && (userdel -r ubuntu 2>/dev/null || true) \
 && rm -rf /var/lib/apt/lists/* \
 && mkdir -p /datos /biblioteca /musica /app

# Solo lo que el servidor necesita (ver .dockerignore): el programa, la app del Roku (el servidor la instala sola en la
# TV) y el arranque del contenedor.
COPY mac /app/mac
COPY roku /app/roku
COPY docker/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh && find /app -name __pycache__ -prune -exec rm -rf {} +

WORKDIR /app
VOLUME ["/datos"]
EXPOSE 8765
HEALTHCHECK --interval=60s --timeout=5s --start-period=60s --retries=3 \
  CMD python3 -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/api/status' % (os.environ.get('PUERTO') or 8765), timeout=4)" || exit 1

ENTRYPOINT ["/usr/bin/tini", "--", "/app/entrypoint.sh"]
