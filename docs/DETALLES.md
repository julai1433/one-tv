# One TV: detalles

Referencia de lo que hay por dentro: comandos, cómo se ordena la biblioteca, el doblaje latino, «Saltar intro»,
el arranque automático, cómo llega cada video a la TV, «En vivo», los subtítulos y la configuración. Para
instalar, ver [INSTALAR.md](INSTALAR.md); para usarlo, el [README](../README.md).

**Qué cubre hoy**: One TV tiene tres piezas (el servidor, la app de la TV y la web). Hoy el servidor corre en **macOS**
y la app de TV es para **Roku**; lo que depende de uno u otro lo dice el título o la frase («macOS», «Roku»), y lo demás
vale para cualquier sistema o TV. Lo que viene está en la [hoja de ruta](HOJA_DE_RUTA.md).

## Comandos

Desde esta carpeta, en una Terminal de macOS (o doble clic en `One TV.command`, que equivale a `./cine`):

| Comando | Qué hace |
|---|---|
| `./cine configurar` | Primer arranque guiado: te pregunta la carpeta de la biblioteca, la contraseña del modo desarrollador del Roku, (opcional) su IP y (opcional) la carpeta de tu música, y crea `config.json`. Se repite cuando quieras sin perder lo demás. `./cine` lo hace solo si aún no existe `config.json`. |
| `./cine` | Si el arranque automático está puesto: aplica tus cambios (p. ej. en `config.json`) y muestra las direcciones. Si no: arranca el servidor en esa ventana. |
| `./cine autoarranque` | Deja el servidor corriendo siempre y arrancando solo al iniciar sesión. |
| `./cine quitar-autoarranque` | Deja de arrancar solo. |
| `./cine estado` | Dice si está corriendo y en qué direcciones. |
| `./cine tailscale` | Publica la página en tu red Tailscale con https, para verla fuera de casa (ver [INSTALAR.md](INSTALAR.md#opcional-fuera-de-casa-con-tailscale)). |
| `./cine barra` / `./cine quitar-barra` | Pone o quita el ícono de la barra de menú (solo macOS). |
| `./cine catalogo` | Lista los videos y cómo llega cada uno a la TV. |
| `./cine instalar` | Reinstala la app en el Roku (hoy la única app de TV). |

### Biblioteca automática

Cada minuto el servicio revisa, sin que haga falta nada más:
- **Lo nuevo en la biblioteca** (suelto en `Biblioteca/`, o en `Películas/` o `Series/` sin el código): lo
  identifica (IMDb para películas, TVmaze para series) y lo mueve a su lugar con el formato de siempre:
  `Películas/Título (Año) {imdb-tt…}/…` y `Series/Serie (Año) {tvdb-…}/Season 01/Serie (Año) - S01E02 - Título.mkv`.
- **Descargas terminadas de Transmission** (`~/Downloads/Torrents`, o las carpetas de `"descargas"` en
  config.json): crea en la biblioteca un **enlace duro**, el mismo archivo con otro nombre, sin ocupar espacio
  extra. Transmission lo sigue compartiendo desde donde está; si borras el torrent, la película se queda.
  Se saltan los extras (Featurettes, Extras…), las muestras y lo que sigue bajando (`.part`).
- Lo que ya está en la biblioteca no se duplica. A lo nuevo se le bajan póster y sinopsis, y la TV se
  actualiza sola. Registro de lo hecho: `datos/organizador.json`.

### Doblaje latino para lo que no lo tiene

Si llega **otra versión** de una película o episodio que ya está en la biblioteca (por ejemplo, una
«Dual Latino» que bajaste en Transmission, o que dejaste en `Biblioteca/`) y trae el audio latino que a la
tuya le falta, el servicio toma **solo ese audio**, lo sincroniza con tu video y lo guarda junto a él como
`Película.latino.m4a`. En la TV y en la web aparece como una pista más: «Español (Latino) · agregado».
Tu video no se toca.

- Cómo se sincroniza (`mac/dubsync.py`): las dos versiones casi nunca empiezan igual (logos distintos) y
  las europeas corren un 4 % más rápido. Se compara el audio original de las dos (inglés con inglés) en 30
  puntos de la película; si la otra no lo trae, se compara la música y los efectos, que todos los doblajes
  comparten. Si los 30 puntos no cuentan la misma historia (otra edición, con escenas distintas), no se
  agrega nada y queda anotado por qué. Probado: la pista queda a menos de 30 ms de donde debe ir.
- Tarda 1–2 minutos por película, con prioridad baja. La web muestra «preparando doblaje de…» mientras tanto.
- La otra versión: si vino de Descargas, se queda ahí (Transmission la sigue compartiendo; bórrala desde
  Transmission cuando quieras). Si la dejaste en la biblioteca, se aparta a `~/Movies/Doblajes ya usados`.
- Lo que no tiene español lo encuentras con el filtro **Sin español** de Películas y Series en la TV. Registro:
  `datos/doblajes.json` (y `/api/dubs`). La sincronización usa numpy en su propio entorno
  (`~/Library/Application Support/cine-roku/doblaje`), que se instala solo la primera vez.
- Cualquier pista aparte con el mismo nombre del video (`Película.algo.m4a` o `.mka`) también aparece.

### Dónde empieza y termina la entrada de las series («Saltar intro»)

No hay una base pública con esos tiempos: el servicio los averigua comparando el audio de los episodios de
una misma temporada, porque la canción de entrada se repite en todos (`mac/introsync.py`, con las mismas
huellas de audio que el doblaje). Se busca lo que suena igual en varios episodios (de 15 s a 2½ min, que
empiece en los primeros 12 min, así que da igual si hay una escena antes); cada episodio se queda con el
tramo en el que coinciden más compañeros. Si no coinciden suficientes (un piloto sin entrada, un episodio
con una entrada especial), ese episodio queda sin marca: no se inventa.

- Corre solo, de a una temporada, con prioridad baja: 5 min después de arrancar y luego cada 10 min por si
  llegaron episodios. Una temporada solo se vuelve a revisar si cambió. Unas 18 temporadas (~160 episodios) tardan 2 min.
- Las marcas quedan en `datos/intros.json` (resumen en `/api/intros`; por video, `/api/marks?id=…`, que
  también da los capítulos de YouTube). En la TV sale un **aviso abajo a la derecha** («Saltar intro» o
  «Siguiente capítulo: …») con una línea que se vacía en 8 s: **OK** salta; ▶ pausa y ⏩/⏪ adelantan o atrasan
  10 s; cualquier otra tecla lo esconde. Nunca salta solo; si se vuelve a entrar al tramo, se ofrece otra vez.
- Para probar una temporada: `python3 pruebas/intro_temporada.py "<carpeta de la temporada>"`.

### Arranque automático (macOS)

`./cine autoarranque` registra un servicio de macOS (launchd, `~/Library/LaunchAgents/local.cine-roku.plist`)
que arranca al iniciar sesión y se relanza solo si se cae. macOS no deja a los servicios leer la carpeta
Documentos, así que el servicio corre desde una copia en `~/Library/Application Support/cine-roku`.
**Después de cambiar algo** (código o `config.json`), corre `./cine`: copia los cambios y reinicia el servicio.

El servicio también:
- busca el Roku cada minuto si no lo encontró (TV apagada, Wi-Fi que tarda en conectar);
- actualiza la app del Roku cuando cambia su código o la dirección IP de la computadora, **pero solo cuando la TV está
  en Inicio o en One TV sin reproducir** (instalar abre la app sola y te sacaría de Netflix/HBO);
- deja su registro en `~/Library/Logs/cine-roku.log`.

El progreso («Seguir viendo») y los idiomas preferidos se guardan en la computadora:
`~/Library/Application Support/cine-roku/datos/progreso.json`. El Roku reporta cada 10 s qué se ve y por dónde va.

### Ícono de la barra de menú (macOS)

App nativa en SwiftUI (`menubar/`), instalada en `~/Applications/One TV.app` y lanzada al iniciar sesión
por launchd (`local.cine-roku.barra`). Pregunta el estado al servidor cada 3 s y usa `launchctl` para encender
(`enable` + `bootstrap`) o apagar (`bootout` + `disable`) el servicio. `./cine` la recompila si cambias su código.

- **Si no ves el ícono**: en las Mac con muesca (la cámara), los íconos que no caben quedan escondidos detrás de ella.
  La app guarda su posición a la derecha de la barra para que no le pase, pero si la barra está muy llena
  quedan fuera otros. Quita los que no uses en Ajustes del Sistema → Barra de menús.
- **Abrir «One TV» desde Spotlight** muestra una ventanita con lo mismo que el menú (encender/apagar,
  abrir la página, registro), por si el ícono no está a la vista.

Las carpetas de videos deben estar fuera de Descargas, Documentos y Escritorio (por ejemplo en `~/Movies`).
Si no, macOS no deja leerlas en segundo plano y el registro lo avisa.

### Fuera de casa por Tailscale

`./cine tailscale` ejecuta `tailscale serve --bg --https=8766 http://127.0.0.1:8765`: la página queda en
`https://<nombre-de-tu-computadora>.<tu-red>.ts.net:8766` (la dirección real la muestra el comando) con certificado válido y **solo** para dispositivos de tu
tailnet (no es pública). Tailscale recuerda la configuración aunque reinicies. Para quitarla:
`tailscale serve --https=8766 off`.

## Qué hace por dentro

- `mac/`: el servidor, un programa en Python que corre en la computadora (hoy en macOS; el nombre de la carpeta viene de ahí).
  - `library.py`: busca los videos, limpia los títulos, los agrupa en filas y decide cómo llega cada uno al Roku.
  - `transcode.py`: arma al vuelo, en trozos, lo que el Roku no puede reproducir tal cual (ver abajo).
  - `server.py`: sirve el catálogo, los videos, portadas y subtítulos. Evita que la computadora se duerma mientras se ve algo.
  - `roku.py`: encuentra el Roku en la red, instala la app y le manda órdenes (control remoto por red, ECP).
  - `cine.py`: comandos, arranque automático, Tailscale e ícono de la barra.
  - `store.py`: progreso y preferencias de idioma.
  - `web/`: la página para elegir desde la computadora o el teléfono (cualquier navegador).
- `menubar/`: el ícono de la barra de menú (SwiftUI).
- `roku/`: la app de TV para Roku (BrightScript/SceneGraph); otras TV tendrán su propia carpeta. El servidor la instala o actualiza sola con la dirección
  actual de la computadora. `components/MainScene` es la pantalla (navegación en `MainScene.brs`, secciones en
  `Catalog.brs`, YouTube en `YouTube.brs`, reproducir y fila en `Playback.brs`) y usa componentes: `SideMenu`
  (menú lateral), `ContentRows` (filas), `PosterGrid` (cuadrícula), `DetailView` (ficha), `SearchView`,
  `Player` (video, aviso para saltar y lo siguiente), `ButtonRow`, `PosterItem`, `OptionItem` (listas del panel
  de idioma) y `EmptyState` (vacíos que enseñan). Sigue el sistema visual de [`DESIGN.md`](../DESIGN.md): **todos
  los colores y la letra** están en `components/Theme.brs` (`theme()` y `makeFont()`, con Big Shoulders Display
  y Archivo de `roku/fonts/`). Los íconos son PNG blancos (trazos de Lucide) que la app tiñe; se regeneran, con
  las piezas 9-patch, con `python3 pruebas/iconos_roku.py`.

### Cómo llega cada video a la TV

Medido en un Roku Streaming Stick (3840R, HD): no decodifica HEVC, ni audio Dolby (AC3/EAC3), DTS o AAC 5.1. Es lo
que el servidor supone de cualquier Roku (`mac/library.py`): un Roku 4K que sí decodifica HEVC recibiría convertido
algo que podría ver tal cual. Pendiente: que la app le diga al servidor qué decodifica.

| Modo | Cuándo | Calidad | Trabajo de la computadora |
|---|---|---|---|
| **Directo** | MP4/MKV con H.264 (hasta nivel 4.2) y audio AAC estéreo o MP3 | Original | Ninguno |
| **Video original, audio convertido** | El video es H.264 compatible pero el audio no (AC3, EAC3, DTS, AAC 5.1) o el contenedor no sirve (AVI con H.264, TS…) | **Video original, sin tocar** | Mínimo: copia el video y convierte solo el audio a AAC estéreo |
| **Conversión completa** | Video HEVC/H.265, H.264 de 10 bits o nivel 5, XviD, MPG, o archivos de más de 25 Mbps | Recodificado a H.264 (6 Mbps en 1080p) | Usa el chip de video de la computadora; con H.264/HEVC comunes todo el trabajo se queda en el chip (`scale_vt`), unas 3 veces menos procesador |

En los dos modos que convierten, el audio 5.1 se pasa a estéreo subiendo el volumen de los diálogos, y el video se
entrega en trozos (HLS). En el modo de video original, los cortes caen en los fotogramas clave del propio archivo.
Saltar o retomar a la mitad tarda menos de medio segundo. En la conversión completa los cortes son cada 6 s y saltar
tarda ~1 s.

`./cine catalogo` muestra la lista completa y el motivo de cada caso.

### En vivo (páginas web de eventos)

Pestaña **En vivo** de la web: pega el enlace de la página donde ves el evento → **Buscar video**. La computadora abre la
página en un Chrome invisible, cierra las ventanas emergentes, hace clic en el reproductor si hace falta y encuentra
el video (HLS, `.m3u8`) con los encabezados que exige la fuente (Referer, Origin, cookies). Queda guardado como canal:
- en la TV, sección **En vivo** del menú;
- en la web, sección **En vivo**: ver en la TV, ver en este dispositivo, cambiar el nombre (lápiz; Enter guarda,
  Esc cancela; la TV lo ve sola) o borrar. Si no escribes un nombre, se usa el título de la página, con « 2»,
  « 3»… si otro canal ya se llama así.

La búsqueda tarda hasta 45 s y sigue aunque cambies de sección o salgas de la app: al terminar, el resultado se
ve en la página y también como aviso. Si la página no tiene video (el evento aún no empieza), lo dice; en el
registro queda el enlace completo.

El video pasa por la computadora (`/live/<canal>/…`): se piden las listas y los trozos a la fuente con esos encabezados, se
reescriben las listas y se quita el disfraz de imagen que algunas páginas ponen a los trozos. Si el enlace caduca
(las fuentes suelen dar enlaces temporales), la computadora vuelve a abrir la página y lo busca de nuevo sola.
No funciona con video protegido con DRM (Netflix, apps oficiales) ni con páginas que bloquean navegadores automáticos.
Los canales se guardan en `~/Library/Application Support/cine-roku/datos/canales.json`. Requiere Google Chrome
(o Brave); otro navegador se puede indicar en `config.json` → `"navegador"`.

### Subtítulos

Se usan los `.srt` / `.vtt` junto al video (`Película.es.srt`, `Película.en.sdh.srt`…) y los que vienen dentro del MKV/MP4.
Los que son imagen (PGS, DVD) no se pueden mostrar.

**Desde internet (OpenSubtitles, como Plex):**
- En la web: ficha de la película → Idioma → **Cambiar** → **Buscar subtítulos en internet** → elige idioma → **Descargar**.
  Primero salen los **✓ sincronizados** (hechos para tu misma copia del archivo: se reconoce por su «huella»,
  el *moviehash*), luego el latino, los hechos por personas y los más descargados.
- En la TV: menú de la película → **Buscar subtítulos en español / en inglés**: baja el mejor y lo deja elegido.
- Se guardan junto al video como `Película.es.opensubtitles-latino.srt` (sirven para cualquier reproductor) y
  aparecen como «Español (Latino) · internet».
- Cupo: 5 descargas al día solo con la clave; 20 si pones usuario y contraseña de tu cuenta gratis en `config.json`.

**Solos, para toda la biblioteca** (`mac/subs_auto.py`): con la clave de OpenSubtitles puesta, la computadora baja
sola los subtítulos que faltan, sin que pidas nada, y aprovecha el cupo de cada día:
- **Qué:** cada película o capítulo que **no es en español** recibe subtítulos en **español** (de preferencia
  latino), en **inglés** y, si su idioma original es otro, también en **ese idioma** (una película japonesa: español,
  inglés y japonés). El idioma original sale de Wikidata (el mismo dato que marca la pista «(original)»); si no se
  sabe, el del audio principal.
- **Lo que ya tiene no se baja:** los subtítulos que vienen dentro del video y los que la biblioteca ya muestra en ese
  idioma. No cuentan los que son imagen (no se pueden mostrar) ni los forzados (solo traducen partes).
- **En qué orden:** primero todos los que faltan en español, después en inglés, después en el idioma original. En cada
  idioma, primero lo que se está viendo, lo de «Seguir viendo» y los 5 capítulos que siguen de esa serie; luego lo
  agregado en el último mes; luego lo demás, de lo más nuevo a lo más viejo.
- **Cuánto:** lee el cupo real de tu cuenta (al entrar dice cuántas descargas permite al día; cada descarga dice
  cuántas quedan y cuándo se renueva) y las gasta todas cada día **menos 2**, que quedan para cuando pidas uno a mano.
  Va despacio (la API acepta 5 consultas por segundo) y, si pide esperar o dice que se acabó el cupo, espera lo que
  diga. Cuando se acaba, sigue sola al renovarse.
- **Cuál elige:** primero el hecho para tu misma copia (la «huella» del archivo); si no hay, busca por el código de
  IMDb de la película o de la serie (el de la serie sale de su código de TheTVDB, por Wikidata) con temporada y
  capítulo. Entre varios: los hechos por personas, el latino, el que más se parece a la copia que tienes (BluRay,
  WEB-DL, el grupo que la publicó: usa también el nombre con que se bajó, que guarda el organizador) y el más
  descargado. Lo bajado se alinea solo con la voz (ver abajo).
- **Memoria:** `datos/subtitulos_automaticos.json` guarda qué se bajó, qué todavía no existe en OpenSubtitles (se
  vuelve a buscar en una semana, en dos días si es un estreno o se agregó hace poco, y cada vez espera el doble, hasta un
  mes), el cupo y cuántos se bajaron cada día. Si borras uno que bajó, no lo vuelve a bajar.
- **Cuándo:** 5 minutos después de arrancar y luego cada hora (o al renovarse el cupo), en un hilo aparte. Al final de
  cada tanda deja en el registro un resumen: «✓ Subtítulos automáticos: 18 bajados hoy (12 en español, 6 en inglés);
  faltan 240; …; siguen mañana a las 18:00». En la web, junto al estado de la TV: «subtítulos automáticos: 18 bajados
  hoy, faltan 240» (y en `/api/status` → `auto_subs`).
- **Apagarlo:** en `config.json`, `"opensubtitles": { …, "automaticos": false }`. Sin clave de OpenSubtitles no hace
  nada (lo dice una vez en el registro).
- El video nunca se toca y nunca se reemplaza un subtítulo que ya estaba (si el nombre está ocupado, se agrega «-2»).

**A tiempo, solos:** los subtítulos que no vienen dentro del video (los de internet y los `.srt`/`.vtt` que pones
junto al video) muchas veces son de otra versión y quedan corridos. One TV los alinea con la voz sin que hagas nada:
- Escucha dónde hay voz en el audio (en 5.1, el canal central) y la compara con cuándo hay una línea en pantalla
  (`mac/subsync_voz.py`). Corrige un desfase fijo, otra velocidad (23,976 / 24 / 25 cuadros por segundo) y saltos a
  medio video (una escena de más o de menos, por tramos como la herramienta *alass*); si al subtítulo le sobra una
  escena, quita esas líneas.
- Solo corrige si la coincidencia es clara; si no (por ejemplo, un subtítulo de otra película), lo deja como está.
- El archivo original no se toca: el alineado se guarda en la caché y es el que reciben la TV y la web, con el mismo
  nombre de pista. Si ya estaba a tiempo, se usa el original.
- Corre solo, con prioridad baja: unos minutos después de arrancar (una vez para los que ya están), al bajar uno y
  cada 2 minutos por si pusiste uno a mano. Tarda segundos por película. Lo que hizo con cada uno (qué corrigió,
  cuánto y con qué confianza) queda en `datos/subtitulos_alineados.json` y en el registro; no se repite si ni el
  subtítulo ni el video cambiaron. Usa el mismo entorno con numpy que el doblaje.

## Configuración (`config.json`)

`config.json` tiene claves y contraseñas, así que no se guarda en el repositorio (`.gitignore`). En una copia
nueva, `./cine configurar` lo crea preguntando lo mínimo (o `cp config.example.json config.json` y llenarlo a mano;
cada campo está explicado en docs/INSTALAR.md).

Todos los campos, con su explicación: [INSTALAR.md → Referencia de `config.json`](INSTALAR.md#referencia-de-configjson).

Tras editarlo, corre `./cine` para aplicarlo.

## Si algo falla

Los síntomas más comunes (con Roku y macOS, lo que hay hoy):

- **La TV dice que no encuentra la computadora**: la computadora está apagada, dormida o en otra red Wi-Fi, o el servicio no corre
  (`./cine estado`). La app reintenta sola cada 5 segundos.
- **La app desapareció del Roku** (tras restablecerlo o apagar el modo desarrollador): vuelve a activar el modo
  desarrollador con la misma contraseña (Inicio ×3, Arriba ×2, Derecha, Izquierda, Derecha, Izquierda, Derecha)
  y corre `./cine instalar`.
- **Se corta al cerrar la tapa de la laptop**: macOS duerme la computadora con la tapa cerrada. Déjala abierta (la pantalla
  puede apagarse; mientras se ve algo, la computadora no se duerme sola).
- **El teléfono no abre la página fuera de casa**: revisa que Tailscale esté encendido en el teléfono.
- Portadas, subtítulos extraídos e índices de fotogramas clave se guardan en `~/Library/Caches/cine-roku`
  (en Linux, `~/.cache/cine-roku`; se puede borrar sin problema).

Requisitos: macOS con `python3` y `ffmpeg` (`brew install ffmpeg`), Ubuntu 24.04 (`sudo apt install python3 python3-venv ffmpeg`;
ver [INSTALAR-UBUNTU.md](INSTALAR-UBUNTU.md)) o Windows 10 u 11 (Python y ffmpeg con winget, que `cine.cmd` ofrece
instalar; ver [INSTALAR-WINDOWS.md](INSTALAR-WINDOWS.md)), Roku en la misma red. Google Chrome o Brave solo para «En
vivo» (en Windows también Edge).

## Limitaciones conocidas

- **Servidor en macOS y en Ubuntu 24.04** (otras versiones de Linux con systemd probablemente sirvan; no se han
  probado). En Linux: arranque con systemd del usuario, el chip de video se elige al arrancar probando un segundo
  (NVENC, Quick Sync, VAAPI; todavía sin probar con hardware real) o el procesador (`libx264`), sin ícono en la barra
  de menú, y el servicio no puede impedir que un escritorio se suspenda. Docker (NAS): en prueba, ver [INSTALAR-DOCKER.md](INSTALAR-DOCKER.md).
- **Servidor en Windows 10 y 11**: arranque con una tarea del Programador de tareas al iniciar sesión (no antes: para
  eso Windows pide guardar la contraseña de la cuenta), el chip de video se elige igual que en Linux (NVENC, Quick
  Sync, AMF; sin probar con hardware real), sin ícono en la barra de menú. Datos, caché y registro en
  `%LOCALAPPDATA%\cine-roku`; lo propio de Windows está en `mac/winapi.py` y `mac/windowsservice.py`.
- **Solo Roku** como app de TV (y la web en cualquier navegador); Google TV, Android TV y Fire TV vienen después. El
  modo desarrollador del Roku admite una sola app instalada a mano a la vez: One TV reemplaza a cualquier otra que hayas
  instalado así.
- **Un Roku por servidor**: si hay varios en la red, usa el primero que encuentra (o el de `roku_ip`).
- **El español latino** es el idioma que se prefiere al elegir audio y sinopsis cuando hay varios (`mac/library.py`,
  `mac/metadata.py`).
- `yt-dlp` (YouTube) y `numpy` (doblaje latino, «Saltar intro» y subtítulos a tiempo) se instalan y actualizan
  solos desde PyPI, en entornos aparte, sin versión fija.

## Seguridad

- El servidor escucha en toda la red de la casa (la TV lo necesita) y **no tiene contraseña**: no abras su puerto a
  internet. Para verlo fuera de casa, usa Tailscale (`./cine tailscale`). Para que solo lo vea esta computadora:
  `"escuchar": "127.0.0.1"` en `config.json`.
- Solo acepta órdenes en JSON y no da permiso a otros sitios web: una página cualquiera abierta en un navegador de la
  casa no puede usar su API.
- Las direcciones que reescribe en las listas para la TV van firmadas con una clave de esta computadora
  (`datos/clave_enlaces`): solo abre lo que él mismo puso en una lista, y solo de internet.
