#!/bin/bash
# Doble clic en Finder para instalar (o poner al día) One TV en esta Mac. Hace lo mismo que pegar esto en la Terminal:
#   curl -fsSL https://raw.githubusercontent.com/julai1433/one-tv/main/instalar.sh | bash
# Si macOS dice que no puede comprobar quién lo hizo: Configuración del Sistema → Privacidad y seguridad → «Abrir de
# todos modos» (solo la primera vez).
cd "$HOME" || exit 1
instalador="$(mktemp "${TMPDIR:-/tmp}/one-tv-instalar.XXXXXX")" || exit 1
if curl -fsSL https://raw.githubusercontent.com/julai1433/one-tv/main/instalar.sh -o "$instalador"; then
  bash "$instalador"
  codigo=$?
else
  echo "✗ No pude bajar el instalador de One TV. ¿Hay internet? Vuelve a intentarlo."
  codigo=1
fi
rm -f "$instalador"
echo
read -r -n 1 -s -p "Pulsa cualquier tecla para cerrar esta ventana." </dev/tty
echo
exit $codigo
