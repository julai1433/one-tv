"""Servidor HTTP: entrega el catálogo, los videos (directos o convertidos),
portadas y subtítulos al Roku, y la página web para mandar cosas a la tele."""

import json
import re
import shutil
import socket
import socketserver
import subprocess
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import hostos
from apptv import TIPO as TV_APP_TYPE, pagina_sin_app
from live import LiveError, decode_url, rewrite_playlist, unwrap_segment
from mosaic import MOSAIC_ID
from teles import ROKU
from youtube import VIDEO_ID, YouTubeError
from transcode import playlist_text

WEB_DIR = Path(__file__).parent / "web"
# Emojis y símbolos que ninguna letra del Roku trae (flechas, dingbats, banderas, selectores de variante, ZWJ).
EMOJI = re.compile("[\u2190-\u21ff\u2300-\u23ff\u2460-\u27bf\u2900-\u2bff\u200d\ufe00-\ufe0f"
                   "\U0001f000-\U0001faff\U000e0000-\U000e007f]+")
KEEP_AS_IS = ("id", "url", "path", "file", "poster", "thumb", "page", "stream", "src", "uri", "href")


def without_emoji(data, key=""):
    """Copia de la respuesta sin emojis en los textos (títulos, nombres…); ids y direcciones quedan intactos."""
    if isinstance(data, dict):
        return {k: without_emoji(v, k) for k, v in data.items()}
    if isinstance(data, list):
        return [without_emoji(v, key) for v in data]
    if isinstance(data, str) and not (key in KEEP_AS_IS or key.endswith(("_id", "url", "Url"))):
        if not EMOJI.search(data):
            return data
        clean = re.sub(r"\s{2,}", " ", EMOJI.sub("", data)).strip()
        return clean or data   # una lista llamada solo «🐾»: mejor el cuadrito que una tarjeta sin nombre
    return data
CONTENT_TYPES = {".mp4": "video/mp4", ".m4v": "video/mp4", ".mov": "video/quicktime",
                 ".mkv": "video/x-matroska", ".ts": "video/mp2t", ".jpg": "image/jpeg",
                 ".m3u8": "application/vnd.apple.mpegurl", ".srt": "text/plain; charset=utf-8",
                 ".html": "text/html; charset=utf-8", ".png": "image/png",
                 ".webmanifest": "application/manifest+json", ".js": "text/javascript; charset=utf-8",
                 ".vtt": "text/vtt; charset=utf-8", ".woff2": "font/woff2"}


class KeepAwake:
    """Evita que la computadora se duerma mientras se está viendo algo (macOS: caffeinate; Linux: systemd-inhibit;
    Windows: winapi.KeepAwake, que reemplaza a esta clase allá)."""

    def __init__(self):
        self.proc = None
        self.until = 0
        self.lock = threading.Lock()

    def poke(self):
        if not AWAKE_CMD:   # sin caffeinate ni systemd-inhibit: el sistema decide cuándo dormir
            return
        now = time.time()
        with self.lock:
            if self.proc and self.proc.poll() is None and self.until - now > 300:
                return
            if self.proc and self.proc.poll() is None:
                self.proc.terminate()
            elif self.proc and self.proc.returncode > 0:
                return   # el sistema no lo permitió (Linux sin permiso para pedirlo): no se insiste
            self.proc = subprocess.Popen(AWAKE_CMD, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                         stderr=subprocess.DEVNULL)
            self.until = now + 900


AWAKE_CMD = hostos.keep_awake_command(900)
if hostos.WINDOWS:   # sin comando: se le pide a Windows desde un hilo propio (mac/winapi.py)
    from winapi import KeepAwake  # noqa: F811


