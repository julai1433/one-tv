# Los instaladores de doble clic y la página del botón «Descargar One TV»:
# - El de la Mac (Instalar-One-TV-Mac.pkg): su guion corre instalar.sh con tu usuario y deja lo que dijo en
#   ~/Library/Logs; si falla, dice por qué. En una Mac se arma de verdad y se instala «solo para ti» con un instalar.sh
#   falso (sin contraseña, sin tocar el One TV de la computadora).
# - Los nombres fijos: los mismos en la página, en el flujo de GitHub que los publica y en el guion que los arma.
# - La página reconoce Mac, Windows, Linux y teléfonos por el navegador (con Node, si está).
# - herramientas/firmar_mac.sh: sin el certificado o el perfil de Apple lo dice y no firma nada (con programas falsos).
# python3 -m unittest discover -s pruebas -p "test_instaladores.py"
import json, os, re, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POSTINSTALL = ROOT / "instaladores" / "mac" / "postinstall"
PAGINA = ROOT / "pagina" / "index.html"
BASH = shutil.which("bash") if sys.platform != "win32" else None
MAC = sys.platform == "darwin"
VERSION = "https://github.com/julai1433/one-tv/releases/download/instaladores/"
NOMBRES = ("Instalar-One-TV-Mac.pkg", "Instalar-One-TV-Windows.cmd")


def guion(path, texto):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/bash\n" + texto + "\n")
    path.chmod(0o755)
    return path


