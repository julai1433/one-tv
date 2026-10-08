"""Windows: que la TV y el teléfono puedan conectarse a esta computadora (el Firewall de Windows).

El servidor escucha en la red de la casa, pero el Firewall de Windows bloquea lo que llega de otros aparatos hasta que
alguien lo permite. Cuando el servidor corre de fondo (la tarea «One TV», sin ventana), Windows ni siquiera muestra el
aviso de «¿Permitir?»: la TV no encuentra la computadora y nadie sabe por qué. Por eso One TV crea una regla de
entrada propia, «One TV»: solo el puerto del servidor (TCP), solo desde aparatos de la misma red (LocalSubnet) y en
cualquier tipo de red (Any: aunque Windows haya marcado la red de la casa como «Pública»).

- status(port): ¿está bloqueada la entrada? Se puede revisar sin permisos de administrador.
- allow(port): crea (o corrige) la regla. Pide permiso de administrador una sola vez (la ventana de Windows de «¿Quieres
  permitir que esta aplicación haga cambios…?»); si ya se es administrador (GitHub Actions), no pregunta.

Lo corren «cine permitir-red», «cine autoarranque», el instalador y, para avisar, «cine estado» y el arranque del
servidor (/api/status dice «red_bloqueada»). Todo con PowerShell (Get-/New-NetFirewallRule).
"""

import base64
import os
import shutil
import subprocess
from pathlib import Path

RULE = "One TV"
# Que no se asome ninguna ventana negra (el servidor corre sin ventana). Fuera de Windows (las pruebas, con pwsh) no
# existe y Python no acepta la opción.
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
CANCELLED = 1223                # ERROR_CANCELLED: en la ventana de permiso se eligió «No»

# Qué perfiles de red tienen el firewall prendido y cómo están las reglas «One TV» (una línea por regla). Sin permisos.
CHECK = r"""$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$prendidos = @(Get-NetFirewallProfile | Where-Object { $_.Enabled -eq 'True' } | ForEach-Object { $_.Name })
'perfiles|' + ($prendidos -join ',')
foreach ($r in @(Get-NetFirewallRule -DisplayName 'One TV' -ErrorAction SilentlyContinue)) {
  $p = $r | Get-NetFirewallPortFilter
  $a = $r | Get-NetFirewallAddressFilter
  'regla|{0}|{1}|{2}|{3}|{4}|{5}|{6}' -f $r.Enabled, $r.Action, $r.Direction, $p.Protocol, ($p.LocalPort -join ','), ($a.RemoteAddress -join ','), $r.Profile
}
exit 0   # sin regla, Get-NetFirewallRule deja $? en falso y PowerShell saldría con 1 aunque todo salió bien
"""

# La regla: se borra la que hubiera (otro puerto, repetida, desactivada) y se crea una sola. Con permisos.
ALLOW = r"""$ErrorActionPreference = 'Stop'
Remove-NetFirewallRule -DisplayName 'One TV' -ErrorAction SilentlyContinue
New-NetFirewallRule -DisplayName 'One TV' -Group 'One TV' -Description 'One TV: deja que la TV y el teléfono de la casa se conecten al servidor (solo desde la misma red).' -Direction Inbound -Action Allow -Protocol TCP -LocalPort {port} -RemoteAddress LocalSubnet -Profile Any | Out-Null
"""

BLOCKED = "La TV y el teléfono no van a poder conectarse: Windows bloquea la entrada. Corre «cine permitir-red»."
ASK = ("Windows te va a preguntar si One TV puede recibir conexiones de tu TV y tu teléfono (una ventana de «¿Quieres "
       "permitir que esta aplicación haga cambios en el dispositivo?», de Windows PowerShell): di que sí.")


def powershell_exe():
    found = shutil.which("powershell")
    if found:
        return found
    root = os.environ.get("SystemRoot") or r"C:\Windows"
    return str(Path(root, "System32", "WindowsPowerShell", "v1.0", "powershell.exe"))


def powershell_args(script):
    """El comando para correr ese guion de PowerShell sin ventana ni perfil. Va codificado (-EncodedCommand: UTF-16 en
    base64) para que comillas y saltos de línea lleguen tal cual."""
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    return [powershell_exe(), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded]


