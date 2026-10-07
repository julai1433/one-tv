"""Cuenta de YouTube del usuario: importa el Google Takeout y arma «Nuevos de tus canales» con el RSS.

Takeout (a mano, una vez): suscripciones, listas de reproducción e historial. Los archivos se
reconocen por su CONTENIDO, no por su nombre, porque Google traduce carpetas y archivos según el
idioma de la cuenta («suscripciones.csv», «historial-de-reproducciones.json»…) y cambia el formato
de vez en cuando. RSS: cada canal tiene https://www.youtube.com/feeds/videos.xml?channel_id=UC…
(Atom, ~15 videos, sin cuenta ni cuota; nada de cookies, así no hay riesgo de bloqueo).
"""

import csv
import hashlib
import io
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from pathlib import Path

from youtube import YT_LANG, _find, _seconds, fetch4
from ytdurations import AGO, AGO_SECONDS

CHANNEL_ID = re.compile(r"^UC[\w-]{22}$")
VIDEO_ID = re.compile(r"^[\w-]{11}$")
PLAYLIST_ID = re.compile(r"^[A-Za-z]{2}[\w-]{10,}$")
STAMP = re.compile(r"^\d{4}-\d{2}-\d{2}")
WATCH_URL = re.compile(r"(?:watch\?v=|youtu\.be/)([\w-]{11})")
WATCHED_PREFIX = re.compile(r"^(?:Watched|Has visto|Viste|Visto|Vista)\s+", re.I)
ADS = re.compile(r"google\s*ads|anuncios\s+de\s+google", re.I)   # «From Google Ads» / «De los anuncios de Google»
TITLE_KEYS = ("title", "título", "titulo", "nombre", "name")
SKIP_TITLE_KEYS = ("original", "language", "idioma", "lang")
FEED_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={}"
FEED_HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/140.0 Safari/537.36"}
OEMBED_URL = "https://www.youtube.com/oembed?url={}&format=json"
OEMBED_MAX = 60        # títulos que se piden por video en una sola llamada; el resto sale en la siguiente
OEMBED_WORKERS = 6
PRIVATE_TITLE = "Video privado"
PRIVATE_RETRY = 30 * 24 * 3600   # un video sin título público se vuelve a intentar al mes
PRIVATE_LIST_RETRY = 24 * 3600   # una lista privada no se vuelve a pedir a yt-dlp en un día
LISTED_RETRY = 24 * 3600         # a una lista pública se le piden las duraciones que falten una vez al día
BATCH = 4            # peticiones a la vez
# El RSS de YouTube contesta 404 o 500 al azar aunque el canal exista (sep 2026: ~la mitad de las veces y, si se
# le insiste, a todo). Por eso: un reintento, dejar de insistir si los primeros canales fallan todos, y leer la
# página «Videos» del canal (más pesada, ~1 MB) para los que falten, pocos por revisión.
FEED_TRIES = 2
FEED_RETRY_PAUSE = 2.0   # segundos antes del reintento
FEED_BREAKER = 12        # si estos primeros canales fallan todos, YouTube está frenando el RSS: no se sigue
PAGE_MAX = 25            # canales que se leen por su página en cada revisión (los más atrasados primero)
PAGE_URL = "https://www.youtube.com/channel/{}/videos?hl=" + YT_LANG   # títulos originales (ver YT_LANG)
# La fecha que muestra la página: «hace 1 día» (o «1 day ago» si YouTube contesta en inglés).
# (AGO y AGO_SECONDS viven en ytdurations, que también los usa.)
MAX_DISMISSED = 5000  # «No me interesa» que se recuerdan (los más viejos se olvidan)
GONE_AFTER = 3       # revisiones seguidas en que la página del canal da 404 antes de darlo por desaparecido
BATCH_PAUSE = 0.5    # segundos entre tandas
SETTLE = 20          # un zip (o una carpeta) modificado hace menos de esto aún se está descargando
TAKEOUT_GLOBS = ("takeout-*.zip", "Takeout", "Takeout *", "takeout-*")   # Safari descomprime el zip en «Takeout»
NS = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015",
      "m": "http://search.yahoo.com/mrss/"}
MONTHS = {"jan": 1, "ene": 1, "feb": 2, "mar": 3, "apr": 4, "abr": 4, "may": 5, "jun": 6, "jul": 7,
          "aug": 8, "ago": 8, "sep": 9, "set": 9, "oct": 10, "nov": 11, "dec": 12, "dic": 12}


def _epoch(text):
    """Fecha ISO (Takeout JSON, Atom) -> epoch; 0 si no se entiende."""
    try:
        dt = datetime.fromisoformat((text or "").strip().replace("Z", "+00:00"))
    except ValueError:
        return 0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def _epoch_html(text):
    """Fecha del historial en HTML, según el idioma: «Sep 12, 2024, 3:04:05 PM CEST» o
    «12 sept 2024, 15:04:05 CST». La zona horaria se ignora (hora local); 0 si no se entiende."""
    t = (text or "").replace(" ", " ").replace("\xa0", " ").lower()
    m = re.search(r"([a-záéíóú]{3,})\.?\s+(\d{1,2}),?\s+(\d{4}),?\s+(\d{1,2}):(\d{2}):(\d{2})\s*([ap]\.?m)?", t)
    if m:
        mon, day, year = m.group(1)[:3], m.group(2), m.group(3)
        h, mi, s, ap = int(m.group(4)), m.group(5), m.group(6), m.group(7)
    else:
        m = re.search(r"(\d{1,2})\s+(?:de\s+)?([a-záéíóú]{3,})\.?\s+(?:de\s+)?(\d{4}),?\s+(\d{1,2}):(\d{2}):(\d{2})\s*([ap]\.?m)?", t)
        if not m:
            return 0
        day, mon, year = m.group(1), m.group(2)[:3], m.group(3)
        h, mi, s, ap = int(m.group(4)), m.group(5), m.group(6), m.group(7)
    if mon not in MONTHS:
        return 0
    if ap:
        h = h % 12 + (12 if ap.startswith("p") else 0)
    try:
        return int(datetime(int(year), MONTHS[mon], int(day), h, int(mi), int(s)).timestamp())
    except ValueError:
        return 0


