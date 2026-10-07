"""Varios videos a la vez en la TV: la computadora arma un solo video con todos juntos («mosaico»).

Un Roku solo reproduce un video a la vez (probado en un Streaming Stick: el segundo da error -5), así que la
computadora junta de 2 a 4 fuentes (canales en vivo, YouTube, películas y episodios) en un solo HLS de 1080p
con ffmpeg y el chip de video, y deja el audio de cada fuente como una pista aparte. Para la TV es un video
normal: cambiar cuál suena es cambiar de pista de audio, sin reiniciar nada.

- Las fuentes en vivo y de YouTube se leen por las rutas del propio servidor (/live/…, /yt/…), que ya
  resuelven los encabezados, las direcciones atadas a la IP y el «disfraz» de los trozos. Las películas y los
  episodios, directo del archivo.
- De cada lista maestra se toma la variante más chica que llena una celda (≥540 de alto): menos red y menos
  trabajo para decodificar lo que de todos modos se va a achicar.
- La salida es en vivo (lista deslizante de trozos de 2 s). El audio va de una de dos formas: «alt» (pistas
  EXT-X-MEDIA, una lista por pista; por omisión) o «ts» (todas las pistas dentro de cada trozo).
- Camino por el chip obligatorio (componer en el procesador calienta la Mac sin ventilador): si el chip
  falla se reintenta decodificando en el chip pero achicando en el procesador y, solo como último recurso,
  todo en el procesador (libx264), y se anota en el registro.
- Un solo mosaico a la vez; se detiene solo si nadie lo pide en 30 s. Si ffmpeg muere o una fuente se cae,
  queda con un error legible y se puede rearmar con la misma receta (status da sources/layout/audio).
"""

import re
import secrets
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from transcode import GPU_FORMATS

CELL_W, CELL_H = 960, 540          # cada fuente ocupa un cuarto del cuadro de 1080p
FRAME_W, FRAME_H = 1920, 1080
FPS = 30
SEG = 2                            # segundos por trozo: el cambio de pista y el retraso en vivo dependen de esto
LIST_SIZE = 10                     # trozos en la lista deslizante
MIN_SOURCES, MAX_SOURCES = 2, 4
IDLE_STOP = 30                     # sin peticiones (archivos o estado) en 30 s: se detiene, como transcode
START_MAX = 60                     # ffmpeg corriendo sin dar el primer trozo en 60 s: algo se trabó
STALL = 30                         # ya andaba y lleva 30 s sin trozos nuevos: una fuente dejó de mandar video
READY_SEGMENTS = 2                 # con 2 trozos (4 s) el reproductor arranca sin quedarse esperando
# Con un canal en vivo el video sale a ráfagas: el canal publica trozos de ~6 s y ffmpeg arma de golpe lo que llega
# (medido en la TV el 30 sep 2026: huecos de hasta 7 s y la TV se quedaba cargando 13 s). Por eso, si hay un en
# vivo, las listas que ven la TV y la web no enseñan los trozos más nuevos: el reproductor va 6 s más atrás y las
# ráfagas no lo alcanzan. Cuesta esos mismos segundos al arrancar.
HOLD_BACK = 3
WAIT_PLAYLIST = 20                 # una lista que aún no existe se espera hasta 20 s (el arranque tarda)
FETCH_TIMEOUT = 60                 # un canal en vivo caducado se vuelve a buscar con Chrome (hasta 45 s)
RW_TIMEOUT = 20_000_000            # µs: una conexión colgada con el servidor cuenta como caída
# Idiomas distintos por pista para que los reproductores las listen por separado (no dicen el idioma real).
LANGS = ("spa", "eng", "fra", "por")
LAYOUTS = ("lado",)
AUDIO_MODES = ("alt", "ts")
TIERS = ("chip", "chip-simple", "procesador")
TIER_LABEL = {"chip": "con el chip de video",
              "chip-simple": "decodificando con el chip y achicando con el procesador",
              "procesador": "todo con el procesador (libx264)"}
KINDS = ("live", "yt", "item")
IDS = {"yt": re.compile(r"^[\w-]{11}$"),          # como youtube.VIDEO_ID
       "live": re.compile(r"^[0-9a-f]{10}$"),     # sha1 del enlace, 10 letras (live.LiveChannels.add)
       "item": re.compile(r"^[0-9a-f]{12}$")}     # sha1 de la ruta, 12 letras (library.Library)
