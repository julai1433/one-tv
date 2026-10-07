# Línea de tiempo de la conversión (mac/transcode.py) cuando el archivo trae un tramo dañado: un video sintético
# (patrón + tono 5.1 en E-AC-3, como las series) con 2 s ilegibles o faltantes, convertido con FullPlan. La salida
# debe durar lo mismo, cada trozo empezar donde se le dice a la TV y no perder ni sobrar sonido (los subtítulos van
# con los tiempos del original). Y al detener ffmpeg a mitad no debe quedar un trozo cortado que pase por completo.
# Usa el chip de video si lo hay; si no, el procesador (libx264). Se salta sola sin ffmpeg. Sin red ni TV.
# python3 -m unittest discover -s pruebas -p "test_linea_de_tiempo.py"
import contextlib, io, shutil, signal, subprocess, sys, tempfile, time, unittest
from pathlib import Path
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mac"))
import hostos
import transcode
from transcode import SEG, CopyPlan, FullPlan, Session

FPS = 24000 / 1001
FRAME = 1 / FPS


def item_de(path, dur, w=320, h=180, codec="mpeg4", channels=6):
    return {"id": "linea", "path": str(path), "full_title": "Prueba", "duration": dur, "mode": "full",
            "info": {"start": 0, "video": {"index": 0, "codec": codec, "pix_fmt": "yuv420p", "width": w, "height": h},
                     "audio": [{"index": 1, "codec": "eac3", "channels": channels}]}}


def valor(cmd, flag):
    return cmd[cmd.index(flag) + 1]


class Comando(unittest.TestCase):
    """Lo que se le pide a ffmpeg para que nada se corra (sin correrlo)."""

    def test_fullplan_rellena_video_y_audio(self):
        cmd = FullPlan(item_de("/pelis/a.mkv", 100)).command(1, 3, Path("/tmp/x"))
        self.assertEqual(valor(cmd, "-fps_mode"), "cfr")   # imagen que falta: se repite la anterior
        af = valor(cmd, "-af")
        self.assertTrue(af.startswith("aresample=async=1:min_hard_comp=0.01,"), af)   # sonido que falta: silencio
        self.assertIn("aformat=channel_layouts=stereo", af)
        # first_pts=0 no: con un trozo dañado que cambia de canales, ffmpeg rearma los filtros y rellenaría con
        # silencio desde el principio (medido: 26 s de más).
        self.assertNotIn("first_pts", af)
        self.assertEqual(valor(cmd, "-output_ts_offset"), "18.000")

    def test_estereo_y_sin_audio(self):
        cmd = FullPlan(item_de("/pelis/a.mkv", 100, channels=2)).command(1, 0, Path("/tmp/x"))
        self.assertEqual(valor(cmd, "-af"), transcode.AUDIO_TIMELINE)
        sin = FullPlan(item_de("/pelis/a.mkv", 100)).command(None, 0, Path("/tmp/x"))
        self.assertIn("-an", sin)
        self.assertNotIn("-af", sin)

    def test_copyplan_rellena_el_audio(self):
        item = item_de("/pelis/a.mkv", 100, codec="h264")
        cmd = CopyPlan(item, [0.0, 6.2, 12.4, 18.6]).command(1, 1, Path("/tmp/x"))
        self.assertEqual(valor(cmd, "-c:v"), "copy")
        self.assertNotIn("-fps_mode", cmd)   # el video se copia tal cual
        self.assertTrue(valor(cmd, "-af").startswith(transcode.AUDIO_TIMELINE + ","))


def _encoder_ok(name):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10",
                        "-t", "1", "-c:v", name, "-f", "null", "-"], capture_output=True, timeout=30)
    return r.returncode == 0


def _encoder():
    """'chip' (VideoToolbox), 'procesador' (libx264) o None si no se puede convertir aquí."""
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        return None
    if transcode.VIDEOTOOLBOX and _encoder_ok("h264_videotoolbox"):
        return "chip"
    if _encoder_ok("libx264"):
        return "procesador"
    return None


ENCODER = _encoder()


