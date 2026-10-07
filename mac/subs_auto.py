"""Subtítulos que se bajan solos de OpenSubtitles para toda la biblioteca, aprovechando el cupo de cada día.

Qué se baja: cada película o capítulo cuyo idioma original no es el español necesita subtítulos en español (de
preferencia latino), en inglés y, si el original es otro (una película japonesa), también en ese idioma. Lo que ya
tiene no se baja otra vez: los subtítulos de texto que vienen dentro del video y los que la biblioteca ya lista para
ese video en ese idioma (mac/library.py; aquí no se buscan archivos por cuenta propia). No cuentan los que son imagen
(PGS, DVD: la TV y la web no los pueden mostrar) ni los «forzados» (solo traducen lo que se habla en otro idioma).
El idioma original sale de mac/metadata.py (Wikidata); si no se sabe, se usa el del audio principal.

En qué orden: primero todo lo que falta en español, después en inglés, después en el idioma original. Dentro de
cada idioma, primero lo que es más probable que se vea pronto: lo que se está viendo, «Seguir viendo» y los capítulos
que siguen de esas series; luego lo agregado en las últimas semanas; luego lo demás (lo más nuevo primero).

Cuánto: el cupo de la cuenta (la API dice al entrar cuántas descargas permite al día y, en cada descarga, cuántas
quedan y cuándo se renueva). Se gasta todo cada día menos una reserva (RESERVE) para cuando la persona pida uno a
mano. Las consultas van despacio (la API acepta 5 por segundo) y, si pide esperar (429) o dice que se acabó el cupo
(406), se espera lo que diga.

Cuál: primero el hecho para la misma copia (la «huella» del archivo, moviehash); después, por el código de IMDb de
la película o el de la serie (sale del código de TheTVDB de la carpeta, por Wikidata) con temporada y capítulo.
Entre varios: el latino antes, y el que mejor coincide con el nombre con que se bajó el video (misma versión:
WEB-DL, BluRay, grupo) y el más descargado. Lo bajado lo alinea con la voz mac/subsync.py, solo.

Memoria: datos/subtitulos_automaticos.json — lo bajado, lo que todavía no existe (no se vuelve a buscar hasta dentro
de unos días; los estrenos antes), el cupo y cuántos se bajaron cada día. El video nunca se toca: el subtítulo se
guarda siempre con save_next_to_video (mac/subtitles_online.py: Película.es.opensubtitles-latino.srt) y nunca
reemplaza otro archivo.

Se apaga con config.json → "opensubtitles" → "automaticos": false. Sin clave de OpenSubtitles no hace nada (y lo
dice una vez en el registro).
"""

import json
import re
import threading
import time
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from library import EPISODE_RE, LANGS, TEXT_SUB_CODECS, _nfc, has_spanish_audio, lang_key, natural_key, show_key
from subtitles_online import FILE_LANG, SubtitleError, os_languages, save_next_to_video

RESERVE = 2                    # descargas que siempre quedan para pedir una a mano
START_DELAY = 5 * 60           # que el servidor arranque tranquilo
CHECK_EVERY = 3600             # cada cuánto se mira si hay algo nuevo (o si ya se renovó el cupo)
PAUSE = 2.0                    # entre un video y otro
PAUSE_PLAYING = 8.0            # más despacio si se está viendo algo en la TV
DAY = 24 * 3600
RETRY_MISSING = 7 * DAY        # lo que no existe todavía se vuelve a buscar en una semana…
RETRY_MISSING_NEW = 2 * DAY    # …y en dos días si es un estreno o se agregó hace poco
RETRY_MAX = 30 * DAY           # cada vez que no aparece se espera el doble, hasta un mes
RETRY_FAILED = 6 * 3600        # un error de ese video (no de la conexión): se reintenta más tarde
MAX_TRIES = 3
RECENT_DAYS = 30               # «agregado hace poco»
NEXT_EPISODES = 5              # de una serie que se está viendo: los capítulos que siguen
WAIT_MAX = 6 * 3600            # lo más que se espera si la API pide esperar
SERIES_RETRY = 14 * DAY        # una serie sin código de IMDb en Wikidata se vuelve a preguntar en dos semanas
LANG_RANK = {"spa": 0, "eng": 1}
FORCED_RE = re.compile(r"(?i)forced|forzad")
IMDB_RE = re.compile(r"\{imdb-tt(\d+)\}")
TVDB_RE = re.compile(r"\{tvdb-(\d+)\}")
YEAR_RE = re.compile(r"\((19\d\d|20\d\d)\)")
# Lo que dice de qué copia es un nombre de archivo: el origen (BluRay, WEB-DL…), el servicio y la resolución.
SOURCES = [("bluray", r"blu-?ray|bd-?rip|br-?rip|bd-?remux|\bbd\b"), ("webdl", r"web-?dl"), ("webrip", r"web-?rip"),
           ("web", r"\bweb\b"), ("hdtv", r"hdtv"), ("dvd", r"dvd-?rip|\bdvd")]
