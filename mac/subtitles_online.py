"""Subtítulos desde internet: OpenSubtitles.com (el mismo servicio que usa Plex).

Hace falta una clave de API gratuita (config.json → "opensubtitles" → "api_key").
Sin usuario: 5 descargas al día; con usuario y clave de una cuenta gratis: 20.
Lo que se sabe del cupo (cuántas quedan, cuándo se renueva) queda en `OpenSubtitles.quota`: lo usan las descargas
a mano y las automáticas (mac/subs_auto.py), que dejan siempre unas pocas para cuando las pidas tú.
"""

import json
import re
import struct
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
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
# Idioma (código de tres letras, el de mac/library.py → lang_key) -> códigos de OpenSubtitles, el preferido primero.
# Sirve para buscar en el idioma original de una película (japonés, coreano, danés…).
OS_LANGS = {
    "spa": "ea,es,sp", "eng": "en", "fre": "fr", "ger": "de", "ita": "it", "por": "pt-br,pt-pt", "jpn": "ja",
    "chi": "zh-cn,zh-tw,ze", "kor": "ko", "rus": "ru", "dut": "nl", "dan": "da", "swe": "sv", "nor": "no",
    "pol": "pl", "tur": "tr", "ara": "ar", "hin": "hi", "cat": "ca", "gre": "el", "heb": "he", "fin": "fi",
    "hun": "hu", "cze": "cs", "per": "fa", "rum": "ro", "slo": "sk", "ice": "is", "tha": "th", "vie": "vi",
    "ind": "id", "ukr": "uk", "srp": "sr", "hrv": "hr", "bul": "bg", "est": "et", "lav": "lv", "lit": "lt",
    "slv": "sl", "may": "ms", "tam": "ta", "tel": "te", "ben": "bn", "urd": "ur", "tgl": "tl", "fil": "tl",
    "bos": "bs", "mac": "mk", "alb": "sq", "arm": "hy", "geo": "ka", "baq": "eu", "glg": "gl", "kur": "ku",
    "mon": "mn", "khm": "km", "mal": "ml", "mar": "mr", "kan": "kn", "kaz": "kk", "nep": "ne", "afr": "af",
    "wel": "cy", "gle": "ga", "yue": "zh-ca",
}
MIN_GAP = 0.3          # entre dos consultas: la API acepta 5 por segundo; vamos más despacio
WAIT_429_MAX = 10      # si pide esperar menos que esto, se espera y se reintenta solo


def os_languages(lang):
    """Los códigos de OpenSubtitles para buscar en un idioma nuestro («spa», «en», «jpn»…), o "" si no tiene."""
    lang = (lang or "").lower()
    if lang in SEARCH_LANGS:
        return SEARCH_LANGS[lang]
    from library import lang_key
    return OS_LANGS.get(lang_key(lang), "")


def parse_reset(info, now=None):
    """Cuándo se renueva el cupo (segundos desde 1970), de lo que dice la API: «reset_time_utc» o, si no,
    «reset_time» («07 hours and 30 minutes»). None si no lo dice."""
    stamp = (info or {}).get("reset_time_utc")
    if stamp:
        try:
            return datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).timestamp()
        except ValueError:
            pass
    text = " ".join(str((info or {}).get(k) or "") for k in ("reset_time", "message"))
    hours = re.search(r"(\d+)\s*hour", text)
    minutes = re.search(r"(\d+)\s*minute", text)
    seconds = re.search(r"(\d+)\s*second", text)
    if not (hours or minutes or seconds):
        return None
    total = sum(int(m.group(1)) * k for m, k in ((hours, 3600), (minutes, 60), (seconds, 1)) if m)
    return (now or time.time()) + total


