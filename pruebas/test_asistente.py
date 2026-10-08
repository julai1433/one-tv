# El asistente del primer arranque (/bienvenida, mac/asistente.py): busca carpetas con videos (con carpetas falsas),
# guarda lo elegido sin tocar lo demás, la contraseña del Roku que inventa, quién puede cambiar la configuración, la
# instalación en un Roku falso, el explorador de carpetas (nunca fuera de los lugares permitidos) y los extras.
# Sin red ni TV.
# python3 -m unittest discover -s pruebas -p "test_asistente.py"
import hashlib, http.client, json, os, re, sys, tempfile, threading, time, unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mac"))
import asistente
import cine
import hostos
from folders import LibraryFolders
from roku import Roku
from server import serve
from subtitles_online import OpenSubtitles, SubtitleError
from teles import Teles

PROYECTO = Path(__file__).resolve().parent.parent


def video(path, size=2000):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\0" * size)


class ConCarpetasFalsas(unittest.TestCase):
    """Una «casa» inventada: la carpeta de videos de la persona, dos discos, una carpeta compartida sin permiso."""

    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.base = Path(self._t.name).resolve()
        for p in (mock.patch.object(asistente, "MIN_BYTES", 1000),
                  mock.patch.object(cine, "CONFIG", self.base / "config.json")):
            p.start()
            self.addCleanup(p.stop)
        b = self.base
        self.videos = b / "casa" / "Videos"
        self.biblio = self.videos / "Biblioteca"
        video(self.biblio / "Películas" / "Una (2001) {imdb-tt0000001}" / "Una (2001).mkv")
        video(self.videos / "Conciertos" / "Uno.mp4")
        video(self.videos / "Conciertos" / "Dos.mp4")
        video(self.videos / "Conciertos" / "clip.mp4", 10)   # muy chico: no cuenta
        self.respaldo = b / "Volumes" / "Respaldo"
        video(self.respaldo / "Videos" / "Movies" / "A (2001)" / "A (2001).mkv")
        video(self.respaldo / "Videos" / "Movies" / "B (2002)" / "B (2002).mkv")
        video(self.respaldo / "Videos" / "Movies" / "B (2002)" / "B (2002)-trailer.mkv")   # extra de Plex: no cuenta
        video(self.respaldo / "Videos" / "TV Shows" / "Serie X" / "Season 01" / "Serie X - S01E01.mkv")
        video(self.respaldo / "Videos" / "TV Shows" / "Serie X" / "Season 01" / "Serie X - S01E02.mkv")
        video(self.respaldo / "Videos" / "TV Shows" / "Otra" / "Season 1" / "Otra S01E01.mkv")
        (self.respaldo / "Fotos").mkdir()
        (self.respaldo / ".Spotlight-V100").mkdir()
        self.pelis = b / "Volumes" / "PELIS"
        video(self.pelis / "X.mkv")
        video(self.pelis / "Y.mp4")
        self.disco3 = b / "Volumes" / "Disco3"
        for n in range(4):
            video(self.disco3 / f"Peli {n} (200{n})" / f"Peli {n} (200{n}).mkv")
        self.compartida = b / "Volumes" / "video"
        video(self.compartida / "Z.mkv")
        self.lugares = [{"ruta": self.videos, "tipo": "casa", "nombre": "Videos"},
                        {"ruta": self.respaldo, "tipo": "disco", "nombre": "Respaldo"},
                        {"ruta": self.pelis, "tipo": "disco", "nombre": "PELIS"},
                        {"ruta": self.disco3, "tipo": "disco", "nombre": "Disco3"},
                        {"ruta": self.compartida, "tipo": "red", "nombre": "video"}]
        self.sin_permiso = os.name != "nt" and os.geteuid() != 0
        if self.sin_permiso:
            self.compartida.chmod(0)
            self.addCleanup(self.compartida.chmod, 0o755)

    def app(self, cfg):
        cine.CONFIG.write_text(json.dumps(cfg))
        return AppFalsa(dict(cfg), self.base, self.lugares)


