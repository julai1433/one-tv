"""Prueba de humo del servidor de verdad: lo arranca con una biblioteca de ejemplo y revisa que responda.

    python3 pruebas/humo_servidor.py [--puerto 8794] [--dejar]

Hace todo en una carpeta temporal (también la carpeta personal: no toca tus datos ni tu caché) y con una copia del
programa (no escribe config.json en el repositorio). Con ffmpeg arma tres videos sintéticos de 160 s (426×240):
- H.264 + AAC en .mp4: va directo a la TV;
- H.264 + AC-3 5.1 en .mkv: se copia el video y se convierte el audio;
- HEVC de 10 bits + AAC en .mkv: se convierte todo (en Linux sin chip de video, con libx264).
Luego arranca «cine.py servir» y revisa /api/library, un póster, la lista HLS y un trozo de cada conversión (que sean
H.264 de verdad), y el código QR en PNG. El Roku se apunta a 127.0.0.1 a propósito: no busca ni toca ninguna TV.
Sale con código 1 si algo falla. Funciona en macOS, en Linux (ver pruebas/ubuntu.sh para correrla en Ubuntu) y en
Windows (ver pruebas/humo_windows.py).
"""

import argparse
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SECONDS = 160   # la biblioteca no muestra lo de menos de 150 s (muestras, menús)
fallas = []


def paso(ok, texto):
    print(("  ✓ " if ok else "  ✗ ") + texto, flush=True)
    if not ok:
        fallas.append(texto)
    return ok


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True, capture_output=True)


def videos(lib):
    src = ["-f", "lavfi", "-i", f"testsrc2=size=426x240:rate=24:duration={SECONDS}",
           "-f", "lavfi", "-i", f"sine=frequency=440:duration={SECONDS}"]
    h264 = ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-g", "48"]
    ffmpeg(*src, *h264, "-c:a", "aac", "-shortest", str(lib / "Prueba Directa (2020).mp4"))
    ffmpeg(*src, *h264, "-c:a", "ac3", "-ac", "6", "-shortest", str(lib / "Prueba Copia (2019).mkv"))
    ffmpeg(*src, "-c:v", "libx265", "-preset", "ultrafast", "-pix_fmt", "yuv420p10le", "-x265-params", "log-level=error",
           "-c:a", "aac", "-shortest", str(lib / "Prueba HEVC (2021).mkv"))


def get(base, path, timeout=60):
    with urllib.request.urlopen(base + path, timeout=timeout) as r:
        return r.status, r.headers.get("Content-Type", ""), r.read()


