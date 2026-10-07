"""Descripciones (sinopsis) de películas, series y episodios, por el código que traen las carpetas.

- Películas {imdb-tt…} y series {tvdb-…}: Wikipedia en español (si no hay, en inglés). El artículo se
  encuentra en Wikidata por el código; se usa la sección «Argumento/Sinopsis» o, si no hay, la introducción.
  Lo que no trae el código en el nombre (una biblioteca de Plex, por ejemplo) usa el que encontró mac/identify.py.
- Episodios: TVmaze (en inglés; no hay fuente abierta en español).
- Idioma original (Wikidata P364 -> código ISO 639-2 P219): sale de la misma consulta a Wikidata que
  encuentra el artículo; los episodios usan el de su serie.
Todo se baja una vez, despacio (Wikipedia limita las consultas seguidas), y se guarda en la Mac.
"""

import html
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

UA = {"User-Agent": "OneTV/1.0 (servidor casero de video; https://github.com/julai1433/one-tv)"}
PAUSE = 2.5                    # entre consultas a Wikipedia
PER_RUN = 12                   # artículos por vuelta (una vuelta por minuto): Wikipedia limita las ráfagas
RETRY_AFTER = 14 * 24 * 3600   # lo que no se encontró se vuelve a buscar en dos semanas
LANG_PER_RUN = 40              # códigos por consulta a Wikidata cuando solo falta el idioma original
ORIGINAL_KEY = "_original"     # dentro de metadata.json: clave de la obra -> {"lang", "t"}
MAX_CHARS = 1500               # la ficha muestra el principio; con «*» en la tele se lee completa
PLOT_HEADINGS = re.compile(r"(?im)^==\s*(argumento|sinopsis|trama|resumen|historia|plot|synopsis|premise|story)\s*==\s*$")


def _get_json(url, timeout=20, tries=3):
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < tries - 1:
                time.sleep(10 * (attempt + 1))   # Wikipedia pide esperar
                continue
            raise


def _clean(text):
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= MAX_CHARS:
        return text
    cut = text[:MAX_CHARS]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return (cut[:end + 1] if end > 200 else cut.rstrip() + "…").strip()


def _plot_from_article(text):
    """La sección de argumento; si no hay, la introducción (lo anterior al primer título)."""
    m = PLOT_HEADINGS.search(text)
    if m:
        rest = text[m.end():]
        nxt = re.search(r"(?m)^==[^=]", rest)
        section = rest[:nxt.start()] if nxt else rest
        section = re.sub(r"(?m)^=+.*=+\s*$", " ", section)   # subtítulos dentro de la sección
        if len(section.strip()) > 80:
            return section
    first = re.search(r"(?m)^==", text)
    return text[:first.start()] if first else text


def _wikipedia_titles(prop, codes):
    """{código: {"es": título, "en": título, "orig": [códigos ISO 639-2 del idioma original]}} en una sola
    consulta a Wikidata."""
    values = " ".join(f'"{c}"' for c in codes)
    query = f"""SELECT ?code ?es ?en ?iso WHERE {{
      VALUES ?code {{ {values} }}
      ?item wdt:{prop} ?code .
      OPTIONAL {{ ?es schema:about ?item; schema:isPartOf <https://es.wikipedia.org/> . }}
      OPTIONAL {{ ?en schema:about ?item; schema:isPartOf <https://en.wikipedia.org/> . }}
      OPTIONAL {{ ?item wdt:P364 ?olang . ?olang wdt:P219 ?iso . }}
    }}"""
    data = _get_json("https://query.wikidata.org/sparql?format=json&query=" + urllib.parse.quote(query), timeout=60)
    return _parse_titles(data)


def _parse_titles(data):
    out = {}
    for row in data["results"]["bindings"]:
        entry = out.setdefault(row["code"]["value"], {})
        for lang in ("es", "en"):
            if lang in row and lang not in entry:
                entry[lang] = urllib.parse.unquote(row[lang]["value"].rsplit("/wiki/", 1)[-1]).replace("_", " ")
        if "iso" in row:
            codes = entry.setdefault("orig", [])
            if row["iso"]["value"] not in codes:
                codes.append(row["iso"]["value"])
    return out


def _wikipedia_plot(lang, title):
    params = urllib.parse.urlencode({"action": "query", "prop": "extracts", "explaintext": 1, "redirects": 1,
                                     "format": "json", "titles": title})
    pages = _get_json(f"https://{lang}.wikipedia.org/w/api.php?{params}")["query"]["pages"]
    text = next(iter(pages.values())).get("extract") or ""
    return _clean(_plot_from_article(text))


