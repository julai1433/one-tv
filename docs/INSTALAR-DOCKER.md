# Instalar One TV en un NAS

Para un **NAS** (Synology, QNAP, Unraid, TrueNAS SCALE, OpenMediaVault…) o cualquier equipo con Linux que quieras
dejar siempre encendido. One TV corre dentro de **Docker**, arranca solo con el NAS y lee tus carpetas **sin poder
cambiar ni borrar nada**. Las carpetas de videos y de música se eligen después, en el navegador.

**En prueba**: todavía no se probó en un NAS de verdad. Si algo no funciona, el registro (abajo, «Si algo falla») dice
qué pasó.

## 1. Docker es requisito

| Tu NAS | Cómo tener Docker |
| --- | --- |
| **Synology** | **Centro de paquetes** → busca **Container Manager** → **Instalar**. |
| **QNAP** | **App Center** → busca **Container Station** → **Instalar**. Ábrela una vez para que termine de prepararse. |
| **Unraid** | Ya viene. Revisa que esté prendido: **Settings** → **Docker** → «Enable Docker»: **Yes**. |
| **TrueNAS SCALE** (24.10 o más nuevo) | Ya viene. **Apps** → **Configuration** → **Choose Pool** (dónde guardar las apps). |
| **OpenMediaVault u otro Linux** | El comando del paso 2 lo instala solo. |

## 2. Instalar

Hay dos caminos. Elige uno.

### Con un comando (lo más fácil, si tu NAS deja usar la terminal)

Entra a la terminal del NAS (en Unraid, el botón **>_** de arriba a la derecha; en los demás, por SSH: en Synology se
activa en Panel de control → Terminal y SNMP). Pega esto y pulsa Enter:

```
wget -qO- https://raw.githubusercontent.com/julai1433/one-tv/main/instalar.sh | bash
```

Reconoce el NAS, revisa Docker, baja One TV y lo deja corriendo. Si te pide tu contraseña, es la de tu usuario del NAS
(dice para qué). Al final te da la dirección para abrirlo desde la computadora o el teléfono. Para ponerlo al día,
vuelve a correr el mismo comando.

### Sin terminal: un «proyecto» en la app de Docker del NAS

Copia el bloque de tu NAS tal cual y pégalo donde se indica. Monta **todas tus carpetas compartidas de solo lectura**
(`:ro`), así después eliges en el navegador cuáles son las de videos y música, sin volver a hacer nada aquí.

**Synology** (Container Manager)

1. En **File Station**, dentro de la carpeta **docker**, crea una carpeta llamada **one-tv**.
2. En **Container Manager** → **Proyecto** → **Crear**. Nombre: `one-tv`. Ruta: la carpeta `docker/one-tv`.
   Origen: **Crear docker-compose.yml**, y pega:

   ```yaml
   services:
     one-tv:
       image: ghcr.io/julai1433/one-tv:latest
       container_name: one-tv
       network_mode: host
       restart: unless-stopped
       environment:
         PUID: "0"
         PGID: "0"
         ONE_TV_COMPARTIDAS: /volume1
       volumes:
         - /volume1/docker/one-tv:/datos
         - /volume1:/volume1:ro
   ```

3. **Siguiente** → **Siguiente** → **Listo**. La primera vez tarda unos minutos en bajar One TV.

Si tienes un segundo volumen, agrega la línea `- /volume2:/volume2:ro` y pon `ONE_TV_COMPARTIDAS: /volume1:/volume2`.

**QNAP** (Container Station): **Aplicaciones** → **Crear**. Nombre: `one-tv`. Pega y pulsa **Crear**:

```yaml
services:
  one-tv:
    image: ghcr.io/julai1433/one-tv:latest
    container_name: one-tv
    network_mode: host
    restart: unless-stopped
    environment:
      PUID: "0"
      PGID: "0"
      ONE_TV_COMPARTIDAS: /share
    volumes:
      - /share/Container/one-tv:/datos
      - /share:/share:ro
```

**Unraid**: instala **Docker Compose Manager** (pestaña **Apps**). Luego, en la pestaña **Docker** → **Add New Stack**
→ nombre `one-tv` → el engrane del stack → **Edit Stack** → **Compose File**, pega y guarda; después **Compose Up**:

