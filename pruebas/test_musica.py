# Pruebas de tu música (mac/music.py y sus rutas) con canciones de prueba hechas al momento con ffmpeg (tonos de 3 s
# con etiquetas). Sin red. Uso: python3 -m unittest pruebas/test_musica.py
import json, subprocess, sys, tempfile, threading, time, unittest, urllib.request
from unittest import mock
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mac"))
import cine
from music import Music
from playqueue import PlayQueue
from store import Store
from server import serve


def cancion(path, title, artist, album, track, codec="flac", album_artist=None, cover=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=3"]
    if cover:
        # Un solo cuadro de portada (r=1:d=1) en vez de cortar con -frames:v, que también cortaba el audio a 0,02 s.
        cmd += ["-f", "lavfi", "-i", "color=c=red:s=64x64:r=1:d=1", "-map", "0:a", "-map", "1:v",
                "-c:v", "mjpeg", "-disposition:v", "attached_pic"]
    meta = {"title": title, "artist": artist, "album": album, "track": str(track), "date": "1999"}
    if album_artist:
        meta["album_artist"] = album_artist
    for k, v in meta.items():
        cmd += ["-metadata", f"{k}={v}"]
    cmd += ["-c:a", {"flac": "flac", "mp3": "libmp3lame", "alac": "alac"}[codec], str(path)]
    subprocess.run(cmd, check=True, capture_output=True)


class Musica(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._t = tempfile.TemporaryDirectory()
        cls.dir = Path(cls._t.name)
        lib = cls.dir / "Música"
        cancion(lib / "Yello" / "Stella" / "1-02 Desire.flac", "Desire", "Yello", "Stella", 2, cover=True)
        cancion(lib / "Yello" / "Stella" / "1-01 Oh Yeah.flac", "Oh Yeah", "Yello", "Stella", 1, cover=True)
        cancion(lib / "Café Tacvba" / "Re" / "01 El Aparato.mp3", "El Aparato", "Café Tacvba", "Re", 1, codec="mp3")
        cancion(lib / "Varios" / "Mix" / "01 Uno.m4a", "Uno", "Alguien", "Mix", 1, codec="alac", album_artist="Varios")
        (lib / "_Playlists").mkdir()
        (lib / "_Playlists" / "Favoritas.m3u8").write_text(
            "#EXTM3U\n#EXTINF:-1,Café Tacvba - El Aparato\n../Café Tacvba/Re/01 El Aparato.mp3\n"
            "#EXTINF:-1,Yello - Oh Yeah\n../Yello/Stella/1-01 Oh Yeah.flac\n../No/Existe.flac\n")
        (lib / "Yello" / "Stella" / "notas.txt").write_text("no es música")
        cls.lib = lib

    @classmethod
    def tearDownClass(cls):
        cls._t.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.music = Music([str(self.lib)], d / "musica.json", d / "cache", log=lambda m: None)

    def tearDown(self):
        self.tmp.cleanup()

    def test_artistas_albumes_y_orden(self):
        self.assertEqual(self.music.scan(), 4)
        d = self.music.public()
        self.assertEqual([a["name"] for a in d["artists"]], ["Café Tacvba", "Varios", "Yello"])
        stella = next(a for a in d["albums"] if a["title"] == "Stella")
        self.assertEqual([d["tracks"][t]["title"] for t in stella["tracks"]], ["Oh Yeah", "Desire"])   # por número
        self.assertEqual(stella["year"], 1999)
        mix = next(a for a in d["albums"] if a["title"] == "Mix")
        self.assertEqual(mix["artist"], "Varios")                      # el artista del álbum, no el de la canción
        self.assertEqual(d["tracks"][mix["tracks"][0]]["artist"], "Alguien")
        self.assertNotIn("path", json.dumps(d))                         # nunca se mandan rutas

    def test_listas_m3u8_con_acentos(self):
        self.music.scan()
        d = self.music.public()
        self.assertEqual(len(d["playlists"]), 1)
        fav = d["playlists"][0]
        self.assertEqual(fav["title"], "Favoritas")
        self.assertEqual([d["tracks"][t]["title"] for t in fav["tracks"]], ["El Aparato", "Oh Yeah"])

    def test_solo_se_leen_otra_vez_los_que_cambian(self):
        self.music.scan()
        calls = []
        self.music.prober = lambda p: calls.append(p) or None
        self.music.scan(force=True)
        self.assertEqual(calls, [])
        other = Music([str(self.lib)], self.music.data_file, self.music.cache, log=lambda m: None)
        other.prober = self.music.prober
        self.assertEqual(other.scan(), 4)   # lo leído se guardó en musica.json
        self.assertEqual(calls, [])

    def test_recien_arrancado_ya_encuentra_las_canciones(self):
        # Sin que nadie haya abierto Música (sin public()), «Escuchar en la TV» ya encuentra la canción.
        fresh = Music([str(self.lib)], self.music.data_file, self.music.cache, log=lambda m: None)
        self.music.scan()
        tid = next(iter(self.music.public()["tracks"]))
        self.assertEqual(fresh.track(tid)["id"], tid)

    def test_portada(self):
        self.music.scan()
        d = self.music.public()
        stella = next(a for a in d["albums"] if a["title"] == "Stella")
        p = self.music.art(stella["id"])
        self.assertTrue(p and p.exists() and p.stat().st_size > 0)
        re_ = next(a for a in d["albums"] if a["title"] == "Re")
        self.assertIsNone(self.music.art(re_["id"]))                    # sin portada
        (self.lib / "Café Tacvba" / "Re" / "cover.jpg").write_bytes(p.read_bytes())
        try:
            self.assertTrue(self.music.art(re_["id"]))                  # la de la carpeta
        finally:
            (self.lib / "Café Tacvba" / "Re" / "cover.jpg").unlink()

    def test_audio_tal_cual_o_convertido(self):
        self.music.scan()
        d = self.music.public()
        by_title = {t["title"]: t["id"] for t in d["tracks"].values()}
        path, kind = self.music.audio(by_title["El Aparato"])
        self.assertTrue(path.endswith(".mp3"))
        self.assertEqual(kind, "audio/mpeg")
        path, kind = self.music.audio(by_title["Oh Yeah"])             # FLAC -> AAC en la caché
        self.assertEqual(kind, "audio/mp4")
        codec = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_name",
                                "-of", "csv=p=0", path], capture_output=True, text=True).stdout.strip()
        self.assertEqual(codec, "aac")
        self.assertEqual(self.music.audio(by_title["Oh Yeah"])[0], path)   # la segunda vez, de la caché
        self.assertIsNone(self.music.audio("noexiste"))


