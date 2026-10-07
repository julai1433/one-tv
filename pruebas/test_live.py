# Pruebas sin red ni Chrome de los canales en vivo (mac/live.py): cambiar el nombre, nombres repetidos,
# mensajes cuando no hay video, el enlace completo en el registro y la ruta POST /api/live/rename.
# Uso: python3 -m unittest discover -s pruebas -p 'test_live.py'
import json, sys, tempfile, threading, time, unittest, urllib.error, urllib.request
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mac"))
import cine
import live
import server
from live import LiveChannels, LiveError, NAME_MAX


class Base(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.tmp = Path(self._t.name)
        self.live = self.canales()

    def tearDown(self):
        self._t.cleanup()

    def canales(self):
        """Canales sobre la carpeta de prueba, con un «Chrome» falso: la página siempre tiene video."""
        ch = LiveChannels(self.tmp / "datos", self.tmp / "cache")
        ch.chrome = "/chrome/de/prueba"
        ch.titles = {}   # enlace -> título de la página
        ch._resolve = lambda url: {"url": url + "/index.m3u8", "headers": {}, "poster": None,
                                   "title": ch.titles.get(url, "Eventos HD En Vivo | Rojadirecta")}
        return ch

    def guardados(self):
        return json.loads((self.tmp / "datos" / "canales.json").read_text())


class CambiarNombre(Base):
    def setUp(self):
        super().setUp()
        self.cid = self.live.add("https://ejemplo.com/evento")["id"]

    def test_recorta_espacios_y_se_guarda(self):
        c = self.live.rename(self.cid, "   Liga MX  ")
        self.assertEqual(c["name"], "Liga MX")
        self.assertEqual(self.guardados()[0]["name"], "Liga MX")
        self.assertEqual(self.canales().get(self.cid)["name"], "Liga MX")   # sobrevive a reiniciar
        self.assertEqual(self.live.public()[0]["name"], "Liga MX")           # lo que ven la TV y la web

    def test_vacio_no_se_acepta(self):
        for name in ("", "   ", None):
            with self.assertRaisesRegex(LiveError, "Escribe un nombre"):
                self.live.rename(self.cid, name)
        self.assertEqual(self.live.get(self.cid)["name"], "Eventos HD En Vivo | Rojadirecta")

    def test_hasta_80_caracteres(self):
        self.assertEqual(self.live.rename(self.cid, "x" * NAME_MAX)["name"], "x" * NAME_MAX)
        self.assertEqual(self.live.rename(self.cid, " " + "y" * NAME_MAX + " ")["name"], "y" * NAME_MAX)
        with self.assertRaisesRegex(LiveError, "muy largo"):
            self.live.rename(self.cid, "z" * (NAME_MAX + 1))
        self.assertEqual(self.live.get(self.cid)["name"], "y" * NAME_MAX)

    def test_canal_que_no_existe(self):
        with self.assertRaisesRegex(LiveError, "ya no existe"):
            self.live.rename("no-existe", "Algo")

    def test_volver_a_agregar_el_mismo_enlace_conserva_el_nombre(self):
        self.live.rename(self.cid, "Mi canal")
        self.assertEqual(self.live.add("https://ejemplo.com/evento")["name"], "Mi canal")
        self.assertEqual(len(self.live.public()), 1)


class NombreRepetido(Base):
    def test_sin_nombre_y_titulo_ya_usado_agrega_2_3(self):
        a = self.live.add("https://ejemplo.com/uno")
        b = self.live.add("https://ejemplo.com/dos")
        c = self.live.add("https://ejemplo.com/tres")
        self.assertEqual([a["name"], b["name"], c["name"]],
                         ["Eventos HD En Vivo | Rojadirecta", "Eventos HD En Vivo | Rojadirecta 2",
                          "Eventos HD En Vivo | Rojadirecta 3"])

    def test_sin_distinguir_mayusculas_y_llenando_huecos(self):
        self.live.titles = {"https://a.com/1": "Partido", "https://a.com/2": "PARTIDO", "https://a.com/3": "Partido"}
        self.assertEqual(self.live.add("https://a.com/1")["name"], "Partido")
        self.assertEqual(self.live.add("https://a.com/2")["name"], "PARTIDO 2")
        self.live.rename(self.live.public()[0]["id"], "Otro")   # «PARTIDO 2» cambia de nombre: queda libre
        self.assertEqual(self.live.add("https://a.com/3")["name"], "Partido 2")

    def test_el_nombre_escrito_gana_aunque_se_repita(self):
        self.live.add("https://ejemplo.com/uno")
        c = self.live.add("https://ejemplo.com/dos", "  Eventos HD En Vivo | Rojadirecta ")
        self.assertEqual(c["name"], "Eventos HD En Vivo | Rojadirecta")

    def test_titulo_largo_con_numero_no_pasa_de_80(self):
        self.live.titles = {"https://a.com/1": "t" * 120, "https://a.com/2": "t" * 120}
        self.assertEqual(self.live.add("https://a.com/1")["name"], "t" * NAME_MAX)
        name = self.live.add("https://a.com/2")["name"]
        self.assertEqual(len(name), NAME_MAX)
        self.assertTrue(name.endswith(" 2"))

    def test_nombre_escrito_largo_se_recorta(self):
        self.assertEqual(len(self.live.add("https://a.com/1", "n" * 200)["name"]), NAME_MAX)


class Enlaces(Base):
    def test_enlace_invalido(self):
        for url in ("", "hola", "ftp://x.com", "https://"):
            with self.assertRaisesRegex(LiveError, "http:// o https://"):
                self.live.add(url)

    def test_sin_chrome_lo_dice_con_la_computadora(self):
        self.live.chrome = None
        with self.assertRaisesRegex(LiveError, "instalado en la computadora"):
            self.live.add("https://ejemplo.com/evento")

    def test_el_mismo_enlace_no_se_busca_dos_veces_a_la_vez(self):
        started, release, errors = threading.Event(), threading.Event(), []

        def slow(url):
            started.set()
            release.wait(5)
            return {"url": url + "/i.m3u8", "headers": {}, "poster": None, "title": "Evento"}
        self.live._resolve = slow
        t = threading.Thread(target=lambda: self.live.add("https://ejemplo.com/evento"))
        t.start()
        started.wait(5)
        try:
            self.live.add("https://ejemplo.com/evento")
        except LiveError as e:
            errors.append(str(e))
        release.set()
        t.join(5)
        self.assertEqual(len(errors), 1)
        self.assertIn("Ya se está buscando", errors[0])
        self.assertEqual(len(self.live.public()), 1)
        self.assertEqual(self.live.add("https://ejemplo.com/evento")["name"], "Evento")   # ya terminó: se puede otra vez


class CDPFalso:
    """Chrome de mentira: la página navega (o no) y manda las peticiones que se le den."""

    def __init__(self, nav=None, events=()):
        self.nav, self.events = nav or {}, list(events)

    def call(self, method, params=None, session=None, timeout=15):
        return {"Target.createTarget": {"targetId": "t1"}, "Target.attachToTarget": {"sessionId": "s1"},
                "Page.navigate": self.nav}.get(method, {})

    def send(self, *args, **kwargs):
        return 1

    def event(self, timeout):
        time.sleep(0.01)
        return self.events.pop(0) if self.events else None


class MensajesSinVideo(unittest.TestCase):
    def test_sin_video_sugiere_volver_cuando_este_al_aire(self):
        with self.assertRaises(LiveError) as e:
            live._watch_page(CDPFalso(), "https://ejemplo.com/evento", 0.2)
        self.assertEqual(str(e.exception), "No encontré un video en esa página. Si el evento aún no empieza, "
                                           "vuelve a intentarlo cuando esté al aire.")

    def test_video_bloqueado_por_la_fuente(self):
        req = {"method": "Network.requestWillBeSent",
               "params": {"requestId": "1", "request": {"url": "https://cdn.x/live.m3u8", "headers": {}}}}
        original = live.fetch
        live.fetch = lambda *a, **k: (_ for _ in ()).throw(urllib.error.URLError("403"))
        try:
            with self.assertRaises(LiveError) as e:
                live._watch_page(CDPFalso(events=[req]), "https://ejemplo.com/evento", 0.2)
        finally:
            live.fetch = original
        self.assertIn("la fuente no deja reproducirlo fuera de su página", str(e.exception))
        self.assertIn("https://cdn.x/live.m3u8", e.exception.detail)

    def test_pagina_que_no_abre(self):
        with self.assertRaises(LiveError) as e:
            live._watch_page(CDPFalso(nav={"errorText": "net::ERR_NAME_NOT_RESOLVED"}), "https://no.existe", 5)
        self.assertIn("No se pudo abrir esa página", str(e.exception))
        self.assertEqual(e.exception.detail, "net::ERR_NAME_NOT_RESOLVED")


class RegistroConEnlaceCompleto(unittest.TestCase):
    def test_al_fallar_se_anota_el_enlace_entero(self):
        url = "https://rojadirectauno.pl/eventoshd.php?r=" + "aHR0cHM6Ly9wbGF5dmkub3JnL2xpZ2FteDIucGhw" * 3

        class Canales:
            def add(self, u, name=""):
                raise LiveError(live.NO_VIDEO, "sin listas HLS en 45 s")
        lines, say = [], cine.say
        cine.say = lines.append
        try:
            r = cine.App.live_add(SimpleNamespace(live=Canales()), url)
        finally:
            cine.say = say
        self.assertEqual(r, {"ok": False, "error": live.NO_VIDEO})
        self.assertIn(url, lines[-1])
        self.assertIn("sin listas HLS", lines[-1])
        self.assertGreater(len(url), 80)


class RutaRename(Base):
    def setUp(self):
        super().setUp()
        self.cid = self.live.add("https://ejemplo.com/evento")["id"]
        app = SimpleNamespace(live=self.live)
        app.live_rename = lambda cid, name: cine.App.live_rename(app, cid, name)
        app._live_public = lambda cid: cine.App._live_public(app, cid)
        self.httpd = server.Server(("127.0.0.1", 0), server.make_handler(app))
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.say, cine.say = cine.say, lambda msg: None

    def tearDown(self):
        cine.say = self.say
        self.httpd.shutdown()
        self.httpd.server_close()
        super().tearDown()

    def post(self, body):
        req = urllib.request.Request(f"http://127.0.0.1:{self.httpd.server_address[1]}/api/live/rename",
                                     data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read())

    def test_cambia_el_nombre(self):
        r = self.post({"id": self.cid, "name": " Clásico  "})
        self.assertTrue(r["ok"])
        self.assertEqual(r["channel"]["name"], "Clásico")
        self.assertEqual(r["channel"]["id"], self.cid)
        self.assertEqual(r["channel"]["poster"], f"/live/{self.cid}/poster.jpg")

    def test_errores_con_mensaje(self):
        self.assertEqual(self.post({"id": self.cid, "name": "  "}), {"ok": False, "error": "Escribe un nombre para el canal."})
        self.assertEqual(self.post({"id": "otro", "name": "X"}), {"ok": False, "error": "Ese canal ya no existe."})
        self.assertFalse(self.post({"id": self.cid, "name": "a" * 81})["ok"])


if __name__ == "__main__":
    unittest.main()
