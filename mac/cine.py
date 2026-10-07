"""One TV: ver las películas de esta computadora en el Roku.

Uso:
    ./cine                      arranca (o, si ya arranca solo con la computadora, lo actualiza y muestra la dirección)
    ./cine configurar           primer arranque guiado: carpeta de videos, Roku y música (crea config.json)
    ./cine autoarranque         deja el servidor corriendo siempre, también al encender la computadora
    ./cine quitar-autoarranque  deja de arrancar solo
    ./cine estado               dice si está corriendo y en qué direcciones
    ./cine tailscale            publica la página en tu red Tailscale con https (para el iPhone)
    ./cine barra                pone el ícono en la barra de menú (y lo actualiza; solo macOS)
    ./cine quitar-barra         quita el ícono de la barra de menú (solo macOS)
    ./cine instalar             solo instala/actualiza la app en el Roku
    ./cine catalogo             lista los videos y cómo llega cada uno a la TV
"""

import atexit
import filecmp
import json
import os
import plistlib
import random
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path

import encoders
import hostos
import linuxservice
import windowsservice
from library import Library
from roku import Roku, build_channel_zip, discover, local_ip_towards
from server import KeepAwake, Media, serve
from store import Store
from live import LiveChannels, LiveError, set_sign_key
from subtitles_online import OpenSubtitles, SubtitleError, save_next_to_video
from youtube import CHANNEL_ID, HISTORY_MAX, YouTube, YouTubeError, fetch_durations, video_id
from ytdurations import DurationFiller
from artwork import Artwork
from metadata import Metadata
from organizer import Organizer
from dubbing import Dubbing
from intro import IntroDetector
from subsync import SubtitleAligner
from playqueue import MAX_ITEMS, PlayQueue
from ytaccount import YouTubeAccount, name_key
from offline import Offline
from transcode import Transcoder
from mosaic import Mosaics, MosaicError, item_source, parse_request
from segcache import SegmentCache
from mylists import FAV, MyLists
from music import Music, default_roots

PROJECT = Path(__file__).resolve().parent.parent
CONFIG = PROJECT / "config.json"
# Carpetas: en macOS ~/Library/…; en Linux las de XDG (~/.cache, ~/.local/share, ~/.local/state). Ver mac/hostos.py.
CACHE = hostos.CACHE

SERVICE_LABEL = "local.cine-roku"
SERVICE_HOME = hostos.SERVICE_HOME
SERVICE_PLIST = Path.home() / "Library" / "LaunchAgents" / f"{SERVICE_LABEL}.plist"   # macOS (en Linux: linuxservice)
SERVICE_LOG = hostos.LOG
DATA = SERVICE_HOME / "datos"   # progreso y preferencias: sobrevive a actualizaciones
# yt-dlp propio del servicio, en un entorno aislado: se actualiza solo sin tocar Homebrew
# (actualizar el Python de Homebrew le quita a macOS el permiso de «Red local» que el servidor necesita).
YTDLP_ENV = SERVICE_HOME / "ytdlp"
YTDLP = hostos.venv_bin(YTDLP_ENV, "yt-dlp")   # en Windows, Scripts\yt-dlp.exe
YTDLP_EVERY = 24 * 3600
# Doblajes: la sincronización necesita numpy, en su propio entorno (se instala solo la primera vez).
DUB_ENV = SERVICE_HOME / "doblaje"
TAILSCALE_PORT = 8766
BARRA_LABEL = "local.cine-roku.barra"
BARRA_APP = Path.home() / "Applications" / "One TV.app"
BARRA_APP_OLD = Path.home() / "Applications" / "Cine en casa.app"   # nombre anterior: se borra al instalar la nueva
BARRA_PLIST = Path.home() / "Library" / "LaunchAgents" / f"{BARRA_LABEL}.plist"
PLAYLIST_IN_QUEUE = 50   # de una lista larga, cuántos videos entran de una vez a la fila
FAVORITES_SHOWN = 40   # la fila «Favoritos» de YouTube (la lista entera se abre desde «Tus listas»)
BECAUSE_TTL = 3600   # «porque viste» se recalcula cada hora
DOWNLOADS_EVERY = 10   # segundos entre vistazos a las Descargas (lo terminado entra a la biblioteca en menos de 1 min)
BECAUSE_MIN = 3      # un grupo de «porque viste» con menos videos que valgan la pena no se muestra
# Palabras que no dicen de qué trata un video (para comparar títulos de recomendaciones con lo que se vio).
COMMON_WORDS = set("""para pero porque como cuando donde este esta estos estas todo toda todos todas sobre entre desde
hasta nunca siempre video videos oficial official completa completo completas completos parte capitulo capítulo
episodio episodios pelicula película peliculas películas español espanol castellano latino latina subtitulado
subtitulada gratis with this that from your what when have will about after into they their there more most best
live full movie movies""".split())
BACKGROUND = False


def say(msg):
    if BACKGROUND:
        print(f"[{time.strftime('%d/%m %H:%M:%S')}] {msg}", flush=True)
    else:
        print(msg, flush=True)


def load_config():
    cfg = {"carpetas": [hostos.default_library()], "puerto": 8765, "roku_ip": "", "roku_password": "", "titulos": {}}
    try:
        cfg.update(json.loads(CONFIG.read_text(encoding="utf-8-sig")))   # (el Bloc de notas de Windows puede ponerle BOM)
    except FileNotFoundError:
        pass
    except json.JSONDecodeError as e:
        sys.exit(f"✗ config.json tiene un error de formato: {e}")
    return cfg


MARK_OFFER = 8   # segundos que se ofrece «saltar» desde donde empieza el tramo


def active_mark(marks, position):
    """La marca que se está ofreciendo en esa posición ({label, end}) o None: desde su inicio, durante
    MARK_OFFER segundos (o hasta su final si es antes). Sin estado: al volver a entrar al tramo, se ofrece de nuevo."""
    for m in sorted(marks or [], key=lambda m: m.get("start", 0)):
        start, end = m.get("start", 0), m.get("end", 0)
        if end > start and start <= position < min(start + MARK_OFFER, end):
            return {"label": m.get("label", ""), "end": end}
    return None




def sign_key(path):
    """La clave con que se firman las direcciones de las listas: se inventa una vez y se guarda (solo para ti), así
    lo que la TV ya tiene sigue sirviendo aunque se reinicie el servidor."""
    try:
        key = Path(path).read_bytes()
        if len(key) >= 32:
            return key
    except OSError:
        pass
    key = os.urandom(32)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(key)
    Path(path).chmod(0o600)
    return key

def title_words(title):
    """Las palabras de un título que dicen de qué trata (4 letras o más, sin las de relleno)."""
    return {w for w in re.findall(r"\w{4,}", (title or "").casefold()) if w not in COMMON_WORDS and not w.isdigit()}

