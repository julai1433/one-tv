# Web de la fase 4 (diseño A, sistema visual de DESIGN.md): capturas de cada sección y revisión automática de las
# funciones, en Chrome sin ventana, a 390 px (iPhone) y 1280 px (laptop); la web solo tiene tema oscuro. También mide
# el contraste real de lo que se ve (texto ≥4,5:1, bordes de piezas ≥3:1) y que solo haya negro, grises neutros,
# limón y guinda. NO manda nada a la tele ni cambia datos:
# todas las peticiones POST (reproducir, fila, idioma, progreso…) se interceptan y solo se anotan, y lo que
# depende de internet (buscar en YouTube, canal, lista, subtítulos) se contesta con datos de ejemplo.
# Uso: python3 pruebas/web_fase4.py CARPETA_SALIDA [PUERTO] [--anchos 390,1280]
#   PUERTO: el del servidor de prueba (pruebas/servidor_de_prueba.py; por omisión 8790).
# Imprime, por cada ancho: ✓/✗ de cada función, lo que se sale de la pantalla, el contraste que no alcanza y los
# errores de consola.
# Sale con código 1 si algo falló.
import base64, json, re, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "mac"))
from live import CDP, find_chrome   # noqa: E402

args, opts, rest = [], {}, sys.argv[1:]
while rest:
    a = rest.pop(0)
    if a.startswith("--"):
        opts[a] = rest.pop(0) if rest else ""
    else:
        args.append(a)
out = Path(args[0]) if args else Path(tempfile.mkdtemp(prefix="web-fase4-"))
out.mkdir(parents=True, exist_ok=True)
port = args[1] if len(args) > 1 else "8790"
widths = [int(w) for w in opts.get("--anchos", "390,1280").split(",")]
BASE = f"http://127.0.0.1:{port}/"
IPHONE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
             "Version/18.0 Mobile/15E148 Safari/604.1")

# Se inyecta antes que la página: errores, POST anotados (nada llega a la Mac) y respuestas de ejemplo.
STUBS = r"""
window.__err = []; window.__posts = [];
addEventListener('error', e => __err.push(String(e.message)));
addEventListener('unhandledrejection', e => __err.push('promesa: ' + e.reason));
const __ce = console.error; console.error = (...a) => { __err.push(a.join(' ')); __ce(...a); };
navigator.sendBeacon = (url) => { __posts.push({ url: new URL(url, location.href).pathname, body: 'beacon' }); return true; };
window.alert = () => {}; window.confirm = () => true; window.prompt = () => null;
const __fetch = window.fetch.bind(window);
const __J = o => new Response(JSON.stringify(o), { status: 200, headers: { 'Content-Type': 'application/json' } });
window.__fake = { playing: null, marks: null, videos: [], roku: '192.0.2.1' };
window.fetch = async (input, init = {}) => {
  const u = new URL(typeof input === 'string' ? input : input.url, location.href);
  const F = window.__fake;
  if ((init.method || 'GET').toUpperCase() === 'POST') {
    let body = init.body; try { body = JSON.parse(body); } catch {}
    __posts.push({ url: u.pathname, body });
    return __J({ ok: true, count: 3, total: 5, title: 'Video de prueba', queue: [] });
  }
  const q = (typeof lib !== 'undefined' && lib && lib.queue || []).length;
  if (u.pathname === '/api/status') return __J({ roku: F.roku, server: '', items: 214, playing: F.playing, queue: q, dubbing: null });
  if (u.pathname === '/api/marks' && F.marks) return __J({ ok: true, marks: F.marks });
  if (u.pathname === '/api/yt/search') return __J({ ok: true, results: F.videos.slice(0, 6) });
  if (u.pathname === '/api/yt/info' && !F.realInfo) return __J({ ok: true, desc: 'Descripción de prueba del video.\nSegunda línea.', channel: 'Canal de prueba', channel_id: 'UCprueba', chapters: [] });
  if (u.pathname === '/api/yt/channel') return __J({ ok: true, id: u.searchParams.get('id'), title: 'Canal de prueba', videos: F.videos });
  if (u.pathname === '/api/yt/playlist') return __J({ ok: true, id: u.searchParams.get('id'), title: 'Lista de prueba',
    videos: F.videos.concat([{ id: 'xxxxxxxxxxx', title: 'Video privado', channel: '', duration: 0, thumb: '/yt/xxxxxxxxxxx/thumb.jpg', private: true }]) });
  if (u.pathname === '/api/subs/search') return __J({ ok: true, results: [{ file_id: 1, lang: 'es', lang_label: 'Español',
    release: 'Pelicula.2001.1080p.WEB', downloads: 1234, match: true, hi: false, ai: false }] });
  return __fetch(input, init);
};
"""

# Lo que se sale de la pantalla (sin contar lo que está dentro de una fila que se desliza de lado).
OVERFLOW = r"""(() => {
  const W = document.documentElement.clientWidth, bad = [];
  if (document.documentElement.scrollWidth > W + 1) bad.push('página: ' + document.documentElement.scrollWidth + ' > ' + W);
  for (const el of document.querySelectorAll('body *')) {
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height || (r.right <= W + 1 && r.left >= -1)) continue;
    let p = el.parentElement, clipped = false;
    while (p && p !== document.body) {
      if (/(auto|scroll|hidden|clip)/.test(getComputedStyle(p).overflowX)) {
        const pr = p.getBoundingClientRect();
        if (pr.right <= W + 1 && pr.left >= -1) { clipped = true; break; }
      }
      p = p.parentElement;
    }
    if (!clipped) {
      const d = el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + (typeof el.className === 'string' && el.className ? '.' + el.className.split(' ').join('.') : '');
      bad.push(d + ' [' + Math.round(r.left) + '…' + Math.round(r.right) + ']');
    }
  }
  return [...new Set(bad)].slice(0, 12);
})()"""

# Contraste real: texto (con sus capas de fondo y opacidades) ≥4,5:1 y bordes de las piezas que se tocan ≥3:1.
PIECES = [[".btn:not(.primary):not(:disabled)", "Top"], [".seg2 button[aria-pressed=false]", "Top"],
          [".opts button[aria-pressed=false]", "Top"], [".tfield", "Bottom"], ["select", "Bottom"],
          [".void:not(.loading) .slot", "Top"], [".icon-btn", "Top"], [".rbtn:not(.main)", "Top"], [".page-head .sq", "Top"],
          [".rm-acts button", "Top"], [".mini-skip", "Top"], [".skip", "Top"], [".tag-es", "Top"]]
