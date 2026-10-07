# YouTube en vivo (30 sep 2026, noche): reconocer transmisiones en vivo, buscar solo en vivo, canales de YouTube en
# «En vivo» (su transmisión de ahora, sin Chrome), enlaces vencidos que se renuevan con la misma variante y el avance
# que no se retoma. Sin red: yt-dlp y YouTube de mentira.
# python3 -m unittest discover -s pruebas -p "test_youtube_en_vivo.py"
import json, sys, tempfile, threading, time, unittest, urllib.error, urllib.request
from pathlib import Path
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mac"))
import youtube
from live import LiveChannels, LiveError
from server import serve
from store import Store
from youtube import YouTube, YouTubeError, info_from, live_url
from test_fase4_api import Falso

VID = "yZh3xsFqCt8"
OTRO = "nI725iVsyoQ"
CANAL = "UCZvDwoC3dXqaMKCv1C7a5zA"


def datos_en_vivo(vid=VID, canal=CANAL):
    return {"id": vid, "title": "DW Español | En vivo", "channel": "DW Español", "channel_id": canal,
            "live_status": "is_live", "concurrent_view_count": 1234, "duration": None,
            "formats": [{"protocol": "m3u8_native", "manifest_url": f"https://manifest/{vid}/master.m3u8", "http_headers": {}}]}


class Reconocer(unittest.TestCase):
    def test_dirección_de_la_transmisión_de_ahora(self):
        self.assertEqual(live_url(CANAL), f"https://www.youtube.com/channel/{CANAL}/live")
        self.assertEqual(live_url("@DWEspanol"), "https://www.youtube.com/@DWEspanol/live")
        self.assertEqual(live_url("https://www.youtube.com/@DWEspanol/videos"), "https://www.youtube.com/@DWEspanol/live")
        self.assertEqual(live_url(f"https://youtu.be/{VID}"), f"https://www.youtube.com/watch?v={VID}")
        self.assertIsNone(live_url("https://ejemplo.com/canal"))

    def test_datos_de_una_transmisión(self):
        info = info_from(VID, datos_en_vivo())
        self.assertEqual((info["live"], info["duration"], info["viewers"]), (True, 0, 1234))
        self.assertNotIn("live", info_from(OTRO, {"title": "Normal", "duration": 300}))
        e = youtube._clean_entry({"id": VID, "live_status": "is_live", "concurrent_view_count": 9})
        self.assertEqual((e["live"], e["viewers"], e["duration"]), (True, 9, 0))
        self.assertNotIn("live", youtube._clean_entry({"id": OTRO, "duration": 60}))