class App:
    def __init__(self, cfg):
        self.cfg = cfg
        self.library = Library(cfg["carpetas"], CACHE, cfg.get("titulos"))
        self.media = Media(CACHE)
        self.keep_awake = KeepAwake()
        self.transcoder = None
        self.mosaics = None   # varios a la vez en la TV (mac/mosaic.py); se crea al arrancar el servidor
        # Trozos de YouTube y de canales en vivo que el mosaico pide antes que ffmpeg (mac/segcache.py).
        self.segments = SegmentCache()
        self.roku = None
        self.server_url = ""
        self.installed_url = None
        self.install_waiting = False
        self.store = Store(DATA / "progreso.json")
        self.subs = OpenSubtitles(cfg)
        self.live = LiveChannels(DATA, CACHE, cfg.get("navegador", ""))
        DATA.mkdir(parents=True, exist_ok=True)
        self.youtube = YouTube(DATA, CACHE, str(YTDLP) if YTDLP.exists() else None)
        set_sign_key(sign_key(DATA / "clave_enlaces"))   # firma de las direcciones de las listas (mac/live.py)
        # Tu música (mac/music.py): config «musica» o, si no, ~/Music/Biblioteca si existe.
        music_roots = cfg.get("musica")
        self.music = Music(default_roots() if music_roots is None else music_roots, DATA / "musica.json",
                           CACHE / "musica", log=say)
        self.music_sessions = {}   # lo que se mandó a la TV para escuchar: id -> {tracks, index, at}
        # Canales de YouTube en «En vivo» (DW, noticias, música 24/7): su transmisión de ahora la da yt-dlp, no Chrome.
        self.live.youtube_live = self._youtube_live_now
        self.live.youtube_thumb = self._youtube_thumb_bytes
        # Duración de los videos de YouTube: el caché vive con YouTube; lo que falte lo pide, poco a poco, el rellenador.
        self.durations = self.youtube.durations
        DurationFiller(self.durations, fetch_durations, log=say)
        # Videos y listas guardados en la computadora (sin conexión): se miran en las mismas direcciones de YouTube.
        self.offline = Offline(cfg.get("sin_conexion"), cfg.get("sin_conexion_gb"), DATA / "sin_conexion.json",
                               self.youtube, log=say, blocked=self.durations.blocked)
        self.youtube.offline = self.durations.offline = self.offline
        self.artwork = Artwork(CACHE)
        self.metadata = Metadata(CACHE)
        self.library.original_lookup = self.metadata.original_langs   # idioma original de cada película/serie
        self.queue = PlayQueue(DATA / "cola.json")
        # Favoritos y listas de One TV (y lo cambiado en las del Takeout): viven en la computadora (mac/mylists.py).
        self.lists = MyLists(DATA / "listas.json")
        self.queue.decorate = self._queue_with_durations
        self.account = YouTubeAccount(DATA, hostos.user_dir("DOWNLOAD"), log=say)
        self.account.durations = self.durations
        downloads = cfg.get("descargas")
        if downloads is None:   # por omisión, la carpeta de torrents de Transmission si existe
            default = hostos.user_dir("DOWNLOAD") / "Torrents"
            downloads = [str(default)] if default.is_dir() else []
        self.organizer = Organizer(cfg["carpetas"], downloads, DATA / "organizador.json", log=say)
        self._organize_lock = threading.Lock()
        self.dubbing = Dubbing(DUB_ENV, Path(__file__).resolve().parent / "dubsync.py", DATA / "doblajes.json",
                               hostos.user_dir("VIDEOS") / "Doblajes ya usados", log=say, on_added=self.dub_added)
        self.intros = IntroDetector(self.dubbing, Path(__file__).resolve().parent / "introsync.py", DATA / "intros.json", log=say)
        # Subtítulos aparte (bajados o junto al video) alineados solos con la voz; la tele y la web reciben el
        # alineado (el original no se toca).
        self.subsync = SubtitleAligner(self.dubbing, Path(__file__).resolve().parent / "subsync_voz.py",
                                       DATA / "subtitulos_alineados.json", CACHE / "subs-alineados", log=say)
        self.media.aligned = self.subsync.aligned
        self.iphone_url = None
        self._because = None   # {"at", "seeds", "data"} de «porque viste»
        self._because_busy = False
        self._because_lock = threading.Lock()
        self._player = (0.0, None)
        self._player_lock = threading.Lock()

    # ---------- Roku ----------

    def connect_roku(self, force=False):
        """Encuentra el Roku y deja su app apuntando a la dirección actual de la Mac."""
        ip = self.cfg.get("roku_ip")
        if not ip and self.roku:
            try:
                self.roku.device_name()
                ip = self.roku.ip
            except OSError:
                ip = None
        ip = ip or discover()
        if not ip:
            return False
        if not self.roku or self.roku.ip != ip:
            self.roku = Roku(ip, self.cfg.get("roku_password", ""))
            try:
                say(f"✓ {self.roku.device_name()} en {ip}")
            except OSError:
                return False
        try:
            self.server_url = f"http://{local_ip_towards(ip)}:{self.cfg['puerto']}"
        except OSError:
            return False  # sin red por ahora
        if self.server_url != self.installed_url:
            if not force and not self.roku_is_free():
                if not self.install_waiting:
                    say("… la app del Roku se actualizará cuando la TV esté en Inicio (no interrumpo lo que se ve)")
                    self.install_waiting = True
                return True
            self.install_waiting = False
            ok, msg = self.install_channel()
            say(("✓ " if ok else "✗ ") + f"App del Roku: {msg}")
            if ok:
                self.installed_url = self.server_url
        return True

    def roku_is_free(self):
        """Instalar la app la abre sola en la tele: solo se hace si nadie está viendo otra cosa."""
        try:
            app_id, app_type = self.roku._active()
            if app_type == "home" or not app_id:
                return True
            return app_id == "dev" and self.roku.player()[0] in ("close", "stop", "")
        except OSError:
            return False

    def install_channel(self):
        zip_bytes = build_channel_zip(PROJECT / "roku", self.server_url)
        return self.roku.install(zip_bytes)

    def watch_roku(self):
        """Reintenta cada minuto: el Roku pudo estar apagado o la Mac pudo cambiar de dirección."""
        while True:
            time.sleep(60)
            try:
                self.connect_roku()
                self.iphone_url = tailscale_url(self.cfg["puerto"])
            except Exception as e:  # noqa: BLE001 - nunca debe tumbar el servidor
                say(f"⚠ Roku: {e}")

    def cast(self, item_id, audio=None, sub=None, start=None, device_id=None):
        """Reproduce en la tele. audio/sub: índice en las listas del catálogo (sub -1 = sin
        subtítulos); start: segundos o None para seguir donde iba. device_id: el aparato que lo pide
        (para recordar SU idioma)."""
        if not self.roku:
            return {"ok": False, "error": "No encontré el Roku en la red."}
        item = self.library.get(item_id)
        if not item:
            return {"ok": False, "error": "Ese video ya no está en la biblioteca."}
        try:
            self.roku.play(item_id, self.server_url, audio=audio, sub=sub,
                           start=None if start is None else int(start))
        except OSError as e:
            return {"ok": False, "error": f"El Roku no respondió ({e})."}
        self.remember_tracks(item, audio, sub, device_id)
        return {"ok": True}

    # ---------- canales en vivo ----------

    def live_add(self, url, name=""):
        try:
            say(f"Buscando el video en vivo de {url[:80]}…")
            channel = self.live.add(url, name)
        except LiveError as e:
            # En el registro, el enlace completo (y el detalle técnico): hace falta para saber qué página falló.
            say(f"✗ En vivo: {e}" + (f" ({e.detail})" if getattr(e, "detail", "") else "") + f" · Enlace: {url}")
            return {"ok": False, "error": str(e)}
        say(f"✓ Canal en vivo: {channel['name']}")
        return {"ok": True, "channel": self._live_public(channel["id"])}

    def live_rename(self, cid, name):
        try:
            channel = self.live.rename(cid, name)
        except LiveError as e:
            return {"ok": False, "error": str(e)}
        say(f"✓ Canal en vivo renombrado: {channel['name']}")
        return {"ok": True, "channel": self._live_public(cid)}

    def _live_public(self, cid):
        return next(c for c in self.live.public() if c["id"] == cid)

    def live_play(self, cid):
        if not self.roku:
            return {"ok": False, "error": "No encontré el Roku en la red."}
        if not self.live.get(cid):
            return {"ok": False, "error": "Ese canal ya no existe."}
        try:
            self.roku.play(f"live:{cid}", self.server_url)
            return {"ok": True}
        except OSError as e:
            return {"ok": False, "error": f"El Roku no respondió ({e})."}

    # ---------- YouTube sin anuncios ----------

    def yt_check(self, vid):
        """¿Se puede reproducir este video? Deja resuelta la dirección (la TV la pide enseguida sin esperar otra vez).
        -> {ok, title, duration} o {ok: False, gone, error}. gone: ya no existe (se salta y se avisa)."""
        try:
            info = self.youtube.resolve(vid)["info"]
            return {"ok": True, "title": info.get("title") or "", "duration": info.get("duration") or 0,
                    "live": bool(info.get("live"))}
        except YouTubeError as e:
            title = self.youtube.title_of(vid) or vid
            say(f"✗ YouTube: «{title}» {e}" if e.gone else f"✗ YouTube: «{title}»: {e}")
            return {"ok": False, "gone": e.gone, "error": str(e)}

    # ---------- guardar videos y listas para verlos sin conexión (mac/offline.py) ----------

    def offline_summary(self):
        off = getattr(self, "offline", None)
        return off.summary() if off else {"ok": False, "error": "Guardar sin conexión no está disponible."}

    def offline_save(self, body):
        """{id} guarda un video; {list} una lista de YouTube (todos sus videos). -> {ok, state} o {ok: False, error}."""
        off = getattr(self, "offline", None)
        if not off:
            return {"ok": False, "error": "Guardar sin conexión no está disponible."}
        if body.get("list"):
            list_id = str(body["list"]).strip()
            try:
                data = self._list_data(list_id)
            except YouTubeError as e:
                return {"ok": False, "error": str(e)}
            result = off.save_list(list_id, data.get("title"), data.get("videos"))
            if result.get("ok"):
                say(f"⬇ Lista guardada sin conexión: {data.get('title') or list_id} ({result['count']} videos)")
            return result
        vid = video_id(str(body.get("id") or ""))
        if not vid:
            return {"ok": False, "error": "Ese no parece un video de YouTube."}
        result = off.save_video(vid)
        if result.get("ok"):
            say(f"⬇ Video en la cola sin conexión: {self.youtube.title_of(vid) or vid}")
        return result

    def offline_remove(self, body):
        off = getattr(self, "offline", None)
        if not off:
            return {"ok": False, "error": "Guardar sin conexión no está disponible."}
        if body.get("list"):
            return off.remove_list(str(body["list"]).strip())
        return off.remove_video(str(body.get("id") or "").strip())

    def _youtube_live_now(self, ref):
        try:
            return self.youtube.live_now(ref)
        except YouTubeError as e:
            raise LiveError(str(e)) from e

    def _youtube_thumb_bytes(self, vid):
        p = self.youtube.thumbnail(vid)
        return p.read_bytes() if p else None

    def yt_search(self, query, page=1, live=False):
        """{ok, results, page, more}: more = hay otra página («Cargar más»). live: solo transmisiones en vivo."""
        try:
            page = max(int(page or 1), 1)
        except (TypeError, ValueError):
            page = 1
        try:
            results, more = self.youtube.search(query, page, live=live)
            return {"ok": True, "results": results, "page": page, "more": more}
        except YouTubeError as e:
            return {"ok": False, "error": str(e)}

    def yt_play(self, vid):
        vid = video_id(vid)
        if not vid:
            return {"ok": False, "error": "Ese no parece un video de YouTube."}
        if not self.roku:
            return {"ok": False, "error": "No encontré el Roku en la red."}
        try:
            info = self.youtube.resolve(vid)["info"]
            self.youtube.remember(info)
            self.roku.play(f"yt:{vid}", self.server_url)
            say(f"▶ YouTube en la TV: {info['title']}")
            return {"ok": True, "title": info["title"]}
        except YouTubeError as e:
            return {"ok": False, "error": str(e)}
        except OSError as e:
            return {"ok": False, "error": f"El Roku no respondió ({e})."}

    # ---------- varios a la vez: la computadora arma un solo video (mac/mosaic.py) ----------

    def _mosaic_sources(self, sources):
        """Completa las fuentes ya revisadas (parse_request) con título, archivo y duración. YouTube se resuelve
        aquí, en paralelo: da el título y, si un video no se puede ver, se avisa enseguida (el servidor lo
        guarda unas horas, así que ffmpeg no vuelve a preguntar). Lanza MosaicError."""
        found = {}

        def resolve(vid):
            try:
                found[vid] = self.youtube.resolve(vid)["info"]
            except YouTubeError as e:
                found[vid] = e
        threads = [threading.Thread(target=resolve, args=(s["id"],), daemon=True) for s in sources if s["kind"] == "yt"]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        out = []
        for s in sources:
            if s["kind"] == "item":
                item = self.library.get(s["id"])
                if not item:
                    raise MosaicError("Uno de los videos ya no está en la biblioteca.")
                out.append(item_source(item, s["audio"], s["start"]))
            elif s["kind"] == "live":
                channel = self.live.get(s["id"])
                if not channel:
                    raise MosaicError("Uno de los canales en vivo ya no existe.")
                out.append({"kind": "live", "id": s["id"], "title": channel["name"] or "Canal en vivo"})
            else:
                info = found[s["id"]]
                if isinstance(info, YouTubeError):
                    raise MosaicError(f"«{self.youtube.title_of(s['id']) or s['id']}»: {info}")
                out.append({"kind": "yt", "id": s["id"], "title": info.get("title") or s["id"],
                            "duration": info.get("duration") or 0, "start": s.get("start")})   # desde donde iba
        return out

    def mosaic_start(self, body):
        """{sources, layout?, audio?, focus?} -> {ok, id, url, tracks} (o {ok: False, error})."""
        try:
            sources, layout, audio, focus = parse_request(body)
            sources = self._mosaic_sources(sources)
        except MosaicError as e:
            return {"ok": False, "error": str(e)}
        # keep: la TV sigue mostrando lo de antes (el mosaico anterior o el video) hasta que este esté listo;
        # entonces los videos empiezan un poco más adelante para no repetir lo visto (mosaic.ADVANCE_EXTRA).
        keep = bool(body.get("keep")) if isinstance(body, dict) else False
        m = self.mosaics.start(sources, layout, audio, focus, keep=keep, advance=keep)
        return {"ok": True, "id": m.id, "url": m.url, "tracks": m.tracks}

    def mosaic_status(self, mid):
        m = self.mosaics.get(mid) if self.mosaics else None
        if not m:
            return {"ok": False, "error": "Ese mosaico ya no existe."}
        m.touch()   # quien pregunta por él lo está esperando: cuenta como pedirlo
        return m.status()

    def mosaic_stop(self, mid):
        if not (self.mosaics and self.mosaics.stop(mid)):
            return {"ok": False, "error": "Ese mosaico ya no existe."}
        return {"ok": True}

    def mosaic_tv(self, body):
        """Arma el mosaico y le dice a la TV que lo abra (la app lo pide como «mosaic:<id>»)."""
        try:
            _, _, _, focus = parse_request(body)   # antes de buscar el Roku: los datos malos se dicen primero
        except MosaicError as e:
            return {"ok": False, "error": str(e)}
        if not self.roku:
            return {"ok": False, "error": "No encontré el Roku en la red."}
        result = self.mosaic_start(body)
        if not result["ok"]:
            return result
        try:
            self.roku.play(f"mosaic:{result['id']}", self.server_url, focus=focus)
        except OSError as e:
            self.mosaics.stop(result["id"])
            return {"ok": False, "error": f"El Roku no respondió ({e})."}
        say("▶ Varios a la vez en la TV: " + " + ".join(result["tracks"]))
        return result

    # ---------- cuenta de YouTube (Takeout y canales) ----------

    def keep_account_fresh(self):
        """Tarea automática: cada 10 min mira si hay un Takeout nuevo en Descargas y lo importa; cada 60 min
        lee el RSS de los canales suscritos. Nunca debe tumbar el servidor."""
        time.sleep(45)
        last_feeds = self.account.summary()["feeds_at"]
        while True:
            try:
                self.account.scan_downloads()
                if self.account.channels() and time.time() - last_feeds >= 3600:   # suscripciones visibles y anclados
                    last_feeds = time.time()
                    self.account.refresh_feeds()
                    self.account.new_videos(40)   # las duraciones que falten se piden ya, antes de que se vean
                self.queue.items()                # lo mismo con la fila
            except Exception as e:
                say(f"⚠ Cuenta de YouTube: {e}")
            time.sleep(600)

    # ---------- música ----------

    def music_tv(self, tracks, index=0, shuffle=False, start=0):
        """Escuchar en la TV: la TV pide la lista (music_session) y suena la canción `index`; las demás siguen solas."""
        tracks = [t for t in tracks if self.music.track(t)]
        if not tracks:
            return {"ok": False, "error": "Esas canciones ya no están en tu música."}
        if not self.roku:
            return {"ok": False, "error": "No encontré el Roku en la red."}
        index = min(max(int(index or 0), 0), len(tracks) - 1)
        if shuffle:
            first = tracks[index]
            rest = [t for t in tracks if t != first]
            random.shuffle(rest)
            tracks, index = [first] + rest, 0
        sid = f"{int(time.time() * 1000) % 10**10:010d}"
        self.music_sessions = {k: v for k, v in self.music_sessions.items() if time.time() - v["at"] < 3600}
        self.music_sessions[sid] = {"tracks": tracks, "index": index, "start": max(int(start or 0), 0), "at": time.time()}
        self.music.prepare_next(tracks[index], 0)
        threading.Thread(target=self.music.audio, args=(tracks[index],), daemon=True).start()   # ya convirtiéndose
        try:
            self.roku.play(f"music:{sid}", self.server_url)
        except OSError as e:
            return {"ok": False, "error": f"El Roku no respondió ({e})."}
        t = self.music.track(tracks[index])
        say(f"♪ Música en la TV: {t['title']} · {t['artist']} ({len(tracks)} canciones)")
        return {"ok": True, "count": len(tracks)}

    def queue_add_tracks(self, tracks, front=False):
        """Canciones a la fila (un álbum, una lista), en su orden. -> {ok, added, count}"""
        entries = []
        for t in tracks:
            try:
                entries.append(self.queue_entry("track", t))
            except ValueError:
                pass
        if not entries:
            return {"ok": False, "error": "Esas canciones ya no están en tu música."}
        added = self.queue.add_many(entries, front)
        self.tell_tv_to_refresh()
        return {"ok": True, "added": added, "count": len(self.queue.items())}

    def music_session(self, sid):
        s = self.music_sessions.get(sid)
        if not s:
            return {"ok": False, "error": "Esa lista ya no está."}
        pub = self.music.public()["tracks"]
        return {"ok": True, "index": s["index"], "start": s.get("start", 0), "tracks": [pub[t] for t in s["tracks"] if t in pub]}

    def keep_avatars(self):
        """Tarea automática: baja de a poco las fotos que falten de «Tus canales» (al arrancar y una vez al día), para
        que la TV y la web no esperen a YouTube la primera vez que las muestran."""
        time.sleep(90)
        while True:
            try:
                for c in self.account.channels():
                    if not (self.youtube.thumbs / f"canal-{c['id']}.png").exists():
                        self.youtube.channel_avatar(c["id"])
                        time.sleep(1)
            except Exception as e:  # noqa: BLE001 - nunca debe tumbar el servidor
                say(f"⚠ Fotos de los canales: {e}")
            time.sleep(24 * 3600)

    # ---------- cola de la tele ----------

    def queue_entry(self, kind, ident, title=""):
        if kind == "track":   # una canción de tu música
            t = self.music.track(ident)
            if not t:
                raise ValueError("Esa canción ya no está en tu música.")
            return {"kind": "track", "id": ident, "title": f"{t['title']} · {t['artist']}",
                    "thumb": f"/music/art/{t['album_id']}.jpg"}
        if kind == "item":
            item = self.library.get(ident)
            if not item:
                raise ValueError("Ese video ya no está en la biblioteca.")
            return {"kind": "item", "id": ident, "title": item["full_title"], "thumb": f"/poster/{ident}.jpg"}
        vid = video_id(ident)
        if not vid:
            raise ValueError("Ese no parece un video de YouTube.")
        title = title or self.youtube.title_of(vid) or self.youtube.resolve(vid)["info"]["title"]
        return {"kind": "yt", "id": vid, "title": title, "thumb": f"/yt/{vid}/thumb.jpg"}

    def queue_add(self, kind, ident, title="", front=False):
        try:
            entry = self.queue_entry(kind, ident, title)
        except (ValueError, YouTubeError) as e:
            return {"ok": False, "error": str(e)}
        count = self.queue.add(entry, front)
        say(f"+ {'a continuación' if front else 'al final de la fila'} ({count}): {entry['title']}")
        self.tell_tv_to_refresh()
        return {"ok": True, "count": count, "queue": self.queue.items()}

    def queue_move(self, index, to):
        """Cambia el orden de la fila: la entrada `index` pasa al lugar `to`."""
        where = self.queue.move(index, to)
        if where is None:
            return {"ok": False, "error": "Ese video ya no está en la fila."}
        self.tell_tv_to_refresh()
        return {"ok": True, "index": where, "queue": self.queue.items()}

    def queue_add_list(self, list_id, front=False, shuffle=False):
        """Una lista entera a la fila de reproducción (a continuación o al final, en orden o al azar), sin
        reproducir nada. Se saltan los videos privados y los que ya no existen. -> {ok, added, total, count}"""
        try:
            data = self._list_data(list_id)
        except YouTubeError as e:
            return {"ok": False, "error": str(e)}
        videos = [v for v in data["videos"] if not v.get("private") and not self.youtube.is_gone(v["id"])]
        if not videos:
            return {"ok": False, "error": "Esa lista no tiene videos que se puedan reproducir."}
        if shuffle:
            random.shuffle(videos)
        added = self.queue.add_many([{"kind": "yt", "id": v["id"], "title": v["title"], "thumb": f"/yt/{v['id']}/thumb.jpg"}
                                     for v in videos], front)
        if not added:
            return {"ok": False, "error": f"La fila de reproducción está llena ({MAX_ITEMS} videos)."}
        say(f"+ Lista {'a continuación' if front else 'al final de la fila'}: {data.get('title', '')} "
            f"({added} de {len(videos)} videos{', al azar' if shuffle else ''})")
        self.tell_tv_to_refresh()
        return {"ok": True, "added": added, "total": len(videos), "count": len(self.queue.items())}

    # ---------- Favoritos y listas de One TV (mac/mylists.py) ----------

    def _list_data(self, list_id, network=True):
        """Una lista para ver, reproducir, poner en la fila o guardar: de One TV, del Takeout (con lo cambiado aquí)
        o pública de YouTube. -> {id, title, videos, source} o lanza YouTubeError."""
        own = self.lists.get(list_id)
        if own:
            self._with_durations(own["videos"])
            return {**own, "source": "onetv"}
        data = self._takeout_list(list_id, network)
        if data:
            data["videos"] = self.lists.apply_edits(list_id, data["videos"])
            self._with_durations(data["videos"])
            return {**data, "source": "takeout"}
        return {**self.youtube.playlist_videos(list_id), "source": "youtube"}

    def _takeout_ids(self, key):
        """Ids de una lista del Takeout con lo cambiado aquí, o None si no es del Takeout."""
        acc = getattr(self, "account", None)
        p = acc.find_list(key) if acc else None
        if p is None:
            return None
        return [v["id"] for v in self.lists.apply_edits(key, [{"id": v["id"]} for v in p["videos"]])]

    def _yt_seen(self):
        seen = {}   # video de YouTube -> última vez que se vio en la app
        for e in self.store.history():
            if e["id"].startswith("yt:"):
                seen[e["id"][3:]] = e["t"]
        return seen

    def _my_playlists(self, seen=None):
        """«Tus listas»: Favoritos (si tiene algo) y luego las de One TV y las del Takeout, la usada más
        recientemente primero (escuchada, reproducida o cambiada aquí)."""
        acc = getattr(self, "account", None)
        rows = []
        for s in self.lists.summaries():
            if s["id"] == FAV and not s["count"]:
                continue
            rows.append({"id": s["id"], "title": s["title"], "count": s["count"], "thumb": s["thumb"],
                         "last_played": s["t"], "source": "onetv"})
        try:
            ranked = acc.playlists_ranked(self._yt_seen() if seen is None else seen) if acc else []
        except Exception as e:  # noqa: BLE001
            say(f"⚠ YouTube: la cuenta no dio tus listas ({e})")
            ranked = []
        for r in ranked:
            edited = self.lists.edited_at(r["id"])
            if edited:
                ids = self._takeout_ids(r["id"]) or []
                r = {**r, "count": len(ids), "last_played": int(max(r["last_played"], edited)),
                     "thumb": f"/yt/{ids[0]}/thumb.jpg" if ids else r["thumb"]}
            rows.append(r)
        fav = [r for r in rows if r["id"] == FAV]
        return fav + sorted((r for r in rows if r["id"] != FAV), key=lambda r: (-r["last_played"], r["title"].lower()))

    def lists_for(self, vid):
        """Dónde se puede guardar un video: Favoritos, las listas de One TV y las del Takeout (no las públicas de
        otros), con `has` si ya está. Favoritos primero y luego la usada más recientemente."""
        vid = video_id(vid or "")
        if not vid:
            return {"ok": False, "error": "Ese no parece un video de YouTube."}
        rows = []
        for r in self._my_playlists():
            if r["source"] == "onetv":
                has = self.lists.has(r["id"], vid)
            elif r["source"] == "takeout":
                has = vid in (self._takeout_ids(r["id"]) or [])
            else:
                continue
            rows.append({"id": r["id"], "title": r["title"], "count": r["count"], "source": r["source"], "has": has})
        if not any(r["id"] == FAV for r in rows):   # Favoritos vacío no sale en «Tus listas», pero aquí sí
            rows.insert(0, {"id": FAV, "title": "Favoritos", "count": 0, "source": "onetv", "has": False})
        return {"ok": True, "lists": rows}

    def _video_record(self, vid, body):
        """Lo que se guarda de un video en una lista: lo que mandó quien lo agrega o lo que ya se sepa."""
        info = self.youtube.cached_info(vid) or self.youtube.known(vid) or {}
        v = {"id": vid, "title": body.get("title") or info.get("title") or self.youtube.title_of(vid) or "Video de YouTube",
             "channel": body.get("channel") or info.get("channel") or "",
             "duration": body.get("duration") or info.get("duration") or 0}
        self._with_durations([v])
        return v

    def list_toggle(self, body):
        """{list, id, on?, title?, channel?, duration?}: agrega (on true) o quita (on false) el video; sin «on»,
        lo contrario de lo que esté. -> {ok, has}"""
        list_id, vid = str(body.get("list") or ""), video_id(str(body.get("id") or ""))
        if not vid:
            return {"ok": False, "error": "Ese no parece un video de YouTube."}
        own = self.lists.owns(list_id)
        if own:
            has = self.lists.has(list_id, vid)
        else:
            ids = self._takeout_ids(list_id)
            if ids is None:
                return {"ok": False, "error": "Esa lista ya no existe."}
            has = vid in ids
        on = (not has) if body.get("on") is None else bool(body.get("on"))
        if on == has:
            return {"ok": True, "has": has}
        video = self._video_record(vid, body)
        try:
            if own and on:
                self.lists.add(list_id, video)
            elif own:
                self.lists.remove(list_id, vid)
            elif on:
                self.lists.edit_takeout(list_id, video=video)
            else:
                self.lists.edit_takeout(list_id, remove=vid)
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        title = next((r["title"] for r in self._my_playlists() if r["id"] == list_id), "Favoritos")
        say(f"{'♥' if list_id == FAV else '+'} {video['title']} {'→' if on else '✕'} {title}")
        self.tell_tv_to_refresh()
        return {"ok": True, "has": on}

    def list_create(self, body):
        """{title, id?, video_title?, channel?, duration?}: crea una lista de One TV y, si viene un video, lo agrega.
        -> {ok, list: {id, title}}"""
        try:
            created = self.lists.create(body.get("title"))
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        vid = video_id(str(body.get("id") or ""))
        if vid:
            self.lists.add(created["id"], self._video_record(vid, {**body, "title": body.get("video_title")}))
        say(f"＋ Lista nueva: {created['title']}")
        self.tell_tv_to_refresh()
        return {"ok": True, "list": {"id": created["id"], "title": created["title"]}}

    def list_rename(self, body):
        try:
            self.lists.rename(str(body.get("list") or ""), body.get("title"))
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        self.tell_tv_to_refresh()
        return {"ok": True}

    def list_delete(self, body):
        try:
            gone = self.lists.delete(str(body.get("list") or ""))
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        if not gone:
            return {"ok": False, "error": "Esa lista ya no existe."}
        self.tell_tv_to_refresh()
        return {"ok": True}

    # ---------- duración de los videos de YouTube ----------

    def _with_durations(self, videos):
        """Pone a cada video de YouTube la duración que se sepa (en su lugar) y encarga las que falten al rellenador."""
        durations = getattr(getattr(self, "youtube", None), "durations", None)
        return durations.apply(videos) if durations else videos

    def _filling(self, videos):
        """Segundos hasta que lleguen duraciones que faltan en estos videos (0: nada en camino): la web vuelve a pedir."""
        durations = getattr(getattr(self, "youtube", None), "durations", None)
        return durations.eta(videos) if durations else 0

    def _queue_with_durations(self, entries):
        self._with_durations([e for e in entries if e.get("kind") == "yt"])
        return entries

    def tell_tv_to_refresh(self):
        """La app de la tele vuelve a leer el catálogo (cola, películas nuevas…), sin esperar."""
        def send():
            try:
                if self.roku and self.roku.active_app() == "dev":
                    self.roku.send(cmd="refresh")
            except OSError:
                pass
        threading.Thread(target=send, daemon=True).start()

    def history(self, limit=150):
        """Historial para la tele y la web: películas, episodios y YouTube, con cuándo y hasta dónde."""
        recent = {h["id"]: h for h in self.youtube.recent()}
        items = self.library.items
        out = []
        for e in self.store.history():
            if e["id"].startswith("yt:"):
                vid = e["id"][3:]
                rec = recent.get(vid) or {}
                entry = {"kind": "yt", "id": vid, "title": rec.get("title") or self.youtube.title_of(vid) or "Video de YouTube",
                         "channel": rec.get("channel", ""), "duration": rec.get("duration") or 0,
                         "thumb": f"/yt/{vid}/thumb.jpg"}
            elif e["id"] in items:
                it = items[e["id"]]
                entry = {"kind": "item", "id": it["id"], "title": it["full_title"], "duration": it["duration"],
                         "thumb": f"/poster/{it['id']}.jpg"}
            else:
                continue   # ya no está en la biblioteca
            entry.update(p=e["p"], done=e["p"] == 0, day=day_label(e["t"]), when=when_label(e["t"]),
                         hour=datetime.fromtimestamp(e["t"]).strftime("%H:%M"))
            out.append(entry)
            if len(out) >= limit:
                break
        self._with_durations([e for e in out if e["kind"] == "yt"])
        return out

    def youtube_next(self, finished):
        """Terminó un video de YouTube y la cola está vacía: con la reproducción continua prendida, el
        primer relacionado que no se haya visto hace poco. None si está apagada o no hay."""
        if not self.store.prefs.get("ytAutoplay") or not finished.startswith("yt:"):
            return None
        queued = {e["id"] for e in self.queue.items()}
        try:
            v = self.youtube.next_after(finished[3:], queued, skip=self._hidden_check())
        except Exception as e:  # noqa: BLE001 - sin relacionados, simplemente se detiene
            say(f"⚠ YouTube: no se pudieron leer los relacionados ({e})")
            return None
        if not v:
            return None
        say(f"↪ YouTube recomienda a continuación: {v['title']}")
        return {"kind": "yt", "id": v["id"], "title": v["title"], "thumb": v["thumb"]}

    def set_yt_autoplay(self, on):
        self.store.set_prefs(ytAutoplay=bool(on))
        self.tell_tv_to_refresh()   # para que la tele muestre el ajuste nuevo
        return {"ok": True, "on": bool(on)}

    def queue_play(self, index=0):
        """Desde la web: pone ya en la tele una entrada de la cola (la primera, si no se dice)."""
        entry = self.queue.remove(index)
        if not entry:
            return {"ok": False, "error": "La fila de reproducción está vacía."}
        if entry["kind"] == "track":
            result = self.music_tv([entry["id"]])
        else:
            result = self.yt_play(entry["id"]) if entry["kind"] == "yt" else self.cast(entry["id"])
        if not result.get("ok"):
            self.queue.add(entry, front=True)   # no se pudo: vuelve a su lugar
        return result

    # ---------- YouTube: seguir viendo, porque viste, canales ----------

    def _yt_entry(self, vid):
        """Datos de un video de YouTube ya visto, con lo mínimo si no hay nada guardado."""
        rec = self.youtube.known(vid) or {}
        entry = {"id": vid, "title": rec.get("title") or self.youtube.title_of(vid) or "Video de YouTube",
                 "channel": rec.get("channel", ""), "duration": rec.get("duration") or 0,
                 "thumb": f"/yt/{vid}/thumb.jpg"}
        return self._with_durations([entry])[0]

    def yt_continue(self, limit=20):
        """«Seguir viendo» de YouTube: videos a medias (p > 0), el más reciente primero."""
        out = []
        for e in self.store.history():
            if e["id"].startswith("yt:") and e["p"] > 0:
                out.append({**self._yt_entry(e["id"][3:]), "p": e["p"], "t": e["t"]})
                if len(out) >= limit:
                    break
        return out

    def _hidden_check(self):
        """-> función(video) que dice si el video es de un canal oculto (siempre False si no hay cuenta)."""
        check = getattr(getattr(self, "account", None), "hidden_check", None)
        return check() if check else (lambda v: False)

    def _because_seeds(self, count=3):
        """Los últimos videos de YouTube vistos (sin los de canales ocultos): del historial propio y, si falta, del de
        Takeout."""
        seeds = []
        hidden = self._hidden_check()
        for e in self.store.history():
            if e["id"].startswith("yt:"):
                if hidden(self.youtube.known(e["id"][3:]) or {}):
                    continue
                v = self._yt_entry(e["id"][3:])
                seeds.append({"id": v["id"], "title": v["title"]})
                if len(seeds) >= count:
                    return seeds
        acc = getattr(self, "account", None)
        if acc:
            try:
                for h in acc.watch_history(count * 3):
                    if all(h["id"] != x["id"] for x in seeds) and not hidden(h):
                        seeds.append({"id": h["id"], "title": h.get("title") or "Video de YouTube"})
                        if len(seeds) >= count:
                            break
            except Exception as e:  # noqa: BLE001 - el respaldo no debe romper nada
                say(f"⚠ YouTube: no se pudo leer el historial de la cuenta ({e})")
        return seeds

    def _rank_related(self, seed, related, affinity):
        """Los relacionados que sí tienen que ver: del mismo canal que lo visto, de canales que sigues o que ves
        seguido (historial del Takeout), o con palabras del título de lo visto. Lo demás (lo popular que YouTube le
        pone a cualquiera sin cuenta: éxitos musicales, noticias…) se descarta. Ordenados por cuánto tienen que ver."""
        ids, names = affinity
        seed_rec = self.youtube.known(seed["id"]) or {}
        seed_cid, seed_channel = seed_rec.get("channel_id") or "", name_key(seed_rec.get("channel"))
        seed_words = title_words(seed["title"])
        scored = []
        for i, v in enumerate(related):
            score = ids.get(v.get("channel_id"), 0) or names.get(name_key(v.get("channel")), 0)
            if (seed_cid and v.get("channel_id") == seed_cid) or (seed_channel and name_key(v.get("channel")) == seed_channel):
                score = max(score, 3)
            score += min(len(title_words(v["title"]) & seed_words), 2)
            if score > 0:
                scored.append((-score, i, v))
        return [v for _, _, v in sorted(scored, key=lambda x: x[:2])]

    def _compute_because(self, count=3, per_group=12):
        """[{"seed": {id,title}, "videos": [...]}]: relacionados de lo último visto que tienen que ver (ver
        _rank_related), sin repetir vistos ni entre grupos. Prueba con más semillas por si alguna no da nada útil."""
        seeds = self._because_seeds(count + 2)
        used = {e["id"][3:] for e in self.store.history() if e["id"].startswith("yt:")}
        used |= {h["id"] for h in self.youtube.recent(HISTORY_MAX)} | {s["id"] for s in seeds}
        hidden = self._hidden_check()
        affinity = getattr(getattr(self, "account", None), "affinity", lambda: ({}, {}))()
        groups = []
        for seed in seeds:
            if len(groups) >= count:
                break
            try:
                related = self.youtube.related(seed["id"])
            except Exception:  # noqa: BLE001 - sin relacionados de este, sigue con los demás
                related = []
            videos = [v for v in self._rank_related(seed, related, affinity) if v["id"] not in used and not hidden(v)]
            videos = videos[:per_group]
            if len(videos) >= BECAUSE_MIN:
                used |= {v["id"] for v in videos}
                groups.append({"seed": seed, "videos": videos})
        return groups

    def yt_because(self):
        """«Porque viste…»: sirve lo ya calculado y, si está viejo o cambió lo último visto, lo recalcula
        en segundo plano (la primera vez puede tardar; mientras, sale vacío)."""
        seed_ids = [s["id"] for s in self._because_seeds()]
        with self._because_lock:
            cached = self._because
            stale = not cached or cached["seeds"] != seed_ids or time.time() - cached["at"] > BECAUSE_TTL
            if stale and not self._because_busy and seed_ids:
                self._because_busy = True

                def work():
                    try:
                        data = self._compute_because()
                        with self._because_lock:
                            self._because = {"at": time.time(), "seeds": seed_ids, "data": data}
                    except Exception as e:  # noqa: BLE001
                        say(f"⚠ YouTube: no se pudo calcular «porque viste» ({e})")
                    finally:
                        with self._because_lock:
                            self._because_busy = False
                threading.Thread(target=work, daemon=True).start()
            data = list(cached["data"]) if cached else []
        # Lo ya calculado puede traer videos de un canal que se ocultó después.
        hidden = self._hidden_check()
        groups = [{**g, "videos": [v for v in g["videos"] if not hidden(v)]} for g in data]
        return [g for g in groups if g["videos"]]

    def yt_home(self):
        """Todo el inicio de YouTube en una sola llamada."""
        acc = getattr(self, "account", None)

        def from_account(name, *args):
            try:
                return getattr(acc, name)(*args) if acc else []
            except Exception as e:  # noqa: BLE001
                say(f"⚠ YouTube: la cuenta no dio {name} ({e})")
                return []
        favorites = self._with_durations(self.lists.get(FAV)["videos"][:FAVORITES_SHOWN])
        data = {"continue": self.yt_continue(), "new": from_account("new_videos", 40) if acc else [],
                "because": self.yt_because(), "recent": self._with_durations(self.youtube.recent()),
                "playlists": self._my_playlists(), "favorites": favorites, "channels": from_account("channels")}
        # Si faltan duraciones que ya se están pidiendo, en cuántos segundos conviene volver a preguntar.
        data["filling"] = self._filling(data["continue"] + data["new"] + data["recent"])
        return data

    def yt_channel(self, ref):
        """Últimos videos de un canal, con si está anclado u oculto (también si YouTube no responde, para poder
        desanclar un canal que ya no existe)."""
        acc = getattr(self, "account", None)

        def flags(cid):
            return acc.channel_flags(cid) if acc else {"pinned": False, "hidden": False}
        try:
            data = self.youtube.channel(ref)
        except YouTubeError as e:
            return {"ok": False, "error": str(e), **flags(ref)}
        cid = data.get("id") if CHANNEL_ID.match(data.get("id") or "") else ref
        return {"ok": True, **data, **flags(cid), "filling": self._filling(data.get("videos"))}

    # ---------- canales ocultos y anclados ----------

    def _after_channel_change(self, cid):
        """La TV vuelve a leer sus datos y, si el canal vuelve a contar (anclado o visible otra vez) y no se ha
        revisado hace poco, se leen ya sus videos (sin esperar a la revisión de cada hora)."""
        self.tell_tv_to_refresh()
        acc = self.account
        if cid in {c["id"] for c in acc.channels()} and acc.needs_refresh(cid):
            threading.Thread(target=acc.refresh_channel, args=(cid,), daemon=True).start()

    def _channel_of(self, vid):
        """(channel_id, nombre) del canal de un video: de lo ya sabido o, si no, preguntándole a YouTube."""
        rec = self.youtube.known(vid) or self.youtube.cached_info(vid) or {}
        if not CHANNEL_ID.match(rec.get("channel_id") or ""):
            rec = self.youtube.resolve(vid)["info"]
        return rec.get("channel_id") or "", rec.get("channel") or ""

    def yt_channel_hide(self, cid, title="", video=""):
        """«Silenciar canal»: no sale en «Tus canales», en lo nuevo ni en las recomendaciones. Con video= (desde una
        recomendación) se busca de qué canal es."""
        if not cid and video:
            try:
                cid, found = self._channel_of(video)
            except (YouTubeError, OSError) as e:
                return {"ok": False, "error": f"No se pudo saber de qué canal es ({e})."}
            title = title or found
        try:
            self.account.hide_channel(cid, title)
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        say(f"⊘ Canal silenciado: {self.account.channel_title(cid)}")
        self.tell_tv_to_refresh()
        return {"ok": True, "id": cid, "title": self.account.channel_title(cid)}

    def yt_dismiss(self, vid, on=True):
        """«No me interesa»: el video no vuelve a recomendarse (on=False lo deshace)."""
        try:
            self.account.dismiss_video(vid, on)
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        self.tell_tv_to_refresh()
        return {"ok": True}

    def yt_channel_unhide(self, cid):
        self.account.unhide_channel(cid)
        self._after_channel_change(cid)
        return {"ok": True}

    def yt_channel_pin(self, cid, title="", on=True):
        try:
            pinned = self.account.pin_channel(cid, title, on)
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        self._after_channel_change(cid)
        return {"ok": True, "pinned": pinned}

    def _known_yt(self, vid):
        rec = self.youtube.known(vid)
        return rec if rec and rec.get("title") else None

    def _takeout_list(self, list_id, network=True):
        """Lista del Takeout con títulos (aunque sea privada), o None si no es del Takeout."""
        acc = getattr(self, "account", None)
        if not acc:
            return None
        return acc.playlist(list_id, public=lambda pid: self.youtube.playlist_videos(pid)["videos"],
                            known=self._known_yt, network=network)

    def yt_playlist(self, list_id):
        try:
            data = self._list_data(list_id)
            return {"ok": True, **data, "filling": self._filling(data.get("videos"))}
        except YouTubeError as e:
            return {"ok": False, "error": str(e)}

    def yt_playlist_play(self, list_id, shuffle=False, start=None):
        """Pone una lista en la tele: el primer video ya y el resto al frente de la fila de reproducción, en
        orden (o al azar). start = desde qué video (índice en la lista). Anota cuándo se escuchó."""
        try:
            data = self._list_data(list_id)
        except YouTubeError as e:
            return {"ok": False, "error": str(e)}
        videos = [v for v in data["videos"] if not v.get("private")]   # los privados no se pueden reproducir
        if start is not None:
            if not 0 <= start < len(data["videos"]):
                return {"ok": False, "error": "Ese video no está en la lista."}
            first = data["videos"][start]
            if shuffle:   # el elegido va primero y el resto al azar
                others = [v for v in videos if v["id"] != first["id"]]
                random.shuffle(others)
                videos = ([] if first.get("private") else [first]) + others
            else:
                videos = [v for v in data["videos"][start:] if not v.get("private")]
        elif shuffle:
            random.shuffle(videos)
        if not videos:
            return {"ok": False, "error": "Esa lista no tiene videos que se puedan reproducir."}
        result = self.yt_play(videos[0]["id"])
        if not result.get("ok"):
            return result
        # Al frente, en el mismo orden, sin sacar de la fila lo que ya estaba (tiene un tope).
        room = min(PLAYLIST_IN_QUEUE, MAX_ITEMS - len(self.queue.items()))
        added = videos[1:1 + max(room, 0)]
        for v in reversed(added):
            self.queue.add({"kind": "yt", "id": v["id"], "title": v["title"], "thumb": f"/yt/{v['id']}/thumb.jpg"},
                           front=True)
        if getattr(self, "account", None) and data.get("source") != "onetv":   # las de One TV ya saben cuándo cambiaron
            self.account.mark_played(list_id, data.get("title", ""), len(data["videos"]),
                                     f"/yt/{data['videos'][0]['id']}/thumb.jpg" if data["videos"] else "")
        self.tell_tv_to_refresh()
        say(f"▶ Lista en la TV: {data.get('title', '')} ({1 + len(added)} de {len(videos)} videos"
            f"{', al azar' if shuffle else ''})")
        return {"ok": True, "count": 1 + len(added), "total": len(videos)}

    def marks(self, item_id, fetch=True):
        """Marcas de «saltar este tramo» ({kind, start, end, label}), por inicio: solo la intro de las series.
        Los capítulos de YouTube NO son marcas de saltar: la tele y la web los muestran como marcadores en la
        barra de avance (salen de /api/yt/info). Nunca falla: sin datos, lista vacía."""
        out = []
        try:
            if (item_id or "").startswith("yt:"):
                out = []
            else:
                intros = getattr(self, "intros", None)
                if intros:
                    out = [dict(m) for m in intros.marks(item_id) or []]
        except Exception:  # noqa: BLE001 - las marcas son un extra: nunca rompen la reproducción
            out = []
        return sorted(out, key=lambda m: m.get("start", 0))

    def continue_watching(self, items):
        """«Seguir viendo» mezclado: biblioteca y YouTube juntos, lo más reciente primero. Una entrada por
        serie. [{kind:"item", id, p, t} | {kind:"yt", id, title, channel, thumb, p, duration, t}]"""
        out = [{"kind": "item", "id": e["id"], "p": e["p"], "t": e["t"]}
               for e in self.store.keep_watching(items, with_time=True)]
        for e in self.yt_continue():
            y = {"kind": "yt", "id": e["id"], "title": e["title"], "channel": e["channel"], "thumb": e["thumb"],
                 "p": e["p"], "duration": e["duration"], "t": e["t"]}
            if e.get("published"):   # cuándo se publicó (ver ytdurations)
                y["published"], y["published_approx"] = e["published"], bool(e.get("published_approx"))
            out.append(y)
        return sorted(out, key=lambda e: -e["t"])

    # ---------- biblioteca al día, sola ----------

    def _organize_now(self, first=False):
        """Ordena lo nuevo (biblioteca y descargas terminadas), pone al día la biblioteca, baja los pósters de lo
        nuevo y avisa a la TV. Una sola vuelta a la vez (la de cada minuto y la de las descargas)."""
        with self._organize_lock:
            actions = self.organizer.run()
            done = [a for a in actions if "dest" in a]
            for a in actions:   # otra versión de algo que ya tenemos: ¿trae el doblaje latino que falta?
                if a.get("have"):
                    self.dubbing.consider(a["src"], a["have"], a["how"])
            self.music.scan()   # la música nueva también aparece sola (leer las carpetas es barato)
            before = set(self.library.items)
            self.library.scan(force=bool(done))
            now = set(self.library.items)
            added, removed = now - before, before - now
            if done or added or first:
                self.artwork.fetch_all(self.artwork.jobs_for(self.library), log=say)
            if added:
                say(f"✓ {len(added)} videos nuevos en la biblioteca")
            if removed:
                say(f"– {len(removed)} videos ya no están en la biblioteca")
            if added or removed:
                self.tell_tv_to_refresh()

    def keep_library_fresh(self):
        """Tarea automática, cada minuto: ordena lo nuevo, detecta películas agregadas a mano y les baja póster y
        sinopsis; luego avisa a la tele."""
        time.sleep(30)
        first = True
        while True:
            try:
                self._organize_now(first)
                self.metadata.fetch_all(self.library, log=say)   # de a poco: sigue donde se quedó
                first = False
            except Exception as e:  # noqa: BLE001 - nunca debe tumbar el servidor
                say(f"⚠ Biblioteca: {e}")
            time.sleep(60)

    def watch_downloads(self):
        """Tarea automática, cada 10 s: si algo terminó de bajarse, entra a la biblioteca ya (sin esperar la vuelta
        de cada minuto). Mirar las Descargas es barato; lo demás solo se hace si hay algo nuevo."""
        time.sleep(40)
        while True:
            try:
                if self.organizer.pending_downloads():
                    self._organize_now()
            except Exception as e:  # noqa: BLE001 - nunca debe tumbar el servidor
                say(f"⚠ Descargas: {e}")
            time.sleep(DOWNLOADS_EVERY)

    def dub_added(self):
        """Se agregó un doblaje: la biblioteca lo muestra como pista más y la tele se actualiza."""
        self.library.scan(force=True)
        self.tell_tv_to_refresh()

    def info(self, key):
        """Sinopsis para la ficha (película, serie o episodio)."""
        return {"ok": True, "desc": self.metadata.desc(key)}

    # ---------- yt-dlp al día ----------

    def keep_ytdlp_fresh(self):
        """Tarea automática: instala yt-dlp la primera vez y lo actualiza cada 24 h."""
        while True:
            try:
                msg = update_ytdlp()
                if YTDLP.exists():
                    self.youtube.ytdlp = str(YTDLP)
                if msg:
                    say(msg)
            except Exception as e:  # noqa: BLE001 - nunca debe tumbar el servidor
                say(f"⚠ yt-dlp: no se pudo actualizar ({e})")
            time.sleep(YTDLP_EVERY)

    # ---------- subtítulos desde internet ----------

    def subs_search(self, item_id, lang):
        item = self.library.get(item_id)
        if not item:
            return {"ok": False, "error": "Ese video ya no está en la biblioteca."}
        if not self.subs.configured:
            return {"ok": False, "setup": True, "error": "Falta configurar OpenSubtitles (clave de API en config.json)."}
        try:
            return {"ok": True, "results": self.subs.search(item, lang or "spa")}
        except SubtitleError as e:
            return {"ok": False, "error": str(e)}

    def subs_download(self, item_id, file_id, os_lang):
        item = self.library.get(item_id)
        if not item:
            return {"ok": False, "error": "Ese video ya no está en la biblioteca."}
        try:
            data, remaining = self.subs.download(file_id)
            saved = save_next_to_video(item, data, os_lang)
        except (SubtitleError, OSError) as e:
            return {"ok": False, "error": str(e)}
        say(f"✓ Subtítulos descargados: {saved.name}")
        self.library.scan(force=True)
        if getattr(self, "subsync", None):
            self.subsync.notify()   # que se alinee con la voz ya, sin esperar la vuelta
        item = self.library.get(item_id)
        index = next((i for i, s in enumerate(item["subs"]) if s.get("file") == str(saved)), -1)
        return {"ok": True, "sub": index, "item": self.library.public_item(item), "remaining": remaining}

    def subs_auto(self, item_id, lang):
        """Para la tele: busca y baja el mejor sin preguntar (primero el hecho para tu misma copia)."""
        found = self.subs_search(item_id, lang)
        if not found["ok"]:
            return found
        if not found["results"]:
            return {"ok": False, "error": "No encontré subtítulos en ese idioma."}
        best = found["results"][0]
        result = self.subs_download(item_id, best["file_id"], best["lang"])
        if result["ok"]:
            result["label"] = best["lang_label"] + (" · sincronizado con tu copia" if best["match"] else "")
        return result

    def remember_tracks(self, item, audio, sub, device_id=None):
        """Lo que se elige una vez se vuelve la preferencia para las siguientes películas: la de ese aparato
        (si se dice cuál) o, como antes, la de toda la casa. Una pista original se guarda como «original»."""
        pub = self.library.public_item(item)
        prefs = {}
        if audio is not None and 0 <= audio < len(pub["audio"]) and len(pub["audio"]) > 1:
            track = pub["audio"][audio]
            prefs["audioLang"] = "original" if device_id and track.get("original") else track["lang"]
        if sub is not None and pub["subs"]:
            prefs["subLang"] = "off" if sub < 0 else pub["subs"][min(sub, len(pub["subs"]) - 1)]["lang"]
        if device_id:
            self.store.set_device_prefs(device_id, **prefs)
        else:
            self.store.set_prefs(**prefs)

    def control(self, cmd, device_id=None, **params):
        """Órdenes para lo que se está viendo: cmd = tracks (audio/sub) o seek (t)."""
        now = self.store.now_playing()
        if not self.roku or not now:
            return {"ok": False, "error": "No hay nada reproduciéndose en la TV."}
        try:
            self.roku.send(cmd=cmd, **{k: v for k, v in params.items() if v is not None})
        except OSError as e:
            return {"ok": False, "error": f"El Roku no respondió ({e})."}
        if cmd == "tracks":
            item = self.library.get(now["id"])
            if item:
                self.remember_tracks(item, params.get("audio"), params.get("sub"), device_id)
        with self._player_lock:
            self._player = (0.0, None)
        return {"ok": True}

    def _player_state(self):
        """Posición exacta según el Roku (se pregunta como mucho una vez por segundo)."""
        with self._player_lock:
            at, value = self._player
            if time.time() - at < 1.0:
                return value
            try:
                value = self.roku.player() if self.roku else None
            except OSError:
                value = None
            self._player = (time.time(), value)
            return value

    def playing(self):
        now = self.store.now_playing()
        if not now:
            return None
        if now["id"].startswith("track:"):   # música: título · artista, portada del álbum y anterior / siguiente
            t = self.music.track(now["id"][6:])
            if not t:
                return None
            live = self._player_state()
            state, position, duration = now["state"], now["p"], now["d"] or t.get("duration") or 0
            if live:
                if live[0] in ("close", "stop", ""):
                    return None
                state = {"play": "play", "pause": "pause"}.get(live[0], "buffer")
                position = live[1] if live[1] is not None else position
                duration = live[2] or duration
            song = now.get("song") or {}
            i, n = song.get("i"), song.get("n")
            return {"id": now["id"], "kind": "music", "title": f"{t['title']} · {t['artist']}", "name": t["title"],
                    "artist": t["artist"], "album": t["album"], "poster": f"/music/art/{t['album_id']}.jpg",
                    "state": state, "position": round(position, 1), "duration": round(duration, 1), "mark": None,
                    "audio": None, "sub": None, "audios": [], "subs": [],
                    "index": i, "count": n, "prev": i is not None and i > 0,
                    "next": i is not None and n is not None and i < n - 1}
        if now["id"].startswith("yt:"):   # YouTube: sin pistas que elegir
            vid = now["id"][3:]
            item = {"id": now["id"], "full_title": self.youtube.title_of(vid) or "YouTube", "duration": 0}
            pub = {"poster": f"/yt/{vid}/thumb.jpg", "audio": [], "subs": []}
        else:
            item = self.library.get(now["id"])
            if not item:
                return None
            pub = self.library.public_item(item)
        state, position, duration = now["state"], now["p"], now["d"] or item["duration"]
        live = self._player_state()
        if live:
            if live[0] in ("close", "stop", ""):
                return None
            state = {"play": "play", "pause": "pause"}.get(live[0], "buffer")
            position = live[1] if live[1] is not None else position
            duration = live[2] or duration
        return {"id": item["id"], "title": item["full_title"], "poster": pub["poster"], "state": state,
                "position": round(position, 1), "duration": round(duration, 1),
                "mark": active_mark(self.marks(item["id"], fetch=False), position),
                "audio": now["audio"], "sub": now["sub"],
                "audios": [a["label"] for a in pub["audio"]], "subs": [s["label"] for s in pub["subs"]]}

    def remote_key(self, key):
        allowed = {"Play", "Rev", "Fwd", "InstantReplay", "Back", "Home", "Select",
                   "Up", "Down", "Left", "Right", "Info"}
        if not self.roku or key not in allowed:
            return {"ok": False}
        try:
            self.roku.key(key)
            return {"ok": True}
        except OSError:
            return {"ok": False}

    def status(self):
        return {"roku": self.roku.ip if self.roku else None, "server": self.server_url,
                "items": len(self.library.items), "iphone": self.iphone_url, "playing": self.playing(),
                "queue": len(self.queue.items()), "dubbing": self.dubbing.current}

    def warm_up(self):
        items = list(self.library.items.values())
        for item in items:
            try:
                self.media.poster(item)
            except Exception:  # noqa: BLE001
                pass
        self.transcoder.warm_keyframes(items)
        self.artwork.fetch_all(self.artwork.jobs_for(self.library), log=say)