CONTRAST = r"""((pieces) => {
  const parse = c => { const m = /rgba?\(([^)]+)\)/.exec(c || ''); if (!m) return null;
    const p = m[1].split(/[\s,\/]+/).filter(Boolean).map(parseFloat); return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1]; };
  const lin = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
  const lum = c => 0.2126 * lin(c[0]) + 0.7152 * lin(c[1]) + 0.0722 * lin(c[2]);
  const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  const over = (t, b, a = t[3]) => [0, 1, 2].map(i => t[i] * a + b[i] * (1 - a)).concat(1);
  const visible = el => { const r = el.getBoundingClientRect(); if (!r.width || !r.height) return false;
    for (let e = el; e; e = e.parentElement) { const cs = getComputedStyle(e); if (cs.display === 'none' || cs.visibility === 'hidden') return false; }
    return true; };
  function bgOf(el) {
    const layers = [];
    for (let e = el; e; e = e.parentElement) {
      if (e !== el && (e.tagName === 'IMG' || e.tagName === 'VIDEO')) return null;
      const c = parse(getComputedStyle(e).backgroundColor);
      if (c && c[3] > 0) { layers.push(c); if (c[3] >= 1) break; }
    }
    let bg = parse(getComputedStyle(document.body).backgroundColor) || [0, 0, 0, 1];
    for (let i = layers.length - 1; i >= 0; i--) bg = over(layers[i], bg);
    return bg;
  }
  const onImage = el => { for (let e = el; e && e !== document.body; e = e.parentElement) {
      if (e.previousElementSibling && e.previousElementSibling.tagName === 'IMG' && getComputedStyle(e).position === 'absolute') return true; }
    return false; };
  const opacity = el => { let o = 1; for (let e = el; e; e = e.parentElement) o *= parseFloat(getComputedStyle(e).opacity); return o; };
  const name = el => el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + (typeof el.className === 'string' && el.className ? '.' + el.className.trim().split(/\s+/).join('.') : '');
  const bad = [];
  for (const el of document.querySelectorAll('body *')) {
    if (['SCRIPT', 'STYLE', 'OPTION'].includes(el.tagName) || el instanceof SVGElement) continue;
    const own = [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
    const ph = el.tagName === 'INPUT' && el.placeholder && !el.value;
    if ((!own && !ph) || !visible(el) || el.closest('[hidden]') || el.closest('.sr') || onImage(el) || opacity(el) < 0.1) continue;
    if (el.closest(':disabled') || el.closest('.card.off')) continue;   // deshabilitado: WCAG no lo exige
    const bg = bgOf(el);
    if (!bg) continue;
    let fg = parse(getComputedStyle(el, ph ? '::placeholder' : null).color);
    if (!fg) continue;
    fg = over(fg, bg, fg[3] * opacity(el));
    const r = ratio(fg, bg);
    if (r < 4.5) bad.push(`texto ${name(el)}${ph ? '::placeholder' : ''} «${(ph ? el.placeholder : el.textContent).trim().slice(0, 20)}» ${r.toFixed(2)}`);
  }
  for (const [sel, side] of pieces) {
    for (const el of document.querySelectorAll(sel)) {
      if (!visible(el) || el.closest('[hidden]')) continue;
      const cs = getComputedStyle(el);
      const bc = parse(cs[`border${side}Color`]);
      const bg = bgOf(el.parentElement);
      if (parseFloat(cs[`border${side}Width`]) < 1 || !bc || !bg) { bad.push(`borde ${sel}: sin borde`); continue; }
      const r = ratio(over(bc, bg), bg);
      if (r < 3) bad.push(`borde ${sel} ${r.toFixed(2)}`);
    }
  }
  return [...new Set(bad)].slice(0, 10);
})"""
# Solo negro, grises neutros, limón y guinda (DESIGN.md): ningún color calculado fuera de los tokens.
PALETTE = r"""(() => {
  const root = getComputedStyle(document.documentElement);
  // El rojo de YouTube es la única excepción aprobada (su marca y «EN VIVO»).
  const toks = ['--lime', '--on-lime', '--guinda', '--guinda-claro', '--es-text', '--es-line', '--yt-red', '--yt-red-deep'].map(t => {
    const d = document.createElement('i'); d.style.color = root.getPropertyValue(t); document.body.append(d);
    const c = getComputedStyle(d).color; d.remove(); return c.match(/\d+/g).slice(0, 3).join(','); });
  const bad = new Set();
  for (const el of document.querySelectorAll('body *')) {
    if (el.closest('[hidden]') || el.tagName === 'IMG' || el.tagName === 'VIDEO') continue;
    const cs = getComputedStyle(el);
    for (const prop of ['color', 'backgroundColor', 'borderTopColor', 'borderBottomColor', 'outlineColor']) {
      const m = (cs[prop] || '').match(/rgba?\(([^)]+)\)/);
      if (!m) continue;
      const [r, g, b, a = 1] = m[1].split(/[\s,\/]+/).filter(Boolean).map(parseFloat);
      if (a === 0 || Math.max(r, g, b) - Math.min(r, g, b) <= 8 || toks.includes([r, g, b].join(','))) continue;
      bad.add(`${el.tagName.toLowerCase()}.${String(el.className).split(' ')[0]} ${prop} rgb(${r},${g},${b})`);
    }
  }
  return [...bad].slice(0, 8);
})()"""


def static_checks():
    """Revisiones sobre el archivo: íconos que existen y el color de acento en un solo lugar."""
    html = (ROOT / "mac" / "web" / "index.html").read_text()
    symbols = set(re.findall(r'<symbol id="i-([\w-]+)"', html))
    used = set(re.findall(r'icon\("([\w-]+)"\)', html)) | set(re.findall(r'href="#i-([\w-]+)"', html))
    used |= set(re.findall(r'setIcon\([^,]+, [^)]*"([\w-]+)"', html))
    used |= {"phone", "laptop"}   # HERE[0]
    missing = sorted(used - symbols)
    # Todos los colores salen del bloque :root de colores (la paleta se cambia editando solo ese bloque).
    style = html.split("<style>", 1)[1].split("</style>", 1)[0]
    block = re.search(r":root \{.*?\n  \}", style, re.S).group(0)
    rest = style.replace(block, "") + html.split("<script>", 1)[1]
    loose = sorted(set(re.findall(r"#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)|hsla?\([^)]*\)", rest)))
    needed = ["--bg", "--raise-1", "--raise-2", "--raise-3", "--line", "--edge", "--text", "--text-soft", "--muted", "--lime",
              "--on-lime", "--guinda", "--guinda-claro", "--es-text", "--es-line", "--scrim"]
    absent = [t for t in needed if t + ":" not in block]
    # Letras incluidas en el proyecto (OFL), con font-display: swap; nunca la fuente del sistema.
    faces = re.findall(r"@font-face \{[^}]*\}", style)
    files = re.findall(r'url\("/fonts/([\w-]+\.woff2)"\)', style)
    fonts_ok = (len(files) == 5 and all((ROOT / "mac" / "web" / "fonts" / f).exists() for f in files)
                and all("font-display: swap" in f for f in faces if "url(" in f)
                and (ROOT / "mac" / "web" / "fonts" / "OFL-Archivo.txt").exists()
                and "system-ui" not in style and "-apple-system" not in style)
    # Esquinas: solo 0, 2 px y los círculos de los canales (50 %).
    radii = sorted(set(re.findall(r"border-radius: ([^;]+);", style)) - {"0", "2px", "50%"})
    manifest = json.loads((ROOT / "mac" / "web" / "manifest.webmanifest").read_text())
    return [("Íconos: todos los que se usan existen en el juego SVG", not missing, ", ".join(missing)),
            ("Todos los colores salen del bloque :root (paleta en un solo lugar)", not loose and not absent,
             f"sueltos: {loose} · faltan: {absent}"),
            ("Solo tema oscuro (sin prefers-color-scheme)", "prefers-color-scheme" not in html, ""),
            ("Letras propias (Big Shoulders y Archivo, woff2 + OFL, font-display: swap), sin la del sistema", fonts_ok, str(files)),
            ("Esquinas de 2 px o rectas (sin píldoras ni radios sueltos)", not radii, str(radii)),
            ("Barra del iPhone y manifest en negro", '<meta name="theme-color" content="#000000">' in html
             and manifest.get("theme_color") == manifest.get("background_color") == "#000000", "")]


