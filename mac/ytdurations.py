"""Duración de los videos de YouTube: un caché persistente (id -> segundos) y un rellenador en segundo plano.

El caché se alimenta de todo lo que ya pasa por la computadora: yt-dlp al reproducir (el historial), los listados
de canales y listas públicas, los relacionados, la página «Videos» de los canales y las búsquedas. Así casi todo
llega con su duración sin pedir nada más.

Lo que se muestra sin duración (lo nuevo de los canales, que viene del RSS; la fila de reproducción; las listas del
Takeout) lo pide el rellenador, muy medido: YouTube bloquea a quien pide demasiado («Sign in to confirm you're not a
bot») y eso rompería la reproducción. Por eso:
- Pide varios videos en una sola página (la de una lista anónima armada con sus ids, ver youtube.fetch_durations):
  una petición de ≈1,4 MB por hasta 50 videos, en lugar de 3 peticiones por video con yt-dlp (una de ellas a la API
  del reproductor, que es justo la que YouTube vigila).
- Límite por videos pedidos (no por peticiones): 1 cada 3 s de media y 100 por hora.
- Si YouTube frena (429, su página «sorry» o el aviso de bot), no se le pide nada en 6 horas. El freno y lo pedido
  en la última hora sobreviven a un reinicio.
Nada de cookies ni cuentas.

Fecha de publicación: el mismo caché guarda, por video, la fecha (epoch) y su precisión. Exacta (RSS, yt-dlp al
reproducir) o aproximada («hace 3 años» sirve al año): una exacta nunca se pisa con una aproximada y una aproximada solo
la reemplaza otra más precisa. `apply` pone `published` y `published_approx` en cada video que la tenga. No pide nada
a YouTube: solo aprende de lo que ya llega.
"""

import calendar
import json
import re
import threading
import time
from pathlib import Path

VIDEO_ID = re.compile(r"^[\w-]{11}$")
MAX_KNOWN = 20000            # duraciones que se guardan (las más viejas se van primero): ≈500 KB
MAX_SECONDS = 100 * 3600     # más que esto no es un video (o es un directo sin fin)
UNKNOWN_RETRY = 7 * 86400    # un video que YouTube no dio (borrado, privado…) se vuelve a pedir a la semana
PER_VIDEO = 3.0              # segundos por video pedido: tras pedir 50, 150 s hasta la siguiente petición
PER_HOUR = 100               # videos pedidos por hora como máximo
BATCH = 50                   # videos por petición (lo más que acepta la lista anónima de YouTube)
BLOCK_FOR = 6 * 3600         # pausa si YouTube frena
ERROR_PAUSE = 15 * 60        # pausa tras un error de red o una página que no se entiende
GATHER = 2.0                 # espera para juntar en una sola petición lo que se pide casi a la vez
PENDING_MAX = 1000           # lo que puede esperar en la cola del rellenador
HOUR = 3600
# La fecha relativa que muestra YouTube: «hace 1 día» (o «1 day ago» si contesta en inglés).
AGO = re.compile(r"(?:hace\s+(\d+)\s+(segundo|minuto|hora|día|dia|semana|mes|año)"
                 r"|(\d+)\s+(second|minute|hour|day|week|month|year)s?\s+ago)", re.I)
AGO_SECONDS = {"second": 1, "minute": 60, "hour": 3600, "day": 86400, "week": 7 * 86400, "month": 30 * 86400,
               "year": 365 * 86400, "segundo": 1, "minuto": 60, "hora": 3600, "día": 86400, "dia": 86400,
               "semana": 7 * 86400, "mes": 30 * 86400, "año": 365 * 86400}
MAX_DATES = 20000            # fechas que se guardan
MIN_EPOCH = 946684800        # antes del 2000 no hay YouTube: es un valor raro
DAY = 86400


class Blocked(Exception):
    """YouTube está frenando: 429, su página «sorry» o el aviso «confirma que no eres un bot»."""