def _run(script, timeout=60, run=subprocess.run):
    try:
        r = run(powershell_args(script), capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired) as e:
        return subprocess.CompletedProcess([], 1, "", str(e))
    out = r.stdout.decode("utf-8", "replace") if isinstance(r.stdout, bytes) else (r.stdout or "")
    err = r.stderr.decode("utf-8", "replace") if isinstance(r.stderr, bytes) else (r.stderr or "")
    return subprocess.CompletedProcess(r.args, r.returncode, out, err)


def _ports(text):
    return {p.strip().lower() for p in str(text).split(",") if p.strip()}


def parse(text, port):
    """Lo que dijo CHECK -> True (bloqueada), False (abierta: hay una regla buena o el firewall está apagado) o None
    (no se pudo saber)."""
    profiles = None
    rules = []
    for line in (text or "").splitlines():
        parts = line.strip().split("|")
        if parts[0] == "perfiles" and len(parts) >= 2:
            profiles = [p for p in parts[1].split(",") if p]
        elif parts[0] == "regla" and len(parts) >= 8:
            rules.append(parts[1:8])
    if profiles is None:
        return None
    if not profiles:   # el firewall de Windows está apagado (o lo reemplaza el de un antivirus): nada que abrir aquí
        return False
    for enabled, action, direction, protocol, local_ports, _remote, _profile in rules:
        if enabled.lower() != "true" or action.lower() != "allow" or direction.lower() != "inbound":
            continue
        if protocol.lower() not in ("tcp", "any"):
            continue
        ports = _ports(local_ports)
        if str(port) in ports or "any" in ports:
            return False
    return True


def status(port, run=subprocess.run):
    """¿Bloquea Windows la entrada al puerto del servidor? True, False o None (no se pudo revisar)."""
    r = _run(CHECK, run=run)
    if r.returncode != 0:
        return None
    return parse(r.stdout, port)


def is_admin():
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError, ImportError):
        return False


def elevated_script(port):
    """Lo que corre esta ventana para pedir el permiso: otra PowerShell, ya como administrador, que solo crea la regla.
    Sale con el código de esa otra (o CANCELLED si en la ventana de permiso se eligió «No»)."""
    inner = powershell_args(ALLOW.format(port=int(port)))[1:]
    quoted = ",".join("'" + a.replace("'", "''") + "'" for a in inner)
    return ("try { $p = Start-Process -FilePath '" + powershell_exe().replace("'", "''") + "' -Verb RunAs "
            "-WindowStyle Hidden -Wait -PassThru -ArgumentList " + quoted + "; exit $p.ExitCode } "
            "catch { exit " + str(CANCELLED) + " }")


def allow(port, run=subprocess.run, admin=None):
    """Crea la regla «One TV» para ese puerto. -> "" si quedó, "cancelado" si no se dio el permiso, o el error."""
    admin = is_admin() if admin is None else admin
    if admin:
        r = _run(ALLOW.format(port=int(port)), timeout=120, run=run)
    else:
        r = _run(elevated_script(port), timeout=900, run=run)   # espera a que la persona conteste
    if r.returncode == CANCELLED:
        return "cancelado"
    if r.returncode != 0:
        return (r.stderr.strip() or r.stdout.strip() or f"código {r.returncode}").splitlines()[-1]
    return ""


def ensure(port, say=print, run=subprocess.run, admin=None):
    """Si Windows bloquea la entrada, lo explica y crea la regla (una sola petición de permiso). -> True si la TV y el
    teléfono pueden conectarse (o no se pudo saber), False si quedó bloqueada."""
    blocked = status(port, run=run)
    if not blocked:
        return True
    say(ASK)
    error = allow(port, run=run, admin=admin)
    if error == "cancelado":
        say(f"⚠ No se dio el permiso. {BLOCKED}")
        return False
    if error:
        say(f"⚠ No se pudo crear la regla del firewall ({error}). {BLOCKED}")
        return False
    if status(port, run=run):
        say(f"⚠ Windows sigue bloqueando la entrada. {BLOCKED}")
        return False
    say("✓ Listo: la TV y el teléfono ya pueden conectarse a esta computadora.")
    return True
