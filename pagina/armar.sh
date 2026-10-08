#!/bin/bash
# Arma la página del botón «Descargar One TV» en una carpeta, lista para GitHub Pages: pagina/index.html más las letras
# de One TV (las mismas de la web: mac/web/fonts, con su licencia) y el ícono. Lo usa .github/workflows/pagina.yml.
# Uso: pagina/armar.sh CARPETA     (para verla en la computadora: python3 -m http.server -d CARPETA 8808)
set -euo pipefail
DIR="$(cd "$(dirname "$0")/.." && pwd)"
SALIDA="${1:?Uso: pagina/armar.sh CARPETA}"
mkdir -p "$SALIDA/fonts"
cp "$DIR/pagina/index.html" "$SALIDA/index.html"
for f in Archivo-Regular Archivo-Medium Archivo-Bold BigShouldersDisplay-Black; do
  cp "$DIR/mac/web/fonts/$f.woff2" "$SALIDA/fonts/"
done
cp "$DIR/mac/web/fonts/"OFL-*.txt "$SALIDA/fonts/"
cp "$DIR/mac/web/icon-180.png" "$SALIDA/icon-180.png"
touch "$SALIDA/.nojekyll"   # tal cual, sin el procesador de páginas de GitHub
echo "✓ Página lista en $SALIDA"