class Falso(cine.App):
    def __init__(self, music, tmp):
        self.music = music
        self.music_sessions = {}
        self.queue = PlayQueue(Path(tmp) / "cola.json")
        self.roku = mock.Mock()
        self.keep_awake = mock.Mock()
        self.server_url = "http://x"
        self.refreshed = 0

    def tell_tv_to_refresh(self):
        self.refreshed += 1


class EnLaApp(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        Musica.setUpClass()
        self.addCleanup(Musica.tearDownClass)
        d = Path(self._t.name)
        self.music = Music([str(Musica.lib)], d / "musica.json", d / "cache", log=lambda m: None)
        self.app = Falso(self.music, d)
        quiet = mock.patch.object(cine, "say", lambda m: None)
        quiet.start()
        self.addCleanup(quiet.stop)
        self.ids = {t["title"]: t["id"] for t in self.music.public()["tracks"].values()}

    def tearDown(self):
        # music_tv deja convirtiendo la canción en segundo plano: se espera a que termine antes de borrar la carpeta.
        time.sleep(0.3)
        for _ in range(200):
            if not self.music.converting:
                break
            time.sleep(0.05)
        self._t.cleanup()

    def test_escuchar_en_la_tv(self):
        r = self.app.music_tv([self.ids["Oh Yeah"], self.ids["Desire"], "noexiste"], 1)
        self.assertEqual(r, {"ok": True, "count": 2})
        sid = self.app.roku.play.call_args[0][0].split(":", 1)[1]
        s = self.app.music_session(sid)
        self.assertEqual((s["index"], [t["title"] for t in s["tracks"]]), (1, ["Oh Yeah", "Desire"]))
        self.assertTrue(s["tracks"][0]["url"].startswith("/music/"))
        self.assertEqual(s["start"], 0)
        self.app.music_tv([self.ids["Oh Yeah"]], 0, start=95)   # desde la web, en el segundo donde iba
        sid = self.app.roku.play.call_args[0][0].split(":", 1)[1]
        self.assertEqual(self.app.music_session(sid)["start"], 95)
        self.assertEqual(self.app.music_session("otra")["ok"], False)
        self.assertEqual(self.app.music_tv(["noexiste"])["ok"], False)

    def _con_store(self):
        d = Path(self._t.name)
        self.app.store = Store(d / "progreso.json")
        self.app.roku.player.return_value = None
        self.app.roku.ip = "192.0.2.1"
        self.app._player_lock = threading.Lock()
        self.app._player = (0.0, None)
        self.app.library = mock.Mock(items={})   # para /api/status
        self.app.iphone_url = None
        self.app.dubbing = mock.Mock(current=None)
        return d

    def test_la_musica_en_la_tv_se_ve_en_el_estado_y_no_deja_avance(self):
        d = self._con_store()
        tid = self.ids["Desire"]
        httpd = serve(self.app, 0)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.shutdown)
        base = f"http://127.0.0.1:{httpd.server_address[1]}"

        def post(path, body):
            req = urllib.request.Request(base + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
            return json.loads(urllib.request.urlopen(req).read())

        def status():
            return json.loads(urllib.request.urlopen(base + "/api/status").read())["playing"]

        self.assertIsNone(status())
        post("/api/progress", {"id": "track:" + tid, "p": 90, "d": 200, "ev": "tick", "state": "play",
                               "song": {"i": 1, "n": 3}})
        p = status()
        t = self.music.track(tid)
        self.assertEqual((p["kind"], p["title"], p["state"]), ("music", f"{t['title']} · {t['artist']}", "play"))
        self.assertEqual((p["position"], p["duration"], p["index"], p["count"], p["prev"], p["next"]),
                         (90, 200, 1, 3, True, True))
        self.assertEqual(p["poster"], f"/music/art/{t['album_id']}.jpg")
        # primera y última de la lista: solo uno de los dos botones
        post("/api/progress", {"id": "track:" + tid, "p": 1, "d": 200, "ev": "start", "song": {"i": 0, "n": 3}})
        self.assertEqual((status()["prev"], status()["next"]), (False, True))
        post("/api/progress", {"id": "track:" + tid, "p": 1, "d": 200, "ev": "tick", "state": "pause",
                               "song": {"i": 2, "n": 3}})
        self.assertEqual((status()["prev"], status()["next"], status()["state"]), (True, False, "pause"))
        # nada de esto entra a «Seguir viendo» ni al historial, ni se guarda en disco
        self.assertEqual(self.app.store.history(), [])
        self.assertEqual(self.app.store.watching(), [])
        self.assertFalse((d / "progreso.json").exists())
        post("/api/progress", {"id": "track:" + tid, "p": 190, "d": 200, "ev": "end"})   # terminó la lista
        self.assertIsNone(status())
        self.assertEqual(self.app.store.history(), [])
        # un video sigue guardándose como siempre
        post("/api/progress", {"id": "peli", "p": 600, "d": 5000, "ev": "tick"})
        self.assertEqual(self.app.store.watching(), [{"id": "peli", "p": 600}])

    def test_ordenes_de_la_musica_en_la_tv(self):
        self._con_store()
        self.assertEqual(self.app.control("song", dir=1)["ok"], False)   # nada suena
        self.app.store.report("track:" + self.ids["Desire"], 5, 200, "tick", song={"i": 0, "n": 2})
        self.assertEqual(self.app.control("song", dir=1), {"ok": True})
        self.app.roku.send.assert_called_with(cmd="song", dir=1)

    def test_una_cancion_a_la_fila(self):
        e = self.app.queue_entry("track", self.ids["Desire"])
        self.assertEqual(e["kind"], "track")
        self.assertEqual(e["title"], "Desire · Yello")
        self.assertTrue(e["thumb"].startswith("/music/art/"))
        with self.assertRaises(ValueError):
            self.app.queue_entry("track", "noexiste")
        r = self.app.queue_add_tracks([self.ids["Oh Yeah"], "noexiste", self.ids["Desire"]], front=True)
        self.assertEqual((r["ok"], r["added"]), (True, 2))
        self.assertEqual([e["title"] for e in self.app.queue.items()], ["Oh Yeah · Yello", "Desire · Yello"])

    def test_rutas(self):
        httpd = serve(self.app, 0)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.shutdown)
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        d = json.loads(urllib.request.urlopen(base + "/api/music").read())
        self.assertTrue(d["ok"] and d["enabled"])
        self.assertEqual(len(d["tracks"]), 4)
        t = d["tracks"][self.ids["Oh Yeah"]]
        r = urllib.request.urlopen(base + t["url"])
        self.assertEqual(r.headers["Content-Type"], "audio/mp4")
        self.assertGreater(len(r.read()), 1000)
        req = urllib.request.Request(base + t["url"], headers={"Range": "bytes=0-99"})
        r = urllib.request.urlopen(req)
        self.assertEqual((r.status, len(r.read())), (206, 100))   # se puede adelantar dentro de la canción
        r = urllib.request.urlopen(base + t["art"])
        self.assertEqual(r.headers["Content-Type"], "image/jpeg")
        body = json.dumps({"tracks": [self.ids["Desire"]], "shuffle": True}).encode()
        r = json.loads(urllib.request.urlopen(urllib.request.Request(base + "/api/music/tv", body,
                                                                     {"Content-Type": "application/json"})).read())
        self.assertEqual(r, {"ok": True, "count": 1})


if __name__ == "__main__":
    unittest.main()
