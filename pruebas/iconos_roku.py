# Genera los íconos de la app del Roku (roku/images/): el Roku no dibuja SVG ni emojis, así que cada ícono
# es un PNG blanco sobre fondo transparente que la app tiñe con blendColor. También genera las piezas 9-patch
# (relleno y contornos con esquinas de 3 px, que en un Roku HD se ven de 2 px; el marco de foco de 6 px), los
# círculos de los canales y la sombra del aviso para saltar (ver DESIGN.md). El ícono y la pantalla de arranque
# de la app no salen de aquí.
# Trazos de Lucide (https://lucide.dev, licencia ISC), los mismos de la web. Se dibujan con Chrome sin ventana.
# Uso: python3 pruebas/iconos_roku.py
import base64, json, subprocess, sys, tempfile, time, urllib.request, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "mac"))
from live import CDP, find_chrome  # noqa: E402

OUT = ROOT / "roku" / "images"
SIZE = 64   # los íconos se dibujan a 64 px; en la tele se muestran de 36 a 56

ICONS = {
    "search": '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    "house": '<path d="M15 21v-8a1 1 0 0 0-1-1h-4a1 1 0 0 0-1 1v8"/><path d="M3 10a2 2 0 0 1 .709-1.528l7-5.999a2 2 0 0 1 2.582 0l7 5.999A2 2 0 0 1 21 10v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "languages": '<path d="m5 8 6 6"/><path d="m4 14 6-6 2-3"/><path d="M2 5h12"/><path d="M7 2h1"/><path d="m22 22-5-10-5 10"/><path d="M14 18h6"/>',
    "clapper": '<path d="M20.2 6 3 11l-.9-2.4c-.3-1.1.3-2.2 1.3-2.5l13.5-4c1.1-.3 2.2.3 2.5 1.3Z"/><path d="m6.2 5.3 3.1 3.9"/><path d="m12.4 3.4 3.1 4"/><path d="M3 11h18v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/>',
    "monitor-play": '<path d="M10 7.75a.75.75 0 0 1 1.142-.638l3.664 2.249a.75.75 0 0 1 0 1.278l-3.664 2.25a.75.75 0 0 1-1.142-.64z"/><path d="M12 17v4"/><path d="M8 21h8"/><rect x="2" y="3" width="20" height="14" rx="2"/>',
    "square-play": '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M9 9.003a1 1 0 0 1 1.517-.859l4.997 2.997a1 1 0 0 1 0 1.718l-4.997 2.997A1 1 0 0 1 9 14.996z"/>',
    "radio": '<path d="M4.9 19.1C1 15.2 1 8.8 4.9 4.9"/><path d="M7.8 16.2c-2.3-2.3-2.3-6.1 0-8.5"/><circle cx="12" cy="12" r="2"/><path d="M16.2 7.8c2.3 2.3 2.3 6.1 0 8.5"/><path d="M19.1 4.9C23 8.8 23 15.1 19.1 19"/>',
    "list-video": '<path d="M12 12H3"/><path d="M16 6H3"/><path d="M12 18H3"/><path d="m16 12 5 3-5 3v-6Z"/>',
    "play": '<polygon points="6 3 20 12 6 21 6 3" fill="white"/>',
    "list-start": '<path d="M16 12H3"/><path d="M16 18H3"/><path d="M10 6H3"/><path d="M21 18V8a2 2 0 0 0-2-2h-5"/><path d="m16 8-2-2 2-2"/>',
    "list-plus": '<path d="M11 12H3"/><path d="M16 6H3"/><path d="M16 18H3"/><path d="M18 9v6"/><path d="M21 12h-6"/>',
    "chevron-right": '<path d="m9 18 6-6-6-6"/>',
    "rotate-ccw": '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/>',
    "refresh": '<path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/>',
    "history": '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l4 2"/>',
    "pause": '<rect x="14" y="4" width="4" height="16" rx="1" fill="white"/><rect x="6" y="4" width="4" height="16" rx="1" fill="white"/>',
    "skip": '<polygon points="5 4 15 12 5 20 5 4" fill="white"/><line x1="19" x2="19" y1="5" y2="19"/>',
    "mic": '<path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" x2="12" y1="19" y2="22"/>',
    "audio": '<path d="M2 10v3"/><path d="M6 6v11"/><path d="M10 3v18"/><path d="M14 8v7"/><path d="M18 5v13"/><path d="M22 10v3"/>',
    "captions": '<rect width="18" height="14" x="3" y="5" rx="2" ry="2"/><path d="M7 15h4M15 15h2M7 11h2M13 11h4"/>',
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "sound": '<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/>',
    "mute": '<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><line x1="22" x2="16" y1="9" y2="15"/><line x1="16" x2="22" y1="9" y2="15"/>',
    "qr-code": '<rect width="5" height="5" x="3" y="3" rx="1"/><rect width="5" height="5" x="16" y="3" rx="1"/><rect width="5" height="5" x="3" y="16" rx="1"/><path d="M21 16h-3a2 2 0 0 0-2 2v3"/><path d="M21 21v.01"/><path d="M12 7v3a2 2 0 0 1-2 2H7"/><path d="M3 12h.01"/><path d="M12 3h.01"/><path d="M12 16v.01"/><path d="M16 12h1"/><path d="M21 12v.01"/><path d="M12 21v-1"/>',
    "repeat": '<path d="m17 2 4 4-4 4"/><path d="M3 11v-1a4 4 0 0 1 4-4h14"/><path d="m7 22-4-4 4-4"/><path d="M21 13v1a4 4 0 0 1-4 4H3"/>',
    "shuffle": '<path d="m18 14 4 4-4 4"/><path d="m18 2 4 4-4 4"/><path d="M2 18h1.973a4 4 0 0 0 3.3-1.7l5.454-7.6a4 4 0 0 1 3.3-1.7H22"/><path d="M2 6h1.972a4 4 0 0 1 3.6 2.2"/><path d="M22 18h-6.041a4 4 0 0 1-3.3-1.8l-.359-.45"/>',
    "tv": '<rect width="20" height="15" x="2" y="7" rx="2" ry="2"/><polyline points="17 2 12 7 7 2"/>',
    "user": '<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
    "info": '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
    "laptop": '<path d="M18 5a2 2 0 0 1 2 2v8.526a2 2 0 0 0 .212.897l1.068 2.127a1 1 0 0 1-.9 1.45H3.62a1 1 0 0 1-.9-1.45l1.068-2.127A2 2 0 0 0 4 15.526V7a2 2 0 0 1 2-2z"/><path d="M20.054 15.987H3.946"/>',
    # Guardar sin conexión: la marca de lo guardado en las tarjetas y el botón de la ficha.
    "download": '<path d="M12 15V3"/><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/>',
    # Canales de YouTube: anclar (y la marca de los anclados), desanclar, ocultar y volver a mostrar.
    "pin": '<path d="M12 17v5"/><path d="M9 10.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24V16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V7a1 1 0 0 1 1-1 2 2 0 0 0 0-4H8a2 2 0 0 0 0 4 1 1 0 0 1 1 1z"/>',
    "pin-off": '<path d="M12 17v5"/><path d="M15 9.34V7a1 1 0 0 1 1-1 2 2 0 0 0 0-4H7.89"/><path d="m2 2 20 20"/><path d="M9 9v1.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24V16a1 1 0 0 0 1 1h11"/>',
    "eye": '<path d="M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0"/><circle cx="12" cy="12" r="3"/>',
    # Favoritos (vacío y lleno) y «Agregar a lista»; subir y bajar en la fila.
    "heart": '<path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z"/>',
    "heart-filled": '<path fill="white" d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z"/>',
    "bookmark-plus": '<path d="m19 21-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16z"/><line x1="12" x2="12" y1="7" y2="13"/><line x1="15" x2="9" y1="10" y2="10"/>',
    "plus": '<path d="M5 12h14"/><path d="M12 5v14"/>',
    "arrow-up": '<path d="m5 12 7-7 7 7"/><path d="M12 19V5"/>',
    "arrow-down": '<path d="M12 5v14"/><path d="m19 12-7 7-7-7"/>',
    "x": '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
    # Reproductor: capítulo anterior (el siguiente es «skip»), ±10 s; recomendaciones: «No me interesa»; música.
    "skip-back": '<polygon points="19 20 9 12 19 4 19 20" fill="white"/><line x1="5" x2="5" y1="19" y2="5"/>',
    "rotate-cw": '<path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/>',
    "ban": '<circle cx="12" cy="12" r="10"/><path d="m4.9 4.9 14.2 14.2"/>',
    "music": '<path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>',
    "disc": '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="2"/>',
    "eye-off": '<path d="M10.733 5.076a10.744 10.744 0 0 1 11.205 6.575 1 1 0 0 1 0 .696 10.747 10.747 0 0 1-1.444 2.49"/><path d="M14.084 14.158a3 3 0 0 1-4.242-4.242"/><path d="M17.479 17.499a10.75 10.75 0 0 1-15.417-5.151 1 1 0 0 1 0-.696 10.75 10.75 0 0 1 4.446-5.143"/><path d="m2 2 20 20"/>',
}

