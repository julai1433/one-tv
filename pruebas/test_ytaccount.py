# Pruebas de mac/ytaccount.py (sin red): python3 -m unittest discover -s pruebas -p "test_ytaccount.py"
import os, sys, tempfile, time, unittest, urllib.error
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mac"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import takeout_de_prueba as gen
from ytaccount import YouTubeAccount, parse_channel_page, parse_feed

GOOGLE, MKBHD, FCC = "UC_x5XG1OV2P6uZZ5FSM9Ttw", "UCBJycsmduvYEL83R_U4JriQ", "UC8butISFwT-Wl7EV0hUK0BQ"


def channel_page(name, videos):
    """Página «Videos» mínima de un canal. videos: [(id, título, «hace…» en inglés)]"""
    import json
    items = [{"richItemRenderer": {"content": {"lockupViewModel": {
        "contentId": v, "contentType": "LOCKUP_CONTENT_TYPE_VIDEO",
        "metadata": {"lockupMetadataViewModel": {"title": {"content": t}, "metadata": {"contentMetadataViewModel": {
            "metadataRows": [{"metadataParts": [{"text": {"content": "3.7M"}, "accessibilityLabel": "3.7 million views"},
                                                {"text": {"content": "?"}, "accessibilityLabel": ago}]}]}}}}}}}}
             for v, t, ago in videos]
    data = {"metadata": {"channelMetadataRenderer": {"title": name}}, "contents": {"items": items}}
    return f"<html><script>var ytInitialData = {json.dumps(data)};</script></html>"


def atom(cid, name, videos):
    """videos: [(id, título, publicado, es_short)]"""
    ents = "".join(
        f'<entry><id>yt:video:{v}</id><yt:videoId>{v}</yt:videoId><yt:channelId>{cid}</yt:channelId>'
        f'<title>{t}</title><link rel="alternate" href="https://www.youtube.com/{"shorts/" if s else "watch?v="}{v}"/>'
        f'<author><name>{name}</name></author><published>{p}</published></entry>' for v, t, p, s in videos)
    return (f'<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015" xmlns="http://www.w3.org/2005/Atom">'
            f'<title>{name}</title><author><name>{name}</name></author>{ents}</feed>').encode()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        gen.build_all(self.dir / "zips")
        (self.dir / "datos").mkdir()
        (self.dir / "dl").mkdir()
        self.acc = YouTubeAccount(self.dir / "datos", self.dir / "dl", log=lambda m: None)
        self.acc.pause = 0
        self.acc.retry_pause = 0

    def tearDown(self):
        self.tmp.cleanup()

    def zip(self, name):
        return self.dir / "zips" / name


