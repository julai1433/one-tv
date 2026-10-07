"""Pósters (portada vertical) de películas y series.

En este orden:
1. El póster que ya está junto a la película o la serie (poster.jpg, folder.jpg, cover.jpg, show.jpg,
   «Película-poster.jpg»…), como lo dejan Plex, Jellyfin, Emby o Kodi. Se lee, nunca se cambia.
2. Por el código de la película o la serie ({imdb-tt…} y {tvdb-…} en el nombre de la carpeta o, si no lo trae, el que
   encontró mac/identify.py por el nombre):
   - películas: el buscador público de IMDb (sin cuenta ni clave);
   - series: TVmaze (gratis, sin cuenta).
3. El fondo que esté junto a ella (fanart.jpg, background.jpg…), recortado.
4. Un recorte vertical del fotograma, para que la cuadrícula se vea pareja.
Se bajan o se preparan una sola vez, se dejan en 600x900 y se guardan en la caché de la computadora.
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
IMAGE_EXTS = (".jpg", ".jpeg", ".png")
MOVIE_POSTERS = ("poster", "folder", "cover", "movie", "default")
SHOW_POSTERS = ("poster", "show", "folder", "cover")
BACKDROPS = ("fanart", "background", "backdrop", "art")
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


def _images(folder):
    """{nombre en minúsculas: ruta} de las imágenes de una carpeta."""
    try:
        return {p.name.lower(): p for p in Path(folder).iterdir()
                if p.suffix.lower() in IMAGE_EXTS and not p.name.startswith(".") and p.is_file()}
    except OSError:
        return {}


def _first(images, stems):
    return next((images[f"{stem}{ext}"] for stem in stems for ext in IMAGE_EXTS if f"{stem}{ext}" in images), None)


def local_images(it=None, show_dir=None):
    """(póster, fondo) que hay junto a una película o en la carpeta de una serie (None si no hay)."""
    if show_dir:
        images = _images(show_dir)
        return _first(images, SHOW_POSTERS), _first(images, BACKDROPS)
    video = Path(it["path"])
    stem = video.stem.lower()
    own = [f"{stem}-poster", f"{stem}.poster", stem]   # «Película-poster.jpg» o «Película.jpg», junto al archivo
    images = _images(video.parent)
    if it.get("movie_dir"):   # la película tiene su carpeta: también poster.jpg, folder.jpg…
        if Path(it["movie_dir"]) != video.parent:
            images = {**_images(it["movie_dir"]), **images}
        return _first(images, own + list(MOVIE_POSTERS)), _first(images, [f"{stem}-fanart"] + list(BACKDROPS))
    return _first(images, own), _first(images, [f"{stem}-fanart"])


class Artwork:
    def __init__(self, cache_dir):
        self.dir = Path(cache_dir) / "art"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.dir / "index.json"
        self.lock = threading.Lock()
        self.busy = threading.Lock()
        try:
            self.index = json.loads(self.index_file.read_text())   # clave -> {"ok": bool, "t": cuándo, "local"?}
        except (OSError, ValueError):
            self.index = {}
        self.codes = None   # códigos encontrados por el nombre (mac/identify.py); la pone la app

    def path(self, key):
        return self.dir / f"{key}.jpg"

    def _mark(self, key, ok, local=None, net=None):
        """ok: hay póster. local: de qué imagen de la carpeta salió. net: cuándo se buscó en internet sin suerte
        (mientras se usa un fondo)."""
        with self.lock:
            self.index[key] = {"ok": ok, "t": time.time(), **({"local": local} if local else {}),
                               **({"net": net} if net else {})}
            tmp = self.index_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.index))
            tmp.replace(self.index_file)

    def _movie_code(self, it):
        if self.codes:
            return self.codes.movie_code(it)
        m = IMDB_RE.search(it["path"])
        return m.group(1) if m else ""

    def _show_code(self, show, library):
        if self.codes:
            return self.codes.show_code(show, library)
        first = library.items.get(show["poster"])
        m = TVDB_RE.search(first["path"]) if first else None
        return m.group(1) if m else ""

    def jobs_for(self, library):
        """(clave, fuente, código o imagen) de lo que hay en la biblioteca: primero el póster que ya está junto a la
        película o la serie; si no hay, el de internet por su código y, después, su fondo («fanart»)."""
        jobs = []
        for it in list(library.items.values()):
            if it["kind"] == "movie":
                poster, backdrop = local_images(it)
                code = "" if poster else self._movie_code(it)
                jobs += [(it["id"], "local", str(poster))] if poster else []
                jobs += [(it["id"], "imdb", code)] if code else []
                jobs += [(it["id"], "fondo", str(backdrop))] if backdrop and not poster else []
        for show in list(library.series):
            key = f"serie-{show['key']}"
            first = library.items.get(show["poster"]) or {}
            poster, backdrop = local_images(show_dir=first.get("show_dir")) if first.get("show_dir") else (None, None)
            code = "" if poster else self._show_code(show, library)
            jobs += [(key, "local", str(poster))] if poster else []
            jobs += [(key, "tvdb", code)] if code else []
            jobs += [(key, "fondo", str(backdrop))] if backdrop and not poster else []
        return jobs

    def _from_local(self, key, image, backdrop=False):
        """Prepara el póster desde una imagen de la carpeta de la película o la serie (la imagen no se toca). Si
        cambia la imagen, se vuelve a preparar. Un fondo solo se usa si no hay un póster de internet."""
        try:
            stamp = ("fondo:" if backdrop else "") + f"{image}|{Path(image).stat().st_mtime}"
        except OSError:
            return False
        prev = self.index.get(key) or {}
        if self.path(key).exists() and (prev.get("local") == stamp or (backdrop and prev.get("ok")
                                                                           and not prev.get("local"))):
            return False
        ok = _to_portrait(Path(image), self.path(key))
        if ok:
            self._mark(key, True, local=stamp)
        return ok

    def _wanted(self, key):
        """¿Hace falta buscar el póster en internet? Si no hay ninguno, o si el que hay es un fondo recortado. Lo que no
        se encontró se reintenta en una semana."""
        prev = self.index.get(key) or {}
        if prev.get("local", "").startswith("fondo:"):
            return time.time() - prev.get("net", 0) > RETRY_AFTER
        if self.path(key).exists():
            return False
        return prev.get("ok", True) or time.time() - prev.get("t", 0) > RETRY_AFTER

    def fetch_all(self, jobs, log=print):
        """Prepara o baja los pósters que falten (uno por uno, sin apurar a los servicios)."""
        if not self.busy.acquire(blocking=False):
            return
        try:
            found = 0
            for key, source, code in jobs:
                if source in ("local", "fondo"):
                    try:
                        found += self._from_local(key, code, backdrop=source == "fondo")
                    except (OSError, subprocess.TimeoutExpired):
                        pass
                    continue
                if not self._wanted(key):
                    continue
                try:
                    url = _imdb_image(code) if source == "imdb" else _tvmaze_image(code)
                    ok = False
                    if url:
                        raw = self.dir / f"{key}.download"
                        raw.write_bytes(_get(url, timeout=30))
                        ok = _to_portrait(raw, self.path(key))
                        raw.unlink(missing_ok=True)
                    backdrop = (self.index.get(key) or {}).get("local", "")
                    if not ok and backdrop.startswith("fondo:"):   # se queda el fondo; se reintenta en una semana
                        self._mark(key, True, local=backdrop, net=time.time())
                    else:
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
