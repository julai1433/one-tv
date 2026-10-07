# Subtítulos que se alinean solos con la voz (mac/subsync.py y mac/subsync_voz.py), sin red ni TV.
# Uso: python3 -m unittest discover -s pruebas -p 'test_subtitulos_alineados.py'
# La parte que compara audio necesita un Python con numpy: CINE_PYTHON_NUMPY=/ruta/al/python (por ejemplo, un
# entorno aparte con numpy) o el mismo python3 si lo tiene. Si no, esas pruebas se saltan.
# El audio es sintético: «voz» = ráfagas de ruido que suben y bajan como sílabas, con pausas, música de
# fondo (tonos parejos) en algunos tramos y un ruido de fondo bajo.
import array
import hashlib
import json
import math
import os
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path

MAC = Path(__file__).resolve().parent.parent / "mac"
sys.path.insert(0, str(MAC))
import subsync
from server import Media
from subsync import SubtitleAligner, apply, describe, parse, read, to_srt

SR = 16000
TOLERANCE = 0.1   # s


def numpy_python():
    for cand in (os.environ.get("CINE_PYTHON_NUMPY"), sys.executable):
        if cand and Path(cand).exists() and subprocess.run(
                [cand, "-c", "import numpy"], capture_output=True, stdin=subprocess.DEVNULL).returncode == 0:
            return cand
    return None


def utterances(seed, duration):
    """Lo que se «dice»: [(inicio, fin)], con pausas y, cada tanto, un rato de música sin voz."""
    rng = random.Random(seed)
    out, t = [], 3.0
    while t < duration - 5:
        if rng.random() < 0.06:
            t += rng.uniform(6, 12)   # música, sin diálogo
            continue
        d = rng.uniform(0.6, 3.5)
        out.append((round(t, 3), round(t + d, 3)))
        t += d + rng.uniform(0.3, 4.0)
    return out


def synth_audio(path, utts, duration, seed=7):
    """Un .wav de 16 kHz: voz donde dicen las frases; fondo bajo; música en los ratos largos sin voz."""
    rng = random.Random(seed)
    n = int(duration * SR)
    # Trozos que se repiten (generarlos muestra por muestra en Python puro sería lento).
    noise = [rng.gauss(0, 1) for _ in range(SR * 4)]
    voice, lp, hp, prev = [], 0.0, 0.0, 0.0
    env_t, syl = 0, []
    while len(syl) < SR * 6:   # sílabas de 120-280 ms con su subida y bajada
        length = int(SR * rng.uniform(0.12, 0.28))
        syl += [math.sin(math.pi * k / length) ** 1.5 for k in range(length)]
    for k in range(SR * 6):   # ruido filtrado entre ~300 y ~3000 Hz
        x = rng.gauss(0, 1)
        lp += 0.55 * (x - lp)
        hp = 0.89 * (hp + lp - prev)
        prev = lp
        voice.append(hp * syl[k] * 9000)
    music = [3000 * (math.sin(2 * math.pi * 220 * k / SR) + 0.6 * math.sin(2 * math.pi * 277 * k / SR)
                     + 0.4 * math.sin(2 * math.pi * 330 * k / SR)) for k in range(SR * 3)]
    pcm = array.array("h", bytes(2 * n))
    floor = [int(150 * x) for x in noise]
    for start in range(0, n, len(floor)):   # fondo
        chunk = floor[:min(len(floor), n - start)]
        pcm[start:start + len(chunk)] = array.array("h", chunk)
    edges = [0.0] + [x for u in utts for x in u] + [duration]
    for a, b in zip(edges[0::2], edges[1::2]):   # música en las pausas largas
        if b - a > 5:
            i, j = int((a + 0.5) * SR), int((b - 0.5) * SR)
            for start in range(i, j, len(music)):
                m = min(len(music), j - start)
                pcm[start:start + m] = array.array("h", (int(music[k] + floor[k]) for k in range(m)))
    for a, b in utts:
        i, j = int(a * SR), min(int(b * SR), n)
        off = rng.randrange(0, len(voice) - (j - i)) if j - i < len(voice) else 0
        pcm[i:j] = array.array("h", (max(-32000, min(32000, int(voice[off + k] + floor[k % len(floor)])))
                                     for k in range(j - i)))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def cues_from(utts, to_sub, extra=()):
    """Subtítulo con las frases llevadas al tiempo del subtítulo; «true» es donde de verdad se oye cada una."""
    cues = []
    for n, (a, b) in enumerate(utts):
        start = to_sub(a)
        if start is None:
            continue
        speed = (to_sub(a + 0.01) - start) / 0.01 if to_sub(a + 0.01) is not None else 1.0
        cues.append({"start": start, "end": start + (b - a) * speed + 0.2, "text": f"frase {n}", "true": a})
    cues += [{"start": a, "end": b, "text": "escena que el video no tiene", "true": None} for a, b in extra]
    return sorted(cues, key=lambda c: c["start"])


