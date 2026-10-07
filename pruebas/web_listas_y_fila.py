# Favoritos, «Agregar a lista», listas enteras a la fila, subir y bajar en la fila y «Cargar más resultados» en la web,
# con Chrome sin ventana contra un servidor de prueba (pruebas/servidor_de_prueba.py, con una COPIA de los datos: esta
# prueba cambia la fila, Favoritos y las listas de esa copia). La búsqueda sí le pregunta a YouTube (dos páginas).
# Uso: python3 pruebas/web_listas_y_fila.py <carpeta de capturas> [puerto=8791]
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


home = api("/api/yt/home")
vids = []
for v in home["recent"] + home["new"]:
    if v["id"] not in {x["id"] for x in vids}:
        vids.append(v)
V1, V2 = vids[0], vids[1]
takeout = next((p for p in home["playlists"] if p.get("source") == "takeout"), None)

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
    go("#youtube", 2.5)

    # ---- ficha: Favorito ----
    viewport(1280); time.sleep(0.4)
    go("#video=" + V1["id"], 2.5)
    check(js("document.querySelectorAll('.f-acts button').length") == 8, "ficha: 8 acciones (con Favorito, Agregar a lista, No me interesa y Silenciar canal)")
    see(".f-acts"); shot("1_ficha_1280.png")
    was = api(f"/api/lists?video={V1['id']}")["lists"][0]["has"]
    click(btn_with("Favorito", "document.querySelector('.f-acts')"), 1.5)
    now = api(f"/api/lists?video={V1['id']}")["lists"][0]["has"]
    check(now != was, "Favorito cambia en la computadora")
    pressed = js("document.querySelector('.f-acts button[aria-pressed]').getAttribute('aria-pressed')")
    check(pressed == ("true" if now else "false"), "el botón dice si está en Favoritos")
    if not now:   # que quede en Favoritos para lo que sigue
        click(btn_with("Favorito", "document.querySelector('.f-acts')"), 1.5)
    check("En Favoritos" in js("document.querySelector('.f-acts').innerText"), "«En Favoritos» con el corazón lleno")
    see(".f-acts"); shot("2_ficha_en_favoritos_1280.png")

    # ---- Agregar a lista ----
    click(btn_with("Agregar a lista", "document.querySelector('.f-acts')"), 2.0)
    check(js("document.getElementById('lists-pick').open") is True, "«Agregar a lista» abre la ventana")
    rows = js("[...document.querySelectorAll('#lists-pick .lpick')].map(b => [b.innerText.split('\\n')[0], b.getAttribute('aria-pressed')])") or []
    check(rows and rows[0] == ["Favoritos", "true"], f"primero Favoritos, marcado ({rows[:1]})")
    shot("3_agregar_a_lista_1280.png")
    if takeout:
        before = api(f"/api/lists?video={V1['id']}")
        idx = next(i for i, l in enumerate(before["lists"]) if l["id"] == takeout["id"])
        click(f"document.getElementById('lpick-{idx}')", 1.5)
        after = next(l for l in api(f"/api/lists?video={V1['id']}")["lists"] if l["id"] == takeout["id"])
        check(after["has"] != before["lists"][idx]["has"], f"marcar una lista del Takeout («{takeout['title']}») la cambia")
        click(f"document.getElementById('lpick-{idx}')", 1.5)   # se deja como estaba
    js("document.getElementById('lists-new-q').value = 'Prueba web'; document.getElementById('lists-new-q').dispatchEvent(new Event('input')); true")
    click("document.querySelector('#lists-new button[type=submit]')", 2.0)
    mine = [l for l in api(f"/api/lists?video={V1['id']}")["lists"] if l["title"] == "Prueba web"]
    check(mine and mine[0]["has"], "«Crear» hace la lista con este video")
    check(js("document.getElementById('lists-pick').open") is False, "al crear se cierra la ventana")
    viewport(390); time.sleep(0.4)
    click(btn_with("Agregar a lista", "document.querySelector('.f-acts')"), 2.0)
    shot("4_agregar_a_lista_390.png")
    js("document.getElementById('lists-pick').close(); true")
    see(".f-acts"); shot("5_ficha_390.png")

    # ---- YouTube: fila Favoritos y la lista nueva en «Tus listas» ----
    viewport(1280); time.sleep(0.4)
    js("refreshYouTube(); true"); time.sleep(2.0)
    go("#youtube", 2.0)
    heads = js("[...document.querySelectorAll('.row-h h2')].map(h => h.textContent)") or []
    check("Favoritos" in heads, "YouTube: fila «Favoritos»")
    check(heads.index("Favoritos") == heads.index("Tus listas") + 1 if "Favoritos" in heads and "Tus listas" in heads else False,
          "«Favoritos» va justo después de «Tus listas»")
    see("[data-key=favs]", "center"); shot("6_youtube_favoritos_1280.png")

    # ---- lista de One TV: a la fila, nombre, borrar ----
    lid = mine[0]["id"] if mine else None
    if lid:
        api("/api/queue/clear", {})
        go("#lista=" + lid, 2.0)
        check("Cambiar el nombre" in js("document.body.innerText") and "Borrar la lista" in js("document.body.innerText"),
              "lista de One TV: cambiar el nombre y borrar")
        shot("7_lista_propia_1280.png")
        click(btn_with("Al final de la fila"), 1.5)
        check([e["id"] for e in api("/api/library")["queue"]] == [V1["id"]], "«Al final de la fila» pone la lista entera en la fila")
        js("window.__promptAnswer = 'Prueba renombrada'; true")
        click(btn_with("Cambiar el nombre"), 1.5)
        check(any(l["title"] == "Prueba renombrada" for l in api(f"/api/lists?video={V1['id']}")["lists"]), "cambiar el nombre")
        click(btn_with("Borrar la lista"), 1.5)
        check(not any(l["id"] == lid for l in api(f"/api/lists?video={V1['id']}")["lists"]), "borrar la lista")
        check(js("location.hash") == "#youtube", "al borrar vuelve a YouTube")
    if takeout:
        api("/api/queue/clear", {})
        go("#lista=" + takeout["id"], 3.0)
        click(btn_with("A continuación"), 3.0)
        n = len(api("/api/library")["queue"])
        check(n > 0, f"lista del Takeout «A continuación»: {n} videos a la fila")

    # ---- fila: subir y bajar ----
    api("/api/queue/clear", {})
    for v in vids[:4]:
        api("/api/queue/add", {"kind": "yt", "id": v["id"], "title": v["title"]})
    js("loadLibrary(); true"); time.sleep(1.5)
    go("#fila", 1.5)
    check(js("document.getElementById('qm-up-0').disabled") is True and js("document.getElementById('qm-down-3').disabled") is True,
          "fila: el primero no sube y el último no baja")
    click("document.getElementById('qm-down-0')", 1.5)
    order = [e["id"] for e in api("/api/library")["queue"]]
    check(order[:2] == [vids[1]["id"], vids[0]["id"]], "bajar el primero lo pone segundo (en la computadora)")
    check(js("document.activeElement && document.activeElement.id") == "qm-down-1", "el foco sigue al video que se movió")
    click("document.getElementById('qm-up-3')", 1.5)
    check([e["id"] for e in api("/api/library")["queue"]][2] == vids[3]["id"], "subir el último lo pone tercero")
    shot("8_fila_1280.png")
    viewport(390); time.sleep(0.5)
    go("#fila", 1.0); shot("9_fila_390.png")
    check(js("document.documentElement.scrollWidth <= innerWidth") is True, "fila a 390 px sin desplazamiento de lado")

    # ---- búsqueda: cargar más ----
    viewport(1280); time.sleep(0.4)
    go("#youtube", 1.0)
    js("document.getElementById('yt-q').value = 'recetas de pan'; document.querySelector('form.search-row').requestSubmit(); true")
    for _ in range(60):
        time.sleep(1)
        if js("!ytSearch.busy && !!ytSearch.results"):
            break
    time.sleep(0.5)
    n1 = js("document.querySelectorAll('.grid.w .card, .grid.w > *').length")
    check(bool(js("!!document.getElementById('yt-more')")), f"búsqueda: botón «Cargar más resultados» ({n1} resultados)")
    see("#yt-more"); shot("10_cargar_mas_1280.png")
    click("document.getElementById('yt-more')", 1.0)
    for _ in range(90):
        time.sleep(1)
        if js("!ytSearch.loadingMore"):
            break
    time.sleep(0.5)
    n2 = js("document.querySelectorAll('.grid.w .card, .grid.w > *').length")
    check(n2 > n1, f"«Cargar más» agrega resultados ({n1} → {n2})")
    check(js("document.activeElement && document.activeElement.id") == "yt-more", "el foco se queda en «Cargar más»")
    see("#yt-more"); shot("11_cargados_1280.png")

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
