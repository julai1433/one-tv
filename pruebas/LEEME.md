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

- `instalador_mac.sh [puerto]` — el instalador de verdad (`instalar.sh`) en esta Mac como si fuera una sin Homebrew,
  sin Python y sin las herramientas de Xcode: HOME falso en `/tmp`, PATH sin Homebrew, otro puerto (8803), sin
  arranque automático y sin poder hablarle a ninguna TV (`sandbox-exec`). Baja de verdad Python y ffmpeg (unos 80 MB) y
  revisa que el servidor arranque con ellos, que `/bienvenida` responda y que volver a correrlo ponga al día sin
  bajar nada ni perder datos. Borra todo al terminar.
- `instalador_ubuntu.sh` — lo mismo en dos contenedores de Ubuntu 24.04: uno recién instalado (sin Python, ffmpeg ni
  curl, sin systemd; instala con apt) y uno con systemd por SSH (el servicio de verdad, con «linger»). Necesita Docker.
- `powershell.sh` — los guiones de PowerShell de Windows sin Windows: `test_red_windows.py` en un contenedor con
  PowerShell 7, con los comandos del firewall reemplazados por unos falsos. Necesita Docker.
- `instalador_nas.sh` — `instalar.sh` con Docker en un Ubuntu con systemd dentro de Docker y sin Docker instalado:
  con `--docker` instala Docker con el oficial (necesita internet) y crea el contenedor `one-tv`; luego, como si fuera
  un Synology, lo reconoce y monta `/volume1` de solo lectura; un `one-tv` ajeno no lo toca. Puerto 8808. Borra todo.
- `test_instalador.py` — las funciones de `instalar.sh` (sin red: lo «bajado» son archivos falsos): qué baja según el
  chip, las sumas de verificación, que no vuelva a bajar lo que ya está y que poner al día conserve `config.json`.
- `test_instalador_nas.py` — la parte de NAS de `instalar.sh` con un sistema de archivos y programas falsos: reconoce
  cada NAS, sus carpetas compartidas y la de datos, el comando de Docker, qué dice si falta Docker en cada uno, y que
  los docker-compose de `docs/INSTALAR-DOCKER.md` monten lo que dicen.
- `test_instaladores.py` — el `.pkg` de la Mac (en una Mac lo arma y lo instala «solo para ti» con un `instalar.sh`
  falso), los nombres fijos de los instaladores, la página del botón (con Node) y la firma de la Mac (si existe su script privado) sin
  certificados (con programas falsos).
- `test_bienvenida.py` — el primer arranque sin preguntas, `/bienvenida`, `cine instalador` y la copia de `config.json`
  del servicio. `test_asistente.py` — el asistente de `/bienvenida` (`mac/asistente.py`): busca carpetas con videos en
  una casa inventada (y en Docker, en `ONE_TV_COMPARTIDAS`), guarda lo elegido sin tocar lo demás, la contraseña del
  Roku, quién puede usarlo, el explorador (nunca fuera de los lugares permitidos) y un Roku falso con contraseña.
  `test_codigo_tele.py` — el código de la TV para usar el asistente desde otro aparato cuando ya se terminó: se genera,
  llega a un Roku y a una TV con Android falsos (o queda en el registro), vence, pocos intentos, la cookie, y que la
  primera configuración y esta computadora siguen igual. `test_red_windows.py` — la regla «One TV» del firewall de Windows y `cine permitir-red`.

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
- `web_asistente.py <carpeta> [puerto=8809]` — el asistente de `/bienvenida` de punta a punta en Chrome sin ventana,
  a 1280 px (en el puerto dado) y 390 px (en el siguiente), con capturas de cada paso. Arma una casa inventada en una
  carpeta temporal (también la carpeta personal: `HOME` apunta ahí), un Roku falso, una TV con Android que se conecta,
  Windows que bloquea la entrada y OpenSubtitles falso; el servidor escucha solo en 127.0.0.1 y no toca nada real.
  Revisa cada paso, lo que queda en `config.json`, que nada se salga a lo ancho y la paleta; al final, desde «otro
  aparato», pide el código de la TV (sin TV y con el Roku falso), escribe uno malo y el bueno. Sale con código 1 si algo falla.
- `web_youtube_continua.py <carpeta> <ancho>` — ajuste de reproducción continua (Fila de reproducción → Ajustes
  generales) y el aviso «Recomendado por YouTube» en el navegador. ⚠ Usa el servidor real: prende y apaga el
  ajuste real y reproduce un video corto; ensucia el historial.
- `servidor_de_prueba.py` — servidor de la web con una copia de los datos (puerto 8790) para pruebas aisladas;
  usa la carpeta de `CINE_PRUEBA` (por omisión `/tmp/cine-prueba`): copia ahí `datos/` antes de arrancarlo.