class Metadata:
    def __init__(self, cache_dir):
        self.file = Path(cache_dir) / "metadata.json"
        self.lock = threading.Lock()
        self.busy = threading.Lock()
        try:
            self.data = json.loads(self.file.read_text())   # clave -> {"desc", "lang", "t"}
        except (OSError, ValueError):
            self.data = {}
        self.codes = None   # códigos encontrados por el nombre (mac/identify.py); la pone la app

    def desc(self, key):
        return (self.data.get(key) or {}).get("desc", "")

    # ---------- idioma original ----------

    @staticmethod
    def original_key(it):
        """La clave de la obra a la que pertenece un video: la película, o la serie si es un episodio."""
        if it.get("kind") == "episode":
            from library import show_key
            return f"serie-{show_key(it.get('show', ''))}"
        return it["id"]

    def original_lang(self, it):
        """Código ISO 639-2 del idioma original de una película o serie, o "" si aún no se sabe."""
        return ((self.data.get(ORIGINAL_KEY) or {}).get(self.original_key(it)) or {}).get("lang", "")

    def original_langs(self, it):
        """Todos los idiomas originales que dice Wikidata (una obra puede tener varios), el primero antes."""
        entry = (self.data.get(ORIGINAL_KEY) or {}).get(self.original_key(it)) or {}
        return list(entry.get("langs") or ([entry["lang"]] if entry.get("lang") else []))

    def _store_original(self, key, codes):
        with self.lock:
            table = self.data.setdefault(ORIGINAL_KEY, {})
            table[key] = {"lang": (codes or [""])[0], "langs": list(codes or []), "t": time.time()}

    def _pending_original(self, key):
        entry = (self.data.get(ORIGINAL_KEY) or {}).get(key)
        if not entry:
            return True
        return not entry["lang"] and time.time() - entry["t"] > RETRY_AFTER

    def _store(self, key, desc, lang):
        with self.lock:
            self.data[key] = {"desc": desc, "lang": lang, "t": time.time(), "max": MAX_CHARS}

    def _save(self):
        with self.lock:
            tmp = self.file.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, ensure_ascii=False))
            tmp.replace(self.file)

    def _pending(self, key):
        entry = self.data.get(key)
        if not entry:
            return True
        if not entry["desc"]:
            return time.time() - entry["t"] > RETRY_AFTER
        # Guardada con un límite más corto y quedó cortada: se vuelve a bajar entera.
        limit = entry.get("max", 700)
        return limit < MAX_CHARS and len(entry["desc"]) >= limit - 20

    def fetch_all(self, library, log=print):
        """Busca lo que falte: películas y series en Wikipedia; episodios en TVmaze."""
        if not self.busy.acquire(blocking=False):
            return
        try:
            found = self._fetch(library)
            self._save()
            if found:
                log(f"✓ {found} descripciones nuevas")
        except urllib.error.HTTPError as e:
            self._save()
            if e.code != 429:   # 429 = «espera un poco»: se sigue sola en la próxima vuelta
                log(f"⚠ Descripciones: se reintentará más tarde ({e})")
        except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
            self._save()
            log(f"⚠ Descripciones: se reintentará más tarde ({e})")
        finally:
            self.busy.release()

    def _fetch(self, library):
        from artwork import IMDB_RE, TVDB_RE
        found = 0
        movies, shows = {}, {}
        movies_lang, shows_lang = {}, {}   # solo les falta el idioma original (la sinopsis ya está)
        def movie_code(it):
            if self.codes:
                return self.codes.movie_code(it)
            m = IMDB_RE.search(it["path"])
            return m.group(1) if m else ""

        def show_code(show):
            if self.codes:
                return self.codes.show_code(show, library)
            first = library.items.get(show["poster"])
            m = TVDB_RE.search(first["path"]) if first else None
            return m.group(1) if m else ""

        for it in list(library.items.values()):
            if it["kind"] == "movie":
                need_desc, need_lang = self._pending(it["id"]), self._pending_original(it["id"])
                code = movie_code(it) if need_desc or need_lang else ""
                if code:
                    (movies if need_desc else movies_lang)[code] = it["id"]
        episodes_by_show = {}
        for show in list(library.series):
            code = show_code(show)
            if not code:
                continue
            key = f"serie-{show['key']}"
            if self._pending(key):
                shows[code] = key
            elif self._pending_original(key):
                shows_lang[code] = key
            eps = [library.items[e["id"]] for s in show["seasons"] for e in s["items"] if e["id"] in library.items]
            eps = [e for e in eps if self._pending(e["id"])]
            if eps:
                episodes_by_show[code] = eps
        # Películas y series: Wikipedia (una consulta a Wikidata por grupo, luego un artículo a la vez),
        # como mucho PER_RUN artículos por vuelta; lo que falte sigue en la próxima. En la misma consulta
        # viene el idioma original: a lo que solo le falta eso se le pide de a LANG_PER_RUN por vuelta.
        budget = PER_RUN
        for prop, wanted, lang_only in (("P345", movies, movies_lang), ("P4835", shows, shows_lang)):
            wanted = dict(list(wanted.items())[:budget])
            lang_only = dict(list(lang_only.items())[:LANG_PER_RUN])
            need_lang = {**lang_only, **{c: k for c, k in wanted.items() if self._pending_original(k)}}
            if not wanted and not lang_only:
                continue
            titles = _wikipedia_titles(prop, list(wanted) + list(lang_only))
            for code, key in need_lang.items():
                self._store_original(key, titles.get(code, {}).get("orig"))
            self._save()
            time.sleep(PAUSE)
            for code, key in wanted.items():
                budget -= 1
                desc, lang = "", ""
                for lang in ("es", "en"):
                    title = titles.get(code, {}).get(lang)
                    if title:
                        desc = _wikipedia_plot(lang, title)
                        time.sleep(PAUSE)
                        if desc:
                            break
                self._store(key, desc, lang if desc else "")
                found += bool(desc)
            self._save()
        # Episodios: TVmaze trae todos los de una serie en una consulta
        for tvdb, eps in episodes_by_show.items():
            try:
                show = _get_json(f"https://api.tvmaze.com/lookup/shows?thetvdb={tvdb}")
                all_eps = _get_json(f"https://api.tvmaze.com/shows/{show['id']}/episodes")
            except urllib.error.HTTPError:
                continue
            by_number = {(e.get("season"), e.get("number")): e for e in all_eps}
            for it in eps:
                nums = re.findall(r"\d+", it.get("ep") or "")
                e = by_number.get((it.get("season"), int(nums[0]))) if nums else None
                desc = _clean((e or {}).get("summary") or "")
                self._store(it["id"], desc, "en" if desc else "")
                found += bool(desc)
            time.sleep(0.5)
        return found
