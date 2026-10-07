# Pruebas sin red del contrato de la API de la fase 4: idioma por aparato, nombres de pista, regla para
# empezar, «seguir viendo» mezclado, tus listas y marcas.
# Uso: python3 -m unittest discover -s pruebas -p 'test_fase4_api.py'
import json, sys, tempfile, threading, unittest, urllib.error
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mac"))
import cine
from mylists import MyLists
import library
import metadata
from library import Library, choose_tracks
from store import Store
from playqueue import PlayQueue
from youtube import YouTube, YouTubeError
from ytaccount import YouTubeAccount


def vid(n):
    return f"vid{n:08d}"[:11]


def audio(index, lang, title="", codec="eac3", channels=6, default=False):
    return {"index": index, "codec": codec, "channels": channels, "lang": lang, "title": title, "default": default}


def sub(key, lang, label, forced=False):
    return {"key": key, "lang": lang, "label": label, "forced": forced, "stream": 0}


def item(tracks, subs=(), path="/pelis/Pelicula/Pelicula.mkv", kind="movie", **extra):
    return {"id": "abc123", "path": path, "title": "Peli", "full_title": "Peli", "kind": kind, "duration": 6000,
            "mode": "copy", "reason": "", "info": {"audio": list(tracks), "subs": [], "video": None},
            "subs": list(subs), **extra}