MOSAIC_ID = re.compile(r"^[0-9a-f]{8}$")
# Arrancar rápido: ffmpeg abre las entradas una por una y, con lo que trae por omisión (5 s / 5 MB de análisis
# por entrada), el primer trozo tardaba 7–9 s con YouTube. Con un trozo de cada lista le basta.
PROBE = ["-probesize", "1000000", "-analyzeduration", "1500000"]
# Lo que se lee a tiempo real (-re) arranca con 4 s de golpe (ffmpeg trae 0,5): el primer trozo sale ~1 s antes
# (medido con dos YouTube: 6,6 → 5,6 s desde que arranca ffmpeg). Abrir cada entrada cuesta ~1 s y no se
# acorta con menos análisis: ffmpeg las abre una tras otra y pide dos trozos de cada una.
READ_BURST = 4
# Con un canal en vivo la TV necesita 5 trozos (READY_SEGMENTS + HOLD_BACK) para arrancar: a 4 s de golpe y luego a
# tiempo real eran 6 s más de espera. El canal ya trae ~12 s listos (empieza 2 trozos de 6 s antes del final), así que
# lo demás también puede entrar de golpe 12 s y los 5 trozos salen apenas abren las fuentes.
LIVE_BURST = 12
# Lo que se pide de antemano de cada fuente (mac/segcache.py): los 2 primeros trozos (ffmpeg los lee para reconocer el
# video) y los que cubren estos segundos desde donde empieza; de un canal en vivo, los 3 últimos.
WARM_SECONDS = 15
# Un canal en vivo empieza este número de trozos antes del final (ffmpeg: -live_start_index). Con -2 los primeros 4
# trozos salían enseguida y el 5.º (la TV necesita 5 con un en vivo) esperaba a que el canal publicara el siguiente:
# hasta 6 s más según en qué parte de su ciclo se arrancaba (medido el 30 sep 2026, noche). Con -3 hay ~18 s listos y
# los 5 salen en ~4 s. Antes de pedir los trozos de antemano, -3 hacía que se le caducaran (abrir tardaba 8 s).
LIVE_START = -3
# Desde la TV, lo que se veía sigue en pantalla mientras se arma el mosaico (advance): sus videos empiezan lo que tardó
# en prepararse más esto (lo que suele tardar ffmpeg en dar los primeros trozos y la TV en arrancar), para que al
# pasar al mosaico no se repita lo que ya se vio.
ADVANCE_EXTRA = 2
# Tras una pausa (la descarga de un trozo de YouTube tarda), ffmpeg vuelve a tiempo real a 1,05× y no alcanzaba nunca:
# el mosaico con un en vivo salía a 0,72× y la TV se quedaba sin video. A 3× se pone al día enseguida.
CATCH_UP = ["-readrate_catchup", "3"]
ACTIVE = ("preparando", "armando", "listo")


class MosaicError(Exception):
    """Motivo para mostrar tal cual (en español); `detail` (técnico) solo va al registro."""

    def __init__(self, message, detail=""):
        super().__init__(message)
        self.detail = detail


# ---------------------------------------------------------------- lo que llega por la API

