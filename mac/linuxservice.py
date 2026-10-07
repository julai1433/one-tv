"""Arranque automático en Linux: un servicio de systemd de tu usuario (~/.config/systemd/user/cine-roku.service).

Hace lo mismo que el de launchd en macOS: arranca el servidor, lo vuelve a arrancar si se cae (a los 30 s) y deja lo
que dice en un registro. Se maneja con «systemctl --user», sin contraseña de administrador.

Para que arranque al encender la computadora aunque nadie inicie sesión (un servidor, un NAS), systemd tiene que
mantener los servicios de tu usuario siempre en marcha: «loginctl enable-linger». En un escritorio lo puede activar el
propio usuario; por SSH puede pedir la contraseña de administrador (o hacerse con sudo).
"""

import getpass
import os
import shutil
import subprocess
from pathlib import Path

from hostos import CONFIG_HOME

NAME = "cine-roku.service"
UNIT = CONFIG_HOME / "systemd" / "user" / NAME
PATH = "/usr/local/bin:/usr/bin:/bin:/usr/local/sbin:/usr/sbin:/sbin:/snap/bin"


def _escape(value):
    """Un valor de una unidad de systemd: «%» tiene un significado especial y se escribe doble."""
    return str(value).replace("%", "%%")


def _quote(value):
    """Una palabra de ExecStart entre comillas (por si la ruta tiene espacios)."""
    return '"' + _escape(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def unit_text(python, script, home, log):
    return f"""# One TV: lo crea y lo actualiza «./cine autoarranque» (se quita con «./cine quitar-autoarranque»).
[Unit]
Description=One TV (servidor de videos para la TV)

[Service]
ExecStart={_quote(python)} {_quote(script)} servir
WorkingDirectory={_escape(home)}
Environment=PYTHONUNBUFFERED=1
Environment=PATH={PATH}
Restart=always
RestartSec=30
StandardOutput=append:{_escape(log)}
StandardError=append:{_escape(log)}

[Install]
WantedBy=default.target
"""


def write(python, script, home, log):
    """Escribe la unidad si cambió. -> True si cambió."""
    text = unit_text(python, script, home, log)
    UNIT.parent.mkdir(parents=True, exist_ok=True)
    Path(log).parent.mkdir(parents=True, exist_ok=True)
    try:
        if UNIT.read_text() == text:
            return False
    except OSError:
        pass
    UNIT.write_text(text)
    return True


def systemctl(*args, timeout=60):
    try:
        return subprocess.run(["systemctl", "--user", *args], capture_output=True, text=True, timeout=timeout,
                              stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as e:
        return subprocess.CompletedProcess(args, 1, "", str(e))


def problem():
    """Por qué no se puede usar systemd de tu usuario aquí, o "" si se puede."""
    if not shutil.which("systemctl"):
        return ("Esta computadora no usa systemd, así que no puedo dejar el servidor arrancando solo. "
                "Puedes usarlo abriendo ./cine cuando quieras ver algo.")
    r = systemctl("show-environment", timeout=15)
    if r.returncode != 0:
        return ("No pude hablar con systemd de tu usuario (" + (r.stderr.strip().splitlines() or ["sin detalle"])[-1]
                + "). Entra directamente con tu usuario (en la computadora o por SSH; no con «su» ni «sudo») "
                  "y vuelve a intentarlo.")
    return ""


def pid():
    """El número del proceso del servidor si el servicio está corriendo, o None."""
    out = systemctl("show", "-p", "MainPID", "--value", NAME, timeout=15).stdout.strip()
    return int(out) if out.isdigit() and int(out) > 0 else None


def start():
    """Carga la unidad (nueva o cambiada), la deja activada para cada arranque y la (re)inicia. -> "" o el error."""
    systemctl("daemon-reload")
    r = systemctl("enable", NAME)
    if r.returncode != 0:
        return r.stderr.strip()
    r = systemctl("restart", NAME)
    return "" if r.returncode == 0 else r.stderr.strip()


def restart():
    systemctl("restart", NAME)


def remove():
    systemctl("disable", "--now", NAME)
    UNIT.unlink(missing_ok=True)
    systemctl("daemon-reload")


def _user():
    try:
        return getpass.getuser()
    except (KeyError, OSError):
        return os.environ.get("USER", "")


def lingering(user=None):
    """¿systemd mantiene tus servicios aunque no hayas iniciado sesión? (así arranca al encender la computadora)"""
    user = user or _user()
    if Path("/var/lib/systemd/linger", user).exists():
        return True
    try:
        out = subprocess.run(["loginctl", "show-user", user, "-p", "Linger", "--value"], capture_output=True,
                             text=True, timeout=15, stdin=subprocess.DEVNULL).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return False
    return out == "yes"


def enable_linger(user=None):
    """Lo activa. Puede pedir la contraseña en la Terminal (por eso no se captura lo que muestra). -> True si quedó."""
    user = user or _user()
    try:
        subprocess.run(["loginctl", "enable-linger", user], timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return lingering(user)


def linger_command():
    return f"sudo loginctl enable-linger {_user() or '$USER'}"
