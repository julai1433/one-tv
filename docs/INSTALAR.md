# Instalar One TV

Guía paso a paso, para alguien que no conoce el proyecto y no necesita saber de programación. Al terminar vas a ver
**tus** películas y series (y YouTube sin anuncios, y tu música) en la TV y en cualquier navegador de tu casa.

## Cómo encajan las piezas

One TV son tres piezas que hablan entre sí por tu propio Wi-Fi. No hay cuentas ni nube:

1. **El servidor**: un programa que corre en una computadora de tu casa. Ahí viven los videos, y es quien los prepara
   para que cualquier pantalla los pueda ver.
2. **La app de la TV**: se instala en tu TV (o en el aparato que la acompaña) y muestra el catálogo con el control remoto.
3. **La web**: una página que el servidor ofrece a cualquier navegador (computadora, teléfono, tableta). No se instala nada.

## Qué funciona hoy

| Pieza | Hoy | Pronto |
|---|---|---|
| **Servidor** (la computadora) | **macOS** y **Ubuntu 24.04** | **Windows 10 y 11** (en prueba) |
| **App de la TV** | **Roku** | Google TV y Android TV (y Fire TV) |
| **Web** | **Cualquier navegador**, en cualquier sistema | |

Los detalles y el orden están en la [hoja de ruta](HOJA_DE_RUTA.md). Esta guía tiene **todos** los pasos de macOS y
Roku (Ubuntu tiene la suya); cuando haya otros sistemas y otras TV, se agrega su sección en la Parte 2 o la Parte 3 y lo demás no cambia.
Si tu computadora o tu TV todavía no están en la lista, no puedes instalar el servidor ahí por ahora, pero sí puedes
usar la web desde cualquier aparato una vez que otra computadora haga de servidor.

¿Tu servidor va a ser una computadora con **Ubuntu** en vez de una Mac? Sigue [INSTALAR-UBUNTU.md](INSTALAR-UBUNTU.md).
¿Con **Windows**? Sigue [INSTALAR-WINDOWS.md](INSTALAR-WINDOWS.md).

Tiempo aproximado: 20 minutos, casi todo esperando descargas.

## Índice

