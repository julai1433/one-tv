# Bibliotecas de otro programa (Plex, Jellyfin…): One TV las lee bien y no les cambia nada. Y la carpeta de One TV se
# sigue ordenando como siempre. Sin red: lo de internet se simula. Los videos de la biblioteca «estilo Plex» se hacen
# con ffmpeg (uno solo, de 2,5 min y 32x32, enlazado con muchos nombres); los del organizador son archivos vacíos
# «grandes» que no ocupan disco. Uso: python3 -m unittest pruebas/test_bibliotecas_ajenas.py
import json, os, shutil, subprocess, sys, tempfile, time, unittest
from unittest import mock
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mac"))
import artwork, folders, identify, library, organizer, subtitles_online
from artwork import Artwork
from folders import LibraryFolders
from identify import Identifier
from library import Library, video_id
from organizer import Organizer

HAY_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
SRT = b"1\n00:00:01,000 --> 00:00:02,000\nHola\n"


def grande(path, age=600):
    """Un video «grande» para el organizador (archivo disperso: no ocupa disco) que cambió hace `age` segundos."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.truncate(organizer.MIN_SIZE + 1)
    t = time.time() - age
    os.utime(path, (t, t))
    return path


def foto(path, color="red"):
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c={color}:s=200x300", "-frames:v", "1",
                    str(path)], check=True, capture_output=True)
    return path


def foto_de(path):
    """Imagen de mentira (para lo que solo mira nombres)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\xff\xd8\xff")
    return path


def todo(folder):
    """Lo que hay en una carpeta (rutas, tamaños y fechas): para ver que nada cambió."""
    out = {}
    for p in sorted(Path(folder).rglob("*")):
        st = p.lstat()
        out[str(p.relative_to(folder))] = (p.is_dir(), st.st_size, st.st_mtime_ns)
    return out


def info_falsa(path):
    """Lo que diría ffprobe de un video común (para armar la biblioteca sin ffmpeg)."""
    return {"duration": 3000.0, "start": 0.0, "audio": [], "subs": [],
            "video": {"index": 0, "codec": "h264", "profile": "High", "level": 41, "pix_fmt": "yuv420p",
                      "width": 1920, "height": 1080}}


def armar(lib, probe=info_falsa):
    """La biblioteca armada sin ffprobe: (raíz, ruta) de lo que encuentra, con la información de mentira."""
    entries = [(root, p, probe(p), p.stat()) for root, p in lib._walk()]
    lib._build(entries)
    return lib


def plex(base):
    """Una biblioteca acomodada para Plex: películas en su carpeta y sueltas, ediciones, partes, extras, códigos de
    Plex, series con «Season 01» y «Specials», y pósters junto a las películas y series."""
    archivos = [
        "Movies/Avatar (2009)/Avatar (2009).mkv",
        "Movies/Avatar (2009)/Avatar (2009)-trailer.mkv",            # extra de Plex: no sale
        "Movies/Avatar (2009)/Featurettes/Detrás de cámaras.mkv",    # carpeta de extras: no sale
        "Movies/Heat (1995).mkv",                                    # sueltas en Movies/
        "Movies/Alien (1979).mp4",
        "Movies/Blade Runner (1982) {edition-Director's Cut}/Blade Runner (1982) {edition-Director's Cut}.mkv",
        "Movies/Blade Runner (1982) {edition-Final Cut}/Blade Runner (1982) {edition-Final Cut}.mkv",
        "Movies/Kill Bill (2003)/Kill Bill (2003) - pt1.mkv",       # una película en dos partes
        "Movies/Kill Bill (2003)/Kill Bill (2003) - pt2.mkv",
        "Movies/Matrix (1999) {imdb-tt0133093}/Matrix (1999).mkv",   # con el código de Plex
        "Movies/Amelie (2001) {tmdb-194}/Amelie (2001).mkv",
        "TV Shows/La Serie (2020)/Season 01/La Serie (2020) - s01e01 - Piloto.mkv",
        "TV Shows/La Serie (2020)/Season 01/La Serie (2020) - s01e02 - Segundo.mkv",
        "TV Shows/La Serie (2020)/Season 02/la.serie.S02E01.1080p.WEB-DL.mkv",   # con otro nombre: misma serie
        "TV Shows/La Serie (2020)/Specials/La Serie (2020) - s00e01 - Especial.mkv",
        "TV Shows/Otra Serie (2018) {tvdb-12345}/Season 1/S01E01.mkv",           # sin nombre en el archivo
    ]
    return [base / a for a in archivos]


