"""Tu música en One TV: artistas, álbumes, canciones y las listas .m3u/.m3u8 de las carpetas de música (config.json:
«musica», por omisión ~/Music/Biblioteca si existe).

- Las etiquetas (título, artista, álbum, número, disco, año, género) y la duración se leen con ffprobe una sola vez
  por archivo; se guardan con su fecha y tamaño (datos/musica.json) y solo se vuelven a leer si el archivo cambia.
- La portada de un álbum: la que viene dentro del archivo o, si no, cover/folder/front.jpg|png de su carpeta; se guarda
  achicada (600 px) en la caché.
- Cada canción se sirve tal cual si es MP3 o AAC; FLAC, ALAC, WAV, AIFF, Ogg… se convierten una sola vez a AAC de
  256 kb/s (con el codificador de macOS) y se guardan en la caché: Chrome no abre ALAC y el Roku no abre todo.
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

AUDIO_EXTS = {".flac", ".m4a", ".mp3", ".aac", ".ogg", ".oga", ".opus", ".wav", ".aiff", ".aif", ".alac", ".wma", ".mp4"}
DIRECT_CODECS = {"mp3", "aac"}          # se mandan tal cual: los abre todo (navegadores y Roku)
PLAYLIST_EXTS = {".m3u", ".m3u8"}
COVER_NAMES = ("cover", "folder", "front", "album", "portada")
ART_SIZE = 600
SKIP_DIRS = {"_playlists"}              # las listas no son álbumes (se leen aparte)
UNKNOWN_ARTIST = "Artista desconocido"
UNKNOWN_ALBUM = "Sin álbum"


def _nfc(text):
    return unicodedata.normalize("NFC", text or "")


def _key(text):
    return " ".join(_nfc(text).casefold().split())


def _hid(*parts, n=12):
    return hashlib.sha1("\0".join(parts).encode("utf-8")).hexdigest()[:n]


def _num(value):
    """«3/12» -> 3; «» -> 0."""
    m = re.match(r"\s*(\d+)", str(value or ""))
    return int(m.group(1)) if m else 0


def _year(value):
    m = re.search(r"(1[89]\d\d|20\d\d)", str(value or ""))
    return int(m.group(1)) if m else 0


def probe(path):
    """Etiquetas, duración, códec y si trae portada adentro; None si no es audio."""
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
                             capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL)
        data = json.loads(out.stdout or "{}")
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None
    streams = data.get("streams") or []
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if not audio:
        return None
    fmt = data.get("format") or {}
    tags = {k.lower(): v for k, v in (fmt.get("tags") or {}).items()}
    tags.update({k.lower(): v for k, v in (audio.get("tags") or {}).items() if k.lower() not in tags})
    art = any(s.get("codec_type") == "video" and (s.get("disposition") or {}).get("attached_pic") or
              s.get("codec_name") in ("mjpeg", "png") for s in streams if s is not audio)
    try:
        duration = float(fmt.get("duration") or audio.get("duration") or 0)
    except ValueError:
        duration = 0
    return {"title": _nfc(tags.get("title")), "artist": _nfc(tags.get("artist")),
            "album_artist": _nfc(tags.get("album_artist") or tags.get("albumartist") or tags.get("album artist")),
            "album": _nfc(tags.get("album")), "track": _num(tags.get("track") or tags.get("tracknumber")),
            "disc": _num(tags.get("disc") or tags.get("discnumber")) or 1,
            "year": _year(tags.get("originaldate") or tags.get("date") or tags.get("year")),
            "genre": _nfc(tags.get("genre")), "duration": round(duration, 2),
            "codec": audio.get("codec_name") or "", "art": bool(art)}


class Music:
    def __init__(self, roots, data_file, cache_dir, log=print, prober=probe):
        self.roots = [Path(os.path.expanduser(r)) for r in roots]
        self.data_file = Path(data_file)
        self.cache = Path(cache_dir)
        self.log = log
        self.prober = prober
        self.lock = threading.Lock()
        self.convert_lock = threading.Lock()
        self.converting = {}       # canción -> threading.Event mientras se convierte
        try:
            self.probes = json.loads(self.data_file.read_text())
        except (OSError, ValueError):
            self.probes = {}       # ruta -> {"mtime", "size", "info"}
        self.tracks, self.albums, self.artists, self.playlists = {}, {}, {}, []
        self.scanned_at = 0

    @property
    def enabled(self):
        return any(r.is_dir() for r in self.roots)

    # ---------- leer las carpetas ----------

    def _walk(self):
        files, lists = [], []
        for root in self.roots:
            if not root.is_dir():
                continue
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames if not d.startswith(".")]
                for name in filenames:
                    if name.startswith("."):
                        continue
                    p = Path(dirpath) / name
                    ext = p.suffix.lower()
                    if ext in PLAYLIST_EXTS:
                        lists.append(p)
                    elif ext in AUDIO_EXTS and not any(_key(x) in SKIP_DIRS for x in p.relative_to(root).parts[:-1]):
                        files.append(p)
        return files, lists

    def scan(self, force=False):
        """Lee lo nuevo (o lo que cambió) y arma artistas, álbumes y listas. -> cuántas canciones hay."""
        with self.lock:
            if not force and time.time() - self.scanned_at < 20:
                return len(self.tracks)
            files, lists = self._walk()
            stats, todo = {}, []
            for p in files:
                try:
                    st = p.stat()
                except OSError:
                    continue
                stats[p] = st
                c = self.probes.get(str(p))
                if not c or c["mtime"] != st.st_mtime or c["size"] != st.st_size:
                    todo.append(p)
            if todo:
                with ThreadPoolExecutor(max_workers=6) as pool:
                    for p, info in zip(todo, pool.map(self.prober, todo)):
                        self.probes[str(p)] = {"mtime": stats[p].st_mtime, "size": stats[p].st_size, "info": info}
            live = {str(p) for p in stats}
            gone = [k for k in self.probes if k not in live]
            for k in gone:
                del self.probes[k]
            if todo or gone:
                self._save()
            self._build(stats, lists)
            self.scanned_at = time.time()
            return len(self.tracks)

    def _save(self):
        try:
            self.data_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.data_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.probes, ensure_ascii=False))
            tmp.replace(self.data_file)
        except OSError:
            pass

    def _build(self, stats, lists):
        tracks, albums, artists = {}, {}, {}
        for p in stats:
            info = (self.probes.get(str(p)) or {}).get("info")
            if not info:
                continue
            artist = info["artist"] or info["album_artist"] or UNKNOWN_ARTIST
            album_artist = info["album_artist"] or info["artist"] or UNKNOWN_ARTIST
            album = info["album"] or p.parent.name or UNKNOWN_ALBUM
            title = info["title"] or re.sub(r"^[\d\s.\-_]+", "", p.stem) or p.stem
            aid = _hid(_key(album_artist), _key(album))
            tid = _hid(str(p))
            tracks[tid] = {"id": tid, "title": title, "artist": artist, "album": album, "album_id": aid,
                           "album_artist": album_artist, "n": info["track"], "disc": info["disc"],
                           "duration": info["duration"], "codec": info["codec"], "path": str(p), "art": info["art"]}
            a = albums.setdefault(aid, {"id": aid, "title": album, "artist": album_artist, "year": 0, "genre": "",
                                        "tracks": [], "folder": str(p.parent), "added": 0})
            a["tracks"].append(tid)
            a["year"] = a["year"] or info["year"]
            a["genre"] = a["genre"] or info["genre"]
            a["added"] = max(a["added"], stats[p].st_mtime)
        for a in albums.values():
            a["tracks"].sort(key=lambda t: (tracks[t]["disc"], tracks[t]["n"] or 999, _key(tracks[t]["title"])))
            a["duration"] = round(sum(tracks[t]["duration"] for t in a["tracks"]))
            name = a["artist"]
            arid = _hid(_key(name), n=10)
            ar = artists.setdefault(arid, {"id": arid, "name": name, "albums": []})
            ar["albums"].append(a["id"])
        for ar in artists.values():
            ar["albums"].sort(key=lambda x: (albums[x]["year"] or 9999, _key(albums[x]["title"])))
        by_path = {_nfc(t["path"]): t["id"] for t in tracks.values()}   # macOS guarda los acentos descompuestos
        playlists = []
        for lp in sorted(lists):
            ids = []
            try:
                for line in lp.read_text(encoding="utf-8", errors="replace").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    target = Path(line) if os.path.isabs(line) else (lp.parent / line)
                    # «../Artista/…» se resuelve como texto (sin seguir enlaces: /var y /private/var son lo mismo)
                    tid = by_path.get(_nfc(os.path.normpath(str(target)))) or by_path.get(_nfc(str(target.resolve())))
                    if tid and tid not in ids:
                        ids.append(tid)
            except OSError:
                continue
            if ids:
                playlists.append({"id": _hid("lista", str(lp), n=10), "title": lp.stem, "tracks": ids})
        self.tracks, self.albums, self.artists, self.playlists = tracks, albums, artists, playlists

    # ---------- lo que se manda a la web y a la TV ----------

    def public(self):
        """Todo lo de la música, sin rutas: {artists, albums, tracks, playlists}. Álbumes por artista y año."""
        self.scan()
        with self.lock:
            albums = sorted(self.albums.values(), key=lambda a: (_key(a["artist"]), a["year"] or 9999, _key(a["title"])))
            return {
                "artists": sorted(({"id": ar["id"], "name": ar["name"], "albums": ar["albums"],
                                    "art": f"/music/art/{ar['albums'][0]}.jpg"} for ar in self.artists.values()),
                                  key=lambda ar: _key(ar["name"])),
                "albums": [{"id": a["id"], "title": a["title"], "artist": a["artist"], "year": a["year"],
                            "genre": a["genre"], "tracks": a["tracks"], "duration": a["duration"],
                            "art": f"/music/art/{a['id']}.jpg", "added": int(a["added"])} for a in albums],
                "tracks": {t["id"]: {"id": t["id"], "title": t["title"], "artist": t["artist"], "album": t["album"],
                                     "album_id": t["album_id"], "n": t["n"], "disc": t["disc"],
                                     "duration": t["duration"], "url": f"/music/{t['id']}/audio",
                                     "format": "mp3" if t["codec"] == "mp3" else "aac" if t["codec"] == "aac" and
                                     Path(t["path"]).suffix.lower() == ".aac" else "mp4",
                                     "art": f"/music/art/{t['album_id']}.jpg"} for t in self.tracks.values()},
                "playlists": [{"id": p["id"], "title": p["title"], "tracks": p["tracks"],
                               "art": f"/music/art/{self.tracks[p['tracks'][0]]['album_id']}.jpg"} for p in self.playlists],
            }

    def track(self, tid):
        with self.lock:
            t = self.tracks.get(tid)
            return dict(t) if t else None

    # ---------- portada ----------

    def art(self, aid):
        """Portada del álbum (600 px, jpg) o None."""
        with self.lock:
            a = self.albums.get(aid)
            tracks = [self.tracks[t] for t in a["tracks"]] if a else []
        if not a:
            return None
        out = self.cache / f"portada-{aid}.jpg"
        if out.exists():
            return out
        self.cache.mkdir(parents=True, exist_ok=True)
        src = next((t["path"] for t in tracks if t["art"]), None)
        folder = Path(a["folder"])
        if not src:
            for name in COVER_NAMES:
                for ext in (".jpg", ".jpeg", ".png"):
                    for cand in (folder / (name + ext), folder / (name.capitalize() + ext)):
                        if cand.exists():
                            src = str(cand)
                            break
                    if src:
                        break
                if src:
                    break
        if not src:
            return None
        tmp = out.with_suffix(".tmp.jpg")
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-an", "-map", "0:v:0", "-frames:v", "1",
                            "-vf", f"scale='min({ART_SIZE},iw)':-2", "-q:v", "3", str(tmp)],
                           capture_output=True, timeout=30, stdin=subprocess.DEVNULL)
        if r.returncode == 0 and tmp.exists():
            tmp.replace(out)
            return out
        tmp.unlink(missing_ok=True)
        return None

    # ---------- la canción, lista para sonar ----------

    def audio(self, tid):
        """(ruta, tipo) de la canción lista para cualquier reproductor, o None. MP3/AAC tal cual; lo demás, AAC en caché."""
        t = self.track(tid)
        if not t:
            return None
        if t["codec"] in DIRECT_CODECS:
            ext = Path(t["path"]).suffix.lower()
            return t["path"], "audio/mpeg" if t["codec"] == "mp3" else ("audio/mp4" if ext in (".m4a", ".mp4") else "audio/aac")
        out = self.cache / f"cancion-{tid}.m4a"
        if out.exists():
            return str(out), "audio/mp4"
        with self.convert_lock:
            ev = self.converting.get(tid)
            mine = ev is None
            if mine:
                ev = self.converting[tid] = threading.Event()
        if not mine:
            ev.wait(120)
            return (str(out), "audio/mp4") if out.exists() else None
        try:
            self.cache.mkdir(parents=True, exist_ok=True)
            tmp = out.with_suffix(".tmp.m4a")
            ok = False
            for codec in ("aac_at", "aac"):   # el de macOS suena mejor; si no está, el de ffmpeg
                r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", t["path"], "-map", "0:a:0", "-vn",
                                    "-c:a", codec, "-b:a", "256k", "-movflags", "+faststart", str(tmp)],
                                   capture_output=True, timeout=300, stdin=subprocess.DEVNULL)
                if r.returncode == 0 and tmp.exists() and tmp.stat().st_size > 0:
                    ok = True
                    break
            if ok:
                tmp.replace(out)
            else:
                tmp.unlink(missing_ok=True)
                self.log(f"⚠ Música: no se pudo preparar «{t['title']}»")
        finally:
            with self.convert_lock:
                self.converting.pop(tid, None)
            ev.set()
        return (str(out), "audio/mp4") if out.exists() else None

    def prepare_next(self, tid, count=2):
        """Deja listas (en segundo plano) las que siguen en el álbum: así no hay espera entre canciones."""
        with self.lock:
            t = self.tracks.get(tid)
            a = self.albums.get(t["album_id"]) if t else None
            nxt = []
            if a and tid in a["tracks"]:
                i = a["tracks"].index(tid)
                nxt = a["tracks"][i + 1:i + 1 + count]

        def work():
            for n in nxt:
                self.audio(n)
        if nxt:
            threading.Thread(target=work, daemon=True).start()


def default_roots():
    """Dónde buscar música si config.json no lo dice: ~/Music/Biblioteca (o ~/Music/Music, la carpeta de Música de
    Apple) si existen."""
    home = Path.home() / "Music"
    for cand in (home / "Biblioteca", home / "Music" / "Media.localized" / "Music", home / "Music" / "Media" / "Music"):
        if cand.is_dir():
            return [str(cand)]
    return []