def _parse_audio(value, n):
    """Pista de una película como en transcode: índice del archivo (3 o «a3»), pista aparte («x0») o «na»."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise MosaicError(f"El video {n} tiene una pista de audio inválida.")
    if isinstance(value, int) and value >= 0:
        return value
    if isinstance(value, str):
        if re.fullmatch(r"a?\d{1,3}", value):
            return int(value.lstrip("a"))
        if re.fullmatch(r"x\d{1,2}|na", value):
            return value
    raise MosaicError(f"El video {n} tiene una pista de audio inválida.")


def parse_request(body):
    """Revisa un pedido {sources, layout?, audio?, focus?}. -> (fuentes, layout, audio, focus).
    Cada fuente: {kind, id, audio, start}. Lanza MosaicError con el motivo."""
    if not isinstance(body, dict):
        raise MosaicError("Datos inválidos.")
    sources = body.get("sources")
    if not isinstance(sources, list) or not MIN_SOURCES <= len(sources) <= MAX_SOURCES:
        raise MosaicError(f"Elige de {MIN_SOURCES} a {MAX_SOURCES} videos.")
    out, seen = [], set()
    for n, s in enumerate(sources, 1):
        if not isinstance(s, dict):
            raise MosaicError(f"El video {n} no es válido.")
        kind, sid = s.get("kind"), s.get("id")
        if kind not in KINDS:
            raise MosaicError(f"El video {n} es de un tipo desconocido (live, yt o item).")
        if not isinstance(sid, str) or not IDS[kind].match(sid):
            raise MosaicError(f"El video {n} no tiene un id válido.")
        if (kind, sid) in seen:
            raise MosaicError(f"El video {n} está repetido.")
        seen.add((kind, sid))
        audio, start = None, None
        if kind == "item":
            audio = _parse_audio(s.get("audio"), n)
        elif s.get("audio") not in (None, ""):
            raise MosaicError(f"El video {n}: la pista de audio solo se elige en películas y episodios.")
        if kind == "live":
            if s.get("start") not in (None, 0):
                raise MosaicError(f"El video {n}: un canal en vivo no se puede empezar en otro punto.")
        else:
            # Películas, episodios y YouTube pueden empezar donde se iban viendo (segundos).
            start = s.get("start")
            if start is not None and (isinstance(start, bool) or not isinstance(start, (int, float)) or start < 0):
                raise MosaicError(f"El video {n} tiene un inicio inválido.")
        out.append({"kind": kind, "id": sid, "audio": audio, "start": float(start) if start else None})
    layout = body.get("layout") or "lado"
    if layout not in LAYOUTS:
        raise MosaicError("Por ahora la única distribución es «lado» (lado a lado; con 3 o 4, en cuadrícula).")
    audio = body.get("audio") or "alt"
    if audio not in AUDIO_MODES:
        raise MosaicError("El modo de audio debe ser «alt» o «ts».")
    focus = body.get("focus")
    if focus is None:
        focus = 0
    if isinstance(focus, bool) or not isinstance(focus, int) or not 0 <= focus < len(out):
        raise MosaicError("«focus» debe ser la posición de uno de los videos (0, 1…).")
    return out, layout, audio, focus


def item_source(item, audio=None, start=None):
    """Completa una fuente de la biblioteca con lo que ffmpeg necesita: archivo, video y la pista elegida
    (None = la marcada por omisión en el archivo, o la primera). Lanza MosaicError si algo no cuadra."""
    title = item.get("full_title") or item.get("title") or "Video"
    video = item["info"].get("video")
    if not video:
        raise MosaicError(f"«{title}» no tiene video.")
    tracks = item["info"].get("audio") or []
    if audio == "na" or not tracks:
        track = None
    elif audio is None:
        track = next((a for a in tracks if a.get("default")), tracks[0])
    else:
        track = next((a for a in tracks if a["index"] == audio), None)
        if track is None:
            raise MosaicError(f"«{title}» no tiene esa pista de audio.")
    duration = item.get("duration") or 0
    if start and duration and start >= duration - 5:
        raise MosaicError(f"«{title}» dura menos que ese inicio.")
    return {"kind": "item", "id": item["id"], "title": title, "path": item["path"], "video": video,
            "audio_index": None if track is None else track["index"], "audio_file": (track or {}).get("file"),
            "channels": (track or {}).get("channels") or 2, "start": start or 0.0, "duration": duration,
            "audio": audio}


# ---------------------------------------------------------------- listas HLS

def _attrs(line):
    """Atributos de una etiqueta HLS (#EXT-X-…:A=1,B="x,y") como diccionario, sin comillas."""
    body = line.split(":", 1)[1] if ":" in line else ""
    return {k: v[1:-1] if v.startswith('"') else v for k, v in re.findall(r'([A-Z0-9-]+)=("[^"]*"|[^,]*)', body)}


def _size(attrs):
    m = re.match(r"(\d+)x(\d+)", attrs.get("RESOLUTION", ""))
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def pick_variant(text, url):
    """De una lista maestra, la variante H.264 más chica que llena una celda (≥540 de alto) y su pista de
    audio (la marcada DEFAULT o la primera del grupo). Si no es maestra, la lista misma.
    -> {"video", "audio" (None si va dentro del video), "width", "height", "codecs"}."""
    lines = [l.strip() for l in text.splitlines()]
    variants, media = [], []
    for n, line in enumerate(lines):
        if line.startswith("#EXT-X-STREAM-INF:"):
            uri = next((l for l in lines[n + 1:] if l and not l.startswith("#")), None)
            if uri:
                variants.append((_attrs(line), uri))
        elif line.startswith("#EXT-X-MEDIA:"):
            media.append(_attrs(line))
    if not variants:
        return {"video": url, "audio": None, "width": 0, "height": 0, "codecs": ""}
    usable = [v for v in variants if "avc1" in v[0].get("CODECS", "avc1")] or variants

    def bandwidth(v):
        return int(v[0].get("BANDWIDTH") or 0)
    big = [v for v in usable if _size(v[0])[1] >= CELL_H]
    if big:
        attrs, uri = min(big, key=lambda v: (_size(v[0])[1], bandwidth(v)))
    else:
        attrs, uri = max(usable, key=lambda v: (_size(v[0])[1], bandwidth(v)))
    audio = None
    group = attrs.get("AUDIO")
    if group:
        options = [m for m in media if m.get("TYPE") == "AUDIO" and m.get("GROUP-ID") == group and m.get("URI")]
        chosen = next((m for m in options if m.get("DEFAULT") == "YES"), options[0] if options else None)
        audio = urllib.parse.urljoin(url, chosen["URI"]) if chosen else None
    w, h = _size(attrs)
    return {"video": urllib.parse.urljoin(url, uri), "audio": audio, "width": w, "height": h,
            "codecs": attrs.get("CODECS", "")}


def _clean_name(title, n):
    """Un NAME de HLS no puede llevar comillas ni saltos de línea."""
    name = re.sub(r'["\r\n]+', "'", title or "").strip()
    return name or f"Video {n + 1}"


def hold_back(playlist, n):
    """Una lista de medios sin sus n trozos más nuevos (ver HOLD_BACK). Si ya terminó (#EXT-X-ENDLIST) o tiene pocos
    trozos, tal cual."""
    lines = playlist.splitlines()
    if any(l.startswith("#EXT-X-ENDLIST") for l in lines):
        return playlist
    uris = [i for i, l in enumerate(lines) if l and not l.startswith("#")]
    if len(uris) <= n + 1:
        return playlist
    return "\n".join(lines[:uris[-n - 1] + 1]) + "\n"


def master_text(ff_master, titles, focus=0):
    """La lista maestra de ffmpeg con el título de cada fuente como nombre de su pista, idiomas distintos y
    solo la pista con el foco marcada DEFAULT/AUTOSELECT (Safari elige por el idioma del sistema si puede)."""
    out = []
    for line in ff_master.splitlines():
        m = re.search(r'URI="a(\d+)/', line) if line.startswith("#EXT-X-MEDIA:") and "TYPE=AUDIO" in line else None
        if m and int(m.group(1)) < len(titles):
            n, a = int(m.group(1)), _attrs(line)
            on = "YES" if n == focus else "NO"
            parts = ["TYPE=AUDIO", f'GROUP-ID="{a.get("GROUP-ID", "group_aud")}"', f'NAME="{_clean_name(titles[n], n)}"',
                     f'LANGUAGE="{LANGS[n]}"', f"DEFAULT={on}", f"AUTOSELECT={on}", f'URI="{a["URI"]}"']
            if a.get("CHANNELS"):
                parts.append(f'CHANNELS="{a["CHANNELS"]}"')
            line = "#EXT-X-MEDIA:" + ",".join(parts)
        out.append(line)
    return "\n".join(out) + "\n"


def segment_count(path):
    """Cuántos trozos lleva escritos una lista en vivo (secuencia inicial + los que lista)."""
    try:
        text = Path(path).read_text()
    except OSError:
        return 0
    seq = re.search(r"#EXT-X-MEDIA-SEQUENCE:(\d+)", text)
    return (int(seq.group(1)) if seq else 0) + text.count("#EXTINF")


def first_segments(text, url, live=False, start=0):
    """Los trozos que ffmpeg lee primero de una lista de medios (direcciones completas, sin repetir): de un canal en
    vivo los 3 últimos (empieza 2 antes del final); si no, los 2 primeros (con ellos reconoce el video aunque
    después salte) y los que cubren WARM_SECONDS desde `start`."""
    segs, dur = [], 0.0
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#EXTINF:"):
            try:
                dur = float(line[8:].split(",")[0])
            except ValueError:
                dur = 0.0
        elif line and not line.startswith("#"):
            segs.append((urllib.parse.urljoin(url, line), dur))
            dur = 0.0
    if live:
        return [u for u, _ in segs[-3:]]
    picked, elapsed, covered = [0, 1], 0.0, 0.0
    for i, (_, d) in enumerate(segs):
        if elapsed + d > (start or 0) or i == len(segs) - 1:
            while i < len(segs) and covered < WARM_SECONDS:
                picked.append(i)
                covered += segs[i][1] or SEG
                i += 1
            break
        elapsed += d
    out = []
    for i in picked:
        if i < len(segs) and segs[i][0] not in out:
            out.append(segs[i][0])
    return out


def prefetch_url(url):
    """Pide un trozo al propio servidor para que lo deje listo (mac/segcache.py); la respuesta se descarta."""
    try:
        req = urllib.request.Request(url, headers={"X-Prefetch": "1"})
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as r:
            r.read()
    except (urllib.error.URLError, OSError, ValueError):
        pass   # si falla, ffmpeg lo pide igual


# ---------------------------------------------------------------- el comando de ffmpeg

def fit(w, h, cw=CELL_W, ch=CELL_H):
    """Tamaño dentro de la celda sin deformar (números pares); lo que sobra queda en negro."""
    if not w or not h:
        return cw, ch
    if w * ch >= h * cw:
        return cw, min(ch, max(2, round(cw * h / w / 2) * 2))
    return min(cw, max(2, round(ch * w / h / 2) * 2)), ch


def _hw(src, tier):
    """Cómo se decodifica una fuente: «vld» (decodifica y achica en el chip), «auto» (decodifica en el chip y
    el cuadro pasa a memoria) o None (procesador). Igual que transcode.FullPlan."""
    codec, pix = src.get("codec") or "h264", src.get("pix_fmt") or "yuv420p"
    if tier == "procesador":
        return None
    if tier == "chip" and (codec, pix) in GPU_FORMATS:
        return "vld"
    return "auto" if codec in ("h264", "hevc") else None


def _input(src, target, tier, video, burst=READ_BURST):
    args = []
    paced = ["-re", "-readrate_initial_burst", str(burst), *CATCH_UP]
    hw = _hw(src, tier) if video else None
    if hw:
        args += ["-hwaccel", "videotoolbox"]
    if hw == "vld":
        args += ["-hwaccel_output_format", "videotoolbox_vld"]
    if src["local"]:
        # Un archivo se lee a tiempo real (-re); si no, ffmpeg lo terminaría en segundos y la lista deslizante
        # se saltaría todo.
        args += paced
        if src.get("start"):
            args += ["-ss", f"{src['start']:.3f}"]
            if hw == "vld":
                # El salto exacto mete un filtro «trim» que no acepta cuadros del chip: con otra entrada lenta
                # (YouTube) ffmpeg no logra armar los filtros y muere (visto con Shrek + YouTube). Así arranca en el
                # fotograma clave anterior; ffmpeg conserva los tiempos respecto del salto, y el audio aparte
                # (doblaje) sigue a tiempo.
                args.append("-noaccurate_seek")
    else:
        # Por el propio servidor. extension_picky: el servidor nombra .ts trozos que a veces son MP4.
        # http_multiple: pide el trozo siguiente mientras lee el actual (el servidor no deja la conexión abierta,
        # así que ffmpeg no lo activa solo y cada trozo esperaba su descarga).
        args += ["-extension_picky", "0", "-seg_max_retry", "3", "-rw_timeout", str(RW_TIMEOUT), "-http_multiple", "1",
                 *PROBE]
        if src["live"]:
            # Un en vivo ya llega a tiempo real (la investigación lo leyó sin -re); si deja de dar trozos nuevos,
            # ffmpeg se rinde en ~8 recargas en vez de las 1000 de siempre. Dónde empieza: ver LIVE_START.
            args += ["-m3u8_hold_counters", "8", "-live_start_index", str(LIVE_START)]
        else:
            args += paced   # YouTube normal es una lista completa: sin -re se leería de golpe
            if src.get("start"):
                # Empieza donde se iba viendo: la lista de YouTube es completa, así que ffmpeg salta al trozo de ese
                # segundo (lo pide directo, sin bajar lo anterior) y -re cuenta el tiempo real desde ahí. Video y audio
                # aparte llevan el mismo salto. Con cuadros del chip, sin el salto exacto (ver arriba).
                args += ["-ss", f"{src['start']:.3f}"]
                if hw == "vld":
                    args.append("-noaccurate_seek")
    return args + ["-i", target]


def build_command(plan, audio_mode, outdir, tier="chip", focus=0, layout="lado"):
    """Comando de ffmpeg para el mosaico. plan: una entrada por fuente con
    {local, live, video, audio (entrada aparte o None), vsel, asel (None = sin audio), width, height,
    codec, pix_fmt, channels, start}."""
    outdir = Path(outdir)
    n = len(plan)
    cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "warning", "-y"]
    graph, cells = [], []
    count = 0
    burst = LIVE_BURST if any(src.get("live") for src in plan) else READ_BURST
    for i, src in enumerate(plan):
        vi = count
        cmd += _input(src, src["video"], tier, video=True, burst=burst)
        count += 1
        ai = vi
        if src.get("audio"):
            ai = count
            cmd += _input(src, src["audio"], tier, video=False, burst=burst)
            count += 1
        fw, fh = fit(src.get("width"), src.get("height"))
        if _hw(src, tier) == "vld":
            # Se achica en el chip y solo baja a memoria el cuadro chico; los de 10 bits se pasan a 8.
            ten = "10" in (src.get("pix_fmt") or "")
            chain = f"scale_vt=w={fw}:h={fh},hwdownload," + ("format=p010le,format=nv12" if ten else "format=nv12")
        else:
            chain = f"scale={fw}:{fh},format=nv12"
        if (fw, fh) != (CELL_W, CELL_H):
            chain += f",pad={CELL_W}:{CELL_H}:(ow-iw)/2:(oh-ih)/2"
        graph.append(f"[{vi}:{src['vsel']}]{chain},setsar=1[c{i}]")
        cells.append(f"[c{i}]")
        if src.get("asel") is None:
            graph.append(f"anullsrc=r=48000:cl=stereo[a{i}]")   # sin audio: su pista va en silencio
        else:
            achain = "aresample=48000,aformat=channel_layouts=stereo"
            if (src.get("channels") or 2) > 2:
                achain += ",volume=1.6,alimiter=limit=0.97"   # de 5.1 a estéreo los diálogos quedan bajos
            graph.append(f"[{ai}:{src['asel']}]{achain}[a{i}]")
    # shortest=1: termina con la primera fuente que se acaba (un video de YouTube, una película).
    if n == 2:
        stack = f"hstack=inputs=2:shortest=1,pad={FRAME_W}:{FRAME_H}:0:{(FRAME_H - CELL_H) // 2}"
    elif n == 3:
        stack = f"xstack=inputs=3:layout=0_0|{CELL_W}_0|{CELL_W // 2}_{CELL_H}:fill=black:shortest=1"
    else:
        stack = f"xstack=inputs=4:layout=0_0|{CELL_W}_0|0_{CELL_H}|{CELL_W}_{CELL_H}:shortest=1"
    graph.append("".join(cells) + stack + f",fps={FPS}" + (",format=yuv420p" if tier == "procesador" else "") + "[v]")
    cmd += ["-filter_complex", ";".join(graph), "-map", "[v]"]
    for i in range(n):
        cmd += ["-map", f"[a{i}]"]
    if tier == "procesador":
        cmd += ["-c:v", "libx264", "-preset", "veryfast"]
    else:
        cmd += ["-c:v", "h264_videotoolbox"]
    cmd += ["-b:v", "6M", "-maxrate", "6M", "-bufsize", "12M", "-profile:v", "high",
            "-force_key_frames", f"expr:gte(t,n_forced*{SEG})",
            "-c:a", "aac", "-ac", "2", "-ar", "48000", "-b:a", "128k",
            "-shortest", "-max_muxing_queue_size", "4096",
            "-f", "hls", "-hls_time", str(SEG), "-hls_list_size", str(LIST_SIZE),
            "-hls_flags", "delete_segments+independent_segments+temp_file", "-hls_segment_type", "mpegts"]
    if audio_mode == "alt":
        streams = ["v:0,agroup:aud,name:video"] + [
            f"a:{i},agroup:aud,name:a{i},language:{LANGS[i]}" + (",default:yes" if i == focus else "") for i in range(n)]
        cmd += ["-var_stream_map", " ".join(streams), "-master_pl_name", "ff_master.m3u8",
                "-hls_segment_filename", str(outdir / "%v" / "seg%d.ts"), str(outdir / "%v" / "index.m3u8")]
    else:
        for i in range(n):
            cmd += [f"-metadata:s:a:{i}", f"language={LANGS[i]}", f"-disposition:a:{i}", "default" if i == focus else "0"]
        cmd += ["-hls_segment_filename", str(outdir / "seg%d.ts"), str(outdir / "index.m3u8")]
    return cmd


