"""Videos y listas de YouTube guardados en la computadora para verlos sin internet (y aunque YouTube los borre).

Una cola de descargas, de a uno, en un hilo: yt-dlp baja el video en H.264 (hasta 1080p) con audio AAC, que es lo único
que el Roku decodifica, y ffmpeg lo pasa (sin recodificar) a un HLS de video bajo demanda en
<carpeta>/<id>/index.m3u8, junto a info.json y las miniaturas. El servidor lo entrega por las MISMAS direcciones de
siempre (/yt/<id>/…) sin tocar YouTube. El ritmo está medido para que YouTube no frene (ver mac/ytdurations.py):
pausa entre videos, tope por hora y espera si YouTube está frenando.

Estado en datos/sin_conexion.json: {"videos": {id: {...}}, "lists": {id: {"title", "videos": [ids]}}, …}. Un video
puede estar guardado solo («solo») y/o por pertenecer a listas; sus archivos se borran cuando ya no lo pide nadie.
"""

import json
import os
import random
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

import hostos
from youtube import GONE, VIDEO_ID, YT_LANG, YouTubeError, find_ytdlp, info_from
from ytdurations import BLOCK_FOR

DEFAULT_FOLDER = hostos.tilde(hostos.user_dir("VIDEOS") / "One TV" / "Sin conexión")   # en macOS, ~/Movies/…
DEFAULT_LIMIT_GB = 100
GB = 1024 ** 3
MIN_FREE = 2 * GB                 # el disco no se llena del todo por guardar videos
EST_BYTES_PER_SECOND = 450_000    # lo que pesa, más o menos, un video de YouTube en 1080p H.264 (para avisar antes)
PAUSE = (15, 30)                  # segundos entre un video y el siguiente
PER_HOUR = 30                     # videos que se piden a YouTube por hora, como máximo
MAX_TRIES = 3                     # intentos por video ante fallas pasajeras
RETRY_AFTER = 600                 # segundos de espera antes de reintentar (se multiplica por el intento)
IDLE_WAIT = 30
SEGMENT_SECONDS = 6
LIST_ID = re.compile(r"^[\w-]{10,64}$")
# Solo H.264 (avc1) hasta 1080p y audio AAC (m4a): el Roku NO decodifica VP9, AV1 ni Opus.
FORMAT = ("bv*[vcodec^=avc1][height<=1080]+ba[ext=m4a]/b[vcodec^=avc1][height<=1080][ext=mp4]")
PERCENT = re.compile(r"\[download\]\s+([\d.]+)%")
DESTINATION = re.compile(r"\[download\] Destination:")
THROTTLED = re.compile(r"429|too many requests|not a bot|no eres un bot|no eres un robot", re.I)
NO_FORMAT = re.compile(r"requested format is not available|no se encuentra el formato|formato solicitado", re.I)


class OfflineError(Exception):
    """Fallo al guardar un video. gone: ya no existe en YouTube. throttled: YouTube está frenando."""

    def __init__(self, message, gone=False, throttled=False, retry=True):
        super().__init__(message)
        self.gone, self.throttled, self.retry = gone, throttled, retry


def find_ffmpeg():
    for c in ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", shutil.which("ffmpeg")):
        if c and Path(c).exists():
            return c
    return None


def dir_size(path):
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def build_hls(video, outdir, ffmpeg=None, run=subprocess.run):
    """mp4 (H.264 + AAC) -> HLS de video bajo demanda en outdir/index.m3u8 (trozos TS de ~6 s), sin recodificar."""
    ffmpeg = ffmpeg or find_ffmpeg()
    if not ffmpeg:
        raise OfflineError("Falta ffmpeg en la computadora (brew install ffmpeg).", retry=False)
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    cmd = [ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error", "-y", "-i", str(video),
           "-map", "0:v:0", "-map", "0:a:0?", "-c", "copy", "-f", "hls", "-hls_time", str(SEGMENT_SECONDS),
           "-hls_playlist_type", "vod", "-hls_segment_type", "mpegts", "-hls_flags", "independent_segments",
           "-hls_segment_filename", str(outdir / "seg%05d.ts"), str(outdir / "index.m3u8")]
    out = run(cmd, capture_output=True, text=True, timeout=1800, stdin=subprocess.DEVNULL)
    if out.returncode != 0 or not (outdir / "index.m3u8").exists():
        tail = (out.stderr or "").strip().splitlines()[-1:] or ["sin detalle"]
        raise OfflineError(f"No se pudo preparar el video para la TV ({tail[0][:140]}).")


