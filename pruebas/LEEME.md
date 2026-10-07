# Herramientas de prueba

No son parte del servicio; sirven para probar cambios sin adivinar.

## Lo de siempre (antes de mandar un cambio)

- **Todas las pruebas de la computadora** (sin red, sin TV, unos 20 s; necesitan `ffmpeg`):
  `python3 -m unittest discover -s pruebas -p 'test_*.py'`. Cada `test_*.py` dice en su primera línea qué prueba.
- **El código de la app del Roku** (BrightScript), sin TV: `npx -y brighterscript@0` desde la raíz del repositorio
  (lee `bsconfig.json`; necesita Node). Debe terminar sin errores.
- **La web**: los `web_*.py` la abren en Chrome sin ventana contra el servidor de prueba (ver abajo) y revisan
  cada función; dejan capturas en la carpeta que les digas.
- **En la TV** (si tienes un Roku en modo desarrollador): `captura_tele.sh` toma una captura de la app.

## Cada herramienta

- `captura_tele.sh [archivo.jpg]` — captura de pantalla de la app del Roku (modo desarrollador). Usa `roku_ip` y `roku_password` de `config.json`; si `roku_ip` está vacío, busca el Roku en la red.
- `iconos_roku.py` — vuelve a generar los íconos de la app del Roku (`roku/images/icons/*.png`, trazos de Lucide
  en blanco que la app tiñe), las piezas 9-patch (relleno y contornos de esquinas casi rectas, marco de foco,
  sombra del aviso), los círculos de los canales y los degradados de la ficha, dibujándolos con Chrome sin
  ventana. Para agregar un ícono: su trazo en `ICONS` y correrlo.
- `web_fase4.py <carpeta> [puerto] [--anchos 390,1280]` — la web en Chrome sin ventana a 390 px
  (iPhone) y 1280 px (laptop), contra el servidor de prueba (por omisión el 8790). Deja una captura de cada
  sección (Inicio, Biblioteca, serie, ficha e idioma, YouTube, canal, lista, Buscar, En vivo, Fila e historial,
  barra y control «En la tele» con el aviso de saltar, reproductor del aparato con su aviso y la cuenta atrás)
  y revisa las funciones una por una (✓/✗), que nada se salga de la pantalla, el contraste real de lo que se ve
  (texto ≥4,5:1, bordes de las piezas que se tocan ≥3:1), que no haya colores fuera de la paleta de `DESIGN.md` y
  que no haya errores de consola. También revisa el archivo: que existan todos los íconos, que todos los colores
  salgan del bloque `:root`, las letras propias (woff2 + OFL) y que las esquinas sean de 2 px o rectas. **No manda nada a la tele ni cambia datos**: todo POST (reproducir, fila, idioma, progreso) se
  intercepta y solo se anota, y lo que depende de internet (buscar en YouTube, canal, lista, subtítulos) se
  contesta con datos de ejemplo. Sale con código 1 si algo falla.
- `web_youtube_continua.py <carpeta> <ancho>` — ajuste de reproducción continua (Fila de reproducción → Ajustes
  generales) y el aviso «Recomendado por YouTube» en el navegador. ⚠ Usa el servidor real: prende y apaga el
  ajuste real y reproduce un video corto; ensucia el historial.
- `servidor_de_prueba.py` — servidor de la web con una copia de los datos (puerto 8790) para pruebas aisladas;
  usa la carpeta de `CINE_PRUEBA` (por omisión `/tmp/cine-prueba`): copia ahí `datos/` antes de arrancarlo.
- `doblaje_trozos_vs_original.py <carpeta> <video> <pista.m4a>` — compara los trozos que se mandan a la tele
  con una pista aparte contra la pista que viene dentro del archivo (necesita numpy: usar el Python de
  `~/Library/Application Support/cine-roku/doblaje/bin/python`).
- `intro_temporada.py "<carpeta de la temporada>" [otra carpeta o video …] [--detalle]` — detecta la entrada
  («Saltar intro») de cada episodio igual que el servicio (`mac/introsync.py`, con el Python de numpy del
  doblaje y prioridad baja) y muestra una tabla: inicio, fin, duración y confianza (cuántos compañeros
  coinciden). Solo lee los videos. Con `--detalle`, el tramo común de cada par de episodios. Con videos de
  series distintas sirve de control: no debe salir ningún tramo común. Al final dice cuánto tardó y su CPU.
- `leer_qr.js <imagen.png>` — lee un código QR con macOS: `osascript -l JavaScript leer_qr.js qr.png`.
- `takeout_de_prueba.py <carpeta>` — genera zips de Takeout SINTÉTICOS (inglés y español, historial en JSON y en
  HTML, formato viejo de listas) con IDs reales de canales y videos. Imitan lo que se sabe del formato de Google;
  no se han comparado con un zip auténtico.
- `test_ytaccount.py` — pruebas unitarias de `mac/ytaccount.py` (sin red): `python3 -m unittest discover -s pruebas -p "test_ytaccount.py"`.
- `test_duraciones.py` — duración de los videos de YouTube (sin red): el caché (`mac/ytdurations.py`), el rellenador
  (varios videos por petición, 1 video cada 3 s y 100 por hora, freno de 6 h si YouTube bloquea, que sobrevive a un
  reinicio), la lectura de las páginas (lista anónima, relacionados, página del canal) y su uso en la fila, «Nuevos»,
  el historial y las listas del Takeout.
- `test_canales_ocultos.py` — canales ocultos y anclados (sin red): la cuenta, los filtros de «Nuevos», «Porque viste…» y la
  reproducción continua, y las rutas por HTTP (el contrato que usa la TV).
- `test_mosaico.py` — varios a la vez en la TV (`mac/mosaic.py`, sin red): el comando de ffmpeg (2–4 fuentes, audio
  «alt» y «ts», respaldo sin el chip), lo que llega por la API, las listas HLS, la sesión con reloj falso (inactividad,
  trabada, fuente caída) y las rutas. Incluye una prueba corta con ffmpeg de verdad que se salta sola sin VideoToolbox.

Después de cualquier prueba que reproduzca algo en el servidor de verdad: restaurar `progreso.json` / `youtube.json`
(o, mejor, probar siempre con `servidor_de_prueba.py` y una copia de los datos).