- `datos_demo.py [servir [carpeta] [--tv [IP]] | capturas SALIDA]` — una biblioteca de EJEMPLO para ver One TV sin
  datos de nadie: 12 películas y 4 capítulos de una serie de DOMINIO PÚBLICO (tramos reales de unos 5 min bajados de
  Internet Archive, solo ese tramo, a 480p; el código de IMDb o TheTVDB va en la carpeta y de ahí salen los pósters),
  cinco álbumes con grabaciones CC0 / de dominio público (Bach, Chopin, Beethoven; portadas con pinturas de dominio
  público de Wikimedia Commons), y YouTube con suscripciones a canales públicos (NASA, ESA, JWST, Blender) importadas
  de un Takeout inventado, sin cuenta de nadie. Las fuentes y licencias están en los comentarios del archivo. Lo que se
  baja queda en `~/Library/Caches/one-tv-demo` (o `CINE_DEMO_CACHE`), fuera del repositorio; sin internet, las
  películas y la música caen a videos y tonos sintéticos. Sin argumentos, arma todo en una carpeta temporal y sirve en
  `http://localhost:8793` (escucha en toda la red de la casa; cambia el puerto con `CINE_PUERTO`). Con `capturas SALIDA`
  abre la web en Chrome sin ventana y deja en `SALIDA` las capturas de laptop (1280 px) y teléfono (390 px); tarda unos
  4 minutos y apaga todo al terminar. Con `servir --tv [IP]` busca tu Roku (IP y contraseña del modo desarrollador de
  tu `config.json`, o `ROKU_IP` y `ROKU_PASSWORD`) e INSTALA la app apuntando a esta biblioteca, para tomar capturas
  de la TV; después, `./cine instalar` la deja otra vez apuntando a tu servidor de verdad. Sin `--tv`, finge una TV
  conectada y no toca el servicio real, su carpeta de datos ni la TV.
- `doblaje_trozos_vs_original.py <carpeta> <video> <pista.m4a>` — compara los trozos que se mandan a la tele
  con una pista aparte contra la pista que viene dentro del archivo (necesita numpy: usar el Python de
  `~/Library/Application Support/cine-roku/doblaje/bin/python`).
- `musica_grande.py CARPETA [canciones]` — una música de EJEMPLO grande, inventada (por omisión 70 000 canciones,
  ~7 150 álbumes y ~3 850 artistas, con un «Varios artistas» de miles de canciones y una lista de 5 000): cada
  canción es un enlace a la misma canción corta y cada álbum trae una portada de un color, así no ocupa espacio; lo ya
  leído queda en `CARPETA/datos/musica.json` (no hace falta ffprobe). Sirve para medir y probar la música por partes en
  la web, el Roku y Android TV (config «musica»: `[CARPETA/musica]`, datos del servidor en `CARPETA/datos`).
  `test_musica_grande.py` usa la misma música, en memoria.
- `intro_temporada.py "<carpeta de la temporada>" [otra carpeta o video …] [--detalle]` — detecta la entrada
  («Saltar intro») de cada episodio igual que el servicio (`mac/introsync.py`, con el Python de numpy del
  doblaje y prioridad baja) y muestra una tabla: inicio, fin, duración y confianza (cuántos compañeros
  coinciden). Solo lee los videos. Con `--detalle`, el tramo común de cada par de episodios. Con videos de
  series distintas sirve de control: no debe salir ningún tramo común. Al final dice cuánto tardó y su CPU.
- `test_subtitulos_automaticos.py` — subtítulos que se bajan solos (`mac/subs_auto.py`) con un OpenSubtitles falso:
  prioridades, reserva, cupo y su renovación, 406 y 429, lo que no existe todavía, lo que ya está, cuál se elige,
  nombres de archivo y que el video no se toca; el cliente (`mac/subtitles_online.py`) contra un servidor falso en la
  misma computadora y, con ffmpeg, que la biblioteca de verdad reconoce lo bajado. Sin red.
- `test_subtitulos_alineados.py` — subtítulos aparte alineados solos con la voz (`mac/subsync.py`): leer y corregir
  .srt/.vtt, el trabajo en segundo plano (no repite, reintenta, guarda el alineado en la caché sin tocar el original)
  y lo que reciben la tele y la web. Con numpy (`CINE_PYTHON_NUMPY=/ruta/al/python`), además, audio sintético con
  desfase fijo, otra velocidad, una escena de más o de menos y un subtítulo de otra película.
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
- `test_bibliotecas_ajenas.py` — una biblioteca falsa acomodada para Plex (en un «NAS»): el organizador no mueve nada
  ahí, lo bajado va a la carpeta de One TV (o no se agrega, con un aviso), se leen bien películas, ediciones, partes,
  series con «Season 01» y «Specials», los códigos de Plex y Jellyfin, los pósters de la carpeta (y el fondo después
  de internet), la identificación por nombre (con internet simulado), los subtítulos bajados van a la carpeta de One
  TV y la biblioteca los encuentra, el doblaje no se agrega ahí, carpetas de solo lectura, «solo_leer» en config.json,
  la pregunta de `./cine configurar`, y que la carpeta de One TV se sigue ordenando como siempre. Una parte lee la
  biblioteca de verdad con ffprobe (un video de 2,5 min hecho con ffmpeg y enlazado con cada nombre).