# ---------- servidor ----------

def run_server(background):
    global BACKGROUND
    BACKGROUND = background
    cfg = load_config()
    app = App(cfg)
    CACHE.mkdir(parents=True, exist_ok=True)
    encoders.detect(cfg.get("codificador"), log=say)   # con qué se convierte el video (en la Mac, su chip)
    app.transcoder = Transcoder(CACHE)
    atexit.register(app.transcoder.shutdown)
    # El mosaico lee YouTube y los canales en vivo por las rutas de este mismo servidor.
    app.mosaics = Mosaics(CACHE, f"http://127.0.0.1:{cfg['puerto']}", log=say)
    atexit.register(app.mosaics.shutdown)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

    say("Buscando tu Roku en la red…")
    if not app.connect_roku():
        say("⚠ No encontré el Roku (¿apagado o en otro Wi-Fi?). Sigo intentando cada minuto.")

    say("Revisando la biblioteca…")
    app.library.scan(force=True)
    for w in app.library.warnings:
        say(f"⚠ {w}")
    items = app.library.items.values()
    count = {m: sum(1 for it in items if it["mode"] == m) for m in ("direct", "copy", "full")}
    say(f"✓ {len(app.library.items)} videos: {count['direct']} directos, {count['copy']} con video original "
        f"y audio convertido, {count['full']} convertidos completos")

    try:
        httpd = serve(app, cfg["puerto"], cfg.get("escuchar") or "0.0.0.0")
    except OSError:
        if background:
            say(f"✗ El puerto {cfg['puerto']} está ocupado; reintento en 30 s.")
            time.sleep(30)
            sys.exit(1)
        sys.exit(f"✗ El puerto {cfg['puerto']} está ocupado. ¿Ya tienes {hostos.CINE} abierto en otra ventana?")
    app.iphone_url = tailscale_url(cfg["puerto"])
    threading.Thread(target=app.warm_up, daemon=True).start()
    threading.Thread(target=app.intros.watch, args=(app.library,), daemon=True).start()   # «Saltar intro»
    threading.Thread(target=app.subsync.watch, args=(app.library,), daemon=True).start()   # subtítulos a tiempo
    threading.Thread(target=app.watch_roku, daemon=True).start()
    threading.Thread(target=app.keep_ytdlp_fresh, daemon=True).start()
    threading.Thread(target=app.keep_library_fresh, daemon=True).start()
    threading.Thread(target=app.watch_downloads, daemon=True).start()
    threading.Thread(target=app.keep_account_fresh, daemon=True).start()
    threading.Thread(target=app.keep_avatars, daemon=True).start()
    app.offline.start()   # la cola de videos guardados sin conexión
    atexit.register(app.offline.stop)

    if background:
        say(f"✓ Sirviendo en {app.server_url or 'puerto ' + str(cfg['puerto'])}")
    else:
        ts = tailscale_url(cfg["puerto"])
        local = app.server_url or f"http://localhost:{cfg['puerto']}"
        lan = None if hostos.MAC or app.server_url else hostos.lan_url(cfg["puerto"])
        if lan:   # Linux sin el Roku todavía: la dirección para entrar desde otro aparato
            local += f"\n  Desde otro aparato:   {lan}"
        print(f"""
──────────────────────────────────────────────
  Listo. En la TV: abre la app «One TV».

  Desde la computadora: {local}""" +
              (f"\n  Desde el iPhone:      {ts}" if ts else "") + """

  Deja esta ventana abierta mientras ves algo.
  Para apagar: Ctrl+C
──────────────────────────────────────────────""", flush=True)
        if os.environ.get("CINE_NO_BROWSER") != "1":
            hostos.open_browser(f"http://localhost:{cfg['puerto']}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nApagando…")


