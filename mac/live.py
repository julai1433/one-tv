"""Canales en vivo desde páginas web.

1. Encontrar el video: se abre la página en un Chrome invisible (controlado por el
   protocolo de depuración, CDP), se cierran las ventanas emergentes, se hace clic
   en el reproductor si hace falta y se anota la lista HLS (.m3u8) que pide la
   página, junto con los encabezados que exige (Referer, Origin, cookies...).
2. Pasar el video por la computadora: la TV pide todo a la computadora, que lo trae
   de la fuente con esos encabezados, reescribe las listas para que apunten a la
   computadora y quita el "disfraz" de imagen que algunas páginas ponen a los trozos
   de video.
"""

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import socket
import struct
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import hostos

CHROME_PATHS = hostos.CHROME_PATHS   # Chrome, Brave o Chromium: dónde están en macOS y en Linux
DESKTOP_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")
HLS_MIME = ("mpegurl",)
KEEP_HEADERS = {"referer", "origin", "user-agent", "cookie", "authorization"}
RESOLVE_TTL = 30 * 60     # la dirección encontrada se usa 30 min sin preguntar; después, mientras la fuente la acepte
RETRY_AFTER = 60          # si falla, no se vuelve a buscar antes de 1 min
YT_LIVE_TTL = 20 * 60     # un canal de YouTube: cada 20 min se pregunta cuál es su transmisión de ahora (puede cambiar)
YOUTUBE_LINK = re.compile(r"^https?://([\w-]+\.)?(youtube\.com|youtu\.be)/", re.I)
NAME_MAX = 80             # largo máximo del nombre de un canal

NO_VIDEO = ("No encontré un video en esa página. Si el evento aún no empieza, vuelve a intentarlo "
            "cuando esté al aire.")
BLOCKED = ("Encontré el video, pero la fuente no deja reproducirlo fuera de su página. "
           "Prueba con otro enlace del mismo evento.")


class LiveError(Exception):
    """Error para mostrar tal cual; `detail` (técnico) solo va al registro."""

    def __init__(self, message, detail=""):
        super().__init__(message)
        self.detail = detail


# ---------------------------------------------------------------- CDP mínimo

