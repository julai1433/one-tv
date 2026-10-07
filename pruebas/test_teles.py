# Pruebas de las TV con Android (Google TV, Android TV, Fire TV) manejadas desde la computadora (mac/teles.py) y de la
# app que se instala con «Downloader» (mac/apptv.py): la cola de órdenes, la consulta que espera, a qué TV se manda, las
# rutas del servidor y la app que se ofrece en /tv. Sin red ni TV.
# Uso: python3 -m unittest discover -s pruebas -p 'test_teles.py'
import io, json, sys, tempfile, threading, time, unittest, urllib.error, urllib.request
from pathlib import Path
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mac"))
import cine
from apptv import APK, AppTv
from server import serve
from store import Store
from teles import GRACIA, ROKU, VIDA_ORDEN, AndroidTv, SinTele, Teles


class Reloj:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class ColaDeOrdenes(unittest.TestCase):
    def setUp(self):
        self.reloj = Reloj()
        self.teles = Teles(reloj=self.reloj)

    def test_sin_consulta_no_hay_tv_conectada(self):
        self.assertEqual(self.teles.android(), [])
        with self.assertRaises(SinTele):
            self.teles.mandar("androidtv-1", {"cmd": "refresh"})

    def test_las_ordenes_esperan_a_la_siguiente_consulta_y_se_entregan_una_vez(self):
        self.assertEqual(self.teles.esperar("androidtv-1", "Sala", espera=0), [])
        self.assertEqual([(t.id, t.nombre) for t in self.teles.android()], [("androidtv-1", "Sala")])
        self.teles.mandar("androidtv-1", {"cmd": "key", "key": "Play"})
        self.teles.mandar("androidtv-1", {"cmd": "seek", "t": 90})
        self.assertEqual(self.teles.esperar("androidtv-1", espera=0),
                         [{"cmd": "key", "key": "Play"}, {"cmd": "seek", "t": 90}])
        self.assertEqual(self.teles.esperar("androidtv-1", espera=0), [])

    def test_un_solo_actualiza_pendiente(self):
        self.teles.esperar("androidtv-1", espera=0)
        for _ in range(3):
            self.teles.mandar("androidtv-1", {"cmd": "refresh"})
        self.assertEqual(self.teles.esperar("androidtv-1", espera=0), [{"cmd": "refresh"}])

    def test_las_ordenes_viejas_ya_no_valen(self):
        self.teles.esperar("androidtv-1", espera=0)
        self.teles.mandar("androidtv-1", {"cmd": "play", "contentId": "peli"})
        self.reloj.t += VIDA_ORDEN + 1
        self.assertEqual(self.teles.esperar("androidtv-1", espera=0), [])

    def test_deja_de_estar_conectada_si_no_vuelve_a_preguntar_o_se_despide(self):
        self.teles.esperar("androidtv-1", espera=0)
        self.reloj.t += GRACIA - 1
        self.assertEqual(len(self.teles.android()), 1)
        self.reloj.t += 2
        self.assertEqual(self.teles.android(), [])
        self.teles.esperar("androidtv-1", espera=0)
        self.teles.adios("androidtv-1")
        self.assertEqual(self.teles.android(), [])
        self.teles.esperar("androidtv-1", espera=0)   # se volvió a abrir
        self.assertEqual(len(self.teles.android()), 1)

    def test_ids_raros_no_se_registran(self):
        self.assertEqual(self.teles.esperar("../../x y", espera=0), [])
        self.assertEqual(self.teles.esperar("", espera=0), [])
        self.assertEqual(self.teles.android(), [])

    def test_nombre_corto_y_sin_saltos(self):
        self.teles.esperar("androidtv-1", "  Sala\n de  la casa " + "x" * 80, espera=0)
        self.assertEqual(self.teles.android()[0].nombre, ("Sala de la casa " + "x" * 80)[:40])
        self.teles.esperar("androidtv-2", "", espera=0)
        self.assertEqual(self.teles.android()[1].nombre, "TV con Android")


