"""Subtítulos que se alinean solos con la voz del video.

Los subtítulos que no vienen dentro del video (los que se bajan de internet y los .srt que se ponen junto
al video) muchas veces se hicieron para otra versión: empiezan antes o después, van a otra velocidad
(23,976 / 24 / 25 cuadros por segundo) o les sobra o les falta una escena. One TV los corrige solo:

1. Se escucha dónde hay voz en el audio del video y se compara con cuándo hay un subtítulo en pantalla
   (mac/subsync_voz.py, que necesita numpy y usa el mismo entorno que la sincronización de doblajes).
2. Se busca la correspondencia: un desfase fijo, una velocidad distinta y, si hace falta, saltos a medio
   video (por tramos, como la herramienta «alass»: cada salto cuesta, así que solo se acepta si mejora
   mucho la coincidencia). Las líneas de una escena que este video no tiene se quitan.
3. Solo se corrige si la coincidencia es clara; si no, el subtítulo queda como está (y se anota).
4. El archivo original nunca se toca: el corregido se guarda en la caché y es el que reciben la tele y la
   web, con el mismo nombre de pista. Si se borra la caché, se vuelve a escribir con la corrección anotada.

Corre solo, en un hilo aparte y con prioridad baja: unos minutos después de arrancar (una vez para los que
ya están) y en cuanto llega un subtítulo nuevo (bajado o puesto junto al video). El resultado queda en
datos/subtitulos_alineados.json y en el registro; no se repite si ni el subtítulo ni el video cambiaron.
Los subtítulos que vienen dentro del video no se tocan.
"""

import hashlib
import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path

import hostos

START_DELAY = 4 * 60      # que el servidor arranque tranquilo
CHECK_EVERY = 2 * 60      # por si pusiste un .srt junto a un video (los bajados avisan al momento)
TIMEOUT = 30 * 60         # una película larga con un audio muy pesado
RETRY_AFTER = 3600
MAX_TRIES = 3
SPANISH = {"spa", "es", "esp", "lat"}
TIME_RE = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{1,2})[,.](\d{1,3})")
# Velocidad de los subtítulos respecto al video -> cuadros por segundo (para el registro).
FPS_NAMES = {25 / 23.976: ("25", "23,976"), 23.976 / 25: ("23,976", "25"), 24 / 23.976: ("24", "23,976"),
             23.976 / 24: ("23,976", "24"), 25 / 24: ("25", "24"), 24 / 25: ("24", "25")}


# ---------- leer, corregir y escribir subtítulos (sin numpy: también lo usa el servidor) ----------

def decode(raw):
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def _secs(m):
    h, mi, s, ms = m.groups()
    return int(h or 0) * 3600 + int(mi) * 60 + int(s) + int(ms.ljust(3, "0")) / 1000


def parse(text):
    """Las líneas de un .srt o .vtt, en el orden del archivo: [{"start", "end", "text"}] (segundos)."""
    cues = []
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n").replace("\r", "\n")):
        lines = block.strip("\n").split("\n")
        idx = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if idx is None:
            continue
        a, _, b = lines[idx].partition("-->")
        ma, mb = TIME_RE.search(a), TIME_RE.search(b)
        if not ma or not mb:
            continue
        start, end = _secs(ma), _secs(mb)
        cues.append({"start": start, "end": max(end, start), "text": "\n".join(lines[idx + 1:]).strip("\n")})
    return cues


def read(path):
    return parse(decode(Path(path).read_bytes()))


