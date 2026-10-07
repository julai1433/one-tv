# Cómo contribuir

¡Gracias! Se reciben arreglos, mejoras y funciones nuevas, hechos por personas o por agentes de IA. Para que un cambio
entre rápido:

- **Si trabajas con un agente de IA** (o eres uno), [AGENTS.md](AGENTS.md) tiene lo mismo en versión corta y práctica:
  cómo está organizado el proyecto, cómo probarlo y las reglas.
- **La meta**: que One TV se instale y se use sin ser una persona técnica. Si algo que cambias lo hace más difícil de
  usar, mejor rediséñalo. Lo que viene está en la [hoja de ruta](docs/HOJA_DE_RUTA.md); ahí también se agradece ayuda
  (por ejemplo, el servidor en Ubuntu o la app para Google TV).

## Antes de empezar

- Para algo grande (una pantalla nueva, otro sistema para el servidor, otra plataforma de TV, cambiar cómo se guarda algo), abre primero un *issue*
  y cuéntalo: así no se duplica trabajo.
- Lee [`docs/DETALLES.md`](docs/DETALLES.md) (cómo funciona por dentro) y [`DESIGN.md`](DESIGN.md) (colores, letras y
  piezas de la interfaz: todo color sale del bloque `:root` de la web y de `roku/components/Theme.brs`).

## Reglas de la casa

- **Todo en español**: lo que ve la persona (textos de la TV y la web, mensajes del servidor) y también los
  comentarios y los nombres de las pruebas. Español neutro, sin jerga: «la computadora», «la TV», «la fila».
- **Sin dependencias nuevas** en el servidor: Python de la biblioteca estándar, más `ffmpeg`. Si algo necesita otra
  cosa, que se instale sola en un entorno aparte (como `yt-dlp`) y que no sea obligatoria.
- **Nada de esta casa en el código**: rutas, IPs, nombres o cuentas van en `config.json` (que nunca se sube); los
  ejemplos de las pruebas, inventados.
- **Seguridad**: el servidor no tiene contraseña y escucha en la red de la casa. Nunca abras archivos ni direcciones
  que mande el cliente sin validarlas (ver «Seguridad» en `docs/DETALLES.md`).

## Probar

```
python3 -m unittest discover -s pruebas -p 'test_*.py'   # la computadora: sin red ni TV, unos 20 s (necesita ffmpeg)
npx -y brighterscript@0                                  # el código de la app del Roku, sin TV (necesita Node)
python3 pruebas/datos_demo.py                            # una biblioteca de ejemplo para ver la web, sin datos de nadie
```

Si cambias la web o la app de la TV, revisa también lo que se ve: los `pruebas/web_*.py` la abren en Chrome sin
ventana y dejan capturas; para la app del Roku hace falta un Roku en modo desarrollador (`./cine instalar` y
`pruebas/captura_tele.sh`). Si no tienes la TV, dilo en el pull request. Más en [`pruebas/LEEME.md`](pruebas/LEEME.md).

## El pull request

- Uno por tema, con la descripción en español: qué cambia para quien lo usa, cómo lo probaste y qué no pudiste
  probar (por ejemplo, «no tengo un Roku 4K»).
- Agrega o ajusta las pruebas de lo que cambias.
- Al abrirlo corren solas las pruebas y la revisión del código del Roku; tienen que pasar.
