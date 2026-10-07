# Instalar One TV en Windows

> **En prueba.** Todo esto está hecho pero todavía no se ha probado en un Windows real. Si lo instalas, cuéntanos
> cómo te fue (un *issue* en GitHub): es lo que falta para darlo por bueno.

Para quien tiene una computadora con **Windows 10 u 11**. Esa computadora hace de servidor: guarda tus videos y los
prepara; el Roku los muestra en la TV. Funciona igual que en una Mac (la guía de la Mac, con más detalle, es
[INSTALAR.md](INSTALAR.md)). No hace falta ser administrador.

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

Baja One TV a la carpeta `one-tv` de tu usuario, deja un acceso **One TV** en el Escritorio (doble clic para
arrancarlo otro día) y lo abre.

- **Si faltan programas** (Python y ffmpeg), lo dice y ofrece instalarlos: escribe `s` y Enter. Si Windows pregunta si
  permites cambios, di que sí.
- Después te hace **cuatro preguntas**; Enter acepta lo que sale entre corchetes:
  1. **Carpeta de tus películas y series**: sugiere `Biblioteca` dentro de tu carpeta Videos. Si no existe, la crea.
  2. **Contraseña del modo desarrollador del Roku**: la vas a inventar en el paso 3. Si aún no la tienes, deja vacío.
  3. **IP del Roku**: déjala vacía; la busca sola.
  4. **Carpeta de música** (opcional): escribe «no» si no quieres la sección Música.
- **El aviso del firewall**: la primera vez, Windows pregunta si Python puede usar la red. Deja marcada **Redes
  privadas** y pulsa **Permitir acceso**. Sin eso, la TV no puede ver la computadora.

Luego el servidor queda corriendo en esa ventana. Para pararlo, ciérrala (o `Ctrl + C`).

¿Prefieres no usar PowerShell? Baja el [ZIP](https://github.com/julai1433/one-tv/archive/refs/heads/main.zip), clic
derecho → **Extraer todo**, abre la carpeta y haz doble clic en `cine.cmd` (si Windows pregunta si quieres
ejecutarlo, elige **Ejecutar**).

**Para escribir un comando de One TV** (`cine autoarranque`, `cine estado`…): abre la carpeta `one-tv` en el
Explorador de archivos, haz clic en la barra de dirección (arriba), escribe `cmd` y pulsa Enter. En la ventana negra
que se abre, escribe el comando y pulsa Enter.

## 3. La app del Roku

Igual que con la Mac: activa el **modo desarrollador** del Roku ([INSTALAR.md, paso
6](INSTALAR.md#paso-6-activar-el-modo-desarrollador-del-roku)) y pon esa contraseña con `cine configurar`. Con el
servidor arrancado y la TV encendida, **el servidor instala la app «One TV» en el Roku** solo ([paso
7](INSTALAR.md#paso-7-instalar-la-app-en-el-roku)); si no pasó, escribe `cine instalar`.

## 4. Que arranque solo

```
cine autoarranque
```

Deja el servidor corriendo de fondo, **sin ventanas**, y **arranca solo cada vez que inicias sesión en Windows**; si se
cae, se vuelve a levantar. No pide contraseña ni permisos de administrador (es una tarea del Programador de tareas
llamada «One TV»). El límite: corre mientras tu sesión está iniciada. Si la computadora se reinicia, entra a tu cuenta
(después puedes bloquearla con `Windows + L`: sigue funcionando).

- `cine estado`: si está corriendo y en qué dirección se abre la página.
- `cine` (o el acceso del Escritorio): después de cambiar algo (`config.json` o una versión nueva), copia los cambios y
  lo reinicia.
- `cine quitar-autoarranque`: deja de arrancar solo.

## 5. Abrir la página y poner tus videos

- En la misma computadora: <http://localhost:8765>. Desde otro aparato (laptop, teléfono): la dirección que muestra
  `cine estado`.
- Pon tus películas y series en la carpeta de la pregunta 1; se ordenan solas ([INSTALAR.md, parte
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

- **No encuentra el Roku o la TV no abre la página**: la red de tu casa tiene que estar como **privada** en Windows:
  Configuración → Red e Internet → tu Wi-Fi (o Ethernet) → **Tipo de perfil de red: Privada**. Si cerraste el aviso
  del firewall sin permitir: Seguridad de Windows → Firewall y protección de red → **Permitir una aplicación a través
  del firewall** → Cambiar la configuración → marca **Privada** en las líneas de Python. Si aun así no lo encuentra,
  pon la IP del Roku en `config.json` (`"roku_ip"`).
- **Dice que falta winget**: instala el «Instalador de aplicación» desde la Microsoft Store
  (<https://apps.microsoft.com/detail/9NBLGGH4NNS1>) y vuelve a abrir One TV.
- **Tienes el Python de la Microsoft Store**: One TV avisa y ofrece instalar el de python.org, que funciona mejor
  (`winget install -e --id Python.Python.3.12`).
- **Para ver qué está pasando**: abre `%LOCALAPPDATA%\cine-roku\Logs\cine-roku.log` con el Bloc de notas.

## Qué se ha probado

Las pruebas automáticas del proyecto corren en las computadoras con Windows de GitHub (sin TV ni chip de video): el
servidor con videos de prueba (catálogo, pósters, conversión con el procesador, código QR), `cine.cmd`, y el arranque
automático de verdad (la tarea «One TV»: arranca sin ventana, se levanta sola si se cae, aplica cambios y se quita).
**Todavía no** se ha probado en una computadora de casa con Windows 10 u 11: el instalador de un comando, winget, el
aviso del firewall con un Roku de verdad, los chips de video (NVIDIA, Intel, AMD), las carpetas en OneDrive, «En
vivo» con Edge o Chrome, Tailscale ni el doblaje latino.