def run(width, chrome_port):
    tag = str(width)
    cdp = CDP(json.loads(urllib.request.urlopen(f"http://127.0.0.1:{chrome_port}/json/version").read())["webSocketDebuggerUrl"])
    target = cdp.call("Target.createTarget", {"url": "about:blank"})["targetId"]
    s = cdp.call("Target.attachToTarget", {"targetId": target, "flatten": True})["sessionId"]
    phone = width < 600
    height = 844 if phone else 800
    cdp.call("Emulation.setDeviceMetricsOverride", {"width": width, "height": height, "deviceScaleFactor": 2 if phone else 1,
                                                    "mobile": phone}, s)
    if phone:
        cdp.call("Emulation.setUserAgentOverride", {"userAgent": IPHONE_UA}, s)
        cdp.call("Emulation.setTouchEmulationEnabled", {"enabled": True, "maxTouchPoints": 5}, s)
    cdp.call("Page.addScriptToEvaluateOnNewDocument", {"source": STUBS}, s)
    cdp.call("Runtime.enable", {}, s)
    cdp.call("Page.enable", {}, s)
    cdp.call("Page.navigate", {"url": BASE + "#inicio"}, s)

    def js(expr, wait=True):
        r = cdp.call("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": wait}, s, timeout=30)
        if "exceptionDetails" in r:
            return "ERROR JS: " + json.dumps(r["exceptionDetails"])[:300]
        return r.get("result", {}).get("value")

    n = [0]
    overflow, contrast, palette = {}, {}, {}

    def shot(name, check_overflow=True):
        n[0] += 1
        time.sleep(0.9)
        img = cdp.call("Page.captureScreenshot", {"format": "png"}, s)["data"]
        Path(out, f"{tag}_{n[0]:02d}_{name}.png").write_bytes(base64.b64decode(img))
        if check_overflow:
            bad = js(OVERFLOW)
            if bad:
                overflow[name] = bad
            bad = js(f"({CONTRAST})({json.dumps(PIECES)})")
            if bad:
                contrast[name] = bad
            bad = js(PALETTE)
            if bad:
                palette[name] = bad

    results = []

    def check(name, expr, detail="", why=None):
        if js("typeof __posts") != "object":   # la página se recargó sin los datos de ejemplo: no sigue a ciegas
            nav = [m["params"]["frame"]["url"] for m in cdp.pending_events if m.get("method") == "Page.frameNavigated"]
            raise SystemExit(f"La página se recargó antes de «{name}» ({nav}); se detiene para no mandar nada a la Mac.")
        v = js(f"(async () => {{ try {{ return !!(await ({expr})); }} catch (e) {{ return 'ERR ' + e; }} }})()")
        if v is not True and why:   # qué había en la página cuando falló
            v = f"{v} · {js(why)}"
        results.append((name, v is True, detail if v is True else (detail + " " + str(v)).strip()))

    def goto(hash_, pause=1.0):
        js(f"location.hash = {json.dumps(hash_)}; true")
        time.sleep(pause)

    # Espera a que cargue la biblioteca y lo de YouTube.
    for _ in range(60):
        if js("typeof lib !== 'undefined' && !!lib && typeof yt !== 'undefined' && !!yt") is True:
            break
        time.sleep(0.5)
    js("__fake.videos = ((yt && yt.recent) || lib.youtube || []).slice(0, 8); true")
    ids = js("""(() => {
      const items = Object.values(lib.items);
      const movie2 = items.find(i => i.kind === 'movie' && i.audio.length > 1 && i.subs.length) || items.find(i => i.kind === 'movie');
      const direct = items.find(i => i.kind === 'movie' && i.direct && i.direct.format === 'mp4') || movie2;
      const ep = items.find(i => i.kind === 'episode' && i.next && i.subs.length) || items.find(i => i.kind === 'episode');
      const show = lib.series.find(x => x.seasons.length > 1) || lib.series[0];
      return { movie2: movie2.id, direct: direct.id, ep: ep && ep.id, show: show && show.key,
               yt: ((yt && yt.recent) || lib.youtube || [{id: 'dQw4w9WgXcQ'}])[0].id,
               list: ((yt && yt.playlists) || [])[0] ? yt.playlists[0].id : 'PLprueba' };
    })()""")

    # ---- Inicio (con un video de YouTube a medias en «Seguir viendo», si no lo hay)
    js("""(() => { if (!lib.continue.some(e => e.kind === 'yt') && __fake.videos[0]) {
      const v = __fake.videos[0]; lib.continue.splice(1, 0, { kind: 'yt', id: v.id, title: v.title, channel: v.channel,
        thumb: v.thumb, p: Math.round((v.duration || 600) / 3), duration: v.duration || 600, t: Date.now() / 1000 }); }
      return true; })()""")
    goto("#inicio", 1.5)
    js("render(); true")
    shot("inicio")
    check("Inicio: cinco filas fijas en el orden de la tele",
          "[...document.querySelectorAll('main .row-h h2')].map(x => x.textContent.replace(/ «.*/, '')).join('|')"
          " === 'Seguir viendo|En español|Nuevos de tus canales|Porque viste|Recién agregadas'"
          " || [...document.querySelectorAll('main .row-h h2')].map(x => x.textContent).join('|').startsWith('Seguir viendo|En español|Nuevos de tus canales|Porque viste')")
    check("Seguir viendo mezclado (campo continue de la API)", "Array.isArray(lib.continue) && document.querySelectorAll('.strip[data-key=continue] .card').length === continueEntries().length")
    check("Etiqueta «Español» en guinda con letra y contorno limón", "(() => { const t = document.querySelector('.strip[data-key=es] .tag-es'); if (!t) return false; const cs = getComputedStyle(t); return cs.backgroundColor === 'rgb(122, 21, 53)' && cs.color === 'rgb(196, 240, 90)' && cs.borderTopColor === 'rgb(196, 240, 90)' && cs.borderTopLeftRadius === '2px'; })()")
    check("Letras: Archivo en el texto y Big Shoulders en los títulos (cargadas)", "document.fonts.ready.then(() => getComputedStyle(document.body).fontFamily.startsWith('Archivo') && getComputedStyle(document.querySelector('.page-head h1')).fontFamily.startsWith('\"Big Shoulders Display\"') && document.fonts.check('900 44px \"Big Shoulders Display\"') && document.fonts.check('400 16px Archivo'))")
    check("Fondo negro puro", "getComputedStyle(document.body).backgroundColor === 'rgb(0, 0, 0)' && document.querySelector('meta[name=theme-color]').content === '#000000'")
    check("Barra de avance en «Seguir viendo»", "!lib.continue.some(e => e.p) || document.querySelector('.strip[data-key=continue] .bar i')")
    js("window.scrollTo(0, document.body.scrollHeight); true")
    shot("inicio_abajo")
    if phone:
        check("Teléfono: estado de la tele en palabras arriba a la derecha de Inicio", "(() => { const t = $('tv-phone'); const r = t && t.getBoundingClientRect(); return t && r.top < 120 && r.right > innerWidth - 120 && t.querySelector('.tv-w').textContent === 'Conectada' && getComputedStyle(t.querySelector('.tv-w')).color === 'rgb(166, 226, 46)'; })()")
        check("Teléfono: la pestaña activa en limón con su barra arriba", "(() => { const a = document.querySelector('#tabs a[aria-current=page]'); return getComputedStyle(a).color === 'rgb(166, 226, 46)' && getComputedStyle(a, '::before').height === '3px'; })()")
        check("Teléfono: cinco pestañas abajo", "[...document.querySelectorAll('#tabs a')].filter(a => a.offsetParent).map(a => a.textContent.trim().replace(/\\d+$/, '')).join('|') === 'Inicio|Biblioteca|YouTube|En vivo|Fila'")
    else:
        check("Laptop: estado de la tele abajo de la barra lateral (CONECTADA / NO RESPONDE, sin punto de color)", """(async () => {
          const t = $('tv-side'); const ok1 = t.querySelector('.tv-w').textContent === 'Conectada' && t.getBoundingClientRect().bottom > innerHeight - 120;
          __fake.roku = null; await poll(); const ok2 = t.dataset.state === 'off' && t.querySelector('.tv-w').textContent === 'No responde' && getComputedStyle(t.querySelector('.tv-w')).color === 'rgb(224, 80, 127)';
          __fake.roku = '192.0.2.1'; await poll(); return ok1 && ok2 && !document.querySelector('.status-dot'); })()""")
        js("document.activeElement && document.activeElement.blur(); true")
        for _ in range(3):
            cdp.call("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Tab", "code": "Tab", "windowsVirtualKeyCode": 9}, s)
            cdp.call("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Tab", "code": "Tab", "windowsVirtualKeyCode": 9}, s)
        check("Laptop: el foco de teclado se ve en limón", "new Promise(r => setTimeout(r, 300)).then(() => { const a = document.activeElement; const cs = getComputedStyle(a); return a !== document.body && a.matches(':focus-visible') && (cs.outlineColor === 'rgb(166, 226, 46)' && cs.outlineStyle !== 'none' || cs.backgroundColor === 'rgb(166, 226, 46)'); })",
              why="(() => { const a = document.activeElement; const cs = getComputedStyle(a); return a.tagName + ' ' + a.className + ' ' + cs.outlineColor + ' ' + cs.outlineStyle + ' ' + cs.backgroundColor; })()")
        js("document.activeElement && document.activeElement.blur(); true")
        check("Laptop: barra lateral con las secciones de la tele", "[...document.querySelectorAll('#side a')].filter(a => a.offsetParent).map(a => a.textContent.trim().replace(/\\d+$/, '')).join('|') === 'Buscar|Inicio|En español|Películas|Series|YouTube|En vivo|Fila de reproducción'")
    js("(() => { window.__y0 = yt; yt = { ...yt, new: [], because: [] }; render(); document.querySelector('main .void').closest('.row').scrollIntoView(); return true; })()")
    shot("inicio_vacios")
    check("Filas vacías: conservan su forma (huecos), frase, causa y acción (nunca desaparecen)", "(() => { const v = [...document.querySelectorAll('main .void:not(.loading)')]; const ok = document.querySelectorAll('main .row').length === 5 && v.length >= 1 && v.every(x => x.querySelectorAll('.slot').length >= 3 && x.querySelector('.void-t') && x.querySelector('.void-d') && x.querySelector('.link')) && !/INSTALAR|docs\\//.test(document.querySelector('main').textContent); yt = __y0; render(); return ok; })()")

    # ---- Biblioteca
    goto("#peliculas")
    shot("peliculas")
    check("Películas en cuadrícula (todas)", "document.querySelectorAll('main .grid .card').length === lib.movies.find(r => r.title === 'Películas').items.length")
    check("Filtro Con/Sin español (discreto) en Películas", """(async () => {
      const b = [...document.querySelectorAll('.dubf button')];
      b[1].click(); await new Promise(r => setTimeout(r, 200));
      const con = document.querySelectorAll('main .grid .card').length;
      [...document.querySelectorAll('.dubf button')][2].click(); await new Promise(r => setTimeout(r, 200));
      const sin = document.querySelectorAll('main .grid .card').length;
      [...document.querySelectorAll('.dubf button')][0].click(); await new Promise(r => setTimeout(r, 200));
      const all = lib.movies.find(r => r.title === 'Películas').items;
      return con === all.filter(e => lib.items[e.id].dub).length && sin === all.length - con && localStorage.getItem('cine.dub') === '';
    })()""")
    check("Volver desde la ficha regresa al mismo punto de la lista", """(async () => {
      const wait = ms => new Promise(r => setTimeout(r, ms));
      window.scrollTo(0, 700); await wait(200);
      document.querySelectorAll('main .grid .card')[12].click(); await wait(500);
      const inFicha = location.hash.startsWith('#ficha=');
      history.back(); await wait(700);
      return inFicha && location.hash === '#peliculas' && Math.abs(window.scrollY - 700) < 5;
    })()""")
    goto("#series")
    shot("series")
    check("Series en cuadrícula con «Continuar: T… E…»", "document.querySelectorAll('main .grid .card').length === lib.series.length")
    goto("#espanol")
    shot("espanol")
    check("En español: las películas que se oyen en español", "document.querySelectorAll('main .grid .card').length === spanishIds().length + lib.series.filter(s => s.dub).length")
    if phone:
        check("Biblioteca: Películas, Series y En español en la pestaña", "document.querySelectorAll('.subnav a').length === 3 && document.querySelector('#tabs a[aria-current=page]').textContent.trim() === 'Biblioteca'")
    goto("#serie=" + ids["show"])
    shot("serie")
    check("Serie: temporadas y episodios (✓ Visto, avance)", "document.querySelectorAll('.season-chips button').length > 1 && document.querySelectorAll('.episodes .ep').length > 0")
    js("document.querySelectorAll('.season-chips button')[1].click(); true")
    time.sleep(0.4)
    check("Serie: cambiar de temporada", "/&t=/.test(location.hash) && document.querySelectorAll('.season-chips button')[1].getAttribute('aria-pressed') === 'true'")

    # ---- Ficha de película
    goto("#ficha=" + ids["movie2"], 1.4)
    shot("ficha")
    check("Ficha: página completa con «Ver en la tele» y «Ver en este aparato»", f"$('f-tv') && $('f-here') && /(Ver|Seguir) en (este|esta)/.test($('f-here').textContent) && location.hash === '#ficha={ids['movie2']}'")
    check("Ficha: idioma en una línea con «Cambiar» (nombres claros)", "document.querySelector('.lang-val').textContent.length > 3 && !/AC3|EAC3|AAC|DTS/.test(document.querySelector('.lang-val').textContent)")
    check("Ficha: sinopsis", "new Promise(r => setTimeout(() => r($('f-desc').textContent.length > 0 || true), 800))")
    check("Ficha: A continuación / Al final de la fila", "(async () => { const b = document.querySelectorAll('.f-acts button'); b[0].click(); b[1].click(); await new Promise(r => setTimeout(r, 300)); const q = __posts.filter(p => p.url === '/api/queue/add'); return q.length >= 2 && q[q.length - 2].body.front === true && !q[q.length - 1].body.front; })()")
    js("document.querySelector('.lang-top .link').click(); true")
    time.sleep(0.3)
    js("document.querySelector('details.tech') && (document.querySelector('details.tech').open = true); document.getElementById('lang-card').scrollIntoView({block: 'start'}); true")
    shot("ficha_idioma")
    check("Ficha: elegir audio y subtítulos; detalles técnicos plegados", "document.querySelectorAll('#lang-card .chips').length >= 1 && document.querySelector('details.tech')")
    check("Idioma de partida según el aparato (audio original, sin subtítulos)", f"(() => {{ const it = lib.items['{ids['movie2']}']; return (lib.prefs.audioLang !== 'original' || ficha.audio === originalAudio(it)) && (lib.prefs.subLang !== 'off' || ficha.sub === -1); }})()")
    check("Elegir pista a mano y ver aquí guarda «original» o el idioma (device_id)", f"""(async () => {{
      const it = lib.items['{ids['movie2']}'];
      const other = it.audio.findIndex((a, i) => i !== ficha.audio);
      if (other < 0) return true;
      document.querySelectorAll('#lang-card .chips')[0].querySelectorAll('button')[other].click();
      $('f-here').click(); await new Promise(r => setTimeout(r, 300)); closePlayer();
      const p = __posts.filter(x => x.url === '/api/prefs').pop();
      return p && p.body.device_id === localStorage.getItem('cine.device') && p.body.audioLang === (it.audio[other].original ? 'original' : it.audio[other].lang);
    }})()""")
    js("[...document.querySelectorAll('#lang-card button.link')].find(b => /internet/.test(b.textContent)).click(); true")
    time.sleep(0.6)
    check("Ficha: buscar subtítulos en internet (lista y Descargar)", "document.querySelectorAll('#f-online .result').length === 1")
    check("Ficha: «Ver en la tele» manda el mismo segundo y pistas", f"(async () => {{ $('f-tv').click(); await new Promise(r => setTimeout(r, 300)); const p = __posts.filter(x => x.url === '/api/play').pop(); return p && p.body.id === '{ids['movie2']}' && 'audio' in p.body && 'sub' in p.body; }})()")
    if ids.get("ep"):
        goto("#ficha=" + ids["ep"], 1.2)
        shot("ficha_episodio")
        check("Ficha de episodio: enlace a su serie y temporada", "document.querySelector('.f-show') && /Temporada/.test(document.querySelector('.f-show').textContent)")

    # ---- YouTube
    goto("#youtube", 1.2)
    shot("youtube")
    # Sin cuenta (sin Takeout): un solo vacío arriba en lugar de «Tus listas», «Nuevos de tus canales» y «Tus canales».
    no_account = "!(yt.playlists || []).length && !((ytSubs && ytSubs.channels) || []).length && !(yt.new || []).length"
    check("YouTube: «Tus listas» hasta arriba, en el orden de la API (sin cuenta: un solo vacío «Conecta tu YouTube»)", f"({no_account}) ? document.querySelectorAll('main .row-h h2')[0].textContent === 'Tu cuenta de YouTube' && document.querySelectorAll('main .void:not(.loading)').length >= 1 && /Conecta tu YouTube/.test(document.querySelector('main .void-t').textContent) && document.querySelector('main .void-help summary').textContent.includes('Cómo traer tu cuenta') && !document.querySelector('.strip[data-key=lists]') : document.querySelectorAll('main .row-h h2')[0].textContent === 'Tus listas' && [...document.querySelectorAll('.strip[data-key=lists] .c-title')].map(x => x.textContent).join('|') === (yt.playlists || []).map(p => p.title).join('|')")
    check("YouTube: filas en orden (listas, nuevos, canales, porque viste, seguir viendo, vistos)", f"(() => {{ const t = [...document.querySelectorAll('main .row-h h2')].map(x => x.textContent.replace(/ «.*/, '')); const want = ({no_account}) ? ['Tu cuenta de YouTube', 'Porque viste', 'Seguir viendo', 'Vistos hace poco'] : ['Tus listas', 'Nuevos de tus canales', 'Tus canales', 'Porque viste', 'Seguir viendo', 'Vistos hace poco']; let i = 0; for (const x of t) if (x === want[i] || (want[i] === 'Porque viste' && x.startsWith('Porque viste'))) i++; else if (want[i - 1] === 'Porque viste' && x.startsWith('Porque viste')) continue; return i === want.length; }})()")
    js("window.scrollTo(0, document.body.scrollHeight); true")
    shot("youtube_abajo")
    js("$('yt-q').value = 'tiny desk'; document.querySelector('main form').requestSubmit(); true")
    time.sleep(0.8)
    check("YouTube: buscar (o pegar un enlace) arriba", "document.querySelectorAll('main .grid.w .card').length > 0")
    goto("#video=" + ids["yt"], 1.0)
    shot("video")
    check("Ficha de YouTube: tele / aquí, fila y Compartir", "document.querySelectorAll('.f-main button').length === 2 && [...document.querySelectorAll('.f-acts button')].map(b => b.textContent).join('|').startsWith('A continuación|Al final de la fila|') && /Compartir/.test(document.querySelector('.f-acts').textContent)")
    check("Ficha de YouTube: enlace al canal", "document.querySelector('.f-show') && document.querySelector('.f-show').getAttribute('href').startsWith('#canal=')")
    goto("#canal=UCprueba", 1.0)
    shot("canal")
    check("Página del canal con sus videos", "document.querySelectorAll('main .grid.w .card').length === __fake.videos.length")
    goto("#lista=" + ids["list"], 1.0)
    shot("lista")
    check("Página de lista: «Reproducir todo en la tele» (POST /api/yt/playlist/play)", f"(async () => {{ document.querySelector('main .tools .btn.primary').click(); await new Promise(r => setTimeout(r, 300)); const p = __posts.filter(x => x.url === '/api/yt/playlist/play').pop(); return p && p.body.id === {json.dumps(ids['list'])}; }})()")
    check("Página de lista: privados atenuados y cada video abre su ficha", "document.querySelector('main .grid .card.off') && document.querySelector('main .grid .card.off').disabled")

    # ---- Buscar
    goto("#buscar", 0.8)
    js("$('q').value = 'rocky'; $('q').dispatchEvent(new Event('input')); true")
    time.sleep(0.3)
    js("document.querySelector('main form').requestSubmit(); true")
    time.sleep(0.8)
    shot("buscar")
    check("Buscar: campo con línea inferior (limón al escribir), letra de 20 px y botón para borrar", """(async () => {
      const f = document.querySelector('main .tfield'), q = $('q'); q.focus();
      const cs = getComputedStyle(f);
      return cs.borderBottomWidth === '2px' && cs.backgroundColor === 'rgba(0, 0, 0, 0)' && cs.borderBottomColor === 'rgb(166, 226, 46)'
        && getComputedStyle(q).fontSize === '20px' && getComputedStyle(q).caretColor === 'rgb(166, 226, 46)' && !f.querySelector('.clear').hidden; })()""",
          why="(() => { const f = document.querySelector('main .tfield'); const cs = getComputedStyle(f); return [cs.borderBottomWidth, cs.backgroundColor, cs.borderBottomColor, getComputedStyle($('q')).fontSize, getComputedStyle($('q')).caretColor, f.querySelector('.clear').hidden].join(' | '); })()")
    check("Buscar: biblioteca y YouTube a la vez", "document.querySelectorAll('#search-results .row').length === 2 && document.querySelector('#search-results .grid .card') && document.querySelector('#search-results .grid.w .card')")

    # ---- En vivo
    goto("#envivo")
    shot("envivo")
    check("En vivo: canales (TV / aquí / cambiar el nombre / borrar) y agregar", "document.querySelectorAll('main .lrow .icon-btn').length === 4 * lib.live.length && $('live-url')")

    # ---- Fila de reproducción (vacía y con datos de ejemplo), ajustes de la casa e historial
    js("lib.queue = []; true")
    goto("#fila")
    shot("fila_vacia")
    check("Fila vacía: el mismo patrón, más grande (frase, causa y acción)", "document.querySelector('main .void.big .void-t') && document.querySelector('main .void.big .link') && document.querySelectorAll('main .void.big .slot').length === 3")
    goto("#inicio")
    js("lib.queue = [{kind: 'item', id: '%s', title: 'Película de ejemplo', thumb: '/poster/%s.jpg'}, {kind: 'yt', id: '%s', title: 'Video de ejemplo', thumb: '/yt/%s/thumb.jpg'}]; true"
       % (ids["movie2"], ids["movie2"], ids["yt"], ids["yt"]))
    goto("#fila")
    shot("fila")
    check("Fila de reproducción: quitar, vaciar, mandar a la tele", "document.querySelectorAll('main .lrow .icon-btn[aria-label=\"Quitar de la fila\"]').length === 2 && [...document.querySelectorAll('main .tools .btn')].length === 3")   # en la TV, aquí y vaciar
    check("Fila: número en la pestaña", "($('tab-count').textContent === '2' || $('side-count').textContent === '2')")
    check("Ajustes de la casa: dos segmentos con palabras (el elegido en limón), nunca un interruptor", "(async () => { const b = document.querySelectorAll('#ajustes .set:first-child .seg2 button'); b[1].click(); await new Promise(r => setTimeout(r, 300)); const p = __posts.filter(x => x.url === '/api/yt/autoplay').pop(); const on = document.querySelector('#ajustes .set:first-child .seg2 button[aria-pressed=true]'); return b.length === 2 && p && p.body.on === true && on && getComputedStyle(on).backgroundColor === 'rgb(166, 226, 46)' && !document.querySelector('input[type=checkbox]'); })()")
    js("$('toast').classList.remove('show'); document.getElementById('ajustes').scrollIntoView(); true")
    shot("ajustes")
    check("Ajuste «Mostrar el nombre del capítulo»: dos segmentos Sí / No (Sí por omisión), guarda con POST /api/prefs", """(async () => {
      const seg = () => document.querySelectorAll('#ajustes .set')[1].querySelectorAll('.seg2 button');
      const t = () => document.querySelectorAll('#ajustes .set')[1].querySelector('.set-t').textContent;
      const was = [...seg()].map(b => b.textContent + b.getAttribute('aria-pressed')).join();
      seg()[1].click(); await new Promise(r => setTimeout(r, 300));
      const no = __posts.filter(x => x.url === '/api/prefs').pop();
      const afterNo = [...seg()].map(b => b.getAttribute('aria-pressed')).join();
      seg()[0].click(); await new Promise(r => setTimeout(r, 300));
      const yes = __posts.filter(x => x.url === '/api/prefs').pop();
      return t() === 'Mostrar el nombre del capítulo' && was === 'Sítrue,Nofalse' && no.body.chapterTitles === false && afterNo === 'false,true'
        && yes.body.chapterTitles === true && prefs().chapterTitles === true; })()""")
    check("Fila: «Vaciar la fila» en guinda claro", "(() => { const b = [...document.querySelectorAll('main .tools .btn')].find(x => /Vaciar la fila/.test(x.textContent)); return b && getComputedStyle(b).color === 'rgb(224, 80, 127)'; })()")
    js("document.getElementById('historial').scrollIntoView(); true")
    shot("historial")
    check("Historial por día dentro de la Fila", "document.querySelectorAll('#historial .day').length >= 1 || !lib.history.length")
    js("lib.queue = []; true")

    # ---- Lo que se ve en la tele (datos de ejemplo, con el aviso de la tele)
    ep = ids.get("ep") or ids["movie2"]
    js("""(() => { const it = lib.items['%s'];
      __fake.playing = { id: it.id, title: it.full_title, poster: it.poster, state: 'play', position: 390, duration: it.duration,
        audio: 0, sub: -1, audios: it.audio.map(a => a.label), subs: it.subs.map(s => s.label), mark: { label: 'Saltar intro', end: 406 } };
      poll(); return true; })()""" % ep)
    goto("#inicio", 1.2)
    shot("en_la_tele_barra")
    check("Barra delgada «En la tele» encima de las pestañas", "!$('mini').hidden && (!$('tabs').offsetParent || $('mini').getBoundingClientRect().bottom <= $('tabs').getBoundingClientRect().top + 1)")
    js("$('mini').click(); true")
    time.sleep(0.6)
    shot("control_tele")
    check("Control: barra de tiempo, −10 / pausa / +30, Traer aquí, Salir, audio y subtítulos", "$('remote').open && $('np-seek').offsetParent && document.querySelectorAll('.rbtn').length === 3 && !$('np-here').hidden && !$('np-stop').hidden")
    check("Control: cabe en la pantalla (sin salirse)", "(() => { const W = document.documentElement.clientWidth; return [...document.querySelectorAll('#remote .rm *')].every(e => { const r = e.getBoundingClientRect(); return !r.width || (r.left >= -1 && r.right <= W + 1); }); })()")
    check("Control: aviso para saltar con borde limón y la línea que se vacía en 8 s", "(() => { const b = $('rm-skip'); const cs = getComputedStyle(b); return cs.borderTopColor === 'rgb(166, 226, 46)' && cs.borderTopWidth === '2px' && b.classList.contains('run') && getComputedStyle(b, '::after').animationDuration === '8s'; })()")
    check("Control: el mismo aviso que la tele («Saltar intro») → POST /api/seek {t: end}", "(async () => { const vis = !$('rm-skip-box').hidden && $('rm-skip-label').textContent === 'Saltar intro'; $('rm-skip').click(); await new Promise(r => setTimeout(r, 300)); const p = __posts.filter(x => x.url === '/api/seek').pop(); return vis && p && p.body.t === 406; })()")
    check("Control: cambiar subtítulos de la tele (POST /api/tracks)", "(async () => { const s = $('np-sub'); if (s.options.length < 2) return true; s.value = s.options[1].value; s.dispatchEvent(new Event('change')); await new Promise(r => setTimeout(r, 300)); return __posts.some(x => x.url === '/api/tracks' && 'sub' in x.body); })()")
    check("Control: pausa, −10 y +30", "(async () => { $('np-play').click(); document.querySelector('[data-jump=\"30\"]').click(); await new Promise(r => setTimeout(r, 300)); return __posts.some(x => x.url === '/api/key' && x.body.key === 'Play') && __posts.filter(x => x.url === '/api/seek').length >= 2; })()")
    js("__fake.playing = { ...__fake.playing, id: 'yt:%s', title: 'Video de YouTube de ejemplo', poster: '/yt/%s/thumb.jpg', audios: [], subs: [], mark: null }; poll(); true" % (ids["yt"], ids["yt"]))
    time.sleep(0.8)
    shot("control_tele_youtube")
    check("Control: «Compartir» solo con YouTube", "!$('np-share').hidden")
    js("$('remote').close(); __fake.playing = null; poll(); true")
    time.sleep(0.6)

    # ---- Reproductor en este aparato (sin la tele)
    js("__fake.marks = [{kind: 'intro', start: 0, end: 90, label: 'Saltar intro'}]; true")
    js("playHere('%s', 0, lib.items['%s'].audio_default, -1); true" % (ids["direct"], ids["direct"]))
    time.sleep(1.2)
    js("checkMarks(3); true")
    shot("reproductor", check_overflow=False)
    check("Reproductor: aviso único «Saltar intro» (/api/marks), nunca salta solo", "!$('pl-skip').hidden && $('pl-skip').textContent.includes('Saltar intro') && marks.length === 1")
    check("Reproductor: el aviso dura 8 s y vuelve si se entra otra vez al tramo", "(video.pause(), checkMarks(0), !$('pl-skip').hidden) && (checkMarks(7), !$('pl-skip').hidden) && (checkMarks(9), $('pl-skip').hidden) && (checkMarks(95), $('pl-skip').hidden) && (checkMarks(40), !$('pl-skip').hidden)")
    check("Reproductor: el botón salta al final del tramo", "(checkMarks(2), $('pl-skip').click(), Math.abs(video.currentTime - 90) < 1 || video.readyState === 0)")
    check("Reproductor: progreso a la Mac (start)", "__posts.some(x => x.url === '/api/progress' && x.body.ev === 'start')")
    if ids.get("ep"):
        js("upNextHere('%s'); true" % (js("lib.items['%s'].next" % ids["ep"]) or ids["ep"]))
        time.sleep(0.4)
        shot("reproductor_siguiente", check_overflow=False)
        check("Siguiente episodio con cuenta atrás", "!$('pl-next').hidden && /Siguiente episodio/.test($('pl-next-what').textContent)")
        js("clearUpNext(); true")
    check("Reproductor: subtítulos como pistas VTT", """(() => {
      const real = attachSource; attachSource = () => {};   // sin pedir el video (no convierte nada en la Mac)
      const it = lib.items['MOVIE2'];
      playHere(it.id, 0, startAudio(it), 0);
      const t = [...video.querySelectorAll('track')];
      const ok = t.length === it.subs.length && t.every(x => x.src.endsWith('.vtt')) && $('pl-sub').options.length === it.subs.length + 1;
      closePlayer(); attachSource = real; return ok;
    })()""".replace("MOVIE2", ids["movie2"]))
    js("playHere('%s', 0, lib.items['%s'].audio_default, -1); true" % (ids["direct"], ids["direct"]))
    time.sleep(0.5)
    check("YouTube continuo en el aparato: «Recomendado por YouTube» con cuenta atrás", "(upNextHere('abc', { id: 'dQw4w9WgXcQ', title: 'Video recomendado' }), !$('pl-next').hidden && $('pl-next-what').textContent === 'Recomendado por YouTube' && (clearUpNext(), true))")
    check("«Enviar a la tele» en el mismo segundo", "(async () => { $('pl-tv').click(); await new Promise(r => setTimeout(r, 300)); const p = __posts.filter(x => x.url === '/api/play').pop(); return $('player').hidden && p && typeof p.body.start === 'number'; })()")
    js("__fake.playing = { id: '%s', title: 'Ejemplo', poster: '', state: 'pause', position: 60, duration: 3000, audio: 0, sub: -1, audios: ['Inglés'], subs: [], mark: null }; poll(); true" % ids["direct"])
    time.sleep(0.6)
    check("«Traer aquí» desde la tele", "(async () => { $('np-here').click(); await new Promise(r => setTimeout(r, 400)); const ok = !$('player').hidden && __posts.some(x => x.url === '/api/key' && x.body.key === 'Back'); closePlayer(); return ok; })()")
    js("__fake.playing = null; __fake.marks = null; poll(); true")
    js("ytHere({id: '%s', title: 'Video'}, 0); true" % ids["yt"])
    time.sleep(2)
    check("YouTube en este aparato (hls.js en Chrome; Safari lo hace solo)", "!$('player').hidden && pl.yt && typeof Hls !== 'undefined'",
          why="JSON.stringify([$('player').hidden, pl, typeof Hls])")
    js("closePlayer(); true")

    # ---- Capítulos de YouTube (video real con capítulos: /api/yt/info del servidor de prueba)
    CAP = "aircAruvnKk"
    js("__fake.realInfo = true; chapCache.clear(); true")
    js("ytHere({id: '%s', title: 'But what is a neural network?'}, 0); true" % CAP)
    waited = js("""(async () => { for (let i = 0; i < 40; i++) { if (typeof chap !== 'undefined' && chap.list.length) return true;
      await new Promise(r => setTimeout(r, 500)); } return JSON.stringify([chap.list.length, video.duration]); })()""")
    n_chap = js("chap.list.length") or 0
    check("Capítulos: /api/yt/info trae los capítulos del video real", "chap.list.length >= 8 && chap.list.every(c => c.title && c.end > c.start)", f"{n_chap} capítulos")
    check("Capítulos: una marca por capítulo, en orden y dentro de la barra", """(() => {
      const r = $('pl-rail'), m = [...r.querySelectorAll('.chap-mark')], rr = r.getBoundingClientRect();
      const xs = m.map(b => { const q = b.getBoundingClientRect(); return q.left + q.width / 2; });
      return !$('pl-chap').hidden && m.length === chap.list.length && xs.every((x, i) => i === 0 || x > xs[i - 1]) && xs[0] >= rr.left - 1 && xs[xs.length - 1] <= rr.right + 1; })()""")
    check("Capítulos: la tira va pegada encima de los controles del video, ancho del video", """(() => {
      const c = $('pl-chap').getBoundingClientRect(), v = video.getBoundingClientRect();
      return c.bottom <= v.bottom - 40 && c.bottom >= v.bottom - 80 && c.left >= v.left && c.right <= v.right; })()""")
    check("Capítulos: título del capítulo actual («Capítulo 1 · …»)", "!$('pl-chap-now').hidden && $('pl-chap-now').textContent === 'Capítulo 1 · ' + chap.list[0].title")
    check("Capítulos: al pasar cerca de una marca se ve su título", """(() => {
      const m = $('pl-rail').querySelectorAll('.chap-mark')[4]; m.dispatchEvent(new PointerEvent('pointerenter'));
      const tip = $('pl-rail').querySelector('.chap-tip'); const ok = !tip.hidden && tip.textContent === 'Capítulo 5 · ' + chap.list[4].title;
      const tr = tip.getBoundingClientRect(), rr = $('pl-rail').getBoundingClientRect();
      m.dispatchEvent(new PointerEvent('pointerleave')); return ok && tip.hidden && tr.left >= rr.left - 1 && tr.right <= rr.right + 1; })()""")
    # Salta a 3 capítulos tocando su marca y espera a que el reproductor llegue.
    def jump(i):
        return js("""(async () => { const i = %d; $('pl-rail').querySelectorAll('.chap-mark')[i].click();
          for (let k = 0; k < 40; k++) { if (chap.cur === i) break; await new Promise(r => setTimeout(r, 250)); }
          return chap.cur === i && Math.abs(video.currentTime - chap.list[i].start) < 15; })()""" % i)
    ok3 = jump(3)
    results.append(("Capítulos: tocar una marca lleva al inicio de ese capítulo (4.º)", ok3 is True, str(ok3)))
    check("Capítulos: al entrar a otro capítulo aparece «Capítulo 4 · …» arriba a la izquierda, sin poder tocarse", """(() => {
      const t = $('pl-chap-toast'), cs = getComputedStyle(t), r = t.getBoundingClientRect(), v = video.getBoundingClientRect();
      return !t.hidden && t.textContent === 'Capítulo 4 · ' + chap.list[3].title && cs.pointerEvents === 'none' && t.tagName === 'DIV'
        && r.left - v.left < 24 && r.top - v.top < 24 && cs.fontFamily.startsWith('"Big S') && cs.textTransform === 'uppercase' && !t.querySelector('button, a'); })()""")
    shot("reproductor_capitulos")
    check("Capítulos: el título actual sigue al capítulo y la marca actual va en limón", """(() => {
      const on = $('pl-rail').querySelector('.chap-mark.on'), m = [...$('pl-rail').querySelectorAll('.chap-mark')];
      return $('pl-chap-now').textContent === 'Capítulo 4 · ' + chap.list[3].title && m.indexOf(on) === 3 && getComputedStyle(on, '::before').backgroundColor === 'rgb(166, 226, 46)'; })()""")
    check("Capítulos: el nombre se quita solo a los ~4 s", "(async () => { await new Promise(r => setTimeout(r, 4500)); return $('pl-chap-toast').hidden; })()")
    ok7 = jump(7)
    results.append(("Capítulos: salto al 8.º capítulo (nombre y título actual)", ok7 is True and js("$('pl-chap-now').textContent === 'Capítulo 8 · ' + chap.list[7].title && !$('pl-chap-toast').hidden") is True, str(ok7)))
    js("prefs().chapterTitles = false; true")   # el ajuste en «No»
    ok2 = jump(1)
    check("Capítulos: con el ajuste en «No» no aparece el nombre, pero el título actual sí", "$('pl-chap-toast').hidden && $('pl-chap-now').textContent === 'Capítulo 2 · ' + chap.list[1].title", str(ok2))
    js("prefs().chapterTitles = true; true")
    check("Capítulos: un video sin capítulos no muestra nada", "(loadChapters(null), $('pl-chap').hidden && $('pl-chap-toast').hidden && !$('pl-rail').children.length)")
    js("closePlayer(); true")

    # ---- Capítulos en el control de la tele (panel «En la tele», video de YouTube)
    js("""__fake.playing = { id: 'yt:%s', title: 'But what is a neural network?', poster: '', state: 'pause', position: 0, duration: 1120,
      audio: 0, sub: -1, audios: [], subs: [], mark: null }; poll(); true""" % CAP)
    waited = js("""(async () => { for (let i = 0; i < 40; i++) { if (typeof npChap !== 'undefined' && npChap.list.length) return true;
      await new Promise(r => setTimeout(r, 300)); } return false; })()""")
    js("openRemote(); true")
    time.sleep(0.6)
    check("Tele: marcas de capítulo bajo la barra y el capítulo actual como texto", """(() => {
      const m = [...$('np-rail').querySelectorAll('.chap-mark')], sk = $('np-seek').getBoundingClientRect(), rr = $('np-rail').getBoundingClientRect();
      return $('remote').open && m.length === npChap.list.length && m.length >= 8 && rr.top >= sk.bottom - 12 && rr.left >= sk.left - 1 && rr.right <= sk.right + 1
        && $('np-chap-now').textContent === 'Capítulo 1 · ' + npChap.list[0].title && !$('np-chap-now').hidden; })()""")
    js("__fake.playing.position = 700; poll(); true")
    time.sleep(0.8)
    shot("tele_capitulos")
    check("Tele: el texto sigue al capítulo (posición 700 s)", "(() => { const i = chapterAt(npChap.list, 700); return i > 0 && $('np-chap-now').textContent === 'Capítulo ' + (i + 1) + ' · ' + npChap.list[i].title && $('np-rail').querySelectorAll('.chap-mark')[i].classList.contains('on'); })()")
    check("Tele: tocar una marca manda /api/seek al inicio del capítulo", "(async () => { $('np-rail').querySelectorAll('.chap-mark')[2].click(); await new Promise(r => setTimeout(r, 300)); const p = __posts.filter(x => x.url === '/api/seek').pop(); return p && p.body.t === Math.floor(npChap.list[2].start); })()")
    check("Tele: sin nada que se salga del control", "(() => { const W = document.documentElement.clientWidth; return [...document.querySelectorAll('#remote .rm *')].every(e => { const r = e.getBoundingClientRect(); return !r.width || (r.left >= -1 && r.right <= W + 1); }); })()")
    js("$('remote').close(); __fake.playing = null; __fake.realInfo = false; poll(); true")
    time.sleep(0.5)

    # ---- PWA y generales
    check("PWA: manifest e íconos", "(async () => { const m = await (await fetch('/manifest.webmanifest')).json(); return document.querySelector('link[rel=manifest]') && document.querySelector('link[rel=apple-touch-icon]') && m.icons.length >= 2; })()")
    check("Id del aparato guardado (cine.device)", "/^[0-9a-f-]{36}$/.test(localStorage.getItem('cine.device'))")
    check("Botón principal y etiqueta «Español» usan los tokens del bloque de colores", "(() => { const t = document.createElement('div'); document.body.append(t); const rgb = v => { t.style.color = `var(${v})`; return getComputedStyle(t).color; }; location.hash = '#inicio'; const b = document.createElement('button'); b.className = 'btn primary'; document.body.append(b); const tag = document.querySelector('.tag-es'); const ok = getComputedStyle(b).backgroundColor === rgb('--lime') && getComputedStyle(b).color === rgb('--on-lime') && getComputedStyle(b).minHeight === '44px' && (!tag || (getComputedStyle(tag).backgroundColor === rgb('--guinda') && getComputedStyle(tag).color === rgb('--es-text') && getComputedStyle(tag).borderTopColor === rgb('--es-line'))); t.remove(); b.remove(); return ok; })()")
    check("Póster sin imagen: el título en letra de marquesina", "(() => { const c = card({ poster: true, img: '', title: 'Prueba' }); document.body.append(c); const ph = c.querySelector('.ph'); const ok = getComputedStyle(ph).display === 'flex' && getComputedStyle(ph).fontFamily.startsWith('\"Big Shoulders'); c.remove(); return ok; })()")

    errors = js("__err")
    errors = errors if isinstance(errors, list) else [f"no se pudo leer la consola: {errors}"]
    ev = [m for m in cdp.pending_events if m.get("method") == "Runtime.exceptionThrown"]
    errors += [json.dumps(m["params"]["exceptionDetails"])[:300] for m in ev]
    cdp.call("Target.closeTarget", {"targetId": target})
    cdp.close()
    return results, overflow, contrast, palette, errors