# ---------- arranque automático (macOS: launchd; Linux: systemd del usuario, ver mac/linuxservice.py; Windows: el
# Programador de tareas, ver mac/windowsservice.py) ----------

def _launchctl(*args):
    return subprocess.run(["launchctl", *args], capture_output=True, text=True)


def service_installed():
    if hostos.WINDOWS:
        return windowsservice.installed()
    return SERVICE_PLIST.exists() if hostos.MAC else linuxservice.UNIT.exists()


def service_pid():
    if not hostos.MAC:
        return _service().pid()
    out = _launchctl("print", f"gui/{os.getuid()}/{SERVICE_LABEL}").stdout
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("pid = "):
            return int(line.split("=")[1])
    return None


def _same_tree(a, b):
    cmp = filecmp.dircmp(a, b, ignore=["__pycache__", ".DS_Store"])
    if cmp.left_only or cmp.right_only or cmp.diff_files or cmp.funny_files:
        return False
    _, mismatch, errors = filecmp.cmpfiles(a, b, cmp.common_files, shallow=False)
    return not mismatch and not errors and all(_same_tree(a / d, b / d) for d in cmp.common_dirs)


def sync_service_files():
    """Copia el programa a ~/Library/Application Support (macOS no deja a los servicios leer Documentos); en Linux, a
    ~/.local/share/cine-roku (así el servicio corre la versión que se probó con ./cine, aunque cambies el repo)."""
    if not CONFIG.exists():
        sys.exit(f"✗ Todavía no hay config.json. Corre  {hostos.CINE} configurar  para crearlo.")
    changed = False
    SERVICE_HOME.mkdir(parents=True, exist_ok=True)
    for sub in ("mac", "roku"):
        src, dst = PROJECT / sub, SERVICE_HOME / sub
        if not dst.exists() or not _same_tree(src, dst):
            shutil.rmtree(dst, ignore_errors=True)
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", ".DS_Store"))
            changed = True
    if not (SERVICE_HOME / "config.json").exists() or not filecmp.cmp(CONFIG, SERVICE_HOME / "config.json", shallow=False):
        shutil.copy2(CONFIG, SERVICE_HOME / "config.json")
        changed = True
    return changed


