# AGENTS.md: guía para agentes de IA que contribuyen

Corta y práctica. Para personas, ver [CONTRIBUTING.md](CONTRIBUTING.md); aquí lo mismo, pensado para quien trabaja con
herramientas y sin preguntar demasiado.

## Qué es el proyecto

**One TV** muestra tus propias películas, series y música (y YouTube sin anuncios) en la TV, la computadora y el
teléfono, por la red de tu casa. Tiene tres piezas:

1. **El servidor** (`mac/`): Python de la biblioteca estándar más `ffmpeg`, en una computadora de la casa. Hoy corre en macOS y en Ubuntu 24.04; Windows 10 y 11, en prueba (falta confirmarlo en un Windows real).
2. **La app de la TV**: `roku/` (BrightScript/SceneGraph) y, en prueba, `androidtv/` para Google TV, Android TV y Fire
   TV (Kotlin + Compose + Media3; ver [androidtv/LEEME.md](androidtv/LEEME.md)).
3. **La web** (`mac/web/index.html`): una sola página que sirve el servidor a cualquier navegador.

Lo que viene y en qué orden: [docs/HOJA_DE_RUTA.md](docs/HOJA_DE_RUTA.md).

**El principio que manda sobre todo**: lo más sencillo posible, para personas que **no** son técnicas. Que se instale
y se use sin terminal donde se pueda, en un solo paso, con mensajes claros y sin jerga. Si una función nueva obliga a
la persona a tocar un archivo o a entender un concepto, rediseña la función, no la explicación.

## Cómo está organizado

| Dónde | Qué hay |
|---|---|
| `mac/cine.py` | Comandos (`./cine …`), arranque, el objeto `App` que junta todo, la configuración (`load_config`) |
| `mac/server.py` | Las rutas HTTP (`/api/…`, videos, portadas) |
| `mac/library.py`, `organizer.py`, `metadata.py`, `artwork.py` | Biblioteca, orden automático de lo nuevo, sinopsis y pósters |
| `mac/transcode.py`, `segcache.py`, `mosaic.py` | Cómo llega cada video a la TV (directo, audio convertido, conversión completa), «varios a la vez» (archivado) |
| `mac/youtube.py`, `ytaccount.py`, `ytdurations.py`, `offline.py`, `live.py` | YouTube, Takeout, duraciones, sin conexión, «En vivo» |
| `mac/music.py`, `playqueue.py`, `mylists.py`, `store.py` | Música, la fila, las listas propias, el progreso |
| `mac/dubbing.py`, `dubsync.py`, `intro.py`, `introsync.py` | Doblaje latino automático y «Saltar intro» |
| `mac/roku.py` | Hablar con el Roku (encontrarlo, instalar la app, control remoto) |
| `mac/teles.py`, `mac/apptv.py` | Las TV con Android (sus órdenes y a cuál TV se manda) y su app para «Downloader» en `/tv` |
| `mac/hostos.py`, `encoders.py`, `linuxservice.py`, `windowsservice.py`, `winapi.py`, `winfirewall.py` | Lo que cambia según el sistema (macOS, Linux, Windows): carpetas, codificador de video, arranque automático, la regla del firewall de Windows |
| `instalar.sh`, `Instalar One TV.*`, `windows/instalar.ps1` | Instalar o poner al día en un paso (ver [docs/instalar-un-paso.md](docs/instalar-un-paso.md)); terminan con `cine instalador` |
| `cine`, `cine.cmd`, `windows/` | Arrancar: `./cine` en macOS y Linux; `cine.cmd` (doble clic) y `windows/cine.ps1` en Windows |
| `mac/web/` | La web (`index.html` y sus letras, íconos y `hls.min.js`; `bienvenida.html`, el asistente del primer arranque, con lo suyo del servidor en `mac/asistente.py`) |
| `roku/` | La app de la TV (`components/` pantallas y piezas, `source/` arranque, `fonts/`, `images/`) |
| `androidtv/` | La app para Google TV, Android TV y Fire TV (`Estado.kt` teclas y estado, `ui/` pantallas, `control/` órdenes de la computadora); ver su `LEEME.md` |
| `menubar/` | El ícono de la barra de menú de macOS (SwiftUI) |
| `pruebas/` | `test_*.py` (sin red ni TV), `web_*.py` (Chrome sin ventana), herramientas; ver [pruebas/LEEME.md](pruebas/LEEME.md) |
| `docs/` | [INSTALAR](docs/INSTALAR.md), [DETALLES](docs/DETALLES.md) (por dentro, seguridad), [HOJA_DE_RUTA](docs/HOJA_DE_RUTA.md) |
| [DESIGN.md](DESIGN.md) | Colores, letras y piezas de la interfaz |

