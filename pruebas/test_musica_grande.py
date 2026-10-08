# Pruebas de la música por partes (mac/music.py: home, more, page, mix, tracks, search, y sus rutas) con una música
# GRANDE inventada en memoria (pruebas/musica_grande.py: ~3 900 artistas, ~7 150 álbumes, 70 000 canciones, sin
# archivos): cada respuesta queda chica, las tandas no repiten ni pierden nada, y escuchar en la TV o mandar a la fila
# un artista entero no necesita mandar sus canciones. Sin red. Uso: python3 -m unittest pruebas/test_musica_grande.py
import json, sys, tempfile, threading, unittest, urllib.request
from unittest import mock
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mac"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cine
import musica_grande
from music import Music, MIX_MAX, PAGE
from playqueue import PlayQueue
from server import serve

KB = 1024


def size(data):
    return len(json.dumps(data, ensure_ascii=False).encode())


class MusicaGrande(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._t = tempfile.TemporaryDirectory()
        d = Path(cls._t.name)
        cls.music = Music([str(d / "musica")], d / "musica.json", d / "cache", log=lambda m: None)
        cls.n = musica_grande.en_memoria(cls.music)
        cls.varios = next(a for a in cls.music.artists.values() if a["name"] == musica_grande.VARIOS)
        cls.enorme = next(p for p in cls.music.playlists if p["title"] == "Todo mezclado")

    @classmethod
    def tearDownClass(cls):
        cls._t.cleanup()

    def test_es_grande_de_verdad(self):
        self.assertEqual(self.n, 70000)
        self.assertGreater(len(self.music.artists), 3800)
        self.assertGreater(len(self.music.albums), 7100)
        self.assertGreater(len(self.varios["albums"]), 250)                     # una página con miles de canciones

    def test_la_respuesta_inicial_es_chica(self):
        h = self.music.home()
        self.assertLess(size(h), 64 * KB)                                       # antes: ~23 MB de una vez
        self.assertEqual(h["counts"], {"artists": len(self.music.artists), "albums": len(self.music.albums),
                                       "tracks": 70000, "playlists": len(self.music.playlists)})
        self.assertEqual((len(h["artists"]), len(h["albums"])), (PAGE, PAGE))
        self.assertEqual(len(h["recent"]), 40)
        t = h["recent"][0]
        self.assertTrue(t["url"].startswith("/music/") and t["art"].startswith("/music/art/"))   # se puede escuchar ya
        newest = max(self.music.albums.values(), key=lambda a: a["added"])
        self.assertEqual(t["album_id"], newest["id"])                           # lo agregado más reciente primero
        self.assertEqual([a["name"] for a in h["artists"]], sorted((a["name"] for a in h["artists"]), key=str.casefold))
        self.assertNotIn("path", json.dumps(h))                                 # nunca se mandan rutas
        self.assertNotIn("tracks", h["albums"][0])                              # los álbumes, sin sus canciones

    def test_las_tandas_no_pierden_ni_repiten(self):
        for kind, every in (("artists", self.music.artists), ("albums", self.music.albums),
                            ("playlists", self.music.lists)):
            seen, offset, total = [], 0, None
            while True:
                got = self.music.more(kind, offset, 200)
                self.assertLess(size(got), 64 * KB)
                total = got["total"]
                seen += [x["id"] for x in got["items"]]
                offset += len(got["items"])
                if not got["items"] or offset >= total:
                    break
            self.assertEqual(len(seen), len(set(seen)), kind)
            self.assertEqual(set(seen), set(every), kind)
            self.assertEqual(total, len(every))
        first = self.music.home()["albums"]
        self.assertEqual([a["id"] for a in self.music.more("albums", 0, PAGE)["items"]], [a["id"] for a in first])
        self.assertEqual(self.music.more("albums", 10 ** 6)["items"], [])       # más allá del final: nada
        self.assertIsNone(self.music.more("canciones"))
        self.assertEqual(len(self.music.more("albums", 0, 10 ** 6)["items"]), 200)   # nunca más de 200 por tanda

    def test_cada_cancion_esta_en_un_album(self):
        counted = sum(a["count"] for a in self.music.more("albums", 0, 200)["items"])
        self.assertGreater(counted, 0)
        everything = sum(len(a["tracks"]) for a in self.music.albums.values())
        self.assertEqual(everything, 70000)

    def test_la_pagina_de_un_artista_enorme_por_tandas(self):
        total = sum(len(self.music.albums[a]["tracks"]) for a in self.varios["albums"])
        got, offset = [], 0
        while offset < total:
            p = self.music.page("artist", self.varios["id"], offset)
            self.assertLess(size(p), 160 * KB)
            self.assertEqual((p["total"], p["title"], p["album_count"]), (total, musica_grande.VARIOS, len(self.varios["albums"])))
            got += [t["id"] for t in p["tracks"]]
            offset += len(p["tracks"])
        self.assertEqual(got, self.music.collection("artist", self.varios["id"]))   # todas, en orden, sin repetir
        self.assertEqual(len(self.music.page("artist", self.varios["id"])["albums"]), len(self.varios["albums"]))

    def test_la_pagina_de_un_album_y_de_una_lista(self):
        a = next(iter(self.music.albums.values()))
        p = self.music.page("album", a["id"])
        self.assertEqual([t["id"] for t in p["tracks"]], a["tracks"])
        self.assertEqual((p["title"], p["artist"], p["total"]), (a["title"], a["artist"], len(a["tracks"])))
        self.assertEqual(p["duration"], round(sum(self.music.tracks[t]["duration"] for t in a["tracks"])))
        p = self.music.page("list", self.enorme["id"], 4900)
        self.assertEqual((p["total"], len(p["tracks"])), (5000, 100))
        self.assertIsNone(self.music.page("album", "noexiste"))
        self.assertIsNone(self.music.page("cancion", a["id"]))

    def test_escuchar_algo_enorme_seguido_o_al_azar(self):
        ids = self.music.collection("list", self.enorme["id"])
        m = self.music.mix("list", self.enorme["id"], 3000)
        self.assertEqual(len(m["tracks"]), MIX_MAX)
        self.assertEqual(m["tracks"][m["index"]]["id"], ids[3000])              # empieza en la elegida…
        self.assertGreater(m["index"], 0)                                        # …y hay unas antes («anterior»)
        self.assertEqual([t["id"] for t in m["tracks"]], ids[3000 - m["index"]:3000 - m["index"] + MIX_MAX])
        m = self.music.mix("list", self.enorme["id"], 4990)                      # al final: no se sale
        self.assertEqual(m["tracks"][m["index"]]["id"], ids[4990])
        self.assertLess(size(m), 200 * KB)
        m = self.music.mix("list", self.enorme["id"], 7, shuffle=True)
        chosen = [t["id"] for t in m["tracks"]]
        self.assertEqual((m["index"], chosen[0], len(chosen), len(set(chosen))), (0, ids[7], MIX_MAX, MIX_MAX))
        self.assertTrue(set(chosen) <= set(ids))
        self.assertNotEqual(chosen[1:20], ids[8:27])                             # al azar de verdad
        small = self.music.mix("album", next(iter(self.music.albums)), 0, shuffle=True)
        self.assertEqual(len(small["tracks"]), small["total"])                   # algo chico: completo
        self.assertIsNone(self.music.mix("artist", "noexiste"))

    def test_buscar(self):
        name = self.varios["name"]
        r = self.music.search("VARIOS artístas")                                  # sin importar acentos ni mayúsculas
        self.assertEqual([a["id"] for a in r["artists"]], [self.varios["id"]], name)
        r = self.music.search("amor")
        self.assertEqual(len(r["tracks"]), 20)                                    # con tope
        self.assertTrue(all("amor" in (t["title"] + t["artist"]).lower() for t in r["tracks"]))
        self.assertLess(size(r), 32 * KB)
        self.assertEqual(self.music.search("  "), {"artists": [], "albums": [], "playlists": [], "tracks": []})
        self.assertEqual(self.music.search("zzzz qqqq")["tracks"], [])

    def test_lo_de_antes_sigue(self):
        d = self.music.public()                                                  # las apps viejas: todo junto
        self.assertEqual(len(d["tracks"]), 70000)
        self.assertEqual(len(d["albums"]), len(self.music.albums))


class Falsa(cine.App):
    def __init__(self, music, tmp):
        self.music = music
        self.music_sessions = {}
        self.queue = PlayQueue(Path(tmp) / "cola.json")
        self.roku = mock.Mock()
        self.keep_awake = mock.Mock()
        self.server_url = "http://x"

    def tell_tv_to_refresh(self):
        pass


class RutasGrandes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        MusicaGrande.setUpClass()
        cls.music, cls.varios, cls.enorme = MusicaGrande.music, MusicaGrande.varios, MusicaGrande.enorme
        cls.app = Falsa(cls.music, MusicaGrande._t.name)
        cls.quiet = mock.patch.object(cine, "say", lambda m: None)
        cls.quiet.start()
        cls.httpd = serve(cls.app, 0, "127.0.0.1")
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.quiet.stop()
        MusicaGrande.tearDownClass()

    def get(self, path):
        with urllib.request.urlopen(self.base + path) as r:
            raw = r.read()
        return json.loads(raw), len(raw)

    def post(self, path, body):
        req = urllib.request.Request(self.base + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())

    def test_rutas_por_partes(self):
        h, n = self.get("/api/music/home")
        self.assertTrue(h["ok"] and h["enabled"] is False and h["counts"]["tracks"] == 70000)
        self.assertLess(n, 64 * KB)
        m, n = self.get("/api/music/more?kind=albums&offset=60&limit=60")
        self.assertEqual((m["kind"], m["offset"], len(m["items"]), m["total"]), ("albums", 60, 60, len(self.music.albums)))
        self.assertLess(n, 32 * KB)
        p, n = self.get(f"/api/music/page?kind=artist&id={self.varios['id']}&offset=200")
        self.assertEqual((p["ok"], p["offset"], len(p["tracks"])), (True, 200, 200))
        self.assertLess(n, 160 * KB)
        self.assertEqual(self.get("/api/music/page?kind=album&id=noexiste")[0]["ok"], False)
        x, n = self.get(f"/api/music/mix?kind=list&id={self.enorme['id']}&index=10&shuffle=1")
        self.assertEqual((x["index"], len(x["tracks"])), (0, MIX_MAX))
        ids = [t["id"] for t in h["recent"][:3]]
        t, _ = self.get("/api/music/tracks?ids=" + ",".join(ids + ["noexiste"]))
        self.assertEqual([x["id"] for x in t["tracks"]], ids)
        s, _ = self.get("/api/music/search?q=" + urllib.parse.quote("varios artistas"))
        self.assertEqual(s["artists"][0]["id"], self.varios["id"])
        self.assertEqual(self.post("/api/music/search", {"q": "varios artistas"})["artists"][0]["id"], self.varios["id"])
        self.assertEqual(self.get("/api/music/more?kind=x")[0]["ok"], False)
        self.assertEqual(self.get("/api/music/more?kind=albums&offset=abc")[0]["offset"], 0)   # basura: desde el principio

    def test_un_artista_enorme_a_la_tv_y_a_la_fila_sin_mandar_sus_canciones(self):
        ids = self.music.collection("artist", self.varios["id"])
        r = self.post("/api/music/tv", {"kind": "artist", "id": self.varios["id"], "index": 1500})
        self.assertEqual(r, {"ok": True, "count": MIX_MAX})
        sid = self.app.roku.play.call_args[0][0].split(":", 1)[1]
        s, n = self.get("/api/music/session?id=" + sid)
        self.assertEqual(s["tracks"][s["index"]]["id"], ids[1500])               # suena la elegida
        self.assertLess(n, 200 * KB)                                              # lo que lee la TV, acotado
        r = self.post("/api/music/tv", {"kind": "artist", "id": self.varios["id"], "index": 9, "shuffle": True})
        sid = self.app.roku.play.call_args[0][0].split(":", 1)[1]
        s, _ = self.get("/api/music/session?id=" + sid)
        self.assertEqual((s["index"], s["tracks"][0]["id"]), (0, ids[9]))         # al azar, empezando por esa
        self.assertEqual(self.post("/api/music/tv", {"kind": "album", "id": "noexiste"})["ok"], False)
        r = self.post("/api/queue/add_tracks", {"kind": "list", "id": self.enorme["id"]})
        self.assertEqual((r["ok"], r["added"]), (True, 500))
        self.post("/api/queue/clear", {})


if __name__ == "__main__":
    unittest.main()
