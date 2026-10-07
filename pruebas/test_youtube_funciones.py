# Pruebas sin red: seguir viendo, «porque viste…» y marcas. Uso: python3 -m unittest pruebas/test_youtube_funciones.py
import sys, tempfile, threading, unittest
from unittest import mock
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mac"))
import cine
from mylists import MyLists
from store import Store
from youtube import YouTube


def vid(n):
    return f"vid{n:08d}"[:11]


class Falso(cine.App):
    def __init__(self, tmp):
        self.store = Store(Path(tmp) / "progreso.json")
        self.lists = MyLists(Path(tmp) / "listas.json")   # Favoritos y listas de One TV
        self.youtube = YouTube(tmp, tmp, ytdlp="/nada")
        self.youtube.related = lambda v: self.relacionados.get(v, [])
        self.relacionados = {}
        self._because = None
        self._because_busy = False
        self._because_lock = threading.Lock()


def video(n):
    return {"id": vid(n), "title": f"Video {n}", "channel": "C", "duration": 600, "thumb": ""}


class Pruebas(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.app = Falso(self._t.name)

    def tearDown(self):
        self._t.cleanup()

    def ver(self, n, p, t):
        self.app.store.progress[f"yt:{vid(n)}"] = {"p": p, "t": t}
        self.app.youtube.history.insert(0, {**video(n), "t": t})

    def test_seguir_viendo_orden_y_terminados(self):
        self.ver(1, 100, 10); self.ver(2, 0, 30); self.ver(3, 50, 20)
        self.app.store.progress["peli1"] = {"p": 90, "t": 40}   # no es de YouTube
        r = self.app.yt_continue()
        self.assertEqual([x["id"] for x in r], [vid(3), vid(1)])
        self.assertEqual(r[0]["p"], 50)
        self.assertEqual(r[0]["title"], "Video 3")

    def test_seguir_viendo_sin_titulo_guardado(self):
        self.app.store.progress[f"yt:{vid(9)}"] = {"p": 70, "t": 5}
        self.assertEqual(self.app.yt_continue()[0]["title"], "Video de YouTube")

    def test_marcas_capitulos(self):
        cap = [{"start": 0, "end": 60, "title": "Intro"}, {"start": 60, "end": 200, "title": "Uno"},
               {"start": 200, "end": 300, "title": "Dos"}]
        self.app.youtube.resolve = lambda v: {"info": {"chapters": cap}}
        # los capítulos se muestran como marcadores en la barra de avance, no como «saltar»
        self.assertEqual(self.app.marks(f"yt:{vid(1)}"), [])

    def test_marcas_sin_datos_o_con_error(self):
        self.assertEqual(self.app.marks("peli"), [])   # sin app.intros

        def falla(v):
            raise cine.YouTubeError("x")
        self.app.youtube.resolve = falla
        self.assertEqual(self.app.marks(f"yt:{vid(1)}"), [])
        self.app.youtube.resolve = lambda v: {"info": {"chapters": []}}
        self.assertEqual(self.app.marks(f"yt:{vid(1)}"), [])

    def test_marcas_intro_ordenadas(self):
        class Intros:
            def marks(self, i):
                return [{"kind": "intro", "start": 300, "end": 330, "label": "b"},
                        {"kind": "intro", "start": 10, "end": 40, "label": "a"}]
        self.app.intros = Intros()
        self.assertEqual([m["start"] for m in self.app.marks("peli")], [10, 300])

    def test_porque_viste_sin_repetidos(self):
        self.ver(4, 0, 5); self.ver(3, 0, 10); self.ver(2, 0, 20); self.ver(1, 0, 30)
        self.app.relacionados = {
            vid(1): [video(10), video(11), video(2), video(4)],   # 2 es semilla, 4 ya visto
            vid(2): [video(10), video(12)],                       # 10 ya salió en el grupo anterior
            vid(3): [video(11), video(13)],
        }
        with mock.patch.object(cine, "BECAUSE_MIN", 1):
            g = self.app._compute_because()
        self.assertEqual([x["seed"]["id"] for x in g], [vid(1), vid(2), vid(3)])
        self.assertEqual([[v["id"] for v in x["videos"]] for x in g],
                         [[vid(10), vid(11)], [vid(12)], [vid(13)]])

    def test_porque_viste_respaldo_de_takeout(self):
        class Cuenta:
            def watch_history(self, limit):
                return [{"id": vid(7), "title": "Viejo", "t": 1}]
        self.app.account = Cuenta()
        self.app.relacionados = {vid(7): [{**video(8), "title": "Viejo otra vez"}, {**video(9), "title": "Viejo y bueno"},
                                          {**video(10), "title": "El viejo"}]}
        g = self.app._compute_because()
        self.assertEqual(g[0]["seed"], {"id": vid(7), "title": "Viejo"})


if __name__ == "__main__":
    unittest.main()
