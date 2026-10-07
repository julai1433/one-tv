# Subtítulos que se bajan solos (mac/subs_auto.py) y el cliente de OpenSubtitles (mac/subtitles_online.py), sin red:
# un OpenSubtitles falso (en memoria y, para el cliente, un servidor falso en esta computadora) y videos de mentira en
# una carpeta temporal. Prioridades, reserva, cupo y su renovación, 429, lo que no existe, lo que ya está, nombres de
# archivo y que el video nunca se toca.
# Uso: python3 -m unittest discover -s pruebas -p 'test_subtitulos_automaticos.py'
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MAC = Path(__file__).resolve().parent.parent / "mac"
sys.path.insert(0, str(MAC))
import subs_auto
import subtitles_online
from library import LANGS, SUB_NAME_LANGS
from store import Store
from subs_auto import (AutoSubtitles, original_of, pick, present_langs, release_score, wanted_langs)
from subtitles_online import OpenSubtitles, SubtitleError, parse_reset, save_next_to_video

SRT = b"1\r\n00:00:01,000 --> 00:00:02,500\r\nHola\r\n\r\n2\r\n00:00:03,000 --> 00:00:04,000\r\nAdios\r\n"
T0 = datetime(2026, 3, 10, 15, 0).timestamp()   # «ahora» en las pruebas
DAY = 24 * 3600


def audio(lang, default=True, index=1):
    return {"index": index, "codec": "aac", "channels": 2, "lang": lang, "title": "", "default": default}


def emb(lang, codec="subrip", forced=False, index=3, title=""):
    return {"index": index, "codec": codec, "lang": lang, "title": title, "forced": forced}


def res(file_id, lang, release="", downloads=0, match=False, ai=False, hi=False, foreign=False, season=None,
        episode=None, show=""):
    return {"file_id": file_id, "lang": lang, "release": release, "downloads": downloads, "match": match, "ai": ai,
            "hi": hi, "trusted": False, "foreign": foreign, "season": season, "episode": episode, "show": show}


class Biblio:
    """Biblioteca falsa con lo que usa subs_auto: items, get, next_ep y scan (que vuelve a listar los .srt aparte
    como lo hace mac/library.py: idioma por el nombre)."""

    def __init__(self, root):
        self.root = Path(root)
        self.items, self.next_ep, self.scans = {}, {}, 0

    def add(self, rel, audio_langs=("eng",), embedded=(), mtime=T0 - 400 * DAY, kind="movie", show="", season=0,
            ep="", title=None):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(hashlib.sha256(rel.encode()).digest() * 8192)   # 256 KB de «video»
        os.utime(path, (mtime, mtime))
        item_id = hashlib.sha1(str(path).encode()).hexdigest()[:12]
        self.items[item_id] = {
            "id": item_id, "path": str(path), "title": title or path.stem, "full_title": title or path.stem,
            "kind": kind, "show": show, "season": season, "ep": ep, "mtime": mtime,
            "info": {"audio": [audio(l, n == 0, n + 1) for n, l in enumerate(audio_langs)], "subs": list(embedded)},
            "subs": []}
        self._list_subs(self.items[item_id])
        return item_id

    def _list_subs(self, it):
        """Lo mismo que hace la biblioteca con los subtítulos aparte: el idioma sale de lo que el nombre agrega."""
        video = Path(it["path"])
        out = []
        for f in sorted(video.parent.iterdir()):
            if f.suffix.lower() != ".srt" or not f.stem.lower().startswith(video.stem.lower()):
                continue
            label = f.stem[len(video.stem):]
            lang = next((code for rx, code in SUB_NAME_LANGS if rx.search(label)), "und")
            if lang == "und":
                m = re.search(r"\.([a-z]{2,3})(?:\.|$)", label.lower())
                lang = m.group(1) if m and m.group(1) in LANGS else "und"
            out.append({"key": f"x{len(out)}", "lang": lang, "label": label, "file": str(f),
                        "forced": bool(re.search(r"(?i)forced|forzad", label))})
        it["subs"] = out

    def get(self, item_id):
        return self.items.get(item_id)

    def scan(self, force=False):
        self.scans += 1
        for it in self.items.values():
            self._list_subs(it)


