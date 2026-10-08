# El asistente del primer arranque (/bienvenida) de punta a punta, con Chrome sin ventana, a 1280 y a 390 px.
# Arma una «casa» inventada en una carpeta temporal (la carpeta personal, un disco con una biblioteca de otro programa,
# uno sin permiso, la música), un Roku falso que «instala» la app, una TV con Android que se conecta, Windows que
# bloquea la entrada y OpenSubtitles falso. Nada sale de esta computadora: el servidor escucha solo en 127.0.0.1.
# Uso: python3 pruebas/web_asistente.py CARPETA_DE_CAPTURAS [puerto=8809]
# (usa el puerto dado para 1280 px y el siguiente para 390 px). Termina con código 1 si algo no salió como se espera.
import base64, json, os, re, shutil, subprocess, sys, tempfile, threading, time, urllib.request
from pathlib import Path

OUT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else sys.exit("Uso: python3 pruebas/web_asistente.py CARPETA [puerto]")
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8809
ROOT = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="one-tv-asistente-")).resolve()
HOME = TMP / "casa"
REAL_HOME = os.environ.get("HOME", "")
os.environ["HOME"] = str(HOME)   # todo lo del servidor (datos, caché, «~») en la casa inventada
os.environ["CINE_NO_BROWSER"] = "1"
sys.path.insert(0, str(ROOT / "mac"))
OUT.mkdir(parents=True, exist_ok=True)


def video(path, mb=40):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.truncate(mb * 1024 * 1024)   # archivo «vacío» del tamaño de un video (no ocupa disco)


def armar(base):
    """La casa inventada: -> (lugares, carpeta de la biblioteca, carpeta de música)."""
    home = base
    biblio = home / "Movies" / "Biblioteca"
    biblio.mkdir(parents=True)
    for n in ("Uno", "Dos", "Tres"):
        video(home / "Movies" / "Conciertos" / f"Concierto {n}.mp4")
    disco = base.parent / "Volumes" / "Respaldo"
    for t, y in (("El viaje", 1999), ("La casa", 2004), ("Otoño", 2011), ("Los otros", 2001), ("Nubes", 2016)):
        video(disco / "Videos" / "Movies" / f"{t} ({y})" / f"{t} ({y}).mkv")
    for s, eps in (("La serie", 3), ("Otra serie", 2)):
        for e in range(1, eps + 1):
            video(disco / "Videos" / "TV Shows" / s / "Season 01" / f"{s} - S01E{e:02d}.mkv")
    video(disco / "Documentales" / "Mar" / "Mar (2020).mp4")
    video(disco / "Documentales" / "Aire" / "Aire (2021).mp4")
    video(disco / "Documentales" / "Fuego (2022).mp4")
    (disco / "Películas nuevas").mkdir()
    viejo = base.parent / "Volumes" / "Viejo"
    video(viejo / "x.mkv")
    viejo.chmod(0)
    musica = home / "Music" / "Mi música"
    for n in range(12):
        (musica / "Artista" / "Álbum").mkdir(parents=True, exist_ok=True)
        (musica / "Artista" / "Álbum" / f"{n:02d} Canción.mp3").write_bytes(b"\0" * 100)
    lugares = [{"ruta": home / "Movies", "tipo": "casa", "nombre": "Movies"},
               {"ruta": disco, "tipo": "disco", "nombre": "Respaldo"},
               {"ruta": viejo, "tipo": "disco", "nombre": "Viejo"}]
    return lugares, biblio, musica


lugares, BIBLIO, MUSICA = armar(HOME)

import cine, asistente, hostos, roku, subs_auto, subtitles_online  # noqa: E402  (después de cambiar HOME)
from server import serve  # noqa: E402
from transcode import Transcoder  # noqa: E402
from live import CDP, find_chrome  # noqa: E402

hostos.lan_url = lambda port: f"http://192.0.2.7:{port}"   # una dirección de ejemplo, no la de esta casa
cine.tailscale_url = lambda port: None
cine.tailscale_cli = lambda: None
cine.tailscale_serve = lambda port: (None, "prueba")
cine.service_installed = lambda: True
for name in ("watch_roku", "keep_library_fresh", "watch_downloads", "keep_account_fresh", "keep_avatars",
             "keep_ytdlp_fresh", "keep_tv_app_fresh", "warm_up"):
    setattr(cine.App, name, lambda self, *a, **k: None)