class Media:
    """Portadas y subtítulos, generados con ffmpeg la primera vez y guardados."""

    def __init__(self, cache_dir):
        self.posters = Path(cache_dir) / "posters"
        self.subs = Path(cache_dir) / "subs"
        self.posters.mkdir(parents=True, exist_ok=True)
        self.subs.mkdir(parents=True, exist_ok=True)
        self.poster_slots = threading.Semaphore(3)
        self.aligned = None   # (video, subtítulo) -> el subtítulo alineado con la voz, o None (mac/subsync.py)
        self.locks = {}
        self.locks_lock = threading.Lock()

    def _lock(self, key):
        with self.locks_lock:
            return self.locks.setdefault(key, threading.Lock())

    def poster(self, item):
        out = self.posters / f"{item['id']}.jpg"
        if out.exists():
            return out
        with self._lock("p" + item["id"]), self.poster_slots:
            if out.exists():
                return out
            v = item["info"]["video"]
            dur = item["duration"] or 600
            at = min(max(dur * 0.12, 20), 900)  # evita logos y negros del principio
            tmp = out.with_suffix(".tmp.jpg")
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                            "-ss", f"{at:.1f}", "-i", item["path"], "-map", f"0:{v['index']}", "-frames:v", "1",
                            "-vf", "scale=480:270:force_original_aspect_ratio=increase,crop=480:270",
                            "-q:v", "4", str(tmp)],
                           stdin=subprocess.DEVNULL, capture_output=True, timeout=60)
            if tmp.exists() and tmp.stat().st_size > 0:
                tmp.replace(out)
                return out
        return None

    def subtitle(self, item, key):
        sub = next((s for s in item["subs"] if s["key"] == key), None)
        if sub is None:
            return None
        if "file" in sub:
            src = (self.aligned(item["path"], sub["file"]) if self.aligned else None) or Path(sub["file"])
            raw = src.read_bytes()
            for enc in ("utf-8-sig", "cp1252", "latin-1"):
                try:
                    text = raw.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue
            if src.suffix.lower() == ".vtt":
                text = vtt_to_srt(text)
            return text.encode("utf-8")
        out = self.subs / f"{item['id']}-{key}.srt"
        if not out.exists():
            with self._lock("s" + item["id"]):
                if not out.exists():
                    self._extract_embedded(item)
        return out.read_bytes() if out.exists() else None

    def _extract_embedded(self, item):
        """Saca de una pasada todas las pistas de texto del archivo (leerlo entero cuesta)."""
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i", item["path"]]
        outs = []
        for s in item["subs"]:
            if "stream" in s:
                tmp = self.subs / f"{item['id']}-{s['key']}.tmp.srt"
                cmd += ["-map", f"0:{s['stream']}", "-c:s", "srt", str(tmp)]
                outs.append(tmp)
        if not outs:
            return
        subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, timeout=600)
        for tmp in outs:
            if tmp.exists():
                tmp.replace(tmp.with_name(tmp.name.replace(".tmp.srt", ".srt")))


def srt_to_vtt(data):
    text = data.decode("utf-8", "replace").replace("\r", "")
    text = re.sub(r"(\d\d:\d\d:\d\d),(\d\d\d)", r"\1.\2", text)
    return ("WEBVTT\n\n" + text).encode("utf-8")


def vtt_to_srt(text):
    blocks, n = [], 0
    for block in re.split(r"\n\s*\n", text.replace("\r", "")):
        lines = [l for l in block.split("\n") if l.strip()]
        idx = next((i for i, l in enumerate(lines) if "-->" in l), None)
        if idx is None:
            continue
        n += 1
        times = re.sub(r"(\d\d:\d\d)\.(\d\d\d)", r"\1,\2", lines[idx].split(" line:")[0].split(" align:")[0])
        if times.count(":") == 4:  # mm:ss.mmm -> 00:mm:ss,mmm
            times = re.sub(r"(?<![\d:])(\d\d:\d\d,\d\d\d)", r"00:\1", times)
        blocks.append(f"{n}\n{times}\n" + "\n".join(lines[idx + 1:]))
    return "\n\n".join(blocks) + "\n"


