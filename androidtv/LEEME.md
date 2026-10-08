# One TV para Google TV, Android TV y Fire TV

La app de la TV de One TV para televisores y aparatos con Android: Google TV (Chromecast con Google TV, TV con Google
TV), Android TV y Fire TV. Se ve y se maneja **igual que la del Roku** (`roku/`): mismas secciones, colores, letras,
textos y teclas del control.

## Qué hace

- **Se conecta sola**: al abrirla busca la computadora con One TV en la red de la casa y la recuerda (su dirección y su
  nombre). Si la computadora cambia de dirección o la TV cambia de Wi-Fi, la vuelve a buscar sola (la misma, por su
  nombre; nunca se pasa sola a otra). Si no la encuentra, deja buscar otra vez o escribir la dirección con el control.
- **Varias computadoras con One TV** (por ejemplo, una computadora y un NAS): si encuentra más de una y ninguna es la
  de antes, pregunta cuál, con el nombre de cada una (`nombre` de `/api/status`) y cuántos videos tiene. Para cambiar
  después: Fila de reproducción › Ajustes generales › **Computadora** › «Cambiar» (o «Elegir otra computadora» en
  «No encuentro la computadora»). Al cambiar, se despide de la anterior (`/api/tv/adios`) y carga la nueva desde Inicio
  (`Computadoras.kt`).
- **Buscar, Inicio, En español, Películas, Series, YouTube, Música, En vivo y Fila de reproducción**, con el menú
  lateral, las filas de pósters, la ficha («Continuar desde…», «A continuación», «Al final de la fila» y el panel
  «Idioma» con audio y subtítulos en dos columnas y «Buscar subtítulos en internet») y la página de cada serie.
- **Buscar** con el teclado de la TV (y el micrófono del control, si tiene): en la biblioteca mientras se escribe y,
  con un botón, en YouTube («Solo en vivo» y «Cargar más resultados»).
- **OK sostenido** hace lo de la tecla ✱ del Roku (en Fire TV también la tecla ☰): las opciones de una tarjeta (verla,
  a la fila, a una lista o a Favoritos, «No me interesa», «Silenciar canal»), mover o quitar un video de la fila, y en
  la ficha la sinopsis completa con los detalles técnicos.
- **Reproductor** con las teclas del Roku: OK pausa; ▼ muestra la barra y otro ▼ abre el panel; ▲ regresa; ◀ ▶ la
  primera vez muestran la barra y después mueven la posición (por capítulos en YouTube); ⏪ ⏩ 15 segundos; Atrás
  oculta lo de encima y luego sale. El panel tiene «Siguiente de la fila», «Audio y subtítulos», la fila y lo visto
  hace poco. Sigue donde te quedaste y avisa a la computadora por dónde va (igual que el Roku), así funcionan
  «Seguir viendo» y la barra «En la TV» de la web. Al terminar un episodio, cuenta atrás para el siguiente. Ofrece
  **Saltar intro** (las marcas de la computadora), dice el nombre de cada capítulo de YouTube al empezar, salta con
  aviso un video de YouTube que ya no existe y da por terminado lo que se queda a décimas del final.
- **YouTube** como en el Roku: las filas, la página de cada canal (Anclar, Silenciar canal y Volver a mostrar) y de
  cada lista (Reproducir todo, A la fila), la ficha de un video (Favorito, Agregar a lista, Compartir con código QR,
  No me interesa, Silenciar canal), el audio original siempre y el doblaje solo si se pide («Audio y subtítulos»), y
  «Cómo traer tu YouTube» cuando la computadora todavía no tiene tu cuenta.
- **Música** (tus listas, lo agregado hace poco, artistas y álbumes; la página del álbum; escuchar con la portada y lo
  que sigue) y **En vivo** (los canales que agregas en la web).
- **Ajustes generales** en la Fila de reproducción: «Al terminar la fila», «Mostrar el nombre del capítulo», los
  canales silenciados y buscar películas y series nuevas.
- **La computadora la maneja como al Roku** (`control/Ordenes.kt`): mientras la app está a la vista deja una consulta
  esperando en el servidor (`GET /api/tv/ordenes?device_id=…&nombre=…`, hasta 25 s; `mac/teles.py`) y hace lo que le
  mandan con lo que ya tiene: ver algo (película, capítulo, YouTube, música, En vivo), pausa o sigue, ir a un segundo,
  audio y subtítulos, canción anterior o siguiente, salir y actualizar. Son las mismas órdenes que recibe el Roku
  (`onInputArgs` en `roku/components/MainScene.brs`). Al irse al fondo avisa (`POST /api/tv/adios`) y deja de estar
  «conectada». Si la computadora ofrece una versión más nueva de la app (`/api/tv/app`), lo avisa al abrirla.

No usa nada de Google Play Services: solo bibliotecas de AndroidX/Jetpack y Media3 (licencia Apache 2.0). Las letras y
los íconos son los de `roku/fonts` y `roku/images/icons` (no hay otra copia).

## Compilar

Necesitas Java 17 o más nuevo y el SDK de Android (variable `ANDROID_HOME`, o un `local.properties` con `sdk.dir`; ese
archivo no se sube). Desde esta carpeta:

