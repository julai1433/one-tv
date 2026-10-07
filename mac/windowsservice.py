"""Arranque automático en Windows: una tarea del Programador de tareas, solo de tu usuario, al iniciar sesión.

Hace lo mismo que launchd en macOS y systemd en Linux: arranca el servidor, lo vuelve a arrancar si se cae (a los
30 s) y deja lo que dice en un registro. No pide contraseña ni permisos de administrador. El límite: arranca cuando
inicias sesión en Windows, no antes (para correr sin sesión, Windows pide guardar la contraseña de la cuenta).

La tarea («One TV») no abre ninguna ventana: corre este mismo archivo con pythonw.exe («lanzar»), que a su vez corre
el servidor (python.exe … cine.py servir) sin ventana, con la salida al registro. Si el lanzador se cierra (al cerrar
sesión, al quitar el autoarranque o desde el Administrador de tareas), Windows cierra con él al servidor y a sus
ffmpeg (winapi.kill_children_with_me).

Se maneja con schtasks, el programa de Windows para las tareas programadas.
"""

import getpass
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parent))   # «lanzar» corre este archivo solo

import hostos  # noqa: E402
import winapi  # noqa: E402

TASK = "One TV"
XML = hostos.SERVICE_HOME / "tarea-windows.xml"   # lo que se registró (para saber si cambió)
PIDFILE = hostos.SERVICE_HOME / "servidor.pid"    # el servidor que corre el lanzador
RESTART_AFTER = 30
MUTEX = "Local\\OneTV-lanzador"


def _user():
    """DOMINIO\\usuario de quien la crea: la tarea es solo para esa cuenta."""
    name = os.environ.get("USERNAME") or getpass.getuser()
    domain = os.environ.get("USERDOMAIN", "")
    return f"{domain}\\{name}" if domain else name


def pythonw_for(python):
    """El pythonw.exe (sin ventana) que va con ese python.exe; si no hay, el mismo python.exe."""
    p = Path(python)
    w = p.with_name("pythonw.exe")
    return str(w) if w.exists() else str(p)


def task_xml(pythonw, launcher, home, user):
    """La tarea: al iniciar sesión ese usuario, sin límite de tiempo, también con la laptop sin cargador, con
    prioridad normal (convierte video en tiempo real) y, si se cae, que Windows la vuelva a intentar cada minuto."""
    e = lambda v: escape(str(v), {'"': "&quot;"})  # noqa: E731
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>One TV: el servidor de videos para la TV. Lo crea «cine autoarranque» y lo quita «cine quitar-autoarranque».</Description>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <UserId>{e(user)}</UserId>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>{e(user)}</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>false</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>4</Priority>
    <RestartOnFailure>
      <Interval>PT1M</Interval>
      <Count>999</Count>
    </RestartOnFailure>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>"{e(pythonw)}"</Command>
      <Arguments>-X utf8 "{e(launcher)}" lanzar</Arguments>
      <WorkingDirectory>{e(home)}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def write(python, home, log):
    """Escribe la tarea (en SERVICE_HOME; start() la registra) si cambió. -> True si cambió. log: solo para crear su
    carpeta (el lanzador escribe ahí)."""
    text = task_xml(pythonw_for(python), Path(home) / "mac" / "windowsservice.py", home, _user())
    Path(log).parent.mkdir(parents=True, exist_ok=True)
    XML.parent.mkdir(parents=True, exist_ok=True)
    try:
        if XML.read_text(encoding="utf-16") == text:
            return False
    except (OSError, UnicodeError):
        pass
    XML.write_text(text, encoding="utf-16")   # schtasks pide el archivo en UTF-16
    return True


def installed():
    return XML.exists()


def _decode(data):
    for enc in ("oem", "utf-8"):   # schtasks escribe en la página de códigos de la consola («oem», solo en Windows)
        try:
            return (data or b"").decode(enc)
        except (LookupError, UnicodeDecodeError):
            continue
    return (data or b"").decode("latin-1")


