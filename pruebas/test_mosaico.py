# Varios a la vez en la TV (mac/mosaic.py): el comando de ffmpeg (2, 3 y 4 fuentes, audio «alt» y «ts», niveles de
# respaldo), lo que llega por la API, las listas HLS, la sesión con un ffmpeg falso y reloj falso (listo, inactividad,
# trabado, reintentos, fuente caída), las rutas con una App falsa y una prueba corta con ffmpeg de verdad (se salta
# sola sin ffmpeg o sin VideoToolbox). Sin red.
# python3 -m unittest discover -s pruebas -p "test_mosaico.py"
import json, shutil, subprocess, sys, tempfile, threading, time, unittest, urllib.error, urllib.request
from pathlib import Path
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mac"))
import cine
import mosaic
from mosaic import (Mosaic, MosaicError, Mosaics, build_command, fit, item_source, master_text, parse_request,
                    pick_variant, segment_count)
from server import serve
from youtube import YouTubeError

OUT = Path("/tmp/mosaico-prueba")


# Las pruebas describen el mosaico con el chip de la Mac y un ffmpeg 7 o más nuevo, en cualquier sistema (en Linux o con
# el ffmpeg 6.1 de Ubuntu cambian el primer nivel y dos opciones: eso lo prueba test_linux.py).
_COMO_EN_LA_MAC = [mock.patch("encoders.current", return_value=mosaic.encoders.VIDEOTOOLBOX),
                   mock.patch("encoders.ffmpeg_knows", return_value=True)]


def setUpModule():
    for p in _COMO_EN_LA_MAC:
        p.start()


def tearDownModule():
    for p in _COMO_EN_LA_MAC:
        p.stop()


def local(path="/pelis/a.mkv", w=1920, h=1080, codec="h264", pix="yuv420p", start=0, asel="1", channels=2):
    return {"local": True, "live": False, "video": path, "audio": None, "vsel": "0", "asel": asel, "width": w,
            "height": h, "codec": codec, "pix_fmt": pix, "channels": channels, "start": start}


def remote(url, audio=None, live=False, w=1280, h=720):
    return {"local": False, "live": live, "video": url, "audio": audio, "vsel": "v:0", "asel": "a:0", "width": w,
            "height": h, "codec": "h264", "pix_fmt": "yuv420p", "channels": 2, "start": 0}


def entradas(cmd):
    """[(opciones, destino)] de cada -i del comando."""
    out, start = [], cmd.index("-y") + 1
    for n, a in enumerate(cmd):
        if a == "-i":
            out.append((cmd[start:n], cmd[n + 1]))
            start = n + 2
    return out


def valor(cmd, flag):
    return cmd[cmd.index(flag) + 1]


