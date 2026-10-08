"""El asistente del primer arranque, en el navegador (/bienvenida, mac/web/bienvenida.html): tus videos, tu TV, los
extras y listo.

Quién puede usarlo. El servidor no tiene contraseña y escucha en la red de la casa; el asistente cambia la
configuración y deja ver los nombres de las carpetas. Por eso:
- Desde esta misma computadora, siempre (para volver a abrirlo desde Ajustes).
- Desde otro aparato de la casa, solo mientras la bienvenida no se ha terminado: es el caso de un NAS o de una
  computadora sin pantalla, que se configuran desde otra. Al terminar se cierra para los demás aparatos.
- Después, desde otro aparato, con un código de 6 cifras que sale en la TV (CodigoTele): solo lo ve quien está en la
  casa frente a ella. Si no hay ninguna TV conectada, queda en el registro del servidor. Con el código, ese navegador
  puede usarlo una hora.
- Siempre que la página se haya abierto con una dirección de la casa (una IP, «localhost», el nombre de la computadora
  o un nombre «.local»). Un nombre de internet puede ser una página ajena que apunta a esta computadora para usar el
  asistente desde el navegador de quien la visita (lo que se llama «DNS rebinding»): no.
- Permitir la entrada en Windows y activar «fuera de casa» abren ventanas o cambian cosas de esta computadora: solo
  desde ella.

El explorador de carpetas solo enseña carpetas (nunca archivos) dentro de lugares razonables: la carpeta de la
persona, los discos conectados y las carpetas compartidas montadas (en un contenedor, lo que se montó). Nada oculto ni
del sistema (Library, AppData…). Toda ruta que manda el navegador se resuelve (sin «..» ni enlaces que salgan) y se
revisa contra esos lugares antes de abrirla o guardarla.

Dónde se buscan videos: las carpetas de la persona (Películas o Videos, Descargas…; en macOS no Descargas, Documentos
ni Escritorio, que el servicio no puede leer sin pedir permiso), los discos externos, las carpetas compartidas
montadas y, en un contenedor, lo que el instalador montó: primero las carpetas compartidas (la variable
ONE_TV_COMPARTIDAS dice dónde, por ejemplo /volume1), cada una por separado («En la carpeta compartida «video»»). De cada carpeta se cuentan películas y series rápido y con
tope (unos segundos en total).
"""

import ipaddress
import math
import os
import re
import secrets
import subprocess
import threading
import time
import unicodedata
from pathlib import Path

import hostos
from library import EPISODE_RE, EXTRA_SUFFIX_RE, PART_RE, SEASON_DIR_RE, SKIP_DIRS, VIDEO_EXTS, nice_show_name
from music import AUDIO_EXTS

# ---------------------------------------------------------------- quién puede usarlo

HOME_SUFFIXES = (".local", ".lan", ".home", ".internal", ".home.arpa")
NOT_ALLOWED = ("Por seguridad, desde otro aparato hace falta el código que aparece en tu TV. "
               "Vuelve a abrir el asistente para pedirlo.")
ONLY_HERE = "Esto solo se puede hacer en la computadora donde está One TV."


def _ip(text):
    text = str(text or "").strip()
    if text.lower().startswith("::ffff:"):
        text = text[7:]
    try:
        return ipaddress.ip_address(text.split("%")[0])
    except ValueError:
        return None


def host_name(header):
    """El nombre de la cabecera Host, sin el puerto: «192.0.2.7:8765» -> «192.0.2.7», «[::1]:8765» -> «::1»."""
    h = str(header or "").strip().lower()
    if h.startswith("["):
        return h[1:h.find("]")] if "]" in h else ""
    if h.count(":") == 1:
        h = h.split(":")[0]
    return h.rstrip(".")


def safe_host(header):
    """¿La página se abrió con una dirección de la casa? (una IP, «localhost», un nombre sin puntos o terminado en
    .local/.lan/.home). Un nombre de internet no: podría ser una página ajena que se hace pasar por esta."""
    name = host_name(header)
    if not name:
        return False
    if name == "localhost" or _ip(name) is not None:
        return True
    return "." not in name or name.endswith(HOME_SUFFIXES)


def is_local(peer, own, host):
    """¿La petición viene de esta misma computadora? (desde 127.0.0.1, o a su propia dirección de la red: entonces quien
    pide y quien contesta tienen la misma IP) y con una dirección de la casa."""
    p = _ip(peer)
    if p is None:
        return False
    return bool(p.is_loopback or (own and p == _ip(own))) and safe_host(host)


def may_change(local, pending, host, with_code=False):
    """¿Puede usar el asistente? Desde esta computadora siempre; desde otro aparato, mientras falte terminarlo o si
    escribió el código que salió en la TV (with_code: su cookie todavía vale)."""
    return safe_host(host) and bool(local or pending or with_code)


# ---------------------------------------------------------------- el código de la TV

CODE_LIFE = 10 * 60        # un código vale 10 minutos
CODE_TRIES = 5             # intentos por código; después hay que pedir otro
CODE_GAP = 30              # segundos entre un código y el siguiente (cada uno sale en la TV)
CODES_PER_HOUR = 10
PASS_LIFE = 60 * 60        # con el código correcto, ese navegador puede usar el asistente una hora
MAX_PASSES = 20            # navegadores autorizados a la vez (se olvida el que vence antes)
COOKIE = "onetv_asistente"


def cookie_value(header, name=COOKIE):
    """El valor de esa cookie en la cabecera Cookie («a=1; onetv_asistente=xyz») o ""."""
    for part in str(header or "").split(";"):
        key, _, value = part.strip().partition("=")
        if key == name:
            return value.strip().strip('"')
    return ""


def pretty_code(code):
    """«482913» -> «482 913» (así se lee en la TV y en el registro)."""
    return f"{code[:3]} {code[3:]}"