def schtasks(*args, timeout=60):
    try:
        r = subprocess.run(["schtasks", *args], capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as e:
        return subprocess.CompletedProcess(args, 1, "", str(e))
    return subprocess.CompletedProcess(args, r.returncode, _decode(r.stdout), _decode(r.stderr))


def _error(r):
    return (r.stderr.strip() or r.stdout.strip() or "sin detalle").splitlines()[-1]


def problem():
    """Por qué no se puede usar el Programador de tareas aquí, o "" si se puede."""
    if not shutil.which("schtasks"):
        return ("No encontré el Programador de tareas de Windows (schtasks), así que no puedo dejar el servidor "
                "arrancando solo. Puedes usarlo abriendo cine.cmd cuando quieras ver algo.")
    return ""


def pid():
    """El número del proceso del servidor si el lanzador lo tiene corriendo, o None."""
    try:
        n = int(PIDFILE.read_text().strip())
    except (OSError, ValueError):
        return None
    try:
        return n if winapi.process_alive(n) else None
    except (OSError, AttributeError, ImportError):
        return None


def start():
    """Registra la tarea (nueva o cambiada) y la arranca ya. -> "" o el error."""
    r = schtasks("/Create", "/TN", TASK, "/XML", str(XML), "/F")
    if r.returncode != 0:
        return _error(r)
    r = schtasks("/Run", "/TN", TASK)
    return "" if r.returncode == 0 else _error(r)


def stop(wait=15):
    """Detiene la tarea (y con ella al servidor) y espera a que el servidor se haya ido."""
    schtasks("/End", "/TN", TASK)
    end = time.time() + wait
    while pid() and time.time() < end:
        time.sleep(0.5)
    if not pid():
        PIDFILE.unlink(missing_ok=True)


def restart():
    stop()
    schtasks("/Run", "/TN", TASK)


def remove():
    stop()
    schtasks("/Delete", "/TN", TASK, "/F")
    XML.unlink(missing_ok=True)


# ---------------------------------------------------------------- el lanzador (lo que corre la tarea)

def _stamp():
    return time.strftime("[%d/%m %H:%M:%S]")


def launch(python, script, home, log, pidfile=PIDFILE, popen=subprocess.Popen, sleep=time.sleep, rounds=None):
    """Corre el servidor sin ventana, con su salida al registro, y lo vuelve a arrancar a los 30 s si se cae (como
    Restart=always de systemd). rounds: cuántas veces (las pruebas); None = siempre."""
    env = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONUTF8": "1"}
    n = 0
    while rounds is None or n < rounds:
        n += 1
        Path(log).parent.mkdir(parents=True, exist_ok=True)
        with open(log, "ab") as out:
            try:
                proc = popen([str(python), "-X", "utf8", str(script), "servir"], cwd=str(home), env=env,
                             stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT,
                             creationflags=winapi.CREATE_NO_WINDOW)
            except OSError as e:
                out.write(f"{_stamp()} ✗ No se pudo arrancar el servidor: {e}\n".encode())
            else:
                Path(pidfile).write_text(str(proc.pid))
                code = proc.wait()
                Path(pidfile).unlink(missing_ok=True)
                out.write(f"{_stamp()} · El servidor terminó (código {code}); vuelve a arrancar en "
                          f"{RESTART_AFTER} s\n".encode())
        sleep(RESTART_AFTER)


def main():
    if sys.argv[1:] != ["lanzar"]:
        sys.exit("Uso: pythonw windowsservice.py lanzar   (lo corre la tarea «One TV»; no hace falta a mano)")
    if not winapi.single_instance(MUTEX):
        return   # ya hay un lanzador corriendo (por ejemplo, la tarea se pidió dos veces)
    job = winapi.kill_children_with_me()   # noqa: F841 - se guarda mientras viva el lanzador
    here = Path(__file__).resolve().parent
    exe = Path(sys.executable)
    python = exe.with_name("python.exe") if exe.name.lower() == "pythonw.exe" else exe
    try:
        launch(python, here / "cine.py", here.parent, hostos.LOG)
    except Exception:   # con pythonw no hay ventana: lo que pasó queda en el registro
        import traceback
        with open(hostos.LOG, "a", encoding="utf-8") as out:
            out.write(f"{_stamp()} ✗ El lanzador de la tarea se detuvo:\n{traceback.format_exc()}")
        raise


if __name__ == "__main__":
    main()