class Offline:
    def __init__(self, folder, limit_gb, state_file, youtube, ytdlp=None, log=print, clock=time.time,
                 blocked=None, downloader=None, packager=None, pause=PAUSE, per_hour=PER_HOUR, rand=random.uniform):
        self.folder = Path(str(folder or DEFAULT_FOLDER)).expanduser()
        try:
            self.limit = int(float(limit_gb if limit_gb is not None else DEFAULT_LIMIT_GB) * GB)
        except (TypeError, ValueError):
            self.limit = DEFAULT_LIMIT_GB * GB
        self.state_file = Path(state_file)
        self.youtube = youtube
        self.ytdlp = ytdlp or getattr(youtube, "ytdlp", None) or find_ytdlp()
        self.log, self.clock = log, clock
        self.blocked = blocked or (lambda: False)   # ¿ytdurations dice que YouTube está frenando?
        self.downloader = downloader or self._ytdlp_download
        self.packager = packager or build_hls
        self.pause, self.per_hour, self.rand = pause, per_hour, rand
        self.lock = threading.RLock()
        self.wake = threading.Event()
        self.thread = None
        self.stopping = False
        self.proc = None          # el yt-dlp de ahora (para cortarlo si quitan ese video)
        self.current = None       # id que se está bajando
        self.paused = ""          # por qué la cola no avanza (en español), o ""
        self.blocked_until = 0.0
        self.videos, self.lists, self.seq, self.started, self.next_at = {}, {}, 0, [], 0.0
        self._load()

    # ---------- estado en disco ----------

    def _load(self):
        try:
            d = json.loads(self.state_file.read_text())
        except (OSError, ValueError):
            d = {}
        if not isinstance(d, dict):
            d = {}
        self.videos = {k: v for k, v in (d.get("videos") or {}).items() if VIDEO_ID.match(k) and isinstance(v, dict)}
        self.lists = {k: v for k, v in (d.get("lists") or {}).items() if isinstance(v, dict)}
        self.seq = int(d.get("seq") or 0)
        now = self.clock()
        self.started = [t for t in d.get("started") or [] if isinstance(t, (int, float)) and now - t < 3600]
        self.next_at = float(d.get("next_at") or 0)
        self.blocked_until = float(d.get("blocked_until") or 0)
        # Lo que estaba bajando cuando se apagó vuelve a la cola, y se borran los restos a medias.
        for vid, v in self.videos.items():
            v["progress"] = 0
            if v.get("state") == "bajando":
                v["state"] = "pendiente"
            if v.get("state") == "listo" and not (self.folder / vid / "index.m3u8").exists():
                v["state"] = "pendiente"   # alguien borró los archivos
                v["bytes"] = 0
        if self.folder.is_dir():
            for p in self.folder.glob(".parcial-*"):
                shutil.rmtree(p, ignore_errors=True)
        self._save()

    def _save(self):
        with self.lock:
            data = {"videos": self.videos, "lists": self.lists, "seq": self.seq, "started": self.started,
                    "next_at": self.next_at, "blocked_until": self.blocked_until}
            try:
                self.state_file.parent.mkdir(parents=True, exist_ok=True)
                tmp = self.state_file.with_suffix(".tmp")
                tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1))
                tmp.replace(self.state_file)
            except OSError as e:
                self.log(f"⚠ Sin conexión: no se pudo guardar el estado ({e})")

    # ---------- consultas ----------

    def _lists_of(self, vid):
        return [lid for lid, l in self.lists.items() if vid in (l.get("videos") or [])]

    def status_of(self, vid):
        """(estado, progreso) de un video en la cola o guardado; None si no está. «error» cuenta como no estar para
        las tarjetas (la web lo ve en /api/offline)."""
        with self.lock:
            v = self.videos.get(vid)
            return (v["state"], int(v.get("progress") or 0)) if v else None

    def mark(self, videos):
        """Pone `offline` (pendiente | bajando | listo) a los videos que están en la cola o guardados, y se lo quita a
        los demás (las listas en caché se reutilizan). Los que dieron error no llevan marca."""
        with self.lock:
            for v in videos or []:
                if not isinstance(v, dict):
                    continue
                s = self.videos.get(v.get("id"))
                if s and s["state"] != "error":
                    v["offline"] = s["state"]
                else:
                    v.pop("offline", None)
        return videos

    def ready(self, vid):
        with self.lock:
            v = self.videos.get(vid)
            if not v or v.get("state") != "listo":
                return False
        return (self.folder / vid / "index.m3u8").exists() and (self.folder / vid / "info.json").exists()

    def info(self, vid):
        """Los datos de un video guardado (de su info.json), sin tocar internet; None si no está listo."""
        if not VIDEO_ID.match(vid or "") or not self.ready(vid):
            return None
        try:
            d = json.loads((self.folder / vid / "info.json").read_text())
        except (OSError, ValueError):
            return None
        return d if isinstance(d, dict) else None

    def file(self, vid, name):
        """Ruta de un archivo de un video guardado (lista, trozo, miniatura) o None."""
        if not self.ready(vid) or not re.fullmatch(r"index\.m3u8|seg\d+\.ts|thumb(-hd)?\.jpg", name or ""):
            return None
        p = self.folder / vid / name
        return p if p.is_file() else None

    def master(self, vid):
        """Lista maestra que se sirve en /yt/<id>/index.m3u8: dice el tamaño (mac/mosaic.py lo usa para no deformar)
        y apunta a la lista de trozos del disco."""
        info = self.info(vid) or {}
        bw = int((info.get("bytes") or 0) * 8 / max(info.get("duration") or 1, 1)) or 4_000_000
        size = f",RESOLUTION={info['width']}x{info['height']}" if info.get("width") and info.get("height") else ""
        return f"#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH={max(bw, 100000)}{size}\nplaylist.m3u8\n"

    def used_bytes(self):
        with self.lock:
            return sum(int(v.get("bytes") or 0) for v in self.videos.values() if v.get("state") == "listo")

    def free_bytes(self):
        p = self.folder
        while not p.exists() and p != p.parent:
            p = p.parent
        try:
            return shutil.disk_usage(p).free
        except OSError:
            return 0

    def summary(self):
        with self.lock:
            videos = []
            for vid, v in sorted(self.videos.items(), key=lambda kv: kv[1].get("n", 0)):
                videos.append({"id": vid, "title": v.get("title") or "Video de YouTube", "channel": v.get("channel") or "",
                               "duration": int(v.get("duration") or 0), "thumb": f"/yt/{vid}/thumb.jpg",
                               "state": v["state"], "progress": int(v.get("progress") or 0),
                               "bytes": int(v.get("bytes") or 0), "error": v.get("error") or "",
                               "lists": self._lists_of(vid)})
            lists = [{"id": lid, "title": l.get("title") or "Lista", "count": len(l.get("videos") or []),
                      "done": sum(1 for x in l.get("videos") or [] if self.videos.get(x, {}).get("state") == "listo")}
                     for lid, l in self.lists.items()]
            paused = self.paused
        return {"ok": True, "videos": videos, "lists": lists, "bytes_total": self.used_bytes(),
                "limit_bytes": self.limit, "free_bytes": self.free_bytes(), "paused": paused}

    # ---------- guardar y quitar ----------

    def _meta(self, vid, meta=None):
        rec = dict(self.youtube.known(vid) or {}) if self.youtube else {}
        rec.update({k: v for k, v in (meta or {}).items() if v})
        return {"title": rec.get("title") or "", "channel": rec.get("channel") or "",
                "duration": int(rec.get("duration") or 0)}

    def _enqueue(self, vid, meta=None, solo=False):
        """Pone un video en la cola (o lo deja si ya está). Se llama con el candado tomado."""
        v = self.videos.get(vid)
        info = self._meta(vid, meta)
        if v:
            for k, val in info.items():
                if val and not v.get(k):
                    v[k] = val
            if v["state"] == "error":   # el usuario lo vuelve a pedir: se intenta de nuevo
                v.update(state="pendiente", error="", tries=0, retry_at=0)
        else:
            self.seq += 1
            v = self.videos[vid] = {**info, "state": "pendiente", "progress": 0, "bytes": 0, "error": "", "tries": 0,
                                    "n": self.seq, "solo": False}
        if solo:
            v["solo"] = True
        return v

    def save_video(self, vid, meta=None):
        vid = (vid or "").strip()
        if not VIDEO_ID.match(vid):
            return {"ok": False, "error": "Ese no parece un video de YouTube."}
        with self.lock:
            v = self._enqueue(vid, meta, solo=True)
            self.paused = ""
            state = v["state"]
        self._save()
        self.wake.set()
        return {"ok": True, "state": state}

    def save_list(self, list_id, title, videos):
        """Recuerda la lista y encola todos sus videos (los privados no se pueden bajar)."""
        if not LIST_ID.match(list_id or ""):
            return {"ok": False, "error": "Esa no parece una lista de YouTube."}
        ids = []
        with self.lock:
            for e in videos or []:
                if e.get("private") or not VIDEO_ID.match(e.get("id") or ""):
                    continue
                self._enqueue(e["id"], e)
                ids.append(e["id"])
            ids = list(dict.fromkeys(ids))
            self.lists[list_id] = {"title": title or "Lista", "videos": ids}
            self.paused = ""
            states = {self.videos[i]["state"] for i in ids}
        self._save()
        self.wake.set()
        state = "listo" if states == {"listo"} else "bajando" if "bajando" in states else "pendiente"
        return {"ok": True, "state": state, "count": len(ids)}

    def _delete_files(self, vid):
        shutil.rmtree(self.folder / vid, ignore_errors=True)
        shutil.rmtree(self.folder / f".parcial-{vid}", ignore_errors=True)

    def _drop(self, vid):
        """Olvida un video y borra sus archivos; si se está bajando, corta la descarga."""
        self.videos.pop(vid, None)
        if self.current == vid and self.proc and self.proc.poll() is None:
            self.proc.terminate()
        self._delete_files(vid)

    def remove_video(self, vid):
        with self.lock:
            if vid not in self.videos:
                return {"ok": True}
            for l in self.lists.values():   # quitarlo es quitarlo: ya no cuenta en sus listas
                if vid in (l.get("videos") or []):
                    l["videos"] = [x for x in l["videos"] if x != vid]
            self._drop(vid)
        self._save()
        return {"ok": True}

    def remove_list(self, list_id):
        """Olvida la lista y borra sus videos, salvo los guardados solos o en otra lista."""
        with self.lock:
            lst = self.lists.pop(list_id, None)
            for vid in (lst or {}).get("videos") or []:
                v = self.videos.get(vid)
                if v and not v.get("solo") and not self._lists_of(vid):
                    self._drop(vid)
        self._save()
        return {"ok": True}

    # ---------- la cola ----------

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stopping = False
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.stopping = True
        self.wake.set()
        with self.lock:
            if self.proc and self.proc.poll() is None:
                self.proc.terminate()

    def _loop(self):
        while not self.stopping:
            try:
                wait = self.step()
            except Exception as e:  # noqa: BLE001 - el hilo nunca debe morir
                self.log(f"⚠ Sin conexión: {e}")
                wait = 60
            if wait:
                self.wake.wait(wait)
            self.wake.clear()

    def _next_pending(self, now):
        """(id, segundos hasta el siguiente reintento): el primero de la cola al que ya le toca."""
        later = None
        for vid, v in sorted(self.videos.items(), key=lambda kv: kv[1].get("n", 0)):
            if v["state"] != "pendiente":
                continue
            wait = float(v.get("retry_at") or 0) - now
            if wait <= 0:
                return vid, 0
            later = wait if later is None else min(later, wait)
        return None, later

    def _estimate(self, vid):
        return int(self.videos[vid].get("duration") or 0) * EST_BYTES_PER_SECOND

    def space_problem(self, vid):
        """Texto en español si no cabe este video (límite de la carpeta o disco casi lleno); "" si cabe."""
        est = self._estimate(vid)
        if self.used_bytes() + est > self.limit:
            return (f"Se llenó el espacio para guardar videos ({self.used_bytes() / GB:.1f} de {self.limit / GB:.0f} GB). "
                    "Quita algunos o sube «sin_conexion_gb» en config.json.")
        if self.free_bytes() - est < MIN_FREE:
            return (f"Quedan menos de 2 GB libres en el disco ({self.free_bytes() / GB:.1f} GB). "
                    "Libera espacio para seguir guardando videos.")
        return ""

    def step(self):
        """Hace lo que toque ahora (a lo más un video) y devuelve cuántos segundos esperar antes de volver a mirar.
        Las pruebas lo llaman a mano, con un reloj falso; el hilo lo llama solo."""
        now = self.clock()
        with self.lock:
            vid, later = self._next_pending(now)
        if not vid:
            self.paused = ""
            return min(later, IDLE_WAIT) if later else IDLE_WAIT
        # Medido, para que YouTube no frene.
        if now < self.blocked_until or self.blocked():
            wait = max(self.blocked_until - now, 300)
            self.paused = "YouTube está frenando las peticiones; la cola espera para no empeorarlo."
            return min(wait, 300)
        with self.lock:
            self.started = [t for t in self.started if now - t < 3600]
            capped = len(self.started) >= self.per_hour
            oldest = min(self.started) if self.started else now
        if capped:
            wait = oldest + 3600 - now
            self.paused = f"Tope de {self.per_hour} videos por hora para no saturar a YouTube."
            return max(wait, 1)
        if now < self.next_at:
            return self.next_at - now
        problem = self.space_problem(vid)
        if problem:
            self.paused = problem
            return IDLE_WAIT
        self.paused = ""
        self._process(vid, now)
        return 0

    def _process(self, vid, now):
        with self.lock:
            v = self.videos.get(vid)
            if not v:
                return
            v.update(state="bajando", progress=0, error="")
            n = v.get("n")   # si lo quitan y lo vuelven a pedir mientras baja, la entrada nueva trae otro número
            self.current = vid
            self.started.append(now)
        self._save()
        tmp = self.folder / f".parcial-{vid}"
        shutil.rmtree(tmp, ignore_errors=True)
        failure = None
        try:
            tmp.mkdir(parents=True)
            self.log(f"⬇ Guardando sin conexión: {v.get('title') or vid}")
            info = self.downloader(vid, tmp, lambda pct: self._progress(vid, pct), self._set_proc)
            if (self.videos.get(vid) or {}).get("n") != n:   # lo quitaron mientras bajaba (y quizá lo volvieron a pedir)
                return
            self._progress(vid, 98)
            self.packager(tmp / "video.mp4", tmp / "hls")
            self._finish(vid, tmp, info)
        except OfflineError as e:
            failure = e
        except YouTubeError as e:
            failure = OfflineError(str(e), gone=e.gone)
        except (OSError, subprocess.SubprocessError, ValueError) as e:
            failure = OfflineError(f"No se pudo guardar ({str(e)[:140]})")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
            with self.lock:
                self.current, self.proc = None, None
                self.next_at = self.clock() + self.rand(*self.pause)
        # Cortado porque lo quitaron: no es una falla. Si lo volvieron a pedir, la entrada nueva sigue en la cola y se
        # baja en cuanto toque (antes se contaba como falla del video nuevo y esperaba minutos para reintentar).
        if failure and (self.videos.get(vid) or {}).get("n") == n:
            self._failed(vid, failure)
        self._save()

    def _set_proc(self, proc):
        with self.lock:
            self.proc = proc

    def _progress(self, vid, pct):
        with self.lock:
            v = self.videos.get(vid)
            if v and v["state"] == "bajando":
                v["progress"] = max(0, min(int(pct), 99))

    def _finish(self, vid, tmp, info):
        """Arma la carpeta final del video (HLS + info.json + miniaturas) y la pone en su lugar de una vez."""
        built = tmp / "hls"
        data = info_from(vid, info)
        data["width"], data["height"] = int(info.get("width") or 0), int(info.get("height") or 0)
        data["title"] = data.get("title") or self.videos.get(vid, {}).get("title") or "Video de YouTube"
        for name, hd in (("thumb.jpg", False), ("thumb-hd.jpg", True)):
            try:
                p = self.youtube.thumbnail(vid, hd=hd)
            except Exception:  # noqa: BLE001 - sin miniatura se sigue: la web pone la de siempre
                p = None
            if p and Path(p).exists():
                shutil.copyfile(p, built / name)
        data["bytes"] = dir_size(built)
        (built / "info.json").write_text(json.dumps(data, ensure_ascii=False, indent=1))
        final = self.folder / vid
        with self.lock:
            if vid not in self.videos:
                return
            shutil.rmtree(final, ignore_errors=True)
            built.replace(final)
            v = self.videos[vid]
            v.update(state="listo", progress=100, bytes=dir_size(final), error="", tries=0,
                     title=data.get("title") or v.get("title"), channel=data.get("channel") or v.get("channel"),
                     duration=int(data.get("duration") or v.get("duration") or 0))
        self.log(f"✓ Guardado sin conexión: {data.get('title') or vid} ({dir_size(final) / 1e6:.0f} MB)")

    def _failed(self, vid, e):
        with self.lock:
            v = self.videos.get(vid)
            if not v:
                return
            if e.throttled:   # no es culpa del video: a la cola otra vez y la cola entera espera
                v.update(state="pendiente", progress=0)
                self.blocked_until = self.clock() + BLOCK_FOR
                self.log("⚠ Sin conexión: YouTube está frenando; la cola espera 6 h.")
                return
            v["tries"] = int(v.get("tries") or 0) + 1
            if e.gone or not e.retry or v["tries"] >= MAX_TRIES:
                v.update(state="error", progress=0, error=str(e))
                self.log(f"✗ Sin conexión: «{v.get('title') or vid}»: {e}")
            else:
                v.update(state="pendiente", progress=0, error="", retry_at=self.clock() + RETRY_AFTER * v["tries"])
                self.log(f"⚠ Sin conexión: «{v.get('title') or vid}» falló ({e}); se reintenta en unos minutos")

    # ---------- yt-dlp ----------

    def _ytdlp_download(self, vid, tmp, progress, set_proc):
        """Baja el video a tmp/video.mp4 (H.264 + AAC) y devuelve lo que dio yt-dlp (su .info.json)."""
        if not self.ytdlp:
            raise OfflineError("Falta yt-dlp en la computadora (brew install yt-dlp).", retry=False)
        ffmpeg = find_ffmpeg()
        cmd = [self.ytdlp, "--force-ipv4", "--no-warnings", "--newline", "--no-playlist", "--no-mtime",
               "--extractor-args", f"youtube:lang={YT_LANG}", "-f", FORMAT, "--merge-output-format", "mp4",
               "--write-info-json", "-o", str(tmp / "video.%(ext)s")]
        if ffmpeg:   # el servicio no hereda el PATH de Homebrew
            cmd += ["--ffmpeg-location", ffmpeg]
        proc = subprocess.Popen(cmd + [f"https://www.youtube.com/watch?v={vid}"], stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, stdin=subprocess.DEVNULL)
        set_proc(proc)
        stage, lines = 0, []
        for line in proc.stdout:
            lines.append(line.rstrip())
            if DESTINATION.search(line):
                stage += 1
            m = PERCENT.search(line)
            if m:   # primero el video (casi todo el peso) y luego el audio
                pct = float(m.group(1))
                progress(pct * 0.92 if stage <= 1 else 92 + pct * 0.06)
        proc.wait()
        if vid not in self.videos:   # lo quitaron: no importa cómo terminó
            return {}
        if proc.returncode != 0:
            err = [l for l in lines if l.startswith("ERROR")] or lines[-1:] or ["sin respuesta"]
            reason = err[-1]
            if GONE.search(reason):
                raise OfflineError("Ya no está disponible en YouTube.", gone=True)
            if THROTTLED.search(reason):
                raise OfflineError("YouTube está frenando las peticiones.", throttled=True)
            if NO_FORMAT.search(reason):
                raise OfflineError("YouTube no tiene este video en un formato que la TV pueda reproducir (H.264).",
                                   retry=False)
            raise OfflineError(f"YouTube no dio el video: {reason[:140]}")
        if not (tmp / "video.mp4").exists():
            raise OfflineError("La descarga terminó sin dejar el video.")
        try:
            return json.loads((tmp / "video.info.json").read_text())
        except (OSError, ValueError):
            return {}
