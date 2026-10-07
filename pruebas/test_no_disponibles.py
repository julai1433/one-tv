# Videos de YouTube que ya no existen: se reconocen (en inglés y en español), se recuerdan una semana, la TV
# pregunta antes de reproducir (/api/yt/check) y la fila se los salta.
# python3 -m unittest discover -s pruebas -p "test_no_disponibles.py"
import json, subprocess, sys, tempfile, threading, time, unittest, urllib.request
from pathlib import Path
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mac"))
import cine
from mylists import MyLists
import youtube
from server import serve
from store import Store
from playqueue import PlayQueue
from youtube import YouTube, YouTubeError


def ytdlp_says(stderr):
    return lambda *a, **k: subprocess.CompletedProcess(a, 1, stdout="", stderr=stderr)


class Reconocer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.yt = YouTube(self.tmp.name, self.tmp.name, ytdlp="/nada")

    def tearDown(self):
        self.tmp.cleanup()

    def error_de(self, stderr):
        with mock.patch.object(youtube.subprocess, "run", ytdlp_says(stderr)):
            try:
                self.yt.resolve("abcdefghijk", force=True)
            except YouTubeError as e:
                return e
        self.fail("no lanzó")

    def test_ya_no_existe_en_ingles_y_en_espanol(self):
        for msg in ["ERROR: [youtube] abcdefghijk: Video unavailable. This video has been removed by the uploader",
                    "ERROR: [youtube] abcdefghijk: This video is unavailable",
                    "ERROR: [youtube] abcdefghijk: Private video. Sign in if you've been granted access",
                    "ERROR: [youtube] abcdefghijk: Este video no está disponible.",
                    "ERROR: [youtube] abcdefghijk: Este video ya no está disponible porque se canceló la cuenta de YouTube asociada.",
                    "ERROR: [youtube] abcdefghijk: Video privado"]:
            e = self.error_de(msg)
            self.assertTrue(e.gone, msg)
            self.assertEqual(str(e), "ya no está disponible en YouTube")

    def test_un_fallo_pasajero_no_cuenta(self):
        for msg in ["ERROR: [youtube] abcdefghijk: Sign in to confirm you're not a bot",
                    "ERROR: unable to download webpage: HTTP Error 429: Too Many Requests"]:
            self.assertFalse(self.error_de(msg).gone, msg)

    def test_se_recuerda_sin_volver_a_preguntar(self):
        calls = []

        def run(*a, **k):
            calls.append(a)
            return subprocess.CompletedProcess(a, 1, stdout="", stderr="ERROR: [youtube] x: Video unavailable")
        with mock.patch.object(youtube.subprocess, "run", run):
            for _ in range(3):
                with self.assertRaises(YouTubeError) as c:
                    self.yt.resolve("abcdefghijk")
                self.assertTrue(c.exception.gone)
        self.assertEqual(len(calls), 1)
        self.assertTrue(self.yt.is_gone("abcdefghijk"))
        otro = YouTube(self.tmp.name, self.tmp.name, ytdlp="/nada")   # sobrevive a un reinicio
        self.assertTrue(otro.is_gone("abcdefghijk"))
        otro.gone["abcdefghijk"]["at"] -= youtube.GONE_TTL + 1   # a la semana se vuelve a probar
        self.assertFalse(otro.is_gone("abcdefghijk"))


class Falso(cine.App):
    def __init__(self, tmp):
        self.store = Store(Path(tmp) / "progreso.json")
        self.lists = MyLists(Path(tmp) / "listas.json")   # Favoritos y listas de One TV
        self.youtube = YouTube(tmp, tmp, ytdlp="/nada")
        self.queue = PlayQueue(Path(tmp) / "cola.json")
        self.account = None
        self.relacionados = {}
        self.youtube.related = lambda v: []

    def tell_tv_to_refresh(self):
        pass


class Rutas(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = Falso(self.tmp.name)
        self.httpd = serve(self.app, 0)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.tmp.cleanup()

    def get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=5) as r:
            return json.loads(r.read())

    def post(self, path, body):
        req = urllib.request.Request(self.base + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read())

    def test_check(self):
        def resolve(vid, force=False):
            if vid == "borradoxxxx":
                raise YouTubeError("ya no está disponible en YouTube", gone=True)
            if vid == "lentoxxxxxx":
                raise YouTubeError("YouTube no dio el video: HTTP Error 429")
            return {"info": {"title": "Existe", "duration": 213}}
        self.app.youtube.resolve = resolve
        with mock.patch.object(cine, "say"):
            self.assertEqual(self.get("/api/yt/check?id=existexxxxx"), {"ok": True, "title": "Existe", "duration": 213, "live": False})
            r = self.get("/api/yt/check?id=borradoxxxx")
            self.assertEqual((r["ok"], r["gone"], r["error"]), (False, True, "ya no está disponible en YouTube"))
            self.assertFalse(self.get("/api/yt/check?id=lentoxxxxxx")["gone"])
        self.assertFalse(self.get("/api/yt/check?id=corto")["ok"])

    def test_la_fila_se_salta_los_que_ya_no_existen(self):
        for vid, title in [("borrado1xxx", "Uno"), ("borrado2xxx", "Dos"), ("existexxxxx", "Tres")]:
            self.app.queue.add({"kind": "yt", "id": vid, "title": title, "thumb": ""})
        self.app.youtube.gone = {"borrado1xxx": {"at": time.time()}, "borrado2xxx": {"at": time.time()}}
        r = self.post("/api/queue/next", {"after": "yt:antes"})
        self.assertEqual((r["entry"]["id"], r["skipped"]), ("existexxxxx", ["Uno", "Dos"]))
        self.assertEqual(self.app.queue.items(), [])


if __name__ == "__main__":
    unittest.main()