- `test_linea_de_tiempo.py` — la conversión completa (`mac/transcode.py`) con un video sintético que trae 2 s dañados
  (bytes ilegibles o pedazos faltantes): la salida dura lo mismo, cada trozo empieza en su segundo, la imagen se
  congela en vez de saltar y el sonido que falta se vuelve silencio (así los subtítulos no se corren). También que al
  detener ffmpeg a mitad no quede un trozo cortado que se mande como completo. Usa el chip de video si lo hay; si no,
  el procesador (libx264).

Después de cualquier prueba que reproduzca algo en el servidor de verdad: restaurar `progreso.json` / `youtube.json`
(o, mejor, probar siempre con `servidor_de_prueba.py` y una copia de los datos).

## Ubuntu (Linux)

- `test_linux.py` — el servidor fuera de macOS, sin red y en cualquier sistema (lo de Linux se simula): carpetas de
  XDG y del usuario (`mac/hostos.py`), la unidad de systemd y `./cine autoarranque` (`mac/linuxservice.py`), qué
  codificador de video se elige (`mac/encoders.py`, con un ffmpeg falso; y la prueba de un segundo con el ffmpeg de
  verdad), el mosaico sin el chip de la Mac y con ffmpeg 6.1, el código QR en Python puro (igual píxel a píxel que el
  de CoreImage para un enlace normal) y lo que revisa `./cine` antes de arrancar (con un `uname` falso que dice Linux).
- `humo_servidor.py [--puerto 8794] [--dejar]` — arranca el servidor de verdad (copia del programa y carpeta personal
  temporales; el Roku apuntado a 127.0.0.1, así que no toca ninguna TV) con tres videos sintéticos de 160 s (directo,
  copia de video con audio convertido y HEVC de 10 bits que se convierte entero) y revisa `/api/library`, un póster,
  la lista HLS y un trozo de cada conversión (que sea H.264) y el QR en PNG. Sirve en macOS y en Linux; sale con
  código 1 si algo falla. Lo corre también GitHub, en el trabajo `ubuntu`.
- `ubuntu.sh` — en un contenedor de Docker con Ubuntu 24.04 (`ubuntu/Dockerfile`: python3, python3-venv y ffmpeg 6.1
  de apt, usuario normal) corre todas las pruebas, con el mismo `faulthandler` que GitHub, y `humo_servidor.py`.
  Borra el contenedor al terminar; la imagen `one-tv-pruebas-ubuntu` queda para la próxima vez.
- `ubuntu_systemd.sh` — `./cine autoarranque` con systemd de verdad: un contenedor que arranca como una computadora
  (`ubuntu/Dockerfile.systemd`, necesita Docker con `--privileged`), entrando por SSH como usuario normal:
  `./cine configurar`, el servicio y «linger», que se levante solo si se cae, que arranque tras reiniciar sin que
  nadie inicie sesión, `./cine estado` y `./cine quitar-autoarranque`. Tarda ~1 min (más la primera vez).

## Windows

- `test_windows.py` — el servidor en Windows, sin red y en cualquier sistema (lo de Windows se simula): carpetas en
  `%LOCALAPPDATA%` y las del usuario aunque estén en OneDrive (`mac/hostos.py`, `mac/winapi.py`), la tarea del
  Programador de tareas y su lanzador sin ventana (`mac/windowsservice.py`), `cine autoarranque`, `estado` y
  `quitar-autoarranque`, el codificador (NVENC, Quick Sync, AMF), que no se duerma, pausar ffmpeg sin señales, los
  ffmpeg que quedaron vivos, los entornos aparte (`Scripts\python.exe`), la prioridad baja sin `nice`, nombres de
  archivo válidos y archivos que se mandan mientras ffmpeg los reemplaza. Las que necesitan Windows de verdad (carpetas
  conocidas, `SetThreadExecutionState`, pausar un proceso, que los hijos se cierren con el lanzador, detener un ffmpeg)
  se saltan solas fuera de Windows.
- `humo_windows.py [--puerto 8798] [--de-verdad]` — en Windows: `humo_servidor.py`, `cine.cmd estado` (la cadena
  `cine.cmd` → `windows\cine.ps1` → Python) y, con `--de-verdad`, el arranque automático con el Programador de tareas
  de verdad (usa `%LOCALAPPDATA%\cine-roku`, así que solo corre en GitHub Actions). Lo corre GitHub en el trabajo
  `windows`.
- `windows\cine.ps1` se revisó aquí con PowerShell 7 en un contenedor de Linux (que se lea bien y el camino «falta
  ffmpeg → winget → arranca»); en Windows lo prueba el trabajo de GitHub.

- `docker.sh [puerto 8802]` — la imagen de Docker (`Dockerfile`, `docker/entrypoint.sh`): la construye, la arranca en red puente
  con tres videos de ejemplo montados de solo lectura y revisa `/api/status`, `/api/library`, un póster, la lista HLS, un
  trozo convertido con libx264, que no escriba en la biblioteca, que corra sin ser «root» y que los datos sobrevivan al
  recrear el contenedor. Necesita Docker; no lo corre GitHub. `test_docker.py` revisa sin Docker las carpetas del
  contenedor y las variables de entorno (`ROKU_IP`, `ROKU_PASSWORD`, `PUERTO`).
