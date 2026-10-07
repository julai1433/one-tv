# One TV para Google TV, Android TV y Fire TV

La app de la TV de One TV para televisores y aparatos con Android: Google TV (Chromecast con Google TV, TV con Google
TV), Android TV y Fire TV. Se ve y se maneja **igual que la del Roku** (`roku/`): mismas secciones, colores, letras,
textos y teclas del control.

## Qué hace (fase 1)

- **Se conecta sola**: al abrirla busca la computadora con One TV en la red de la casa y la recuerda. Si la
  computadora cambia de dirección o la TV cambia de Wi-Fi, la vuelve a buscar sola. Si no la encuentra, deja buscar
  otra vez o escribir la dirección con el control.
- **Inicio, En español, Películas, Series, YouTube, Música y Fila de reproducción**, con el menú lateral, las filas
  de pósters, la ficha («Continuar desde…», «A continuación», «Al final de la fila», «Idioma») y la página de cada
  serie con sus temporadas.
- **Reproductor** con las teclas del Roku: OK pausa; ▼ muestra la barra y otro ▼ abre el panel; ▲ regresa; ◀ ▶ la
  primera vez muestran la barra y después mueven la posición (por capítulos en YouTube); ⏪ ⏩ 15 segundos; Atrás
  oculta lo de encima y luego sale. El panel tiene «Siguiente de la fila», «Audio y subtítulos», la fila y lo visto
  hace poco. Sigue donde te quedaste y avisa a la computadora por dónde va (igual que el Roku), así funcionan
  «Seguir viendo» y la barra «En la TV» de la web. Al terminar un episodio, cuenta atrás para el siguiente.
- **YouTube** (las filas de la app del Roku; se reproduce con capítulos) y **Música** (tus listas, lo agregado hace
  poco, artistas y álbumes; la página del álbum; escuchar con la portada y lo que sigue).

No usa nada de Google Play Services: solo bibliotecas de AndroidX/Jetpack y Media3 (licencia Apache 2.0). Las letras y
los íconos son los de `roku/fonts` y `roku/images/icons` (no hay otra copia).

## Compilar

Necesitas Java 17 o más nuevo y el SDK de Android (variable `ANDROID_HOME`, o un `local.properties` con `sdk.dir`; ese
archivo no se sube). Desde esta carpeta:

```
./gradlew :app:testDebugUnitTest     # pruebas en la computadora (búsqueda, lectura del servidor, reportes, textos)
./gradlew :app:assembleRelease       # la app: app/build/outputs/apk/release/app-release.apk
```

En esta fase la versión para instalar va firmada con la llave de pruebas de Android (sirve para instalarla a mano;
para una tienda hará falta una llave propia).

## Instalar en una TV (hoy, con adb)

1. En la TV, activa las opciones de desarrollador (Ajustes › Sistema › Información › toca 7 veces «Compilación»; en
   Fire TV: Mi Fire TV › Acerca de › toca 7 veces el nombre) y prende **Depuración por red** (o «Depuración ADB»).
2. Anota la dirección de la TV (Ajustes › Red) y, desde la computadora: `adb connect <dirección de la TV>`, acepta el
   aviso en la TV, y `adb -s <dirección de la TV>:5555 install -r app-release.apk`.
3. Abre «One TV» desde las apps de la TV. Encuentra sola la computadora si está en el mismo Wi-Fi.

Para probar en el emulador contra un servidor de prueba: `adb -s emulator-5554 shell am start -n app.onetv.tv/.MainActivity
--ei puerto 8797` (busca en ese puerto) o `--es servidor http://10.0.2.2:8797` (dirección fija). Como en el Roku,
`--es contentId yt:<video>` o el id de una película abre la app reproduciéndolo.

## Lo que falta

- Buscar (con el teclado de la TV), En vivo, los ajustes generales, las listas y canales de YouTube, «Saltar intro»,
  el doblaje de YouTube, guardar sin conexión y las opciones con la tecla `*`.
- Que la web controle esta app como controla al Roku (pausa, avance, «Ver en la TV»): necesita un canal nuevo en el
  servidor.
- Instalar sin adb para personas no técnicas (por ejemplo, el servidor ofrece la app y un código para «Downloader»).
- Lectores de pantalla: hoy las teclas las maneja la app (como el Roku) y no se anuncian.
