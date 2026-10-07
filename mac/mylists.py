"""Listas de One TV: «Favoritos» y las listas que se crean desde la TV o la web, con videos de YouTube.

Viven en la computadora (datos/listas.json), no en la cuenta de YouTube: One TV no entra a la cuenta de Google, así
que lo que se cambia aquí no se ve en la app de YouTube.

Las listas que llegaron con el Takeout (mac/ytaccount.py) también se pueden cambiar: lo agregado y lo quitado se
guarda aparte («edits», por lista) y se aplica encima de la lista del Takeout, así importar un Takeout nuevo no lo
borra.

Formato: {"lists": [{"id", "title", "videos": [{id, title, channel, duration, thumb, t}], "t"}],
          "edits": {clave de la lista del Takeout: {"added": [video…], "removed": [id…], "t"}}}
"""

import json
import re
import secrets
import threading
import time
from pathlib import Path

FAV = "fav"
FAV_TITLE = "Favoritos"
TITLE_MAX = 80
MAX_VIDEOS = 5000            # por lista
OWN_ID = re.compile(r"^(fav|ot-[0-9a-f]{8})$")
VIDEO_ID = re.compile(r"^[\w-]{11}$")


def clean_video(v, now):
    """Lo que se guarda de un video: lo justo para mostrarlo sin preguntarle a YouTube."""
    vid = str(v.get("id") or "")
    return {"id": vid, "title": str(v.get("title") or "Video de YouTube")[:300], "channel": str(v.get("channel") or "")[:120],
            "duration": int(v.get("duration") or 0), "thumb": f"/yt/{vid}/thumb.jpg", "t": now}