def generar(dest, segundos, dano=None):
    """Video de prueba (MPEG-4 + E-AC-3 5.1 en MKV). dano: 'ilegible' (bytes cambiados) o 'faltante' (paquetes
    quitados) entre los segundos 12 y 14, sin tocar los tiempos de lo demás."""
    base = dest.parent / f"limpio-{segundos}.mkv"
    if not base.exists():
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                        "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=24000/1001",
                        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000,aformat=channel_layouts=5.1",
                        "-t", str(segundos), "-c:v", "mpeg4", "-g", "48", "-q:v", "5", "-c:a", "eac3", "-b:a", "384k",
                        str(base)], check=True, capture_output=True, timeout=120)
    if dano is None:
        return base
    tramo = "between(pts*tb\\,12\\,14)"
    bsf = f"noise=amount=if({tramo}\\,40\\,0)" if dano == "ilegible" else f"noise=drop={tramo}"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(base), "-map", "0", "-c", "copy",
                    "-bsf:v", bsf, "-bsf:a", bsf, str(dest)], check=True, capture_output=True, timeout=60)
    return dest


def paquetes(path, sel):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", sel, "-show_entries",
                          "packet=pts_time,duration_time", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, timeout=60).stdout
    rows = []
    for line in out.splitlines():
        t, d = (line.split(",") + ["", ""])[:2]
        if t not in ("", "N/A"):
            rows.append((float(t), float(d) if d not in ("", "N/A") else 0.0))
    return sorted(rows)


def imagen(path):
    """(primer instante, fin) de las imágenes de un trozo."""
    v = paquetes(path, "v:0")
    return v[0][0], v[-1][0] + v[-1][1]


@contextlib.contextmanager
def con_el_codificador():
    """Sin el chip de video, FullPlan usa el procesador (como en Linux)."""
    with mock.patch.object(transcode, "VIDEOTOOLBOX", ENCODER == "chip"):
        yield


