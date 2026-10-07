# Instalar One TV en Google TV, Android TV o Fire TV

**Primera versión, en prueba.** Sirve para Chromecast con Google TV, Google TV Streamer, las TV con Google TV o Android TV
integrado (Sony, TCL, Hisense, Philips…), Nvidia Shield, Fire TV Stick, Fire TV Cube y las TV con Fire TV.

Necesitas:

- Una computadora de la casa con One TV funcionando (guías: [Mac](INSTALAR.md), [Ubuntu](INSTALAR-UBUNTU.md),
  [Windows](INSTALAR-WINDOWS.md)).
- La TV en el mismo Wi-Fi que esa computadora.
- Unos 10 minutos. No hace falta cable ni conectar nada a la computadora.

La app se instala con **Downloader**, una app gratuita que baja archivos en la TV.

## 1. La dirección para escribir en la TV

En la computadora o el teléfono abre la página de One TV y ve a **Fila de reproducción › Ajustes generales ›
Instalar en Google TV, Android TV o Fire TV**. Ahí está, en grande, la dirección que vas a escribir en la TV; es algo
como:

```
http://192.0.2.5:8765/tv
```

(Es la dirección de la computadora con `/tv` al final. Los números de tu casa serán otros.)

## 2. Instala Downloader en la TV

- **Google TV y Android TV**: en **Apps** (o Google Play), busca **Downloader** (ícono naranja con una flecha) e
  instálala.
- **Fire TV**: con la lupa, busca **Downloader** y descárgala.

## 3. Dale permiso a Downloader para instalar apps

Las TV solo instalan apps de la tienda hasta que les das permiso. Se hace una vez.

**Google TV** (Chromecast con Google TV, TV con Google TV):

1. **Configuración › Sistema › Información**: baja hasta **Compilación del SO de Android TV** y presiona OK 7 veces,
   hasta que diga que ya eres desarrollador (si pide el PIN de la TV, ponlo).
2. **Configuración › Apps › Seguridad y restricciones › Fuentes desconocidas**: prende **Downloader**.

**Android TV** de antes (Sony, Philips, Nvidia Shield…): **Configuración › Preferencias del dispositivo › Seguridad y
restricciones › Fuentes desconocidas** › **Downloader**.

**Fire TV**:

1. **Configuración › Mi Fire TV › Acerca de**: presiona OK 7 veces sobre el nombre de tu Fire TV, hasta que diga que
   ya eres desarrollador.
2. Regresa a **Mi Fire TV › Opciones para desarrolladores › Instalar apps desconocidas** y activa **Downloader**.

Los nombres de los menús cambian un poco según la marca y la versión. Si al instalar la TV avisa que no permite apps de
esa fuente, ese mismo aviso trae un botón **Configuración** que lleva directo al permiso.

## 4. Baja e instala One TV

1. Abre **Downloader**. En el recuadro de la dirección escribe la del paso 1 con el control y elige **Go**.
2. Cuando termine de bajar, elige **Instalar** y después **Abrir**.
3. Downloader pregunta si borra el archivo que bajó: **Borrar** (ya no hace falta).

Si en lugar de bajar la app aparece una página que dice «Todavía no hay app para esta TV», la computadora todavía no la
tiene: la baja sola de internet una vez al día. Prueba más tarde con la misma dirección.

## 5. Abre One TV

Queda con tus apps como **One TV**. Al abrirla busca sola la computadora de la casa. Si no la encuentra, elige
**Escribir la dirección** y pon la del paso 1 sin el `/tv` del final (por ejemplo `192.0.2.5`).

## Manejarla desde el teléfono o la computadora

Igual que con el Roku: en la página de One TV, **Ver en la TV**, y desde la barra **En la TV** pausa, avanzar, idioma
y subtítulos, canción anterior o siguiente y salir. Solo funciona **mientras One TV está abierta en la TV** (a
diferencia del Roku, la computadora no puede abrirla sola).

Si en la casa hay más de una TV (por ejemplo un Roku y un Google TV), debajo de **TV conectada** aparece **Lo que elijas
se ve en**, para elegir a cuál va. Sin tocarlo, va a la que se usó por última vez.

## Actualizar

Cuando hay una versión nueva, la app lo avisa al abrirla. Para actualizar, repite el paso 4 con la misma dirección. Lo
que viste y tus ajustes no se pierden: viven en la computadora.

## Qué probar

Lo que alcances sirve:

1. **Instalar** con esta guía: ¿algún paso se ve distinto en tu TV?
2. **Que encuentre sola** la computadora al abrirla.
3. **Ver algo**: una película, un capítulo de una serie, un video de YouTube y música. Pausa (OK), ◀ ▶, ⏪ ⏩, y
   **Audio y subtítulos** (▼ dos veces).
4. **Desde el teléfono**: Ver en la TV, pausa, avanzar, salir; y que la barra **En la TV** diga lo que pasa.
5. **Salir y volver**: ¿sigue donde lo dejaste?

## Cómo avisar si algo falla

Abre un *issue* en GitHub: [abrir uno](https://github.com/julai1433/one-tv/issues/new?template=reporte-de-prueba.md)
(pide una cuenta de GitHub, gratis). Si no tienes cuenta, manda lo mismo por mensaje a quien te compartió One TV.
Cuéntanos:

- **El modelo de la TV o del aparato** (por ejemplo «Chromecast con Google TV 4K» o «Fire TV Stick 4K Max»; está en
  Configuración › Sistema › Información, o Mi Fire TV › Acerca de).
- **Qué hiciste**, paso por paso.
- **Qué pasó**: el mensaje exacto o una foto de la pantalla.
- **La versión de One TV**: la dice la página de One TV en Ajustes generales, debajo de la dirección.

## Si algo no sale

- **«App no instalada»** al instalar: si ya tenías una One TV puesta de otra forma (por ejemplo una de prueba), quítala
  primero (Configuración › Apps › One TV › Desinstalar) y repite el paso 4. Lo que viste no se pierde.
- **Downloader no baja nada**: revisa la dirección (empieza con `http://`, sin la «s»; números, puntos y el `:8765`) y
  que la TV y la computadora estén en el mismo Wi-Fi. Prueba abrir la página de One TV en el teléfono con esa misma
  dirección sin el `/tv`.
- **One TV no encuentra la computadora**: revisa que la computadora esté encendida con One TV funcionando y elige
  **Escribir la dirección**.