class ConsultaQueEspera(unittest.TestCase):
    def test_contesta_en_cuanto_llega_una_orden(self):
        teles = Teles()
        teles.esperar("androidtv-1", espera=0)
        got = {}

        def preguntar():
            t0 = time.monotonic()
            got["ordenes"] = teles.esperar("androidtv-1", espera=5)
            got["tardo"] = time.monotonic() - t0
        h = threading.Thread(target=preguntar)
        h.start()
        time.sleep(0.2)
        teles.mandar("androidtv-1", {"cmd": "key", "key": "Back"})
        h.join(3)
        self.assertEqual(got["ordenes"], [{"cmd": "key", "key": "Back"}])
        self.assertLess(got["tardo"], 2)

    def test_vacia_al_vencer_y_conectada_mientras_espera(self):
        teles = Teles()
        h = threading.Thread(target=teles.esperar, args=("androidtv-1", "Sala", 0.4))
        h.start()
        time.sleep(0.1)
        self.assertEqual(len(teles.android()), 1)
        t0 = time.monotonic()
        h.join(3)
        self.assertLess(time.monotonic() - t0, 1)

    def test_una_consulta_nueva_suelta_a_la_anterior(self):
        teles = Teles()
        got = []
        h = threading.Thread(target=lambda: got.append(teles.esperar("androidtv-1", espera=10)))
        h.start()
        time.sleep(0.15)
        t0 = time.monotonic()
        threading.Thread(target=teles.esperar, args=("androidtv-1", "", 0.3)).start()
        h.join(3)
        self.assertEqual(got, [[]])
        self.assertLess(time.monotonic() - t0, 1)

    def test_devolver_si_no_se_pudo_entregar(self):
        teles = Teles()
        teles.esperar("androidtv-1", espera=0)
        teles.mandar("androidtv-1", {"cmd": "seek", "t": 5})
        ordenes = teles.esperar("androidtv-1", espera=0)
        teles.devolver("androidtv-1", ordenes)
        self.assertEqual(teles.esperar("androidtv-1", espera=0), [{"cmd": "seek", "t": 5}])


class AQueTele(unittest.TestCase):
    def setUp(self):
        self.reloj = Reloj()
        self.teles = Teles(reloj=self.reloj)
        self.roku = mock.Mock()

    def test_sin_tv_ninguna(self):
        self.assertIsNone(self.teles.destino(None))

    def test_solo_el_roku_es_como_siempre(self):
        self.assertIs(self.teles.destino(self.roku), self.roku)
        self.assertEqual(self.teles.lista(self.roku, "Roku de la sala"),
                         [{"id": ROKU, "nombre": "Roku de la sala", "tipo": "roku", "elegida": True}])

    def test_solo_una_android(self):
        self.teles.esperar("androidtv-1", "Recámara", espera=0)
        tv = self.teles.destino(None)
        self.assertIsInstance(tv, AndroidTv)
        self.assertEqual(tv.id, "androidtv-1")

    def test_la_que_se_uso_por_ultima_vez(self):
        self.reloj.t += 1
        self.teles.esperar("androidtv-1", "Recámara", espera=0)   # se acaba de abrir: es la que se está usando
        self.assertEqual(self.teles.destino(self.roku).id, "androidtv-1")
        self.reloj.t += 1
        self.teles.usar(ROKU)                                    # el Roku empezó a reproducir algo
        self.assertIs(self.teles.destino(self.roku), self.roku)
        self.reloj.t += 1
        self.assertTrue(self.teles.elegir("androidtv-1", self.roku))   # elegida en la web
        lista = self.teles.lista(self.roku, "")
        self.assertEqual([(t["id"], t["nombre"], t["elegida"]) for t in lista],
                         [(ROKU, "Roku", False), ("androidtv-1", "Recámara", True)])
        self.assertFalse(self.teles.elegir("otra", self.roku))
        self.assertFalse(self.teles.elegir(ROKU, None))

    def test_si_la_elegida_se_cierra_vuelve_a_la_otra(self):
        self.reloj.t += 1
        self.teles.esperar("androidtv-1", espera=0)
        self.teles.adios("androidtv-1")
        self.assertIs(self.teles.destino(self.roku), self.roku)

    def test_quien_reporta(self):
        self.teles.esperar("androidtv-1", "Sala", espera=0)
        self.assertEqual(self.teles.de("androidtv-1", self.roku).nombre, "Sala")
        self.assertIs(self.teles.de("id-del-roku", self.roku), self.roku)
        self.assertIs(self.teles.de(None, self.roku), self.roku)


