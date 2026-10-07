# Pruebas sin red de la duración de los videos de YouTube: el caché (mac/ytdurations.py), el rellenador (límite de
# 1 video cada 3 s y 100 por hora, y el freno ante un bloqueo), la lectura de las páginas y su uso en la app.
# Uso: python3 -m unittest discover -s pruebas -p "test_duraciones.py"
import io, json, sys, tempfile, threading, unittest, urllib.error
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mac"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cine
from mylists import MyLists
import ytdurations
from library import Library
from playqueue import PlayQueue
from store import Store
from youtube import YouTube, fetch_durations, page_durations
from ytaccount import YouTubeAccount, parse_channel_page
from ytdurations import Blocked, DurationFiller, Durations
from test_ytaccount import MKBHD

HORA = 3600


def vid(n):
    return f"dur{n:08d}"[:11]


def pagina(data):
    return f"<html><script>var ytInitialData = {json.dumps(data)};</script></html>"


def panel(pares):
    """Página de una lista anónima (watch_videos): la lista al lado con la duración de cada video."""
    items = [{"playlistPanelVideoRenderer": {"videoId": v, "lengthText": {"simpleText": t}}} for v, t in pares]
    return pagina({"contents": {"twoColumnWatchNextResults": {"playlist": {"playlist": {"contents": items}}}}})


class Reloj:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