def _stamp(t):
    ms = int(round(max(t, 0.0) * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def to_srt(cues):
    return "\n".join(f"{n}\n{_stamp(c['start'])} --> {_stamp(c['end'])}\n{c['text']}\n"
                     for n, c in enumerate(cues, 1))


def apply(cues, fix):
    """Las líneas corregidas: t_video = velocidad · t_subtítulo + desfase de su tramo. Los tramos son
    [[desde (en tiempo del subtítulo), desfase]]; «quitar» son los tramos del subtítulo que el video no tiene."""
    speed = float(fix.get("speed", 1.0))
    segments = sorted(fix.get("segments") or [[0.0, 0.0]])
    drop = fix.get("quitar") or []
    out = []
    for c in cues:
        if any(a <= c["start"] < b for a, b in drop):
            continue
        offset = segments[0][1]
        for since, o in segments:
            if c["start"] < since:
                break
            offset = o
        start, end = speed * c["start"] + offset, speed * c["end"] + offset
        if end <= 0.05:   # quedaría antes de que empiece el video
            continue
        out.append({**c, "start": max(start, 0.0), "end": end})
    out.sort(key=lambda c: c["start"])
    return out


def _num(x, digits=1):
    return f"{x:.{digits}f}".replace(".", ",")


def describe(fix):
    """La corrección en palabras, para el registro: «se atrasan 2,3 s; velocidad de 25 a 23,976 cuadros…»."""
    parts = []
    segments = fix.get("segments") or [[0.0, 0.0]]
    if len(segments) == 1:
        o = segments[0][1]
        if abs(o) >= 0.05:
            parts.append(f"se {'atrasan' if o > 0 else 'adelantan'} {_num(abs(o))} s")
    else:
        first, last = segments[0][1], segments[-1][1]
        parts.append(f"{len(segments) - 1} {'salto' if len(segments) == 2 else 'saltos'} a medio video "
                     f"(de {_num(first, 1)} s a {_num(last, 1)} s de desfase)")
    speed = float(fix.get("speed", 1.0))
    if abs(speed - 1) > 1e-4:
        names = next((v for k, v in FPS_NAMES.items() if abs(k - speed) < 1e-4), None)
        parts.append(f"velocidad de {names[0]} a {names[1]} cuadros por segundo" if names
                     else f"velocidad ×{_num(speed, 4)}")
    if fix.get("dropped"):
        parts.append(f"sin {fix['dropped']} líneas de una escena que este video no tiene")
    return "; ".join(parts) or "sin cambios"


# ---------- el trabajo en segundo plano ----------

def pick_track(info):
    """La pista con la que se compara: la original (la que no es español); si no, la principal."""
    tracks = [a for a in (info or {}).get("audio", []) if isinstance(a.get("index"), int)]
    if not tracks:
        return None
    return next((a for a in tracks if (a.get("lang") or "und").lower() not in SPANISH), None) \
        or next((a for a in tracks if a.get("default")), tracks[0])


def _sig(sub_file, video):
    """Cambia si se reemplaza el subtítulo o el video."""
    a, b = os.stat(sub_file), os.stat(video)
    return f"{a.st_size}:{int(a.st_mtime)}:{b.st_size}:{int(b.st_mtime)}"


def run_subsync(python, script, video, index, channels, subs, cache=None, timeout=TIMEOUT):
    """Corre mac/subsync_voz.py (con numpy y prioridad baja). Devuelve su JSON."""
    env = {**os.environ, "OMP_NUM_THREADS": "2", "OPENBLAS_NUM_THREADS": "2", "VECLIB_MAXIMUM_THREADS": "2"}
    cmd = hostos.low_priority([python, script, "alinear", video, index, channels, *subs]
                              + (["--cache", cache] if cache else []))
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL, env=env,
                       **hostos.LOW_PRIORITY)
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        lines = (r.stderr or "").strip().splitlines()
        raise RuntimeError(lines[-1][:200] if lines else "el análisis del audio se cortó") from None


class SubtitleAligner:
    def __init__(self, dubbing, script, state_file, out_dir, log=print):
        self.dubbing = dubbing          # su entorno de numpy (el de los doblajes) sirve igual
        self.script = Path(script)
        self.state_file = Path(state_file)
        self.out_dir = Path(out_dir)    # en la caché: los corregidos y la voz de cada video
        self.log = log
        self.lock = threading.Lock()
        self.wake = threading.Event()
        self.queue = []
        self.current = None
        self.env_retry_at = 0           # si no se pudo instalar numpy (sin internet), cuándo reintentar
        try:
            self.state = json.loads(self.state_file.read_text())
        except (OSError, ValueError):
            self.state = {}
        self.state.setdefault("subs", {})   # subtítulo -> {video -> {"sig", "status", "fix", …}}

    def _save(self):
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, ensure_ascii=False, indent=1))
        tmp.replace(self.state_file)

    def _entry(self, sub_file, video):
        with self.lock:
            return self.state["subs"].get(str(sub_file), {}).get(str(video))

    def _out(self, sub_file, video):
        return self.out_dir / (hashlib.sha1(f"{video}|{sub_file}".encode()).hexdigest()[:16] + ".srt")

    # ---------- lo que reciben la tele y la web ----------

    def aligned(self, video, sub_file):
        """El subtítulo corregido para ese video, o None (entonces se usa el original tal cual)."""
        e = self._entry(sub_file, video)
        if not e or e.get("status") != "alineado":
            return None
        try:
            if _sig(sub_file, video) != e["sig"]:
                return None   # cambió el subtítulo o el video: hasta revisarlo de nuevo, el original
        except OSError:
            return None
        out = self._out(sub_file, video)
        if not out.exists():   # se borró la caché: se vuelve a escribir con la corrección anotada
            try:
                self._write(sub_file, e["fix"], out)
            except (OSError, ValueError, KeyError):
                return None
        return out

    def _write(self, sub_file, fix, out):
        text = to_srt(apply(read(sub_file), fix))
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_name(out.name + ".tmp")
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:   # \n también en Windows (igual en todos lados)
            f.write(text)
        tmp.replace(out)

    def notify(self):
        """Llegó un subtítulo nuevo: que se revise ya, sin esperar la vuelta."""
        self.wake.set()

    def summary(self):
        with self.lock:
            entries = [e for per_video in self.state["subs"].values() for e in per_video.values()]
        entries.sort(key=lambda e: e.get("t", 0), reverse=True)
        return {"working": self.current, "pending": len(self.queue),
                "recent": [{k: e.get(k) for k in ("title", "label", "status", "what", "confidence", "t")}
                           for e in entries[:15]]}

    # ---------- qué hay que revisar ----------

    def consider(self, library):
        """Pone en fila los subtítulos aparte que nunca se revisaron o que cambiaron (lo más nuevo primero)."""
        now, jobs = time.time(), {}
        for it in list(library.items.values()):
            files = [s for s in it.get("subs") or [] if s.get("file")]
            track = pick_track(it.get("info")) if files else None
            if not track:
                continue
            for s in files:
                try:
                    sig = _sig(s["file"], it["path"])
                    newest = os.stat(s["file"]).st_mtime
                except OSError:
                    continue
                old = self._entry(s["file"], it["path"])
                retry = old and old["status"] == "falló" and old.get("tries", 0) < MAX_TRIES \
                    and old.get("next_at", 0) <= now
                if old and old["sig"] == sig and not retry:
                    continue
                job = jobs.setdefault(it["path"], {"video": it["path"], "title": it.get("full_title") or it["title"],
                                                   "index": track["index"], "channels": track["channels"],
                                                   "subs": [], "newest": 0})
                job["subs"].append({"file": s["file"], "label": s.get("label", ""), "sig": sig,
                                    "tries": old.get("tries", 0) if old and old["sig"] == sig else 0})
                job["newest"] = max(job["newest"], newest)
        with self.lock:
            self.queue = sorted(jobs.values(), key=lambda j: -j["newest"])
            return len(self.queue)

    def watch(self, library):
        """Tarea automática: espera unos minutos tras arrancar y luego revisa cada 2 min o cuando se le avisa."""
        time.sleep(START_DELAY)
        while True:
            try:
                while self.consider(library) and self._run_next():
                    pass
            except Exception as e:  # noqa: BLE001 - nunca debe tumbar el servidor
                self.log(f"⚠ Subtítulos alineados: {e}")
            self.wake.wait(CHECK_EVERY)
            self.wake.clear()

    # ---------- el trabajo, de a un video ----------

    def _record(self, job, s, fields):
        with self.lock:
            self.state["subs"].setdefault(s["file"], {})[job["video"]] = {
                "title": job["title"], "label": s["label"], "sig": s["sig"], "t": time.time(), **fields}
            self._save()

    def _run_next(self):
        with self.lock:
            if not self.queue or time.time() < self.env_retry_at:
                return False
            job = self.queue.pop(0)
        while getattr(self.dubbing, "current", None):   # un doblaje leyendo películas enteras: primero ese
            time.sleep(30)
        try:
            python = self.dubbing.python()
        except Exception as e:  # noqa: BLE001 - sin numpy no se puede ninguno: un solo aviso, y se reintenta
            self.env_retry_at = time.time() + RETRY_AFTER
            self.log(f"⚠ Subtítulos alineados con la voz: {e} (se reintenta en 1 h)")
            return False
        self.current = job["title"]
        t0 = time.time()
        try:
            r = run_subsync(python, self.script, job["video"], job["index"], job["channels"],
                            [s["file"] for s in job["subs"]], cache=self.out_dir / "voz")
            if not r.get("ok") or len(r.get("subs", [])) != len(job["subs"]):
                raise RuntimeError(r.get("why") or "no se pudo analizar el audio")
        except Exception as e:  # noqa: BLE001 - un video fallido no debe frenar a los demás
            for s in job["subs"]:
                tries = s["tries"] + 1
                self._record(job, s, {"status": "falló", "why": str(e)[:200], "tries": tries,
                                      "next_at": time.time() + RETRY_AFTER})
            final = all(s["tries"] + 1 >= MAX_TRIES for s in job["subs"])
            self.log(f"⚠ Subtítulos de «{job['title']}»: {e}" + ("" if final else " (se reintenta en 1 h)"))
            return True
        finally:
            self.current = None
        secs = round(time.time() - t0)
        for s, res in zip(job["subs"], r["subs"]):
            self._finish(job, s, res, secs)
        return True

    def _finish(self, job, s, res, secs):
        name = f"«{job['title']}» · {s['label']}" if s["label"] else f"«{job['title']}»"
        conf = res.get("confidence")
        conf_txt = f" (confianza {_num(conf)})" if conf is not None else ""
        if not res.get("ok"):
            self._record(job, s, {"status": "no se pudo leer", "why": res.get("why", ""), "secs": secs})
            self.log(f"– Subtítulos de {name}: {res.get('why') or 'no se pudieron leer'}")
            return
        base = {"confidence": conf, "secs": secs, "detail": res.get("detail")}
        if res["action"] == "corregir":
            fix = {"speed": res["speed"], "segments": res["segments"], "quitar": res.get("quitar") or [],
                   "dropped": res.get("dropped", 0)}
            what = describe(fix)
            try:
                self._write(s["file"], fix, self._out(s["file"], job["video"]))
            except (OSError, ValueError) as e:
                self._record(job, s, {**base, "status": "falló", "why": str(e)[:200], "tries": MAX_TRIES})
                self.log(f"⚠ Subtítulos de {name}: no se pudo guardar el corregido ({e})")
                return
            self._record(job, s, {**base, "status": "alineado", "fix": fix, "what": what})
            self.log(f"✓ Subtítulos alineados con la voz: {name}: {what}{conf_txt}")
        elif res["action"] == "a tiempo":
            self._record(job, s, {**base, "status": "ya estaba a tiempo", "what": "sin cambios"})
            self.log(f"✓ Subtítulos de {name}: ya estaban a tiempo{conf_txt}")
        else:
            why = res.get("why") or "no coinciden claramente con la voz"
            self._record(job, s, {**base, "status": "sin coincidencia clara", "why": why})
            self.log(f"– Subtítulos de {name}: {why}; se dejan como están{conf_txt}")
