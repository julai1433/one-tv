"""YouTube sin anuncios: la Mac lee el video con yt-dlp y lo pasa a la tele por trozos (HLS).

Los anuncios de YouTube son videos aparte que mete su propio reproductor; aquí solo se pide el
video, así que no hay anuncios. Las direcciones de YouTube quedan atadas a la IP de quien las
pidió, así que todo pasa por la Mac, y por IPv4 (las IPv6 temporales cambian durante el día).
"""

import http.client
import json
import re
import shutil
import socket
import ssl
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from html import unescape as html_unescape
from pathlib import Path

from live import check_web_url, rewrite_playlist
from qrpng import write_qr
from ytdurations import Blocked, Durations, date_of, epoch_of, parse_ago, seconds_of

RESOLVE_TTL = 3 * 3600    # YouTube da las direcciones por unas 6 h; se renuevan antes
LIVE_TTL = 1800           # una transmisión en vivo se vuelve a preguntar cada 30 min (puede haber terminado)
# Filtro «En vivo» de la búsqueda de YouTube (el parámetro sp de su página de resultados, codificado dos veces para yt-dlp).
LIVE_FILTER = "EgJAAQ%253D%253D"
ITAG = re.compile(r"/itag/(\d+)/")
# Idioma en que se piden los títulos (el de la interfaz). Con «en», YouTube da la traducción al inglés que muchos
# canales en español ponen a sus títulos; en español se ve el título original (y los canales en inglés siguen en
# inglés, salvo que el canal haya puesto su propia traducción, como en la app de YouTube en español).
YT_LANG = "es-419"
RELATED_TTL = 3600         # los relacionados de un video se piden una vez por hora
AVATAR_SIZE = 240          # foto de un canal (en círculo), en píxeles
AVATAR_AT_ONCE = 3         # fotos de canales que se bajan a la vez
AVATAR_RETRY = 24 * 3600   # una foto que no se pudo bajar se vuelve a intentar al día siguiente
AVATAR_META = re.compile(r'<meta property="og:image" content="([^"]+)"')
MIN_RELATED_SECONDS = 60   # sin «shorts» en la reproducción continua
PAGE_HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/140.0 Safari/537.36",
                "Accept-Language": "es-MX,es;q=0.9", "Cookie": "CONSENT=YES+1; SOCS=CAI"}
HISTORY_MAX = 400          # se guardan muchos (para títulos de «Seguir viendo»); recent() enseña los últimos 40
RECENT_SHOWN = 40
LISTING_TTL = 1800         # canales y listas: 30 min de caché
CHANNEL_VIDEOS = 30
PLAYLIST_MAX = 200
HANDLE = re.compile(r"^@[\w.\-]{3,60}$")
CHANNEL_ID = re.compile(r"^UC[\w-]{22}$")
LIST_ID = re.compile(r"^[\w-]{10,64}$")
SEARCH_PAGE = 24   # resultados por página de búsqueda
SEARCH_PAGES = 8   # hasta 192 resultados («Cargar más» 7 veces)
MAX_HEIGHT = 1080          # el Roku de la casa no pasa de 1080p
VIDEO_ID = re.compile(r"^[\w-]{11}$")
URL_ID = re.compile(r"(?:v=|youtu\.be/|shorts/|live/|embed/)([\w-]{11})")
# Duración de varios videos con una sola página: YouTube arma una lista anónima con los ids (hasta 50) y la muestra
# al lado del primero, cada uno con su duración (ver fetch_durations y mac/ytdurations.py).
BATCH_URL = "https://www.youtube.com/watch_videos?video_ids={}&hl=es&gl=MX"
BOT_PAGE = re.compile(r"not a bot|no eres un bot|no eres un robot", re.I)   # «Sign in to confirm you're not a bot»


QR_SIZE = 624   # lo que ocupa en la tele (cuadros enteros, con margen negro; ver mac/qrpng.py)


def share_url(vid, at=0):
    return f"https://youtu.be/{vid}" + (f"?t={int(at)}" if at else "")


class YouTubeError(Exception):
    """gone=True: el video ya no existe para nosotros (borrado, privado, cuenta cerrada, bloqueado en el país)."""
    def __init__(self, message, gone=False):
        super().__init__(message)
        self.gone = gone


# Lo que dice yt-dlp cuando el video ya no está (a diferencia de un fallo pasajero de YouTube o de la red).
# (En inglés o en español: YouTube contesta en el idioma que se le pide, ver YT_LANG.)
GONE = re.compile(r"unavailable|no longer available|has been removed|removed by|private video|video is private|"
                  r"terminated|not available in your country|blocked it in your country|copyright|does not exist|"
                  r"no está disponible|ya no está|se eliminó|eliminad[oa]|video privado|es privado|"
                  r"se canceló|cancelad[oa]|bloque[oó]|derechos de autor|no existe", re.I)
GONE_TTL = 7 * 24 * 3600   # un video no disponible se vuelve a probar a la semana (a veces vuelven)


