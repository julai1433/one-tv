"""Subtítulos desde internet: OpenSubtitles.com (el mismo servicio que usa Plex).

Hace falta una clave de API gratuita (config.json → "opensubtitles" → "api_key").
Sin usuario: 5 descargas al día; con usuario y clave de una cuenta gratis: 20.
"""

import json
import re
import struct
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://api.opensubtitles.com/api/v1"
USER_AGENT = "CineEnCasa v1.0"

# Nuestros códigos de idioma -> los de OpenSubtitles (el primero es el preferido).
SEARCH_LANGS = {"spa": "ea,es,sp", "es": "ea,es,sp", "eng": "en", "en": "en", "por": "pt-br,pt-pt",
                "fre": "fr", "fra": "fr", "ita": "it", "ger": "de", "deu": "de"}
LANG_LABELS = {"ea": "Español (Latino)", "es": "Español", "sp": "Español (España)", "en": "Inglés",
               "pt-br": "Portugués (Brasil)", "pt-pt": "Portugués", "fr": "Francés", "it": "Italiano", "de": "Alemán"}
FILE_LANG = {"ea": "es", "es": "es", "sp": "es", "en": "en", "pt-br": "pt", "pt-pt": "pt",
             "fr": "fr", "it": "it", "de": "de"}
FILE_TAG = {"ea": "latino", "sp": "espana", "pt-br": "brasil"}
IMDB_RE = re.compile(r"\{imdb-tt(\d+)\}")


class SubtitleError(Exception):
    pass


def movie_hash(path):
    """Huella de OpenSubtitles: tamaño + suma de los primeros y últimos 64 KB. Identifica la copia exacta."""
    size = Path(path).stat().st_size
    chunk = 65536
    if size < chunk * 2:
        return None
    total = size
    with open(path, "rb") as f:
        for offset in (0, size - chunk):
            f.seek(offset)
            data = f.read(chunk)
            total += sum(struct.unpack(f"<{chunk // 8}Q", data))
            total &= 0xFFFFFFFFFFFFFFFF
    return f"{total:016x}"


