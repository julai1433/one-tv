# El primer arranque sin preguntas y la bienvenida: ./cine sin config.json crea lo básico sin preguntar nada y manda a
# /bienvenida (el asistente del navegador); la página principal manda ahí hasta que se termina; «cine instalador» deja
# el arranque automático (o, en las pruebas, el servidor de fondo) y abre el navegador; la copia del servicio no pisa
# lo que se guardó desde el navegador; el servicio usa el Python y el ffmpeg que el instalador bajó para One TV. Sin
# red ni TV.
# python3 -m unittest discover -s pruebas -p "test_bienvenida.py"
import http.client, io, json, os, plistlib, sys, tempfile, threading, time, unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mac"))
import cine
from server import serve


class PrimerArranque(unittest.TestCase):
    """./cine sin config.json: lo básico sin preguntar nada, y la bienvenida en el navegador."""

    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.dir = Path(self._t.name)
        self.conf = self.dir / "config.json"
        self.biblio = self.dir / "Movies" / "Biblioteca"
        for p in (mock.patch.object(cine, "CONFIG", self.conf),
                  mock.patch.object(cine, "SERVICE_HOME", self.dir / "sin-servidor"),
                  mock.patch.object(cine.hostos, "default_library", return_value=str(self.biblio)),
                  mock.patch("builtins.input", side_effect=AssertionError("no debe preguntar nada"))):
            p.start()
            self.addCleanup(p.stop)

    def test_sin_config_no_pregunta_y_crea_lo_basico(self):
        out = io.StringIO()
        with mock.patch.dict(os.environ, {"ONE_TV_PUERTO": "8803"}), \
                mock.patch.object(sys, "argv", ["cine.py", "permitir-red"]), \
                mock.patch.object(cine.hostos, "WINDOWS", False), redirect_stdout(out):
            cine.main()
        cfg = json.loads(self.conf.read_text())
        self.assertIs(cfg["bienvenida_hecha"], False)
        self.assertEqual(cfg["puerto"], 8803)
        self.assertEqual(cfg["carpetas"], [str(self.biblio)])
        self.assertNotIn("musica", cfg)   # sin «musica»: la sección la encuentra sola (mac/music.py)
        self.assertNotIn("solo_leer", cfg)
        self.assertTrue(self.biblio.is_dir())
        if os.name != "nt":
            self.assertEqual(self.conf.stat().st_mode & 0o777, 0o600)
        self.assertIn("http://localhost:8803/bienvenida", out.getvalue())
        self.assertIn("configurar", out.getvalue())

    def test_si_ya_habia_un_servidor_usa_su_configuracion(self):
        # One TV ya arrancaba solo desde otra carpeta (una copia con git, antes del instalador): no se empieza de cero
        # (al poner al día el servicio, la de cero pisaría la de verdad).
        servicio = self.dir / "servicio"
        servicio.mkdir()
        (servicio / "config.json").write_text(json.dumps({"puerto": 8765, "roku_password": "la-de-siempre"}))
        out = io.StringIO()
        with mock.patch.object(cine, "SERVICE_HOME", servicio), redirect_stdout(out):
            cfg = cine.create_config_quietly()
        self.assertEqual(cfg["roku_password"], "la-de-siempre")
        self.assertEqual(json.loads(self.conf.read_text())["roku_password"], "la-de-siempre")
        self.assertNotIn("bienvenida_hecha", cfg)   # ya estaba configurado: nada de bienvenida
        self.assertIn("Uso la configuración que ya tenía One TV", out.getvalue())
        self.assertFalse(self.biblio.exists())

    def test_una_carpeta_con_videos_de_otro_programa_solo_se_lee(self):
        (self.biblio / "Una película (2001)").mkdir(parents=True)
        (self.biblio / "Una película (2001)" / "Una película (2001).mkv").write_bytes(b"\0" * 10)
        with mock.patch.object(cine, "looks_like_one_tv", return_value=False):
            cfg = cine.default_config()
        self.assertEqual(cfg["solo_leer"], {str(self.biblio): True})

    def test_configurar_en_la_terminal_cuenta_como_bienvenida_hecha(self):
        respuestas = iter([str(self.biblio), "", "192.0.2.10", "no"])
        with mock.patch("builtins.input", lambda *_: next(respuestas)), redirect_stdout(io.StringIO()):
            cine.configure_first_time()
        cfg = json.loads(self.conf.read_text())
        self.assertIs(cfg["bienvenida_hecha"], True)
        self.assertEqual(cfg["roku_ip"], "192.0.2.10")

    def test_guardar_cambia_solo_lo_pedido(self):
        self.conf.write_text(json.dumps({"puerto": 8765, "roku_password": "x", "bienvenida_hecha": False}))
        cine.save_config({"bienvenida_hecha": True})
        self.assertEqual(json.loads(self.conf.read_text()),
                         {"puerto": 8765, "roku_password": "x", "bienvenida_hecha": True})
        self.assertEqual(list(self.dir.glob("*.nuevo")), [])

    def test_a_donde_abrir(self):
        self.assertEqual(cine.welcome_url({"puerto": 8765, "bienvenida_hecha": False}),
                         "http://localhost:8765/bienvenida")
        self.assertEqual(cine.welcome_url({"puerto": 8765, "bienvenida_hecha": True}), "http://localhost:8765")
        self.assertEqual(cine.welcome_url({"puerto": 8765}), "http://localhost:8765")   # instalaciones de antes