class SubtitleError(Exception):
    """Algo salió mal con OpenSubtitles. code: la respuesta (406, 429…); wait: cuántos segundos pide esperar;
    quota: se acabaron las descargas del día; reset_at: cuándo se renuevan (si lo dijo)."""

    def __init__(self, message, code=None, wait=None, quota=False, reset_at=None):
        super().__init__(message)
        self.code, self.wait, self.quota, self.reset_at = code, wait, quota, reset_at


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
        self._last_request = 0.0
        # El cupo de descargas, según lo último que dijo la API: allowed = por día, remaining = las que quedan,
        # reset_at = cuándo se renueva, t = cuándo se supo.
        self.quota = {"allowed": None, "remaining": None, "reset_at": None, "t": 0}

    @property
    def configured(self):
        return bool(self.api_key)

    def _note_quota(self, **fields):
        fields = {k: v for k, v in fields.items() if v is not None}
        if fields:
            self.quota.update(fields, t=time.time())

    # ---------- HTTP ----------

    def _request(self, method, path, params=None, body=None, auth=False, retry=True, tries_429=2):
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
        gap = MIN_GAP - (time.monotonic() - self._last_request)
        if gap > 0:
            time.sleep(gap)
        self._last_request = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            try:
                detail = json.loads(e.read() or b"{}")
            except ValueError:
                detail = {}
            finally:
                e.close()
            if not isinstance(detail, dict):
                detail = {}
            message = detail.get("message") or detail.get("errors") or ""
            if e.code == 401 and auth and retry and self.username:
                self.token = None
                self._login()
                return self._request(method, path, params, body, auth, retry=False)
            if e.code in (401, 403) and not auth:
                raise SubtitleError("OpenSubtitles rechazó la clave de API (revisa config.json).", code=e.code) from e
            about_quota = "remaining" in detail or "reset_time" in detail or \
                re.search(r"(?i)download|quota|allowed", str(message)) or not message
            if (e.code == 406 and about_quota) or ("download" in str(message).lower() and e.code in (403, 429)):
                reset_at = parse_reset(detail)
                self._note_quota(remaining=0, reset_at=reset_at)
                raise SubtitleError(f"Se acabaron las descargas de hoy en OpenSubtitles. {message}".strip(),
                                    code=e.code, quota=True, reset_at=reset_at) from e
            if e.code == 429:
                wait = _retry_after(e.headers)
                if tries_429 > 0 and wait <= WAIT_429_MAX:
                    time.sleep(wait)
                    return self._request(method, path, params, body, auth, retry, tries_429 - 1)
                raise SubtitleError("OpenSubtitles pide esperar un momento entre búsquedas.", code=429,
                                    wait=wait) from e
            raise SubtitleError(f"OpenSubtitles respondió {e.code}: {message}", code=e.code) from e
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
        self._note_quota(allowed=(data.get("user") or {}).get("allowed_downloads"))

    def user_info(self):
        """Cuántas descargas permite la cuenta al día y cuántas quedan (solo con usuario; no gasta cupo)."""
        if not self.configured or not self.username:
            return None
        with self.lock:
            self._login()
            data = self._request("GET", "/infos/user", auth=True).get("data") or {}
        self._note_quota(allowed=data.get("allowed_downloads"), remaining=data.get("remaining_downloads"))
        return data

    # ---------- buscar y descargar ----------

    def search(self, item, lang, parent_imdb=None):
        """Los subtítulos de ese video en ese idioma, el mejor primero. parent_imdb: el código de IMDb de la serie
        (sin «tt»), para buscar un capítulo por código en vez de por nombre."""
        if not self.configured:
            raise SubtitleError("Falta la clave de OpenSubtitles en config.json.")
        languages = os_languages(lang) or lang
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
            params.update({"type": "episode", "season_number": item["season"]})
            if parent_imdb:
                params["parent_imdb_id"] = int(parent_imdb)
            else:
                params["query"] = item["show"]
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
            feature = a.get("feature_details") or {}
            results.append({
                "file_id": files[0]["file_id"], "lang": code, "lang_label": LANG_LABELS.get(code, code),
                "release": a.get("release") or files[0].get("file_name") or "",
                "downloads": a.get("download_count") or 0, "match": bool(a.get("moviehash_match")),
                "ai": bool(a.get("ai_translated") or a.get("machine_translated")),
                "hi": bool(a.get("hearing_impaired")), "trusted": bool(a.get("from_trusted")),
                "foreign": bool(a.get("foreign_parts_only")),   # solo traduce lo que se habla en otro idioma
                "season": feature.get("season_number"), "episode": feature.get("episode_number"),
                "show": feature.get("parent_title") or "",
            })
        # Primero lo completo (no solo las partes en otro idioma), lo hecho para tu misma copia, lo humano, el
        # idioma preferido y lo más descargado.
        results.sort(key=lambda r: (r["foreign"], not r["match"], r["ai"],
                                    order.index(r["lang"]) if r["lang"] in order else 9,
                                    r["hi"], not r["trusted"], -r["downloads"]))
        return results[:30]

    def download(self, file_id):
        if not self.configured:
            raise SubtitleError("Falta la clave de OpenSubtitles en config.json.")
        with self.lock:
            self._login()
            info = self._request("POST", "/download", body={"file_id": int(file_id), "sub_format": "srt"}, auth=True)
        self._note_quota(remaining=info.get("remaining"), reset_at=parse_reset(info))
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


def _retry_after(headers):
    """Cuántos segundos pide esperar la API tras un 429 (encabezado Retry-After o RateLimit-Reset); 1 si no dice."""
    for name in ("Retry-After", "RateLimit-Reset", "X-RateLimit-Reset"):
        value = (headers or {}).get(name)
        try:
            if value is not None and float(value) >= 0:
                return min(float(value), 3600.0)
        except (TypeError, ValueError):
            continue
    return 1.0


def save_next_to_video(item, data, os_lang, file_lang=None):
    """Guarda el .srt junto al video (Película.es.opensubtitles-latino.srt): lo verá cualquier reproductor.
    file_lang: el código de idioma que va en el nombre, si no es el de siempre («ja», «kor»…). Nunca reemplaza
    un archivo que ya existe: si el nombre está ocupado, agrega -2, -3…"""
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
    base = f"{video.stem}.{file_lang or FILE_LANG.get(os_lang, os_lang)}.{tag}"
    target = video.with_name(base + ".srt")
    n = 2
    while target.exists():
        target = video.with_name(f"{base}-{n}.srt")
        n += 1
    with open(target, "w", encoding="utf-8", newline="\n") as f:   # saltos de línea \n también en Windows
        f.write(text)
    return target