def write_plist():
    if hostos.WINDOWS:   # la tarea del Programador de tareas (con el Python que corre esto: «python3» puede no existir)
        return windowsservice.write(sys.executable, SERVICE_HOME, SERVICE_LOG)
    python = shutil.which("python3") or sys.executable
    if not hostos.MAC:   # Linux: la unidad de systemd
        return linuxservice.write(python, SERVICE_HOME / "mac" / "cine.py", SERVICE_HOME, SERVICE_LOG)
    SERVICE_PLIST.parent.mkdir(parents=True, exist_ok=True)
    SERVICE_LOG.parent.mkdir(parents=True, exist_ok=True)
    plist = {
        "Label": SERVICE_LABEL,
        "ProgramArguments": [python, str(SERVICE_HOME / "mac" / "cine.py"), "servir"],
        "WorkingDirectory": str(SERVICE_HOME),
        "EnvironmentVariables": {"PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
                                 "PYTHONUNBUFFERED": "1"},
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 30,
        "ProcessType": "Interactive",  # sin frenos de energía: convierte video en tiempo real
        "StandardOutPath": str(SERVICE_LOG),
        "StandardErrorPath": str(SERVICE_LOG),
    }
    new = plistlib.dumps(plist)
    if SERVICE_PLIST.exists() and SERVICE_PLIST.read_bytes() == new:
        return False
    SERVICE_PLIST.write_bytes(new)
    return True


DAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
          "noviembre", "diciembre"]


def day_label(t):
    """«Hoy», «Ayer» o «lunes 21 de septiembre» (con el año si no es este)."""
    d = datetime.fromtimestamp(t).date()
    today = datetime.now().date()
    if d == today:
        return "Hoy"
    if (today - d).days == 1:
        return "Ayer"
    text = f"{DAYS[d.weekday()]} {d.day} de {MONTHS[d.month - 1]}"
    return (text if d.year == today.year else f"{text} de {d.year}").capitalize()


def when_label(t):
    """Corto, para una tarjeta: «hoy 20:14», «ayer 21:02», «21 sep»."""
    dt = datetime.fromtimestamp(t)
    day = day_label(t)
    if day in ("Hoy", "Ayer"):
        return f"{day.lower()} {dt:%H:%M}"
    return f"{dt.day} {MONTHS[dt.month - 1][:3]}" + ("" if dt.year == datetime.now().year else f" {dt.year}")


def _ytdlp_version():
    try:
        return subprocess.run([str(YTDLP), "--version"], capture_output=True, text=True, timeout=120,
                              stdin=subprocess.DEVNULL).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def update_ytdlp():
    """Crea el entorno la primera vez (o si se rompió) e instala o actualiza yt-dlp con pip."""
    before = _ytdlp_version() if YTDLP.exists() else ""
    if not before:
        shutil.rmtree(YTDLP_ENV, ignore_errors=True)
        subprocess.run([sys.executable, "-m", "venv", str(YTDLP_ENV)], check=True, capture_output=True, timeout=300)
    r = subprocess.run([str(hostos.venv_bin(YTDLP_ENV, "pip")), "install", "-q", "-U", "yt-dlp[default]"],
                       capture_output=True, text=True, timeout=600, stdin=subprocess.DEVNULL)
    after = _ytdlp_version()
    if not after:
        raise RuntimeError((r.stderr or "pip falló").strip().splitlines()[-1][:160])
    if not before:
        return f"✓ yt-dlp {after} listo para YouTube (se actualiza solo cada 24 h)"
    return f"✓ yt-dlp actualizado: {before} → {after}" if after != before else None