class Comando(unittest.TestCase):
    def test_dos_fuentes_audio_alt_por_el_chip(self):
        yt = remote("http://127.0.0.1:1/yt/v/m/x.m3u8", audio="http://127.0.0.1:1/yt/v/m/a.m3u8")
        live = remote("http://127.0.0.1:1/live/c/m/y.m3u8", live=True, w=960, h=540)
        cmd = build_command([yt, live], "alt", OUT)
        ins = entradas(cmd)
        self.assertEqual([t for _, t in ins], [yt["video"], yt["audio"], live["video"]])
        video_yt, audio_yt, video_live = (o for o, _ in ins)
        # Video por el chip (decodifica y achica ahí); el audio aparte no lleva -hwaccel.
        self.assertEqual(video_yt[:4], ["-hwaccel", "videotoolbox", "-hwaccel_output_format", "videotoolbox_vld"])
        self.assertNotIn("-hwaccel", audio_yt)
        # YouTube normal a tiempo real (con arranque de golpe: 12 s porque hay un en vivo, que ya trae ~12 s listos y la
        # TV necesita 5 trozos para arrancar); el en vivo no, y se rinde si deja de dar trozos.
        for o in (video_yt, audio_yt):
            self.assertIn("-re", o)
            self.assertEqual(valor(o, "-readrate_initial_burst"), "12")
        # Sin en vivo, 4 s de golpe (bastan los 2 trozos de READY_SEGMENTS).
        otro = remote("http://127.0.0.1:1/yt/w/m/x.m3u8")
        for o, _ in entradas(build_command([yt, otro], "alt", OUT)):
            self.assertEqual(valor(o, "-readrate_initial_burst"), "4")
        self.assertNotIn("-re", video_live)
        self.assertEqual(valor(video_live, "-m3u8_hold_counters"), "8")
        for o in (video_yt, audio_yt, video_live):   # por el servidor: análisis corto, extensiones flexibles
            self.assertEqual(valor(o, "-extension_picky"), "0")
            self.assertEqual(valor(o, "-probesize"), "1000000")
            self.assertEqual(valor(o, "-analyzeduration"), "1500000")
        graph = valor(cmd, "-filter_complex")
        self.assertEqual(graph.count("scale_vt="), 2)
        self.assertIn("[0:v:0]scale_vt=w=960:h=540,hwdownload,format=nv12,setsar=1[c0]", graph)
        self.assertIn("[1:a:0]aresample=48000,aformat=channel_layouts=stereo[a0]", graph)   # audio de YouTube: entrada 1
        self.assertIn("[2:a:0]", graph)                                                    # en vivo: dentro del video
        self.assertIn("[c0][c1]hstack=inputs=2:shortest=1,pad=1920:1080:0:270,fps=30[v]", graph)
        self.assertEqual(valor(cmd, "-var_stream_map"),
                         "v:0,agroup:aud,name:video a:0,agroup:aud,name:a0,language:spa,default:yes "
                         "a:1,agroup:aud,name:a1,language:eng")
        self.assertEqual(valor(cmd, "-master_pl_name"), "ff_master.m3u8")
        self.assertEqual(cmd[-1], str(OUT / "%v" / "index.m3u8"))
        self.assertEqual(valor(cmd, "-hls_segment_filename"), str(OUT / "%v" / "seg%d.ts"))
        for flag, want in (("-c:v", "h264_videotoolbox"), ("-b:v", "6M"), ("-maxrate", "6M"), ("-bufsize", "12M"),
                           ("-profile:v", "high"), ("-force_key_frames", "expr:gte(t,n_forced*2)"), ("-c:a", "aac"),
                           ("-ac", "2"), ("-b:a", "128k"), ("-hls_time", "2"), ("-hls_list_size", "10"),
                           ("-hls_flags", "delete_segments+independent_segments+temp_file")):
            self.assertEqual(valor(cmd, flag), want, flag)
        self.assertIn("-shortest", cmd)
        self.assertEqual(cmd.count("-map"), 3)

    def test_cuatro_fuentes_audio_ts(self):
        plan = [local("/p/a.mkv", start=600, channels=6),
                local("/p/b.mkv", w=640, h=480, asel=None),             # 4:3 y sin audio
                local("/p/c.mkv", w=1920, h=800, codec="hevc", pix="yuv420p10le"),
                local("/p/d.avi", codec="mpeg4", w=720, h=400)]        # el chip no lo decodifica
        cmd = build_command(plan, "ts", OUT, focus=2)
        ins = entradas(cmd)
        self.assertEqual(len(ins), 4)
        for o, _ in ins:
            self.assertIn("-re", o)
            self.assertNotIn("-extension_picky", o)
        a, b, c, d = (o for o, _ in ins)
        self.assertEqual(valor(a, "-ss"), "600.000")
        self.assertIn("-noaccurate_seek", a)   # el salto exacto no funciona con cuadros del chip
        self.assertNotIn("-ss", b)
        self.assertNotIn("-hwaccel", d)
        graph = valor(cmd, "-filter_complex")
        self.assertIn("volume=1.6,alimiter=limit=0.97[a0]", graph)                         # 5.1 a estéreo
        self.assertIn("scale_vt=w=720:h=540,hwdownload,format=nv12,pad=960:540:(ow-iw)/2:(oh-ih)/2", graph)
        self.assertIn("anullsrc=r=48000:cl=stereo[a1]", graph)
        self.assertIn("scale_vt=w=960:h=400,hwdownload,format=p010le,format=nv12", graph)   # 10 bits
        self.assertIn("[3:0]scale=960:534,format=nv12", graph)                              # por el procesador
        self.assertIn("xstack=inputs=4:layout=0_0|960_0|0_540|960_540:shortest=1,fps=30[v]", graph)
        self.assertNotIn("-var_stream_map", cmd)
        self.assertEqual(cmd[-1], str(OUT / "index.m3u8"))
        langs = [cmd[i + 1] for i, x in enumerate(cmd) if x.startswith("-metadata:s:a:")]
        self.assertEqual(langs, ["language=spa", "language=eng", "language=fra", "language=por"])
        disp = [cmd[i + 1] for i, x in enumerate(cmd) if x.startswith("-disposition:a:")]
        self.assertEqual(disp, ["0", "0", "default", "0"])
        self.assertEqual(cmd.count("-map"), 5)

    def test_tres_fuentes_en_cuadricula(self):
        cmd = build_command([local("/a"), local("/b"), local("/c")], "alt", OUT)
        self.assertIn("xstack=inputs=3:layout=0_0|960_0|480_540:fill=black:shortest=1", valor(cmd, "-filter_complex"))
        self.assertTrue(valor(cmd, "-var_stream_map").endswith("a:2,agroup:aud,name:a2,language:fra"))

    def test_foco_en_la_segunda(self):
        cmd = build_command([local("/a"), local("/b")], "alt", OUT, focus=1)
        streams = valor(cmd, "-var_stream_map").split(" ")
        self.assertNotIn("default", streams[1])
        self.assertTrue(streams[2].endswith(",default:yes"))

    def test_niveles_de_respaldo(self):
        plan = [local("/a", start=30), remote("http://x/yt/v/m/x.m3u8", audio="http://x/yt/v/m/a.m3u8")]
        simple = build_command(plan, "alt", OUT, "chip-simple")
        self.assertNotIn("-hwaccel_output_format", simple)
        self.assertEqual(simple.count("-hwaccel"), 2)   # sigue decodificando en el chip (solo los videos)
        self.assertNotIn("-noaccurate_seek", simple)
        self.assertNotIn("scale_vt", valor(simple, "-filter_complex"))
        self.assertIn("scale=960:540,format=nv12", valor(simple, "-filter_complex"))
        self.assertEqual(valor(simple, "-c:v"), "h264_videotoolbox")
        cpu = build_command(plan, "alt", OUT, "procesador")
        self.assertNotIn("-hwaccel", cpu)
        self.assertEqual(valor(cpu, "-c:v"), "libx264")
        self.assertEqual(valor(cpu, "-preset"), "veryfast")
        self.assertIn("fps=30,format=yuv420p[v]", valor(cpu, "-filter_complex"))

    def test_tamano_dentro_de_la_celda(self):
        self.assertEqual(fit(1920, 1080), (960, 540))
        self.assertEqual(fit(1280, 720), (960, 540))
        self.assertEqual(fit(640, 480), (720, 540))
        self.assertEqual(fit(1920, 800), (960, 400))
        self.assertEqual(fit(720, 720), (540, 540))
        self.assertEqual(fit(0, 0), (960, 540))