class CDP:
    """Cliente WebSocket mínimo (solo biblioteca estándar) para hablar con Chrome."""

    def __init__(self, ws_url):
        u = urllib.parse.urlsplit(ws_url)
        self.sock = socket.create_connection((u.hostname, u.port), timeout=10)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((f"GET {u.path} HTTP/1.1\r\nHost: {u.hostname}:{u.port}\r\nUpgrade: websocket\r\n"
                           f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise LiveError("Chrome cerró la conexión")
            head += chunk
        if b" 101 " not in head.split(b"\r\n", 1)[0]:
            raise LiveError("Chrome no aceptó la conexión de control")
        self.buf = head.split(b"\r\n\r\n", 1)[1]
        self.next_id = 0
        self.pending_events = []

    def _read(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise EOFError
            self.buf += chunk
        data, self.buf = self.buf[:n], self.buf[n:]
        return data

    def _write(self, opcode, payload):
        header = bytearray([0x80 | opcode])
        n = len(payload)
        if n < 126:
            header.append(0x80 | n)
        elif n < 65536:
            header += bytes([0x80 | 126]) + struct.pack(">H", n)
        else:
            header += bytes([0x80 | 127]) + struct.pack(">Q", n)
        mask = os.urandom(4)
        masked = bytes(b ^ mask[i & 3] for i, b in enumerate(payload))
        self.sock.sendall(bytes(header) + mask + masked)

    def _message(self):
        parts = []
        while True:
            b1, b2 = self._read(2)
            opcode, n = b1 & 0x0F, b2 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read(8))[0]
            mask = self._read(4) if b2 & 0x80 else None
            payload = self._read(n)
            if mask:
                payload = bytes(b ^ mask[i & 3] for i, b in enumerate(payload))
            if opcode == 0x9:        # ping
                self._write(0xA, payload)
                continue
            if opcode == 0x8:        # close
                raise EOFError
            parts.append(payload)
            if b1 & 0x80:
                return json.loads(b"".join(parts))

    def send(self, method, params=None, session=None):
        self.next_id += 1
        msg = {"id": self.next_id, "method": method, "params": params or {}}
        if session:
            msg["sessionId"] = session
        self._write(0x1, json.dumps(msg).encode())
        return self.next_id

    def call(self, method, params=None, session=None, timeout=15):
        wanted = self.send(method, params, session)
        end = time.time() + timeout
        while time.time() < end:
            self.sock.settimeout(max(0.1, end - time.time()))
            msg = self._message()
            if msg.get("id") == wanted:
                if "error" in msg:
                    raise LiveError(msg["error"].get("message", "error de Chrome"))
                return msg.get("result", {})
            if "method" in msg:
                self.pending_events.append(msg)
        raise LiveError(f"Chrome no respondió a {method}")

    def event(self, timeout):
        if self.pending_events:
            return self.pending_events.pop(0)
        self.sock.settimeout(timeout)
        try:
            msg = self._message()
        except (socket.timeout, TimeoutError):
            return None
        return msg if "method" in msg else None

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


# ---------------------------------------------------------------- buscar el video

def find_chrome(configured=""):
    for path in ([configured] if configured else []) + CHROME_PATHS:
        if path and Path(path).exists():
            return path
    return None


def fetch(url, headers, timeout=15):
    check_web_url(url)
    req = urllib.request.Request(url, headers={"User-Agent": DESKTOP_UA, **headers})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.headers.get("Content-Type", ""), r.read(), r.geturl()


def _looks_like_hls(url, mime=""):
    path = urllib.parse.urlsplit(url).path.lower()
    return path.endswith(".m3u8") or any(m in (mime or "").lower() for m in HLS_MIME)


def resolve_stream(page_url, chrome, timeout=45):
    """Abre la página y devuelve {"url", "headers", "title", "poster"} del video en vivo."""
    profile = tempfile.mkdtemp(prefix="cine-live-", dir=hostos.chrome_profile_parent(chrome))
    proc = subprocess.Popen(
        [chrome, "--headless=new", "--remote-debugging-port=0", f"--user-data-dir={profile}",
         "--no-first-run", "--no-default-browser-check", "--mute-audio", "--window-size=1280,720",
         "--autoplay-policy=no-user-gesture-required", f"--user-agent={DESKTOP_UA}",
         "--disable-features=IsolateOrigins,site-per-process", "about:blank"],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    cdp = None
    try:
        port_file = Path(profile) / "DevToolsActivePort"
        for _ in range(100):
            if port_file.exists() and port_file.read_text().strip():
                break
            time.sleep(0.1)
        else:
            raise LiveError("No se pudo abrir Chrome en la computadora. Vuelve a intentarlo.", "Chrome no arrancó")
        port = int(port_file.read_text().split()[0])
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=5) as r:
            cdp = CDP(json.loads(r.read())["webSocketDebuggerUrl"])
        return _watch_page(cdp, page_url, timeout)
    finally:
        if cdp:
            try:
                cdp.send("Browser.close")
            except OSError:
                pass
            cdp.close()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(profile, ignore_errors=True)


def _watch_page(cdp, page_url, timeout):
    cdp.call("Target.setDiscoverTargets", {"discover": True})
    main_target = cdp.call("Target.createTarget", {"url": "about:blank"})["targetId"]
    main = cdp.call("Target.attachToTarget", {"targetId": main_target, "flatten": True})["sessionId"]
    sessions = {main}

    def prepare(session):
        cdp.send("Network.enable", {}, session)
        cdp.send("Page.enable", {}, session)
        cdp.send("Target.setAutoAttach", {"autoAttach": True, "waitForDebuggerOnStart": True, "flatten": True}, session)
        cdp.send("Runtime.runIfWaitingForDebugger", {}, session)

    prepare(main)
    nav = cdp.call("Page.navigate", {"url": page_url}, main)
    if nav.get("errorText"):   # no existe, sin internet, certificado inválido…
        raise LiveError("No se pudo abrir esa página. Revisa el enlace y vuelve a intentarlo.", nav["errorText"])
    requests = {}      # requestId -> {"url", "headers"}
    candidates = []    # en el orden en que aparecen
    start = time.time()
    clicks = 0
    found_at = None
    while time.time() - start < timeout:
        ev = cdp.event(0.5)
        if ev:
            method, p = ev["method"], ev.get("params", {})
            if method == "Target.targetCreated":
                info = p.get("targetInfo", {})
                if info.get("type") == "page" and info.get("targetId") != main_target:
                    cdp.send("Target.closeTarget", {"targetId": info["targetId"]})   # ventana emergente
            elif method == "Target.attachedToTarget":
                child = p["sessionId"]
                if p.get("targetInfo", {}).get("type") in ("iframe", "page", "worker", "service_worker"):
                    sessions.add(child)
                    prepare(child)
                else:
                    cdp.send("Runtime.runIfWaitingForDebugger", {}, child)
            elif method == "Network.requestWillBeSent":
                req = p.get("request", {})
                rid = p.get("requestId")
                entry = requests.setdefault(rid, {"url": req.get("url", ""), "headers": {}})
                entry["url"] = req.get("url", entry["url"])
                entry["headers"].update({k.lower(): v for k, v in (req.get("headers") or {}).items()})
                if _looks_like_hls(entry["url"]) and entry not in candidates:
                    candidates.append(entry)
            elif method == "Network.requestWillBeSentExtraInfo":
                entry = requests.setdefault(p.get("requestId"), {"url": "", "headers": {}})
                entry["headers"].update({k.lower(): v for k, v in (p.get("headers") or {}).items()})
            elif method == "Network.responseReceived":
                resp = p.get("response", {})
                entry = requests.get(p.get("requestId"))
                if entry and _looks_like_hls(resp.get("url", ""), resp.get("mimeType")) and entry not in candidates:
                    candidates.append(entry)
        elapsed = time.time() - start
        if candidates and found_at is None:
            found_at = time.time()
        if found_at and time.time() - found_at > 2.5:
            break   # se da un momento por si llega la lista maestra
        # Muchas páginas solo cargan el video después de un clic (que además abre anuncios).
        if not candidates and clicks < 4 and elapsed > 6 + clicks * 5:
            _click_player(cdp, main)
            clicks += 1
    for entry in candidates:
        headers = {k: v for k, v in entry["headers"].items()
                   if k in KEEP_HEADERS or k.startswith("x-")}
        try:
            status, _, body, final = fetch(entry["url"], headers)
        except (urllib.error.URLError, OSError, ValueError):
            continue
        if body.lstrip().startswith(b"#EXTM3U"):
            title = _evaluate(cdp, main, "document.title") or urllib.parse.urlsplit(page_url).hostname
            poster = _screenshot(cdp, main)
            return {"url": final, "headers": headers, "title": title.strip()[:80], "poster": poster}
    if not candidates:
        raise LiveError(NO_VIDEO, f"sin listas HLS en {timeout} s")
    raise LiveError(BLOCKED, f"{len(candidates)} listas HLS, ninguna se pudo leer: "
                             + " · ".join(c["url"] for c in candidates[:3]))


def _evaluate(cdp, session, expression):
    try:
        r = cdp.call("Runtime.evaluate", {"expression": expression, "returnByValue": True}, session, timeout=5)
        return r.get("result", {}).get("value")
    except LiveError:
        return None


def _player_rect(cdp, session):
    """El elemento más grande que parezca reproductor (video o iframe): [x, y, ancho, alto]."""
    return _evaluate(cdp, session, """(() => {
        let best = null, area = 0;
        for (const el of document.querySelectorAll('video, iframe, [class*=player], [id*=player]')) {
            const r = el.getBoundingClientRect();
            if (r.width * r.height > area && r.width > 200 && r.height > 120) { area = r.width * r.height; best = r; }
        }
        return best ? [best.left, best.top, best.width, best.height] : null;
    })()""")


def _click_player(cdp, session):
    rect = _player_rect(cdp, session) or [0, 0, 1280, 720]
    x, y = rect[0] + rect[2] / 2, rect[1] + rect[3] / 2
    for kind in ("mousePressed", "mouseReleased"):
        cdp.send("Input.dispatchMouseEvent", {"type": kind, "x": x, "y": y, "button": "left", "clickCount": 1}, session)


def _screenshot(cdp, session):
    """Portada del canal: solo el reproductor (sin los anuncios de alrededor)."""
    params = {"format": "jpeg", "quality": 70}
    rect = _player_rect(cdp, session)
    if rect:
        params["clip"] = {"x": max(0, rect[0]), "y": max(0, rect[1]), "width": rect[2], "height": rect[3], "scale": 1}
    try:
        data = cdp.call("Page.captureScreenshot", params, session, timeout=8)["data"]
        return base64.b64decode(data)
    except (LiveError, KeyError, ValueError):
        return None


# ---------------------------------------------------------------- pasar el video por la computadora

# Las direcciones que la computadora reescribe en las listas (para que la TV las pida a través de ella) van FIRMADAS:
# así el servidor solo abre lo que él mismo puso en una lista, nunca una dirección que alguien le mande (sin esto,
# cualquiera en la red podría pedirle que leyera archivos de la computadora con file://). La clave se guarda en los
# datos (set_sign_key); si no hay, se inventa una al arrancar.
_sign_key = secrets.token_bytes(32)


def set_sign_key(key):
    global _sign_key
    _sign_key = key


def _sign(url):
    return base64.urlsafe_b64encode(hmac.new(_sign_key, url.encode(), hashlib.sha256).digest()[:12]).decode()


def encode_url(url):
    return base64.urlsafe_b64encode(url.encode()).decode().rstrip("=") + "~" + _sign(url)


def decode_url(token):
    """La dirección de un token firmado por encode_url. ValueError si no tiene firma, la firma no es de esta
    computadora o no es de internet (http/https)."""
    body, _, sig = token.partition("~")
    url = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)).decode()
    if not sig or not hmac.compare_digest(sig, _sign(url)):
        raise ValueError("dirección sin firma válida")
    check_web_url(url)
    return url