cine.App.connect_roku = lambda self, force=False: False
subs_auto.AutoSubtitles.watch = lambda self: None   # ni los subtítulos automáticos (irían a OpenSubtitles de verdad)


class RokuFalso:
    """Un Roku inventado (192.0.2.10): «instala» la app en 2 s si la contraseña es la del asistente."""
    instalados = []

    def __init__(self, ip, password=""):
        self.ip, self.dev_password = ip, password

    def device_name(self):
        return "TV de la sala"

    def install(self, zip_bytes):
        time.sleep(2)
        RokuFalso.instalados.append(self.dev_password)
        return True, "app instalada"

    def active_app(self):
        return ""

    def player(self):
        return ("", None, None)

    def __getattr__(self, _):
        return lambda *a, **k: None


roku.Roku, roku.discover, roku.local_ip_towards = RokuFalso, (lambda timeout=3: "192.0.2.10"), (lambda ip: "192.0.2.7")


class OpenSubtitlesFalso(subtitles_online.OpenSubtitles):
    def _request(self, method, path, params=None, body=None, auth=False, retry=True, tries_429=2):
        if self.api_key != "clave-de-prueba":
            raise subtitles_online.SubtitleError("no", code=401)
        if path == "/login" and (self.username, self.password) != ("ana", "secreto"):
            raise subtitles_online.SubtitleError("no", code=401)
        return {"token": "t"}


subtitles_online.OpenSubtitles = OpenSubtitlesFalso


class Firewall:
    """Windows que bloquea la entrada hasta que se toca «Permitir»."""
    pedidos = 0

    @staticmethod
    def allow(port):
        Firewall.pedidos += 1
        time.sleep(1)
        return ""

    @staticmethod
    def status(port):
        return False


def arrancar(port, base):
    cine.CONFIG = base / "config.json"
    cine.CONFIG.write_text(json.dumps({
        "carpetas": [hostos.tilde(BIBLIO)], "puerto": port, "roku_ip": "", "roku_password": "", "titulos": {},
        "musica": [], "descargas": [], "opensubtitles": {"api_key": "", "usuario": "", "clave": ""},
        "bienvenida_hecha": False}, ensure_ascii=False, indent=2))
    cine.CACHE = base / "cache"
    cine.DATA = base / "datos"
    cfg = cine.load_config()
    app = cine.App(cfg)
    app.transcoder = Transcoder(cine.CACHE)
    app.roku, app.roku_name = RokuFalso("192.0.2.10"), "TV de la sala"   # «Encontré un Roku en tu casa»
    app.asistente.places = lambda: lugares
    app.asistente.firewall = Firewall
    app.library.scan(force=True)
    httpd = serve(app, port, "127.0.0.1")
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return app, httpd


STUB = """
(() => {
  window.__errs = [];
  window.addEventListener("error", e => __errs.push("error: " + e.message));
  window.addEventListener("unhandledrejection", e => __errs.push("promesa: " + e.reason));
  const ce = console.error; console.error = (...a) => { __errs.push("console.error: " + a.join(" ")); ce(...a); };
})();
"""

problems = []


def check(cond, what):
    print(("ok    " if cond else "FALLA ") + what, flush=True)
    if not cond:
        problems.append(what)


def paleta():
    """Todos los colores salen del bloque :root (como pruebas/web_fase4.py revisa en la web)."""
    html = (ROOT / "mac" / "web" / "bienvenida.html").read_text()
    style = html.split("<style>", 1)[1].split("</style>", 1)[0]
    block = re.search(r":root \{.*?\n  \}", style, re.S).group(0)
    rest = style.replace(block, "") + html.split("<script>", 1)[1]
    loose = sorted(set(re.findall(r"#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)|hsla?\([^)]*\)", rest)))
    radii = sorted(set(re.findall(r"border-radius: ([^;]+);", style)) - {"0", "2px", "50%"})
    check(not loose, f"Colores solo del bloque :root ({loose or 'ninguno suelto'})")
    check(not radii, f"Esquinas de 2 px o rectas ({radii or 'bien'})")
    check("system-ui" not in style and "-apple-system" not in style, "Letras propias (sin la del sistema)")
    for palabra in ("config.json", "endpoint", "launchd", "NAS"):
        visibles = re.findall(r'"([^"]*' + re.escape(palabra) + r'[^"]*)"', html.split("<script>", 1)[1])
        visibles = [v for v in visibles if not v.startswith(("/api", "#", "http"))]
        check(not visibles, f"Sin «{palabra.strip()}» en lo que se ve ({visibles[:2] or 'bien'})")


