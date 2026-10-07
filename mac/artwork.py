"""Pósters (portada vertical) de películas y series, por el código que traen en el nombre de la carpeta.

- Películas {imdb-tt…}: el buscador público de IMDb (sin cuenta ni clave).
- Series {tvdb-…}: TVmaze (gratis, sin cuenta).
Se bajan una sola vez, se dejan en 600x900 y se guardan en la Mac. Si no hay póster,
se usa un recorte vertical del fotograma, para que la cuadrícula se vea pareja.
"""

import json
import re
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

IMDB_RE = re.compile(r"\{imdb-(tt\d+)\}")
TVDB_RE = re.compile(r"\{tvdb-(\d+)\}")
RETRY_AFTER = 7 * 24 * 3600   # si no se encontró, se vuelve a intentar en una semana
UA = {"User-Agent": "Mozilla/5.0 (Macintosh) OneTV"}


def _get(url, timeout=15):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


def _imdb_image(tt):
    data = json.loads(_get(f"https://v3.sg.media-imdb.com/suggestion/t/{tt}.json"))
    entry = next((e for e in data.get("d", []) if e.get("id") == tt), None)
    url = ((entry or {}).get("i") or {}).get("imageUrl")
    return url.replace("._V1_.jpg", "._V1_UX600_.jpg") if url else None


def _tvmaze_image(tvdb):
    try:
        data = json.loads(_get(f"https://api.tvmaze.com/lookup/shows?thetvdb={tvdb}"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    image = data.get("image") or {}
    return image.get("original") or image.get("medium")


def _to_portrait(src, dst):
    """Deja la imagen en 600x900 (recorta lo que sobre, sin deformar)."""
    tmp = dst.with_suffix(".tmp.jpg")
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vf",
                        "scale=600:900:force_original_aspect_ratio=increase,crop=600:900", "-q:v", "3", str(tmp)],
                       capture_output=True, stdin=subprocess.DEVNULL, timeout=60)
    if r.returncode != 0 or not tmp.exists():
        tmp.unlink(missing_ok=True)
        return False
    tmp.replace(dst)
    return True


class Artwork:
    def __init__(self, cache_dir):
        self.dir = Path(cache_dir) / "art"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.dir / "index.json"
        self.lock = threading.Lock()
        self.busy = threading.Lock()
        try:
            self.index = json.loads(self.index_file.read_text())   # clave -> {"ok": bool, "t": cuándo}
        except (OSError, ValueError):
            self.index = {}

    def path(self, key):
        return self.dir / f"{key}.jpg"

    def _mark(self, key, ok):
        with self.lock:
            self.index[key] = {"ok": ok, "t": time.time()}
            tmp = self.index_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.index))
            tmp.replace(self.index_file)

    def jobs_for(self, library):
        """(clave, fuente, código) de lo que hay en la biblioteca."""
        jobs = []
        for it in library.items.values():
            if it["kind"] == "movie":
                m = IMDB_RE.search(it["path"])
                if m:
                    jobs.append((it["id"], "imdb", m.group(1)))
        for show in library.series:
            first = library.items.get(show["poster"])
            m = TVDB_RE.search(first["path"]) if first else None
            if m:
                jobs.append((f"serie-{show['key']}", "tvdb", m.group(1)))
        return jobs

    def fetch_all(self, jobs, log=print):
        """Baja los pósters que falten (uno por uno, sin apurar a los servicios)."""
        if not self.busy.acquire(blocking=False):
            return
        try:
            found = 0
            for key, source, code in jobs:
                if self.path(key).exists():
                    continue
                prev = self.index.get(key)
                if prev and not prev["ok"] and time.time() - prev["t"] < RETRY_AFTER:
                    continue
                try:
                    url = _imdb_image(code) if source == "imdb" else _tvmaze_image(code)
                    ok = False
                    if url:
                        raw = self.dir / f"{key}.download"
                        raw.write_bytes(_get(url, timeout=30))
                        ok = _to_portrait(raw, self.path(key))
                        raw.unlink(missing_ok=True)
                    self._mark(key, ok)
                    found += ok
                except (urllib.error.URLError, OSError, ValueError, subprocess.TimeoutExpired):
                    continue   # sin internet o el servicio falló: se reintenta en el próximo arranque
                time.sleep(0.3)
            if found:
                log(f"✓ {found} pósters nuevos")
        finally:
            self.busy.release()

    def frame_fallback(self, key, frame):
        """Recorte vertical del fotograma, para lo que no tiene póster."""
        dst = self.dir / f"{key}-frame.jpg"
        if not dst.exists() and frame and Path(frame).exists():
            _to_portrait(Path(frame), dst)
        return dst if dst.exists() else None
