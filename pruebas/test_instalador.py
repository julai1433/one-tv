# El instalador de un paso para Mac y Linux (instalar.sh): elige bien qué bajar según la máquina (chip de Apple o
# Intel, también con Rosetta), revisa las sumas de verificación y si no coinciden no instala, no vuelve a bajar lo que
# ya está (el Python y el ffmpeg de la computadora, o los de One TV al día) y, al poner al día One TV, conserva
# config.json y lo bajado para One TV y no pisa una carpeta que no es suya. Sin red ni TV: lo «bajado» son archivos
# falsos en una carpeta temporal (file://). Necesitan bash (se saltan en Windows).
# python3 -m unittest discover -s pruebas -p "test_instalador.py"
import hashlib, os, shutil, subprocess, sys, tarfile, tempfile, unittest, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INSTALAR = ROOT / "instalar.sh"
BASH = shutil.which("bash") if sys.platform != "win32" else None


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def guion(path, texto):
    """Un programa falso (un guion de sh) que hace de python3, ffmpeg, uname…"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n" + texto + "\n")
    path.chmod(0o755)
    return path


@unittest.skipUnless(BASH, "instalar.sh necesita bash")
class InstaladorShell(unittest.TestCase):
    """Las funciones de instalar.sh, cargadas con ONE_TV_SOLO_FUNCIONES=1 (sin instalar nada)."""

    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.dir = Path(self._t.name)
        self.dest = self.dir / "One TV"
        self.tmp = self.dir / "tmp"
        self.tmp.mkdir()
        self.bin = self.dir / "bin"   # programas falsos, primero en el PATH
        self.bin.mkdir()

    def bash(self, codigo, **env):
        script = (f'ONE_TV_SOLO_FUNCIONES=1 source "{INSTALAR}"\n'
                  f'DEST="{self.dest}"; TMP="{self.tmp}"\n' + codigo)
        entorno = {"PATH": f"{self.bin}:/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(self.dir), "LANG": "C.UTF-8",
                   "ONE_TV_LUGARES": "", **env}
        r = subprocess.run([BASH, "-c", script], capture_output=True, text=True, env=entorno, timeout=120)
        return r.returncode, r.stdout + r.stderr

    # ---------- qué se baja según la máquina ----------

    def test_python_y_ffmpeg_segun_el_chip(self):
        code, out = self.bash("python_para arm64; python_para x86_64; ffmpeg_para arm64; ffmpeg_para x86_64; "
                              "python_para ppc || echo NO-PPC; ffmpeg_para i386 || echo NO-I386")
        self.assertEqual(code, 0, out)
        lineas = out.strip().splitlines()
        self.assertIn("cpython-3.12.15%2B20261003-aarch64-apple-darwin-install_only_stripped.tar.gz", lineas[0])
        self.assertTrue(lineas[0].endswith(" ad8d0c637c0a36b967b310e2c07254f4d2ca8cabaa7699e55ed6290aceb481a2"))
        self.assertIn("x86_64-apple-darwin-install_only_stripped.tar.gz", lineas[1])
        self.assertTrue(lineas[1].startswith("https://github.com/astral-sh/python-build-standalone/releases/download/"))
        url_ffmpeg, sha_ffmpeg, url_ffprobe, sha_ffprobe = lineas[2].split()
        self.assertEqual(url_ffmpeg, "https://ffmpeg.martin-riedl.de/download/macos/arm64/1789931890_9.0.2/ffmpeg.zip")
        self.assertTrue(url_ffprobe.endswith("/arm64/1789931890_9.0.2/ffprobe.zip"))
        self.assertNotEqual(sha_ffmpeg, sha_ffprobe)
        self.assertIn("/macos/amd64/", lineas[3])
        self.assertEqual(lineas[4:], ["NO-PPC", "NO-I386"])
        for linea in lineas[:4]:   # todas las sumas: 64 cifras hexadecimales
            for parte in linea.split()[1::2]:
                self.assertRegex(parte, r"^[0-9a-f]{64}$")

    def test_chip_de_apple_aunque_la_terminal_corra_con_rosetta(self):
        guion(self.bin / "uname", 'echo x86_64')
        guion(self.bin / "sysctl", 'echo 1')   # sysctl.proc_translated = 1: Rosetta
        self.assertEqual(self.bash("arquitectura")[1].strip(), "arm64")
        guion(self.bin / "sysctl", 'echo 0')
        self.assertEqual(self.bash("arquitectura")[1].strip(), "x86_64")
        guion(self.bin / "uname", 'echo arm64')
        self.assertEqual(self.bash("arquitectura")[1].strip(), "arm64")

    def test_version_de_ffmpeg(self):
        casos = {"ffmpeg version 7.1.1 Copyright": True, "ffmpeg version 9.0.2-https://www.martin-riedl.de": True,
                 "ffmpeg version n7.0.2": True, "ffmpeg version N-127236-g17ec998942": True,
                 "ffmpeg version 6.1.1-3ubuntu5": False, "ffmpeg version 4.4.2": False, "algo raro": False}
        for primera, sirve in casos.items():
            guion(self.bin / "ffmpeg", f'echo "{primera}"')
            guion(self.bin / "ffprobe", "exit 0")
            code, _ = self.bash(f'ffmpeg_sirve "{self.bin}/ffmpeg"')
            self.assertEqual(code == 0, sirve, primera)
        (self.bin / "ffprobe").unlink()   # sin ffprobe al lado no sirve
        guion(self.bin / "ffmpeg", 'echo "ffmpeg version 8.0"')
        self.assertNotEqual(self.bash(f'ffmpeg_sirve "{self.bin}/ffmpeg"')[0], 0)

    def test_el_python3_de_la_mac_sin_xcode_no_cuenta(self):
        # /usr/bin/python3 sin las herramientas de Xcode abriría su instalador: no se usa ni se prueba.
        guion(self.bin / "xcode-select", "exit 2")
        code, _ = self.bash("xcode_listo")
        self.assertNotEqual(code, 0)
        dev = self.dir / "Developer"
        guion(dev / "usr" / "bin" / "python3", "exit 0")
        guion(self.bin / "xcode-select", f'echo "{dev}"')
        self.assertEqual(self.bash("xcode_listo")[0], 0)

    # ---------- no vuelve a bajar lo que ya está ----------

    def test_usa_el_python_y_el_ffmpeg_que_ya_hay(self):
        guion(self.bin / "python3", "exit 0")   # «import venv, ensurepip» y 3.9+: sí
        guion(self.bin / "ffmpeg", 'echo "ffmpeg version 8.0.1"')
        guion(self.bin / "ffprobe", "exit 0")
        guion(self.bin / "curl", 'echo "NO DEBIA BAJAR NADA" >&2; exit 9')
        code, out = self.bash('programas_mac && echo "PY=$PY" && echo "FFMPEG=$FFMPEG"')
        self.assertEqual(code, 0, out)
        self.assertIn(f"PY={self.bin}/python3", out)
        self.assertIn(f"FFMPEG={self.bin}/ffmpeg", out)
        self.assertIn("uso el que ya tienes", out)
        self.assertNotIn("NO DEBIA", out)
        # Fuera de los lugares que mira el servicio de fondo (Homebrew, /usr/local/bin): se enlaza en programas/bin.
        self.assertEqual(os.readlink(self.dest / "programas" / "bin" / "ffmpeg"), f"{self.bin}/ffmpeg")
        self.assertFalse((self.dest / "programas" / "python").exists())

    def test_un_ffmpeg_fuera_de_los_lugares_de_siempre_se_enlaza(self):
        otro = self.dir / "macports" / "bin"
        guion(otro / "ffmpeg", 'echo "ffmpeg version 7.1"')
        guion(otro / "ffprobe", "exit 0")
        code, out = self.bash(f'enlazar_ffmpeg "{otro}/ffmpeg" && readlink "$DEST/programas/bin/ffmpeg" '
                              '&& readlink "$DEST/programas/bin/ffprobe"')
        self.assertEqual(code, 0, out)
        self.assertEqual(out.split(), [f"{otro}/ffmpeg", f"{otro}/ffprobe"])

    def test_lo_de_one_tv_al_dia_no_se_vuelve_a_bajar_y_lo_viejo_si(self):
        py = guion(self.dest / "programas" / "python" / "bin" / "python3", "exit 0")
        (py.parent.parent / ".version-one-tv").write_text("3.12.15+20261003\n")
        guion(self.dest / "programas" / "bin" / "ffmpeg", 'echo "ffmpeg version 9.0.2-https://www.martin-riedl.de"')
        guion(self.dest / "programas" / "bin" / "ffprobe", "exit 0")
        (self.dest / "programas" / "bin" / ".ffmpeg-one-tv").write_text("9.0.2\n")
        guion(self.bin / "curl", 'echo "NO DEBIA BAJAR NADA" >&2; exit 9')
        code, out = self.bash('programas_mac && echo "PY=$PY"')
        self.assertEqual(code, 0, out)
        self.assertIn(f"PY={py}", out)
        self.assertNotIn("NO DEBIA", out)
        # Un Python de One TV de una versión anterior: se baja el nuevo (curl falla aquí: lo intentó).
        (py.parent.parent / ".version-one-tv").write_text("3.12.1+20240101\n")
        code, out = self.bash("programas_mac")
        self.assertNotEqual(code, 0)
        self.assertIn("NO DEBIA", out)
        self.assertIn("No pude bajar Python", out)

    # ---------- las sumas de verificación ----------

    def preparar_python_falso(self):
        """Un «python-build-standalone» falso: python/bin/python3 dentro de un .tar.gz, servido con file://."""
        pbs = self.dir / "pbs" / "20261003"
        pbs.mkdir(parents=True)
        dentro = self.dir / "pbs-dentro"
        guion(dentro / "python" / "bin" / "python3", "exit 0")
        archivo = pbs / "cpython-3.12.15+20261003-aarch64-apple-darwin-install_only_stripped.tar.gz"
        with tarfile.open(archivo, "w:gz") as t:
            t.add(dentro / "python", arcname="python")
        return f"file://{self.dir}/pbs", sha(archivo)

    def test_python_con_su_suma_se_instala_y_si_no_coincide_no(self):
        base, suma = self.preparar_python_falso()
        code, out = self.bash(f'PY_BASE="{base}"; PY_SHA_arm64="{suma}"; instalar_python_mac arm64')
        self.assertEqual(code, 0, out)
        self.assertTrue((self.dest / "programas" / "python" / "bin" / "python3").exists())
        self.assertEqual((self.dest / "programas" / "python" / ".version-one-tv").read_text().strip(),
                         "3.12.15+20261003")
        shutil.rmtree(self.dest / "programas")
        code, out = self.bash(f'PY_BASE="{base}"; PY_SHA_arm64="{"0" * 64}"; instalar_python_mac arm64')
        self.assertNotEqual(code, 0)
        self.assertIn("su suma de verificación no coincide", out)
        self.assertIn("no lo instalo", out)
        self.assertFalse((self.dest / "programas" / "python").exists())

    def preparar_ffmpeg_falso(self, version="9.0.2"):
        d = self.dir / "riedl" / "arm64" / "1789931890_9.0.2"
        d.mkdir(parents=True, exist_ok=True)
        sumas = {}
        for programa in ("ffmpeg", "ffprobe"):
            with zipfile.ZipFile(d / f"{programa}.zip", "w") as z:
                z.writestr(programa, f'#!/bin/sh\necho "{programa} version {version}-prueba"\n')
            sumas[programa] = sha(d / f"{programa}.zip")
        return f"file://{self.dir}/riedl", sumas

    def test_ffmpeg_con_su_suma_se_instala_y_si_no_coincide_no(self):
        base, sumas = self.preparar_ffmpeg_falso()
        guion(self.bin / "sw_vers", "echo 14.5")
        code, out = self.bash(f'FFMPEG_BASE="{base}"; FFMPEG_SHA_arm64="{sumas["ffmpeg"]}"; '
                              f'FFPROBE_SHA_arm64="{sumas["ffprobe"]}"; instalar_ffmpeg_mac arm64')
        self.assertEqual(code, 0, out)
        self.assertIn("unos 56 MB", out)
        for programa in ("ffmpeg", "ffprobe"):
            self.assertTrue(os.access(self.dest / "programas" / "bin" / programa, os.X_OK))
        self.assertEqual((self.dest / "programas" / "bin" / ".ffmpeg-one-tv").read_text().strip(), "9.0.2")
        shutil.rmtree(self.dest / "programas")
        code, out = self.bash(f'FFMPEG_BASE="{base}"; FFMPEG_SHA_arm64="{sumas["ffmpeg"]}"; '
                              f'FFPROBE_SHA_arm64="{"f" * 64}"; instalar_ffmpeg_mac arm64')
        self.assertNotEqual(code, 0)
        self.assertIn("lo que bajó de ffprobe no es lo que esperaba", out.lower())
        self.assertFalse((self.dest / "programas" / "bin").exists())

    def test_ffmpeg_pide_macos_12(self):
        base, sumas = self.preparar_ffmpeg_falso()
        guion(self.bin / "sw_vers", "echo 11.7.10")
        code, out = self.bash(f'FFMPEG_BASE="{base}"; instalar_ffmpeg_mac arm64')
        self.assertNotEqual(code, 0)
        self.assertIn("macOS 12", out)
        self.assertIn("brew install ffmpeg", out)

    # ---------- bajar One TV y ponerlo al día ----------

    def fuente(self, nombre, archivos):
        """Un .tar.gz como el de GitHub: todo dentro de one-tv-main/."""
        d = self.dir / f"fuente-{nombre}" / "one-tv-main"
        for ruta, texto in archivos.items():
            (d / ruta).parent.mkdir(parents=True, exist_ok=True)
            (d / ruta).write_text(texto)
        archivo = self.dir / f"{nombre}.tar.gz"
        with tarfile.open(archivo, "w:gz") as t:
            t.add(d, arcname="one-tv-main")
        return archivo

    def test_actualizar_conserva_la_configuracion_y_lo_bajado(self):
        v1 = self.fuente("v1", {"cine": "#!/bin/bash\n", "mac/cine.py": "v1", "mac/viejo.py": "se va", "README.md": "1",
                                ".gitattributes": "x", "One TV.command": "doble clic"})
        code, out = self.bash(f'ONE_TV_FUENTE="{v1}" bajar_one_tv')
        self.assertEqual(code, 0, out)
        self.assertIn("Bajando One TV", out)
        self.assertEqual((self.dest / "mac" / "cine.py").read_text(), "v1")
        self.assertTrue(os.access(self.dest / "cine", os.X_OK))
        self.assertTrue((self.dest / "One TV.command").exists())   # nombres con espacios
        self.assertTrue((self.dest / ".gitattributes").exists())   # y los que empiezan con punto
        (self.dest / "config.json").write_text('{"puerto": 8765, "roku_password": "secreta"}')
        guion(self.dest / "programas" / "bin" / "ffmpeg", "exit 0")
        v2 = self.fuente("v2", {"cine": "#!/bin/bash\n", "mac/cine.py": "v2", "README.md": "2",
                                "Instalar One TV.command": "nuevo"})
        code, out = self.bash(f'ONE_TV_FUENTE="{v2}" bajar_one_tv')
        self.assertEqual(code, 0, out)
        self.assertIn("Poniendo al día One TV", out)
        self.assertEqual((self.dest / "mac" / "cine.py").read_text(), "v2")
        self.assertFalse((self.dest / "mac" / "viejo.py").exists())        # lo que se borró del proyecto se va
        self.assertTrue((self.dest / "Instalar One TV.command").exists())
        self.assertIn("secreta", (self.dest / "config.json").read_text())   # tu configuración se queda
        self.assertTrue((self.dest / "programas" / "bin" / "ffmpeg").exists())   # y lo bajado para One TV

    def test_no_pisa_una_carpeta_que_no_es_de_one_tv(self):
        self.dest.mkdir()
        (self.dest / "foto.jpg").write_text("tuya")
        v1 = self.fuente("v1", {"cine": "#!/bin/bash\n", "mac/cine.py": "v1"})
        code, out = self.bash(f'ONE_TV_FUENTE="{v1}" bajar_one_tv')
        self.assertNotEqual(code, 0)
        self.assertIn("no es de One TV", out)
        self.assertEqual(sorted(p.name for p in self.dest.iterdir()), ["foto.jpg"])

    def test_lo_que_no_parece_one_tv_no_se_instala(self):
        malo = self.fuente("malo", {"index.html": "<html>error</html>"})
        code, out = self.bash(f'ONE_TV_FUENTE="{malo}" bajar_one_tv')
        self.assertNotEqual(code, 0)
        self.assertIn("no parece One TV", out)
        self.assertFalse(self.dest.exists())

    def test_una_copia_con_git_no_se_pisa(self):
        if not shutil.which("git"):
            self.skipTest("sin git")
        self.dest.mkdir()
        (self.dest / "cine").write_text("mio")
        subprocess.run(["git", "init", "-q", str(self.dest)], check=True)
        v1 = self.fuente("v1", {"cine": "#!/bin/bash\n", "mac/cine.py": "v1"})
        code, out = self.bash(f'ONE_TV_FUENTE="{v1}" bajar_one_tv', PATH=f"{self.bin}:{os.environ['PATH']}")
        self.assertEqual(code, 0, out)
        self.assertIn("copia hecha con git", out)
        self.assertEqual((self.dest / "cine").read_text(), "mio")


if __name__ == "__main__":
    unittest.main()
