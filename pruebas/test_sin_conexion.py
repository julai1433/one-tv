# Videos y listas de YouTube guardados sin conexión (mac/offline.py): la cola con ritmo medido, el espacio, listas,
# reinicios, las marcas `offline`, y que un video guardado se reproduce por las mismas direcciones sin llamar a YouTube.
# Sin red: yt-dlp y la descarga están simulados; una prueba corta usa ffmpeg de verdad (se salta sin ffmpeg).
# python3 -m unittest discover -s pruebas -p "test_sin_conexion.py"
import json, shutil, subprocess, sys, tempfile, threading, unittest, urllib.error, urllib.request
from pathlib import Path
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mac"))
import cine
from mylists import MyLists
import offline
from offline import GB, Offline, OfflineError, build_hls, find_ffmpeg
from playqueue import PlayQueue
from server import serve
from store import Store
from youtube import YouTube, YouTubeError
from ytdurations import Durations

A, B, C = "aaaaaaaaaaa", "bbbbbbbbbbb", "ccccccccccc"
LISTA = "PLlistaDePrueba1"


class Reloj:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t


def hls_falso(video, outdir):
    """Lo que dejaría ffmpeg: una lista de dos trozos."""
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "seg00000.ts").write_bytes(b"\x47" + b"\0" * 999)
    (outdir / "seg00001.ts").write_bytes(b"\x47" + b"\0" * 499)
    (outdir / "index.m3u8").write_text("#EXTM3U\n#EXT-X-TARGETDURATION:6\n#EXT-X-PLAYLIST-TYPE:VOD\n#EXTINF:6.0,\n"
                                       "seg00000.ts\n#EXTINF:3.0,\nseg00001.ts\n#EXT-X-ENDLIST\n")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.clock = Reloj()
        self.yt = YouTube(self.root / "datos", self.root / "cache", ytdlp="/nada")
        self.yt.thumbnail = lambda vid, hd=False: None
        self.bajados = []
        self.falla = {}   # id -> OfflineError que simula yt-dlp
        self.libre = 500 * GB

    def tearDown(self):
        self.tmp.cleanup()

    def descarga(self, vid, tmp, progress, set_proc):
        self.bajados.append(vid)
        if vid in self.falla:
            raise self.falla[vid]
        progress(40)
        progress(90)
        (tmp / "video.mp4").write_bytes(b"x")
        return {"title": f"Título {vid[0]}", "channel": "Canal", "channel_id": "UC" + "a" * 22, "duration": 120,
                "description": "desc", "width": 1920, "height": 1080, "upload_date": "20240105", "chapters": []}

    def hacer(self, **kw):
        kw.setdefault("downloader", self.descarga)
        kw.setdefault("packager", hls_falso)
        kw.setdefault("rand", lambda a, b: 20)
        off = Offline(kw.pop("folder", self.root / "sin conexión"), kw.pop("limit_gb", 100), self.root / "datos" / "sin_conexion.json",
                      self.yt, ytdlp="/nada", log=lambda m: None, clock=self.clock, **kw)
        off.free_bytes = lambda: self.libre
        self.yt.offline = off
        return off

    def correr(self, off, veces=1):
        """Una pasada de la cola por video, saltando la pausa entre videos."""
        for _ in range(veces):
            off.step()
            self.clock.t += 31