class Base(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.tmp = Path(self._t.name)
        self.lib = Library([str(self.tmp)], self.tmp)

    def tearDown(self):
        self._t.cleanup()

    def pub(self, it, original=""):
        self.lib.original_lookup = (lambda i: original) if original else None
        return self.lib.public_item(it)


class PreferenciasPorAparato(Base):
    def test_aparato_nuevo_es_original_y_sin_subtitulos(self):
        st = Store(self.tmp / "p.json")
        st.set_prefs(ytAutoplay=True)
        self.assertEqual(st.prefs_for("nuevo"), {"ytAutoplay": True, "audioLang": "original", "subLang": "off"})

    def test_se_guardan_por_aparato_y_sobreviven_a_reiniciar(self):
        st = Store(self.tmp / "p.json")
        st.set_device_prefs("A", audioLang="spa", subLang="eng")
        st.set_device_prefs("B", audioLang="original")
        st = Store(self.tmp / "p.json")
        self.assertEqual(st.prefs_for("A")["audioLang"], "spa")
        self.assertEqual(st.prefs_for("A")["subLang"], "eng")
        self.assertEqual(st.prefs_for("B"), {"audioLang": "original", "subLang": "off"})
        self.assertEqual(st.prefs_for("C")["audioLang"], "original")

    def test_solo_cambia_lo_que_se_manda(self):
        st = Store(self.tmp / "p.json")
        st.set_device_prefs("A", audioLang="spa", subLang="eng")
        st.set_device_prefs("A", subLang="off")
        self.assertEqual(st.prefs_for("A")["audioLang"], "spa")
        self.assertEqual(st.prefs_for("A")["subLang"], "off")

    def test_migracion_no_hereda_las_globales_ni_pierde_datos(self):
        (self.tmp / "p.json").write_text(json.dumps({"progress": {"x": {"p": 99, "t": 5}},
                                                      "prefs": {"audioLang": "fre", "subLang": "eng"}}))
        st = Store(self.tmp / "p.json")
        p = st.prefs_for("aparato-nuevo")
        self.assertEqual((p["audioLang"], p["subLang"]), ("original", "off"))
        self.assertEqual(st.prefs_for(None), {"audioLang": "fre", "subLang": "eng"})   # sin aparato: como hoy
        st.set_device_prefs("aparato-nuevo", audioLang="spa")
        data = json.loads((self.tmp / "p.json").read_text())
        self.assertEqual(data["progress"], {"x": {"p": 99, "t": 5}})
        self.assertEqual(data["prefs"], {"audioLang": "fre", "subLang": "eng"})
        self.assertEqual(data["device_prefs"], {"aparato-nuevo": {"audioLang": "spa"}})

    def test_recordar_pistas_original_contra_idioma(self):
        class Falso(cine.App):
            def __init__(s, lib, store):
                s.library, s.store = lib, store
        st = Store(self.tmp / "p.json")
        app = Falso(self.lib, st)
        it = item([audio(1, "eng", default=True), audio(2, "spa", "Latino")],
                  [sub("e3", "spa", "Español (Latino)"), sub("e4", "eng", "Inglés")])
        self.lib.items = {"abc123": it}
        self.lib.original_lookup = lambda i: "eng"
        app.remember_tracks(it, 0, -1, "A")           # la original, sin subtítulos
        self.assertEqual((st.prefs_for("A")["audioLang"], st.prefs_for("A")["subLang"]), ("original", "off"))
        app.remember_tracks(it, 1, 0, "A")            # el doblaje latino con subtítulos en español
        self.assertEqual((st.prefs_for("A")["audioLang"], st.prefs_for("A")["subLang"]), ("spa", "spa"))
        self.assertEqual(st.prefs, {})                # nada global
        app.remember_tracks(it, 1, 1, None)           # sin aparato: como antes
        self.assertEqual(st.prefs, {"audioLang": "spa", "subLang": "eng"})


class NombresDePista(Base):
    def test_latino_espana_y_generico(self):
        it = item([audio(1, "eng", default=True), audio(2, "spa", "Latino"), audio(3, "spa", "Castellano"),
                   audio(4, "spa", "Español")], path="/pelis/Sin pista de nada/x.mkv")
        names = [a["name"] for a in self.pub(it, "eng")["audio"]]
        self.assertEqual(names, ["Inglés (original)", "Español (latino)", "Español (España)", "Español"])

    def test_sin_jerga_y_con_datos_tecnicos_aparte(self):
        a = self.pub(item([audio(1, "eng", codec="eac3", channels=6, default=True),
                           audio(2, "fre", codec="aac", channels=2)]), "eng")["audio"]
        self.assertEqual((a[0]["name"], a[0]["tech"]), ("Inglés (original)", "EAC3 5.1"))
        self.assertEqual((a[1]["name"], a[1]["tech"]), ("Francés", "AAC estéreo"))
        self.assertTrue(all(k in a[0] for k in ("label", "lang", "hls")))   # lo de hoy sigue ahí

    def test_pista_agregada(self):
        extra = audio("x0", "spa", "Latino", codec="aac", channels=2)
        extra["file"] = "/pelis/Pelicula.latino.m4a"
        a = self.pub(item([audio(1, "eng", default=True), extra]), "eng")["audio"]
        self.assertEqual(a[1]["name"], "Español (latino) · agregado")
        self.assertTrue(a[1]["ext"] and not a[1]["original"])

    def test_latino_por_el_nombre_del_archivo(self):
        it = item([audio(1, "spa", "", default=True)], path="/pelis/Peli Latino 1080p/Peli.mkv")
        self.assertEqual(self.pub(it)["audio"][0]["name"], "Español (latino, original)")   # la única pista
        it = item([audio(1, "eng", default=True), audio(2, "spa")], path="/pelis/Peli Latino 1080p/Peli.mkv")
        self.assertEqual(self.pub(it, "eng")["audio"][1]["name"], "Español (latino)")

    def test_mismo_nombre_se_numera(self):
        a = self.pub(item([audio(1, "eng", default=True), audio(2, "eng", "Commentary")]), "eng")["audio"]
        self.assertEqual([x["name"] for x in a], ["Inglés (original)", "Inglés (comentarios)"])
        b = self.pub(item([audio(1, "eng", default=True), audio(2, "fre"), audio(3, "fre")]), "eng")["audio"]
        self.assertEqual([x["name"] for x in b], ["Inglés (original)", "Francés 1", "Francés 2"])

    def test_subtitulos(self):
        s = self.pub(item([audio(1, "eng", default=True)],
                          [sub("e1", "spa", "Español (Latino)"), sub("e2", "spa", "Español (España)"),
                           sub("e3", "eng", "Inglés"), sub("e4", "eng", "Inglés (forzados)", forced=True),
                           sub("e5", "fre", "Francés (SDH)")]))["subs"]
        self.assertEqual([x["name"] for x in s], ["Español (latino)", "Español (España)", "Inglés",
                                                   "Inglés (forzados)", "Francés (para sordos)"])
        self.assertTrue(all("label" in x and "lang" in x and "url" in x for x in s))

    def test_original_por_idioma_de_wikidata(self):
        it = item([audio(1, "eng", default=True), audio(2, "jpn")])
        a = self.pub(it, "jpn")["audio"]
        self.assertEqual([x["original"] for x in a], [False, True])
        # «fra» de Wikidata y «fre» del archivo son el mismo idioma
        a = self.pub(item([audio(1, "eng", default=True), audio(2, "fre")]), "fra")["audio"]
        self.assertEqual([x["original"] for x in a], [False, True])

    def test_respaldo_sin_idioma_original(self):
        a = self.pub(item([audio(1, "eng"), audio(2, "fre", default=True)]))["audio"]
        self.assertEqual([x["original"] for x in a], [False, True])       # la predeterminada
        a = self.pub(item([audio(1, "eng"), audio(2, "fre")]))["audio"]
        self.assertEqual([x["original"] for x in a], [True, False])       # si no, la primera
        a = self.pub(item([audio(1, "eng", default=True), audio(2, "fre")]), "kor")["audio"]
        self.assertEqual([x["original"] for x in a], [True, False])       # idioma que ninguna pista tiene

    def test_pista_aparte_nunca_es_la_original(self):
        extra = audio("x0", "eng", "", codec="aac", channels=2)
        a = self.pub(item([audio(1, "fre", default=True), extra]), "eng")["audio"]
        self.assertEqual([x["original"] for x in a], [True, False])

    def test_pelicula_en_espanol_la_original_no_es_la_latina(self):
        it = item([audio(1, "spa", "Latino", default=True), audio(2, "spa", "Castellano")],
                  path="/pelis/x/x.mkv")
        a = self.pub(it, "spa")["audio"]
        self.assertEqual([x["original"] for x in a], [False, True])

    def test_sin_audio(self):
        a = self.pub(item([]))["audio"]
        self.assertEqual(len(a), 1)
        self.assertTrue(a[0]["original"])

    def test_varios_idiomas_originales_gana_el_primero_que_haya(self):
        it = item([audio(1, "spa", default=True), audio(2, "fre")])
        a = self.pub(it, ["eng", "fre", "spa"])["audio"]
        self.assertEqual([x["original"] for x in a], [False, True])

    def test_subtitulo_sin_idioma_ni_nombre(self):
        s = self.pub(item([audio(1, "eng", default=True)], [sub("e1", "und", "UND")]))["subs"]
        self.assertEqual(s[0]["name"], "Subtítulos")

    def test_solo_una_original(self):
        a = self.pub(item([audio(1, "eng"), audio(2, "eng"), audio(3, "spa")]), "eng")["audio"]
        self.assertEqual(sum(x["original"] for x in a), 1)


class ReglaParaEmpezar(Base):
    def caso(self, tracks, subs, audio_lang, sub_lang, original=""):
        return choose_tracks(self.pub(item(tracks, subs), original), audio_lang, sub_lang)

    def test_original_usa_la_pista_original(self):
        t = [audio(1, "spa", "Latino", default=True), audio(2, "eng")]
        self.assertEqual(self.caso(t, [], "original", "off", "eng"), (1, -1))

    def test_original_sin_dato_usa_la_predeterminada(self):
        t = [audio(1, "eng"), audio(2, "spa", default=True)]
        self.assertEqual(self.caso(t, [], "original", "off"), (1, -1))

    def test_un_idioma_toma_la_primera_de_ese_idioma(self):
        t = [audio(1, "eng"), audio(2, "spa", "Latino"), audio(3, "spa", "Castellano")]
        self.assertEqual(self.caso(t, [], "spa", "off", "eng")[0], 1)

    def test_idioma_que_no_hay_cae_en_la_original(self):
        t = [audio(1, "eng"), audio(2, "fre")]
        self.assertEqual(self.caso(t, [], "spa", "off", "fre")[0], 1)

    def test_subtitulos(self):
        s = [sub("a", "eng", "Inglés (forzados)", forced=True), sub("b", "eng", "Inglés"), sub("c", "spa", "Español")]
        t = [audio(1, "eng")]
        self.assertEqual(self.caso(t, s, "original", "off")[1], -1)
        self.assertEqual(self.caso(t, s, "original", "eng")[1], 1)      # el completo antes que el forzado
        self.assertEqual(self.caso(t, s, "original", "spa")[1], 2)
        self.assertEqual(self.caso(t, s, "original", "fre")[1], -1)     # no hay de ese idioma
        solo_forzados = [sub("a", "eng", "Inglés (forzados)", forced=True)]
        self.assertEqual(self.caso(t, solo_forzados, "original", "eng")[1], 0)
        self.assertEqual(self.caso(t, [], "original", "eng")[1], -1)


class Falso(cine.App):
    """App sin arrancar nada: solo lo que usan estas pruebas."""

    def __init__(self, tmp):
        self.store = Store(Path(tmp) / "progreso.json")
        self.lists = MyLists(Path(tmp) / "listas.json")   # Favoritos y listas de One TV
        self.youtube = YouTube(tmp, tmp, ytdlp="/nada")
        self.account = YouTubeAccount(tmp, tmp, log=lambda m: None)
        self.queue = PlayQueue(Path(tmp) / "cola.json")
        self.library = Library([str(tmp)], tmp)
        self.played = []
        self._because, self._because_busy, self._because_lock = None, False, threading.Lock()
        self.server_url = "http://mac"

        self.iphone_url, self.dubbing = None, type("D", (), {"current": None})()
        self._player, self._player_lock = (__import__("time").time(), None), threading.Lock()   # sin preguntarle al Roku

        class Tele:
            ip = "0.0.0.0"

            def player(s):
                return None

            def play(s, ident, url, **kw):
                self.played.append(ident)
        self.roku = Tele()
        self.youtube.resolve = lambda v: {"info": {"id": v, "title": f"T {v}", "channel": "C", "duration": 60,
                                                   "chapters": self.chapters.get(v, [])}}
        self.chapters = {}

    def tell_tv_to_refresh(self):
        pass


class SeguirViendoMezclado(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.app = Falso(self._t.name)

    def tearDown(self):
        self._t.cleanup()

    def test_mezcla_por_fecha_y_una_entrada_por_serie(self):
        items = {"peli": {"kind": "movie"},
                 "s1e1": {"kind": "episode", "show": "S", "next": "s1e2"},
                 "s1e2": {"kind": "episode", "show": "S", "next": ""},
                 "otra": {"kind": "movie"}}
        prog = self.app.store.progress
        prog["peli"] = {"p": 500, "t": 100}
        prog["s1e1"] = {"p": 0, "t": 300}        # terminado: entra el siguiente
        prog["s1e2"] = {"p": 0, "t": 10}         # más viejo, misma serie: no repite
        prog[f"yt:{vid(1)}"] = {"p": 40, "t": 200}
        prog[f"yt:{vid(2)}"] = {"p": 0, "t": 250}   # terminado: no sale
        prog["otra"] = {"p": 30, "t": 50}
        self.app.youtube.history.insert(0, {"id": vid(1), "title": "Uno", "channel": "Canal", "duration": 90, "t": 200})
        out = self.app.continue_watching(items)
        self.assertEqual([(e["kind"], e["id"], e["t"]) for e in out],
                         [("item", "s1e2", 300), ("yt", vid(1), 200), ("item", "peli", 100), ("item", "otra", 50)])
        self.assertEqual(out[0], {"kind": "item", "id": "s1e2", "p": 0, "t": 300})
        self.assertEqual(out[1], {"kind": "yt", "id": vid(1), "title": "Uno", "channel": "Canal",
                                  "thumb": f"/yt/{vid(1)}/thumb.jpg", "p": 40, "duration": 90, "t": 200})

    def test_keep_watching_no_cambia(self):
        items = {"peli": {"kind": "movie"}}
        self.app.store.progress["peli"] = {"p": 500, "t": 100}
        self.assertEqual(self.app.store.keep_watching(items), [{"id": "peli", "p": 500}])


class TusListas(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.app = Falso(self._t.name)
        acc = self.app.account
        acc.lists = [
            {"id": "PLaaaaaaaaaaaa", "title": "Música", "videos": [{"id": vid(1), "t": 1}, {"id": vid(2), "t": 1}]},
            {"id": "PLbbbbbbbbbbbb", "title": "Cocina", "videos": [{"id": vid(3), "t": 1}]},
            {"id": "PLcccccccccccc", "title": "Viajes", "videos": [{"id": vid(4), "t": 1}]},
            {"id": "", "title": "Sin id", "videos": []},
        ]
        acc.history = [{"id": vid(3), "title": "Receta", "channel": "Chef", "t": 5000},
                       {"id": vid(1), "title": "Canción", "channel": "Banda", "t": 1000}]

    def tearDown(self):
        self._t.cleanup()

    def test_orden_por_la_mas_reciente_de_las_tres_fuentes(self):
        # Música: visto en la app a las 9000; Cocina: historial del Takeout a las 5000;
        # Viajes: reproducida desde la app a las 7000; «Sin id»: nunca.
        self.app.store.progress[f"yt:{vid(2)}"] = {"p": 10, "t": 9000}
        self.app.account.played["PLcccccccccccc"] = {"t": 7000}
        rows = self.app.yt_home()["playlists"]
        self.assertEqual([r["title"] for r in rows], ["Música", "Viajes", "Cocina", "Sin id"])
        self.assertEqual([r["last_played"] for r in rows], [9000, 7000, 5000, 0])
        self.assertEqual(rows[0], {"id": "PLaaaaaaaaaaaa", "title": "Música", "count": 2, "last_played": 9000,
                                   "thumb": f"/yt/{vid(1)}/thumb.jpg", "source": "takeout"})
        self.assertTrue(rows[3]["id"].startswith("tk-") and rows[3]["thumb"] == "" and rows[3]["count"] == 0)

    def test_empate_sin_escuchar_va_por_titulo(self):
        self.app.account.history = []
        self.assertEqual([r["title"] for r in self.app.yt_home()["playlists"]],
                         ["Cocina", "Música", "Sin id", "Viajes"])

    def test_lista_de_youtube_reproducida_desde_la_app(self):
        self.app.account.mark_played("PLzzzzzzzzzzzz", "Lista pública", 12, "/yt/x/thumb.jpg")
        r = [x for x in self.app.yt_home()["playlists"] if x["source"] == "youtube"]
        self.assertEqual(len(r), 1)
        self.assertEqual((r[0]["title"], r[0]["count"]), ("Lista pública", 12))
        self.assertGreater(r[0]["last_played"], 0)

    def test_titulos_del_takeout(self):
        # Música: uno en el historial, otro solo por oEmbed. La lista no es pública (yt-dlp falla).
        pedidos = []

        def oembed(v):
            pedidos.append(v)
            if v == vid(2):
                return {"title": "Otra canción", "author_name": "Banda"}
            raise urllib.error.HTTPError("u", 401, "privado", {}, None)
        self.app.account.oembed = oembed

        def falla(pid):
            raise YouTubeError("privada")
        self.app.youtube.playlist_videos = falla
        r = self.app.yt_playlist("PLaaaaaaaaaaaa")
        self.assertTrue(r["ok"])
        self.assertEqual([v["title"] for v in r["videos"]], ["Canción", "Otra canción"])
        self.assertEqual(pedidos, [vid(2)])
        # caché: la segunda vez no se pide nada
        self.app.yt_playlist("PLaaaaaaaaaaaa")
        self.assertEqual(pedidos, [vid(2)])
        # Viajes: oEmbed no lo conoce -> «Video privado», y se recuerda
        r = self.app.yt_playlist("PLcccccccccccc")
        self.assertEqual(r["videos"][0]["title"], "Video privado")
        self.assertTrue(r["videos"][0]["private"])
        self.app.yt_playlist("PLcccccccccccc")
        self.assertEqual(pedidos, [vid(2), vid(4)])
        # el archivo de caché sobrevive
        again = YouTubeAccount(self._t.name, self._t.name, log=lambda m: None)
        self.assertIn(vid(2), again.titles["videos"])

    def test_titulos_de_la_lista_publica_con_una_sola_llamada(self):
        self.app.account.history = []
        llamadas = []

        def publica(pid):
            llamadas.append(pid)
            return {"videos": [{"id": vid(1), "title": "Uno", "channel": "A"}, {"id": vid(2), "title": "Dos", "channel": "B"}]}
        self.app.youtube.playlist_videos = publica
        self.app.account.oembed = lambda v: self.fail("no debía pedir oEmbed")
        r = self.app.yt_playlist("PLaaaaaaaaaaaa")
        self.assertEqual([v["title"] for v in r["videos"]], ["Uno", "Dos"])
        self.assertEqual(llamadas, ["PLaaaaaaaaaaaa"])

    def test_sin_internet_no_se_guarda_como_privado(self):
        self.app.account.history = []

        def sin_red(v):
            raise OSError("sin red")
        self.app.account.oembed = sin_red
        self.app.youtube.playlist_videos = lambda pid: (_ for _ in ()).throw(YouTubeError("no"))
        r = self.app.yt_playlist("PLcccccccccccc")
        self.assertEqual(r["videos"][0]["title"], "Video de YouTube")
        self.assertNotIn(vid(4), self.app.account.titles["videos"])

    def test_lista_que_no_es_del_takeout_va_a_youtube(self):
        self.app.youtube.playlist_videos = lambda pid: {"id": pid, "title": "Pública", "videos": []}
        r = self.app.yt_playlist("PLzzzzzzzzzzzz")
        self.assertEqual((r["ok"], r["title"]), (True, "Pública"))

    def test_reproducir_la_lista(self):
        self.app.account.history = []
        self.app.account.oembed = lambda v: {"title": f"T {v}", "author_name": ""}
        self.app.youtube.playlist_videos = lambda pid: (_ for _ in ()).throw(YouTubeError("no"))
        self.app.queue.add({"kind": "yt", "id": "viejo000000", "title": "ya estaba", "thumb": ""})
        self.app.account.lists[0]["videos"].append({"id": vid(5), "t": 1})
        r = self.app.yt_playlist_play("PLaaaaaaaaaaaa")
        self.assertEqual(r, {"ok": True, "count": 3, "total": 3})
        self.assertEqual(self.app.played, [f"yt:{vid(1)}"])
        self.assertEqual([e["id"] for e in self.app.queue.items()], [vid(2), vid(5), "viejo000000"])
        self.assertGreater(self.app.yt_home()["playlists"][0]["last_played"], 0)
        self.assertEqual(self.app.yt_home()["playlists"][0]["title"], "Música")

    def test_lista_larga_no_saca_lo_que_ya_estaba_en_la_fila(self):
        self.app.account.history = []
        self.app.account.oembed = lambda v: {"title": f"T {v}", "author_name": ""}
        self.app.youtube.playlist_videos = lambda pid: (_ for _ in ()).throw(YouTubeError("no"))
        viejos = cine.MAX_ITEMS - 20   # a la fila le caben 20 más
        for n in range(viejos):
            self.app.queue.add({"kind": "yt", "id": f"viejo{n:06d}", "title": "ya estaba", "thumb": ""})
        self.app.account.lists[0]["videos"] = [{"id": vid(i), "t": 1} for i in range(1, 121)]
        r = self.app.yt_playlist_play("PLaaaaaaaaaaaa")
        self.assertEqual(r, {"ok": True, "count": 21, "total": 120})   # 1 ya + 20 que caben
        ids = [e["id"] for e in self.app.queue.items()]
        self.assertEqual(len(ids), cine.MAX_ITEMS)
        self.assertEqual(ids[:20], [vid(i) for i in range(2, 22)])
        self.assertEqual(ids[20:], [f"viejo{n:06d}" for n in range(viejos)])

    def test_reproducir_desde_un_video_y_al_azar(self):
        self.app.account.oembed = lambda v: {"title": f"T {v}", "author_name": ""}
        self.app.youtube.playlist_videos = lambda pid: (_ for _ in ()).throw(YouTubeError("no"))
        self.app.account.lists[0]["videos"] += [{"id": vid(5), "t": 1}, {"id": vid(6), "t": 1}]
        r = self.app.yt_playlist_play("PLaaaaaaaaaaaa", start=2)
        self.assertEqual(r["count"], 2)
        self.assertEqual(self.app.played, [f"yt:{vid(5)}"])
        self.assertEqual([e["id"] for e in self.app.queue.items()], [vid(6)])
        self.app.queue.clear()
        r = self.app.yt_playlist_play("PLaaaaaaaaaaaa", shuffle=True, start=1)
        self.assertEqual(self.app.played[-1], f"yt:{vid(2)}")     # el elegido va primero
        self.assertEqual(sorted(e["id"] for e in self.app.queue.items()), sorted([vid(1), vid(5), vid(6)]))
        self.app.queue.clear()
        self.app.yt_playlist_play("PLaaaaaaaaaaaa", shuffle=True)
        self.assertEqual(len(self.app.queue.items()), 3)
        self.assertEqual(self.app.yt_playlist_play("PLaaaaaaaaaaaa", start=99)["ok"], False)

    def test_privados_no_se_reproducen(self):
        self.app.account.history = []
        self.app.account.oembed = lambda v: (_ for _ in ()).throw(urllib.error.HTTPError("u", 404, "x", {}, None))
        self.app.youtube.playlist_videos = lambda pid: (_ for _ in ()).throw(YouTubeError("no"))
        r = self.app.yt_playlist_play("PLaaaaaaaaaaaa")
        self.assertFalse(r["ok"])
        self.assertEqual(self.app.played, [])

    def test_sin_tele_no_toca_la_fila_ni_anota(self):
        self.app.account.oembed = lambda v: {"title": "t", "author_name": ""}
        self.app.youtube.playlist_videos = lambda pid: (_ for _ in ()).throw(YouTubeError("no"))
        self.app.roku.play = lambda *a, **k: (_ for _ in ()).throw(OSError("apagada"))
        r = self.app.yt_playlist_play("PLaaaaaaaaaaaa")
        self.assertFalse(r["ok"])
        self.assertEqual(self.app.queue.items(), [])
        self.assertEqual(self.app.account.played, {})


class Marcas(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.app = Falso(self._t.name)

    def tearDown(self):
        self._t.cleanup()

    def test_app_marks_de_youtube_e_intro(self):
        self.app.chapters[vid(1)] = [{"start": 0, "end": 30, "title": "A"}, {"start": 30, "end": 60, "title": "B"}]
        # los capítulos ya no son marcas de «saltar»: se ven como marcadores en la barra de avance
        self.assertEqual(self.app.marks(f"yt:{vid(1)}"), [])

        class Intros:
            def marks(s, i):
                return [{"kind": "intro", "start": 50, "end": 90, "label": "Saltar intro"}]
        self.app.intros = Intros()
        self.assertEqual(self.app.marks("episodio"), [{"kind": "intro", "start": 50, "end": 90, "label": "Saltar intro"}])

    def test_marca_activa_ocho_segundos_o_hasta_el_final(self):
        marks = [{"kind": "intro", "start": 50, "end": 90, "label": "Saltar intro"}]
        act = cine.active_mark
        self.assertIsNone(act(marks, 49.9))
        self.assertEqual(act(marks, 50), {"label": "Saltar intro", "end": 90})
        self.assertEqual(act(marks, 57.9), {"label": "Saltar intro", "end": 90})
        self.assertIsNone(act(marks, 58))                 # pasaron los 8 s
        self.assertIsNone(act(marks, 90))
        self.assertEqual(act(marks, 50), {"label": "Saltar intro", "end": 90})   # al volver a entrar, otra vez
        corta = [{"kind": "chapter", "start": 10, "end": 13, "label": "x"}]
        self.assertEqual(act(corta, 12.9), {"label": "x", "end": 13})
        self.assertIsNone(act(corta, 13))                 # hasta el final si es antes
        self.assertIsNone(act([{"kind": "intro", "start": 5, "end": 5, "label": "vacía"}], 5))
        self.assertIsNone(act([], 10))

    def test_playing_mark_en_status(self):
        # un video de YouTube con capítulos no ofrece «saltar»: el teléfono no muestra botón
        self.app.chapters[vid(1)] = [{"start": 0, "end": 100, "title": "A"}, {"start": 100, "end": 200, "title": "B"}]
        self.app.youtube.streams[vid(1)] = {"info": self.app.youtube.resolve(vid(1))["info"], "at": __import__("time").time()}
        self.app.store.report(f"yt:{vid(1)}", 3, 200, "tick")
        self.assertIsNone(self.app.status()["playing"]["mark"])

    def test_ajuste_nombre_del_capitulo_es_de_la_casa(self):
        self.assertNotIn("chapterTitles", self.app.store.prefs_for("tele-1"))   # sin elegir: el cliente asume «Sí»
        self.app.store.set_prefs(chapterTitles=False)
        self.assertIs(self.app.store.prefs_for("tele-1")["chapterTitles"], False)
        self.assertIs(self.app.store.prefs_for("telefono-2")["chapterTitles"], False)

    def test_playing_mark_de_intro_de_la_biblioteca(self):
        class Intros:
            def marks(s, i):
                return [{"kind": "intro", "start": 20, "end": 70, "label": "Saltar intro"}]
        self.app.intros = Intros()
        self.app.library.items["ep1"] = {"id": "ep1", "path": "/x/a.mkv", "title": "E1", "full_title": "S · E1",
                                         "kind": "episode", "duration": 3000, "mode": "copy", "reason": "",
                                         "info": {"audio": [audio(1, "eng", default=True)], "subs": [], "video": None},
                                         "subs": [], "show": "S", "season": 1, "ep": "E1", "ep_title": ""}
        self.app.queue = PlayQueue(Path(self._t.name) / "c2.json")
        self.app.store.report("ep1", 25, 3000, "tick")
        self.assertEqual(self.app.status()["playing"]["mark"], {"label": "Saltar intro", "end": 70})
        self.app.store.report("ep1", 500, 3000, "tick")
        self.assertIsNone(self.app.status()["playing"]["mark"])


class IdiomaOriginalEnMetadata(unittest.TestCase):
    def test_lee_p364_de_la_respuesta_de_wikidata(self):
        data = {"results": {"bindings": [
            {"code": {"value": "tt1"}, "iso": {"value": "fre"}, "es": {"value": "https://es.wikipedia.org/wiki/Amelie"}},
            {"code": {"value": "tt1"}, "iso": {"value": "fre"}},
            {"code": {"value": "tt2"}, "en": {"value": "https://en.wikipedia.org/wiki/Parasite_(film)"}, "iso": {"value": "kor"}},
            {"code": {"value": "tt3"}}]}}
        out = metadata._parse_titles(data)
        self.assertEqual(out["tt1"], {"es": "Amelie", "orig": ["fre"]})
        self.assertEqual(out["tt2"], {"en": "Parasite (film)", "orig": ["kor"]})
        self.assertEqual(out["tt3"], {})

    def test_guarda_en_cache_y_los_episodios_usan_el_de_su_serie(self):
        with tempfile.TemporaryDirectory() as tmp:
            md = metadata.Metadata(tmp)
            md._store_original("m1", ["jpn", "eng"])
            md._store_original("serie-severance", ["eng"])
            md._save()
            md = metadata.Metadata(tmp)
            self.assertEqual(md.original_lang({"id": "m1", "kind": "movie"}), "jpn")
            self.assertEqual(md.original_langs({"id": "m1", "kind": "movie"}), ["jpn", "eng"])
            self.assertEqual(md.original_lang({"id": "e1", "kind": "episode", "show": "Severance"}), "eng")
            self.assertEqual(md.original_lang({"id": "otra", "kind": "movie"}), "")
            self.assertFalse(md._pending_original("m1"))
            self.assertTrue(md._pending_original("otra"))
            md._store_original("vacia", None)    # se buscó y no había: se reintenta a las dos semanas, no ya
            self.assertFalse(md._pending_original("vacia"))
            md.data["_original"]["vacia"]["t"] -= metadata.RETRY_AFTER + 1
            self.assertTrue(md._pending_original("vacia"))
            self.assertEqual(md.desc("_original"), "")   # no estorba a las sinopsis


if __name__ == "__main__":
    unittest.main()


class PistaSinIdioma(unittest.TestCase):
    """Una pista sin idioma marcado que es la original toma el idioma de la obra (o «Idioma original»)."""
    def pista(self, lang, index, default=False):
        return {"lang": lang, "index": index, "title": "", "codec": "aac", "channels": 2, "default": default}

    def test_toma_el_idioma_de_la_obra(self):
        from library import _audio_names
        self.assertEqual(_audio_names([self.pista("und", 1, True)], {}, 0, [False], "eng")[0][0], "Inglés (original)")

    def test_sin_dato_de_la_obra(self):
        from library import _audio_names
        self.assertEqual(_audio_names([self.pista("und", 1, True)], {}, 0, [False], "")[0][0], "Idioma original")

    def test_las_demas_sin_idioma_siguen_numeradas(self):
        from library import _audio_names
        names = [n for n, _ in _audio_names([self.pista("und", 1, True), self.pista("und", 2)], {}, 0,
                                            [False, False], ["fre", "eng"])]
        self.assertEqual(names, ["Francés (original)", "Pista 2"])
