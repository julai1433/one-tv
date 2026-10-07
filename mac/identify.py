"""Códigos de IMDb (películas) y de TheTVDB (series) para lo que no los trae en el nombre, como casi toda biblioteca
acomodada para Plex («Movies/Avatar (2009)/Avatar (2009).mkv»).

Con el código salen el póster (mac/artwork.py), la sinopsis y el idioma original (mac/metadata.py). Se busca así:
1. En el nombre de la carpeta o del archivo: {imdb-tt…} y {tvdb-…} (One TV y Plex), [imdbid-tt…] y [tvdbid-…]
   (Jellyfin). Esto es lo de siempre y no cambia.
2. Con el código de otro sitio que traiga ({tmdb-…} de Plex, o un {imdb-tt…} en la carpeta de una serie): Wikidata
   dice cuál es el que hace falta.
3. Por el nombre y el año de la película o de la serie: el buscador de IMDb para películas y TVmaze para series (los
   mismos que usa el organizador, sin cuenta ni clave).
Lo encontrado se guarda en la caché (codigos.json): los archivos no se tocan nunca. Lo que no se encuentra se vuelve a
buscar en dos semanas. Sin el año, una película puede confundirse con otra del mismo nombre; con el año, casi nunca.
"""

import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

IMDB_TAG = re.compile(r"(?i)[\{\[]imdb(?:id)?[-=](tt\d+)[\}\]]")
TMDB_TAG = re.compile(r"(?i)[\{\[]tmdb(?:id)?[-=](\d+)[\}\]]")
TVDB_TAG = re.compile(r"(?i)[\{\[]tvdb(?:id)?[-=](\d+)[\}\]]")
UA = {"User-Agent": "OneTV/1.0 (servidor casero de video; https://github.com/julai1433/one-tv)"}
PER_RUN = 40                   # búsquedas por nombre por vuelta (una vuelta por minuto)
PAUSE = 0.3                    # entre búsquedas: sin apurar a los servicios
RETRY_AFTER = 14 * 24 * 3600   # lo que no se encontró se vuelve a buscar en dos semanas
WIKIDATA_BATCH = 150
# Wikidata: de qué código a cuál. P4947 TMDB (película), P4983 TMDB (serie), P345 IMDb, P4835 TheTVDB (serie).
MOVIE_FROM_TMDB = ("P4947", "P345")
SHOW_FROM_TMDB = ("P4983", "P4835")
SHOW_FROM_IMDB = ("P345", "P4835")


def _get_json(url, timeout=20):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return json.loads(r.read())


def split_title(title):
    """«Avatar (2009)» -> ("Avatar", 2009); sin año -> ("Avatar", None)."""
    m = re.match(r"^(.*?)\s*\((\d{4})\)$", (title or "").strip())
    return (m.group(1).strip(), int(m.group(2))) if m else ((title or "").strip(), None)


def find_movie(name, year):
    """Código de IMDb de una película por su nombre y año (el buscador público de IMDb), o ""."""
    query = f"{name} {year}" if year else name
    q = urllib.parse.quote(query.lower())
    data = _get_json(f"https://v3.sg.media-imdb.com/suggestion/{q[0] if q[0].isalnum() else 'x'}/{q}.json")
    results = [r for r in data.get("d", []) if r.get("id", "").startswith("tt")
               and r.get("qid") in ("movie", "tvMovie", "video", "short")]
    if year:
        results = [r for r in results if r.get("y") and abs(r["y"] - year) <= 1]
    return results[0]["id"] if results else ""


def find_show(name, year):
    """Código de TheTVDB de una serie por su nombre (y año, si lo hay), según TVmaze; o ""."""
    found = _get_json("https://api.tvmaze.com/search/shows?q=" + urllib.parse.quote(name))
    shows = [r.get("show") or {} for r in found or []]
    if year:
        shows = [s for s in shows if (s.get("premiered") or "")[:4].isdigit()
                 and abs(int(s["premiered"][:4]) - year) <= 1]
    for show in shows[:1]:
        tvdb = (show.get("externals") or {}).get("thetvdb")
        return str(tvdb) if tvdb else ""
    return ""


def wikidata_map(prop_from, prop_to, values):
    """{código: otro código} en una consulta a Wikidata (por ejemplo, de TMDB a IMDb)."""
    if not values:
        return {}
    listed = " ".join(f'"{v}"' for v in values)
    query = f"SELECT ?from ?to WHERE {{ VALUES ?from {{ {listed} }} ?item wdt:{prop_from} ?from . " \
            f"?item wdt:{prop_to} ?to . }}"
    data = _get_json("https://query.wikidata.org/sparql?format=json&query=" + urllib.parse.quote(query), timeout=60)
    out = {}
    for row in data["results"]["bindings"]:
        out.setdefault(row["from"]["value"], row["to"]["value"])
    return out


