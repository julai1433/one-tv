# El servidor en Windows: carpetas (%LOCALAPPDATA% y las del usuario aunque estén en OneDrive), la tarea de arranque
# automático y su lanzador, el codificador (NVENC, Quick Sync, AMF), que no se duerma, pausar ffmpeg sin señales, los
# ffmpeg que quedaron vivos, los entornos aparte (Scripts\python.exe), nombres de archivo válidos y lo que dice
# «cine». Corren en cualquier sistema (lo de Windows se simula); las que necesitan Windows de verdad se saltan solas
# fuera de Windows. Sin red.
# python3 -m unittest discover -s pruebas -p "test_windows.py"
import importlib, io, json, os, re, subprocess, sys, tempfile, time, unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mac"))
import cine
import encoders
import hostos
import organizer
import server
import transcode
import windowsservice
import winapi

ROOT = Path(__file__).resolve().parent.parent
WINDOWS = sys.platform == "win32"
INVALIDOS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
RESERVADOS = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}


def nombre_valido_en_windows(nombre):
    """¿Se puede llamar así un archivo o carpeta en Windows?"""
    return (bool(nombre) and not INVALIDOS.search(nombre) and not nombre.endswith((".", " "))
            and nombre.split(".")[0].lower() not in RESERVADOS)