class OSFalso:
    """OpenSubtitles falso: busca en un catálogo {(ruta, idioma): [resultados]} y cuenta el cupo como la API."""

    def __init__(self, catalog=None, remaining=20, allowed=20, reset_at=T0 + 3 * 3600, username="alguien"):
        self.catalog = catalog if catalog is not None else {}
        self.server_remaining, self.allowed, self.reset_at = remaining, allowed, reset_at
        self.username, self.configured = username, True
        self.quota = {"allowed": None, "remaining": None, "reset_at": None, "t": 0}
        self.searches, self.downloads, self.infos = [], [], 0
        self.errors = []          # errores a lanzar en las próximas búsquedas
        self.lie_remaining = None  # lo que dice /infos/user si no coincide con la verdad (para probar el 406)
        self._seq = 0

    def _note(self, **kw):
        self._seq += 1
        self.quota.update({k: v for k, v in kw.items() if v is not None}, t=self._seq)

    def user_info(self):
        self.infos += 1
        said = self.server_remaining if self.lie_remaining is None else self.lie_remaining
        self._note(allowed=self.allowed, remaining=said)
        return {"allowed_downloads": self.allowed, "remaining_downloads": said}

    def search(self, item, lang, parent_imdb=None):
        self.searches.append((item["id"], lang, parent_imdb))
        if self.errors:
            raise self.errors.pop(0)
        return [dict(r) for r in self.catalog.get((item["path"], lang), [])]

    def download(self, file_id):
        if self.server_remaining <= 0:
            self._note(remaining=0, reset_at=self.reset_at)
            raise SubtitleError("Se acabaron las descargas de hoy en OpenSubtitles.", code=406, quota=True,
                                reset_at=self.reset_at)
        self.server_remaining -= 1
        self.downloads.append(file_id)
        self._note(remaining=self.server_remaining, reset_at=self.reset_at)
        return SRT, self.server_remaining

    def renew(self):
        self.server_remaining = self.allowed


