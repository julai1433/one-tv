"""Escaneo de la biblioteca: encuentra videos, los analiza con ffprobe,
les pone un título limpio, los agrupa en filas y decide si el Roku
los puede reproducir tal cual o hay que convertirlos al vuelo."""

import hashlib
import json
import os
import re
import subprocess
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import hostos

VIDEO_EXTS = {".mp4", ".m4v", ".mov", ".mkv", ".avi", ".wmv", ".mpg", ".mpeg",
              ".ts", ".m2ts", ".webm", ".flv", ".divx", ".3gp", ".ogm"}
SUB_EXTS = {".srt", ".vtt"}
# Pistas de audio aparte, junto al video (los doblajes que agrega el servicio: «Película.latino.m4a»).
AUDIO_SIDECAR_EXTS = {".m4a", ".mka"}
# Carpetas de material extra que no queremos en el catálogo.
SKIP_DIRS = {"featurettes", "extras", "extra", "sample", "samples", "trailers",
             "behind the scenes", "deleted scenes", "interviews", "shorts",
             "bonus", "other", "others", "scenes"}
MIN_DURATION = 150  # segundos; lo más corto suele ser muestra o menú

# Lo que este Roku (Streaming Stick 3840R) decodifica, medido con CanDecodeVideo/Audio.
DIRECT_CONTAINERS = {".mp4": "mp4", ".m4v": "mp4", ".mov": "mp4", ".mkv": "mkv"}
DIRECT_AUDIO_MAX_CH = {"aac": 2, "mp3": 2, "flac": 6, "alac": 6, "opus": 6, "vorbis": 6}
TEXT_SUB_CODECS = {"subrip", "srt", "ass", "ssa", "mov_text", "webvtt", "text"}

LANGS = {
    "spa": "Español", "es": "Español", "esp": "Español", "lat": "Español", "eng": "Inglés",
    "en": "Inglés", "fre": "Francés", "fra": "Francés", "fr": "Francés", "ita": "Italiano",
    "it": "Italiano", "ger": "Alemán", "deu": "Alemán", "de": "Alemán", "por": "Portugués",
    "pt": "Portugués", "jpn": "Japonés", "ja": "Japonés", "chi": "Chino", "zho": "Chino",
    "kor": "Coreano", "rus": "Ruso", "dut": "Neerlandés", "nld": "Neerlandés",
    "dan": "Danés", "swe": "Sueco", "nor": "Noruego", "pol": "Polaco", "tur": "Turco",
    "ara": "Árabe", "hin": "Hindi", "cat": "Catalán", "gre": "Griego", "ell": "Griego",
    "heb": "Hebreo", "fin": "Finés", "hun": "Húngaro", "cze": "Checo", "ces": "Checo",
}
# Palabras en nombres de archivo de subtítulos -> código de idioma.
SUB_NAME_LANGS = [
    (re.compile(r"(?i)(spanish|español|espanol|castellano|latino|\bspa\b|\besp\b|\bes\b|\blat\b)"), "spa"),
    (re.compile(r"(?i)(english|\beng\b|\ben\b)"), "eng"),
]
LANG_ORDER = {"spa": 0, "eng": 1}
SPANISH_CODES = {"spa", "es", "esp", "lat"}
SPANISH_WORDS = re.compile(r"(?i)latino|castellano|espa[ñn]ol|spanish")
CASTILIAN_WORDS = re.compile(r"(?i)castellano|castilian|espa[ñn]a|spain|europe|\bes-es\b|\bcast\b")

EPISODE_RE = re.compile(r"(?i)(?:^|[\s._\-\[(])s(\d{1,2})[\s._-]?e(\d{1,3})")
YEAR_RE = re.compile(r"(?<!\d)(19[2-9]\d|20[0-4]\d)(?!\d)")
PAREN_YEAR_RE = re.compile(r"\((19[2-9]\d|20[0-4]\d)\)")
# Bibliotecas acomodadas para Plex (o Jellyfin, Emby, Kodi):
# - extras junto a la película con un sufijo: «Película (2009)-trailer.mkv», «…-behindthescenes.mkv»;
# - una película en varios archivos: «Película (2009) - pt1.mkv», «… - cd2.avi», «… part3»;
# - ediciones: «Película (1982) {edition-Director's Cut}»;
# - carpetas de temporada («Season 01», «Temporada 2», «Specials») dentro de la carpeta de la serie;
# - carpetas con películas sueltas («Movies/Avatar (2009).mkv»): son películas, no una colección.
EXTRA_SUFFIX_RE = re.compile(r"(?i)-(trailer|behindthescenes|deleted|featurette|interview|scene|short|other)$")
PART_RE = re.compile(r"(?i)[\s._-]+(?:cd|dvd|disc|disk|part|pt)[\s._-]?(\d{1,2})$")
EDITION_RE = re.compile(r"\{edition-([^}]+)\}")
SEASON_DIR_RE = re.compile(r"(?i)^(?:(?:season|temporada|staffel|saison|series)\s*\d{1,3}|s\d{1,3}|specials|especiales)$")
MOVIE_DIR_RE = re.compile(r"(?i)^(movies?|pel[ií]culas?|pelis|films?|filmes|cine)\b")
JUNK_RE = re.compile(
    r"(?i)(?<![a-z0-9])(2160p|1080p|720p|576p|480p|4k|uhd|blu-?ray|brrip|bdrip|bd-?rip|"
    r"web-?rip|web-?dl|hdtv|dvd-?rip|dvdscr|hdrip|x26[45]|h\.?26[45]|hevc|avc|xvid|divx|"
    r"aac(?:5\.1)?|ac3|dd5|ddp5|ddp|dts|10bit|remux|proper|repack|extended|unrated|imax|yts|yify|"
    r"rarbg|amzn|nf|dsnp|hmax|atvp|multi|dual|subs?|rm4k|remastered|latino|castellano)(?![a-z0-9])")
