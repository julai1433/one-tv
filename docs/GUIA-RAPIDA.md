# Guía rápida: tu caso en pocos pasos

Cada caso, en llano y en pocos pasos. La instalación completa, paso a paso, está en [INSTALAR.md](INSTALAR.md) (Mac),
[INSTALAR-UBUNTU.md](INSTALAR-UBUNTU.md), [INSTALAR-WINDOWS.md](INSTALAR-WINDOWS.md) (en prueba) e
[INSTALAR-DOCKER.md](INSTALAR-DOCKER.md) (un NAS, en prueba).

- [Ya tengo mi biblioteca en un NAS y uso Plex](#ya-tengo-mi-biblioteca-en-un-nas-y-uso-plex)
- [Quiero que el servidor sea el NAS mismo](#quiero-que-el-servidor-sea-el-nas-mismo)
- [Tengo todo en un disco externo](#tengo-todo-en-un-disco-externo)
- [Empiezo de cero](#empiezo-de-cero)
- [Mis descargas llegan a otra carpeta](#mis-descargas-llegan-a-otra-carpeta)
- [Mi música está en el NAS](#mi-música-está-en-el-nas)
- [Verlo fuera de casa](#verlo-fuera-de-casa)

**Una regla para todos los casos.** One TV solo mueve, renombra o escribe en una carpeta **suya**: una nueva o vacía,
o una que ya ordenó One TV (con `Películas/` y `Series/` y sus códigos `{imdb-…}`, `{tvdb-…}`). Una carpeta que ya
trae videos acomodados de otra forma (por Plex, Jellyfin, Emby o a mano), o en la que One TV no puede escribir, la usa
**solo para leer**: no mueve, no renombra, no borra y no agrega nada ahí. Al arrancar, el registro dice qué carpeta
usa solo para leer.

---

## Ya tengo mi biblioteca en un NAS y uso Plex

Puedes probar One TV junto a Plex sin cambiar nada: One TV lee las mismas carpetas que Plex y no las toca.

**1. Que la computadora vea la carpeta del NAS** (la computadora que hará de servidor de One TV):

- **Mac**: en el Finder, menú **Ir → Conectarse al servidor** (⌘K), escribe `smb://nombre-del-nas` (o su IP, por
  ejemplo `smb://192.0.2.20`), entra con tu usuario del NAS y elige la carpeta compartida (por ejemplo `video`).
  Queda en `/Volumes/video`. Para que se conecte sola: **Configuración del Sistema → General → Ítems de inicio** y, en
  «Abrir al iniciar sesión», agrega la carpeta del NAS con **+**. Si macOS pregunta si `python3` puede leer un volumen
  de red, di **Permitir**.
- **Ubuntu**: lo más firme es una línea en `/etc/fstab`, así se conecta al encender, aunque nadie inicie sesión.
  Instala el programa para carpetas de Windows y NAS (`sudo apt install cifs-utils`), crea la carpeta donde va a
  aparecer (`sudo mkdir -p /mnt/nas-video`) y agrega esta línea a `/etc/fstab` (con `sudo nano /etc/fstab`), con tu
  NAS, tu carpeta y tu usuario:

  ```
  //nombre-del-nas/video  /mnt/nas-video  cifs  username=TU_USUARIO,password=TU_CLAVE,uid=1000,ro,nofail,_netdev  0  0
  ```

  `ro` la conecta **solo para leer**: así ni One TV ni nada de esta computadora puede cambiarla. `uid=1000` es tu
  usuario (el número lo dice el comando `id`). Luego `sudo mount -a`. Ojo: cualquiera con cuenta en esta computadora
  puede leer esa línea con la clave. (Otra forma, solo mientras tienes la sesión abierta: en **Archivos → Otras ubicaciones →
  Conectar al servidor**, `smb://nombre-del-nas/video`; queda en una ruta larga dentro de `/run/user/1000/gvfs/`.)
- **Windows** (en prueba): en el Explorador de archivos, **Este equipo → Conectar unidad de red**, elige una letra
  (por ejemplo `Z:`), escribe `\\nombre-del-nas\video`, marca **Conectar de nuevo al iniciar sesión** y entra con tu
  usuario del NAS.

**2. Decirle a One TV qué carpetas leer.** Las mismas que tiene Plex (en Plex: Ajustes → Administrar → Bibliotecas →
editar → Agregar carpetas). Si Plex usa dos carpetas, como `Movies` y `TV Shows` dentro de `video`, basta con la que
las contiene a las dos.

- La forma fácil: corre `./cine configurar` (en Windows, `cine configurar`) y, en la pregunta 1, escribe la carpeta
  (`/Volumes/video`, `/mnt/nas-video` o `Z:/`). Como ya tiene videos, pregunta **«¿Otro programa, como Plex, usa esta
  carpeta?»**: di que sí (`s`). One TV no moverá ni cambiará nada ahí.
- O a mano, en `config.json` (en Windows puedes escribir las rutas con `/`: `"Z:/"`):

  ```
  "carpetas": ["/Volumes/video"],
  "solo_leer": {"/Volumes/video": true},
  "descargas": []
  ```

  `"solo_leer"` deja la carpeta solo para leer aunque One TV crea que es suya; `false` hace lo contrario (One TV la
  ordena). `"descargas": []` es para que One TV no tome lo que baja tu programa de torrents (ver
  [Mis descargas](#mis-descargas-llegan-a-otra-carpeta)).

**3. Corre `./cine`** (o `./cine autoarranque`). En unos minutos ves tus películas y series en la TV y en la web.

**Qué hace One TV con esa carpeta:**

- La **lee**: películas en su carpeta (`Movies/Avatar (2009)/Avatar (2009).mkv`) o sueltas (`Movies/Avatar (2009).mkv`),
  dos ediciones de la misma película (`{edition-Director's Cut}`: «Blade Runner (1982) · Director's Cut»), películas en varias
  partes (`- pt1`, `- cd2`: «Parte 1», «Parte 2»), series con `Season 01` y `Specials` (los especiales van al final, en
  «Especiales»), y los códigos de Plex o Jellyfin si los trae (`{imdb-tt…}`, `{tmdb-…}`, `{tvdb-…}`, `[imdbid-…]`).
  Los extras (`-trailer`, `Featurettes/`…) no salen.
- **Pósters**: usa los que estén junto a la película o la serie (`poster.jpg`, `folder.jpg`, `show.jpg`,
  `Avatar (2009).jpg`); si no hay, los baja de internet. Lo que no trae código lo identifica por su nombre y año
  (IMDb y TVmaze, sin cuenta). Si internet no tiene póster, usa el fondo (`fanart.jpg`). Todo se guarda en la caché de
  One TV, no en tu carpeta.
- **Sinopsis**: de Wikipedia, con el mismo código.
- **Subtítulos que bajes** (a mano o solos, con [OpenSubtitles](INSTALAR.md#opcional-subtítulos-de-opensubtitles)):
  se guardan en la carpeta de datos de One TV, no junto al video. One TV los muestra igual; Plex no los ve.
- Lo que ya viste, tus listas y en qué minuto vas: se guarda en One TV.

**Qué no hace (todavía):**

- **No importa lo visto en Plex**, ni en qué minuto ibas, ni tus colecciones, ni los pósters que elegiste dentro de
  Plex (Plex los guarda en su propia base de datos, no en la carpeta).
- No agrega el doblaje latino automático a esos videos (la pista iría junto al video, y ahí no escribe).
- Las series por fecha (`Programa - 2020-03-15.mkv`) o con `1x01` no se reconocen como episodios; dos series con el
  mismo nombre y distinto año se juntan en una; las partes de una película se ven como dos entradas.
- Si la carpeta del NAS cambia de ruta (otra letra en Windows, o `/Volumes/video-1` en la Mac si se conectó dos
  veces), One TV ve videos «nuevos» y lo visto empieza de cero. Desconecta la de más y deja una sola.
- Si el NAS no está conectado, sus videos no salen; cuando se conecta, aparecen solos en un minuto.

---

## Quiero que el servidor sea el NAS mismo

Con **Docker**, One TV corre dentro del NAS (Synology, Unraid, TrueNAS, QNAP…) y arranca con él: **en prueba**, guía
en [INSTALAR-DOCKER.md](INSTALAR-DOCKER.md). Ahí tu carpeta de películas se monta de **solo lectura** (el `:ro` del
archivo `docker-compose.yml`): One TV la lee y no puede cambiar nada, aunque Plex la use al mismo tiempo. Los
subtítulos que se bajen quedan en la carpeta de datos de One TV.

---

## Tengo todo en un disco externo

1. Conecta el disco. Su carpeta es algo como `/Volumes/MiDisco/Películas` en la Mac, `/media/TU_USUARIO/MiDisco/Películas`
   en Ubuntu o `E:/Películas` en Windows.
2. Corre `./cine configurar` y pon esa carpeta en la pregunta 1.
   - Si está **vacía o es nueva**: es de One TV y ordena lo que pongas ahí.
   - Si ya tiene videos, pregunta si otro programa la usa. Di que **sí** si la ordenó Plex u otro programa, o si la
     quieres tal como está (solo se lee); di que **no** si quieres que One TV la ordene a su manera (mueve y renombra
     lo que encuentre suelto).
3. Si el disco no está conectado, sus videos no salen (y One TV no escribe nada en su lugar); al conectarlo, aparecen
   solos en un minuto, con lo que ya habías visto.

En la Mac, la primera vez macOS puede preguntar si `python3` puede leer un volumen extraíble: **Permitir**.

---

## Empiezo de cero

Lo de [INSTALAR.md](INSTALAR.md), resumido:

1. Instala lo necesario y descarga One TV ([paso 1 y 2](INSTALAR.md#paso-1-instalar-los-programas-de-apoyo)).
2. Corre `./cine`. La primera vez pregunta lo mínimo: deja la carpeta que sugiere (`~/Movies/Biblioteca` en la Mac) o
   escribe otra nueva; se crea sola.
3. Suelta ahí tus videos como vengan («Mi.Pelicula.2019.1080p.mkv», «serie s01e03.mkv»): cada minuto One TV los
   identifica y los acomoda en `Películas/` y `Series/`, con póster y sinopsis.
4. Lo que bajes con Transmission a `~/Downloads/Torrents` entra solo a la biblioteca, sin ocupar espacio de más.
5. Instala la app en la TV ([Roku, paso 6 y 7](INSTALAR.md#paso-6-activar-el-modo-desarrollador-del-roku); Google TV,
   Android TV o Fire TV, en prueba: [INSTALAR-GOOGLE-TV.md](INSTALAR-GOOGLE-TV.md)) y, si quieres, que arranque sola:
   `./cine autoarranque`.

---

## Mis descargas llegan a otra carpeta

Para Transmission, qBittorrent o cualquier otro, en tu computadora o en el NAS:

1. En el programa de torrents, que lo **incompleto vaya a otra carpeta** (Transmission: «Usar carpeta para
   incompletos»; qBittorrent: «Mantener los torrents incompletos en»). Así One TV solo ve lo terminado.
2. En `config.json`, la carpeta de lo terminado:

   ```
   "descargas": ["/Volumes/descargas/terminadas"]
   ```

3. Corre `./cine`. Cada 10 segundos One TV mira esa carpeta, identifica lo nuevo y lo pone en **tu primera carpeta de
   One TV** (la de `"carpetas"` que es suya), no en las de Plex.

- Si todas tus carpetas son de otro programa, lo que se baja **no se agrega** y el registro avisa una vez. Para que se
  agregue, suma a `"carpetas"` una carpeta nueva para One TV, por ejemplo `"carpetas": ["/Volumes/video",
  "~/Movies/One TV"]`.
- Si las descargas y la carpeta de One TV están en el mismo disco, el video queda en los dos lugares sin ocupar espacio
  de más (el programa de torrents lo sigue compartiendo). Si están en discos distintos (por ejemplo, descargas en el NAS
  y One TV en la computadora), One TV **mueve** el video a su carpeta y deja un acceso en su lugar.
- Si Plex, Sonarr o Radarr ya acomodan tus descargas, no le des esa carpeta a One TV (`"descargas": []`): One TV verá
  cada video cuando llegue a la biblioteca de Plex.

---

## Mi música está en el NAS

1. Conecta la carpeta de música del NAS igual que la de películas ([paso 1 de Plex](#ya-tengo-mi-biblioteca-en-un-nas-y-uso-plex)).
2. Corre `./cine configurar` y ponla en la pregunta 4, o en `config.json`: `"musica": ["/Volumes/musica"]`.

One TV solo la lee: las etiquetas de cada canción, la portada que traen adentro o un `cover.jpg`/`folder.jpg`, y las
listas `.m3u`. Lo que convierte (FLAC, ALAC…) lo guarda en su caché, no en el NAS.

---

## Verlo fuera de casa

Con **Tailscale** (gratis para uso personal), tu teléfono entra a One TV desde cualquier lugar, como si estuviera en
casa, sin publicar nada en internet:

1. Instala Tailscale en la computadora que hace de servidor y en el teléfono, con la misma cuenta.
2. Corre `./cine tailscale`: te da una dirección `https://…ts.net:8766`. Ábrela en el teléfono y agrégala a la
   pantalla de inicio.

Pasos con detalle: [INSTALAR.md → Tailscale](INSTALAR.md#opcional-fuera-de-casa-con-tailscale). Si el servidor es
el NAS con Docker, instala Tailscale en el NAS. **Compartir con familia y amigos** está en la
[hoja de ruta](HOJA_DE_RUTA.md).
