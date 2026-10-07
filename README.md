# One TV

Tus películas, tus series, tu música y YouTube sin anuncios, en la TV, en la computadora y en el teléfono. Una Mac
de tu casa hace de servidor y un Roku los muestra en la TV, por tu propio Wi-Fi. Sin cuentas, sin nube y sin
suscripciones: todo pasa entre tus aparatos y lo que se ve es tuyo (One TV no trae ni descarga contenido).

*English summary at the end.*

## Qué hace

**Tu biblioteca**
- Películas y series con pósters, sinopsis en español, temporadas y «Seguir viendo» (donde te quedaste, en cualquier
  aparato).
- Lo que termina de bajarse (por ejemplo en Transmission) entra solo a la biblioteca en menos de un minuto, ya
  ordenado y con su póster; no se mueve de su lugar, así se sigue compartiendo.
- Cualquier formato: lo que la TV no entiende se convierte al momento con el chip de video de la Mac.
- Doblaje latino automático: si llega otra versión de algo que ya tienes con audio en español latino, se le agrega a
  la tuya como una pista más, sincronizada.
- «Saltar intro» en las series (se detecta comparando el audio de los episodios) y subtítulos de internet.

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
 Mac (servidor)  ──Wi-Fi──▶  Roku (app One TV)          en la TV
  Python + ffmpeg  ──────▶  página web (Chrome, Safari)  en la computadora y el iPhone (también fuera de casa, con Tailscale)
```

- **El servidor** es Python sin librerías externas, más `ffmpeg` (y `yt-dlp` para YouTube, que se instala y
  actualiza solo). Arranca con la computadora.
- **La app de la TV** se instala en el Roku desde la propia Mac (modo desarrollador del Roku: gratis, sin tienda).
- **La web** es una sola página, servida por la Mac; en el iPhone se puede agregar a la pantalla de inicio.

## Instalar

Necesitas una Mac (macOS 14 o más nuevo, con Python 3.9+ y ffmpeg 7+) y un Roku en el mismo Wi-Fi, y tus videos. Por ahora el servidor solo
corre en macOS y la app de TV es solo para Roku (en cualquier otra TV o aparato funciona la página web); Linux,
Docker y Google TV están en la hoja de ruta. La guía paso a paso, sin suponer
nada, está en **[docs/INSTALAR.md](docs/INSTALAR.md)**. Para quien ya sabe:

```
brew install ffmpeg
git clone https://github.com/julai1433/one-tv.git && cd one-tv
./cine            # la primera vez pregunta lo mínimo (carpeta de videos, Roku, música) y crea config.json
```

## En la TV

| Tecla | En las filas | Viendo algo |
|---|---|---|
| **OK** | abre la ficha | el panel: barra de avance, botones, fila y lo visto |
| **▶** | reproduce sin abrir la ficha | pausa o sigue |
| **‹ ›** | moverse | capítulo anterior o siguiente (sin capítulos, −10 s / +10 s; con música, canción) |
| **⏪ ⏩** | una pantalla arriba o abajo | −15 s / +15 s |
| **▼** | moverse | la fila de reproducción, a un lado (OK: verlo ya) |
| **\*** | opciones de esa tarjeta: verla, a la fila, a una lista, «No me interesa», «Silenciar canal» | (el Roku la usa para sus propios ajustes) |
| **Atrás** | cierra lo de encima; en una sección, abre el menú | salir (se guarda dónde te quedaste) |

## En la computadora y el teléfono

`http://<ip-de-la-mac>:8765` desde cualquier navegador de la casa. La ficha de cada cosa se abre encima, sin
perder tu lugar; cada video tiene su menú **⋯**; lo que ves aquí se puede minimizar y seguir abajo, y al volver a
abrir la página te ofrece seguir donde te quedaste. También controla la TV: lo que se ve, la fila y lo visto.

## Privacidad y seguridad

Todo vive en tu Mac (`~/Library/Application Support/cine-roku`). One TV no tiene servidores propios ni manda tus
datos a nadie. Solo se conecta a internet para pósters y sinopsis (IMDb, TVmaze, Wikipedia), YouTube (los videos que
pides, sin tu cuenta) y, si lo configuras, subtítulos (OpenSubtitles). El servidor no tiene contraseña: es para la red
de tu casa; no abras su puerto a internet (para verlo fuera, Tailscale). Más en
[docs/DETALLES.md](docs/DETALLES.md#seguridad).

## Hoja de ruta

- **Google TV y Android TV** (Chromecast con Google TV, Nvidia Shield…) con la misma app que servirá para **Fire TV**.
- **Apple TV**.
- Servidor también en **Windows y Linux**.
- **Varios videos a la vez** en la misma pantalla: está hecho, pero archivado hasta pulirlo.

## Más

- [docs/INSTALAR.md](docs/INSTALAR.md): instalar, paso a paso.
- [docs/DETALLES.md](docs/DETALLES.md): comandos, cómo funciona por dentro, configuración y qué hacer si algo falla.
- [DESIGN.md](DESIGN.md): colores, letras y piezas de la interfaz.
- Pruebas: `python3 -m unittest discover -s pruebas -p 'test_*.py'` (sin red ni Roku). En `pruebas/LEEME.md`, las
  que usan Chrome sin ventana o la TV.

## Contribuir

Se reciben arreglos y funciones nuevas (de personas o de agentes): ver [CONTRIBUTING.md](CONTRIBUTING.md). Cada pull
request corre solo las pruebas.

## Licencia y créditos

Código bajo la licencia MIT ([LICENSE](LICENSE)). Usa obras de otros (hls.js, íconos de Lucide, letras con licencia
OFL): ver [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Necesita [ffmpeg](https://ffmpeg.org) y usa
[yt-dlp](https://github.com/yt-dlp/yt-dlp), que se instalan aparte. YouTube es marca de Google y Roku de Roku, Inc.;
One TV no está afiliado a ellos.

---

## English summary

One TV turns a Mac into a home media server for your own movies, TV shows and music, plus ad-free YouTube, and
plays them on a TV through a Roku app (sideloaded, developer mode) and on any browser at home (laptop, iPhone).
No accounts or cloud: everything stays between your devices. Movies and shows get posters, synopses, resume points,
automatic organizing of finished downloads, on-the-fly transcoding with the Mac's video chip, automatic Latin
Spanish dub syncing from another release, intro skipping and subtitles. YouTube works without signing in (import a
Google Takeout for subscriptions, playlists and history), always with the original audio, with relevant
recommendations you can tune (“not interested”, mute channel), live streams, chapters and offline saving. Music
shows artists, albums and `.m3u8` playlists with cover art. One shared play queue for everything.
Setup: `brew install ffmpeg`, clone, `./cine` (guided first run); full guide in Spanish in `docs/INSTALAR.md`.
Next: a Google TV / Android TV app (also for Fire TV), Apple TV, and a Windows/Linux server.