class Base(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.tmp = Path(self._t.name)
        self.lib = Biblio(self.tmp / "Biblioteca")
        self.now = [T0]
        self.logs, self.sleeps = [], []
        self.os = OSFalso()
        self.store = Store(self.tmp / "progreso.json")

    def tearDown(self):
        self._t.cleanup()

    def auto(self, cfg=None, originals=None, **kw):
        return AutoSubtitles(self.os, self.lib, self.tmp / "datos" / "subtitulos_automaticos.json",
                             cfg or {"opensubtitles": {"api_key": "x"}}, original_langs=originals or (lambda it: []),
                             store=self.store, log=self.logs.append, series_imdb=kw.pop("series_imdb", lambda c: {}),
                             clock=lambda: self.now[0], sleep=self.sleeps.append, **kw)

    def offer(self, item_id, lang, *results):
        self.os.catalog[(self.lib.items[item_id]["path"], lang)] = list(results)

    def offer_all(self, langs=("spa", "eng")):
        n = 1000
        for item_id in self.lib.items:
            for lang in langs:
                code = {"spa": "ea", "eng": "en"}.get(lang, "ja")
                n += 1
                self.offer(item_id, lang, res(n, code, downloads=10))


class QueFalta(Base):
    def test_idiomas_que_se_quieren(self):
        self.assertEqual(wanted_langs("eng"), ["spa", "eng"])
        self.assertEqual(wanted_langs("jpn"), ["spa", "eng", "jpn"])
        self.assertEqual(wanted_langs("spa"), [])
        self.assertEqual(wanted_langs(""), ["spa", "eng"])          # no se sabe: español e inglés
        self.assertEqual(wanted_langs("xyz"), ["spa", "eng"])       # un idioma que OpenSubtitles no tiene

    def test_idioma_original(self):
        pel = self.lib.items[self.lib.add("P/Pel.mkv", audio_langs=("jpn",))]
        self.assertEqual(original_of(pel), "jpn")                            # sin dato de la obra: el audio
        self.assertEqual(original_of(pel, lambda it: ["ko"]), "kor")         # el de la obra manda
        multi = self.lib.items[self.lib.add("P/Multi.mkv", audio_langs=("spa", "fre"))]
        # Varios idiomas en la obra: el primero que tenga pista (aunque la predeterminada sea un doblaje).
        self.assertEqual(original_of(multi, lambda it: ["fre", "ita", "spa"]), "fre")
        self.assertEqual(original_of(multi, lambda it: ["ger", "eng"]), "ger")   # ninguno con pista: el primero
        latino = self.lib.items[self.lib.add("P/Peli Latino/Peli.mkv", audio_langs=("und",))]
        self.assertEqual(original_of(latino), "spa")                         # sin idioma marcado, pero dice «Latino»
        self.assertEqual(original_of(self.lib.items[self.lib.add("P/Nada.mkv", audio_langs=("und",))]), "")

    def test_lo_que_ya_tiene_no_se_baja(self):
        dentro = self.lib.add("P/Dentro.mkv", embedded=[emb("spa")])
        imagen = self.lib.add("P/Imagen.mkv", embedded=[emb("spa", codec="hdmv_pgs_subtitle")])
        forzados = self.lib.add("P/Forzados.mkv", embedded=[emb("eng", forced=True), emb("spa", index=4,
                                                                                            title="Forced")])
        aparte = self.lib.add("P/Aparte/Aparte.mkv")
        (self.tmp / "Biblioteca/P/Aparte/Aparte.en.srt").write_bytes(SRT)
        (self.tmp / "Biblioteca/P/Aparte/Aparte.es.forced.srt").write_bytes(SRT)
        espanola = self.lib.add("P/Espanola.mkv", audio_langs=("spa",))
        japonesa = self.lib.add("P/Japonesa.mkv", audio_langs=("jpn",), embedded=[emb("jpn")])
        self.lib.scan()
        self.assertEqual(present_langs(self.lib.items[dentro]), {"spa"})
        self.assertEqual(present_langs(self.lib.items[imagen]), set())       # imagen: la TV no la puede mostrar
        self.assertEqual(present_langs(self.lib.items[forzados]), set())     # forzados: no cuentan
        self.assertEqual(present_langs(self.lib.items[aparte]), {"eng"})
        jobs, _ = self.auto().plan()
        got = {(j["id"], j["lang"]) for j in jobs}
        self.assertEqual(got, {(dentro, "eng"), (imagen, "spa"), (imagen, "eng"), (forzados, "spa"),
                               (forzados, "eng"), (aparte, "spa"), (japonesa, "spa"), (japonesa, "eng")})
        self.assertNotIn(espanola, {j["id"] for j in jobs})                  # hablada en español: nada

    def test_prioridades(self):
        ep = {}
        for n in range(1, 9):
            ep[n] = self.lib.add(f"Series/Serie (2020) {{tvdb-123}}/Season 01/Serie (2020) - S01E0{n}.mkv",
                                 kind="episode", show="Serie", season=1, ep=f"E{n}")
        for n in range(1, 8):
            self.lib.next_ep[ep[n]] = ep[n + 1]
        vieja = self.lib.add("Películas/Vieja (1990)/Vieja (1990).mkv")
        nueva = self.lib.add("Películas/Nueva (2025)/Nueva (2025).mkv", mtime=T0 - 2 * DAY)
        japonesa = self.lib.add("Películas/Japonesa (2001)/Japonesa (2001).mkv", audio_langs=("jpn",))
        empezada = self.lib.add("Películas/Empezada (1999)/Empezada (1999).mkv")
        self.store.progress = {ep[2]: {"p": 0, "t": T0 - 3600},           # E2 terminado: sigue E3
                               empezada: {"p": 600, "t": T0 - 7200}}      # a medias
        jobs, _ = self.auto().plan()
        order = [(j["id"], j["lang"]) for j in jobs]
        spa = [i for i, lang in order if lang == "spa"]
        # Seguir viendo (E3 y los 5 que siguen, luego la empezada), lo nuevo, y lo demás.
        self.assertEqual(spa[:8], [ep[3], ep[4], ep[5], ep[6], ep[7], ep[8], empezada, nueva])
        self.assertEqual(set(spa[8:]), {vieja, japonesa, ep[1], ep[2]})
        langs = [lang for _, lang in order]
        self.assertEqual(langs, sorted(langs, key=lambda l: {"spa": 0, "eng": 1}.get(l, 2)))   # todo español primero
        self.assertEqual(order[-1], (japonesa, "jpn"))                       # el original, al final
        self.assertEqual([i for i, lang in order if lang == "eng"][:2], [ep[3], ep[4]])

    def test_lo_que_se_esta_viendo_va_primero(self):
        a = self.lib.add("P/A.mkv")
        b = self.lib.add("P/B.mkv", mtime=T0 - DAY)
        self.store.now = {"id": a, "p": 10, "d": 100, "state": "play", "t": __import__("time").time()}
        jobs, _ = self.auto().plan()
        self.assertEqual([j["id"] for j in jobs if j["lang"] == "spa"], [a, b])


class Cupo(Base):
    def setUp(self):
        super().setUp()
        for n in range(6):
            self.lib.add(f"P/Peli{n}.mkv")
        self.offer_all()

    def test_reserva_y_renovacion(self):
        self.os.server_remaining = 5
        a = self.auto()
        wait = a.run_once()
        self.assertEqual(len(self.os.downloads), 3)                        # 5 - reserva de 2
        self.assertEqual(self.os.server_remaining, subs_auto.RESERVE)      # quedan para pedir uno a mano
        self.assertAlmostEqual(wait, 3 * 3600 + 60, delta=1)              # hasta que se renueve
        searches = len(self.os.searches)
        self.now[0] += 3600                                               # antes de renovarse: nada
        a.run_once()
        self.assertEqual((len(self.os.downloads), len(self.os.searches)), (3, searches))
        self.now[0] = T0 + 3 * 3600 + 120                                 # ya se renovó
        self.os.renew()
        self.os.reset_at = T0 + 27 * 3600
        a.run_once()
        self.assertEqual(len(self.os.downloads), 12)                       # el resto (12 hacen falta en total)
        self.assertEqual(self.os.server_remaining, 20 - 9)
        self.assertIn("no falta nada más", self.logs[-1])

    def test_gasta_todo_menos_la_reserva(self):
        self.os.server_remaining = 10
        self.auto().run_once()
        self.assertEqual(len(self.os.downloads), 8)
        self.assertEqual(self.os.server_remaining, 2)

    def test_406_corta_la_tanda_y_espera_la_renovacion(self):
        self.os.server_remaining, self.os.lie_remaining = 1, 15   # dice 15 pero en verdad queda 1
        a = self.auto()
        wait = a.run_once()
        self.assertEqual(len(self.os.downloads), 1)
        self.assertAlmostEqual(wait, 3 * 3600 + 60, delta=1)
        self.assertEqual(self.os.quota["remaining"], 0)
        searches = len(self.os.searches)
        self.now[0] += 600
        a.run_once()
        self.assertEqual(len(self.os.searches), searches)                 # no se busca nada hasta renovarse

    def test_429_espera_lo_que_pide(self):
        self.os.errors = [SubtitleError("espera", code=429, wait=120)]
        a = self.auto()
        wait = a.run_once()
        self.assertEqual(wait, 120)
        self.assertEqual(self.os.downloads, [])
        self.assertEqual(a.state["videos"], {})                           # nada se marca como intentado

    def test_sin_conexion_no_marca_nada(self):
        self.os.errors = [SubtitleError("No hay conexión con OpenSubtitles.")]
        a = self.auto()
        self.assertEqual(a.run_once(), subs_auto.CHECK_EVERY)
        self.assertEqual(a.state["videos"], {})
        self.assertIn("se sigue en una hora", self.logs[-1])

    def test_el_cupo_se_recuerda_al_reiniciar(self):
        self.os.server_remaining = 4
        self.auto().run_once()
        self.assertEqual(len(self.os.downloads), 2)
        otro_cliente = OSFalso(self.os.catalog, remaining=2)
        self.os = otro_cliente
        self.now[0] += 60
        self.auto().run_once()                                             # mismo archivo de datos
        self.assertEqual((otro_cliente.downloads, otro_cliente.searches, otro_cliente.infos), ([], [], 0))

    def test_resumen_en_el_registro_y_en_el_estado(self):
        self.os.server_remaining = 5
        self.lib.add("P/Japonesa.mkv", audio_langs=("jpn",))
        a = self.auto()
        self.assertEqual(a.status()["text"], "")                          # antes de la primera tanda
        a.run_once()
        line = self.logs[-1]
        # La japonesa va primero (P/Japonesa antes que P/Peli0) y no tiene subtítulos en el catálogo falso.
        self.assertRegex(line, r"^✓ Subtítulos automáticos: 3 bajados hoy \(3 en español\); faltan 11 \(1 todavía "
                               r"no existe en OpenSubtitles; se vuelve a buscar en unos días\); "
                               r"quedan 2 de 20 descargas de hoy; siguen hoy a las \d\d:\d\d$")
        st = a.status()
        self.assertEqual(st["text"], "subtítulos automáticos: 3 bajados hoy, faltan 11")
        self.assertEqual((st["today"], st["missing"], st["remaining"], st["allowed"]), (3, 11, 2, 20))
        self.assertEqual(json.loads(json.dumps(st)), st)                  # se puede mandar por /api/status


class LoQueNoExiste(Base):
    def test_no_se_busca_otra_vez_hasta_dentro_de_unos_dias(self):
        vieja = self.lib.add("P/Vieja (1990)/Vieja (1990).mkv")
        estreno = self.lib.add("P/Estreno (2026)/Estreno (2026).mkv")
        a = self.auto()
        a.run_once()
        self.assertEqual(len(self.os.searches), 4)
        self.assertIn("4 todavía no existen", self.logs[-1])
        a.run_once()
        self.assertEqual(len(self.os.searches), 4)                        # el mismo día: nada
        self.now[0] += 2 * DAY + 60
        a.run_once()
        self.assertEqual({s[0] for s in self.os.searches[4:]}, {estreno})  # el estreno, a los dos días
        self.now[0] = T0 + 7 * DAY + 60
        a.run_once()
        self.assertIn(vieja, {s[0] for s in self.os.searches[6:]})         # lo demás, a la semana
        # Cada vez que no aparece, se espera el doble (2, 4, 8 días…).
        note = a.state["videos"][self.lib.items[estreno]["path"]]["spa"]
        self.assertEqual(note["missing"], 3)
        self.assertAlmostEqual(note["retry_at"] - self.now[0], 8 * DAY, delta=1)

    def test_un_error_de_ese_video_se_reintenta_mas_tarde(self):
        pel = self.lib.add("P/Pel.mkv")
        self.offer(pel, "spa", res(1, "ea"))
        a = self.auto()
        a.run_once()
        self.os.catalog = {}
        self.os.errors = [SubtitleError("OpenSubtitles respondió 400: algo", code=400)]
        self.lib.items[pel]["subs"] = []   # (como si se hubiera borrado el bajado: no se vuelve a bajar)
        self.now[0] += 60
        a.run_once()
        self.assertEqual(len(self.os.downloads), 1)
        notes = a.state["videos"][self.lib.items[pel]["path"]]
        self.assertEqual(notes["spa"]["status"], "bajado")
        self.assertEqual(notes["eng"]["status"], "no existe")


class Archivos(Base):
    def test_nombres_y_el_video_no_se_toca(self):
        pel = self.lib.add("P/Japonesa (2001)/Japonesa (2001).mkv", audio_langs=("jpn",))
        cor = self.lib.add("P/Coreana (2003)/Coreana (2003).mkv", audio_langs=("kor",))
        chi = self.lib.add("P/China (1994)/China (1994).mkv", audio_langs=("chi",))
        for item_id in (pel, cor, chi):
            self.offer(item_id, "spa", res(item_id + "1", "es", downloads=900), res(item_id + "2", "ea", downloads=5))
            self.offer(item_id, "eng", res(item_id + "3", "en"))
        self.offer(pel, "jpn", res(31, "ja"))
        self.offer(cor, "kor", res(32, "ko"))
        self.offer(chi, "chi", res(33, "zh-tw"))
        video = Path(self.lib.items[pel]["path"])
        before = (hashlib.sha1(video.read_bytes()).hexdigest(), video.stat().st_mtime)
        mine = video.with_name("Japonesa (2001).en.srt")      # uno que ya estaba: no se toca
        a = self.auto()
        a.run_once()
        names = sorted(f.name for f in video.parent.iterdir())
        self.assertEqual(names, ["Japonesa (2001).en.opensubtitles.srt", "Japonesa (2001).es.opensubtitles-latino.srt",
                                 "Japonesa (2001).ja.opensubtitles.srt", "Japonesa (2001).mkv"])
        self.assertIn("Coreana (2003).kor.opensubtitles.srt", os.listdir(video.parent.parent / "Coreana (2003)"))
        self.assertIn("China (1994).chi.opensubtitles.srt", os.listdir(video.parent.parent / "China (1994)"))
        self.assertEqual((hashlib.sha1(video.read_bytes()).hexdigest(), video.stat().st_mtime), before)
        saved = video.with_name("Japonesa (2001).es.opensubtitles-latino.srt").read_bytes()
        self.assertNotIn(b"\r", saved)                                     # saltos de línea \n
        # La biblioteca los reconoce: ya no falta nada y la tanda siguiente no busca.
        self.assertEqual(present_langs(self.lib.items[pel]), {"spa", "eng", "jpn"})
        self.assertGreater(self.lib.scans, 0)
        searches = len(self.os.searches)
        self.now[0] += 60
        a.run_once()
        self.assertEqual(len(self.os.searches), searches)
        # Nunca reemplaza un archivo: si el nombre está ocupado, agrega -2.
        mine.write_bytes(b"mio")
        again = save_next_to_video(self.lib.items[pel], SRT, "en")
        self.assertEqual(again.name, "Japonesa (2001).en.opensubtitles-2.srt")
        self.assertEqual(mine.read_bytes(), b"mio")

    def test_lo_bajado_se_alinea_con_la_voz(self):
        avisos = []
        pel = self.lib.add("P/Pel.mkv")
        self.offer(pel, "spa", res(1, "ea"))
        a = self.auto(aligner=type("A", (), {"notify": lambda s: avisos.append(1)})())
        a.run_once()
        self.assertEqual(avisos, [1])

    def test_lo_que_no_es_subtitulo_no_se_guarda(self):
        pel = self.lib.add("P/Pel.mkv")
        self.offer(pel, "spa", res(1, "ea", downloads=99), res(2, "es"))
        malo = OSFalso.download

        def download(s, file_id):
            data, rem = malo(s, file_id)
            return (b"<html>no</html>" if file_id == 1 else data), rem
        self.os.download = download.__get__(self.os)
        a = self.auto()
        a.run_once()
        note = a.state["videos"][self.lib.items[pel]["path"]]["spa"]
        self.assertEqual((note["status"], note["bad"]), ("falló", ["1"]))
        self.now[0] = note["retry_at"] + 1
        a.run_once()                                                       # la vez siguiente, otro
        self.assertEqual(self.os.downloads, [1, 2])
        self.assertEqual(a.state["videos"][self.lib.items[pel]["path"]]["spa"]["status"], "bajado")


class Eleccion(Base):
    def test_huella_latino_copia_y_descargas(self):
        it = {"kind": "movie", "path": "/p/x.mkv"}
        found = pick(it, "spa", [res(1, "es", downloads=9000), res(2, "ea", downloads=10), res(3, "sp", match=True),
                                 res(4, "ea", downloads=99999, foreign=True), res(5, "en", downloads=5),
                                 res(6, "ea", downloads=50000, ai=True)])
        self.assertEqual([r["file_id"] for r in found], [3, 2, 1, 6])     # huella, latino, genérico; IA al final
        names = ["Peli (2019) {imdb-tt0000001}.mkv", "Peli.2019.1080p.AMZN.WEB-DL.DDP5.1.H.264-NTG.mkv"]
        found = pick(it, "eng", [res(7, "en", "Peli.2019.1080p.BluRay.x264-SPARKS", downloads=800),
                                 res(8, "en", "Peli.2019.1080p.AMZN.WEB-DL.DDP5.1.H.264-NTG.en", downloads=3),
                                 res(9, "en", "Peli.2019.720p.WEBRip.x264-GalaxyRG", downloads=50)], names)
        self.assertEqual([r["file_id"] for r in found], [8, 9, 7])        # misma copia, mismo origen, otra
        self.assertGreater(release_score(names, "Peli.2019.1080p.WEB-DL-NTG"), release_score(names, "Peli.BluRay"))

    def test_capitulo_correcto(self):
        it = {"kind": "episode", "path": "/s/Serie - S02E05.mkv", "show": "The Office", "season": 2, "ep": "E5"}
        results = [res(1, "en", season=2, episode=6, downloads=900), res(2, "en", season=1, episode=5),
                   res(3, "en", season=2, episode=5, show="The Office (US)"), res(4, "en"),
                   res(5, "en", season=2, episode=5, show="Office Space", downloads=5000)]
        self.assertEqual([r["file_id"] for r in pick(it, "eng", results)], [5, 3, 4])
        # Buscado por el nombre de la serie: que la serie coincida.
        self.assertEqual([r["file_id"] for r in pick(it, "eng", results, by_name=True)], [3, 4])
        # Videos sueltos en una carpeta (sin S02E05 en el nombre): solo el hecho para esa copia.
        suelto = {"kind": "episode", "path": "/s/Saga/Parte uno.mkv", "show": "Saga", "season": 1, "ep": "E1"}
        self.assertEqual([r["file_id"] for r in pick(suelto, "eng", [res(6, "en"), res(7, "en", match=True)])], [7])

    def test_el_nombre_con_que_se_bajo(self):
        pel = self.lib.add("Películas/Peli (2019) {imdb-tt0000001}/Peli (2019) {imdb-tt0000001}.mkv")
        org = type("O", (), {"state": {"done": {
            "/descargas/Peli.2019.1080p.AMZN.WEB-DL.DDP5.1.H.264-NTG.mkv": self.lib.items[pel]["path"]}}})()
        self.offer(pel, "spa", res(1, "ea", "Peli.2019.1080p.BluRay.x264-SPARKS", downloads=800),
                   res(2, "ea", "Peli.2019.1080p.AMZN.WEB-DL.DDP5.1.H.264-NTG", downloads=3))
        self.auto(organizer=org).run_once()
        self.assertEqual(self.os.downloads[0], 2)

    def test_series_por_codigo_de_imdb(self):
        e1 = self.lib.add("Series/Serie (2020) {tvdb-123}/Season 01/Serie (2020) - S01E01.mkv", kind="episode",
                          show="Serie", season=1, ep="E1", embedded=[emb("eng")])
        e2 = self.lib.add("Series/Serie (2020) {tvdb-123}/Season 01/Serie (2020) - S01E02.mkv", kind="episode",
                          show="Serie", season=1, ep="E2", embedded=[emb("eng")])
        otra = self.lib.add("Series/Otra (2020) {tvdb-456}/Season 01/Otra (2020) - S01E01.mkv", kind="episode",
                            show="Otra", season=1, ep="E1", embedded=[emb("eng")])
        preguntas = []

        def wikidata(codes):
            preguntas.append(list(codes))
            return {"123": "tt7654321"}
        a = self.auto(series_imdb=wikidata)
        a.run_once()
        a.run_once()
        self.assertEqual(preguntas, [["123", "456"]])                      # una sola consulta, y se recuerda
        by_id = {s[0]: s[2] for s in self.os.searches}
        self.assertEqual((by_id[e1], by_id[e2], by_id[otra]), ("7654321", "7654321", None))   # sin código: por nombre

    def test_sin_wikidata_se_busca_por_nombre(self):
        e1 = self.lib.add("Series/Serie {tvdb-1}/Season 01/Serie - S01E01.mkv", kind="episode", show="Serie",
                          season=1, ep="E1")

        def falla(codes):
            raise OSError("sin internet")
        self.auto(series_imdb=falla).run_once()
        self.assertEqual({s[2] for s in self.os.searches if s[0] == e1}, {None})


class EncendidoYApagado(Base):
    def test_sin_clave_lo_dice_una_vez_y_no_hace_nada(self):
        self.os.configured = False
        self.lib.add("P/Pel.mkv")
        a = self.auto()
        a.watch()                                                          # vuelve enseguida
        self.assertEqual(len(self.logs), 1)
        self.assertIn('"api_key"', self.logs[0])
        self.assertEqual(self.sleeps, [])
        self.assertIsNone(a.status())
        a.run_once()
        self.assertEqual(self.os.searches, [])

    def test_apagado_en_config(self):
        self.lib.add("P/Pel.mkv")
        a = self.auto({"opensubtitles": {"api_key": "x", "automaticos": False}})
        self.assertIsNone(a.status())
        self.assertEqual(a.run_once(), subs_auto.CHECK_EVERY)
        a.watch()
        self.assertEqual(self.os.searches, [])
        self.assertIn('"automaticos": false', self.logs[0])

    def test_estado_de_la_app(self):
        import cine
        app = cine.App.__new__(cine.App)
        app.roku, app.server_url, app.iphone_url = None, "", None
        app.library = self.lib
        app.queue = type("Q", (), {"items": lambda s: []})()
        app.dubbing = type("D", (), {"current": None})()
        app.playing = lambda: None
        self.assertIsNone(app.status()["auto_subs"])                       # una app sin esto: no falla
        app.auto_subs = self.auto()
        self.assertEqual(app.status()["auto_subs"]["text"], "")


# ---------- el cliente de verdad contra un OpenSubtitles falso en esta computadora ----------

class API(BaseHTTPRequestHandler):
    state = {}

    def log_message(self, *a):
        pass

    def _json(self, code, data, headers=None):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        st = API.state
        st["calls"].append(("GET", self.path))
        if self.path.startswith("/api/v1/subtitles"):
            if st["throttle"] > 0:
                st["throttle"] -= 1
                return self._json(429, {"message": "Throttle limit reached. Retry later."}, {"Retry-After": "0"})
            return self._json(200, {"data": [{"attributes": {
                "language": "ea", "download_count": 3, "release": "Peli.2019.WEB", "moviehash_match": True,
                "foreign_parts_only": False, "files": [{"file_id": 77, "file_name": "x"}]}}]})
        if self.path.startswith("/api/v1/infos/user"):
            return self._json(200, {"data": {"allowed_downloads": 20, "remaining_downloads": st["remaining"]}})
        if self.path == "/archivo.srt":
            self.send_response(200)
            self.send_header("Content-Length", str(len(SRT)))
            self.end_headers()
            return self.wfile.write(SRT)
        self._json(404, {})

    def do_POST(self):
        st = API.state
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        st["calls"].append(("POST", self.path))
        if self.path == "/api/v1/login":
            return self._json(200, {"token": "t", "user": {"allowed_downloads": 20}})
        if self.path == "/api/v1/download":
            if st.get("bad_id"):
                return self._json(406, {"message": "Invalid file_id"})
            if st["remaining"] <= 0:
                return self._json(406, {"requests": 21, "remaining": -1, "reset_time": "03 hours and 02 minutes",
                                        "reset_time_utc": "2026-10-08T07:00:00.000Z",
                                        "message": "You have downloaded your allowed 20 subtitles for 24h."})
            st["remaining"] -= 1
            return self._json(200, {"link": f"http://127.0.0.1:{st['port']}/archivo.srt", "remaining": st["remaining"],
                                    "reset_time": "07 hours", "reset_time_utc": "2026-10-08T07:00:00Z"})
        self._json(404, {})


class Cliente(unittest.TestCase):
    def setUp(self):
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), API)
        port = self.httpd.server_address[1]
        API.state = {"calls": [], "throttle": 0, "remaining": 1, "port": port}
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.c = OpenSubtitles({"opensubtitles": {"api_key": "k", "usuario": "u", "clave": "c"}})
        self.c.base = f"http://127.0.0.1:{port}/api/v1"
        self._t = tempfile.TemporaryDirectory()
        video = Path(self._t.name) / "Peli (2019) {imdb-tt0000001}.mkv"
        video.write_bytes(b"\0" * 300000)
        self.item = {"kind": "movie", "path": str(video), "title": "Peli (2019)"}

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self._t.cleanup()

    def test_429_espera_y_reintenta(self):
        API.state["throttle"] = 2
        found = self.c.search(self.item, "spa")
        self.assertEqual([r["file_id"] for r in found], [77])
        self.assertEqual(sum(1 for m, p in API.state["calls"] if p.startswith("/api/v1/subtitles")), 3)
        API.state["throttle"] = 5
        with self.assertRaises(SubtitleError) as e:
            self.c.search(self.item, "spa")
        self.assertEqual((e.exception.code, e.exception.wait), (429, 0.0))
        self.assertIn("moviehash=", next(p for m, p in API.state["calls"] if "subtitles" in p))   # la huella
        self.assertIn("imdb_id=1", next(p for m, p in API.state["calls"] if "subtitles" in p))

    def test_cupo_desde_la_api(self):
        self.assertEqual(self.c.user_info()["remaining_downloads"], 1)
        self.assertEqual((self.c.quota["allowed"], self.c.quota["remaining"]), (20, 1))
        data, remaining = self.c.download(77)
        self.assertEqual((data, remaining), (SRT, 0))
        reset = datetime(2026, 10, 8, 7, 0, tzinfo=timezone.utc).timestamp()
        self.assertEqual((self.c.quota["remaining"], self.c.quota["reset_at"]), (0, reset))
        with self.assertRaises(SubtitleError) as e:
            self.c.download(77)
        self.assertTrue(e.exception.quota)
        self.assertEqual((e.exception.code, e.exception.reset_at), (406, reset))
        self.assertIn("Se acabaron las descargas", str(e.exception))

    def test_otro_406_no_es_el_cupo(self):
        API.state["bad_id"] = True
        with self.assertRaises(SubtitleError) as e:
            self.c.download(1)
        self.assertFalse(e.exception.quota)
        self.assertIsNone(self.c.quota["remaining"])

    def test_idiomas_y_renovacion(self):
        self.assertEqual(subtitles_online.os_languages("spa"), "ea,es,sp")
        self.assertEqual(subtitles_online.os_languages("jpn"), "ja")
        self.assertEqual(subtitles_online.os_languages("ko"), "ko")
        self.assertEqual(subtitles_online.os_languages("zho"), "zh-cn,zh-tw,ze")
        self.assertEqual(subtitles_online.os_languages("xyz"), "")
        self.assertEqual(parse_reset({"reset_time": "07 hours and 30 minutes"}, now=1000), 1000 + 7.5 * 3600)
        self.assertIsNone(parse_reset({"message": "nada"}))