class Importar(Base):
    def check(self, name, fmt, history):
        r = self.acc.import_zip(self.zip(name))
        self.assertEqual((r["subscriptions"], r["history_format"], r["history"]), (5, fmt, history), r)
        self.assertEqual(r["warnings"], [])
        self.assertEqual({s["id"] for s in self.acc.subscriptions()}, {c[0] for c in gen.CHANNELS})
        pls = {p["title"]: p for p in self.acc.playlists()}
        self.assertEqual(len(pls), 2, pls)   # channel.csv (el canal propio) no es una lista
        self.assertEqual(sorted(p["count"] for p in pls.values()), [1, 3])
        self.assertTrue(any(p["id"] == gen.PL for p in pls.values()))
        h = self.acc.watch_history()
        self.assertNotIn("ADSADSADS12", [e["id"] for e in h])   # anuncio fuera
        self.assertTrue(all(h[i]["t"] >= h[i + 1]["t"] for i in range(len(h) - 1)))
        despacito = next(e for e in h if e["id"] == "kJQP7kiw5Fk")
        self.assertEqual((despacito["title"], despacito["channel"]), ("Luis Fonsi - Despacito ft. Daddy Yankee", "LuisFonsiVEVO"))
        self.assertGreater(despacito["t"], 1.7e9)

    def test_ingles_json(self):
        self.check("takeout-en.zip", "json", 5)   # 4 videos + uno con la dirección como título; sin borrado ni anuncio

    def test_espanol_json(self):
        self.check("takeout-es.zip", "json", 5)
        self.assertIn("Mis favoritos", [p["title"] for p in self.acc.playlists()])

    def test_espanol_latinoamerica_json(self):
        # Como el Takeout real: «playlists», «X videos.csv» y anuncios «De los anuncios de Google».
        self.check("takeout-es419.zip", "json", 5)
        self.assertIn("Mis favoritos", [p["title"] for p in self.acc.playlists()])

    def test_listas_que_se_llaman_casi_igual(self):
        # Google guarda la segunda como «borrar videos(1).csv»: cada archivo va con su propia lista.
        import zipfile
        root = "Takeout/YouTube y YouTube Music/playlists"
        head = gen.ES419["pl_head"]
        with zipfile.ZipFile(self.dir / "dobles.zip", "w") as z:
            z.writestr(f"{root}/playlists.csv", f"{head}\nPLaaaaaaaaaaaa,false,2025-01-01T00:00:00+00:00,2025-01-02T00:00:00+00:00,manual,Private,Borrar,Borrar,,\n"
                                                f"PLbbbbbbbbbbbb,false,2025-01-01T00:00:00+00:00,2025-01-02T00:00:00+00:00,manual,Private,borrar,borrar,,\n")
            z.writestr(f"{root}/Borrar videos.csv", f"{gen.ES419['vid_head']}\nkJQP7kiw5Fk,{gen.STAMPS[0]}\n")
            z.writestr(f"{root}/borrar videos(1).csv", f"{gen.ES419['vid_head']}\n9bZkp7q19f0,{gen.STAMPS[0]}\n"
                                                        f"JGwWNGJdvx8,{gen.STAMPS[1]}\n")
        self.acc.import_zip(self.dir / "dobles.zip")
        got = sorted((p["id"], p["title"], p["count"]) for p in self.acc.playlists())
        self.assertEqual(got, [("PLaaaaaaaaaaaa", "Borrar", 1), ("PLbbbbbbbbbbbb", "borrar", 2)])

    @unittest.skipUnless(Path("/usr/bin/zip").exists(), "hace falta el zip del sistema")
    def test_nombres_sin_marca_utf8(self):
        # El zip de macOS no marca los nombres como UTF-8: los acentos y emojis no deben salir deformados.
        import subprocess, zipfile
        src = self.dir / "src" / "Takeout" / "YouTube y YouTube Music" / "playlists"
        src.mkdir(parents=True)
        (src / "playlists.csv").write_text(f"{gen.ES419['pl_head']}\nPLcccccccccccc,false,2025-01-01T00:00:00+00:00,2025-01-02T00:00:00+00:00,manual,Private,Código 💧,Código 💧,,\n")
        (src / "Código 💧 videos.csv").write_text(f"{gen.ES419['vid_head']}\nkJQP7kiw5Fk,{gen.STAMPS[0]}\n")
        subprocess.run(["/usr/bin/zip", "-qr", str(self.dir / "mac.zip"), "Takeout"], cwd=self.dir / "src", check=True)
        with zipfile.ZipFile(self.dir / "mac.zip") as z:
            flagged = all(i.flag_bits & 0x800 for i in z.infolist() if not i.filename.isascii())
        self.acc.import_zip(self.dir / "mac.zip")
        self.assertEqual([(p["id"], p["title"]) for p in self.acc.playlists()], [("PLcccccccccccc", "Código 💧")],
                         "con marca UTF-8" if flagged else "sin marca UTF-8")

    def test_ingles_html(self):
        self.check("takeout-en-html.zip", "html", 4)

    def test_espanol_html(self):
        self.check("takeout-es-html.zip", "html", 4)
        days = sorted(e["t"] for e in self.acc.watch_history())
        self.assertEqual(len(set(days)), 4)   # «sept» se entendió: las fechas son distintas y válidas
        self.assertTrue(all(d > 1.7e9 for d in days))

    def test_formato_viejo_con_metadatos_arriba(self):
        self.acc.import_zip(self.zip("takeout-viejo.zip"))
        pls = self.acc.playlists()
        self.assertEqual([(p["id"], p["title"], p["count"]) for p in pls], [(gen.PL, "My favorites", 3)])

    def test_persiste_y_se_recarga(self):
        self.acc.import_zip(self.zip("takeout-es.zip"))
        otra = YouTubeAccount(self.dir / "datos", self.dir / "dl", log=lambda m: None)
        self.assertEqual(otra.summary()["subscriptions"], 5)
        self.assertEqual(otra.summary()["imported_file"], "takeout-es.zip")
        self.assertFalse((self.dir / "datos" / "youtube_cuenta.tmp").exists())

    def test_zip_sin_nada_avisa(self):
        import zipfile
        with zipfile.ZipFile(self.dir / "vacio.zip", "w") as z:
            z.writestr("Takeout/otra-cosa.txt", "hola")
        r = self.acc.import_zip(self.dir / "vacio.zip")
        self.assertEqual((r["subscriptions"], r["history"]), (0, 0))
        self.assertEqual(len(r["warnings"]), 2)


