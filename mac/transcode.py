"""Conversión al vuelo a HLS para lo que el Roku no reproduce tal cual.

El Roku recibe desde el principio la lista (playlist) completa de trozos y
cada trozo se genera con ffmpeg justo cuando hace falta. Si el Roku pide un
trozo lejano (adelantaste o retomas una película), ffmpeg se reinicia en ese
punto. Los cortes caen siempre en los mismos instantes, así que los trozos
de distintas ejecuciones encajan entre sí.

Dos planes:
- CopyPlan: el video del Roku sirve tal cual (H.264) y solo falla el audio.
  Se copia el video sin tocarlo (calidad original, casi sin trabajo para la
  Mac) y solo se convierte el audio. Los cortes caen en los fotogramas clave
  del propio archivo.
- FullPlan: hay que convertir también el video (HEVC, AVI...). Se recodifica
  con el chip de video de la Mac y se fuerzan cortes exactos cada 6 s. Con
  H.264/HEVC comunes todo el trabajo (leer, achicar, recodificar) se queda en
  el chip: unas 3 veces menos procesador, y la Mac se calienta menos.
"""

import json
import math
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

SEG = 6                 # segundos por trozo (objetivo)
RESTART_GAP = 8         # si piden un trozo más allá de esto, se reinicia en ese punto
AHEAD_MAX = 60          # ffmpeg se pausa si va 60 trozos por delante de lo que se ve...
AHEAD_RESUME = 30       # ...y sigue cuando quedan 30 de margen
KEEP_BEHIND = 30        # trozos ya vistos que se guardan por si retrocedes
IDLE_STOP = 15 * 60     # sin peticiones en 15 min: se detiene ffmpeg
IDLE_DROP = 60 * 60     # sin peticiones en 1 h: se borran sus trozos
OTHER_IDLE = 30         # al empezar otra cosa, se detiene lo que lleva 30 s sin pedirse


# Formatos que el chip de video decodifica solo (H.264 de 10 bits o 4:2:2, por ejemplo, no).
VIDEOTOOLBOX = sys.platform == "darwin"   # el chip de video de la Mac; en otros sistemas se convierte con el procesador
GPU_FORMATS = {("h264", "yuv420p"), ("h264", "yuvj420p"), ("hevc", "yuv420p"), ("hevc", "yuv420p10le")}


def gpu_size(v):
    """Tamaño de salida: como mucho 1920 de ancho, en números pares."""
    w, h = v["width"], v["height"]
    if w > 1920:
        w, h = 1920, h * 1920 / w
    return int(w) // 2 * 2, int(round(h / 2)) * 2


def ext_audio(item, audio_index):
    """La pista que vive en un archivo aparte junto al video (un doblaje agregado), o None."""
    if not isinstance(audio_index, str):
        return None
    return next((a for a in item["info"]["audio"] if a["index"] == audio_index and a.get("file")), None)


def audio_input(item, audio_index, ss, copyts=False):
    """Segunda entrada de ffmpeg para las pistas aparte. El archivo aparte empieza donde empieza el video."""
    a = ext_audio(item, audio_index)
    if not a:
        return []
    start = item["info"].get("start", 0) if copyts else 0   # con -copyts los tiempos del video son los del archivo
    args = ["-itsoffset", f"{start:.6f}"] if start else []
    if ss - start > 0:
        args += ["-ss", f"{ss - start:.6f}"]
    return args + ["-i", a["file"]]


def audio_args(item, audio_index):
    if audio_index is None:
        return ["-an"]
    audio = next((a for a in item["info"]["audio"] if a["index"] == audio_index), None)
    source = "1:a:0" if ext_audio(item, audio_index) else f"0:{audio_index}"
    args = ["-map", source, "-c:a", "aac", "-ac", "2", "-ar", "48000", "-b:a", "192k"]
    if audio and audio["channels"] > 2:
        # Al pasar de 5.1 a estéreo los diálogos quedan bajos: se sube y se limita.
        args += ["-af", "aformat=channel_layouts=stereo,volume=1.6,alimiter=limit=0.97"]
    return args