def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "OneTV/1.0"

        def log_message(self, fmt, *args):
            pass  # silencio: el Roku hace cientos de peticiones por película

        # ---------- respuestas ----------

        def _send(self, code, body=b"", ctype="text/plain; charset=utf-8", headers=None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, data, code=200):
            if "Roku" in self.headers.get("User-Agent", ""):   # las letras del Roku no tienen emojis: saldrían cuadritos
                data = without_emoji(data)
            self._send(code, json.dumps(data, ensure_ascii=False).encode(), "application/json; charset=utf-8")

        def _file(self, path, ctype=None, cache=False, headers=None):
            """Entrega un archivo respetando 'Range' (el Roku pide la película a trozos)."""
            try:
                f = hostos.open_shared(path)   # en Windows, sin impedir que ffmpeg lo reemplace o se borre
            except OSError:
                return self._send(404, b"no encontrado")
            with f:
                size = Path(path).stat().st_size
                start, end = 0, size - 1
                rng = self.headers.get("Range")
                m = re.match(r"bytes=(\d*)-(\d*)$", rng or "")
                if m and (m.group(1) or m.group(2)):
                    if m.group(1):
                        start = int(m.group(1))
                        end = min(int(m.group(2)), size - 1) if m.group(2) else size - 1
                    else:
                        start = max(0, size - int(m.group(2)))
                    if start > end or start >= size:
                        return self._send(416, headers={"Content-Range": f"bytes */{size}"})
                length = end - start + 1
                self.send_response(206 if m and rng else 200)
                self.send_header("Content-Type", ctype or CONTENT_TYPES.get(Path(path).suffix.lower(), "application/octet-stream"))
                self.send_header("Content-Length", str(length))
                self.send_header("Accept-Ranges", "bytes")
                if m and rng:
                    self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                self.send_header("Cache-Control", "max-age=86400" if cache else "no-cache")
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                if self.command == "HEAD":
                    return
                self.wfile.flush()
                self.connection.sendfile(f, offset=start, count=length)

        # ---------- rutas ----------

        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            try:
                self._route_get(urllib.parse.urlsplit(self.path).path)
            except (BrokenPipeError, ConnectionResetError, TimeoutError):
                pass  # el Roku cortó la conexión (adelantó, salió...): normal

        def _route_get(self, path):
            parts = [urllib.parse.unquote(p) for p in path.strip("/").split("/")]
            if path in ("/", "/index.html"):
                return self._file(WEB_DIR / "index.html")
            if len(parts) == 1 and re.fullmatch(r"[\w.-]+\.(png|webmanifest|js)", parts[0]):
                return self._file(WEB_DIR / parts[0], cache=True)
            if len(parts) == 2 and parts[0] == "fonts" and re.fullmatch(r"[\w-]+\.woff2", parts[1]):   # letras de la web
                return self._file(WEB_DIR / "fonts" / parts[1], cache=True)
            if path == "/api/library":
                device_id = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get("device_id", [""])[0]
                app.library.scan()
                data = app.library.api()
                data["watching"] = [w for w in app.store.watching() if w["id"] in data["items"]]
                data["seen"] = [i for i in app.store.seen() if i in data["items"]]
                data["keep_watching"] = app.store.keep_watching(data["items"])
                data["continue"] = app.continue_watching(data["items"])   # biblioteca y YouTube juntos
                data["live"] = app.live.public()
                data["youtube"] = app.youtube.recent()
                data["queue"] = app.queue.items()
                # Pósters (vertical) de películas y series; ?v cambia cuando llega el póster de verdad.
                for it in data["items"].values():
                    if it["kind"] == "movie":
                        it["art"] = f"/art/{it['id']}.jpg?v={int(app.artwork.path(it['id']).exists())}"
                for show in data["series"]:
                    key = f"serie-{show['key']}"
                    show["art"] = f"/art/{key}.jpg?v={int(app.artwork.path(key).exists())}"
                data["prefs"] = app.store.prefs_for(device_id)   # el idioma es de cada aparato
                data["history"] = app.history()
                return self._json(data)
            if path == "/api/status":
                return self._json(app.status())
            if path == "/api/tv/ordenes":   # la app de la TV con Android espera aquí las órdenes (mac/teles.py)
                return self._tv_orders()
            if path == "/api/tv/app":   # la app para Google TV / Android TV / Fire TV: versión y dirección para instalarla
                return self._json(app.tv_app())
            if path.lower().rstrip("/") in ("/tv", "/tv.apk", "/tv/one-tv.apk"):   # instalarla con «Downloader»
                return self._tv_apk()
            if path == "/api/intros":   # dónde empieza y termina la entrada de las series (mac/intro.py)
                return self._json(app.intros.summary())
            if path == "/api/yt/next":   # la web, al terminar un video de YouTube en el propio aparato
                q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                return self._json({"ok": True, "entry": app.youtube_next("yt:" + q.get("id", [""])[0])})
            if path == "/api/dubs":
                return self._json(app.dubbing.summary())
            if path == "/api/yt/account":
                return self._json(app.account.summary())
            if path == "/api/yt/subscriptions":   # «Tus canales» (anclados primero, sin ocultos) y «Nuevos de tus canales»
                return self._json({"channels": app.account.channels(), "videos": app.account.new_videos()})
            if path == "/api/yt/hidden":   # canales ocultos (Ajustes generales)
                return self._json({"channels": app.account.hidden_channels()})
            if path == "/api/subs/search":
                q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                return self._json(app.subs_search(q.get("id", [""])[0], q.get("lang", ["spa"])[0]))
            if parts[0] == "poster" and len(parts) == 2:
                item = app.library.get(parts[1].removesuffix(".jpg"))
                p = app.media.poster(item) if item else None
                return self._file(p, cache=True) if p else self._send(404)
            if parts[0] == "art" and len(parts) == 2 and re.fullmatch(r"[\w-]+\.jpg", parts[1]):
                return self._art(parts[1][:-4])
            if parts[0] == "media" and len(parts) == 2:
                item = app.library.get(Path(parts[1]).stem)
                if not item:
                    return self._send(404)
                app.keep_awake.poke()
                return self._file(item["path"])
            if parts[0] == "subs" and len(parts) == 3:
                item = app.library.get(parts[1])
                key, ext = parts[2].rsplit(".", 1) if "." in parts[2] else (parts[2], "srt")
                data = app.media.subtitle(item, key) if item else None
                if not data:
                    return self._send(404)
                if ext == "vtt":  # los navegadores solo entienden WebVTT
                    return self._send(200, srt_to_vtt(data), CONTENT_TYPES[".vtt"])
                return self._send(200, data, CONTENT_TYPES[".srt"])
            if parts[0] == "hls" and len(parts) == 4:
                return self._hls(*parts[1:])
            if parts[0] == "live" and len(parts) >= 3:
                return self._live(parts[1], parts[2:])
            if path == "/api/yt/search":   # ?q=&page= (page 2, 3…: «Cargar más»)&live=1 (solo transmisiones en vivo)
                q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                return self._json(app.yt_search(q.get("q", [""])[0], q.get("page", ["1"])[0],
                                                _bool(q.get("live", [""])[0])))
            if path == "/api/lists":   # ?video=<id>: dónde se puede guardar (Favoritos, tus listas) y si ya está
                q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                return self._json(app.lists_for(q.get("video", [""])[0]))
            if path == "/api/offline":   # lo guardado sin conexión y la cola de descargas
                return self._json(app.offline_summary())
            if path == "/api/yt/home":
                return self._json(app.yt_home())
            if path == "/api/yt/channel":
                q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                return self._json(app.yt_channel(q.get("id", [""])[0]))
            if path == "/api/yt/playlist":
                q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                return self._json(app.yt_playlist(q.get("id", [""])[0]))
            if path == "/api/marks":   # un solo aviso de «saltar»: capítulos (YouTube) o intro (biblioteca)
                q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                return self._json({"ok": True, "marks": app.marks(q.get("id", [""])[0])})
            if path == "/api/yt/check":   # la TV pregunta antes de reproducir: ¿existe y se puede pasar?
                vid = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get("id", [""])[0]
                if not VIDEO_ID.match(vid):
                    return self._json({"ok": False, "gone": False, "error": "Ese no parece un video de YouTube."})
                return self._json(app.yt_check(vid))
            if path in ("/api/info", "/api/yt/info"):
                q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                key = q.get("id", [""])[0]
                if path == "/api/info":
                    return self._json(app.info(key))
                try:
                    info = app.youtube.resolve(key)["info"] if VIDEO_ID.match(key) else None
                except YouTubeError as e:
                    return self._json({"ok": False, "error": str(e)})
                if info and info.get("published"):
                    app.youtube.durations.learn_dates([{"id": key, "published": info["published"]}])
                when = app.youtube.durations.date(key) if info else None   # exacta (yt-dlp) o la que se sepa
                state = app.offline.status_of(key) if getattr(app, "offline", None) else None
                return self._json({"ok": bool(info), "title": (info or {}).get("title", ""),
                                   "fav": bool(info) and app.lists.is_favorite(key),
                                   "live": bool((info or {}).get("live")), "viewers": (info or {}).get("viewers") or 0,
                                   **({"offline": state[0], "offline_progress": state[1]} if state and state[0] != "error" else {}),
                                   "published": when[0] if when else 0, "published_approx": bool(when and when[1]),
                                   "duration": (info or {}).get("duration") or 0,
                                   "desc": (info or {}).get("description", ""),
                                   "channel": (info or {}).get("channel", ""),
                                   "channel_id": (info or {}).get("channel_id", ""),
                                   "chapters": (info or {}).get("chapters", []),
                                   "dubs": (info or {}).get("dubs", [])})
            if parts[0] == "yt" and len(parts) >= 3 and VIDEO_ID.match(parts[1]):
                return self._youtube(parts[1], parts[2:])
            if path == "/api/music":   # tu música: {ok, artists, albums, tracks, playlists}
                return self._json({"ok": True, "enabled": app.music.enabled, **app.music.public()})
            if path == "/api/music/session":   # ?id=: lo que se mandó a la TV para escuchar
                sid = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get("id", [""])[0]
                return self._json(app.music_session(sid))
            if parts[0] == "music" and len(parts) == 3 and parts[1] == "art":   # /music/art/<álbum>.jpg
                p = app.music.art(parts[2].rsplit(".", 1)[0])
                return self._file(p, "image/jpeg", cache=True) if p else self._file(WEB_DIR / "icon-512.png")
            if parts[0] == "music" and len(parts) == 3 and parts[2] == "audio":   # /music/<canción>/audio
                got = app.music.audio(parts[1])
                if not got:
                    return self._send(404, b"no encontrada")
                app.music.prepare_next(parts[1])
                app.keep_awake.poke()
                return self._file(got[0], got[1], cache=True)
            if parts[0] == "ytc" and len(parts) == 3 and parts[2] == "avatar.png":   # foto del canal (404: iniciales)
                p = app.youtube.channel_avatar(parts[1])
                return self._file(p, cache=True) if p else self._send(404)
            if path == "/api/mosaic/status":   # ?id= -> {ok, ready, error, sources, tracks, …}
                mid = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get("id", [""])[0]
                return self._json(app.mosaic_status(mid))
            if parts[0] == "mosaic" and len(parts) in (3, 4):
                return self._mosaic(parts[1], "/".join(parts[2:]))
            self._send(404, b"no encontrado")

        def _tv_orders(self):
            """Espera (hasta ~25 s) las órdenes para esa TV: ver algo, pausa, avanzar, pistas, salir, actualiza…"""
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            device_id = q.get("device_id", [""])[0]
            orders = app.teles.esperar(device_id, q.get("nombre", [""])[0])
            try:
                self._json({"ok": True, "ordenes": orders})
            except (BrokenPipeError, ConnectionResetError, TimeoutError):
                app.teles.devolver(device_id, orders)   # se cortó: las recoge en la próxima consulta

        def _tv_apk(self):
            """El archivo de la app (o, si esta computadora todavía no lo tiene, una página que lo dice en llano)."""
            got = app.app_tv.actual_o_buscar()
            if not got:
                return self._send(200, pagina_sin_app().encode(), "text/html; charset=utf-8")
            return self._file(got["path"], TV_APP_TYPE,
                              headers={"Content-Disposition": 'attachment; filename="one-tv.apk"'})

        def _mosaic(self, mid, rel):
            """Varios a la vez (mac/mosaic.py): la lista maestra, las listas y los trozos. Sin caché: es en vivo."""
            m = app.mosaics.get(mid) if app.mosaics and MOSAIC_ID.match(mid) else None
            got = m.file(rel) if m else None
            if got is None:
                return self._send(404, b"no encontrado")
            app.keep_awake.poke()
            if isinstance(got, bytes):
                return self._send(200, got, CONTENT_TYPES[".m3u8"], {"Cache-Control": "no-cache"})
            if rel.endswith(".m3u8"):
                try:
                    body = hostos.read_shared(got)
                except OSError:
                    return self._send(404, b"no encontrado")
                return self._send(200, body, CONTENT_TYPES[".m3u8"], {"Cache-Control": "no-cache"})
            self._file(got)

        def _art(self, key):
            """Póster vertical; si no hay, un recorte vertical del fotograma."""
            p = app.artwork.path(key)
            if not p.exists():
                if key.startswith("serie-"):
                    show = next((s for s in app.library.series if s["key"] == key[6:]), None)
                    item = app.library.get(show["poster"]) if show else None
                else:
                    item = app.library.get(key)
                p = app.artwork.frame_fallback(key, app.media.poster(item)) if item else None
            return self._file(p, cache=True) if p else self._send(404)

        def _youtube(self, vid, rest):
            """YouTube pasando por la Mac: listas filtradas para el Roku y trozos tal cual."""
            if rest == ["qr.png"]:   # compartir desde la tele: se escanea con el teléfono
                p = app.youtube.qr(vid)
                return self._file(p, cache=True) if p else self._send(404)
            off = getattr(app, "offline", None)
            if off and off.ready(vid):   # guardado en la computadora: todo sale del disco, sin llamar a YouTube
                return self._saved_youtube(off, vid, rest)
            if rest in (["thumb.jpg"], ["thumb-hd.jpg"]):   # -hd: para agrandarla en una tarjeta vertical
                p = app.youtube.thumbnail(vid, hd=rest == ["thumb-hd.jpg"])
                return self._file(p, cache=True) if p else self._file(WEB_DIR / "icon-512.png")
            try:
                if rest == ["index.m3u8"]:   # ?dub=es: el doblaje en ese idioma; si no, el audio original
                    dub = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get("dub", [""])[0][:5]
                    text = app.youtube.playlist(vid, dub=dub.lower() or None)
                elif len(rest) == 2 and rest[0] == "m":
                    text = app.youtube.playlist(vid, decode_url(rest[1].rsplit(".", 1)[0]))
                elif len(rest) == 2 and rest[0] == "s":
                    url = decode_url(rest[1].rsplit(".", 1)[0])
                    # El mosaico los pide de antemano (X-Prefetch) y ffmpeg los encuentra listos (mac/segcache.py).
                    body, media_type = app.segments.get(("yt", vid, rest[1]), lambda: app.youtube.segment(vid, url),
                                                        keep=self.headers.get("X-Prefetch") == "1")
                    app.keep_awake.poke()
                    return self._send(200, body, media_type)
                else:
                    return self._send(404)
            except (YouTubeError, OSError, ValueError) as e:
                return self._send(502, str(e).encode())
            self._send(200, text.encode(), CONTENT_TYPES[".m3u8"], {"Cache-Control": "no-cache"})

        def _saved_youtube(self, off, vid, rest):
            """Un video guardado sin conexión (mac/offline.py): las mismas direcciones de /yt/<id>/…, desde el disco."""
            if len(rest) != 1:
                return self._send(404)
            name = rest[0]
            if name == "index.m3u8":   # lista maestra con el tamaño; la de trozos es playlist.m3u8
                info = off.info(vid)
                app.youtube.remember(info)   # cuenta en «vistos hace poco» como cualquier video
                return self._send(200, off.master(vid).encode(), CONTENT_TYPES[".m3u8"], {"Cache-Control": "no-cache"})
            p = off.file(vid, "index.m3u8" if name == "playlist.m3u8" else name)
            if not p:
                return self._send(404)
            if name.startswith("thumb"):
                return self._file(p, cache=True)
            if name.endswith(".ts"):
                app.keep_awake.poke()
            self._file(p, CONTENT_TYPES[".m3u8"] if name.endswith(".m3u8") else None)

        def _hls(self, item_id, audio, name):
            item = app.library.get(item_id)
            if not item:
                return self._send(404)
            try:
                if audio == "na":
                    audio_index = None
                elif re.fullmatch(r"x\d+", audio):   # pista aparte (doblaje agregado)
                    audio_index = audio
                else:
                    audio_index = int(audio.lstrip("a"))
            except ValueError:
                return self._send(404)
            session = app.transcoder.session(item, audio_index, self.client_address[0])
            if name == "index.m3u8":
                return self._send(200, playlist_text(session.plan).encode(), CONTENT_TYPES[".m3u8"])
            m = re.match(r"seg(\d+)\.ts$", name)
            if not m:
                return self._send(404)
            app.keep_awake.poke()
            seg = session.segment(int(m.group(1)))
            if seg is None:
                return self._send(503, b"no se pudo convertir este trozo")
            self._file(seg)

        def _live(self, cid, rest):
            """Canal en vivo pasando por la Mac: listas reescritas y trozos sin disfraz."""
            if rest == ["poster.jpg"]:
                p = app.media.posters / f"live-{cid}.jpg"
                return self._file(p, cache=True) if p.exists() else self._file(WEB_DIR / "icon-512.png")
            channel = app.live.get(cid)
            if channel and channel.get("youtube"):
                return self._live_youtube(cid, rest)
            try:
                if rest == ["index.m3u8"]:
                    kind, url = "m", None
                elif len(rest) == 2 and rest[0] in ("m", "s", "k"):
                    kind, url = rest[0], decode_url(rest[1].rsplit(".", 1)[0])
                else:
                    return self._send(404)
                if kind == "s":   # un trozo: puede venir pedido de antemano por el mosaico (mac/segcache.py)
                    status, ctype, body, final = app.segments.get(
                        ("live", cid, rest[1]), lambda: app.live.fetch_through(cid, url),
                        keep=self.headers.get("X-Prefetch") == "1")
                else:
                    status, ctype, body, final = app.live.fetch_through(cid, url)
            except (LiveError, OSError, ValueError) as e:
                return self._send(502, str(e).encode())
            app.keep_awake.poke()
            if kind == "m" or body.lstrip().startswith(b"#EXTM3U"):
                text = rewrite_playlist(body.decode("utf-8", "replace"), final, f"/live/{cid}")
                return self._send(200, text.encode(), CONTENT_TYPES[".m3u8"], {"Cache-Control": "no-cache"})
            if kind == "k":
                return self._send(200, body, "application/octet-stream")
            data, media_type = unwrap_segment(body)
            self._send(200, data, media_type)

        def _live_youtube(self, cid, rest):
            """Canal de YouTube en «En vivo»: su lista es la de la transmisión de ahora, que pasa por /yt/<id>/ (así el
            Roku, la web y el mosaico lo ven como cualquier canal)."""
            if rest != ["index.m3u8"]:
                return self._send(404)
            try:
                vid = app.live.youtube_vid(cid)
                try:
                    text = app.youtube.playlist(vid)
                except (YouTubeError, OSError):
                    vid = app.live.youtube_vid(cid, force=True)   # terminó y volvió a transmitir con otro video
                    text = app.youtube.playlist(vid)
            except (LiveError, YouTubeError, OSError, ValueError) as e:
                return self._send(502, str(e).encode())
            app.keep_awake.poke()
            self._send(200, text.encode(), CONTENT_TYPES[".m3u8"], {"Cache-Control": "no-cache"})

        def do_POST(self):
            # Solo JSON: una página web de otro sitio abierta en la casa no puede mandar órdenes (el navegador le
            # exige permiso para mandar JSON a otro lado, y este servidor no lo da).
            if not (self.headers.get("Content-Type") or "").lower().startswith("application/json"):
                return self._send(415, "Solo se aceptan órdenes en JSON.".encode())
            try:
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}") if length else {}
                path = urllib.parse.urlsplit(self.path).path
                if path == "/api/play":
                    return self._json(app.cast(body.get("id", ""), audio=_int(body.get("audio")),
                                               sub=_int(body.get("sub")), start=_int(body.get("start")),
                                               device_id=body.get("device_id")))
                if path == "/api/tracks":
                    return self._json(app.control("tracks", device_id=body.get("device_id"),
                                                  audio=_int(body.get("audio")), sub=_int(body.get("sub"))))
                if path == "/api/music/step":   # {dir: -1 | 1}: la canción anterior o la siguiente en la TV
                    return self._json(app.control("song", dir=1 if (_int(body.get("dir")) or 1) > 0 else -1))
                if path == "/api/seek":
                    return self._json(app.control("seek", t=_int(body.get("t"))))
                if path == "/api/progress":  # reportes del Roku
                    item = str(body.get("id", ""))
                    live = item.startswith("yt:") and bool((app.youtube.cached_info(item[3:]) or {}).get("live"))
                    device_id = str(body.get("device_id") or "")[:80] or None
                    app.store.report(item, float(body.get("p") or 0), float(body.get("d") or 0),
                                     body.get("ev", "tick"), _int(body.get("audio")), _int(body.get("sub")),
                                     body.get("state", "play"), body.get("device", "tv"), live=live,
                                     song=_song(body), device_id=device_id)
                    teles = getattr(app, "teles", None)
                    if teles and body.get("device", "tv") == "tv" and body.get("ev") == "start":
                        # La TV que empieza a reproducir pasa a ser la que se usó por última vez (mac/teles.py).
                        teles.usar(device_id if teles.es_android(device_id) else ROKU)
                    return self._json({"ok": True})
                if path == "/api/import":  # lo que el Roku tenía guardado antes de esta versión
                    app.store.import_from_roku(body.get("progress"), body.get("prefs"))
                    return self._json({"ok": True})
                if path == "/api/subs/download":
                    return self._json(app.subs_download(body.get("id", ""), body.get("file_id"), body.get("lang", "")))
                if path == "/api/subs/auto":
                    return self._json(app.subs_auto(body.get("id", ""), body.get("lang") or "spa"))
                if path == "/api/live/add":
                    return self._json(app.live_add(body.get("url", ""), body.get("name", "")))
                if path == "/api/live/rename":   # {id, name} -> {ok, channel} o {ok: false, error}
                    return self._json(app.live_rename(str(body.get("id", "")), str(body.get("name", ""))))
                if path == "/api/live/remove":
                    app.live.remove(body.get("id", ""))
                    return self._json({"ok": True})
                if path == "/api/live/play":
                    return self._json(app.live_play(body.get("id", "")))
                if path == "/api/offline/save":   # {id} o {list} -> {ok, state}
                    return self._json(app.offline_save(body))
                if path == "/api/offline/remove":   # {id} o {list} -> {ok}
                    return self._json(app.offline_remove(body))
                if path == "/api/yt/search":  # el Roku busca por POST (no puede codificar direcciones)
                    return self._json(app.yt_search(body.get("q", ""), body.get("page", 1), _bool(body.get("live"))))
                if path == "/api/lists/toggle":   # {list, id, on?, title?, channel?, duration?} -> {ok, has}
                    return self._json(app.list_toggle(body))
                if path == "/api/lists/create":   # {title, id?} -> {ok, list: {id, title}}
                    return self._json(app.list_create(body))
                if path == "/api/lists/rename":   # {list, title} -> {ok}
                    return self._json(app.list_rename(body))
                if path == "/api/lists/delete":   # {list} -> {ok}
                    return self._json(app.list_delete(body))
                if path == "/api/yt/play":
                    return self._json(app.yt_play(body.get("id", "")))
                if path == "/api/queue/add":
                    return self._json(app.queue_add(body.get("kind", "item"), body.get("id", ""),
                                                    body.get("title", ""), bool(body.get("front"))))
                if path == "/api/queue/remove":
                    app.queue.remove(_int(body.get("index")) or 0)
                    app.tell_tv_to_refresh()
                    return self._json({"ok": True, "queue": app.queue.items()})
                if path == "/api/queue/move":   # {index, to} -> {ok, index, queue}
                    return self._json(app.queue_move(_int(body.get("index")) or 0, _int(body.get("to")) or 0))
                if path == "/api/queue/add_list":   # {id, front?, shuffle?}: una lista entera a la fila, sin reproducir
                    return self._json(app.queue_add_list(str(body.get("id", "")), _bool(body.get("front")),
                                                         _bool(body.get("shuffle"))))
                if path == "/api/queue/clear":
                    app.queue.clear()
                    app.tell_tv_to_refresh()
                    return self._json({"ok": True, "queue": []})
                if path == "/api/queue/play":  # la web: poner ya en la tele algo de la cola
                    return self._json(app.queue_play(_int(body.get("index")) or 0))
                if path in ("/api/queue/next", "/api/queue/take"):  # el Roku: lo siguiente (y se quita de la cola)
                    entry, source = app.queue.remove(_int(body.get("index")) or 0), "queue"
                    skipped = []   # videos de la fila que ya se sabe que no existen: se saltan
                    while path == "/api/queue/next" and entry and entry.get("kind") == "yt" and app.youtube.is_gone(entry["id"]):
                        skipped.append(entry.get("title") or "")
                        entry = app.queue.remove(0)
                    if entry is None and path == "/api/queue/next":
                        # Cola vacía después de YouTube: reproducción continua, si está prendida.
                        entry, source = app.youtube_next(body.get("after") or ""), "related"
                    return self._json({"ok": True, "entry": entry, "source": source if entry else "", "skipped": skipped})
                if path == "/api/yt/playlist/play":   # una lista entera a la tele (en orden o al azar)
                    return self._json(app.yt_playlist_play(str(body.get("id", "")), bool(body.get("shuffle")),
                                                           _int(body.get("start"))))
                if path == "/api/yt/channel/hide":   # «Silenciar canal»: {id, title} o {video} (el canal de ese video) -> {ok, id, title}
                    return self._json(app.yt_channel_hide(str(body.get("id") or ""), str(body.get("title") or ""),
                                                          video=str(body.get("video") or "")))
                if path == "/api/queue/add_tracks":   # {tracks: [id…], front?} -> canciones a la fila
                    tracks = body.get("tracks") if isinstance(body.get("tracks"), list) else []
                    return self._json(app.queue_add_tracks([str(t) for t in tracks][:500], _bool(body.get("front", False))))
                if path == "/api/music/tv":   # {tracks: [id…], index?, shuffle?, start?} -> escuchar en la TV
                    tracks = body.get("tracks") if isinstance(body.get("tracks"), list) else []
                    return self._json(app.music_tv([str(t) for t in tracks][:2000], _int(body.get("index")) or 0,
                                                   _bool(body.get("shuffle", False)), _int(body.get("start")) or 0))
                if path == "/api/yt/dismiss":   # «No me interesa»: {id, on?} -> {ok}
                    return self._json(app.yt_dismiss(str(body.get("id", "")), _bool(body.get("on", True))))
                if path == "/api/yt/channel/unhide":   # {id} -> {ok}
                    return self._json(app.yt_channel_unhide(str(body.get("id", ""))))
                if path == "/api/yt/channel/pin":   # {id, title, on} -> {ok, pinned}
                    return self._json(app.yt_channel_pin(str(body.get("id", "")), str(body.get("title") or ""),
                                                         _bool(body.get("on", True))))
                if path == "/api/mosaic/start":   # {sources, layout?, audio?, focus?} -> {ok, id, url, tracks}
                    return self._json(app.mosaic_start(body))
                if path == "/api/mosaic/stop":   # {id} -> {ok}
                    return self._json(app.mosaic_stop(str(body.get("id", "")) if isinstance(body, dict) else ""))
                if path == "/api/mosaic/tv":   # {sources, focus?} -> arma el mosaico y la TV lo abra
                    return self._json(app.mosaic_tv(body))
                if path == "/api/yt/autoplay":
                    return self._json(app.set_yt_autoplay(body.get("on")))
                if path == "/api/yt/import":   # el zip del Takeout: el de "path" o el más nuevo de Descargas
                    try:
                        if body.get("path"):   # solo un zip que esté en Descargas (no cualquier archivo)
                            p = Path(str(body["path"])).expanduser().resolve()
                            downloads = hostos.user_dir("DOWNLOAD").resolve()
                            if downloads not in p.parents:
                                return self._json({"ok": False, "error": "El Takeout tiene que estar en Descargas."})
                            result = app.account.import_zip(str(p))
                        else:
                            result = app.account.scan_downloads() or {"ok": False, "error": "No hay un Takeout nuevo en Descargas."}
                    except Exception as e:   # zip dañado, ruta que no existe…
                        result = {"ok": False, "error": f"No pude abrir el zip: {e}"}
                    return self._json(result)
                if path == "/api/yt/feeds/refresh":   # RSS de los canales; con {"wait": true} espera al final
                    if body.get("wait"):
                        return self._json(app.account.refresh_feeds())
                    threading.Thread(target=app.account.refresh_feeds, daemon=True).start()
                    return self._json({"ok": True, "started": True})
                if path == "/api/prefs":
                    low = {k.lower(): v for k, v in body.items()}  # el Roku manda las claves en minúsculas
                    if "chaptertitles" in low:   # ajuste de la casa: mostrar el nombre del capítulo al empezar
                        app.store.set_prefs(chapterTitles=bool(low["chaptertitles"]))
                    if low.get("device_id"):   # el idioma de ese aparato
                        app.store.set_device_prefs(low["device_id"], audioLang=low.get("audiolang"),
                                                   subLang=low.get("sublang"))
                    else:
                        app.store.set_prefs(audioLang=low.get("audiolang"), subLang=low.get("sublang"))
                    return self._json({"ok": True})
                if path == "/api/key":
                    return self._json(app.remote_key(body.get("key", "")))
                if path == "/api/tv/elegir":   # {id}: la web elige a qué TV mandar «Ver en la TV» (con más de una)
                    return self._json(app.tv_choose(body.get("id", "")))
                if path == "/api/tv/adios":   # {device_id}: la app de la TV con Android se cerró o se fue al fondo
                    app.teles.adios(str(body.get("device_id", "")))
                    return self._json({"ok": True})
                if path == "/api/rescan":
                    app.library.scan(force=True)
                    return self._json({"ok": True, "items": len(app.library.items)})
                self._send(404)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except (json.JSONDecodeError, ValueError, TypeError):
                self._send(400, b"datos invalidos")

    return Handler


