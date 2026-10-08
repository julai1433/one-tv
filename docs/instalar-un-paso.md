# Instalar en un paso

Un botón, un doble clic o un comando por sistema. Instala lo que falte, deja One TV corriendo y arrancando solo, y abre
el navegador en la bienvenida (`/bienvenida`), donde se eligen las carpetas y la TV. **Volver a correrlo lo pone al
día**: tu configuración y lo que ya viste se quedan.

## El botón

**<https://julai1433.github.io/one-tv/>** — reconoce el sistema y ofrece lo suyo: el instalador de doble clic en Mac y
Windows, el comando en Linux, y «¿Tienes un NAS?» para la guía de Docker. Los instaladores salen de la versión
«instaladores» de GitHub, con nombres fijos (el enlace no cambia nunca):

- Mac: <https://github.com/julai1433/one-tv/releases/download/instaladores/Instalar-One-TV-Mac.pkg>
- Windows: <https://github.com/julai1433/one-tv/releases/download/instaladores/Instalar-One-TV-Windows.cmd>

## Mac

Con el botón: abre **Instalar-One-TV-Mac.pkg** y sigue los pasos (se instala solo para ti, sin contraseña). Mientras
el paquete no esté firmado por Apple, la primera vez macOS pide permitirlo en Configuración del Sistema → Privacidad y
seguridad → «Abrir de todos modos». O, en la **Terminal** (`⌘ + Espacio`, escribe «Terminal»):

```
curl -fsSL https://raw.githubusercontent.com/julai1433/one-tv/main/instalar.sh | bash
```

Baja One TV a la carpeta **One TV** de tu usuario. Si a la Mac le falta Python o ffmpeg, los baja solo para One TV,
dentro de esa carpeta (unos 80 MB; sin Homebrew, sin las herramientas de Xcode y sin pedir contraseña); si ya los
tienes (por ejemplo, de Homebrew), usa esos. Deja el arranque automático puesto y abre <http://localhost:8765/bienvenida>.
El .pkg hace lo mismo (baja y corre ese instalar.sh); lo que dijo queda en `~/Library/Logs/One TV - instalador.log`.

## Windows 10 y 11

Con el botón: abre **Instalar-One-TV-Windows.cmd** con doble clic (si el navegador o Windows avisan: «Conservar», y
luego «Más información» → «Ejecutar de todas formas»). O en **PowerShell** (Inicio → escribe «PowerShell»):

```
irm https://raw.githubusercontent.com/julai1433/one-tv/main/windows/instalar.ps1 | iex
```

Baja One TV a `one-tv` en tu carpeta de usuario, instala con winget lo que falte (Python y ffmpeg), pide permiso de
administrador **una vez** para que la TV y el teléfono puedan conectarse (la regla «One TV» del Firewall de Windows),
deja el arranque automático al iniciar sesión y abre <http://localhost:8765/bienvenida>.

## Linux (Ubuntu, Debian y otros con apt)

En la **Terminal** (`Ctrl + Alt + T`) o por SSH:

```
wget -qO- https://raw.githubusercontent.com/julai1433/one-tv/main/instalar.sh | bash
```

(o lo mismo con `curl -fsSL … | bash`). Baja One TV a `~/one-tv`, instala con apt lo que falte (Python y ffmpeg) y
pide tu contraseña **una sola vez**, diciendo para qué. Deja el servicio de systemd que arranca al encender la
computadora y abre el navegador; en un servidor sin pantalla, dice la dirección exacta para abrir desde otro aparato
(algo como `http://192.168.1.20:8765/bienvenida`). Para usar Docker en vez de instalar directo:
`wget -qO- … | bash -s -- --docker`. Si ya tienes One TV en Docker en esa computadora, lo pone al día ahí, en Docker,
aunque no pongas `--docker`.

## NAS

**Con terminal** (SSH, o el botón `>_` de Unraid): el mismo comando de Linux. Reconoce el NAS (Synology, Unraid, QNAP,
TrueNAS SCALE, OpenMediaVault) e instala con **Docker**:

- **Docker es requisito.** En Unraid y TrueNAS SCALE ya viene (si está apagado, dice dónde prenderlo: Unraid, Settings →
  Docker; TrueNAS, Apps → Choose Pool). En Synology y QNAP se instala desde su tienda de apps («Container Manager» en el
  Centro de paquetes, «Container Station» en el App Center): el instalador lo dice y pide volver a correr el comando.
  En OpenMediaVault (y en otro Linux con `--docker`) lo instala con el instalador oficial de Docker, pidiendo la
  contraseña una vez.
- Crea el contenedor `one-tv`: red `host` (para encontrar la TV), arranque con el NAS, el chip de video (`/dev/dri`) si
  lo hay, los datos en una carpeta clara (`/volume1/docker/one-tv`, `/mnt/user/appdata/one-tv`,
  `/share/Container/one-tv`…) y **todas las carpetas compartidas de solo lectura** en la misma ruta (`/volume1`,
  `/mnt/user`, `/share`, cada pool de `/mnt`…): en el asistente se eligen las de videos y música sin volver a crearlo.
- Al final dice la dirección para abrirlo desde la computadora o el teléfono: `http://<ip-del-nas>:8765/bienvenida`.
- Volver a correrlo baja la versión nueva y vuelve a crear el contenedor con lo mismo (los datos se quedan).
- Si lo instalaste a mano (Portainer, un proyecto de Container Manager, otro nombre de contenedor), vuelve a correr el
  comando: te ofrece cambiarlo por el del instalador, sin perder nada (datos, carpetas, clave del Roku y puerto). El de
  antes solo se borra cuando el nuevo ya responde; si el nuevo no arranca, vuelve como estaba. Si encuentra más de un
  One TV en Docker, no toca ninguno y dice cuáles son.

**Sin terminal**: un «proyecto» con un docker-compose listo para pegar en Container Manager (Synology), Container
Station (QNAP), Unraid, TrueNAS o Portainer: [INSTALAR-DOCKER.md](INSTALAR-DOCKER.md).

## Qué baja y cómo se revisa (Mac)

Solo si la Mac no tiene uno que sirva (Python 3.9 o más nuevo; ffmpeg 7 o más nuevo), y con la versión y la suma de
verificación (sha256) fijas en `instalar.sh`; si lo que llega no coincide, no se instala y lo dice:

- **Python 3.12.15** de [python-build-standalone](https://github.com/astral-sh/python-build-standalone) (versión
  20261003), unos 25 MB, para chip de Apple o Intel.
- **ffmpeg y ffprobe 9.0.2** estáticos y firmados de [martin-riedl.de](https://ffmpeg.martin-riedl.de) (con
  VideoToolbox, el chip de video de la Mac), unos 56 MB (chip de Apple) o 67 MB (Intel). Piden macOS 12 o más nuevo.

Quedan en `~/One TV/programas`; nada fuera de esa carpeta. Para quitar One TV: `./cine quitar-autoarranque` dentro
de la carpeta y luego bórrala.

## Publicar (para quien mantiene One TV)

- **La página**: `pagina/` (armada con `pagina/armar.sh`), publicada por `.github/workflows/pagina.yml` al subir a main.
  Una sola vez: Settings → Pages → Source: «GitHub Actions».
- **Los instaladores**: `.github/workflows/instaladores.yml` arma el .pkg y el .cmd
  (`instaladores/armar.sh`) y los sube a la versión «instaladores» (sin marcarla como la más nueva: esa
  es la de la app de la TV). Solo cuando cambian `instaladores/`, `Instalar One TV.cmd` o el guion que los arma: los
  dos bajan instalar.sh y One TV de main al correr.
