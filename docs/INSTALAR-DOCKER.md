# Instalar One TV en un NAS (Docker)

**En prueba.** La imagen se construyó y se probó con una biblioteca de ejemplo, pero todavía no en un NAS de verdad
(ni con el chip de video de Intel, ni buscando el Roku desde un NAS). Si algo no funciona, el registro del contenedor
(paso 6) dice qué pasó.

Para quien tiene un **NAS** (Synology, Unraid, TrueNAS, QNAP…) o cualquier computadora con Linux y **Docker**. El
servidor de One TV corre dentro de un contenedor: no instalas Python ni ffmpeg, y arranca solo con el NAS. La guía de
la Mac, con más detalle sobre la TV, es [INSTALAR.md](INSTALAR.md).

Tiempo aproximado: 15 minutos.

## 1. Qué necesitas

- Un NAS (o servidor) con **Docker** o, en Synology, **Container Manager**; encendido cuando quieras ver algo y en la
  **misma red** que el Roku.
- Un **Roku** con el modo desarrollador activado (casi todos). Anota la **contraseña** que inventes al activarlo:
  [INSTALAR.md, paso 6](INSTALAR.md#paso-6-activar-el-modo-desarrollador-del-roku).
- Tus películas y series en una carpeta del NAS (`.mkv`, `.mp4`…). One TV solo las **lee**: nunca escribe ni borra nada
  en ella.
- Una carpeta **nueva y vacía** para los datos de One TV (por ejemplo `docker/one-tv`): ahí guarda lo que ya viste,
  tus favoritos y los pósters. No la mezcles con tus películas.

## 2. El archivo de configuración

Todo se resume en un archivo, [`docker-compose.yml`](../docker-compose.yml), que viene comentado. Ábrelo y cambia
solo esto:

| Qué | Dónde | Ejemplo |
| --- | --- | --- |
| La carpeta de datos | `volumes`, primera línea | `/volume1/docker/one-tv:/datos` |
| La carpeta de tus películas | `volumes`, segunda línea (déjale el `:ro`) | `/volume1/video/peliculas:/biblioteca:ro` |
| La carpeta de música (opcional) | `volumes`, tercera línea; si no tienes, bórrala | `/volume1/music:/musica:ro` |
| La contraseña del Roku | `ROKU_PASSWORD` | la del modo desarrollador |
| Tu usuario del NAS | `PUID` y `PGID` | ver abajo |
| Tu zona horaria | `TZ` | `America/Mexico_City` |

**PUID y PGID** son los números de tu usuario del NAS, para que One TV pueda escribir en la carpeta de datos. Se ven
entrando por SSH y escribiendo `id tu_usuario`. Si no los sabes, deja `1000` y `1000`; en Unraid suelen ser `99` y `100`.
Si One TV dice que no puede escribir en `/datos`, es esto.

**La red `host` es importante, no la quites.** El Roku se encuentra con un aviso a toda la red de la casa, y la TV
necesita llegar al servidor por la dirección del NAS; con la red aparte que Docker crea normalmente ninguna de las dos
cosas funciona.

Si tu NAS **no tiene chip de video Intel** (o no sabes), no pasa nada: One TV usa el procesador. Si `/dev/dri` no
existe en tu NAS, borra las dos líneas de `devices` o Docker no arrancará el contenedor.

## 3. Arrancar, según tu NAS

### Synology (DSM 7.2 o más nuevo, Container Manager)

1. En **Container Manager** → **Proyecto** → **Crear**.
2. Nombre: `one-tv`. Ruta: una carpeta nueva, por ejemplo `docker/one-tv`.
3. En «Origen», elige **Crear docker-compose.yml** y pega el contenido de `docker-compose.yml` ya con tus cambios.
4. Siguiente → Siguiente → **Listo**. La primera vez descarga la imagen (unos minutos).
5. El chip de video: algunos modelos con Intel piden dar permiso a `/dev/dri` (por SSH:
   `sudo chmod 666 /dev/dri/*`, y se repite al reiniciar el NAS). Es opcional; sin él funciona con el procesador.

### Unraid

Con el complemento **Docker Compose Manager** (de la tienda «Aplicaciones»): **Add New Stack**, pega el
`docker-compose.yml` y **Compose Up**. Usa rutas como `/mnt/user/appdata/one-tv:/datos` y
`/mnt/user/Peliculas:/biblioteca:ro`.

Sin el complemento, desde la pestaña **Docker** → **Add Container**:

- Repository: `ghcr.io/julai1433/one-tv:latest`; Network Type: **Host**.
- Agrega las rutas (Add another Path): `/datos` (lectura y escritura), `/biblioteca` y `/musica` (solo lectura).
- Agrega las variables (Add another Variable): `PUID` = `99`, `PGID` = `100`, `TZ`, `ROKU_PASSWORD`.
- Para el chip de video, en «Extra Parameters»: `--device=/dev/dri`.

### TrueNAS SCALE y QNAP

- **TrueNAS SCALE** (24.10 o más nuevo): **Apps** → **Discover Apps** → **Install via YAML**; pega el
  `docker-compose.yml` con tus rutas (las de los conjuntos de datos, como `/mnt/tanque/peliculas`).
- **QNAP** (Container Station): **Aplicaciones** → **Crear** → pega el `docker-compose.yml`.

### Cualquier Linux con Docker

```
mkdir one-tv && cd one-tv
# Guarda ahí el docker-compose.yml, con tus cambios, y:
docker compose up -d
```

## 4. Abrir la página

Con el contenedor corriendo, abre desde cualquier aparato de la casa: **`http://IP-DEL-NAS:8765`** (la IP la ves en el
panel de tu NAS; es algo como `192.168.1.20`). Si es tu primera vez, tarda uno o dos minutos en revisar la
biblioteca y hacer los pósters. Pon esa página en la pantalla de inicio de tu teléfono y listo.

## 5. La app del Roku

No hay nada que instalar a mano: con `ROKU_PASSWORD` puesta y el Roku encendido, el servidor **instala solo la app
«One TV»** en la TV (si no la ves, mira el registro: ahí dice qué falló). Ábrela y verás tu biblioteca. Si el Roku no
aparece, pon su IP en `ROKU_IP` (la ves en Ajustes del Roku → Red).

## 6. Si algo falla

- **El registro**: en Synology, Container Manager → Contenedor → `one-tv` → Registro; en Unraid, el ícono del
  contenedor → Logs; en Linux, `docker logs one-tv`.
- **«No puedo escribir en /datos»**: revisa `PUID` y `PGID` (paso 2).
- **«/biblioteca está vacía»**: la ruta de la izquierda en `volumes` no es la de tus películas.
- **La página abre pero la TV no encuentra el servidor**: confirma que la red es `host` y que el NAS y el Roku están en
  la misma red; pon `ROKU_IP`.
- **Las películas se ven cortadas o lentas**: el NAS convierte el video con el procesador; un chip Intel ayuda mucho
  (`devices`, paso 2). En el registro, la línea que empieza con «Video:» dice qué usa.

## 7. Actualizar

La imagen se actualiza cada vez que cambia One TV. Tus datos (en `/datos`) se conservan.

- **Linux**: `docker compose pull && docker compose up -d`.
- **Synology**: Container Manager → Proyecto → `one-tv` → **Acción** → **Detener**, luego **Limpiar** (descarga la
  versión nueva) y **Compilar**/**Iniciar**.
- **Unraid**: pestaña Docker → «Check for Updates» → **apply update** en `one-tv`.

## Qué cambia respecto a la Mac y Ubuntu

- Sin ícono en la barra de menú ni arranque con systemd: lo hace Docker (`restart: unless-stopped`).
- **«En vivo»** (canales de páginas web) necesita Chrome, que la imagen no trae: esa sección no funciona. Lo demás sí:
  películas, series, YouTube (yt-dlp se instala solo en `/datos` y se actualiza), música y la página web.
- **Tailscale** (ver YouTube fuera de casa en el iPhone) no viene dentro: instálalo en el NAS directamente.
- La configuración se puede dar con variables (`ROKU_IP`, `ROKU_PASSWORD`, `PUERTO`, `CODIFICADOR`) o con un
  `config.json` dentro de la carpeta de datos (con las mismas claves de [config.example.json](../config.example.json));
  las variables ganan. Dentro del contenedor las carpetas son siempre `/biblioteca` y `/musica`.