def write_srt(path, cues):
    Path(path).write_text(to_srt(cues), encoding="utf-8")


def mapped(cues, result):
    """Cada línea corregida junto a dónde debería estar."""
    fix = {"speed": result.get("speed", 1.0), "segments": result.get("segments") or [[0.0, 0.0]],
           "quitar": result.get("quitar") or []}
    out = []
    for c in cues:
        r = apply([c], fix)
        out.append((r[0]["start"] if r else None, c["true"]))
    return out


# ---------- leer, corregir y escribir (sin numpy) ----------

class LeerYCorregir(unittest.TestCase):
    def test_lee_srt_con_bom_y_saltos_de_windows(self):
        raw = ("\ufeff1\r\n00:00:01,500 --> 00:00:03,000\r\n<i>Hola</i>\r\ncariño\r\n\r\n"
               "2\r\n01:02:03,040 --> 01:02:04,000\r\nAdiós\r\n")
        cues = parse(subsync.decode(raw.encode("utf-8")))
        self.assertEqual(len(cues), 2)
        self.assertEqual((cues[0]["start"], cues[0]["end"], cues[0]["text"]), (1.5, 3.0, "<i>Hola</i>\ncariño"))
        self.assertAlmostEqual(cues[1]["start"], 3723.04)

    def test_lee_vtt(self):
        raw = ("WEBVTT\n\nNOTE algo\n\nuno\n00:01.250 --> 00:02.000 line:90%\nHola\n\n"
               "01:00:00.000 --> 01:00:01.500\nChau\n")
        cues = parse(raw)
        self.assertEqual([(c["start"], c["end"], c["text"]) for c in cues],
                         [(1.25, 2.0, "Hola"), (3600.0, 3601.5, "Chau")])

    def test_ida_y_vuelta(self):
        cues = [{"start": 0.0, "end": 1.0, "text": "a"}, {"start": 3661.007, "end": 3662.5, "text": "b\nc"}]
        text = to_srt(cues)
        self.assertIn("01:01:01,007 --> 01:01:02,500\nb\nc", text)
        self.assertEqual(parse(text), cues)

    def test_corrige_desfase_velocidad_tramos_y_quita_lo_que_sobra(self):
        cues = [{"start": t, "end": t + 1, "text": str(t)} for t in (1.0, 10.0, 20.0, 30.0, 40.0)]
        out = apply(cues, {"speed": 1.0, "segments": [[0.0, 2.0]]})
        self.assertEqual([c["start"] for c in out], [3.0, 12.0, 22.0, 32.0, 42.0])
        out = apply(cues, {"speed": 2.0, "segments": [[0.0, -1.0]]})
        self.assertEqual([(c["start"], c["end"]) for c in out][:2], [(1.0, 3.0), (19.0, 21.0)])
        out = apply(cues, {"speed": 1.0, "segments": [[0.0, 0.5], [30.0, -5.0]], "quitar": [[20.0, 20.001]]})
        self.assertEqual([c["text"] for c in out], ["1.0", "10.0", "30.0", "40.0"])
        self.assertEqual([c["start"] for c in out], [1.5, 10.5, 25.0, 35.0])
        out = apply(cues, {"speed": 1.0, "segments": [[0.0, -10.5]]})   # lo que queda antes del inicio
        self.assertEqual([c["start"] for c in out], [0.0, 9.5, 19.5, 29.5])

    def test_la_correccion_en_palabras(self):
        self.assertEqual(describe({"speed": 1.0, "segments": [[0.0, 2.34]]}), "se atrasan 2,3 s")
        self.assertEqual(describe({"speed": 25 / 23.976, "segments": [[0.0, -1.2]]}),
                         "se adelantan 1,2 s; velocidad de 25 a 23,976 cuadros por segundo")
        self.assertEqual(describe({"speed": 1.0, "segments": [[0.0, 0.8], [300.0, -24.2]], "dropped": 9}),
                         "1 salto a medio video (de 0,8 s a -24,2 s de desfase); "
                         "sin 9 líneas de una escena que este video no tiene")