class MyLists:
    def __init__(self, path, clock=time.time):
        self.path = Path(path)
        self.clock = clock
        self.lock = threading.Lock()
        try:
            data = json.loads(self.path.read_text())
        except (OSError, ValueError):
            data = {}
        self.lists = [l for l in data.get("lists", []) if isinstance(l, dict) and OWN_ID.match(str(l.get("id")))]
        self.edits = data.get("edits", {}) if isinstance(data.get("edits"), dict) else {}
        if not any(l["id"] == FAV for l in self.lists):
            self.lists.insert(0, {"id": FAV, "title": FAV_TITLE, "videos": [], "t": 0})

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"lists": self.lists, "edits": self.edits}, ensure_ascii=False))
        tmp.replace(self.path)

    def _find(self, lid):
        return next((l for l in self.lists if l["id"] == lid), None)

    # ---------- las listas propias ----------

    def owns(self, lid):
        with self.lock:
            return self._find(lid) is not None

    def summaries(self):
        """[{id, title, count, thumb, t, source: "onetv"}]: Favoritos primero y luego la más reciente."""
        with self.lock:
            out = []
            for l in self.lists:
                vids = l["videos"]
                newest = max((v.get("t", 0) for v in vids), default=0)
                cover = (self._ordered(l) or [{}])[0].get("id")
                out.append({"id": l["id"], "title": l["title"], "count": len(vids), "t": int(max(l.get("t", 0), newest)),
                            "thumb": f"/yt/{cover}/thumb.jpg" if cover else "", "source": "onetv"})
        return [o for o in out if o["id"] == FAV] + sorted((o for o in out if o["id"] != FAV), key=lambda o: -o["t"])

    @staticmethod
    def _ordered(l):
        """Favoritos se ven del más reciente al más viejo; las demás listas, en el orden en que se agregaron."""
        return list(reversed(l["videos"])) if l["id"] == FAV else list(l["videos"])

    def get(self, lid):
        """{id, title, videos} (copias) o None si no es una lista propia."""
        with self.lock:
            l = self._find(lid)
            return {"id": l["id"], "title": l["title"], "videos": [dict(v) for v in self._ordered(l)]} if l else None

    def create(self, title):
        title = " ".join(str(title or "").split())[:TITLE_MAX]
        if not title:
            raise ValueError("Escribe un nombre para la lista.")
        with self.lock:
            if title.casefold() == FAV_TITLE.casefold() or any(l["title"].casefold() == title.casefold() for l in self.lists):
                raise ValueError(f"Ya tienes una lista que se llama «{title}».")
            l = {"id": f"ot-{secrets.token_hex(4)}", "title": title, "videos": [], "t": self.clock()}
            self.lists.append(l)
            self._save()
            return {"id": l["id"], "title": l["title"], "count": 0}

    def rename(self, lid, title):
        title = " ".join(str(title or "").split())[:TITLE_MAX]
        if not title:
            raise ValueError("Escribe un nombre para la lista.")
        with self.lock:
            l = self._find(lid)
            if not l:
                raise ValueError("Esa lista ya no existe.")
            if lid == FAV:
                raise ValueError("Favoritos no se puede renombrar.")
            if any(o is not l and o["title"].casefold() == title.casefold() for o in self.lists):
                raise ValueError(f"Ya tienes una lista que se llama «{title}».")
            l["title"] = title
            self._save()

    def delete(self, lid):
        with self.lock:
            if lid == FAV:
                raise ValueError("Favoritos no se puede borrar (puedes quitarle los videos).")
            l = self._find(lid)
            if not l:
                return False
            self.lists.remove(l)
            self._save()
            return True

    def add(self, lid, video):
        """Agrega un video al final (en Favoritos se ve primero). -> True si se agregó, False si ya estaba."""
        if not VIDEO_ID.match(str(video.get("id") or "")):
            raise ValueError("Ese no parece un video de YouTube.")
        with self.lock:
            l = self._find(lid)
            if not l:
                raise ValueError("Esa lista ya no existe.")
            if any(v["id"] == video["id"] for v in l["videos"]):
                return False
            if len(l["videos"]) >= MAX_VIDEOS:
                raise ValueError(f"«{l['title']}» ya tiene {MAX_VIDEOS} videos.")
            now = self.clock()
            l["videos"].append(clean_video(video, now))
            l["t"] = now
            self._save()
            return True

    def remove(self, lid, vid):
        with self.lock:
            l = self._find(lid)
            if not l:
                return False
            before = len(l["videos"])
            l["videos"] = [v for v in l["videos"] if v["id"] != vid]
            if len(l["videos"]) == before:
                return False
            l["t"] = self.clock()
            self._save()
            return True

    def has(self, lid, vid):
        with self.lock:
            l = self._find(lid)
            return bool(l) and any(v["id"] == vid for v in l["videos"])

    def is_favorite(self, vid):
        return self.has(FAV, vid)

    # ---------- cambios a las listas del Takeout ----------

    def edit_takeout(self, key, video=None, remove=None):
        """Agrega `video` (dict) o quita `remove` (id) de una lista del Takeout."""
        with self.lock:
            e = self.edits.setdefault(key, {"added": [], "removed": [], "t": 0})
            now = self.clock()
            if video is not None:
                if not VIDEO_ID.match(str(video.get("id") or "")):
                    raise ValueError("Ese no parece un video de YouTube.")
                e["removed"] = [r for r in e["removed"] if r != video["id"]]
                if not any(a["id"] == video["id"] for a in e["added"]):
                    e["added"].append(clean_video(video, now))
            if remove is not None:
                e["added"] = [a for a in e["added"] if a["id"] != remove]
                if remove not in e["removed"]:
                    e["removed"].append(remove)
            e["t"] = now
            self._save()

    def apply_edits(self, key, videos):
        """La lista del Takeout con lo agregado (al final) y sin lo quitado."""
        with self.lock:
            e = self.edits.get(key)
            if not e:
                return list(videos)
            removed = set(e["removed"])
            out = [v for v in videos if v["id"] not in removed]
            have = {v["id"] for v in out}
            out += [dict(a) for a in e["added"] if a["id"] not in have]
            return out

    def edited_at(self, key):
        with self.lock:
            return (self.edits.get(key) or {}).get("t", 0)
