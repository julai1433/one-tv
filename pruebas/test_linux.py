# El servidor fuera de macOS (Linux, Ubuntu): carpetas de XDG y del usuario, el servicio de systemd, qué codificador
# de video se elige, el mosaico sin el chip de la Mac y con el ffmpeg 6.1 de Ubuntu, el código QR en Python puro y
# lo que revisa ./cine antes de arrancar. Corren en cualquier sistema (lo de Linux se simula, también en Windows); las
# que necesitan Linux de verdad (o bash) se saltan solas. Sin red.
# python3 -m unittest discover -s pruebas -p "test_linux.py"
import hashlib, importlib, io, os, shutil, struct, subprocess, sys, tempfile, unittest, zlib
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mac"))
import cine
import encoders
import hostos
import linuxservice
import mosaic
import qrcodegen
import qrpng
from transcode import FullPlan
from youtube import YouTube

ROOT = Path(__file__).resolve().parent.parent
LINUX = sys.platform.startswith("linux")
WINDOWS = sys.platform == "win32"


def casa(path):
    """La carpeta personal de prueba, para macOS y Linux (HOME) y para Windows (USERPROFILE)."""
    return {"HOME": str(path), "USERPROFILE": str(path)}


def leer_png(data):
    """(ancho, alto, filas RGB) de un PNG de color sin entrelazar, con filtro 0 (como los que hace qrpng)."""
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    pos, idat, ihdr = 8, b"", None
    while pos < len(data):
        n, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + n]
        assert zlib.crc32(kind + body) & 0xFFFFFFFF == struct.unpack(">I", data[pos + 8 + n:pos + 12 + n])[0]
        if kind == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", body)
        elif kind == b"IDAT":
            idat += body
        pos += 12 + n
    w, h, bits, color = ihdr[:4]
    assert (bits, color) == (8, 2)
    raw = zlib.decompress(idat)
    rows = [raw[y * (w * 3 + 1):(y + 1) * (w * 3 + 1)] for y in range(h)]
    assert all(r[0] == 0 for r in rows)
    return w, h, [r[1:] for r in rows]


def ffmpeg_hay():
    return shutil.which("ffmpeg") is not None