class Pedido(unittest.TestCase):
    YT = [{"kind": "yt", "id": "7fPVfHqUNJM"}, {"kind": "yt", "id": "ZVgHPSyEIqk"}]

    def error(self, body):
        with self.assertRaises(MosaicError) as c:
            parse_request(body)
        return str(c.exception)

    def test_lo_minimo(self):
        sources, layout, audio, focus = parse_request({"sources": self.YT})
        self.assertEqual(sources[0], {"kind": "yt", "id": "7fPVfHqUNJM", "audio": None, "start": None})
        self.assertEqual((layout, audio, focus), ("lado", "alt", 0))
        body = {"sources": [{"kind": "live", "id": "6184a9ebb0"}, {"kind": "item", "id": "749f2e6dc383", "audio": "a0",
                                                                     "start": 900, "title": "Shrek"}],
                "layout": "lado", "audio": "ts", "focus": 1}
        sources, layout, audio, focus = parse_request(body)
        self.assertEqual(sources[1], {"kind": "item", "id": "749f2e6dc383", "audio": 0, "start": 900.0})
        self.assertEqual((audio, focus), ("ts", 1))

    def test_cantidad(self):
        self.assertEqual(self.error({"sources": self.YT[:1]}), "Elige de 2 a 4 videos.")
        extra = [{"kind": "yt", "id": f"abcdefghij{n}"} for n in range(5)]
        self.assertEqual(self.error({"sources": extra}), "Elige de 2 a 4 videos.")
        self.assertEqual(self.error({"sources": "7fPVfHqUNJM"}), "Elige de 2 a 4 videos.")
        self.assertEqual(self.error([1, 2]), "Datos inválidos.")

    def test_tipos_e_ids(self):
        self.assertIn("tipo desconocido", self.error({"sources": [self.YT[0], {"kind": "tv", "id": "x"}]}))
        self.assertIn("El video 2 no es válido", self.error({"sources": [self.YT[0], "ZVgHPSyEIqk"]}))
        for bad in ({"kind": "yt", "id": "corto"}, {"kind": "yt", "id": 123}, {"kind": "live", "id": "6184A9EBB0"},
                    {"kind": "item", "id": "749f2e6dc38"}, {"kind": "item", "id": "../../etc/pa"}):
            self.assertIn("no tiene un id válido", self.error({"sources": [self.YT[0], bad]}), bad)
        self.assertIn("repetido", self.error({"sources": [self.YT[0], dict(self.YT[0])]}))

    def test_pista_e_inicio(self):
        def audio(a):
            return parse_request({"sources": [self.YT[0], {"kind": "item", "id": "749f2e6dc383", "audio": a}]})[0][1]["audio"]
        self.assertEqual([audio(a) for a in (None, "", 3, "a3", "2", "x0", "na")], [None, None, 3, 3, 2, "x0", "na"])
        for bad in (-1, True, "z1", "a", 1.5, [1]):
            self.assertIn("pista de audio inválida",
                          self.error({"sources": [self.YT[0], {"kind": "item", "id": "749f2e6dc383", "audio": bad}]}))
        for bad in (-5, True, "10"):
            self.assertIn("inicio inválido",
                          self.error({"sources": [self.YT[0], {"kind": "item", "id": "749f2e6dc383", "start": bad}]}))
        self.assertIn("la pista de audio solo se elige en películas",
                      self.error({"sources": [{"kind": "yt", "id": "7fPVfHqUNJM", "audio": 1}, self.YT[1]]}))
        # YouTube también puede empezar donde se iba viendo (desde la TV: «Ver con otro»); un canal en vivo, no.
        sources = parse_request({"sources": [{"kind": "yt", "id": "7fPVfHqUNJM", "start": 754}, self.YT[1]]})[0]
        self.assertEqual(sources[0], {"kind": "yt", "id": "7fPVfHqUNJM", "audio": None, "start": 754.0})
        for bad in (-5, True, "10"):
            self.assertIn("inicio inválido", self.error({"sources": [{"kind": "yt", "id": "7fPVfHqUNJM", "start": bad},
                                                                     self.YT[1]]}))
        self.assertIn("en vivo no se puede empezar",
                      self.error({"sources": [self.YT[0], {"kind": "live", "id": "6184a9ebb0", "start": 30}]}))
        live = parse_request({"sources": [self.YT[0], {"kind": "live", "id": "6184a9ebb0", "start": 0}]})[0][1]
        self.assertIsNone(live["start"])

    def test_distribucion_modo_y_foco(self):
        self.assertIn("«lado»", self.error({"sources": self.YT, "layout": "cuadricula"}))
        self.assertIn("«alt» o «ts»", self.error({"sources": self.YT, "audio": "hls"}))
        for bad in (2, -1, True, "0"):
            self.assertIn("«focus»", self.error({"sources": self.YT, "focus": bad}))


def item(iid="749f2e6dc383", path="/p/a.mkv", audio=None, video=True, duration=5400.0):
    audio = [{"index": 0, "channels": 6, "default": False}, {"index": 2, "channels": 2, "default": True},
             {"index": "x0", "channels": 2, "default": False, "file": "/p/doblaje.m4a"}] if audio is None else audio
    return {"id": iid, "path": path, "full_title": "Shrek (2001)", "duration": duration,
            "info": {"video": {"index": 1, "codec": "h264", "pix_fmt": "yuv420p", "width": 1920, "height": 1080}
                     if video else None, "audio": audio}}


class Pelicula(unittest.TestCase):
    def test_pistas(self):
        self.assertEqual(item_source(item())["audio_index"], 2)          # la marcada por omisión
        s = item_source(item(), 0, 600)
        self.assertEqual((s["audio_index"], s["channels"], s["start"], s["audio_file"]), (0, 6, 600, None))
        self.assertEqual(item_source(item(), "x0")["audio_file"], "/p/doblaje.m4a")
        self.assertIsNone(item_source(item(), "na")["audio_index"])
        self.assertIsNone(item_source(item(audio=[]))["audio_index"])
        self.assertEqual(item_source(item(audio=[{"index": 3, "channels": 2, "default": False}]))["audio_index"], 3)

    def test_errores(self):
        for args, msg in (((item(), 7), "no tiene esa pista"), ((item(video=False),), "no tiene video"),
                          ((item(), None, 5399), "dura menos")):
            with self.assertRaises(MosaicError) as c:
                item_source(*args)
            self.assertIn(msg, str(c.exception))