class ConLaBibliotecaDeVerdad(unittest.TestCase):
    """Un video de verdad (ffmpeg) en mac/library.py: lo bajado aparece con el idioma y el nombre correctos."""

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "hace falta ffmpeg")
    def test_la_biblioteca_reconoce_lo_bajado(self):
        from library import Library
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "Películas" / "Japonesa (2001) {imdb-tt0000009}"
            folder.mkdir(parents=True)
            video = folder / "Japonesa (2001) {imdb-tt0000009}.mkv"
            r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                                "color=c=black:s=32x32:r=2:d=160", "-f", "lavfi", "-i", "anullsrc=r=8000:cl=mono",
                                "-t", "160", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
                                "-metadata:s:a:0", "language=jpn", str(video)], capture_output=True,
                               stdin=subprocess.DEVNULL)
            self.assertEqual(r.returncode, 0, r.stderr)
            lib = Library([tmp], Path(tmp) / "cache")
            lib.scan(force=True)
            (item_id, it), = lib.items.items()
            client = OSFalso({(it["path"], "spa"): [res(1, "ea")], (it["path"], "eng"): [res(2, "en")],
                              (it["path"], "jpn"): [res(3, "ja")]})
            before = hashlib.sha1(video.read_bytes()).hexdigest()
            a = AutoSubtitles(client, lib, Path(tmp) / "datos.json", {"opensubtitles": {"api_key": "x"}},
                              log=lambda m: None, sleep=lambda s: None, series_imdb=lambda c: {})
            a.run_once()
            self.assertEqual(client.downloads, [1, 2, 3])
            names = sorted((s["lang"], s["label"]) for s in lib.get(item_id)["subs"])
            self.assertEqual(names, [("eng", "Inglés · internet"), ("ja", "Japonés · internet"),
                                     ("spa", "Español (Latino) · internet")])
            self.assertEqual(hashlib.sha1(video.read_bytes()).hexdigest(), before)
            self.assertEqual(a.plan()[0], [])                              # ya no falta nada


if __name__ == "__main__":
    unittest.main()