class Carpetas(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def en_linux(self):
        """hostos como si esta computadora fuera Linux, con la carpeta personal de prueba."""
        env = {**casa(self.home), "XDG_CACHE_HOME": "", "XDG_DATA_HOME": "", "XDG_STATE_HOME": "",
               "XDG_CONFIG_HOME": ""}
        with mock.patch.dict(os.environ, env), mock.patch("sys.platform", "linux"):
            mod = importlib.reload(hostos)
            self.addCleanup(importlib.reload, hostos)   # al terminar, como era
            return mod

    def test_linux_usa_las_carpetas_de_xdg(self):
        h = self.en_linux()
        self.assertFalse(h.MAC)
        self.assertEqual(h.CACHE, self.home / ".cache" / "cine-roku")
        self.assertEqual(h.SERVICE_HOME, self.home / ".local" / "share" / "cine-roku")
        self.assertEqual(h.LOG, self.home / ".local" / "state" / "cine-roku" / "cine-roku.log")

    def test_xdg_de_las_variables_si_son_rutas_completas(self):
        otra = os.path.join(os.path.abspath(os.sep), "otra", "cache")   # /otra/cache (C:\otra\cache en Windows)
        with mock.patch.dict(os.environ, {"XDG_CACHE_HOME": otra, "XDG_DATA_HOME": "relativa"}):
            self.assertEqual(hostos._xdg("XDG_CACHE_HOME", ".cache"), Path(otra))
            self.assertEqual(hostos._xdg("XDG_DATA_HOME", ".local/share"), Path.home() / ".local/share")

    def test_carpetas_del_usuario_en_espanol(self):
        h = self.en_linux()
        conf = self.home / ".config"
        conf.mkdir()
        (conf / "user-dirs.dirs").write_text('# comentario\nXDG_DOWNLOAD_DIR="$HOME/Descargas"\n'
                                             'XDG_VIDEOS_DIR="$HOME/Vídeos"\nXDG_MUSIC_DIR="$HOME"\n')
        with mock.patch.dict(os.environ, casa(self.home)), mock.patch.object(h, "CONFIG_HOME", conf):
            self.assertEqual(h.user_dir("DOWNLOAD"), self.home / "Descargas")
            self.assertEqual(h.user_dir("VIDEOS"), self.home / "Vídeos")
            self.assertEqual(h.user_dir("MUSIC"), self.home / "Music")   # «$HOME» a secas: no hay; la de inglés
            self.assertEqual(h.default_library(), os.path.join("~", "Vídeos", "Biblioteca"))

    def test_sin_user_dirs_las_de_ingles(self):
        h = self.en_linux()
        with mock.patch.dict(os.environ, casa(self.home)):
            self.assertEqual(h.user_dir("VIDEOS"), self.home / "Videos")
            self.assertEqual(h.user_dir("DOWNLOAD"), self.home / "Downloads")

    @unittest.skipUnless(sys.platform == "darwin", "solo macOS")
    def test_macos_queda_igual(self):
        home = Path.home()
        self.assertEqual(hostos.CACHE, home / "Library" / "Caches" / "cine-roku")
        self.assertEqual(hostos.SERVICE_HOME, home / "Library" / "Application Support" / "cine-roku")
        self.assertEqual(hostos.LOG, home / "Library" / "Logs" / "cine-roku.log")
        self.assertEqual([hostos.user_dir(k) for k in ("DOWNLOAD", "VIDEOS", "MUSIC")],
                         [home / "Downloads", home / "Movies", home / "Music"])
        self.assertEqual(hostos.default_library(), "~/Movies/Biblioteca")
        self.assertEqual((cine.CACHE, cine.SERVICE_LOG), (hostos.CACHE, hostos.LOG))
        self.assertEqual(hostos.keep_awake_command(900), ["caffeinate", "-i", "-t", "900"])

    def test_linux_sin_pantalla_no_abre_el_navegador(self):
        h = self.en_linux()
        with mock.patch.dict(os.environ, {"DISPLAY": "", "WAYLAND_DISPLAY": ""}), \
                mock.patch("subprocess.Popen") as popen, mock.patch("webbrowser.open") as wb:
            self.assertFalse(h.open_browser("http://localhost:8765"))
        popen.assert_not_called()
        wb.assert_not_called()
        with mock.patch.dict(os.environ, {"DISPLAY": ":0"}), mock.patch("shutil.which", return_value="/usr/bin/xdg-open"), \
                mock.patch("subprocess.Popen") as popen:
            self.assertTrue(h.open_browser("http://localhost:8765"))
        self.assertEqual(popen.call_args[0][0], ["/usr/bin/xdg-open", "http://localhost:8765"])

    def test_linux_no_dormirse_con_systemd_inhibit(self):
        h = self.en_linux()
        with mock.patch("shutil.which", return_value="/usr/bin/systemd-inhibit"):
            cmd = h.keep_awake_command(900)
        self.assertEqual(cmd[0], "systemd-inhibit")
        self.assertIn("--what=sleep:idle", cmd)
        self.assertEqual(cmd[-2:], ["sleep", "900"])
        with mock.patch("shutil.which", return_value=None):
            self.assertIsNone(h.keep_awake_command(900))

    def test_chrome_de_snap_usa_una_carpeta_que_el_snap_ve(self):
        h = self.en_linux()
        guion = self.home / "chromium-browser"
        guion.write_text("#!/bin/sh\nexec /snap/bin/chromium \"$@\"\n")
        normal = self.home / "chrome"
        normal.write_bytes(b"\x7fELF...")
        with mock.patch.dict(os.environ, casa(self.home)):
            esperado = str(self.home / "snap" / "chromium" / "common")
            self.assertEqual(h.chrome_profile_parent("/snap/bin/chromium"), esperado)
            self.assertEqual(h.chrome_profile_parent(str(guion)), esperado)
            self.assertIsNone(h.chrome_profile_parent(str(normal)))
        self.assertTrue(all(p.startswith(("/usr/", "/opt/", "/snap/")) for p in h.CHROME_PATHS))


class Servicio(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.unit = Path(self.tmp.name) / "systemd" / "user" / "cine-roku.service"
        p = mock.patch.object(linuxservice, "UNIT", self.unit)
        p.start()
        self.addCleanup(p.stop)

    def test_la_unidad(self):
        log = Path(self.tmp.name) / "estado" / "cine-roku.log"
        text = linuxservice.unit_text("/usr/bin/python3", "/home/ana/mis cosas/100% cine/mac/cine.py",
                                      "/home/ana/.local/share/cine-roku", log)
        self.assertIn('ExecStart="/usr/bin/python3" "/home/ana/mis cosas/100%% cine/mac/cine.py" servir', text)
        for line in ("Restart=always", "RestartSec=30", "WorkingDirectory=/home/ana/.local/share/cine-roku",
                     f"StandardOutput=append:{log}", f"StandardError=append:{log}", "WantedBy=default.target",
                     "Environment=PYTHONUNBUFFERED=1"):
            self.assertIn(line + "\n", text)

    def test_se_escribe_solo_si_cambia(self):
        log = Path(self.tmp.name) / "estado" / "cine-roku.log"
        self.assertTrue(linuxservice.write("/usr/bin/python3", "/x/mac/cine.py", "/x", log))
        self.assertTrue(self.unit.exists() and log.parent.is_dir())
        self.assertFalse(linuxservice.write("/usr/bin/python3", "/x/mac/cine.py", "/x", log))
        self.assertTrue(linuxservice.write("/usr/bin/python3.12", "/x/mac/cine.py", "/x", log))

    def test_pid(self):
        for out, want in (("4242\n", 4242), ("0\n", None), ("", None)):
            with mock.patch.object(linuxservice, "systemctl",
                                   return_value=subprocess.CompletedProcess([], 0, out, "")):
                self.assertEqual(linuxservice.pid(), want)

    def test_sin_systemd_lo_dice(self):
        with mock.patch("shutil.which", return_value=None):
            self.assertIn("no usa systemd", linuxservice.problem())
        with mock.patch("shutil.which", return_value="/usr/bin/systemctl"), \
                mock.patch.object(linuxservice, "systemctl", return_value=subprocess.CompletedProcess(
                    [], 1, "", "Failed to connect to bus: No medium found")):
            self.assertIn("No medium found", linuxservice.problem())

    def test_autoarranque_en_linux(self):
        """./cine autoarranque en Linux: copia el programa, escribe la unidad, la arranca y activa «linger»."""
        llamadas = []
        with mock.patch.object(cine.hostos, "MAC", False), mock.patch.object(cine.hostos, "WINDOWS", False), \
                mock.patch.object(cine, "sync_service_files", lambda: llamadas.append("copiar")), \
                mock.patch.object(cine, "write_plist", lambda: llamadas.append("unidad")), \
                mock.patch.object(linuxservice, "problem", return_value=""), \
                mock.patch.object(linuxservice, "start", lambda: llamadas.append("arrancar") or ""), \
                mock.patch.object(linuxservice, "lingering", return_value=False), \
                mock.patch.object(linuxservice, "enable_linger", lambda: llamadas.append("linger") or True), \
                mock.patch.object(cine, "server_answers", return_value=None), redirect_stdout(io.StringIO()):
            cine.install_service({"puerto": 1})
        self.assertEqual(llamadas, ["copiar", "unidad", "arrancar", "linger"])
        with mock.patch.object(cine.hostos, "MAC", False), mock.patch.object(cine.hostos, "WINDOWS", False):
            self.assertFalse(cine.service_installed())
            self.unit.parent.mkdir(parents=True)
            self.unit.write_text("[Unit]\n")
            self.assertTrue(cine.service_installed())

    def test_la_barra_no_aplica_en_linux(self):
        out = io.StringIO()
        with mock.patch.object(cine.hostos, "MAC", False), mock.patch.object(cine.hostos, "WINDOWS", False), \
                mock.patch.object(sys, "argv", ["cine.py", "barra"]), \
                mock.patch.object(cine, "install_menubar") as barra, redirect_stdout(out):
            cine.main()
        barra.assert_not_called()
        self.assertIn("solo para macOS", out.getvalue())


def corrida(returncode=0, stdout=""):
    return subprocess.CompletedProcess([], returncode, stdout, "")


class Codificador(unittest.TestCase):
    def setUp(self):
        for p in (mock.patch.object(encoders, "MAC", False), mock.patch.object(encoders, "WINDOWS", False),
                  mock.patch.object(encoders, "render_nodes", return_value=[])):
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(setattr, encoders, "_current", None)
        self.logs = []

    def falso(self, conocidos, sirven):
        """run de mentira: ffmpeg trae estos codificadores y solo estos funcionan en la prueba de un segundo."""
        self.probados = []

        def run(cmd, **kw):
            if "-encoders" in cmd:
                return corrida(0, "Encoders:\n V..... = Video\n" + "".join(f" V....D {c}  algo\n" for c in conocidos))
            codec = cmd[cmd.index("-c:v") + 1]
            self.probados.append(codec)
            return corrida(0 if codec in sirven else 1)
        return run

    def test_se_queda_con_el_primer_chip_que_funciona(self):
        run = self.falso(["libx264", "h264_nvenc", "h264_qsv", "h264_vaapi"], {"h264_qsv", "h264_vaapi"})
        with mock.patch.object(encoders, "render_nodes", return_value=["/dev/dri/renderD128"]):
            enc = encoders.detect("auto", self.logs.append, run)
        self.assertEqual((enc.name, self.probados), ("qsv", ["h264_nvenc", "h264_qsv"]))
        self.assertIs(encoders.current(), enc)
        self.assertIn("Quick Sync", self.logs[-1])

    def test_vaapi_por_cada_dispositivo(self):
        run = self.falso(["h264_vaapi"], {"h264_vaapi"})
        with mock.patch.object(encoders, "render_nodes", return_value=["/dev/dri/renderD128", "/dev/dri/renderD129"]):
            enc = encoders.detect("auto", self.logs.append, run)
        self.assertEqual(enc.name, "vaapi")
        self.assertEqual(enc.args[:2], ["-vaapi_device", "/dev/dri/renderD128"])
        self.assertEqual(enc.upload, ",format=nv12,hwupload")

    def test_sin_chip_el_procesador(self):
        run = self.falso(["libx264", "h264_nvenc"], set())
        with mock.patch.object(encoders, "render_nodes", return_value=[]):
            self.assertIs(encoders.detect("auto", self.logs.append, run), encoders.SOFTWARE)
        self.assertIn("libx264", self.logs[0])
        run = self.falso(["libx264"], set())
        with mock.patch.object(encoders, "render_nodes", return_value=[]):
            self.assertIs(encoders.detect("auto", self.logs.append, run), encoders.SOFTWARE)
        self.assertEqual(self.probados, [])   # nada que probar

    def test_config_lo_fija(self):
        run = self.falso(["h264_nvenc", "h264_qsv"], {"h264_nvenc", "h264_qsv"})
        self.assertIs(encoders.detect("libx264", self.logs.append, run), encoders.SOFTWARE)
        self.assertEqual(self.probados, [])
        self.assertEqual(encoders.detect("qsv", self.logs.append, run).name, "qsv")
        self.assertEqual(self.probados, ["h264_qsv"])
        self.assertIs(encoders.detect("vaapi", self.logs.append, self.falso(["h264_vaapi"], set())), encoders.SOFTWARE)
        self.assertIn("no funcionó", self.logs[-1])
        encoders.detect("cualquiera", self.logs.append, self.falso([], set()))
        self.assertIn("debe ser uno de", self.logs[-2])

    def test_en_la_mac_siempre_videotoolbox(self):
        with mock.patch.object(encoders, "MAC", True):
            self.assertIs(encoders.detect("libx264", self.logs.append, self.falso([], set())), encoders.VIDEOTOOLBOX)
        self.assertEqual(self.logs, [])

    def test_la_conversion_completa_usa_el_elegido(self):
        item = {"id": "a" * 12, "path": "/pelis/a.mkv", "duration": 60, "full_title": "A",
                "info": {"video": {"index": 0, "codec": "hevc", "pix_fmt": "yuv420p10le", "width": 3840,
                                   "height": 2160}, "audio": [{"index": 1, "channels": 2}]}}
        with mock.patch("transcode.VIDEOTOOLBOX", False):
            for enc, codec in ((encoders.SOFTWARE, "libx264"), (encoders.NVENC, "h264_nvenc"),
                               (encoders.vaapi("/dev/dri/renderD128"), "h264_vaapi")):
                with mock.patch.object(encoders, "_current", enc):
                    cmd = FullPlan(item).command(1, 0, Path("/tmp/x"))
                self.assertEqual(cmd[cmd.index("-c:v") + 1], codec)
                self.assertNotIn("videotoolbox", " ".join(cmd))
                vf = cmd[cmd.index("-vf") + 1]
                self.assertEqual(vf.endswith(",format=nv12,hwupload"), codec == "h264_vaapi")
                self.assertEqual("-vaapi_device" in cmd, codec == "h264_vaapi")
                self.assertEqual(cmd[cmd.index("-profile:v") + 1], "high")
            # Con el procesador, las mismas opciones de antes de este cambio.
            with mock.patch.object(encoders, "_current", encoders.SOFTWARE):
                cmd = FullPlan(item).command(1, 0, Path("/tmp/x"))
            i = cmd.index("-vf")
            self.assertEqual(cmd[i + 2:i + 8], ["-c:v", "libx264", "-preset", "veryfast", "-profile:v", "high"])

    @unittest.skipUnless(ffmpeg_hay(), "hace falta ffmpeg")
    def test_la_prueba_de_un_segundo_de_verdad(self):
        self.assertTrue(encoders.works(encoders.SOFTWARE))
        self.assertFalse(encoders.works(encoders.Encoder("nada", "nada", ["-c:v", "h264_no_existe"])))
        self.assertTrue(encoders.ffmpeg_knows("readrate_initial_burst"))   # ffmpeg 6.1 o más nuevo
        self.assertFalse(encoders.ffmpeg_knows("opcion_que_no_existe"))

    @unittest.skipUnless(LINUX and ffmpeg_hay(), "solo en Linux con ffmpeg")
    def test_en_linux_de_verdad_elige_alguno(self):
        enc = encoders.detect("auto", self.logs.append)
        self.assertIn(enc.name, ("nvenc", "qsv", "vaapi", "libx264"))
        self.assertTrue(self.logs[0].startswith(("✓ Video", "· Video")))


class MosaicoEnLinux(unittest.TestCase):
    def test_empieza_con_el_procesador(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        with mock.patch.object(encoders, "_current", encoders.SOFTWARE):
            m = mosaic.Mosaic("abcd0123", [], tmp.name, "http://127.0.0.1:1")
        self.assertEqual(mosaic.TIERS[m.tier], "procesador")
        with mock.patch.object(encoders, "_current", encoders.VIDEOTOOLBOX):
            self.assertEqual(mosaic.Mosaic("abcd0124", [], tmp.name, "http://127.0.0.1:1").tier, 0)

    def test_ffmpeg_6_sin_las_opciones_del_7(self):
        src = {"local": False, "live": True, "video": "http://127.0.0.1:1/live/x/index.m3u8", "audio": None,
               "vsel": "v:0", "asel": "a:0", "width": 1280, "height": 720, "codec": "h264", "pix_fmt": "yuv420p",
               "channels": 2, "start": 0}
        yt = dict(src, live=False)
        for conoce in (True, False):
            with mock.patch.object(encoders, "ffmpeg_knows", return_value=conoce):
                cmd = mosaic.build_command([src, yt], "alt", Path("/tmp/m"), tier="procesador")
            self.assertEqual("-extension_picky" in cmd, conoce)
            self.assertEqual("-readrate_catchup" in cmd, conoce)
            self.assertIn("-readrate_initial_burst", cmd)
            self.assertEqual(cmd[cmd.index("-c:v") + 1], "libx264")


class CodigoQR(unittest.TestCase):
    def test_como_el_de_coreimage(self):
        """El de un video normal sale igual, píxel por píxel, que el que hacía la Mac con CoreImage (comparado el
        7 oct 2026): 624×624, cuadros de 18 px claros sobre negro."""
        w, h, rows = leer_png(qrpng.qr_png("https://youtu.be/dQw4w9WgXcQ", 624))
        self.assertEqual((w, h), (624, 624))
        self.assertEqual(hashlib.sha256(b"".join(rows)).hexdigest(),
                         "39e66936971477e27fc8ce02d976a6dae7fed7ffb74f4194d35385876f21190e")
        self.assertEqual({rows[y][x:x + 3] for y in range(0, 624, 7) for x in range(0, 624 * 3, 21)},
                         {bytes(qrpng.LIGHT), bytes(qrpng.DARK)})

    def test_los_cuadros_son_los_del_codigo(self):
        text = "https://youtu.be/abcdefghijk?t=125"
        qr = qrcodegen.QrCode.encode_segments(qrcodegen.QrSegment.make_segments(text), qrcodegen.QrCode.Ecc.MEDIUM,
                                              boostecl=False)
        n = qr.get_size() + 2
        scale = (624 - 64) // n
        off = (624 - n * scale) // 2
        _, _, rows = leer_png(qrpng.qr_png(text, 624))
        for y in range(n):
            for x in range(n):
                on = 0 < x < n - 1 and 0 < y < n - 1 and qr.get_module(x - 1, y - 1)
                px = rows[off + y * scale + scale // 2][(off + x * scale + scale // 2) * 3:][:3]
                self.assertEqual(px, bytes(qrpng.LIGHT if on else qrpng.DARK), (x, y))

    def test_youtube_lo_guarda(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        yt = YouTube(tmp.name, tmp.name, ytdlp="/nada")
        with mock.patch("subprocess.run") as run:
            path = yt.qr("dQw4w9WgXcQ")
        run.assert_not_called()   # ni osascript ni ffmpeg
        self.assertEqual(leer_png(path.read_bytes())[:2], (624, 624))
        self.assertEqual(yt.qr("dQw4w9WgXcQ"), path)   # la segunda vez, el mismo archivo


@unittest.skipIf(WINDOWS, "./cine es de bash (en Windows lo hace cine.cmd: ver test_windows.py y humo_windows.py)")
class Arranque(unittest.TestCase):
    """./cine revisa lo que falta antes de arrancar (aquí con un «uname» de mentira que dice Linux)."""

    def correr(self, con_python=True, con_ffmpeg=False):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        bin_ = Path(tmp.name)
        (bin_ / "uname").write_text("#!/bin/sh\necho Linux\n")
        (bin_ / "apt-get").write_text("#!/bin/sh\nexit 0\n")
        for f in ("uname", "apt-get"):
            (bin_ / f).chmod(0o755)
        os.symlink(shutil.which("dirname"), bin_ / "dirname")
        if con_python:
            os.symlink(sys.executable, bin_ / "python3")
        if con_ffmpeg:
            for f in ("ffmpeg", "ffprobe"):
                (bin_ / f).write_text("#!/bin/sh\nexit 0\n")
                (bin_ / f).chmod(0o755)
        # «ayuda» no es un comando: el programa solo muestra cómo se usa (no busca el Roku ni el servidor).
        return subprocess.run(["/bin/bash", str(ROOT / "cine"), "ayuda"], capture_output=True, text=True,
                              env={"PATH": str(bin_), "HOME": tmp.name}, timeout=60)

    def test_sin_ffmpeg_dice_el_comando_de_apt(self):
        r = self.correr()
        self.assertEqual(r.returncode, 1)
        self.assertIn("Faltan programas que One TV necesita:", r.stdout)
        linea = next(l for l in r.stdout.splitlines() if "sudo apt" in l).strip()
        self.assertTrue(linea.startswith("sudo apt update && sudo apt install -y "))
        self.assertTrue(linea.endswith("ffmpeg"))

    def test_sin_python(self):
        r = self.correr(con_python=False)
        self.assertIn("sudo apt update && sudo apt install -y python3 python3-venv ffmpeg", r.stdout)

    def test_con_todo_arranca_el_programa(self):
        r = self.correr(con_ffmpeg=True)
        self.assertNotIn("Faltan programas", r.stdout)
        self.assertIn("Uso:", r.stderr)


if __name__ == "__main__":
    unittest.main()