# ---------------------------------------------------------------- una sesión

def fetch_text(url, timeout=FETCH_TIMEOUT):
    """Lista del propio servidor. Si falla, el servidor manda el motivo en el cuerpo (502): se usa tal cual."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        with e:
            reason = e.read().decode("utf-8", "replace").strip()
        raise MosaicError(reason if reason and reason != "no encontrado" else f"la computadora contestó {e.code}",
                          f"{url}: HTTP {e.code}") from e
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise MosaicError("la computadora no la pudo leer", f"{url}: {e}") from e


def _youtube_start(s):
    """El inicio de un video de YouTube, revisado contra su duración: una transmisión en vivo (sin duración) no se
    puede saltar, y uno que ya casi termina (como en item_source, a menos de 5 s del final) empieza desde el principio
    para no cerrar el mosaico al instante. Lo que queda es lo que dice la receta (status), así «ver solo este» cuadra."""
    if s.get("kind") != "yt" or not s.get("start"):
        return s
    duration = s.get("duration") or 0
    if not duration or s["start"] >= duration - 5:
        return {**s, "start": None}
    return s


class Mosaic:
    popen = staticmethod(subprocess.Popen)   # las pruebas lo cambian por un proceso falso

    def __init__(self, mid, sources, outdir, base_url, layout="lado", audio="alt", focus=0,
                 log=print, clock=time.time, fetch=fetch_text, prefetch=prefetch_url, advance=False):
        self.id = mid
        self.sources = [_youtube_start(dict(s)) for s in sources]   # copias: advance cambia el inicio
        self.prefetch = prefetch
        self.advance = advance   # lo de antes sigue en pantalla mientras se arma: ver ADVANCE_EXTRA
        self.held_back = any(src.get("kind") == "live" for src in sources)   # ver HOLD_BACK
        self.dir = Path(outdir)
        self.base = base_url.rstrip("/")
        self.layout, self.audio, self.focus = layout, audio, focus
        self.log, self.clock, self.fetch = log, clock, fetch
        self.lock = threading.RLock()
        self.state = "preparando"   # → armando → listo → (terminado | detenido | error)
        self.error = ""
        self.note = ""
        self.tier = 0
        self.plan = None
        self.proc = None
        self.created = self.last_seen = clock()
        self.launched = None
        self.first_segment = None   # segundos desde que se pidió hasta el primer trozo
        self.last_count = 0
        self.last_growth = None
        self.stalled = False
        self.dir.mkdir(parents=True, exist_ok=True)

    # ---------- datos ----------

    @property
    def url(self):
        return f"/mosaic/{self.id}/" + ("master.m3u8" if self.audio == "alt" else "index.m3u8")

    @property
    def tracks(self):
        return [s["title"] for s in self.sources]

    def _video_playlist(self):
        return self.dir / ("video" if self.audio == "alt" else "") / "index.m3u8"

    def _outputs_ready(self):
        if self.audio == "ts":
            return True
        return (self.dir / "ff_master.m3u8").exists() and all(
            (self.dir / f"a{i}" / "index.m3u8").exists() for i in range(len(self.sources)))

    def refresh(self, now=None):
        """Cuenta los trozos nuevos y pasa a «listo» cuando ya se puede reproducir."""
        now = self.clock() if now is None else now
        with self.lock:
            if self.state not in ("armando", "listo"):
                return
            count = segment_count(self._video_playlist())
            if count > self.last_count:
                self.last_count, self.last_growth = count, now
                if self.first_segment is None:
                    self.first_segment = round(now - self.created, 1)
            need = READY_SEGMENTS + (HOLD_BACK if self.held_back else 0)   # los que se esconden no cuentan
            if self.state == "armando" and count >= need and self._outputs_ready():
                self.state = "listo"
                self.log(f"✓ Mosaico {self.id} listo en {now - self.created:.1f} s")

    def status(self):
        self.refresh()
        with self.lock:
            return {"ok": True, "id": self.id, "state": self.state, "ready": self.state == "listo",
                    "error": self.error, "ended": self.state == "terminado", "note": self.note,
                    "url": self.url, "layout": self.layout, "audio": self.audio, "focus": self.focus,
                    "tier": TIERS[self.tier], "first_segment_s": self.first_segment,
                    "tracks": self.tracks,
                    # la receta: se puede mandar tal cual a /api/mosaic/start para rearmarlo
                    "sources": [{"kind": s["kind"], "id": s["id"], "title": s["title"], "audio": s.get("audio"),
                                 "start": s.get("start") or None} for s in self.sources]}

    def touch(self):
        with self.lock:
            self.last_seen = self.clock()

    # ---------- arrancar ----------

    def begin(self):
        threading.Thread(target=self._prepare_and_launch, daemon=True).start()

    def _prepare_and_launch(self):
        try:
            plan = self.prepare()
        except MosaicError as e:
            return self._fail(str(e), e.detail)
        with self.lock:
            if self.state != "preparando":
                return   # lo detuvieron (o lo reemplazaron) mientras se preparaba
            if self.advance:
                self._shift_starts(plan, self.clock() - self.created + ADVANCE_EXTRA)
            self.plan = plan
            self._launch()

    def _shift_starts(self, plan, secs):
        """Las películas y los videos de YouTube empiezan `secs` más adelante (siguieron avanzando en la TV mientras
        se armaba). Si así ya se acabarían, empiezan donde se pidió. La receta (status) dice el inicio de verdad."""
        for s, p in zip(self.sources, plan):
            if s["kind"] == "live" or p.get("live"):
                continue
            duration = s.get("duration") or 0
            start = (s.get("start") or 0) + secs
            if duration and start >= duration - 5:
                continue
            s["start"] = p["start"] = round(start, 1)

    def prepare(self):
        """Una entrada de ffmpeg por fuente. YouTube y en vivo se piden en paralelo (cada uno tarda)."""
        plan, errors = [None] * len(self.sources), [None] * len(self.sources)

        def one(n, s):
            try:
                plan[n] = self._prepare_source(s)
            except MosaicError as e:
                errors[n] = e
        threads = [threading.Thread(target=one, args=(n, s), daemon=True) for n, s in enumerate(self.sources)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        for s, e in zip(self.sources, errors):
            if e:
                raise MosaicError(f"No se pudo abrir «{s['title']}»: {e}", e.detail)
        return plan

    def _prepare_source(self, s):
        if s["kind"] == "item":
            v = s["video"]
            separate = bool(s.get("audio_file"))
            return {"local": True, "live": False, "video": s["path"], "vsel": str(v["index"]),
                    "audio": s["audio_file"] if separate else None,
                    "asel": None if s.get("audio_index") is None else ("a:0" if separate else str(s["audio_index"])),
                    "width": v.get("width"), "height": v.get("height"), "codec": v.get("codec"),
                    "pix_fmt": v.get("pix_fmt"), "channels": s.get("channels") or 2, "start": s.get("start") or 0}
        url = f"{self.base}/{s['kind']}/{s['id']}/index.m3u8"
        var = pick_variant(self.fetch(url), url)
        codecs = var["codecs"]
        codec = "h264" if not codecs or "avc1" in codecs else "hevc" if re.search(r"hvc1|hev1", codecs) else "otro"
        # En vivo: los canales, y YouTube sin duración (una transmisión en vivo).
        live = s["kind"] == "live" or not s.get("duration")
        self._warm(var, live, 0 if live else s.get("start") or 0)
        return {"local": False, "live": live, "video": var["video"], "audio": var["audio"], "vsel": "v:0",
                "asel": "a:0", "width": var["width"], "height": var["height"], "codec": codec,
                "pix_fmt": "yuv420p", "channels": 2, "start": 0 if live else s.get("start") or 0}

    def _warm(self, var, live, start):
        """Pide de antemano, todos a la vez, los trozos que ffmpeg va a leer primero de esta fuente (mac/segcache.py):
        ffmpeg abre las fuentes una tras otra bajando dos trozos de cada una, y eso era lo que más tardaba."""
        urls = []
        for playlist in (var["video"], var["audio"]):
            if not playlist:
                continue
            try:
                urls += first_segments(self.fetch(playlist, timeout=15), playlist, live, start)
            except MosaicError:
                pass   # ffmpeg la pedirá igual y dirá si no está
        for u in urls:
            threading.Thread(target=self.prefetch, args=(u,), daemon=True).start()

    def _launch(self):
        """Arranca ffmpeg en el nivel actual (se llama con el candado tomado)."""
        tier = TIERS[self.tier]
        for f in self.dir.rglob("*"):   # restos de un intento anterior (el registro se queda)
            if f.is_file() and f.name != "ffmpeg.log":
                f.unlink(missing_ok=True)
        if self.audio == "alt":
            for name in ["video"] + [f"a{i}" for i in range(len(self.sources))]:
                (self.dir / name).mkdir(exist_ok=True)
        cmd = build_command(self.plan, self.audio, self.dir, tier, self.focus, self.layout)
        with open(self.dir / "ffmpeg.log", "ab") as log:
            log.write(f"\n== {time.strftime('%H:%M:%S')} {tier}\n".encode())
            log.flush()
            self.proc = self.popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=log)
        self.state = "armando"
        self.launched = self.last_growth = self.clock()
        self.last_count, self.stalled = 0, False
        threading.Thread(target=self._watch, args=(self.proc,), daemon=True).start()
        self.log(f"▶ Mosaico {self.id}: " + " + ".join(f"«{t}»" for t in self.tracks) + f" ({TIER_LABEL[tier]})")

    # ---------- cuando ffmpeg termina ----------

    def _log_tail(self, lines=3):
        try:
            text = (self.dir / "ffmpeg.log").read_text(errors="replace")
        except OSError:
            return ""
        return " | ".join(l.strip() for l in text.strip().splitlines()[-lines:])

    def diagnose(self):
        """¿Se cayó alguna fuente? Se vuelve a pedir su lista al servidor. -> motivo o ""."""
        for s in self.sources:
            if s["kind"] == "item":
                if not Path(s["path"]).exists():
                    return f"Ya no está el archivo de «{s['title']}»."
                continue
            try:
                self.fetch(f"{self.base}/{s['kind']}/{s['id']}/index.m3u8", timeout=20)
            except MosaicError as e:
                return f"Se cayó «{s['title']}»: {e}"
        return ""

    def _watch(self, proc):
        rc = proc.wait()
        with self.lock:
            if proc is not self.proc or self.state not in ("armando", "listo"):
                return   # lo detuvimos nosotros, o ya hay otro ffmpeg
            produced = segment_count(self._video_playlist()) > 0
            stalled = self.stalled
        down = self.diagnose()   # fuera del candado: puede tardar
        with self.lock:
            if proc is not self.proc or self.state not in ("armando", "listo"):
                return
            if down:
                return self._fail(down, self._log_tail())
            if not produced and rc != 0 and not stalled:
                if self.tier + 1 < len(TIERS):
                    nxt = TIERS[self.tier + 1]
                    self.log(f"⚠ Mosaico {self.id}: ffmpeg falló {TIER_LABEL[TIERS[self.tier]]} (código {rc}: "
                             f"{self._log_tail(2)}); se reintenta {TIER_LABEL[nxt]}"
                             + (". Así la computadora trabaja y se calienta mucho más." if nxt == "procesador" else ""))
                    self.tier += 1
                    return self._launch()
                return self._fail("No se pudo armar el mosaico (ffmpeg falló también con el procesador).",
                                  self._log_tail())
            if stalled:
                return self._fail("Una de las fuentes dejó de mandar video y el mosaico se detuvo.", self._log_tail())
            vod = [s for s in self.sources if s["kind"] == "item" or s.get("duration")]
            if rc == 0 and vod:
                # Termina con la primera fuente que se acaba (shortest=1).
                self.state = "terminado"
                self.note = "Terminó " + " o ".join(f"«{s['title']}»" for s in vod) + "."
                self.log(f"■ Mosaico {self.id}: {self.note}")
                return
            return self._fail(f"El mosaico se cortó (ffmpeg terminó con el código {rc}). Se puede volver a armar.",
                              self._log_tail())

    def _fail(self, message, detail=""):
        with self.lock:
            if self.state in ("detenido", "error"):
                return
            self.state, self.error = "error", message
            self._terminate()
        self.log(f"✗ Mosaico {self.id}: {message}" + (f" ({detail})" if detail else ""))

    # ---------- detener ----------

    def _terminate(self):
        proc = self.proc
        if proc is None or proc.poll() is not None:
            return
        proc.terminate()   # ffmpeg cierra la lista con #EXT-X-ENDLIST
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()

    def stop(self, why=""):
        with self.lock:
            was = self.state
            if was in ACTIVE:
                self.state = "detenido"
            self._terminate()
        if was in ACTIVE and why:
            self.log(f"■ Mosaico {self.id}: {why}")
        shutil.rmtree(self.dir, ignore_errors=True)

    def housekeeping(self, now=None):
        now = self.clock() if now is None else now
        with self.lock:
            if self.state not in ACTIVE:
                return
            if now - self.last_seen > IDLE_STOP:
                idle = True
            else:
                idle = False
                self.refresh(now)
                alive = self.proc is not None and self.proc.poll() is None
                limit = STALL if self.state == "listo" else START_MAX
                if alive and self.last_growth is not None and now - self.last_growth > limit:
                    # Una fuente dejó de mandar (o nunca mandó): se corta y _watch dice cuál.
                    self.stalled = True
                    self.proc.terminate()
        if idle:
            self.stop(f"nadie lo pidió en {IDLE_STOP} s; se detiene")

    # ---------- archivos ----------

    def _allowed(self, rel):
        if self.audio == "alt":
            m = re.fullmatch(r"master\.m3u8|(video|a(\d))/(index\.m3u8|seg\d+\.ts)", rel)
            return bool(m) and (m.group(2) is None or int(m.group(2)) < len(self.sources))
        return bool(re.fullmatch(r"index\.m3u8|seg\d+\.ts", rel))

    def file(self, rel, wait=WAIT_PLAYLIST):
        """master.m3u8 -> su texto (bytes); lo demás -> la ruta del archivo; None si no existe. Una lista que aún
        no existe se espera un poco mientras el mosaico arranca (como transcode con los trozos)."""
        if not self._allowed(rel):
            return None
        self.touch()
        target = self.dir / ("ff_master.m3u8" if rel == "master.m3u8" else rel)
        deadline = time.time() + (wait if rel.endswith(".m3u8") else 0)
        while not target.exists() and time.time() < deadline:
            with self.lock:
                if self.state not in ("preparando", "armando"):
                    break
            time.sleep(0.2)
        if rel == "master.m3u8":
            try:
                return master_text(target.read_text(), self.tracks, self.focus).encode()
            except OSError:
                return None
        if rel.endswith(".m3u8") and self.held_back:
            try:
                return hold_back(target.read_text(), HOLD_BACK).encode()
            except OSError:
                return None
        return target if target.exists() else None


# ---------------------------------------------------------------- el mosaico de la casa (uno a la vez)

class Mosaics:
    """Los mosaicos de la casa: uno a la vez, salvo mientras se arma uno nuevo desde la TV con el anterior todavía en
    pantalla (keep): entonces los dos andan hasta que la TV detiene el viejo (o nadie lo pide en IDLE_STOP)."""

    def __init__(self, cache_dir, base_url, log=print, clock=time.time, run=True):
        self.root = Path(cache_dir) / "mosaico"   # junto a hls/ (las sesiones de transcode)
        # Un ffmpeg que quedó vivo si el servidor se cerró a la fuerza: se detiene al volver a arrancar.
        subprocess.run(["pkill", "-TERM", "-f", str(self.root)], capture_output=True)
        shutil.rmtree(self.root, ignore_errors=True)
        self.root.mkdir(parents=True, exist_ok=True)
        self.base = base_url
        self.log, self.clock = log, clock
        self.active = []   # el más nuevo al final; a lo más dos (el de antes y el que se arma)
        self.lock = threading.Lock()
        if run:
            threading.Thread(target=self._loop, daemon=True).start()

    @property
    def current(self):
        with self.lock:
            return self.active[-1] if self.active else None

    def start(self, sources, layout="lado", audio="alt", focus=0, keep=False, advance=False):
        """Arma un mosaico nuevo. Detiene los anteriores; con keep, el último sigue andando (lo que la TV muestra
        mientras se arma este). sources: ya completas (título, archivo…)."""
        mid = secrets.token_hex(4)
        m = Mosaic(mid, sources, self.root / mid, self.base, layout, audio, focus, log=self.log, clock=self.clock,
                   advance=advance)
        with self.lock:
            old = self.active[:-1] if keep else self.active[:]
            self.active = [x for x in self.active if x not in old] + [m]
        for x in old:
            x.stop("se reemplaza por uno nuevo")
        m.begin()
        return m

    def get(self, mid):
        with self.lock:
            return next((m for m in self.active if m.id == mid), None)

    def stop(self, mid):
        m = self.get(mid)
        if m:
            m.stop("se detuvo a pedido")
            self._prune()
        return m is not None

    def _prune(self):
        """Los que ya no andan salen de la lista; el más nuevo se queda para que su estado se pueda leer."""
        with self.lock:
            self.active = [m for m in self.active if m.state in ACTIVE or m is self.active[-1]]

    def housekeeping(self, now=None):
        with self.lock:
            active = list(self.active)
        for m in active:
            m.housekeeping(now)
        self._prune()

    def _loop(self):
        while True:
            time.sleep(2)
            try:
                self.housekeeping()
            except Exception as e:  # noqa: BLE001 - nunca debe tumbar el servidor
                self.log(f"⚠ Mosaico: {e}")

    def shutdown(self):
        with self.lock:
            active, self.active = self.active, []
        for m in active:
            m.stop()
