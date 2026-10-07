# One TV

Tus películas, tus series, tu música y YouTube sin anuncios, en la TV, en la computadora y en el teléfono. Un
programa en una computadora de tu casa (el servidor) los prepara; una app en tu TV y una página web en cualquier
navegador los muestran, por tu propio Wi-Fi. Sin cuentas, sin nube y sin suscripciones: todo pasa entre tus aparatos y
lo que se ve es tuyo (One TV no trae ni descarga contenido).

> **Qué funciona hoy**: el servidor corre en **macOS** y en **Ubuntu 24.04** (en **Windows 10 y 11**, en prueba), y la app de TV
> es para **Roku**, y para **Google TV, Android TV y Fire TV** en su primera versión, en prueba
> ([guía](docs/INSTALAR-GOOGLE-TV.md)); la **web** funciona en cualquier navegador. Lo que viene: la
> [hoja de ruta](docs/HOJA_DE_RUTA.md). La meta de todo el proyecto: que cualquiera lo instale y lo use, sin saber de
> programación.

![One TV en la computadora: Inicio con «Seguir viendo» y las películas en español](docs/capturas/laptop-inicio.png)

*English summary at the end.*

## Qué hace

**Tu biblioteca**
- Películas y series con pósters, sinopsis en español, temporadas y «Seguir viendo» (donde te quedaste, en cualquier
  aparato).
- Lo que termina de bajarse (por ejemplo en Transmission) entra solo a la biblioteca en menos de un minuto, ya
  ordenado y con su póster; no se mueve de su lugar, así se sigue compartiendo.
- Cualquier formato: lo que la TV no entiende se convierte al momento (con el chip de video de la computadora cuando lo tiene).
- Doblaje latino automático: si llega otra versión de algo que ya tienes con audio en español latino, se le agrega a
  la tuya como una pista más, sincronizada.
- «Saltar intro» en las series (se detecta comparando el audio de los episodios) y subtítulos de internet, que se
  bajan solos (español, inglés y el idioma original, aprovechando el cupo diario) y se alinean solos con la voz si
  son de otra versión.

**YouTube, sin anuncios**
- Busca, ve canales y listas; con tu propia copia de datos de Google (Takeout) aparecen tus suscripciones, tus
  listas y tu historial. Nunca se entra a tu cuenta.
- Siempre con el audio original; los doblajes automáticos de YouTube, solo si los pides.
- Recomendaciones que tienen que ver con lo que ves; «No me interesa» y «Silenciar canal» en cada video.
- Transmisiones en vivo, capítulos, Favoritos y tus propias listas, y guardar videos para verlos sin internet.

**Tu música**
- Artistas, álbumes, canciones y tus listas (`.m3u8`), con sus portadas. Suena en la computadora como en Spotify
  (abajo, mientras navegas) o en la TV con la portada en grande.

**Fila de reproducción**
- Una sola fila para todo (películas, episodios, YouTube y canciones): lo que agregas desde cualquier aparato sigue
  al terminar lo que ves, en la TV o en la computadora.

## Cómo funciona

```
 Servidor (una computadora de tu casa)  ──Wi-Fi──▶  app de TV      en la TV (hoy: Roku)
  Python + ffmpeg                       ──────────▶  página web     en la computadora y el teléfono (también fuera de casa, con Tailscale)
```

- **El servidor** es Python sin librerías externas, más `ffmpeg` (y `yt-dlp` para YouTube, que se instala y
  actualiza solo). Arranca con la computadora. Hoy corre en macOS y en Ubuntu; en Windows, en prueba.
- **La app de la TV** se instala desde el propio servidor. En Roku, con el modo desarrollador (gratis, sin tienda).
- **La web** es una sola página, servida por el servidor; en el teléfono se puede agregar a la pantalla de inicio.

## Instalar

Hoy necesitas: una computadora con **macOS** (14 o más nuevo, con Python 3.9+ y ffmpeg 7+), con **Ubuntu 24.04** o con
**Windows 10 u 11** (en prueba) como servidor, un **Roku** en la misma red como TV, y tus videos. En cualquier otro aparato con
navegador funciona la página web. **Google TV, Android TV y Fire TV** (primera versión, en prueba): se instala con
«Downloader», sin cables, con **[docs/INSTALAR-GOOGLE-TV.md](docs/INSTALAR-GOOGLE-TV.md)**. La guía paso a
paso, sin suponer nada: **[docs/INSTALAR.md](docs/INSTALAR.md)** (Mac), **[docs/INSTALAR-UBUNTU.md](docs/INSTALAR-UBUNTU.md)**
(Ubuntu), **[docs/INSTALAR-WINDOWS.md](docs/INSTALAR-WINDOWS.md)** (Windows, con un solo comando o doble clic) y
**[docs/INSTALAR-DOCKER.md](docs/INSTALAR-DOCKER.md)** (un NAS o cualquier Linux con Docker, en prueba).