class AppFalsa:
    """Lo que el asistente usa de la App de mac/cine.py, sin servidor de verdad."""
    welcome_pending = cine.App.welcome_pending
    welcome_done = cine.App.welcome_done

    def __init__(self, cfg, base, lugares):
        self.cfg = cfg
        self.library = SimpleNamespace(roots=[], scanned_at=5, scan=lambda force=False: None)
        self.folders = LibraryFolders(cfg.get("carpetas", []), cfg.get("solo_leer"), base / "carpetas.json",
                                      log=lambda *_: None)
        self.organizer = SimpleNamespace(roots=[])
        self.music = SimpleNamespace(roots=[], tracks={}, scanned_at=9, scan=lambda force=False: 0)
        self.subs = OpenSubtitles(cfg)
        self.auto_subs = SimpleNamespace(watch=lambda: None)
        self.teles = Teles()
        self.roku, self.roku_name, self.server_url, self.installed_url = None, "", "", None
        self.account = SimpleNamespace(summary=lambda: {"subscriptions": 0, "playlists": 0})
        self.network_blocked = False
        self.asistente = asistente.Asistente(self, cine.save_config, PROYECTO, log=lambda *_: None)
        if lugares is not None:
            self.asistente.places = lambda: lugares

    def tv_app(self):
        return {"ok": True, "hay": True, "direccion": "http://192.0.2.7:8765/tv"}


class BuscarCarpetas(ConCarpetasFalsas):
    def test_encuentra_las_carpetas_con_videos_y_cuenta(self):
        app = self.app({"puerto": 8765, "carpetas": [str(self.biblio)], "bienvenida_hecha": False})
        cards = app.asistente.folders()["carpetas"]
        por_nombre = {c["nombre"]: c for c in cards}
        primera = cards[0]   # la de la biblioteca, primero y marcada
        self.assertEqual((primera["ruta"], primera["elegida"], primera["peliculas"]), (str(self.biblio), True, 1))
        self.assertFalse(primera["solo_lectura"])   # acomodada por One TV
        self.assertEqual(primera["donde"], "En esta computadora")
        self.assertEqual((por_nombre["Conciertos"]["peliculas"], por_nombre["Conciertos"]["series"]), (2, 0))
        v = por_nombre["Videos"]   # la de Plex, dentro del disco: la carpeta entera, no cada película
        self.assertEqual((v["ruta"], v["peliculas"], v["series"]), (str(self.respaldo / "Videos"), 2, 2))
        self.assertEqual(v["donde"], "En el disco «Respaldo»")
        self.assertEqual((v["solo_lectura"], v["motivo"]), (True, "otro"))
        self.assertTrue(v["elegida"])   # la primera vez se proponen marcadas
        self.assertEqual(por_nombre["PELIS"]["ruta"], str(self.pelis))   # videos sueltos en la raíz: el disco entero
        self.assertEqual(por_nombre["PELIS"]["peliculas"], 2)
        self.assertEqual((por_nombre["Disco3"]["ruta"], por_nombre["Disco3"]["peliculas"]), (str(self.disco3), 4))
        self.assertNotIn("Fotos", por_nombre)
        self.assertNotIn("Biblioteca", [c["nombre"] for c in cards[1:]])   # no se repite
        if self.sin_permiso:
            c = por_nombre["video"]
            self.assertTrue(c["sin_permiso"])
            self.assertFalse(c["elegida"])
            self.assertEqual(c["donde"], "En la carpeta compartida «video»")
            self.assertTrue(c["arreglo"])
        textos = json.dumps(cards, ensure_ascii=False)
        self.assertNotIn("NAS", textos)

    def test_despues_de_la_bienvenida_lo_nuevo_no_se_marca_solo(self):
        app = self.app({"puerto": 8765, "carpetas": [str(self.biblio)], "bienvenida_hecha": True})
        cards = app.asistente.folders()["carpetas"]
        self.assertEqual([c["elegida"] for c in cards][:1], [True])
        self.assertFalse(any(c["elegida"] for c in cards[1:]))

    def test_una_carpeta_de_la_biblioteca_que_no_esta(self):
        app = self.app({"puerto": 8765, "carpetas": [str(self.base / "no-existe")], "bienvenida_hecha": False})
        c = app.asistente.folders()["carpetas"][0]
        self.assertTrue(c["no_esta"])
        self.assertTrue(c["elegida"])

    def test_el_tope_de_tiempo(self):
        t = asistente.tally(self.respaldo, time.monotonic() - 1)
        self.assertTrue(t["mas"])