class Cola(Base):
    def test_baja_de_a_uno_y_queda_listo(self):
        off = self.hacer()
        self.assertEqual(off.save_video(A), {"ok": True, "state": "pendiente"})
        off.save_video(B)
        self.assertEqual(off.step(), 0)
        self.assertEqual(self.bajados, [A])
        self.assertEqual(off.status_of(A), ("listo", 100))
        self.assertEqual(off.status_of(B), ("pendiente", 0))
        self.assertTrue(off.ready(A))
        info = off.info(A)
        self.assertEqual((info["title"], info["duration"], info["width"]), ("Título a", 120, 1920))
        self.assertGreater(info["published"], 0)
        self.assertEqual(sorted(p.name for p in (off.folder / A).iterdir()), ["index.m3u8", "info.json", "seg00000.ts", "seg00001.ts"])
        self.assertFalse(list(off.folder.glob(".parcial-*")))

    def test_pausa_entre_videos(self):
        off = self.hacer()
        off.save_video(A)
        off.save_video(B)
        off.step()
        espera = off.step()
        self.assertEqual(self.bajados, [A])   # todavía no
        self.assertAlmostEqual(espera, 20, delta=1)
        self.clock.t += 21
        off.step()
        self.assertEqual(self.bajados, [A, B])

    def test_tope_por_hora(self):
        off = self.hacer(per_hour=2, pause=(0, 0), rand=lambda a, b: 0)
        for v in (A, B, C):
            off.save_video(v)
        for _ in range(3):
            off.step()
        self.assertEqual(self.bajados, [A, B])
        espera = off.step()
        self.assertGreater(espera, 3000)
        self.assertIn("por hora", off.paused)
        self.clock.t += 3601
        off.step()
        self.assertEqual(self.bajados, [A, B, C])

    def test_si_youtube_frena_se_espera(self):
        frena = [True]
        off = self.hacer(blocked=lambda: frena[0])
        off.save_video(A)
        off.step()
        self.assertEqual(self.bajados, [])
        self.assertIn("frenando", off.paused)
        frena[0] = False
        off.step()
        self.assertEqual(self.bajados, [A])

    def test_un_429_frena_toda_la_cola_seis_horas(self):
        off = self.hacer()
        self.falla[A] = OfflineError("YouTube está frenando las peticiones.", throttled=True)
        off.save_video(A)
        off.save_video(B)
        off.step()
        self.assertEqual(off.status_of(A)[0], "pendiente")   # no es culpa del video
        self.clock.t += 3600
        off.step()
        self.assertEqual(self.bajados, [A])   # sigue esperando
        self.clock.t += 6 * 3600
        self.falla.clear()
        off.step()
        self.assertEqual(self.bajados, [A, A])

    def test_video_que_ya_no_existe_queda_en_error(self):
        off = self.hacer()
        self.falla[A] = OfflineError("Ya no está disponible en YouTube.", gone=True)
        off.save_video(A)
        off.step()
        self.assertEqual(off.status_of(A)[0], "error")
        v = [x for x in off.summary()["videos"] if x["id"] == A][0]
        self.assertEqual(v["error"], "Ya no está disponible en YouTube.")
        self.clock.t += 31
        off.step()
        self.assertEqual(self.bajados, [A])   # no se reintenta solo
        self.assertEqual(off.mark([{"id": A}])[0].get("offline"), None)
        off.save_video(A)   # pero si lo piden otra vez, sí
        self.assertEqual(off.status_of(A)[0], "pendiente")

    def test_fallas_pasajeras_se_reintentan_tres_veces(self):
        off = self.hacer()
        self.falla[A] = OfflineError("YouTube no dio el video: HTTP 500")
        off.save_video(A)
        for n in range(1, 4):
            off.step()
            self.assertEqual(off.status_of(A)[0], "pendiente" if n < 3 else "error", n)
            self.clock.t += offline.RETRY_AFTER * n + 31
        self.assertEqual(self.bajados, [A, A, A])

    def test_error_de_yt_dlp_se_traduce_a_nuestro_error(self):
        off = self.hacer(downloader=lambda *a: (_ for _ in ()).throw(YouTubeError("ya no está disponible en YouTube", gone=True)))
        off.save_video(A)
        off.step()
        self.assertEqual(off.status_of(A)[0], "error")


class Espacio(Base):
    def test_limite_de_la_carpeta(self):
        off = self.hacer(limit_gb=0.0001)   # ≈ 100 KB: un video de 2 min estimado no cabe
        off.save_video(A, {"duration": 120})
        off.step()
        self.assertEqual(self.bajados, [])
        self.assertIn("Se llenó el espacio", off.paused)
        self.assertIn("sin_conexion_gb", off.paused)
        self.assertEqual(off.status_of(A)[0], "pendiente")

    def test_disco_casi_lleno(self):
        off = self.hacer()
        self.libre = 2 * GB + 1000
        off.save_video(A, {"duration": 600})
        off.step()
        self.assertEqual(self.bajados, [])
        self.assertIn("menos de 2 GB libres", off.paused)
        self.libre = 50 * GB   # el usuario libera espacio
        off.step()
        self.assertEqual(self.bajados, [A])
        self.assertEqual(off.paused, "")

    def test_resumen_trae_los_numeros_del_contrato(self):
        off = self.hacer(limit_gb=7)
        off.save_video(A)
        off.step()
        s = off.summary()
        self.assertEqual((s["limit_bytes"], s["free_bytes"]), (7 * GB, 500 * GB))
        self.assertGreater(s["bytes_total"], 1000)