class CodigoTele:
    """El código de 6 cifras que sale en la TV para usar el asistente desde otro aparato cuando ya se terminó (por
    ejemplo, One TV en un NAS sin pantalla). Solo lo ve quien está en la casa frente a la TV. Uno a la vez: pedir otro
    deja sin valor al anterior; vale CODE_LIFE segundos, CODE_TRIES intentos y una sola vez. Con el código correcto el
    navegador recibe una cookie con un valor aleatorio que vale PASS_LIFE segundos (solo vive en la memoria del
    servidor: al reiniciarlo hay que pedir otro código)."""

    def __init__(self, clock=time.monotonic, rng=secrets):
        self.clock = clock
        self.rng = rng
        self.lock = threading.Lock()
        self.code = None     # {"valor", "hasta", "intentos"}
        self.asked = []      # cuándo se dio cada código de la última hora
        self.passes = {}     # valor de la cookie -> hasta cuándo vale

    def new(self):
        """-> (código, None) o (None, por qué no)."""
        with self.lock:
            now = self.clock()
            self.asked = [t for t in self.asked if now - t < 3600]
            if self.asked and now - self.asked[-1] < CODE_GAP:
                wait = max(1, math.ceil(CODE_GAP - (now - self.asked[-1])))
                return None, f"Espera {wait} segundos para pedir otro código."
            if len(self.asked) >= CODES_PER_HOUR:
                return None, "Pediste muchos códigos seguidos. Prueba otra vez en un rato."
            self.asked.append(now)
            value = f"{self.rng.randbelow(10 ** 6):06d}"
            self.code = {"valor": value, "hasta": now + CODE_LIFE, "intentos": 0}
            return value, None

    def check(self, typed):
        """-> (valor de la cookie, None) si es el código, o (None, qué decir)."""
        typed = re.sub(r"[^0-9]", "", str(typed or ""))[:12]   # sin espacios ni guiones
        if len(typed) != 6:
            return None, "Escribe los 6 números que aparecen en tu TV."
        with self.lock:
            now = self.clock()
            code = self.code
            if not code or now > code["hasta"]:
                self.code = None
                return None, "Ese código ya no sirve. Pide otro."
            code["intentos"] += 1
            if not secrets.compare_digest(typed, code["valor"]):
                left = CODE_TRIES - code["intentos"]
                if left <= 0:
                    self.code = None
                    return None, "Ese no es el código. Pide otro."
                return None, f"Ese no es el código. Te queda{'' if left == 1 else 'n'} {left} intento{'' if left == 1 else 's'}."
            self.code = None   # se usa una sola vez
            self.passes = {k: v for k, v in self.passes.items() if v > now}
            while len(self.passes) >= MAX_PASSES:
                del self.passes[min(self.passes, key=self.passes.get)]
            token = secrets.token_urlsafe(32)
            self.passes[token] = now + PASS_LIFE
            return token, None

    def valid(self, token):
        """¿Esa cookie todavía deja usar el asistente?"""
        if not token:
            return False
        with self.lock:
            until = self.passes.get(token)
            if until is None:
                return False
            if self.clock() > until:
                del self.passes[token]
                return False
            return True


# ---------------------------------------------------------------- la contraseña del Roku

CONSONANTS = "bcdfghjkmnprstvz"   # sin l, q, w, x, y (se confunden o cuesta encontrarlas)
VOWELS = "aeu"                    # sin i ni o (se confunden con 1 y 0)
DIGITS = "2345679"                # sin 0, 1 ni 8


def roku_password(rng=secrets):
    """Una contraseña fácil de escribir con el control del Roku: dos sílabas y dos números, en minúsculas («baku47»)."""
    return "".join(rng.choice(s) for s in (CONSONANTS, VOWELS, CONSONANTS, VOWELS, DIGITS, DIGITS))


# ---------------------------------------------------------------- dónde buscar

NETWORK_FS = {"smbfs", "afpfs", "nfs", "nfs4", "cifs", "smb3", "webdav", "davfs", "fuse.davfs", "fuse.sshfs", "sshfs",
              "9p", "fuse.rclone", "ftp", "fuse.smbnetfs", "fuse.gvfsd-fuse"}
DISK_FS = {"ext2", "ext3", "ext4", "xfs", "btrfs", "zfs", "ntfs", "ntfs3", "fuseblk", "exfat", "vfat", "msdos", "hfsplus",
           "apfs", "hfs", "f2fs", "jfs", "reiserfs", "udf"}
VIRTUAL_FS = {"proc", "sysfs", "tmpfs", "devtmpfs", "devpts", "mqueue", "cgroup", "cgroup2", "overlay", "shm", "securityfs",
              "debugfs", "tracefs", "pstore", "bpf", "autofs", "binfmt_misc", "configfs", "fusectl", "hugetlbfs", "nsfs",
              "ramfs", "squashfs", "efivarfs", "rpc_pipefs", "nfsd", "fuse.portal", "fuse.snapfuse"}
SYSTEM_MOUNTS = ("/proc", "/sys", "/dev", "/run", "/boot", "/efi", "/snap", "/var", "/usr", "/etc", "/tmp", "/opt",
                 "/root", "/lib", "/lib64", "/bin", "/sbin", "/app", "/System", "/private", "/cores", "/nix")
# Carpetas de la carpeta personal que no son de videos (o son del sistema): ni se buscan ni se exploran.
HOME_SKIP = {"library", "appdata", "application data", "applications", "aplicaciones", "public", "público", "publico",
             "snap", "pictures", "imágenes", "imagenes", "fotos", "photos", "music", "música", "musica", "templates",
             "plantillas", "saved games", "contacts", "favorites", "links", "searches", "3d objects", "go",
             "node_modules", "anaconda3", "miniconda3", "sites"}
# En macOS el servicio no puede leer estas sin pedir permiso con una ventana: no se buscan solas (sí se pueden elegir).
MAC_PROTECTED = {"downloads", "documents", "desktop"}
# Nunca se exploran: del sistema, papeleras, copias de seguridad, miniaturas de un NAS.
BLOCKED = {"library", "appdata", "application data", "$recycle.bin", "system volume information", "backups.backupdb",
           "lost+found", "@eadir", "#recycle", "#snapshot", "@recycle", "windows", "program files",
           "program files (x86)", "programdata", "recovery", "node_modules"}
# Carpetas compartidas de un NAS que no son de videos (Synology, Unraid, QNAP): no se buscan solas.
SHARE_SKIP = {"photo", "photos", "fotos", "music", "música", "musica", "web", "docker", "appdata", "domains", "isos",
              "system", "surveillance", "netbackup", "activebackupforbusiness"}
PACKAGES = (".app", ".photoslibrary", ".imovielibrary", ".fcpbundle", ".tvlibrary", ".musiclibrary", ".bundle",
            ".lrdata", ".framework", ".theater", ".rcproject")