- [Parte 1. Antes de empezar](#parte-1-antes-de-empezar)
- [Parte 2. El servidor](#parte-2-el-servidor)
  - [macOS](#servidor-en-macos): [programas de apoyo](#paso-1-instalar-los-programas-de-apoyo), [descargar el proyecto](#paso-2-descargar-el-proyecto), [primer arranque](#paso-3-primer-arranque), [permisos](#paso-4-permisos-que-va-a-pedir-macos), [arranque automático](#paso-5-arranque-automático)
  - [Ubuntu](#servidor-en-ubuntu) y [Windows](#servidor-en-windows)
- [Parte 3. La TV](#parte-3-la-tv)
  - [Roku](#tv-roku): [modo desarrollador](#paso-6-activar-el-modo-desarrollador-del-roku), [instalar la app](#paso-7-instalar-la-app-en-el-roku)
  - [Google TV, Android TV y Fire TV](#tv-google-tv-android-tv-y-fire-tv-pronto) y [sin app de TV](#sin-app-de-tv-solo-la-web)
- [Parte 4. Tus videos](#parte-4-tus-películas-y-series)
- [Parte 5. Opcional](#parte-5-opcional): [fuera de casa](#opcional-fuera-de-casa-con-tailscale), [subtítulos](#opcional-subtítulos-de-opensubtitles), [YouTube](#opcional-youtube-y-el-takeout-de-google), [música](#opcional-tu-música), [doblaje latino](#opcional-doblaje-latino-automático), [ícono en la barra de menú (macOS)](#opcional-macos-el-ícono-en-la-barra-de-menú)
- [Si algo falla](#si-algo-falla)
- [Referencia de `config.json`](#referencia-de-configjson)

---

## Parte 1. Antes de empezar

**Qué necesitas**

- **Una computadora que haga de servidor**, que quede encendida (o al menos despierta) cuando quieras ver algo. Hoy,
  una **Mac con macOS 14 o más nuevo**, con Python 3.9 o más nuevo y ffmpeg 7 o más nuevo (los de Apple y Homebrew sirven; en
  [el paso 1](#paso-1-instalar-los-programas-de-apoyo) se instalan).
- **Una TV con su aparato**, en el **mismo Wi-Fi** que la computadora. Hoy, un **Roku** (cualquier modelo con «modo
  desarrollador», que son casi todos). Sin app de TV, la web funciona igual desde cualquier navegador.
- Tus **películas y series** en archivos de video (`.mkv`, `.mp4`…) en esa computadora. El proyecto no trae ni
  descarga contenido.
- Internet para instalar los programas y para pósters, sinopsis y YouTube.
- Opcional: **Google Chrome o Brave**, solo para la pestaña «En vivo» (páginas web de eventos en directo).

**La Terminal.** Hoy la instalación pide pegar unos comandos en la **Terminal** (en macOS, la app que recibe órdenes
escritas: ábrela con Spotlight, `⌘ + Espacio`, escribiendo «Terminal»). Copia cada comando, pégalo y pulsa Enter. Una
de las metas del proyecto es que no haga falta (ver la [hoja de ruta](HOJA_DE_RUTA.md)).

---

## Parte 2. El servidor

El servidor es lo que se instala en la computadora. Elige la sección de tu sistema; las demás partes de esta guía son
iguales para todos.

### Servidor en macOS

#### Paso 1. Instalar los programas de apoyo

**Homebrew** es el «instalador de programas» de los desarrolladores para macOS. Con él se instala lo demás.

1. Si no lo tienes, instálalo con el comando de la página <https://brew.sh> (es una sola línea que se pega en la
   Terminal). Al terminar, te muestra dos o tres comandos «Next steps»: cópialos y pégalos también.
2. Instala **ffmpeg**, el programa que convierte los videos que el Roku no entiende:

   ```
   brew install ffmpeg
   ```

3. Comprueba que **python3** existe (viene con las «herramientas de línea de comandos» de Apple, que
   Homebrew ya instaló en el punto 1):

   ```
   python3 --version
   ffmpeg -version
   ```

   Ambos deben mostrar un número de versión. Si `python3` dice «command not found», corre
   `xcode-select --install` y espera a que termine.

No hace falta instalar **yt-dlp** (el programa que baja los videos de YouTube): el proyecto lo instala solo, en
un entorno propio, y lo actualiza cada 24 horas.

#### Paso 2. Descargar el proyecto

Elige una carpeta que no sea Documentos, Descargas ni Escritorio (macOS las protege y da problemas al arrancar
solo; por ejemplo, `~/Proyectos`). Con **git** (viene con las herramientas de Apple):

```
mkdir -p ~/Proyectos && cd ~/Proyectos
git clone https://github.com/julai1433/one-tv.git
cd one-tv
```

Sin git: en la página del repositorio, botón verde **Code → Download ZIP**, descomprime en `~/Proyectos`, y en la
Terminal `cd ~/Proyectos/one-tv` (o el nombre que tenga la carpeta).

Si al ejecutar `./cine` dice «permission denied», corre una vez `chmod +x cine "One TV.command"`.

#### Paso 3. Primer arranque

Desde la carpeta del proyecto:

```
./cine
```

Como todavía no hay configuración, te hace **cuatro preguntas** (Enter acepta lo que sale entre corchetes):

1. **Carpeta de la biblioteca**: donde van a estar tus películas y series. Sugiere `~/Movies/Biblioteca`. Si
   no existe, la crea. (`~` significa «tu carpeta de usuario».)
2. **Contraseña del modo desarrollador del Roku**: la vas a inventar en el [paso 6](#paso-6-activar-el-modo-desarrollador-del-roku). Si aún no la tienes (o no usas Roku), deja
   vacío y ponla después en `config.json` (campo `roku_password`).
3. **IP del Roku**: la **dirección IP** es el número que identifica al Roku dentro de tu red (algo como
   `192.168.1.50`). Déjalo vacío: el programa lo busca solo. Solo pon un número si más adelante no lo encuentra.
4. **Carpeta de música** (opcional): donde está tu música (ver [Tu música](#opcional-tu-música)). Sugiere `~/Music/Biblioteca` si existe;
   escribe «no» si no quieres la sección Música.

Con eso crea el archivo `config.json`. También revisa que ffmpeg esté instalado y te avisa si no. Puedes repetir
las preguntas cuando quieras con `./cine configurar`; no pierde lo que ya tenías (claves, títulos).

Después de las preguntas, `./cine` arranca el servidor en esa ventana de la Terminal. Verás algo como
`✓ Sirviendo en http://192.168.1.20:8765` y se abre la página en el navegador de la computadora (vacía si aún no hay
videos). Para pararlo: `Ctrl + C`. Mientras no hagas el [paso 5](#paso-5-arranque-automático), el servidor solo vive mientras esa ventana esté
abierta.

#### Paso 4. Permisos que va a pedir macOS

La primera vez, macOS muestra avisos. Acepta todos; sin ellos no funciona:

- **«"python3" quiere buscar y conectarse a dispositivos de tu red local»** (permiso de **Red local**): déjalo en
  **Permitir**. Es lo que deja hablar con el Roku. Si lo negaste sin querer: Ajustes del Sistema → Privacidad y
  seguridad → **Red local** → activa el interruptor de `python3` (o de Terminal).
- **Acceso a carpetas** (por ejemplo «"python3" quiere acceder a archivos en la carpeta Películas» o similar):
  **Permitir**. Si la biblioteca está en un disco externo, también sale «volúmenes extraíbles».
- **Firewall**: si lo tienes activado, macOS puede preguntar si permites conexiones entrantes: **Permitir**. Así
  la TV y los teléfonos pueden pedirle videos a la computadora.
- Si más adelante cambias de dispositivo o de red y algo deja de conectar, este es el primer lugar donde mirar.

#### Paso 5. Arranque automático

Para no tener que dejar una Terminal abierta, y que el servidor arranque solo cada vez que inicies sesión en la computadora:

```
./cine autoarranque
```

Registra un **servicio de macOS** (un programa que corre de fondo; se llama «launchd») y se relanza solo si se
cae. Dice `✓ Listo…` y muestra las direcciones. Para el servicio, macOS necesita una copia del programa en
`~/Library/Application Support/cine-roku`, así que **cada vez que cambies algo** (por ejemplo `config.json`)
corre otra vez `./cine`: copia los cambios y reinicia el servicio.

- Ver si está corriendo y dónde entrar: `./cine estado`.
- Registro de lo que hace: `~/Library/Logs/cine-roku.log`.
- Quitarlo: `./cine quitar-autoarranque`.

La computadora tiene que estar encendida y despierta. Con la tapa cerrada de una laptop se duerme: déjala abierta (la
pantalla puede apagarse; mientras se ve algo, la computadora no se duerme sola).

### Servidor en Ubuntu

Ubuntu 24.04 tiene su propia guía, más corta: **[INSTALAR-UBUNTU.md](INSTALAR-UBUNTU.md)**. La parte de la TV (abajo)
es igual.

### Servidor en Windows

Windows 10 y 11 tienen su propia guía, más corta (un solo comando o doble clic): **[INSTALAR-WINDOWS.md](INSTALAR-WINDOWS.md)**.
La parte de la TV (abajo) es igual.

---

## Parte 3. La TV

La app de la TV es lo que muestra el catálogo en la pantalla grande. Elige tu TV; con cualquiera, la web sigue funcionando.

### TV: Roku

#### Paso 6. Activar el modo desarrollador del Roku

El **modo desarrollador** es un ajuste del Roku que permite instalar apps que no vienen de la tienda oficial. Es
gratis, no toca tus otras apps ni cuentas, y hace falta porque esta app es tuya y no está en la tienda.

1. Con el **control remoto del Roku** (el de siempre, no el del teléfono), en la pantalla de **Inicio**, pulsa
   esta secuencia, sin prisa pero seguida:

   **Inicio** (el botón con una casa) **3 veces** → **Arriba 2 veces** → **Derecha** → **Izquierda** → **Derecha** →
   **Izquierda** → **Derecha**

2. Aparece la pantalla **«Developer Settings»**. Anota la **dirección IP** que muestra (ahí está la IP del
   Roku) y elige **«Enable installer and restart»**.
3. Acepta el acuerdo de licencia. Te pide crear una **contraseña**: inventa una que recuerdes (por ejemplo, de 6
   o más caracteres). **Esta es la contraseña del modo desarrollador**, la que pide la pregunta 2 del [primer arranque](#paso-3-primer-arranque).
4. El Roku se reinicia. Ya está.

**¿Cómo encuentro la IP del Roku si no la anoté?** Configuración → Red → Acerca de (Settings → Network → About).
O en la app del router, en la lista de dispositivos conectados. Normalmente no la necesitas: la computadora lo encuentra sola.

Si pusiste la contraseña más tarde: abre `config.json` con TextEdit y llena `"roku_password"`
(ver [la referencia](#referencia-de-configjson)).

#### Paso 7. Instalar la app en el Roku

Con el servidor arrancado ([paso 3](#paso-3-primer-arranque)) y la TV encendida, el propio programa **instala la app «One TV» en
el Roku** cuando lo encuentra. Verás `✓ … en 192.168.x.x` en la Terminal. Si no pasó solo, o cambiaste la
contraseña:

```
./cine instalar
```

Busca la app **«One TV»** al final de tus apps en el Inicio del Roku. Ábrela: aparece el catálogo. Mientras
la app está instalada, el servidor la mantiene al día solo (sin sacarte de Netflix ni de lo que estés viendo).

Si dice `✗ No encontré el Roku en la red`: revisa que la TV esté encendida y en el mismo Wi-Fi; pon su IP en
`config.json` → `"roku_ip"` y repite. Si dice que la contraseña es incorrecta, corrige `"roku_password"`.

### TV: Google TV, Android TV y Fire TV (pronto)

La app para Google TV y Android TV (Chromecast con Google TV, Nvidia Shield y TV con Google TV integrado) es lo
segundo en la [hoja de ruta](HOJA_DE_RUTA.md); la misma servirá para Fire TV. Cuando exista, esta sección tendrá sus
pasos y nada de lo demás cambia.

### Sin app de TV: solo la web

Mientras tu TV no tenga app, abre `http://<dirección de la computadora>:8765` en cualquier navegador de la casa (la
dirección exacta la muestra `./cine estado`). Si tu TV o su aparato trae navegador, también sirve ahí.

---

## Parte 4. Tus películas y series

**En la carpeta de la biblioteca** (la del [primer arranque](#paso-3-primer-arranque); la lista de carpetas está en `config.json` → `carpetas`)
puedes soltar los archivos de video tal cual: el programa los identifica (por internet, con IMDb y TVmaze, sin
cuenta) y **los ordena solo**. Con esta forma:

```
Biblioteca/
├── Películas/
│   └── Título (2001) {imdb-tt0123456}/Título (2001).mkv
└── Series/
    └── Nombre de la serie (2010) {tvdb-123456}/
        └── Season 01/Nombre de la serie (2010) - S01E02 - Título del episodio.mkv
```

- El código entre llaves (`{imdb-tt…}`, `{tvdb-…}`) es el número de la película o serie en IMDb / TheTVDB; sirve
  para bajar el póster y la sinopsis correctos. Lo pone el organizador; si nombras a mano, agrégalo
  para que no haya confusión.
- **Nombra como quieras y déjalo suelto** («Mi.Pelicula.2019.1080p.mkv», «serie s01e03.mkv»): cada minuto el
  organizador lo identifica y lo mueve a su lugar. Lo que no logra identificar se queda donde está (lo
  reintenta al día siguiente); si tiene un nombre razonable, igual sale en el catálogo.
- **Descargas con Transmission** (el programa de torrents): las terminadas en `~/Downloads/Torrents` se
  aprovechan solas. El organizador crea en la biblioteca un **enlace duro** (el mismo archivo con otro nombre, sin
  ocupar espacio extra), así Transmission sigue compartiéndolo y, si borras el torrent, la película se queda.
  Para usar otra carpeta de descargas: `config.json` → `"descargas": ["~/Downloads/Otra"]`.
- El catálogo se actualiza solo. Para forzarlo a mano, en la TV el botón **\*** del control (en Roku); en la web,
  recarga la página.
- Puedes ver cómo llegará cada video a la TV con `./cine catalogo`.

**Evita** guardar la biblioteca en Documentos, Descargas o Escritorio: macOS protege esas carpetas y un servicio en
segundo plano necesita tu permiso para leerlas. `~/Movies` va perfecto. (Para Descargas, donde One TV busca lo que
bajas por torrent y el Takeout, macOS te pide permiso una vez: «python3 quiere acceder a Descargas» → Permitir. Si
no apareció, en Configuración del Sistema → Privacidad y seguridad → Archivos y carpetas.) También puedes usar un disco externo (`/Volumes/MiDisco/Peliculas`) si
está conectado al arrancar.

---

## Parte 5. Opcional

Nada de esto hace falta para empezar; cada cosa se agrega cuando la quieras.

### Opcional: fuera de casa con Tailscale

En la misma red Wi-Fi, el teléfono ya puede abrir la página con `http://<IP de la computadora>:8765` (la dirección exacta la muestra
`./cine estado`). Para **abrirla también fuera de tu red, con https y como si fuera una app**, se usa Tailscale (por ahora; compartir con familia y amigos está en la [hoja de ruta](HOJA_DE_RUTA.md)).

**Tailscale** es un servicio gratuito (para uso personal) que conecta tus dispositivos entre sí, estén donde estén,
como si compartieran la misma red privada (tu «tailnet»). Nada se publica en internet: solo tus dispositivos entran.

1. Crea una cuenta gratis en <https://tailscale.com> e instala la app **Tailscale** en la computadora (desde su página o
   la tienda de aplicaciones de macOS) e inicia sesión. Instálala también en el teléfono, con **la misma cuenta**.
2. En <https://login.tailscale.com/admin/dns> activa **MagicDNS** y, más abajo, **HTTPS Certificates**
   (Habilitar certificados HTTPS). Sin esto no hay https.
3. En la computadora, en la carpeta del proyecto:

   ```
   ./cine tailscale
   ```

   Muestra una dirección como `https://<nombre-de-tu-computadora>.<tu-red>.ts.net:8766`. Tailscale la recuerda aunque
   reinicies.
4. En el teléfono, con Tailscale encendido, abre esa dirección en el navegador (en iPhone, **Safari**). Para tenerla como app: botón
   **Compartir** → **Añadir a pantalla de inicio**.

Para quitar la publicación: `tailscale serve --https=8766 off`.

### Opcional: subtítulos de OpenSubtitles

Sirve para **buscar subtítulos por internet** desde la ficha de una película. Los que ya vienen dentro del video o
junto a él funcionan sin esto.

1. Crea una cuenta gratis en <https://www.opensubtitles.com>.
2. Entra a <https://www.opensubtitles.com/consumers>, crea una «consumer» (le pones cualquier nombre) y copia su
   **API key** (la clave que identifica tu programa ante el servicio).
3. Abre `config.json` con TextEdit y llénalo:

   ```
   "opensubtitles": { "api_key": "TU_CLAVE", "usuario": "", "clave": "" }
   ```

   Con solo la clave tienes 5 descargas al día. Si además pones tu `usuario` y `clave` (los de tu cuenta), 20.
4. Corre `./cine` para aplicar.

### Opcional: YouTube y el Takeout de Google

**YouTube sin anuncios** funciona desde el principio, sin cuenta: en la TV, fila «YouTube» → «Buscar en
YouTube»; en la web, pestaña YouTube (busca o pega un enlace). Esta parte instala sola su herramienta (`yt-dlp`) la
primera vez; necesita internet y tarda un minuto.

Para que además aparezcan **tus suscripciones, tus listas y tu historial**, se importa un **Takeout**: una copia
de tus datos que Google te deja descargar (no se comparte tu contraseña con nadie). La misma ayuda está en la web:
pestaña YouTube → «Cómo traer tu cuenta».

![Código QR de takeout.google.com](../mac/web/qr-takeout.png)

*Escanéalo con el teléfono para abrir takeout.google.com.*

1. Entra a <https://takeout.google.com> con tu cuenta de Google y pulsa **Anular selección**.
2. Marca solo **YouTube y YouTube Music**.
3. En **«Se incluyen todos los datos de YouTube»**, deja **historial**, **listas de reproducción** y
   **suscripciones**, y quita **«vídeos»**.
4. En **«Varios formatos»**, cambia el historial a **JSON** (también se lee en HTML, pero JSON trae más datos).
5. Pulsa **Paso siguiente**, elige una sola exportación en archivo **.zip** y pulsa **Crear exportación**.
6. Cuando llegue el correo (Google tarda de unos minutos a un par de horas), descarga el `.zip` en la computadora
   donde corre One TV y déjalo en **Descargas** (`~/Downloads`) sin cambiarle el nombre (empieza con `takeout-`).
   One TV lo importa solo en unos minutos (revisa Descargas cada 10 minutos) y aparecen «Tus listas», «Nuevos de
   tus canales» y el historial. No borra ni mueve el archivo. Para actualizar más adelante, repite el proceso.

### Opcional: tu música

La sección **Música** (en la TV y en la web) muestra la música de una carpeta de la computadora: tus listas, lo
agregado hace poco, los artistas y los álbumes, con sus portadas. No hace falta ningún programa más.

- **Dónde**: la carpeta que contestaste en la pregunta 4 del [primer arranque](#paso-3-primer-arranque) (por omisión `~/Music/Biblioteca`).
  Para cambiarla: `./cine configurar`, o en `config.json` el campo `musica` (ver la referencia).
- **Cómo ordenarla**: como quieras (por ejemplo `Artista/Álbum/01 Canción.flac`). One TV lee las **etiquetas** de
  cada archivo (título, artista, álbum, número, año) y la portada que trae adentro o un `cover.jpg` (o
  `folder.jpg`) en la carpeta del álbum. Archivos: FLAC, ALAC/AAC (`.m4a`), MP3, WAV, AIFF, Ogg y Opus.
- **Listas**: los archivos `.m3u` o `.m3u8` que estén en esa carpeta (por ejemplo los que hace Spotify, iTunes o
  un programa de descargas) aparecen como «Tus listas», en su orden.
- **Al escuchar**: en la web suena abajo, como Spotify (sigue al cambiar de página y se recuerda aunque cierres la
  página); en la TV, con la portada en grande y **‹ ›** para la canción anterior o la siguiente. «En la TV» la manda
  desde la web. Lo nuevo aparece solo en un minuto. FLAC, ALAC, WAV… se convierten una sola vez a AAC de
  256 kb/s (los guarda la computadora en su caché) para que suenen en cualquier navegador y en el Roku.

### Opcional: doblaje latino automático

No hay nada que configurar. Si en tu biblioteca o en las descargas aparece **otra versión** de una película o
episodio que ya tienes (por ejemplo, una «Dual Latino») con un audio en español latino que a la tuya le falta, la
computadora toma **solo ese audio**, lo sincroniza con tu video y lo deja como una pista más: «Español (Latino) ·
agregado». Tu video no se toca. Tarda 1–2 minutos por película, con prioridad baja, y la primera vez instala su
propio entorno de Python con `numpy` (una librería de cálculo; necesita internet). Detalles en
[DETALLES.md](DETALLES.md).

### Opcional (macOS): el ícono en la barra de menú

```
./cine barra
```

Pone arriba a la derecha un ícono que dice si el servidor está encendido, si encontró el Roku y qué se ve, y
tiene un interruptor para apagarlo o encenderlo. Necesita las herramientas de línea de comandos de Apple
(`xcode-select --install`) y una Mac con chip Apple (M1 o más nuevo). Quitarlo: `./cine quitar-barra`.

---

---

## Si algo falla

Primero, `./cine estado` y las últimas líneas de `~/Library/Logs/cine-roku.log` (si usas el autoarranque).

| Síntoma | Qué hacer |
|---|---|
| `✗ Falta ffmpeg` | `brew install ffmpeg`. Si `brew` no existe, [paso 1](#paso-1-instalar-los-programas-de-apoyo). |
| `./cine: permission denied` | `chmod +x cine "One TV.command"` |
| `python3: command not found` | `xcode-select --install`, esperar, y reintentar. |
| Dice `✗ No encontré el Roku en la red` | TV encendida, mismo Wi-Fi que la computadora, permiso de **Red local** ([paso 4](#paso-4-permisos-que-va-a-pedir-macos)). Pon la IP a mano en `config.json` → `"roku_ip"`. Algunos routers aíslan los dispositivos entre sí («aislamiento de clientes» o «AP isolation»): desactívalo. |
| La app del Roku no aparece | Revisa que el modo desarrollador esté activo y la contraseña de `config.json` sea la misma; corre `./cine instalar`. |
| La app desapareció del Roku | Pasa tras restablecer el Roku: repite el [paso 6](#paso-6-activar-el-modo-desarrollador-del-roku) con la misma contraseña y corre `./cine instalar`. |
| La TV dice que no encuentra la computadora | La computadora está apagada, dormida, en otro Wi-Fi o el servicio no corre (`./cine estado`). La app reintenta sola cada 5 segundos. |
| Se corta al cerrar la tapa | La computadora se duerme con la tapa cerrada. Déjala abierta. |
| Mis películas no salen | Comprueba que estén en una de las carpetas de `config.json` → `carpetas`, que no sea Documentos/Descargas/Escritorio, y corre `./cine catalogo` para ver qué encuentra. |
| «El puerto 8765 está ocupado» | Ya hay otro `./cine` abierto (o el servicio automático). Ciérralo con `Ctrl + C`, o usa `./cine estado`. |
| El teléfono no abre la página fuera de casa | Tailscale encendido en el teléfono y en la computadora ([Tailscale](#opcional-fuera-de-casa-con-tailscale)); los mismos dos dispositivos, misma cuenta. |
| Cambié `config.json` y no pasa nada | Corre `./cine` para aplicar (con el autoarranque copia los cambios y reinicia). |
| Quiero empezar la configuración de cero | `./cine configurar`, o borra `config.json` y corre `./cine`. |

Los pósters, subtítulos extraídos e índices se guardan en `~/Library/Caches/cine-roku`; se puede borrar sin problema.

## Referencia de `config.json`

`./cine` lo crea por ti ([primer arranque](#paso-3-primer-arranque)). Guarda contraseñas, así que **no se comparte ni se sube al repositorio**. JSON no
admite comentarios, así que aquí se explica cada campo; el archivo `config.example.json` es la plantilla completa.

```
{
  "carpetas": ["~/Movies/Biblioteca"],
  "puerto": 8765,
  "roku_ip": "",
  "roku_password": "la-contraseña-del-paso-5",
  "titulos": {},
  "opensubtitles": { "api_key": "", "usuario": "", "clave": "" }
}
```

| Campo | Para qué |
|---|---|
| `carpetas` | Lista de carpetas donde buscar videos. El organizador acomoda lo nuevo dentro de cada una. |
| `puerto` | Número de «puerta» del servidor. Déjalo en 8765 salvo que otro programa lo use. |
| `roku_ip` | Vacío = la computadora busca el Roku sola. Si falla, pon su IP entre comillas (`"192.168.1.50"`). |
| `roku_password` | Contraseña del modo desarrollador del Roku ([paso 6](#paso-6-activar-el-modo-desarrollador-del-roku)). |
| `musica` | Opcional. Lista de carpetas con tu música ([Tu música](#opcional-tu-música)). Si falta, se usa `~/Music/Biblioteca` cuando existe; `[]` = sin la sección Música. |
| `escuchar` | Opcional. En qué red escucha el servidor: vacío = toda la red de la casa (la TV lo necesita); `"127.0.0.1"` = solo esta computadora. No abras el puerto a internet (ver [DETALLES.md](DETALLES.md#seguridad)). |
| `titulos` | Opcional. Nombres a mano por código de IMDb, para títulos que el Roku no puede dibujar (chino, japonés…). Ejemplo: `"titulos": { "tt0123456": "Nombre que quiero ver (2001)" }`. Vacío está bien. |
| `opensubtitles` | Ver [Subtítulos de OpenSubtitles](#opcional-subtítulos-de-opensubtitles). |
| `descargas` | Opcional. Carpetas de descargas de torrents que el organizador vigila (por omisión, `~/Downloads/Torrents`). |
| `sin_conexion` | Opcional. Carpeta donde se guardan los videos y listas de YouTube para verlos sin internet (por omisión `~/Movies/One TV/Sin conexión`). Cada video queda como un HLS (`<id>/index.m3u8`) que la TV y la web abren por las mismas direcciones de siempre. |
| `sin_conexion_gb` | Opcional. Cuánto espacio como máximo ocupan esos videos (por omisión 100 GB). Si se llena, o si el disco queda con menos de 2 GB libres, la cola de descargas se detiene y avisa. |
| `navegador` | Opcional. Ruta de otro navegador basado en Chrome para «En vivo», si no usas Chrome ni Brave. |

Tras editar el archivo, corre `./cine` para aplicarlo.