class Listas(Base):
    def videos(self, *ids):
        return [{"id": i, "title": f"V {i[0]}", "channel": "C", "duration": 60} for i in ids]

    def test_guardar_lista_encola_todo_y_la_recuerda(self):
        off = self.hacer()
        r = off.save_list(LISTA, "Mi lista", self.videos(A, B) + [{"id": C, "private": True}])
        self.assertEqual((r["ok"], r["state"], r["count"]), (True, "pendiente", 2))
        s = off.summary()
        self.assertEqual(s["lists"], [{"id": LISTA, "title": "Mi lista", "count": 2, "done": 0}])
        self.assertEqual([v["lists"] for v in s["videos"]], [[LISTA], [LISTA]])
        self.correr(off, 2)
        self.assertEqual(off.summary()["lists"][0]["done"], 2)
        self.assertEqual(off.save_list(LISTA, "Mi lista", self.videos(A, B))["state"], "listo")

    def test_quitar_lista_borra_salvo_los_guardados_solos_o_en_otra_lista(self):
        off = self.hacer()
        off.save_list(LISTA, "Una", self.videos(A, B, C))
        off.save_list("PLotraListaaa", "Otra", self.videos(B))
        off.save_video(C)   # solo
        self.correr(off, 3)
        self.assertTrue(all(off.ready(v) for v in (A, B, C)))
        off.remove_list(LISTA)
        self.assertFalse((off.folder / A).exists())
        self.assertTrue(off.ready(B))   # sigue en otra lista
        self.assertTrue(off.ready(C))   # guardado solo
        self.assertEqual([l["id"] for l in off.summary()["lists"]], ["PLotraListaaa"])

    def test_quitar_un_video_borra_sus_archivos_y_lo_saca_de_las_listas(self):
        off = self.hacer()
        off.save_list(LISTA, "Una", self.videos(A, B))
        self.correr(off, 2)
        off.remove_video(A)
        self.assertFalse((off.folder / A).exists())
        self.assertEqual(off.summary()["lists"][0]["count"], 1)
        self.assertIsNone(off.status_of(A))

    def test_quitar_lo_que_se_esta_bajando_corta_la_descarga(self):
        off = self.hacer()
        proc = mock.Mock()
        proc.poll.return_value = None

        def lenta(vid, tmp, progress, set_proc):
            set_proc(proc)
            off.remove_video(vid)   # el usuario lo quita mientras baja
            return {}
        off.downloader = lenta
        off.save_video(A)
        off.step()
        proc.terminate.assert_called_once()
        self.assertIsNone(off.status_of(A))
        self.assertFalse(list(off.folder.glob(".parcial-*")))


class Reinicio(Base):
    def test_lo_que_bajaba_vuelve_a_pendiente_y_se_borran_restos(self):
        off = self.hacer()
        off.save_video(A)
        off.save_video(B)
        off.step()   # A listo
        off.videos[B]["state"] = "bajando"
        off._save()
        resto = off.folder / f".parcial-{B}"
        resto.mkdir(parents=True)
        (resto / "video.mp4").write_bytes(b"a medias")
        nuevo = self.hacer()
        self.assertEqual(nuevo.status_of(A)[0], "listo")
        self.assertEqual(nuevo.status_of(B)[0], "pendiente")
        self.assertFalse(resto.exists())
        self.assertTrue(nuevo.ready(A))

    def test_si_borran_los_archivos_vuelve_a_la_cola(self):
        off = self.hacer()
        off.save_video(A)
        off.step()
        shutil.rmtree(off.folder / A)
        self.assertEqual(self.hacer().status_of(A)[0], "pendiente")

    def test_carpeta_y_limite_por_omision(self):
        off = Offline(None, None, self.root / "s.json", self.yt, ytdlp="/nada")
        self.assertEqual(off.folder, Path.home() / "Movies" / "One TV" / "Sin conexión")
        self.assertEqual(off.limit, 100 * GB)


class Marcas(Base):
    def test_durations_apply_pone_offline(self):
        off = self.hacer()
        self.yt.durations.offline = off
        off.save_video(A)
        off.save_video(B)
        off.step()
        vs = self.yt.durations.apply([{"id": A, "duration": 5}, {"id": B, "duration": 5}, {"id": C, "duration": 5}])
        self.assertEqual([v.get("offline") for v in vs], ["listo", "pendiente", None])
        off.remove_video(A)   # las listas en caché se reutilizan: la marca se quita sola
        self.yt.durations.apply(vs)
        self.assertNotIn("offline", vs[0])