class Carpetas(unittest.TestCase):
    """Qué carpeta es de One TV y cuál de otro programa."""

    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.dir = Path(self._t.name).resolve()
        self.log = []

    def carpetas(self, roots, solo_leer=None):
        return LibraryFolders(roots, solo_leer, self.dir / "datos" / "carpetas.json", self.dir / "datos" / "subs",
                              log=self.log.append)

    def test_la_de_one_tv_vacia_o_con_sus_codigos(self):
        nueva = self.dir / "Nueva"
        nueva.mkdir()
        propia = self.dir / "Biblioteca"
        grande(propia / "Películas" / "Heat (1995) {imdb-tt0113277}" / "Heat (1995) {imdb-tt0113277}.mkv")
        (propia / "Series" / "La Serie (2020) {tvdb-12345}").mkdir(parents=True)
        f = self.carpetas([nueva, propia])
        self.assertTrue(f.own(nueva))
        self.assertTrue(f.own(propia))
        self.assertEqual(f.own_roots(), [nueva, propia])

    def test_la_de_plex_solo_se_lee(self):
        nas = self.dir / "NAS"
        for p in plex(nas):
            foto_de(p)
        f = self.carpetas([nas])
        self.assertFalse(f.own(nas))
        self.assertTrue(any("solo para leer" in m for m in self.log))

    def test_plex_en_espanol_con_peliculas_y_series_sin_codigos_tambien_es_ajena(self):
        nas = self.dir / "Videos"
        foto_de(nas / "Películas" / "Avatar (2009)" / "Avatar (2009).mkv")
        foto_de(nas / "Películas" / "Heat (1995)" / "Heat (1995).mkv")
        foto_de(nas / "Películas" / "Matrix (1999) {imdb-tt0133093}" / "Matrix (1999).mkv")   # una con código no basta
        foto_de(nas / "Series" / "La Serie (2020)" / "Season 01" / "La Serie - s01e01.mkv")
        self.assertFalse(self.carpetas([nas]).own(nas))

    def test_config_manda_en_los_dos_sentidos(self):
        nas, propia = self.dir / "NAS", self.dir / "Biblioteca"
        foto_de(nas / "Movies" / "Heat (1995).mkv")
        (propia / "Películas").mkdir(parents=True)
        f = self.carpetas([nas, propia], {str(nas): False, str(propia): True})
        self.assertTrue(f.own(nas))
        self.assertFalse(f.own(propia))
        self.assertFalse(self.carpetas([nas], [str(nas)]).own(nas))   # también como lista

    @unittest.skipIf(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0), "permisos de Unix")
    def test_sin_permiso_de_escritura_solo_se_lee(self):
        ro = self.dir / "SoloLectura"
        (ro / "Películas").mkdir(parents=True)
        os.chmod(ro, 0o555)
        self.addCleanup(os.chmod, ro, 0o755)
        f = self.carpetas([ro], {str(ro): False})   # ni aunque config diga que la ordene
        self.assertFalse(f.own(ro))
        self.assertEqual(f.subtitle_dirs(ro / "Películas" / "x.mkv"), [self.dir / "datos" / "subs" / video_id(ro / "Películas" / "x.mkv")])

    def test_desconectada_no_se_toca(self):
        f = self.carpetas([self.dir / "NoEsta"])
        self.assertIsNone(f.own(self.dir / "NoEsta"))
        self.assertEqual(f.own_roots(), [])

    def test_una_vez_decidida_no_cambia_sola(self):
        lib = self.dir / "Biblioteca"
        lib.mkdir()
        f = self.carpetas([lib])                 # la ve vacía: es de One TV
        foto_de(lib / "Pelicula.Suelta.2001.mkv")   # y luego le sueltan videos sin ordenar
        self.assertTrue(f.own(lib))
        self.assertTrue(self.carpetas([lib]).own(lib))   # también al volver a arrancar

    def test_si_en_esa_ruta_aparece_otro_disco_se_vuelve_a_mirar(self):
        punto = self.dir / "nas"
        punto.mkdir()
        self.carpetas([punto])                   # vacía (el NAS todavía no se montó): de One TV
        foto_de(punto / "Movies" / "Heat (1995).mkv")
        estado = self.dir / "datos" / "carpetas.json"
        guardado = json.loads(estado.read_text())
        guardado[str(punto.resolve())]["disco"] += 1   # como si ahora fuera otro disco (el NAS ya montado)
        estado.write_text(json.dumps(guardado))
        self.assertFalse(self.carpetas([punto]).own(punto))