def check_web_url(url):
    """Solo direcciones de internet: nada de file://, ftp://… ValueError si no."""
    if urllib.parse.urlsplit(url).scheme not in ("http", "https"):
        raise ValueError("solo se piden direcciones http o https")
    return url


def rewrite_playlist(text, base_url, prefix):
    """Cambia cada dirección de la lista por una de la computadora (listas, trozos, claves y cabeceras de video)."""
    out = []
    next_is_playlist = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            out.append(line)
            continue
        if stripped.startswith("#"):
            if stripped.startswith("#EXT-X-STREAM-INF"):
                next_is_playlist = True

            def repl(m, tag=stripped):
                absolute = urllib.parse.urljoin(base_url, m.group(1))
                kind = "m" if tag.startswith(("#EXT-X-MEDIA", "#EXT-X-I-FRAME-STREAM-INF")) else \
                       "k" if tag.startswith(("#EXT-X-KEY", "#EXT-X-SESSION-KEY")) else "s"
                ext = {"m": "m3u8", "k": "key", "s": "mp4"}[kind]
                return f'URI="{prefix}/{kind}/{encode_url(absolute)}.{ext}"'

            out.append(re.sub(r'URI="([^"]+)"', repl, line))
            continue
        absolute = urllib.parse.urljoin(base_url, stripped)
        if next_is_playlist or _looks_like_hls(absolute):
            out.append(f"{prefix}/m/{encode_url(absolute)}.m3u8")
        else:
            out.append(f"{prefix}/s/{encode_url(absolute)}.ts")
        next_is_playlist = False
    return "\n".join(out) + "\n"