@unittest.skipUnless(BASH and MAC, "el instalador de la Mac se prueba en una Mac")
class InstaladorMac(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.dir = Path(self._t.name).resolve()
        self.casa = self.dir / "casa"
        self.casa.mkdir()
        self.registro = self.casa / "Library" / "Logs" / "One TV - instalador.log"

    def postinstall(self, falso, **env):
        entorno = {**os.environ, "ONE_TV_INSTALADOR": f"file://{falso}", "ONE_TV_CASA": str(self.casa),
                   "ONE_TV_SIN_VENTANAS": "1", **env}
        r = subprocess.run([str(POSTINSTALL), "/ruta/del.pkg", str(self.casa), "/", "/"], capture_output=True,
                           text=True, env=entorno, timeout=60)
        return r.returncode, r.stdout + r.stderr

    def test_corre_instalar_sh_como_tu_y_guarda_lo_que_dijo(self):
        marca = self.dir / "marca.txt"
        falso = guion(self.dir / "instalar.sh", f'echo "HOME=$HOME PWD=$PWD YO=$(id -u)" > "{marca}"; echo "✓ todo bien"')
        code, out = self.postinstall(falso)
        self.assertEqual(code, 0, out)
        self.assertEqual(marca.read_text().strip(), f"HOME={self.casa} PWD={self.casa} YO={os.getuid()}")
        self.assertIn("✓ todo bien", self.registro.read_text())

    def test_si_falla_dice_por_que(self):
        falso = guion(self.dir / "instalar.sh", 'echo "· bajando…"; echo "✗ No pude bajar Python. ¿Hay internet?" >&2; exit 1')
        code, out = self.postinstall(falso)
        self.assertEqual(code, 1)
        self.assertIn("One TV no se pudo instalar: No pude bajar Python. ¿Hay internet?", out)
        self.assertIn(str(self.registro), out)
        code, out = self.postinstall(self.dir / "no-existe.sh")
        self.assertEqual(code, 1)
        self.assertIn("No pude bajar el instalador de One TV", out)

    @unittest.skipUnless(shutil.which("pkgbuild") and shutil.which("installer"), "sin pkgbuild")
    def test_el_pkg_se_instala_solo_para_ti_sin_contrasena(self):
        """El .pkg de verdad (instaladores/armar.sh), con un instalar.sh falso: macOS corre su guion con
        tu usuario y dentro de tu sesión, sin pedir contraseña ni dejar nada instalado."""
        marca = self.dir / "marca.txt"
        falso = guion(self.dir / "instalar.sh", f'echo "YO=$(id -u) HOME=$HOME" > "{marca}"')
        variante = self.dir / "postinstall"
        texto = POSTINSTALL.read_text().replace(
            'INSTALADOR="${ONE_TV_INSTALADOR:-https://raw.githubusercontent.com/julai1433/one-tv/main/instalar.sh}"',
            f'INSTALADOR="file://{falso}"; export ONE_TV_CASA="{self.casa}" ONE_TV_SIN_VENTANAS=1')
        self.assertNotEqual(texto, POSTINSTALL.read_text())
        variante.write_text(texto)
        variante.chmod(0o755)
        r = subprocess.run([str(ROOT / "instaladores" / "armar.sh"), str(self.dir / "dist"), "mac"],
                           capture_output=True, text=True, env={**os.environ, "ONE_TV_POSTINSTALL": str(variante)})
        self.assertEqual(r.returncode, 0, r.stderr)
        pkg = self.dir / "dist" / "Instalar-One-TV-Mac.pkg"
        r = subprocess.run(["installer", "-pkg", str(pkg), "-target", "CurrentUserHomeDirectory"],
                           capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(marca.read_text().strip(), f"YO={os.getuid()} HOME={self.casa}")
        self.assertTrue(self.registro.exists())


class NombresFijos(unittest.TestCase):
    """El botón apunta a la versión «instaladores» con los nombres que arma instaladores/armar.sh y sube
    .github/workflows/instaladores.yml."""

    def test_los_mismos_nombres_en_todos_lados(self):
        pagina = PAGINA.read_text(encoding="utf-8")
        armar = (ROOT / "instaladores" / "armar.sh").read_text(encoding="utf-8")
        flujo = (ROOT / ".github" / "workflows" / "instaladores.yml").read_text(encoding="utf-8")
        for nombre in NOMBRES:
            self.assertIn(f'href="{VERSION}{nombre}"', pagina)
            self.assertIn(f"$SALIDA/{nombre}", armar)
            self.assertIn(nombre, flujo)
        self.assertIn("gh release upload instaladores", flujo)
        self.assertIn("--latest=false", flujo)   # «la más nueva» es la de la app de la TV (app-tv.yml)

    def test_los_comandos_de_la_pagina_son_los_de_la_guia(self):
        pagina = PAGINA.read_text(encoding="utf-8")
        guia = (ROOT / "docs" / "instalar-un-paso.md").read_text(encoding="utf-8")
        comandos = re.findall(r"<code>(.*?)</code>", pagina)
        self.assertEqual(len(comandos), 3)
        for c in comandos:
            self.assertIn(c, guia)
        self.assertIn(VERSION + NOMBRES[0], guia)
        self.assertIn("https://github.com/julai1433/one-tv/blob/main/docs/INSTALAR-DOCKER.md", pagina)

    @unittest.skipUnless(BASH, "instaladores/armar.sh necesita bash")
    def test_el_de_windows_es_el_de_siempre(self):
        with tempfile.TemporaryDirectory() as t:
            r = subprocess.run([BASH, str(ROOT / "instaladores" / "armar.sh"), t, "windows"],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(Path(t, NOMBRES[1]).read_bytes(), (ROOT / "Instalar One TV.cmd").read_bytes())
            self.assertIn(b"\r\n", Path(t, NOMBRES[1]).read_bytes())   # con CRLF: cmd.exe lo pide


@unittest.skipUnless(shutil.which("node"), "sin Node")
class PaginaReconoceElSistema(unittest.TestCase):
    AGENTES = {
        "mac": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141 Safari/537.36", 0),
        "windows": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141 Safari/537.36", 0),
        "linux": ("Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0", 0),
        "movil": ("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148", 5),
    }

    def detectar(self, ua, toques=0, buscar=""):
        js = re.search(r"function detectar\(\) \{.*?\n  \}\n", PAGINA.read_text(encoding="utf-8"), re.S).group(0)
        # Dentro de una función: Node ya trae su propio «navigator», y así el de mentira lo tapa.
        codigo = (f"(function () {{\nvar SISTEMAS = ['mac', 'windows', 'linux', 'movil'];\n"
                  f"var location = {{search: {json.dumps(buscar)}}};\n"
                  f"var navigator = {{userAgent: {json.dumps(ua)}, maxTouchPoints: {toques}, platform: ''}};\n"
                  f"{js}\nconsole.log(detectar());\n}})();")
        r = subprocess.run(["node", "-e", codigo], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def test_cada_sistema(self):
        for sistema, (ua, toques) in self.AGENTES.items():
            self.assertEqual(self.detectar(ua, toques), sistema, ua)
        android = "Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 Chrome/141 Mobile Safari/537.36"
        self.assertEqual(self.detectar(android), "movil")   # dice «Linux», pero es un teléfono
        ipad = self.AGENTES["mac"][0]
        self.assertEqual(self.detectar(ipad, toques=5), "movil")   # un iPad se presenta como Mac, pero es táctil
        self.assertEqual(self.detectar(self.AGENTES["mac"][0], buscar="?sistema=linux"), "linux")   # a mano


@unittest.skipUnless(BASH and MAC, "herramientas/firmar_mac.sh es para una Mac")
# El script de firma vive en herramientas/ (no se publica): en el repositorio público esta prueba se salta sola.
@unittest.skipUnless((ROOT / "herramientas" / "firmar_mac.sh").exists(), "sin herramientas/firmar_mac.sh")
class FirmarMac(unittest.TestCase):
    """Con programas falsos (security, xcrun…): nunca toca el llavero ni la cuenta de Apple de verdad."""

    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.dir = Path(self._t.name)
        self.bin = self.dir / "bin"
        self.log = self.dir / "llamadas.txt"
        self.log.touch()
        for p in ("productsign", "pkgutil", "spctl", "gh"):
            guion(self.bin / p, f'echo "{p} $*" >> "$LOG"')

    def firmar(self, identidades, perfil_ok, *args):
        guion(self.bin / "security", f'printf "%s\\n" {json.dumps(identidades)}')
        guion(self.bin / "xcrun", f'echo "xcrun $*" >> "$LOG"; [ "$1 $2" = "notarytool history" ] && exit {0 if perfil_ok else 1}; exit 0')
        pkg = self.dir / "Instalar-One-TV-Mac.pkg"
        pkg.write_text("pkg")
        r = subprocess.run([BASH, str(ROOT / "herramientas" / "firmar_mac.sh"), str(pkg), *args], capture_output=True,
                           text=True, env={"PATH": f"{self.bin}:/usr/bin:/bin", "LOG": str(self.log), "HOME": str(self.dir),
                                     "ONE_TV_EQUIPO_APPLE": "ABCDE12345"})
        return r.returncode, r.stdout + r.stderr

    def test_sin_certificado_ni_perfil_lo_dice_y_no_firma(self):
        code, out = self.firmar('  1) ABC "Apple Development: Ana (XYZ)"', False)
        self.assertEqual(code, 1)
        self.assertIn("Falta el certificado «Developer ID Installer» del equipo ABCDE12345", out)
        self.assertIn("Falta el perfil de notarización «one-tv»", out)
        self.assertIn("No firmé nada", out)
        self.assertNotIn("productsign", self.log.read_text())
        self.assertNotIn("submit", self.log.read_text())

    def test_con_el_de_aplicacion_pero_sin_el_de_instalador_explica_la_diferencia(self):
        code, out = self.firmar('  1) ABC "Developer ID Application: Ana Ejemplo (ABCDE12345)"', True)
        self.assertEqual(code, 1)
        self.assertIn("firma programas, no instaladores .pkg", out)
        self.assertNotIn("Falta el perfil", out)
        self.assertNotIn("productsign", self.log.read_text())

    def test_con_todo_firma_notariza_y_engrapa(self):
        guion(self.bin / "productsign", 'echo "productsign $*" >> "$LOG"; cp "${@: -2:1}" "${@: -1}"')
        guion(self.bin / "xcrun", r'''echo "xcrun $*" >> "$LOG"
case "$1 $2" in
  "notarytool submit") printf '<?xml version="1.0"?><plist version="1.0"><dict><key>status</key><string>Accepted</string><key>id</key><string>1</string></dict></plist>' ;;
  "stapler validate") exit 1 ;;
esac
exit 0''')
        guion(self.bin / "security", 'printf "%s\\n" \'  1) ABC "Developer ID Installer: Ana Ejemplo (ABCDE12345)"\'')
        pkg = self.dir / "Instalar-One-TV-Mac.pkg"
        pkg.write_text("pkg")
        r = subprocess.run([BASH, str(ROOT / "herramientas" / "firmar_mac.sh"), str(pkg)], capture_output=True,
                           text=True, env={"PATH": f"{self.bin}:/usr/bin:/bin", "LOG": str(self.log), "HOME": str(self.dir),
                                     "ONE_TV_EQUIPO_APPLE": "ABCDE12345"})
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, out)
        llamadas = self.log.read_text()
        self.assertIn('productsign --sign Developer ID Installer: Ana Ejemplo (ABCDE12345) --timestamp', llamadas)
        self.assertIn("xcrun notarytool submit", llamadas)
        self.assertIn("--keychain-profile one-tv --wait", llamadas)
        self.assertIn("xcrun stapler staple", llamadas)
        self.assertIn("Firmado, notarizado y engrapado", out)
        self.assertNotIn("gh release upload", llamadas)   # sin --subir no sube nada


if __name__ == "__main__":
    unittest.main()
