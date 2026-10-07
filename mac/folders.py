"""¿De quién es cada carpeta de la biblioteca? One TV solo mueve, renombra o escribe dentro de las suyas.

Mucha gente ya tiene su biblioteca acomodada para Plex, Jellyfin o Emby (casi siempre en un NAS) y quiere probar One TV
junto a ese programa sin que nada cambie. Esas carpetas One TV las usa SOLO PARA LEER: el organizador no mueve ni
renombra nada ahí, no se agregan doblajes junto a esos videos, y los subtítulos que se bajan para ellos se guardan en
una carpeta de One TV (entre sus datos), donde la biblioteca también los busca.

La regla, en este orden:
1. Si la carpeta no está (el NAS o el disco sin conectar), no se toca nada ahí.
2. Si One TV no puede escribir en ella (un disco de solo lectura, el «:ro» de Docker, sin permiso): solo se lee.
3. Lo que diga config.json → "solo_leer": {"carpeta": true} (solo leer) o {"carpeta": false} (One TV la ordena).
   También vale una lista: "solo_leer": ["carpeta"]. `./cine configurar` lo pregunta y lo anota.
4. Lo que ya se decidió antes para esa carpeta: se recuerda, así una carpeta no cambia de dueño sola. Se recuerda junto
   con el disco en que está: si en esa ruta aparece otro disco (en Linux, la carpeta vacía donde después se monta el
   NAS), se vuelve a mirar.
5. Si no, se mira qué tiene (la primera vez que One TV la ve):
   - ningún video todavía: es de One TV (lo que se suelte ahí después se ordena, como siempre);
   - Películas/ o Series/ con los códigos de One TV ({imdb-tt…}, {tvdb-…}) en al menos la mitad de lo que hay
     adentro (o vacías): es de One TV;
   - videos acomodados de otra forma (Movies/, TV Shows/, Películas/ sin códigos, carpetas por película…): es de
     otro programa y solo se lee.
"""

import json
import os
import threading
import unicodedata
from pathlib import Path

from library import SKIP_DIRS, VIDEO_EXTS, video_id

OWN, OTHER = "propia", "ajena"
TAGS = {"películas": "{imdb-tt", "series": "{tvdb-"}


def _nfc(text):
    return unicodedata.normalize("NFC", text)


def _path(folder):
    return Path(os.path.expanduser(str(folder))).resolve()


def read_only_setting(value):
    """config.json → "solo_leer" como {carpeta: True/False}. Acepta un diccionario o una lista (todas de solo leer)."""
    if isinstance(value, (list, tuple)):
        value = {folder: True for folder in value}
    if not isinstance(value, dict):
        return {}
    return {_path(folder): bool(flag) for folder, flag in value.items() if str(folder).strip()}


def has_videos(folder):
    """¿Hay al menos un video en la carpeta (o más adentro)? Se detiene en el primero."""
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and _nfc(d).lower() not in SKIP_DIRS]
        if any(not f.startswith(".") and Path(f).suffix.lower() in VIDEO_EXTS for f in filenames):
            return True
    return False


def looks_like_one_tv(folder):
    """¿Tiene Películas/ o Series/ como las deja One TV (con sus códigos en al menos la mitad de lo que hay adentro)?"""
    found, tagged, total = False, 0, 0
    for entry in os.scandir(folder):
        tag = TAGS.get(_nfc(entry.name).lower())
        if not tag or not entry.is_dir():
            continue
        found = True
        for sub in os.scandir(entry.path):
            if sub.name.startswith("."):
                continue
            total += 1
            tagged += tag in sub.name
    return found and tagged * 2 >= total


def writable(folder):
    return os.access(folder, os.W_OK | os.X_OK)