def codec_de(data, folder):
    f = folder / "trozo.ts"
    f.write_bytes(data)
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=codec_name,pix_fmt", "-of", "csv=p=0", str(f)], capture_output=True, text=True)
    return next((l for l in r.stdout.split() if l.strip()), "")   # (un .ts lo nombra también en su programa)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--puerto", type=int, default=8794)
    ap.add_argument("--dejar", action="store_true", help="no borrar la carpeta temporal (para mirar el registro)")
    args = ap.parse_args()
    if args.puerto == 8765:
        sys.exit("✗ El 8765 es el del servidor de verdad: usa otro puerto.")
    tmp = Path(tempfile.mkdtemp(prefix="one-tv-humo-"))
    casa, proyecto, lib = tmp / "casa", tmp / "proyecto", tmp / "biblioteca"
    for d in (casa, lib):
        d.mkdir()
    for sub in ("mac", "roku"):
        shutil.copytree(ROOT / sub, proyecto / sub, ignore=shutil.ignore_patterns("__pycache__"))
    (proyecto / "config.json").write_text(json.dumps({
        "carpetas": [str(lib)], "puerto": args.puerto, "roku_ip": "127.0.0.1", "roku_password": "",
        "musica": [], "descargas": [], "escuchar": "127.0.0.1"}))
    print(f"Carpeta temporal: {tmp}")
    print("Videos de prueba…", flush=True)
    t0 = time.time()
    videos(lib)
    print(f"  listos en {time.time() - t0:.1f} s")

    env = {k: v for k, v in os.environ.items() if not k.startswith("XDG_")}
    env.update({"HOME": str(casa), "CINE_NO_BROWSER": "1", "PYTHONUNBUFFERED": "1", "PYTHONUTF8": "1"})
    if os.name == "nt":   # en Windows la carpeta personal y la de datos vienen de estas (HOME no cuenta)
        env.update({"USERPROFILE": str(casa), "LOCALAPPDATA": str(casa / "AppData" / "Local")})
    log = open(tmp / "servidor.log", "wb")
    proc = subprocess.Popen([sys.executable, str(proyecto / "mac" / "cine.py"), "servir"], cwd=proyecto, env=env,
                            stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{args.puerto}"
    try:
        t0 = time.time()
        status = None
        while time.time() - t0 < 90 and proc.poll() is None:
            try:
                status = json.loads(get(base, "/api/status", timeout=2)[2])
                break
            except OSError:
                time.sleep(0.5)
        if not paso(status is not None, f"el servidor responde /api/status ({time.time() - t0:.1f} s)"):
            return
        _, _, body = get(base, "/api/library")
        data = json.loads(body)
        items = data["items"]
        modos = {it["title"]: it["mode"] for it in items.values()}
        paso(len(items) == 3, f"/api/library: {len(items)} videos {sorted(modos.items())}")
        por_modo = {it["mode"]: it for it in items.values()}
        paso(set(por_modo) == {"direct", "copy", "full"}, "un video de cada forma: directo, copia y conversión completa")

        it = por_modo.get("full") or next(iter(items.values()), None)
        if it:
            st, ctype, img = get(base, it["poster"])
            paso(st == 200 and img[:3] == b"\xff\xd8\xff", f"póster {it['poster']} ({ctype}, {len(img)} bytes)")

        for modo in ("full", "copy"):
            it = por_modo.get(modo)
            if not it:
                continue
            hls = it["audio"][0]["hls"]
            st, ctype, lista = get(base, hls)
            texto = lista.decode()
            paso(st == 200 and texto.startswith("#EXTM3U") and "seg0.ts" in texto,
                 f"lista HLS ({modo}): {texto.count('#EXTINF')} trozos")
            t1 = time.time()
            st, _, trozo = get(base, hls.replace("index.m3u8", "seg1.ts"), timeout=90)
            codec = codec_de(trozo, tmp)
            paso(st == 200 and len(trozo) > 10_000 and codec.startswith("h264"),
                 f"trozo convertido ({modo}): {len(trozo)} bytes, video {codec}, {time.time() - t1:.1f} s")

        st, ctype, png = get(base, "/yt/dQw4w9WgXcQ/qr.png")
        ok = st == 200 and png[:8] == b"\x89PNG\r\n\x1a\n"
        w, h = struct.unpack(">II", png[16:24]) if ok else (0, 0)
        paso(ok and (w, h) == (624, 624), f"código QR en PNG ({w}×{h}, {len(png)} bytes)")
    finally:
        # Primero sus procesos hijos (ffmpeg, caffeinate…): solo los de este servidor de prueba.
        if os.name == "nt":   # Windows: el servidor y todo lo que lanzó, de una vez
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
        else:
            subprocess.run(["pkill", "-TERM", "-P", str(proc.pid)], capture_output=True)
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()
        registro = (tmp / "servidor.log").read_text(encoding="utf-8", errors="replace")
        lineas = [l for l in registro.splitlines() if ("Video:" in l or "yt-dlp" in l or "✗" in l or "Traceback" in l)
                  and "SIGTERM" not in l]   # (yt-dlp a medio instalar cuando se apagó el servidor de prueba)
        print("Del registro del servidor:")
        for l in lineas[:12]:
            print("  " + l)
        if args.dejar or fallas:
            print(f"Registro completo: {tmp / 'servidor.log'}")
        if not args.dejar and not fallas:
            shutil.rmtree(tmp, ignore_errors=True)
    print("Todo bien." if not fallas else f"{len(fallas)} cosa(s) fallaron.")
    sys.exit(1 if fallas else 0)


if __name__ == "__main__":
    main()
