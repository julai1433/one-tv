# Ayudar a probar One TV

Gracias por ayudar. One TV funciona todos los días en una Mac con un Roku; lo que falta es probarlo en otras
computadoras y otras TV. No necesitas saber programar: basta con instalarlo siguiendo la guía, usarlo un rato y
contarnos qué pasó, sobre todo si algo no salió como dice la guía.

## Qué falta probar

| Si tienes… | Guía para instalar | Qué tiene de nuevo |
|---|---|---|
| Una computadora con **Windows 10 u 11** | [INSTALAR-WINDOWS.md](INSTALAR-WINDOWS.md) | Nunca ha corrido en un Windows de verdad |
| Una computadora con **Ubuntu 24.04** (u otro Linux) | [INSTALAR-UBUNTU.md](INSTALAR-UBUNTU.md) | Solo se probó en un Ubuntu simulado, sin TV |
| Una TV con **Google TV**, **Android TV** o un **Fire TV** | [INSTALAR-GOOGLE-TV.md](INSTALAR-GOOGLE-TV.md) | Solo se probó en una TV simulada |

Para la app de Google TV, Android TV o Fire TV hace falta además una computadora de la casa con One TV (Mac, Ubuntu o
Windows).

## Qué probar

Con unos cuantos videos tuyos en la carpeta que elegiste al instalar:

1. **Instalar**: ¿la guía se entendió? ¿algún paso no salió como dice?
2. **Arrancar**: después de reiniciar la computadora, ¿la página de One TV abre sola desde el teléfono, sin hacer nada?
3. **Ver algo** en la TV o en la computadora: una película, un capítulo de una serie, un video de YouTube.
   - ¿Arranca en pocos segundos? ¿Se puede pausar, adelantar y cambiar el idioma o los subtítulos?
   - Si tienes videos en formatos raros (MKV, HEVC, 4K), pruébalos: ahí es donde la computadora tiene que convertir.
4. **Seguir viendo**: deja algo a la mitad, cierra y vuelve a abrir: ¿sigue donde lo dejaste?
5. **Controlar desde el teléfono** lo que se ve en la TV: pausa, avance, la fila.
6. **Música**, si tienes una carpeta de música.

No hace falta probar todo: lo que alcances sirve.

## Cómo avisar

Lo más útil es un *issue* en GitHub: [abrir uno](https://github.com/julai1433/one-tv/issues/new?template=reporte-de-prueba.md)
(pide una cuenta de GitHub, gratis). Si no tienes cuenta, manda lo mismo por mensaje a quien te compartió One TV.

Cuéntanos:

- **Qué tienes**: Windows 10 u 11, Ubuntu (versión), o el modelo de la TV o del aparato (por ejemplo «Chromecast con
  Google TV 4K», «Fire TV Stick 4K Max»). Si sabes la tarjeta de video de la computadora (NVIDIA, Intel, AMD), también.
- **Qué hiciste**, paso por paso, y **qué esperabas**.
- **Qué pasó**: el mensaje exacto si salió uno, o una foto de la pantalla.
- **El registro** de la computadora: corre `cine estado` (en Mac y Ubuntu, `./cine estado`); al final dice
  «Registro:» y la ruta de un archivo. Adjunta ese archivo. Lleva los nombres de tus videos; si prefieres no
  compartirlos, copia solo las últimas líneas.
