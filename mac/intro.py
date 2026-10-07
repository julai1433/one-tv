"""«Saltar intro» en las series: dónde empieza y termina la entrada de cada episodio.

No hay una base pública con esos tiempos; se averiguan en la Mac comparando el audio de los episodios de
una misma temporada (la canción de entrada se repite en todos, ver mac/introsync.py). Aquí se decide QUÉ
revisar y se guardan los resultados:
- De a una temporada por vez, en un hilo aparte y con prioridad baja, unos minutos después de arrancar y
  luego cada 10 min, por si llegaron episodios.
- Una temporada se vuelve a revisar solo si cambió (llegó o se reemplazó un episodio). Las que no tienen
  entrada se recuerdan, para no repetirlas en cada vuelta.
- Las marcas quedan en datos/intros.json. La tele solo AVISA («Saltar intro»): OK salta; nunca salta sola.
La comparación necesita numpy: usa el mismo entorno que la sincronización de doblajes (no instala otro).
"""

import hashlib
import json
import os
import subprocess
import threading
import time
from collections import Counter
from pathlib import Path

import hostos

START_DELAY = 5 * 60      # que el servidor arranque tranquilo (pósters, fotogramas clave…)
CHECK_EVERY = 10 * 60
TIMEOUT = 40 * 60         # una temporada larga con archivos muy pesados
RETRY_AFTER = 3600
MAX_TRIES = 3
LABEL = "Saltar intro"


def pick_tracks(infos):
    """La pista que se compara en cada episodio: la del idioma que tienen todos (casi siempre el original).
    infos: el ffprobe de cada episodio. Devuelve [pista o None] en el mismo orden."""
    own = [[a for a in (info or {}).get("audio", []) if isinstance(a["index"], int)] for info in infos]
    count = Counter(lang for tracks in own for lang in {(a["lang"] or "und").lower() for a in tracks})
    first = next((tracks for tracks in own if tracks), [])
    order = {(a["lang"] or "und").lower(): n for n, a in enumerate(first)}
    lang = min(count, key=lambda code: (-count[code], order.get(code, 99)), default=None)
    out = []
    for tracks in own:
        out.append(next((a for a in tracks if (a["lang"] or "und").lower() == lang), None)
                   or next((a for a in tracks if a["default"]), None) or (tracks[0] if tracks else None))
    return out


def run_introsync(python, script, episodes, detail=False, timeout=TIMEOUT):
    """episodes: [(ruta, pista, canales, duración)]. Devuelve el JSON de introsync.py (y su stderr si detail)."""
    env = {**os.environ, "OMP_NUM_THREADS": "2", "OPENBLAS_NUM_THREADS": "2", "VECLIB_MAXIMUM_THREADS": "2"}
    args = [str(x) for ep in episodes for x in (ep[0], ep[1], ep[2], f"{ep[3]:.1f}")]
    # Prioridad baja: que no le quite fluidez a lo que se esté viendo ni caliente la Mac.
    cmd = hostos.low_priority([python, script, "detectar", *args] + (["--detalle"] if detail else []))
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL, env=env,
                       **hostos.LOW_PRIORITY)
    try:
        result = json.loads(r.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        lines = (r.stderr or "").strip().splitlines()
        raise RuntimeError(lines[-1][:200] if lines else "la detección se cortó") from None
    if detail:
        result["detail"] = r.stderr
    return result


def _signature(items):
    """Cambia si llega, se va o se reemplaza un episodio de la temporada."""
    parts = sorted(f"{it['id']}:{it['size']}" for it in items)
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:12]


