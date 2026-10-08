# Instalar One TV en Windows

> **En prueba.** Todo esto está hecho pero todavía no se ha probado en un Windows real. Si lo instalas, cuéntanos
> cómo te fue (un *issue* en GitHub): es lo que falta para darlo por bueno.

Para quien tiene una computadora con **Windows 10 u 11**. Esa computadora hace de servidor: guarda tus videos y los
prepara; el Roku los muestra en la TV. Funciona igual que en una Mac (la guía de la Mac, con más detalle, es
[INSTALAR.md](INSTALAR.md)). Solo pide permiso de administrador una vez, para que la TV y el teléfono puedan
conectarse (la regla del firewall).

Tiempo aproximado: 15 minutos.

## 1. Qué necesitas

- La computadora con Windows 10 u 11, encendida cuando quieras ver algo, en la **misma red** que el Roku.
- Un **Roku** con modo desarrollador (casi todos).
- Tus películas y series en archivos de video (`.mkv`, `.mp4`…).

## 2. Instalar y arrancar: un solo comando

Abre **PowerShell** (botón Inicio, escribe `PowerShell` y pulsa Enter), pega esto y pulsa Enter:

```
irm https://raw.githubusercontent.com/julai1433/one-tv/main/windows/instalar.ps1 | iex
```

Baja One TV a la carpeta `one-tv` de tu usuario, deja un acceso **One TV** en el Escritorio y:

- **Si faltan programas** (Python y ffmpeg), los instala con winget, sin preguntar. Si Windows pregunta si permites
  cambios para instalarlos, di que sí.
- **El permiso para la TV y el teléfono**: Windows te pregunta si permites que una aplicación (Windows PowerShell)
  haga cambios en el dispositivo. Di que **sí**: es para crear la regla «One TV» del firewall, que deja que la TV y el
  teléfono se conecten a la computadora (solo desde la red de tu casa). Es la única vez que pide algo así.