def _key(name):
    return unicodedata.normalize("NFC", name).casefold()


def _hidden(name):
    k = _key(name)
    return name.startswith((".", "$", "~$", "@", "#")) or k in BLOCKED or k.endswith(PACKAGES) or k.startswith("com.apple.")


def _mounts():
    """[(punto de montaje, tipo)] de lo montado: macOS con «mount», Linux y el contenedor con /proc/self/mounts."""
    out = []
    if hostos.MAC and not hostos.CONTAINER:
        try:
            text = subprocess.run(["mount"], capture_output=True, text=True, timeout=5).stdout
        except (OSError, subprocess.SubprocessError):
            return out
        for line in text.splitlines():
            m = re.match(r"^.*? on (.+) \(([^,)]+)", line)
            if m:
                out.append((m.group(1), m.group(2).strip().lower()))
        return out
    for source in ("/proc/self/mounts", "/proc/mounts"):
        try:
            text = Path(source).read_text(errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            parts = line.split()
            if len(parts) >= 3:
                point = re.sub(r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), parts[1])
                out.append((point, parts[2].lower()))
        break
    return out


def _system_mount(point):
    if point in ("/", "") or point.startswith("/run/media/"):
        return point in ("/", "")
    return any(point == s or point.startswith(s + "/") for s in SYSTEM_MOUNTS)


def _windows_drives():
    """[(raíz, tipo, nombre)] de los discos de Windows que no son el del sistema: los conectados («disco») y las
    unidades de red («red»)."""
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        mask = k32.GetLogicalDrives()
    except (AttributeError, OSError, ImportError):
        return []
    system = (os.environ.get("SystemDrive") or "C:").rstrip("\\").upper()
    out = []
    for i in range(26):
        if not mask & (1 << i):
            continue
        letter = f"{chr(65 + i)}:"
        if letter == system:
            continue
        root = letter + "\\"
        kind = k32.GetDriveTypeW(root)
        if kind not in (2, 3, 4):   # extraíble, fijo o de red (no CD ni lo desconocido)
            continue
        label = ctypes.create_unicode_buffer(261)
        try:
            k32.GetVolumeInformationW(root, label, 261, None, None, None, None, 0)
        except OSError:
            pass
        name = label.value.strip() or letter
        out.append((Path(root), "red" if kind == 4 else "disco", f"{name} ({letter})" if label.value.strip() else letter))
    return out


def shared_roots():
    """En un contenedor: dónde montó el instalador las carpetas compartidas (en su misma ruta, de solo lectura). Lo dice
    la variable ONE_TV_COMPARTIDAS: «/volume1» en Synology, «/mnt/user» en Unraid; varias, separadas por «:» o «,»."""
    out = []
    for part in re.split(r"[:,;\n]+", os.environ.get("ONE_TV_COMPARTIDAS", "")):
        part = part.strip()
        if part.startswith("/"):
            p = Path(part)
            try:
                if p.is_dir() and p not in out:
                    out.append(p)
            except OSError:
                pass
    return out


def places():
    """Los lugares donde buscar y explorar: [{"ruta": Path, "tipo": casa|disco|red|montada|compartidas, "nombre"}]
    («compartidas»: una carpeta que tiene adentro las carpetas compartidas, como /volume1 en un contenedor)."""
    out = []
    if hostos.CONTAINER:   # primero las carpetas compartidas; luego lo demás que se montó (videos, música)
        shared = shared_roots()
        out += [{"ruta": r, "tipo": "compartidas",
                 "nombre": "Carpetas compartidas" if len(shared) == 1 else f"Carpetas compartidas «{r.name or r}»"}
                for r in shared]
        data = Path(hostos.SERVICE_HOME)
        for point, kind in _mounts():
            p = Path(point)
            if kind in VIRTUAL_FS or _system_mount(point) or p == data or data in p.parents or not p.is_dir():
                continue
            if any(r == p or r in p.parents for r in shared):
                continue   # ya está dentro de las compartidas
            out.append({"ruta": p, "tipo": "red" if kind in NETWORK_FS else "montada", "nombre": p.name or point})
        return _dedupe(out)
    home = Path.home()
    seen = set()
    candidates = [hostos.user_dir("VIDEOS"), hostos.user_dir("DOWNLOAD")]
    try:
        candidates += sorted((e for e in home.iterdir() if e.is_dir()), key=lambda e: _key(e.name))
    except OSError:
        pass
    for p in candidates:
        k = _key(p.name)
        if p in seen or _hidden(p.name) or k in HOME_SKIP or (hostos.MAC and k in MAC_PROTECTED):
            continue
        seen.add(p)
        try:
            if p.is_dir():
                out.append({"ruta": p, "tipo": "casa", "nombre": p.name})
        except OSError:
            pass
    if hostos.WINDOWS:
        out += [{"ruta": r, "tipo": t, "nombre": n} for r, t, n in _windows_drives()]
        return _dedupe(out)
    mounts = _mounts()
    if hostos.MAC:
        kinds = dict(mounts)
        try:
            volumes = sorted(Path("/Volumes").iterdir(), key=lambda e: _key(e.name))
        except OSError:
            volumes = []
        for v in volumes:
            try:
                if _hidden(v.name) or v.resolve() == Path("/") or not v.is_dir():
                    continue
            except OSError:
                continue
            out.append({"ruta": v, "tipo": "red" if kinds.get(str(v)) in NETWORK_FS else "disco", "nombre": v.name})
        return _dedupe(out)
    for point, kind in mounts:   # Linux: discos (en /media, /mnt, /run/media o donde sea) y carpetas compartidas
        p = Path(point)
        if _system_mount(point) or p == home or p in home.parents or (kind not in DISK_FS and kind not in NETWORK_FS):
            continue
        if kind in NETWORK_FS or point.startswith(("/media/", "/mnt/", "/run/media/", "/srv/", "/data")) or kind in DISK_FS:
            out.append({"ruta": p, "tipo": "red" if kind in NETWORK_FS else "disco", "nombre": p.name or point})
    return _dedupe(out)


def _dedupe(found):
    out, seen = [], set()
    for p in found:
        if str(p["ruta"]) not in seen:
            seen.add(str(p["ruta"]))
            out.append(p)
    return out


