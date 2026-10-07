"""Ordena solo lo nuevo, con el mismo formato que el resto de la biblioteca:

  Películas/Título (Año) {imdb-tt…}/Título (Año) {imdb-tt…}.mkv
  Series/Serie (Año) {tvdb-…}/Season 01/Serie (Año) - S01E02 - Título del episodio.mkv

- Lo que llega a la biblioteca con otro nombre (suelto en la raíz, o en Películas/Series sin el código)
  se identifica y se mueve a su lugar.
- Lo que termina de bajarse en Transmission NO se mueve: se crea un «enlace duro» en la biblioteca (el
  mismo archivo con un segundo nombre; no ocupa espacio extra). Transmission lo sigue compartiendo desde
  donde está y, si un día se borra el torrent, la película se queda en la biblioteca.
- Solo en las carpetas de One TV (mac/folders.py). Las de otro programa (Plex, Jellyfin…), o en las que no se puede
  escribir, solo se leen: ahí no se mueve ni se renombra nada, y lo que termina de bajarse va a la primera carpeta de
  One TV (si no hay ninguna, no se agrega y se avisa en el registro).
Películas: el buscador de IMDb. Series y episodios: TVmaze. Sin cuentas ni claves.
"""

import json
import os
import plistlib
import re
import shutil
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import hostos
from folders import LibraryFolders
from library import EPISODE_RE, SKIP_DIRS, SUB_EXTS, VIDEO_EXTS, YEAR_RE, _nfc, clean_title

MIN_SIZE = 60 * 1024 * 1024     # lo más chico suele ser una muestra (sample)
SETTLE = 120                    # un archivo que cambió hace menos de 2 min puede estar copiándose
# Transmission le pone «.part» al nombre mientras baja (su opción «Append .part to incomplete files' names», prendida
# de fábrica) y solo lo quita al terminar: un video de Descargas sin «.part» ya está completo y basta esperar poco.
DOWNLOAD_SETTLE = 15
TRANSMISSION_PREFS = Path.home() / "Library" / "Preferences" / "org.m0k.transmission.plist"
RETRY_FAILED = 24 * 3600
UA = {"User-Agent": "Mozilla/5.0 (Macintosh) OneTV"}
TAGGED_MOVIE = re.compile(r"\{imdb-tt\d+\}")
TAGGED_SHOW = re.compile(r"\{tvdb-\d+\}")