PAGE = """<!doctype html><html><body><script>
function svgPng(inner, size) {
  const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="' + size + '" height="' + size + '" viewBox="0 0 24 24" ' +
    'fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' + inner + '</svg>';
  return new Promise(ok => {
    const img = new Image();
    img.onload = () => { const c = document.createElement('canvas'); c.width = c.height = size;
      c.getContext('2d').drawImage(img, 0, 0, size, size); ok(c.toDataURL('image/png')); };
    img.src = 'data:image/svg+xml;base64,' + btoa(svg);
  });
}
// 9-patch: borde de 1 px con marcas negras que dicen qué parte se estira (arriba e izquierda). La parte que
// se estira empieza donde terminan la esquina y el trazo, para que el contorno no engorde al estirarse.
function ninePatch(size, radius, stroke) {
  const n = size + 2, c = document.createElement('canvas'); c.width = c.height = n;
  const g = c.getContext('2d'), margin = Math.max(radius, stroke);
  g.beginPath();
  if (stroke) { const h = stroke / 2; g.roundRect(1 + h, 1 + h, size - stroke, size - stroke, Math.max(0, radius - h));
    g.strokeStyle = 'white'; g.lineWidth = stroke; g.stroke(); }
  else { g.roundRect(1, 1, size, size, radius); g.fillStyle = 'white'; g.fill(); }
  g.fillStyle = 'black';
  g.fillRect(1 + margin, 0, size - 2 * margin, 1);
  g.fillRect(0, 1 + margin, 1, size - 2 * margin);
  return c.toDataURL('image/png');
}
// Sombra suave (9-patch) para lo único que flota encima del video: el aviso para saltar.
function shadow(size, pad, blur) {
  const n = size + 2, c = document.createElement('canvas'); c.width = c.height = n;
  const g = c.getContext('2d');
  g.shadowColor = 'rgba(0,0,0,0.8)'; g.shadowBlur = blur;
  g.fillStyle = 'rgba(0,0,0,0.8)'; g.fillRect(1 + pad, 1 + pad, size - 2 * pad, size - 2 * pad);
  g.shadowColor = 'transparent'; g.fillStyle = 'black';
  const m = pad + blur;
  g.fillRect(1 + m, 0, size - 2 * m, 1);
  g.fillRect(0, 1 + m, 1, size - 2 * m);
  return c.toDataURL('image/png');
}
// Degradado blanco (la app lo tiñe con el color de fondo) para fundir el fotograma de la ficha.
function fade(w, h, horizontal) {
  const c = document.createElement('canvas'); c.width = w; c.height = h;
  const g = c.getContext('2d');
  const grad = horizontal ? g.createLinearGradient(0, 0, w, 0) : g.createLinearGradient(0, 0, 0, h);
  if (horizontal) { grad.addColorStop(0, 'rgba(255,255,255,1)'); grad.addColorStop(0.25, 'rgba(255,255,255,0.92)');
                    grad.addColorStop(1, 'rgba(255,255,255,0)'); }
  else { grad.addColorStop(0, 'rgba(255,255,255,0)'); grad.addColorStop(1, 'rgba(255,255,255,1)'); }
  g.fillStyle = grad; g.fillRect(0, 0, w, h); return c.toDataURL('image/png');
}
function circle(size, stroke) {
  const c = document.createElement('canvas'); c.width = c.height = size;
  const g = c.getContext('2d'); g.beginPath();
  if (stroke) { g.arc(size / 2, size / 2, size / 2 - stroke / 2, 0, Math.PI * 2); g.strokeStyle = 'white';
    g.lineWidth = stroke; g.stroke(); }
  else { g.arc(size / 2, size / 2, size / 2 - 1, 0, Math.PI * 2); g.fillStyle = 'white'; g.fill(); }
  return c.toDataURL('image/png');
}
</script></body></html>"""