class Organizador(unittest.TestCase):
    """El organizador no mueve nada en una carpeta de otro programa; en la de One TV, como siempre."""

    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.dir = Path(self._t.name).resolve()
        self.nas = self.dir / "NAS"
        for p in plex(self.nas):
            grande(p)
        grande(self.nas / "Suelta.Pelicula.2010.1080p.mkv")   # suelta en la raíz: en la de One TV se movería
        grande(self.nas / "Películas" / "Otra (2011)" / "Otra (2011).mkv")
        self.propia = self.dir / "Biblioteca"
        grande(self.propia / "Películas" / "Heat (1995) {imdb-tt0113277}" / "Heat (1995) {imdb-tt0113277}.mkv")
        self.down = self.dir / "Torrents"
        self.down.mkdir()
        self.log = []
        p = mock.patch.object(organizer, "TRANSMISSION_PREFS", self.dir / "no-existe.plist")
        p.start()
        self.addCleanup(p.stop)

    def tearDown(self):
        self._t.cleanup()

    def organizador(self, roots):
        return Organizer([str(r) for r in roots], [str(self.down)], self.dir / "datos" / "organizador.json",
                         log=self.log.append)

    @staticmethod
    def identificar(path):
        return {"kind": "movie", "imdb": "tt0000001", "title": "Película", "year": 2010,
                "folder": ("Películas", "Película (2010) {imdb-tt0000001}"), "file": "Película (2010) {imdb-tt0000001}"}

    def test_en_la_carpeta_de_plex_no_se_mueve_nada(self):
        antes = todo(self.nas)
        org = self.organizador([self.nas])
        with mock.patch.object(Organizer, "identify", side_effect=self.identificar) as ident:
            self.assertEqual(org.candidates(), [])
            self.assertEqual(org.run(), [])
            ident.assert_not_called()
        self.assertEqual(todo(self.nas), antes)

    def test_lo_que_se_baja_va_a_la_carpeta_de_one_tv(self):
        grande(self.down / "Pelicula.2010.1080p.mkv", age=60)
        antes = todo(self.nas)
        org = self.organizador([self.nas, self.propia])   # la de Plex primero en la lista
        with mock.patch.object(Organizer, "identify", side_effect=self.identificar):
            hecho = org.run()
        self.assertEqual([Path(a["dest"]).parent.parent.parent for a in hecho], [self.propia])
        self.assertTrue((self.propia / "Películas" / "Película (2010) {imdb-tt0000001}").is_dir())
        self.assertEqual(todo(self.nas), antes)

    def test_si_todas_son_de_otro_programa_lo_bajado_no_se_agrega_y_avisa(self):
        grande(self.down / "Pelicula.2010.1080p.mkv", age=60)
        antes = todo(self.nas)
        org = self.organizador([self.nas])
        self.assertFalse(org.pending_downloads())
        with mock.patch.object(Organizer, "identify", side_effect=self.identificar):
            self.assertEqual(org.run(), [])
        self.assertEqual(sum("Descargas" in m for m in self.log), 1)   # un solo aviso
        self.assertEqual(todo(self.nas), antes)

    def test_la_carpeta_de_one_tv_se_sigue_ordenando_como_hoy(self):
        grande(self.propia / "Suelta.Pelicula.2010.1080p.mkv")
        grande(self.propia / "Películas" / "Sin Codigo 2010" / "Sin.Codigo.2010.mkv")
        org = self.organizador([self.propia])
        encontrados = {(p.name, how) for p, how in org.candidates()}
        self.assertEqual(encontrados, {("Suelta.Pelicula.2010.1080p.mkv", "move"), ("Sin.Codigo.2010.mkv", "move")})
        with mock.patch.object(Organizer, "identify", side_effect=self.identificar):
            hecho = org.run()
        self.assertEqual(len([a for a in hecho if "dest" in a]), 1)   # el segundo ya «estaba»
        self.assertFalse((self.propia / "Suelta.Pelicula.2010.1080p.mkv").exists())
        self.assertTrue((self.propia / "Películas" / "Película (2010) {imdb-tt0000001}"
                         / "Película (2010) {imdb-tt0000001}.mkv").exists())

    def test_el_doblaje_no_se_agrega_junto_a_un_video_de_otro_programa(self):
        from dubbing import Dubbing
        with mock.patch("threading.Thread"):
            dub = Dubbing(self.dir / "env", self.dir / "x.py", self.dir / "datos" / "doblajes.json", self.dir / "usados")
        f = LibraryFolders([self.nas, self.propia], None, self.dir / "datos" / "carpetas.json", log=lambda *_: None)
        dub.can_write_next_to = f.can_write_next_to
        otra = grande(self.dir / "Otra version.mkv")
        with mock.patch("dubbing.probe", side_effect=AssertionError("no debía ni mirarlo")):
            self.assertFalse(dub.consider(otra, self.nas / "Movies" / "Heat (1995).mkv", "link"))