def corrida(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


class Carpetas(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)

    def en_windows(self, carpetas=None):
        """hostos como si esta computadora fuera Windows. carpetas: lo que «dice Windows» de Descargas, Videos y Música."""
        env = {"LOCALAPPDATA": str(self.home / "AppData" / "Local"), "ProgramFiles": str(self.home / "PF"),
               "ProgramFiles(x86)": str(self.home / "PF86"), "HOME": str(self.home), "USERPROFILE": str(self.home)}
        with mock.patch.dict(os.environ, env), mock.patch("sys.platform", "win32"):
            mod = importlib.reload(hostos)
        self.addCleanup(importlib.reload, hostos)   # al terminar, como era
        p = mock.patch.object(winapi, "user_folder", lambda kind: (carpetas or {}).get(kind))
        p.start()
        self.addCleanup(p.stop)
        return mod

    def test_todo_en_localappdata(self):
        h = self.en_windows()
        local = self.home / "AppData" / "Local" / "cine-roku"
        self.assertTrue(h.WINDOWS and not h.MAC)
        self.assertEqual((h.SERVICE_HOME, h.CACHE, h.LOG), (local, local / "Cache", local / "Logs" / "cine-roku.log"))
        self.assertEqual((h.SYSTEM, h.CINE, h.guide()), ("Windows", "cine", "docs/INSTALAR-WINDOWS.md"))

    def test_las_carpetas_del_usuario_las_dice_windows(self):
        onedrive = self.home / "OneDrive" / "Videos"
        h = self.en_windows({"VIDEOS": onedrive, "DOWNLOAD": self.home / "D" / "Descargas"})
        self.assertEqual(h.user_dir("VIDEOS"), onedrive)
        self.assertEqual(h.user_dir("DOWNLOAD"), self.home / "D" / "Descargas")
        with mock.patch.dict(os.environ, {"HOME": str(self.home), "USERPROFILE": str(self.home)}):
            self.assertEqual(h.user_dir("MUSIC"), self.home / "Music")   # si Windows no responde: la de siempre
        # La biblioteca que se sugiere va con la ruta completa (en Windows nadie escribe «~»).
        self.assertEqual(h.default_library(), str(onedrive / "Biblioteca"))
        self.assertEqual(h.tilde(self.home / "x"), str(self.home / "x"))

    def test_carpetas_conocidas_y_registro(self):
        visto = []
        onedrive, otro_disco = self.home / "OneDrive" / "Música", self.home / "D" / "Videos"   # (rutas completas)

        def conocida(guid):
            visto.append(guid)
            if guid.startswith("18989B1D"):
                raise OSError("no responde")
            return str(onedrive)

        def registro(nombre):
            return {"My Video": str(otro_disco)}.get(nombre)
        self.assertEqual(winapi.user_folder("MUSIC", conocida, registro), onedrive)
        # Si la carpeta conocida no responde, el registro (ya con %USERPROFILE% expandido).
        self.assertEqual(winapi.user_folder("VIDEOS", conocida, registro), otro_disco)
        self.assertIsNone(winapi.user_folder("DOWNLOAD", lambda g: None, lambda n: None))
        self.assertIsNone(winapi.user_folder("DOWNLOAD", lambda g: "relativa", lambda n: ""))
        self.assertEqual(visto[0], "4BD8D571-6D19-48D3-BE97-422220080E43")
        self.assertEqual(winapi.KNOWN_FOLDERS["VIDEOS"][1], "My Video")

    def test_programas(self):
        h = self.en_windows()
        pf = str(self.home / "PF")
        self.assertIn(str(Path(pf, "Google", "Chrome", "Application", "chrome.exe")), h.CHROME_PATHS)
        self.assertIn(str(Path(pf, "Microsoft", "Edge", "Application", "msedge.exe")), h.CHROME_PATHS)   # siempre está
        self.assertIn(str(self.home / "AppData" / "Local" / "BraveSoftware" / "Brave-Browser" / "Application" /
                          "brave.exe"), h.CHROME_PATHS)
        self.assertEqual(h.CHROME_PATHS.index(str(Path(pf, "Google", "Chrome", "Application", "chrome.exe"))), 0)
        self.assertIsNone(h.chrome_profile_parent(h.CHROME_PATHS[0]))
        self.assertIn(str(Path(pf, "Tailscale", "tailscale.exe")), h.TAILSCALE_PATHS)
        self.assertIsNone(h.keep_awake_command(900))
        self.assertEqual(h.install_hint("ffmpeg").split("   ")[0], "winget install -e --id Gyan.FFmpeg")

    def test_entornos_aparte_y_prioridad_baja(self):
        h = self.en_windows()
        self.assertEqual(h.venv_bin(Path("C:/x/ytdlp"), "yt-dlp"), Path("C:/x/ytdlp") / "Scripts" / "yt-dlp.exe")
        self.assertEqual(h.venv_bin(Path("C:/x/doblaje"), "python"), Path("C:/x/doblaje") / "Scripts" / "python.exe")
        self.assertEqual(h.low_priority(["py", Path("a.py"), 3]), ["py", str(Path("a.py")), "3"])   # sin «nice»
        self.assertEqual(h.LOW_PRIORITY, {"creationflags": 0x4000})   # BELOW_NORMAL_PRIORITY_CLASS

    @unittest.skipIf(WINDOWS, "lo de macOS y Linux")
    def test_en_macos_y_linux_queda_igual(self):
        self.assertEqual(hostos.venv_bin("/x", "pip"), Path("/x/bin/pip"))
        self.assertEqual(hostos.low_priority(["python", 1]), ["nice", "-n", "15", "python", "1"])
        self.assertEqual(hostos.LOW_PRIORITY, {})
        self.assertEqual(hostos.CINE, "./cine")

    def test_cine_usa_el_entorno_de_yt_dlp_de_este_sistema(self):
        self.assertEqual(cine.YTDLP, hostos.venv_bin(cine.YTDLP_ENV, "yt-dlp"))


class AnalisisConPrioridadBaja(unittest.TestCase):
    """Doblaje, «Saltar intro» y subtítulos con la voz: el mismo prefijo de prioridad baja (sin «nice» en Windows)."""

    def correr(self, windows, llamar):
        visto = {}

        def run(cmd, **kw):
            visto["cmd"], visto["kw"] = cmd, kw
            return corrida(0, json.dumps({"ok": True}) + "\n")
        prefijo = (lambda cmd: [str(c) for c in cmd]) if windows else (lambda cmd: ["nice", "-n", "15", *map(str, cmd)])
        with mock.patch("subprocess.run", run), mock.patch.object(hostos, "low_priority", prefijo), \
                mock.patch.object(hostos, "LOW_PRIORITY", {"creationflags": 0x4000} if windows else {}):
            llamar()
        return visto["cmd"], visto["kw"]

    def test_los_tres(self):
        import dubbing, intro, subsync
        doblaje = dubbing.Dubbing.__new__(dubbing.Dubbing)   # (sin arrancar sus hilos)
        doblaje.script = Path("dubsync.py")
        llamadas = {
            "intro": lambda: intro.run_introsync("py", "introsync.py", [("a.mkv", 1, 2, 60.0)]),
            "subsync": lambda: subsync.run_subsync("py", "voz.py", "a.mkv", 1, 2, ["a.srt"]),
            "doblaje": lambda: doblaje._dubsync("py", "analizar"),
        }
        for nombre, llamar in llamadas.items():
            cmd, kw = self.correr(True, llamar)
            self.assertEqual(cmd[0], "py", nombre)
            self.assertEqual(kw.get("creationflags"), 0x4000, nombre)
            cmd, kw = self.correr(False, llamar)
            self.assertEqual(cmd[:4], ["nice", "-n", "15", "py"], nombre)
            self.assertNotIn("creationflags", kw, nombre)


class NoDormirse(unittest.TestCase):
    def test_pide_y_suelta(self):
        llamadas = []
        awake = winapi.KeepAwake(seconds=0.3, set_state=llamadas.append)
        awake.poke()
        awake.poke()   # ya hay quien lo pida: no otro hilo
        hilo = awake.thread
        self.assertIsNotNone(hilo)
        hilo.join(5)
        self.assertEqual(llamadas, [winapi.ES_CONTINUOUS | winapi.ES_SYSTEM_REQUIRED, winapi.ES_CONTINUOUS])
        self.assertIsNone(awake.thread)
        awake.poke()   # otra vez, después de vencer
        awake.thread.join(5)
        self.assertEqual(len(llamadas), 4)

    def test_si_windows_no_deja_no_insiste(self):
        veces = []

        def no(flags):
            veces.append(flags)
            raise OSError("no")
        awake = winapi.KeepAwake(seconds=5, set_state=no)
        awake.poke()
        awake.thread.join(5) if awake.thread else None
        awake.poke()
        self.assertEqual(len(veces), 1)

    def test_el_servidor_usa_el_de_windows_alla(self):
        if WINDOWS:
            self.assertIs(server.KeepAwake, winapi.KeepAwake)
        else:
            self.assertIsNot(server.KeepAwake, winapi.KeepAwake)


class Procesos(unittest.TestCase):
    def test_pausar_en_windows_sin_senales(self):
        proc = mock.Mock(pid=4242)
        with mock.patch.object(hostos, "WINDOWS", True), mock.patch.object(winapi, "suspend") as suspend:
            hostos.pause_process(proc, True)
            hostos.pause_process(proc, False)
            hostos.pause_process(None, True)   # sin ffmpeg: nada
            suspend.side_effect = ProcessLookupError(4242)
            hostos.pause_process(proc, True)   # ya terminó: nada
        self.assertEqual([c.args for c in suspend.call_args_list], [(4242, True), (4242, False), (4242, True)])

    @unittest.skipIf(WINDOWS, "SIGSTOP y SIGCONT son de macOS y Linux")
    def test_pausar_en_macos_y_linux(self):
        import signal
        with mock.patch("os.kill") as kill:
            hostos.pause_process(mock.Mock(pid=7), True)
            hostos.pause_process(mock.Mock(pid=7), False)
        self.assertEqual([c.args for c in kill.call_args_list], [(7, signal.SIGSTOP), (7, signal.SIGCONT)])

    def test_la_sesion_pausa_y_sigue_con_nombres(self):
        s = transcode.Session.__new__(transcode.Session)
        s.proc = mock.Mock(pid=5)
        with mock.patch.object(hostos, "pause_process") as pause:
            s._signal("SIGSTOP")
            s._signal("SIGCONT")
        self.assertEqual([c.args[1] for c in pause.call_args_list], [True, False])

    def test_ffmpeg_que_quedaron_vivos_en_windows(self):
        carpeta = "C:\\Users\\ana\\AppData\\Local\\cine-roku\\Cache\\hls"
        llamadas = []

        def run(cmd, **kw):
            llamadas.append((cmd, kw))
            if cmd[0] == "tasklist":
                return corrida(0, hay)
            return corrida(0, b"")
        hay = "INFORMACIÓN: no hay tareas ejecutándose que coincidan.".encode("cp850")
        self.assertFalse(winapi.stop_processes_using(carpeta, run=run))
        self.assertEqual(len(llamadas), 1)   # sin ffmpeg corriendo, ni se le pregunta a PowerShell
        hay = b'"ffmpeg.exe","1234","Console","1","50.000 K"\r\n'
        self.assertTrue(winapi.stop_processes_using(carpeta, run=run))
        cmd, kw = llamadas[-1]
        self.assertEqual(cmd[0], "powershell")
        self.assertEqual(kw["env"]["ONE_TV_CARPETA"], carpeta)   # la carpeta va aparte: sin problemas de comillas
        self.assertIn("Stop-Process", cmd[-1])
        with mock.patch.object(hostos, "WINDOWS", True), mock.patch.object(winapi, "stop_processes_using") as stop:
            hostos.stop_leftovers(Path(carpeta))
        stop.assert_called_once_with(Path(carpeta))

    @unittest.skipIf(WINDOWS, "pkill es de macOS y Linux")
    def test_ffmpeg_que_quedaron_vivos_en_macos_y_linux(self):
        with mock.patch("subprocess.run") as run:
            hostos.stop_leftovers("/x/hls")
        self.assertEqual([c.args[0] for c in run.call_args_list],
                         [["pkill", "-CONT", "-f", "/x/hls"], ["pkill", "-TERM", "-f", "/x/hls"]])
        with mock.patch("subprocess.run", side_effect=FileNotFoundError("pkill")):
            hostos.stop_leftovers("/x/hls")   # sin pkill: no se cae


class Codificador(unittest.TestCase):
    def setUp(self):
        for p in (mock.patch.object(encoders, "MAC", False), mock.patch.object(encoders, "WINDOWS", True),
                  mock.patch.object(encoders, "render_nodes", return_value=[])):
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(setattr, encoders, "_current", None)
        self.logs = []

    def falso(self, conocidos, sirven, amf_idr=True):
        self.probados = []

        def run(cmd, **kw):
            if "-encoders" in cmd:
                return corrida(0, "Encoders:\n" + "".join(f" V....D {c}  algo\n" for c in conocidos))
            if "-h" in cmd:
                return corrida(0, "Encoder h264_amf\n  -quality <int>\n" + ("  -forced_idr <boolean>\n" if amf_idr else ""))
            codec = cmd[cmd.index("-c:v") + 1]
            self.probados.append(codec)
            return corrida(0 if codec in sirven else 1)
        return run

    def test_orden_nvidia_intel_amd(self):
        run = self.falso(["libx264", "h264_amf", "h264_qsv", "h264_nvenc", "h264_mf"], set())
        self.assertIs(encoders.detect("auto", self.logs.append, run), encoders.SOFTWARE)
        self.assertEqual(self.probados, ["h264_nvenc", "h264_qsv", "h264_amf"])
        self.assertIn("libx264", self.logs[-1])

    def test_amd(self):
        enc = encoders.detect("auto", self.logs.append, self.falso(["h264_amf", "h264_nvenc"], {"h264_amf"}))
        self.assertEqual(enc.name, "amf")
        self.assertIn("AMD (AMF)", self.logs[-1])
        self.assertEqual(enc.args[enc.args.index("-forced_idr") + 1], "1")
        # Un ffmpeg viejo sin esa opción para AMF: se usa igual, sin pedirla.
        viejo = encoders.detect("amf", self.logs.append, self.falso(["h264_amf"], {"h264_amf"}, amf_idr=False))
        self.assertEqual((viejo.name, "-forced_idr" in viejo.args), ("amf", False))

    def test_config_y_conversion(self):
        self.assertIn("amf", encoders.CHOICES)
        self.assertEqual(encoders.detect("qsv", self.logs.append, self.falso(["h264_qsv"], {"h264_qsv"})).name, "qsv")
        item = {"id": "a" * 12, "path": "C:\\Pelis\\a.mkv", "duration": 60, "full_title": "A",
                "info": {"video": {"index": 0, "codec": "hevc", "pix_fmt": "yuv420p10le", "width": 1920, "height": 1080},
                         "audio": [{"index": 1, "channels": 2}]}}
        with mock.patch("transcode.VIDEOTOOLBOX", False), \
                mock.patch.object(encoders, "_current", encoders.amf(self.falso([], set()))):
            cmd = transcode.FullPlan(item).command(1, 0, Path("hls"))
        self.assertEqual(cmd[cmd.index("-c:v") + 1], "h264_amf")
        self.assertNotIn("videotoolbox", " ".join(cmd))

    def test_en_linux_no_se_prueba_amf(self):
        with mock.patch.object(encoders, "WINDOWS", False):
            encoders.detect("auto", self.logs.append, self.falso(["h264_amf"], {"h264_amf"}))
        self.assertEqual(self.probados, [])


def xml_de_prueba(**kw):
    datos = {"pythonw": "C:\\Python312\\pythonw.exe", "launcher": "C:\\Users\\ana\\AppData\\Local\\cine-roku\\mac\\"
             "windowsservice.py", "home": "C:\\Users\\ana\\AppData\\Local\\cine-roku", "user": "PC-DE-ANA\\ana"}
    datos.update(kw)
    return windowsservice.task_xml(**datos)


class Tarea(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        for p in (mock.patch.object(windowsservice, "XML", self.dir / "tarea-windows.xml"),
                  mock.patch.object(windowsservice, "PIDFILE", self.dir / "servidor.pid")):
            p.start()
            self.addCleanup(p.stop)

    def test_la_tarea(self):
        import xml.dom.minidom
        texto = xml_de_prueba(home="C:\\Users\\R&B\\AppData\\Local\\cine-roku")
        doc = xml.dom.minidom.parseString(texto.replace('encoding="UTF-16"', 'encoding="UTF-8"').encode())
        val = lambda tag: doc.getElementsByTagName(tag)[0].firstChild.data  # noqa: E731
        self.assertEqual(val("UserId"), "PC-DE-ANA\\ana")   # solo esta cuenta: no pide administrador
        self.assertEqual(val("LogonType"), "InteractiveToken")   # sin guardar la contraseña
        self.assertEqual(val("RunLevel"), "LeastPrivilege")
        self.assertEqual(len(doc.getElementsByTagName("LogonTrigger")), 1)
        self.assertEqual(val("ExecutionTimeLimit"), "PT0S")   # sin límite (de fábrica, 3 días)
        self.assertEqual((val("DisallowStartIfOnBatteries"), val("StopIfGoingOnBatteries")), ("false", "false"))
        self.assertEqual(val("Priority"), "4")   # prioridad normal: convierte video en tiempo real
        self.assertEqual(val("MultipleInstancesPolicy"), "IgnoreNew")
        self.assertEqual(val("Command"), '"C:\\Python312\\pythonw.exe"')   # sin ventana
        self.assertTrue(val("Arguments").startswith("-X utf8 \""))
        self.assertTrue(val("Arguments").endswith('windowsservice.py" lanzar'))
        self.assertEqual(val("WorkingDirectory"), "C:\\Users\\R&B\\AppData\\Local\\cine-roku")   # «&» bien escrito

    def test_se_escribe_solo_si_cambia_y_en_utf16(self):
        log = self.dir / "Logs" / "cine-roku.log"
        with mock.patch.object(windowsservice, "_user", return_value="PC\\ana"):
            self.assertTrue(windowsservice.write("C:\\Python312\\python.exe", self.dir, log))
            self.assertFalse(windowsservice.write("C:\\Python312\\python.exe", self.dir, log))
            self.assertTrue(windowsservice.write("C:\\Python313\\python.exe", self.dir, log))
        raw = windowsservice.XML.read_bytes()
        self.assertEqual(raw[:2], b"\xff\xfe")   # UTF-16 con su marca: lo que pide schtasks
        self.assertIn("Python313", raw.decode("utf-16"))
        self.assertTrue(log.parent.is_dir() and windowsservice.installed())

    def test_pythonw(self):
        carpeta = self.dir / "Python312"
        carpeta.mkdir()
        (carpeta / "python.exe").write_bytes(b"")
        self.assertEqual(windowsservice.pythonw_for(carpeta / "python.exe"), str(carpeta / "python.exe"))
        (carpeta / "pythonw.exe").write_bytes(b"")
        self.assertEqual(windowsservice.pythonw_for(carpeta / "python.exe"), str(carpeta / "pythonw.exe"))

    def test_registrar_arrancar_detener_y_quitar(self):
        pedidos = []

        def schtasks(*args, timeout=60):
            pedidos.append(args[0])
            return corrida(0, "CORRECTO")
        with mock.patch.object(windowsservice, "schtasks", schtasks), mock.patch.object(windowsservice, "pid",
                                                                                       return_value=None):
            self.assertEqual(windowsservice.start(), "")
            windowsservice.restart()
            windowsservice.XML.write_text("x", encoding="utf-16")
            windowsservice.remove()
        self.assertEqual(pedidos, ["/Create", "/Run", "/End", "/Run", "/End", "/Delete"])
        self.assertFalse(windowsservice.XML.exists())
        with mock.patch.object(windowsservice, "schtasks",
                               lambda *a, **k: corrida(1, "", "ERROR: Acceso denegado.\r\n")):
            self.assertEqual(windowsservice.start(), "ERROR: Acceso denegado.")

    def test_pid(self):
        self.assertIsNone(windowsservice.pid())
        windowsservice.PIDFILE.write_text("4242")
        with mock.patch.object(winapi, "process_alive", return_value=True) as vivo:
            self.assertEqual(windowsservice.pid(), 4242)
        vivo.assert_called_once_with(4242)
        with mock.patch.object(winapi, "process_alive", return_value=False):
            self.assertIsNone(windowsservice.pid())
        windowsservice.PIDFILE.write_text("basura")
        self.assertIsNone(windowsservice.pid())

    def test_el_lanzador(self):
        log = self.dir / "Logs" / "cine-roku.log"
        pidfile = self.dir / "servidor.pid"
        vistos, esperas = [], []

        class Proc:
            pid = 777

            def wait(self):
                vistos.append(pidfile.read_text())   # mientras corre, el número está guardado
                return 1

        def popen(cmd, **kw):
            vistos.append((cmd, kw))
            return Proc()
        windowsservice.launch("C:\\Py\\python.exe", "C:\\x\\mac\\cine.py", "C:\\x", log, pidfile=pidfile,
                              popen=popen, sleep=esperas.append, rounds=2)
        (cmd, kw), guardado = vistos[0], vistos[1]
        self.assertEqual(cmd, ["C:\\Py\\python.exe", "-X", "utf8", "C:\\x\\mac\\cine.py", "servir"])
        self.assertEqual(kw["creationflags"], winapi.CREATE_NO_WINDOW)   # ni el servidor ni sus ffmpeg abren ventanas
        self.assertEqual((kw["cwd"], kw["env"]["PYTHONUTF8"], kw["env"]["PYTHONUNBUFFERED"]), ("C:\\x", "1", "1"))
        self.assertIs(kw["stderr"], subprocess.STDOUT)
        self.assertEqual(guardado, "777")
        self.assertFalse(pidfile.exists())   # terminó: ya no hay número
        self.assertEqual(esperas, [30, 30])   # vuelve a arrancar a los 30 s, como en Linux
        self.assertIn("vuelve a arrancar en 30 s", log.read_text(encoding="utf-8"))

        def no_arranca(cmd, **kw):
            raise FileNotFoundError("python.exe")
        windowsservice.launch("C:\\Py\\python.exe", "cine.py", ".", log, pidfile=pidfile, popen=no_arranca,
                              sleep=esperas.append, rounds=1)
        self.assertIn("No se pudo arrancar el servidor", log.read_text(encoding="utf-8"))


class ComandoCine(unittest.TestCase):
    """«cine autoarranque», «estado», «quitar-autoarranque» y «barra» en Windows (simulado)."""

    def setUp(self):
        for p in (mock.patch.object(cine.hostos, "MAC", False), mock.patch.object(cine.hostos, "WINDOWS", True),
                  mock.patch.object(cine.hostos, "SYSTEM", "Windows"), mock.patch.object(cine.hostos, "CINE", "cine")):
            p.start()
            self.addCleanup(p.stop)

    def test_autoarranque(self):
        llamadas = []
        with mock.patch.object(cine, "sync_service_files", lambda: llamadas.append("copiar")), \
                mock.patch.object(cine, "write_plist", lambda: llamadas.append("tarea")), \
                mock.patch.object(windowsservice, "problem", return_value=""), \
                mock.patch.object(windowsservice, "start", lambda: llamadas.append("arrancar") or ""), \
                mock.patch.object(cine.linuxservice, "lingering", side_effect=AssertionError("es de Linux")), \
                mock.patch.object(cine, "server_answers", return_value=None), redirect_stdout(io.StringIO()):
            cine.install_service({"puerto": 1})
        self.assertEqual(llamadas, ["copiar", "tarea", "arrancar"])
        with mock.patch.object(windowsservice, "start", return_value="Acceso denegado"), \
                mock.patch.object(windowsservice, "problem", return_value=""), \
                mock.patch.object(cine, "sync_service_files"), mock.patch.object(cine, "write_plist"), \
                mock.patch.object(cine, "server_answers", return_value=None):
            with self.assertRaises(SystemExit) as e:
                cine.install_service({"puerto": 1})
        self.assertIn("Windows no aceptó la tarea", str(e.exception))

    def test_la_tarea_con_el_python_que_corre_esto(self):
        with mock.patch.object(windowsservice, "write", return_value=True) as write:
            self.assertTrue(cine.write_plist())
        self.assertEqual(write.call_args.args, (sys.executable, cine.SERVICE_HOME, cine.SERVICE_LOG))

    def test_estado_y_quitar(self):
        st = {"items": 3, "roku": None, "server": "", "iphone": None}
        out = io.StringIO()
        with mock.patch.object(windowsservice, "installed", return_value=True), \
                mock.patch.object(windowsservice, "pid", return_value=99), \
                mock.patch.object(cine.linuxservice, "lingering", side_effect=AssertionError("es de Linux")), \
                mock.patch.object(cine, "tailscale_url", return_value=None), \
                mock.patch.object(cine.hostos, "lan_url", return_value=None), redirect_stdout(out):
            cine.print_status({"puerto": 8798}, st)
        self.assertIn("arranca solo cuando inicias sesión", out.getvalue())
        self.assertIn("corre cine tailscale", out.getvalue())
        out = io.StringIO()
        with mock.patch.object(sys, "argv", ["cine.py", "quitar-autoarranque"]), \
                mock.patch.object(cine, "load_config", return_value={"puerto": 1}), \
                mock.patch.object(windowsservice, "remove") as quitar, mock.patch("shutil.rmtree"), \
                mock.patch.object(Path, "unlink"), redirect_stdout(out):
            cine.main()
        quitar.assert_called_once()
        self.assertIn("abre cine cuando", out.getvalue())

    def test_la_barra_no_aplica(self):
        out = io.StringIO()
        with mock.patch.object(sys, "argv", ["cine.py", "barra"]), \
                mock.patch.object(cine, "load_config", return_value={"puerto": 1}), \
                mock.patch.object(cine, "install_menubar") as barra, redirect_stdout(out):
            cine.main()
        barra.assert_not_called()
        self.assertIn("solo para macOS: en Windows no aplica (usa cine estado)", out.getvalue())

    def test_config_con_bom_del_bloc_de_notas(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        conf = Path(tmp.name) / "config.json"
        conf.write_bytes(b"\xef\xbb\xbf" + json.dumps({"puerto": 8798, "carpetas": ["C:\\Películas"]},
                                                      ensure_ascii=False).encode("utf-8"))
        with mock.patch.object(cine, "CONFIG", conf):
            cfg = cine.load_config()
        self.assertEqual((cfg["puerto"], cfg["carpetas"]), (8798, ["C:\\Películas"]))


class NombresDeArchivo(unittest.TestCase):
    """Lo que el servidor crea en la caché y en la biblioteca: sin «:», «?» ni nada que Windows no acepte."""

    def test_los_de_la_cache(self):
        from library import show_key
        import hashlib
        vid, canal = "dQw4w9WgXcQ", "UCabc_DEF-123"
        item_id = hashlib.sha1("C:\\Películas\\Matrix (1999)\\Matrix.mkv".encode()).hexdigest()[:12]
        nombres = [f"{item_id}.jpg", f"{item_id}-e2.srt", f"{item_id}.json", f"yt-{vid}.jpg", f"yt-{vid}-hd.jpg",
                   f"qr-oscuro-{vid}.png", f"canal-{canal}.png", f".parcial-{vid}", "seg12.ts", "seg%d.ts",
                   f"serie-{show_key('Dr. House: M.D.?')}.jpg", f"live-{hashlib.sha1(b'x').hexdigest()[:10]}.jpg"]
        for client in ("192.0.2.7", "127.0.0.1", "::ffff:192.0.2.7"):   # la carpeta de cada aparato que mira
            nombres.append(f"{item_id}-1-{client.replace(':', '_').replace('.', '_')}")
        for n in nombres:
            self.assertTrue(nombre_valido_en_windows(n), n)

    def test_la_biblioteca_ordenada(self):
        raros = ['Misión: Imposible', 'AC/DC: "Live" at <River> | Plate?', "¿Qué pasó ayer?", "Ocean's Eleven...",
                 "Back\\slash *", "Star Wars: Episodio IV - Una nueva esperanza (1977) {imdb-tt0076759}"]
        with mock.patch.object(organizer.hostos, "WINDOWS", True):
            for t in raros:
                self.assertTrue(nombre_valido_en_windows(organizer.safe_name(t)), organizer.safe_name(t))
        with mock.patch.object(organizer.hostos, "WINDOWS", False):   # macOS y Linux: como antes
            self.assertEqual(organizer.safe_name('AC/DC: "Live" <x>'), 'AC-DC - "Live" <x>')


class Archivos(unittest.TestCase):
    """Corren en todos los sistemas; en Windows prueban lo que allá es distinto."""

    def test_reemplazar_y_borrar_lo_que_se_esta_mandando(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        d = Path(tmp.name)
        lista, nueva, trozo = d / "index.m3u8", d / "index.m3u8.tmp", d / "seg1.ts"
        lista.write_bytes(b"#EXTM3U\nvieja\n")
        trozo.write_bytes(b"x" * 1000)
        with hostos.open_shared(lista) as f, hostos.open_shared(trozo) as g:
            nueva.write_bytes(b"#EXTM3U\nnueva\n")
            os.replace(nueva, lista)   # lo que hace ffmpeg con su lista cada pocos segundos
            trozo.unlink()             # lo que hace transcode con los trozos ya vistos
            self.assertEqual(f.read(), b"#EXTM3U\nvieja\n")   # lo que se estaba mandando sigue entero
            self.assertEqual(len(g.read()), 1000)
        self.assertEqual(hostos.read_shared(lista), b"#EXTM3U\nnueva\n")
        with self.assertRaises(FileNotFoundError):
            hostos.open_shared(d / "no-existe.ts")

    def test_un_solo_servidor_por_puerto(self):
        uno = server.Server(("127.0.0.1", 0), server.BaseHTTPRequestHandler)
        self.addCleanup(uno.server_close)
        with self.assertRaises(OSError):   # en Windows, sin el puerto en exclusiva, este también «funcionaría»
            server.Server(("127.0.0.1", uno.server_address[1]), server.BaseHTTPRequestHandler).server_close()


@unittest.skipUnless(WINDOWS, "solo en Windows de verdad")
class EnWindowsDeVerdad(unittest.TestCase):
    def test_carpetas(self):
        for kind in ("DOWNLOAD", "VIDEOS", "MUSIC"):
            p = winapi.user_folder(kind)
            self.assertTrue(p is not None and p.is_absolute(), kind)
            self.assertEqual(hostos.user_dir(kind), p)
        self.assertTrue(str(hostos.SERVICE_HOME).startswith(os.environ["LOCALAPPDATA"]))

    def test_no_dormirse(self):
        self.assertNotEqual(winapi._set_execution_state(winapi.ES_CONTINUOUS | winapi.ES_SYSTEM_REQUIRED), None)
        winapi._set_execution_state(winapi.ES_CONTINUOUS)

    def test_pausar_y_seguir(self):
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        self.addCleanup(proc.kill)
        self.assertTrue(winapi.process_alive(proc.pid))
        winapi.suspend(proc.pid, True)
        winapi.suspend(proc.pid, False)
        self.assertIsNone(proc.poll())
        proc.kill()
        proc.wait()
        self.assertFalse(winapi.process_alive(proc.pid))
        self.assertTrue(winapi.process_alive(os.getpid()))
        self.assertFalse(winapi.process_alive(os.getpid(), prefix="ffmpeg"))

    def test_un_solo_lanzador(self):
        nombre = f"Local\\OneTV-prueba-{os.getpid()}"
        primero = winapi.single_instance(nombre)
        self.assertIsNotNone(primero)
        self.assertIsNone(winapi.single_instance(nombre))

    def test_los_hijos_se_cierran_con_el_lanzador(self):
        """Lo que hace el lanzador de la tarea: si muere, Windows cierra al servidor (aquí, un proceso que duerme)."""
        codigo = ("import os, subprocess, sys, time; sys.path.insert(0, sys.argv[1]); import winapi; "
                  "assert winapi.kill_children_with_me(); "
                  "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)']); "
                  "print(p.pid, flush=True); time.sleep(1); os._exit(0)")
        r = subprocess.run([sys.executable, "-c", codigo, str(ROOT / "mac")], capture_output=True, text=True,
                           timeout=60)
        hijo = int(r.stdout.split()[0])
        fin = time.time() + 10
        while winapi.process_alive(hijo) and time.time() < fin:
            time.sleep(0.2)
        self.assertFalse(winapi.process_alive(hijo))

    @unittest.skipUnless(subprocess.run(["where", "ffmpeg"], capture_output=True).returncode == 0 if WINDOWS else False,
                         "hace falta ffmpeg")
    def test_detener_ffmpeg_que_quedo_vivo(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        marca = Path(tmp.name) / f"hls-{os.getpid()}"
        marca.mkdir()
        proc = subprocess.Popen(["ffmpeg", "-nostdin", "-loglevel", "error", "-re", "-f", "lavfi", "-i",
                                 "testsrc2=size=64x64:rate=5", "-f", "segment", "-segment_time", "1",
                                 str(marca / "seg%d.ts")], stdin=subprocess.DEVNULL)
        self.addCleanup(lambda: proc.poll() is None and proc.kill())
        time.sleep(2)
        self.assertTrue(hostos.stop_leftovers(marca) is None)
        self.assertIsNotNone(proc.wait(timeout=30))

    def test_utf8(self):
        self.assertEqual(sys.flags.utf8_mode, 1, "las pruebas corren con PYTHONUTF8=1, como el servidor")


if __name__ == "__main__":
    unittest.main()
