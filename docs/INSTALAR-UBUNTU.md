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
wget -qO- https://raw.githubusercontent.com/julai1433/one-tv/main/instalar.sh | bash
```

(con `curl -fsSL … | bash` es lo mismo). Baja One TV a `~/one-tv` e instala con apt lo que falte (Python y ffmpeg):
para eso pide **tu contraseña** (la de tu usuario de Ubuntu) una sola vez y dice para qué. Deja el servidor
corriendo de fondo y arrancando solo con la computadora (paso 4) y abre el navegador en la **bienvenida**
(<http://localhost:8765/bienvenida>), que termina la configuración. En un servidor sin pantalla, muestra la dirección
exacta para abrir desde otro aparato (algo como `http://192.168.1.20:8765/bienvenida`).

Tus películas y series van en `~/Vídeos/Biblioteca` (o `~/Videos/Biblioteca`; la crea si no existe). Si prefieres
contestar unas preguntas en la Terminal: `cd ~/one-tv && ./cine configurar`. Para ponerlo al día cuando quieras,
vuelve a pegar el mismo comando: tu configuración y lo que ya viste se quedan.

Si algún día `./cine` dice `✗ Faltan programas`, copia y pega el comando `sudo apt …` que muestra.

## 3. La app del Roku

Igual que con la Mac: activa el **modo desarrollador** del Roku ([INSTALAR.md, paso
6](INSTALAR.md#paso-6-activar-el-modo-desarrollador-del-roku)) y pon esa contraseña con `./cine configurar`. Con el
servidor arrancado y la TV encendida, **el servidor instala la app «One TV» en el Roku** solo ([paso
7](INSTALAR.md#paso-7-instalar-la-app-en-el-roku)); si no pasó, corre `./cine instalar`.

## 4. Que arranque solo

El instalador ya lo deja así. A mano (por ejemplo, si lo quitaste):

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
- Pon tus películas y series en tu carpeta de la biblioteca; se ordenan solas ([INSTALAR.md, parte
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
