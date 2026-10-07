# Pruebas sin red de canales ocultos y anclados (mac/ytaccount.py, mac/cine.py y las rutas de mac/server.py).
# Uso: python3 -m unittest discover -s pruebas -p 'test_canales_ocultos.py'
import json, sys, tempfile, threading, time, unittest, urllib.request
from unittest import mock
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mac"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import takeout_de_prueba as gen
import cine
from mylists import MyLists
from server import serve
from store import Store
from playqueue import PlayQueue
from youtube import YouTube, YouTubeError, parse_related
from ytaccount import YouTubeAccount
from test_ytaccount import GOOGLE, MKBHD, FCC, atom

OTRO = "UC" + "otro" * 5 + "xy"          # un canal al que no está suscrito


def vid(n):
    return f"vid{n:08d}"[:11]


def video(n, cid="", channel="C"):
    v = {"id": vid(n), "title": f"Video {n}", "channel": channel, "duration": 600, "thumb": ""}
    if cid:
        v["channel_id"] = cid
    return v


class Base(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.dir = Path(self._t.name)
        gen.build_all(self.dir / "zips")
        (self.dir / "datos").mkdir()
        self.acc = YouTubeAccount(self.dir / "datos", self.dir, log=lambda m: None)
        self.acc.pause = self.acc.retry_pause = 0
        self.acc.import_zip(self.dir / "zips" / "takeout-en.zip")
        self.subs = {s["id"]: s["title"] for s in self.acc.subscriptions()}
        quiet = mock.patch.object(cine, "say", lambda m: None)   # sin mensajes del servicio en la salida
        quiet.start()
        self.addCleanup(quiet.stop)

    def tearDown(self):
        self._t.cleanup()

    def ids(self):
        return [c["id"] for c in self.acc.channels()]


class OcultarYAnclar(Base):
    def test_el_takeout_de_prueba_trae_los_canales_que_se_usan(self):
        self.assertTrue({GOOGLE, MKBHD, FCC} <= set(self.subs), self.subs)
        self.assertNotIn(OTRO, self.subs)

    def test_ocultar_y_volver_a_mostrar(self):
        self.acc.hide_channel(MKBHD, "Marques Brownlee")
        self.assertNotIn(MKBHD, self.ids())
        self.assertEqual(self.acc.hidden_channels(), [{"id": MKBHD, "title": "Marques Brownlee"}])
        self.assertEqual(self.acc.channel_flags(MKBHD), {"pinned": False, "hidden": True})
        self.acc.unhide_channel(MKBHD)
        self.assertIn(MKBHD, self.ids())
        self.assertEqual(self.acc.hidden_channels(), [])
        self.acc.unhide_channel(MKBHD)   # dos veces no pasa nada

    def test_ocultos_el_mas_reciente_primero_y_titulo_de_la_suscripcion(self):
        self.acc.hide_channel(GOOGLE)            # sin título: toma el de la suscripción
        time.sleep(0.01)
        self.acc.hide_channel(FCC, "freeCodeCamp")
        self.assertEqual(self.acc.hidden_channels(), [{"id": FCC, "title": "freeCodeCamp"},
                                                      {"id": GOOGLE, "title": self.subs[GOOGLE]}])

    def test_anclados_primero_en_el_orden_en_que_se_anclaron(self):
        self.assertEqual(self.acc.pin_channel(FCC, "", True), True)
        time.sleep(0.01)
        self.acc.pin_channel(GOOGLE, "", True)
        chans = self.acc.channels()
        self.assertEqual([c["id"] for c in chans[:2]], [FCC, GOOGLE])
        self.assertEqual([c["pinned"] for c in chans], [True, True] + [False] * (len(chans) - 2))
        self.assertEqual(len(chans), len(self.subs))   # sin repetir
        rest = [c["title"].lower() for c in chans[2:]]
        self.assertEqual(rest, sorted(rest))            # el resto, como siempre (por nombre)
        time.sleep(0.01)
        self.acc.pin_channel(FCC, "", True)             # volver a anclar no lo mueve
        self.assertEqual(self.ids()[:2], [FCC, GOOGLE])

    def test_desanclar(self):
        self.acc.pin_channel(MKBHD, "", True)
        self.assertEqual(self.acc.pin_channel(MKBHD, "", False), False)
        self.assertFalse(any(c["pinned"] for c in self.acc.channels()))
        self.assertIn(MKBHD, self.ids())   # sigue suscrito

    def test_canal_anclado_que_no_esta_en_las_suscripciones(self):
        self.acc.pin_channel(OTRO, "Canal Nuevo", True)
        first = self.acc.channels()[0]
        self.assertEqual((first["id"], first["title"], first["pinned"]), (OTRO, "Canal Nuevo", True))
        self.assertEqual(first["url"], f"https://www.youtube.com/channel/{OTRO}")
        self.acc.pin_channel(OTRO, "", False)
        self.assertNotIn(OTRO, self.ids())   # desanclado y sin suscripción: ya no sale

    def test_ocultar_un_anclado_lo_desancla_y_anclar_un_oculto_lo_muestra(self):
        self.acc.pin_channel(GOOGLE, "", True)
        self.acc.hide_channel(GOOGLE)
        self.assertNotIn(GOOGLE, self.ids())
        self.assertEqual(self.acc.channel_flags(GOOGLE), {"pinned": False, "hidden": True})
        self.acc.pin_channel(GOOGLE, "", True)
        self.assertEqual(self.acc.channel_flags(GOOGLE), {"pinned": True, "hidden": False})
        self.assertEqual(self.ids()[0], GOOGLE)

    def test_id_que_no_es_de_canal(self):
        for bad in ("", "@mkbhd", "UCcorto", "https://www.youtube.com/@mkbhd"):
            with self.assertRaises(ValueError):
                self.acc.hide_channel(bad)
            with self.assertRaises(ValueError):
                self.acc.pin_channel(bad, "", True)

    def test_reimportar_el_takeout_no_los_pierde(self):
        self.acc.hide_channel(MKBHD)
        self.acc.pin_channel(FCC, "", True)
        self.acc.pin_channel(OTRO, "Canal Nuevo", True)
        self.acc.import_zip(self.dir / "zips" / "takeout-es.zip")   # otro Takeout (trae a MKBHD otra vez)
        self.assertNotIn(MKBHD, self.ids())
        self.assertEqual(self.ids()[:2], [FCC, OTRO])
        otra = YouTubeAccount(self.dir / "datos", self.dir, log=lambda m: None)   # y sobreviven a reiniciar
        self.assertEqual([c["id"] for c in otra.channels()][:2], [FCC, OTRO])
        self.assertEqual(otra.hidden_channels()[0]["id"], MKBHD)
        otra.import_zip(self.dir / "zips" / "takeout-en.zip")
        self.assertEqual(otra.channel_flags(MKBHD)["hidden"], True)
        saved = json.loads((self.dir / "datos" / "youtube_cuenta.json").read_text())
        self.assertEqual(set(saved["hidden"]), {MKBHD})
        self.assertEqual(set(saved["pinned"]), {FCC, OTRO})
        self.assertEqual(set(saved["pinned"][OTRO]), {"title", "at"})

    def test_saber_si_un_video_es_de_un_canal_oculto(self):
        self.acc.hide_channel(MKBHD, "Marques Brownlee")
        hidden = self.acc.hidden_check()
        self.assertTrue(hidden({"channel_id": MKBHD}))
        self.assertTrue(hidden({"channel_url": f"https://www.youtube.com/channel/{MKBHD}"}))   # historial del Takeout
        self.assertTrue(hidden({"channel": "marques  brownlee"}))       # sin id: por el nombre exacto
        self.assertFalse(hidden({"channel_id": GOOGLE, "channel": "Marques Brownlee"}))   # el id manda
        self.assertFalse(hidden({"channel": "Marques"}))
        self.assertFalse(hidden({}))


class Revision(Base):
    def setUp(self):
        super().setUp()
        self.calls = []
        self.feeds = {
            GOOGLE: atom(GOOGLE, "Google for Developers", [("g_new", "Nuevo G", "2025-09-10T10:00:00+00:00", False)]),
            MKBHD: atom(MKBHD, "Marques Brownlee", [("m_mid", "Medio M", "2025-09-05T10:00:00+00:00", False)]),
            OTRO: atom(OTRO, "Canal Nuevo", [("o_new", "Del anclado", "2025-09-11T10:00:00+00:00", False)]),
        }

        def fetch(url):
            cid = url.split("channel_id=")[1]
            self.calls.append(cid)
            if cid not in self.feeds:
                raise OSError("sin red")
            return self.feeds[cid]
        self.acc.fetch = fetch
        self.acc.page_fetch = lambda url: (_ for _ in ()).throw(OSError("sin red"))

    def test_los_ocultos_no_se_revisan_y_los_anclados_si(self):
        self.acc.hide_channel(MKBHD)
        self.acc.pin_channel(OTRO, "Canal Nuevo", True)
        r = self.acc.refresh_feeds()
        self.assertNotIn(MKBHD, self.calls)
        self.assertIn(OTRO, self.calls)
        self.assertEqual(r["channels"], len(self.subs))   # 5 suscripciones - 1 oculta + 1 anclada
        self.assertEqual([v["id"] for v in self.acc.new_videos()], ["o_new", "g_new"])

    def test_ocultar_despues_de_revisar_quita_sus_videos_de_nuevos(self):
        self.acc.refresh_feeds()
        self.assertIn("m_mid", [v["id"] for v in self.acc.new_videos()])
        self.acc.hide_channel(MKBHD)
        self.assertNotIn("m_mid", [v["id"] for v in self.acc.new_videos()])
        self.acc.unhide_channel(MKBHD)
        self.assertIn("m_mid", [v["id"] for v in self.acc.new_videos()])   # lo ya leído vuelve a salir

    def test_leer_solo_el_canal_recien_anclado(self):
        self.acc.pin_channel(OTRO, "Canal Nuevo", True)
        self.assertTrue(self.acc.needs_refresh(OTRO))
        self.assertTrue(self.acc.refresh_channel(OTRO))
        self.assertEqual(self.calls, [OTRO])
        self.assertFalse(self.acc.needs_refresh(OTRO))
        self.assertEqual([v["id"] for v in self.acc.new_videos()], ["o_new"])
        self.assertFalse(self.acc.refresh_channel("@nada"))
        with self.acc.refreshing:   # si ya se están revisando todos, no se cruza
            self.assertFalse(self.acc.refresh_channel(OTRO))


class Falso(cine.App):
    """App sin arrancar nada: la cuenta de prueba, relacionados a mano y una TV que no existe."""

    def __init__(self, tmp, account):
        self.store = Store(Path(tmp) / "progreso.json")
        self.lists = MyLists(Path(tmp) / "listas.json")   # Favoritos y listas de One TV
        self.youtube = YouTube(tmp, tmp, ytdlp="/nada")
        self.youtube.related = lambda v: self.relacionados.get(v, [])
        self.relacionados = {}
        self.account = account
        self.queue = PlayQueue(Path(tmp) / "cola.json")
        self._because, self._because_busy, self._because_lock = None, False, threading.Lock()
        self.refreshed = 0

    def tell_tv_to_refresh(self):
        self.refreshed += 1


class EnLaApp(Base):
    def setUp(self):
        super().setUp()
        self.app = Falso(self.dir, self.acc)
        self.acc.refresh_channel = lambda cid: True   # sin red

    def ver(self, n, t, **rec):
        self.app.store.progress[f"yt:{vid(n)}"] = {"p": 0, "t": t}
        self.app.youtube.history.insert(0, {**video(n), **rec, "t": t})

    def test_porque_viste_sin_canales_ocultos(self):
        self.ver(1, 100)
        self.app.relacionados = {vid(1): [video(10, MKBHD), video(11, GOOGLE), video(12, channel="Marques Brownlee"),
                                          video(13)]}
        self.acc.hide_channel(MKBHD, "Marques Brownlee")
        with mock.patch.object(cine, "BECAUSE_MIN", 1):
            g = self.app._compute_because()
        self.assertEqual([v["id"] for v in g[0]["videos"]], [vid(11), vid(13)])

    def test_porque_viste_ya_calculado_se_filtra_al_ocultar(self):
        self.ver(1, 100)
        self.app._because = {"at": time.time(), "seeds": [vid(1)],
                             "data": [{"seed": {"id": vid(1), "title": "Video 1"}, "videos": [video(10, MKBHD), video(11, GOOGLE)]},
                                      {"seed": {"id": vid(2), "title": "Video 2"}, "videos": [video(12, MKBHD)]}]}
        self.acc.hide_channel(MKBHD)
        got = self.app.yt_because()
        self.assertEqual([[v["id"] for v in x["videos"]] for x in got], [[vid(11)]])   # el grupo vacío no sale
        self.assertEqual(len(self.app._because["data"][0]["videos"]), 2)   # lo guardado no se toca

    def test_porque_viste_no_parte_de_un_video_de_un_canal_oculto(self):
        self.ver(1, 100, channel="Otro")
        self.ver(2, 200, channel="Marques Brownlee", channel_id=MKBHD)
        self.acc.history = [{"id": vid(3), "title": "Del Takeout", "channel": "MB",
                             "channel_url": f"https://www.youtube.com/channel/{MKBHD}", "t": 1},
                            {"id": vid(4), "title": "Otro del Takeout", "channel": "X", "t": 1}]
        self.acc.hide_channel(MKBHD)
        self.assertEqual([s["id"] for s in self.app._because_seeds()], [vid(1), vid(4)])

    def test_reproduccion_continua_se_salta_los_canales_ocultos(self):
        self.app.store.prefs["ytAutoplay"] = True
        self.app.relacionados = {vid(1): [video(10, MKBHD), video(11, channel="Marques Brownlee"), video(12, GOOGLE)]}
        self.acc.hide_channel(MKBHD, "Marques Brownlee")
        self.assertEqual(self.app.youtube_next(f"yt:{vid(1)}")["id"], vid(12))

    def test_inicio_y_suscripciones_con_los_canales(self):
        self.acc.pin_channel(OTRO, "Canal Nuevo", True)
        self.acc.hide_channel(MKBHD)
        home = self.app.yt_home()
        self.assertEqual(home["channels"], self.acc.channels())
        self.assertEqual(home["channels"][0]["id"], OTRO)
        self.assertNotIn(MKBHD, [c["id"] for c in home["channels"]])

    def test_pagina_del_canal_dice_si_esta_anclado_u_oculto(self):
        self.app.youtube.channel = lambda ref: {"id": GOOGLE, "title": "Google", "videos": []}
        self.assertEqual({k: self.app.yt_channel(GOOGLE)[k] for k in ("ok", "pinned", "hidden")},
                         {"ok": True, "pinned": False, "hidden": False})
        self.acc.pin_channel(GOOGLE, "", True)
        self.assertTrue(self.app.yt_channel("@google")["pinned"])   # por @usuario: con el id que dio YouTube
        self.acc.hide_channel(GOOGLE)
        self.assertEqual({k: self.app.yt_channel(GOOGLE)[k] for k in ("pinned", "hidden")}, {"pinned": False, "hidden": True})

        def falla(ref):
            raise YouTubeError("YouTube no dio el video: 404")
        self.app.youtube.channel = falla
        r = self.app.yt_channel(GOOGLE)   # aunque YouTube no responda, se puede volver a mostrar o desanclar
        self.assertEqual((r["ok"], r["hidden"], r["pinned"]), (False, True, False))

    def test_acciones_de_la_app(self):
        self.assertEqual(self.app.yt_channel_pin(OTRO, "Canal Nuevo", True), {"ok": True, "pinned": True})
        self.assertEqual(self.app.yt_channel_pin(OTRO, "", False), {"ok": True, "pinned": False})
        self.assertEqual(self.app.yt_channel_hide(MKBHD, "MB")["ok"], True)
        self.assertEqual(self.app.yt_channel_unhide(MKBHD), {"ok": True})
        self.assertGreaterEqual(self.app.refreshed, 4)   # la TV vuelve a leer sus datos
        bad = self.app.yt_channel_hide("nada")
        self.assertEqual(bad["ok"], False)
        self.assertTrue(bad["error"])
        self.assertEqual(self.app.yt_channel_pin("nada", "", True)["ok"], False)


class Rutas(Base):
    """El contrato por HTTP (el mismo que usa la TV)."""

    def setUp(self):
        super().setUp()
        self.app = Falso(self.dir, self.acc)
        self.acc.refresh_channel = lambda cid: True
        self.app.youtube.channel = lambda ref: {"id": ref, "title": "Canal", "videos": []}
        self.httpd = serve(self.app, 0)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        super().tearDown()

    def get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=5) as r:
            return json.loads(r.read())

    def post(self, path, body):
        req = urllib.request.Request(self.base + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read())

    def test_contrato(self):
        self.assertEqual(self.post("/api/yt/channel/pin", {"id": FCC, "title": "freeCodeCamp", "on": True}),
                         {"ok": True, "pinned": True})
        self.assertEqual(self.post("/api/yt/channel/pin", {"id": OTRO, "title": "Canal Nuevo", "on": True}),
                         {"ok": True, "pinned": True})
        self.assertEqual(self.post("/api/yt/channel/hide", {"id": MKBHD, "title": "Marques Brownlee"}),
                         {"ok": True, "id": MKBHD, "title": "Marques Brownlee"})
        subs = self.get("/api/yt/subscriptions")["channels"]
        self.assertEqual([(c["id"], c["pinned"]) for c in subs[:2]], [(FCC, True), (OTRO, True)])
        self.assertEqual(subs[1]["title"], "Canal Nuevo")
        self.assertNotIn(MKBHD, [c["id"] for c in subs])
        self.assertEqual(self.get("/api/yt/home")["channels"], subs)
        self.assertEqual(self.get("/api/yt/hidden"), {"channels": [{"id": MKBHD, "title": "Marques Brownlee"}]})
        ch = self.get(f"/api/yt/channel?id={MKBHD}")
        self.assertEqual((ch["ok"], ch["pinned"], ch["hidden"]), (True, False, True))
        self.assertTrue(self.get(f"/api/yt/channel?id={FCC}")["pinned"])
        self.assertEqual(self.post("/api/yt/channel/unhide", {"id": MKBHD}), {"ok": True})
        self.assertEqual(self.get("/api/yt/hidden"), {"channels": []})
        self.assertEqual(self.post("/api/yt/channel/pin", {"id": FCC, "on": False}), {"ok": True, "pinned": False})
        self.assertEqual(self.post("/api/yt/channel/pin", {"id": FCC, "on": "false"})["pinned"], False)
        self.assertEqual(self.post("/api/yt/channel/hide", {"id": "@nada"})["ok"], False)