- Deja el servidor corriendo de fondo y **arrancando solo cada vez que inicias sesión** (paso 4) y abre el navegador
  en la **bienvenida** (<http://localhost:8765/bienvenida>), que termina la configuración. Tus películas y series van
  en `Biblioteca`, dentro de tu carpeta Videos (la crea si no existe). Si prefieres contestar unas preguntas en la
  ventana de comandos: `cine configurar`.

Para ponerlo al día cuando quieras, vuelve a pegar el mismo comando: tu configuración y lo que ya viste se quedan.

¿Prefieres no usar PowerShell? Baja el [ZIP](https://github.com/julai1433/one-tv/archive/refs/heads/main.zip), clic
derecho → **Extraer todo**, abre la carpeta y haz doble clic en `Instalar One TV.cmd` (si Windows avisa que viene de
internet: **Más información** → **Ejecutar de todas formas**). Hace lo mismo.

**Para escribir un comando de One TV** (`cine autoarranque`, `cine estado`…): abre la carpeta `one-tv` en el
Explorador de archivos, haz clic en la barra de dirección (arriba), escribe `cmd` y pulsa Enter. En la ventana negra
que se abre, escribe el comando y pulsa Enter.

## 3. La app del Roku

Igual que con la Mac: activa el **modo desarrollador** del Roku ([INSTALAR.md, paso
6](INSTALAR.md#paso-6-activar-el-modo-desarrollador-del-roku)) y pon esa contraseña con `cine configurar`. Con el
servidor arrancado y la TV encendida, **el servidor instala la app «One TV» en el Roku** solo ([paso
7](INSTALAR.md#paso-7-instalar-la-app-en-el-roku)); si no pasó, escribe `cine instalar`.

## 4. Que arranque solo

El instalador ya lo deja así. A mano (por ejemplo, si lo quitaste):

```
cine autoarranque
```

Deja el servidor corriendo de fondo, **sin ventanas**, y **arranca solo cada vez que inicias sesión en Windows**; si se
cae, se vuelve a levantar. Es una tarea del Programador de tareas llamada «One TV» (no pide contraseña; si falta la
regla del firewall, pide ese permiso una vez). El límite: corre mientras tu sesión está iniciada. Si la computadora se reinicia, entra a tu cuenta
(después puedes bloquearla con `Windows + L`: sigue funcionando).

- `cine estado`: si está corriendo y en qué dirección se abre la página.
- `cine` (o el acceso del Escritorio): después de cambiar algo (`config.json` o una versión nueva), copia los cambios y
  lo reinicia.
- `cine quitar-autoarranque`: deja de arrancar solo.
- `cine permitir-red`: crea (o corrige) la regla del firewall que deja entrar a la TV y al teléfono.

## 5. Abrir la página y poner tus videos

- En la misma computadora: <http://localhost:8765>. Desde otro aparato (laptop, teléfono): la dirección que muestra
  `cine estado`.
- Pon tus películas y series en tu carpeta de la biblioteca (`Biblioteca`, dentro de Videos); se ordenan solas ([INSTALAR.md, parte
  4](INSTALAR.md#parte-4-tus-películas-y-series)). Revisa cómo llegará cada una a la TV con `cine catalogo`.

## Diferencias con la Mac

- **Convertir video**: al arrancar, One TV prueba un segundo de video con el chip de la computadora (NVIDIA, Intel o
  AMD) y lo usa si funciona; si no, usa el procesador. El registro dice cuál («✓ Video: se convierte con…»). Para
  fijarlo, en `config.json`: `"codificador": "libx264"` (procesador), `"nvenc"`, `"qsv"` o `"amf"`.
- **Que no se duerma**: mientras ves algo, la computadora no se suspende sola (cerrar la tapa de una laptop sí la
  duerme).
- **«En vivo»** usa Google Chrome, Brave o Microsoft Edge (Edge ya viene con Windows).
- **El iPhone fuera de casa** (Tailscale): instala Tailscale para Windows (<https://tailscale.com/download/windows>) y
  escribe `cine tailscale`.
- **El ícono de la barra de menú** es solo de macOS.
- **Tus carpetas**: One TV usa tus carpetas Videos, Música y Descargas donde estén de verdad, aunque las hayas movido o
  estén en OneDrive. Si tus películas están en OneDrive, haz clic derecho en la carpeta → **Mantener siempre en este
  dispositivo** (si no, OneDrive las deja en la nube y la TV no las puede ver).
- Dónde guarda sus cosas: todo en `%LOCALAPPDATA%\cine-roku` (pégalo en la barra de dirección del Explorador): datos
  (progreso, listas) en `datos`, caché (se puede borrar) en `Cache`, registro en `Logs\cine-roku.log`.

## Si algo falla

### La TV no encuentra la computadora

(La app de la TV no la encuentra, o escribiendo la dirección, como `192.168.1.79:8765`, se queda esperando.)

1. **Pruébalo desde el teléfono**: conectado al Wi-Fi de tu casa, abre en su navegador `http://<la IP de la
   computadora>:8765` (la dirección que muestra `cine estado`, «Desde otro aparato»). Si abre, la computadora está bien
   y el problema está en la TV (revisa que esté en la misma red).
2. **Si no abre**: casi siempre es el firewall de Windows, que bloquea la entrada sin avisar cuando el servidor corre
   de fondo. Abre una ventana de comandos en la carpeta `one-tv` y escribe `cine permitir-red`; Windows pide permiso
   de administrador una vez: di que sí. `cine estado` avisa si sigue bloqueado.
3. **Si tienes otro antivirus con su propio firewall** (Norton, McAfee, Avast, AVG, Bitdefender, Kaspersky, ESET…):
   ese manda sobre el de Windows. Busca en su configuración «Firewall» → reglas o aplicaciones permitidas, y permite
   **One TV** (o **Python**, `python.exe` y `pythonw.exe`) en la red de tu casa.
4. **La misma red**: la TV y la computadora tienen que estar en la misma red de tu casa; no en la de **invitados** del
   router (esa aísla a cada aparato), ni una por cable en otro router y la otra por Wi-Fi en otro.

### Otros

- **No encuentra el Roku**: si aun con lo de arriba no lo encuentra, pon la IP del Roku en `config.json`
  (`"roku_ip"`; la ves en el Roku: Configuración → Red → Acerca de).
- **Dice que falta winget**: instala el «Instalador de aplicación» desde la Microsoft Store
  (<https://apps.microsoft.com/detail/9NBLGGH4NNS1>) y vuelve a abrir One TV.
- **Tienes el Python de la Microsoft Store**: One TV avisa y ofrece instalar el de python.org, que funciona mejor
  (`winget install -e --id Python.Python.3.12`).
- **Para ver qué está pasando**: abre `%LOCALAPPDATA%\cine-roku\Logs\cine-roku.log` con el Bloc de notas.

## Qué se ha probado

Las pruebas automáticas del proyecto corren en las computadoras con Windows de GitHub (sin TV ni chip de video): el
servidor con videos de prueba (catálogo, pósters, conversión con el procesador, código QR), `cine.cmd`, el arranque
automático de verdad (la tarea «One TV»: arranca sin ventana, se levanta sola si se cae, aplica cambios y se quita) y
la regla «One TV» del firewall (`cine permitir-red`: una sola, se corrige si cambia el puerto; allá sin la ventana de
permiso, porque corren como administrador). **Todavía no** se ha probado en una computadora de casa con Windows 10 u
11: el instalador de un comando y su doble clic, winget, la ventana de permiso del firewall con un Roku de verdad, los chips de video (NVIDIA, Intel, AMD), las carpetas en OneDrive, «En
vivo» con Edge o Chrome, Tailscale ni el doblaje latino.