class Identifier:
    def __init__(self, cache_dir):
        self.file = Path(cache_dir) / "codigos.json"
        self.lock = threading.Lock()
        self.busy = threading.Lock()
        try:
            self.data = json.loads(self.file.read_text())   # clave -> {"code": "tt…" | "123" | "", "t": cuándo}
        except (OSError, ValueError):
            self.data = {}

    # ---------- qué código tiene cada cosa ----------

    @staticmethod
    def movie_key(it):
        return "peli:" + (it.get("work") or it["title"]).lower()

    @staticmethod
    def show_key(show, first):
        return f"serie:{show['key']}:{(first or {}).get('show_year') or ''}"

    def _stored(self, key):
        return (self.data.get(key) or {}).get("code", "")

    def movie_code(self, it):
        """El código de IMDb de una película («tt…»), o "" si aún no se sabe."""
        m = IMDB_TAG.search(it["path"])
        return m.group(1) if m else self._stored(self.movie_key(it))

    def show_code(self, show, library):
        """El código de TheTVDB de una serie, o "" si aún no se sabe."""
        first = library.items.get(show["poster"])
        if not first:
            return ""
        m = TVDB_TAG.search(first["path"])
        return m.group(1) if m else self._stored(self.show_key(show, first))

    # ---------- buscar lo que falta ----------

    def _pending(self, key):
        entry = self.data.get(key)
        return not entry or (not entry["code"] and time.time() - entry["t"] > RETRY_AFTER)

    def _store(self, key, code):
        with self.lock:
            self.data[key] = {"code": code or "", "t": time.time()}

    def _save(self):
        with self.lock:
            try:
                self.file.parent.mkdir(parents=True, exist_ok=True)
                tmp = self.file.with_suffix(".tmp")
                tmp.write_text(json.dumps(self.data, ensure_ascii=False))
                tmp.replace(self.file)
            except OSError:
                pass

    def todo(self, library):
        """(películas, series) que no traen código y aún no se buscaron: {clave: (código de otro sitio, nombre, año)}."""
        movies, shows = {}, {}
        for it in list(library.items.values()):
            if it["kind"] != "movie" or IMDB_TAG.search(it["path"]):
                continue
            key = self.movie_key(it)
            if key in movies or not self._pending(key):
                continue
            tmdb = TMDB_TAG.search(it["path"])
            name, year = split_title(it.get("work") or it["title"])
            movies[key] = (("tmdb", tmdb.group(1)) if tmdb else None, name, year)
        for show in list(library.series):
            first = library.items.get(show["poster"])
            if not first or TVDB_TAG.search(first["path"]):
                continue
            key = self.show_key(show, first)
            if key in shows or not self._pending(key):
                continue
            folder = first.get("show_dir") or ""   # los códigos de otro sitio, solo en la carpeta de la serie
            tmdb, imdb = TMDB_TAG.search(folder), IMDB_TAG.search(folder)
            other = ("tmdb", tmdb.group(1)) if tmdb else ("imdb", imdb.group(1)) if imdb else None
            shows[key] = (other, show["title"], first.get("show_year") or None)
        return movies, shows

    def fetch_all(self, library, log=print):
        """Busca los códigos que falten (de a poco: sigue en la próxima vuelta). Devuelve cuántos encontró."""
        if not self.busy.acquire(blocking=False):
            return 0
        found = 0
        try:
            movies, shows = self.todo(library)
            if not movies and not shows:
                return 0
            try:
                found += self._by_other_code(movies, shows)
            except (urllib.error.URLError, OSError, ValueError, KeyError):
                pass   # Wikidata no respondió: lo de abajo (por el nombre) sigue igual
            budget = PER_RUN
            for table, search in ((movies, find_movie), (shows, find_show)):
                for key, (_, name, year) in list(table.items()):
                    if budget <= 0:
                        break
                    if not self._pending(key) or len(name) < 2:
                        continue
                    budget -= 1
                    code = search(name, year)
                    self._store(key, code)
                    found += bool(code)
                    time.sleep(PAUSE)
            if found:
                log(f"✓ {found} películas o series identificadas por su nombre (para pósters y sinopsis)")
        except (urllib.error.URLError, OSError, ValueError, KeyError):
            pass   # sin internet o el servicio falló: sigue en la próxima vuelta
        finally:
            self._save()
            self.busy.release()
        return found

    def _by_other_code(self, movies, shows):
        """Lo que trae el código de otro sitio ({tmdb-…}): Wikidata da el que hace falta. Lo que no aparece ahí se
        busca después por el nombre."""
        found = 0
        for table, kind, (prop_from, prop_to) in ((movies, "tmdb", MOVIE_FROM_TMDB), (shows, "tmdb", SHOW_FROM_TMDB),
                                                  (shows, "imdb", SHOW_FROM_IMDB)):
            wanted = {other[1]: key for key, (other, _, _) in table.items() if other and other[0] == kind}
            values = list(wanted)[:WIKIDATA_BATCH]
            if not values:
                continue
            answer = wikidata_map(prop_from, prop_to, values)
            for value in values:
                if answer.get(value):
                    self._store(wanted[value], answer[value])
                    found += 1
            time.sleep(PAUSE)
        return found
