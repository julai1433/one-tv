# Ubuntu 24.04 con lo mismo que pide ./cine (python3, python3-venv y ffmpeg de apt) y un usuario normal, para correr
# las pruebas como en una computadora con Ubuntu. Lo usa pruebas/ubuntu.sh.
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-venv ffmpeg ca-certificates zip \
 && rm -rf /var/lib/apt/lists/*
RUN useradd -m prueba
USER prueba
WORKDIR /home/prueba