> **¿Tu biblioteca ya la usa Plex, Jellyfin u otro programa (por ejemplo en un NAS)?** Por ahora no le des esa carpeta
> a One TV: One TV acomoda (mueve y renombra) los videos que encuentra sueltos en su carpeta, y eso puede desordenar la
> de otro programa. Ya viene una versión que la usa solo para leer, sin tocar nada.

Para quien ya sabe (macOS):

```
brew install ffmpeg
git clone https://github.com/julai1433/one-tv.git && cd one-tv
./cine            # la primera vez pregunta lo mínimo (carpeta de videos, Roku, música) y crea config.json
```

## En la TV

| | | |
|---|---|---|
| ![Inicio en la TV, con «Seguir viendo»](docs/capturas/tele-inicio.jpg) | ![La ficha de un capítulo en la TV](docs/capturas/tele-ficha.jpg) | ![YouTube en la TV](docs/capturas/tele-youtube.jpg) |
| ![El panel del reproductor: siguiente de la fila, la fila y lo visto](docs/capturas/tele-panel.jpg) | ![Música en la TV](docs/capturas/tele-musica.jpg) | ![Escuchando un álbum en la TV](docs/capturas/tele-escuchando.jpg) |

*Con la biblioteca de ejemplo de `pruebas/datos_demo.py`. Las capturas del Roku no incluyen la imagen del video (sale
negra); en la TV sí se ve.*

Con el control remoto del Roku (otras TV tendrán su equivalente):

| Tecla | En las filas | Viendo algo |
|---|---|---|
| **OK** | abre la ficha | pausa o sigue |
| **▶** | reproduce sin abrir la ficha | pausa o sigue |
| **▼** | moverse | muestra la barra de avance; otra vez, el panel: «Siguiente de la fila», «Audio y subtítulos», la fila y lo visto (con música, canción anterior y siguiente) |
| **▲** | moverse | del panel a la barra; de la barra, oculta todo |
| **‹ ›** | moverse | el primer toque muestra la barra; después te mueves en ella (por capítulos si el video los tiene; si no, cada vez más rápido) |
| **⏪ ⏩** | una pantalla arriba o abajo | −15 s / +15 s |
| **\*** | opciones de esa tarjeta: verla, a la fila, a una lista, «No me interesa», «Silenciar canal» | (el Roku la usa para sus propios ajustes) |
| **Atrás** | cierra lo de encima; en una sección, abre el menú | oculta la barra o el panel; después sale (se guarda dónde te quedaste) |

La barra y el panel se ocultan solos a los pocos segundos si sigue reproduciendo; en pausa se quedan.

## En la computadora y el teléfono

`http://<dirección-de-la-computadora>:8765` desde cualquier navegador de la casa (`./cine estado` muestra la dirección). La ficha de cada cosa se abre encima, sin
perder tu lugar; cada video tiene su menú **⋯**; lo que ves aquí se puede minimizar y seguir abajo, y al volver a
abrir la página te ofrece seguir donde te quedaste. También controla la TV: lo que se ve, la fila y lo visto.

| Inicio | YouTube, sin anuncios | La ficha, encima |
|---|---|---|
| ![Inicio](docs/capturas/laptop-inicio.png) | ![YouTube con tus canales y lo nuevo de cada uno](docs/capturas/laptop-youtube.png) | ![La ficha de una película](docs/capturas/laptop-ficha.png) |

| Películas | Una serie | Un canal de YouTube |
|---|---|---|
| ![Películas](docs/capturas/laptop-peliculas.png) | ![Una serie con sus capítulos](docs/capturas/laptop-serie.png) | ![Un canal de YouTube](docs/capturas/laptop-youtube-canal.png) |

| Música | Un álbum | Viendo en la computadora |
|---|---|---|
| ![Música](docs/capturas/laptop-musica.png) | ![Un álbum](docs/capturas/laptop-album.png) | ![Una película reproduciéndose en la computadora](docs/capturas/laptop-reproduciendo.png) |

| Controlando la TV: una película | Controlando la TV: música | Un video de YouTube |
|---|---|---|
| ![El panel «En la TV» con una película y la fila](docs/capturas/laptop-tele-pelicula.png) | ![El panel «En la TV» con música](docs/capturas/laptop-tele-musica.png) | ![La ficha de un video de YouTube](docs/capturas/laptop-youtube-video.png) |

En el teléfono (390 px):

<img src="docs/capturas/telefono-inicio.png" alt="Inicio en el teléfono" width="190"> <img src="docs/capturas/telefono-youtube.png" alt="YouTube en el teléfono" width="190"> <img src="docs/capturas/telefono-peliculas.png" alt="Películas en el teléfono" width="190"> <img src="docs/capturas/telefono-musica.png" alt="Música en el teléfono" width="190"> <img src="docs/capturas/telefono-tele-musica.png" alt="El panel «En la TV» en el teléfono" width="190">