MASTER_YT = """#EXTM3U
#EXT-X-INDEPENDENT-SEGMENTS
#EXT-X-MEDIA:URI="/yt/v/m/a233.m3u8",TYPE=AUDIO,GROUP-ID="233",NAME="Default",DEFAULT=NO,AUTOSELECT=YES
#EXT-X-MEDIA:URI="/yt/v/m/a234.m3u8",TYPE=AUDIO,GROUP-ID="234",NAME="Default",DEFAULT=YES,AUTOSELECT=YES
#EXT-X-STREAM-INF:BANDWIDTH=290000,CODECS="avc1.4D400C,mp4a.40.5",RESOLUTION=256x144,AUDIO="233"
/yt/v/m/v144.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=1500000,CODECS="avc1.4D401F,mp4a.40.2",RESOLUTION=1280x720,FRAME-RATE=60,AUDIO="234"
/yt/v/m/v720p60.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=1100000,CODECS="avc1.4D401F,mp4a.40.2",RESOLUTION=1280x720,FRAME-RATE=30,AUDIO="234"
/yt/v/m/v720.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=900000,CODECS="vp09.00.40.08,mp4a.40.2",RESOLUTION=1280x720,AUDIO="234"
/yt/v/m/vp9.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=4500000,CODECS="avc1.640028,mp4a.40.2",RESOLUTION=1920x1080,AUDIO="234"
/yt/v/m/v1080.m3u8
"""

FF_MASTER = """#EXTM3U
#EXT-X-VERSION:6
#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="group_aud",NAME="audio_1",DEFAULT=YES,LANGUAGE="spa",CHANNELS="2",URI="a0/index.m3u8"
#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="group_aud",NAME="audio_2",DEFAULT=NO,LANGUAGE="eng",CHANNELS="2",URI="a1/index.m3u8"
#EXT-X-STREAM-INF:BANDWIDTH=6740800,RESOLUTION=1920x1080,CODECS="avc1.640028,mp4a.40.2",AUDIO="group_aud"
video/index.m3u8
"""