def browse_roots(found):
    """Dónde se puede explorar: la carpeta de la persona (fuera de un contenedor) y los discos y carpetas compartidas."""
    roots = [] if hostos.CONTAINER else [Path.home()]
    roots += [p["ruta"] for p in found if p["tipo"] != "casa"]
    roots += [p["ruta"] for p in found if p["tipo"] == "casa" and not any(r == p["ruta"] or r in p["ruta"].parents for r in roots)]
    return roots


def container_label():
    name = hostos.computer_name()
    return f"En «{name}»" if name and name != "Contenedor" else "En el equipo donde está One TV"


def where(path, found):
    """«En esta computadora», «En el disco «Respaldo»», «En la carpeta compartida «video»»."""
    path = Path(path)
    best = None
    for p in found:
        r = p["ruta"]
        if (r == path or r in path.parents) and p["tipo"] != "casa" and (best is None or len(r.parts) > len(best["ruta"].parts)):
            best = p
    if best and best["tipo"] == "compartidas":
        rel = path.relative_to(best["ruta"]).parts
        return f"En la carpeta compartida «{rel[0]}»" if rel else container_label()
    if best and best["tipo"] == "disco":
        return f"En el disco «{best['nombre']}»"
    if best and best["tipo"] == "red":
        return f"En la carpeta compartida «{best['nombre']}»"
    return container_label() if hostos.CONTAINER else "En esta computadora"


def resolve_allowed(path, roots):
    """La carpeta que pidió el navegador, si se puede abrir: ruta completa, que exista, dentro de uno de los lugares
    y sin nada oculto ni del sistema en el camino. Si no, None."""
    if not isinstance(path, str) or not path or len(path) > 4096 or "\0" in path:
        return None
    raw = Path(path)
    if not raw.is_absolute():
        return None
    try:
        p = raw.resolve(strict=True)
        if not p.is_dir():
            return None
    except (OSError, RuntimeError):
        return None
    for root in roots:
        try:
            r = Path(root).resolve()
        except (OSError, RuntimeError):
            continue
        if p == r or r in p.parents:
            rel = p.relative_to(r).parts
            if any(_hidden(part) for part in rel):
                return None
            if r == Path.home().resolve() and rel and _key(rel[0]) in HOME_SKIP - {"music", "música", "musica"}:
                return None   # Library, AppData…: sí la música (para elegir dónde está)
            return p
    return None


# ---------------------------------------------------------------- contar rápido

MIN_BYTES = 20 * 1024 * 1024   # menos que esto suele ser un clip (del teléfono, de WhatsApp), no una película
WALK_LIMIT = 3000              # cosas que se miran por carpeta, como mucho
MAX_DEPTH = 6


def _show_name(path, stem, m):
    raw = stem[:m.start()]
    name = nice_show_name(raw) if raw.strip(" -._") else ""
    if not name.strip():
        parent = path.parent
        if SEASON_DIR_RE.match(parent.name):
            parent = parent.parent
        name = nice_show_name(parent.name)
    return _key(name.strip())


def tally(folder, deadline, limit=WALK_LIMIT):
    """Cuántas películas y series hay en la carpeta (rápido: con tope de tiempo y de cosas que se miran).
    -> {"peliculas", "series", "mas" (no se terminó de contar), "legible", "existe", "sueltos" (videos directo en ella)}"""
    movies, shows = set(), set()
    seen, more, loose = 0, False, 0
    stack = [(Path(folder), 0)]
    while stack and not more:
        d, depth = stack.pop()
        try:
            entries = list(os.scandir(d))
        except PermissionError:
            if depth == 0:
                return {"peliculas": 0, "series": 0, "mas": False, "legible": False, "existe": True, "sueltos": 0}
            continue
        except OSError:
            if depth == 0:
                return {"peliculas": 0, "series": 0, "mas": False, "legible": False, "existe": False, "sueltos": 0}
            continue
        for e in entries:
            seen += 1
            if seen > limit or time.monotonic() > deadline:
                more = True
                break
            name = e.name
            if _hidden(name):
                continue
            try:
                is_dir = e.is_dir(follow_symlinks=False)
            except OSError:
                continue
            if is_dir:
                if depth < MAX_DEPTH and _key(name) not in SKIP_DIRS:
                    stack.append((Path(e.path), depth + 1))
                continue
            stem, ext = os.path.splitext(name)
            if ext.lower() not in VIDEO_EXTS or re.search(r"(?i)(?<![a-z])sample(?![a-z])", name) or EXTRA_SUFFIX_RE.search(stem):
                continue
            try:
                if e.stat().st_size < MIN_BYTES:
                    continue
            except OSError:
                continue
            if depth == 0:
                loose += 1
            m = EPISODE_RE.search(stem)
            if m:
                shows.add(_show_name(Path(e.path), stem, m))
            else:
                movies.add(_key(PART_RE.sub("", stem)))
    return {"peliculas": len(movies), "series": len(shows), "mas": more, "legible": True, "existe": True, "sueltos": loose}


def count_songs(roots, deadline, limit=20000):
    """(canciones, ¿hay más?) en las carpetas de música, rápido y con tope."""
    n = 0
    for root in roots:
        stack = [Path(root)]
        while stack:
            d = stack.pop()
            try:
                entries = list(os.scandir(d))
            except OSError:
                continue
            for e in entries:
                if n >= limit or time.monotonic() > deadline:
                    return n, True
                if e.name.startswith("."):
                    continue
                try:
                    if e.is_dir(follow_symlinks=False):
                        stack.append(Path(e.path))
                    elif os.path.splitext(e.name)[1].lower() in AUDIO_EXTS:
                        n += 1
                except OSError:
                    continue
    return n, False


def _sum(tallies):
    return {"peliculas": sum(t["peliculas"] for t in tallies), "series": sum(t["series"] for t in tallies),
            "mas": any(t["mas"] for t in tallies), "legible": True, "existe": True, "sueltos": 0}


