"""Lo que cambia según el sistema de la computadora que hace de servidor: macOS, Linux (Ubuntu) o Windows.

- Carpetas: en macOS, las de siempre (~/Library/Caches, ~/Library/Application Support, ~/Library/Logs). En Linux,
  las de XDG, como cualquier programa: ~/.cache/cine-roku, ~/.local/share/cine-roku y ~/.local/state/cine-roku. En
  Windows, todo en %LOCALAPPDATA%\\cine-roku (con «Cache» y «Logs» dentro).
- Carpetas del usuario (Descargas, Videos, Música): en macOS ~/Downloads, ~/Movies y ~/Music; en Linux las que diga
  ~/.config/user-dirs.dirs (en un escritorio en español: ~/Descargas, ~/Vídeos, ~/Música); en Windows las que diga
  Windows (pueden estar en otro disco o en OneDrive; ver mac/winapi.py).
- Abrir la página en el navegador, dónde está Chrome (para «En vivo») y Tailscale, y cómo no dejar que la computadora
  se duerma.
- Lo que en Windows no existe: «nice», SIGSTOP/SIGCONT, pkill, la carpeta «bin» de los entornos aparte (allá es
  «Scripts») y borrar o reemplazar un archivo que otro tiene abierto.

En macOS todo queda igual que antes de este módulo.
"""

import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import webbrowser
from pathlib import Path

import winapi

MAC = sys.platform == "darwin"
WINDOWS = sys.platform == "win32"
LINUX = sys.platform.startswith("linux")
APP = "cine-roku"
SYSTEM = "macOS" if MAC else "Windows" if WINDOWS else "Linux"
CINE = "cine" if WINDOWS else "./cine"   # cómo se escribe el comando en la ventana de comandos de este sistema


def _xdg(var, default):
    """Una carpeta de XDG: la de la variable si es una ruta completa; si no, la de siempre dentro de la carpeta personal."""
    value = os.environ.get(var, "")
    return Path(value) if os.path.isabs(value) else Path.home() / default


def _local_appdata():
    """%LOCALAPPDATA% (C:\\Users\\<tú>\\AppData\\Local): lo de esta computadora que no viaja con la cuenta."""
    value = os.environ.get("LOCALAPPDATA", "")
    return Path(value) if os.path.isabs(value) else Path.home() / "AppData" / "Local"


if MAC:
    CACHE = Path.home() / "Library" / "Caches" / APP
    SERVICE_HOME = Path.home() / "Library" / "Application Support" / APP
    LOG = Path.home() / "Library" / "Logs" / f"{APP}.log"
elif WINDOWS:
    SERVICE_HOME = _local_appdata() / APP
    CACHE = SERVICE_HOME / "Cache"
    LOG = SERVICE_HOME / "Logs" / f"{APP}.log"
else:
    CACHE = _xdg("XDG_CACHE_HOME", ".cache") / APP
    SERVICE_HOME = _xdg("XDG_DATA_HOME", ".local/share") / APP
    LOG = _xdg("XDG_STATE_HOME", ".local/state") / APP / f"{APP}.log"
CONFIG_HOME = _xdg("XDG_CONFIG_HOME", ".config")

MAC_DIRS = {"DOWNLOAD": "Downloads", "VIDEOS": "Movies", "MUSIC": "Music"}
LINUX_DIRS = {"DOWNLOAD": "Downloads", "VIDEOS": "Videos", "MUSIC": "Music"}


def user_dir(kind):
    """Carpeta del usuario: «DOWNLOAD», «VIDEOS» o «MUSIC» (ver arriba)."""
    if MAC:
        return Path.home() / MAC_DIRS[kind]
    if WINDOWS:
        return winapi.user_folder(kind) or Path.home() / LINUX_DIRS[kind]
    try:
        text = (CONFIG_HOME / "user-dirs.dirs").read_text(errors="replace")
    except OSError:
        text = ""
    m = re.search(rf'^\s*XDG_{kind}_DIR="(.*)"\s*$', text, re.M)
    if m:
        value = m.group(1).replace("$HOME", str(Path.home())).replace('\\"', '"')
        if os.path.isabs(value) and Path(value) != Path.home():   # «$HOME» a secas quiere decir que no hay
            return Path(value)
    return Path.home() / LINUX_DIRS[kind]