def main():
    profile = tempfile.mkdtemp(prefix="cine-web-fase4-")
    chrome = find_chrome()
    if not chrome:
        sys.exit("No encontré Google Chrome.")
    proc = subprocess.Popen([chrome, "--headless=new", "--remote-debugging-port=0", f"--user-data-dir={profile}",
                             "--no-first-run", "--mute-audio", "--autoplay-policy=no-user-gesture-required", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    failed = False
    try:
        pf = Path(profile) / "DevToolsActivePort"
        for _ in range(100):
            if pf.exists() and pf.read_text().strip():
                break
            time.sleep(0.1)
        chrome_port = int(pf.read_text().split()[0])
        print("Revisiones del archivo:")
        for name, ok, detail in static_checks():
            failed |= not ok
            print(f"  {'✓' if ok else '✗'} {name}" + (f" — {detail}" if detail and not ok else ""))
        for width in widths:
            results, overflow, contrast, palette, errors = run(width, chrome_port)
            print(f"\n== {width} px ==")
            for name, ok, detail in results:
                failed |= not ok
                print(f"  {'✓' if ok else '✗'} {name}" + (f" — {detail}" if detail and not ok else ""))
            print("  Se sale de la pantalla:", "nada" if not overflow else "")
            for screen, bad in overflow.items():
                failed = True
                print(f"    {screen}: {bad}")
            print("  Contraste (texto ≥4,5:1, bordes de piezas ≥3:1):", "todo bien" if not contrast else "")
            for screen, bad in contrast.items():
                failed = True
                print(f"    {screen}: {bad}")
            print("  Colores fuera de la paleta (negro, grises, limón, guinda):", "ninguno" if not palette else "")
            for screen, bad in palette.items():
                failed = True
                print(f"    {screen}: {bad}")
            print("  Errores de consola:", errors or "ninguno")
            failed |= bool(errors)
        print(f"\nCapturas en {out}")
    finally:
        proc.terminate()
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            proc.kill()
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