FAMILY = {"bluray": "bluray", "webdl": "web", "webrip": "web", "web": "web", "hdtv": "hdtv", "dvd": "dvd"}
SERVICES = {"amzn", "nf", "dsnp", "hmax", "max", "atvp", "hulu", "pcok", "pmtp", "stan", "crav", "it", "ma"}
RESOLUTION_RE = re.compile(r"(?i)\b(2160|1080|720|576|480)[pi]\b")
GROUP_RE = re.compile(r"(?<=\S)-([A-Za-z0-9]{2,})$")
NOT_GROUP_RE = re.compile(r"(?i)s\d+e\d+|\d+")


# ---------- qué idiomas hacen falta ----------

def original_of(it, original_langs=None):
    """Idioma original de un video (código de tres letras, «eng», «jpn»…) o "" si no se sabe. Primero el de la obra
    (Wikidata); si no, el del audio principal (la pista predeterminada o la primera dentro del video)."""
    langs = []
    if original_langs:
        try:
            langs = original_langs(it) or []
        except Exception:  # noqa: BLE001 - el idioma de la obra es un extra: sin él se usa el audio
            langs = []
    if isinstance(langs, str):
        langs = [langs]
    work = [k for k in (lang_key(c) for c in langs if c) if k != "und"]
    inside = [a for a in (it.get("info") or {}).get("audio") or [] if not isinstance(a.get("index"), str)]
    main = next((a for a in inside if a.get("default")), inside[0]) if inside else {}
    key = lang_key(main.get("lang"))
    if work:
        # Una obra con varios idiomas (Dunkerque: inglés, francés, alemán): el primero que tenga una pista en el
        # video, como la pista «(original)» de la app (library._pick_original); si ninguno, el primero de la obra.
        tracks = {lang_key(a.get("lang")) for a in inside}
        return next((w for w in work if w in tracks), work[0])
    if not inside:
        return ""
    if key != "und":
        return key
    # Sin idioma marcado: si la pista o el nombre del archivo dicen «latino», «castellano»… se oye en español.
    return "spa" if has_spanish_audio(it["path"], {"audio": inside}) else ""


def wanted_langs(original):
    """Los idiomas que debe tener un video, en orden: español, inglés y el original si es otro ([] si es en español)."""
    if original == "spa":
        return []
    out = ["spa", "eng"]
    if original and original not in out and os_languages(original):
        out.append(original)
    return out


def present_langs(it):
    """Los idiomas de subtítulos que ya tiene un video y que One TV puede mostrar (de texto, completos), según lo
    que lista la biblioteca (mac/library.py): los de dentro del video y los aparte (junto al video o donde la
    biblioteca los encuentre). No se buscan archivos por cuenta propia."""
    have = set()
    for s in (it.get("info") or {}).get("subs") or []:   # dentro del video (todos, aunque la lista muestre pocos)
        if s.get("codec") in TEXT_SUB_CODECS and not s.get("forced") and not FORCED_RE.search(s.get("title") or ""):
            have.add(lang_key(s.get("lang")))
    for s in it.get("subs") or []:                       # los que la biblioteca ofrece para ese video
        if not s.get("forced"):
            have.add(lang_key(s.get("lang")))
    have.discard("und")
    return have


def file_code(lang, os_code):
    """El código de idioma que va en el nombre del archivo, uno que la biblioteca reconozca («es», «ja», «kor»)."""
    if os_code in FILE_LANG:
        return FILE_LANG[os_code]
    short = (os_code or "").split("-")[0]
    if short in LANGS:
        return short
    return lang


def lang_label(lang):
    return LANGS.get(lang, lang.upper()).lower()