class Buscar(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.yt = YouTube(self._t.name, self._t.name, ytdlp="/nada")
        self.args = []

        def run(args, timeout=60):
            self.args.append(args)
            return {"entries": [{"id": f"vid{i:08d}", "title": f"R{i}", "live_status": "is_live"} for i in range(24)]}
        self.yt._run = run

    def tearDown(self):
        self._t.cleanup()

    def test_solo_en_vivo_con_el_filtro_de_youtube(self):
        videos, more = self.yt.search("noticias de hoy", live=True)
        self.assertTrue(more)
        self.assertTrue(all(v["live"] for v in videos))
        url = self.args[-1][-1]
        self.assertTrue(url.startswith("https://www.youtube.com/results?search_query=noticias+de+hoy&sp="), url)
        self.assertEqual(self.args[-1][:5], ["--flat-playlist", "--playlist-start", "1", "--playlist-end", "24"])
        self.yt.search("noticias de hoy", page=2, live=True)
        self.assertEqual(self.args[-1][2:5], ["25", "--playlist-end", "48"])


class TransmisionDeAhora(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.yt = YouTube(self._t.name, self._t.name, ytdlp="/nada")

    def tearDown(self):
        self._t.cleanup()

    def test_deja_resuelto_el_video(self):
        self.yt._run = lambda args, timeout=60: datos_en_vivo()
        info = self.yt.live_now("@DWEspanol")
        self.assertEqual((info["id"], info["channel_id"], info["live"]), (VID, CANAL, True))
        self.assertEqual(self.yt.cached_info(VID)["title"], "DW Español | En vivo")

    def test_canal_que_no_transmite(self):
        def run(args, timeout=60):
            raise YouTubeError("YouTube no dio el video: ERROR: [youtube:tab] @canalx: The channel is not currently live")
        self.yt._run = run
        with self.assertRaisesRegex(YouTubeError, "no está transmitiendo en vivo ahora"):
            self.yt.live_now("@canalx")
        self.yt._run = lambda args, timeout=60: {**datos_en_vivo(), "live_status": "was_live"}
        with self.assertRaisesRegex(YouTubeError, "no está transmitiendo"):
            self.yt.live_now("@canalx")
        with self.assertRaisesRegex(YouTubeError, "no parece un canal"):
            self.yt.live_now("https://ejemplo.com")

    def test_la_transmisión_se_vuelve_a_preguntar_cada_30_min(self):
        calls = []
        self.yt._run = lambda args, timeout=60: calls.append(1) or datos_en_vivo()
        self.yt.resolve(VID)
        self.yt.resolve(VID)
        self.assertEqual(len(calls), 1)
        self.yt.streams[VID]["at"] -= youtube.LIVE_TTL + 1
        self.yt.resolve(VID)
        self.assertEqual(len(calls), 2)


class EnlaceVencido(unittest.TestCase):
    """La lista de una variante caducó (403): se vuelve a pedir el video y se usa la misma variante (mismo itag)."""

    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.yt = YouTube(self._t.name, self._t.name, ytdlp="/nada")
        self.gen = [0]

        def run(args, timeout=60):
            self.gen[0] += 1
            d = datos_en_vivo()
            d["formats"][0]["manifest_url"] = f"https://manifest/g{self.gen[0]}/master.m3u8"
            return d
        self.yt._run = run
        self.fetched = []

        def fetch(url, headers, timeout=20):
            self.fetched.append(url)
            if url.endswith("master.m3u8"):
                g = url.split("/")[3]
                return (f'#EXTM3U\n#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="234",URI="https://m/{g}/itag/234/a.m3u8"\n'
                        f'#EXT-X-STREAM-INF:BANDWIDTH=1,RESOLUTION=1280x720,CODECS="avc1.4d401f"\n'
                        f'https://m/{g}/itag/232/v.m3u8\n').encode(), url
            if "/g1/" in url:
                raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)
            return b"#EXTM3U\n#EXTINF:5.0,\nhttps://seg/x.ts\n", url
        patcher = mock.patch.object(youtube, "fetch4", fetch)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self._t.cleanup()

    def test_misma_variante_en_la_lista_nueva(self):
        self.yt.playlist(VID)   # la maestra g1
        text = self.yt.playlist(VID, "https://m/g1/itag/232/v.m3u8")
        self.assertIn("/yt/" + VID + "/s/", text)
        self.assertIn("https://m/g2/itag/232/v.m3u8", self.fetched)
        self.assertEqual(self.yt.moved["https://m/g1/itag/232/v.m3u8"], "https://m/g2/itag/232/v.m3u8")
        n = len(self.fetched)
        self.yt.playlist(VID, "https://m/g1/itag/232/v.m3u8")   # la siguiente vez va directo a la nueva
        self.assertEqual(self.fetched[n:], ["https://m/g2/itag/232/v.m3u8"])
        self.yt.playlist(VID, "https://m/g1/itag/234/a.m3u8")   # también la pista de audio (URI de EXT-X-MEDIA)
        self.assertIn("https://m/g3/itag/234/a.m3u8", self.fetched)


class CanalesDeYouTube(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        tmp = Path(self._t.name)
        self.live = LiveChannels(tmp / "datos", tmp / "cache")
        self.now = {"vid": VID}
        self.asked = []

        def youtube_live(ref):
            self.asked.append(ref)
            if self.now["vid"] is None:
                raise LiveError("Ese canal no está transmitiendo en vivo ahora.")
            return {"id": self.now["vid"], "title": "Transmisión", "channel": "DW Español", "channel_id": CANAL}
        self.live.youtube_live = youtube_live
        self.live.youtube_thumb = lambda vid: b"jpg-" + vid.encode()
        self.live.chrome = None   # sin Chrome: los de YouTube no lo necesitan

    def tearDown(self):
        self._t.cleanup()

    def test_se_guarda_el_canal_no_el_video(self):
        ch = self.live.add("https://www.youtube.com/@DWEspanol/live")
        self.assertEqual((ch["name"], ch["youtube"], ch["page"]), ("DW Español", CANAL, f"https://www.youtube.com/channel/{CANAL}/live"))
        again = self.live.add(f"https://youtu.be/{VID}")   # otro enlace del mismo canal: el mismo canal
        self.assertEqual(again["id"], ch["id"])
        self.assertEqual(len(self.live.public()), 1)
        pub = self.live.public()[0]
        self.assertEqual((pub["host"], pub["youtube"]), ("YouTube", True))
        self.assertEqual((self.live.posters / f"live-{ch['id']}.jpg").read_bytes(), b"jpg-" + VID.encode())

    def test_transmisión_de_ahora_cada_20_min(self):
        cid = self.live.add("https://www.youtube.com/@DWEspanol")["id"]
        self.asked.clear()
        self.assertEqual(self.live.youtube_vid(cid), VID)
        self.assertEqual(self.asked, [])   # reciente: sin preguntar
        # La elegida sigue al aire: se queda esa (aunque el canal tenga otra principal).
        principal = self.live.youtube_live
        self.live.youtube_live = lambda ref: ({"id": VID, "channel_id": CANAL, "channel": "DW"} if VID in ref
                                              else principal(ref))
        self.now["vid"] = OTRO
        self.live.get(cid)["stream"]["at"] -= 21 * 60
        self.assertEqual(self.live.youtube_vid(cid), VID)
        # Ya terminó: la principal del canal.
        def solo_canal(ref):
            if "watch?v=" in ref:
                raise LiveError("Ese canal no está transmitiendo en vivo ahora.")
            return principal(ref)
        self.live.youtube_live = solo_canal
        self.live.get(cid)["stream"]["at"] -= 21 * 60
        self.assertEqual(self.live.youtube_vid(cid), OTRO)
        self.assertEqual((self.live.posters / f"live-{cid}.jpg").read_bytes(), b"jpg-" + OTRO.encode())
        self.now["vid"] = None
        with self.assertRaisesRegex(LiveError, "no está transmitiendo"):
            self.live.youtube_vid(cid, force=True)

    def test_un_canal_que_no_transmite_no_se_agrega(self):
        self.now["vid"] = None
        with self.assertRaisesRegex(LiveError, "no está transmitiendo"):
            self.live.add("https://www.youtube.com/@x")
        self.assertEqual(self.live.public(), [])


class Avance(unittest.TestCase):
    def test_en_vivo_entra_al_historial_como_vista(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = Store(Path(tmp) / "progreso.json")
            s.report(f"yt:{VID}", 600, 0, "tick", live=True)
            self.assertEqual(s.progress[f"yt:{VID}"]["p"], 0)   # no se retoma: no sale en «Seguir viendo»
            s.report(f"yt:{OTRO}", 600, 3000, "tick")
            self.assertEqual(s.progress[f"yt:{OTRO}"]["p"], 600)


class Rutas(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        tmp = Path(self._t.name)
        self.app = Falso(self._t.name)
        self.app.live = LiveChannels(tmp / "datos", tmp / "cache")
        self.app.live.youtube_live = lambda ref: {"id": VID, "title": "T", "channel": "DW Español", "channel_id": CANAL}
        self.app.live.youtube_thumb = lambda vid: None
        self.app.keep_awake = mock.Mock()
        self.app.youtube.playlist = lambda vid, url=None: f"#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1\n/yt/{vid}/m/abc.m3u8\n"
        self.server = serve(self.app, 0)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self._t.cleanup()

    def test_el_canal_de_youtube_se_ve_por_live(self):
        cid = self.app.live.add("https://www.youtube.com/@DWEspanol")["id"]
        with urllib.request.urlopen(f"{self.base}/live/{cid}/index.m3u8", timeout=5) as r:
            text = r.read().decode()
        self.assertIn(f"/yt/{VID}/m/abc.m3u8", text)
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(f"{self.base}/live/{cid}/s/x.ts", timeout=5)
        self.assertEqual(e.exception.code, 404)
        e.exception.close()

    def test_avance_de_un_en_vivo(self):
        self.app.youtube.streams[VID] = {"master": "", "headers": {}, "at": time.time(),
                                         "info": {"id": VID, "title": "T", "live": True}}
        req = urllib.request.Request(f"{self.base}/api/progress", json.dumps({"id": f"yt:{VID}", "p": 900, "d": 0}).encode(),
                                     {"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=5).read()
        self.assertEqual(self.app.store.progress[f"yt:{VID}"]["p"], 0)


if __name__ == "__main__":
    unittest.main()