def folders_in(place, deadline, skip=()):
    """Las carpetas con videos de un lugar -> [(carpeta, cuenta)]: el lugar mismo si tiene videos sueltos o una carpeta
    por película (como Descargas, o un disco con todo en la raíz); si no, cada carpeta de primer nivel con videos.
    Un disco o una carpeta compartida que no se puede leer sale igual (con «legible»: False), para decir cómo arreglarlo."""
    root = place["ruta"]
    first = tally(root, min(deadline, time.monotonic() + 0.5), limit=400)   # solo lo de arriba: ¿videos sueltos?
    if not first["legible"]:
        return [(root, first)] if first["existe"] and place["tipo"] != "casa" else []
    shares = place["tipo"] == "compartidas"   # la carpeta de las compartidas: nunca entera, cada una por separado
    if first["sueltos"] and not shares:
        return [(root, tally(root, deadline))]
    try:
        subs = sorted((Path(e.path) for e in os.scandir(root) if not _hidden(e.name) and e.is_dir(follow_symlinks=False)
                       and _key(e.name) not in SKIP_DIRS), key=lambda p: _key(p.name))
    except OSError:
        return []
    found = []
    for sub in subs:
        if time.monotonic() > deadline:
            break
        if any(sub.resolve() == s or s in sub.resolve().parents or sub.resolve() in s.parents for s in skip):
            continue   # ya está en la biblioteca (o la contiene)
        if shares and _key(sub.name) in SHARE_SKIP:
            continue
        t = tally(sub, deadline)
        if t["legible"] and (t["peliculas"] or t["series"]):
            found.append((sub, t))
    titles = [t for _, t in found if t["peliculas"] + t["series"] <= 1 and not t["mas"]]
    if found and len(titles) * 2 >= len(found) and not shares:
        return [(root, _sum([t for _, t in found]))]
    return found


# ---------------------------------------------------------------- textos

def fix_hint():
    """Qué hacer cuando One TV no puede leer una carpeta, en una frase."""
    if hostos.MAC and not hostos.CONTAINER:
        return ("Abre Ajustes del Sistema › Privacidad y seguridad › Acceso total al disco y activa «python3» (es One "
                "TV). Después toca «Revisar otra vez».")
    return hostos.unreadable_hint()


def _resolve(folder):
    return Path(os.path.expanduser(str(folder))).resolve()


# ---------------------------------------------------------------- el asistente