class Listas(unittest.TestCase):
    URL = "http://127.0.0.1:8793/yt/v/index.m3u8"

    def test_variante_mas_chica_que_llena_la_celda(self):
        v = pick_variant(MASTER_YT, self.URL)
        self.assertEqual(v["video"], "http://127.0.0.1:8793/yt/v/m/v720.m3u8")   # 720p a 30 (menos datos), H.264
        self.assertEqual(v["audio"], "http://127.0.0.1:8793/yt/v/m/a234.m3u8")   # la de su grupo
        self.assertEqual((v["width"], v["height"]), (1280, 720))

    def test_solo_chicas_y_lista_simple(self):
        small = MASTER_YT.split("#EXT-X-STREAM-INF:BANDWIDTH=1500000")[0]
        self.assertEqual(pick_variant(small, self.URL)["video"], "http://127.0.0.1:8793/yt/v/m/v144.m3u8")
        media = "#EXTM3U\n#EXT-X-TARGETDURATION:6\n#EXTINF:6,\n/live/c/s/abc.ts\n"
        v = pick_variant(media, "http://127.0.0.1:8793/live/c/index.m3u8")
        self.assertEqual((v["video"], v["audio"]), ("http://127.0.0.1:8793/live/c/index.m3u8", None))
        muxed = '#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=2130000,RESOLUTION=960x540,CODECS="avc1.42801f,mp4a.40.2"\n/live/c/m/v.m3u8\n'
        v = pick_variant(muxed, "http://127.0.0.1:8793/live/c/index.m3u8")
        self.assertEqual((v["video"], v["audio"]), ("http://127.0.0.1:8793/live/c/m/v.m3u8", None))

    def test_maestra_con_titulos(self):
        text = master_text(FF_MASTER, ['Canal "en vivo"', "El Camino"], focus=1)
        lines = text.splitlines()
        self.assertEqual(lines[2], '#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="group_aud",NAME="Canal \'en vivo\'",LANGUAGE="spa",'
                                   'DEFAULT=NO,AUTOSELECT=NO,URI="a0/index.m3u8",CHANNELS="2"')
        self.assertEqual(lines[3], '#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="group_aud",NAME="El Camino",LANGUAGE="eng",'
                                   'DEFAULT=YES,AUTOSELECT=YES,URI="a1/index.m3u8",CHANNELS="2"')
        self.assertEqual(lines[4:], FF_MASTER.splitlines()[4:])

    def test_cuantos_trozos(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "index.m3u8"
            self.assertEqual(segment_count(p), 0)
            p.write_text("#EXTM3U\n#EXT-X-MEDIA-SEQUENCE:5\n#EXTINF:2.0,\nseg5.ts\n#EXTINF:2.0,\nseg6.ts\n#EXTINF:2.0,\nseg7.ts\n")
            self.assertEqual(segment_count(p), 8)


class Reloj:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class FfmpegFalso:
    """Proceso falso: vive hasta que lo terminan (o termina solo con `rc` si se pide)."""

    def __init__(self, rc=None):
        self.returncode = rc
        self.done = threading.Event()
        self.terminated = False
        if rc is not None:
            self.done.set()

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        if not self.done.wait(timeout):
            raise subprocess.TimeoutExpired("ffmpeg", timeout)
        return self.returncode

    def terminate(self, rc=255):
        self.terminated = True
        if self.returncode is None:
            self.returncode = rc
        self.done.set()

    def kill(self):
        self.terminate(-9)

    def finish(self, rc):
        self.returncode = rc
        self.done.set()


def esperar(cond, segundos=5):
    fin = time.time() + segundos
    while time.time() < fin:
        if cond():
            return True
        time.sleep(0.02)
    return False


class Sesion(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.reloj = Reloj()
        self.logs = []
        self.procs = []
        self.rcs = []   # códigos con que terminan solos los próximos ffmpeg (None = sigue vivo)

        def popen(cmd, **kw):
            p = FfmpegFalso(self.rcs.pop(0) if self.rcs else None)
            p.cmd = cmd
            self.procs.append(p)
            return p
        patcher = mock.patch.object(Mosaic, "popen", staticmethod(popen))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.mosaics = Mosaics(self.tmp.name, "http://127.0.0.1:1", log=self.logs.append, clock=self.reloj, run=False)
        self.pelis = []
        for n in range(2):
            f = Path(self.tmp.name) / f"peli{n}.mkv"
            f.write_bytes(b"")
            self.pelis.append(item_source(item(iid=f"{n}" * 12, path=str(f), duration=0)))
        self.pelis[1]["title"] = "Otra"

    def tearDown(self):
        self.mosaics.shutdown()
        self.tmp.cleanup()

    def arrancar(self, fuentes=None, **kw):
        m = self.mosaics.start(fuentes or self.pelis, **kw)
        self.assertTrue(esperar(lambda: m.state != "preparando"), m.state)
        return m

    def escribir(self, m, trozos=2):
        (m.dir / "ff_master.m3u8").write_text(FF_MASTER)
        for name in ("video", "a0", "a1"):
            segs = "".join(f"#EXTINF:2.0,\nseg{i}.ts\n" for i in range(trozos))
            (m.dir / name / "index.m3u8").write_text(f"#EXTM3U\n#EXT-X-MEDIA-SEQUENCE:0\n{segs}")
            for i in range(trozos):
                (m.dir / name / f"seg{i}.ts").write_bytes(b"G" * 188)

    def test_arranca_y_queda_listo(self):
        m = self.arrancar()
        self.assertEqual((m.state, m.tier), ("armando", 0))
        self.assertEqual(len(self.procs), 1)
        self.assertIn("h264_videotoolbox", self.procs[0].cmd)
        self.assertEqual(len(m.id), 8)
        self.assertEqual(m.url, f"/mosaic/{m.id}/master.m3u8")
        self.escribir(m, trozos=1)
        self.assertFalse(m.status()["ready"])      # con un trozo todavía no
        self.escribir(m, trozos=2)
        st = m.status()
        self.assertTrue(st["ready"])
        self.assertEqual(st["tracks"], ["Shrek (2001)", "Otra"])
        self.assertEqual(st["sources"][0], {"kind": "item", "id": "0" * 12, "title": "Shrek (2001)", "audio": None,
                                            "start": None})
        master = m.file("master.m3u8").decode()
        self.assertIn('NAME="Shrek (2001)",LANGUAGE="spa",DEFAULT=YES', master)
        self.assertIn('NAME="Otra",LANGUAGE="eng",DEFAULT=NO', master)
        self.assertEqual(m.file("video/seg1.ts"), m.dir / "video" / "seg1.ts")
        for bad in ("../ff_master.m3u8", "a2/index.m3u8", "index.m3u8", "video/ffmpeg.log", "ffmpeg.log"):
            self.assertIsNone(m.file(bad, wait=0), bad)

    def test_se_detiene_solo_si_nadie_lo_pide(self):
        m = self.arrancar()
        self.reloj.t += 20
        self.mosaics.housekeeping()
        self.assertEqual(m.state, "armando")
        m.file("master.m3u8", wait=0)            # alguien lo pide: vuelve a contar
        self.reloj.t += 25
        self.mosaics.housekeeping()
        self.assertEqual(m.state, "armando")
        self.reloj.t += 6
        self.mosaics.housekeeping()
        self.assertEqual(m.state, "detenido")
        self.assertTrue(self.procs[0].terminated)
        self.assertFalse(m.dir.exists())
        self.assertIn("nadie lo pidió en 30 s", self.logs[-1])

    def test_uno_a_la_vez_y_detener(self):
        a = self.arrancar()
        b = self.arrancar(focus=1)
        self.assertEqual((a.state, b.state), ("detenido", "armando"))
        self.assertTrue(self.procs[0].terminated)
        self.assertIsNone(self.mosaics.get(a.id))
        self.assertIs(self.mosaics.get(b.id), b)
        self.assertTrue(self.mosaics.stop(b.id))
        self.assertEqual(b.state, "detenido")
        self.assertFalse(self.mosaics.stop("ffffffff"))

    def test_si_el_chip_falla_se_reintenta_y_se_anota(self):
        self.rcs = [1, 1, 1]
        m = self.mosaics.start(self.pelis)
        self.assertTrue(esperar(lambda: m.state == "error"), m.state)
        self.assertEqual([("-hwaccel_output_format" in p.cmd, "libx264" in p.cmd) for p in self.procs],
                         [(True, False), (False, False), (False, True)])
        avisos = [l for l in self.logs if l.startswith("⚠")]
        self.assertEqual(len(avisos), 2)
        self.assertIn("se reintenta decodificando con el chip", avisos[0])
        self.assertIn("se calienta", avisos[1])
        self.assertIn("falló también con el procesador", m.error)

    def test_si_el_chip_falla_una_vez_sigue_con_el_siguiente(self):
        self.rcs = [1]
        m = self.mosaics.start(self.pelis)
        self.assertTrue(esperar(lambda: m.tier == 1 and m.state == "armando"))
        self.assertEqual(m.status()["tier"], "chip-simple")
        self.assertEqual(m.error, "")

    def test_se_traba_una_fuente(self):
        m = self.arrancar()
        self.escribir(m)
        m.refresh()
        self.assertEqual(m.state, "listo")
        self.reloj.t += mosaic.STALL + 1
        m.touch()
        self.mosaics.housekeeping()
        self.assertTrue(esperar(lambda: m.state == "error"))
        self.assertIn("dejó de mandar video", m.error)

    def test_termina_con_la_primera_que_se_acaba(self):
        m = self.arrancar()
        self.escribir(m)
        self.procs[0].finish(0)
        self.assertTrue(esperar(lambda: m.state == "terminado"))
        self.assertEqual((m.error, m.status()["ended"]), ("", True))
        self.assertIn("Terminó «Shrek (2001)»", m.note)

    def test_ffmpeg_muere(self):
        m = self.arrancar()
        self.escribir(m)
        self.procs[0].finish(-9)
        self.assertTrue(esperar(lambda: m.state == "error"))
        self.assertEqual(m.error, "El mosaico se cortó (ffmpeg terminó con el código -9). Se puede volver a armar.")

    def test_archivo_que_ya_no_esta(self):
        m = self.arrancar()
        Path(self.pelis[1]["path"]).unlink()
        self.procs[0].finish(1)
        self.assertTrue(esperar(lambda: m.state == "error"))
        self.assertEqual(m.error, "Ya no está el archivo de «Otra».")
        self.assertEqual(len(self.procs), 1)   # no tiene caso reintentar sin el chip

    def test_fuente_de_youtube_caida(self):
        yt = {"kind": "yt", "id": "7fPVfHqUNJM", "title": "El Camino", "duration": 219}
        calls = []

        def fetch(url, timeout=60):
            calls.append(url)
            if len(calls) == 1:
                return MASTER_YT
            raise MosaicError("ya no está disponible en YouTube")
        with mock.patch.object(Mosaic, "__init__", wraps_init(fetch)):
            m = self.arrancar([self.pelis[0], yt])
            # La lista maestra y, para pedir de antemano sus primeros trozos, la de video y la de audio elegidas
            # (aquí ya fallan: no importa, ffmpeg las pide igual).
            self.assertEqual(calls, ["http://127.0.0.1:1/yt/7fPVfHqUNJM/index.m3u8", "http://127.0.0.1:1/yt/v/m/v720.m3u8",
                                     "http://127.0.0.1:1/yt/v/m/a234.m3u8"])
            ins = entradas(self.procs[0].cmd)
            self.assertEqual(ins[1][1], "http://127.0.0.1:1/yt/v/m/v720.m3u8")
            self.assertEqual(ins[2][1], "http://127.0.0.1:1/yt/v/m/a234.m3u8")
            self.escribir(m)
            self.procs[0].finish(0)
            self.assertTrue(esperar(lambda: m.state == "error"))
        self.assertEqual(m.error, "Se cayó «El Camino»: ya no está disponible en YouTube")

    def test_no_se_pudo_abrir_al_preparar(self):
        live = {"kind": "live", "id": "6184a9ebb0", "title": "Canal"}

        def fetch(url, timeout=60):
            raise MosaicError("Ese canal ya no existe.")
        with mock.patch.object(Mosaic, "__init__", wraps_init(fetch)):
            m = self.mosaics.start([self.pelis[0], live])
            self.assertTrue(esperar(lambda: m.state == "error"))
        self.assertEqual(m.error, "No se pudo abrir «Canal»: Ese canal ya no existe.")
        self.assertEqual(self.procs, [])


def wraps_init(fetch):
    """Mosaic.__init__ con otra forma de pedir las listas (sin red)."""
    original = Mosaic.__init__

    def init(self, *a, **kw):
        kw["fetch"] = fetch
        original(self, *a, **kw)
    return init


class Roku:
    def __init__(self):
        self.calls = []

    def play(self, content_id, server_url, **options):
        self.calls.append((content_id, server_url, options))


class Falso(cine.App):
    def __init__(self, tmp, pelis):
        self.roku = None
        self.server_url = "http://192.168.0.2:8765"
        self.keep_awake = mock.Mock()
        self.library = mock.Mock()
        self.library.get = lambda iid: pelis.get(iid)
        self.live = mock.Mock()
        self.live.get = lambda cid: {"id": cid, "name": "Canal 5"} if cid == "6184a9ebb0" else None
        self.youtube = mock.Mock()
        self.youtube.title_of = lambda vid: "Borrado" if vid == "borradoxxxx" else ""

        def resolve(vid, force=False):
            if vid == "borradoxxxx":
                raise YouTubeError("ya no está disponible en YouTube", gone=True)
            return {"info": {"title": "El Camino", "duration": 219}}
        self.youtube.resolve = mock.Mock(side_effect=resolve)
        self.mosaics = Mosaics(tmp, "http://127.0.0.1:1", log=lambda m: None, run=False)


class Rutas(unittest.TestCase):
    PELI = {"kind": "item", "id": "749f2e6dc383", "audio": "a0", "start": 60}
    YT = {"kind": "yt", "id": "7fPVfHqUNJM"}
    LIVE = {"kind": "live", "id": "6184a9ebb0"}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        patcher = mock.patch.object(Mosaic, "begin", lambda self: setattr(self, "state", "armando"))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.app = Falso(self.tmp.name, {"749f2e6dc383": item()})
        self.httpd = serve(self.app, 0)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.app.mosaics.shutdown()
        self.tmp.cleanup()

    def get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=5) as r:
            return json.loads(r.read())

    def raw(self, path):
        try:
            with urllib.request.urlopen(self.base + path, timeout=5) as r:
                return r.status, r.headers, r.read()
        except urllib.error.HTTPError as e:
            with e:
                return e.code, e.headers, e.read()

    def post(self, path, body):
        req = urllib.request.Request(self.base + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read())

    def test_arrancar_estado_y_detener(self):
        r = self.post("/api/mosaic/start", {"sources": [self.PELI, self.YT, self.LIVE]})
        self.assertTrue(r["ok"], r)
        self.assertRegex(r["id"], r"^[0-9a-f]{8}$")
        self.assertEqual(r["url"], f"/mosaic/{r['id']}/master.m3u8")
        self.assertEqual(r["tracks"], ["Shrek (2001)", "El Camino", "Canal 5"])
        self.app.youtube.resolve.assert_called_once_with("7fPVfHqUNJM")
        st = self.get(f"/api/mosaic/status?id={r['id']}")
        for k in ("ok", "ready", "error", "sources", "tracks"):
            self.assertIn(k, st)
        self.assertEqual((st["ok"], st["ready"], st["error"], st["state"]), (True, False, "", "armando"))
        self.assertEqual(st["sources"][0], {"kind": "item", "id": "749f2e6dc383", "title": "Shrek (2001)", "audio": 0,
                                            "start": 60.0})
        # La receta se puede mandar tal cual para rearmarlo; el anterior deja de existir.
        again = self.post("/api/mosaic/start", {"sources": st["sources"], "audio": "ts"})
        self.assertTrue(again["ok"])
        self.assertEqual(again["url"], f"/mosaic/{again['id']}/index.m3u8")
        self.assertEqual(self.get(f"/api/mosaic/status?id={r['id']}"), {"ok": False, "error": "Ese mosaico ya no existe."})
        self.assertEqual(self.post("/api/mosaic/stop", {"id": again["id"]}), {"ok": True})
        self.assertEqual(self.get(f"/api/mosaic/status?id={again['id']}")["state"], "detenido")
        self.assertFalse(self.post("/api/mosaic/stop", {"id": "ffffffff"})["ok"])
        self.assertFalse(self.post("/api/mosaic/stop", ["x"])["ok"])

    def test_errores_legibles(self):
        cases = [({"sources": [self.YT]}, "Elige de 2 a 4 videos."),
                 ({"sources": [self.YT, {"kind": "yt", "id": "borradoxxxx"}]}, "«Borrado»: ya no está disponible en YouTube"),
                 ({"sources": [self.YT, {"kind": "live", "id": "0000000000"}]}, "Uno de los canales en vivo ya no existe."),
                 ({"sources": [self.YT, {"kind": "item", "id": "000000000000"}]}, "Uno de los videos ya no está en la biblioteca."),
                 ({"sources": [self.YT, dict(self.PELI, audio=5)]}, "«Shrek (2001)» no tiene esa pista de audio."),
                 ([1], "Datos inválidos.")]
        for body, msg in cases:
            self.assertEqual(self.post("/api/mosaic/start", body), {"ok": False, "error": msg}, body)
        self.assertIsNone(self.app.mosaics.current)

    def test_archivos(self):
        r = self.post("/api/mosaic/start", {"sources": [self.PELI, self.YT]})
        m = self.app.mosaics.get(r["id"])
        for name in ("video", "a0", "a1"):
            (m.dir / name).mkdir(parents=True, exist_ok=True)
            (m.dir / name / "index.m3u8").write_text("#EXTM3U\n#EXTINF:2.0,\nseg0.ts\n")
        (m.dir / "video" / "seg0.ts").write_bytes(b"G" * 376)
        (m.dir / "ff_master.m3u8").write_text(FF_MASTER)
        code, headers, body = self.raw(f"/mosaic/{r['id']}/master.m3u8")
        self.assertEqual((code, headers["Content-Type"], headers["Cache-Control"]),
                         (200, "application/vnd.apple.mpegurl", "no-cache"))
        self.assertIn('NAME="Shrek (2001)"', body.decode())
        self.assertIn('NAME="El Camino"', body.decode())
        code, headers, body = self.raw(f"/mosaic/{r['id']}/a1/index.m3u8")
        self.assertEqual((code, headers["Content-Type"], headers["Cache-Control"]),
                         (200, "application/vnd.apple.mpegurl", "no-cache"))
        code, headers, body = self.raw(f"/mosaic/{r['id']}/video/seg0.ts")
        self.assertEqual((code, headers["Content-Type"], headers["Cache-Control"], len(body)),
                         (200, "video/mp2t", "no-cache", 376))
        self.app.keep_awake.poke.assert_called()
        for bad in (f"/mosaic/{r['id']}/video/seg9.ts", "/mosaic/ffffffff/master.m3u8", "/mosaic/zz/master.m3u8",
                    f"/mosaic/{r['id']}/ffmpeg.log", f"/mosaic/{r['id']}/a0/../../x.ts"):
            self.assertEqual(self.raw(bad)[0], 404, bad)

    def test_a_la_tv(self):
        body = {"sources": [self.PELI, self.YT], "focus": 1}
        self.assertEqual(self.post("/api/mosaic/tv", body), {"ok": False, "error": "No encontré el Roku en la red."})
        self.assertIsNone(self.app.mosaics.current)
        self.assertEqual(self.post("/api/mosaic/tv", {"sources": [self.YT]})["error"], "Elige de 2 a 4 videos.")
        self.app.roku = Roku()
        with mock.patch.object(cine, "say"):
            r = self.post("/api/mosaic/tv", body)
        self.assertTrue(r["ok"], r)
        self.assertEqual(self.app.roku.calls, [(f"mosaic:{r['id']}", "http://192.168.0.2:8765", {"focus": 1})])
        self.assertEqual(self.app.mosaics.current.focus, 1)


def _videotoolbox():
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        return False
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10",
                        "-t", "1", "-c:v", "h264_videotoolbox", "-f", "null", "-"], capture_output=True, timeout=30)
    return r.returncode == 0