class Falso(cine.App):
    """Lo mínimo del objeto App para mandar cosas a la TV (sin biblioteca de verdad)."""

    def __init__(self, tmp, roku=True):
        self.cfg = {"puerto": 8765}
        self.roku = mock.Mock() if roku else None
        if roku:
            self.roku.player.return_value = None
            self.roku.ip = "192.0.2.10"
        self.roku_name = "Roku de prueba"
        self.teles = Teles()
        self.store = Store(Path(tmp) / "progreso.json")
        self.library = mock.Mock(items={"peli": {}})
        self.library.get.side_effect = lambda i: {"id": i, "full_title": "Peli", "duration": 100} if i == "peli" else None
        self.library.public_item.return_value = {"poster": "/poster/peli.jpg", "audio": [], "subs": []}
        self.server_url = "http://192.0.2.5:8765"
        self._player_lock = threading.Lock()
        self._player = (0.0, None)
        self.queue = mock.Mock()
        self.queue.items.return_value = []
        self.iphone_url = None
        self.dubbing = mock.Mock(current=None)
        self.app_tv = AppTv(Path(tmp) / "app-tv", Path(tmp) / "compilada")

    def remember_tracks(self, *a, **k):
        pass

    def marks(self, *a, **k):
        return []


class LaComputadoraManda(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.app = Falso(self._t.name)
        quiet = mock.patch.object(cine, "say", lambda m: None)
        quiet.start()
        self.addCleanup(quiet.stop)

    def conectar(self, ident="androidtv-1", nombre="Sala"):
        self.app.teles.esperar(ident, nombre, espera=0)

    def ordenes(self, ident="androidtv-1"):
        return self.app.teles.esperar(ident, espera=0)

    def test_con_solo_el_roku_todo_igual(self):
        self.assertEqual(self.app.cast("peli", audio=1, sub=-1, start=30), {"ok": True})
        self.app.roku.play.assert_called_with("peli", self.app.server_url, audio=1, sub=-1, start=30)
        self.app.store.report("peli", 40, 100, "tick", device_id="id-del-roku")
        self.assertEqual(self.app.control("seek", t=60), {"ok": True})
        self.app.roku.send.assert_called_with(cmd="seek", t=60)
        self.assertEqual(self.app.remote_key("Play"), {"ok": True})
        self.app.roku.key.assert_called_with("Play")
        self.assertEqual(self.app.status()["teles"], [{"id": ROKU, "nombre": "Roku de prueba", "tipo": "roku", "elegida": True}])
        self.assertNotIn("donde", self.app.status()["playing"])

    def test_ver_en_la_tv_con_android(self):
        self.conectar()
        self.assertEqual(self.app.cast("peli", audio=0, sub=1, start=None), {"ok": True})
        self.app.roku.play.assert_not_called()
        self.assertEqual(self.ordenes(), [{"cmd": "play", "contentId": "peli", "audio": 0, "sub": 1}])

    def test_las_ordenes_van_a_la_tv_donde_se_ve(self):
        self.conectar()
        self.app.store.report("peli", 40, 100, "tick", device_id="androidtv-1")
        self.app.teles.usar(ROKU)   # aunque «Ver en la TV» ahora iría al Roku…
        self.assertEqual(self.app.control("tracks", audio=1, sub=None), {"ok": True})
        self.assertEqual(self.app.control("seek", t=75), {"ok": True})
        self.assertEqual(self.app.control("song", dir=-1), {"ok": True})
        self.assertEqual(self.app.remote_key("Play"), {"ok": True})
        self.assertEqual(self.app.remote_key("Back"), {"ok": True})
        self.assertEqual(self.ordenes(), [{"cmd": "tracks", "audio": 1}, {"cmd": "seek", "t": 75},
                                          {"cmd": "song", "dir": -1}, {"cmd": "key", "key": "Play"},
                                          {"cmd": "key", "key": "Back"}])
        self.app.roku.send.assert_not_called()
        self.app.roku.player.assert_not_called()   # la posición la cuenta el reporte de la TV con Android
        st = self.app.status()
        self.assertEqual(st["playing"]["donde"], "Sala")
        self.assertEqual(st["playing"]["position"], 40)

    def test_si_la_tv_se_cerro(self):
        self.conectar()
        self.app.store.report("peli", 40, 100, "tick", device_id="androidtv-1")
        self.app.teles.adios("androidtv-1")
        r = self.app.control("seek", t=75)
        self.assertFalse(r["ok"])
        self.assertIn("Sala", r["error"])
        self.app.roku = None
        self.assertEqual(self.app.cast("peli")["error"], "No encontré la TV: abre One TV en la TV y prueba otra vez.")

    def test_actualiza_y_varios_a_la_vez(self):
        self.conectar()
        with mock.patch.object(cine.threading, "Thread"):
            self.app.tell_tv_to_refresh()
        self.assertEqual(self.ordenes(), [{"cmd": "refresh"}])
        r = self.app.mosaic_tv({"sources": [{"kind": "item", "id": "peli"}, {"kind": "item", "id": "peli"}]})
        self.assertFalse(r["ok"])

    def test_rutas(self):
        httpd = serve(self.app, 0)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        base = f"http://127.0.0.1:{httpd.server_address[1]}"

        def post(path, body):
            req = urllib.request.Request(base + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
            return json.loads(urllib.request.urlopen(req, timeout=10).read())

        got = {}

        def consulta():   # la app de la TV: espera hasta que la computadora tenga una orden
            t0 = time.monotonic()
            got["r"] = json.loads(urllib.request.urlopen(base + "/api/tv/ordenes?device_id=androidtv-9&nombre=Sala%20grande",
                                                         timeout=30).read())
            got["tardo"] = time.monotonic() - t0
        h = threading.Thread(target=consulta)
        h.start()
        for _ in range(50):
            if self.app.teles.android():
                break
            time.sleep(0.05)
        st = json.loads(urllib.request.urlopen(base + "/api/status").read())
        self.assertEqual([(t["nombre"], t["elegida"]) for t in st["teles"]], [("Roku de prueba", False), ("Sala grande", True)])
        self.assertEqual(post("/api/tv/elegir", {"id": ROKU})["ok"], True)
        self.assertEqual(post("/api/tv/elegir", {"id": "androidtv-9"})["ok"], True)
        self.assertEqual(post("/api/tv/elegir", {"id": "no-existe"})["ok"], False)
        self.assertEqual(post("/api/play", {"id": "peli", "start": 12}), {"ok": True})
        h.join(10)
        self.assertEqual(got["r"], {"ok": True, "ordenes": [{"cmd": "play", "contentId": "peli", "start": 12}]})
        self.assertLess(got["tardo"], 5)
        # el Roku empieza a reproducir: pasa a ser la elegida; luego la TV con Android, otra vez
        post("/api/progress", {"id": "peli", "p": 0, "d": 100, "ev": "start", "device_id": "id-del-roku"})
        self.assertIs(self.app.teles.destino(self.app.roku), self.app.roku)
        post("/api/progress", {"id": "peli", "p": 0, "d": 100, "ev": "start", "device_id": "androidtv-9"})
        self.assertEqual(self.app.teles.destino(self.app.roku).id, "androidtv-9")
        self.assertEqual(self.app.store.now_playing()["device_id"], "androidtv-9")
        post("/api/tv/adios", {"device_id": "androidtv-9"})
        self.assertEqual(self.app.teles.android(), [])


def apk_falso():
    buf = io.BytesIO()
    import zipfile
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("AndroidManifest.xml", b"x")
    return buf.getvalue()


class Respuesta(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class AppParaDownloader(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.dir = Path(self._t.name)
        self.pedidas = []

    def abrir(self, versiones, apk):
        def abrir(req, timeout=0):
            url = req.full_url
            self.pedidas.append(url)
            if "api.github.com" in url:
                return Respuesta(json.dumps(versiones).encode())
            if url.endswith(".json"):
                return Respuesta(json.dumps({"version": "0.1.7", "version_code": 8}).encode())
            return Respuesta(apk)
        return abrir

    def version(self, tag, nombre=APK, draft=False):
        return {"tag_name": tag, "draft": draft, "assets": [
            {"name": nombre, "browser_download_url": f"https://github.com/x/releases/download/{tag}/{nombre}"},
            {"name": "one-tv-tv.json", "browser_download_url": f"https://github.com/x/releases/download/{tag}/one-tv-tv.json"}]}

    def test_sin_app_ninguna(self):
        a = AppTv(self.dir / "cache", self.dir / "no-existe")
        self.assertIsNone(a.actual())
        self.assertEqual(a.info()["hay"], False)

    def test_baja_la_tv_mas_nueva_de_github_una_sola_vez(self):
        versiones = [self.version("v2.0", "otra-cosa.zip"), self.version("tv-0.1.8", draft=True), self.version("tv-0.1.7"),
                     self.version("tv-0.1.6")]
        a = AppTv(self.dir / "cache", None, abrir=self.abrir(versiones, apk_falso()))
        self.assertIn("0.1.7", a.actualizar())
        self.assertEqual(a.info(), {"hay": True, "version": "0.1.7", "version_code": 8, "origen": "github"})
        self.assertTrue(any(u.endswith("tv-0.1.7/" + APK) for u in self.pedidas))
        self.pedidas.clear()
        self.assertIsNone(a.actualizar())   # ya la tiene: solo pregunta, no la baja otra vez
        self.assertEqual(len(self.pedidas), 1)

    def test_no_guarda_algo_que_no_es_una_app(self):
        a = AppTv(self.dir / "cache", None, abrir=self.abrir([self.version("tv-0.1.7")], b"<html>error</html>"))
        with self.assertRaises(ValueError):
            a.actualizar()
        self.assertIsNone(a.actual())

    def test_la_compilada_aqui_gana(self):
        d = self.dir / "release"
        d.mkdir()
        (d / "app-release.apk").write_bytes(apk_falso())
        (d / "output-metadata.json").write_text(json.dumps(
            {"elements": [{"versionCode": 1, "versionName": "0.1", "outputFile": "app-release.apk"}]}))
        a = AppTv(self.dir / "cache", d, abrir=self.abrir([self.version("tv-0.1.7")], apk_falso()))
        a.actualizar()
        self.assertEqual(a.info(), {"hay": True, "version": "0.1", "version_code": 1, "origen": "compilada"})

    def test_la_direccion_corta_entrega_la_app(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        app = Falso(tmp.name)
        with mock.patch.object(cine.hostos, "lan_url", lambda port: f"http://192.0.2.5:{port}"):
            app.server_url = ""
            self.assertEqual(app.tv_app()["direccion"], "http://192.0.2.5:8765/tv")
        httpd = serve(app, 0)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        r = urllib.request.urlopen(base + "/tv")   # sin app todavía: una página que lo dice en llano
        self.assertTrue(r.headers["Content-Type"].startswith("text/html"))
        self.assertIn("Todavía no hay app", r.read().decode())
        d = Path(tmp.name) / "compilada"
        d.mkdir()
        (d / "app-release.apk").write_bytes(apk_falso())
        for ruta in ("/tv", "/TV/", "/tv.apk"):
            r = urllib.request.urlopen(base + ruta)
            self.assertEqual(r.headers["Content-Type"], "application/vnd.android.package-archive")
            self.assertIn("one-tv.apk", r.headers["Content-Disposition"])
            self.assertEqual(r.read(), apk_falso())
        info = json.loads(urllib.request.urlopen(base + "/api/tv/app").read())
        self.assertEqual((info["ok"], info["hay"], info["origen"]), (True, True, "compilada"))
        self.assertTrue(info["direccion"].endswith("/tv"))
        self.assertNotIn("path", info)


if __name__ == "__main__":
    unittest.main()