```yaml
services:
  one-tv:
    image: ghcr.io/julai1433/one-tv:latest
    container_name: one-tv
    network_mode: host
    restart: unless-stopped
    environment:
      PUID: "0"
      PGID: "0"
      ONE_TV_COMPARTIDAS: /mnt/user
    volumes:
      - /mnt/user/appdata/one-tv:/datos
      - /mnt/user:/mnt/user:ro
```

**TrueNAS SCALE**: **Apps** → **Discover Apps** → los tres puntos (⋮) → **Install via YAML**. Nombre: `one-tv`. Pega
esto, cambiando `tanque` por el nombre de tu pool (lo ves en **Storage**), y pulsa **Save**:

```yaml
services:
  one-tv:
    image: ghcr.io/julai1433/one-tv:latest
    container_name: one-tv
    network_mode: host
    restart: unless-stopped
    environment:
      PUID: "0"
      PGID: "0"
      ONE_TV_COMPARTIDAS: /mnt/tanque
    volumes:
      - /mnt/tanque/docker/one-tv:/datos
      - /mnt/tanque:/mnt/tanque:ro
```

**Portainer** (en cualquier NAS): **Stacks** → **Add stack** → nombre `one-tv` → **Web editor**, pega el bloque de tu
NAS de arriba y pulsa **Deploy the stack**.

Opcional, si tu NAS tiene procesador Intel o AMD: agrega estas dos líneas al final del bloque (a la altura de
`volumes:`) para que el chip de video convierta los videos sin cansar el procesador. Si tu NAS no tiene la carpeta
`/dev/dri`, no las pongas: Docker no arrancaría el contenedor.

```yaml
    devices:
      - /dev/dri:/dev/dri
```

## 3. Abrir el asistente

Desde la computadora o el teléfono, en la misma red de la casa, abre:

**`http://IP-DEL-NAS:8765/bienvenida`**

(La IP del NAS la ves en su panel; es algo como `192.168.1.20`.) Ahí eliges tus carpetas de videos y de música, y la
TV. Después, la página de todos los días es `http://IP-DEL-NAS:8765`: ponla en la pantalla de inicio del teléfono.

## Poner al día

- **Con el comando**: vuelve a correrlo. Tus datos se quedan.
- **Synology**: Container Manager → **Proyecto** → `one-tv` → **Acción** → **Detener**, luego **Limpiar** y
  **Compilar** (baja la versión nueva).
- **Unraid**: en el stack `one-tv`, **Update Stack**.
- **Portainer**: el stack `one-tv` → **Editor** → **Update the stack** con «Re-pull image» encendido.
- **QNAP y TrueNAS**: borra la aplicación `one-tv` y vuelve a crearla con el mismo bloque: tus datos se quedan en su
  carpeta (`/share/Container/one-tv` o `/mnt/tanque/docker/one-tv`).

## Si algo falla

- **El registro** dice qué pasó: en Synology, Container Manager → **Contenedor** → `one-tv` → **Registro**; en QNAP,
  Container Station → `one-tv` → **Registros**; en Unraid, el ícono del contenedor → **Logs**; por terminal,
  `docker logs one-tv`.
- **La página abre pero la TV no encuentra One TV**: el NAS y la TV tienen que estar en la misma red de la casa, y el
  bloque debe tener `network_mode: host`.
- **No veo una carpeta en el navegador**: tiene que estar dentro de lo montado (por ejemplo, en Synology, en el
  `/volume1`). Si está en otro volumen o en un disco USB, agrégalo como en el paso 2.
- **«Bind mount failed» en Synology**: falta la carpeta `docker/one-tv` (paso 2, punto 1).

## Qué cambia respecto a la Mac, Windows y Ubuntu

- Sin ícono en la barra de menú: el arranque lo hace Docker.
- **«En vivo»** (canales de páginas web) necesita Chrome, que esta versión no trae: esa sección no funciona. Lo demás
  sí: películas, series, YouTube, música y la página web.
- **Tailscale** (ver YouTube fuera de casa en el iPhone) no viene dentro: instálalo en el NAS directamente.
- Ajustes avanzados con variables (`ROKU_IP`, `ROKU_PASSWORD`, `NOMBRE`, `PUERTO`, `CODIFICADOR`, `TZ`) o en el
  `config.json` de la carpeta de datos (con las claves de [config.example.json](../config.example.json)); las variables
  ganan. El ejemplo comentado completo está en [`docker-compose.yml`](../docker-compose.yml).
