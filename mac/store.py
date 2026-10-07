"""Progreso ("Seguir viendo") y preferencias de idioma, guardados en la Mac.

La Mac es la única fuente de verdad: el Roku reporta cada pocos segundos qué
se está viendo y por dónde va, y la web y el Roku leen de aquí.
"""

import json
import threading
import time
from pathlib import Path

MIN_SAVE = 30        # menos de esto no cuenta como "empezada"
END_MARGIN = 120     # a menos de 2 min del final se da por vista
NOW_STALE = 40       # sin reportes en este tiempo: ya no se está viendo nada


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.Lock()
        try:
            data = json.loads(self.path.read_text())
        except (OSError, ValueError):
            data = {}
        self.progress = data.get("progress", {})   # id -> {"p": segundos, "t": cuándo}; p=0 = terminada
        self.prefs = data.get("prefs", {})         # {"audioLang": "spa", "subLang": "off"|"eng"...}: ajustes de la casa
        # Idioma por aparato: {id_de_aparato: {"audioLang": "original"|"spa"..., "subLang": "off"|"eng"...}}
        self.device_prefs = data.get("device_prefs", {})
        self.now = None                            # lo que se está viendo ahora mismo

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"progress": self.progress, "prefs": self.prefs,
                                    "device_prefs": self.device_prefs}, ensure_ascii=False))
        tmp.replace(self.path)

    def report(self, item_id, position, duration, event, audio=None, sub=None, state="play", device="tv", live=False,
               song=None, device_id=None):
        """El Roku (o un navegador) avisa: event = start | tick | stop | end.
        Solo lo de la tele cuenta como "lo que se está viendo en la tele". live: una transmisión en vivo de YouTube,
        que no se retoma: entra al historial como vista (p = 0) y nunca a «Seguir viendo».
        La música (ids «track:…») sí cuenta como «lo que suena ahora» —song = {"i": lugar, "n": cuántas}—, pero nunca deja
        avance guardado: no entra a «Seguir viendo» ni al historial.
        device_id: qué TV lo reporta (el Roku o una con Android; las órdenes de la web van a esa, mac/teles.py)."""
        now = time.time()
        with self.lock:
            if device == "tv":
                if event in ("stop", "end"):
                    if self.now and self.now["id"] == item_id:
                        self.now = None
                else:
                    self.now = {"id": item_id, "p": position, "d": duration, "state": state,
                                "audio": audio, "sub": sub, "t": now, "device_id": device_id}
                    if song:
                        self.now["song"] = song
            if item_id.startswith("track:"):
                return
            finished = live or event == "end" or (duration > 0 and (position > duration - END_MARGIN
                                                                     or position > duration * 0.95))
            if finished:
                self.progress[item_id] = {"p": 0, "t": now}
            elif position >= MIN_SAVE:
                self.progress[item_id] = {"p": int(position), "t": now}
            else:
                return
            self._save()

    def import_from_roku(self, entries, prefs):
        """Primera vez: el Roku sube lo que tenía guardado; gana lo más reciente."""
        with self.lock:
            for item_id, e in (entries or {}).items():
                mine = self.progress.get(item_id)
                if not mine or mine["t"] < e.get("t", 0):
                    self.progress[item_id] = {"p": int(e.get("p", 0)), "t": e.get("t", 0)}
            for k, v in (prefs or {}).items():
                self.prefs.setdefault(k, v)
            self._save()

    def set_prefs(self, **prefs):
        with self.lock:
            changed = {k: v for k, v in prefs.items() if v is not None and self.prefs.get(k) != v}
            if changed:
                self.prefs.update(changed)
                self._save()

    def prefs_for(self, device_id=None):
        """Lo que se manda a un cliente: los ajustes de la casa y el idioma de SU aparato. Un aparato sin
        preferencias empieza en «original» y sin subtítulos (las globales viejas no se heredan).
        Sin id de aparato: las de siempre."""
        with self.lock:
            if not device_id:
                return dict(self.prefs)
            out = {k: v for k, v in self.prefs.items() if k not in ("audioLang", "subLang")}
            mine = self.device_prefs.get(device_id) or {}
            out["audioLang"] = mine.get("audioLang") or "original"
            out["subLang"] = mine.get("subLang") or "off"
            return out

    def set_device_prefs(self, device_id, audioLang=None, subLang=None):
        """Guarda el idioma de audio y de subtítulos de un aparato (solo lo que se manda)."""
        device_id = str(device_id or "").strip()[:80]
        if not device_id:
            return
        with self.lock:
            mine = dict(self.device_prefs.get(device_id) or {})
            for key, value in (("audioLang", audioLang), ("subLang", subLang)):
                if value not in (None, ""):
                    mine[key] = str(value).strip().lower()
            if mine and mine != self.device_prefs.get(device_id):
                self.device_prefs[device_id] = mine
                self._save()

    def watching(self):
        """Lo empezado y no terminado, lo más reciente primero."""
        with self.lock:
            rows = [(v["t"], k, v["p"]) for k, v in self.progress.items() if v["p"] > 0]
        return [{"id": k, "p": p} for _, k, p in sorted(rows, reverse=True)]

    def keep_watching(self, items, with_time=False):
        """«Seguir viendo»: lo empezado y, de cada serie, lo último que tocaste: el episodio a medias
        o, si lo terminaste, el inmediato siguiente. Una sola entrada por serie; lo más reciente primero.
        Con with_time cada entrada trae también "t": cuándo se vio por última vez."""
        with self.lock:
            rows = sorted(((v["t"], k, v["p"]) for k, v in self.progress.items()), reverse=True)
            where = {k: v["p"] for k, v in self.progress.items()}
        out, shows = [], set()
        for t, item_id, p in rows:
            it = items.get(item_id)
            if not it:
                continue
            stamp = {"t": t} if with_time else {}
            if it["kind"] != "episode":
                if p > 0:
                    out.append({"id": item_id, "p": p, **stamp})
                continue
            if it["show"] in shows:
                continue
            shows.add(it["show"])
            if p > 0:
                out.append({"id": item_id, "p": p, **stamp})
            elif it.get("next"):
                out.append({"id": it["next"], "p": where.get(it["next"], 0), "next": True, **stamp})
        return out

    def history(self):
        """Todo lo que se vio (terminado o no), lo más reciente primero: una entrada por video."""
        with self.lock:
            rows = sorted(((v["t"], k, v["p"]) for k, v in self.progress.items()), reverse=True)
        return [{"id": k, "p": p, "t": t} for t, k, p in rows]

    def seen(self):
        """Lo que se terminó de ver (para marcar episodios vistos)."""
        with self.lock:
            return [k for k, v in self.progress.items() if v["p"] == 0]

    def now_playing(self):
        with self.lock:
            if self.now and time.time() - self.now["t"] < NOW_STALE:
                return dict(self.now)
            return None
