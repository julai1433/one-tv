# El ajuste de reproducción continua (Fila de reproducción → Ajustes de la casa) y la reproducción continua en el
# propio navegador (servidor real, 8765).
import base64, json, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mac"))
from live import CDP, find_chrome
out = Path(sys.argv[1]); width = int(sys.argv[2]) if len(sys.argv) > 2 else 430
profile = tempfile.mkdtemp(prefix="cine-webtest-")
proc = subprocess.Popen([find_chrome(), "--headless=new", "--remote-debugging-port=0", f"--user-data-dir={profile}",
                         "--no-first-run", "--mute-audio", "--autoplay-policy=no-user-gesture-required",
                         f"--window-size={width},900", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    pf = Path(profile) / "DevToolsActivePort"
    while not (pf.exists() and pf.read_text().strip()):
        time.sleep(0.1)
    port = int(pf.read_text().split()[0])
    cdp = CDP(json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version").read())["webSocketDebuggerUrl"])
    target = cdp.call("Target.createTarget", {"url": "http://127.0.0.1:8765/"})["targetId"]
    s = cdp.call("Target.attachToTarget", {"targetId": target, "flatten": True})["sessionId"]
    def js(expr):
        r = cdp.call("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True}, s)
        return r.get("result", {}).get("value")
    def shot(name):
        Path(out, name).write_bytes(base64.b64decode(cdp.call("Page.captureScreenshot", {"format": "png"}, s)["data"]))
    time.sleep(3)
    js("location.hash = 'fila'; true"); time.sleep(1)
    print("selector:", js("[...document.querySelectorAll('#ajustes .seg button')].map(b => b.textContent + '=' + b.getAttribute('aria-pressed'))"))
    js("document.querySelectorAll('#ajustes .seg button')[1].click(); true"); time.sleep(1.5)
    print("tras elegir «seguir»:", js("[...document.querySelectorAll('#ajustes .seg button')].map(b => b.getAttribute('aria-pressed'))"),
          json.loads(urllib.request.urlopen("http://127.0.0.1:8765/api/library").read())["prefs"].get("ytAutoplay"))
    js("document.getElementById('ajustes').scrollIntoView(); true"); shot(f"yt_auto_{width}.png")
    js("ytHere({id: 'RXTAco9KgFs', title: 'Timelapse de 15 segundos de nuevo.'}); true")
    for _ in range(60):
        time.sleep(1)
        if js("!document.getElementById('pl-next').hidden"):
            break
    print("aviso:", js("document.getElementById('pl-next').innerText.replace(/\\n/g, ' | ')"))
    shot(f"yt_next_{width}.png")
    js("clearUpNext(); closePlayer(); true")
    js("document.querySelectorAll('#ajustes .seg button')[0].click(); true"); time.sleep(1.5)
    print("al final queda:", json.loads(urllib.request.urlopen("http://127.0.0.1:8765/api/library").read())["prefs"].get("ytAutoplay"))
finally:
    proc.terminate()
