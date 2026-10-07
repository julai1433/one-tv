"""Doblaje latino para lo que no lo tiene, tomado de otra versión de la misma película o episodio.

Cuando llega otra versión de algo que ya está en la biblioteca (terminó de bajarse en Transmission, o la
dejaste en la biblioteca) y esa versión trae el audio latino que a la nuestra le falta:
1. se compara el audio de las dos versiones para saber cómo se corresponden (mac/dubsync.py);
2. se toma SOLO el audio latino, se ajusta al video de la biblioteca y se guarda junto a él como
   «Película.latino.m4a». El video no se toca.
3. La otra versión: si vino de Descargas, se queda donde está (Transmission la sigue compartiendo; se
   puede borrar desde Transmission). Si la dejaste en la biblioteca, se mueve a ~/Movies/Doblajes ya usados.
La sincronización necesita numpy: vive en su propio entorno, que se instala solo la primera vez.
"""

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from library import latino_track, needs_latino, probe

PACKAGES = ["numpy"]
TIMEOUT = 45 * 60          # una película de 4K muy pesada tarda en leerse entera
RETRY_AFTER = 3600         # si algo falló por falta de internet o disco, se reintenta en una hora
MAX_TRIES = 3
LANG_ALIASES = {"en": "eng", "es": "spa", "esp": "spa", "lat": "spa", "fr": "fre", "fra": "fre", "de": "ger",
                "deu": "ger", "it": "ita", "ja": "jpn", "zh": "chi", "zho": "chi", "pt": "por", "ko": "kor",
                "ru": "rus"}


def _lang(code):
    code = (code or "und").lower()
    return LANG_ALIASES.get(code, code)


def sidecar_path(video):
    video = Path(video)
    return video.with_name(f"{video.stem}.latino.m4a")