class AppDePrueba:
    welcome_pending = cine.App.welcome_pending
    welcome_done = cine.App.welcome_done
    status = cine.App.status
    computer_name = cine.App.computer_name
    unreadable_folders = cine.App.unreadable_folders
    tv_state = cine.App.tv_state

    def __init__(self, cfg):
        self.cfg = cfg
        self.roku = None
        self.server_url = ""
        self.library = SimpleNamespace(items={})
        self.iphone_url = None
        self.queue = SimpleNamespace(items=lambda: [])
        self.dubbing = SimpleNamespace(current=None)
        self.network_blocked = False

    def playing(self):
        return None


class Bienvenida(unittest.TestCase):
    """/bienvenida, la página principal que manda ahí la primera vez y el botón que lo termina."""

    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.conf = Path(self._t.name) / "config.json"
        p = mock.patch.object(cine, "CONFIG", self.conf)
        p.start()
        self.addCleanup(p.stop)

    def servidor(self, cfg):
        self.conf.write_text(json.dumps(cfg))
        app = AppDePrueba(dict(cfg))
        httpd = serve(app, 0, "127.0.0.1")
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        return app, httpd.server_address[1]

    def pedir(self, port, metodo, ruta, cuerpo=None, tipo="application/json"):
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        headers = {"Content-Type": tipo} if cuerpo is not None else {}
        c.request(metodo, ruta, body=json.dumps(cuerpo) if cuerpo is not None else None, headers=headers)
        r = c.getresponse()
        datos = r.read()
        c.close()
        return r.status, r.getheader("Location"), datos

    def test_la_primera_vez_manda_a_la_bienvenida_hasta_terminarla(self):
        app, port = self.servidor({"puerto": 8765, "roku_password": "x", "bienvenida_hecha": False})
        status, donde, _ = self.pedir(port, "GET", "/")
        self.assertEqual((status, donde), (302, "/bienvenida"))
        status, _, html = self.pedir(port, "GET", "/bienvenida")
        self.assertEqual(status, 200)
        self.assertIn("Bienvenido a One TV", html.decode())
        self.assertIn("/api/bienvenida", html.decode())
        self.assertEqual(self.pedir(port, "GET", "/index.html")[0], 200)   # la principal, si alguien la pide directo
        st = json.loads(self.pedir(port, "GET", "/api/status")[2])
        self.assertIs(st["bienvenida_pendiente"], True)
        self.assertIs(st["red_bloqueada"], False)
        # Una página de otro sitio no puede marcarla (solo JSON, como todas las órdenes).
        self.assertEqual(self.pedir(port, "POST", "/api/bienvenida", {"hecha": True}, "text/plain")[0], 415)
        status, _, datos = self.pedir(port, "POST", "/api/bienvenida", {"hecha": True})
        self.assertEqual(json.loads(datos), {"ok": True, "pendiente": False})
        self.assertEqual(json.loads(self.conf.read_text()),
                         {"puerto": 8765, "roku_password": "x", "bienvenida_hecha": True})   # lo demás, igual
        self.assertEqual(self.pedir(port, "GET", "/")[0], 200)
        self.assertIs(json.loads(self.pedir(port, "GET", "/api/status")[2])["bienvenida_pendiente"], False)

    def test_las_instalaciones_de_antes_no_ven_la_bienvenida(self):
        _, port = self.servidor({"puerto": 8765})
        self.assertEqual(self.pedir(port, "GET", "/")[0], 200)
        self.assertEqual(self.pedir(port, "GET", "/bienvenida/")[0], 200)   # pero la página existe

    def test_la_red_bloqueada_se_ve_en_el_estado(self):
        app, port = self.servidor({"puerto": 8765})
        app.network_blocked = True
        self.assertIs(json.loads(self.pedir(port, "GET", "/api/status")[2])["red_bloqueada"], True)