class LeerPlex(unittest.TestCase):
    """Una biblioteca de Plex se lee bien: películas, ediciones, partes, series agrupadas, especiales al final."""

    @classmethod
    def setUpClass(cls):
        cls._t = tempfile.TemporaryDirectory()
        cls.dir = Path(cls._t.name)
        cls.nas = cls.dir / "NAS"
        for p in plex(cls.nas):
            foto_de(p)
        cls.lib = armar(Library([str(cls.nas)], cls.dir / "cache"))
        cls.por_titulo = {it["full_title"]: it for it in cls.lib.items.values()}

    @classmethod
    def tearDownClass(cls):
        cls._t.cleanup()

    def test_peliculas(self):
        peliculas = sorted(it["title"] for it in self.lib.items.values() if it["kind"] == "movie")
        self.assertEqual(peliculas, ["Alien (1979)", "Amelie (2001)", "Avatar (2009)", "Blade Runner (1982) · Director's Cut",
                                     "Blade Runner (1982) · Final Cut", "Heat (1995)", "Kill Bill (2003) · Parte 1",
                                     "Kill Bill (2003) · Parte 2", "Matrix (1999)"])

    def test_series_agrupadas_por_su_carpeta_con_especiales_al_final(self):
        series = {s["title"]: s for s in self.lib.series}
        self.assertEqual(sorted(series), ["La Serie", "Otra Serie"])
        la = series["La Serie"]
        self.assertEqual(la["episodes"], 4)
        self.assertEqual([t["title"] for t in la["seasons"]], ["Temporada 1", "Temporada 2", "Especiales"])
        primero = self.lib.items[la["poster"]]
        self.assertEqual((primero["season"], primero["ep"]), (1, "E1"))   # «Empezar» no empieza por un especial
        especial = next(i for t in la["seasons"] if t["season"] == 0 for i in [t["items"][0]["id"]])
        ultimo = next(i for t in la["seasons"] if t["season"] == 2 for i in [t["items"][-1]["id"]])
        self.assertNotIn(especial, self.lib.next_ep)
        self.assertNotEqual(self.lib.next_ep.get(ultimo), especial)
        self.assertEqual(primero["show_year"], 2020)

    def test_codigos_de_plex_y_de_jellyfin(self):
        codes = Identifier(self.dir / "cache")
        por_titulo = {it["title"]: it for it in self.lib.items.values()}
        self.assertEqual(codes.movie_code(por_titulo["Matrix (1999)"]), "tt0133093")
        otra = next(s for s in self.lib.series if s["title"] == "Otra Serie")
        self.assertEqual(codes.show_code(otra, self.lib), "12345")
        self.assertEqual(identify.IMDB_TAG.search("Peli (2001) [imdbid-tt0012345]").group(1), "tt0012345")
        self.assertEqual(identify.TVDB_TAG.search("Serie [tvdbid-777]").group(1), "777")
        peliculas, series = codes.todo(self.lib)
        self.assertEqual(peliculas["peli:amelie (2001)"][0], ("tmdb", "194"))   # Wikidata dirá su código de IMDb
        self.assertEqual(peliculas["peli:avatar (2009)"], (None, "Avatar", 2009))
        self.assertNotIn("peli:matrix (1999)", peliculas)
        self.assertEqual(list(series.values()), [(None, "La Serie", 2020)])

    def test_una_carpeta_de_temporada_sin_peliculas_sigue_siendo_coleccion(self):
        with tempfile.TemporaryDirectory() as t:
            raiz = Path(t)
            for n in (1, 2, 3):
                foto_de(raiz / "Documentales" / "Planeta Tierra" / f"Capitulo {n}.mkv")
            lib = armar(Library([str(raiz)], raiz / "cache"))
            self.assertEqual([s["title"] for s in lib.series], ["Planeta Tierra"])