def _int(v):
    return None if v is None or v == "" else int(float(v))


def _song(body):
    """De un reporte de la TV con música: {"i": lugar de la canción (desde 0), "n": cuántas hay} o None."""
    song = body.get("song")
    try:
        return {"i": int(song["i"]), "n": int(song["n"])} if isinstance(song, dict) else None
    except (KeyError, TypeError, ValueError):
        return None


def _bool(v):
    """true/false de JSON; también «true»/«false» o 1/0, por si algún cliente los manda como texto."""
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "si", "sí", "on", "yes")
    return bool(v)


class Server(ThreadingHTTPServer):
    daemon_threads = True
    # En Windows, «reusar la dirección» deja que dos programas escuchen en el mismo puerto (y no se nota que ya hay un
    # servidor): allá se pide el puerto en exclusiva.
    allow_reuse_address = not hostos.WINDOWS

    def server_bind(self):
        # Lo mismo que HTTPServer, pero sin preguntarle a la red el nombre de esta computadora (socket.getfqdn): en
        # algunas redes (un NAS, una máquina de pruebas) esa pregunta tarda minutos y el servidor no arranca.
        if hostos.WINDOWS:
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        socketserver.TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        self.server_name = host
        self.server_port = port

    def handle_error(self, request, client_address):
        # Navegadores y el Roku cierran conexiones todo el tiempo: no es un error.
        if isinstance(sys.exc_info()[1], (ConnectionError, TimeoutError)):
            return
        super().handle_error(request, client_address)


def serve(app, port, host="0.0.0.0"):
    """host: en qué red escucha (config «escuchar»). Por omisión todas: la TV y el teléfono están en la red de la
    casa. Para que solo la vea esta computadora: "127.0.0.1"."""
    httpd = Server((host, port), make_handler(app))
    httpd.daemon_threads = True
    return httpd