# ---------- cuál de los encontrados ----------

def release_traits(text):
    """Lo que dice un nombre de archivo de su copia: {"source", "family", "group", "service", "res", "words"}."""
    name = _nfc(text or "")
    name = re.sub(r"\[[^\]]*\]|\{[^}]*\}", " ", name)
    name = re.sub(r"(?i)\.(srt|sub|vtt|ass|mkv|mp4|m4v|avi)$", "", name.strip())
    name = re.sub(r"(?i)(\.[a-z]{2}(-[a-z]{2})?)+$", "", name)   # «….es», «….en.sdh» al final de un subtítulo
    low = name.lower()
    source = next((key for key, rx in SOURCES if re.search(rx, low)), "")
    words = set(re.findall(r"[a-z0-9]+", low))
    group = GROUP_RE.search(name.strip())
    group = group.group(1).lower() if group and not NOT_GROUP_RE.fullmatch(group.group(1)) else ""
    res = RESOLUTION_RE.search(name)
    return {"source": source, "family": FAMILY.get(source, ""), "group": group,
            "service": next((w for w in words if w in SERVICES), ""), "res": res.group(1) if res else "",
            "words": words}


def release_score(video_names, release):
    """Cuánto se parece la copia del subtítulo a la del video (0 = nada en común)."""
    sub = release_traits(release)
    best = 0.0
    for name in video_names:
        mine = release_traits(name)
        score = 0.0
        if mine["source"] and mine["source"] == sub["source"]:
            score += 3
        elif mine["family"] and mine["family"] == sub["family"]:
            score += 2
        if mine["group"] and mine["group"] == sub["group"]:
            score += 4
        if mine["service"] and mine["service"] == sub["service"]:
            score += 2
        if mine["res"] and mine["res"] == sub["res"]:
            score += 1
        if mine["words"] and sub["words"]:
            score += len(mine["words"] & sub["words"]) / max(len(mine["words"] | sub["words"]), 1)
        best = max(best, score)
    return best


def pick(it, lang, results, video_names=(), skip=(), by_name=False):
    """Los resultados que sirven para ese video e idioma, el mejor primero: el hecho para la misma copia, lo hecho
    por personas, el latino (en español), el que más se parece a la copia del video, sin la marca para sordos y el
    más descargado. by_name: el capítulo se buscó por el nombre de la serie (sin código): que la serie coincida.
    Un «capítulo» sin «S01E02» en el nombre (videos sueltos en una carpeta) solo acepta el hecho para su copia."""
    order = os_languages(lang).split(",")
    episode = it.get("kind") == "episode"
    numbers = [int(n) for n in re.findall(r"\d+", it.get("ep") or "")] if episode else []
    loose = episode and not EPISODE_RE.search(Path(it.get("path") or "").stem)
    out = []
    for r in results:
        if r.get("lang") not in order or r.get("foreign") or str(r.get("file_id")) in skip:
            continue
        if loose and not r.get("match"):
            continue
        if episode:   # que sea ese capítulo (cuando la API lo dice)
            if r.get("season") not in (None, it.get("season")):
                continue
            if numbers and r.get("episode") not in (None, *numbers):
                continue
            if by_name and r.get("show") and not r.get("match"):
                mine, theirs = show_key(it.get("show") or ""), show_key(r["show"])
                if not mine or (mine not in theirs and theirs not in mine):
                    continue
        out.append(r)
    out.sort(key=lambda r: (not r.get("match"), bool(r.get("ai")), order.index(r["lang"]),
                            -release_score(video_names, r.get("release") or ""), bool(r.get("hi")),
                            -(r.get("downloads") or 0)))
    return out