class Base(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.dir = Path(self._t.name)
        self.reloj = Reloj()

    def tearDown(self):
        self._t.cleanup()

    def cache(self):
        return Durations(self.dir / "youtube_duraciones.json", save_delay=0, clock=self.reloj)


class Cache(Base):
    def test_aprende_de_listas_y_diccionarios_y_sobrevive_a_un_reinicio(self):
        d = self.cache()
        self.assertEqual(d.learn([{"id": vid(1), "duration": 252}, {"id": vid(2), "duration": 0},
                                  {"id": "corto", "duration": 30}, {"id": vid(3), "duration": 12.7}]), 2)
        self.assertEqual(d.learn({vid(4): "3723", vid(5): None, vid(6): -3}), 1)
        self.assertEqual((d.get(vid(1)), d.get(vid(2)), d.get(vid(3)), d.get(vid(4)), d.get(vid(5))), (252, 0, 12, 3723, 0))
        otra = self.cache()
        self.assertEqual((otra.get(vid(1)), otra.get(vid(4)), otra.count()), (252, 3723, 3))

    def test_apply_pone_la_duracion_y_pide_las_que_faltan(self):
        d = self.cache()
        pedidos = []
        d.filler = type("F", (), {"want": lambda s, ids: pedidos.extend(ids), "blocked": lambda s: False})()
        d.learn({vid(1): 100})
        videos = [{"id": vid(1), "duration": 0}, {"id": vid(2)}, {"id": vid(3), "duration": 61},
                  {"id": vid(4), "private": True, "duration": 0}]
        self.assertIs(d.apply(videos), videos)
        self.assertEqual([v.get("duration") for v in videos], [100, 0, 61, 0])
        self.assertEqual(pedidos, [vid(2)])            # ni los que ya traen duración ni los privados
        self.assertEqual(d.get(vid(3)), 61)            # aprende la que venía en el video
        d.apply([{"id": vid(5)}], want=False)
        self.assertEqual(pedidos, [vid(2)])

    def test_lo_que_youtube_no_dio_se_reintenta_a_la_semana(self):
        d = self.cache()
        d.give_up([vid(1)])
        self.assertFalse(d.worth_asking(vid(1)))
        self.reloj.t += ytdurations.UNKNOWN_RETRY + 1
        self.assertTrue(d.worth_asking(vid(1)))
        d.learn({vid(1): 30})
        self.assertFalse(d.worth_asking(vid(1)))       # ya se sabe

    def test_tiene_un_tope_y_se_van_las_mas_viejas(self):
        viejo = ytdurations.MAX_KNOWN
        ytdurations.MAX_KNOWN = 3
        try:
            d = self.cache()
            d.learn({vid(i): 60 + i for i in range(5)})
            self.assertEqual(d.count(), 3)
            self.assertEqual((d.get(vid(0)), d.get(vid(4))), (0, 64))
        finally:
            ytdurations.MAX_KNOWN = viejo

    def test_archivo_danado_no_rompe(self):
        (self.dir / "youtube_duraciones.json").write_text("{no es json")
        self.assertEqual(self.cache().count(), 0)


class Rellenador(Base):
    def setUp(self):
        super().setUp()
        self.d = self.cache()
        self.pedidos = []          # (cuándo, ids)
        self.respuesta = None      # función(ids) -> {id: segundos}; por omisión, todos con 100 s
        self.f = self.nuevo()

    def nuevo(self):
        def fetch(ids):
            self.pedidos.append((self.reloj.t, list(ids)))
            return self.respuesta(ids) if self.respuesta else {v: 100 for v in ids}
        return DurationFiller(self.d, fetch, log=lambda m: None, clock=self.reloj, background=False)

    def test_pide_varios_en_una_sola_peticion_y_aprende_de_regalo(self):
        self.respuesta = lambda ids: {**{v: 200 for v in ids[:-1]}, vid(99): 42}   # el último no existe
        self.f.want([vid(i) for i in range(5)])
        self.assertEqual(self.f.step(), "ok")
        self.assertEqual(len(self.pedidos), 1)
        self.assertEqual(self.pedidos[0][1], [vid(i) for i in range(5)])
        self.assertEqual((self.d.get(vid(0)), self.d.get(vid(99))), (200, 42))
        self.assertFalse(self.d.worth_asking(vid(4)))   # no vino: se reintenta a la semana
        self.assertEqual(self.f.pending, [])

    def test_lo_nuevo_que_se_muestra_va_primero_sin_repetir(self):
        self.f.want([vid(1), vid(2)])
        self.f.want([vid(3), vid(2)])                  # el 2 ya esperaba: conserva su lugar
        self.assertEqual(self.f.pending, [vid(3), vid(1), vid(2)])
        self.d.learn({vid(3): 5})
        self.f.want([vid(3)])                          # ya se sabe: no se pide
        self.assertEqual(self.f.pending, [vid(3), vid(1), vid(2)])
        self.f.step()
        self.assertEqual(self.pedidos[0][1], [vid(1), vid(2)])

    def test_un_video_cada_3_segundos(self):
        self.f.want([vid(i) for i in range(60)])
        self.assertEqual(self.f.step(), "ok")
        self.assertEqual(len(self.pedidos[0][1]), 50)   # lo más que cabe en una petición
        self.reloj.t += 149
        self.assertIsNone(self.f.step())               # 50 videos = 150 s
        self.assertEqual(int(self.f.wait()), 1)
        self.reloj.t += 1
        self.assertEqual(self.f.step(), "ok")
        self.assertEqual(len(self.pedidos[1][1]), 10)

    def test_no_mas_de_100_por_hora(self):
        self.f.want([vid(i) for i in range(300)])
        for _ in range(2):
            self.assertEqual(self.f.step(), "ok")
            self.reloj.t += 150
        self.assertEqual(self.f.used(), 100)
        self.assertIsNone(self.f.step())
        self.assertAlmostEqual(self.f.wait(), HORA - 300, delta=1)   # hasta que la primera petición salga de la hora
        self.reloj.t += HORA - 300
        self.assertEqual(self.f.step(), "ok")
        self.assertEqual(len(self.pedidos[-1][1]), 50)

    def test_simulacion_larga_nunca_pasa_los_limites(self):
        """Tres horas con videos nuevos a cada rato y el hilo despertando cada segundo."""
        n = 0
        for s in range(3 * HORA):
            if s % 7 == 0:
                self.f.want([vid(n + k) for k in range(3)])
                n += 3
            self.f.step()
            self.reloj.t += 1
        self.assertGreater(len(self.pedidos), 3)
        for i, (t, ids) in enumerate(self.pedidos):
            en_la_hora = sum(len(x) for tt, x in self.pedidos if t - HORA < tt <= t)
            self.assertLessEqual(en_la_hora, 100)
            if i:
                antes, ids_antes = self.pedidos[i - 1]
                self.assertGreaterEqual(t - antes, 3 * len(ids_antes))
        self.assertLessEqual(sum(len(x) for _, x in self.pedidos), 300)

    def test_si_youtube_frena_no_se_le_pide_nada_en_6_horas(self):
        def frena(ids):
            raise Blocked("pide confirmar que no es un bot")
        self.respuesta = frena
        self.f.want([vid(1), vid(2)])
        self.assertEqual(self.f.step(), "blocked")
        self.assertTrue(self.f.blocked() and self.d.blocked())
        self.assertEqual(self.f.pending, [vid(1), vid(2)])   # se conserva lo pendiente
        self.assertEqual(self.d.eta([{"id": vid(1)}]), 0)     # frenado: la web no espera nada
        self.respuesta = None
        self.reloj.t += 6 * HORA - 1
        self.assertIsNone(self.f.step())
        # El freno sobrevive a un reinicio del servidor.
        self.d = self.cache()
        self.f = self.nuevo()
        self.f.want([vid(1)])
        self.assertIsNone(self.f.step())
        self.assertEqual(len(self.pedidos), 1)
        self.reloj.t += 2
        self.assertEqual(self.f.step(), "ok")

    def test_lo_pedido_en_la_ultima_hora_sobrevive_a_un_reinicio(self):
        self.f.want([vid(i) for i in range(100)])
        self.f.step()
        self.reloj.t += 150
        self.f.step()
        self.d = self.cache()
        self.f = self.nuevo()
        self.assertEqual(self.f.used(), 100)
        self.f.want([vid(500)])
        self.assertIsNone(self.f.step())

    def test_un_error_de_red_espera_15_minutos(self):
        def falla(ids):
            raise urllib.error.URLError("sin internet")
        self.respuesta = falla
        self.f.want([vid(1)])
        self.assertEqual(self.f.step(), "error")
        self.respuesta = None
        self.reloj.t += 15 * 60 - 1
        self.assertIsNone(self.f.step())
        self.reloj.t += 1
        self.assertEqual(self.f.step(), "ok")

    def test_eta_para_que_la_web_vuelva_a_preguntar(self):
        self.f.want([vid(1)])
        self.assertGreater(self.d.eta([{"id": vid(1), "duration": 0}]), 0)
        self.assertEqual(self.d.eta([{"id": vid(2), "duration": 0}]), 0)   # no se está pidiendo
        self.f.step()
        self.assertEqual(self.d.eta([{"id": vid(1), "duration": 0}]), 0)

    def test_el_hilo_de_fondo_pide_solo(self):
        listo = threading.Event()

        def fetch(ids):
            listo.set()
            return {v: 77 for v in ids}
        f = DurationFiller(self.cache(), fetch, log=lambda m: None, gather=0)
        f.want([vid(1)])
        self.assertTrue(listo.wait(5))
        for _ in range(100):
            if f.durations.get(vid(1)):
                break
            threading.Event().wait(0.02)
        self.assertEqual(f.durations.get(vid(1)), 77)


class Paginas(unittest.TestCase):
    def test_lista_anonima_y_relacionados(self):
        lockup = {"lockupViewModel": {"contentId": "hXI8RQYC36Q", "contentType": "LOCKUP_CONTENT_TYPE_VIDEO",
                  "contentImage": {"thumbnailViewModel": {"overlays": [{"thumbnailOverlayBadgeViewModel": {
                      "thumbnailBadges": [{"thumbnailBadgeViewModel": {"text": "1:02:03"}}]}}]}}}}
        lista = {"lockupViewModel": {"contentId": "PLxxxxxxxxxx", "contentType": "LOCKUP_CONTENT_TYPE_PLAYLIST",
                 "contentImage": {"thumbnailBadgeViewModel": {"text": "12 videos"}}}}
        directo = {"compactVideoRenderer": {"videoId": "s5IIWKZr_2w", "lengthText": {"simpleText": "EN VIVO"}}}
        data = {"contents": {"twoColumnWatchNextResults": {
            "playlist": {"playlist": {"contents": [
                {"playlistPanelVideoRenderer": {"videoId": "GnmatfBhzyo", "lengthText": {"simpleText": "8:04"}}},
                {"playlistPanelVideoRenderer": {"videoId": "CJRLSuK8aoI", "lengthText": {"runs": [{"text": "1:56:10"}]}}}]}},
            "secondaryResults": {"results": [lockup, lista, directo,
                {"compactVideoRenderer": {"videoId": "JGwWNGJdvx8", "lengthText": {"simpleText": "3:30"}}}]}}}}
        self.assertEqual(page_durations(pagina(data)), {"GnmatfBhzyo": 484, "CJRLSuK8aoI": 6970, "hXI8RQYC36Q": 3723,
                                                        "JGwWNGJdvx8": 210})
        with self.assertRaises(ValueError):
            page_durations("<html>nada</html>")

    def test_fetch_durations_una_sola_pagina(self):
        urls = []

        def fetch(url):
            urls.append(url)
            return panel([("GnmatfBhzyo", "8:04")]).encode(), "https://www.youtube.com/watch?v=GnmatfBhzyo&list=TLGGx"
        self.assertEqual(fetch_durations(["GnmatfBhzyo", "XUQpFdQUlXM"], fetch), {"GnmatfBhzyo": 484})
        self.assertEqual(len(urls), 1)
        self.assertIn("watch_videos?video_ids=GnmatfBhzyo,XUQpFdQUlXM", urls[0])

    def test_fetch_durations_reconoce_el_bloqueo(self):
        def error(code, url="https://www.youtube.com/watch_videos"):
            def fetch(u):
                raise urllib.error.HTTPError(url, code, "x", {}, io.BytesIO(b""))
            return fetch
        with self.assertRaises(Blocked):
            fetch_durations([vid(1)], error(429))
        with self.assertRaises(Blocked):
            fetch_durations([vid(1)], error(403, "https://www.google.com/sorry/index?continue=x"))
        with self.assertRaises(urllib.error.HTTPError):   # otro error no es un bloqueo
            fetch_durations([vid(1)], error(500))
        with self.assertRaises(Blocked):
            fetch_durations([vid(1)], lambda u: (b"<html>captcha</html>", "https://www.google.com/sorry/index"))
        bot = pagina({"playabilityStatus": {"status": "LOGIN_REQUIRED",
                                            "reason": "Sign in to confirm you’re not a bot"}})
        with self.assertRaises(Blocked):
            fetch_durations([vid(1)], lambda u: (bot.encode(), "https://www.youtube.com/watch?v=x"))
        es = pagina({"reason": "Inicia sesión para confirmar que no eres un bot"})
        with self.assertRaises(Blocked):
            fetch_durations([vid(1)], lambda u: (es.encode(), "https://www.youtube.com/watch?v=x"))
        with self.assertRaises(ValueError):   # la página cambió: error normal (pausa corta), no bloqueo
            fetch_durations([vid(1)], lambda u: (b"<html></html>", "https://www.youtube.com/watch?v=x"))

    def test_pagina_del_canal_trae_la_duracion(self):
        def lockup(v, ago, badge):
            imagen = {"thumbnailViewModel": {"overlays": [{"thumbnailOverlayBadgeViewModel": {
                "thumbnailBadges": [{"thumbnailBadgeViewModel": {"text": badge}}]}}]}} if badge else {}
            return {"richItemRenderer": {"content": {"lockupViewModel": {
                "contentId": v, "contentType": "LOCKUP_CONTENT_TYPE_VIDEO", "contentImage": imagen,
                "metadata": {"lockupMetadataViewModel": {"title": {"content": "T"}, "metadata": {"contentMetadataViewModel": {
                    "metadataRows": [{"metadataParts": [{"text": {"content": "?"}, "accessibilityLabel": ago}]}]}}}}}}}}
        data = {"metadata": {"channelMetadataRenderer": {"title": "MKBHD"}}, "contents": {"items": [
            lockup("rayrrXot17M", "1 day ago", "12:34"), lockup("pOX1l1edBME", "hace 2 semanas", "1:02:03"),
            lockup("yyyyyyyyyyy", "hace 3 horas", "")]}}
        vids = parse_channel_page(pagina(data), MKBHD, now=2_000_000_000)
        self.assertEqual([(v["id"], v["duration"]) for v in vids],
                         [("rayrrXot17M", 754), ("pOX1l1edBME", 3723), ("yyyyyyyyyyy", 0)])


class Falso(cine.App):
    """App sin arrancar nada, con un rellenador que no pide nada a internet."""

    def __init__(self, tmp):
        self.store = Store(Path(tmp) / "progreso.json")
        self.lists = MyLists(Path(tmp) / "listas.json")   # Favoritos y listas de One TV
        self.youtube = YouTube(tmp, tmp, ytdlp="/nada")
        self.durations = self.youtube.durations
        self.durations.save_delay = 0
        self.pedidos = []
        self.filler = DurationFiller(self.durations, lambda ids: self.pedidos.append(list(ids)) or {},
                                     log=lambda m: None, background=False)
        self.queue = PlayQueue(Path(tmp) / "cola.json")
        self.queue.decorate = self._queue_with_durations
        self.account = YouTubeAccount(tmp, tmp, log=lambda m: None)
        self.account.durations = self.durations
        self.library = Library([str(tmp)], tmp)
        self._because, self._because_busy, self._because_lock = None, False, threading.Lock()


class EnLaApp(Base):
    def setUp(self):
        super().setUp()
        self.app = Falso(self.dir)

    def test_la_fila_trae_la_duracion_de_youtube(self):
        self.app.durations.learn({vid(1): 252})
        self.app.queue.add({"kind": "yt", "id": vid(1), "title": "Uno", "thumb": ""})
        self.app.queue.add({"kind": "yt", "id": vid(2), "title": "Dos", "thumb": ""})
        self.app.queue.add({"kind": "item", "id": "abc123abc123", "title": "Peli", "thumb": ""})
        q = self.app.queue.items()
        self.assertEqual([e.get("duration") for e in q], [252, 0, None])
        self.assertEqual(self.app.filler.pending, [vid(2)])
        self.assertNotIn("duration", json.loads((self.dir / "cola.json").read_text())[0])   # no se guarda en la fila

    def test_nuevos_de_tus_canales_y_filling(self):
        acc = self.app.account
        acc.feeds = {MKBHD: {"videos": [{"id": vid(1), "title": "A", "published": 3},
                                        {"id": vid(2), "title": "B", "published": 2, "duration": 61},
                                        {"id": vid(3), "title": "C", "published": 1}], "t": 1, "status": "ok"}}
        acc.pinned = {MKBHD: {"title": "MKBHD", "at": 1}}
        self.app.durations.learn({vid(3): 300})
        home = self.app.yt_home()
        self.assertEqual([v["duration"] for v in home["new"]], [0, 61, 300])
        self.assertEqual(self.app.filler.pending, [vid(1)])
        self.assertGreater(home["filling"], 0)
        self.app.filler.step()
        self.assertEqual(self.app.pedidos, [[vid(1)]])
        self.assertEqual(self.app.yt_home()["filling"], 0)   # YouTube no lo dio: no hay nada en camino

    def test_historial_y_seguir_viendo_con_duracion(self):
        self.app.durations.learn({vid(1): 90})
        self.app.store.progress["yt:" + vid(1)] = {"p": 30, "t": 100}
        h = self.app.history()
        self.assertEqual((h[0]["id"], h[0]["duration"]), (vid(1), 90))
        self.assertEqual(self.app.yt_continue()[0]["duration"], 90)

    def test_la_lista_del_takeout_toma_las_duraciones_de_la_lista_publica(self):
        acc = self.app.account
        acc.lists = [{"id": "PL0123456789abcdef", "title": "Música", "videos": [{"id": vid(i), "t": 0} for i in range(3)]}]
        acc.history = [{"id": vid(i), "title": f"V{i}", "channel": "C", "t": 1} for i in range(3)]   # títulos ya sabidos
        llamadas = []

        def publica(pid):
            llamadas.append(pid)
            return [{"id": vid(0), "title": "V0", "duration": 180}, {"id": vid(1), "title": "V1", "duration": 0}]
        r = acc.playlist("PL0123456789abcdef", public=publica)
        self.assertEqual([v["duration"] for v in r["videos"]], [180, 0, 0])
        self.assertEqual(llamadas, ["PL0123456789abcdef"])
        self.assertEqual(self.app.filler.pending, [vid(1), vid(2)])   # lo que la lista no trajo, al rellenador
        acc.playlist("PL0123456789abcdef", public=publica)
        self.assertEqual(len(llamadas), 1)                              # la pública, una vez al día

    def test_lista_del_takeout_sin_pedir_la_publica_si_youtube_frena(self):
        acc = self.app.account
        acc.lists = [{"id": "PL0123456789abcdef", "title": "Música", "videos": [{"id": vid(1), "t": 0}]}]
        acc.history = [{"id": vid(1), "title": "V1", "channel": "C", "t": 1}]
        self.app.filler.blocked_until = self.app.filler.clock() + 3600
        llamadas = []
        acc.playlist("PL0123456789abcdef", public=lambda pid: llamadas.append(pid) or [])
        self.assertEqual(llamadas, [])


if __name__ == "__main__":
    unittest.main()