class _HTTPS4(http.client.HTTPSConnection):
    """Conexión HTTPS solo por IPv4."""

    def connect(self):
        family, kind, proto, _, addr = socket.getaddrinfo(self.host, self.port, socket.AF_INET,
                                                          socket.SOCK_STREAM)[0]
        sock = socket.create_connection(addr, self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class _HTTPS4Handler(urllib.request.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(_HTTPS4, req, context=self._context)


_opener = urllib.request.build_opener(_HTTPS4Handler(context=ssl.create_default_context()))


def fetch4(url, headers, timeout=20):
    check_web_url(url)   # nunca file:// ni nada que no sea de internet
    with _opener.open(urllib.request.Request(url, headers=headers), timeout=timeout) as r:
        return r.read(), r.geturl()


def find_ytdlp():
    for c in ("/opt/homebrew/bin/yt-dlp", "/usr/local/bin/yt-dlp", shutil.which("yt-dlp")):
        if c and Path(c).exists():
            return c
    return None


def video_id(text):
    text = (text or "").strip()
    if VIDEO_ID.match(text):
        return text
    m = URL_ID.search(text)
    return m.group(1) if m else None


def is_live(e):
    """¿Es una transmisión en vivo ahora? (lo que da yt-dlp, o lo que ya se guardó con live: true)."""
    return e.get("live_status") == "is_live" or e.get("is_live") is True or e.get("live") is True


def _clean_entry(e):
    vid = e.get("id") or ""
    out = {"id": vid, "title": e.get("title") or "Video de YouTube",
           "channel": e.get("channel") or e.get("uploader") or "",
           "duration": int(e.get("duration") or 0), "thumb": f"/yt/{vid}/thumb.jpg"}
    if is_live(e):   # en vivo: sin duración; cuántos la ven, si se sabe
        out["live"] = True
        out["duration"] = 0
        viewers = e.get("concurrent_view_count") or e.get("viewers")
        if viewers:
            out["viewers"] = int(viewers)
    if CHANNEL_ID.match(e.get("channel_id") or ""):   # para no recomendar canales ocultos
        out["channel_id"] = e["channel_id"]
    if epoch_of(e.get("published")):   # fecha exacta que dio yt-dlp al resolver (ver resolve)
        out["published"] = epoch_of(e["published"])
    return out


def _channel_id_in(o):
    """El primer id de canal (UC…) al que lleva algo de ese pedazo de la página (el avatar o el nombre)."""
    return next((b.get("browseId") for _, b in _find(o, ("browseEndpoint",), [])
                 if CHANNEL_ID.match(b.get("browseId") or "")), "")


def _find(o, keys, out):
    """Junta, en orden, los objetos con alguna de esas claves dentro del JSON de la página."""
    if isinstance(o, dict):
        for k, v in o.items():
            if k in keys:
                out.append((k, v))
            _find(v, keys, out)
    elif isinstance(o, list):
        for v in o:
            _find(v, keys, out)
    return out


def _seconds(text):
    """«12:34» o «1:02:03» -> segundos; None si no es una duración (p. ej. «EN VIVO»)."""
    if not text or not re.fullmatch(r"\d{1,2}(:\d{2}){1,2}", text.strip()):
        return None
    total = 0
    for part in text.strip().split(":"):
        total = total * 60 + int(part)
    return total


def _row_date(rows, now=None):
    """La fecha «hace N …» de las filas de metadatos de una tarjeta (la 2.ª: «1,2 M de vistas • hace 3 años») ->
    {published, published_approx, published_unit} o {}."""
    for row in rows or []:
        for p in row.get("metadataParts") or []:
            got = parse_ago((p.get("text") or {}).get("content") or "", now)
            if got:
                return {"published": got[0], "published_approx": True, "published_unit": got[1]}
    return {}


def parse_related(html):
    """Los videos de la columna «relacionados» de la página de un video (lo mismo que ves al lado)."""
    m = re.search(r"var ytInitialData\s*=\s*(\{.*?\});\s*</script>", html, re.S)
    if not m:
        return []
    data = json.loads(m.group(1))
    side = ((data.get("contents") or {}).get("twoColumnWatchNextResults") or {}).get("secondaryResults") or {}
    out = []
    for kind, v in _find(side, ("lockupViewModel", "compactVideoRenderer"), []):
        if kind == "lockupViewModel":   # formato actual de la página
            if v.get("contentType") != "LOCKUP_CONTENT_TYPE_VIDEO":
                continue   # listas y «mixes»
            vid = v.get("contentId") or ""
            meta = (v.get("metadata") or {}).get("lockupMetadataViewModel") or {}
            title = (meta.get("title") or {}).get("content") or ""
            rows = ((meta.get("metadata") or {}).get("contentMetadataViewModel") or {}).get("metadataRows") or []
            parts = (rows[0].get("metadataParts") or []) if rows else []
            channel = ((parts[0].get("text") or {}).get("content") or "") if parts else ""
            badges = [b.get("text") for _, b in _find(v.get("contentImage") or {}, ("thumbnailBadgeViewModel",), [])]
            duration = next((d for d in map(_seconds, badges) if d), None)
            # El avatar lleva al canal (en una colaboración, el primero es el dueño del video).
            channel_id = _channel_id_in(meta.get("image") or {}) or _channel_id_in(meta)
            date = _row_date(rows[1:])
        else:                              # formato anterior
            vid = v.get("videoId") or ""
            title = (v.get("title") or {}).get("simpleText") or ""
            channel = "".join(r.get("text", "") for r in (v.get("longBylineText") or {}).get("runs") or [])
            duration = _seconds((v.get("lengthText") or {}).get("simpleText"))
            channel_id = _channel_id_in(v.get("longBylineText") or {})
            date = ({"published": got[0], "published_approx": True, "published_unit": got[1]}
                    if (got := parse_ago(_text(v.get("publishedTimeText")))) else {})
        if VIDEO_ID.match(vid) and duration and duration >= MIN_RELATED_SECONDS:
            entry = {"id": vid, "title": title or "Video de YouTube", "channel": channel,
                     "duration": duration, "thumb": f"/yt/{vid}/thumb.jpg"}
            if channel_id:
                entry["channel_id"] = channel_id
            entry.update(date)
            out.append(entry)
    return out


def _text(o):
    """Texto de un pedazo de la página: {"simpleText": …} o {"runs": [{"text": …}]}."""
    if not isinstance(o, dict):
        return ""
    return o.get("simpleText") or "".join(r.get("text", "") for r in o.get("runs") or [])


def page_durations(html):
    """Todas las duraciones que trae una página de YouTube -> {id: segundos}: la lista de al lado (una lista anónima o
    de reproducción), los relacionados, los videos de un canal o de una búsqueda. Lanza ValueError si la página no
    trae los datos."""
    m = re.search(r"var ytInitialData\s*=\s*(\{.*?\});\s*</script>", html, re.S)
    if not m:
        raise ValueError("la página no trae ytInitialData")
    data = json.loads(m.group(1))
    out = {}
    kinds = ("lockupViewModel", "playlistPanelVideoRenderer", "compactVideoRenderer", "videoRenderer",
             "gridVideoRenderer", "playlistVideoRenderer")
    for kind, v in _find(data, kinds, []):
        if not isinstance(v, dict):
            continue
        if kind == "lockupViewModel":   # formato actual: la duración es la etiqueta sobre la miniatura
            if v.get("contentType") != "LOCKUP_CONTENT_TYPE_VIDEO":
                continue
            vid = v.get("contentId") or ""
            badges = [b.get("text") for _, b in _find(v.get("contentImage") or {}, ("thumbnailBadgeViewModel",), [])]
            sec = next((d for d in map(_seconds, badges) if d), None)
        else:
            vid = v.get("videoId") or ""
            sec = seconds_of(v.get("lengthSeconds")) or _seconds(_text(v.get("lengthText")))
        if VIDEO_ID.match(vid) and sec:
            out.setdefault(vid, sec)
    return out


def page_dates(html):
    """Las fechas «hace N …» que trae una página de YouTube junto a cada video (tarjetas de relacionados, canal o
    búsqueda) -> {id: (epoch aproximado, precisión en segundos)}. Sin datos, {} (nunca lanza)."""
    m = re.search(r"var ytInitialData\s*=\s*(\{.*?\});\s*</script>", html, re.S)
    if not m:
        return {}
    try:
        data = json.loads(m.group(1))
    except ValueError:
        return {}
    out = {}
    for kind, v in _find(data, ("lockupViewModel", "compactVideoRenderer", "videoRenderer", "gridVideoRenderer"), []):
        if not isinstance(v, dict):
            continue
        if kind == "lockupViewModel":
            if v.get("contentType") != "LOCKUP_CONTENT_TYPE_VIDEO":
                continue
            vid = v.get("contentId") or ""
            meta = (v.get("metadata") or {}).get("lockupMetadataViewModel") or {}
            rows = ((meta.get("metadata") or {}).get("contentMetadataViewModel") or {}).get("metadataRows") or []
            d = _row_date(rows[1:])
            got = (d["published"], d["published_unit"]) if d else None
        else:
            vid = v.get("videoId") or ""
            got = parse_ago(_text(v.get("publishedTimeText")))
        if VIDEO_ID.match(vid) and got:
            out.setdefault(vid, got)
    return out


class Found(dict):
    """{id: segundos} de fetch_durations, con las fechas que traía la misma página en `dates`."""
    dates = {}


def fetch_durations(ids, fetch=None):
    """Duración de hasta 50 videos con UNA página (≈1,4 MB, ≈1 s): la de la lista anónima que YouTube arma con esos
    ids (watch_videos). Los que no salen no existen o no se pueden ver. -> {id: segundos}, con los relacionados de la
    página de regalo. Lanza Blocked si YouTube frena (429, su página «sorry» o el aviso de bot)."""
    fetch = fetch or (lambda url: fetch4(url, PAGE_HEADERS, timeout=30))
    try:
        body, final = fetch(BATCH_URL.format(",".join(ids)))
    except urllib.error.HTTPError as e:
        if e.code == 429 or "/sorry" in (e.geturl() or ""):
            raise Blocked(f"HTTP {e.code}") from e
        raise
    u = urllib.parse.urlsplit(final or "")
    if "/sorry" in u.path or not (u.hostname or "").endswith("youtube.com"):
        raise Blocked("página «sorry»")
    html = body.decode("utf-8", "replace")
    if BOT_PAGE.search(html):
        raise Blocked("pide confirmar que no es un bot")
    found = Found(page_durations(html))
    found.dates = page_dates(html)
    return found


AUDIO_KIND = re.compile(r"acont(?:%3D|=)([\w-]+)")
DUB_LANGS = ("es", "en")   # los doblajes que se ofrecen (si el video los tiene); el resto de idiomas sería ruido


def _attr(line, name):
    m = re.search(rf'{name}="([^"]*)"', line) or re.search(rf"{name}=([^,]*)", line)
    return m.group(1) if m else ""


def _audio_kind(line):
    """«original», «dubbed», «dubbed-auto»… de una pista de audio de la lista maestra ('' si YouTube no lo dice)."""
    m = AUDIO_KIND.search(line)
    if m:
        return m.group(1)
    return "original" if re.search(r"\boriginal\b", _attr(line, "NAME"), re.I) else ""


def filter_master(text, dub=None):
    """Deja solo las variantes que el Roku reproduce: H.264 hasta 1080p (quita VP9/AV1 y 4K). Del audio deja una sola
    pista por grupo: la ORIGINAL (YouTube ofrece hasta 20+ doblajes, muchos hechos por computadora, y el Roku o Safari
    escogían solos el del idioma del aparato); con dub="es" (u otro idioma), ese doblaje si existe."""
    lines = text.splitlines()
    groups = {}
    for i, line in enumerate(lines):
        if line.startswith("#EXT-X-MEDIA") and "TYPE=AUDIO" in line:
            groups.setdefault(_attr(line, "GROUP-ID"), []).append(i)
    keep = set()
    for idxs in groups.values():
        def pick(test):
            return next((i for i in idxs if test(lines[i])), None)
        chosen = None
        if dub:
            chosen = pick(lambda l: _audio_kind(l).startswith("dub") and _attr(l, "LANGUAGE").lower().startswith(dub))
        if chosen is None:
            chosen = pick(lambda l: _audio_kind(l) == "original")
        if chosen is None:
            chosen = pick(lambda l: "DEFAULT=YES" in l)
        keep.add(idxs[0] if chosen is None else chosen)
    out, skip_next = [], False
    for i, line in enumerate(lines):
        if skip_next:
            skip_next = False
            continue
        if line.startswith("#EXT-X-MEDIA") and "TYPE=AUDIO" in line:
            if i not in keep:
                continue
            line = re.sub(r"DEFAULT=(YES|NO)", "DEFAULT=YES", line)
            line = re.sub(r"AUTOSELECT=(YES|NO)", "AUTOSELECT=YES", line)
        if line.startswith("#EXT-X-STREAM-INF"):
            codecs = re.search(r'CODECS="([^"]+)"', line)
            res = re.search(r"RESOLUTION=\d+x(\d+)", line)
            if not codecs or "avc1" not in codecs.group(1) or (res and int(res.group(1)) > MAX_HEIGHT):
                skip_next = True
                continue
        out.append(line)
    return "\n".join(out) + "\n"


def _xtags(url):
    m = re.search(r"xtags(?:%3D|=)([^/;&]*)", url)
    return m.group(1) if m else ""


def dubs_of(data):
    """Doblajes que ofrece YouTube para el video, solo en los idiomas de DUB_LANGS: [{lang, name}] (puede ser [])."""
    found = {}
    for f in data.get("formats") or []:
        note, lang = f.get("format_note") or "", (f.get("language") or "").lower()
        if f.get("vcodec") == "none" and "dubbed" in note.lower():
            short = lang.split("-")[0]
            if short in DUB_LANGS and short not in found:
                found[short] = {"lang": short, "name": {"es": "Español", "en": "Inglés"}[short]}
    return [found[k] for k in DUB_LANGS if k in found]


def _chapters(data):
    """Capítulos del video ([{start,end,title}]), como los da yt-dlp; [] si no tiene."""
    out = []
    for c in data.get("chapters") or []:
        try:
            start = float(c.get("start_time") or 0)
            end = float(c.get("end_time") or 0)
        except (TypeError, ValueError):
            continue
        out.append({"start": int(start), "end": int(end), "title": (c.get("title") or "").strip()})
    return out


def info_from(vid, data):
    """Los datos de un video que se guardan y se muestran, a partir de lo que dio yt-dlp (también los usa mac/offline.py
    para guardar el video con los mismos campos)."""
    info = {"id": vid, "title": data.get("title"), "channel": data.get("channel") or data.get("uploader"),
            "duration": data.get("duration"), "description": (data.get("description") or "")[:3000],
            "channel_id": data.get("channel_id") or "", "chapters": _chapters(data), "published": date_of(data),
            "dubs": dubs_of(data)}
    if is_live(data):
        info.update(live=True, duration=0, viewers=data.get("concurrent_view_count") or 0)
    return info


def live_url(ref):
    """Dónde está la transmisión en vivo de ahora de un canal: «UC…», «@usuario» o un enlace de YouTube (del canal o
    de un video). -> dirección para yt-dlp, o None si no es de YouTube."""
    ref = (ref or "").strip()
    if CHANNEL_ID.match(ref):
        return f"https://www.youtube.com/channel/{ref}/live"
    if HANDLE.match(ref):
        return f"https://www.youtube.com/{ref}/live"
    u = urllib.parse.urlsplit(ref)
    host = (u.hostname or "").lower()
    if u.scheme not in ("http", "https") or not (host == "youtu.be" or host.endswith("youtube.com")):
        return None
    m = re.match(r"^/(channel/UC[\w-]{22}|@[\w.\-]+|c/[^/]+|user/[^/]+)", u.path)
    if m:
        return f"https://www.youtube.com/{m.group(1)}/live"
    vid = video_id(ref)
    return f"https://www.youtube.com/watch?v={vid}" if vid else None


def channel_url(ref):
    """«UC…», «@usuario» o una dirección de YouTube -> la pestaña de videos del canal; None si no sirve."""
    ref = (ref or "").strip()
    if CHANNEL_ID.match(ref):
        return f"https://www.youtube.com/channel/{ref}/videos"
    if HANDLE.match(ref):
        return f"https://www.youtube.com/{ref}/videos"
    u = urllib.parse.urlsplit(ref)
    if u.scheme in ("http", "https") and (u.hostname or "").endswith("youtube.com") and \
            re.match(r"^/(channel/UC[\w-]{22}|@[\w.\-]+|c/[^/]+|user/[^/]+)", u.path):
        base = re.match(r"^/(?:channel/[^/]+|@[^/]+|c/[^/]+|user/[^/]+)", u.path).group(0)
        return f"https://www.youtube.com{base}/videos"
    return None


class YouTube:
    def __init__(self, data_dir, cache_dir, ytdlp=None):
        self.ytdlp = ytdlp or find_ytdlp()
        self.history_file = Path(data_dir) / "youtube.json"
        self.gone_file = Path(data_dir) / "youtube_no_disponibles.json"   # id -> {"at", "title"}
        self.thumbs = Path(cache_dir) / "posters"
        self.thumbs.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.offline = None   # mac/offline.py: videos guardados en la computadora (se pone al armar la App)
        self.streams = {}   # id -> {"master", "headers", "info", "at"}
        self.moved = {}     # dirección de una variante que caducó -> la misma variante en una lista nueva (playlist)
        self.related_cache = {}   # id -> (cuándo, [videos relacionados])
        self.avatar_failed = {}   # canal -> cuándo no se pudo bajar su foto (se reintenta en un día)
        self.avatar_slots = threading.Semaphore(AVATAR_AT_ONCE)
        self.listing_cache = {}   # clave -> (cuándo, resultado) de canales y listas
        try:
            self.history = json.loads(self.history_file.read_text())
        except (OSError, ValueError):
            self.history = []
        try:
            self.gone = json.loads(self.gone_file.read_text())
        except (OSError, ValueError):
            self.gone = {}
        # Duración de cada video que pasa por aquí (lo visto, listados, relacionados, búsquedas): mac/ytdurations.py.
        self.durations = Durations(Path(data_dir) / "youtube_duraciones.json")
        self.durations.learn(self.history)
        self.durations.learn_dates(self.history)

    @property
    def available(self):
        return bool(self.ytdlp)

    def _run(self, args, timeout=60):
        if not self.ytdlp:
            raise YouTubeError("Falta yt-dlp en la computadora (brew install yt-dlp).")
        try:
            out = subprocess.run([self.ytdlp, "--force-ipv4", "--no-warnings", "-J",
                                  "--extractor-args", f"youtube:lang={YT_LANG}", *args],
                                 capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired as e:
            raise YouTubeError("YouTube tardó demasiado en responder.") from e
        if out.returncode != 0 or not out.stdout.strip():
            err = (out.stderr or "").strip().splitlines()
            reason = err[-1] if err else "sin respuesta"
            if GONE.search(reason):
                raise YouTubeError("ya no está disponible en YouTube", gone=True)
            if "Sign in" in reason or "age" in reason.lower():
                raise YouTubeError("YouTube pide iniciar sesión para ver este video (edad o privado).")
            raise YouTubeError(f"YouTube no dio el video: {reason[:160]}")
        return json.loads(out.stdout)

    # ---------- buscar ----------

    def search(self, query, page=1, live=False):
        """Resultados de una búsqueda, de SEARCH_PAGE en SEARCH_PAGE: page=2 trae los que siguen («Cargar más»).
        live: solo transmisiones en vivo ahora (el filtro de YouTube). -> (videos, ¿hay más?). Un enlace a un video o a
        una lista no tiene más páginas."""
        query = (query or "").strip()
        if not query:
            return [], False
        vid = video_id(query)
        if vid:
            return [_clean_entry(self.resolve(vid)["info"])], False
        if query.startswith("http") and "list=" in query:
            data = self._run(["--flat-playlist", "--playlist-end", "50", query])
            more = False
        elif live:
            page = min(max(int(page or 1), 1), SEARCH_PAGES)
            url = f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(query)}&sp={LIVE_FILTER}"
            data = self._run(["--flat-playlist", "--playlist-start", str((page - 1) * SEARCH_PAGE + 1),
                              "--playlist-end", str(page * SEARCH_PAGE), url], timeout=60 + 15 * page)
            more = page < SEARCH_PAGES and len(data.get("entries") or []) >= SEARCH_PAGE
        else:
            page = min(max(int(page or 1), 1), SEARCH_PAGES)
            # yt-dlp lee las páginas de resultados de YouTube en orden: para la página 2 vuelve a pasar por la 1, pero
            # solo entrega las nuevas.
            data = self._run(["--flat-playlist", "--playlist-start", str((page - 1) * SEARCH_PAGE + 1),
                              f"ytsearch{page * SEARCH_PAGE}:{query}"], timeout=60 + 15 * page)
            more = page < SEARCH_PAGES and len(data.get("entries") or []) >= SEARCH_PAGE
        videos = [_clean_entry(e) for e in data.get("entries") or [] if VIDEO_ID.match(e.get("id") or "")]
        return self.durations.apply(videos), more

    # ---------- relacionados (reproducción continua) ----------

    def related(self, vid):
        """Los relacionados que YouTube muestra junto al video. Si la página cambia de formato, el «Mix»
        de YouTube (su lista automática, que solo existe para música) con yt-dlp."""
        with self.lock:
            hit = self.related_cache.get(vid)
        if hit and time.time() - hit[0] < RELATED_TTL:
            return hit[1]
        videos = []
        try:
            body, _ = fetch4(f"https://www.youtube.com/watch?v={vid}&hl=es&gl=MX", PAGE_HEADERS)
            html = body.decode("utf-8", "replace")
            videos = parse_related(html)
            self.durations.learn(page_durations(html))   # también los que no se recomiendan (cortos, listas)
            self.durations.learn_dates(page_dates(html))
        except (urllib.error.URLError, OSError, ValueError):
            pass
        if not videos and self.ytdlp:
            try:
                data = self._run(["--flat-playlist", "--yes-playlist", "--playlist-end", "15",
                                  f"https://www.youtube.com/watch?v={vid}&list=RD{vid}"])
                videos = [_clean_entry(e) for e in data.get("entries") or []
                          if VIDEO_ID.match(e.get("id") or "") and e.get("id") != vid]
            except YouTubeError:
                pass
        self.durations.apply(videos, want=False)   # aprende duración y fecha (y les pone la que se sepa)
        with self.lock:
            self.related_cache[vid] = (time.time(), videos)
        return videos

    def next_after(self, vid, avoid=(), skip=None):
        """El primer relacionado que no se haya visto hace poco (como la reproducción automática de YouTube).
        skip(video) -> True para saltarlo (p. ej. si es de un canal oculto)."""
        avoid = set(avoid) | {vid} | {h["id"] for h in self.recent()}
        return next((v for v in self.related(vid) if v["id"] not in avoid and not (skip and skip(v))), None)

    # ---------- canales y listas ----------

    def _listing(self, key, url, extra, id_, default_title):
        with self.lock:
            hit = self.listing_cache.get(key)
        if hit and time.time() - hit[0] < LISTING_TTL:
            self.durations.apply(hit[1]["videos"])   # con las que se hayan sabido después
            return hit[1]
        data = self._run(["--flat-playlist", *extra, url], timeout=90)
        title = re.sub(r"\s+-\s+(Videos|Vídeos)$", "", data.get("title") or data.get("channel") or "")
        videos = []
        for e in data.get("entries") or []:
            if VIDEO_ID.match(e.get("id") or ""):
                v = _clean_entry(e)
                if key[0] == "c":
                    v["channel"] = v["channel"] or title
                videos.append(v)
        self.durations.apply(videos)   # aprende las que trae yt-dlp y pide las que falten
        result = {"id": (data.get("channel_id") if key[0] == "c" else None) or data.get("id") or id_, "title": title or default_title,
                  "videos": videos}
        with self.lock:
            self.listing_cache[key] = (time.time(), result)
        return result

    def channel(self, ref):
        """Últimos videos de un canal (ref = UC…, @usuario o dirección)."""
        url = channel_url(ref)
        if not url:
            raise YouTubeError("Ese no parece un canal de YouTube.")
        return self._listing(("c", url), url, ["--playlist-end", str(CHANNEL_VIDEOS)], ref, "Canal")

    def playlist_videos(self, list_id):
        list_id = (list_id or "").strip()
        if not LIST_ID.match(list_id):
            raise YouTubeError("Esa no parece una lista de YouTube.")
        return self._listing(("l", list_id), f"https://www.youtube.com/playlist?list={list_id}",
                             ["--playlist-end", str(PLAYLIST_MAX)], list_id, "Lista")

    # ---------- el video ----------

    def is_gone(self, vid):
        """¿Se supo hace poco que este video ya no está en YouTube?"""
        with self.lock:
            g = self.gone.get(vid)
        return bool(g) and time.time() - g.get("at", 0) < GONE_TTL

    def _mark_gone(self, vid):
        title = self.title_of(vid) or ""   # fuera del candado: title_of también lo toma
        with self.lock:
            self.gone[vid] = {"at": time.time(), "title": title}
            data = dict(self.gone)
        try:
            tmp = self.gone_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1))
            tmp.replace(self.gone_file)
        except OSError:
            pass

    def resolve(self, vid, force=False):
        """Lista maestra HLS del video (sin anuncios) y sus datos; se reutiliza unas horas. Si el video ya no está
        en YouTube lanza YouTubeError(gone=True), y durante una semana lo sabe sin volver a preguntar."""
        saved = self.offline.info(vid) if self.offline else None
        if saved:   # guardado en la computadora: sin internet, y aunque YouTube ya lo haya borrado (mac/offline.py)
            return {"master": None, "headers": {}, "at": time.time(), "info": saved, "offline": True}
        with self.lock:
            s = self.streams.get(vid)
        if s and not force and time.time() - s["at"] < (LIVE_TTL if s["info"].get("live") else RESOLVE_TTL):
            return s
        if not force and self.is_gone(vid):
            raise YouTubeError("ya no está disponible en YouTube", gone=True)
        try:
            data = self._run([f"https://www.youtube.com/watch?v={vid}"])
        except YouTubeError as e:
            if e.gone:
                self._mark_gone(vid)
            raise
        return self._keep_stream(vid, data)

    def _keep_stream(self, vid, data):
        """Guarda (unas horas) la lista maestra HLS que dio yt-dlp para este video. Lanza YouTubeError si no hay."""
        hls = next((f for f in data.get("formats") or [] if f.get("protocol") == "m3u8_native" and f.get("manifest_url")), None)
        if not hls:
            raise YouTubeError("Este video no tiene versión para pasar a la TV (¿es un estreno que todavía no empieza?).")
        s = {"master": hls["manifest_url"], "headers": hls.get("http_headers") or {}, "at": time.time(),
             "info": info_from(vid, data)}
        with self.lock:
            self.streams[vid] = s
        return s

    def live_now(self, ref):
        """La transmisión en vivo de ahora de un canal (ver live_url). Deja resuelto el video (la TV lo pide enseguida).
        -> sus datos (id, title, channel, channel_id…) o YouTubeError si no es de YouTube o no está transmitiendo."""
        url = live_url(ref)
        if not url:
            raise YouTubeError("Ese no parece un canal ni un video de YouTube.")
        try:
            data = self._run([url])
        except YouTubeError as e:
            if re.search(r"not (currently )?live|no.*live stream|does not have a live|is not live", str(e), re.I):
                raise YouTubeError("Ese canal no está transmitiendo en vivo ahora.") from e
            raise
        if not is_live(data) or not VIDEO_ID.match(data.get("id") or ""):
            raise YouTubeError("Ese canal no está transmitiendo en vivo ahora.")
        return self._keep_stream(data["id"], data)["info"]

    def cached_info(self, vid):
        """Datos del video si ya se resolvieron hace poco; None si no (nunca pide nada a internet)."""
        with self.lock:
            s = self.streams.get(vid)
        return s["info"] if s and time.time() - s["at"] < RESOLVE_TTL else None

    def playlist(self, vid, url=None, dub=None):
        """Lista (maestra o de una variante) con las direcciones cambiadas para que pasen por la Mac. Si YouTube ya no
        acepta la dirección (caduca en ~6 h: una transmisión en vivo larga, o un video en pausa toda la tarde), se
        vuelve a pedir el video y se usa la misma variante (mismo itag) de la lista nueva."""
        s = self.resolve(vid)
        with self.lock:
            target = self.moved.get(url, url) if url else None
        try:
            body, final = fetch4(target or s["master"], s["headers"])
        except urllib.error.HTTPError as e:
            if e.code not in (403, 404, 410):
                raise
            s = self.resolve(vid, force=True)
            if url is None:
                body, final = fetch4(s["master"], s["headers"])
            else:
                fresh = self._same_variant(s, url)
                if not fresh:
                    raise
                with self.lock:
                    self.moved[url] = fresh
                body, final = fetch4(fresh, s["headers"])
        text = body.decode("utf-8", "replace")
        if url is None:
            text = filter_master(text, dub)
            self.remember(s["info"])
        return rewrite_playlist(text, final, f"/yt/{vid}")

    def _same_variant(self, s, old_url):
        """En la lista maestra nueva, la variante (o pista de audio) con el mismo itag que old_url; None si no hay."""
        m = ITAG.search(old_url)
        if not m:
            return None
        body, final = fetch4(s["master"], s["headers"])
        for line in body.decode("utf-8", "replace").splitlines():
            uri = re.search(r'URI="([^"]+)"', line).group(1) if 'URI="' in line else (line.strip() if line and not line.startswith("#") else "")
            if uri and ITAG.search(uri) and ITAG.search(uri).group(1) == m.group(1) \
                    and _xtags(uri) == _xtags(old_url):   # una pista de audio: además, el mismo idioma
                return urllib.parse.urljoin(final, uri)
        return None

    def segment(self, vid, url):
        s = self.resolve(vid)
        body, _ = fetch4(url, s["headers"], timeout=30)
        media_type = "video/mp2t" if body[:1] == b"\x47" else "audio/aac" if body[:3] == b"ID3" else "video/mp4"
        return body, media_type

    def thumbnail(self, vid, hd=False):
        """Miniatura del video. hd: la de 1280×720 (para agrandarla en una tarjeta vertical); si el video no la
        tiene, la de 4:3 sin sus franjas negras de arriba y abajo."""
        path = self.thumbs / (f"yt-{vid}-hd.jpg" if hd else f"yt-{vid}.jpg")
        if not path.exists():
            names = ("hq720.jpg", "maxresdefault.jpg", "sddefault.jpg", "hqdefault.jpg") if hd \
                else ("mqdefault.jpg", "hqdefault.jpg")
            for name in names:
                try:
                    body, _ = fetch4(f"https://i.ytimg.com/vi/{vid}/{name}", {"User-Agent": "Mozilla/5.0"})
                except (urllib.error.URLError, OSError):
                    continue
                path.write_bytes(body)
                if hd and name in ("sddefault.jpg", "hqdefault.jpg"):   # 4:3 con franjas: se deja el 16:9 del centro
                    tmp = path.with_suffix(".tmp.jpg")
                    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(path), "-vf", "crop=iw:iw*9/16",
                                        "-q:v", "3", str(tmp)], capture_output=True, timeout=20, stdin=subprocess.DEVNULL)
                    if r.returncode == 0:
                        tmp.replace(path)
                    tmp.unlink(missing_ok=True)
                break
        return path if path.exists() else None

    def qr(self, vid):
        """Código QR del enlace al video, para abrirlo o compartirlo desde el teléfono."""
        path = self.thumbs / f"qr-oscuro-{vid}.png"
        if not path.exists():
            # En fondo oscuro, como el resto de One TV: cuadritos claros sobre negro (Python puro, mac/qrpng.py).
            try:
                write_qr(share_url(vid), path, QR_SIZE)
            except OSError:
                pass
        return path if path.exists() else None

    # ---------- foto de un canal ----------

    def channel_avatar(self, cid, fetch=None):
        """Foto del canal en círculo (PNG con lo de afuera transparente): la de su página de YouTube. Se baja una
        vez y se guarda; si no se pudo, se reintenta en un día. -> ruta o None."""
        if not CHANNEL_ID.match(cid or ""):
            return None
        path = self.thumbs / f"canal-{cid}.png"
        if path.exists():
            return path
        with self.lock:
            if time.time() - self.avatar_failed.get(cid, 0) < AVATAR_RETRY:
                return None
        fetch = fetch or (lambda url, headers: fetch4(url, headers))
        with self.avatar_slots:   # pocas a la vez: la página de un canal pesa ~1 MB
            if path.exists():
                return path
            src = path.with_suffix(".src")
            try:
                body, _ = fetch(f"https://www.youtube.com/channel/{cid}", PAGE_HEADERS)
                m = AVATAR_META.search(body.decode("utf-8", "replace"))
                if not m:
                    raise ValueError("la página del canal no trae foto")
                img, _ = fetch(re.sub(r"=s\d+", f"=s{AVATAR_SIZE * 2}", html_unescape(m.group(1)), count=1),
                               {"User-Agent": "Mozilla/5.0"})
                src.write_bytes(img)
                # El doble de grande, se recorta en círculo y se achica: el borde queda suave.
                r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vf",
                                    f"scale={AVATAR_SIZE * 2}:{AVATAR_SIZE * 2}:force_original_aspect_ratio=increase,"
                                    f"crop={AVATAR_SIZE * 2}:{AVATAR_SIZE * 2},format=rgba,"
                                    "geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='255*lt(hypot(X-W/2+0.5,Y-H/2+0.5),W/2)',"
                                    f"scale={AVATAR_SIZE}:{AVATAR_SIZE}:flags=area", "-frames:v", "1", str(path)],
                                   capture_output=True, timeout=30, stdin=subprocess.DEVNULL)
                if r.returncode != 0 or not path.exists():
                    raise OSError("ffmpeg no pudo recortar la foto")
            except (urllib.error.URLError, OSError, ValueError, subprocess.TimeoutExpired):
                path.unlink(missing_ok=True)
                with self.lock:
                    self.avatar_failed[cid] = time.time()
                return None
            finally:
                src.unlink(missing_ok=True)
        return path

    # ---------- vistos hace poco ----------

    def remember(self, info):
        entry = _clean_entry(info)
        entry["t"] = time.time()
        self.durations.learn([entry])   # la que dio yt-dlp al reproducir
        self.durations.learn_dates([entry])
        with self.lock:
            self.history = [entry] + [h for h in self.history if h["id"] != entry["id"]]
            self.history = self.history[:HISTORY_MAX]
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.history_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.history, ensure_ascii=False))
            tmp.replace(self.history_file)

    def recent(self, limit=RECENT_SHOWN):
        with self.lock:
            return [dict(h) for h in self.history[:limit]]

    def known(self, vid):
        """Título, canal y duración de un video ya visto (o None): para pintar «Seguir viendo»."""
        with self.lock:
            return next((dict(h) for h in self.history if h["id"] == vid), None)

    def title_of(self, vid):
        with self.lock:
            s = self.streams.get(vid)
            if s:
                return s["info"]["title"]
            return next((h["title"] for h in self.history if h["id"] == vid), "")