class Explorador(ConCarpetasFalsas):
    def test_solo_carpetas_y_dentro_de_los_lugares(self):
        app = self.app({"puerto": 8765, "carpetas": [str(self.biblio)], "bienvenida_hecha": False})
        w = app.asistente
        inicio = w.browse("")
        self.assertIn(str(self.respaldo), [c["ruta"] for c in inicio["carpetas"]])
        r = w.browse(str(self.respaldo))
        self.assertEqual(sorted(c["nombre"] for c in r["carpetas"]), ["Fotos", "Videos"])   # sin ocultas ni archivos
        self.assertEqual(r["arriba"], "")   # arriba del disco: la lista de lugares
        r = w.browse(str(self.respaldo / "Videos" / "Movies"))
        self.assertEqual(r["arriba"], str(self.respaldo / "Videos"))
        self.assertEqual(r["peliculas"], 2)
        afuera = Path(self._t.name).resolve() / "afuera"
        afuera.mkdir()
        for mala in ("/", str(afuera), "relativa/Videos", str(self.respaldo / ".Spotlight-V100"),
                     str(self.respaldo / "Videos" / ".." / ".." / "afuera"), 5):
            self.assertFalse(w.browse(mala)["ok"], mala)
        enlace = self.respaldo / "atajo"
        try:
            enlace.symlink_to(afuera)
        except (OSError, NotImplementedError):
            return
        self.assertFalse(w.browse(str(enlace))["ok"])   # un enlace que sale del lugar: no


class Permisos(unittest.TestCase):
    def test_direcciones_de_la_casa(self):
        for host in ("127.0.0.1:8765", "localhost:8765", "192.0.2.7:8765", "[::1]:8765", "mi-mac.local:8765",
                     "nas:8765", "MI-MAC.LOCAL", "nas.lan"):
            self.assertTrue(asistente.safe_host(host), host)
        for host in ("evil.example.com", "evil.example.com:8765", "x.ts.net", "", "192.0.2.7.nip.io:8765"):
            self.assertFalse(asistente.safe_host(host), host)

    def test_desde_esta_computadora(self):
        self.assertTrue(asistente.is_local("127.0.0.1", "127.0.0.1", "localhost:8765"))
        self.assertTrue(asistente.is_local("::ffff:127.0.0.1", "", "127.0.0.1:8765"))
        self.assertTrue(asistente.is_local("192.0.2.7", "192.0.2.7", "192.0.2.7:8765"))   # su propia IP de la red
        self.assertFalse(asistente.is_local("192.0.2.8", "192.0.2.7", "192.0.2.7:8765"))   # otro aparato
        self.assertFalse(asistente.is_local("127.0.0.1", "127.0.0.1", "evil.example.com"))   # «DNS rebinding»
        self.assertFalse(asistente.is_local("127.0.0.1", "127.0.0.1", "mi-mac.tail1234.ts.net"))   # Tailscale

    def test_quien_puede_cambiar(self):
        self.assertTrue(asistente.may_change(True, False, "localhost"))
        self.assertTrue(asistente.may_change(False, True, "192.0.2.7:8765"))
        self.assertFalse(asistente.may_change(False, False, "192.0.2.7:8765"))
        self.assertFalse(asistente.may_change(True, True, "evil.example.com"))