def seconds_of(value):
    """Duración válida en segundos (int) o 0: acepta números y textos con cifras; nada de directos ni valores raros."""
    try:
        s = int(float(value))
    except (TypeError, ValueError):
        return 0
    return s if 0 < s < MAX_SECONDS else 0


def parse_ago(text, now=None):
    """«hace 3 años» / «3 years ago» dentro de un texto -> (epoch aproximado, segundos de precisión) o None."""
    m = AGO.search(text or "")
    if not m:
        return None
    unit = AGO_SECONDS[(m.group(2) or m.group(4)).lower()]
    return int((now or time.time()) - int(m.group(1) or m.group(3)) * unit), unit


def epoch_of(value):
    """Epoch válido (int) o 0."""
    try:
        t = int(float(value))
    except (TypeError, ValueError):
        return 0
    return t if MIN_EPOCH < t < 4102444800 else 0


def date_of(entry):
    """La fecha exacta que da yt-dlp de un video: `timestamp` o, si no, `upload_date` («20230912») -> epoch o 0."""
    t = epoch_of(entry.get("timestamp") or entry.get("release_timestamp"))
    if t:
        return t
    m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})", str(entry.get("upload_date") or ""))
    if m:
        try:
            return epoch_of(calendar.timegm((int(m.group(1)), int(m.group(2)), int(m.group(3)), 12, 0, 0)))
        except (ValueError, OverflowError):
            return 0
    return 0


