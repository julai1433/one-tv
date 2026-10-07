# Que el mosaico arranque rápido (ronda del 30 sep 2026, noche): los trozos que se piden de antemano (mac/segcache.py
# y mosaic.first_segments), dos mosaicos a la vez mientras la TV sigue mostrando el anterior (keep), el adelanto de
# los videos que siguieron avanzando (advance) y el enlace del canal en vivo que se sigue usando mientras funciona.
# Sin red. python3 -m unittest discover -s pruebas -p "test_mosaico_rapido.py"
import sys, tempfile, threading, time, unittest, urllib.error
from pathlib import Path
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mac"))
import live
import mosaic
from live import LiveChannels
from mosaic import ADVANCE_EXTRA, Mosaic, Mosaics, first_segments, item_source
from segcache import SegmentCache
from test_mosaico import FfmpegFalso, MASTER_YT, Reloj, esperar, item


def lista(n, dur=5.0, base="s"):
    return "#EXTM3U\n#EXT-X-TARGETDURATION:6\n" + "".join(f"#EXTINF:{dur},\n{base}{i}.ts\n" for i in range(n))


class PrimerosTrozos(unittest.TestCase):
    URL = "http://127.0.0.1:1/yt/v/m/v.m3u8"

    def test_en_vivo_los_tres_ultimos(self):
        self.assertEqual(first_segments(lista(5, 6.0), self.URL, live=True),
                         [f"http://127.0.0.1:1/yt/v/m/s{i}.ts" for i in (2, 3, 4)])

    def test_desde_el_principio_cubre_15_segundos(self):
        self.assertEqual(first_segments(lista(10), self.URL), [f"http://127.0.0.1:1/yt/v/m/s{i}.ts" for i in (0, 1, 2)])

    def test_desde_un_segundo_los_dos_primeros_y_los_de_ahi(self):
        # 120 s con trozos de 5 s: empieza en el trozo 24 y sigue 25 y 26 (15 s).
        self.assertEqual(first_segments(lista(100), self.URL, start=120),
                         [f"http://127.0.0.1:1/yt/v/m/s{i}.ts" for i in (0, 1, 24, 25, 26)])

    def test_inicio_pasado_el_final_y_lista_vacia(self):
        self.assertEqual(first_segments(lista(3), self.URL, start=999), [f"http://127.0.0.1:1/yt/v/m/s{i}.ts" for i in (0, 1, 2)])
        self.assertEqual(first_segments("#EXTM3U\n", self.URL), [])
        self.assertEqual(first_segments("#EXTM3U\n", self.URL, live=True), [])


class Memoria(unittest.TestCase):
    def test_solo_guarda_lo_pedido_de_antemano(self):
        c, calls = SegmentCache(), []

        def produce():
            calls.append(1)
            return b"x" * 10, "video/mp2t"
        self.assertEqual(c.get("a", produce), (b"x" * 10, "video/mp2t"))
        self.assertEqual(len(c), 0)
        c.get("a", produce, keep=True)
        c.get("a", produce)
        self.assertEqual(len(calls), 2)   # la segunda vez salió de la memoria

    def test_quien_llega_mientras_baja_espera_la_misma_descarga(self):
        c, calls, started, release = SegmentCache(), [], threading.Event(), threading.Event()

        def slow():
            calls.append("lento")
            started.set()
            release.wait(5)
            return b"trozo"
        t = threading.Thread(target=lambda: c.get("k", slow, keep=True))
        t.start()
        started.wait(5)
        got = []
        t2 = threading.Thread(target=lambda: got.append(c.get("k", lambda: calls.append("otra") or b"otra")))
        t2.start()
        time.sleep(0.1)
        self.assertEqual(got, [])   # espera
        release.set()
        t.join(5)
        t2.join(5)
        self.assertEqual(got, [b"trozo"])
        self.assertEqual(calls, ["lento"])

    def test_si_falla_no_queda_nada_y_se_pide_otra_vez(self):
        c = SegmentCache()

        def boom():
            raise urllib.error.URLError("sin red")
        with self.assertRaises(urllib.error.URLError):
            c.get("k", boom, keep=True)
        self.assertEqual(c.get("k", lambda: b"bien"), b"bien")

    def test_vence_y_respeta_el_tope(self):
        now = [0.0]
        c = SegmentCache(ttl=90, max_bytes=25, clock=lambda: now[0])
        for k in "abc":
            c.get(k, lambda: b"x" * 10, keep=True)
            now[0] += 1
        self.assertEqual(len(c), 3)
        c.get("d", lambda: b"y", keep=True)   # al guardar se revisa el tope: se van los más viejos
        self.assertLessEqual(len(c), 3)
        self.assertNotIn("a", c.items)
        now[0] += 100
        c.get("e", lambda: b"z")
        self.assertEqual(len(c), 0)


