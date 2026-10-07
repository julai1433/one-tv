# La web en el uso de todos los días, con Chrome sin ventana contra un servidor de prueba (pruebas/servidor_de_prueba.py,
# con una COPIA de los datos: esta prueba cambia la fila y lo recomendado de esa copia):
# - la ficha se abre como tarjeta lateral encima de la página, sin perder el lugar (ni el de cada fila);
# - flechas para mover las filas con el mouse;
# - el menú ⋯ de cada video: a la fila, a una lista, «No me interesa», «Silenciar canal»;
# - reproducir la fila en la computadora y la barra de abajo que recuerda lo que se veía (como Spotify);
# - «Ver con otro» archivado (no sale).
# Uso: python3 pruebas/web_uso.py <carpeta de capturas> [puerto=8791]
# Termina con código 1 si hubo errores de JavaScript o algo no salió como se espera.
import base64, json, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mac"))
from live import CDP, find_chrome

out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8791
BASE = f"http://127.0.0.1:{PORT}"
ONLY = set(sys.argv[3].split(",")) if len(sys.argv) > 3 else None   # partes a probar (todas si no se dice)


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
})();
"""

profile = tempfile.mkdtemp(prefix="cine-webtest-")
proc = subprocess.Popen([find_chrome(), "--headless=new", "--remote-debugging-port=0", f"--user-data-dir={profile}",
                         "--no-first-run", "--mute-audio", "--autoplay-policy=no-user-gesture-required",
                         "--window-size=1280,900", "about:blank"],
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
            problems.append("excepción evaluando: " + expr[:80] + " -> " + json.dumps(r["exceptionDetails"].get("exception", {}).get("description", ""))[:300])
        return r.get("result", {}).get("value")

    def shot(name):
        (out / name).write_bytes(base64.b64decode(cdp.call("Page.captureScreenshot", {"format": "png"}, s)["data"]))

    def viewport(w):
        cdp.call("Emulation.setDeviceMetricsOverride", {"width": w, "height": 900 if w > 600 else 844, "deviceScaleFactor": 1, "mobile": w < 600}, s)

    def check(cond, what):
        print(("ok    " if cond else "FALLA ") + what, flush=True)
        if not cond:
            problems.append(what)

    def go(hash_, wait=1.5):
        js(f"location.hash = {json.dumps(hash_)}; true"); time.sleep(wait)

    def click(selector_js, wait=1.0):
        js(f"({selector_js}).click(); true"); time.sleep(wait)

    def key(k, wait=0.6):
        js(f"document.dispatchEvent(new KeyboardEvent('keydown', {{key: {json.dumps(k)}, bubbles: true}})); true"); time.sleep(wait)

    def part(name):
        return ONLY is None or name in ONLY

    def load(wait=4.0, hash_=""):
        cdp.call("Page.navigate", {"url": "about:blank"}, s)   # documento nuevo (no solo otro #)
        time.sleep(0.5)
        cdp.call("Page.navigate", {"url": BASE + "/" + hash_}, s)
        time.sleep(wait)

    cdp.call("Page.enable", {}, s)
    cdp.call("Page.addScriptToEvaluateOnNewDocument", {"source": STUB}, s)
    viewport(1280)
    load()

    # ---------- la ficha como tarjeta lateral ----------
    if part("ficha"):
        go("#youtube", 3.0)
        strip = "document.querySelector('.strip[data-key=new]')"
        js(f"{strip}.scrollLeft = 600; window.scrollTo(0, 300); true"); time.sleep(0.5)
        before = js(f"[{strip}.scrollLeft, Math.round(scrollY)]")
        mark = js("main.firstElementChild.dataset.marca = 'sigue'; true")
        click(f"{strip}.querySelectorAll('.card')[3]", 2.5)
        check(js("location.hash").startswith("#video="), "un video abre su ficha (#video=…)")
        check(js("!document.getElementById('sheet').hidden"), "la ficha es una tarjeta encima de la página")
        check(js("main.dataset.page") == "youtube", "la página de abajo sigue siendo YouTube")
        check(js("document.body.classList.contains('sheet-open')"), "lo de atrás no se mueve mientras está abierta")
        w = js("document.getElementById('sheet-card').getBoundingClientRect().width")
        check(500 <= (w or 0) <= 721, f"la tarjeta ocupa el lado derecho ({w} px)")
        shot("1_ficha_lateral_1280.png")
        key("Escape", 1.0)
        check(js("document.getElementById('sheet').hidden"), "Esc cierra la ficha")
        check(js("location.hash") == "#youtube", "y regresa a #youtube")
        check(js("main.firstElementChild.dataset.marca") == "sigue", "la página de abajo no se volvió a dibujar")
        after = js(f"[{strip}.scrollLeft, Math.round(scrollY)]")
        check(after == before, f"la fila y la página siguen en el mismo lugar ({before} → {after})")
        # clic afuera
        click(f"{strip}.querySelectorAll('.card')[4]", 2.0)
        click("document.getElementById('sheet-dim')", 1.0)
        check(js("document.getElementById('sheet').hidden") and js("location.hash") == "#youtube", "un clic afuera la cierra")
        # la X de la tarjeta
        click(f"{strip}.querySelectorAll('.card')[4]", 2.0)
        click("document.querySelector('#sheet-card .hero .sq')", 1.0)
        check(js("document.getElementById('sheet').hidden"), "la X de la tarjeta la cierra")
        # una película desde Inicio
        go("#inicio", 2.0)
        click("document.querySelector('.strip[data-key=es] .card')", 2.0)
        check(js("location.hash").startswith("#ficha=") and js("!document.getElementById('sheet').hidden"),
              "una película también abre su ficha encima")
        shot("2_ficha_pelicula_1280.png")
        # abrir directo (enlace con #video=)
        vid = api("/api/yt/home")["recent"][0]["id"]
        load(4.0, "#video=" + vid)
        check(js("!document.getElementById('sheet').hidden") and js("main.dataset.page") == "inicio",
              "un enlace directo a una ficha la abre encima de Inicio")
        key("Escape", 1.0)
        check(js("location.hash") in ("#inicio", "") and js("main.dataset.page") == "inicio", "y al cerrarla queda Inicio")
        viewport(390); time.sleep(0.5)
        go("#video=" + vid, 2.5)
        w = js("document.getElementById('sheet-card').getBoundingClientRect().width")
        check(w == 390, f"en el teléfono la tarjeta ocupa toda la pantalla ({w} px)")
        check(js("document.documentElement.scrollWidth <= innerWidth") is True, "a 390 px sin desplazamiento de lado")
        shot("3_ficha_390.png")
        key("Escape", 1.0)
        viewport(1280); time.sleep(0.4)

    # ---------- «Silenciar canal» y «No me interesa» en la ficha ----------
    if part("fichamenu"):
        viewport(1280); time.sleep(0.3)
        go("#youtube", 3.0)
        click("document.querySelector('.strip[data-key=new] .card')", 3.0)
        acts = js("[...document.querySelectorAll('#sheet-card .f-acts button')].map(b => b.textContent)") or []
        check("Silenciar canal" in acts and "No me interesa" in acts, f"la ficha tiene «Silenciar canal» y «No me interesa» ({acts})")
        shot("17_ficha_silenciar_1280.png")
        before = len(api("/api/yt/hidden").get("channels", api("/api/yt/hidden").get("hidden", [])) or [])
        click("[...document.querySelectorAll('#sheet-card .f-acts button')].find(b => b.textContent === 'Silenciar canal')", 4.0)
        hidden = api("/api/yt/hidden")
        n = len(hidden.get("channels") or hidden.get("hidden") or [])
        check(n == before + 1, f"«Silenciar canal» desde la ficha lo silencia ({before} → {n})")
        check("Deshacer" in (js("document.getElementById('toast').innerText") or ""), "y ofrece «Deshacer»")
        click("document.querySelector('#toast .toast-act')", 3.0)
        hidden = api("/api/yt/hidden")
        check(len(hidden.get("channels") or hidden.get("hidden") or []) == before, "«Deshacer» lo vuelve a mostrar")
        key("Escape", 1.0)
        viewport(390); time.sleep(0.4)
        go("#video=" + api("/api/yt/home")["new"][0]["id"], 2.5)
        shot("18_ficha_silenciar_390.png")
        check(js("document.documentElement.scrollWidth <= innerWidth") is True, "ficha a 390 px sin desplazamiento de lado")
        key("Escape", 1.0)
        viewport(1280); time.sleep(0.3)

    # ---------- flechas de las filas (mouse) ----------
    if part("flechas"):
        viewport(1280); time.sleep(0.3)
        go("#youtube", 3.0)
        box = "document.querySelector('.strip[data-key=new]').parentElement"
        check(js(f"{box}.classList.contains('strip-box')"), "cada fila va con sus flechas")
        check(js(f"{box}.querySelector('.prev').hidden") is True, "al principio no hay flecha de «anteriores»")
        check(js(f"{box}.querySelector('.next').hidden") is False, "sí hay flecha de «ver más»")
        x0 = js(f"{box}.querySelector('.strip').scrollLeft")
        cdp.call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": 700, "y": 400}, s)
        click(f"{box}.querySelector('.next')", 1.2)
        x1 = js(f"{box}.querySelector('.strip').scrollLeft")
        check(x1 > x0 + 300, f"la flecha mueve la fila ({x0} → {x1})")
        check(js(f"{box}.querySelector('.prev').hidden") is False, "ahora sí hay flecha de «anteriores»")
        click(f"{box}.querySelector('.prev')", 1.2)
        check(js(f"{box}.querySelector('.strip').scrollLeft") < x1, "y regresa")
        js(f"{box}.scrollIntoView({{block: 'center'}}); true"); time.sleep(0.3)
        r = js(f"(() => {{ const b = {box}.getBoundingClientRect(); return [b.left + 400, b.top + 60]; }})()")
        cdp.call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": r[0], "y": r[1]}, s); time.sleep(0.4)
        shot("4_flechas_1280.png")

    # ---------- menú ⋯ de las tarjetas ----------
    if part("menu"):
        viewport(1280); time.sleep(0.3)
        api("/api/queue/clear", {})
        go("#youtube", 3.0)
        card = "document.querySelector('.strip[data-key=new] .card-box')"
        title = js(f"{card}.querySelector('.c-title').textContent")
        click(f"{card}.querySelector('.card-more')", 0.8)
        check(js("!document.getElementById('card-menu').hidden"), "⋯ abre el menú")
        items = js("[...document.querySelectorAll('#card-menu button')].map(b => b.textContent)") or []
        check(items[:3] == ["Reproducir a continuación", "Al final de la fila", "Agregar a una lista o a Favoritos"],
              f"menú: a la fila y a una lista ({items[:3]})")
        check(any(t == "No me interesa" for t in items) and any(t.startswith("Silenciar") for t in items),
              "menú: «No me interesa» y «Silenciar el canal»")
        check(js("location.hash") == "#youtube", "abrir el menú no abre la ficha")
        shot("5_menu_1280.png")
        click("[...document.querySelectorAll('#card-menu button')].find(b => b.textContent === 'Al final de la fila')", 1.5)
        q = api("/api/library")["queue"]
        check([e["title"] for e in q] == [title], f"«Al final de la fila» desde el menú ({[e['title'] for e in q]})")
        check(js("document.getElementById('card-menu').hidden"), "el menú se cierra al elegir")
        # No me interesa: sale de Nuevos y se puede deshacer
        vid = js(f"{card}.querySelector('.card').getAttribute('onclick') || ''")
        first = api("/api/yt/home")["new"][0]["id"]
        click(f"{card}.querySelector('.card-more')", 0.6)
        click("[...document.querySelectorAll('#card-menu button')].find(b => b.textContent === 'No me interesa')", 1.5)
        check(first not in [v["id"] for v in api("/api/yt/home")["new"]], "«No me interesa» lo quita de Nuevos (en la computadora)")
        check(js(f"[...document.querySelectorAll('.strip[data-key=new] .c-title')].some(t => t.textContent === {json.dumps(title)})") is False,
              "y de la página, sin esperar")
        check("Deshacer" in (js("document.getElementById('toast').innerText") or ""), "el aviso ofrece «Deshacer»")
        shot("6_no_me_interesa_1280.png")
        click("document.querySelector('#toast .toast-act')", 2.0)
        check(first in [v["id"] for v in api("/api/yt/home")["new"]], "«Deshacer» lo regresa")
        # Esc cierra el menú
        click(f"{card}.querySelector('.card-more')", 0.6)
        js("document.querySelector('#card-menu button').dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true})); true"); time.sleep(0.4)
        check(js("document.getElementById('card-menu').hidden"), "Esc cierra el menú")
        # película de la biblioteca
        go("#inicio", 2.0)
        click("document.querySelector('.strip[data-key=es] .card-more')", 0.6)
        items = js("[...document.querySelectorAll('#card-menu button')].map(b => b.textContent)") or []
        check(items == ["Reproducir a continuación", "Al final de la fila"], f"película: a la fila ({items})")
        key("Escape", 0.3)
        js("closeCardMenu(); true")
        viewport(390); time.sleep(0.5)
        go("#youtube", 2.0)
        click("document.querySelector('.strip[data-key=new] .card-more')", 0.6)
        b = js("document.getElementById('card-menu').getBoundingClientRect().toJSON()")
        check(b and b["left"] == 8 and abs(b["right"] - 382) < 1, f"teléfono: el menú va abajo, a lo ancho ({b and [b['left'], b['right']]})")
        shot("7_menu_390.png")
        js("closeCardMenu(); true")
        check(js("document.documentElement.scrollWidth <= innerWidth") is True, "a 390 px sin desplazamiento de lado")
        viewport(1280); time.sleep(0.3)
        api("/api/queue/clear", {})

    # ---------- reproducir aquí: minimizado abajo, la fila, y lo que se recuerda ----------
    if part("reproductor"):
        lib = api("/api/library")
        eps = [k for k, v in lib["items"].items() if (v.get("direct") or {}).get("format") == "mp4" and v.get("kind") == "episode"][:4]
        E1, E2, E3 = eps[:3]
        api("/api/queue/clear", {})
        viewport(1280); time.sleep(0.3)
        load(4.0)
        js("try { localStorage.removeItem('cine.here'); } catch {} ; true")
        go("#ficha=" + E1, 2.0)
        click("document.getElementById('f-here')", 4.0)
        check(js("!document.getElementById('player').hidden && !document.getElementById('player').classList.contains('mini')"),
              "«Ver en esta computadora» abre el reproductor")
        check((js("document.getElementById('pl-video').currentTime") or 0) > 0, "y el video avanza")
        check(js("document.getElementById('pl-close').title").startswith("Minimizar"), "el botón de arriba a la izquierda minimiza")
        click("document.getElementById('pl-close')", 1.0)
        check(js("document.getElementById('player').classList.contains('mini')"), "minimizado: queda abajo")
        check(js("document.body.style.overflow") == "", "y la página se puede usar")
        go("#youtube", 2.0)
        check(js("document.getElementById('pl-video').paused") is False, "sigue sonando mientras se navega")
        saved = json.loads(js("localStorage.getItem('cine.here')") or "{}")
        check(saved.get("id") == E1, "se recuerda en este navegador qué se veía")
        shot("8_minimizado_1280.png")
        js("document.getElementById('pl-video').currentTime = 300; true"); time.sleep(6.5)
        load(4.0)
        check(js("!document.getElementById('player').hidden && document.getElementById('player').classList.contains('mini')"),
              "al volver a abrir la página: la barra de abajo con lo que se veía")
        sub = js("document.getElementById('plm-sub').textContent") or ""
        check(sub.startswith("Seguir aquí · 5:"), f"«Seguir aquí» con el minuto ({sub})")
        shot("9_seguir_aqui_1280.png")
        click("document.getElementById('plm-play')", 4.0)
        t = js("document.getElementById('pl-video').currentTime") or 0
        check(t >= 295, f"▶ sigue donde se quedó ({t:.0f} s)")
        # la fila, aquí
        api("/api/queue/add", {"kind": "item", "id": E2})
        api("/api/queue/add", {"kind": "item", "id": E3})
        js("loadLibrary(); true"); time.sleep(1.5)
        js("paintMini(); true")
        check(js("!document.getElementById('plm-next').hidden"), "con algo en la fila: botón «Siguiente»")
        click("document.getElementById('plm-next')", 4.0)
        check(js("pl && pl.id") == E2, "«Siguiente» pone lo primero de la fila")
        check([e["id"] for e in api("/api/library")["queue"]] == [E3], "y lo quita de la fila")
        js("(() => { const v = document.getElementById('pl-video'); v.currentTime = v.duration - 1.5; })(); true"); time.sleep(4)
        check("fila" in (js("isMini() ? document.getElementById('plm-sub').textContent : document.getElementById('pl-next-what').textContent") or ""),
              "al terminar: «Sigue en tu fila en 5 s…»")
        time.sleep(6)
        check(js("pl && pl.id") == E3, "y sigue lo de la fila")
        js("(() => { const v = document.getElementById('pl-video'); v.currentTime = v.duration - 1.5; })(); true"); time.sleep(4)
        click("document.getElementById('pl-next-cancel')", 1.0)
        check(js("!document.getElementById('player').hidden"), "cancelar lo que sigue no cierra el reproductor")
        check(js("document.getElementById('plm-sub').textContent") == "Terminó", "se queda abajo: «Terminó»")
        shot("10_termino_1280.png")
        click("document.getElementById('plm-close')", 1.0)
        check(js("document.getElementById('player').hidden"), "la X de la barra lo cierra")
        check(js("localStorage.getItem('cine.here')") is None, "y ya no se ofrece al volver")
        # «Reproducir la fila en esta computadora»
        api("/api/queue/add", {"kind": "item", "id": E2})
        js("loadLibrary(); true"); time.sleep(1.5)
        go("#fila", 1.5)
        check(bool(js("!!document.getElementById('q-here')")), "Fila: «Reproducir la fila en esta computadora»")
        click("document.getElementById('q-here')", 4.0)
        check(js("pl && pl.id") == E2 and js("!document.getElementById('player').classList.contains('mini')"),
              "la fila se reproduce aquí, en grande")
        check(api("/api/library")["queue"] == [], "y se va quitando de la fila")
        click("document.getElementById('pl-stop')", 1.0)
        # YouTube aquí: se guarda su avance (antes no)
        vid = next(v["id"] for v in api("/api/yt/home")["recent"] if not v.get("live") and (v.get("duration") or 0) > 120)
        js(f"ytHere({{id: {json.dumps(vid)}, title: 'Prueba'}}, 0); true"); time.sleep(16)
        js("document.getElementById('pl-video').currentTime = 40; true"); time.sleep(12)
        prog = json.loads(open(Path(__import__('os').environ.get('CINE_PRUEBA', '/tmp/cine-prueba')) / 'datos' / 'progreso.json').read()) if __import__('os').environ.get('CINE_PRUEBA') else {}
        p = ((prog.get("progress") or prog).get("yt:" + vid) or {}).get("p", 0) if prog else None
        check(p is None or p >= 30, f"YouTube visto aquí guarda su avance ({p})")
        click("document.getElementById('pl-stop')", 1.0)
        viewport(390); time.sleep(0.4)
        js(f"playHere({json.dumps(E1)}, 10, 0, -1); true"); time.sleep(3)
        click("document.getElementById('pl-close')", 1.0)
        shot("11_minimizado_390.png")
        b = js("document.getElementById('player').getBoundingClientRect().toJSON()")
        check(b and b["width"] == 390, "teléfono: la barra va a lo ancho, arriba de las pestañas")
        check(js("document.documentElement.scrollWidth <= innerWidth") is True, "a 390 px sin desplazamiento de lado")
        click("document.getElementById('plm-close')", 1.0)
        viewport(1280); time.sleep(0.3)
        api("/api/queue/clear", {})

    # ---------- tu música ----------
    if part("musica"):
        viewport(1280); time.sleep(0.3)
        api("/api/queue/clear", {})
        js("try { localStorage.removeItem('cine.here'); } catch {} ; true")
        go("#musica", 3.0)
        check(js("document.querySelector('#side a[data-side=musica]').getAttribute('aria-current')") == "page", "Música en el menú")
        heads = js("[...document.querySelectorAll('main .row-h h2')].map(h => h.textContent)") or []
        check(heads[:4] == ["Tus listas", "Agregadas hace poco", "Artistas", "Álbumes"], f"Música: listas, recientes, artistas y álbumes ({heads})")
        check((js("document.querySelectorAll('main .grid .card.s').length") or 0) >= 50, "álbumes con su portada (cuadradas)")
        shot("12_musica_1280.png")
        click("document.querySelector('main .grid .card.s')", 2.0)
        check(js("location.hash").startswith("#album="), "un álbum abre su página")
        check(js("!!document.getElementById('m-play')") and (js("document.querySelectorAll('.tracks li').length") or 0) >= 1, "página del álbum con sus canciones")
        click("document.querySelector('.trk')", 3.0)
        check(js("pl && pl.music") is True, "una canción suena aquí")
        check(js("document.getElementById('player').classList.contains('mini')"), "la música empieza abajo, como Spotify")
        check((js("document.getElementById('pl-video').currentTime") or 0) > 0.5, "y avanza")
        check(js("document.getElementById('plm-sub').textContent") == js("pl.artist"), "abajo: la canción y su artista")
        shot("13_cancion_1280.png")
        # una lista: «Aleatorio» y la siguiente canción con el botón
        go("#musica", 1.5)
        click("document.querySelector('[data-key=mlists] .card')", 2.0)
        check(js("location.hash").startswith("#mlista="), "una lista abre su página")
        n = js("document.querySelectorAll('.tracks li').length") or 0
        check(n >= 10, f"la lista con sus canciones ({n})")
        click("document.getElementById('m-play')", 3.0)
        first = js("pl.id")
        click("document.getElementById('plm-next')", 3.0)
        check(js("pl.i") == 1 and js("pl.id") != first, "«Siguiente» pasa a la otra canción de la lista")
        check(js("!document.getElementById('plm-prev').hidden"), "con música: botón de la anterior")
        js("(() => { const v = document.getElementById('pl-video'); v.currentTime = v.duration - 1; })(); true"); time.sleep(4)
        check(js("pl.i") == 2, "al terminar una canción sigue la siguiente, sin esperar")
        shot("14_lista_1280.png")
        saved = json.loads(js("localStorage.getItem('cine.here')") or "{}")
        check(saved.get("kind") == "music" and saved.get("i") == 2, "se recuerda la canción y la lista")
        load(4.0)
        check("Seguir aquí" in (js("document.getElementById('plm-sub').textContent") or ""), "al volver a abrir la página: «Seguir aquí»")
        click("document.getElementById('plm-play')", 4.0)
        check(js("pl && pl.music && pl.i") == 2, "▶ sigue con esa canción de la lista")
        click("document.getElementById('plm-close')", 1.0)
        # a la fila
        go("#musica", 2.0)
        click("document.querySelector('[data-key=mrecent] .card-more')", 0.6)
        click("[...document.querySelectorAll('#card-menu button')].find(b => b.textContent === 'Al final de la fila')", 1.5)
        q = api("/api/library")["queue"]
        check(len(q) == 1 and q[0]["kind"] == "track", "una canción a la fila desde ⋯")
        viewport(390); time.sleep(0.5)
        go("#musica", 2.0)
        shot("15_musica_390.png")
        check(js("document.documentElement.scrollWidth <= innerWidth") is True, "Música a 390 px sin desplazamiento de lado")
        check(js("getComputedStyle(document.getElementById('tabs')).gridTemplateColumns.split(' ').length") == 6, "seis pestañas en el teléfono")
        go("#album=" + js("music.albums.find(a => a.tracks.length > 1).id"), 2.0)
        shot("16_album_390.png")
        check(js("document.documentElement.scrollWidth <= innerWidth") is True, "álbum a 390 px sin desplazamiento de lado")
        viewport(1280); time.sleep(0.3)
        api("/api/queue/clear", {})

    # ---------- «Ver con otro» archivado ----------
    if part("archivado"):
        check(js("document.getElementById('pl-multi').hidden") is True, "«Ver con otro» no se ofrece (archivado)")

    errs = js("window.__errs") or []
    check(not errs, "sin errores de JavaScript" + (f": {errs[:3]}" if errs else ""))
finally:
    proc.terminate()
print("\n" + ("TODO BIEN" if not problems else f"{len(problems)} problema(s):\n  " + "\n  ".join(problems)))
sys.exit(1 if problems else 0)