class CopiaDelServicio(unittest.TestCase):
    """El servicio corre una copia del programa y de config.json: lo que se guardó desde el navegador no se pierde."""

    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        d = Path(self._t.name)
        self.proyecto, self.servicio = d / "One TV", d / "servicio"
        for sub in ("mac", "roku"):
            (self.proyecto / sub).mkdir(parents=True)
            (self.proyecto / sub / "a.txt").write_text(sub)
        self.conf = self.proyecto / "config.json"
        for p in (mock.patch.object(cine, "PROJECT", self.proyecto), mock.patch.object(cine, "CONFIG", self.conf),
                  mock.patch.object(cine, "SERVICE_HOME", self.servicio)):
            p.start()
            self.addCleanup(p.stop)

    def escribir(self, path, cfg, hace):
        path.write_text(json.dumps(cfg))
        t = time.time() - hace
        os.utime(path, (t, t))

    def test_lo_mas_nuevo_gana(self):
        self.escribir(self.conf, {"bienvenida_hecha": False}, 100)
        self.assertTrue(cine.sync_service_files())
        suya = self.servicio / "config.json"
        self.assertEqual(json.loads(suya.read_text()), {"bienvenida_hecha": False})
        # El navegador terminó la bienvenida (el servidor escribió su copia): se trae al proyecto, sin reiniciar.
        self.escribir(suya, {"bienvenida_hecha": True, "roku_password": "nueva"}, 10)
        self.assertFalse(cine.sync_service_files())
        self.assertEqual(json.loads(self.conf.read_text()), {"bienvenida_hecha": True, "roku_password": "nueva"})
        # Después alguien cambia config.json a mano: esa gana y el servicio se reinicia.
        self.escribir(self.conf, {"bienvenida_hecha": True, "roku_password": "otra"}, 0)
        self.assertTrue(cine.sync_service_files())
        self.assertEqual(json.loads(suya.read_text())["roku_password"], "otra")


class ServicioConLoPropio(unittest.TestCase):
    """El servicio de fondo usa el Python y el ffmpeg que el instalador bajó para One TV."""

    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.dir = Path(self._t.name)
        self.programas = self.dir / "programas"
        p = mock.patch.object(cine, "PROGRAMS", self.programas)
        p.start()
        self.addCleanup(p.stop)

    def test_el_path_empieza_por_programas_bin(self):
        self.assertEqual(cine.service_path("/usr/bin:/bin"), "/usr/bin:/bin")   # sin programas/bin: igual
        (self.programas / "bin").mkdir(parents=True)
        propio = str(self.programas / "bin")
        self.assertEqual(cine.service_path("/usr/bin:/bin"), f"{propio}{os.pathsep}/usr/bin:/bin")
        self.assertEqual(cine.service_path(f"{propio}{os.pathsep}/bin"), f"{propio}{os.pathsep}/bin")   # sin repetir

    def test_el_python(self):
        with mock.patch.object(cine, "own_python", return_value=True), mock.patch("shutil.which", return_value="/x"):
            self.assertEqual(cine.service_python(), sys.executable)
        # «python3» del PATH que es otro (el de la Mac sin Xcode): el que corre esto
        with mock.patch.object(cine, "own_python", return_value=False), \
                mock.patch("shutil.which", return_value=str(self.dir / "otro-python3")):
            self.assertEqual(cine.service_python(), sys.executable)
        enlace = self.dir / "python3"   # el mismo Python con otra ruta (Homebrew): esa ruta, que no cambia
        try:
            enlace.symlink_to(sys.executable)
        except (OSError, NotImplementedError):
            self.skipTest("sin enlaces simbólicos")
        with mock.patch.object(cine, "own_python", return_value=False), mock.patch("shutil.which", return_value=str(enlace)):
            self.assertEqual(cine.service_python(), str(enlace))

    def test_launchd_con_lo_propio(self):
        (self.programas / "bin").mkdir(parents=True)
        plist = self.dir / "LaunchAgents" / "local.cine-roku.plist"
        with mock.patch.object(cine.hostos, "MAC", True), mock.patch.object(cine.hostos, "WINDOWS", False), \
                mock.patch.object(cine, "SERVICE_PLIST", plist), mock.patch.object(cine, "SERVICE_LOG", self.dir / "x.log"), \
                mock.patch.object(cine, "service_python", return_value="/One TV/programas/python/bin/python3"):
            self.assertTrue(cine.write_plist())
        datos = plistlib.loads(plist.read_bytes())
        self.assertEqual(datos["ProgramArguments"][0], "/One TV/programas/python/bin/python3")
        self.assertTrue(datos["EnvironmentVariables"]["PATH"].startswith(str(self.programas / "bin") + os.pathsep))
        self.assertIn("/opt/homebrew/bin", datos["EnvironmentVariables"]["PATH"])


