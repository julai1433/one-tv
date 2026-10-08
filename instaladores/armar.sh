#!/bin/bash
# Arma los instaladores de doble clic que se publican en la versión «instaladores» de GitHub, con nombres fijos para
# que el botón de la página de descarga (pagina/index.html) no cambie nunca:
#   Instalar-One-TV-Mac.pkg       el instalador de la Mac (solo se arma en una Mac: pkgbuild y productbuild). Sin firmar:
#                                 la firma va después, con herramientas/firmar_mac.sh
#   Instalar-One-TV-Windows.cmd   el mismo «Instalar One TV.cmd» de siempre
# Lo usa .github/workflows/instaladores.yml (al subir a main). Uso: instaladores/armar.sh [CARPETA] [mac|windows]
# (por omisión, en dist/ y los dos).
set -euo pipefail
export COPYFILE_DISABLE=1
DIR="$(cd "$(dirname "$0")/.." && pwd)"
SALIDA="${1:-$DIR/dist}"
CUALES="${2:-mac windows}"
mkdir -p "$SALIDA"
SALIDA="$(cd "$SALIDA" && pwd)"

for cual in $CUALES; do
  case "$cual" in
    windows)
      cp "$DIR/Instalar One TV.cmd" "$SALIDA/Instalar-One-TV-Windows.cmd"   # (con su fin de línea CRLF: .gitattributes)
      echo "✓ $SALIDA/Instalar-One-TV-Windows.cmd"
      ;;
    mac)
      if [ "$(uname -s)" != Darwin ]; then
        echo "✗ El instalador de la Mac (.pkg) solo se arma en una Mac." >&2
        exit 1
      fi
      tmp="$(mktemp -d)"
      trap 'rm -rf "$tmp"' EXIT
      mkdir -p "$tmp/scripts"
      cp "${ONE_TV_POSTINSTALL:-$DIR/instaladores/mac/postinstall}" "$tmp/scripts/postinstall"   # (otro: las pruebas)
      chmod 755 "$tmp/scripts/postinstall"
      xattr -c "$tmp/scripts/postinstall" 2>/dev/null || true   # sin atributos de la Mac (no viajan «._postinstall»)
      # Sin archivos que copiar (--nopayload): todo lo hace postinstall, que baja y corre instalar.sh.
      pkgbuild --quiet --nopayload --scripts "$tmp/scripts" --identifier io.github.julai1433.onetv.instalador \
        --version 1.0 "$tmp/one-tv.pkg"
      productbuild --quiet --distribution "$DIR/instaladores/mac/distribution.xml" \
        --resources "$DIR/instaladores/mac/recursos" --package-path "$tmp" "$SALIDA/Instalar-One-TV-Mac.pkg"
      echo "✓ $SALIDA/Instalar-One-TV-Mac.pkg"
      ;;
    *)
      echo "✗ No sé armar «${cual}» (mac o windows)." >&2
      exit 1
      ;;
  esac
done