class RelacionadosConCanal(unittest.TestCase):
    def test_parse_related_trae_el_id_del_canal(self):
        lockup = {"lockupViewModel": {"contentId": "hXI8RQYC36Q", "contentType": "LOCKUP_CONTENT_TYPE_VIDEO",
            "contentImage": {"thumbnailViewModel": {"overlays": [{"thumbnailBadgeViewModel": {"text": "4:01"}}]}},
            "metadata": {"lockupMetadataViewModel": {"title": {"content": "Canción"},
                "image": {"decoratedAvatarViewModel": {"rendererContext": {"commandContext": {"onTap": {"innertubeCommand": {
                    "browseEndpoint": {"browseId": MKBHD}}}}}}},
                "metadata": {"contentMetadataViewModel": {"metadataRows": [{"metadataParts": [{"text": {"content": "MB"}}]}]}}}}}}
        compact = {"compactVideoRenderer": {"videoId": "s5IIWKZr_2w", "title": {"simpleText": "Otra"},
            "lengthText": {"simpleText": "3:30"},
            "longBylineText": {"runs": [{"text": "Google", "navigationEndpoint": {"browseEndpoint": {"browseId": GOOGLE}}}]}}}
        sin = {"compactVideoRenderer": {"videoId": "JGwWNGJdvx8", "title": {"simpleText": "Sin canal"},
                                        "lengthText": {"simpleText": "3:30"}, "longBylineText": {"runs": [{"text": "X"}]}}}
        data = {"contents": {"twoColumnWatchNextResults": {"secondaryResults": {"results": [lockup, compact, sin]}}}}
        html = f"<script>var ytInitialData = {json.dumps(data)};</script>"
        got = parse_related(html)
        self.assertEqual([(v["id"], v["channel"], v.get("channel_id")) for v in got],
                         [("hXI8RQYC36Q", "MB", MKBHD), ("s5IIWKZr_2w", "Google", GOOGLE), ("JGwWNGJdvx8", "X", None)])


if __name__ == "__main__":
    unittest.main()