def _zip_name(info):
    """Nombre de un archivo dentro del zip. Si el zip no marcó sus nombres como UTF-8 (bit 11), zipfile
    los lee como cp437 y los acentos y emojis salen deformados («C├│digo»): se recuperan."""
    if info.flag_bits & 0x800:
        return info.filename
    try:
        return info.filename.encode("cp437").decode("utf-8")
    except UnicodeError:
        return info.filename


def _takeout_files(path):
    """(nombre, leer) de cada archivo del Takeout, venga en .zip o ya descomprimido en una carpeta."""
    if path.is_dir():
        for f in sorted(path.rglob("*")):
            if f.is_file():
                yield str(f.relative_to(path)), f.read_bytes
        return
    with zipfile.ZipFile(path) as z:
        for info in z.infolist():
            if not info.is_dir():
                yield _zip_name(info), (lambda info=info: z.read(info))


def _stamp(path):
    """(tamaño, fecha) para saber si un Takeout ya se importó; en una carpeta, la suma y el más reciente."""
    if not path.is_dir():
        st = path.stat()
        return st.st_size, st.st_mtime
    files = [f.stat() for f in path.rglob("*") if f.is_file()]
    return sum(st.st_size for st in files), max((st.st_mtime for st in files), default=path.stat().st_mtime)


def _looks_like_takeout(path):
    """Una carpeta cuenta como Takeout si trae algo de YouTube (csv o json) dentro."""
    if not path.is_dir():
        return path.suffix.lower() == ".zip"
    try:
        return any(f.suffix.lower() in (".csv", ".json") and "youtube" in str(f.relative_to(path)).lower()
                   for f in path.rglob("*"))
    except OSError:
        return False


def _decode(raw):
    for enc in ("utf-8-sig", "utf-16"):
        try:
            return raw.decode(enc)
        except UnicodeError:
            pass
    return raw.decode("latin-1")


def _norm(text):
    return re.sub(r"\W+", "", (text or "").lower())


def _name_key(text):
    """Nombre de canal comparable: sin mayúsculas ni espacios de más."""
    return " ".join((text or "").casefold().split())


name_key = _name_key


def channel_from_url(url):
    """«https://www.youtube.com/channel/UC…» (el historial del Takeout) -> «UC…»; "" si no la trae."""
    m = re.search(r"/channel/(UC[\w-]{22})", url or "")
    return m.group(1) if m else ""


def _header_title(header, row):
    """El título de la lista según la fila de encabezados (en cualquier idioma)."""
    best = None
    for i, name in enumerate(header):
        low = name.lower()
        if i >= len(row) or not row[i].strip() or not any(k in low for k in TITLE_KEYS):
            continue
        if any(k in low for k in SKIP_TITLE_KEYS):
            best = best or row[i].strip()   # «Título (original)»: solo si no hay otro
        else:
            return row[i].strip()
    return best or ""


def parse_csv(text, name=""):
    """Un CSV del Takeout, por contenido. -> {"subs": [...], "metas": [(id, título)], "videos": [(id, t)]}.
    Cubre suscripciones, listas (un CSV por lista), playlists.csv y el formato viejo (metadatos arriba)."""
    out = {"subs": [], "metas": [], "videos": []}
    header = []
    for row in csv.reader(io.StringIO(text)):
        row = [c.strip() for c in row]
        if not any(row):
            continue
        first = row[0]
        if CHANNEL_ID.match(first) and len(row) <= 4:
            url = next((c for c in row[1:] if c.startswith("http")), "")
            title = next((c for c in reversed(row[1:]) if c and not c.startswith("http")), "")
            out["subs"].append({"id": first, "title": title,
                                "url": url or f"https://www.youtube.com/channel/{first}"})
        elif VIDEO_ID.match(first) and len(row) >= 2 and STAMP.match(row[1]):
            out["videos"].append((first, _epoch(row[1])))
        elif PLAYLIST_ID.match(first) and not CHANNEL_ID.match(first) and any(STAMP.match(c) for c in row[1:]):
            out["metas"].append((first, _header_title(header, row)))
        else:
            header = row
    return out


def _entry_from_json(e):
    """Una entrada de watch-history.json -> dict del historial, o None (anuncio, borrado, no es video)."""
    url = e.get("titleUrl") or ""
    m = WATCH_URL.search(url)
    if not m:
        return None   # video borrado o búsqueda: sin enlace al video
    if any(ADS.search(str(d.get("name", ""))) for d in (e.get("details") or []) if isinstance(d, dict)):
        return None
    title = WATCHED_PREFIX.sub("", e.get("title") or "").strip()
    if title.startswith("http"):
        title = ""   # los videos que ya no existen traen la dirección como título
    sub = (e.get("subtitles") or [{}])[0] or {}
    return {"id": m.group(1), "title": title, "channel": sub.get("name", ""),
            "channel_url": sub.get("url", ""), "t": _epoch(e.get("time"))}


def parse_history_json(text):
    data = json.loads(text)
    if not isinstance(data, list) or not any(isinstance(e, dict) and ("titleUrl" in e or "time" in e)
                                             for e in data[:50]):
        return None   # otro JSON del Takeout
    out = [x for x in (_entry_from_json(e) for e in data if isinstance(e, dict)) if x]
    return out


