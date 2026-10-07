# Avisos de terceros

One TV incluye o usa estas obras de otros. Sus licencias completas están en [`LICENSES/`](LICENSES/) o junto a los
archivos.

| Qué | Dónde se usa | Licencia |
|---|---|---|
| [hls.js](https://github.com/video-dev/hls.js) 1.7.3 (© Dailymotion) | `mac/web/hls.min.js` (la web reproduce HLS en Chrome) | Apache 2.0: [`LICENSES/hls.js.txt`](LICENSES/hls.js.txt) y [`LICENSES/Apache-2.0.txt`](LICENSES/Apache-2.0.txt) |
| Íconos de [Lucide](https://lucide.dev) (y Feather) | trazos SVG en `mac/web/index.html`; PNG en `roku/images/icons/` (los genera `pruebas/iconos_roku.py`); la app de Android TV usa esos mismos PNG | ISC / MIT: [`LICENSES/lucide.txt`](LICENSES/lucide.txt) |
| [qrcodegen](https://www.nayuki.io/page/qr-code-generator-library) 1.8.0 (© Project Nayuki) | `mac/qrcodegen.py` (el código QR para compartir un video desde la TV) | MIT: [`LICENSES/qrcodegen.txt`](LICENSES/qrcodegen.txt) |
| [AndroidX/Jetpack](https://developer.android.com/jetpack/androidx) (Compose, Activity, Core, Lifecycle), [Media3/ExoPlayer](https://github.com/androidx/media) 1.11, Kotlin y kotlinx.coroutines | dentro de la app de Android TV (`androidtv/`; se bajan al compilar); `androidtv/gradle/wrapper/gradle-wrapper.jar` (Gradle) | Apache 2.0: [`LICENSES/Apache-2.0.txt`](LICENSES/Apache-2.0.txt) |
| Letras [Archivo](https://fonts.google.com/specimen/Archivo) y [Big Shoulders Display](https://fonts.google.com/specimen/Big+Shoulders+Display) | `mac/web/fonts/`, `roku/fonts/` (la app de Android TV las toma de ahí al compilar) | SIL Open Font License 1.1: `OFL-*.txt` junto a cada letra |

Programas que One TV usa pero **no incluye** (se instalan aparte): [ffmpeg](https://ffmpeg.org) (LGPL/GPL según
cómo se haya compilado), [yt-dlp](https://github.com/yt-dlp/yt-dlp) (Unlicense; One TV lo instala solo en un entorno
propio), [numpy](https://numpy.org) (BSD; solo para el doblaje latino), Google Chrome o Brave (solo para «En vivo») y
Tailscale (opcional).

YouTube y su logotipo, Android, Google TV y Android TV son marcas de Google LLC; Roku es marca de Roku, Inc.; Fire TV
es marca de Amazon.com, Inc. One TV no está afiliado a ellos.
