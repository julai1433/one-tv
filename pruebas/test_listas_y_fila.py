# Fila de reproducción (mover, una lista entera), Favoritos y listas de One TV (mac/mylists.py, también cambios a las
# listas del Takeout) y «Cargar más» en la búsqueda de YouTube. Sin red: apps falsas sobre carpetas temporales.
# python3 -m unittest discover -s pruebas -p "test_listas_y_fila.py"
import json, sys, tempfile, threading, unittest, urllib.request
from pathlib import Path
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mac"))
import cine
from mylists import FAV, MyLists
from playqueue import MAX_ITEMS, PlayQueue
from server import serve
from youtube import YouTube, YouTubeError
from test_fase4_api import Falso, vid


def entrada(n):
    return {"kind": "yt", "id": vid(n), "title": f"T{n}", "thumb": ""}


class Fila(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.q = PlayQueue(Path(self._t.name) / "cola.json")
        for n in range(5):
            self.q.add(entrada(n))

    def tearDown(self):
        self._t.cleanup()

    def ids(self):
        return [e["id"] for e in self.q.items()]

    def test_mover(self):
        self.assertEqual(self.q.move(4, 0), 0)
        self.assertEqual(self.ids(), [vid(4), vid(0), vid(1), vid(2), vid(3)])
        self.assertEqual(self.q.move(0, 99), 4)   # fuera del final: queda al final
        self.assertEqual(self.ids(), [vid(0), vid(1), vid(2), vid(3), vid(4)])
        self.assertEqual(self.q.move(1, 2), 2)
        self.assertEqual(self.ids(), [vid(0), vid(2), vid(1), vid(3), vid(4)])
        self.assertIsNone(self.q.move(9, 0))
        # Se guarda en el archivo
        self.assertEqual([e["id"] for e in json.loads(self.q.path.read_text())], self.ids())

    def test_varias_de_una_vez_con_tope(self):
        self.assertEqual(self.q.add_many([entrada(10), entrada(11)], front=True), 2)
        self.assertEqual(self.ids()[:3], [vid(10), vid(11), vid(0)])
        self.assertEqual(self.q.add_many([entrada(n) for n in range(100, 100 + MAX_ITEMS)]), MAX_ITEMS - 7)
        self.assertEqual(len(self.q.items()), MAX_ITEMS)
        self.assertEqual(self.q.add_many([entrada(1000)]), 0)


class ListasPropias(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.path = Path(self._t.name) / "listas.json"
        self.t = [100.0]
        self.l = MyLists(self.path, clock=lambda: self.t[0])

    def tearDown(self):
        self._t.cleanup()

    def video(self, n):
        self.t[0] += 1
        return {"id": vid(n), "title": f"Video {n}", "channel": "Canal", "duration": 60 + n}

    def test_favoritos_siempre_existe_y_va_primero(self):
        nueva = self.l.create("Para correr")
        self.assertRegex(nueva["id"], r"^ot-[0-9a-f]{8}$")
        self.assertEqual([s["id"] for s in self.l.summaries()], [FAV, nueva["id"]])
        with self.assertRaisesRegex(ValueError, "no se puede borrar"):
            self.l.delete(FAV)
        with self.assertRaisesRegex(ValueError, "no se puede renombrar"):
            self.l.rename(FAV, "Otra")

    def test_favoritos_del_mas_reciente_y_listas_en_orden(self):
        for n in (1, 2, 3):
            self.assertTrue(self.l.add(FAV, self.video(n)))
        self.assertFalse(self.l.add(FAV, self.video(2)))   # ya estaba
        self.assertEqual([v["id"] for v in self.l.get(FAV)["videos"]], [vid(3), vid(2), vid(1)])
        lid = self.l.create("Música")["id"]
        for n in (1, 2):
            self.l.add(lid, self.video(n))
        self.assertEqual([v["id"] for v in self.l.get(lid)["videos"]], [vid(1), vid(2)])
        self.assertEqual(self.l.get(lid)["videos"][0], {"id": vid(1), "title": "Video 1", "channel": "Canal",
                                                         "duration": 61, "thumb": f"/yt/{vid(1)}/thumb.jpg", "t": 105.0})
        self.assertTrue(self.l.remove(lid, vid(1)))
        self.assertFalse(self.l.remove(lid, vid(1)))
        self.assertTrue(self.l.is_favorite(vid(3)))
        # Sobrevive a reiniciar
        otra = MyLists(self.path)
        self.assertEqual([v["id"] for v in otra.get(lid)["videos"]], [vid(2)])
        self.assertEqual(otra.summaries()[0]["thumb"], f"/yt/{vid(3)}/thumb.jpg")

    def test_nombres(self):
        self.l.create("  Música   suave ")
        with self.assertRaisesRegex(ValueError, "Ya tienes una lista que se llama «música suave»"):
            self.l.create("música suave")
        with self.assertRaisesRegex(ValueError, "Ya tienes"):
            self.l.create("favoritos")
        with self.assertRaisesRegex(ValueError, "Escribe un nombre"):
            self.l.create("   ")
        self.assertEqual(len(self.l.create("x" * 200)["title"]), 80)
        with self.assertRaisesRegex(ValueError, "no parece un video"):
            self.l.add(FAV, {"id": "corto"})

    def test_cambios_a_una_lista_del_takeout(self):
        base = [{"id": vid(1)}, {"id": vid(2)}, {"id": vid(3)}]
        self.l.edit_takeout("PLx", video=self.video(9))
        self.l.edit_takeout("PLx", remove=vid(2))
        self.assertEqual([v["id"] for v in self.l.apply_edits("PLx", base)], [vid(1), vid(3), vid(9)])
        self.l.edit_takeout("PLx", video=self.video(2))   # se vuelve a agregar: ya no está quitado
        self.l.edit_takeout("PLx", remove=vid(9))
        self.assertEqual([v["id"] for v in self.l.apply_edits("PLx", base)], [vid(1), vid(2), vid(3)])
        self.assertEqual(self.l.apply_edits("otra", base), base)
        self.assertGreater(self.l.edited_at("PLx"), 0)


class EnLaApp(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.app = Falso(self._t.name)
        acc = self.app.account
        acc.lists = [{"id": "PLaaaaaaaaaaaa", "title": "Música", "videos": [{"id": vid(1), "t": 1}, {"id": vid(2), "t": 1}]},
                     {"id": "PLbbbbbbbbbbbb", "title": "Cocina", "videos": [{"id": vid(3), "t": 1}]}]
        acc.history = [{"id": vid(3), "title": "Receta", "channel": "Chef", "t": 5000},
                       {"id": vid(1), "title": "Canción", "channel": "Banda", "t": 1000}]
        acc.oembed = lambda v: {"title": f"T {v}", "author_name": ""}
        self.app.youtube.playlist_videos = lambda pid: (_ for _ in ()).throw(YouTubeError("no"))

    def tearDown(self):
        self._t.cleanup()

    def test_favorito_y_tus_listas(self):
        lists = self.app.lists_for(vid(7))["lists"]
        self.assertEqual([(r["id"], r["has"]) for r in lists], [(FAV, False), ("PLbbbbbbbbbbbb", False),
                                                                 ("PLaaaaaaaaaaaa", False)])
        self.assertEqual(self.app.list_toggle({"list": FAV, "id": vid(7), "title": "Siete"}), {"ok": True, "has": True})
        home = self.app.yt_home()
        self.assertEqual([v["id"] for v in home["favorites"]], [vid(7)])
        self.assertEqual(home["playlists"][0]["id"], FAV)   # con algo, Favoritos sale primero en «Tus listas»
        self.assertEqual(self.app.list_toggle({"list": FAV, "id": vid(7)}), {"ok": True, "has": False})
        self.assertNotIn(FAV, [r["id"] for r in self.app.yt_home()["playlists"]])   # vacío: no sale
        self.assertFalse(self.app.list_toggle({"list": "PLnoexiste000", "id": vid(7)})["ok"])
        self.assertFalse(self.app.list_toggle({"list": FAV, "id": "x"})["ok"])

    def test_agregar_a_una_lista_del_takeout_y_quitar(self):
        self.assertTrue(self.app.list_toggle({"list": "PLaaaaaaaaaaaa", "id": vid(8), "title": "Ocho", "on": True})["has"])
        self.assertTrue(self.app.list_toggle({"list": "PLaaaaaaaaaaaa", "id": vid(1), "on": False})["ok"])
        data = self.app.yt_playlist("PLaaaaaaaaaaaa")
        self.assertEqual([v["id"] for v in data["videos"]], [vid(2), vid(8)])
        self.assertEqual(data["videos"][1]["title"], "Ocho")
        row = next(r for r in self.app.yt_home()["playlists"] if r["id"] == "PLaaaaaaaaaaaa")
        self.assertEqual((row["count"], row["thumb"]), (2, f"/yt/{vid(2)}/thumb.jpg"))
        self.assertEqual([(r["id"], r["has"]) for r in self.app.lists_for(vid(8))["lists"]][0:2],
                         [(FAV, False), ("PLaaaaaaaaaaaa", True)])   # recién cambiada: sube

    def test_lista_nueva_con_un_video_se_ve_reproduce_y_se_borra(self):
        r = self.app.list_create({"title": "Para la cena", "id": vid(5), "video_title": "Pasta"})
        self.assertTrue(r["ok"])
        lid = r["list"]["id"]
        self.assertEqual(self.app.list_create({"title": "para la cena"})["error"], "Ya tienes una lista que se llama «para la cena».")
        data = self.app.yt_playlist(lid)
        self.assertEqual((data["title"], [v["id"] for v in data["videos"]], data["source"]), ("Para la cena", [vid(5)], "onetv"))
        self.assertEqual(data["videos"][0]["title"], "Pasta")   # el título del video, no el de la lista
        self.assertEqual(self.app.yt_playlist_play(lid), {"ok": True, "count": 1, "total": 1})
        self.assertEqual(self.app.played, [f"yt:{vid(5)}"])
        self.assertNotIn(lid, self.app.account.played)   # las de One TV no se anotan como «de YouTube»
        self.assertTrue(self.app.list_rename({"list": lid, "title": "Cena"})["ok"])
        self.assertEqual(self.app.yt_playlist(lid)["title"], "Cena")
        self.assertTrue(self.app.list_delete({"list": lid})["ok"])
        self.assertFalse(self.app.list_delete({"list": lid})["ok"])

    def test_lista_entera_a_la_fila(self):
        self.app.queue.add(entrada(50))
        r = self.app.queue_add_list("PLaaaaaaaaaaaa")
        self.assertEqual(r, {"ok": True, "added": 2, "total": 2, "count": 3})
        self.assertEqual([e["id"] for e in self.app.queue.items()], [vid(50), vid(1), vid(2)])
        self.assertEqual(self.app.queue_add_list("PLbbbbbbbbbbbb", front=True)["added"], 1)
        self.assertEqual([e["id"] for e in self.app.queue.items()], [vid(3), vid(50), vid(1), vid(2)])
        self.assertEqual(self.app.played, [])   # no reproduce nada
        self.app.youtube.is_gone = lambda v: v == vid(1)   # los que ya no existen no entran
        self.assertEqual(self.app.queue_add_list("PLaaaaaaaaaaaa")["added"], 1)
        self.assertFalse(self.app.queue_add_list("PLnoexiste000")["ok"])
        self.app.queue.add_many([entrada(n) for n in range(1000, 1000 + MAX_ITEMS)])
        self.assertEqual(self.app.queue_add_list("PLbbbbbbbbbbbb")["error"],
                         f"La fila de reproducción está llena ({MAX_ITEMS} videos).")

    def test_mover_en_la_fila(self):
        for n in range(3):
            self.app.queue.add(entrada(n))
        r = self.app.queue_move(2, 0)
        self.assertEqual((r["ok"], r["index"], [e["id"] for e in r["queue"]]), (True, 0, [vid(2), vid(0), vid(1)]))
        self.assertFalse(self.app.queue_move(7, 0)["ok"])


class Busqueda(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.yt = YouTube(self._t.name, self._t.name, ytdlp="/nada")
        self.args = []

        def run(args, timeout=60):
            self.args.append(args)
            n = int(args[-1].split(":")[0][len("ytsearch"):])
            start = int(args[args.index("--playlist-start") + 1])
            return {"entries": [{"id": vid(i), "title": f"R{i}"} for i in range(start, min(n, 60) + 1)]}
        self.yt._run = run

    def tearDown(self):
        self._t.cleanup()

    def test_paginas(self):
        videos, more = self.yt.search("gatos")
        self.assertEqual((len(videos), more, videos[0]["id"]), (24, True, vid(1)))
        self.assertEqual(self.args[-1][-3:], ["--playlist-start", "1", "ytsearch24:gatos"])
        videos, more = self.yt.search("gatos", 2)
        self.assertEqual((len(videos), more, videos[0]["id"]), (24, True, vid(25)))
        self.assertEqual(self.args[-1][-3:], ["--playlist-start", "25", "ytsearch48:gatos"])
        videos, more = self.yt.search("gatos", 3)   # YouTube ya no tenía más: 12 y se acaba
        self.assertEqual((len(videos), more), (12, False))

    def test_en_la_app(self):
        app = Falso(self._t.name)
        app.youtube = self.yt
        self.assertEqual({k: v for k, v in app.yt_search("gatos", "2").items() if k != "results"},
                         {"ok": True, "page": 2, "more": True})
        self.assertEqual(app.yt_search("gatos", "x")["page"], 1)


class Rutas(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.app = Falso(self._t.name)
        self.app.account.lists = [{"id": "PLaaaaaaaaaaaa", "title": "Música", "videos": [{"id": vid(1), "t": 1}]}]
        self.app.account.oembed = lambda v: {"title": f"T {v}", "author_name": ""}
        self.app.youtube.playlist_videos = lambda pid: (_ for _ in ()).throw(YouTubeError("no"))
        self.server = serve(self.app, 0)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self._t.cleanup()

    def get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=5) as r:
            return json.loads(r.read())

    def post(self, path, body):
        req = urllib.request.Request(self.base + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read())

    def test_contrato(self):
        self.assertEqual(self.post("/api/lists/toggle", {"list": "fav", "id": vid(4)}), {"ok": True, "has": True})
        lists = self.get(f"/api/lists?video={vid(4)}")
        self.assertEqual([(r["id"], r["has"], r["source"]) for r in lists["lists"]],
                         [("fav", True, "onetv"), ("PLaaaaaaaaaaaa", False, "takeout")])
        lid = self.post("/api/lists/create", {"title": "Nueva", "id": vid(4)})["list"]["id"]
        self.assertTrue(self.post("/api/lists/rename", {"list": lid, "title": "Otra"})["ok"])
        self.assertTrue(self.post("/api/lists/delete", {"list": lid})["ok"])
        self.assertEqual(self.post("/api/queue/add_list", {"id": "PLaaaaaaaaaaaa", "front": True})["added"], 1)
        self.app.queue.add(entrada(9))
        self.assertEqual([e["id"] for e in self.post("/api/queue/move", {"index": 1, "to": 0})["queue"]], [vid(9), vid(1)])


if __name__ == "__main__":
    unittest.main()