class LibraryFolders:
    """Qué carpetas de la biblioteca son de One TV. La usan el organizador, los subtítulos bajados y los doblajes."""

    def __init__(self, roots, read_only=None, state_file=None, subs_dir=None, log=print):
        self.roots = [_path(r) for r in roots]
        self.forced = read_only_setting(read_only)
        self.state_file = Path(state_file) if state_file else None
        self.subs_dir = Path(subs_dir) if subs_dir else None
        self.log = log
        self.lock = threading.Lock()
        self.told = set()   # carpetas que ya se anunciaron en el registro
        try:
            self.decided = json.loads(self.state_file.read_text()) if self.state_file else {}
        except (OSError, ValueError):
            self.decided = {}
        for root in self.roots:   # se decide al ver cada carpeta por primera vez (vacía = de One TV)
            self.why(root)

    def _remember(self, root, how):
        try:
            disk = os.stat(root).st_dev
        except OSError:
            return
        self.decided[str(root)] = {"como": how, "disco": disk}
        if not self.state_file:
            return
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.state_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.decided, ensure_ascii=False, indent=1))
            tmp.replace(self.state_file)
        except OSError:
            pass

    def why(self, root):
        """(¿es de One TV?, motivo). (None, motivo) si la carpeta no está."""
        root = _path(root)
        if not root.is_dir():
            return None, "no está (¿el disco o el NAS sin conectar?)"
        if not writable(root):
            return False, "One TV no puede escribir ahí"
        if root in self.forced:
            return (not self.forced[root]), "así lo dice config.json (solo_leer)"
        with self.lock:
            known = self.decided.get(str(root)) or {}
            try:
                same_disk = known.get("disco") == os.stat(root).st_dev
            except OSError:
                same_disk = False
            if known and same_disk:
                mine = known.get("como") == OWN
                return mine, ("es de One TV" if mine else "ya tiene videos acomodados por otro programa")
            try:
                if looks_like_one_tv(root):
                    self._remember(root, OWN)
                    return True, "es de One TV"
                if not has_videos(root):
                    self._remember(root, OWN)
                    return True, "todavía no tenía videos"
            except OSError:
                return None, "no se pudo leer"
            self._remember(root, OTHER)
            return False, "ya tiene videos acomodados por otro programa"

    def own(self, root):
        """True: One TV la ordena. False: solo se lee. None: no está (no se toca)."""
        root = _path(root)
        mine, why = self.why(root)
        if mine is False and root not in self.told:
            self.told.add(root)
            self.log(f"· Biblioteca: {root} se usa solo para leer ({why}); One TV no mueve ni cambia nada ahí.")
        return mine

    def own_roots(self):
        """Las carpetas de One TV que están conectadas, en el orden de config.json."""
        return [r for r in self.roots if self.own(r)]

    def root_of(self, path):
        """La carpeta de la biblioteca que contiene ese archivo (la más honda, si una está dentro de otra)."""
        path = Path(path)
        path = path.parent.resolve() / path.name   # la carpeta tal como la ven las raíces (sin seguir el archivo)
        inside = [r for r in self.roots if r == path or r in path.parents]
        return max(inside, key=lambda r: len(r.parts), default=None)

    def can_write_next_to(self, video):
        """¿Se puede guardar algo junto a este video? Solo si está en una carpeta de One TV."""
        root = self.root_of(video)
        return bool(root and self.own(root))

    def subtitle_dirs(self, video):
        """Dónde guardar un subtítulo bajado para este video, en orden: junto al video si su carpeta es de One TV; si no
        (o si ahí falla), en la carpeta de subtítulos de One TV, donde la biblioteca también los busca."""
        video = Path(video)
        kept = [self.subs_dir / video_id(video)] if self.subs_dir else []
        return ([video.parent] if self.can_write_next_to(video) else []) + kept

    def summary(self):
        """[(carpeta, texto)] para mostrar al arrancar."""
        out = []
        for root in self.roots:
            mine, why = self.why(root)
            if mine is None:
                out.append((root, f"no está: {why}"))
            elif mine:
                out.append((root, "de One TV: ordena lo nuevo"))
            else:
                out.append((root, f"solo para leer ({why}): One TV no mueve ni cambia nada ahí"))
        return out