class IdentificarPorNombre(unittest.TestCase):
    """Lo que no trae código se identifica por su nombre y año (sin tocar los archivos) y así tiene póster y sinopsis."""

    def test_busca_por_nombre_y_anio_y_lo_recuerda(self):
        with tempfile.TemporaryDirectory() as t:
            raiz = Path(t) / "NAS"
            for p in plex(raiz):
                foto_de(p)
            lib = armar(Library([str(raiz)], Path(t) / "cache"))
            pedidos = []

            def internet(url, timeout=20):
                pedidos.append(url)
                if "wikidata" in url:
                    return {"results": {"bindings": [{"from": {"value": "194"}, "to": {"value": "tt0211915"}}]}}
                if "tvmaze" in url:
                    return [{"show": {"name": "La Serie", "premiered": "2020-01-10", "externals": {"thetvdb": 999}}},
                            {"show": {"name": "La Serie", "premiered": "1990-01-10", "externals": {"thetvdb": 111}}}]
                if "avatar" in url:
                    return {"d": [{"id": "tt0499549", "l": "Avatar", "y": 2009, "qid": "movie"}]}
                return {"d": []}

            codes = Identifier(Path(t) / "cache")
            with mock.patch.object(identify, "_get_json", side_effect=internet), mock.patch.object(identify, "PAUSE", 0):
                codes.fetch_all(lib, log=lambda *_: None)
                por_titulo = {it["title"]: it for it in lib.items.values()}
                self.assertEqual(codes.movie_code(por_titulo["Avatar (2009)"]), "tt0499549")
                self.assertEqual(codes.movie_code(por_titulo["Amelie (2001)"]), "tt0211915")   # por su {tmdb-194}
                la = next(s for s in lib.series if s["title"] == "La Serie")
                self.assertEqual(codes.show_code(la, lib), "999")   # la del año que dice la carpeta
                antes = len(pedidos)
                codes.fetch_all(lib, log=lambda *_: None)   # lo ya buscado no se vuelve a buscar
                self.assertEqual(len(pedidos), antes)
            self.assertTrue(any("avatar%202009" in u for u in pedidos))
            art = Artwork(Path(t) / "cache")
            art.codes = codes
            trabajos = art.jobs_for(lib)
            self.assertIn((por_titulo["Avatar (2009)"]["id"], "imdb", "tt0499549"), trabajos)
            self.assertIn(("serie-laserie", "tvdb", "999"), trabajos)


