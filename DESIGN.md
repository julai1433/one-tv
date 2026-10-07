# Sistema visual — One TV

Negro y verde limón. Osado y seguro de sí, sin cansar la vista: una sala de cine con las luces apagadas y
una marquesina encendida. Rige la TV (Roku), la web (iPhone y laptop) y la futura app de Android TV.

Es una interfaz para **operar** (elegir y ver algo rápido, a veces a 3 metros con un control): se escanea
antes de leerse. La personalidad vive en decisiones precisas y repetidas (color, letra, foco), no en adornos.

## Qué se va y qué entra

La primera versión funcionaba pero tenía las señales típicas de lo hecho a prisa por una IA. Cada una se
reemplaza por una decisión propia:

| Se va | Entra |
|---|---|
| Fondos azul marino (#0B0E13, #0E1116) | **Negro puro** (#000) y grises neutros sin tinte |
| Fuente del sistema | **Big Shoulders Display** (títulos) + **Archivo** (todo lo demás), incluidas en el proyecto |
| Diez radios distintos (6–18 px) y píldoras | **Esquinas casi rectas**: 2 px en piezas, 0 en paneles y barras |
| Resaltado blanco suave en lo elegido | **Lo que señalas se vuelve limón**: relleno limón con letra negra |
| Interruptor redondo tipo iPhone | **Selector de dos segmentos** con palabras |
| Punto verde «TV conectada» | **Estado en palabras**: TV · CONECTADA / BUSCANDO / NO RESPONDE |
| Filas vacías con una frase gris | **Vacío que enseña**: el hueco de la fila dibujado, por qué está vacío y qué hacer |
| Campos de texto en caja gris redondeada | **Línea inferior**, letra grande, cursor limón |
| Etiqueta verde «Español» | **Guinda con letra y contorno limón** |

## Logo

**1▶**: un 1 y el play, en `on-lime` sobre un cuadrado `lime` con esquinas de 3 (en una caja de 100). Se lee
«One» y «reproducir» de un vistazo. Junto al nombre, **ONE TV** en Big Shoulders Black, con la marca un poco más
alta que las mayúsculas (la altura de mayúsculas ≈ 62 % de la marca). Ícono de app: la marca al 64 % sobre negro.
Mosaico del Roku: la marca y ONE TV debajo. Las imágenes ya hechas están en `roku/images/` y `mac/web/`.

## Color

Solo negro, grises neutros, limón y guinda. Ningún otro tono.

| Token | Valor | Uso |
|---|---|---|
| `bg` | `#000000` | Fondo de todo |
| `raise-1` | `#0C0C0C` | Barra lateral, pestañas de abajo, barra «En la TV» |
| `raise-2` | `#161616` | Paneles (idioma, control de la TV), menú abierto en la TV |
| `raise-3` | `#222222` | Pista de las barras de avance, pósters que faltan |
| `line` | `#2E2E2E` | Líneas finas que solo separan (1,55:1: decorativas) |
| `edge` | `#5E5E58` | Bordes de lo que se toca: botón secundario, segmento no elegido, línea de los campos en reposo, huecos de un vacío (3,1:1) |
| `edge-panel` | `#686862` | Lo mismo, pero encima de un panel `raise-2` (3,2:1 sobre `#161616`) |
| `text` | `#F2F2EE` | Texto principal |
| `text-soft` | `#C9C9C2` | Sinopsis, línea de información |
| `muted` | `#8C8C85` | Ayudas, conteos, textos de apoyo (6,2:1 sobre negro) |
| `lime` | `#A6E22E` | Foco, botón principal, barras de avance, sección actual, estado bueno |
| `on-lime` | `#0A0F00` | Letra e íconos sobre limón (12,5:1) |
| `guinda` | `#7A1535` | Fondo de la etiqueta «Español» |
| `guinda-claro` | `#E0507F` | Problemas: NO RESPONDE, errores, «Vaciar la fila» (5,6:1 sobre negro) |
| `es-text` / `es-line` | `#C4F05A` | Letra y contorno de la etiqueta «Español» (8:1 sobre guinda) |
| `scrim` | `rgba(0,0,0,.72)` | Velo detrás del menú abierto, del control y sobre imágenes |
| `badge` | `rgba(0,0,0,.85)` | Fondo de la etiqueta de duración sobre las miniaturas de YouTube |

El limón es escaso a propósito: aparece donde está la acción o la atención, nunca de fondo de secciones.
Si una pantalla tiene más de dos o tres cosas en limón a la vez, sobra alguna.

Excepción: la marca de YouTube (`yt-red` #FF0033 con el triángulo en `text`) en las tarjetas de videos de YouTube
que van entre pósters, para reconocerlos de un vistazo (decisión del 29 sep 2026). Solo esa marca, nada más en rojo.

## Letra

- **Big Shoulders Display** (800–900), en MAYÚSCULAS: títulos de página (INICIO, PELÍCULAS…), título de la
  ficha, la palabra de estado (CONECTADA), la frase de un vacío y el aviso SALTAR INTRO. Es letra de
  marquesina: grande, apretada (tracking −0,01 em), pocas palabras.
- **Archivo** (400, 500, 700): todo lo demás. Títulos de fila en 700 con mayúscula inicial. Números con
  cifras tabulares (tiempos, conteos).
- Nunca la fuente del sistema. Los archivos van en el proyecto (licencia OFL, con su `OFL.txt`):
  web en `mac/web/fonts/` (woff2), Roku en `roku/fonts/` (TTF fijos, sacados de las variables).
- Escala web (px): 12 · 14 · 16 · 20 · 28 · 44 · 64. Escala TV (sobre 1920×1080): 27 (mínimo) · 32 · 38 ·
  48 · 72 · 110.

## Forma

- Esquinas: **2 px** en pósters, botones, campos y etiquetas; **0** en paneles, barras, menús y pestañas.
  Sin píldoras. Solo son redondos los avatares de canal (son caras, no botones).
- Líneas de 1 px en `line` para separar; bordes de piezas que se tocan en `edge`. Foco con 2 px (web) o 5 px
  (TV) en limón.
- Sin sombras decorativas. La única sombra es la del aviso encima del video (con desplazamiento y difuminado).
- Sin tarjetas como contenedor de secciones: las filas y las listas van directo sobre el negro.
- Espaciado en múltiplos de 8 (web) y de 12 (TV): grupos apretados, separaciones generosas, más aire arriba
  de un título que abajo.

## Foco y selección (la regla que más se nota)

**Lo que señalas se vuelve limón.** Una sola regla en todo el producto:

- Botones, opciones de menú, segmentos y elementos de lista con foco: **relleno limón, letra negra**.
  Sin foco: sin relleno (botón secundario: contorno `edge`).
- Pósters con foco (TV): marco limón de 5 px pegado al borde, póster al 106 %, y el resto de la fila al 55 %
  de opacidad (como un reflector). Transición de 120 ms, salida suave.
- Sección actual sin foco (menú lateral cerrado, pestañas del teléfono): ícono y texto en limón.
- Web: `:hover` pone texto o contorno en limón; `:focus-visible` es contorno limón de 2 px separado 2 px.
- Lo que no es foco nunca usa el relleno limón, salvo el botón principal de cada pantalla (uno solo).

## Piezas

1. **Campos de texto** (buscar, pegar un enlace, agregar un canal en vivo o cambiarle el nombre): sin caja. Línea inferior de 2 px
   (`edge`, limón al escribir), letra Archivo 500 grande (web 20 px, TV 44), marcador de posición `muted`,
   cursor limón, ícono de lupa a la izquierda que se vuelve limón con el foco, botón para borrar.
2. **Ajustes de dos opciones** (p. ej. «Al terminar la fila»): dos segmentos rectos lado a lado con la
   palabra de cada opción; la elegida en relleno limón con letra negra, la otra con contorno. Nunca un
   interruptor redondo.
3. **Estado de la TV**: ícono de TV + «TV» en `muted` pequeño + la palabra en letra de marquesina:
   **CONECTADA** (limón) · **BUSCANDO** (`muted`) · **NO RESPONDE** (guinda claro). Sin puntos de color.
   Laptop: abajo de la barra lateral. Teléfono: arriba a la derecha de Inicio.
4. **Vacíos**: la fila conserva su forma con 3 o 4 huecos dibujados (contorno `edge`) y encima una frase
   corta en letra de marquesina (TODAVÍA NO HAY CANALES), una oración con la causa y una acción en limón
   («Cómo traer tus suscripciones»). La página vacía (fila de reproducción sin nada) usa el mismo patrón, más grande.
5. **Botones**: principal en relleno limón y letra negra (uno por pantalla); secundario con contorno `edge` y
   letra `text`; peligroso en letra guinda claro. Alto 44 px en web, 64 en TV. Ícono + palabra.
6. **Etiqueta «Español»**: fondo guinda, letra y contorno limón claro (1 px web, 2 px TV), «ESPAÑOL» en
   Archivo 700 con tracking 0,04 em, esquinas de 2 px.
7. **Barras de avance**: 4 px (web) / 6 px (TV), pista `raise-3`, avance limón, extremos rectos.
8. **Aviso para saltar** (encima del video, abajo a la derecha): panel negro al 92 %, borde limón de 2 px,
   texto en letra de marquesina (SALTAR INTRO / SIGUIENTE CAPÍTULO: …), tecla OK dibujada con contorno limón,
   línea limón abajo que se vacía en 8 s.
9. **Pósters sin imagen**: fondo `raise-3` con el título en letra de marquesina, nunca un rectángulo vacío.
9b. **Video de YouTube en una fila de pósters** (p. ej. «Seguir viendo»): la miniatura grande (1280×720) llena
    la tarjeta vertical, recortada al centro; abajo, sobre un degradado a negro, el ícono y «YouTube» en 700 y el
    canal en `text-soft`. El título va donde el de los demás pósters (opción A, elegida el 29 sep 2026).
9c. **Duración de un video de YouTube** (decisión del 29 sep: tiene que notarse): etiqueta sobre la miniatura, abajo a
    la derecha, como en YouTube: fondo `badge`, letra `text` en Archivo 700 con cifras tabulares («4:12», «1:02:03»),
    esquinas de 2 px. Web 12 px (14 px en las tarjetas de la laptop); TV 27 (el mínimo) en una caja de 40 de alto. Si
    hay barra de avance, la etiqueta sube para no taparla; en la tarjeta vertical de «Seguir viendo» va justo encima
    de «YouTube» y el canal. La etiqueta «Español» va arriba a la izquierda, así que no se cruzan. Va en todas las
    tarjetas y renglones de videos de YouTube (filas, cuadrículas, la fila de reproducción, el historial y el panel
    «En la TV»); si no se sabe la duración, no se dibuja. Debajo de la tarjeta ya no se repite: ahí va el canal.
9d. **Guardado sin conexión** (30 sep 2026): marca discreta en las tarjetas de los videos de YouTube que ya están
    guardados en la computadora (`offline = "listo"`; mientras se baja o espera no lleva marca, eso se dice en el texto
    de debajo y en la ficha). Es un cuadro con el ícono de descarga (Lucide `download`, trazo 2, en `text`) sobre
    fondo `badge` con esquinas de 2 px, **arriba a la derecha** de la miniatura: web 20 px (24 en la laptop) con el
    ícono de 14 (16); TV un cuadro de 40 con el ícono de 28, a 10 px del borde. La duración va abajo a la derecha, «Español»
    arriba a la izquierda y la marca de YouTube abajo a la izquierda: las cuatro esquinas no se cruzan. Mismas
    palabras en web y TV: «Guardar sin conexión», «En la cola para guardar», «Guardando… 45 %», «Guardado sin
    conexión», «Guardar la lista sin conexión», «Guardando 3 de 12», «Lista guardada». En la TV, quitar un guardado
    pide un segundo OK («OK otra vez para quitar», en guinda claro, como «Ocultar canal»). La fila «Guardados» va
    entre «Seguir viendo» y «Vistos hace poco», solo si hay algo: primero lo que se baja o falló, luego lo guardado,
    lo más nuevo primero.
10. **Pestañas del teléfono**: fondo `raise-1`, línea fina arriba; la activa con ícono y palabra en limón y una
    barra limón de 3 px en su borde superior.
11. **Íconos**: los de trazo que ya existen (Lucide, trazo 2), en `text`; limón solo cuando señalan foco o
    la sección actual.

## Lo que el navegador trae y también se diseña

Selección de texto en limón con letra negra, cursor limón, barras de desplazamiento oscuras (`edge` sobre
negro), anillos de foco limón, color del sistema y de la barra del iPhone en negro (`theme-color` y
`manifest.webmanifest`).

## Movimiento

Un solo momento con intención: el cambio de foco (reflector en la TV, contorno en la web), 120 ms con salida
suave. Nada entra deslizándose por su cuenta. Con «reducir movimiento» activado, cambios instantáneos.

## Cómo se aplica

- **Web**: todos los tokens en el bloque `:root` de `mac/web/index.html`; las fuentes en `mac/web/fonts/`
  (el servidor debe servir `.woff2`).
- **Roku**: todos los colores en `roku/components/Theme.brs`; las fuentes en `roku/fonts/` y `makeFont()`
  las usa en lugar de la del sistema.
- **Android TV** (futura): los mismos tokens y las mismas dos fuentes.

## Notas por plataforma (lo que cada una no puede o resolvió distinto)

- **Roku**: el marco de foco de los pósters mide 6 px y va por dentro de la imagen (las listas del Roku
  recortan lo que se sale); las esquinas de 3 px se ven de 2 en una TV HD. El reflector atenúa todo lo que no
  tiene el foco, no solo su fila. La transición la hace la animación propia de las listas. El Roku no permite
  espaciado de letra, cifras tabulares ni cambiar la letra del teclado y del reproductor. El botón principal sin
  foco lleva contorno limón (para no ver dos rellenos limón a la vez). En los filtros la opción elegida va en
  letra limón; en los ajustes, en relleno limón. La caja de texto del teclado sigue bajo el campo de búsqueda
  porque de ella depende la voz. Las fuentes no traen cirílico ni alfabetos asiáticos (pendiente: respaldo).
- **Web**: `edge-panel` para bordes sobre paneles. El aviso para saltar no dibuja la tecla OK (se toca con el
  dedo). «Visto» en gris claro y el número de la pestaña Fila en gris, para no repetir limón en cada renglón. El
  filtro Con/Sin español mide 36 px de alto (discreto). Mientras cargan las letras se usa Arial ajustada. El error
  de un formulario (agregar un canal en vivo) sigue el vacío con error: la frase en letra de marquesina guinda
  claro y la causa debajo; además sale como aviso. Mientras se edita el nombre de un canal, «Guardar» es el único
  botón principal de la pantalla. El código QR del Takeout solo se muestra en la laptop.
- **Capítulos de YouTube** (decisión del 29 sep): no son un aviso de saltar. Marcadores en la barra de
  avance con su título; al empezar un capítulo, su nombre unos segundos, solo como texto, sin ser seleccionable
  (ajuste general «Mostrar el nombre del capítulo»).