def _get_json(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as r:
        return json.loads(r.read())


def safe_name(text):
    """Nombre válido para una carpeta de macOS (sin «/» ni «:»). En Windows tampoco van \\ " < > | (y no puede
    terminar en punto ni en espacio, que ya se quitan)."""
    text = _nfc(text).replace("/", "-").replace(":", " -").replace("?", "").replace("*", "")
    if hostos.WINDOWS:
        text = text.replace("\\", "-").replace('"', "'").replace("<", "").replace(">", "").replace("|", "-")
    return re.sub(r"\s+", " ", text).strip(" .")


def transmission_marks_partial(prefs=None):
    """¿Transmission le pone «.part» a lo que no ha terminado? Sí de fábrica; no solo si se apagó esa opción."""
    try:
        with open(prefs or TRANSMISSION_PREFS, "rb") as f:
            return bool(plistlib.load(f).get("RenamePartialFiles", True))
    except (OSError, ValueError, plistlib.InvalidFileException):
        return True


def _is_candidate(path, now, settle=SETTLE):
    """Video completo y ya quieto: no es parcial, ni muestra, ni lo están copiando."""
    if path.suffix.lower() not in VIDEO_EXTS or path.name.startswith("."):
        return False
    if re.search(r"(?i)(?<![a-z])sample(?![a-z])", path.name):
        return False
    if any(_nfc(part).lower() in SKIP_DIRS for part in path.parent.parts[-3:]):
        return False   # extras, featurettes, tráilers… de la película
    try:
        st = path.stat()
    except OSError:
        return False
    return st.st_size >= MIN_SIZE and now - st.st_mtime > settle


class Organizer:
    def __init__(self, library_roots, download_roots, state_file, log=print, folders=None):
        self.roots = [Path(os.path.expanduser(r)).resolve() for r in library_roots]
        self.downloads = [Path(os.path.expanduser(d)) for d in download_roots]
        self.state_file = Path(state_file)
        self.log = log
        # Qué carpetas son de One TV (las demás solo se leen); la app pasa la misma que usan subtítulos y doblajes.
        self.folders = folders or LibraryFolders(library_roots, None, self.state_file.with_name("carpetas.json"), log=log)
        self.warned_no_target = False
        self.lock = threading.Lock()
        try:
            self.state = json.loads(self.state_file.read_text())
        except (OSError, ValueError):
            self.state = {}
        self.state.setdefault("done", {})     # origen -> destino (o motivo por el que no hizo falta)
        self.state.setdefault("failed", {})   # origen -> {"t", "why"}
        self.shows = {}                        # búsquedas de TVmaze ya hechas (nombre -> serie)

    def _save(self):
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, ensure_ascii=False, indent=1))
        tmp.replace(self.state_file)

    # ---------- qué hay que ordenar ----------

    def candidates(self):
        """[(ruta, "move" | "link")]: lo nuevo en la biblioteca y lo terminado en Descargas."""
        now = time.time()
        found = []
        for root in self.roots:
            if not self.folders.own(root):
                continue   # de otro programa, de solo lectura o sin conectar: no se toca nada ahí
            movies, series = root / "Películas", root / "Series"
            try:
                loose = [p for p in root.iterdir() if p.is_file()]
            except OSError:
                continue
            found += [(p, "move") for p in loose if _is_candidate(p, now)]
            for folder, tag in ((movies, TAGGED_MOVIE), (series, TAGGED_SHOW)):
                if not folder.is_dir():
                    continue
                for entry in folder.iterdir():
                    if entry.name.startswith(".") or tag.search(entry.name):
                        continue
                    videos = [entry] if entry.is_file() else [p for p in entry.rglob("*") if p.is_file()]
                    found += [(p, "move") for p in videos if _is_candidate(p, now)]
        found += self._downloads(now)
        return self._pending(found, now)

    def _downloads(self, now):
        if not self.downloads:
            return []
        settle = DOWNLOAD_SETTLE if transmission_marks_partial() else SETTLE
        found = []
        for d in self.downloads:
            if d.is_dir():
                found += [(p, "link") for p in d.rglob("*") if p.is_file() and _is_candidate(p, now, settle)]
        if found and not self.target():
            if not self.warned_no_target and self._pending(found, now):
                self.warned_no_target = True
                self.log("⚠ Descargas: lo que termina de bajarse no se agrega a One TV porque todas las carpetas de la "
                         "biblioteca son de otro programa (o no se puede escribir en ellas). Para que se agregue solo, "
                         "suma a «carpetas» una carpeta vacía para One TV (ver docs/GUIA-RAPIDA.md).")
            return []
        return found

    def target(self):
        """Dónde se ordena lo nuevo: la primera carpeta de One TV que esté conectada (None si no hay)."""
        return next(iter(self.folders.own_roots()), None)

    def _pending(self, found, now):
        done, failed = self.state["done"], self.state["failed"]
        return [(p, how) for p, how in found
                if str(p) not in done and now - failed.get(str(p), {}).get("t", 0) > RETRY_FAILED]

    def pending_downloads(self):
        """¿Terminó de bajarse algo que todavía no está en la biblioteca? (barato: solo mira las Descargas)."""
        return bool(self._pending(self._downloads(time.time()), time.time()))

    # ---------- identificar ----------

    def identify(self, path):
        """{"kind": "movie", …} o {"kind": "episode", …} con el nombre final; None si no se reconoce."""
        stem, parent = _nfc(path.stem), _nfc(path.parent.name)
        ep = EPISODE_RE.search(stem) or EPISODE_RE.search(f"{parent} {stem}")
        if ep:
            return self._identify_episode(path, stem, parent, ep)
        return self._identify_movie(stem, parent)

    def _identify_movie(self, stem, parent):
        title = clean_title(stem)
        if not YEAR_RE.search(title) and YEAR_RE.search(clean_title(parent)):
            title = clean_title(parent)   # el año suele venir en el nombre de la carpeta del torrent
        m = re.match(r"^(.*?)\s*\((\d{4})\)$", title)
        name, year = (m.group(1), int(m.group(2))) if m else (title, None)
        if len(name) < 2:
            return None
        query = f"{name} {year}" if year else name
        q = urllib.parse.quote(query.lower())
        data = _get_json(f"https://v3.sg.media-imdb.com/suggestion/{q[0] if q[0].isalnum() else 'x'}/{q}.json")
        results = [r for r in data.get("d", []) if r.get("id", "").startswith("tt")
                   and r.get("qid") in ("movie", "tvMovie", "video", "short")]
        if year:
            results = [r for r in results if r.get("y") and abs(r["y"] - year) <= 1]
        if not results:
            return None
        r = results[0]
        base = safe_name(f"{r['l']} ({r['y']}) {{imdb-{r['id']}}}")
        return {"kind": "movie", "imdb": r["id"], "title": r["l"], "year": r.get("y"),
                "folder": ("Películas", base), "file": base}

    def _find_show(self, name):
        key = name.lower()
        if key not in self.shows:
            try:
                self.shows[key] = _get_json("https://api.tvmaze.com/singlesearch/shows?embed=episodes&q="
                                            + urllib.parse.quote(name))
            except urllib.error.HTTPError as e:
                if e.code != 404:
                    raise
                self.shows[key] = None
        return self.shows[key]

    def _identify_episode(self, path, stem, parent, ep):
        text = stem if EPISODE_RE.search(stem) else f"{parent} {stem}"
        raw = text[:EPISODE_RE.search(text).start()]
        name = clean_title(raw).strip(" -") or clean_title(re.sub(r"(?i)\b(season|temporada)\s*\d+.*$", "", parent))
        name = YEAR_RE.sub("", name).replace("()", "").strip(" -")
        if len(name) < 2:
            return None
        show = self._find_show(name)
        if not show:
            return None
        season, number = int(ep.group(1)), int(ep.group(2))
        extra = re.match(r"(?i)[-\s]?e(\d{1,3})", stem[ep.end():] if EPISODE_RE.search(stem) else "")
        tvdb = (show.get("externals") or {}).get("thetvdb")
        year = (show.get("premiered") or "")[:4]
        show_base = safe_name(f"{show['name']} ({year})" if year else show["name"])
        folder = self._existing_show_folder(tvdb) or (safe_name(f"{show_base} {{tvdb-{tvdb}}}") if tvdb else show_base)
        episodes = (show.get("_embedded") or {}).get("episodes") or []
        ep_title = next((e.get("name") for e in episodes if e.get("season") == season and e.get("number") == number), "")
        code = f"S{season:02d}E{number:02d}" + (f"-E{int(extra.group(1)):02d}" if extra else "")
        show_label = re.sub(r" \{tvdb-\d+\}$", "", folder)
        file_base = f"{show_label} - {code}" + (f" - {safe_name(ep_title)}" if ep_title else "")
        return {"kind": "episode", "tvdb": tvdb, "show": show["name"], "season": season, "number": number,
                "folder": ("Series", folder, f"Season {season:02d}"), "file": file_base}

    def _existing_show_folder(self, tvdb):
        if not tvdb:
            return None
        for root in self.roots:
            series = root / "Series"
            if series.is_dir():
                for d in series.iterdir():
                    if f"{{tvdb-{tvdb}}}" in d.name:
                        return d.name
        return None

    def _already_have(self, info):
        """¿Ya está en la biblioteca (misma película, o mismo episodio de la misma serie)? Devuelve el
        video que ya tenemos (o su carpeta si no se encuentra el archivo), o None."""
        for root in self.roots:
            if info["kind"] == "movie":
                folder = root / "Películas"
                if not folder.is_dir():
                    continue
                for d in folder.iterdir():
                    if f"{{imdb-{info['imdb']}}}" in d.name:
                        return self._main_video(d) or d
            else:
                season_dir = root.joinpath(*info["folder"])
                code = re.compile(rf"(?i)s0*{info['season']}e0*{info['number']}(?!\d)")
                if season_dir.is_dir():
                    found = [p for p in season_dir.iterdir() if code.search(p.name) and p.suffix.lower() in VIDEO_EXTS]
                    if found:
                        return found[0]
        return None

    @staticmethod
    def _main_video(folder):
        """El video principal de la carpeta de una película (el más pesado, fuera de los extras)."""
        if folder.is_file():
            return folder
        videos = [p for p in folder.rglob("*") if p.suffix.lower() in VIDEO_EXTS and not p.name.startswith(".")
                  and not any(_nfc(x).lower() in SKIP_DIRS for x in p.relative_to(folder).parts[:-1])]
        return max(videos, key=lambda p: p.stat().st_size, default=None)

    # ---------- mover o enlazar ----------

    def _sidecar_subs(self, video):
        """Subtítulos que vienen con el video: mismo nombre, o carpeta Subs/Subtitles."""
        out, stem = [], _nfc(video.stem).lower()
        for p in video.parent.iterdir():
            if p.suffix.lower() in SUB_EXTS and _nfc(p.stem).lower().startswith(stem):
                out.append((p, _nfc(p.stem)[len(stem):].strip(" ._-")))
        for d in video.parent.iterdir():
            if d.is_dir() and d.name.lower() in ("subs", "subtitles"):
                for p in d.rglob("*"):
                    if p.suffix.lower() in SUB_EXTS:
                        out.append((p, _nfc(p.stem)))
        return out

    def _place(self, src, dest, how):
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            return
        if how == "move":
            shutil.move(str(src), str(dest))
            return
        try:
            os.link(src, dest)   # el mismo archivo con otro nombre: Transmission lo sigue compartiendo
        except OSError:
            shutil.move(str(src), str(dest))   # otro disco: se mueve y queda un acceso en su lugar
            try:
                os.symlink(dest, src)
            except OSError:   # Windows sin permiso para crear accesos: el archivo queda movido a la biblioteca
                pass

    def run(self, dry_run=False):
        """Ordena lo pendiente. Devuelve la lista de lo hecho (o, en prueba, lo que haría)."""
        with self.lock:
            actions = []
            for path, how in self.candidates():
                try:
                    info = self.identify(path)
                except (urllib.error.URLError, OSError, ValueError) as e:
                    actions.append({"src": str(path), "error": f"sin conexión ({e})"})
                    continue
                if not info:
                    actions.append({"src": str(path), "error": "no se reconoció"})
                    if not dry_run:
                        self.state["failed"][str(path)] = {"t": time.time(), "why": "no se reconoció"}
                    continue
                have = self._already_have(info)
                if have:
                    actions.append({"src": str(path), "skip": "ya está en la biblioteca", "info": info,
                                    "have": str(have), "how": how})
                    if not dry_run:
                        self.state["done"][str(path)] = "ya estaba"
                    continue
                target = self.target()
                if not target:   # la carpeta de One TV se desconectó a medio camino: se reintenta en la próxima vuelta
                    actions.append({"src": str(path), "error": "no hay una carpeta de One TV conectada"})
                    continue
                dest = target.joinpath(*info["folder"]) / (info["file"] + path.suffix.lower())
                actions.append({"src": str(path), "dest": str(dest), "how": how, "info": info})
                if dry_run:
                    continue
                subs = self._sidecar_subs(path)
                self._place(path, dest, how)
                for sub, label in subs:
                    suffix = f".{safe_name(label)}" if label else ""
                    self._place(sub, dest.with_name(f"{dest.stem}{suffix}{sub.suffix.lower()}"), how)
                self.state["done"][str(path)] = str(dest)
                verb = "enlazada desde Descargas" if how == "link" else "ordenada"
                self.log(f"✓ Biblioteca: {info['file']} ({verb})")
                if how == "move":
                    self._remove_if_empty(path.parent)
            if not dry_run:
                self._save()
            return actions

    def _remove_if_empty(self, folder):
        """Si la carpeta de origen dentro de la biblioteca quedó vacía, se quita."""
        folder = Path(folder)
        if folder in self.roots or folder.name in ("Películas", "Series"):
            return
        try:
            leftovers = [p for p in folder.rglob("*") if p.is_file() and p.name != ".DS_Store"]
            if not leftovers:
                shutil.rmtree(folder)
        except OSError:
            pass