@unittest.skipUnless(HAY_FFMPEG, "hace falta ffmpeg")
class PostersLocales(unittest.TestCase):
    """El póster que ya está junto a la película o la serie se usa antes que el de internet, sin tocarlo."""

    def test_poster_folder_show_y_fanart(self):
        with tempfile.TemporaryDirectory() as t:
            raiz = Path(t) / "NAS"
            for p in plex(raiz):
                foto_de(p)
            foto(raiz / "Movies" / "Avatar (2009)" / "poster.jpg")
            foto(raiz / "Movies" / "Heat (1995).jpg", "blue")                      # suelta: «Película.jpg» al lado
            foto(raiz / "Movies" / "Kill Bill (2003)" / "folder.jpg", "green")
            foto(raiz / "TV Shows" / "La Serie (2020)" / "show.jpg", "yellow")
            foto(raiz / "Movies" / "Matrix (1999) {imdb-tt0133093}" / "fanart.jpg", "white")   # fondo: después de internet
            antes = todo(raiz)
            lib = armar(Library([str(raiz)], Path(t) / "cache"))
            art = Artwork(Path(t) / "cache")
            ids = {it["title"]: it["id"] for it in lib.items.values()}
            trabajos = art.jobs_for(lib)
            fuentes = {(k, f) for k, f, _ in trabajos}
            self.assertIn((ids["Avatar (2009)"], "local"), fuentes)
            self.assertIn((ids["Heat (1995)"], "local"), fuentes)
            self.assertIn((ids["Kill Bill (2003) · Parte 2"], "local"), fuentes)
            self.assertIn(("serie-laserie", "local"), fuentes)
            matrix = [f for k, f, _ in trabajos if k == ids["Matrix (1999)"]]
            self.assertEqual(matrix, ["imdb", "fondo"])
            with mock.patch.object(artwork, "_imdb_image", return_value=None):   # sin póster en internet: queda el fondo
                art.fetch_all(trabajos, log=lambda *_: None)
            for key in (ids["Avatar (2009)"], ids["Heat (1995)"], "serie-laserie", ids["Matrix (1999)"]):
                self.assertTrue(art.path(key).exists(), key)
            self.assertEqual(todo(raiz), antes)   # nada cambió en la biblioteca
            # Si después aparece el póster en internet, reemplaza al fondo (pasada una semana del último intento).
            art.index[ids["Matrix (1999)"]]["net"] = 0
            with mock.patch.object(artwork, "_imdb_image", return_value="https://ejemplo.invalid/p.jpg"), \
                    mock.patch.object(artwork, "_get", return_value=(raiz / "Movies" / "Avatar (2009)" / "poster.jpg").read_bytes()):
                art.fetch_all(art.jobs_for(lib), log=lambda *_: None)
            self.assertNotIn("local", art.index[ids["Matrix (1999)"]])


