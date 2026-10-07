# YouTube en vivo en la web: «Solo en vivo» en la búsqueda, la marca EN VIVO en tarjetas y ficha, «Agregar a En vivo» y
# el canal en la página En vivo. Chrome sin ventana contra un servidor de prueba (pruebas/servidor_de_prueba.py, con una
# COPIA de los datos: agrega un canal a esa copia). Le pregunta de verdad a YouTube (búsqueda y transmisión de ahora).
# Uso: python3 pruebas/web_en_vivo.py <carpeta de capturas> [puerto=8791]
# Termina con código 1 si hubo errores de JavaScript o algo no salió como se espera.
import base64, json, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mac"))
from live import CDP, find_chrome

out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8791
BASE = f"http://127.0.0.1:{PORT}"


def api(path, body=None):
    req = urllib.request.Request(BASE + path, json.dumps(body).encode() if body is not None else None,
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())



STUB = """
(() => {
  window.__errs = [];
  window.addEventListener("error", e => __errs.push("error: " + e.message));
  window.addEventListener("unhandledrejection", e => __errs.push("promesa: " + e.reason));
  const ce = console.error; console.error = (...a) => { __errs.push("console.error: " + a.join(" ")); ce(...a); };
  window.confirm = () => true;
  window.prompt = (msg, value) => window.__promptAnswer || value;
})();
"""

profile = tempfile.mkdtemp(prefix="cine-webtest-")
proc = subprocess.Popen([find_chrome(), "--headless=new", "--remote-debugging-port=0", f"--user-data-dir={profile}",
                         "--no-first-run", "--mute-audio", "--window-size=1280,900", "about:blank"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
problems = []
try:
    pf = Path(profile) / "DevToolsActivePort"
    while not (pf.exists() and pf.read_text().strip()):
        time.sleep(0.1)
    port = int(pf.read_text().split()[0])
    cdp = CDP(json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version").read())["webSocketDebuggerUrl"])
    target = cdp.call("Target.createTarget", {"url": "about:blank"})["targetId"]
    s = cdp.call("Target.attachToTarget", {"targetId": target, "flatten": True})["sessionId"]

    def js(expr):
        r = cdp.call("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True}, s, timeout=90)
        if "exceptionDetails" in r:
            problems.append("excepción evaluando: " + expr[:80] + " -> " + json.dumps(r["exceptionDetails"].get("exception", {}).get("description", ""))[:200])
        return r.get("result", {}).get("value")

    def shot(name):
        (out / name).write_bytes(base64.b64decode(cdp.call("Page.captureScreenshot", {"format": "png"}, s)["data"]))

    def viewport(w):
        cdp.call("Emulation.setDeviceMetricsOverride", {"width": w, "height": 900 if w > 600 else 844, "deviceScaleFactor": 1, "mobile": w < 600}, s)

    def check(cond, what):
        print(("ok    " if cond else "FALLA ") + what)
        if not cond:
            problems.append(what)

    def go(hash_, wait=1.5):
        js(f"location.hash = {json.dumps(hash_)}; true"); time.sleep(wait)

    def click(selector_js, wait=1.0):
        js(f"({selector_js}).click(); true"); time.sleep(wait)

    def btn_with(text, scope="document"):
        return f"[...{scope}.querySelectorAll('button')].find(b => b.textContent.includes({json.dumps(text)}))"

    def see(selector, block="center"):
        js(f"(document.querySelector({json.dumps(selector)}) || document.body).scrollIntoView({{block: {json.dumps(block)}}}); true"); time.sleep(0.4)

    cdp.call("Page.enable", {}, s)
    cdp.call("Page.addScriptToEvaluateOnNewDocument", {"source": STUB}, s)
    cdp.call("Page.navigate", {"url": BASE + "/"}, s)
    time.sleep(3.5)
    for width in (1280, 390):
        viewport(width); time.sleep(0.4)
        w = str(width)
        go("#youtube", 2.0)
        js("ytLiveOnly = false; render(); true"); time.sleep(0.3)
        click(btn_with("Solo en vivo"), 0.3)
        check(js("document.querySelector('.chip-live').getAttribute('aria-pressed')") == "true", f"[{w}] «Solo en vivo» queda marcado")
        js("document.getElementById('yt-q').value = 'noticias'; document.querySelector('form.search-row').requestSubmit(); true")
        for _ in range(60):
            time.sleep(1)
            if js("!ytSearch.busy && !!ytSearch.results"):
                break
        time.sleep(0.5)
        n = js("ytSearch.results.length")
        lives = js("ytSearch.results.filter(v => v.live).length")
        check(n > 0 and lives == n, f"[{w}] todos los resultados son en vivo ({lives} de {n})")
        check(js("document.querySelectorAll('.dur.live').length") >= min(n, 3), f"[{w}] tarjetas con «EN VIVO»")
        check(js("document.documentElement.scrollWidth <= innerWidth") is True, f"[{w}] sin desplazamiento de lado")
        see(".search-row", "start"); shot(f"1_busqueda_en_vivo_{w}.png")
    viewport(1280); time.sleep(0.4)
    vid = js("ytSearch.results[0].id")
    go("#video=" + vid, 4.0)
    meta = js("document.querySelector('.f-meta').innerText")
    check("EN VIVO" in meta, f"ficha: «EN VIVO» ({meta})")
    acts = js("document.querySelector('.f-acts').innerText")
    check("Agregar a En vivo" in acts and "Al final de la fila" not in acts, "ficha en vivo: «Agregar a En vivo», sin fila")
    check("Ver en vivo en la TV" in js("document.querySelector('.f-main').innerText"), "«Ver en vivo en la TV»")
    shot("2_ficha_en_vivo_1280.png")
    before = len(api("/api/library")["live"])
    click(btn_with("Agregar a En vivo"), 12.0)
    live = api("/api/library")["live"]
    yt = [c for c in live if c.get("youtube")]
    check(len(live) == before + 1 or yt, f"«Agregar a En vivo» deja el canal ({[c['name'] for c in yt]})")
    go("#envivo", 2.0)
    check(any(c["name"] in js("document.body.innerText") for c in yt), "el canal sale en la página En vivo")
    shot("3_en_vivo_1280.png")
    if yt:
        with urllib.request.urlopen(f"{BASE}/live/{yt[0]['id']}/index.m3u8", timeout=60) as r:
            text = r.read().decode()
        check("/yt/" in text and "#EXT-X-STREAM-INF" in text, "/live/<canal>/index.m3u8 da la lista de la transmisión de ahora")
    errs = js("window.__errs") or []
    check(not errs, "sin errores de JavaScript" + (": " + "; ".join(errs[:3]) if errs else ""))
finally:
    proc.terminate()
    try:
        proc.wait(5)
    except subprocess.TimeoutExpired:
        proc.kill()

print("\n" + ("TODO BIEN" if not problems else f"{len(problems)} PROBLEMA(S):\n- " + "\n- ".join(problems)))
sys.exit(1 if problems else 0)