SEASON_WORD_RE = re.compile(r"(?i)\b(season|temporada)\s*\d+.*$")


def _nfc(s):
    return unicodedata.normalize("NFC", s)


IMDB_RE = re.compile(r"\{imdb-(tt\d+)\}")
GROUP_CHUNK = 14  # filas largas de películas se parten alfabéticamente


def video_id(path):
    """El identificador de un video de la biblioteca (el mismo para la TV, la web y lo guardado de él)."""
    return hashlib.sha1(str(path).encode()).hexdigest()[:12]


def _year_of(name):
    """El año entre paréntesis de un nombre ya limpio («Serie (2020)» -> 2020), o 0."""
    m = PAREN_YEAR_RE.search(clean_title(name))
    return int(m.group(1)) if m else 0


def clean_title(name, fallback=None):
    """'Boogie.Nights.1997.1080p.BluRay.x264-[YTS.AM]' -> 'Boogie Nights (1997)'."""
    s = re.sub(r"\[[^\]]*\]|\{[^}]*\}", " ", _nfc(name))
    s = re.sub(r"[._]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    junk = JUNK_RE.search(s)
    q = junk.start() if junk else len(s)
    year = next((m for m in YEAR_RE.finditer(s) if m.start() > 0), None)
    title = s[:q]
    if year and year.start() < q:
        head = s[:year.start()].strip(" -([")
        tail = s[year.end():q].strip(" -()[]")
        if len(tail.split()) < 3 and head:
            title = f"{head} ({year.group(1)})"
    elif year and title.strip(" -(["):
        title = f"{title.strip(' -([')} ({year.group(1)})"
    title = re.sub(r"\s+-\s*[A-Za-z0-9]+$", "", title.strip(" -([")) or title
    title = re.sub(r"\s+", " ", title).strip(" -([")
    return title or (name if fallback is None else fallback)


def _initial(title):
    c = unicodedata.normalize("NFD", title[:1].upper())[:1]
    return c if "A" <= c <= "Z" else "#"


LANG_WORDS = {"english", "ingles", "inglés", "spanish", "español", "espanol", "french", "francés", "français",
              "german", "deutsch", "italian", "italiano", "portuguese", "japanese", "chinese", "korean",
              "russian", "subtitulos", "subtítulos", "subtitles", "subs", "audio"}


def _useful_tag(title, label):
    """Descarta títulos de pista que no aportan ('Stereo', 'Español' en una pista española...)."""
    t = _nfc(title or "").strip()
    # "Español Latino" -> "Latino": se quitan las palabras que solo repiten el idioma.
    t = _trim(" ".join(w for w in t.split() if w.lower().strip("()[]") not in LANG_WORDS))
    if not t or len(t) >= 30 or t.lower() in label.lower():
        return False
    if t.lower() in {"english", "spanish", "español", "espanol", "french", "français", "german", "deutsch",
                     "italian", "italiano", "portuguese", "japanese", "chinese", "korean", "russian"}:
        return False
    return not re.search(r"(?i)^(stereo|estéreo|mono|surround|5\.1|7\.1|2\.0|dolby.*|aac.*|ac-?3.*|e-?ac-?3.*|dts.*|sdh)$", t)


def _trim(t):
    """Quita guiones y paréntesis sueltos de las puntas sin romper los que cierran algo: 'Latino (Redoblaje)'."""
    t = t.strip(" -")
    while t.startswith("(") and t.count("(") > t.count(")"):
        t = t[1:].strip(" -")
    while t.endswith(")") and t.count(")") > t.count("("):
        t = t[:-1].strip(" -")
    if t.startswith("(") and t.endswith(")") and "(" not in t[1:-1]:
        t = t[1:-1].strip(" -")
    return t


def _clean_tag(title):
    t = _trim(" ".join(w for w in _nfc(title).split() if w.lower().strip("()[]") not in LANG_WORDS))
    t = re.sub(r"\s*\(([^()]*)\)", r", \1", t).strip(" ,")  # va entre paréntesis: sin anidar otros
    return t or _nfc(title).strip()


def has_spanish_audio(path, info):
    """¿Se puede oír en español? (doblada o hablada en español desde el origen)."""
    tracks = info["audio"]
    for a in tracks:
        lang = (a["lang"] or "und").lower()
        if lang in SPANISH_CODES or (lang == "und" and SPANISH_WORDS.search(a["title"] or "")):
            return True
    # Pistas sin idioma marcado: el nombre del archivo o su carpeta suelen decirlo ("… Latino 1080p").
    unknown = tracks and all((a["lang"] or "und").lower() == "und" for a in tracks)
    return bool(unknown and SPANISH_WORDS.search(_nfc(f"{Path(path).parent.name} {Path(path).name}")))


LATINO_WORDS = re.compile(r"(?i)latin|\blat\b|m[eé]xic|latam|am[eé]rica")


def _spanish_tracks(path, info):
    """[(pista, variante)] de las pistas en español; variante: "latino", "castellano" o "" (no lo dice)."""
    name = _nfc(f"{Path(path).parent.name} {Path(path).name}")
    by_name = "latino" if LATINO_WORDS.search(name) else "castellano" if CASTILIAN_WORDS.search(name) else ""
    unknown = info["audio"] and all((a["lang"] or "und").lower() == "und" for a in info["audio"])
    out = []
    for a in info["audio"]:
        lang, title = (a["lang"] or "und").lower(), a["title"] or ""
        if not (lang in SPANISH_CODES or (lang == "und" and SPANISH_WORDS.search(title))):
            continue
        if lang == "lat" or LATINO_WORDS.search(title):
            out.append((a, "latino"))
        elif CASTILIAN_WORDS.search(title):
            out.append((a, "castellano"))
        else:
            out.append((a, "" if unknown else by_name))
    return out


def latino_track(path, info):
    """La pista que sirve como doblaje latino (la marcada como latina, o una en español sin decir cuál)."""
    tracks = _spanish_tracks(path, info)
    return next((a for want in ("latino", "") for a, v in tracks if v == want), None)


def needs_latino(path, info):
    """¿Le falta el doblaje latino? (no tiene español, o solo el de España)."""
    if not has_spanish_audio(path, info):
        return True
    tracks = _spanish_tracks(path, info)
    return bool(tracks) and all(v == "castellano" for _, v in tracks)


# Códigos de idioma que significan lo mismo (ffprobe, Wikidata y los archivos no siempre usan el mismo).
LANG_CANON = {"es": "spa", "esp": "spa", "lat": "spa", "en": "eng", "fr": "fre", "fra": "fre", "de": "ger",
              "deu": "ger", "it": "ita", "pt": "por", "ja": "jpn", "zh": "chi", "zho": "chi", "ko": "kor",
              "ru": "rus", "nl": "dut", "nld": "dut", "el": "gre", "ell": "gre", "cs": "cze", "ces": "cze",
              "ca": "cat", "ar": "ara", "hi": "hin", "da": "dan", "sv": "swe", "no": "nor", "nb": "nor",
              "pl": "pol", "tr": "tur", "he": "heb", "fi": "fin", "hu": "hun", "fa": "per", "fas": "per",
              "ro": "rum", "ron": "rum", "sk": "slo", "slk": "slo", "is": "ice", "isl": "ice", "cy": "wel",
              "cym": "wel", "hy": "arm", "hye": "arm", "eu": "baq", "eus": "baq", "ka": "geo", "kat": "geo",
              "mk": "mac", "mkd": "mac", "ms": "may", "msa": "may", "my": "bur", "mya": "bur", "sq": "alb",
              "sqi": "alb", "bo": "tib", "bod": "tib", "mi": "mao", "mri": "mao"}


def lang_key(code):
    """El mismo código para el mismo idioma: «fra» y «fre», «es» y «spa»."""
    code = (code or "und").strip().lower()
    return LANG_CANON.get(code, code)


def _audio_extras(title):
    """Lo que un título de pista dice además del idioma y que vale la pena mostrar, sin jerga."""
    t = title or ""
    out = []
    if re.search(r"(?i)commentar|comentari", t):
        out.append("comentarios")
    if re.search(r"(?i)descriptive|audio ?descri|\bad\b", t):
        out.append("audiodescripción")
    if re.search(r"(?i)redoblaje|redub", t):
        out.append("redoblaje")
    return out


def _audio_names(info_audio, spanish, original_index, ext_flags, original_lang=""):
    """[(nombre, técnico)] de cada pista: «Español (latino)», «Inglés (original)», «… · agregado».
    Una pista sin idioma marcado que es la original toma el idioma de la obra («Inglés (original)») o, si no se
    sabe, se llama «Idioma original»; las demás sin idioma, «Pista 2», «Pista 3»…"""
    wants = [original_lang] if isinstance(original_lang, str) else list(original_lang or [])
    work_lang = next((w for w in wants if w and w != "und"), "")
    names = []
    for n, a in enumerate(info_audio):
        lang = (a["lang"] or "und").lower()
        if lang != "und":
            base = lang_name(lang)
        elif n == original_index:
            base = lang_name(work_lang) if work_lang else "Idioma original"
        else:
            base = f"Pista {n + 1}"
        variant = spanish.get(a["index"], "")
        parts = []
        if variant == "latino":
            parts.append("latino")
        elif variant == "castellano":
            parts.append("España")
        parts += _audio_extras(a["title"])
        if n == original_index and base != "Idioma original":
            parts.append("original")
        name = base + (f" ({', '.join(parts)})" if parts else "")
        if ext_flags[n]:
            name += " · agregado"
        tech = f"{(a['codec'] or '').upper()} {channels_label(a['channels'])}".strip()
        names.append((name, tech))
    # Dos pistas con el mismo nombre se distinguen con un número.
    total = {}
    for name, _ in names:
        total[name.split(" · agregado")[0]] = total.get(name.split(" · agregado")[0], 0) + 1
    seen, out = {}, []
    for name, tech in names:
        stem, sep, tail = name.partition(" · agregado")
        if total[stem] > 1:
            seen[stem] = seen.get(stem, 0) + 1
            stem = f"{stem} {seen[stem]}"
        out.append((stem + sep + tail, tech))
    return out


def _pick_original(info_audio, spanish, default, original_lang):
    """Índice de la pista en el idioma original de la obra. Respaldo: la predeterminada; si no, la primera.
    Una pista aparte (archivo suelto) nunca es la original."""
    inside = [n for n, a in enumerate(info_audio) if not isinstance(a["index"], str)]
    if not inside:
        return default
    wants = [original_lang] if isinstance(original_lang, str) else list(original_lang or [])
    for want in [lang_key(w) for w in wants if w]:   # una obra puede tener varios idiomas originales: el primero que haya
        found = [n for n in inside if lang_key(info_audio[n]["lang"]) == want
                 or (want == "spa" and n in spanish_positions(info_audio, spanish))]
        if found:
            # En una película en español con doblaje latino, la original es la que no es latina.
            return min(found, key=lambda n: (spanish.get(info_audio[n]["index"]) == "latino",
                                             not info_audio[n]["default"], n))
    return default if default in inside else inside[0]


def spanish_positions(info_audio, spanish):
    return {n for n, a in enumerate(info_audio) if a["index"] in spanish}


def _sub_name(s):
    """Nombre sin jerga de un subtítulo: «Español (latino)», «Inglés», «Inglés (forzados)»."""
    label, lang = s["label"], (s["lang"] or "und").lower()
    if lang == "und":
        return label if label and label.upper() != "UND" else "Subtítulos"
    low = label.lower()
    parts = []
    if lang == "lat" or "latino" in low:
        parts.append("latino")
    elif re.search(r"espana|españa|castellano", low):
        parts.append("España")
    if s.get("forced") or "forzad" in low:
        parts.append("forzados")
    if re.search(r"sdh|hearing|\bcc\b", low):
        parts.append("para sordos")
    if "internet" in low:
        parts.append("de internet")
    return lang_name(lang) + (f" ({', '.join(parts)})" if parts else "")


def choose_tracks(pub, audio_lang="original", sub_lang="off"):
    """Regla para EMPEZAR un video (la misma que aplican la tele y la web). -> (audio, sub) como índices en
    pub["audio"] y pub["subs"]; sub -1 = sin subtítulos.
    Audio: «original» -> la pista original (si no hay, la predeterminada); un idioma -> la primera pista de
    ese idioma y, si no hay, la original. Subtítulos: «off» -> ninguno; un idioma -> el completo de ese
    idioma (antes que los forzados) y, si no hay de ese idioma, ninguno."""
    tracks = pub.get("audio") or []
    original = next((n for n, a in enumerate(tracks) if a.get("original")), pub.get("audio_default", 0))
    audio = original
    if (audio_lang or "original") != "original":
        want = lang_key(audio_lang)
        audio = next((n for n, a in enumerate(tracks) if lang_key(a.get("lang")) == want), original)
    subs = pub.get("subs") or []
    sub = -1
    if (sub_lang or "off") != "off":
        want = lang_key(sub_lang)
        same = [n for n, s in enumerate(subs) if lang_key(s.get("lang")) == want]
        full = [n for n in same if not subs[n].get("forced")]
        sub = (full or same or [-1])[0]
    return audio, sub


def _ep_numbers(label):
    return [int(n) for n in re.findall(r"\d+", label or "")]


def _follows(a, b):
    """¿b es el episodio inmediato siguiente de a? E5 → E6, o del último de una temporada al E1 de la siguiente."""
    na, nb = _ep_numbers(a["ep"]), _ep_numbers(b["ep"])
    if not na or not nb:
        return False
    if b["season"] == a["season"]:
        return nb[0] == na[-1] + 1
    return b["season"] == a["season"] + 1 and nb[0] == 1


def show_key(name):
    return re.sub(r"[^a-z0-9]", "", name.lower())


def nice_show_name(raw):
    name = clean_title(raw)
    name = YEAR_RE.sub("", name).replace("()", "").strip(" -")
    if name and name == name.lower():
        name = name.title()
    return name


def lang_name(code):
    return LANGS.get((code or "").lower(), (code or "").upper() or "Desconocido")


def channels_label(ch):
    return {1: "mono", 2: "estéreo", 6: "5.1", 7: "6.1", 8: "7.1"}.get(ch, f"{ch}ch")


def natural_key(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def probe(path):
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
            capture_output=True, text=True, timeout=90, stdin=subprocess.DEVNULL)
        data = json.loads(out.stdout or "{}")
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
        return None
    fmt = data.get("format") or {}
    info = {"duration": float(fmt.get("duration") or 0), "start": float(fmt.get("start_time") or 0),
            "video": None, "audio": [], "subs": []}
    for s in data.get("streams", []):
        kind = s.get("codec_type")
        tags = {k.lower(): v for k, v in (s.get("tags") or {}).items()}
        disp = s.get("disposition") or {}
        if kind == "video" and not disp.get("attached_pic") and info["video"] is None:
            info["video"] = {
                "index": s["index"], "codec": s.get("codec_name"), "profile": s.get("profile") or "",
                "level": s.get("level") or 0, "pix_fmt": s.get("pix_fmt") or "",
                "width": s.get("width") or 0, "height": s.get("height") or 0,
            }
            if not info["duration"]:
                info["duration"] = float(s.get("duration") or 0)
        elif kind == "audio":
            info["audio"].append({
                "index": s["index"], "codec": s.get("codec_name"), "channels": s.get("channels") or 2,
                "lang": tags.get("language", "und"), "title": tags.get("title", ""),
                "default": bool(disp.get("default")),
            })
        elif kind == "subtitle":
            info["subs"].append({
                "index": s["index"], "codec": s.get("codec_name"), "lang": tags.get("language", "und"),
                "title": tags.get("title", ""), "forced": bool(disp.get("forced")),
            })
    return info


MAX_MBPS = 25  # más que esto no pasa fluido por el Wi-Fi del Roku: se recodifica más liviano


def classify(ext, info, size):
    """Decide cómo llega cada video al Roku. Devuelve (modo, motivo):
    - "direct": el Roku lo reproduce tal cual.
    - "copy": el video sirve; se copia intacto y solo se convierte el audio (o se cambia el contenedor).
    - "full": hay que convertir también el video."""
    video_problem = _video_problem(info)
    if video_problem:
        return "full", video_problem
    mbps = size * 8 / max(info["duration"], 1) / 1e6
    if mbps > MAX_MBPS:
        return "full", f"archivo muy pesado para el Wi-Fi ({mbps:.0f} Mbps)"
    audio_problem = _audio_problem(info)
    if audio_problem:
        return "copy", audio_problem
    if ext not in DIRECT_CONTAINERS:
        return "copy", f"formato {ext[1:].upper()}"
    return "direct", None


def _video_problem(info):
    v = info["video"]
    if v["codec"] != "h264":
        return f"video {v['codec'].upper()}"
    if "10" in v["profile"] or v["pix_fmt"] not in ("yuv420p", "yuvj420p"):
        return "video de 10 bits"
    if v["level"] and v["level"] > 42:
        return f"H.264 nivel {v['level'] / 10:g}"
    if v["width"] > 1920 or v["height"] > 1088:
        return "resolución 4K"
    return None


def _audio_problem(info):
    for a in info["audio"]:
        max_ch = DIRECT_AUDIO_MAX_CH.get(a["codec"])
        if max_ch is None:
            return f"audio {a['codec'].upper()}"
        if a["channels"] > max_ch:
            return f"audio {a['codec'].upper()} {channels_label(a['channels'])}"
    return None


def _show_dir(root, episode):
    """(carpeta de la serie, ¿el episodio está en una carpeta de temporada?). La carpeta de la serie es la que contiene
    «Season 01», «Temporada 2» o «Specials»; o, si no hay, la del propio episodio. None si sería la raíz."""
    parent = episode.parent
    in_season = parent != root and bool(SEASON_DIR_RE.match(_nfc(parent.name)))
    folder = parent.parent if in_season else parent
    return (folder if folder != root and root in folder.parents else None), in_season


def _movies_folder(folder, videos):
    """¿Una carpeta con varios videos sueltos es de películas y no una colección o temporada? Sí si se llama como
    una («Movies», «Películas», «Films»…), si son las partes de una sola película o si la mayoría trae el año entre
    paréntesis, como pide Plex («Avatar (2009).mkv»)."""
    if MOVIE_DIR_RE.match(_nfc(folder.name)):
        return True
    if all(PART_RE.search(v.stem) for v in videos):
        return True
    return sum(bool(PAREN_YEAR_RE.search(v.stem)) for v in videos) * 2 > len(videos)


class Library:
    def __init__(self, roots, cache_dir, title_overrides=None):
        self.roots = [Path(os.path.expanduser(r)).resolve() for r in roots]
        self.overrides = title_overrides or {}  # {"tt0286112": "Shaolin Soccer (2001)"}
        self.cache_file = Path(cache_dir) / "probe-cache.json"
        self.lock = threading.Lock()
        self.items = {}        # id -> dict con todo lo que sabemos del video
        self.rows = []         # filas de la versión anterior de la app del Roku
        self.movie_rows = []   # películas: recientes + tramos alfabéticos
        self.series = []       # series -> temporadas -> episodios
        self.next_ep = {}      # episodio -> el inmediato siguiente (si está en la biblioteca)
        self.scanned_at = 0
        self.warnings = []
        self.ext_probe = {}    # (ruta, mtime, tamaño) de pistas aparte -> ffprobe
        self.original_lookup = None   # función(video) -> código de idioma original; la pone la app (metadata.py)
        # Subtítulos que One TV guardó en su propia carpeta (los de videos en carpetas de otro programa, como Plex):
        # <carpeta>/<id del video>/… La pone la app (mac/folders.py); sin ella, solo se buscan junto al video.
        self.own_subs = None
        try:
            self.probe_cache = json.loads(self.cache_file.read_text())
        except (OSError, json.JSONDecodeError):
            self.probe_cache = {}

    # ---------- escaneo ----------

    def _walk(self):
        """Lista (raíz, ruta) de todos los videos, sin extras ni archivos ocultos."""
        found = []
        self.warnings = []
        for root in self.roots:
            try:
                os.listdir(root)
            except (FileNotFoundError, NotADirectoryError):
                self.warnings.append(f"no existe la carpeta {root}")
                continue
            except PermissionError:
                self.warnings.append(f"macOS no deja leer {root} (mueve los videos a ~/Movies "
                                     "o da «Acceso total al disco» a python3 en Ajustes → Privacidad)" if hostos.MAC
                                     else f"tu usuario no tiene permiso para leer {root}")
                continue
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames
                               if not d.startswith(".") and _nfc(d).lower() not in SKIP_DIRS]
                for f in filenames:
                    if f.startswith(".") or Path(f).suffix.lower() not in VIDEO_EXTS:
                        continue
                    if re.search(r"(?i)(?<![a-z])sample(?![a-z])", f):
                        continue
                    if EXTRA_SUFFIX_RE.search(Path(f).stem):   # extra de Plex: «Película (2009)-trailer.mkv»
                        continue
                    found.append((root, Path(dirpath) / f))
        return found

    def scan(self, force=False):
        with self.lock:
            if not force and time.time() - self.scanned_at < 20:
                return
            files = self._walk()
            todo = []
            stats = {}
            for root, path in files:
                try:
                    st = path.stat()
                except OSError:
                    continue
                stats[path] = st
                cached = self.probe_cache.get(str(path))
                if not cached or cached["mtime"] != st.st_mtime or cached["size"] != st.st_size:
                    todo.append(path)
            if todo:
                with ThreadPoolExecutor(max_workers=6) as pool:
                    for path, info in zip(todo, pool.map(probe, todo)):
                        st = stats[path]
                        self.probe_cache[str(path)] = {"mtime": st.st_mtime, "size": st.st_size, "info": info}
            live = {str(p) for p in stats}
            self.probe_cache = {k: v for k, v in self.probe_cache.items() if k in live}
            try:
                self.cache_file.parent.mkdir(parents=True, exist_ok=True)
                self.cache_file.write_text(json.dumps(self.probe_cache))
            except OSError:
                pass
            entries = []
            for root, path in files:
                c = self.probe_cache.get(str(path))
                if not c or not c["info"] or not c["info"]["video"]:
                    continue
                if c["info"]["duration"] and c["info"]["duration"] < MIN_DURATION:
                    continue
                entries.append((root, path, c["info"], stats[path]))
            self._build(entries)
            self.scanned_at = time.time()

    # ---------- títulos y filas ----------

    def _build(self, entries):
        # Cuántos videos hay bajo cada carpeta (para saber si una carpeta es "de una película").
        under = {}
        direct = {}   # carpeta -> los videos que están directo en ella
        for root, path, _, _ in entries:
            direct.setdefault(path.parent, []).append(path)
            for parent in path.parents:
                under[parent] = under.get(parent, 0) + 1
                if parent == root:
                    break
        direct_count = {folder: len(videos) for folder, videos in direct.items()}
        items, groups = {}, {}
        for root, path, info, st in entries:
            item_id = video_id(path)
            ep = EPISODE_RE.search(path.stem)
            rel_parent = path.parent.relative_to(root)
            part = None if ep else PART_RE.search(path.stem)
            if ep:
                raw_show = path.stem[:ep.start()]
                show = nice_show_name(raw_show) if clean_title(raw_show).strip(" -") else ""
                show_dir, in_season_dir = _show_dir(root, path)
                if show_dir and in_season_dir:
                    # Serie/Season 01/episodio (como lo acomodan One TV, Plex y Jellyfin): la serie es la de su carpeta,
                    # aunque los archivos se llamen distinto entre sí.
                    show = nice_show_name(show_dir.name) or show
                elif show_dir and show_key(nice_show_name(show_dir.name)) != show_key(show):
                    show_dir = None   # episodios sueltos en otra carpeta («Series/», «TV Shows/»): no es la de la serie
                if not show:
                    show = nice_show_name(SEASON_WORD_RE.sub("", path.parent.name)) or "Series"
                season, episode = int(ep.group(1)), int(ep.group(2))
                rest_raw = path.stem[ep.end():]
                multi = re.match(r"(?i)[-\s]?e(\d{1,3})", rest_raw)  # episodio doble: S04E01E02
                ep_label = f"E{episode}–{int(multi.group(1))}" if multi else f"E{episode}"
                if multi:
                    rest_raw = rest_raw[multi.end():]
                rest = clean_title(rest_raw, fallback="").strip(" -")
                title = f"T{season} {ep_label}" + (f" · {rest}" if rest and len(rest) > 2 else "")
                gkey = ("serie", show_key(show))
                gtitle = show
                sort = (season, episode, path.name)
                full = f"{show} · T{season} {ep_label}" + (f" · {rest}" if rest and len(rest) > 2 else "")
                extra = {"kind": "episode", "show": show, "season": season, "ep": ep_label,
                         "ep_title": rest if rest and len(rest) > 2 else "",
                         "show_year": _year_of(show_dir.name if show_dir else raw_show),
                         "show_dir": str(show_dir) if show_dir else ""}
            elif direct_count[path.parent] >= 2 and path.parent != root and \
                    under[path.parent] == direct_count[path.parent] and not _movies_folder(path.parent, direct[path.parent]):
                # Carpeta con varios videos sueltos y sin subcarpetas: una temporada/colección.
                gtitle = clean_title(path.parent.name)
                gkey = ("serie", show_key(gtitle))
                title = clean_title(path.stem)
                sort = (0, 0, natural_key(path.name))
                full = f"{gtitle} · {title}"
                season_word = re.search(r"(?i)(?:season|temporada)\s*(\d+)", path.parent.name)
                extra = {"kind": "episode", "show": gtitle, "season": int(season_word.group(1)) if season_word else 1,
                         "ep": "", "ep_title": title}
            else:
                # Película: sube por las carpetas que solo contienen este video.
                top = path.parent
                while top != root and top.parent != root and under.get(top.parent, 0) == 1:
                    top = top.parent
                # Una película en varios archivos (pt1, pt2…) también tiene su carpeta, si en ella solo están sus partes.
                alone = under.get(top, 0) == 1 or (part and top == path.parent and under.get(top, 0) == direct_count[top]
                                                   and all(PART_RE.search(v.stem) for v in direct[top]))
                folder_title = clean_title(top.name) if top != root and alone else ""
                file_title = clean_title(path.stem[:part.start()] if part else path.stem)
                if folder_title and (YEAR_RE.search(folder_title) or not YEAR_RE.search(file_title)):
                    title = folder_title
                else:
                    title = file_title
                imdb = IMDB_RE.search(str(path))
                if imdb and imdb.group(1) in self.overrides:
                    title = self.overrides[imdb.group(1)]
                work = title
                if part:
                    title = f"{title} · Parte {int(part.group(1))}"
                category = top.parent if folder_title else path.parent
                rel = category.relative_to(root) if category != root else Path()
                gtitle = " · ".join(_nfc(p) for p in rel.parts) or "Películas"
                gkey = ("peli", gtitle.lower())
                sort = (0, 0, title.lower())
                full = title
                edition = EDITION_RE.search(path.stem) or (EDITION_RE.search(top.name) if folder_title else None)
                extra = {"kind": "movie", "work": work, "movie_dir": str(top) if folder_title else "",
                         "edition": _nfc(edition.group(1)).strip() if edition else ""}
            mode, reason = classify(path.suffix.lower(), info, st.st_size)
            ext_audio = self._ext_audio(path)
            if ext_audio:
                info = {**info, "audio": info["audio"] + ext_audio}
            items[item_id] = {
                "id": item_id, "path": str(path), "title": title, "full_title": full,
                "duration": round(info["duration"], 1), "mtime": st.st_mtime, "size": st.st_size,
                "info": info, "mode": mode, "reason": reason, "rel": _nfc(str(rel_parent)),
                "subs": self._find_subs(path, info, direct_count.get(path.parent, 1)),
                **extra,
            }
            groups.setdefault(gkey, {"title": gtitle, "kind": gkey[0], "items": []})["items"].append((sort, item_id))

        # Dos ediciones de la misma película ({edition-…} de Plex): se distinguen por la edición.
        same_title = {}
        for it in items.values():
            if it["kind"] == "movie":
                same_title.setdefault(it["title"].lower(), []).append(it)
        for same in same_title.values():
            if len(same) > 1:
                for it in same:
                    if it["edition"]:
                        it["title"] = it["full_title"] = f"{it['title']} · {it['edition']}"

        self._build_sections(items, groups)
        rows = []
        recent = sorted(items.values(), key=lambda it: it["mtime"], reverse=True)[:15]
        if recent:
            rows.append({"title": "Recién agregadas", "items": [
                {"id": it["id"], "label": it["full_title"]} for it in recent]})
        for kind in ("peli", "serie"):
            for g in sorted((g for k, g in groups.items() if k[0] == kind), key=lambda g: g["title"].lower()):
                g["items"].sort(key=lambda t: t[0])
                ids = [i for _, i in g["items"]]
                if kind == "peli" and len(ids) > GROUP_CHUNK * 1.5:
                    # Parte la fila en tramos alfabéticos para no tener que avanzar 60 veces.
                    chunks = [ids[n:n + GROUP_CHUNK] for n in range(0, len(ids), GROUP_CHUNK)]
                    if len(chunks) > 1 and len(chunks[-1]) < GROUP_CHUNK // 2:
                        tail = chunks.pop()
                        chunks[-1] += tail
                    for chunk in chunks:
                        first, last = _initial(items[chunk[0]]["title"]), _initial(items[chunk[-1]]["title"])
                        rows.append({"title": f"{g['title']} · {first}–{last}" if first != last else f"{g['title']} · {first}",
                                     "items": [{"id": i, "label": items[i]["title"]} for i in chunk]})
                else:
                    rows.append({"title": g["title"], "items": [
                        {"id": i, "label": items[i]["title"]} for i in ids]})
        self.items, self.rows = items, rows

    def _build_sections(self, items, groups):
        """Películas en filas (recientes + tramos alfabéticos) y series por temporadas."""
        movies = []
        recent = sorted((it for it in items.values() if it["kind"] == "movie"), key=lambda it: it["mtime"], reverse=True)
        if recent:
            movies.append({"title": "Recién agregadas", "items": [{"id": it["id"], "label": it["title"]} for it in recent[:15]]})
        # Todas juntas y en orden alfabético: la tele y la web las muestran en cuadrícula.
        ids = sorted((i for i, it in items.items() if it["kind"] == "movie"), key=lambda i: items[i]["title"].lower())
        if ids:
            movies.append({"title": "Películas", "items": [{"id": i, "label": items[i]["title"]} for i in ids]})

        series, nexts = [], {}
        for key, g in sorted(((k, g) for k, g in groups.items() if k[0] == "serie"), key=lambda kg: kg[1]["title"].lower()):
            # Los especiales (temporada 0, «Specials» de Plex) van al final: «Empezar» es por el primer episodio.
            episode_ids = [i for _, i in sorted(g["items"], key=lambda t: (t[0][0] == 0, t[0]))]
            seasons = {}
            for i in episode_ids:
                seasons.setdefault(items[i]["season"], []).append(i)
            out = []
            for number in sorted(seasons, key=lambda n: (n == 0, n)):
                entries = []
                for n, i in enumerate(seasons[number], 1):
                    it = items[i]
                    if not it["ep"]:  # colecciones sin SxxEyy: se numeran por orden
                        it["ep"] = f"E{n}"
                    entries.append({"id": i, "label": it["ep"] + (f" · {it['ep_title']}" if it["ep_title"] else "")})
                out.append({"season": number, "title": "Especiales" if number == 0 else f"Temporada {number}",
                            "items": entries})
            ordered = [e["id"] for season in out for e in season["items"]]
            for a, b in zip(ordered, ordered[1:]):
                if _follows(items[a], items[b]):
                    nexts[a] = b
            series.append({"key": key[1], "title": g["title"], "poster": episode_ids[0],
                           "episodes": len(episode_ids), "seasons": out,
                           "dub": any(has_spanish_audio(items[i]["path"], items[i]["info"]) for i in episode_ids)})
        self.movie_rows, self.series, self.next_ep = movies, series, nexts

    # ---------- pistas de audio aparte ----------

    def _ext_audio(self, path):
        """Doblajes en archivo aparte junto al video: «Película.latino.m4a», «Película.es.mka»…"""
        stem = _nfc(path.stem).lower()
        out = []
        try:
            files = sorted(f for f in path.parent.iterdir() if f.suffix.lower() in AUDIO_SIDECAR_EXTS
                           and not f.name.startswith(".") and _nfc(f.stem).lower().startswith(stem + "."))
        except OSError:
            return out
        for f in files:
            try:
                st = f.stat()
            except OSError:
                continue
            key = (str(f), st.st_mtime, st.st_size)
            if key not in self.ext_probe:
                self.ext_probe[key] = probe(f)
            info = self.ext_probe[key]
            if not info or not info["audio"]:
                continue
            a = info["audio"][0]
            label = _nfc(f.stem)[len(stem) + 1:]
            lang = a["lang"] if a["lang"] != "und" else \
                next((code for rx, code in SUB_NAME_LANGS if rx.search(label)), "und")
            title = a["title"] or label.replace(".", " ").strip().capitalize()
            out.append({"index": f"x{len(out)}", "codec": a["codec"], "channels": a["channels"],
                        "lang": lang, "title": title, "default": False, "file": str(f)})
        return out

    # ---------- subtítulos ----------

    def _find_subs(self, path, info, videos_in_dir):
        subs = []
        stem = _nfc(path.stem).lower()
        candidates = []
        try:
            if self.own_subs:   # los que One TV guardó en su carpeta (videos en carpetas de otro programa)
                kept = Path(self.own_subs) / video_id(path)
                if kept.is_dir():
                    candidates += [f for f in kept.iterdir() if f.suffix.lower() in SUB_EXTS]
            for f in path.parent.iterdir():
                if f.suffix.lower() in SUB_EXTS and (_nfc(f.stem).lower().startswith(stem) or videos_in_dir == 1):
                    candidates.append(f)
            subs_dir = next((d for d in path.parent.iterdir() if d.is_dir() and d.name.lower() in ("subs", "subtitles")), None)
            if subs_dir:
                per_episode = subs_dir / path.stem
                search = per_episode if per_episode.is_dir() else (subs_dir if videos_in_dir == 1 else None)
                if search:
                    candidates += [f for f in search.iterdir() if f.suffix.lower() in SUB_EXTS]
        except OSError:
            pass
        for n, f in enumerate(sorted(candidates, key=lambda p: natural_key(p.name))):
            label_src = _nfc(f.stem)[len(stem):] if _nfc(f.stem).lower().startswith(stem) else _nfc(f.stem)
            lang = next((code for rx, code in SUB_NAME_LANGS if rx.search(label_src)), "und")
            if lang == "und":
                m2 = re.search(r"\.([a-z]{2,3})(?:\.|$)", label_src.lower())
                lang = m2.group(1) if m2 and m2.group(1) in LANGS else "und"
            extra = " (SDH)" if re.search(r"(?i)sdh|hearing|\bcc\b", label_src) else ""
            extra += " (forzados)" if re.search(r"(?i)forced|forzad", label_src) else ""
            if re.search(r"(?i)latino", label_src):
                extra = " (Latino)" + extra
            elif re.search(r"(?i)espana|españa|castellano", label_src):
                extra = " (España)" + extra
            if "opensubtitles" in label_src.lower():
                extra += " · internet"
            subs.append({"key": f"x{n}", "lang": lang, "label": lang_name(lang) + extra if lang != "und"
                         else (label_src.strip(" ._-") or "Subtítulos"), "file": str(f),
                         "forced": bool(re.search(r"(?i)forced|forzad", label_src))})
        for s in info["subs"]:
            if s["codec"] not in TEXT_SUB_CODECS:
                continue
            extra = f" ({_clean_tag(s['title'])})" if _useful_tag(s["title"], lang_name(s["lang"])) else ""
            extra = re.sub(r"(?i)\bforced\b", "forzados", extra)
            forced = s["forced"] or "forzados" in extra.lower()
            if forced and "forzados" not in extra.lower():
                extra += " (forzados)"
            subs.append({"key": f"e{s['index']}", "lang": s["lang"], "label": lang_name(s["lang"]) + extra,
                         "stream": s["index"], "forced": forced})
        if len(subs) > 6:
            subs = [s for s in subs if s["lang"] in ("spa", "eng", "und")] or subs
        # Por idioma (español, inglés, lo demás) y, en cada uno, los completos antes que los forzados.
        subs.sort(key=lambda s: (LANG_ORDER.get(s["lang"], 5), s.get("forced", False)))
        per_lang, kept = {}, []
        for s in subs:  # algunos MKV traen 40 pistas; con 3 por idioma basta
            per_lang[s["lang"]] = per_lang.get(s["lang"], 0) + 1
            if per_lang[s["lang"]] <= 4:
                kept.append(s)
        return kept[:8]

    # ---------- salida para el Roku / la web ----------

    def public_item(self, it):
        info = it["info"]
        ext = Path(it["path"]).suffix.lower()
        spanish = {a["index"]: v for a, v in _spanish_tracks(it["path"], info)}
        audio = []
        default = 0
        for n, a in enumerate(info["audio"]):
            label = lang_name(a["lang"]) if a["lang"] != "und" else f"Pista {n + 1}"
            if _useful_tag(a["title"], label):
                label += f" ({_clean_tag(a['title'])})"
            separate = isinstance(a["index"], str)   # pista aparte: «x0», «x1»…
            label += " · agregado" if separate else f" · {a['codec'].upper()} {channels_label(a['channels'])}"
            entry = {"label": label, "lang": a["lang"],
                     "hls": f"/hls/{it['id']}/{a['index'] if separate else 'a' + str(a['index'])}/index.m3u8"}
            if separate:
                entry["ext"] = True   # el Roku no la ve dentro del archivo: siempre llega por la Mac
            audio.append(entry)
            if a["default"] and not info["audio"][default]["default"]:
                default = n
        if audio:
            try:
                original_lang = self.original_lookup(it) if self.original_lookup else ""
            except Exception:  # noqa: BLE001 - el idioma original es un extra: sin él se usa el respaldo
                original_lang = ""
            original = _pick_original(info["audio"], spanish, default, original_lang)
            names = _audio_names(info["audio"], spanish, original, [isinstance(a["index"], str) for a in info["audio"]],
                                 original_lang)
            for n, entry in enumerate(audio):
                entry["name"], entry["tech"] = names[n]
                entry["original"] = n == original
        else:
            audio.append({"label": "Sin audio", "lang": "und", "hls": f"/hls/{it['id']}/na/index.m3u8",
                          "name": "Sin audio", "tech": "", "original": True})
        subs = [{"label": s["label"], "lang": s["lang"], "url": f"/subs/{it['id']}/{s['key']}.srt",
                 "forced": bool(s.get("forced")), "name": _sub_name(s)} for s in it["subs"]]
        seen = {}
        for name in [s["name"] for s in subs]:
            seen[name] = seen.get(name, 0) + 1
        count = {}
        for s in subs:   # dos con el mismo nombre se distinguen con un número
            if seen[s["name"]] > 1:
                count[s["name"]] = count.get(s["name"], 0) + 1
                s["name"] = f"{s['name']} {count[s['name']]}"
        return {
            "id": it["id"], "title": it["title"], "full_title": it["full_title"], "kind": it["kind"],
            "show": it.get("show", ""), "season": it.get("season", 0), "ep": it.get("ep", ""),
            "ep_title": it.get("ep_title", ""), "next": self.next_ep.get(it["id"], ""),
            "duration": it["duration"], "poster": f"/poster/{it['id']}.jpg",
            "mode": it["mode"],
            "direct": {"url": f"/media/{it['id']}{ext}", "format": DIRECT_CONTAINERS[ext]} if it["mode"] == "direct" else None,
            "convert_reason": it["reason"] or "",
            "audio": audio, "audio_default": default, "dub": has_spanish_audio(it["path"], info),
            "subs": subs,
        }

    def api(self):
        with self.lock:
            return {"rows": self.rows, "movies": self.movie_rows, "series": self.series,
                    "items": {i: self.public_item(it) for i, it in self.items.items()}}

    def get(self, item_id):
        with self.lock:
            return self.items.get(item_id)