class _HistoryHTML(HTMLParser):
    """Historial en HTML: cada entrada es un <div class="outer-cell"> con «Watched <a>título</a><br>
    <a>canal</a><br>fecha» y, aparte, «Products: YouTube · Details: From Google Ads» si es un anuncio."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.cells, self.cur, self.href = [], None, None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "div" and "outer-cell" in (a.get("class") or ""):
            self._close()
            self.cur = {"links": [], "text": []}
        elif tag == "a" and self.cur is not None:
            self.href = a.get("href") or ""
            self.cur["links"].append([self.href, ""])
            self.cur["text"].append("\x00")
        elif tag == "br" and self.cur is not None:
            self.cur["text"].append("\n")

    def handle_endtag(self, tag):
        if tag == "a":
            self.href = None

    def handle_data(self, data):
        if self.cur is None:
            return
        self.cur["text"].append(data)
        if self.href is not None and self.cur["links"]:
            self.cur["links"][-1][1] += data

    def _close(self):
        if self.cur is not None:
            self.cells.append(self.cur)
        self.cur = None

    def close(self):
        self._close()
        super().close()


def parse_history_html(text):
    if "watch?v=" not in text or "content-cell" not in text:
        return None
    p = _HistoryHTML()
    p.feed(text)
    p.close()
    out = []
    for cell in p.cells:
        body = "".join(cell["text"])
        if ADS.search(body) or not cell["links"]:
            continue
        m = WATCH_URL.search(cell["links"][0][0])
        if not m:
            continue
        title = cell["links"][0][1].strip()
        if title.startswith("http"):
            title = ""
        channel, channel_url = "", ""
        if len(cell["links"]) > 1:
            channel_url, channel = cell["links"][1][0], cell["links"][1][1].strip()
        lines = [ln.strip() for ln in body.replace("\x00", "").split("\n")]
        when = next((_epoch_html(ln) for ln in reversed(lines) if ln and _epoch_html(ln)), 0)
        out.append({"id": m.group(1), "title": title, "channel": channel,
                    "channel_url": channel_url, "t": when})
    return out


def parse_feed(xml_bytes):
    """Atom de un canal -> lista de videos (sin Shorts). Lanza ET.ParseError si no es XML."""
    root = ET.fromstring(xml_bytes)
    channel = (root.findtext("a:author/a:name", "", NS) or root.findtext("a:title", "", NS) or "").strip()
    out = []
    for e in root.findall("a:entry", NS):
        vid = (e.findtext("yt:videoId", "", NS) or "").strip()
        links = [l.get("href", "") for l in e.findall("a:link", NS)]
        if not vid or any("/shorts/" in h for h in links):
            continue
        out.append({"id": vid, "title": (e.findtext("a:title", "", NS) or "").strip(),
                    "channel": (e.findtext("a:author/a:name", "", NS) or channel).strip(),
                    "channel_id": (e.findtext("yt:channelId", "", NS) or "").strip(),
                    "published": _epoch(e.findtext("a:published", "", NS))})
    return out


def parse_channel_page(html, cid, now=None):
    """Página «Videos» de un canal -> videos como los de parse_feed, con la fecha aproximada que muestra la
    página («hace 1 día») y la duración de la etiqueta de la miniatura («12:34»; 0 si no la trae). Lanza ValueError
    si la página no trae los datos."""
    now = now or time.time()
    m = re.search(r"var ytInitialData\s*=\s*(\{.*?\});\s*</script>", html, re.S)
    if not m:
        raise ValueError("la página del canal no trae ytInitialData")
    data = json.loads(m.group(1))
    name = ((data.get("metadata") or {}).get("channelMetadataRenderer") or {}).get("title") or ""
    out = []
    for _, v in _find(data, ("lockupViewModel",), []):
        if v.get("contentType") != "LOCKUP_CONTENT_TYPE_VIDEO":
            continue
        vid = v.get("contentId") or ""
        meta = (v.get("metadata") or {}).get("lockupMetadataViewModel") or {}
        rows = ((meta.get("metadata") or {}).get("contentMetadataViewModel") or {}).get("metadataRows") or []
        labels = [p.get("accessibilityLabel") or (p.get("text") or {}).get("content") or ""
                  for r in rows for p in r.get("metadataParts") or []]
        ago = next((a for a in map(AGO.search, labels) if a), None)
        if not VIDEO_ID.match(vid) or not ago:
            continue   # estrenos y directos por venir no tienen «hace…»
        badges = [b.get("text") for _, b in _find(v.get("contentImage") or {}, ("thumbnailBadgeViewModel",), [])]
        out.append({"id": vid, "title": ((meta.get("title") or {}).get("content") or "").strip(),
                    "channel": name, "channel_id": cid,
                    "published": int(now - int(ago.group(1) or ago.group(3))
                                     * AGO_SECONDS[(ago.group(2) or ago.group(4)).lower()]),
                    "published_approx": True,
                    "published_unit": AGO_SECONDS[(ago.group(2) or ago.group(4)).lower()],
                    "duration": next((d for d in map(_seconds, badges) if d), 0)})
    return out


class YouTubeAccount:
    def __init__(self, data_dir, downloads_dir, log=print, fetch=None, oembed=None):
        self.path = Path(data_dir) / "youtube_cuenta.json"
        self.downloads = Path(downloads_dir)
        self.log = log
        self.fetch = fetch or (lambda url: fetch4(url, FEED_HEADERS, timeout=20)[0])
        self.page_fetch = lambda url: fetch4(url, {**FEED_HEADERS, "Accept-Language": f"{YT_LANG},es;q=0.9"},
                                             timeout=30)[0].decode("utf-8", "replace")
        self.pause = BATCH_PAUSE
        self.retry_pause = FEED_RETRY_PAUSE
        self.breaker = FEED_BREAKER
        self.page_max = PAGE_MAX
        self.lock = threading.RLock()
        self.refreshing = threading.Lock()
        try:
            d = json.loads(self.path.read_text())
        except (OSError, ValueError):
            d = {}
        self.imported = d.get("imported") or {}    # {"path","size","mtime","at"}
        self.subs = d.get("subscriptions", [])     # [{"id","title","url"}]
        self.lists = d.get("playlists", [])        # [{"id","title","videos":[{"id","t"}]}]
        self.history = d.get("history", [])        # [{"id","title","channel","t"}], lo más reciente primero
        self.feeds = d.get("feeds", {})            # channel_id -> {"videos","t","status"}
        self.feeds_at = d.get("feeds_at", 0)
        self.played = d.get("played", {})          # id de lista -> {"t","title","count","thumb"}: reproducidas desde la app
        # Canales que el usuario ocultó o ancló en One TV: {channel_id: {"title","at"}}. No vienen del Takeout, así que
        # reimportarlo no los toca. El orden de los anclados es el orden en que se anclaron ("at").
        self.hidden = d.get("hidden") or {}
        self.pinned = d.get("pinned") or {}
        # «No me interesa»: videos que no vuelven a recomendarse (ni en «Nuevos»): {id: cuándo}.
        self.dismissed = d.get("dismissed") or {}
        self.titles_path = Path(data_dir) / "youtube_titulos.json"
        try:
            self.titles = json.loads(self.titles_path.read_text())
        except (OSError, ValueError):
            self.titles = {}
        self.titles.setdefault("videos", {})       # id -> {"title","channel","t"} o {"private": true,"t"}
        self.titles.setdefault("private_lists", {})   # id de lista -> cuándo yt-dlp no pudo leerla
        self.titles.setdefault("listed", {})          # id de lista -> cuándo se leyó la pública por las duraciones
        self.oembed = oembed or self._oembed
        # Caché de duraciones (ytdurations.Durations) que pone la app: sin él, los videos salen con duración 0.
        self.durations = None

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"imported": self.imported, "subscriptions": self.subs,
                                   "playlists": self.lists, "history": self.history,
                                   "feeds": self.feeds, "feeds_at": self.feeds_at,
                                   "played": self.played, "hidden": self.hidden, "pinned": self.pinned,
                                   "dismissed": self.dismissed},
                                  ensure_ascii=False))
        tmp.replace(self.path)

    def _save_titles(self):
        self.titles_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.titles_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.titles, ensure_ascii=False))
        tmp.replace(self.titles_path)

    # ---------- Takeout ----------

    def import_zip(self, path):
        """Lee el Takeout (el .zip o la carpeta en que lo descomprimió el navegador) y reemplaza suscripciones,
        listas e historial. Lanza OSError/BadZipFile si no se puede abrir. Devuelve el resumen con avisos de lo
        que no se pudo leer."""
        path = Path(path).expanduser()
        size, mtime = _stamp(path)
        subs, metas, listfiles, hist_json, hist_html, warnings = {}, [], [], None, None, []
        for name, read in _takeout_files(path):
            if "__MACOSX" in name or Path(name).name.startswith("."):
                continue
            ext = Path(name).suffix.lower()
            if ext not in (".csv", ".json", ".html", ".htm"):
                continue
            try:
                text = _decode(read())
                if ext == ".csv":
                    r = parse_csv(text, name)
                    for s in r["subs"]:
                        subs.setdefault(s["id"], s)
                    metas += r["metas"]
                    if r["videos"]:
                        listfiles.append((Path(name).stem, r))
                elif ext == ".json":
                    h = parse_history_json(text)
                    if h is not None and (hist_json is None or len(h) > len(hist_json)):
                        hist_json = h
                else:
                    h = parse_history_html(text)
                    if h is not None and (hist_html is None or len(h) > len(hist_html)):
                        hist_html = h
            except (ValueError, zipfile.BadZipFile) as e:
                warnings.append(f"No pude leer {name}: {e}")
        lists = self._build_lists(metas, listfiles)
        if hist_json is not None:
            history, fmt = hist_json, "json"
        elif hist_html is not None:
            history, fmt = hist_html, "html"
            if not history:
                warnings.append("El historial viene en HTML y no pude leerlo: vuelve a pedir el Takeout con "
                                "el historial en formato JSON.")
        else:
            history, fmt = [], "ninguno"
            warnings.append("No encontré el historial de reproducciones en el zip.")
        if not subs:
            warnings.append("No encontré suscripciones en el zip.")
        history.sort(key=lambda e: -e["t"])
        with self.lock:
            self.subs = sorted(subs.values(), key=lambda s: s["title"].lower())
            self.lists = lists
            self.history = history
            self.imported = {"path": str(path), "size": size, "mtime": mtime, "at": time.time()}
            self._save()
        for w in warnings:
            self.log(f"⚠ Takeout: {w}")
        self.log(f"✓ Takeout importado: {len(self.subs)} suscripciones, {len(lists)} listas, "
                 f"{len(history)} del historial ({path.name})")
        return {"ok": True, "file": path.name, "subscriptions": len(self.subs), "playlists": len(lists),
                "history": len(history), "history_format": fmt, "warnings": warnings}

    @staticmethod
    def _build_lists(metas, listfiles):
        """Une los CSV de cada lista con sus metadatos (playlists.csv o las filas de arriba del formato viejo)."""
        by_title = {}
        for i, t in metas:
            if t:
                by_title.setdefault(_norm(t), []).append((i, t))
        out, used = [], set()
        for stem, r in listfiles:
            # «Mi lista-videos», «Mi lista videos» o, si dos listas se llaman casi igual, «mi lista videos(1)»
            title = re.sub(r"[-_ ]+v[ií]deos?(?:\s*\(\d+\))?$", "", stem, flags=re.I).strip() or stem
            if r["metas"]:   # formato viejo: los metadatos vienen dentro del mismo archivo
                pid, mtitle = r["metas"][0]
                title = mtitle or title
            else:   # la que se llama exactamente igual; si no, la primera parecida que siga libre
                free = [c for c in by_title.get(_norm(title), []) if c[0] not in used]
                pid, mtitle = ([c for c in free if c[1] == title] or free or [("", "")])[0]
                title = mtitle or title
            if pid:
                used.add(pid)
            seen, vids = set(), []
            for vid, t in r["videos"]:
                if vid not in seen:
                    seen.add(vid)
                    vids.append({"id": vid, "t": t})
            out.append({"id": pid, "title": title, "videos": vids})
        for pid, title in metas:   # listas de playlists.csv sin CSV propio (vacías o no exportadas)
            if pid not in used and title and not any(p["title"] == title for p in out):
                out.append({"id": pid, "title": title, "videos": []})
        return out

    def scan_downloads(self):
        """Busca en Descargas el Takeout (takeout-*.zip, o la carpeta «Takeout» si el navegador lo descomprimió);
        si el más reciente es nuevo lo importa. No borra ni mueve nada. Devuelve el resumen o None si no había
        nada nuevo."""
        try:
            found = {p for pattern in TAKEOUT_GLOBS for p in self.downloads.glob(pattern)}
            stamps = {p: _stamp(p) for p in found if _looks_like_takeout(p)}
        except OSError:
            return None
        if not stamps:
            return None
        newest = max(stamps, key=lambda p: stamps[p][1])
        size, mtime = stamps[newest]
        if time.time() - mtime < SETTLE:
            return None   # todavía se está descargando
        with self.lock:
            same = (self.imported.get("path") == str(newest) and self.imported.get("size") == size
                    and self.imported.get("mtime") == mtime)
        if same:
            return None
        try:
            return self.import_zip(newest)
        except (OSError, zipfile.BadZipFile) as e:
            self.log(f"⚠ No pude importar {newest.name}: {e}")
            return None

    # ---------- lo importado ----------

    def subscriptions(self):
        with self.lock:
            return list(self.subs)

    def playlists(self):
        with self.lock:
            return [{"id": p["id"], "title": p["title"], "count": len(p["videos"])} for p in self.lists]

    @staticmethod
    def list_key(p):
        """Identificador con el que la web y la tele piden una lista: el de YouTube o, si el Takeout no lo
        trajo, uno estable armado con el título."""
        return p["id"] or "tk-" + hashlib.sha1(p["title"].encode()).hexdigest()[:10]

    def playlists_ranked(self, seen=None):
        """Tus listas, la escuchada más recientemente primero. «Escuchada» = lo más reciente entre haber visto
        cualquier video de la lista (historial del Takeout y `seen`, {id de video: cuándo} de la app) y haberla
        reproducido desde la app. -> [{id, title, count, thumb, last_played, source}]"""
        seen = seen or {}
        with self.lock:
            lists = [dict(p) for p in self.lists]
            played = {k: dict(v) for k, v in self.played.items()}
            watched = {}
            for h in self.history:
                if h["t"] > watched.get(h["id"], 0):
                    watched[h["id"]] = h["t"]
        rows, keys = [], set()
        for p in lists:
            key = self.list_key(p)
            keys.add(key)
            vids = [v["id"] for v in p["videos"]]
            last = max([watched.get(v, 0) for v in vids] + [seen.get(v, 0) for v in vids]
                       + [played.get(key, {}).get("t", 0)])
            rows.append({"id": key, "title": p["title"], "count": len(vids), "last_played": int(last),
                         "thumb": f"/yt/{vids[0]}/thumb.jpg" if vids else "", "source": "takeout"})
        for key, rec in played.items():   # listas de YouTube que no son del Takeout, reproducidas desde la app
            if key not in keys:
                rows.append({"id": key, "title": rec.get("title") or "Lista", "count": rec.get("count", 0),
                             "last_played": int(rec.get("t", 0)), "thumb": rec.get("thumb", ""), "source": "youtube"})
        return sorted(rows, key=lambda r: (-r["last_played"], r["title"].lower()))

    def mark_played(self, key, title="", count=0, thumb=""):
        """Anota que la lista se reprodujo ahora desde la app."""
        with self.lock:
            self.played[key] = {"t": time.time(), "title": title, "count": count, "thumb": thumb}
            self._save()

    def find_list(self, key):
        with self.lock:
            return next((dict(p) for p in self.lists if self.list_key(p) == key), None)

    # ---------- listas del Takeout con títulos ----------

    @staticmethod
    def _oembed(vid):
        url = OEMBED_URL.format(urllib.parse.quote(f"https://www.youtube.com/watch?v={vid}", safe=""))
        return json.loads(fetch4(url, FEED_HEADERS, timeout=10)[0])

    def _cached_title(self, vid):
        rec = self.titles["videos"].get(vid)
        if not rec:
            return None
        if rec.get("private"):
            return {"title": PRIVATE_TITLE, "channel": "", "private": True} \
                if time.time() - rec.get("t", 0) < PRIVATE_RETRY else None
        return {"title": rec["title"], "channel": rec.get("channel", "")}

    def playlist(self, key, public=None, known=None, network=True):
        """Una lista del Takeout con título de cada video, o None si no es del Takeout.
        Títulos, por orden: los ya guardados, el historial del Takeout, `known(id)` (lo visto en la app),
        la lista pública de YouTube (`public(id)` -> [{id,title,channel}], una sola llamada) y, por último,
        oEmbed video por video (sin clave), con caché; «Video privado» si no hay forma.
        Duraciones: las del caché (self.durations); si faltan, la lista pública (una vez al día) y, lo que siga
        faltando, el rellenador en segundo plano.
        Con network=False no se pide nada a internet. -> {id, title, videos: [{id,title,channel,duration,thumb,
        private?}]} """
        p = self.find_list(key)
        if not p:
            return None
        vids = [v["id"] for v in p["videos"]]
        found, changed = {}, False
        with self.lock:
            hist = {}
            for h in self.history:
                if h.get("title") and h["id"] not in hist:
                    hist[h["id"]] = {"title": h["title"], "channel": h.get("channel", "")}
        for vid in vids:
            got = self._cached_title(vid) or hist.get(vid)
            if not got and known:
                rec = known(vid)
                got = {"title": rec["title"], "channel": rec.get("channel", "")} if rec and rec.get("title") else None
            if got:
                found[vid] = got
        missing = [v for v in vids if v not in found]
        # Duraciones: si faltan, la lista pública las trae todas en una sola llamada (a lo más una vez al día, y nada
        # mientras YouTube esté frenando). Las que sigan faltando las pide el rellenador (ver apply, al final).
        dur = self.durations
        need_durations = bool(dur) and not dur.blocked() and \
            time.time() - self.titles["listed"].get(p["id"], 0) > LISTED_RETRY and \
            any(dur.worth_asking(v) for v in vids if not found.get(v, {}).get("private"))
        if (missing or need_durations) and network and public and p["id"] and \
                time.time() - self.titles["private_lists"].get(p["id"], 0) > PRIVATE_LIST_RETRY:
            try:
                listed = {e["id"]: e for e in public(p["id"]) or []}
                if need_durations:
                    self.titles["listed"][p["id"]] = time.time()
                    changed = True
            except Exception:  # noqa: BLE001 - lista privada o sin internet: se sigue con oEmbed
                listed = {}
                self.titles["private_lists"][p["id"]] = time.time()
                changed = True
            if dur:
                dur.learn(list(listed.values()))
            for vid in missing:
                e = listed.get(vid)
                if e and e.get("title"):
                    found[vid] = {"title": e["title"], "channel": e.get("channel", "")}
                    self.titles["videos"][vid] = {"title": found[vid]["title"], "channel": found[vid]["channel"],
                                                  "t": time.time()}
                    changed = True
            missing = [v for v in vids if v not in found]
        if missing and network:
            def ask(vid):
                try:
                    data = self.oembed(vid)
                    return vid, {"title": data.get("title") or "", "channel": data.get("author_name") or ""}
                except urllib.error.HTTPError as e:
                    return vid, ("private" if e.code in (400, 401, 403, 404) else None)
                except (OSError, ValueError):
                    return vid, None   # sin internet o límite de consultas: se intenta otra vez después
            with ThreadPoolExecutor(OEMBED_WORKERS) as pool:
                for vid, res in pool.map(ask, missing[:OEMBED_MAX]):
                    if res == "private":
                        self.titles["videos"][vid] = {"private": True, "t": time.time()}
                        found[vid] = {"title": PRIVATE_TITLE, "channel": "", "private": True}
                        changed = True
                    elif res and res["title"]:
                        self.titles["videos"][vid] = {**res, "t": time.time()}
                        found[vid] = res
                        changed = True
        if changed:
            with self.lock:
                self._save_titles()
        videos = []
        for vid in vids:
            got = found.get(vid) or {"title": "Video de YouTube", "channel": ""}
            entry = {"id": vid, "title": got["title"], "channel": got.get("channel", ""), "duration": 0,
                     "thumb": f"/yt/{vid}/thumb.jpg"}
            if got.get("private"):
                entry["private"] = True
            videos.append(entry)
        if dur:
            dur.apply(videos, want=network)
        return {"id": key, "title": p["title"], "videos": videos}

    def watch_history(self, limit=None):
        with self.lock:
            rows = list(self.history)
        return rows[:limit] if limit else rows

    # ---------- canales ocultos y anclados (de One TV, no del Takeout) ----------

    def _title_of(self, cid, title=""):
        """El título de un canal: el que se manda, el de la suscripción o el que ya estaba guardado."""
        title = (title or "").strip()[:200]
        if title:
            return title
        sub = next((s for s in self.subs if s["id"] == cid), None)
        return (sub or {}).get("title") or (self.pinned.get(cid) or self.hidden.get(cid) or {}).get("title") or ""

    def hide_channel(self, cid, title=""):
        """Oculta un canal: sale de «Tus canales», no se revisa y sus videos no se recomiendan. Si estaba anclado,
        deja de estarlo (ocultar es más fuerte). Lanza ValueError si no es un id de canal."""
        if not CHANNEL_ID.match(cid or ""):
            raise ValueError("Ese no parece un canal de YouTube.")
        with self.lock:
            self.hidden[cid] = {"title": self._title_of(cid, title), "at": time.time()}
            self.pinned.pop(cid, None)
            self._save()

    def unhide_channel(self, cid):
        with self.lock:
            if self.hidden.pop(cid, None) is not None:
                self._save()

    def pin_channel(self, cid, title="", on=True):
        """Ancla (o desancla) un canal: los anclados van primero en «Tus canales», en el orden en que se anclaron.
        Anclar un canal oculto lo vuelve a mostrar. Devuelve si quedó anclado. Lanza ValueError si no es un canal."""
        if not CHANNEL_ID.match(cid or ""):
            raise ValueError("Ese no parece un canal de YouTube.")
        with self.lock:
            if on:
                old = self.pinned.get(cid) or {}
                self.pinned[cid] = {"title": self._title_of(cid, title), "at": old.get("at") or time.time()}
                self.hidden.pop(cid, None)
            else:
                self.pinned.pop(cid, None)
            self._save()
            return cid in self.pinned

    def channel_title(self, cid):
        with self.lock:
            return self._title_of(cid) or cid

    def channel_flags(self, cid):
        with self.lock:
            return {"pinned": cid in self.pinned, "hidden": cid in self.hidden}

    def hidden_channels(self):
        """[{id, title}], el ocultado más recientemente primero."""
        with self.lock:
            rows = sorted(self.hidden.items(), key=lambda kv: -kv[1].get("at", 0))
            return [{"id": cid, "title": h.get("title") or "Canal"} for cid, h in rows]

    def channels(self):
        """«Tus canales»: primero los anclados (en el orden en que se anclaron, aunque no estén en las suscripciones)
        y después las suscripciones, sin los ocultos. Cada uno con "pinned"."""
        with self.lock:
            subs = {s["id"]: s for s in self.subs}
            out = []
            for cid, p in sorted(self.pinned.items(), key=lambda kv: kv[1].get("at", 0)):
                if cid in self.hidden:
                    continue
                s = subs.get(cid) or {"id": cid, "title": p.get("title") or "Canal",
                                      "url": f"https://www.youtube.com/channel/{cid}"}
                out.append({**s, "pinned": True})
            out += [{**s, "pinned": False} for s in self.subs if s["id"] not in self.pinned and s["id"] not in self.hidden]
            return out

    def _watched_ids(self):
        """Canales que se revisan y cuyos videos salen en «Nuevos»: suscripciones visibles y anclados."""
        with self.lock:
            ids = [s["id"] for s in self.subs if s["id"] not in self.hidden]
            ids += [c for c in sorted(self.pinned, key=lambda c: self.pinned[c].get("at", 0))
                    if c not in self.hidden and c not in ids]
            return ids

    def dismiss_video(self, vid, on=True):
        """«No me interesa» (on=False: lo deshace). El video ya no se recomienda ni sale en «Nuevos»."""
        if not VIDEO_ID.match(vid or ""):
            raise ValueError("Ese no parece un video de YouTube.")
        with self.lock:
            if on:
                self.dismissed[vid] = time.time()
                if len(self.dismissed) > MAX_DISMISSED:   # los más viejos se olvidan
                    for old in sorted(self.dismissed, key=self.dismissed.get)[:len(self.dismissed) - MAX_DISMISSED]:
                        del self.dismissed[old]
            else:
                self.dismissed.pop(vid, None)
            self._save()

    def hidden_check(self):
        """-> función(video) que dice si no debe recomendarse: «No me interesa», o de un canal silenciado (por su
        channel_id, o la dirección del canal en el historial del Takeout, cuando se conoce; si no, por el nombre
        exacto del canal)."""
        with self.lock:
            ids = set(self.hidden)
            names = {_name_key(h.get("title")) for h in self.hidden.values()} - {""}
            dismissed = set(self.dismissed)

        def hidden(v):
            if not v:
                return False
            if v.get("id") in dismissed:
                return True
            if not ids:
                return False
            cid = v.get("channel_id") or channel_from_url(v.get("channel_url"))
            if cid:
                return cid in ids
            return _name_key(v.get("channel")) in names
        return hidden

    def affinity(self):
        """-> (ids, nombres): los canales que le interesan al usuario (suscripciones visibles, fijados y los que más
        aparecen en su historial del Takeout), para ordenar las recomendaciones. {channel_id: peso}, {nombre: peso}."""
        with self.lock:
            ids, names = {}, {}
            for s in self.subs:
                if s["id"] not in self.hidden:
                    ids[s["id"]] = 3
                    names[_name_key(s.get("title"))] = 3
            for cid, p in self.pinned.items():
                ids[cid] = 3
                names[_name_key(p.get("title"))] = 3
            counts = {}
            for h in self.history[:5000]:   # lo más reciente primero
                key = channel_from_url(h.get("channel_url")) or _name_key(h.get("channel"))
                if key:
                    counts[key] = counts.get(key, 0) + 1
            for key, n in counts.items():
                weight = 2 if n >= 3 else 1
                target = ids if CHANNEL_ID.match(key) else names
                target[key] = max(target.get(key, 0), weight)
            names.pop("", None)
            for cid in self.hidden:
                ids.pop(cid, None)
            return ids, names

    # ---------- RSS de los canales ----------

    def _fetch_channel(self, cid):
        """RSS del canal -> (estado, videos), estado ok | error. Un 404 del RSS no quiere decir que el canal ya no
        exista (YouTube lo contesta al azar): eso solo lo dice la página del canal."""
        for attempt in range(FEED_TRIES):
            if attempt:
                time.sleep(self.retry_pause * attempt)
            try:
                videos = parse_feed(self.fetch(FEED_URL.format(cid)))
                if self.durations:
                    self.durations.learn_dates(videos)   # el RSS trae la fecha exacta
                return "ok", videos
            except (OSError, ET.ParseError, ValueError):   # HTTPError es OSError
                pass
        return "error", []

    def _fetch_page(self, cid):
        """Página «Videos» del canal -> (estado, videos), estado ok | missing (404: el canal ya no existe) | error."""
        try:
            videos = parse_channel_page(self.page_fetch(PAGE_URL.format(cid)), cid)
            if self.durations:
                self.durations.learn(videos)
            return "ok", videos
        except urllib.error.HTTPError as e:
            return ("missing" if e.code == 404 else "error"), []
        except (OSError, ValueError):
            return "error", []

    def refresh_feeds(self):
        """Lee el RSS de cada suscripción visible y de cada canal anclado (4 a la vez, pausa entre tandas; los ocultos
        no se revisan); los que no respondan, por su página (PAGE_MAX por revisión, los más atrasados primero). Si un
        canal no responde se conserva lo que ya tenía; solo tras GONE_AFTER revisiones seguidas con la página en 404 se
        da por desaparecido (y aun así se conservan sus videos). Devuelve un resumen."""
        if not self.refreshing.acquire(blocking=False):
            return {"ok": False, "error": "Ya se están actualizando los canales."}
        try:
            ids = self._watched_ids()
            results = {}
            stopped = False
            for i in range(0, len(ids), BATCH):
                chunk = ids[i:i + BATCH]
                threads = [threading.Thread(target=lambda c=c: results.__setitem__(c, self._fetch_channel(c)))
                           for c in chunk]
                for t in threads:
                    t.start()
                for t in threads:
                    t.join()
                if len(results) >= self.breaker and all(r[0] != "ok" for r in results.values()):
                    stopped = True   # YouTube está frenando el RSS: insistir solo empeora
                    break
                if i + BATCH < len(ids):
                    time.sleep(self.pause)
            pending = [c for c in ids if results.get(c, ("error",))[0] != "ok"]
            pending.sort(key=lambda c: (self.feeds.get(c) or {}).get("t", 0))   # los más atrasados primero
            for n, cid in enumerate(pending[:self.page_max]):
                if n:
                    time.sleep(self.pause)
                results[cid] = self._fetch_page(cid)
            now = time.time()
            with self.lock:
                feeds = {}
                for cid in ids:
                    status, videos = results.get(cid, ("error", []))
                    old = self.feeds.get(cid) or {}
                    if status == "ok":
                        feeds[cid] = {"videos": videos, "t": now, "status": "ok"}
                        continue
                    # Sin respuesta: se queda lo de antes. Solo el 404 repetido cuenta para darlo por desaparecido.
                    misses = old.get("misses", 0) + 1 if status == "missing" else old.get("misses", 0)
                    feeds[cid] = {"videos": old.get("videos", []), "t": old.get("t", 0), "misses": misses,
                                  "status": "gone" if misses >= GONE_AFTER else "error"}
                self.feeds, self.feeds_at = feeds, now
                self._save()
            states = [f["status"] for f in feeds.values()]
            ok, gone, errors = states.count("ok"), states.count("gone"), states.count("error")
            self.log(f"✓ Canales al día: {ok} bien, {errors} sin respuesta de YouTube (se conserva lo anterior)"
                     + (f", {gone} desaparecidos" if gone else "") + (" · el RSS no responde" if stopped else ""))
            return {"ok": True, "channels": len(ids), "updated": ok, "gone": gone, "errors": errors}
        finally:
            self.refreshing.release()

    def refresh_channel(self, cid):
        """Lee solo ese canal (al anclarlo o volver a mostrarlo) para que sus videos salgan ya en «Nuevos», sin esperar
        a la revisión de cada hora. No hace nada si ya se están revisando todos. -> True si lo leyó."""
        if not CHANNEL_ID.match(cid or "") or not self.refreshing.acquire(blocking=False):
            return False
        try:
            status, videos = self._fetch_channel(cid)
            if status != "ok":
                status, videos = self._fetch_page(cid)
            if status != "ok":
                return False
            with self.lock:
                self.feeds[cid] = {"videos": videos, "t": time.time(), "status": "ok"}
                self._save()
            return True
        finally:
            self.refreshing.release()

    def needs_refresh(self, cid, max_age=3600):
        with self.lock:
            return time.time() - (self.feeds.get(cid) or {}).get("t", 0) > max_age

    def new_videos(self, limit=40):
        """Lo más nuevo de las suscripciones visibles y de los anclados, por fecha; con la forma de los demás videos
        de YouTube. Nada de los canales ocultos."""
        wanted = set(self._watched_ids())
        with self.lock:
            hidden = set(self.hidden)
            rows = [(cid, v) for cid, f in self.feeds.items() if cid in wanted for v in f.get("videos", [])
                    if (v.get("channel_id") or cid) not in hidden and v.get("id") not in self.dismissed]
        out, seen = [], set()
        if self.durations:   # las fechas de todo lo que ya se leyó sirven también a otras listas (canal, historial…)
            self.durations.learn_dates([v for _, v in rows])
        for cid, v in sorted(rows, key=lambda r: -r[1].get("published", 0)):
            if v["id"] in seen:
                continue
            seen.add(v["id"])
            out.append({"id": v["id"], "title": v.get("title") or "Video de YouTube",
                        "channel": v.get("channel", ""), "duration": v.get("duration") or 0,
                        "thumb": f"/yt/{v['id']}/thumb.jpg",
                        "published": v.get("published", 0), "channel_id": v.get("channel_id") or cid})
            if v.get("published_approx"):   # de la página del canal («hace 3 días»), no del RSS
                out[-1]["published_approx"] = True
                out[-1]["published_unit"] = v.get("published_unit") or 86400
            if limit and len(out) >= limit:
                break
        # El RSS no trae la duración (la página del canal sí): la del caché y, si no se sabe, la pide el rellenador.
        return self.durations.apply(out) if self.durations else out

    def summary(self):
        with self.lock:
            states = [f.get("status") for f in self.feeds.values()]
            return {"subscriptions": len(self.subs), "playlists": len(self.lists), "history": len(self.history),
                    "imported_at": int(self.imported.get("at", 0)),
                    "imported_file": Path(self.imported["path"]).name if self.imported.get("path") else "",
                    "feeds_at": int(self.feeds_at), "feeds_ok": states.count("ok"),
                    "feeds_gone": states.count("gone"), "refreshing": self.refreshing.locked()}
