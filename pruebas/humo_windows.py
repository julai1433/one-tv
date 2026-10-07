"""Prueba de humo en Windows: lo mismo que en Ubuntu y lo propio de Windows.

    python pruebas/humo_windows.py [--puerto 8798] [--de-verdad]

1. El servidor de verdad con videos de prueba (pruebas/humo_servidor.py): catálogo, póster, conversión y código QR.
2. cine.cmd → windows\\cine.ps1 → Python: «cine estado» encuentra Python y ffmpeg y responde (sin preguntar nada).
3. Solo con --de-verdad: el arranque automático con el Programador de tareas de verdad. «cine autoarranque» registra
   la tarea «One TV» y el servidor arranca sin ventana (pythonw); si el servidor se cae, vuelve solo a los 30 s; «cine»
   aplica un cambio y lo reinicia; «cine quitar-autoarranque» lo detiene y quita la tarea. Usa la carpeta de datos de
   verdad (%LOCALAPPDATA%\\cine-roku), así que solo corre en una computadora de pruebas (GitHub Actions): si ahí ya hay
   un One TV instalado, no hace nada.
Sale con código 1 si algo falla. Sin TV: el Roku se apunta a 127.0.0.1.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "mac"))
TASK = "One TV"
fallas = []


def paso(ok, texto):
    print(("  ✓ " if ok else "  ✗ ") + texto, flush=True)
    if not ok:
        fallas.append(texto)
    return ok


def status(port, timeout=2):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=timeout) as r:
            return json.loads(r.read())
    except (OSError, ValueError):
        return None


def esperar(cond, seconds, every=1.0):
    end = time.time() + seconds
    while time.time() < end:
        got = cond()
        if got:
            return got
        time.sleep(every)
    return cond()


def correr(cmd, timeout=180, **kw):
    env = {**os.environ, "CINE_NO_BROWSER": "1", "PYTHONUTF8": "1", "ONE_TV_SIN_PREGUNTAS": "1", **kw.pop("env", {})}
    r = subprocess.run(cmd, capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL, env=env, **kw)
    return r.returncode, (r.stdout or b"").decode("utf-8", "replace") + (r.stderr or b"").decode("utf-8", "replace")


def humo_del_servidor(port):
    print("1) El servidor con videos de prueba", flush=True)
    r = subprocess.run([sys.executable, str(ROOT / "pruebas" / "humo_servidor.py"), "--puerto", str(port)],
                       env={**os.environ, "PYTHONUTF8": "1"})
    paso(r.returncode == 0, "pruebas/humo_servidor.py")


def cine_cmd():
    print("2) cine.cmd (PowerShell revisa Python y ffmpeg y arranca Python)", flush=True)
    code, out = correr(["cmd", "/c", str(ROOT / "cine.cmd"), "estado"], cwd=ROOT)
    paso(code == 0 and ("El servidor no está corriendo" in out or "Servidor funcionando" in out),
         f"«cine estado» responde (código {code})")
    if code != 0 or "Falta" in out:
        print("    " + out.strip().replace("\n", "\n    "))
    code, out = correr(["cmd", "/c", str(ROOT / "cine.cmd"), "barra"], cwd=ROOT)
    paso("en Windows no aplica" in out, "«cine barra» dice que en Windows no aplica, sin fallar")


def proceso(pid):
    """(nombre, nombre del padre) de un proceso, preguntándole a Windows."""
    script = (f"$p = Get-CimInstance Win32_Process -Filter 'ProcessId={int(pid)}'; "
              "$q = Get-CimInstance Win32_Process -Filter \"ProcessId=$($p.ParentProcessId)\"; "
              "Write-Output \"$($p.Name)|$($q.Name)\"")
    _, out = correr(["powershell", "-NoProfile", "-Command", script], timeout=60)
    name, _, parent = out.strip().partition("|")
    return name.lower(), parent.lower()


def autoarranque(port):
    import hostos
    import windowsservice
    print("3) Arranque automático con el Programador de tareas", flush=True)
    if (hostos.SERVICE_HOME / "config.json").exists() or windowsservice.XML.exists():
        paso(False, f"ya hay un One TV instalado en {hostos.SERVICE_HOME}: esta parte no se corre aquí")
        return
    tmp = Path(tempfile.mkdtemp(prefix="one-tv-tarea-"))
    proyecto, lib = tmp / "proyecto", tmp / "biblioteca"
    lib.mkdir(parents=True)
    for sub in ("mac", "roku"):
        shutil.copytree(ROOT / sub, proyecto / sub, ignore=shutil.ignore_patterns("__pycache__"))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=426x240:rate=24:duration=160",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=160", "-c:v", "libx264", "-preset", "ultrafast",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(lib / "Prueba Tarea (2020).mp4")],
                   check=True, capture_output=True)
    (proyecto / "config.json").write_text(json.dumps({
        "carpetas": [str(lib)], "puerto": port, "roku_ip": "127.0.0.1", "roku_password": "", "musica": [],
        "descargas": [], "escuchar": "127.0.0.1"}), encoding="utf-8")
    cine = [sys.executable, "-X", "utf8", str(proyecto / "mac" / "cine.py")]
    try:
        code, out = correr([*cine, "autoarranque"], cwd=proyecto)
        if not paso(code == 0 and "Servidor funcionando" in out, f"«cine autoarranque» (código {code})"):
            print("    " + out.strip().replace("\n", "\n    "))
            print(correr(["schtasks", "/Query", "/TN", TASK, "/V", "/FO", "LIST"])[1])
            return
        paso(correr(["schtasks", "/Query", "/TN", TASK])[0] == 0, "la tarea «One TV» está registrada")
        paso(status(port) is not None, "el servidor responde /api/status")
        pid = windowsservice.pid()
        if paso(pid is not None, f"el lanzador guardó el número del servidor ({pid})"):
            name, parent = proceso(pid)
            paso(name == "python.exe" and parent == "pythonw.exe",
                 f"el servidor ({name}) corre bajo el lanzador sin ventana ({parent})")
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)   # se «cae»
            paso(esperar(lambda: status(port) is None, 15), "el servidor se cayó a propósito")
            nuevo = esperar(lambda: (windowsservice.pid() not in (None, pid)) and status(port), 90)
            paso(bool(nuevo), "volvió a arrancar solo (a los 30 s)")
        (proyecto / "mac" / "_cambio_de_prueba.txt").write_text("x", encoding="utf-8")
        antes = windowsservice.pid()
        code, out = correr(cine, cwd=proyecto)   # «cine» con el autoarranque puesto: copia el cambio y reinicia
        paso(code == 0 and "reiniciando" in out and esperar(lambda: windowsservice.pid() not in (None, antes), 60),
             "«cine» aplica un cambio y reinicia el servidor")
        paso((hostos.SERVICE_HOME / "mac" / "_cambio_de_prueba.txt").exists(), "el cambio quedó copiado")
        code, out = correr([*cine, "quitar-autoarranque"], cwd=proyecto)
        paso(code == 0 and "Ya no arranca solo" in out, "«cine quitar-autoarranque»")
        paso(esperar(lambda: status(port) is None, 30), "el servidor se detuvo")
        paso(correr(["schtasks", "/Query", "/TN", TASK])[0] != 0, "la tarea ya no está")
        _, quedan = correr(["powershell", "-NoProfile", "-Command",
                            "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and "
                            "$_.CommandLine.Contains($env:LOCALAPPDATA + '\\cine-roku') -and "
                            "$_.Name -match 'python|ffmpeg' } | ForEach-Object { $_.Name }"], timeout=60)
        paso(not quedan.strip(), "no quedó ningún proceso del servidor" + (f" ({quedan.split()})" if quedan.strip() else ""))
    finally:
        if fallas:
            try:
                print("Del registro del servicio:\n  " + "\n  ".join(
                    hostos.LOG.read_text(encoding="utf-8", errors="replace").splitlines()[-25:]))
            except OSError:
                pass
        correr(["schtasks", "/End", "/TN", TASK])
        correr(["schtasks", "/Delete", "/TN", TASK, "/F"])
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--puerto", type=int, default=8798)
    ap.add_argument("--de-verdad", action="store_true", help="también el arranque automático (solo en una computadora "
                                                            "de pruebas: usa la carpeta de datos de verdad)")
    args = ap.parse_args()
    if os.name != "nt":
        sys.exit("✗ Esta prueba es para Windows (en macOS y Linux: pruebas/humo_servidor.py).")
    if args.puerto == 8765:
        sys.exit("✗ El 8765 es el del servidor de verdad: usa otro puerto.")
    humo_del_servidor(args.puerto)
    cine_cmd()
    if args.de_verdad:
        if not (os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS")):
            sys.exit("✗ --de-verdad solo en una computadora de pruebas (GitHub Actions): usa tu carpeta de datos real.")
        autoarranque(args.puerto - 1)
    print("Todo bien." if not fallas else f"{len(fallas)} cosa(s) fallaron.")
    sys.exit(1 if fallas else 0)


if __name__ == "__main__":
    main()