def tilde(path):
    """La ruta con «~» en vez de la carpeta personal (para sugerirla en una pregunta). En Windows, la ruta completa:
    allá nadie escribe «~»."""
    path, home = str(path), str(Path.home())
    if WINDOWS:
        return path
    return "~" + path[len(home):] if path == home or path.startswith(home + os.sep) else path


def default_library():
    """Carpeta de películas y series que se sugiere: ~/Movies/Biblioteca en macOS, ~/Vídeos/Biblioteca (o
    ~/Videos/Biblioteca) en Linux, la carpeta Videos del usuario y «Biblioteca» dentro en Windows."""
    return tilde(user_dir("VIDEOS") / "Biblioteca")


def lan_url(port):
    """La dirección de esta computadora en la red de la casa (para abrir la página desde otro aparato), o None. No manda
    nada: solo le pregunta al sistema por qué conexión saldría (192.0.2.1 es una dirección de ejemplo, no existe)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 9))
        ip = s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()
    return None if ip.startswith("127.") else f"http://{ip}:{port}"


def open_browser(url):
    """Abre la página en el navegador de esta computadora. En Linux sin pantalla (un servidor, por SSH) no hace nada:
    ahí el navegador de texto se quedaría con la Terminal."""
    if MAC or WINDOWS:   # en Windows, el navegador que el usuario tenga elegido
        return webbrowser.open(url)
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return False
    opener = shutil.which("xdg-open")
    if not opener:
        return False
    try:
        subprocess.Popen([opener, url], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        return False
    return True


def _windows_programs(*relative):
    """Dónde puede estar un programa de Windows: en «Archivos de programa» (las dos) o instalado solo para el usuario."""
    bases = [os.environ.get(v, "") for v in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA")]
    return [str(Path(b, *r.split("/"))) for r in relative for b in bases if b]


# Chrome (o Brave, o Chromium) sin ventana, para encontrar el video de una página «En vivo» (mac/live.py). En
# Windows también sirve Edge, que siempre está.
if MAC:
    CHROME_PATHS = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
                    "/Applications/Chromium.app/Contents/MacOS/Chromium"]
elif WINDOWS:
    CHROME_PATHS = _windows_programs("Google/Chrome/Application/chrome.exe",
                                     "BraveSoftware/Brave-Browser/Application/brave.exe",
                                     "Microsoft/Edge/Application/msedge.exe", "Chromium/Application/chrome.exe")
else:
    CHROME_PATHS = ["/usr/bin/google-chrome-stable", "/usr/bin/google-chrome", "/opt/google/chrome/chrome",
                    "/usr/bin/brave-browser", "/opt/brave.com/brave/brave", "/usr/bin/chromium",
                    "/usr/bin/chromium-browser", "/snap/bin/chromium"]


def chrome_profile_parent(chrome):
    """Dónde crear el perfil temporal de Chrome: None = la carpeta temporal de siempre. El Chromium de Ubuntu viene
    como «snap», que tiene su propia carpeta temporal y no ve la nuestra: su perfil va en ~/snap/chromium/common."""
    if MAC or WINDOWS or not chrome:
        return None
    snap = chrome.startswith("/snap/")
    if not snap:
        try:   # /usr/bin/chromium-browser de Ubuntu es un guion que abre el snap
            with open(chrome, "rb") as f:
                head = f.read(4096)
            snap = head.startswith(b"#!") and b"/snap/" in head
        except OSError:
            return None
    if not snap:
        return None
    parent = Path.home() / "snap" / "chromium" / "common"
    try:
        parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    return str(parent)


def keep_awake_command(seconds):
    """Comando que impide que la computadora se duerma durante esos segundos mientras se ve algo, o None.
    macOS: caffeinate. Linux: systemd-inhibit, que Ubuntu permite a ./cine abierto en una ventana de la propia
    computadora pero no al servicio de arranque automático (su política lo niega; server.KeepAwake deja de intentarlo).
    En un servidor no hace falta: no se suspende solo. En Windows no hay comando: lo hace winapi.KeepAwake."""
    if WINDOWS:
        return None
    if MAC:
        return ["caffeinate", "-i", "-t", str(seconds)] if shutil.which("caffeinate") else None
    if shutil.which("systemd-inhibit"):
        return ["systemd-inhibit", "--what=sleep:idle", "--who=One TV", "--why=Se está viendo algo en la TV",
                "--mode=block", "sleep", str(seconds)]
    return None


WINGET = {"ffmpeg": "Gyan.FFmpeg", "python3": "Python.Python.3.12"}   # su nombre en winget (Windows)


def install_hint(package):
    """Cómo instalar un programa que falta, en una línea."""
    if MAC:
        return f"brew install {package}   (si no tienes Homebrew: https://brew.sh)"
    if WINDOWS:
        return f"winget install -e --id {WINGET.get(package, package)}   (y vuelve a abrir la ventana)"
    if shutil.which("apt-get"):
        return f"sudo apt install -y {package}"
    return f"instala «{package}» con el instalador de programas de tu sistema"


def guide():
    """La guía de instalación de este sistema."""
    return "docs/INSTALAR.md" if MAC else "docs/INSTALAR-WINDOWS.md" if WINDOWS else "docs/INSTALAR-UBUNTU.md"


# Tailscale (https para el iPhone fuera de casa): dónde está su programa de línea de comandos, además del PATH.
if MAC:
    TAILSCALE_PATHS = ["/Applications/Tailscale.app/Contents/MacOS/Tailscale"]
elif WINDOWS:
    TAILSCALE_PATHS = _windows_programs("Tailscale/tailscale.exe")
else:
    TAILSCALE_PATHS = []


def venv_bin(env, name):
    """Un programa de un entorno aparte de Python (yt-dlp, numpy): env/bin/<name> en macOS y Linux,
    env\\Scripts\\<name>.exe en Windows."""
    return Path(env) / "Scripts" / f"{name}.exe" if WINDOWS else Path(env) / "bin" / name


# Prioridad baja para los análisis largos (doblajes, «Saltar intro», subtítulos con la voz): que no le quiten fluidez a
# lo que se está viendo. En macOS y Linux, «nice -n 15» delante del comando; en Windows no hay «nice»: el comando va tal
# cual y la prioridad se pide al crearlo (LOW_PRIORITY va en subprocess.run/Popen).
LOW_PRIORITY = {"creationflags": getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0x4000)} if WINDOWS else {}


def low_priority(cmd):
    """El comando con prioridad baja (ver LOW_PRIORITY)."""
    return [str(c) for c in cmd] if WINDOWS else ["nice", "-n", "15", *(str(c) for c in cmd)]


def pause_process(proc, pause):
    """Pausa a un proceso (ffmpeg muy adelantado) o lo deja seguir: SIGSTOP/SIGCONT en macOS y Linux; en Windows,
    que no tiene esas señales, se le pide al sistema directamente."""
    if proc is None:
        return
    try:
        if WINDOWS:
            winapi.suspend(proc.pid, pause)
        else:
            os.kill(proc.pid, signal.SIGSTOP if pause else signal.SIGCONT)
    except (ProcessLookupError, OSError):
        pass


def stop_leftovers(folder):
    """Detiene los ffmpeg que quedaron vivos trabajando en esa carpeta (si el servidor se cerró a la fuerza)."""
    if WINDOWS:
        winapi.stop_processes_using(folder)
        return
    for sig in ("-CONT", "-TERM"):   # primero que sigan (por si estaban en pausa) y luego que terminen
        try:
            subprocess.run(["pkill", sig, "-f", str(folder)], capture_output=True)
        except OSError:
            pass


def open_shared(path):
    """Abre un archivo para mandarlo. En Windows, sin impedir que mientras tanto ffmpeg lo reemplace o se borre (allá
    un archivo abierto de la forma normal no se puede borrar ni reemplazar)."""
    return winapi.open_shared(path) if WINDOWS else open(path, "rb")


def read_shared(path):
    """Lee un archivo entero como open_shared (una lista de ffmpeg que se renueva cada pocos segundos)."""
    with open_shared(path) as f:
        return f.read()


def rerun_utf8():
    """Windows: vuelve a correr este programa con los textos en UTF-8 (-X utf8, como en macOS y Linux) y devuelve su
    código de salida. Sin esto, Python lee y escribe con la página de códigos de Windows: los acentos de config.json,
    los nombres de las películas y lo que dicen ffmpeg y yt-dlp saldrían mal. cine.cmd ya lo pide; esto es por si
    alguien corre mac\\cine.py directamente."""
    os.environ["PYTHONUTF8"] = "1"   # también para lo que este programa lance (yt-dlp, los análisis con numpy)
    proc = subprocess.Popen([sys.executable, "-X", "utf8", *sys.argv])
    while True:
        try:
            return proc.wait()
        except KeyboardInterrupt:
            continue   # el Ctrl+C también le llega al programa, que se apaga solo