class Dubbing:
    def __init__(self, env_dir, script, state_file, used_dir, log=print, on_added=None):
        self.env_dir = Path(env_dir)
        self.script = Path(script)
        self.state_file = Path(state_file)
        self.used_dir = Path(used_dir)
        self.log = log
        self.on_added = on_added
        self.lock = threading.Lock()
        self.env_lock = threading.Lock()   # la detección de entradas de series usa el mismo entorno
        self.wake = threading.Event()
        self.current = None
        try:
            self.state = json.loads(self.state_file.read_text())
        except (OSError, ValueError):
            self.state = {}
        self.state.setdefault("jobs", {})   # otra versión -> {"lib", "how", "status", …}
        threading.Thread(target=self._worker, daemon=True).start()

    def _save(self):
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, ensure_ascii=False, indent=1))
        tmp.replace(self.state_file)

    # ---------- qué hay que hacer ----------

    def consider(self, donor, have, how):
        """El organizador encontró otra versión de algo que ya está en la biblioteca. ¿Sirve su audio?"""
        donor = Path(donor)
        lib = Path(have) if have else None
        if not lib or not lib.is_file() or not donor.is_file() or lib.resolve() == donor.resolve():
            return False
        with self.lock:
            if str(donor) in self.state["jobs"]:
                return False
        if sidecar_path(lib).exists():
            return False
        lib_info, donor_info = probe(lib), probe(donor)
        if not lib_info or not donor_info or not lib_info["audio"] or not lib_info["video"]:
            return False
        if not needs_latino(lib, lib_info) or not latino_track(donor, donor_info):
            return False
        with self.lock:
            self.state["jobs"][str(donor)] = {"lib": str(lib), "how": how, "status": "pendiente",
                                              "title": lib.stem, "t": time.time(), "tries": 0}
            self._save()
        self.log(f"🎙 La otra versión de «{lib.stem}» trae doblaje latino: se va a agregar")
        self.wake.set()
        return True

    def summary(self):
        with self.lock:
            jobs = sorted(self.state["jobs"].values(), key=lambda j: j["t"], reverse=True)
            return {"working": self.current,
                    "pending": sum(j["status"] == "pendiente" for j in jobs),
                    "recent": [{"title": j["title"], "status": j["status"], "why": j.get("why", ""),
                                "via": j.get("via", ""), "t": j["t"]} for j in jobs[:15]]}

    # ---------- el trabajo, de uno en uno ----------

    def _next(self):
        now = time.time()
        with self.lock:
            return next((k for k, j in self.state["jobs"].items()
                         if j["status"] == "pendiente" and j.get("next_at", 0) <= now), None)

    def _update(self, key, **fields):
        with self.lock:
            self.state["jobs"][key].update(fields, t=time.time())
            self._save()

    def _worker(self):
        time.sleep(20)
        while True:
            key = self._next()
            if not key:
                self.wake.wait(600)
                self.wake.clear()
                continue
            job = self.state["jobs"][key]
            self.current = job["title"]
            try:
                self._run(key, job)
            except Exception as e:  # noqa: BLE001 - un doblaje fallido no debe tumbar el servidor
                tries = job.get("tries", 0) + 1
                final = tries >= MAX_TRIES
                self._update(key, tries=tries, next_at=time.time() + RETRY_AFTER,
                             status="falló" if final else "pendiente", why=str(e)[:200])
                self.log(f"⚠ Doblaje latino de «{job['title']}»: {e}" + ("" if final else " (se reintenta en 1 h)"))
            finally:
                self.current = None

    def _run(self, key, job):
        donor, lib = Path(key), Path(job["lib"])
        if not donor.is_file() or not lib.is_file():
            return self._update(key, status="falló", why="uno de los dos archivos ya no está")
        if sidecar_path(lib).exists():
            return self._update(key, status="listo", why="ya tenía la pista")
        python = self.python()
        lib_info, donor_info = probe(lib), probe(donor)
        if not lib_info or not donor_info:
            raise RuntimeError("no se pudieron leer los archivos")
        latino = latino_track(donor, donor_info)
        # Referencia: la pista original de nuestro video (la que no es español).
        ref = next((a for a in lib_info["audio"] if _lang(a["lang"]) != "spa"), lib_info["audio"][0])
        same = None
        if _lang(ref["lang"]) != "und":
            same = next((a for a in donor_info["audio"]
                         if a is not latino and _lang(a["lang"]) == _lang(ref["lang"])), None)
        tries = ([(same, "mismo", "el audio original")] if same else []) + \
                [(latino, "distinto", "la música y los efectos")]
        found, last = None, {}
        for track, mode, via in tries:
            last = self._dubsync(python, "analizar", lib, ref["index"], ref["channels"],
                                 donor, track["index"], track["channels"], mode)
            if last.get("ok"):
                found = (last, via)
                break
        if not found:
            why = last.get("why") or "no se pudo sincronizar"
            self._update(key, status="no sirve", why=why)
            self.log(f"✗ Doblaje latino de «{job['title']}»: {why}")
            return
        r, via = found
        tmp = lib.with_name(f".{lib.stem}.latino.tmp.m4a")
        title = "Latino"
        out = self._dubsync(python, "preparar", donor, latino["index"], latino["channels"],
                            f"{r['a']:.8f}", f"{r['b']:.4f}", f"{lib_info['duration']:.3f}", tmp, title)
        if not out.get("ok"):
            tmp.unlink(missing_ok=True)
            raise RuntimeError(out.get("why") or "ffmpeg no pudo escribir la pista")
        tmp.replace(sidecar_path(lib))
        note = ""
        if job["how"] == "move":   # la dejaste en la biblioteca: se aparta para que no salga repetida
            self.used_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(donor), str(self.used_dir / donor.name))
            note = "; la otra versión quedó en «Doblajes ya usados»"
        speed = "" if abs(r["a"] - 1) < 1e-3 else f", velocidad ×{1 / r['a']:.4f}"
        self._update(key, status="listo", via=via, a=r["a"], b=r["b"], points=f"{r['inliers']}/{r['anchors']}")
        self.log(f"✓ Doblaje latino agregado a «{job['title']}» (sincronizado por {via}: "
                 f"{r['inliers']} de {r['anchors']} puntos, desfase {r['b']:+.2f} s{speed}{note})")
        if self.on_added:
            self.on_added()

    # ---------- herramientas ----------

    def _dubsync(self, python, *args):
        env = {**os.environ, "OMP_NUM_THREADS": "2", "OPENBLAS_NUM_THREADS": "2", "VECLIB_MAXIMUM_THREADS": "2"}
        # Prioridad baja: que no le quite fluidez a lo que se esté viendo ni caliente la Mac.
        cmd = ["nice", "-n", "15", str(python), str(self.script)] + [str(a) for a in args]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT, stdin=subprocess.DEVNULL, env=env)
        try:
            return json.loads(r.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            lines = (r.stderr or "").strip().splitlines()
            raise RuntimeError(lines[-1][:200] if lines else "la sincronización se cortó") from None

    def python(self):
        """El Python con numpy (lo instala la primera vez). También lo usa mac/intro.py."""
        with self.env_lock:
            return self._ensure_env()

    def _ensure_env(self):
        python = self.env_dir / "bin" / "python"
        if python.exists() and subprocess.run([str(python), "-c", "import numpy"], capture_output=True,
                                              stdin=subprocess.DEVNULL).returncode == 0:
            return python
        shutil.rmtree(self.env_dir, ignore_errors=True)
        subprocess.run([sys.executable, "-m", "venv", str(self.env_dir)], check=True, capture_output=True, timeout=300)
        r = subprocess.run([str(self.env_dir / "bin" / "pip"), "install", "-q", *PACKAGES],
                           capture_output=True, text=True, timeout=900, stdin=subprocess.DEVNULL)
        if r.returncode != 0:
            lines = (r.stderr or "").strip().splitlines()
            raise RuntimeError("no se pudo instalar numpy" + (f": {lines[-1][:120]}" if lines else ""))
        self.log("✓ Herramienta para sincronizar doblajes instalada")
        return python
