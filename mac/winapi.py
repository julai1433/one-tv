"""Lo que en Windows se le pide directamente al sistema (con ctypes, sin instalar nada). Lo usa mac/hostos.py.

- Las carpetas del usuario (Descargas, Videos, Música) donde de verdad están: pueden estar movidas a otro disco o
  en OneDrive. Se le preguntan a Windows (SHGetKnownFolderPath) y, si no responde, al registro («User Shell Folders»).
- Que la computadora no se duerma mientras se ve algo: SetThreadExecutionState, desde un hilo propio (el pedido vale
  mientras viva el hilo que lo hizo). Es lo que en macOS hace caffeinate.
- Pausar y seguir un proceso (ffmpeg que va muy adelantado): Windows no tiene SIGSTOP ni SIGCONT.
- Abrir un archivo para mandarlo sin impedir que otro lo borre o lo reemplace mientras tanto (en Windows, un archivo
  abierto de la forma normal no se puede borrar ni reemplazar: ffmpeg no podría renovar sus listas).
- Detener los ffmpeg que quedaron vivos de una vez anterior (en macOS y Linux: pkill).
- Para el arranque automático (mac/windowsservice.py): si un proceso sigue vivo, que los procesos hijos se cierren
  con el que los lanzó, y que no haya dos lanzadores a la vez.

Este módulo se puede importar en cualquier sistema (las pruebas lo hacen); las llamadas a Windows solo se hacen en
Windows.
"""

import os
import subprocess
import threading
import time
from pathlib import Path

# Carpetas conocidas de Windows: su identificador y su nombre en el registro («User Shell Folders»).
KNOWN_FOLDERS = {
    "DOWNLOAD": ("374DE290-123F-4565-9164-39C4925E467B", "{374DE290-123F-4565-9164-39C4925E467B}"),
    "VIDEOS": ("18989B1D-99B5-455B-841C-AB7C74E4DDFC", "My Video"),
    "MUSIC": ("4BD8D571-6D19-48D3-BE97-422220080E43", "My Music"),
}
SHELL_FOLDERS = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
PROCESS_SUSPEND_RESUME = 0x0800
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
STILL_ACTIVE = 259
GENERIC_READ = 0x80000000
FILE_SHARE_ALL = 0x1 | 0x2 | 0x4          # leer, escribir y borrar (o reemplazar) mientras está abierto
OPEN_EXISTING = 3
FILE_FLAG_SEQUENTIAL_SCAN = 0x08000000
ERROR_ALREADY_EXISTS = 183
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
CREATE_NO_WINDOW = 0x08000000


def _kernel32():
    import ctypes
    from ctypes import wintypes
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.OpenProcess.restype = wintypes.HANDLE
    k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    k.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    k.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                             ctypes.POINTER(wintypes.DWORD)]
    k.CreateFileW.restype = wintypes.HANDLE
    k.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD,
                              wintypes.DWORD, wintypes.HANDLE]
    k.CreateMutexW.restype = wintypes.HANDLE
    k.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    k.CreateJobObjectW.restype = wintypes.HANDLE
    k.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    k.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
    k.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    k.GetCurrentProcess.restype = wintypes.HANDLE
    k.SetThreadExecutionState.restype = ctypes.c_uint
    k.SetThreadExecutionState.argtypes = [ctypes.c_uint]
    return k


# ---------------------------------------------------------------- carpetas del usuario

def _known_folder(guid):
    """La ruta de una carpeta conocida de Windows (SHGetKnownFolderPath), o None."""
    import ctypes
    import uuid
    from ctypes import wintypes

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                    ("Data4", ctypes.c_ubyte * 8)]

    shell32, ole32 = ctypes.WinDLL("shell32"), ctypes.WinDLL("ole32")
    shell32.SHGetKnownFolderPath.restype = ctypes.c_long
    shell32.SHGetKnownFolderPath.argtypes = [ctypes.POINTER(GUID), wintypes.DWORD, wintypes.HANDLE,
                                             ctypes.POINTER(ctypes.c_wchar_p)]
    ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    rfid = GUID.from_buffer_copy(uuid.UUID(guid).bytes_le)
    out = ctypes.c_wchar_p()
    if shell32.SHGetKnownFolderPath(ctypes.byref(rfid), 0, None, ctypes.byref(out)) != 0:
        return None
    try:
        return out.value or None
    finally:
        ole32.CoTaskMemFree(out)


def _registry_folder(name):
    """La carpeta según el registro del usuario, con %USERPROFILE% y demás ya expandidos, o None."""
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, SHELL_FOLDERS) as key:
            value, _ = winreg.QueryValueEx(key, name)
    except OSError:
        return None
    return os.path.expandvars(value) if value else None


def user_folder(kind, known=None, registry=None):
    """Descargas, Videos o Música («DOWNLOAD», «VIDEOS», «MUSIC») donde estén de verdad, o None si Windows no lo dice."""
    guid, name = KNOWN_FOLDERS[kind]
    for ask, key in ((known or _known_folder, guid), (registry or _registry_folder, name)):
        try:
            path = ask(key)
        except (OSError, AttributeError, ImportError, ValueError):
            path = None
        if path and os.path.isabs(path):
            return Path(path)
    return None


# ---------------------------------------------------------------- que no se duerma

def _set_execution_state(flags):
    return _kernel32().SetThreadExecutionState(flags)