class ServidorDeFondo(unittest.TestCase):
    """El servidor que queda de fondo sin arranque automático: al ponerlo al día se cambia por el nuevo, y solo si
    el número guardado es de verdad un servidor de One TV (sin «ps», que no siempre se puede usar)."""

    @unittest.skipIf(os.name == "nt", "en Windows se pregunta de otra forma (winapi)")
    def test_como_se_arranco_un_proceso(self):
        import subprocess
        p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(20)", "cine.py", "servir"],
                             env={**os.environ, "SECRETO_DE_PRUEBA": "no-debe-salir"})
        self.addCleanup(p.kill)
        time.sleep(0.5)
        linea = cine.hostos.command_line(p.pid)
        self.assertTrue(linea.endswith("cine.py servir"), linea)
        self.assertNotIn("SECRETO_DE_PRUEBA", linea)   # solo los argumentos, nunca el entorno
        self.assertTrue(cine._is_our_server(p.pid))
        self.assertFalse(cine._is_our_server(os.getpid()))
        self.assertEqual(cine.hostos.command_line(2 ** 22 + 12345), "")


class LoUltimoDelInstalador(unittest.TestCase):
    """«cine instalador»: arranque automático (o de fondo, en las pruebas) y la bienvenida en el navegador."""

    def correr(self, cfg, env, **parches):
        llamadas = []
        out = io.StringIO()
        base = {"start_detached": lambda c: llamadas.append("de-fondo"),
                "install_service": lambda c: llamadas.append("autoarranque"),
                "update_service": lambda c: llamadas.append("al-dia"),
                "service_installed": lambda: False,
                "wait_for_server": lambda port, seconds=0: {"items": 0},
                "load_config": lambda: cfg,
                "open_network": lambda c, say=print: llamadas.append("red") or True}
        base.update(parches)
        with mock.patch.dict(os.environ, env), mock.patch.object(cine.hostos, "lan_url", return_value="http://192.0.2.7:8765"), \
                mock.patch.object(cine.hostos, "open_browser", lambda url: llamadas.append(url) or True), \
                redirect_stdout(out):
            with mock.patch.multiple(cine, **base):
                cine.finish_install(cfg)
        return llamadas, out.getvalue()

    def test_en_las_pruebas_nunca_un_servicio_de_verdad(self):
        cfg = {"puerto": 8765, "bienvenida_hecha": False}
        llamadas, out = self.correr(cfg, {"ONE_TV_SIN_AUTOARRANQUE": "1", "CINE_NO_BROWSER": ""})
        self.assertEqual(llamadas, ["red", "de-fondo", "http://localhost:8765/bienvenida"])
        self.assertIn("http://192.0.2.7:8765/bienvenida", out)
        self.assertIn("hasta que apagues la computadora", out)

    def test_instala_o_pone_al_dia_el_arranque_automatico(self):
        cfg = {"puerto": 8765, "bienvenida_hecha": True}
        with mock.patch.object(cine.hostos, "MAC", True), mock.patch.object(cine.hostos, "WINDOWS", False):
            llamadas, out = self.correr(cfg, {"ONE_TV_SIN_AUTOARRANQUE": "", "CINE_NO_BROWSER": ""})
            self.assertEqual(llamadas, ["red", "autoarranque", "http://localhost:8765"])
            self.assertIn("arranca solo con la computadora", out)
            llamadas, _ = self.correr(cfg, {"ONE_TV_SIN_AUTOARRANQUE": "", "CINE_NO_BROWSER": "1"},
                                      service_installed=lambda: True)
            self.assertEqual(llamadas, ["red", "al-dia"])   # sin abrir el navegador

    def test_linux_sin_systemd_queda_de_fondo(self):
        cfg = {"puerto": 8765, "bienvenida_hecha": False}
        with mock.patch.object(cine.hostos, "MAC", False), mock.patch.object(cine.hostos, "WINDOWS", False), \
                mock.patch.object(cine.linuxservice, "problem", return_value="Esta computadora no usa systemd."):
            llamadas, out = self.correr(cfg, {"ONE_TV_SIN_AUTOARRANQUE": "", "CINE_NO_BROWSER": ""},
                                        **{"say": print})
        self.assertEqual(llamadas[:2], ["red", "de-fondo"])
        self.assertIn("no usa systemd", out)

    def test_si_no_arranca_dice_donde_mirar(self):
        with self.assertRaises(SystemExit) as e:
            self.correr({"puerto": 8765}, {"ONE_TV_SIN_AUTOARRANQUE": "1"}, wait_for_server=lambda port, seconds=0: None)
        self.assertIn("registro", str(e.exception))


if __name__ == "__main__":
    unittest.main()