def wikidata_series_imdb(codes):
    """{código de TheTVDB: código de IMDb («tt…»)} de las series que Wikidata conoce. Una sola consulta."""
    values = " ".join(f'"{c}"' for c in codes)
    query = f"SELECT ?code ?imdb WHERE {{ VALUES ?code {{ {values} }} ?item wdt:P4835 ?code . ?item wdt:P345 ?imdb . }}"
    req = urllib.request.Request("https://query.wikidata.org/sparql?format=json&query=" + urllib.parse.quote(query),
                                 headers={"User-Agent": "OneTV/1.0 (servidor casero de video)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read())
    return {b["code"]["value"]: b["imdb"]["value"] for b in data["results"]["bindings"]
            if b["imdb"]["value"].startswith("tt")}


# ---------- el trabajo ----------

class AutoSubtitles:
    def __init__(self, client, library, state_file, cfg=None, original_langs=None, store=None, organizer=None,
                 aligner=None, log=print, series_imdb=wikidata_series_imdb, clock=time.time, sleep=time.sleep):
        self.client = client                    # mac/subtitles_online.py: OpenSubtitles
        self.library = library
        self.state_file = Path(state_file)
        conf = (cfg or {}).get("opensubtitles") or {}
        self.enabled = conf.get("automaticos", True) not in (False, 0, "no", "false")
        self.original_langs = original_langs   # función(video) -> idiomas originales (mac/metadata.py)
        self.store = store                     # progreso: «Seguir viendo» y lo que se está viendo
        self.organizer = organizer             # sus notas dicen con qué nombre se bajó cada video
        self.aligner = aligner                 # mac/subsync.py: alinea con la voz lo que se baja
        self.log = log
        self.series_imdb = series_imdb
        self.clock, self.sleep = clock, sleep
        self.lock = threading.Lock()
        self.wake = threading.Event()
        self.working = False
        self.last = {}                         # lo de la última tanda, para el estado
        try:
            self.state = json.loads(self.state_file.read_text())
        except (OSError, ValueError):
            self.state = {}
        for key in ("videos", "days", "series"):
            self.state.setdefault(key, {})
        saved = self.state.get("quota") or {}
        if saved.get("t", 0) > (client.quota.get("t") or 0):   # lo último que se supo del cupo, si es más nuevo
            client.quota.update(saved)

    @property
    def active(self):
        return self.enabled and self.client.configured

    def _save(self):
        with self.lock:
            self.state["quota"] = dict(self.client.quota)
            cutoff = (datetime.fromtimestamp(self.clock()) - timedelta(days=30)).strftime("%Y-%m-%d")
            self.state["days"] = {d: n for d, n in self.state["days"].items() if d >= cutoff}
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.state_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.state, ensure_ascii=False, indent=1))
            tmp.replace(self.state_file)

    def notify(self):
        """Algo cambió (un video nuevo): que se mire ya, sin esperar la hora."""
        self.wake.set()

    # ---------- qué falta y en qué orden ----------

    def _priorities(self, items):
        """id -> (nivel, orden). 0: lo que se está viendo, «Seguir viendo» y los capítulos que siguen;
        1: lo agregado hace poco (lo más nuevo primero); 2: lo demás."""
        rank, n = {}, 0
        nexts = getattr(self.library, "next_ep", {}) or {}
        first = []
        if self.store:
            playing = self.store.now_playing() if hasattr(self.store, "now_playing") else None
            if playing and playing.get("id") in items:
                first.append(playing["id"])
            with_next = {i: {**it, "next": nexts.get(i, "")} for i, it in items.items()}
            first += [e["id"] for e in self.store.keep_watching(with_next)]
        for item_id in first:
            chain, cur = [item_id], item_id
            for _ in range(NEXT_EPISODES):
                cur = nexts.get(cur)
                if not cur:
                    break
                chain.append(cur)
            for i in chain:
                if i in items and i not in rank:
                    rank[i], n = (0, n), n + 1
        now = self.clock()
        rest = sorted((it for it in items.values() if it["id"] not in rank),
                      key=lambda it: (-int(it.get("mtime", 0) // DAY), natural_key(it["path"])))
        for it in rest:
            recent = now - it.get("mtime", 0) < RECENT_DAYS * DAY
            rank[it["id"]], n = (1 if recent else 2, n), n + 1
        return rank

    def plan(self):
        """(trabajos en orden, cuántos esperan porque aún no existen). Un trabajo: {id, path, lang}."""
        items = dict(self.library.items)
        rank = self._priorities(items)
        now = self.clock()
        jobs, waiting = [], Counter()
        for it in items.values():
            want = wanted_langs(original_of(it, self.original_langs))
            if not want:
                continue
            have = present_langs(it)
            notes = self.state["videos"].get(it["path"], {})
            for lang in want:
                if lang in have:
                    continue
                note = notes.get(lang)
                if note and note.get("status") == "bajado":
                    continue   # ya se bajó una vez (si se borró a mano, no se vuelve a bajar)
                if note and note.get("retry_at", 0) > now:
                    waiting[lang] += 1
                    continue
                jobs.append({"id": it["id"], "path": it["path"], "lang": lang,
                             "key": (LANG_RANK.get(lang, 2), *rank[it["id"]])})
        jobs.sort(key=lambda j: j["key"])
        if items:   # lo que ya no está en la biblioteca se olvida (si la carpeta no está, no se borra nada)
            paths = {it["path"] for it in items.values()}
            with self.lock:
                self.state["videos"] = {p: v for p, v in self.state["videos"].items() if p in paths}
        return jobs, waiting

    # ---------- el cupo ----------

    def budget(self):
        """Cuántas descargas se pueden gastar ahora sin tocar la reserva. Si no se sabe, 1 (la respuesta lo dirá)."""
        q = self.client.quota
        remaining, now = q.get("remaining"), self.clock()
        renewed = q.get("reset_at") and now >= q["reset_at"]
        unsure = not q.get("reset_at") and now - (q.get("t") or 0) > CHECK_EVERY - 60
        if remaining is not None and (renewed or unsure):
            remaining = None   # ya se renovó (o no se sabe cuándo y es viejo): hay que preguntar de nuevo
        if remaining is None and getattr(self.client, "username", ""):
            try:
                self.client.user_info()
                remaining = q.get("remaining")
            except SubtitleError:
                remaining = None
        if remaining is None:
            return 1
        return max(0, int(remaining) - RESERVE)

    def _wait_quota(self):
        """Segundos hasta que se renueve el cupo (o hasta la próxima vuelta, si no se sabe)."""
        reset = self.client.quota.get("reset_at")
        if reset and reset > self.clock():
            return min(reset - self.clock() + 60, 2 * DAY)
        return CHECK_EVERY

    # ---------- de a un video ----------

    def _series_code(self, it):
        """El código de IMDb de la serie de un capítulo (sin «tt»), o None (entonces se busca por nombre)."""
        m = IMDB_RE.search(str(Path(it["path"]).parent.parent)) or IMDB_RE.search(str(Path(it["path"]).parent))
        if m:
            return m.group(1)
        m = TVDB_RE.search(it["path"])
        entry = self.state["series"].get(m.group(1)) if m else None
        return entry["imdb"][2:] if entry and entry.get("imdb") else None

    def _learn_series(self, items):
        """Pregunta a Wikidata, de una vez, el código de IMDb de las series que solo traen el de TheTVDB."""
        now, codes = self.clock(), set()
        for it in items.values():
            m = TVDB_RE.search(it["path"]) if it.get("kind") == "episode" else None
            if not m:
                continue
            entry = self.state["series"].get(m.group(1))
            if not entry or (not entry.get("imdb") and now - entry.get("t", 0) > SERIES_RETRY):
                codes.add(m.group(1))
        if not codes:
            return
        try:
            found = self.series_imdb(sorted(codes))
        except Exception:  # noqa: BLE001 - sin Wikidata se busca por el nombre de la serie
            return
        with self.lock:
            for code in codes:
                self.state["series"][code] = {"imdb": found.get(code, ""), "t": now}

    def _video_names(self, it):
        """Nombres que dicen de qué copia es el video: el archivo, su carpeta y el nombre con que se bajó."""
        path = Path(it["path"])
        names = [path.name, path.parent.name]
        done = (getattr(self.organizer, "state", None) or {}).get("done") or {}
        for src, dest in done.items():
            if dest == it["path"]:
                names += [Path(src).name, Path(src).parent.name]
        return names

    def _note(self, it, lang, **fields):
        with self.lock:
            self.state["videos"].setdefault(it["path"], {})[lang] = {"t": self.clock(), **fields}

    def _retry_missing(self, it, tries):
        years = [int(y) for y in YEAR_RE.findall(it["path"])]
        now = self.clock()
        fresh = (years and max(years) >= datetime.fromtimestamp(now).year - 1) or \
            now - it.get("mtime", 0) < RECENT_DAYS * DAY
        return min((RETRY_MISSING_NEW if fresh else RETRY_MISSING) * 2 ** max(tries - 1, 0), RETRY_MAX)

    def do_one(self, job):
        """Busca y baja el subtítulo de un trabajo. -> "bajado", "no existe", "falló" u "olvidado" (ya no está).
        Los errores de la conexión, del cupo o de «espera» se dejan pasar: cortan la tanda."""
        it = self.library.get(job["id"]) if hasattr(self.library, "get") else self.library.items.get(job["id"])
        if not it or it["path"] != job["path"]:
            return "olvidado"
        lang = job["lang"]
        old = (self.state["videos"].get(it["path"]) or {}).get(lang) or {}
        tries = old.get("tries", 0) + 1
        parent = self._series_code(it) if it.get("kind") == "episode" else None
        try:
            results = self.client.search(it, lang, parent_imdb=parent)
        except SubtitleError as e:
            if e.code is None or e.quota or e.wait is not None or (e.code or 0) >= 500:
                raise
            self._note(it, lang, status="falló", why=str(e)[:200], tries=tries,
                       retry_at=self.clock() + (RETRY_FAILED * tries if tries < MAX_TRIES else RETRY_MAX))
            return "falló"
        bad = set(old.get("bad") or [])
        found = pick(it, lang, results, self._video_names(it), skip=bad,
                     by_name=it.get("kind") == "episode" and not parent)
        if not found:
            missing = old.get("missing", 0) + 1
            self._note(it, lang, status="no existe", missing=missing,
                       retry_at=self.clock() + self._retry_missing(it, missing))
            return "no existe"
        best = found[0]
        data, _ = self.client.download(best["file_id"])   # errores de cupo o de conexión: cortan la tanda
        try:
            saved = save_next_to_video(it, data, best["lang"], file_lang=file_code(lang, best["lang"]))
        except (SubtitleError, OSError) as e:
            bad.add(str(best["file_id"]))
            self._note(it, lang, status="falló", why=str(e)[:200], tries=tries, bad=sorted(bad),
                       retry_at=self.clock() + (RETRY_FAILED * tries if tries < MAX_TRIES else RETRY_MAX))
            return "falló"
        self._note(it, lang, status="bajado", file=saved.name, release=best.get("release", ""),
                   match=bool(best.get("match")), file_id=best["file_id"])
        day = datetime.fromtimestamp(self.clock()).strftime("%Y-%m-%d")
        with self.lock:
            counts = self.state["days"].setdefault(day, {})
            counts[lang] = counts.get(lang, 0) + 1
        self._save()
        try:   # que la biblioteca lo muestre ya y que se alinee con la voz sin esperar la vuelta
            if hasattr(self.library, "scan"):
                self.library.scan(force=True)
            if self.aligner:
                self.aligner.notify()
        except Exception as e:  # noqa: BLE001 - el subtítulo ya está guardado; lo demás es un extra
            self.log(f"⚠ Subtítulos automáticos: {e}")
        return "bajado"

    # ---------- una tanda ----------

    def run_once(self):
        """Una tanda: baja lo que falta, en orden, hasta gastar el cupo de hoy (menos la reserva).
        -> segundos hasta la próxima tanda."""
        if not self.active:
            return CHECK_EVERY
        self.working = True
        did = Counter()
        wait, stopped = CHECK_EVERY, ""
        try:
            self._learn_series(dict(self.library.items))
            jobs, waiting = self.plan()
            left = len(jobs)
            budget = self.budget() if jobs else 0
            for job in jobs:
                if budget <= 0:
                    stopped, wait = "cupo", self._wait_quota()
                    break
                if did:
                    busy = self.store and hasattr(self.store, "now_playing") and self.store.now_playing()
                    self.sleep(PAUSE_PLAYING if busy else PAUSE)
                known = self.client.quota.get("t")
                try:
                    result = self.do_one(job)
                except SubtitleError as e:
                    if e.quota:
                        stopped, wait = "cupo", self._wait_quota()
                    elif e.wait is not None:
                        stopped, wait = "espera", min(max(e.wait, 60), WAIT_MAX)
                    else:
                        stopped, wait = "error", CHECK_EVERY
                        self.log(f"⚠ Subtítulos automáticos: {e} (se sigue en una hora)")
                    break
                did[result] += 1
                if result in ("bajado", "no existe", "olvidado"):
                    left -= 1
                if result == "bajado":   # la respuesta dice cuántas quedan; si no lo dijo, se cuenta una menos
                    budget = self.budget() if self.client.quota.get("t") != known else budget - 1
                if result == "no existe":
                    waiting[job["lang"]] += 1
            self.last = {"missing": max(left, 0), "waiting": sum(waiting.values()), "stopped": stopped,
                         "next_at": self.clock() + wait, "t": self.clock()}
            self._save()
            if did.get("bajado") or did.get("no existe") or did.get("falló"):
                self.log(self.summary_line())
            return wait
        finally:
            self.working = False

    def watch(self):
        """Tarea automática: espera unos minutos tras arrancar; luego una tanda cada hora, o cuando se renueva el
        cupo, o cuando se le avisa."""
        if not self.client.configured:
            import hostos
            self.log("· Subtítulos automáticos: apagados porque falta la clave de OpenSubtitles. Para que se bajen "
                     "solos, pon tu clave en config.json → \"opensubtitles\" → \"api_key\" (cómo sacarla gratis: "
                     f"docs/INSTALAR.md, «Subtítulos de OpenSubtitles») y corre {hostos.CINE}.")
            return
        if not self.enabled:
            self.log("· Subtítulos automáticos: apagados en config.json (\"opensubtitles\" → \"automaticos\": false).")
            return
        self.sleep(START_DELAY)
        while True:
            try:
                wait = self.run_once()
            except Exception as e:  # noqa: BLE001 - nunca debe tumbar el servidor
                self.log(f"⚠ Subtítulos automáticos: {e}")
                wait = CHECK_EVERY
            self.wake.wait(wait)
            self.wake.clear()

    # ---------- lo que se cuenta ----------

    def _today(self):
        day = datetime.fromtimestamp(self.clock()).strftime("%Y-%m-%d")
        return dict(self.state["days"].get(day) or {})

    def _when(self, ts):
        now = datetime.fromtimestamp(self.clock())
        at = datetime.fromtimestamp(ts)
        if at.date() == now.date():
            return f"hoy a las {at:%H:%M}"
        if at.date() == (now + timedelta(days=1)).date():
            return f"mañana a las {at:%H:%M}"
        return f"el {at:%d/%m} a las {at:%H:%M}"

    def summary_line(self):
        """«✓ Subtítulos automáticos: 18 bajados hoy (12 en español, 6 en inglés); faltan 240; siguen mañana a las 07:00»."""
        today = self._today()
        total = sum(today.values())
        parts = ", ".join(f"{n} en {lang_label(lang)}"
                          for lang, n in sorted(today.items(), key=lambda kv: (LANG_RANK.get(kv[0], 2), kv[0])))
        text = f"✓ Subtítulos automáticos: {total} bajado{'s' if total != 1 else ''} hoy" + (f" ({parts})" if parts else "")
        last = self.last or {}
        missing, waiting = last.get("missing", 0), last.get("waiting", 0)
        if missing:
            text += f"; faltan {missing}"
        else:
            text += "; no falta nada más por ahora"
        if waiting:
            text += (f" ({waiting} todavía no existe{'n' if waiting != 1 else ''} en OpenSubtitles; se vuelve"
                     f"{'n' if waiting != 1 else ''} a buscar en unos días)")
        q = self.client.quota
        if q.get("remaining") is not None and q.get("allowed"):
            text += f"; quedan {q['remaining']} de {q['allowed']} descargas de hoy"
        if missing and last.get("stopped") == "cupo" and q.get("reset_at"):
            text += f"; siguen {self._when(q['reset_at'] + 60)}"
        elif missing and last.get("next_at"):
            text += f"; siguen {self._when(last['next_at'])}"
        return text

    def status(self):
        """Resumen corto para /api/status (y la web). None si está apagado."""
        if not self.active:
            return None
        today = self._today()
        total = sum(today.values())
        last = self.last or {}
        text = ""   # antes de la primera tanda y sin nada bajado hoy, no hay nada que contar
        if last or total:
            text = f"subtítulos automáticos: {total} bajado{'s' if total != 1 else ''} hoy"
        if last:
            text += f", faltan {last['missing']}" if last.get("missing") else ", al día"
        return {"today": total, "by_lang": today, "missing": last.get("missing"), "waiting": last.get("waiting"),
                "working": self.working, "remaining": self.client.quota.get("remaining"),
                "allowed": self.client.quota.get("allowed"), "next_at": last.get("next_at"), "text": text}