class SubtitulosBajados(unittest.TestCase):
    """Un subtítulo bajado para un video de otro programa se guarda en la carpeta de One TV y la biblioteca lo encuentra."""

    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.dir = Path(self._t.name)
        self.addCleanup(setattr, subtitles_online, "subtitle_dirs", subtitles_online.subtitle_dirs)

    def tearDown(self):
        self._t.cleanup()

    def test_en_la_de_plex_va_a_la_carpeta_de_one_tv(self):
        nas = self.dir / "NAS"
        for p in plex(nas):
            foto_de(p)
        antes = todo(nas)
        guardados = self.dir / "datos" / "subtitulos"
        f = LibraryFolders([nas], None, self.dir / "datos" / "carpetas.json", guardados, log=lambda *_: None)
        subtitles_online.subtitle_dirs = f.subtitle_dirs
        lib = Library([str(nas)], self.dir / "cache")
        lib.own_subs = guardados
        armar(lib)
        heat = next(it for it in lib.items.values() if it["title"] == "Heat (1995)")
        hecho = subtitles_online.save_next_to_video(heat, SRT, "ea")
        self.assertEqual(hecho.parent, guardados / heat["id"])
        self.assertEqual(hecho.name, "Heat (1995).es.opensubtitles-latino.srt")
        self.assertEqual(todo(nas), antes)   # nada nuevo junto a los videos
        armar(lib)
        heat = lib.items[heat["id"]]
        self.assertEqual([(s["lang"], s["file"]) for s in heat["subs"]], [("spa", str(hecho))])
        # Con el código de idioma que eligen los subtítulos automáticos, igual.
        otro = subtitles_online.save_next_to_video(heat, SRT, "en", file_lang="en")
        self.assertEqual(otro.parent, guardados / heat["id"])

    def test_en_la_de_one_tv_sigue_junto_al_video(self):
        propia = self.dir / "Biblioteca"
        video = foto_de(propia / "Películas" / "Heat (1995) {imdb-tt0113277}" / "Heat (1995) {imdb-tt0113277}.mkv")
        f = LibraryFolders([propia], None, self.dir / "datos" / "carpetas.json", self.dir / "datos" / "subtitulos")
        subtitles_online.subtitle_dirs = f.subtitle_dirs
        hecho = subtitles_online.save_next_to_video({"path": str(video)}, SRT, "en")
        self.assertEqual(hecho, video.with_name("Heat (1995) {imdb-tt0113277}.en.opensubtitles.srt"))
        self.assertFalse((self.dir / "datos" / "subtitulos").exists())


@unittest.skipUnless(HAY_FFMPEG, "hace falta ffmpeg")
class BibliotecaDeVerdad(unittest.TestCase):
    """La biblioteca de Plex leída de verdad (ffprobe): videos de 2,5 min hechos con ffmpeg, enlazados con cada nombre."""

    def test_se_lee_entera_y_sin_tocarla(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            muestra = t / "muestra.mkv"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=32x32:r=1:d=160",
                            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(muestra)], check=True, capture_output=True)
            raiz = t / "NAS"
            for p in plex(raiz):
                p.parent.mkdir(parents=True, exist_ok=True)
                os.link(muestra, p)
            antes = todo(raiz)
            lib = Library([str(raiz)], t / "cache")
            lib.scan(force=True)
            titulos = sorted(it["full_title"] for it in lib.items.values())
            self.assertEqual(len(titulos), 14)   # sin el tráiler ni lo de Featurettes
            self.assertIn("La Serie · T0 E1 · Especial", titulos)
            self.assertIn("Otra Serie · T1 E1", titulos)
            self.assertEqual(todo(raiz), antes)


class Configurar(unittest.TestCase):
    """«./cine configurar» pregunta si otro programa usa la carpeta cuando ya tiene videos, y lo anota."""

    def test_pregunta_y_anota(self):
        import cine
        with tempfile.TemporaryDirectory() as t:
            nas = Path(t) / "NAS"
            for p in plex(nas):
                foto_de(p)
            with mock.patch("builtins.input", return_value=""), mock.patch("builtins.print"):
                anotado = cine._ask_other_program(str(nas), nas, None)   # Enter: lo sugerido (sí, es de otro)
            self.assertEqual(anotado, {str(nas): True})
            with mock.patch("builtins.input", return_value="n"), mock.patch("builtins.print"):
                anotado = cine._ask_other_program(str(nas), nas, {"/otra/carpeta": True})
            self.assertEqual(anotado, {str(Path("/otra/carpeta").resolve()): True, str(nas): False})
            vacia = Path(t) / "Vacia"
            vacia.mkdir()
            with mock.patch("builtins.input", side_effect=AssertionError("no debía preguntar")):
                self.assertIsNone(cine._ask_other_program(str(vacia), vacia, None))


if __name__ == "__main__":
    unittest.main()