@unittest.skipUnless(_videotoolbox(), "hace falta ffmpeg con VideoToolbox (macOS)")
class Integracion(unittest.TestCase):
    """ffmpeg de verdad con dos videos generados (patrón + tono): la lista maestra, dos pistas de audio y trozos."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.fuentes = []
        for n, (size, freq) in enumerate((("640x360", 440), ("320x240", 660))):
            f = Path(self.tmp.name) / f"prueba{n}.mp4"
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                            f"testsrc=size={size}:rate=30", "-f", "lavfi", "-i", f"sine=frequency={freq}:sample_rate=48000",
                            "-t", "10", "-c:v", "h264_videotoolbox", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ac", "2", str(f)],
                           check=True, capture_output=True, timeout=60)
            w, h = map(int, size.split("x"))
            self.fuentes.append(item_source({
                "id": f"{n}" * 12, "path": str(f), "full_title": f"Prueba {'AB'[n]}", "duration": 10,
                "info": {"video": {"index": 0, "codec": "h264", "pix_fmt": "yuv420p", "width": w, "height": h},
                         "audio": [{"index": 1, "channels": 2, "default": True}]}}))
        self.logs = []
        self.mosaics = Mosaics(self.tmp.name, "http://127.0.0.1:1", log=self.logs.append, run=False)

    def tearDown(self):
        self.mosaics.shutdown()
        self.tmp.cleanup()

    def test_arma_el_hls(self):
        m = self.mosaics.start(self.fuentes)
        self.assertTrue(esperar(lambda: m.status()["ready"] or m.error, 30), self.logs)
        self.assertEqual((m.error, m.tier), ("", 0), self.logs)
        master = m.file("master.m3u8").decode()
        self.assertEqual(master.count("#EXT-X-MEDIA:TYPE=AUDIO"), 2)
        self.assertIn('NAME="Prueba A",LANGUAGE="spa",DEFAULT=YES', master)
        self.assertIn('NAME="Prueba B",LANGUAGE="eng",DEFAULT=NO', master)
        self.assertIn("RESOLUTION=1920x1080", master)
        for name in ("a0", "a1"):
            self.assertTrue((m.dir / name / "index.m3u8").exists(), name)
        segs = sorted((m.dir / "video").glob("seg*.ts"))
        self.assertGreaterEqual(len(segs), 2)
        probe = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_name,width,height",
                                           "-of", "json", str(segs[0])], capture_output=True, text=True).stdout)
        self.assertEqual(probe["streams"][0], {"codec_name": "h264", "width": 1920, "height": 1080})
        proc = m.proc
        self.mosaics.stop(m.id)
        self.assertIsNotNone(proc.poll())   # no queda ffmpeg vivo
        self.assertFalse(m.dir.exists())


if __name__ == "__main__":
    unittest.main()


class ConCanalEnVivo(unittest.TestCase):
    """Con un en vivo el video sale a ráfagas: la lista que ve el reproductor esconde los trozos más nuevos."""

    def test_esconde_los_trozos_mas_nuevos(self):
        lista = "#EXTM3U\n#EXT-X-TARGETDURATION:2\n#EXT-X-MEDIA-SEQUENCE:5\n" + "".join(
            f"#EXTINF:2.000000,\nseg{i}.ts\n" for i in range(5, 12))
        corta = mosaic.hold_back(lista, 3)
        self.assertIn("seg8.ts", corta)
        self.assertNotIn("seg9.ts", corta)
        self.assertTrue(corta.rstrip().endswith("seg8.ts"))
        self.assertEqual(mosaic.hold_back(lista + "#EXT-X-ENDLIST\n", 3), lista + "#EXT-X-ENDLIST\n")   # ya terminó
        pocas = "#EXTM3U\n#EXTINF:2.0,\nseg0.ts\n#EXTINF:2.0,\nseg1.ts\n"
        self.assertEqual(mosaic.hold_back(pocas, 3), pocas)

    def test_como_se_lee_cada_fuente(self):
        vivo = mosaic._input({"local": False, "live": True, "codec": "h264"}, "http://x/live/a/index.m3u8", "chip", True)
        self.assertIn("-live_start_index", vivo)
        self.assertEqual(vivo[vivo.index("-live_start_index") + 1], "-3")   # ver mosaic.LIVE_START
        self.assertNotIn("-re", vivo)
        yt = mosaic._input({"local": False, "live": False, "codec": "h264"}, "http://x/yt/a/index.m3u8", "chip", True)
        self.assertIn("-re", yt)
        self.assertEqual(yt[yt.index("-readrate_catchup") + 1], "3")
        self.assertNotIn("-ss", yt)
        for args in (vivo, yt):
            self.assertEqual(args[args.index("-http_multiple") + 1], "1")


class YouTubeDesdeUnSegundo(unittest.TestCase):
    """«Ver con otro» desde la TV: el video de YouTube que se veía sigue en el mismo segundo dentro del mosaico."""

    def test_salta_en_video_y_audio(self):
        yt = dict(remote("http://x/yt/v/m/v.m3u8", audio="http://x/yt/v/m/a.m3u8"), start=754.0)
        live = dict(remote("http://x/live/c/m/y.m3u8", live=True), start=30)   # un en vivo nunca salta
        video_yt, audio_yt, video_live = (o for o, _ in entradas(build_command([yt, live], "alt", OUT)))
        for o in (video_yt, audio_yt):
            self.assertEqual(valor(o, "-ss"), "754.000")
            self.assertIn("-re", o)                         # y sigue a tiempo real desde ahí
        self.assertIn("-noaccurate_seek", video_yt)         # cuadros del chip: sin el salto exacto
        self.assertNotIn("-noaccurate_seek", audio_yt)
        self.assertNotIn("-ss", video_live)
        # Sin el chip (último nivel) el salto es exacto.
        cpu = entradas(build_command([yt, live], "alt", OUT, tier="procesador"))[0][0]
        self.assertEqual(valor(cpu, "-ss"), "754.000")
        self.assertNotIn("-noaccurate_seek", cpu)

    def test_la_receta_lo_conserva_y_lo_revisa(self):
        with tempfile.TemporaryDirectory() as tmp:
            def fuente(start, duration=600):
                return {"kind": "yt", "id": "7fPVfHqUNJM", "title": "El Camino", "duration": duration, "start": start}
            otra = {"kind": "yt", "id": "ZVgHPSyEIqk", "title": "Otro", "duration": 300}
            m = Mosaic("abcd1234", [fuente(120.0), otra], Path(tmp) / "m", "http://127.0.0.1:1", fetch=lambda *a, **k: MASTER_YT)
            self.assertEqual(m.status()["sources"][0]["start"], 120.0)
            self.assertIsNone(m.status()["sources"][1]["start"])
            plan = m.prepare()
            self.assertEqual((plan[0]["start"], plan[0]["live"]), (120.0, False))
            self.assertEqual(plan[1]["start"], 0)
            # Casi al final: empieza desde el principio (no cierra el mosaico al instante). En vivo: no salta.
            for s in (fuente(598.0), fuente(120.0, duration=0)):
                m = Mosaic("abcd1235", [s, otra], Path(tmp) / "n", "http://127.0.0.1:1", fetch=lambda *a, **k: MASTER_YT)
                self.assertIsNone(m.status()["sources"][0]["start"], s)
                self.assertEqual(m.prepare()[0]["start"], 0)