@unittest.skipUnless(ENCODER, "hace falta ffmpeg con VideoToolbox o libx264")
class TramoDanado(unittest.TestCase):
    """40 s con 2 s dañados: la salida conserva la duración y cada trozo empieza en su segundo."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls.tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def convertir(self, dano, start=0):
        src = generar(self.dir / f"{dano}.mkv", 40, dano)
        item = item_de(src, 40.0)
        out = self.dir / f"hls-{dano}-{start}"
        out.mkdir()
        with con_el_codificador():
            plan = FullPlan(item)
            cmd = plan.command(1, start, out)
        r = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, timeout=180)
        self.assertEqual(r.returncode, 0, r.stderr[-800:])
        return plan, out

    def revisar(self, plan, out, start=0):
        n = len(plan.starts)
        segs = [out / f"seg{i}.ts" for i in range(start, n)]
        for s in segs:
            self.assertTrue(s.exists(), s.name)
        video = [paquetes(s, "v:0") for s in segs]
        audio = [paquetes(s, "a:0") for s in segs]
        # El contenedor suma un retraso fijo (unos 1,4 s): se toma del primer trozo.
        base = video[0][0][0] - plan.starts[start]
        for k, (v, a) in enumerate(zip(video, audio)):
            i = start + k
            self.assertGreaterEqual(v[0][0] - base - plan.starts[i], -0.005, f"seg{i} empieza antes")
            self.assertLess(v[0][0] - base - plan.starts[i], FRAME + 0.005, f"seg{i} empieza tarde")
            if i < n - 1:
                self.assertIn(len(v), (143, 144), f"seg{i}: {len(v)} imágenes en 6 s")
        todos_v = [p for v in video for p in v]
        huecos_v = [b[0] - a[0] for a, b in zip(todos_v, todos_v[1:])]
        self.assertLess(max(huecos_v), 1.5 * FRAME, "faltan imágenes: la imagen debe congelarse, no saltar")
        fin_v = todos_v[-1][0] + todos_v[-1][1] - base
        self.assertAlmostEqual(fin_v, 40.0, delta=2 * FRAME)
        todos_a = [p for a in audio for p in a]
        huecos_a = [b[0] - (a[0] + a[1]) for a, b in zip(todos_a, todos_a[1:])]
        # Donde ffmpeg rearma los filtros (un pedazo dañado que llega con otros canales) puede faltar un cuadro de
        # sonido (32 ms); más que eso, no.
        self.assertLess(max(huecos_a), 0.05, "falta sonido: debe haber silencio en su lugar")
        self.assertGreater(min(huecos_a), -0.05, "sobra sonido")
        muestras = sum(d for _, d in todos_a)
        tramo = todos_a[-1][0] + todos_a[-1][1] - todos_a[0][0]
        self.assertAlmostEqual(muestras, tramo, delta=0.05)          # el sonido dura lo que marcan sus tiempos
        self.assertAlmostEqual(tramo, 40.0 - plan.starts[start], delta=0.1)

    def test_datos_ilegibles(self):
        plan, out = self.convertir("ilegible")
        self.revisar(plan, out)

    def test_paquetes_faltantes(self):
        plan, out = self.convertir("faltante")
        self.revisar(plan, out)

    def test_salto_despues_del_dano(self):
        # La TV salta al trozo 3 (18 s): ffmpeg arranca ahí y todo sigue en su segundo.
        plan, out = self.convertir("ilegible", start=3)
        self.revisar(plan, out, start=3)


@unittest.skipUnless(ENCODER, "hace falta ffmpeg con VideoToolbox o libx264")
class AlDetener(unittest.TestCase):
    """La TV en pausa mucho rato (o se empieza otra cosa): Session.stop() detiene ffmpeg a mitad de un trozo."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.src = generar(self.dir / "largo.mkv", 120)

    def tearDown(self):
        # En Windows un archivo abierto no se puede borrar: si quedó algún ffmpeg trabajando en la carpeta, se detiene
        # como lo hace el servidor al arrancar (hostos.stop_leftovers), y se reintenta (el antivirus puede tener el
        # registro abierto un momento). Si aun así queda algo, la carpeta temporal se deja: no es lo que se prueba.
        hostos.stop_leftovers(self.dir / "hls")
        for _ in range(40):
            try:
                self.tmp.cleanup()
                return
            except PermissionError:
                time.sleep(0.25)
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_no_queda_un_trozo_cortado(self):
        item = item_de(self.src, 120.0)
        with con_el_codificador(), contextlib.redirect_stdout(io.StringIO()):
            s = Session(item, 1, FullPlan(item), self.dir / "hls")
            self.assertIsNotNone(s.segment(0))
            limite = time.time() + 30
            while not s.path(3).exists() and time.time() < limite:
                time.sleep(0.005)
            self.assertIsNone(s.proc.poll(), "ffmpeg terminó antes de tiempo; la prueba no sirve")
            s._signal("SIGSTOP")      # como housekeeping cuando va muy adelantado (también en Windows)
            s.paused = True
            s.stop()
            quedan = sorted(i for i, _ in s._segment_files())
            for i in quedan:
                ini, fin = imagen(s.path(i))
                self.assertGreater(fin - ini, SEG - 2 * FRAME, f"quedó seg{i} con {fin - ini:.2f} s de {SEG}")
            # La TV sigue: el que falta se vuelve a convertir entero y empata con el anterior.
            k = quedan[-1] + 1
            self.assertIsNotNone(s.segment(k))
            _, fin_prev = imagen(s.path(k - 1))
            ini, fin = imagen(s.path(k))
            self.assertGreater(fin - ini, SEG - 2 * FRAME)
            # Entre una ejecución y la siguiente puede haber hasta ~0,1 s de diferencia (el arranque desde 0 corre todo
            # un poco para que nada quede en negativo: 21 ms con el chip, 83 ms con libx264); un hueco de segundos, no.
            self.assertAlmostEqual(ini, fin_prev, delta=0.15)
            s.stop()
            self.assertIsNotNone(s.proc.poll())   # no queda ffmpeg vivo


if __name__ == "__main__":
    unittest.main()