class Sesiones(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.reloj = Reloj()
        self.procs = []

        def popen(cmd, **kw):
            p = FfmpegFalso(None)
            p.cmd = cmd
            self.procs.append(p)
            return p
        patcher = mock.patch.object(Mosaic, "popen", staticmethod(popen))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.mosaics = Mosaics(self.tmp.name, "http://127.0.0.1:1", log=lambda *a: None, clock=self.reloj, run=False)
        self.pelis = []
        for n in range(3):
            f = Path(self.tmp.name) / f"peli{n}.mkv"
            f.write_bytes(b"")
            self.pelis.append(item_source(item(iid=f"{n}" * 12, path=str(f), duration=5400.0), start=60.0 * n or None))

    def tearDown(self):
        self.mosaics.shutdown()
        self.tmp.cleanup()

    def arrancar(self, fuentes, **kw):
        m = self.mosaics.start(fuentes, **kw)
        self.assertTrue(esperar(lambda: m.state != "preparando"), m.state)
        return m

    def test_con_keep_el_anterior_sigue_hasta_que_la_tv_lo_detiene(self):
        a = self.arrancar(self.pelis[:2])
        b = self.arrancar(self.pelis[1:], keep=True)
        self.assertEqual((a.state, b.state), ("armando", "armando"))
        self.assertIs(self.mosaics.get(a.id), a)
        self.assertIs(self.mosaics.get(b.id), b)
        c = self.arrancar([self.pelis[0], self.pelis[2]], keep=True)   # a lo más dos: el más viejo se detiene
        self.assertEqual((a.state, b.state, c.state), ("detenido", "armando", "armando"))
        self.assertIsNone(self.mosaics.get(a.id))
        self.assertTrue(self.mosaics.stop(b.id))
        self.assertIsNone(self.mosaics.get(b.id))
        d = self.arrancar(self.pelis[:2])   # sin keep: se detienen todos los demás
        self.assertEqual((c.state, d.state), ("detenido", "armando"))
        self.assertTrue(self.mosaics.stop(d.id))
        self.assertEqual(self.mosaics.get(d.id).status()["state"], "detenido")   # el último se puede seguir leyendo

    def test_advance_adelanta_lo_que_tardo_en_prepararse(self):
        m = self.mosaics.start(self.pelis[1:], advance=True)
        self.assertTrue(esperar(lambda: m.state != "preparando"))
        st = m.status()["sources"]
        self.assertEqual([s["start"] for s in st], [60.0 + ADVANCE_EXTRA, 120.0 + ADVANCE_EXTRA])
        self.assertIn(f"{60.0 + ADVANCE_EXTRA:.3f}", self.procs[-1].cmd)
        sin = self.arrancar(self.pelis[1:])
        self.assertEqual([s["start"] for s in sin.status()["sources"]], [60.0, 120.0])

    def test_advance_no_pasa_del_final(self):
        casi = dict(self.pelis[1], start=5394.0)   # dura 5400: con el adelanto quedaría a menos de 5 s del final
        m = self.mosaics.start([self.pelis[0], casi], advance=True)
        self.assertTrue(esperar(lambda: m.state != "preparando"))
        self.assertEqual(m.status()["sources"][1]["start"], 5394.0)

    def test_pide_de_antemano_los_primeros_trozos(self):
        pedidos, listas = [], {"http://127.0.0.1:1/yt/7fPVfHqUNJM/index.m3u8": MASTER_YT,
                               "http://127.0.0.1:1/yt/v/m/v720.m3u8": lista(40, base="v"),
                               "http://127.0.0.1:1/yt/v/m/a234.m3u8": lista(40, base="a")}
        yt = {"kind": "yt", "id": "7fPVfHqUNJM", "title": "El Camino", "duration": 219, "start": 30}
        m = Mosaic("abcd0123", [self.pelis[0], yt], Path(self.tmp.name) / "m", "http://127.0.0.1:1",
                   clock=self.reloj, fetch=lambda url, timeout=60: listas[url], prefetch=pedidos.append)
        m.begin()
        self.assertTrue(esperar(lambda: m.state == "armando" and len(pedidos) == 10))
        base = "http://127.0.0.1:1/yt/v/m/"
        self.assertEqual(sorted(pedidos), sorted([base + f"{k}{i}.ts" for k in "va" for i in (0, 1, 6, 7, 8)]))
        m.stop()


class EnlaceDelCanal(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        tmp = Path(self._t.name)
        self.live = LiveChannels(tmp / "datos", tmp / "cache")
        self.live.chrome = "/chrome/de/prueba"
        self.resolves, n = [], iter(range(1, 100))

        def resolve(url):
            self.resolves.append(url)
            return {"url": f"https://cdn.ejemplo/{next(n)}/index.m3u8", "headers": {}, "poster": None,
                    "title": "Canal"}
        self.live._resolve = resolve
        self.cid = self.live.add("https://ejemplo.com/evento")["id"]
        self.resolves.clear()
        self.answers = {}

        def fetch(url, headers, timeout=15):
            a = self.answers.get(url, b"#EXTM3U\n")
            if isinstance(a, Exception):
                raise a
            return 200, "application/vnd.apple.mpegurl", a, url
        patcher = mock.patch.object(live, "fetch", fetch)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self._t.cleanup()

    def envejecer(self, secs=3600):
        self.live.get(self.cid)["stream"]["at"] -= secs

    def test_vieja_que_funciona_se_sigue_usando_sin_chrome(self):
        self.envejecer()
        self.assertEqual(self.live.fetch_through(self.cid)[3], "https://cdn.ejemplo/1/index.m3u8")
        self.assertEqual(self.resolves, [])

    def test_vieja_que_ya_no_funciona_se_busca_de_nuevo(self):
        for bad in (urllib.error.HTTPError("u", 500, "x", {}, None), urllib.error.URLError("caído"), b"<html>"):
            with self.subTest(bad=bad):
                self.answers = {self.live.get(self.cid)["stream"]["url"]: bad}
                self.envejecer()
                self.assertTrue(self.live.fetch_through(self.cid)[2].startswith(b"#EXTM3U"))
                self.assertEqual(len(self.resolves), 1)
                self.resolves.clear()

    def test_reciente_con_error_de_servidor_no_busca(self):
        self.answers = {"https://cdn.ejemplo/1/index.m3u8": urllib.error.HTTPError("u", 500, "x", {}, None)}
        with self.assertRaises(urllib.error.HTTPError):
            self.live.fetch_through(self.cid)
        self.assertEqual(self.resolves, [])


if __name__ == "__main__":
    unittest.main()