class KeepAwake:
    """Como server.KeepAwake (caffeinate en macOS), pero con SetThreadExecutionState: cada poke() asegura que la
    computadora no se duerma sola durante los próximos `seconds` segundos. Un hilo propio hace el pedido y lo retira
    al vencerse (Windows lo retira solo si el hilo termina). La pantalla sí se puede apagar."""

    def __init__(self, seconds=900, set_state=None):
        self.seconds = seconds
        self.set_state = set_state or _set_execution_state
        self.until = 0
        self.thread = None
        self.refused = False   # Windows no lo permitió: no se insiste
        self.lock = threading.Lock()

    def poke(self):
        with self.lock:
            self.until = time.time() + self.seconds
            if self.thread is None and not self.refused:
                self.thread = threading.Thread(target=self._hold, name="sin-dormir", daemon=True)
                self.thread.start()

    def _hold(self):
        try:
            self.set_state(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
        except (OSError, AttributeError):   # no se pudo pedir: el sistema decide cuándo dormir (como sin caffeinate)
            with self.lock:
                self.thread, self.refused = None, True
            return
        while True:
            with self.lock:
                left = self.until - time.time()
                if left <= 0:
                    self.thread = None
                    break
            time.sleep(min(left, 30))
        try:
            self.set_state(ES_CONTINUOUS)
        except (OSError, AttributeError):
            pass


# ---------------------------------------------------------------- procesos

def suspend(pid, pause):
    """Pausa (pause=True) o deja seguir a un proceso, como SIGSTOP y SIGCONT. ProcessLookupError si ya no está."""
    import ctypes
    k = _kernel32()
    nt = ctypes.WinDLL("ntdll")
    handle = k.OpenProcess(PROCESS_SUSPEND_RESUME, False, pid)
    if not handle:
        raise ProcessLookupError(pid)
    try:
        (nt.NtSuspendProcess if pause else nt.NtResumeProcess)(ctypes.c_void_p(handle))
    finally:
        k.CloseHandle(handle)


def process_alive(pid, prefix="python"):
    """¿Sigue vivo ese proceso y su programa empieza con `prefix`? (por si Windows ya le dio el número a otro)"""
    import ctypes
    from ctypes import wintypes
    k = _kernel32()
    handle = k.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        return False
    try:
        code = wintypes.DWORD()
        if not k.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value != STILL_ACTIVE:
            return False
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(len(buf))
        if k.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return Path(buf.value).name.lower().startswith(prefix)
        return True
    finally:
        k.CloseHandle(handle)


def stop_processes_using(text, image="ffmpeg.exe", run=subprocess.run):
    """Detiene los procesos `image` cuya línea de comandos menciona `text` (una carpeta de este servidor): los que
    quedaron vivos si la vez anterior se cerró a la fuerza. Primero mira rápido si hay alguno (tasklist); solo si hay,
    le pregunta a PowerShell por sus líneas de comandos."""
    try:
        out = run(["tasklist", "/FI", f"IMAGENAME eq {image}", "/FO", "CSV", "/NH"], capture_output=True,
                  timeout=20, stdin=subprocess.DEVNULL).stdout or b""
    except (OSError, subprocess.SubprocessError):
        return False
    if image.lower().encode() not in out.lower():
        return False
    script = (f"Get-CimInstance Win32_Process -Filter \"Name='{image}'\" | "
              "Where-Object { $_.CommandLine -and $_.CommandLine.Contains($env:ONE_TV_CARPETA) } | "
              "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }")
    try:
        run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True, timeout=60,
            stdin=subprocess.DEVNULL, env={**os.environ, "ONE_TV_CARPETA": str(text)})
    except (OSError, subprocess.SubprocessError):
        return False
    return True


def kill_children_with_me():
    """Mete a este proceso (y a todo lo que lance después) en un «job» de Windows que se cierra con él: si este
    proceso termina, por lo que sea, Windows cierra también a sus hijos (el servidor y sus ffmpeg). Devuelve el job
    (hay que guardarlo mientras el proceso viva) o None si no se pudo."""
    import ctypes
    from ctypes import wintypes

    class BASIC(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class IO(ctypes.Structure):
        _fields_ = [(n, ctypes.c_uint64) for n in ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                                                    "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class EXTENDED(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", BASIC), ("IoInfo", IO), ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t)]

    k = _kernel32()
    job = k.CreateJobObjectW(None, None)
    if not job:
        return None
    info = EXTENDED()
    info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not k.SetInformationJobObject(job, JOB_OBJECT_EXTENDED_LIMIT_INFORMATION, ctypes.byref(info),
                                     ctypes.sizeof(info)) or not k.AssignProcessToJobObject(job, k.GetCurrentProcess()):
        k.CloseHandle(job)
        return None
    return job


def single_instance(name):
    """Un candado con nombre para todo Windows: devuelve su identificador si es el primero, o None si otro proceso ya
    lo tiene (otro lanzador corriendo)."""
    import ctypes
    k = _kernel32()
    ctypes.set_last_error(0)
    handle = k.CreateMutexW(None, False, name)
    if not handle:
        return None
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        k.CloseHandle(handle)
        return None
    return handle


# ---------------------------------------------------------------- archivos

def open_shared(path):
    """Abre un archivo para leerlo dejando que, mientras tanto, otro lo borre o lo reemplace (como en macOS y Linux).
    OSError (FileNotFoundError, PermissionError…) si no se puede."""
    import ctypes
    import msvcrt
    k = _kernel32()
    handle = k.CreateFileW(str(path), GENERIC_READ, FILE_SHARE_ALL, None, OPEN_EXISTING, FILE_FLAG_SEQUENTIAL_SCAN,
                           None)
    if handle is None or handle == ctypes.c_void_p(-1).value:
        err = ctypes.get_last_error()
        raise OSError(None, ctypes.FormatError(err).strip(), str(path), err)
    try:
        fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    except OSError:
        k.CloseHandle(handle)
        raise
    return os.fdopen(fd, "rb")