class Descargas(Base):
    def put(self, name, age=3600, src="takeout-en.zip"):
        p = self.dir / "dl" / name
        p.write_bytes(self.zip(src).read_bytes())
        t = time.time() - age
        os.utime(p, (t, t))
        return p

    def test_importa_una_vez_y_no_toca_el_zip(self):
        p = self.put("takeout-20250901T000000Z-001.zip")
        self.assertEqual(self.acc.scan_downloads()["subscriptions"], 5)
        self.assertTrue(p.exists())
        self.assertIsNone(self.acc.scan_downloads())   # idempotente
        self.assertEqual(len(self.acc.subscriptions()), 5)

    def test_el_mas_reciente_gana_y_uno_nuevo_se_reimporta(self):
        self.put("takeout-viejo-001.zip", age=7200, src="takeout-viejo.zip")
        self.put("takeout-nuevo-001.zip", age=3600, src="takeout-es.zip")
        self.acc.scan_downloads()
        self.assertEqual(self.acc.summary()["imported_file"], "takeout-nuevo-001.zip")
        self.put("takeout-nuevo-002.zip", age=100, src="takeout-en.zip")
        self.acc.scan_downloads()
        self.assertEqual(self.acc.summary()["imported_file"], "takeout-nuevo-002.zip")

    def test_ignora_lo_que_aun_se_descarga_y_zips_rotos(self):
        self.put("takeout-a.zip", age=1)
        self.assertIsNone(self.acc.scan_downloads())
        (self.dir / "dl" / "takeout-b.zip").write_bytes(b"no es un zip")
        p = self.dir / "dl" / "takeout-b.zip"
        os.utime(p, (time.time() - 60, time.time() - 60))
        self.assertIsNone(self.acc.scan_downloads())   # no lanza
        self.assertEqual(self.acc.summary()["subscriptions"], 0)

    def test_carpeta_que_descomprimio_el_navegador(self):
        # Safari abre el zip solo y deja la carpeta «Takeout» en Descargas.
        import zipfile
        with zipfile.ZipFile(self.zip("takeout-es419.zip")) as z:
            z.extractall(self.dir / "dl")
        t = time.time() - 600
        for f in (self.dir / "dl" / "Takeout").rglob("*"):
            os.utime(f, (t, t))
        r = self.acc.scan_downloads()
        self.assertEqual((r["subscriptions"], r["history"], r["file"]), (5, 5, "Takeout"))
        self.assertNotIn("ADSADSADS12", [e["id"] for e in self.acc.watch_history()])
        self.assertIsNone(self.acc.scan_downloads())   # idempotente
        self.assertTrue((self.dir / "dl" / "Takeout").exists())   # no se borra ni se mueve

    def test_carpeta_que_aun_se_copia_espera(self):
        import zipfile
        with zipfile.ZipFile(self.zip("takeout-en.zip")) as z:
            z.extractall(self.dir / "dl")
        self.assertIsNone(self.acc.scan_downloads())   # archivos recién escritos

    def test_carpeta_ajena_no_cuenta(self):
        (self.dir / "dl" / "Takeout").mkdir()
        (self.dir / "dl" / "Takeout" / "fotos.csv").write_text("a,b\n")
        os.utime(self.dir / "dl" / "Takeout" / "fotos.csv", (time.time() - 600, time.time() - 600))
        self.assertIsNone(self.acc.scan_downloads())

    def test_sin_carpeta(self):
        acc = YouTubeAccount(self.dir / "datos", self.dir / "no-existe", log=lambda m: None)
        self.assertIsNone(acc.scan_downloads())