## Cómo correr y probar

Desde la raíz del repositorio. Necesitas `python3` (3.9+) y `ffmpeg`; para la app de la TV, Node.

```
python3 -m unittest discover -s pruebas -p 'test_*.py'   # todo lo del servidor: sin red ni TV, unos 20 s
npx -y brighterscript@0                                  # revisa el código de la app del Roku (si tocaste roku/)
```

**Servidor de prueba con una copia de datos** (nunca pruebes contra el servicio real, ni su puerto 8765, ni la TV):

```
mkdir -p /tmp/cine-prueba/datos        # o copia ahí los datos que necesites
CINE_PRUEBA=/tmp/cine-prueba CINE_PUERTO=8790 python3 pruebas/servidor_de_prueba.py
```

Para algo que se vea (y para capturas) sin datos de nadie: `python3 pruebas/datos_demo.py` arma una biblioteca de ejemplo
(tramos de películas y música de dominio público, canales públicos de YouTube; lo que baja queda en una caché fuera del
repositorio) y la sirve en el puerto 8793.

**Web con Chrome sin ventana**, contra el servidor de prueba: `python3 pruebas/web_fase4.py CARPETA_DE_SALIDA 8790`
(deja capturas a 390 y 1280 px y revisa funciones, contraste y paleta; sale con código 1 si algo falla). Los otros
`web_*.py` están descritos en `pruebas/LEEME.md`. Apaga tu servidor de prueba al terminar y no dejes procesos sueltos.

## Reglas

- **Todo en español**: lo que ve la persona (TV, web, mensajes del servidor), los comentarios, los nombres de las
  pruebas, los commits y los pull requests. Español neutro, sin jerga: «la computadora», «la TV», «la fila».
- **Sin dependencias nuevas en el servidor**: biblioteca estándar de Python más `ffmpeg`. Si algo necesita otra cosa, que
  se instale sola en un entorno aparte (como `yt-dlp`) y que no sea obligatoria.
- **Nada personal en el repositorio**: ni nombres, ni rutas con un usuario, ni direcciones IP de una casa, ni claves.
  Lo propio de cada instalación va en `config.json` (que nunca se sube); los ejemplos de pruebas y de documentos son
  inventados (para direcciones de ejemplo, `192.0.2.x`).
- **Seguridad**: el servidor no tiene contraseña y escucha en la red de la casa. **No abras archivos ni direcciones que
  mande el cliente sin validarlos.** Lee «Seguridad» en [docs/DETALLES.md](docs/DETALLES.md#seguridad) y mira
  `decode_url` en `mac/live.py`: las direcciones que se reescriben van firmadas y solo se abre lo que el propio
  servidor puso, y solo de internet. Rutas de archivos: dentro de las carpetas configuradas, sin `..`.
- **Interfaz**: colores y letras solo de los tokens de [DESIGN.md](DESIGN.md) (el bloque `:root` de `mac/web/index.html` y
  `roku/components/Theme.brs`). Ni un hex suelto: `pruebas/web_fase4.py` lo revisa.
- **Texto para personas no técnicas**: nada de «endpoint», «servicio launchd» ni «API» en pantalla; di qué pasó y qué hacer.

## Cómo trabajar

1. **Una rama por tema**, desde `main` actualizado (por ejemplo `feat/ubuntu-servidor`, `fix/titulo-largo`). No mezcles temas.
2. **Cambios pequeños y commits claros**, en español, que cuenten el porqué.
3. **Pruebas antes del pull request**: corre las de arriba; agrega o ajusta las de lo que cambias. Si tocaste la web o la TV,
   míralo funcionando (capturas) y di qué no pudiste probar (por ejemplo «no tengo un Roku 4K»).
4. **Pull request** con la descripción de la plantilla (`.github/pull_request_template.md`): qué cambia para quien lo usa,
   cómo lo probaste, qué falta. Al abrirlo corren solas las pruebas y la revisión del código del Roku; tienen que pasar.
5. Para algo grande (otra plataforma, cómo se guarda algo), abre antes un *issue* con la idea.
6. Si cambias lo que se ve o cómo se instala, actualiza también los documentos (`README.md`, `docs/`).