class Durations:
    """Caché de duraciones en disco (datos/youtube_duraciones.json). Seguro entre hilos."""

    def __init__(self, path, save_delay=3.0, clock=time.time):
        self.path = Path(path)
        self.save_delay = save_delay   # se junta lo aprendido unos segundos antes de escribir (0: en el acto)
        self.clock = clock
        self.lock = threading.RLock()
        self.filler = None             # DurationFiller, si lo hay: pide lo que falte
        self.offline = None            # mac/offline.py: marca los videos guardados o en la cola de descargas
        self._timer = None
        try:
            d = json.loads(self.path.read_text())
        except (OSError, ValueError):
            d = {}
        if not isinstance(d, dict):
            d = {}
        self.known = {k: seconds_of(v) for k, v in (d.get("durations") or {}).items()
                      if VIDEO_ID.match(k) and seconds_of(v)}
        # id -> [epoch, precisión en segundos]; 0 = exacta (formato viejo: el archivo no trae «published»)
        self.dates = {}
        for k, v in (d.get("published") or {}).items():
            try:
                t, unit = epoch_of(v[0]), max(int(v[1]), 0)
            except (TypeError, ValueError, IndexError, KeyError):
                continue
            if VIDEO_ID.match(k) and t:
                self.dates[k] = [t, unit]
        self.unknown = {k: float(t) for k, t in (d.get("unknown") or {}).items() if VIDEO_ID.match(k)}
        self.state = d.get("filler") if isinstance(d.get("filler"), dict) else {}   # freno y lo pedido (ver el rellenador)

    # ---------- leer y aprender ----------

    def get(self, vid):
        with self.lock:
            return self.known.get(vid, 0)

    def count(self):
        with self.lock:
            return len(self.known)

    def learn(self, source):
        """Anota duraciones: {id: segundos} o una lista de videos ({id, duration}). -> cuántas cambiaron."""
        if isinstance(source, dict):
            pairs = source.items()
        else:
            pairs = [(v.get("id"), v.get("duration")) for v in source or [] if isinstance(v, dict)]
        changed = 0
        with self.lock:
            for vid, value in pairs:
                sec = seconds_of(value)
                if not sec or not VIDEO_ID.match(vid or ""):
                    continue
                self.unknown.pop(vid, None)
                if self.known.get(vid) != sec:
                    self.known.pop(vid, None)
                    self.known[vid] = sec   # al final: lo último aprendido es lo último en irse
                    changed += 1
            if changed:
                for old in list(self.known)[:max(0, len(self.known) - MAX_KNOWN)]:
                    del self.known[old]
                self._changed()
        return changed

    def learn_dates(self, source):
        """Anota fechas de publicación: {id: (epoch, precisión)} o una lista de videos con `published` (epoch) y, si es
        aproximada, `published_approx` y `published_unit` (segundos de precisión; si falta, un día). Una exacta no la
        pisa una aproximada; una aproximada solo la reemplaza otra más precisa. -> cuántas cambiaron."""
        if isinstance(source, dict):
            rows = [(k, v[0], v[1]) for k, v in source.items()]
        else:
            rows = []
            for v in source or []:
                if isinstance(v, dict) and epoch_of(v.get("published")):
                    unit = 0 if not v.get("published_approx") else max(int(v.get("published_unit") or DAY), 1)
                    rows.append((v.get("id"), v["published"], unit))
        changed = 0
        with self.lock:
            for vid, t, unit in rows:
                t = epoch_of(t)
                if not t or not VIDEO_ID.match(vid or ""):
                    continue
                old = self.dates.get(vid)
                if old and ((not old[1] and unit) or (old[1] and unit and unit >= old[1])):
                    continue   # lo que se sabía es igual de bueno o mejor (exacta > aproximada; más fina > más gruesa)
                if old == [t, unit]:
                    continue
                self.dates.pop(vid, None)
                self.dates[vid] = [t, unit]
                changed += 1
            if changed:
                for old in list(self.dates)[:max(0, len(self.dates) - MAX_DATES)]:
                    del self.dates[old]
                self._changed()
        return changed

    def date(self, vid):
        """(epoch, aproximada) de la fecha que se sabe del video, o None."""
        with self.lock:
            d = self.dates.get(vid)
        return (d[0], bool(d[1])) if d else None

    def give_up(self, ids):
        """YouTube no dio la duración de estos videos (borrados, privados…): no se piden otra vez en una semana."""
        with self.lock:
            now = self.clock()
            for vid in ids:
                if VIDEO_ID.match(vid or "") and vid not in self.known:
                    self.unknown[vid] = now
            for old in [k for k, t in self.unknown.items() if now - t > UNKNOWN_RETRY]:
                del self.unknown[old]
            self._changed()

    def worth_asking(self, vid):
        """¿Vale la pena pedirla? (no se sabe y no se intentó hace poco)."""
        with self.lock:
            return bool(VIDEO_ID.match(vid or "")) and vid not in self.known and \
                self.clock() - self.unknown.get(vid, -UNKNOWN_RETRY) >= UNKNOWN_RETRY

    def apply(self, videos, want=True):
        """Pone en cada video (en su lugar) la duración que se sepa, si no la trae, y si está guardado sin conexión (`offline`); aprende las que sí traen y, con
        want, pide al rellenador las que falten. Se salta los privados. Devuelve la misma lista."""
        self.learn([v for v in videos or [] if isinstance(v, dict) and seconds_of(v.get("duration"))])
        self.learn_dates(videos)
        if self.offline:   # todo video de YouTube que sale en la web o la TV pasa por aquí: lleva su marca «sin conexión»
            self.offline.mark(videos)
        missing = []
        with self.lock:
            for v in videos or []:
                if isinstance(v, dict) and v.get("id") in self.dates:
                    v["published"], v["published_approx"] = self.dates[v["id"]][0], bool(self.dates[v["id"]][1])
                    v.pop("published_unit", None)
                if not isinstance(v, dict) or v.get("private") or seconds_of(v.get("duration")):
                    continue
                sec = self.known.get(v.get("id"))
                if sec:
                    v["duration"] = sec
                else:
                    v["duration"] = 0
                    missing.append(v.get("id"))
        missing = [vid for vid in missing if self.worth_asking(vid)]
        if missing and want and self.filler:
            self.filler.want(missing)
        return videos

    def blocked(self):
        """¿YouTube está frenando? (entonces tampoco conviene pedirle listados solo por las duraciones)."""
        return bool(self.filler) and self.filler.blocked()

    def eta(self, videos):
        """Segundos hasta que el rellenador traiga la próxima duración de estos videos (para que la web vuelva a
        preguntar); 0 si no hay nada en camino (ya están, no se pueden saber o el rellenador está frenado)."""
        ids = [v.get("id") for v in videos or [] if isinstance(v, dict) and not v.get("private")
               and not seconds_of(v.get("duration"))]
        return self.filler.eta(ids) if ids and self.filler else 0

    # ---------- disco ----------

    def _changed(self):
        if self.save_delay <= 0:
            self.save()
        elif self._timer is None:
            self._timer = threading.Timer(self.save_delay, self.save)
            self._timer.daemon = True
            self._timer.start()

    def save(self):
        with self.lock:
            self._timer = None
            data = {"durations": dict(self.known), "published": dict(self.dates), "unknown": dict(self.unknown), "filler": dict(self.state)}
        if not self.path.parent.is_dir():
            return   # la carpeta de datos ya no está (p. ej. la de una prueba que terminó): no se vuelve a crear
        try:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
            tmp.replace(self.path)
        except OSError:
            pass   # sin disco no se pierde nada más que el caché


