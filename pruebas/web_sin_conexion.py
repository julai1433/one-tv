# «Guardar sin conexión» en la web, con Chrome sin ventana contra un servidor de prueba (pruebas/servidor_de_prueba.py).
# La API /api/offline… se simula dentro de la página (se intercepta fetch), así que se puede probar cada estado.
# Uso: python3 pruebas/web_sin_conexion.py <carpeta de capturas> [puerto=8796]
# Escribe capturas a 1280 y 390 px y termina con código 1 si hubo errores de JavaScript o algo no salió como se espera.
import base64, json, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mac"))
from live import CDP, find_chrome

out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8796
BASE = f"http://127.0.0.1:{PORT}"

home = json.loads(urllib.request.urlopen(BASE + "/api/yt/home").read())
pool = [v for v in home["new"] + home["recent"] if v.get("duration")]
seen = set(); vids = []
for v in pool:
    if v["id"] not in seen:
        seen.add(v["id"]); vids.append(v)
assert len(vids) >= 22, "faltan videos de YouTube en la copia de los datos"
V1, V2, V3, V4 = vids[0], vids[1], vids[2], vids[3]
LIST = "PLPRUEBA"
LIST_VIDS = vids[4:16]

STUB = """
(() => {
  window.__errs = []; window.__gets = 0; window.__calls = []; window.__fail = false;
  window.addEventListener("error", e => __errs.push("error: " + e.message));
  window.addEventListener("unhandledrejection", e => __errs.push("promesa: " + e.reason));
  const ce = console.error; console.error = (...a) => { __errs.push("console.error: " + a.join(" ")); ce(...a); };
  window.__off = { ok: true, videos: [], lists: [], bytes_total: 0, limit_bytes: 100e9, free_bytes: 300e9 };
  window.__vids = %s;
  const real = window.fetch.bind(window);
  const json = (o, status = 200) => Promise.resolve(new Response(JSON.stringify(o), { status, headers: { "Content-Type": "application/json" } }));
  window.fetch = (url, opts) => {
    const u = typeof url === "string" ? url : url.url;
    if (u.startsWith("/api/offline")) {
      if (window.__fail) return Promise.reject(new TypeError("Failed to fetch"));
      if (opts && opts.method === "POST") { __calls.push([u, opts.body]); return json({ ok: true, state: "pendiente" }); }
      __gets++;
      return json(window.__off);
    }
    if (u.startsWith("/api/yt/info?")) {
      const id = decodeURIComponent(u.split("id=")[1]);
      const v = window.__vids.find(x => x.id === id) || {};
      return json({ ok: true, id, title: v.title, channel: v.channel, channel_id: "UCprueba", duration: v.duration,
                    desc: "Descripción de prueba del video.\\nSegunda línea.", published: 1790000000 });
    }
    if (u.startsWith("/api/yt/playlist?")) return json({ ok: true, title: "Para el viaje", filling: 0, videos: window.__list });
    return real(url, opts);
  };
})();
""" % json.dumps(vids[:16])

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
        r = cdp.call("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True}, s)
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

    def vid(v, **kw):
        e = {"id": v["id"], "title": v["title"], "channel": v["channel"], "duration": v["duration"], "thumb": v["thumb"],
             "state": "listo", "progress": 1, "bytes": 184_000_000, "error": "", "lists": []}
        e.update(kw)
        return e

    def set_off(videos=(), lists=(), used=3_200_000_000, limit=100_000_000_000):
        js("window.__off = %s; true" % json.dumps({"ok": True, "videos": list(videos), "lists": list(lists), "bytes_total": used,
                                                    "limit_bytes": limit, "free_bytes": 210_000_000_000}))

    def refresh(wait=1.2):
        js("offAt = 0; loadOffline(); true"); time.sleep(wait)

    def go(hash_, wait=1.5):
        js(f"location.hash = {json.dumps(hash_)}; true"); time.sleep(wait)

    def see(selector, block="center"):
        js(f"(document.querySelector({json.dumps(selector)}) || document.body).scrollIntoView({{block: {json.dumps(block)}}}); true"); time.sleep(0.4)

    cdp.call("Page.enable", {}, s)
    cdp.call("Page.addScriptToEvaluateOnNewDocument", {"source": STUB}, s)
    cdp.call("Page.navigate", {"url": BASE + "/"}, s)
    time.sleep(3.5)
    js("window.__list = window.__vids.slice(4, 16); true")
    go("#youtube", 2.5)   # carga YouTube: así la ficha ya conoce los videos

    for width in (1280, 390):
        viewport(width); time.sleep(0.5)
        w = str(width)

        # ---- ficha en cada estado ----
        set_off([]); refresh()
        go("#video=" + V1["id"], 1.5)
        txt = js("document.querySelector('.f-acts').innerText")
        check("Guardar sin conexión" in txt, f"[{w}] ficha sin guardar: botón «Guardar sin conexión»")
        check(js("document.querySelectorAll('.f-acts button').length") == 6, f"[{w}] ficha: 6 acciones")
        see(".f-acts"); shot(f"ficha_1_sin_guardar_{w}.png")
        js("[...document.querySelectorAll('.f-acts button')].find(b => /Guardar sin conexión/.test(b.textContent)).click(); true"); time.sleep(1.5)
        check(json.loads(js("JSON.stringify(window.__calls)") or "[]")[-1:] == [["/api/offline/save", json.dumps({"id": V1["id"]}, separators=(",", ":"))]],
              f"[{w}] guardar manda POST /api/offline/save {{id}}")
        check("En la cola para guardar" in js("document.querySelector('.f-main').parentElement.innerText"), f"[{w}] tras guardar aparece «En la cola para guardar» (optimista)")

        set_off([vid(V1, state="pendiente", progress=0, bytes=0)]); refresh()
        see(".f-acts")
        check("En la cola para guardar" in js("document.querySelector('.f-body').innerText") and "Cancelar" in js("document.querySelector('.f-acts').innerText"), f"[{w}] ficha pendiente: texto + Cancelar")
        shot(f"ficha_2_pendiente_{w}.png")

        set_off([vid(V1, state="bajando", progress=0.45, bytes=80_000_000)]); refresh()
        check("Guardando… 45 %" in js("document.querySelector('.f-body').innerText"), f"[{w}] ficha bajando: «Guardando… 45 %»")
        check(js("document.querySelector('.off-bar i').style.width") == "45%", f"[{w}] barra al 45 %")
        see(".f-acts"); shot(f"ficha_3_bajando_{w}.png")

        # sondeo: mientras baja se vuelve a preguntar cada ~3 s y se actualiza solo
        g0 = js("window.__gets"); set_off([vid(V1, state="bajando", progress=0.7, bytes=130_000_000)]); time.sleep(7)
        g1 = js("window.__gets")
        check(2 <= g1 - g0 <= 4, f"[{w}] sondeo cada ~3 s mientras baja ({g1 - g0} lecturas en 7 s)")
        check("Guardando… 70 %" in js("document.querySelector('.f-body').innerText"), f"[{w}] el avance se actualiza solo (70 %)")

        set_off([vid(V1)]); time.sleep(3.6)
        check("Guardado sin conexión" in js("document.querySelector('.f-body').innerText") and "Quitar" in js("document.querySelector('.f-acts').innerText"), f"[{w}] ficha lista: «Guardado sin conexión» + Quitar")
        see(".f-acts"); shot(f"ficha_4_listo_{w}.png")
        g0 = js("window.__gets"); time.sleep(7)
        check(js("window.__gets") == g0, f"[{w}] sin nada bajando, el sondeo se detiene")

        set_off([vid(V1, state="error", progress=0.3, error="YouTube no dejó bajar este video (restringido por edad).")]); refresh()
        check("restringido por edad" in js("document.querySelector('.f-body').innerText") and "Reintentar" in js("document.querySelector('.f-acts').innerText"), f"[{w}] ficha con error: motivo + Reintentar")
        see(".f-acts"); shot(f"ficha_5_error_{w}.png")

        # ---- lista ----
        set_off([]); refresh()
        go("#lista=" + LIST, 2)
        check("Guardar la lista sin conexión" in js("document.querySelector('.tools').innerText"), f"[{w}] lista sin guardar")
        shot(f"lista_1_sin_guardar_{w}.png")
        part = [vid(v, lists=[LIST], state="listo") for v in LIST_VIDS[:3]] + \
               [vid(LIST_VIDS[3], lists=[LIST], state="bajando", progress=0.4, bytes=60_000_000)] + \
               [vid(v, lists=[LIST], state="pendiente", progress=0, bytes=0) for v in LIST_VIDS[4:]]
        set_off(part, [{"id": LIST, "title": "Para el viaje", "count": 12, "done": 3}]); refresh()
        check("Guardando 3 de 12" in js("document.querySelector('main').innerText"), f"[{w}] lista a medias: «Guardando 3 de 12»")
        shot(f"lista_2_guardando_{w}.png")
        full = [vid(v, lists=[LIST]) for v in LIST_VIDS]
        set_off(full, [{"id": LIST, "title": "Para el viaje", "count": 12, "done": 12}]); time.sleep(3.6) ; refresh()
        check("Lista guardada" in js("document.querySelector('main').innerText"), f"[{w}] lista completa: «Lista guardada»")
        see("main", "start"); shot(f"lista_3_guardada_{w}.png")

        # ---- página YouTube: fila «Guardados» + marca en tarjetas ----
        mixed = [vid(V2, state="bajando", progress=0.45, bytes=70_000_000), vid(V3), vid(V4, state="error", error="Sin espacio en la computadora."),
                 vid(vids[5]), vid(vids[6], state="pendiente", progress=0, bytes=0)]
        set_off(mixed, [], used=3_200_000_000); go("#youtube", 2); refresh()
        check(js("[...document.querySelectorAll('.row-h h2')].some(h => h.textContent === 'Guardados')"), f"[{w}] fila «Guardados» en YouTube")
        see("[data-key=saved]"); shot(f"yt_fila_guardados_{w}.png")
        n = js("document.querySelectorAll('[data-key=saved] .saved-mark').length")
        check(n == 2, f"[{w}] la fila marca solo lo listo ({n} marcas de 5)")
        # tarjeta con marca entre las de siempre (el video está en «Nuevos…»/«Vistos») y sin choque con la duración
        set_off([vid(v) for v in vids[:12]] + [vid(c) for c in home["continue"] if c["id"] not in {x["id"] for x in vids[:12]}]); refresh()
        see("[data-key=new]")
        r = json.loads(js("""(() => { const c = document.querySelector('.card .saved-mark'); if (!c) return 'null';
              const th = c.closest('.thumb'), d = th.querySelector('.dur'), a = c.getBoundingClientRect(), b = d && d.getBoundingClientRect();
              const y = document.querySelector('.thumb .tag-es'); return JSON.stringify({ mark: [a.left, a.top, a.right, a.bottom], dur: b && [b.left, b.top, b.right, b.bottom] }); })()""") or "null")
        check(bool(r) and (not r["dur"] or r["mark"][3] <= r["dur"][1]), f"[{w}] la marca no choca con la duración")
        shot(f"tarjeta_marca_{w}.png")
        go("#inicio", 2); refresh()
        if js("!!document.querySelector('.thumb.tile .saved-mark')"):
            see(".thumb.tile"); shot(f"tarjeta_marca_seguir_viendo_{w}.png")
        else:
            print("aviso: Inicio sin una tarjeta «Seguir viendo» marcada")

        # ---- página #guardados ----
        lists = [{"id": LIST, "title": "Para el viaje", "count": 12, "done": 12}, {"id": "PLOTRA", "title": "Documentales", "count": 5, "done": 2}]
        gl = [vid(v, lists=[LIST]) for v in LIST_VIDS[:3]] + [vid(vids[20], lists=["PLOTRA"], state="bajando", progress=0.2, bytes=30_000_000),
              vid(vids[21], lists=["PLOTRA"], state="pendiente", progress=0, bytes=0)] + mixed
        set_off(gl, lists, used=3_200_000_000); go("#guardados", 1.5); refresh()
        check("Usa 3,2 GB de 100 GB" in js("document.querySelector('.off-sum').innerText"), f"[{w}] resumen: «Usa 3,2 GB de 100 GB»")
        shot(f"guardados_1_{w}.png")
        see(".off-sec"); shot(f"guardados_2_listas_{w}.png")
        set_off([], [], used=0); refresh()
        check("nada guardado" in js("document.querySelector('main').innerText").lower(), f"[{w}] #guardados vacío")
        shot(f"guardados_3_vacio_{w}.png")
        # quitar con confirmación y petición
        set_off([vid(V1)], [], used=184_000_000); refresh()
        js("window.confirm = () => true; window.__calls = []; true")
        js("document.querySelector('.lrow .icon-btn').click(); true"); time.sleep(1.2)
        check(json.loads(js("JSON.stringify(window.__calls)"))[-1:] == [["/api/offline/remove", json.dumps({"id": V1["id"]}, separators=(",", ":"))]], f"[{w}] quitar manda POST /api/offline/remove {{id}}")

        # ---- Ajustes ----
        set_off([vid(v) for v in vids[:12]], [], used=3_200_000_000); go("#fila", 1.5); refresh()
        check("usa 3,2 GB de 100 GB · 12 videos" in js("document.getElementById('sinconexion').innerText"), f"[{w}] Ajustes: «usa 3,2 GB de 100 GB · 12 videos»")
        check(js("document.querySelector('#sinconexion a').getAttribute('href')") == "#guardados", f"[{w}] Ajustes: enlace a #guardados")
        see("#sinconexion"); shot(f"ajustes_{w}.png")
        set_off([vid(v) for v in vids[:12]], [], used=100_000_000_000); refresh()
        check("Se llenó el espacio" in js("document.getElementById('sinconexion').innerText"), f"[{w}] Ajustes: aviso de espacio lleno")

        # ---- errores de red ----
        js("window.__fail = true; offAt = 0; true"); go("#guardados", 1.5)
        js("offAt = 0; loadOffline(); true"); time.sleep(1)
        check(js("document.getElementById('toast').classList.contains('err')") and "No se pudo leer" in js("document.getElementById('toast').textContent"), f"[{w}] sin red: aviso claro")
        shot(f"guardados_4_sin_red_{w}.png") if width == 1280 else None
        js("window.__fail = false; true")

    # ---- errores de JavaScript ----
    errs = json.loads(js("JSON.stringify(window.__errs)"))
    check(not errs, "sin errores de JavaScript en la consola" + (": " + "; ".join(errs[:4]) if errs else ""))
finally:
    proc.terminate()
print("\nPROBLEMAS:" if problems else "\nTodo bien.")
for p in problems:
    print(" -", p)
sys.exit(1 if problems else 0)