```
./gradlew :app:testDebugUnitTest     # pruebas en la computadora (búsqueda, lectura del servidor, reportes, textos)
./gradlew :app:assembleRelease       # la app: app/build/outputs/apk/release/app-release.apk
```

Compilada así va firmada con la llave de pruebas de Android y es la versión 0.1 (1): sirve para instalarla a mano. Si
la computadora con One TV corre desde esta carpeta del proyecto, ofrece esta en `/tv` (antes que la de GitHub).

## Instalar en una TV con «Downloader» (para todos)

La guía para personas no técnicas está en [docs/INSTALAR-GOOGLE-TV.md](../docs/INSTALAR-GOOGLE-TV.md): en la TV se
instala la app «Downloader», se le da permiso para instalar apps y se escribe `http://<computadora>:8765/tv`. Esa
dirección (`mac/apptv.py`) entrega la app compilada en la computadora o, si no hay, la más nueva publicada en GitHub,
que la computadora baja sola una vez al día. Para actualizar, lo mismo; la app avisa cuando hay una nueva.

## Publicar en GitHub (versión firmada)

Al subir a `main` algo de `androidtv/` (o las letras e íconos de `roku/` que usa), `.github/workflows/app-tv.yml`
compila la app firmada y crea la versión **`tv-0.1.N`** con **`one-tv-tv.apk`** (siempre ese nombre) y
`one-tv-tv.json` (`{"version", "version_code"}`). El número de versión sube solo en cada publicación
(`ONETV_VERSION_CODE` = número de la ejecución + 1, `ONETV_VERSION_NAME` = `0.1.N`). La más nueva queda siempre en
`https://github.com/julai1433/one-tv/releases/latest/download/one-tv-tv.apk`.

Secretos del repositorio que hacen falta (GitHub › Settings › Secrets and variables › Actions); sin ellos no se publica
nada:

| Secreto | Qué es |
|---|---|
| `ANDROID_KEYSTORE_BASE64` | El archivo de la llave (`.jks`) en base64 |
| `ANDROID_KEYSTORE_PASSWORD` | La contraseña del archivo de la llave |
| `ANDROID_KEY_ALIAS` | El nombre de la llave dentro del archivo |
| `ANDROID_KEY_PASSWORD` | La contraseña de la llave (si es la misma del archivo, repítela) |

Cómo se crea la llave (una sola vez, en la computadora de quien mantiene el proyecto; **guárdala bien**: sin ella no
se pueden publicar actualizaciones que se instalen encima de las anteriores, y no se sube al repositorio):

```
keytool -genkeypair -v -keystore one-tv.jks -alias one-tv -keyalg RSA -keysize 4096 -validity 10000
base64 -i one-tv.jks | pbcopy        # macOS: queda copiada para pegarla en ANDROID_KEYSTORE_BASE64
```

(`keytool` viene con Java. En Linux: `base64 -w0 one-tv.jks`.) Para compilar firmada en la computadora:
`ANDROID_KEYSTORE_FILE=one-tv.jks ANDROID_KEYSTORE_PASSWORD=… ANDROID_KEY_ALIAS=one-tv ./gradlew :app:assembleRelease`.
Una TV con la versión de pruebas (firmada con la llave de pruebas) no se actualiza con la publicada: hay que
desinstalarla primero (lo que se vio vive en la computadora y no se pierde).

## Instalar en una TV con adb (para desarrollar)

1. En la TV, activa las opciones de desarrollador (Ajustes › Sistema › Información › toca 7 veces «Compilación»; en
   Fire TV: Mi Fire TV › Acerca de › toca 7 veces el nombre) y prende **Depuración por red** (o «Depuración ADB»).
2. Anota la dirección de la TV (Ajustes › Red) y, desde la computadora: `adb connect <dirección de la TV>`, acepta el
   aviso en la TV, y `adb -s <dirección de la TV>:5555 install -r app-release.apk`.
3. Abre «One TV» desde las apps de la TV. Encuentra sola la computadora si está en el mismo Wi-Fi.

Para probar en el emulador contra un servidor de prueba: `adb -s emulator-5554 shell am start -n app.onetv.tv/.MainActivity
--ei puerto 8797` (busca en ese puerto; con dos servidores de prueba a la vez, `--eia puertos 8804,8805`) o
`--es servidor http://10.0.2.2:8797` (dirección fija). Como en el Roku,
`--es contentId yt:<video>` o el id de una película abre la app reproduciéndolo. Con la app abierta, la web del
servidor de prueba la maneja («Ver en la TV», la barra «En la TV»), o a mano: `curl -H 'Content-Type: application/json'
-d '{"id":"<película>"}' localhost:8797/api/play`, `-d '{"key":"Play"}' …/api/key`, `-d '{"t":120}' …/api/seek`.

## Lo que falta

- Guardar sin conexión (la fila «Guardados» y su botón en la ficha) y «varios a la vez» (archivado también en el Roku).
- La computadora no puede abrir la app sola (al Roku sí): las órdenes llegan solo con One TV abierta.
- Probar la instalación con Downloader en TV de verdad (Google TV, Fire TV) y la versión firmada de GitHub.
- Lectores de pantalla: hoy las teclas las maneja la app (como el Roku) y no se anuncian.