def server_answers(port, timeout=1.5):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=timeout) as r:
            return json.loads(r.read())
    except (OSError, ValueError):
        return None


def wait_for_server(port, seconds=40):
    end = time.time() + seconds
    while time.time() < end:
        st = server_answers(port)
        if st:
            return st
        time.sleep(1)
    return None


def install_service(cfg):
    if server_answers(cfg["puerto"]) and not service_pid():
        sys.exit(f"✗ Ya hay un {hostos.CINE} abierto en otra ventana. Ciérralo con Ctrl+C y vuelve a intentar.")
    if hostos.WINDOWS:
        return install_windows_service()
    if not hostos.MAC:
        return install_linux_service()
    sync_service_files()
    write_plist()
    _launchctl("bootout", f"gui/{os.getuid()}/{SERVICE_LABEL}")
    time.sleep(1)
    _launchctl("enable", f"gui/{os.getuid()}/{SERVICE_LABEL}")
    r = _launchctl("bootstrap", f"gui/{os.getuid()}", str(SERVICE_PLIST))
    if r.returncode != 0:
        sys.exit(f"✗ macOS no aceptó el servicio: {r.stderr.strip()}")


def _service():
    """El arranque automático de este sistema fuera de macOS (los dos tienen problem, start, restart, pid y remove)."""
    return windowsservice if hostos.WINDOWS else linuxservice


def install_windows_service():
    problem = windowsservice.problem()
    if problem:
        sys.exit(f"✗ {problem}")
    sync_service_files()
    write_plist()
    error = windowsservice.start()
    if error:
        sys.exit(f"✗ Windows no aceptó la tarea de arranque automático: {error}")


def install_linux_service():
    problem = linuxservice.problem()
    if problem:
        sys.exit(f"✗ {problem}")
    sync_service_files()
    write_plist()
    error = linuxservice.start()
    if error:
        sys.exit(f"✗ systemd no aceptó el servicio: {error}")
    if not linuxservice.lingering():
        print("Para que arranque al encender la computadora aunque nadie inicie sesión, systemd tiene que mantener tus")
        print("servicios en marcha siempre. Lo activo ahora (puede pedirte tu contraseña):", flush=True)
        if linuxservice.enable_linger():
            print("✓ Activado.")
        else:
            print(f"⚠ No se pudo. Hazlo con este comando:  {linuxservice.linger_command()}")
            print("  Mientras tanto, el servidor arranca solo cuando inicias sesión.\n")


def update_service(cfg):
    """./cine con el autoarranque puesto: copia cambios, reinicia si hizo falta y muestra dónde entrar."""
    problem = "" if hostos.MAC else _service().problem()
    if problem:
        sys.exit(f"✗ {problem}")
    files_changed = sync_service_files()
    plist_changed = write_plist()
    if not hostos.MAC:
        if plist_changed or not service_pid():
            say("Arrancando el servidor…")
            _service().start()
        elif files_changed:
            say("Aplicando cambios y reiniciando el servidor…")
            _service().restart()
            time.sleep(2)
        return
    if plist_changed or not service_pid():
        say("Arrancando el servidor…")
        _launchctl("bootout", f"gui/{os.getuid()}/{SERVICE_LABEL}")
        time.sleep(1)
        _launchctl("enable", f"gui/{os.getuid()}/{SERVICE_LABEL}")
        _launchctl("bootstrap", f"gui/{os.getuid()}", str(SERVICE_PLIST))
    elif files_changed:
        say("Aplicando cambios y reiniciando el servidor…")
        _launchctl("kickstart", "-k", f"gui/{os.getuid()}/{SERVICE_LABEL}")
        time.sleep(2)
    if menubar_outdated():
        install_menubar()


def print_status(cfg, st=None):
    st = st or server_answers(cfg["puerto"])
    pid = service_pid()
    local = f"http://localhost:{cfg['puerto']}"
    auto = service_installed()
    if st:
        how = " (arranca solo con la computadora)" if auto and pid else " (en una ventana de Terminal)"
        if auto and pid and not hostos.MAC and (hostos.WINDOWS or not linuxservice.lingering()):
            how = " (arranca solo cuando inicias sesión)"
        print(f"✓ Servidor funcionando" + how)
        print(f"  {st['items']} videos · Roku: {st['roku'] or 'no encontrado todavía'}")
        print(f"\n  Desde la computadora: {st['server'] or local}")
        lan = None if hostos.MAC or st["server"] else hostos.lan_url(cfg["puerto"])
        if lan:   # Linux sin el Roku todavía (un servidor sin pantalla): la dirección para entrar desde otro aparato
            print(f"  Desde otro aparato:   {lan}")
        ts = tailscale_url(cfg["puerto"])
        print(f"  Desde el iPhone:      {ts}" if ts else f"  Desde el iPhone:      corre {hostos.CINE} tailscale")
    else:
        print("✗ El servidor no está corriendo." + (" Revisa el registro: " + str(SERVICE_LOG) if auto else ""))
    if auto:
        print(f"\n  Registro: {SERVICE_LOG}")
    if auto and not hostos.MAC and not hostos.WINDOWS and not linuxservice.lingering():
        print("  Arranca solo cuando inicias sesión. Para que arranque al encender la computadora:\n"
              f"    {linuxservice.linger_command()}")


# ---------- ícono en la barra de menú ----------

def _app_icon(res_dir):
    """Ícono de la app a partir de menubar/AppIcon-1024.png (el mismo dibujo que el del Roku y el iPhone),
    con las herramientas que ya trae macOS (sips e iconutil)."""
    source = PROJECT / "menubar" / "AppIcon-1024.png"
    if not source.exists():
        return
    iconset = res_dir / "AppIcon.iconset"
    iconset.mkdir()
    for size in (16, 32, 128, 256, 512):
        for scale, name in ((1, f"icon_{size}x{size}.png"), (2, f"icon_{size}x{size}@2x.png")):
            px = str(size * scale)
            subprocess.run(["sips", "-z", px, px, str(source), "--out", str(iconset / name)], capture_output=True)
    subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(res_dir / "AppIcon.icns")], capture_output=True)
    shutil.rmtree(iconset, ignore_errors=True)


def install_menubar():
    """Compila la app de la barra (SwiftUI), la deja en ~/Applications y la hace arrancar al iniciar sesión."""
    sources = sorted(str(p) for p in (PROJECT / "menubar").glob("*.swift"))
    build = CACHE / "barra-build"
    shutil.rmtree(build, ignore_errors=True)
    app = build / BARRA_APP.name
    (app / "Contents" / "MacOS").mkdir(parents=True)
    (app / "Contents" / "Resources").mkdir()
    say("Compilando el ícono de la barra…")
    r = subprocess.run(["xcrun", "swiftc", "-parse-as-library", "-O", "-swift-version", "6",
                        "-target", "arm64-apple-macos14.0", "-o", str(app / "Contents" / "MacOS" / "CineEnCasa"),
                        *sources], capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("✗ No compiló la app de la barra:\n" + r.stderr[-3000:])
    (app / "Contents" / "Info.plist").write_bytes(plistlib.dumps({
        "CFBundleIdentifier": BARRA_LABEL, "CFBundleName": "One TV", "CFBundleDisplayName": "One TV",
        "CFBundleExecutable": "CineEnCasa", "CFBundlePackageType": "APPL", "CFBundleIconFile": "AppIcon",
        "CFBundleShortVersionString": "1.0", "CFBundleVersion": "1", "LSMinimumSystemVersion": "14.0",
        "LSUIElement": True,  # solo en la barra: sin ícono en el Dock
        "NSAppTransportSecurity": {"NSAllowsLocalNetworking": True},
    }))
    _app_icon(app / "Contents" / "Resources")
    subprocess.run(["codesign", "--force", "--sign", "-", str(app)], capture_output=True)

    _launchctl("bootout", f"gui/{os.getuid()}/{BARRA_LABEL}")
    shutil.rmtree(BARRA_APP, ignore_errors=True)
    if BARRA_APP_OLD.exists():   # migración: la app con el nombre anterior no se deja a la vista en Spotlight
        shutil.rmtree(BARRA_APP_OLD, ignore_errors=True)
        say(f"– Se borró la app anterior: {BARRA_APP_OLD}")
    BARRA_APP.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(app), BARRA_APP)
    BARRA_PLIST.write_bytes(plistlib.dumps({
        "Label": BARRA_LABEL,
        "ProgramArguments": [str(BARRA_APP / "Contents" / "MacOS" / "CineEnCasa")],
        "RunAtLoad": True,
        "LimitLoadToSessionType": "Aqua",
        "ProcessType": "Interactive",
    }))
    time.sleep(1)
    _launchctl("bootstrap", f"gui/{os.getuid()}", str(BARRA_PLIST))
    say("✓ Ícono en la barra de menú (arriba a la derecha). Aparece solo cada vez que inicias sesión.")