class Falso(cine.App):
    def __init__(self, tmp, off, yt):
        self.store = Store(Path(tmp) / "progreso.json")
        self.lists = MyLists(Path(tmp) / "listas.json")   # Favoritos y listas de One TV
        self.youtube = yt
        self.offline = off
        self.queue = PlayQueue(Path(tmp) / "cola.json")
        self.account = None
        self.keep_awake = mock.Mock()
        yt.related = lambda v: []

    def tell_tv_to_refresh(self):
        pass


class Rutas(Base):
    def setUp(self):
        super().setUp()
        self.llamadas = []
        self.yt.durations.offline = None
        self.off = self.hacer()
        self.yt.durations.offline = self.off
        self.yt.resolve_red = self.yt.resolve   # la de verdad: pasaría por yt-dlp
        self.app = Falso(self.root, self.off, self.yt)
        self.httpd = serve(self.app, 0)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        # Cualquier cosa que pida internet falla el caso: yt-dlp, páginas e imágenes de YouTube.
        for patch in (mock.patch("youtube.subprocess.run", side_effect=self.sin_red),
                      mock.patch("youtube.fetch4", side_effect=self.sin_red)):
            patch.start()
            self.addCleanup(patch.stop)

    def sin_red(self, *a, **k):
        self.llamadas.append(a)
        raise OSError("se llamó a YouTube (la prueba lo cuenta en self.llamadas)")

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        super().tearDown()

    def get(self, path, raw=False, headers=None):
        req = urllib.request.Request(self.base + path, headers=headers or {})
        with urllib.request.urlopen(req, timeout=5) as r:
            body = r.read()
            return (body, r) if raw else json.loads(body)

    def post(self, path, body):
        req = urllib.request.Request(self.base + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read())

    def test_api_guardar_y_quitar(self):
        with mock.patch.object(cine, "say"):
            self.assertEqual(self.post("/api/offline/save", {"id": A}), {"ok": True, "state": "pendiente"})
            self.assertFalse(self.post("/api/offline/save", {"id": "corto"})["ok"])
            self.yt.playlist_videos = lambda lid: {"id": lid, "title": "Mi lista", "videos": [
                {"id": B, "title": "B", "channel": "c", "duration": 9}, {"id": C, "title": "C", "channel": "c", "duration": 9}]}
            self.assertEqual(self.post("/api/offline/save", {"list": LISTA})["state"], "pendiente")
            s = self.get("/api/offline")
            self.assertEqual([v["id"] for v in s["videos"]], [A, B, C])
            self.assertEqual(s["lists"][0]["id"], LISTA)
            self.assertEqual(set(s["videos"][0]), {"id", "title", "channel", "duration", "thumb", "state", "progress",
                                                   "bytes", "error", "lists"})
            self.assertEqual({"bytes_total", "limit_bytes", "free_bytes"} <= set(s), True)
            self.assertEqual(self.post("/api/offline/remove", {"list": LISTA}), {"ok": True})
            self.assertEqual(self.post("/api/offline/remove", {"id": A}), {"ok": True})
        self.assertEqual(self.get("/api/offline")["videos"], [])

    def test_lista_que_no_se_puede_leer(self):
        def mal(lid):
            raise YouTubeError("YouTube no dio el video: x")
        self.yt.playlist_videos = mal
        with mock.patch.object(cine, "say"):
            r = self.post("/api/offline/save", {"list": LISTA})
        self.assertEqual(r["ok"], False)

    def test_guardado_se_reproduce_sin_youtube(self):
        self.off.save_video(A)
        self.off.step()
        # index.m3u8 (maestra) -> playlist.m3u8 -> trozos, todo del disco
        master, r = self.get(f"/yt/{A}/index.m3u8", raw=True)
        self.assertIn("mpegurl", r.headers["Content-Type"])
        self.assertIn(b"RESOLUTION=1920x1080", master)
        self.assertIn(b"playlist.m3u8", master)
        lista, _ = self.get(f"/yt/{A}/playlist.m3u8", raw=True)
        self.assertIn(b"seg00000.ts", lista)
        seg, r = self.get(f"/yt/{A}/seg00000.ts", raw=True)
        self.assertEqual((len(seg), r.headers["Content-Type"]), (1000, "video/mp2t"))
        parte, r = self.get(f"/yt/{A}/seg00000.ts", raw=True, headers={"Range": "bytes=0-9"})
        self.assertEqual((r.status, len(parte)), (206, 10))
        self.off.folder.joinpath(A, "thumb.jpg").write_bytes(b"\xff\xd8jpg")
        thumb, r = self.get(f"/yt/{A}/thumb.jpg", raw=True)
        self.assertEqual(thumb, b"\xff\xd8jpg")
        with self.assertRaises(urllib.error.HTTPError) as e:
            self.get(f"/yt/{A}/seg99999.ts")
        self.assertEqual(e.exception.code, 404)
        # check e info, sin red
        self.assertEqual(self.get(f"/api/yt/check?id={A}"), {"ok": True, "title": "Título a", "duration": 120, "live": False})
        info = self.get(f"/api/yt/info?id={A}")
        self.assertEqual((info["ok"], info["title"], info["offline"], info["offline_progress"], info["duration"]),
                         (True, "Título a", "listo", 100, 120))
        # se anota en «vistos hace poco»
        self.assertEqual([h["id"] for h in self.yt.recent()], [A])
        self.assertEqual(self.llamadas, [])

    def test_info_de_uno_en_la_cola_trae_el_estado(self):
        self.off.save_video(B)
        self.yt.resolve = lambda vid, force=False: {"info": {"title": "T", "duration": 7}}
        info = self.get(f"/api/yt/info?id={B}")
        self.assertEqual((info["offline"], info["offline_progress"]), ("pendiente", 0))
        self.assertNotIn("offline", self.get(f"/api/yt/info?id={C}"))

    def test_lo_que_no_esta_listo_sigue_pidiendo_a_youtube(self):
        self.off.save_video(B)
        with self.assertRaises(urllib.error.HTTPError) as e:   # la ruta normal intentó pasar por YouTube (simulado caído)
            self.get(f"/yt/{B}/index.m3u8")
        self.assertEqual(e.exception.code, 502)
        self.assertTrue(self.llamadas)