class EnUnContenedor(unittest.TestCase):
    """Docker en un NAS: el instalador monta las carpetas compartidas en su misma ruta y lo dice ONE_TV_COMPARTIDAS."""

    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.base = Path(self._t.name).resolve()
        self.vol = self.base / "volume1"
        video(self.vol / "video" / "Películas" / "A (2001)" / "A (2001).mkv")
        video(self.vol / "video" / "Películas" / "B (2002)" / "B (2002).mkv")
        video(self.vol / "video" / "Series" / "Serie" / "Season 01" / "Serie - S01E01.mkv")
        video(self.vol / "photo" / "Vacaciones" / "IMG_0001.MOV")   # videos del teléfono: no se proponen
        video(self.vol / "@eaDir" / "x.mkv")
        video(self.vol / "#recycle" / "y.mkv")
        video(self.vol / "homes" / "ana" / "Concierto.mp4")
        for p in (mock.patch.object(asistente, "MIN_BYTES", 1000), mock.patch.object(hostos, "CONTAINER", True),
                  mock.patch.dict(os.environ, {"ONE_TV_COMPARTIDAS": str(self.vol)}),
                  mock.patch.object(asistente, "_mounts", return_value=[]),
                  mock.patch.object(hostos, "computer_name", return_value="Contenedor"),
                  mock.patch.object(cine, "CONFIG", self.base / "config.json")):
            p.start()
            self.addCleanup(p.stop)

    def test_empieza_por_las_carpetas_compartidas(self):
        lugares = asistente.places()
        self.assertEqual(lugares[0], {"ruta": self.vol, "tipo": "compartidas", "nombre": "Carpetas compartidas"})
        cfg = {"puerto": 8765, "carpetas": [str(self.base / "biblioteca")], "bienvenida_hecha": False}
        cine.CONFIG.write_text(json.dumps(cfg))
        app = AppFalsa(dict(cfg), self.base, None)
        cards = app.asistente.folders()["carpetas"]
        por_nombre = {c["nombre"]: c for c in cards}
        self.assertTrue(por_nombre["biblioteca"]["no_esta"])
        v = por_nombre["video"]
        self.assertEqual((v["ruta"], v["peliculas"], v["series"]), (str(self.vol / "video"), 2, 1))
        self.assertEqual(v["donde"], "En la carpeta compartida «video»")
        self.assertEqual(por_nombre["homes"]["donde"], "En la carpeta compartida «homes»")
        self.assertNotIn("photo", por_nombre)
        self.assertNotIn("volume1", por_nombre)   # nunca todas juntas
        self.assertFalse({"@eaDir", "#recycle"} & set(por_nombre))
        inicio = app.asistente.browse("")["carpetas"]
        self.assertEqual(inicio[0]["nombre"], "Carpetas compartidas")
        dentro = [c["nombre"] for c in app.asistente.browse(str(self.vol))["carpetas"]]
        self.assertEqual(dentro, ["homes", "photo", "video"])
        self.assertEqual(app.asistente.browse(str(self.vol / "video"))["donde"], "En la carpeta compartida «video»")
        self.assertNotIn("NAS", json.dumps(cards + inicio, ensure_ascii=False))
        st = app.asistente.state(True, False)
        self.assertEqual((st["sistema"], st["arranque"], st["youtube"]["disponible"]), ("contenedor", "equipo", False))


class ContrasenaDelRoku(unittest.TestCase):
    def test_facil_de_escribir_con_el_control(self):
        vistas = {asistente.roku_password() for _ in range(200)}
        self.assertGreater(len(vistas), 150)
        for p in vistas:
            self.assertRegex(p, r"^[bcdfghjkmnprstvz][aeu][bcdfghjkmnprstvz][aeu][2345679]{2}$")