class OpenSubtitles:
    def __init__(self, cfg):
        conf = cfg.get("opensubtitles") or {}
        self.api_key = conf.get("api_key", "").strip()
        self.username = conf.get("usuario", "").strip()
        self.password = conf.get("clave", "")
        self.base = API
        self.token = None
        self.token_at = 0
        self.lock = threading.Lock()

    @property
    def configured(self):
        return bool(self.api_key)

    # ---------- HTTP ----------

    def _request(self, method, path, params=None, body=None, auth=False, retry=True):
        url = self.base + path
        if params:
            # La API pide los parámetros en minúsculas y en orden alfabético (si no, redirige).
            url += "?" + urllib.parse.urlencode(sorted((k.lower(), str(v).lower()) for k, v in params.items()))
        headers = {"Api-Key": self.api_key, "User-Agent": USER_AGENT, "Accept": "application/json"}
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode()
        if auth and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            try:
                detail = json.loads(e.read() or b"{}")
            except ValueError:
                detail = {}
            message = detail.get("message") or detail.get("errors") or ""
            if e.code == 401 and auth and retry and self.username:
                self.token = None
                self._login()
                return self._request(method, path, params, body, auth, retry=False)
            if e.code in (401, 403) and not auth:
                raise SubtitleError("OpenSubtitles rechazó la clave de API (revisa config.json).") from e
            if e.code == 406 or ("download" in str(message).lower() and e.code in (403, 429)):
                raise SubtitleError(f"Se acabaron las descargas de hoy en OpenSubtitles. {message}".strip()) from e
            if e.code == 429:
                raise SubtitleError("OpenSubtitles pide esperar un momento entre búsquedas.") from e
            raise SubtitleError(f"OpenSubtitles respondió {e.code}: {message}") from e
        except (urllib.error.URLError, TimeoutError) as e:
            raise SubtitleError("No hay conexión con OpenSubtitles.") from e

    def _login(self):
        """Con usuario se pasa de 5 a 20 descargas diarias; el token dura un día."""
        if not self.username or (self.token and time.time() - self.token_at < 12 * 3600):
            return
        data = self._request("POST", "/login", body={"username": self.username, "password": self.password},
                             retry=False)
        self.token, self.token_at = data.get("token"), time.time()
        if data.get("base_url"):
            self.base = f"https://{data['base_url']}/api/v1"

    # ---------- buscar y descargar ----------

    def search(self, item, lang):
        if not self.configured:
            raise SubtitleError("Falta la clave de OpenSubtitles en config.json.")
        languages = SEARCH_LANGS.get(lang, lang)
        params = {"languages": languages}
        try:
            h = movie_hash(item["path"])
            if h:
                params["moviehash"] = h
        except OSError:
            pass
        imdb = IMDB_RE.search(item["path"])
        if item["kind"] == "episode":
            number = re.search(r"\d+", item.get("ep") or "")
            params.update({"type": "episode", "query": item["show"], "season_number": item["season"]})
            if number:
                params["episode_number"] = int(number.group())
        elif imdb:
            params.update({"type": "movie", "imdb_id": int(imdb.group(1))})
        else:
            title = re.sub(r"\s*\(\d{4}\)$", "", item["title"])
            year = re.search(r"\((\d{4})\)$", item["title"])
            params.update({"type": "movie", "query": title})
            if year:
                params["year"] = year.group(1)
        with self.lock:
            data = self._request("GET", "/subtitles", params=params)
        order = languages.split(",")
        results = []
        for entry in data.get("data", []):
            a = entry.get("attributes", {})
            files = a.get("files") or []
            if not files or len(files) > 1:  # los partidos en varios CD no sirven aquí
                continue
            code = (a.get("language") or "").lower()
            results.append({
                "file_id": files[0]["file_id"], "lang": code, "lang_label": LANG_LABELS.get(code, code),
                "release": a.get("release") or files[0].get("file_name") or "",
                "downloads": a.get("download_count") or 0, "match": bool(a.get("moviehash_match")),
                "ai": bool(a.get("ai_translated") or a.get("machine_translated")),
                "hi": bool(a.get("hearing_impaired")), "trusted": bool(a.get("from_trusted")),
            })
        # Primero lo hecho para tu misma copia, luego lo humano, el idioma preferido y lo más descargado.
        results.sort(key=lambda r: (not r["match"], r["ai"], order.index(r["lang"]) if r["lang"] in order else 9,
                                    r["hi"], not r["trusted"], -r["downloads"]))
        return results[:30]

    def download(self, file_id):
        if not self.configured:
            raise SubtitleError("Falta la clave de OpenSubtitles en config.json.")
        with self.lock:
            self._login()
            info = self._request("POST", "/download", body={"file_id": int(file_id), "sub_format": "srt"}, auth=True)
        link = info.get("link")
        if not link:
            raise SubtitleError(info.get("message") or "OpenSubtitles no dio el enlace de descarga.")
        try:
            with urllib.request.urlopen(urllib.request.Request(link, headers={"User-Agent": USER_AGENT}),
                                        timeout=30) as r:
                data = r.read()
        except (urllib.error.URLError, TimeoutError) as e:
            raise SubtitleError("Falló la descarga del subtítulo.") from e
        return data, info.get("remaining")


def save_next_to_video(item, data, os_lang):
    """Guarda el .srt junto al video (Película.es.opensubtitles-latino.srt): lo verá cualquier reproductor."""
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip() + "\n"
    if "-->" not in text:
        raise SubtitleError("El archivo descargado no parece un subtítulo.")
    video = Path(item["path"])
    tag = "opensubtitles" + (f"-{FILE_TAG[os_lang]}" if os_lang in FILE_TAG else "")
    base = f"{video.stem}.{FILE_LANG.get(os_lang, os_lang)}.{tag}"
    target = video.with_name(base + ".srt")
    n = 2
    while target.exists():
        target = video.with_name(f"{base}-{n}.srt")
        n += 1
    target.write_text(text, encoding="utf-8")
    return target