def unwrap_segment(data):
    """Algunas páginas disfrazan los trozos de video de imagen (PNG/JPG delante): se quita el disfraz."""
    if not data or data[0] == 0x47:
        return data, "video/mp2t"
    if data[4:8] in (b"ftyp", b"styp", b"moof", b"sidx"):
        return data, "video/mp4"
    limit = min(len(data) - 376, 65536)
    for i in range(1, max(limit, 1)):
        if data[i] == 0x47 and data[i + 188] == 0x47 and data[i + 376] == 0x47:
            return data[i:], "video/mp2t"
    return data, "application/octet-stream"


class LiveChannels:
    """Canales guardados y el paso del video por la computadora."""

    def __init__(self, data_dir, cache_dir, chrome=""):
        self.file = Path(data_dir) / "canales.json"
        self.posters = Path(cache_dir) / "posters"
        self.posters.mkdir(parents=True, exist_ok=True)
        self.chrome = find_chrome(chrome)
        self.lock = threading.Lock()
        self.resolve_lock = threading.Lock()
        self.adding = set()     # enlaces que se están buscando ahora (sin búsquedas dobles)
        # Canales de YouTube en vivo (DW, noticias, música 24/7): no se buscan con Chrome. La App pone estas dos
        # funciones: youtube_live(enlace) -> datos de la transmisión de ahora (id, channel, channel_id) o lanza
        # LiveError; youtube_thumb(id) -> bytes de su miniatura o None.
        self.youtube_live = None
        self.youtube_thumb = None
        try:
            self.channels = json.loads(self.file.read_text())
        except (OSError, ValueError):
            self.channels = []

    def _save(self):
        self.file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.file.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.channels, ensure_ascii=False, indent=1))
        tmp.replace(self.file)

    def get(self, cid):
        with self.lock:
            return next((c for c in self.channels if c["id"] == cid), None)

    def public(self):
        with self.lock:
            return [{"id": c["id"], "name": c["name"], "page": c["page"],
                     "host": "YouTube" if c.get("youtube") else urllib.parse.urlsplit(c["page"]).hostname or "",
                     "poster": f"/live/{c['id']}/poster.jpg", **({"youtube": True} if c.get("youtube") else {})}
                    for c in self.channels]

    def add(self, page_url, name=""):
        """Busca el video de la página y lo guarda como canal (o actualiza el que ya existía)."""
        page_url = (page_url or "").strip()
        if not re.match(r"https?://\S", page_url):
            raise LiveError("Pega un enlace que empiece con http:// o https://.")
        if YOUTUBE_LINK.match(page_url) and self.youtube_live:
            return self._add_youtube(page_url, name)
        if not self.chrome:
            raise LiveError("Hace falta Google Chrome (o Brave) instalado en la computadora.")
        with self.lock:
            if page_url in self.adding:
                raise LiveError("Ya se está buscando el video de ese enlace. Espera a que termine.")
            self.adding.add(page_url)
        try:
            found = self._resolve(page_url)
        finally:
            with self.lock:
                self.adding.discard(page_url)
        cid = hashlib.sha1(page_url.encode()).hexdigest()[:10]
        with self.lock:
            channel = next((c for c in self.channels if c["id"] == cid), None)
            if channel is None:
                channel = {"id": cid, "page": page_url, "name": ""}
                self.channels.insert(0, channel)
            # Un nombre escrito gana; si no, se queda el que ya tenía; si es nuevo, el título de la página
            # (con « 2», « 3»… si otro canal ya se llama así).
            channel["name"] = (name or "").strip()[:NAME_MAX] or channel["name"] or self._free_name(found["title"], cid)
            channel["stream"] = {"url": found["url"], "headers": found["headers"], "at": time.time()}
            self._save()
        if found.get("poster"):
            (self.posters / f"live-{cid}.jpg").write_bytes(found["poster"])
        return channel

    def _add_youtube(self, link, name=""):
        """Un canal de YouTube que transmite en vivo: se guarda el canal (no el video, que cambia cada vez que vuelve a
        transmitir) y su transmisión de ahora."""
        found = self.youtube_live(link)
        channel_id = found.get("channel_id") or ""
        if not channel_id:
            raise LiveError("YouTube no dijo de qué canal es esa transmisión.")
        cid = hashlib.sha1(f"youtube:{channel_id}".encode()).hexdigest()[:10]
        with self.lock:
            channel = next((c for c in self.channels if c["id"] == cid), None)
            if channel is None:
                channel = {"id": cid, "page": f"https://www.youtube.com/channel/{channel_id}/live", "name": ""}
                self.channels.insert(0, channel)
            channel["youtube"] = channel_id
            channel["name"] = (name or "").strip()[:NAME_MAX] or channel["name"] or self._free_name(found.get("channel") or found.get("title"), cid)
            channel["stream"] = {"vid": found["id"], "at": time.time()}
            self._save()
        self._youtube_poster(cid, found["id"])
        return channel

    def _youtube_poster(self, cid, vid):
        thumb = self.youtube_thumb(vid) if self.youtube_thumb else None
        if thumb:
            (self.posters / f"live-{cid}.jpg").write_bytes(thumb)

    def youtube_vid(self, cid, force=False):
        """La transmisión de ahora de un canal de YouTube (id del video): la guardada si es reciente; si no, se le
        pregunta a YouTube. Lanza LiveError si ya no transmite."""
        channel = self.get(cid)
        if not channel or not channel.get("youtube"):
            raise LiveError("Ese canal ya no existe.")
        stream = channel.get("stream") or {}
        if stream.get("vid") and not force and time.time() - stream.get("at", 0) < YT_LIVE_TTL:
            return stream["vid"]
        # Primero la que se eligió (un canal puede transmitir dos a la vez); si ya terminó, la principal del canal.
        found = None
        if stream.get("vid"):
            try:
                found = self.youtube_live(f"https://www.youtube.com/watch?v={stream['vid']}")
            except LiveError:
                found = None
        found = found or self.youtube_live(channel["youtube"])
        with self.lock:
            changed = stream.get("vid") != found["id"]
            channel["stream"] = {"vid": found["id"], "at": time.time()}
            self._save()
        if changed:
            self._youtube_poster(cid, found["id"])
        return found["id"]

    def _free_name(self, title, cid):
        """El título tal cual o, si otro canal ya lo usa, con « 2», « 3»… (se llama con self.lock tomado)."""
        title = (title or "").strip()[:NAME_MAX] or "Canal en vivo"
        taken = {c["name"].casefold() for c in self.channels if c["id"] != cid}
        name, n = title, 1
        while name.casefold() in taken:
            n += 1
            suffix = f" {n}"
            name = title[:NAME_MAX - len(suffix)].rstrip() + suffix
        return name

    def rename(self, cid, name):
        """Cambia el nombre de un canal (sin espacios a los lados, no vacío, hasta NAME_MAX caracteres)."""
        name = (name or "").strip()
        if not name:
            raise LiveError("Escribe un nombre para el canal.")
        if len(name) > NAME_MAX:
            raise LiveError(f"El nombre es muy largo: puede tener hasta {NAME_MAX} caracteres.")
        with self.lock:
            channel = next((c for c in self.channels if c["id"] == cid), None)
            if channel is None:
                raise LiveError("Ese canal ya no existe.")
            channel["name"] = name
            self._save()
            return channel

    def remove(self, cid):
        with self.lock:
            self.channels = [c for c in self.channels if c["id"] != cid]
            self._save()

    def _resolve(self, page_url):
        with self.resolve_lock:  # un Chrome a la vez
            return resolve_stream(page_url, self.chrome)

    def stream(self, cid, force=False):
        """Dirección del video. Se vuelve a buscar en la página (Chrome, ~12 s) solo si no hay o si la fuente ya no la
        acepta (force, desde fetch_through); una vieja que sigue funcionando se sigue usando: los enlaces de estos
        canales suelen valer horas, y buscarla de nuevo cada 30 min hacía esperar 12 s al abrir el canal o el mosaico."""
        channel = self.get(cid)
        if not channel:
            raise LiveError("Ese canal ya no existe.")
        stream = channel.get("stream") or {}
        age = time.time() - stream.get("at", 0)
        if stream and not force:
            return stream
        if stream and force and age < RETRY_AFTER:
            return stream
        found = self._resolve(channel["page"])
        with self.lock:
            channel["stream"] = {"url": found["url"], "headers": found["headers"], "at": time.time()}
            self._save()
        return channel["stream"]

    def fetch_through(self, cid, url=None):
        """Trae de la fuente (con los encabezados de la página) la lista principal o lo que se pida. Con más de
        RESOLVE_TTL sin revisarla, la lista principal se prueba: si la fuente ya no la da (cualquier error o algo que
        no es una lista), se busca de nuevo en la página."""
        stream = self.stream(cid)
        target = url or stream["url"]
        stale = url is None and time.time() - max(stream.get("at", 0), stream.get("checked", 0)) >= RESOLVE_TTL
        try:
            result = fetch(target, stream["headers"])
        except urllib.error.HTTPError as e:
            if url is None and (stale or e.code in (401, 403, 404, 410)):
                stream = self.stream(cid, force=True)     # el enlace caducó: se busca de nuevo
                return fetch(stream["url"], stream["headers"])
            raise
        except (urllib.error.URLError, OSError):
            if not stale:
                raise
            stream = self.stream(cid, force=True)
            return fetch(stream["url"], stream["headers"])
        if stale:
            if not result[2].lstrip().startswith(b"#EXTM3U"):
                stream = self.stream(cid, force=True)
                return fetch(stream["url"], stream["headers"])
            with self.lock:
                stream["checked"] = time.time()   # en memoria: al reiniciar se vuelve a probar una vez
        return result
