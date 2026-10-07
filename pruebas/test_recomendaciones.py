# Pruebas sin red de las recomendaciones: «No me interesa», «Silenciar canal» desde un video y que «Porque viste…»
# solo traiga lo que tiene que ver. Uso: python3 -m unittest pruebas/test_recomendaciones.py
import json, sys, threading, unittest, urllib.request
from unittest import mock
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mac"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cine
from server import serve
from youtube import YouTubeError
from test_canales_ocultos import Base, Falso, OTRO, video, vid
from test_ytaccount import GOOGLE, MKBHD


class Recomendaciones(Base):
    def setUp(self):
        super().setUp()
        self.app = Falso(self.dir, self.acc)
        self.acc.refresh_channel = lambda cid: True

    def ver(self, n, t, **rec):
        self.app.store.progress[f"yt:{vid(n)}"] = {"p": 0, "t": t}
        self.app.youtube.history.insert(0, {**video(n), **rec, "t": t})

    def test_solo_lo_que_tiene_que_ver(self):
        self.ver(1, 100, title="Radiohead en vivo en Glastonbury", channel="Canal Música", channel_id=OTRO)
        self.app.relacionados = {vid(1): [
            {**video(10, "UC" + "x" * 22, "Ed Sheeran"), "title": "Shape of You (Official Music Video)"},   # lo popular
            {**video(11, OTRO, "Canal Música"), "title": "Otro concierto"},             # mismo canal que lo visto
            {**video(12, "UC" + "y" * 22, "Fans"), "title": "Radiohead: la historia"},  # palabras del título
            {**video(13, GOOGLE, "Google"), "title": "Algo de Google"},                # canal al que está suscrito
            {**video(14, "UC" + "z" * 22, "Noticias"), "title": "Presidenta en conferencia"},   # nada que ver
        ]}
        g = self.app._compute_because()
        self.assertEqual(len(g), 1)
        ids = [v["id"] for v in g[0]["videos"]]
        self.assertEqual(set(ids), {vid(11), vid(12), vid(13)})
        self.assertNotIn(vid(10), ids)
        self.assertEqual(ids[-1], vid(12))   # una palabra en común cuenta menos que un canal que sigue

    def test_canales_del_historial_del_takeout_cuentan(self):
        cid = "UC" + "h" * 22
        self.acc.history = [{"id": vid(90 + i), "title": "x", "channel": "Visto Seguido",
                             "channel_url": f"https://www.youtube.com/channel/{cid}", "t": i} for i in range(3)]
        ids, _ = self.acc.affinity()
        self.assertEqual(ids[cid], 2)
        self.assertEqual(ids[GOOGLE], 3)
        self.acc.hide_channel(GOOGLE)
        self.assertNotIn(GOOGLE, self.acc.affinity()[0])

    def test_grupo_con_pocos_videos_no_sale(self):
        self.ver(1, 100, channel="Uno")
        self.app.relacionados = {vid(1): [{**video(10, channel="Uno")}, {**video(11, channel="Uno")}]}
        self.assertEqual(self.app._compute_because(), [])

    def test_no_me_interesa(self):
        self.ver(1, 100, channel="Uno")
        self.app.relacionados = {vid(1): [video(n, channel="Uno") for n in (10, 11, 12, 13)]}
        self.assertEqual(self.app.yt_dismiss(vid(11)), {"ok": True})
        g = self.app._compute_because()
        self.assertEqual([v["id"] for v in g[0]["videos"]], [vid(10), vid(12), vid(13)])
        # lo ya calculado también lo deja de mostrar
        self.app._because = {"at": 1e12, "seeds": [vid(1)], "data": [{"seed": {"id": vid(1), "title": "V"},
                                                                       "videos": [video(11), video(12)]}]}
        with mock.patch.object(self.app, "_because_seeds", lambda count=3: [{"id": vid(1), "title": "V"}]):
            got = self.app.yt_because()
        self.assertEqual([v["id"] for v in got[0]["videos"]], [vid(12)])
        # ni la reproducción continua
        self.assertTrue(self.app._hidden_check()({"id": vid(11)}))
        # se puede deshacer
        self.app.yt_dismiss(vid(11), on=False)
        self.assertFalse(self.app._hidden_check()({"id": vid(11)}))
        self.assertEqual(self.app.yt_dismiss("nada")["ok"], False)

    def test_no_me_interesa_en_nuevos(self):
        self.acc.feeds = {GOOGLE: {"videos": [{"id": vid(20), "title": "A", "published": 2, "channel_id": GOOGLE},
                                              {"id": vid(21), "title": "B", "published": 1, "channel_id": GOOGLE}],
                                   "t": 1, "status": "ok"}}
        self.assertEqual([v["id"] for v in self.acc.new_videos()], [vid(20), vid(21)])
        self.acc.dismiss_video(vid(20))
        self.assertEqual([v["id"] for v in self.acc.new_videos()], [vid(21)])

    def test_silenciar_canal_desde_un_video(self):
        self.app.youtube.history.insert(0, {**video(5, MKBHD, "Marques Brownlee"), "t": 1})
        r = self.app.yt_channel_hide("", video=vid(5))
        self.assertEqual(r, {"ok": True, "id": MKBHD, "title": "Marques Brownlee"})
        self.assertIn(MKBHD, {h["id"] for h in self.acc.hidden_channels()})
        # un video que no se conoce: se le pregunta a YouTube
        self.app.youtube.resolve = lambda v: {"info": {"channel_id": GOOGLE, "channel": "Google"}}
        self.assertEqual(self.app.yt_channel_hide("", video=vid(6))["id"], GOOGLE)

        def falla(v):
            raise YouTubeError("sin red")
        self.app.youtube.resolve = falla
        r = self.app.yt_channel_hide("", video=vid(7))
        self.assertEqual(r["ok"], False)
        self.assertIn("sin red", r["error"])


class Rutas(Base):
    def setUp(self):
        super().setUp()
        self.app = Falso(self.dir, self.acc)
        self.httpd = serve(self.app, 0)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.addCleanup(self.httpd.shutdown)

    def post(self, path, body):
        req = urllib.request.Request(f"http://127.0.0.1:{self.httpd.server_address[1]}{path}",
                                     data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        return json.loads(urllib.request.urlopen(req, timeout=5).read())

    def test_contrato(self):
        self.assertEqual(self.post("/api/yt/dismiss", {"id": vid(3)}), {"ok": True})
        self.assertIn(vid(3), self.acc.dismissed)
        self.assertEqual(self.post("/api/yt/dismiss", {"id": vid(3), "on": False}), {"ok": True})
        self.assertNotIn(vid(3), self.acc.dismissed)
        self.app.youtube.history.insert(0, {**video(5, MKBHD, "MB"), "t": 1})
        self.assertEqual(self.post("/api/yt/channel/hide", {"video": vid(5)})["id"], MKBHD)


if __name__ == "__main__":
    unittest.main()