# ---------- el trabajo en segundo plano (con un análisis de mentira) ----------

class Biblioteca:
    def __init__(self, items):
        self.items = items


class Doblaje:
    current = None

    def python(self):
        return sys.executable


class EnSegundoPlano(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.tmp = Path(self._t.name)
        self.video = self.tmp / "Peli (2020).mkv"
        self.video.write_bytes(b"video")
        self.sub = self.tmp / "Peli (2020).es.opensubtitles-latino.srt"
        self.original = "1\n00:00:10,000 --> 00:00:12,000\nHola\n\n2\n00:00:20,000 --> 00:00:21,000\nChau\n"
        self.sub.write_text(self.original, encoding="utf-8")
        self.item = {"id": "abc", "path": str(self.video), "title": "Peli", "full_title": "Peli (2020)",
                     "info": {"audio": [{"index": 1, "lang": "spa", "channels": 6, "default": True},
                                        {"index": 2, "lang": "eng", "channels": 6, "default": False}]},
                     "subs": [{"key": "x0", "lang": "spa", "label": "Español (Latino) · internet",
                               "file": str(self.sub)},
                              {"key": "e3", "lang": "eng", "label": "Inglés", "stream": 3}]}
        self.library = Biblioteca({"abc": self.item})
        self.logs, self.calls = [], []
        self.aligner = SubtitleAligner(Doblaje(), MAC / "subsync_voz.py", self.tmp / "datos" / "subs.json",
                                       self.tmp / "cache" / "subs-alineados", log=self.logs.append)
        self.answer = {"ok": True, "action": "corregir", "confidence": 15.2, "speed": 1.0,
                       "segments": [[0.0, 2.5]], "quitar": [], "dropped": 0}

        def fake_run(python, script, video, index, channels, subs, cache=None):
            self.calls.append((video, index, channels, list(subs)))
            return {"ok": True, "subs": [dict(self.answer) for _ in subs]}
        self._real = subsync.run_subsync
        subsync.run_subsync = fake_run

    def tearDown(self):
        subsync.run_subsync = self._real
        self._t.cleanup()

    def run_all(self):
        while self.aligner.consider(self.library) and self.aligner._run_next():
            pass

    def test_alinea_guarda_aparte_y_no_toca_el_original(self):
        before = (self.sub.read_bytes(), self.sub.stat().st_mtime)
        self.run_all()
        # Solo el subtítulo aparte (el que viene dentro del video no se toca), con la pista original (inglés).
        self.assertEqual(self.calls, [(str(self.video), 2, 6, [str(self.sub)])])
        self.assertEqual((self.sub.read_bytes(), self.sub.stat().st_mtime), before)
        fixed = self.aligner.aligned(str(self.video), str(self.sub))
        self.assertIsNotNone(fixed)
        self.assertTrue(str(fixed).startswith(str(self.tmp / "cache")))
        self.assertEqual([c["start"] for c in read(fixed)], [12.5, 22.5])
        self.assertEqual([p.name for p in self.tmp.iterdir() if p.suffix == ".srt"], [self.sub.name])
        state = json.loads((self.tmp / "datos" / "subs.json").read_text())
        entry = state["subs"][str(self.sub)][str(self.video)]
        self.assertEqual((entry["status"], entry["confidence"], entry["what"]), ("alineado", 15.2, "se atrasan 2,5 s"))
        self.assertEqual(len(self.logs), 1)
        self.assertIn("✓ Subtítulos alineados con la voz: «Peli (2020)» · Español (Latino) · internet: "
                      "se atrasan 2,5 s (confianza 15,2)", self.logs[0])

    def test_no_repite_si_nada_cambio_y_si_cambia_vuelve_a_revisar(self):
        self.run_all()
        self.assertEqual(self.aligner.consider(self.library), 0)
        self.assertEqual(len(self.calls), 1)
        self.sub.write_text(self.original + "\n3\n00:00:30,000 --> 00:00:31,000\nOtra\n", encoding="utf-8")
        os.utime(self.sub, (1, 1))   # otro tamaño y otra fecha
        self.assertIsNone(self.aligner.aligned(str(self.video), str(self.sub)))   # mientras, el original
        self.run_all()
        self.assertEqual(len(self.calls), 2)
        self.assertEqual([c["start"] for c in read(self.aligner.aligned(str(self.video), str(self.sub)))],
                         [12.5, 22.5, 32.5])

    def test_si_se_borra_la_cache_se_reescribe(self):
        self.run_all()
        shutil.rmtree(self.tmp / "cache")
        fixed = self.aligner.aligned(str(self.video), str(self.sub))
        self.assertEqual([c["start"] for c in read(fixed)], [12.5, 22.5])

    def test_sin_coincidencia_clara_deja_el_original(self):
        self.answer = {"ok": True, "action": "dudoso", "why": "no coinciden claramente con la voz", "confidence": 3.1}
        self.run_all()
        self.assertIsNone(self.aligner.aligned(str(self.video), str(self.sub)))
        self.assertEqual(self.aligner.consider(self.library), 0)   # anotado: no se repite
        self.assertIn("no coinciden claramente con la voz; se dejan como están (confianza 3,1)", self.logs[0])

    def test_ya_a_tiempo_no_genera_otro(self):
        self.answer = {"ok": True, "action": "a tiempo", "confidence": 18.0, "speed": 1.0, "segments": [[0.0, 0.08]]}
        self.run_all()
        self.assertIsNone(self.aligner.aligned(str(self.video), str(self.sub)))
        self.assertIn("ya estaban a tiempo", self.logs[0])

    def test_si_falla_se_reintenta_mas_tarde(self):
        def broken(*a, **k):
            raise RuntimeError("ffmpeg no pudo leer el audio")
        subsync.run_subsync = broken
        self.run_all()
        self.assertIn("se reintenta en 1 h", self.logs[0])
        self.assertEqual(self.aligner.consider(self.library), 0)   # todavía no
        entry = self.aligner._entry(str(self.sub), str(self.video))
        entry["next_at"] = 0
        self.assertEqual(self.aligner.consider(self.library), 1)

    def test_sin_numpy_un_solo_aviso_y_se_reintenta_mas_tarde(self):
        class SinInternet:
            current = None

            def python(self):
                raise RuntimeError("no se pudo instalar numpy")
        self.aligner.dubbing = SinInternet()
        self.library.items["def"] = {**self.item, "id": "def", "path": str(self.video) + ".otro"}
        Path(self.library.items["def"]["path"]).write_bytes(b"video")
        self.run_all()
        self.assertEqual(self.logs,
                         ["⚠ Subtítulos alineados con la voz: no se pudo instalar numpy (se reintenta en 1 h)"])
        self.assertIsNone(self.aligner._entry(str(self.sub), str(self.video)))   # no cuenta como intento fallido
        self.aligner.dubbing, self.aligner.env_retry_at = Doblaje(), 0
        self.run_all()
        self.assertEqual(len(self.calls), 2)

    def test_la_tele_y_la_web_reciben_el_alineado(self):
        media = Media(self.tmp / "cache-media")
        self.assertIn(b"00:00:10,000", media.subtitle(self.item, "x0"))   # antes de alinear: el original
        media.aligned = self.aligner.aligned
        self.run_all()
        data = media.subtitle(self.item, "x0").decode()
        self.assertIn("00:00:12,500 --> 00:00:14,500\nHola", data)

    def test_lo_nuevo_primero(self):
        other_video = self.tmp / "Otra (2021).mkv"
        other_video.write_bytes(b"video")
        other_sub = self.tmp / "Otra (2021).en.srt"
        other_sub.write_text(self.original, encoding="utf-8")
        os.utime(self.sub, (1000, 1000))
        self.library.items["def"] = {**self.item, "id": "def", "path": str(other_video), "full_title": "Otra",
                                     "subs": [{"key": "x0", "lang": "eng", "label": "Inglés", "file": str(other_sub)}]}
        self.assertEqual(self.aligner.consider(self.library), 2)
        self.assertEqual(self.aligner.queue[0]["video"], str(other_video))


# ---------- con audio de verdad (sintético) y numpy ----------

PYTHON = numpy_python()


@unittest.skipUnless(PYTHON, "hace falta un Python con numpy (CINE_PYTHON_NUMPY)")
class ConLaVoz(unittest.TestCase):
    DURATION = 600.0

    @classmethod
    def setUpClass(cls):
        cls._t = tempfile.TemporaryDirectory()
        cls.tmp = Path(cls._t.name)
        cls.utts = utterances(1, cls.DURATION)
        cls.video = cls.tmp / "Peli sintética.wav"
        synth_audio(cls.video, cls.utts, cls.DURATION)
        speed = 25 / 23.976
        cut = 300.0
        cls.cases = {
            "a tiempo": cues_from(cls.utts, lambda v: v),
            "fijo": cues_from(cls.utts, lambda v: v + 3.4),
            # Hecho para la versión de 25 cuadros por segundo (4 % más rápida) y, además, corrido 1,2 s.
            "velocidad": cues_from(cls.utts, lambda v: v / speed + 1.2),
            # Al subtítulo le sobra una escena de 25 s a la mitad (con sus propias líneas).
            "sobra escena": cues_from(cls.utts, lambda v: v + 0.8 if v < cut else v + 25.8,
                                      extra=[(cut + 1.3 + 3 * k, cut + 3.0 + 3 * k) for k in range(8)]),
            # Al video le sobra una escena de 20 s a la mitad (el subtítulo no tiene sus líneas).
            "falta escena": cues_from(cls.utts, lambda v: v + 0.8 if v < cut else (None if v < cut + 20 else v - 19.2)),
            # De otra película: no debe tocarse.
            "otra película": cues_from(utterances(99, cls.DURATION), lambda v: v),
        }
        for c in cls.cases["otra película"]:
            c["true"] = None
        cls.files = {}
        for name, cues in cls.cases.items():
            path = cls.tmp / f"Peli sintética.{name.replace(' ', '-')}.srt"
            write_srt(path, cues)
            cls.files[name] = path
        cls.hashes = {name: hashlib.sha1(p.read_bytes()).hexdigest() for name, p in cls.files.items()}
        out = subsync.run_subsync(PYTHON, MAC / "subsync_voz.py", cls.video, 0, 1, list(cls.files.values()),
                                  cache=cls.tmp / "voz", timeout=600)
        assert out.get("ok"), out
        cls.results = dict(zip(cls.files, out["subs"]))

    @classmethod
    def tearDownClass(cls):
        cls._t.cleanup()

    def check_mapped(self, name, keep=0.97):
        res = self.results[name]
        self.assertEqual(res["action"], "corregir", res)
        pairs = mapped(self.cases[name], res)
        real = [(got, true) for got, true in pairs if true is not None]
        kept = [(got, true) for got, true in real if got is not None]
        errors = [abs(got - true) for got, true in kept]
        self.assertGreaterEqual(len(kept), keep * len(real), f"{name}: se perdieron líneas")
        self.assertLessEqual(max(errors), TOLERANCE, f"{name}: error máximo {max(errors):.3f} s")
        return res

    def test_desfase_fijo(self):
        res = self.check_mapped("fijo")
        self.assertEqual(len(res["segments"]), 1)
        self.assertAlmostEqual(res["segments"][0][1], -3.4, delta=TOLERANCE)
        self.assertEqual(res["speed"], 1.0)

    def test_otra_velocidad(self):
        res = self.check_mapped("velocidad")
        self.assertAlmostEqual(res["speed"], 25 / 23.976, places=6)

    def test_sobra_una_escena_en_el_subtitulo(self):
        res = self.check_mapped("sobra escena")
        self.assertEqual(len(res["segments"]), 2)
        pairs = mapped(self.cases["sobra escena"], res)
        extra_kept = sum(1 for got, true in pairs if true is None and got is not None)
        self.assertLessEqual(extra_kept, 1, "las líneas de la escena que el video no tiene se quitan")

    def test_falta_una_escena_en_el_subtitulo(self):
        res = self.check_mapped("falta escena", keep=1.0)
        self.assertEqual(len(res["segments"]), 2)
        self.assertEqual(res["dropped"], 0)

    def test_ya_estaba_a_tiempo(self):
        self.assertEqual(self.results["a tiempo"]["action"], "a tiempo", self.results["a tiempo"])

    def test_de_otra_pelicula_no_se_aplica(self):
        res = self.results["otra película"]
        self.assertEqual(res["action"], "dudoso", res)
        self.assertLess(res["confidence"], 6)

    def test_la_confianza_separa(self):
        good = min(self.results[n]["confidence"] for n in ("fijo", "velocidad", "sobra escena", "falta escena"))
        self.assertGreater(good, 2 * self.results["otra película"]["confidence"])

    def test_los_originales_quedan_intactos(self):
        for name, path in self.files.items():
            self.assertEqual(hashlib.sha1(path.read_bytes()).hexdigest(), self.hashes[name], name)

    def test_de_punta_a_punta_con_el_servicio(self):
        """El hilo del servicio con el análisis de verdad: guarda el alineado aparte y el original no cambia."""
        class Doblaje:
            current = None

            def python(self):
                return PYTHON
        item = {"id": "s1", "path": str(self.video), "title": "Peli sintética", "full_title": "Peli sintética",
                "info": {"audio": [{"index": 0, "lang": "und", "channels": 1, "default": True}]},
                "subs": [{"key": "x0", "lang": "spa", "label": "Español", "file": str(self.files["fijo"])}]}
        logs = []
        aligner = SubtitleAligner(Doblaje(), MAC / "subsync_voz.py", self.tmp / "datos.json", self.tmp / "alineados",
                                  log=logs.append)
        while aligner.consider(Biblioteca({"s1": item})) and aligner._run_next():
            pass
        fixed = aligner.aligned(str(self.video), str(self.files["fijo"]))
        self.assertIsNotNone(fixed, logs)
        got = [c["start"] for c in read(fixed)]
        want = [c["true"] for c in self.cases["fijo"]]
        self.assertEqual(len(got), len(want))
        self.assertLessEqual(max(abs(a - b) for a, b in zip(got, want)), TOLERANCE)
        self.assertEqual(hashlib.sha1(self.files["fijo"].read_bytes()).hexdigest(), self.hashes["fijo"])
        self.assertRegex(logs[0], r"^✓ Subtítulos alineados con la voz: «Peli sintética» · Español: "
                                  r"se adelantan 3,4 s")


if __name__ == "__main__":
    unittest.main()