def menubar_outdated():
    binary = BARRA_APP / "Contents" / "MacOS" / "CineEnCasa"
    if not BARRA_PLIST.exists():
        return False
    if not binary.exists():
        return True
    built = binary.stat().st_mtime
    return any(p.stat().st_mtime > built for p in [*(PROJECT / "menubar").glob("*.swift"),
                                                    *(PROJECT / "menubar").glob("*.png")])


# ---------- Tailscale (https para el iPhone) ----------

def tailscale_cli():
    for c in (*hostos.TAILSCALE_PATHS, shutil.which("tailscale")):
        if c and Path(c).exists():
            return c
    return None


def tailscale_url(port):
    cli = tailscale_cli()
    if not cli:
        return None
    # Sin TERM (como corre el servicio) la app de Tailscale intenta abrir su ventana en vez de responder.
    env = {**os.environ, "TERM": os.environ.get("TERM") or "dumb"}
    try:
        out = subprocess.run([cli, "serve", "status", "--json"], capture_output=True, text=True, timeout=5,
                             env=env).stdout
        web = json.loads(out or "{}").get("Web", {})
    except (subprocess.TimeoutExpired, ValueError, OSError):
        return None
    for hostport, conf in web.items():
        for handler in (conf.get("Handlers") or {}).values():
            if handler.get("Proxy", "").rstrip("/").endswith(f":{port}"):
                host, _, p = hostport.rpartition(":")
                return f"https://{host}" if p == "443" else f"https://{hostport}"
    return None


def setup_tailscale(cfg):
    cli = tailscale_cli()
    if not cli:
        sys.exit("✗ No encontré Tailscale en esta computadora.")
    url = tailscale_url(cfg["puerto"])
    if not url:
        r = subprocess.run([cli, "serve", "--bg", f"--https={TAILSCALE_PORT}", f"http://127.0.0.1:{cfg['puerto']}"],
                           capture_output=True, text=True, timeout=30)
        url = tailscale_url(cfg["puerto"])
        if not url:
            hint = "" if hostos.MAC or hostos.WINDOWS else ("\n  Si dice que no tienes permiso, dáselo a tu usuario una vez con:  "
                                          "sudo tailscale set --operator=$USER")
            sys.exit("✗ Tailscale no aceptó la configuración:\n" + (r.stdout + r.stderr).strip() + hint)
    print(f"✓ Página disponible en tu red Tailscale (solo tus dispositivos):\n  {url}")
    print("  En el iPhone: ábrela en Safari → Compartir → «Añadir a pantalla de inicio».")


# ---------- catálogo ----------

def print_catalog(app):
    app.library.scan(force=True)
    data = app.library.api()
    items = data["items"]
    how = {"direct": "directo", "copy": "video original, convierte audio", "full": "convierte todo"}
    for row in data["rows"][1:]:
        print(f"\n{row['title']}")
        for entry in row["items"]:
            it = items[entry["id"]]
            reason = f" ({it['convert_reason']})" if it["convert_reason"] else ""
            print(f"  · {entry['label']:<50} {how[it['mode']]}{reason}")
    count = {m: sum(1 for it in items.values() if it["mode"] == m) for m in how}
    print(f"\n{len(items)} videos: {count['direct']} directos, {count['copy']} con video original y audio "
          f"convertido, {count['full']} convertidos completos.")


def ask(question, default=""):
    """Pregunta en la Terminal. Enter deja el valor sugerido. Si no hay quien conteste, sale con un aviso."""
    suffix = f" [{default}]" if default else ""
    try:
        answer = input(f"{question}{suffix}: ").strip()
    except EOFError:
        sys.exit(f"\n✗ No pude leer la respuesta. Corre  {hostos.CINE} configurar  desde una Terminal.")
    return answer or default


def configure_first_time():
    """Primer arranque guiado: pregunta lo mínimo y crea config.json (o lo actualiza, sin perder lo demás)."""
    current = {}
    if CONFIG.exists():
        try:
            current = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError:
            current = {}
        print("Ya existe un config.json. Vamos a repasarlo: Enter deja lo que ya tiene.\n")
    else:
        print("Te damos la bienvenida a One TV. Todavía no hay configuración: vamos a crearla (1 minuto).")
        print("Solo son cuatro preguntas; lo demás se puede cambiar después en config.json.\n")

    if not shutil.which("ffmpeg"):
        print("⚠ No encuentro ffmpeg, que hace falta para pasar los videos a la TV.")
        print(f"  Instálalo con:  {hostos.install_hint('ffmpeg')}\n")

    folders = current.get("carpetas") or []
    print("1) ¿En qué carpeta de la computadora van a estar tus películas y series?")
    print("   Si no existe, la creo." + (" Mejor fuera de Descargas, Documentos y Escritorio (macOS las protege)."
                                           if hostos.MAC else ""))
    while True:
        folder = ask("   Carpeta", folders[0] if folders else hostos.default_library())
        path = Path(folder).expanduser()
        try:
            path.mkdir(parents=True, exist_ok=True)
            break
        except OSError as e:
            print(f"   ✗ No pude crear {path}: {e.strerror or e}. Prueba con otra.")
    protected = [Path.home() / d for d in ("Downloads", "Documents", "Desktop")]
    if hostos.MAC and any(path == p or p in path.parents for p in protected):
        print("   ⚠ macOS no deja al servicio leer esa carpeta en segundo plano; mejor usa una dentro de ~/Movies.")
    print(f"   ✓ Carpeta lista: {path}\n")

    print("2) Contraseña del modo desarrollador del Roku (la que pusiste al activarlo; ver docs/INSTALAR.md, paso 6).")
    print("   Sin ella no puedo instalar la app en el Roku. Enter para ponerla más tarde en config.json.")
    password = ask("   Contraseña", current.get("roku_password", ""))
    if password == "contraseña-del-modo-desarrollador":
        password = ""
    print()

    print("3) IP del Roku (algo como 192.168.1.50). Enter para que la busque sola, que es lo normal.")
    roku_ip = ask("   IP del Roku", current.get("roku_ip", ""))
    if not roku_ip:
        print("   Buscando el Roku en tu red…")
        found = discover()
        print(f"   ✓ Encontré un Roku en {found}." if found else
              "   · No lo encontré ahora (TV apagada o sin Wi-Fi). Se seguirá buscando de forma automática.")
    print()

    music_now = current.get("musica")
    suggested = hostos.tilde(music_now[0] if music_now else (default_roots() or [""])[0])
    print("4) ¿Dónde está tu música (opcional)? Artistas, álbumes y listas .m3u8, con sus portadas.")
    print("   Enter acepta la sugerencia; «no» para no usar música.")
    music = ask("   Carpeta de música", suggested or "no")
    if music.strip().lower() in ("no", "-", "ninguna"):
        music_roots = []
        print(f"   · Sin música (se puede agregar después con  {hostos.CINE} configurar).")
    elif Path(music).expanduser().is_dir():
        music_roots = [music]
        print(f"   ✓ La sección Música va a leer {Path(music).expanduser()}")
    else:
        music_roots = [music]
        print(f"   · {Path(music).expanduser()} no existe todavía: en cuanto pongas música ahí, aparece sola.")
    print()

    cfg = dict(current)
    cfg.update({"carpetas": [folder if folder.startswith("~") else str(path)],
                "puerto": current.get("puerto", 8765), "roku_ip": roku_ip, "roku_password": password,
                "musica": music_roots})
    cfg.setdefault("titulos", {})
    cfg.setdefault("opensubtitles", {"api_key": "", "usuario": "", "clave": ""})
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n")
    CONFIG.chmod(0o600)   # tiene contraseñas: solo para ti
    print(f"✓ Guardé la configuración en {CONFIG}")
    print(f"  Pon tus películas y series en {path} (o descárgalas con Transmission: se ordenan solas).")
    return cfg


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "iniciar"
    if cmd == "configurar":
        configure_first_time()
        print(f"\nSiguiente paso: corre  {hostos.CINE}  para arrancar (guía completa en {hostos.guide()}).")
        return
    if cmd != "servir" and not CONFIG.exists() and cmd in ("iniciar", "catalogo", "tailscale", "autoarranque", "instalar"):
        configure_first_time()   # primer arranque: sin config.json no se puede hacer nada más
        print()
    cfg = load_config()

    if cmd == "servir":  # lo usa launchd
        return run_server(background=True)
    if cmd == "catalogo":
        return print_catalog(App(cfg))
    if cmd == "tailscale":
        return setup_tailscale(cfg)
    if cmd in ("barra", "quitar-barra") and not hostos.MAC:
        return print(f"· El ícono de la barra de menú es solo para macOS: en {hostos.SYSTEM} no aplica "
                     f"(usa {hostos.CINE} estado).")
    if cmd == "barra":
        return install_menubar()
    if cmd == "quitar-barra":
        _launchctl("bootout", f"gui/{os.getuid()}/{BARRA_LABEL}")
        BARRA_PLIST.unlink(missing_ok=True)
        shutil.rmtree(BARRA_APP, ignore_errors=True)
        shutil.rmtree(BARRA_APP_OLD, ignore_errors=True)
        return print("✓ Ícono quitado de la barra de menú.")
    if cmd == "estado":
        return print_status(cfg)
    if cmd == "autoarranque":
        install_service(cfg)
        when = ("se encienda la computadora" if not hostos.MAC and not hostos.WINDOWS and linuxservice.lingering()
                else "inicies sesión en la computadora")
        print(f"✓ Listo: el servidor queda corriendo y arrancará solo cada vez que {when}.")
        print("  Esperando a que arranque…\n")
        return print_status(cfg, wait_for_server(cfg["puerto"]))
    if cmd == "quitar-autoarranque":
        if hostos.MAC:
            _launchctl("bootout", f"gui/{os.getuid()}/{SERVICE_LABEL}")
            SERVICE_PLIST.unlink(missing_ok=True)
        else:
            _service().remove()
        for sub in ("mac", "roku"):  # "datos" (progreso) se conserva
            shutil.rmtree(SERVICE_HOME / sub, ignore_errors=True)
        (SERVICE_HOME / "config.json").unlink(missing_ok=True)
        return print(f"✓ Ya no arranca solo. Para usarlo, abre {hostos.CINE} cuando quieras ver algo.")
    if cmd == "instalar":
        app = App(cfg)
        if not app.connect_roku(force=True):
            sys.exit("✗ No encontré el Roku en la red.")
        return
    if cmd != "iniciar":
        sys.exit(__doc__)

    if service_installed():
        update_service(cfg)
        print_status(cfg, wait_for_server(cfg["puerto"]))
        if os.environ.get("CINE_NO_BROWSER") != "1":
            hostos.open_browser(f"http://localhost:{cfg['puerto']}")
        return
    run_server(background=False)


if __name__ == "__main__":
    if hostos.WINDOWS and not sys.flags.utf8_mode:   # textos en UTF-8, como en macOS y Linux (ver hostos.rerun_utf8)
        sys.exit(hostos.rerun_utf8())
    main()