def main():
    chrome = find_chrome()
    if not chrome:
        sys.exit("No encontré Chrome.")
    work = Path(tempfile.mkdtemp(prefix="cine-iconos-"))
    (work / "p.html").write_text(PAGE)
    proc = subprocess.Popen([chrome, "--headless=new", "--remote-debugging-port=0", f"--user-data-dir={work / 'perfil'}",
                             "--no-first-run", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        pf = work / "perfil" / "DevToolsActivePort"
        while not (pf.exists() and pf.read_text().strip()):
            time.sleep(0.1)
        port = int(pf.read_text().split()[0])
        cdp = CDP(json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version").read())["webSocketDebuggerUrl"])
        target = cdp.call("Target.createTarget", {"url": (work / "p.html").as_uri()})["targetId"]
        s = cdp.call("Target.attachToTarget", {"targetId": target, "flatten": True})["sessionId"]
        time.sleep(1)

        def js(expr):
            r = cdp.call("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True}, s)
            return r.get("result", {}).get("value")

        def save(name, data_url):
            (OUT / name).write_bytes(base64.b64decode(data_url.split(",", 1)[1]))

        (OUT / "icons").mkdir(parents=True, exist_ok=True)
        for name, inner in ICONS.items():
            save(f"icons/{name}.png", js(f"svgPng({json.dumps(inner)}, {SIZE})"))
        save("fill.9.png", js("ninePatch(16, 3, 0)"))          # botones, segmentos, etiquetas (esquinas de 3)
        save("line.9.png", js("ninePatch(16, 3, 3)"))          # contornos: botón secundario, segmento, huecos
        save("frame.9.png", js("ninePatch(16, 0, 3)"))         # contorno recto de paneles (aviso para saltar)
        save("focus.9.png", js("ninePatch(24, 3, 6)"))         # marco de foco limón
        save("shadow.9.png", js("shadow(128, 40, 20)"))       # sombra del aviso encima del video
        save("circle.png", js("circle(160, 0)"))              # canales de YouTube
        save("circle_line.png", js("circle(176, 3)"))         # hueco de un canal (fila vacía)
        save("circle_focus.png", js("circle(176, 6)"))        # foco de un canal (por dentro del círculo)
        for name in ("pill.9.png", "round.9.png", "ring.9.png", "placeholder.png"):   # piezas de la primera versión
            (OUT / name).unlink(missing_ok=True)
        save("fade_left.png", js("fade(256, 4, true)"))      # la ficha: el fotograma se funde a la izquierda
        save("fade_bottom.png", js("fade(4, 256, false)"))   # y hacia abajo
        print(f"{len(ICONS)} íconos y las piezas en {OUT}")
    finally:
        proc.terminate()
        try:
            proc.wait(5)
        except Exception:  # noqa: BLE001
            proc.kill()
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