class ConFfmpeg(unittest.TestCase):
    @unittest.skipUnless(find_ffmpeg(), "no hay ffmpeg")
    def test_arma_el_hls_desde_un_mp4(self):
        with tempfile.TemporaryDirectory() as tmp:
            mp4 = Path(tmp) / "video.mp4"
            r = subprocess.run([find_ffmpeg(), "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=25",
                                "-f", "lavfi", "-i", "sine=frequency=440", "-t", "14", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                                "-g", "50", "-c:a", "aac", "-shortest", str(mp4)], capture_output=True)
            if r.returncode != 0:
                self.skipTest("este ffmpeg no sabe generar libx264/aac")
            out = Path(tmp) / "hls"
            build_hls(mp4, out)
            lista = (out / "index.m3u8").read_text()
            self.assertIn("#EXT-X-ENDLIST", lista)
            self.assertIn("#EXT-X-PLAYLIST-TYPE:VOD", lista)
            trozos = sorted(out.glob("seg*.ts"))
            self.assertGreaterEqual(len(trozos), 2)
            self.assertTrue(all(t.name in lista for t in trozos))
            self.assertEqual(trozos[0].read_bytes()[:1], b"\x47")   # MPEG-TS
            with self.assertRaises(OfflineError):
                build_hls(Path(tmp) / "no-existe.mp4", Path(tmp) / "otro")


if __name__ == "__main__":
    unittest.main()


class QuitarYPedirOtraVez(unittest.TestCase):
    """Quitar un video mientras baja corta la descarga; si se vuelve a pedir enseguida, no cuenta como falla."""

    def test_volver_a_pedir_mientras_baja(self):
        import offline as off_mod
        with tempfile.TemporaryDirectory() as d:
            box = {}
            def downloader(vid, tmp, progress, set_proc):
                # mientras «baja»: el usuario lo quita y lo vuelve a pedir; la descarga cortada falla
                box["off"].remove_video(vid)
                box["off"].save_video(vid)
                raise off_mod.OfflineError("cortada")
            off = off_mod.Offline(Path(d) / "g", 5, Path(d) / "estado.json", youtube=None, log=lambda *a: None,
                                  downloader=downloader, packager=lambda *a: None)
            box["off"] = off
            off.save_video("abcdefghijk")
            off.step()
            v = off.videos["abcdefghijk"]
            self.assertEqual(v["state"], "pendiente")
            self.assertEqual(v.get("tries"), 0)
            self.assertFalse(v.get("retry_at"))
