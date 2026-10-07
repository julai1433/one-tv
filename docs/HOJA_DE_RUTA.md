# Hoja de ruta

Lo que ya funciona hoy y lo que viene, en orden. Para ayudar con alguna de estas piezas, ver
[CONTRIBUTING.md](../CONTRIBUTING.md); para el estado de hoy, el [README](../README.md).

## El principio

**Hacerlo lo más sencillo posible.** One TV es para cualquier persona, no solo para quien sabe de terminales o trabaja
con agentes de IA. Cada pieza nueva se mide con la misma pregunta: ¿alguien que no sabe qué es un servidor puede
instalarla y usarla? Por eso, siempre que se pueda:

- Se instala y se usa **sin abrir la terminal**, y en **un solo paso** (un instalador que se abre con doble clic, no
  una lista de comandos).
- Lo que el programa puede averiguar solo (la dirección de la TV, el idioma, las carpetas), lo averigua solo.
- Los mensajes dicen qué pasó y qué hacer, sin jerga.

## Hoy

| Pieza | Estado |
|---|---|
| Servidor (la computadora que guarda y prepara tus videos) | **macOS** y **Ubuntu 24.04**; **Windows 10 y 11**, en prueba |
| App de TV | **Roku** (instalada desde la propia computadora, en modo desarrollador) |
| Web (en la computadora y el teléfono) | **Cualquier navegador moderno**: ya funciona en cualquier sistema |

## Lo que sigue, en este orden

### 1. El servidor en Ubuntu: hecho

Una computadora con Ubuntu 24.04 (o una mini PC vieja que se queda siempre encendida) ya puede ser el servidor: arranca
sola al encender, usa el chip de video cuando lo hay y el procesador cuando no. Guía:
[INSTALAR-UBUNTU.md](INSTALAR-UBUNTU.md). Falta probarlo con chips de video reales (NVIDIA, Intel, AMD); después, otras
versiones de Linux. Para quien tiene un NAS o ya usa Docker, hay una imagen **en prueba**:
[INSTALAR-DOCKER.md](INSTALAR-DOCKER.md) (falta probarla en un NAS de verdad).

### 2. La app para Google TV y Android TV

Cubre Chromecast con Google TV, Nvidia Shield, y las TV con Android TV o Google TV integrado. Se instalará con un
archivo (APK), sin pasar por la tienda; la meta es que sea un solo paso, sin comandos. **La misma app servirá para Fire TV** (Amazon). Seguirá el mismo diseño de la TV de hoy ([DESIGN.md](../DESIGN.md)),
con el control remoto como única forma de manejarla. Mientras tanto, cualquier TV o aparato con navegador puede abrir
la página web de One TV.

### 3. El servidor en Windows: en prueba

Está hecho para que una PC con Windows 10 u 11 sea el servidor, pero **todavía no se ha probado en un Windows real**: se instala con un solo comando (o doble clic en `cine.cmd`), que
ofrece instalar lo que falte; arranca solo al iniciar sesión, sin ventanas ni permisos de administrador, y usa el chip
de video (NVIDIA, Intel o AMD) cuando lo hay. Guía: [INSTALAR-WINDOWS.md](INSTALAR-WINDOWS.md). Falta probarlo en una
PC de verdad, con un Roku y chips de video reales.

### 4. Compartir tu biblioteca con aparatos fuera de tu red

Hoy One TV vive en la red de tu casa; fuera de ella, el camino es Tailscale (ver [INSTALAR.md](INSTALAR.md#opcional-fuera-de-casa-con-tailscale)),
que sirve para ti pero pide instalar y configurar algo en cada aparato. El objetivo: poder invitar a **familia y
amigos**, también fuera de casa, a ver lo que tú decidas compartir, con un enlace o un código, sin que tengan que
instalar nada raro y sin abrir tu red a internet. Hay decisiones de seguridad importantes (quién puede entrar, a qué
carpetas, cómo se revoca una invitación) que se discuten antes de escribir código: se agradecen ideas en un *issue*.

## Además

- **Varios videos a la vez** en la misma pantalla de la TV (hasta cuatro). Está hecho, pero archivado hasta pulirlo:
  falta medir cuánta carga aguanta cada tipo de computadora y cómo se maneja con el control remoto.
- **Apple TV**, con el mismo diseño.
- **Que la app de la TV diga qué reproduce sin convertir.** Hoy el servidor supone que cualquier TV es de las más
  sencillas y convierte de más cuando la TV podría ver el archivo tal cual (por ejemplo, en un Roku 4K).
- **Varias TV** a la vez (hoy el servidor usa una).
- **Letras de otros alfabetos** (cirílico, chino, japonés…) en la app de la TV.
- **Un instalador de un solo paso** para cada sistema: parte del principio de arriba y se hace pieza por pieza al
  terminar cada sistema nuevo.