class Canales(Base):
    def setUp(self):
        super().setUp()
        self.acc.import_zip(self.zip("takeout-en.zip"))
        self.calls = []
        self.feeds = {
            GOOGLE: atom(GOOGLE, "Google for Developers", [("g_new", "Nuevo G", "2025-09-10T10:00:00+00:00", False),
                                                           ("g_old", "Viejo G", "2025-09-01T10:00:00+00:00", False),
                                                           ("g_short", "Un short", "2025-09-12T10:00:00+00:00", True)]),
            MKBHD: atom(MKBHD, "Marques Brownlee", [("m_mid", "Medio M", "2025-09-05T10:00:00+00:00", False)]),
            FCC: urllib.error.HTTPError("u", 404, "no", {}, None),
        }

        def fetch(url):
            cid = url.split("channel_id=")[1]
            self.calls.append(cid)
            r = self.feeds.get(cid)
            if isinstance(r, Exception):
                raise r
            if r is None:
                raise OSError("sin red")
            return r
        self.acc.fetch = fetch
        self.pages, self.page_calls = {}, []   # página «Videos» de cada canal; sin entrada: sin red

        def page(url):
            cid = url.split("/channel/")[1].split("/")[0]
            self.page_calls.append(cid)
            r = self.pages.get(cid)
            if isinstance(r, Exception):
                raise r
            if r is None:
                raise OSError("sin red")
            return r
        self.acc.page_fetch = page

    def test_parse_feed_quita_shorts(self):
        vids = parse_feed(self.feeds[GOOGLE])
        self.assertEqual([v["id"] for v in vids], ["g_new", "g_old"])
        self.assertEqual(vids[0]["channel_id"], GOOGLE)
        self.assertEqual(vids[0]["published"], 1757498400)

    def test_refresh_tolera_404_y_errores_y_new_videos_ordena(self):
        r = self.acc.refresh_feeds()
        # FCC contesta 404 siempre: una revisión no basta para darlo por desaparecido.
        self.assertEqual((r["channels"], r["updated"], r["gone"], r["errors"]), (5, 2, 0, 3))
        self.assertEqual(sorted(set(self.calls)), sorted(c[0] for c in gen.CHANNELS))
        self.assertEqual(self.calls.count(GOOGLE), 1)   # al primer intento bueno no se repite
        vids = self.acc.new_videos()
        self.assertEqual([v["id"] for v in vids], ["g_new", "m_mid", "g_old"])   # por fecha, sin el short
        v = vids[0]
        self.assertEqual((v["title"], v["channel"], v["duration"], v["thumb"], v["channel_id"]),
                         ("Nuevo G", "Google for Developers", 0, "/yt/g_new/thumb.jpg", GOOGLE))
        self.assertEqual(len(self.acc.new_videos(limit=2)), 2)
        s = self.acc.summary()
        self.assertEqual((s["feeds_ok"], s["feeds_gone"], s["imported_file"]), (2, 0, "takeout-en.zip"))
        self.assertGreater(s["feeds_at"], 0)

    def test_parse_channel_page(self):
        html = channel_page("Marques Brownlee", [("rayrrXot17M", "Nothing Headphone", "1 day ago"),
                                                 ("pOX1l1edBME", "Apple Watch", "hace 2 semanas"),
                                                 ("zzzzzzzzzzz", "Estreno", "Se estrenará en 3 días"),
                                                 ("yyyyyyyyyyy", "Directo", "Transmitido hace 3 horas")])
        vids = parse_channel_page(html, MKBHD, now=2_000_000_000)
        self.assertEqual([(v["id"], v["channel"], v["channel_id"], v["published"]) for v in vids],
                         [("rayrrXot17M", "Marques Brownlee", MKBHD, 2_000_000_000 - 86400),
                          ("pOX1l1edBME", "Marques Brownlee", MKBHD, 2_000_000_000 - 14 * 86400),
                          ("yyyyyyyyyyy", "Marques Brownlee", MKBHD, 2_000_000_000 - 3 * 3600)])
        with self.assertRaises(ValueError):
            parse_channel_page("<html>nada</html>", MKBHD)

    def test_si_el_rss_falla_se_lee_la_pagina(self):
        self.feeds[MKBHD] = urllib.error.HTTPError("u", 404, "no", {}, None)
        self.pages[MKBHD] = channel_page("Marques Brownlee", [("pagina0001x", "Desde la página", "3 hours ago")])
        r = self.acc.refresh_feeds()
        self.assertIn("pagina0001x", [v["id"] for v in self.acc.new_videos()])
        self.assertEqual(r["updated"], 2)   # GOOGLE por RSS y MKBHD por su página
        self.assertIn(MKBHD, self.page_calls)
        self.assertNotIn(GOOGLE, self.page_calls)   # al que respondió por RSS no se le pide la página

    def test_la_pagina_se_pide_a_pocos_y_a_los_mas_atrasados(self):
        self.acc.page_max = 2
        r = self.acc.refresh_feeds()   # 3 canales sin RSS: solo 2 páginas
        self.assertEqual(len(self.page_calls), 2)

    def test_si_el_rss_no_responde_a_nadie_no_se_insiste(self):
        from ytaccount import FEED_TRIES
        self.acc.breaker = 4
        for cid in list(self.feeds):
            self.feeds[cid] = urllib.error.HTTPError("u", 404, "no", {}, None)
        self.acc.refresh_feeds()
        self.assertEqual(len(self.calls), 4 * FEED_TRIES)   # la primera tanda de 4 y ya no la quinta

    def test_404_al_azar_se_reintenta(self):
        # El RSS real contesta 404 más o menos la mitad de las veces aunque el canal exista.
        respuestas = {MKBHD: [urllib.error.HTTPError("u", 404, "no", {}, None), self.feeds[MKBHD]]}
        base = self.acc.fetch

        def al_azar(url):
            cid = url.split("channel_id=")[1]
            if respuestas.get(cid):
                r = respuestas[cid].pop(0)
                self.calls.append(cid)
                if isinstance(r, Exception):
                    raise r
                return r
            return base(url)
        self.acc.fetch = al_azar
        self.acc.refresh_feeds()
        self.assertEqual(self.calls.count(MKBHD), 2)
        self.assertIn("m_mid", [v["id"] for v in self.acc.new_videos()])

    def test_404_no_borra_lo_que_ya_habia_y_desaparece_solo_tras_varias_revisiones(self):
        from ytaccount import GONE_AFTER, FEED_TRIES
        self.acc.refresh_feeds()
        self.feeds[GOOGLE] = urllib.error.HTTPError("u", 404, "no", {}, None)
        self.pages[GOOGLE] = urllib.error.HTTPError("u", 404, "no", {}, None)   # la página tampoco existe
        for n in range(1, GONE_AFTER + 1):
            self.calls.clear()
            r = self.acc.refresh_feeds()
            self.assertEqual(self.calls.count(GOOGLE), FEED_TRIES)
            self.assertIn("g_new", [v["id"] for v in self.acc.new_videos()])   # lo de antes se queda
            self.assertEqual(self.acc.feeds[GOOGLE]["status"], "gone" if n >= GONE_AFTER else "error")
        self.assertEqual(r["gone"], 1)   # solo GOOGLE: a FCC no le falla la página, le falla la red
        self.feeds[GOOGLE] = atom(GOOGLE, "Google for Developers", [("g_otro", "Otro", "2025-09-20T10:00:00+00:00", False)])
        self.acc.refresh_feeds()
        self.assertEqual(self.acc.feeds[GOOGLE]["status"], "ok")   # volvió: cuenta desde cero

    def test_error_de_red_conserva_lo_anterior(self):
        self.acc.refresh_feeds()
        self.feeds[GOOGLE] = OSError("sin red")
        self.acc.refresh_feeds()
        self.assertIn("g_new", [v["id"] for v in self.acc.new_videos()])

    def test_maximo_4_a_la_vez(self):
        import threading
        activos, pico, lock = [0], [0], threading.Lock()
        base = self.acc.fetch

        def lento(url):
            with lock:
                activos[0] += 1
                pico[0] = max(pico[0], activos[0])
            time.sleep(0.05)
            with lock:
                activos[0] -= 1
            return base(url)
        self.acc.fetch = lento
        self.acc.refresh_feeds()
        self.assertLessEqual(pico[0], 4)
        self.assertGreaterEqual(pico[0], 2)

    def test_reimportar_conserva_canales_y_quita_desuscritos(self):
        self.acc.refresh_feeds()
        self.acc.subs = [s for s in self.acc.subs if s["id"] != MKBHD]   # ya no está suscrito
        self.assertNotIn("m_mid", [v["id"] for v in self.acc.new_videos()])


if __name__ == "__main__":
    unittest.main()