class DurationFiller:
    """Pide a YouTube, poco a poco, la duración de los videos que se muestran sin ella.

    fetch(ids) -> {id: segundos} (puede traer de más: se aprende todo); lanza Blocked si YouTube frena y otra
    excepción si falla la red o la página no se entiende. step() hace una petición si los límites lo permiten (las
    pruebas lo llaman a mano, con un reloj falso); el hilo de fondo lo llama solo cuando toca."""

    def __init__(self, durations, fetch, log=print, clock=time.time, per_video=PER_VIDEO, per_hour=PER_HOUR,
                 batch=BATCH, block_for=BLOCK_FOR, error_pause=ERROR_PAUSE, gather=GATHER, background=True):
        self.durations = durations
        self.fetch = fetch
        self.log = log
        self.clock = clock
        self.per_video, self.per_hour, self.batch = per_video, per_hour, batch
        self.block_for, self.error_pause, self.gather = block_for, error_pause, gather
        self.background = background
        self.cond = threading.Condition()
        self.pending = []   # ids por pedir, en orden (lo que apareció sin duración más recientemente va primero)
        self.thread = None
        st = durations.state
        now = clock()
        self.blocked_until = float(st.get("blocked_until") or 0)
        self.next_at = float(st.get("next_at") or 0)
        self.asked = [(float(t), int(n)) for t, n in st.get("asked") or [] if now - float(t) < HOUR]
        self.stats = {"requests": 0, "asked": 0, "found": 0, "extra": 0, "secs": 0.0, "errors": 0}
        durations.filler = self

    # ---------- lo que se pide ----------

    def want(self, ids):
        """Estos videos se están mostrando sin duración: los que no esperaban ya van primero en la cola; los que ya
        esperaban conservan su lugar (la fila se consulta a cada rato y no debe pasar siempre adelante)."""
        ids = [v for v in dict.fromkeys(ids) if self.durations.worth_asking(v)]
        with self.cond:
            waiting = set(self.pending)
            new = [v for v in ids if v not in waiting]
            if not new:
                return
            self.pending = (new + self.pending)[:PENDING_MAX]
            self.cond.notify_all()
        if self.background:
            self._start()

    def eta(self, ids):
        with self.cond:
            waiting = set(self.pending) & set(ids)
        if not waiting:
            return 0
        now = self.clock()
        if now < self.blocked_until:
            return 0
        return int(max(self.wait(now), 0) + self.gather + 3)

    # ---------- límites ----------

    def blocked(self):
        return self.clock() < self.blocked_until

    def used(self, now=None):
        """Videos pedidos en la última hora."""
        now = self.clock() if now is None else now
        return sum(n for t, n in self.asked if now - t < HOUR)

    def wait(self, now=None):
        """Segundos hasta que se pueda volver a pedir (0: ya)."""
        now = self.clock() if now is None else now
        waits = [self.blocked_until - now, self.next_at - now]
        if self.used(now) >= self.per_hour:   # hasta que la petición más vieja de la hora salga de ella
            waits.append(min(t for t, n in self.asked if now - t < HOUR) + HOUR - now)
        return max([0.0] + waits)

    def _save_state(self):
        now = self.clock()
        self.asked = [(t, n) for t, n in self.asked if now - t < HOUR]
        with self.durations.lock:
            self.durations.state = {"blocked_until": self.blocked_until, "next_at": self.next_at,
                                    "asked": [[t, n] for t, n in self.asked]}
            self.durations._changed()

    # ---------- una petición ----------

    def step(self):
        """Una petición a YouTube, si toca. -> "ok" | "blocked" | "error" | None (nada que hacer o hay que esperar)."""
        now = self.clock()
        if self.wait(now) > 0:
            return None
        with self.cond:
            self.pending = [v for v in self.pending if self.durations.worth_asking(v)]
            room = min(self.batch, self.per_hour - self.used(now))
            ids = self.pending[:max(room, 0)]
        if not ids:
            return None
        self.asked.append((now, len(ids)))
        self.next_at = now + self.per_video * len(ids)
        self.stats["requests"] += 1
        self.stats["asked"] += len(ids)
        started = time.monotonic()
        try:
            found = self.fetch(ids) or {}
        except Blocked as e:
            self.blocked_until = now + self.block_for
            self._save_state()
            self.log(f"⚠ Duraciones de YouTube: YouTube está frenando ({e}); no se le pide nada en "
                     f"{self.block_for // 3600} h")
            return "blocked"
        except Exception as e:  # noqa: BLE001 - red o página que cambió: se reintenta más tarde
            self.next_at = max(self.next_at, now + self.error_pause)
            self.stats["errors"] += 1
            self._save_state()
            self.log(f"⚠ Duraciones de YouTube: no se pudieron leer ({e}); se reintenta en {self.error_pause // 60} min")
            return "error"
        took = time.monotonic() - started
        self.stats["secs"] += took
        got = [v for v in ids if seconds_of(found.get(v))]
        self.durations.learn(found)
        self.durations.learn_dates(getattr(found, "dates", None) or {})   # las fechas que traía esa misma página
        self.durations.give_up([v for v in ids if v not in got])
        self.stats["found"] += len(got)
        self.stats["extra"] += len([v for v in found if v not in ids and seconds_of(found[v])])
        with self.cond:
            done = set(ids)
            self.pending = [v for v in self.pending if v not in done]
            left = len(self.pending)
        self._save_state()
        self.log(f"✓ Duraciones de YouTube: {len(got)} de {len(ids)} en una petición ({took:.1f} s)"
                 + (f"; faltan {left}" if left else ""))
        return "ok"

    # ---------- el hilo ----------

    def _start(self):
        with self.cond:
            if self.thread and self.thread.is_alive():
                return
            self.thread = threading.Thread(target=self._loop, name="duraciones", daemon=True)
            self.thread.start()

    def _loop(self):
        while True:
            with self.cond:
                while not self.pending:
                    self.cond.wait()
            time.sleep(self.gather)   # lo que se pide casi a la vez (Inicio y la fila) va en la misma petición
            pause = self.wait()
            if pause > 0:
                with self.cond:
                    self.cond.wait(timeout=min(pause, 600))
                continue
            try:
                self.step()
            except Exception as e:  # noqa: BLE001 - el hilo nunca debe morir
                self.log(f"⚠ Duraciones de YouTube: {e}")
                time.sleep(60)

    def status(self):
        now = self.clock()
        with self.cond:
            pending = len(self.pending)
        return {"pending": pending, "used_last_hour": self.used(now), "wait": int(self.wait(now)),
                "blocked": now < self.blocked_until, **self.stats}