class IntroDetector:
    def __init__(self, dubbing, script, state_file, log=print):
        self.dubbing = dubbing          # su entorno de numpy (el de los doblajes) sirve igual
        self.script = Path(script)
        self.state_file = Path(state_file)
        self.log = log
        self.lock = threading.Lock()
        self.queue = []                 # temporadas por revisar, en orden
        self.current = None
        try:
            self.state = json.loads(self.state_file.read_text())
        except (OSError, ValueError):
            self.state = {}
        self.state.setdefault("seasons", {})   # "serie/T1" -> {"sig", "status", "found", …}
        self.state.setdefault("marks", {})     # id del episodio -> {"start", "end", "confidence", "season"}

    def _save(self):
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, ensure_ascii=False, indent=1))
        tmp.replace(self.state_file)

    # ---------- lo que ven la tele y la web ----------

    def marks(self, item_id):
        with self.lock:
            m = self.state["marks"].get(item_id)
        if not m:
            return []
        return [{"kind": "intro", "start": m["start"], "end": m["end"], "label": LABEL}]

    def summary(self):
        with self.lock:
            seasons = sorted(self.state["seasons"].values(), key=lambda s: s["t"], reverse=True)
            return {"working": self.current, "pending": len(self.queue), "marked": len(self.state["marks"]),
                    "seasons": [{"show": s["show"], "season": s["season"], "status": s["status"],
                                 "found": s.get("found", 0), "episodes": s["episodes"], "intro": s.get("intro"),
                                 "why": s.get("why", ""), "t": s["t"]} for s in seasons]}

    # ---------- qué hay que revisar ----------

    def consider(self, library):
        """Encola las temporadas que nunca se revisaron o que cambiaron. Devuelve cuántas encoló."""
        items, now, added = library.items, time.time(), 0
        for show in library.series:
            for season in show["seasons"]:
                eps = [items[e["id"]] for e in season["items"] if e["id"] in items]
                tracks = pick_tracks([it["info"] for it in eps])
                job_eps = [{"id": it["id"], "path": it["path"], "ep": it.get("ep", ""), "index": t["index"],
                            "channels": t["channels"], "duration": it["duration"]}
                           for it, t in zip(eps, tracks) if t]
                if len(job_eps) < 2:   # con un solo episodio no hay con qué comparar
                    continue
                key = f"{show['key']}/T{season['season']}"
                sig = _signature(eps)
                with self.lock:
                    old = self.state["seasons"].get(key)
                    if old and old["sig"] == sig and not (old["status"] == "falló" and old.get("tries", 0) < MAX_TRIES
                                                          and old.get("next_at", 0) <= now):
                        continue
                    job = {"key": key, "show": show["title"], "season": season["season"], "sig": sig,
                           "episodes": job_eps, "tries": old.get("tries", 0) if old and old["sig"] == sig else 0}
                    queued = next((n for n, q in enumerate(self.queue) if q["key"] == key), None)
                    if queued is not None:
                        self.queue[queued] = job   # llegó otro episodio mientras esperaba: se revisa con todos
                    else:
                        self.queue.append(job)
                        added += 1
        return added

    # ---------- el trabajo, de a una temporada ----------

    def watch(self, library):
        """Tarea automática: espera unos minutos tras arrancar y luego revisa cada 10 min."""
        time.sleep(START_DELAY)
        while True:
            try:
                self.consider(library)
                while self._run_next():
                    pass
            except Exception as e:  # noqa: BLE001 - nunca debe tumbar el servidor
                self.log(f"⚠ Entradas de series: {e}")
            time.sleep(CHECK_EVERY)

    def _run_next(self):
        with self.lock:
            if not self.queue:
                return False
            job = self.queue.pop(0)
        while self.dubbing.current:   # un doblaje en curso: primero ese (los dos leen archivos enteros)
            time.sleep(60)
        self.current = f"{job['show']} · T{job['season']}"
        t0 = time.time()
        try:
            python = self.dubbing.python()
            eps = job["episodes"]
            r = run_introsync(python, self.script, [(e["path"], e["index"], e["channels"], e["duration"]) for e in eps])
            if not r.get("ok"):
                raise RuntimeError(r.get("why") or "no se pudo comparar")
        except Exception as e:  # noqa: BLE001 - una temporada fallida no debe frenar a las demás
            tries = job["tries"] + 1
            with self.lock:
                self.state["seasons"][job["key"]] = {
                    "show": job["show"], "season": job["season"], "sig": job["sig"], "status": "falló",
                    "episodes": len(job["episodes"]), "why": str(e)[:200], "tries": tries,
                    "next_at": time.time() + RETRY_AFTER, "t": time.time()}
                self._save()
            self.log(f"⚠ Entrada de «{job['show']}» T{job['season']}: {e}"
                     + (" (se reintenta en 1 h)" if tries < MAX_TRIES else ""))
            return True
        finally:
            self.current = None
        found = [(e, m) for e, m in zip(eps, r["episodes"]) if m]
        lengths = sorted(m["end"] - m["start"] for _, m in found)
        intro = round(lengths[len(lengths) // 2]) if lengths else None
        with self.lock:
            self.state["marks"] = {k: v for k, v in self.state["marks"].items() if v.get("season") != job["key"]}
            for e, m in found:
                self.state["marks"][e["id"]] = {"start": m["start"], "end": m["end"],
                                                "confidence": m["confidence"], "season": job["key"]}
            self.state["seasons"][job["key"]] = {
                "show": job["show"], "season": job["season"], "sig": job["sig"],
                "status": "listo" if found else "sin entrada", "found": len(found), "episodes": len(eps),
                "intro": intro, "secs": round(time.time() - t0), "t": time.time()}
            self._save()
        if found:
            self.log(f"✓ Entrada de «{job['show']}» T{job['season']}: {len(found)} de {len(eps)} episodios "
                     f"(~{intro} s)")
        else:
            self.log(f"– «{job['show']}» T{job['season']}: no tiene una entrada que se repita")
        return True