class PorLaRed(ConCarpetasFalsas):
    """Las rutas /api/asistente/… y /api/bienvenida con un servidor de verdad (en 127.0.0.1, puerto libre)."""

    def servidor(self, cfg):
        app = self.app(cfg)
        httpd = serve(app, 0, "127.0.0.1")
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        self.port = httpd.server_address[1]
        return app

    def pedir(self, metodo, ruta, cuerpo=None, host=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=20)
        headers = {"Content-Type": "application/json"} if cuerpo is not None else {}
        if host:
            headers["Host"] = host
        c.request(metodo, ruta, body=json.dumps(cuerpo) if cuerpo is not None else None, headers=headers)
        r = c.getresponse()
        datos = r.read()
        c.close()
        try:
            return r.status, json.loads(datos)
        except ValueError:
            return r.status, datos

    def config(self):
        return json.loads(cine.CONFIG.read_text())

    def test_guardar_las_carpetas_sin_tocar_lo_demas(self):
        app = self.servidor({"puerto": 8765, "carpetas": [str(self.biblio)], "roku_password": "",
                             "titulos": {"tt1": "X"}, "bienvenida_hecha": False})
        status, datos = self.pedir("GET", "/api/asistente/carpetas")
        self.assertEqual(status, 200)
        plex = str(self.respaldo / "Videos")
        self.assertIn(plex, [c["ruta"] for c in datos["carpetas"]])
        status, datos = self.pedir("POST", "/api/asistente/carpetas", {"carpetas": [str(self.biblio), plex, plex]})
        self.assertEqual(datos, {"ok": True, "carpetas": 2})
        cfg = self.config()
        self.assertEqual(cfg["carpetas"], [str(self.biblio), hostos.tilde(plex)])
        self.assertEqual(cfg["solo_leer"], {hostos.tilde(plex): True})   # ya tenía videos acomodados: solo leerla
        self.assertEqual((cfg["puerto"], cfg["titulos"], cfg["bienvenida_hecha"]), (8765, {"tt1": "X"}, False))
        self.assertEqual(app.library.roots, [self.biblio, Path(plex)])   # sin reiniciar
        self.assertEqual(app.folders.roots, [self.biblio, Path(plex)])
        self.assertEqual(app.organizer.roots, [self.biblio, Path(plex)])
        self.assertIs(app.folders.own(Path(plex)), False)
        # Quitar una: se va también de «solo_leer».
        self.pedir("POST", "/api/asistente/carpetas", {"carpetas": [str(self.biblio)]})
        self.assertEqual((self.config()["carpetas"], self.config()["solo_leer"]), ([str(self.biblio)], {}))

    def test_rutas_que_no_se_aceptan(self):
        self.servidor({"puerto": 8765, "carpetas": [str(self.biblio)], "bienvenida_hecha": False})
        antes = self.config()
        for malas in ([], ["/"], ["../Videos"], [str(Path(self._t.name).resolve())], [str(self.respaldo / ".Spotlight-V100")],
                      "texto", [5], [str(self.biblio)] * 60):
            status, datos = self.pedir("POST", "/api/asistente/carpetas", {"carpetas": malas})
            self.assertFalse(datos["ok"], malas)
        self.assertEqual(self.config(), antes)
        self.assertEqual(self.pedir("GET", "/api/asistente/explorar?ruta=/etc")[1]["ok"], False)

    def test_contrasena_del_roku_se_guarda_una_vez(self):
        self.servidor({"puerto": 8765, "carpetas": [str(self.biblio)], "roku_password": "", "bienvenida_hecha": False})
        clave = self.pedir("GET", "/api/asistente/estado")[1]["roku"]["clave"]
        self.assertRegex(clave, r"^[a-z]{4}\d\d$")
        self.assertEqual(self.config()["roku_password"], clave)
        self.assertEqual(self.pedir("GET", "/api/asistente/estado")[1]["roku"]["clave"], clave)   # la misma

    def test_la_que_ya_tenia_no_se_cambia(self):
        self.servidor({"puerto": 8765, "carpetas": [str(self.biblio)], "roku_password": "la-mia", "bienvenida_hecha": False})
        self.assertEqual(self.pedir("GET", "/api/asistente/estado")[1]["roku"]["clave"], "la-mia")

    def test_desde_otro_aparato_solo_mientras_falta_terminarlo(self):
        self.servidor({"puerto": 8765, "carpetas": [str(self.biblio)], "roku_password": "", "bienvenida_hecha": False})
        with mock.patch.object(asistente, "is_local", return_value=False):   # como si pidiera el teléfono
            st = self.pedir("GET", "/api/asistente/estado")[1]
            self.assertEqual((st["permitido"], st["local"]), (True, False))
            self.assertEqual(self.pedir("GET", "/api/asistente/carpetas")[0], 200)
            # Lo que pasa en esta computadora (la ventana de Windows, Tailscale): solo desde ella.
            self.assertEqual(self.pedir("POST", "/api/asistente/permitir-red", {})[0], 403)
            self.assertEqual(self.pedir("POST", "/api/asistente/fuera", {})[0], 403)
            self.assertEqual(self.pedir("POST", "/api/bienvenida", {"hecha": True})[1]["pendiente"], False)
            st = self.pedir("GET", "/api/asistente/estado")[1]
            self.assertEqual(st, {"ok": True, "permitido": False, "local": False, "pendiente": False})   # ni la clave
            for metodo, ruta, cuerpo in (("GET", "/api/asistente/carpetas", None),
                                         ("GET", "/api/asistente/explorar?ruta=" + str(self.respaldo), None),
                                         ("GET", "/api/asistente/qr.png", None),
                                         ("POST", "/api/asistente/carpetas", {"carpetas": [str(self.pelis)]}),
                                         ("POST", "/api/asistente/subtitulos", {"api_key": "x"}),
                                         ("POST", "/api/asistente/roku", {}),
                                         ("POST", "/api/bienvenida", {"hecha": False})):
                self.assertEqual(self.pedir(metodo, ruta, cuerpo)[0], 403, ruta)
        self.assertEqual(self.config()["carpetas"], [str(self.biblio)])
        self.assertIs(self.config()["bienvenida_hecha"], True)
        # Desde esta computadora, siempre (también volver a abrirlo).
        self.assertEqual(self.pedir("GET", "/api/asistente/carpetas")[0], 200)
        self.assertEqual(self.pedir("POST", "/api/bienvenida", {"hecha": False})[1]["pendiente"], True)

    def test_una_pagina_de_internet_que_apunta_aqui(self):
        self.servidor({"puerto": 8765, "carpetas": [str(self.biblio)], "bienvenida_hecha": False})
        st = self.pedir("GET", "/api/asistente/estado", host="evil.example.com")[1]
        self.assertEqual(st["permitido"], False)
        self.assertEqual(self.pedir("GET", "/api/asistente/carpetas", host="evil.example.com")[0], 403)
        self.assertEqual(self.pedir("POST", "/api/bienvenida", {"hecha": True}, host="evil.example.com")[0], 403)
        self.assertEqual(self.pedir("GET", "/api/asistente/carpetas", host="mi-mac.local:8765")[0], 200)

    def test_qr_y_estado(self):
        self.servidor({"puerto": 8765, "carpetas": [str(self.biblio)], "bienvenida_hecha": False})
        status, png = self.pedir("GET", "/api/asistente/qr.png")
        self.assertEqual((status, png[:8]), (200, b"\x89PNG\r\n\x1a\n"))
        st = self.pedir("GET", "/api/asistente/estado")[1]
        self.assertEqual(st["android"]["direccion"], "192.0.2.7:8765/tv")
        self.assertEqual((st["tele"], st["roku"]["encontrado"], st["musica"]["lista"]), ("", False, False))
        self.assertEqual(st["carpetas"], 1)

    def test_tu_musica(self):
        app = self.servidor({"puerto": 8765, "carpetas": [str(self.biblio)], "bienvenida_hecha": False})
        musica = self.respaldo / "Música"
        for n in range(3):
            video(musica / "Artista" / f"{n}.mp3", 10)
        status, datos = self.pedir("POST", "/api/asistente/musica", {"carpeta": str(musica)})
        self.assertEqual((datos["ok"], datos["canciones"]), (True, 3))
        self.assertEqual(self.config()["musica"], [hostos.tilde(musica)])
        self.assertEqual(app.music.roots, [musica])
        self.assertFalse(self.pedir("POST", "/api/asistente/musica", {"carpeta": "/"})[1]["ok"])

    def test_subtitulos_se_comprueban_antes_de_guardar(self):
        app = self.servidor({"puerto": 8765, "carpetas": [str(self.biblio)], "bienvenida_hecha": False,
                             "opensubtitles": {"api_key": "", "usuario": "", "clave": "", "automaticos": True}})
        arrancados = []
        app.auto_subs = SimpleNamespace(watch=lambda: arrancados.append(1))

        class Falso(OpenSubtitles):
            def _request(self, method, path, params=None, body=None, auth=False, retry=True, tries_429=2):
                if self.api_key != "buena":
                    raise SubtitleError("rechazó la clave", code=401)
                if path == "/login" and (self.username, self.password) != ("ana", "secreto"):
                    raise SubtitleError("no", code=401)
                return {"token": "t"}
        app.asistente.OpenSubtitles = Falso
        malo = self.pedir("POST", "/api/asistente/subtitulos", {"api_key": "mala"})[1]
        self.assertIn("no reconoce esa clave", malo["error"])
        malo = self.pedir("POST", "/api/asistente/subtitulos", {"api_key": "buena", "usuario": "ana", "clave": "x"})[1]
        self.assertIn("usuario y contraseña", malo["error"])
        self.assertIn("usuario", self.pedir("POST", "/api/asistente/subtitulos", {"api_key": "buena", "usuario": "ana"})[1]["error"])
        self.assertEqual(self.config()["opensubtitles"]["api_key"], "")   # nada se guardó
        bien = self.pedir("POST", "/api/asistente/subtitulos", {"api_key": "buena", "usuario": "ana", "clave": "secreto"})[1]
        self.assertEqual(bien, {"ok": True})   # sin devolver la clave
        self.assertEqual(self.config()["opensubtitles"], {"api_key": "buena", "usuario": "ana", "clave": "secreto",
                                                          "automaticos": True})
        self.assertEqual((app.subs.api_key, app.subs.username), ("buena", "ana"))
        time.sleep(0.2)
        self.assertEqual(arrancados, [1])   # los automáticos arrancan ya (antes faltaba la clave)
        self.assertEqual(self.pedir("GET", "/api/asistente/estado")[1]["subtitulos"], {"activos": True, "usuario": "ana"})

    def test_permitir_la_entrada_en_windows(self):
        app = self.servidor({"puerto": 8765, "carpetas": [str(self.biblio)], "bienvenida_hecha": False})
        app.network_blocked = True
        respuestas = iter(["cancelado", ""])
        app.asistente.firewall = SimpleNamespace(allow=lambda port: next(respuestas), status=lambda port: False)
        app.asistente.windows = True
        self.assertIs(self.pedir("GET", "/api/asistente/estado")[1]["puede_permitir"], True)
        self.assertIn("No se dio el permiso", self.pedir("POST", "/api/asistente/permitir-red", {})[1]["error"])
        self.assertEqual(self.pedir("POST", "/api/asistente/permitir-red", {})[1], {"ok": True, "bloqueada": False})
        self.assertFalse(app.network_blocked)