def correr(width, port):
    w = str(width)
    base = TMP / f"servidor-{width}"
    base.mkdir()
    app, httpd = arrancar(port, base)
    apagar = threading.Event()
    url = f"http://127.0.0.1:{port}"
    check(json.loads(urllib.request.urlopen(url + "/api/status", timeout=10).read()).get("bienvenida_pendiente") is True,
          f"[{width}] el servidor de prueba contesta")
    profile = tempfile.mkdtemp(prefix="cine-asistente-chrome-")
    chrome = subprocess.Popen([find_chrome(), "--headless=new", "--remote-debugging-port=0", f"--user-data-dir={profile}",
                               "--no-first-run", "--mute-audio", f"--window-size={width},900", "about:blank"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              env={**os.environ, "HOME": REAL_HOME})   # Chrome, con su carpeta de siempre
    try:
        pf = Path(profile) / "DevToolsActivePort"
        for _ in range(200):
            if pf.exists() and pf.read_text().strip():
                break
            time.sleep(0.1)
        cport = int(pf.read_text().split()[0])
        cdp = CDP(json.loads(urllib.request.urlopen(f"http://127.0.0.1:{cport}/json/version").read())["webSocketDebuggerUrl"])
        target = cdp.call("Target.createTarget", {"url": "about:blank"})["targetId"]
        s = cdp.call("Target.attachToTarget", {"targetId": target, "flatten": True})["sessionId"]
        cdp.call("Emulation.setDeviceMetricsOverride", {"width": width, "height": 900 if width > 600 else 844,
                                                         "deviceScaleFactor": 1, "mobile": width < 600}, s)
        cdp.call("Page.enable", {}, s)
        cdp.call("Page.addScriptToEvaluateOnNewDocument", {"source": STUB}, s)

        def js(expr):
            r = cdp.call("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True}, s)
            if "exceptionDetails" in r:
                problems.append(f"[{w}] excepción: {expr[:70]} -> " + json.dumps(r["exceptionDetails"].get("exception", {}).get("description", ""))[:200])
            return r.get("result", {}).get("value")

        def esperar(expr, segundos=15):
            fin = time.time() + segundos
            while time.time() < fin:
                if js(expr):
                    return True
                time.sleep(0.2)
            return False

        alto_pantalla = 900 if width > 600 else 844

        def pantalla(alto):
            cdp.call("Emulation.setDeviceMetricsOverride", {"width": width, "height": alto, "deviceScaleFactor": 1,
                                                             "mobile": width < 600}, s)

        def foto(nombre, completa=True):
            time.sleep(0.4)
            check(js("document.documentElement.scrollWidth <= innerWidth + 1"), f"[{w}] {nombre}: sin desborde a lo ancho")
            check(js("[...document.querySelectorAll('.barra button, main button, main a.btn')].every(b => !b.offsetParent || "
                     "b.getBoundingClientRect().right <= innerWidth + 1)"), f"[{w}] {nombre}: los botones caben")
            if completa:   # la página entera, con la barra de abajo al final (como se ve al bajar hasta el fondo)
                pantalla(max(alto_pantalla, js("document.documentElement.scrollHeight")))
                time.sleep(0.4)
            (OUT / f"{w}-{nombre}.png").write_bytes(base64.b64decode(cdp.call("Page.captureScreenshot", {"format": "png"}, s)["data"]))
            if completa:
                pantalla(alto_pantalla)

        def clic(selector):
            ok = js(f"(() => {{ const e = document.querySelector({json.dumps(selector)}); if (!e) return false; e.click(); return true; }})()")
            check(bool(ok), f"[{w}] existe {selector}")
            time.sleep(0.3)

        def texto(selector="main"):
            return js(f"(document.querySelector({json.dumps(selector)}) || {{}}).innerText || ''") or ""

        # ---- llega desde la página principal ----
        cdp.call("Page.navigate", {"url": url + "/"}, s)
        check(esperar("location.pathname === '/bienvenida' && !!document.querySelector('#empezar')"),
              f"[{w}] la primera vez «/» manda a la bienvenida")
        check(esperar("document.fonts.check('800 20px \"Big Shoulders Display\"') && document.fonts.check('16px Archivo')"),
              f"[{w}] letras de One TV cargadas")
        check("Te ayudo a dejarlo listo en unos minutos" in texto(), f"[{w}] paso 0: el texto de bienvenida")
        foto("0-bienvenida")
        clic("#empezar")

        # ---- 1. Tus videos ----
        check(esperar("!!document.querySelector('#carpetas')", 20), f"[{w}] paso 1: terminó de buscar carpetas")
        t = texto()
        check("Biblioteca" in t and "Conciertos" in t and "3 películas" in t, f"[{w}] paso 1: la biblioteca y «Conciertos» con su cuenta")
        check("Videos" in t and "5 películas y 2 series" in t and "En el disco «Respaldo»" in t, f"[{w}] paso 1: la biblioteca del disco, con su cuenta")
        check("SOLO LECTURA" in t.upper(), f"[{w}] paso 1: «Solo lectura» en la de otro programa")
        check("Documentales" in t and "Fotos" not in t, f"[{w}] paso 1: las carpetas del disco por separado (sin las vacías)")
        check("No puedo abrir esta carpeta" in t, f"[{w}] paso 1: la carpeta sin permiso en guinda")
        check("NAS" not in t, f"[{w}] paso 1: no menciona NAS")
        clic("#carpetas .carpeta.mal button")
        check("Privacidad y seguridad" in texto() or "permiso" in texto(), f"[{w}] paso 1: «Cómo arreglarlo» explica qué hacer")
        foto("1-tus-videos")
        # Quitar «Documentales» y agregar una carpeta con el explorador.
        js("[...document.querySelectorAll('#carpetas label')].find(l => l.innerText.includes('Documentales')).click()")
        clic("#agregar")
        check(esperar("!document.querySelector('#velo').hidden && document.querySelectorAll('#exp-lista button').length > 0"),
              f"[{w}] explorador: abre con los lugares")
        foto("1b-explorador", completa=False)
        js("[...document.querySelectorAll('#exp-lista button')].find(b => b.innerText.includes('Respaldo')).click()")
        check(esperar("document.querySelector('#exp-t').textContent === 'Respaldo'"), f"[{w}] explorador: entra al disco")
        nombres = js("[...document.querySelectorAll('#exp-lista .n')].map(e => e.textContent)")
        check(nombres == ["Documentales", "Películas nuevas", "Videos"], f"[{w}] explorador: solo carpetas, sin ocultas ({nombres})")
        js("[...document.querySelectorAll('#exp-lista button')].find(b => b.innerText.includes('Películas nuevas')).click()")
        check(esperar("document.querySelector('#exp-t').textContent === 'Películas nuevas'"), f"[{w}] explorador: entra a «Películas nuevas»")
        foto("1c-explorador-carpeta", completa=False)
        clic("#exp-elegir")
        check(esperar("document.querySelector('#velo').hidden && document.querySelector('#carpetas').innerText.includes('Películas nuevas')"),
              f"[{w}] explorador: la carpeta elegida aparece marcada")
        clic("#sig")
        check(esperar("!!document.querySelector('#tv-roku')"), f"[{w}] paso 1 → 2 guarda y sigue")
        cfg = json.loads(cine.CONFIG.read_text())
        disco = HOME.parent / "Volumes" / "Respaldo"
        esperadas = [hostos.tilde(BIBLIO), hostos.tilde(HOME / "Movies" / "Conciertos"), str(disco / "Videos"), str(disco / "Películas nuevas")]
        check(sorted(cfg["carpetas"]) == sorted(esperadas), f"[{w}] config: las carpetas elegidas ({cfg['carpetas']})")
        check(cfg.get("solo_leer") == {hostos.tilde(HOME / "Movies" / "Conciertos"): True, str(disco / "Videos"): True},
              f"[{w}] config: las que ya tenían videos acomodados, solo para leer ({cfg.get('solo_leer')})")
        check(sorted(str(r) for r in app.library.roots) == sorted(str(Path(os.path.expanduser(e)).resolve()) for e in esperadas),
              f"[{w}] la biblioteca ya usa las carpetas nuevas (sin reiniciar)")

        # ---- 2. Tu TV: Roku ----
        t = texto()
        clave = json.loads(cine.CONFIG.read_text()).get("roku_password", "")
        check("Encontré un Roku en tu casa" in t, f"[{w}] paso 2: dice que encontró el Roku")
        check(bool(re.fullmatch(r"[a-z]{4}\d\d", clave or "")) and texto("#clave") == clave, f"[{w}] paso 2: la contraseña inventada, en grande ({clave})")
        check(js("document.querySelector('#tv-roku').getAttribute('aria-pressed')") == "true", f"[{w}] paso 2: Roku preseleccionado")
        foto("2-roku")
        clic("#instalar-roku")
        check(esperar("document.querySelector('#panel-roku').innerText.includes('Instalando')", 5), f"[{w}] Roku: muestra el avance")
        foto("2b-roku-instalando")
        check(esperar("document.querySelector('#panel-roku').innerText.includes('Listo: One TV ya está en tu Roku')", 10),
              f"[{w}] Roku: instalada")
        check(RokuFalso.instalados[-1:] == [clave], f"[{w}] Roku: se instaló con la contraseña del asistente")
        foto("2c-roku-listo")

        # ---- 2. Tu TV: Google TV / Android TV / Fire TV ----
        clic("#tv-android")
        check("192.0.2.7:" + str(port) + "/tv" == texto("#direccion-tv"), f"[{w}] Android: la dirección para Downloader")
        check("Esperando a que tu TV se conecte" in texto(), f"[{w}] Android: esperando a la TV")
        foto("2d-android-esperando")

        def tele():   # la app de la TV deja su consulta esperando, una tras otra, mientras está abierta
            while not apagar.is_set():
                try:
                    urllib.request.urlopen(f"{url}/api/tv/ordenes?device_id=androidtv-prueba&nombre=TV%20del%20cuarto", timeout=30).read()
                except OSError:
                    time.sleep(0.5)
        threading.Thread(target=tele, daemon=True).start()
        check(esperar("document.querySelector('#tv-estado').innerText.includes('Tu TV está conectada')", 8),
              f"[{w}] Android: «Tu TV está conectada» cuando la app se conecta")
        foto("2e-android-conectada")
        # Windows bloquea la entrada: «Permitir».
        app.network_blocked, app.asistente.windows = True, True
        js("cargarEstado().then(render)")
        check(esperar("!!document.querySelector('#permitir')", 6), f"[{w}] Windows: «Tu TV no puede entrar…» con «Permitir»")
        foto("2f-windows-bloquea")
        clic("#permitir")
        check(esperar("!document.querySelector('#aviso-red')", 6) and Firewall.pedidos >= 1, f"[{w}] Windows: «Permitir» pide el permiso y se quita el aviso")
        app.asistente.windows = False

        # ---- 3. Extras ----
        clic("#sig")
        check(esperar("!!document.querySelector('#extras')"), f"[{w}] paso 3: extras")
        check("No encontré tu música" in texto("#x-musica"), f"[{w}] música: no encontrada, «Elegir carpeta»")
        foto("3-extras")
        clic("#elegir-musica")
        check(esperar("document.querySelectorAll('#exp-lista button').length > 0"), f"[{w}] música: el explorador")
        js("[...document.querySelectorAll('#exp-lista button')].find(b => b.innerText.includes('Tu carpeta personal')).click()")
        check(esperar("document.querySelector('#exp-t').textContent === 'casa'"), f"[{w}] música: la carpeta personal")
        js("[...document.querySelectorAll('#exp-lista button')].find(b => b.innerText.includes('Music')).click()")
        esperar("document.querySelector('#exp-t').textContent === 'Music'")
        js("[...document.querySelectorAll('#exp-lista button')].find(b => b.innerText.includes('Mi música')).click()")
        esperar("document.querySelector('#exp-t').textContent === 'Mi música'")
        clic("#exp-elegir")
        check(esperar("document.querySelector('#x-musica').innerText.includes('12 canciones')"), f"[{w}] música: «✓ Lista» con 12 canciones")
        check(json.loads(cine.CONFIG.read_text()).get("musica") == [hostos.tilde(MUSICA)], f"[{w}] config: la música")
        clic("#activar-subs")
        js("document.querySelector('#os-clave').value = 'otra'; document.querySelector('#os-usuario').value = 'ana';"
           "document.querySelector('#os-contrasena').value = 'secreto'; true")
        clic("#guardar-subs")
        check(esperar("document.querySelector('#x-subs').innerText.includes('no reconoce esa clave')"), f"[{w}] subtítulos: una clave mala se dice")
        foto("3b-subtitulos")
        js("document.querySelector('#os-clave').value = 'clave-de-prueba'; true")
        clic("#guardar-subs")
        check(esperar("document.querySelector('#x-subs').innerText.includes('Activos')"), f"[{w}] subtítulos: comprobados y activos")
        os_cfg = json.loads(cine.CONFIG.read_text()).get("opensubtitles", {})
        check(os_cfg.get("api_key") == "clave-de-prueba" and os_cfg.get("usuario") == "ana", f"[{w}] config: OpenSubtitles")
        js("[...document.querySelectorAll('#x-youtube button')].find(b => b.innerText.includes('Traer')).click()")
        time.sleep(0.3)
        clic("#ya-youtube")
        check(esperar("document.querySelector('#x-youtube').innerText.includes('Todavía no está en Descargas')"), f"[{w}] YouTube: sin Takeout lo dice")
        clic("#como-fuera")
        check("Tailscale" in texto("#x-fuera"), f"[{w}] fuera de casa: explica cómo")
        foto("3c-extras-abiertos")

        # ---- 4. Listo ----
        clic("#sig")
        check(esperar("!!document.querySelector('#resumen')"), f"[{w}] paso 4: listo")
        time.sleep(0.6)
        t = texto()
        check("arranca solo cada vez que prendes esta computadora" in t, f"[{w}] paso 4: arranca solo")
        check("Tus videos: 4 carpetas" in t and "Tu música" in t and "Subtítulos" in t and "TV del cuarto" in t, f"[{w}] paso 4: el resumen")
        check("192.0.2.7:" + str(port) in t, f"[{w}] paso 4: la dirección para el teléfono")
        if width > 640:
            check(esperar("document.querySelector('img.qr').complete && document.querySelector('img.qr').naturalWidth === 440"), f"[{w}] paso 4: el código QR")
        check(json.loads(cine.CONFIG.read_text()).get("bienvenida_hecha") is True, f"[{w}] config: bienvenida hecha")
        foto("4-listo")
        clic("#abrir")
        check(esperar("location.pathname === '/' && !!document.querySelector('main')"), f"[{w}] «Abrir One TV» va a la página principal (ya sin la bienvenida)")
        js("location.hash = '#fila'; true")
        check(esperar("!!document.querySelector('#asistente a[href=\"/bienvenida\"]')", 10), f"[{w}] Ajustes: «Abrir el asistente»")
        js("document.querySelector('#asistente').scrollIntoView({block: 'center'}); true")
        foto("5-ajustes", completa=False)

        # ---- otro aparato, ya terminada: no se puede ----
        real = asistente.is_local
        asistente.is_local = lambda *a: False
        try:
            cdp.call("Page.navigate", {"url": url + "/bienvenida"}, s)
            check(esperar("document.querySelector('main').innerText.includes('solo se abre en la computadora')"), f"[{w}] otro aparato: «Ya está configurado»")
            foto("6-otro-aparato")
        finally:
            asistente.is_local = real
        errs = js("window.__errs") or []
        check(not errs, f"[{w}] sin errores de JavaScript {errs[:3]}")
    finally:
        apagar.set()
        app.teles.adios("androidtv-prueba")
        chrome.terminate()
        try:
            chrome.wait(10)
        except subprocess.TimeoutExpired:
            chrome.kill()
        httpd.shutdown()
        httpd.server_close()
        shutil.rmtree(profile, ignore_errors=True)


try:
    paleta()
    correr(1280, PORT)
    correr(390, PORT + 1)
finally:
    (HOME.parent / "Volumes" / "Viejo").chmod(0o755)
    shutil.rmtree(TMP, ignore_errors=True)
    os.environ["HOME"] = REAL_HOME
print(f"\nCapturas en {OUT}")
if problems:
    print("\n" + str(len(problems)) + " problema(s):\n  " + "\n  ".join(problems))
    sys.exit(1)
print("Todo bien.")