*Las capturas usan una biblioteca de ejemplo, sin datos de nadie: películas y una serie de dominio público (tramos de
[Internet Archive](https://archive.org)), música de Bach, Chopin y Beethoven en grabaciones CC0 o de dominio público
(Kimiko Ishizaka y [Musopen](https://musopen.org)) con portadas de pinturas de dominio público (Wikimedia Commons), y
suscripciones a canales públicos de NASA, ESA, el telescopio James Webb y Blender. Las genera
`python3 pruebas/datos_demo.py capturas docs/capturas`; las fuentes están en los comentarios de ese archivo.*

## Privacidad y seguridad

Todo vive en la computadora que hace de servidor (en macOS, `~/Library/Application Support/cine-roku`). One TV no tiene servidores propios ni manda tus
datos a nadie. Solo se conecta a internet para pósters y sinopsis (IMDb, TVmaze, Wikipedia), YouTube (los videos que
pides, sin tu cuenta) y, si lo configuras, subtítulos (OpenSubtitles). El servidor no tiene contraseña: es para la red
de tu casa; no abras su puerto a internet (para verlo fuera, Tailscale). Más en
[docs/DETALLES.md](docs/DETALLES.md#seguridad).

## Hoja de ruta

Ya funciona: el servidor en **Ubuntu** ([guía](docs/INSTALAR-UBUNTU.md)). En prueba: el servidor en **Windows** ([guía](docs/INSTALAR-WINDOWS.md)).
Lo que sigue, en este orden (detalles y el porqué en [docs/HOJA_DE_RUTA.md](docs/HOJA_DE_RUTA.md)):

1. La app para **Google TV, Android TV y Fire TV**: primera versión, en prueba ([guía](docs/INSTALAR-GOOGLE-TV.md));
   falta lo que la app del Roku tiene de más (buscar, En vivo, canales de YouTube…).
2. **Compartir tu biblioteca con aparatos fuera de tu red** (familia y amigos, también fuera de casa).

Además: **Apple TV**, y **varios videos a la vez** en la misma pantalla (está hecho, pero archivado hasta pulirlo). Siempre
con la misma meta: lo más sencillo posible, que se instale y se use sin terminal donde se pueda.

## Más

- [docs/INSTALAR.md](docs/INSTALAR.md): instalar, paso a paso.
- [docs/DETALLES.md](docs/DETALLES.md): comandos, cómo funciona por dentro, configuración y qué hacer si algo falla.
- [docs/HOJA_DE_RUTA.md](docs/HOJA_DE_RUTA.md): lo que viene.
- [DESIGN.md](DESIGN.md): colores, letras y piezas de la interfaz.
- Pruebas: `python3 -m unittest discover -s pruebas -p 'test_*.py'` (sin red ni TV). En `pruebas/LEEME.md`, las
  que usan Chrome sin ventana o la TV.

## Contribuir

Se reciben arreglos y funciones nuevas (de personas o de agentes): ver [CONTRIBUTING.md](CONTRIBUTING.md); los agentes
de IA, además, [AGENTS.md](AGENTS.md). Cada pull request corre solo las pruebas.

**¿Tienes Windows, Ubuntu o una TV con Google TV, Android TV o Fire TV?** Ayúdanos a probarlo: [docs/PROBAR.md](docs/PROBAR.md).

## Licencia y créditos

Código bajo la licencia MIT ([LICENSE](LICENSE)). Usa obras de otros (hls.js, íconos de Lucide, letras con licencia
OFL): ver [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Necesita [ffmpeg](https://ffmpeg.org) y usa
[yt-dlp](https://github.com/yt-dlp/yt-dlp), que se instalan aparte. YouTube es marca de Google y Roku de Roku, Inc.;
One TV no está afiliado a ellos.

---

## English summary

One TV is a home media server for your own movies, TV shows and music, plus ad-free YouTube. A server program runs on
a computer at home; a TV app and any web browser show everything over your own Wi-Fi. No accounts or cloud: everything
stays between your devices. **Today the server runs on macOS and Ubuntu 24.04 (Windows 10/11 support is being tested), and the TV app is for
Roku** (sideloaded in developer mode), with a first test version for Google TV / Android TV / Fire TV installed with
the Downloader app (`docs/INSTALAR-GOOGLE-TV.md`); the web page works in any browser. Next: sharing your library outside
your network (see `docs/HOJA_DE_RUTA.md`). Movies and
shows get posters, synopses, resume points, automatic organizing of finished downloads, on-the-fly transcoding (the
computer's video chip when there is one), automatic Latin Spanish dub syncing from another release, intro skipping and
subtitles. YouTube works without signing in (import a Google Takeout for subscriptions, playlists and history), always
with the original audio, with relevant recommendations you can tune, live streams, chapters and offline saving. Music
shows artists, albums and `.m3u8` playlists with cover art. One shared play queue for everything. The guiding goal is
simplicity: anyone should be able to install and use it, no terminal or AI tooling required where possible.
Setup: macOS `brew install ffmpeg`, clone, `./cine` (guided first run); full guides in Spanish in `docs/INSTALAR.md`
(macOS), `docs/INSTALAR-UBUNTU.md` (Ubuntu) and `docs/INSTALAR-WINDOWS.md` (Windows: one PowerShell command, or
double-click `cine.cmd`). Contributors (people and AI agents): `CONTRIBUTING.md` and `AGENTS.md`.
