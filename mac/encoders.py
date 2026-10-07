"""Con qué se comprime a H.264 el video que hay que convertir para la TV (mac/transcode.py).

- En la Mac, siempre su chip de video (VideoToolbox), como siempre.
- En otra computadora (Linux o Windows), al arrancar el servidor se prueba un segundo de video con cada chip que
  conozca ffmpeg, en este orden: NVIDIA (NVENC), Intel (Quick Sync) y, en Linux, VAAPI (Intel y AMD); en Windows,
  AMD (AMF). Se queda el primero que funcione. Si ninguno, el procesador (libx264), que siempre está. config.json
  puede fijarlo con «codificador»: "auto" (lo de siempre), "nvenc", "qsv", "amf", "vaapi" o "libx264".

Con un chip, el video se sigue abriendo y achicando con el procesador; solo la compresión (lo que más trabajo da)
va al chip. La prueba usa los mismos filtros y opciones que la conversión de verdad.

También dice si este ffmpeg conoce una opción (el de Ubuntu 24.04 es el 6.1; algunas son del 7).
"""

import functools
import glob
import os
import re
import subprocess
import sys

MAC = sys.platform == "darwin"
WINDOWS = sys.platform == "win32"
PROBE_SECONDS = 1
PROBE_TIMEOUT = 20


class Encoder:
    """name: nombre corto; label: para el registro; args: opciones de ffmpeg (codificador y, si hace falta, el
    dispositivo); upload: lo que se agrega al final de los filtros de video para pasar el cuadro al chip."""

    def __init__(self, name, label, args, upload=""):
        self.name, self.label, self.args, self.upload = name, label, list(args), upload

    def __repr__(self):
        return f"Encoder({self.name})"


VIDEOTOOLBOX = Encoder("videotoolbox", "el chip de video de la Mac (VideoToolbox)",
                       ["-c:v", "h264_videotoolbox", "-allow_sw", "1"])
SOFTWARE = Encoder("libx264", "el procesador (libx264)", ["-c:v", "libx264", "-preset", "veryfast"])
NVENC = Encoder("nvenc", "la tarjeta NVIDIA (NVENC)", ["-c:v", "h264_nvenc", "-preset", "p4", "-forced-idr", "1"])
QSV = Encoder("qsv", "el chip de Intel (Quick Sync)", ["-c:v", "h264_qsv", "-preset", "veryfast", "-forced_idr", "1"])


def amf(run=subprocess.run):
    """AMD en Windows. Que cada corte empiece con un cuadro completo («IDR», como NVENC y Quick Sync) se pide solo si
    este ffmpeg lo sabe pedir para AMF (las versiones viejas no)."""
    idr = ["-forced_idr", "1"] if "forced_idr" in encoder_help("h264_amf", run) else []
    return Encoder("amf", "la tarjeta AMD (AMF)", ["-c:v", "h264_amf", "-quality", "balanced", *idr])


def encoder_help(name, run=subprocess.run):
    """Las opciones de un codificador de este ffmpeg (texto), o "" si no se pudo preguntar."""
    try:
        return run(["ffmpeg", "-hide_banner", "-h", f"encoder={name}"], capture_output=True, text=True,
                   timeout=PROBE_TIMEOUT, stdin=subprocess.DEVNULL).stdout or ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def vaapi(device):
    return Encoder("vaapi", f"el chip de video por VAAPI ({device})", ["-vaapi_device", device, "-c:v", "h264_vaapi"],
                   upload=",format=nv12,hwupload")


CHOICES = ("auto", "nvenc", "qsv", "amf", "vaapi", "libx264")
_current = None


def current():
    """El codificador elegido al arrancar; antes de eso (las pruebas), el de siempre del sistema, sin probar nada."""
    return _current or (VIDEOTOOLBOX if MAC else SOFTWARE)


def probe_command(enc):
    """Un segundo de video de prueba, comprimido con las mismas opciones que una conversión de verdad
    (mac/transcode.py, FullPlan) y tirado a la basura."""
    return ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error",
            "-f", "lavfi", "-i", f"testsrc2=size=1280x720:rate=30:duration={PROBE_SECONDS}",
            "-vf", "format=yuv420p" + enc.upload, *enc.args, "-profile:v", "high",
            "-b:v", "4M", "-maxrate", "4M", "-bufsize", "12M",
            "-force_key_frames", "expr:gte(t,n_forced*6)", "-f", "null", "-"]


def render_nodes():
    return sorted(glob.glob("/dev/dri/renderD*"))


def candidates(known, run=subprocess.run):
    """Los chips que vale la pena probar, en orden. known: los codificadores que trae este ffmpeg."""
    out = []
    if "h264_nvenc" in known:
        out.append(NVENC)
    if "h264_qsv" in known:
        out.append(QSV)
    if WINDOWS and "h264_amf" in known:
        out.append(amf(run))
    if "h264_vaapi" in known:
        out += [vaapi(node) for node in render_nodes()]
    return out


def ffmpeg_encoders(run=subprocess.run):
    try:
        out = run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=PROBE_TIMEOUT,
                  stdin=subprocess.DEVNULL).stdout
    except (OSError, subprocess.TimeoutExpired):
        return set()
    return {m.group(1) for m in re.finditer(r"^\s*V\S*\s+(\S+)", out or "", re.M)}


def works(enc, run=subprocess.run):
    try:
        r = run(probe_command(enc), capture_output=True, text=True, timeout=PROBE_TIMEOUT, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0


def detect(choice="auto", log=print, run=subprocess.run):
    """Elige el codificador (ver arriba), lo dice en el registro y lo deja para current()."""
    global _current
    if MAC:
        _current = VIDEOTOOLBOX
        return _current
    choice = (choice or "auto").strip().lower()
    if choice not in CHOICES:
        log(f"⚠ «codificador» en config.json debe ser uno de: {', '.join(CHOICES)}. Uso «auto».")
        choice = "auto"
    if choice == "libx264":
        _current = SOFTWARE
        log("✓ Video: se convierte con el procesador (libx264), como pide config.json")
        return _current
    known = ffmpeg_encoders(run)
    tried = [e for e in candidates(known, run) if choice == "auto" or e.name == choice]
    for enc in tried:
        if works(enc, run):
            _current = enc
            log(f"✓ Video: se convierte con {enc.label}")
            return _current
    _current = SOFTWARE
    if choice != "auto":
        log(f"⚠ Video: «{choice}» (config.json) no funcionó en esta computadora; se convierte con el procesador "
            "(libx264)")
    elif tried:
        log("· Video: no hay chip de video que funcione (se probó " + ", ".join(e.name for e in tried) + "); se "
            "convierte con el procesador (libx264)")
    else:
        log("· Video: no hay chip de video que ffmpeg pueda usar; se convierte con el procesador (libx264)")
    nodes = [n for n in render_nodes() if not os.access(n, os.R_OK | os.W_OK)]
    if nodes:
        log(f"  (hay chip de video en {nodes[0]}, pero tu usuario no tiene permiso: "
            "sudo usermod -aG render,video $USER  y reinicia la computadora)")
    return _current


@functools.lru_cache(maxsize=1)
def _ffmpeg_help():
    try:
        return subprocess.run(["ffmpeg", "-hide_banner", "-h", "full"], capture_output=True, text=True, timeout=30,
                              stdin=subprocess.DEVNULL).stdout or ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def ffmpeg_knows(option):
    """¿Este ffmpeg conoce la opción? (sin «-»). Si no se pudo preguntar, se supone que sí (como antes)."""
    text = _ffmpeg_help()
    return not text or re.search(rf"^\s*-{re.escape(option)}\b", text, re.M) is not None