class FullPlan:
    """Convierte video y audio; cortes exactos cada SEG segundos."""
    atomic = True   # el muxer HLS escribe cada trozo aparte y lo renombra al terminar
    gpu_failed = set()  # videos con los que el chip no pudo: van por el camino de siempre

    def __init__(self, item):
        self.item = item
        v = item["info"]["video"]
        self.gpu = VIDEOTOOLBOX and (v["codec"], v["pix_fmt"]) in GPU_FORMATS and item["id"] not in FullPlan.gpu_failed
        n = max(1, int((max(item["duration"], 1) - 0.5) // SEG) + 1)
        self.starts = [float(i * SEG) for i in range(n)]
        self.end = max(item["duration"], self.starts[-1] + 0.5)

    def command(self, audio_index, start, outdir):
        v = self.item["info"]["video"]
        ss = self.starts[start]
        cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error"]
        if self.gpu:
            cmd += ["-hwaccel", "videotoolbox", "-hwaccel_output_format", "videotoolbox_vld"]
        elif v["codec"] in ("h264", "hevc") and VIDEOTOOLBOX:
            cmd += ["-hwaccel", "videotoolbox"]
        if ss:
            cmd += ["-ss", f"{ss:.3f}"]
        cmd += ["-i", self.item["path"]] + audio_input(self.item, audio_index, ss) + ["-map", f"0:{v['index']}"]
        out_h = min(v["height"] or 1080, 1080)
        bitrate = "6M" if out_h >= 900 else "4M" if out_h >= 650 else "2500k"
        if self.gpu:
            w, h = gpu_size(v)
            vf = f"scale_vt=w={w}:h={h}"
        else:
            vf = "scale=w='min(1920,iw)':h=-2,format=yuv420p"
        if VIDEOTOOLBOX:
            cmd += ["-vf", vf, "-c:v", "h264_videotoolbox", "-allow_sw", "1", "-profile:v", "high"]
        else:   # sin el chip de video de la Mac (Linux, Windows): el procesador
            cmd += ["-vf", "scale=w='min(1920,iw)':h=-2,format=yuv420p", "-c:v", "libx264", "-preset", "veryfast",
                    "-profile:v", "high"]
        cmd += ["-b:v", bitrate, "-maxrate", bitrate, "-bufsize", "12M",
                "-force_key_frames", f"expr:gte(t,n_forced*{SEG})"]
        cmd += audio_args(self.item, audio_index)
        cmd += ["-sn", "-dn", "-max_muxing_queue_size", "4096", "-output_ts_offset", f"{ss:.3f}",
                "-f", "hls", "-hls_time", str(SEG), "-hls_list_size", "0", "-hls_segment_type", "mpegts",
                "-hls_flags", "temp_file+independent_segments", "-start_number", str(start),
                "-hls_segment_filename", str(outdir / "seg%d.ts"), str(outdir / "ffmpeg.m3u8")]
        return cmd


class CopyPlan:
    """Copia el video original y convierte solo el audio; corta en fotogramas clave."""
    atomic = False  # el muxer 'segment' escribe directo: un trozo está listo cuando existe el siguiente

    def __init__(self, item, keys):
        self.item = item
        starts = [keys[0]]
        for k in keys[1:]:
            if k - starts[-1] >= SEG and item["duration"] - k > 1:
                starts.append(k)
        self.starts = starts
        self.end = max(item["duration"], starts[-1] + 0.5)

    def command(self, audio_index, start, outdir):
        v = self.item["info"]["video"]
        ss = self.starts[start]
        cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error"]
        if start:
            cmd += ["-ss", f"{ss:.6f}"]
        cmd += ["-copyts", "-i", self.item["path"]] + audio_input(self.item, audio_index, ss if start else 0, True)
        cmd += ["-map", f"0:{v['index']}", "-c:v", "copy"]
        if start:
            # El salto cae en un fotograma clave anterior; se descarta el video previo al corte.
            cmd += ["-bsf:v", f"noise=drop=lt(pts*tb\\,{ss - 0.002:.6f})"]
        cmd += audio_args(self.item, audio_index)
        # Los tiempos de corte se cuentan desde donde arranca esta ejecución.
        cuts = ",".join(f"{t - ss:.6f}" for t in self.starts[start + 1:])
        cmd += ["-sn", "-dn", "-avoid_negative_ts", "disabled", "-max_muxing_queue_size", "4096",
                "-f", "segment", "-segment_format", "mpegts", "-segment_time_delta", "0.05",
                "-segment_start_number", str(start)]
        if cuts:
            cmd += ["-segment_times", cuts]
        else:
            cmd += ["-segment_time", "100000"]
        cmd.append(str(outdir / "seg%d.ts"))
        return cmd


def playlist_text(plan):
    ends = plan.starts[1:] + [plan.end]
    durations = [max(0.1, b - a) for a, b in zip(plan.starts, ends)]
    lines = ["#EXTM3U", "#EXT-X-VERSION:3", f"#EXT-X-TARGETDURATION:{math.ceil(max(durations)) + 1}",
             "#EXT-X-MEDIA-SEQUENCE:0", "#EXT-X-PLAYLIST-TYPE:VOD", "#EXT-X-INDEPENDENT-SEGMENTS"]
    for i, d in enumerate(durations):
        lines += [f"#EXTINF:{d:.3f},", f"seg{i}.ts"]
    lines.append("#EXT-X-ENDLIST")
    return "\n".join(lines) + "\n"


class Keyframes:
    """Instantes de los fotogramas clave de cada archivo (leer el índice tarda 1-2 s; se guarda)."""

    def __init__(self, cache_dir):
        self.dir = Path(cache_dir) / "keyframes"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()

    def get(self, item):
        f = self.dir / f"{item['id']}.json"
        stamp = [item["mtime"], item["size"]]
        try:
            data = json.loads(f.read_text())
            if data["stamp"] == stamp:
                return data["keys"]
        except (OSError, ValueError, KeyError):
            pass
        with self.lock:
            try:
                out = subprocess.run(
                    ["ffprobe", "-v", "error", "-select_streams", str(item["info"]["video"]["index"]),
                     "-show_entries", "packet=pts_time,flags", "-of", "csv=p=0", item["path"]],
                    capture_output=True, text=True, timeout=180, stdin=subprocess.DEVNULL).stdout
            except (subprocess.TimeoutExpired, OSError):
                return []
            keys = set()
            for line in out.splitlines():
                t, _, flags = line.partition(",")
                if "K" in flags and t not in ("", "N/A"):
                    keys.add(round(float(t), 6))
            keys = sorted(keys)
            if keys:
                f.write_text(json.dumps({"stamp": stamp, "keys": keys}))
            return keys


class Session:
    def __init__(self, item, audio_index, plan, outdir):
        self.item = item
        self.audio_index = audio_index
        self.plan = plan
        self.dir = outdir
        self.dir.mkdir(parents=True, exist_ok=True)
        self.n = len(plan.starts)
        self.lock = threading.Lock()
        self.proc = None
        self.start_seg = 0
        self.cursor = -1        # último trozo listo de forma continua desde start_seg
        self.last_req = 0
        self.last_seen = time.time()
        self.paused = False
        self.discarded = False

    def path(self, i):
        return self.dir / f"seg{i}.ts"

    def alive(self):
        return self.proc is not None and self.proc.poll() is None

    def ready(self, i):
        if not self.path(i).exists():
            return False
        if self.plan.atomic or self.path(i + 1).exists():
            return True
        return self.proc is not None and self.proc.poll() == 0 and i >= self.start_seg

    def _advance(self):
        i = max(self.cursor + 1, self.start_seg)
        while i < self.n and self.ready(i):
            i += 1
        self.cursor = i - 1

    def _signal(self, sig):
        try:
            os.kill(self.proc.pid, sig)
        except (ProcessLookupError, AttributeError):
            pass

    def _segment_files(self):
        for f in self.dir.glob("seg*.ts"):
            try:
                yield int(f.stem[3:]), f
            except ValueError:
                pass

    def stop(self):
        if self.proc is None:
            return
        if self.alive():
            if self.paused:
                self._signal(signal.SIGCONT)
            self.proc.terminate()
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        if not self.plan.atomic and self.proc.returncode != 0 and not self.discarded:
            # Se cortó (o falló) a medias: el último trozo escrito está incompleto.
            written = [i for i, _ in self._segment_files() if i >= self.start_seg]
            if written:
                self.path(max(written)).unlink(missing_ok=True)
            self.discarded = True
        self.paused = False

    def _start(self, i):
        self.stop()
        if not self.plan.atomic:
            for idx, f in self._segment_files():
                if idx >= i:
                    f.unlink(missing_ok=True)
        self.start_seg, self.cursor = i, i - 1
        self.discarded = False
        log = open(self.dir / "ffmpeg.log", "ab")
        self.proc = subprocess.Popen(self.plan.command(self.audio_index, i, self.dir),
                                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=log)
        log.close()
        how = "copiando el video y convirtiendo el audio" if isinstance(self.plan, CopyPlan) else "convirtiendo"
        print(f"  ▶ {how} de «{self.item['full_title']}» desde {int(self.plan.starts[i]) // 60} min", flush=True)

    def segment(self, i, timeout=40):
        """Devuelve la ruta del trozo i cuando esté listo (o None si no se pudo)."""
        if not 0 <= i < self.n:
            return None
        with self.lock:
            self.last_req, self.last_seen = i, time.time()
            if self.ready(i):
                return self.path(i)
            self._advance()
            if not self.alive() or i < self.start_seg or i > self.cursor + RESTART_GAP:
                self._start(i)
            elif self.paused:
                self._signal(signal.SIGCONT)
                self.paused = False
            proc = self.proc
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self.lock:
                if self.ready(i):
                    return self.path(i)
                if self.proc is not proc and i < self.start_seg:
                    return None  # alguien saltó a otro punto; esta petición ya no importa
                if proc.poll() is not None and self.proc is proc:
                    if proc.returncode > 0 and getattr(self.plan, "gpu", False):
                        # El chip de video no pudo con este archivo: se repite por el camino de siempre.
                        FullPlan.gpu_failed.add(self.item["id"])
                        self.plan.gpu = False
                        print(f"  ! el chip de video no pudo con «{self.item['full_title']}»; "
                              "se convierte con el procesador", flush=True)
                        self._start(i)
                        proc = self.proc
                        continue
                    return None
            time.sleep(0.1)
        return None

    def housekeeping(self):
        now = time.time()
        with self.lock:
            if self.alive():
                self._advance()
                ahead = self.cursor - self.last_req
                if not self.paused and ahead > AHEAD_MAX:
                    self._signal(signal.SIGSTOP)
                    self.paused = True
                elif self.paused and ahead < AHEAD_RESUME:
                    self._signal(signal.SIGCONT)
                    self.paused = False
                if now - self.last_seen > IDLE_STOP:
                    self.stop()
            for idx, f in self._segment_files():
                if idx < self.last_req - KEEP_BEHIND:
                    f.unlink(missing_ok=True)


class Transcoder:
    def __init__(self, cache_dir):
        self.root = Path(cache_dir) / "hls"
        # Conversiones que quedaron vivas si la vez anterior se cerró a la fuerza.
        for sig in ("-CONT", "-TERM"):
            subprocess.run(["pkill", sig, "-f", str(self.root)], capture_output=True)
        shutil.rmtree(self.root, ignore_errors=True)
        self.root.mkdir(parents=True, exist_ok=True)
        self.keyframes = Keyframes(cache_dir)
        self.sessions = {}
        self.lock = threading.Lock()
        threading.Thread(target=self._loop, daemon=True).start()

    def _plan(self, item):
        # "direct" también llega aquí cuando lo pide un navegador (Safari no abre MKV): el video se copia igual.
        if item["mode"] in ("copy", "direct"):
            keys = self.keyframes.get(item)
            if len(keys) >= 2:
                return CopyPlan(item, keys)
        return FullPlan(item)

    def session(self, item, audio_index, client=""):
        """Una sesión por video, pista de audio y aparato (la tele y el iPhone pueden ver a la vez)."""
        key = (item["id"], audio_index, client)
        with self.lock:
            s = self.sessions.get(key)
            if s is None or s.item["path"] != item["path"] or s.item["mode"] != item["mode"]:
                if s is not None:
                    s.stop()
                plan = self._plan(item)
                folder = f"{item['id']}-{audio_index}-{client.replace(':', '_').replace('.', '_')}"
                s = Session(item, audio_index, plan, self.root / folder)
                self.sessions[key] = s
            # Lo que nadie pidió en los últimos segundos (cambiaste de película) deja de convertirse.
            for k, other in self.sessions.items():
                if k != key and other.alive() and time.time() - other.last_seen > OTHER_IDLE:
                    other.stop()
            return s

    def warm_keyframes(self, items):
        for item in items:
            if item["mode"] in ("copy", "direct"):
                self.keyframes.get(item)

    def _loop(self):
        while True:
            time.sleep(2)
            with self.lock:
                sessions = list(self.sessions.items())
            for key, s in sessions:
                s.housekeeping()
                if time.time() - s.last_seen > IDLE_DROP:
                    s.stop()
                    shutil.rmtree(s.dir, ignore_errors=True)
                    with self.lock:
                        self.sessions.pop(key, None)

    def shutdown(self):
        with self.lock:
            for s in self.sessions.values():
                s.stop()