class RokuFalso(ConCarpetasFalsas):
    """Instalar One TV en un Roku inventado: el de verdad (mac/roku.py) contra un instalador falso con contraseña, y el
    avance que ve el asistente."""

    def test_el_instalador_del_roku_pide_la_contrasena(self):
        clave = "baku47"
        recibido = []

        class Instalador(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _reto(self):
                self.send_response(401)
                self.send_header("WWW-Authenticate", 'Digest realm="rokudev", nonce="n123", qop="auth"')
                self.send_header("Content-Length", "0")
                self.end_headers()

            def _ok(self):
                auth = self.headers.get("Authorization", "")
                f = dict(re.findall(r'(\w+)="?([^",]*)"?', auth))
                if f.get("username") != "rokudev":
                    return False
                ha1 = hashlib.md5(f"rokudev:rokudev:{clave}".encode()).hexdigest()
                ha2 = hashlib.md5(f"{self.command}:{f.get('uri')}".encode()).hexdigest()
                esperado = hashlib.md5(f"{ha1}:n123:{f.get('nc')}:{f.get('cnonce')}:auth:{ha2}".encode()).hexdigest()
                return f.get("response") == esperado

            def do_GET(self):
                self._reto()

            def do_POST(self):
                datos = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                if not self._ok():
                    return self._reto()
                recibido.append(datos)
                body = b"<html>Install Success.</html>"
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        httpd = ThreadingHTTPServer(("127.0.0.1", 0), Instalador)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        ip = f"127.0.0.1:{httpd.server_address[1]}"   # (el instalador del Roku está en su puerto 80)
        self.assertEqual(Roku(ip, clave)._upload(b"PK zip de prueba" * 9000), (True, "app instalada"))
        self.assertIn(b"PK zip de prueba", recibido[0])
        ok, msg = Roku(ip, "otra")._upload(b"PK")
        self.assertFalse(ok)
        self.assertIn("contraseña", msg)

    def instalar(self, app, resultado, ip="192.0.2.50"):
        hechos = []

        class RokuDePrueba:
            def __init__(self, ip, password):
                self.ip, self.dev_password = ip, password

            def device_name(self):
                return "TV de la sala"

            def install(self, zip_bytes):
                hechos.append((self.dev_password, zip_bytes))
                return resultado
        w = app.asistente
        w.Roku, w.discover, w.local_ip = RokuDePrueba, lambda: ip, lambda ip: "192.0.2.7"
        w.build_zip = lambda carpeta, url: url.encode()
        vistos = [w.roku_install()["estado"]]
        for _ in range(100):
            estado = w.roku_status()["estado"]
            if estado not in vistos:
                vistos.append(estado)
            if estado in ("listo", "error"):
                break
            time.sleep(0.02)
        return vistos, w.roku_status(), hechos

    def test_instalar_desde_el_asistente(self):
        app = self.app({"puerto": 8765, "carpetas": [str(self.biblio)], "roku_password": "", "bienvenida_hecha": False})
        vistos, st, hechos = self.instalar(app, (True, "app instalada"))
        self.assertEqual(vistos[0], "buscando")
        self.assertEqual(st["estado"], "listo")
        clave = self.config_clave()
        self.assertEqual(hechos, [(clave, b"http://192.0.2.7:8765")])   # con la contraseña que inventó el asistente
        self.assertEqual((app.roku.ip, app.roku_name, app.installed_url), ("192.0.2.50", "TV de la sala", "http://192.0.2.7:8765"))

    def config_clave(self):
        return json.loads(cine.CONFIG.read_text())["roku_password"]

    def test_lo_que_dice_si_no_se_pudo(self):
        app = self.app({"puerto": 8765, "carpetas": [str(self.biblio)], "roku_password": "kemu35", "bienvenida_hecha": False})
        st = self.instalar(app, (False, "contraseña del modo desarrollador incorrecta (revisa config.json)"))[1]
        self.assertEqual(st["estado"], "error")
        self.assertIn("kemu35", st["mensaje"])
        self.assertNotIn("config.json", st["mensaje"])
        st = self.instalar(app, (False, "no se pudo conectar al instalador del Roku (x). ¿Está activo…?"))[1]
        self.assertIn("pasos 1 a 3", st["mensaje"])
        st = self.instalar(app, (True, "x"), ip=None)[1]
        self.assertIn("No encontré tu Roku", st["mensaje"])


if __name__ == "__main__":
    unittest.main()
