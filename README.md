# One TV

Tus películas, series, música y YouTube sin anuncios, en tu TV y en tu teléfono. Con tus propios archivos, en tu casa,
sin cuentas ni suscripciones.

![One TV](docs/capturas/laptop-inicio.png)

## Empieza aquí

Instálalo en la computadora que guarda tus videos (tiene que quedarse encendida mientras ves algo):

[![Descargar One TV](docs/capturas/boton-descargar.svg)](https://julai1433.github.io/one-tv/)

El botón reconoce tu computadora y te da el instalador para abrir con doble clic. ¿Prefieres la terminal?

- **Mac y Linux:** `bash -c "$(curl -fsSL https://raw.githubusercontent.com/julai1433/one-tv/main/instalar.sh || wget -qO- https://raw.githubusercontent.com/julai1433/one-tv/main/instalar.sh)"`
- **Windows** (en PowerShell): `irm https://raw.githubusercontent.com/julai1433/one-tv/main/windows/instalar.ps1 | iex`
- **NAS** (Synology, Unraid, QNAP, TrueNAS…): el mismo comando de Mac y Linux, por SSH; necesita Docker, y si no lo
  tiene te dice cómo agregarlo. ¿Sin terminal? [Con clics, desde el NAS](docs/INSTALAR-DOCKER.md).

Al terminar se abre un asistente en el navegador que te guía en 4 pasos: tus videos, tu TV, extras y listo.

La primera vez, la computadora puede avisar que el instalador no es de una tienda: en Mac, *Configuración del Sistema ›
Privacidad y seguridad › Abrir de todos modos*; en Windows, *Más información › Ejecutar de todas formas*.

## Qué hace

- Tus películas y series con pósters y sinopsis, y «Seguir viendo» desde cualquier aparato.
- Ve cualquier video: lo que tu TV no puede abrir tal cual, se convierte al momento.
- Subtítulos que se bajan solos y se ajustan a la voz.
- YouTube sin anuncios, con tus suscripciones y tus listas.
- Tu música, en la TV o en el teléfono.
- Una sola fila para todo lo que quieres ver después.

| | | |
|---|---|---|
| ![Inicio en la TV](docs/capturas/tele-inicio.jpg) | ![YouTube en la computadora](docs/capturas/laptop-youtube.png) | ![Música en la TV](docs/capturas/tele-escuchando.jpg) |

## Dónde funciona

| | Listo | En prueba |
|---|---|---|
| **Computadora** | Mac · Linux | Windows · NAS |
| **TV** | Roku | Google TV · Android TV · Fire TV |
| **Teléfono y computadora** | Cualquier navegador | |

## Ayuda

- [Tu caso, paso a paso](docs/GUIA-RAPIDA.md): ya uso Plex, tengo un disco externo, verlo fuera de casa…
- [Si algo no funciona](docs/DETALLES.md#si-algo-falla) · [Teclas de la TV](docs/DETALLES.md#teclas-de-la-tv)
- **Privacidad:** todo se queda en tu casa. One TV no tiene cuentas ni servidores propios.

## Para quien quiera ayudar

- [Probar One TV en tu TV o tu computadora](docs/PROBAR.md)
- [Contribuir](CONTRIBUTING.md) · [Hoja de ruta](docs/HOJA_DE_RUTA.md)

## Licencia

Código abierto, licencia MIT ([LICENSE](LICENSE)). Usa obras de otros: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
One TV no está afiliado a YouTube, Google, Roku ni Amazon.

---

*English:* One TV plays your own movies, shows and music, plus ad-free YouTube, on your TV and phone, from a computer
at home. No accounts, no cloud. Install it with the download button above (or the one-line command for your system);
a setup wizard opens in your browser when it finishes.