class Asistente:
    """Lo que hace el asistente con la App (mac/cine.py): leer y guardar la configuración y aplicarla sin reiniciar."""

    def __init__(self, app, save, project, tailscale_url=None, tailscale_cli=None, tailscale_serve=None,
                 autostart=None, log=print):
        from roku import Roku, build_channel_zip, discover, local_ip_towards
        from subtitles_online import OpenSubtitles
        import winfirewall
        self.app = app
        self.save = save   # cine.save_config: cambia algunas claves de config.json sin tocar las demás
        self.project = Path(project)
        self.tailscale_url = tailscale_url or (lambda port: None)
        self.tailscale_cli = tailscale_cli or (lambda: None)
        self.tailscale_serve = tailscale_serve
        self.autostart = autostart or (lambda: False)
        self.log = log
        self.places = places
        self.discover, self.Roku, self.local_ip, self.build_zip = discover, Roku, local_ip_towards, build_channel_zip
        self.OpenSubtitles = OpenSubtitles
        self.firewall = winfirewall
        self.windows = hostos.WINDOWS   # (las pruebas lo cambian para ver lo de Windows en otra computadora)
        self.lock = threading.Lock()
        self.roku_job = {"estado": "nada", "mensaje": ""}
        self._looking = 0.0      # cuándo se buscó el Roku por última vez desde el asistente
        self._outside = (0.0, None)
        self.codigo = CodigoTele()   # para usarlo desde otro aparato cuando ya se terminó

    # ---------- el código de la TV ----------

    def ask_code(self):
        """Un código nuevo, a las TV conectadas (el Roku y las TV con Android con One TV abierta) y al registro."""
        code, error = self.codigo.new()
        if error:
            return {"ok": False, "error": error}
        shown = self._code_to_tvs(code)
        self.log(f"Código para cambiar la configuración de One TV desde otro aparato: {pretty_code(code)} "
                 f"(vale {CODE_LIFE // 60} minutos)" + (f"; está en la TV: {', '.join(shown)}" if shown else ""))
        return {"ok": True, "en_tele": bool(shown), "minutos": CODE_LIFE // 60}

    def _code_to_tvs(self, code):
        """-> los nombres de las TV a las que llegó."""
        app = self.app
        shown = []
        teles = getattr(app, "teles", None)
        for tv in teles.android() if teles else []:
            try:
                tv.send(cmd="codigo", codigo=code)
                shown.append(tv.nombre)
            except OSError:
                pass
        roku = getattr(app, "roku", None)
        if roku is not None and getattr(app, "roku_name", "") and hasattr(roku, "show_code"):
            try:
                roku.show_code(code, getattr(app, "server_url", ""))
                shown.append(app.roku_name)
            except OSError:
                pass
        return shown

    def enter_code(self, typed):
        """-> (respuesta, valor de la cookie o None)."""
        token, error = self.codigo.check(typed)
        if error:
            return {"ok": False, "error": error}, None
        self.log("Un aparato escribió el código: puede cambiar la configuración durante una hora.")
        return {"ok": True}, token

    # ---------- estado ----------

    def roku_password(self):
        """La contraseña del modo desarrollador: la que ya tenga config.json o una nueva (se guarda en seguida)."""
        cfg = self.app.cfg
        with self.lock:
            if not str(cfg.get("roku_password") or "").strip():
                pwd = roku_password()
                self.save({"roku_password": pwd})
                cfg["roku_password"] = pwd
                if getattr(self.app, "roku", None) is not None and hasattr(self.app.roku, "dev_password"):
                    self.app.roku.dev_password = pwd
            return str(cfg["roku_password"])

    def _look_for_roku(self):
        """Si todavía no se encontró el Roku, se busca otra vez (de fondo, a lo más cada 20 s)."""
        connect = getattr(self.app, "connect_roku", None)
        if not connect or time.monotonic() - self._looking < 20:
            return
        self._looking = time.monotonic()

        def look():
            try:
                connect()
            except Exception:  # noqa: BLE001 - nunca debe tumbar el servidor
                pass
        threading.Thread(target=look, daemon=True).start()

    def state(self, allowed, local, can_ask=False):
        """can_ask: sin permiso, ¿puede pedir el código de la TV? (si la página se abrió con una dirección de la casa)"""
        app = self.app
        out = {"ok": True, "permitido": bool(allowed), "local": bool(local), "pendiente": bool(app.welcome_pending())}
        if not allowed:
            out["codigo"] = bool(can_ask)
            return out
        cfg = app.cfg
        port = cfg["puerto"]
        roku = getattr(app, "roku", None)
        roku_ok = roku is not None and bool(getattr(app, "roku_name", ""))
        if not roku_ok:
            self._look_for_roku()
        teles = getattr(app, "teles", None)
        androids = teles.android() if teles else []
        tv = app.tv_app() if hasattr(app, "tv_app") else {"direccion": f"http://localhost:{port}/tv"}
        music = getattr(app, "music", None)
        roots = [r for r in (getattr(music, "roots", None) or []) if Path(r).is_dir()]
        songs, more = (len(getattr(music, "tracks", None) or {}), False)
        if not songs and roots:
            songs, more = count_songs(roots, time.monotonic() + 0.8)
        account = getattr(app, "account", None)
        yt = account.summary() if account else {}
        subs = getattr(app, "subs", None)
        phone = hostos.lan_url(port) or getattr(app, "server_url", "") or f"http://localhost:{port}"
        out.update({
            "sistema": "contenedor" if hostos.CONTAINER else "mac" if hostos.MAC else "windows" if hostos.WINDOWS else "linux",
            "carpetas": len(cfg.get("carpetas") or []),
            "roku": {"encontrado": roku_ok, "nombre": getattr(app, "roku_name", "") if roku_ok else "",
                     "clave": self.roku_password(), "instalacion": dict(self.roku_job),
                     "instalada": bool(getattr(app, "installed_url", None))},
            "android": {"conectada": bool(androids), "nombre": androids[0].nombre if androids else "",
                        "direccion": re.sub(r"^https?://", "", tv.get("direccion", "")), "hay_app": bool(tv.get("hay", True))},
            "tele": "android" if androids else "roku" if roku_ok else "",
            "red_bloqueada": bool(getattr(app, "network_blocked", False)),
            "puede_permitir": bool(self.windows and local),
            "musica": {"lista": songs > 0, "canciones": songs, "mas": more,
                       "carpeta": roots[0].name if roots else ""},
            "youtube": {"listo": bool(yt.get("subscriptions") or yt.get("playlists")),
                        "suscripciones": yt.get("subscriptions", 0), "listas": yt.get("playlists", 0),
                        "disponible": not hostos.CONTAINER},
            "subtitulos": {"activos": bool(subs and subs.configured), "usuario": getattr(subs, "username", "") or ""},
            "fuera": self._outside_state(port, local),
            "telefono": phone,
            "arranque": "equipo" if hostos.CONTAINER else "solo" if self._autostart() else "",
        })
        return out

    def _autostart(self):
        try:
            return bool(self.autostart())
        except Exception:  # noqa: BLE001
            return False

    def _outside_state(self, port, local):
        if hostos.CONTAINER:
            return {"estado": "falta", "puede": False}
        at, url = self._outside
        if time.monotonic() - at > 20:
            try:
                url = self.tailscale_url(port)
            except Exception:  # noqa: BLE001
                url = None
            self._outside = (time.monotonic(), url)
        if url:
            return {"estado": "listo", "direccion": url, "puede": bool(local)}
        try:
            installed = bool(self.tailscale_cli())
        except Exception:  # noqa: BLE001
            installed = False
        return {"estado": "instalado" if installed else "falta", "puede": bool(local)}

    # ---------- tus videos ----------

    def _configured(self):
        """[(lo que dice config.json, ruta completa)] de las carpetas de la biblioteca."""
        return [(str(f), _resolve(f)) for f in self.app.cfg.get("carpetas") or []]

    def folders(self, budget=10.0):
        """Las carpetas para el paso «Tus videos»: las de la biblioteca primero (marcadas) y luego las que se encontraron."""
        app = self.app
        found = self.places()
        start = time.monotonic()
        pending = bool(app.welcome_pending())
        out, taken = [], []
        lf = getattr(app, "folders", None)
        for _, root in self._configured():
            t = tally(root, time.monotonic() + 2.0)
            mine, why = lf.why(root) if lf else (True, "")
            item = self._card(root, t, found, chosen=True)
            if mine is False:
                item["solo_lectura"] = True
                item["motivo"] = "otro" if "otro programa" in why or "solo_leer" in why else "protegida"
            item["no_esta"] = mine is None and not t["existe"]
            item["configurada"] = True
            out.append(item)
            taken.append(root)
        candidates = []
        for i, place in enumerate(found):
            left = budget - (time.monotonic() - start)
            if left <= 0:
                break
            deadline = time.monotonic() + max(1.0, left / (len(found) - i))
            for folder, t in folders_in(place, deadline, taken):
                folder = folder.resolve()
                if any(folder == r or r in folder.parents or folder in r.parents for r in taken):
                    continue   # ya está (o está dentro, o contiene una) en la biblioteca
                taken.append(folder)
                candidates.append(self._card(folder, t, found, chosen=pending and t["legible"],
                                             name=place["nombre"] if folder == place["ruta"] else None))
        candidates.sort(key=lambda c: (c["sin_permiso"], -(c["peliculas"] + c["series"])))
        return {"ok": True, "carpetas": out + candidates[:12]}

    def _card(self, folder, t, found, chosen, name=None):
        from folders import looks_like_one_tv, writable
        card = {"ruta": str(folder), "nombre": name or folder.name or str(folder), "donde": where(folder, found),
                "peliculas": t["peliculas"], "series": t["series"], "mas": t["mas"], "elegida": bool(chosen),
                "solo_lectura": False, "motivo": "", "sin_permiso": not t["legible"] and t["existe"],
                "no_esta": not t["existe"], "arreglo": "" if t["legible"] or not t["existe"] else fix_hint(),
                "configurada": False}
        if t["legible"] and t["existe"]:
            try:
                if not writable(folder):
                    card["solo_lectura"], card["motivo"] = True, "protegida"
                elif (t["peliculas"] or t["series"]) and not looks_like_one_tv(folder):
                    card["solo_lectura"], card["motivo"] = True, "otro"
            except OSError:
                pass
        return card

    def browse(self, path):
        """El explorador de «Agregar otra carpeta»: sin ruta, los lugares; con ruta, sus carpetas (nunca archivos)."""
        found = self.places()
        roots = browse_roots(found)
        if not path:
            items = [{"ruta": str(r), "nombre": "Tu carpeta personal" if r == Path.home() and not hostos.CONTAINER else
                      next((p["nombre"] for p in found if p["ruta"] == r), r.name or str(r)), "donde": where(r, found)}
                     for r in roots]
            return {"ok": True, "ruta": "", "nombre": "", "arriba": None, "carpetas": items}
        p = resolve_allowed(path, roots)
        if p is None:
            return {"ok": False, "error": "Esa carpeta no se puede abrir desde aquí."}
        try:
            subs = sorted((e for e in os.scandir(p) if not _hidden(e.name) and e.is_dir()), key=lambda e: _key(e.name))
        except PermissionError:
            return {"ok": True, "ruta": str(p), "nombre": p.name or str(p), "donde": where(p, found),
                    "arriba": self._up(p, roots), "carpetas": [], "sin_permiso": True, "arreglo": fix_hint()}
        except OSError:
            return {"ok": False, "error": "No pude abrir esa carpeta."}
        items = []
        for e in subs[:400]:
            q = resolve_allowed(e.path, roots)
            if q is not None:
                items.append({"ruta": str(q), "nombre": e.name})
        t = tally(p, time.monotonic() + 0.6, limit=1500)
        return {"ok": True, "ruta": str(p), "nombre": p.name or str(p), "donde": where(p, found),
                "arriba": self._up(p, roots), "carpetas": items, "peliculas": t["peliculas"], "series": t["series"],
                "mas": t["mas"]}

    @staticmethod
    def _up(p, roots):
        if any(p == Path(r).resolve() for r in roots):
            return ""   # el principio: la lista de lugares
        return str(p.parent) if resolve_allowed(str(p.parent), roots) else ""

    def save_folders(self, chosen):
        """Guarda las carpetas elegidas (las de antes se pueden quitar; las nuevas tienen que estar en un lugar
        razonable) y las aplica sin reiniciar. -> {ok, carpetas} o {ok: false, error}"""
        if not isinstance(chosen, list) or not all(isinstance(c, str) for c in chosen) or len(chosen) > 50:
            return {"ok": False, "error": "No entendí qué carpetas elegiste."}
        app = self.app
        before = {root: text for text, root in self._configured()}
        roots = browse_roots(self.places())
        from folders import has_videos, looks_like_one_tv
        keep, read_only = [], dict(app.cfg.get("solo_leer") or {}) if isinstance(app.cfg.get("solo_leer"), dict) else {}
        if isinstance(app.cfg.get("solo_leer"), list):
            read_only = {f: True for f in app.cfg["solo_leer"]}
        seen = set()
        for c in chosen:
            try:
                resolved = Path(c).resolve() if Path(c).is_absolute() else None
            except (OSError, RuntimeError):
                resolved = None
            if resolved in before:
                text = before[resolved]
            else:
                p = resolve_allowed(c, roots)
                if p is None:
                    return {"ok": False, "error": "Una de las carpetas no se puede usar desde aquí."}
                resolved, text = p, hostos.tilde(p)
                try:
                    if has_videos(p) and not looks_like_one_tv(p):
                        read_only[text] = True   # ya tiene videos acomodados: solo leerla, por si acaso
                except OSError:
                    pass
            if resolved not in seen:
                seen.add(resolved)
                keep.append(text)
        if not keep:
            return {"ok": False, "error": "Elige al menos una carpeta: ahí One TV busca tus películas y series."}
        known = {_resolve(k) for k in keep}
        read_only = {k: v for k, v in read_only.items() if _resolve(k) in known}
        changes = {"carpetas": keep}
        if read_only or "solo_leer" in app.cfg:
            changes["solo_leer"] = read_only
        try:
            self.save(changes)
        except (OSError, ValueError) as e:
            return {"ok": False, "error": f"No se pudo guardar: {e}"}
        app.cfg.update(changes)
        self._apply_folders(keep, read_only)
        return {"ok": True, "carpetas": len(keep)}

    def _apply_folders(self, keep, read_only):
        """La biblioteca, el organizador y quién es dueño de cada carpeta, con las carpetas nuevas (sin reiniciar)."""
        from folders import read_only_setting
        app = self.app
        roots = [_resolve(f) for f in keep]
        library = getattr(app, "library", None)
        if library is not None:
            library.roots = list(roots)
            library.scanned_at = 0
        lf = getattr(app, "folders", None)
        if lf is not None:
            lf.roots = list(roots)
            lf.forced = read_only_setting(read_only)
            for r in roots:
                lf.why(r)
        organizer = getattr(app, "organizer", None)
        if organizer is not None:
            organizer.roots = list(roots)

        def rescan():
            try:
                if library is not None and hasattr(library, "scan"):
                    library.scan(force=True)
                if hasattr(app, "tell_tv_to_refresh"):
                    app.tell_tv_to_refresh()
            except Exception as e:  # noqa: BLE001 - nunca debe tumbar el servidor
                self.log(f"⚠ Biblioteca: {e}")
        threading.Thread(target=rescan, daemon=True).start()

    # ---------- tu TV: el Roku ----------

    def roku_status(self):
        return {"ok": True, **self.roku_job}

    def _roku(self, estado, mensaje):
        self.roku_job = {"estado": estado, "mensaje": mensaje}

    def roku_install(self):
        """Instala One TV en el Roku (de fondo; el avance en roku_status)."""
        with self.lock:
            if self.roku_job["estado"] in ("buscando", "instalando"):
                return {"ok": True, **self.roku_job}
            self._roku("buscando", "Buscando tu Roku…")
        threading.Thread(target=self._install_roku, daemon=True).start()
        return {"ok": True, **self.roku_job}

    def _install_roku(self):
        app = self.app
        pwd = self.roku_password()
        current = getattr(app, "roku", None)
        try:
            ip = (app.cfg.get("roku_ip") or (getattr(current, "ip", None) if getattr(app, "roku_name", "") else None)
                  or self.discover() or self.discover())
            if not ip:
                return self._roku("error", "No encontré tu Roku. Revisa que esté prendido y conectado al mismo Wi-Fi "
                                           "que esta computadora, y prueba otra vez.")
            self._roku("instalando", "Instalando One TV en tu Roku…")
            roku = current if current is not None and getattr(current, "ip", None) == ip and hasattr(current, "install") \
                else self.Roku(ip, pwd)
            roku.dev_password = pwd
            name = roku.device_name()
            server = f"http://{self.local_ip(ip)}:{app.cfg['puerto']}"
            ok, msg = roku.install(self.build_zip(self.project / "roku", server))
        except OSError:
            return self._roku("error", "No pude hablar con tu Roku. Revisa que esté prendido y prueba otra vez.")
        except Exception as e:  # noqa: BLE001 - nunca debe tumbar el servidor
            self.log(f"⚠ Asistente, Roku: {e}")
            return self._roku("error", "No se pudo instalar. Prueba otra vez en un momento.")
        if ok:
            app.roku, app.roku_name, app.server_url = roku, name, server
            app.installed_url = server
            self.log(f"✓ App del Roku: {msg} (desde el asistente)")
            return self._roku("listo", "Listo: One TV ya está en tu Roku.")
        self.log(f"✗ App del Roku: {msg} (desde el asistente)")
        if "contraseña" in msg:
            return self._roku("error", f"El Roku no aceptó la contraseña. Repite los pasos 1 a 3 y escribe {pwd}.")
        if "no se pudo conectar" in msg:
            return self._roku("error", "Tu Roku todavía no está listo para instalar apps. Haz los pasos 1 a 3, espera "
                                       "a que reinicie y prueba otra vez.")
        return self._roku("error", "El Roku no pudo instalar la app. Prueba otra vez en un momento.")

    # ---------- Windows: dejar entrar a la TV ----------

    def allow_network(self):
        app = self.app
        if not self.windows:
            app.network_blocked = False
            return {"ok": True, "bloqueada": False}
        port = app.cfg["puerto"]
        error = self.firewall.allow(port)
        if error == "cancelado":
            return {"ok": False, "bloqueada": True, "error": "No se dio el permiso. Toca «Permitir» otra vez y elige «Sí»."}
        if error:
            self.log(f"⚠ Firewall: {error}")
            return {"ok": False, "bloqueada": True, "error": "Windows no dejó abrir la entrada. Prueba otra vez."}
        blocked = bool(self.firewall.status(port))
        app.network_blocked = blocked
        if blocked:
            return {"ok": False, "bloqueada": True, "error": "Windows sigue bloqueando la entrada. Prueba otra vez."}
        return {"ok": True, "bloqueada": False}

    # ---------- extras ----------

    def music(self, folder):
        """La carpeta de tu música: se guarda y se lee de nuevo. -> {ok, canciones}"""
        roots = browse_roots(self.places())
        p = resolve_allowed(folder, roots)
        if p is None:
            return {"ok": False, "error": "Esa carpeta no se puede usar desde aquí."}
        songs, more = count_songs([p], time.monotonic() + 1.5)
        try:
            self.save({"musica": [hostos.tilde(p)]})
        except (OSError, ValueError) as e:
            return {"ok": False, "error": f"No se pudo guardar: {e}"}
        app = self.app
        app.cfg["musica"] = [hostos.tilde(p)]
        music = getattr(app, "music", None)
        if music is not None:
            music.roots = [p]
            music.scanned_at = 0

            def rescan():
                try:
                    music.scan(force=True)
                except Exception as e:  # noqa: BLE001
                    self.log(f"⚠ Música: {e}")
            threading.Thread(target=rescan, daemon=True).start()
        return {"ok": True, "canciones": songs, "mas": more, "carpeta": p.name}

    def subtitles(self, body):
        """Los datos de OpenSubtitles: se comprueban con el propio OpenSubtitles antes de guardarlos (nunca se devuelven)."""
        from subtitles_online import SubtitleError
        key = str(body.get("api_key") or "").strip()[:200]
        user = str(body.get("usuario") or "").strip()[:100]
        pwd = str(body.get("clave") or "")[:200]
        if not key:
            return {"ok": False, "error": "Falta la clave (la «API key» de opensubtitles.com/consumers)."}
        if bool(user) != bool(pwd):
            return {"ok": False, "error": "Escribe tu usuario y tu contraseña de OpenSubtitles."}
        client = self.OpenSubtitles({"opensubtitles": {"api_key": key, "usuario": user, "clave": pwd}})
        try:
            client._request("GET", "/infos/formats", retry=False)
        except SubtitleError as e:
            if e.code in (401, 403):
                return {"ok": False, "error": "OpenSubtitles no reconoce esa clave. Cópiala otra vez."}
            return {"ok": False, "error": "No pude comprobarla: no hay conexión con OpenSubtitles. Prueba en un momento."}
        if user:
            try:
                client._login()
            except SubtitleError as e:
                if e.code in (400, 401, 403):
                    return {"ok": False, "error": "OpenSubtitles no aceptó ese usuario y contraseña."}
                return {"ok": False, "error": "No pude comprobarlos: no hay conexión con OpenSubtitles. Prueba en un momento."}
        app = self.app
        conf = dict(app.cfg.get("opensubtitles") or {})
        conf.update({"api_key": key, "usuario": user, "clave": pwd})
        try:
            self.save({"opensubtitles": conf})
        except (OSError, ValueError) as e:
            return {"ok": False, "error": f"No se pudo guardar: {e}"}
        app.cfg["opensubtitles"] = conf
        subs = getattr(app, "subs", None)
        was_on = bool(subs and subs.configured)
        if subs is not None:
            subs.api_key, subs.username, subs.password, subs.token = key, user, pwd, None
        auto = getattr(app, "auto_subs", None)
        if auto is not None and not was_on and hasattr(auto, "watch"):
            threading.Thread(target=auto.watch, daemon=True).start()   # antes no arrancó: faltaba la clave
        return {"ok": True}

    def outside(self):
        """Fuera de casa: publica la página en la red privada de Tailscale (solo tus aparatos)."""
        if not self.tailscale_serve:
            return {"ok": False, "error": "Esto no se puede hacer aquí."}
        try:
            url, error = self.tailscale_serve(self.app.cfg["puerto"])
        except Exception as e:  # noqa: BLE001
            url, error = None, str(e)
        self._outside = (0.0, None)
        if not url:
            if error:
                self.log(f"⚠ Tailscale: {error}")
            return {"ok": False, "error": "No se pudo activar. Abre Tailscale en esta computadora, entra con tu cuenta y "
                                          "prueba otra vez."}
        return {"ok": True, "direccion": url}

    def qr(self):
        """El código QR de la dirección para el teléfono (cuadritos claros sobre negro, como en la TV)."""
        from qrpng import qr_png
        port = self.app.cfg["puerto"]
        url = hostos.lan_url(port) or getattr(self.app, "server_url", "") or f"http://localhost:{port}"
        return qr_png(url, 440, 32)
