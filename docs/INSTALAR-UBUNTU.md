# Instalar One TV en Ubuntu

Para quien tiene una computadora o un servidor con **Ubuntu 24.04** (con escritorio o sin él, por ejemplo un NAS).
Esa computadora hace de servidor: guarda tus videos y los prepara; el Roku los muestra en la TV. Funciona igual que
en una Mac (la guía de la Mac, con más detalle, es [INSTALAR.md](INSTALAR.md)).

Tiempo aproximado: 15 minutos.

## 1. Qué necesitas

- La computadora con Ubuntu 24.04, encendida cuando quieras ver algo, en la **misma red** que el Roku.
- Un **Roku** con modo desarrollador (casi todos).
- Tus películas y series en archivos de video (`.mkv`, `.mp4`…).

## 2. Instalar y arrancar: un solo comando

Abre la **Terminal** (en el escritorio: `Ctrl + Alt + T`; en un servidor: entra por SSH), pega esto y pulsa Enter:

```
sudo apt update && sudo apt install -y git python3 python3-venv ffmpeg && git clone https://github.com/julai1433/one-tv.git ~/one-tv && cd ~/one-tv && ./cine
```

Primero pide **tu contraseña** (la de tu usuario de Ubuntu) para instalar los programas que hacen falta. Después
`./cine` te hace **cuatro preguntas**; Enter acepta lo que sale entre corchetes:

1. **Carpeta de tus películas y series**: sugiere `~/Vídeos/Biblioteca` (o `~/Videos/Biblioteca`). Si no existe, la crea.
2. **Contraseña del modo desarrollador del Roku**: la vas a inventar en el paso 3. Si aún no la tienes, deja vacío.
3. **IP del Roku**: déjala vacía; la busca sola.
4. **Carpeta de música** (opcional): escribe «no» si no quieres la sección Música.

Luego arranca el servidor en esa ventana. Para pararlo: `Ctrl + C`.

Si algún día `./cine` dice `✗ Faltan programas`, copia y pega el comando `sudo apt …` que muestra.

## 3. La app del Roku

Igual que con la Mac: activa el **modo desarrollador** del Roku ([INSTALAR.md, paso
6](INSTALAR.md#paso-6-activar-el-modo-desarrollador-del-roku)) y pon esa contraseña con `./cine configurar`. Con el
servidor arrancado y la TV encendida, **el servidor instala la app «One TV» en el Roku** solo ([paso
7](INSTALAR.md#paso-7-instalar-la-app-en-el-roku)); si no pasó, corre `./cine instalar`.

## 4. Que arranque solo

```
./cine autoarranque
```

Deja el servidor corriendo de fondo (un servicio de tu usuario en systemd, el sistema que arranca los programas de
Ubuntu): se vuelve a levantar si se cae y **arranca al encender la computadora, aunque nadie inicie sesión**. Para
eso activa una opción de systemd («linger»); si no pudo, te dice el comando (`sudo loginctl enable-linger tu-usuario`).

- `./cine estado`: si está corriendo y en qué dirección se abre la página.
- `./cine`: después de cambiar algo (`config.json` o una versión nueva del proyecto), copia los cambios y lo reinicia.
- `./cine quitar-autoarranque`: deja de arrancar solo.

## 5. Abrir la página y poner tus videos

- En la misma computadora: <http://localhost:8765>. Desde otro aparato (laptop, teléfono): la dirección que muestra
  `./cine estado` («Desde la computadora» o «Desde otro aparato»).
- Pon tus películas y series en la carpeta de la pregunta 1; se ordenan solas ([INSTALAR.md, parte
  4](INSTALAR.md#parte-4-tus-películas-y-series)). Revisa cómo llegará cada una a la TV con `./cine catalogo`.

## Diferencias con la Mac

- **Convertir video**: al arrancar, One TV prueba un segundo de video con el chip de la computadora (NVIDIA, Intel o
  AMD) y lo usa si funciona; si no, usa el procesador. El registro dice cuál («✓ Video: se convierte con…»). Para
  fijarlo, en `config.json`: `"codificador": "libx264"` (procesador), `"nvenc"`, `"qsv"` o `"vaapi"`. Con Intel o
  AMD, tu usuario necesita permiso para el chip: `sudo usermod -aG render,video $USER` y reinicia (el registro lo
  avisa).
- **Que no se suspenda**: en un escritorio, si la computadora se duerme mientras ves algo, apaga la suspensión
  automática en Configuración → Energía. (Un servidor no se suspende solo.)
- **«En vivo»** necesita Google Chrome o Brave instalados (o Chromium).
- **El iPhone fuera de casa** (Tailscale): instálalo con las instrucciones de <https://tailscale.com/download/linux>,
  dale permiso a tu usuario una vez con `sudo tailscale set --operator=$USER` y corre `./cine tailscale`.
- **El ícono de la barra de menú** es solo de macOS.
- Con el ffmpeg de Ubuntu 24.04 (6.1), «varios a la vez en la TV» con un canal en vivo puede atrasarse un poco (la
  opción que lo evita es de ffmpeg 7.1).
- Dónde guarda sus cosas: datos (progreso, listas) en `~/.local/share/cine-roku/datos`; caché (se puede borrar) en
  `~/.cache/cine-roku`; registro en `~/.local/state/cine-roku/cine-roku.log`.

## Si algo falla

- **No encuentra el Roku o la TV no abre la página**: revisa que estén en la misma red. Si usas el cortafuegos de
  Ubuntu (`ufw`), abre el puerto (`sudo ufw allow 8765/tcp`) y pon la IP del Roku en `config.json` (`"roku_ip"`):
  el cortafuegos no deja pasar la respuesta de la búsqueda automática.
- **`./cine autoarranque` dice «No pude hablar con systemd de tu usuario»**: entra directamente con tu usuario (en
  la computadora o por SSH), no con `su` ni `sudo`.
- **Para ver qué está pasando**: `tail -f ~/.local/state/cine-roku/cine-roku.log` (`Ctrl + C` para salir).

## Qué se ha probado

En Ubuntu 24.04 (contenedor, sin TV ni chip de video): la instalación con apt, las preguntas de `./cine`, el servidor
con videos de prueba (catálogo, pósters, conversión con el procesador, código QR), el arranque automático con systemd
(también al encender sin iniciar sesión, y que se levante solo si se cae) y todas las pruebas automáticas. **Todavía
no** se ha probado con un Roku ni con chips de video reales (NVIDIA, Intel, AMD), ni «En vivo» con Chrome, Tailscale
o el doblaje latino en Linux.
