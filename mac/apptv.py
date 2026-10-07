"""La app de One TV para Google TV, Android TV y Fire TV, lista para instalar con «Downloader»: la computadora la
ofrece en http://<computadora>:<puerto>/tv (una dirección corta, fácil de escribir con el control).

¿De dónde sale? Si en esta computadora se compiló la app (androidtv/, `./gradlew :app:assembleRelease`), esa: es para
quien la está desarrollando. Si no, la versión más nueva publicada en GitHub (versiones «tv-…» con el archivo
one-tv-tv.apk, que arma .github/workflows/app-tv.yml): se baja sola a la caché y se revisa una vez al día, como yt-dlp.
"""

import json
import re
import time
import urllib.request
from pathlib import Path

REPO = "julai1433/one-tv"
VERSIONES = f"https://api.github.com/repos/{REPO}/releases?per_page=30"
PAGINA = f"https://github.com/{REPO}/releases"
APK = "one-tv-tv.apk"        # nombre fijo del archivo en cada versión de GitHub
DATOS = "one-tv-tv.json"     # {"version": "0.1.37", "version_code": 38}, junto al archivo
CADA = 24 * 3600
PEDIDA = 5 * 60   # si alguien pide la app y no la hay, se pregunta a GitHub ya (a lo mucho una vez cada 5 min)
TIPO = "application/vnd.android.package-archive"
UA = {"User-Agent": "one-tv (servidor de la casa)", "Accept": "application/vnd.github+json"}


class AppTv:
    def __init__(self, cache_dir, compilada_dir=None, log=print, abrir=urllib.request.urlopen):
        self.dir = Path(cache_dir)
        self.compilada_dir = Path(compilada_dir) if compilada_dir else None
        self.log = log
        self._abrir = abrir
        self._pedida = 0.0

    # ---------- cuál se ofrece ----------

    def compilada(self):
        """La que se compiló en esta computadora (androidtv/app/build/outputs/apk/release/), o None."""
        d = self.compilada_dir
        if not d or not d.is_dir():
            return None
        version, code, archivo = "", 0, None
        try:   # lo escribe Gradle junto al archivo: {"elements": [{"versionCode", "versionName", "outputFile"}]}
            meta = json.loads((d / "output-metadata.json").read_text(encoding="utf-8"))
            e = (meta.get("elements") or [{}])[0]
            version, code = str(e.get("versionName") or ""), int(e.get("versionCode") or 0)
            if e.get("outputFile") and (d / e["outputFile"]).is_file():
                archivo = d / e["outputFile"]
        except (OSError, ValueError, TypeError, AttributeError, IndexError):
            pass
        if archivo is None:
            apks = sorted(d.glob("*.apk"), key=lambda p: p.stat().st_mtime, reverse=True)
            if not apks:
                return None
            archivo = apks[0]
        return {"path": archivo, "version": version, "version_code": code, "origen": "compilada"}

    def descargada(self):
        """La última bajada de GitHub (en la caché), o None."""
        archivo = self.dir / APK
        if not archivo.is_file():
            return None
        meta = self._meta()
        return {"path": archivo, "version": meta.get("version", ""), "version_code": int(meta.get("version_code") or 0),
                "origen": "github"}

    def actual(self):
        return self.compilada() or self.descargada()

    def actual_o_buscar(self):
        """La app para entregarla ya. Si esta computadora todavía no la tiene (por ejemplo, se publicó después de que
        arrancó el servidor), se le pregunta a GitHub en ese momento en lugar de esperar a la revisión de cada día."""
        got = self.actual()
        if got or time.time() - self._pedida < PEDIDA:
            return got
        self._pedida = time.time()
        try:
            msg = self.actualizar()
            if msg:
                self.log(msg)
        except Exception as e:  # noqa: BLE001 - sin internet o GitHub no responde: la página lo dice en llano
            self.log(f"⚠ App para Google TV: no se pudo bajar de GitHub ({e})")
        return self.actual()

    def info(self):
        """Lo que se dice afuera (la web, la app de la TV): sin rutas de esta computadora."""
        a = self.actual()
        if not a:
            return {"hay": False, "version": "", "version_code": 0, "origen": ""}
        return {"hay": True, "version": a["version"], "version_code": a["version_code"], "origen": a["origen"]}

    def _meta(self):
        try:
            return json.loads((self.dir / "version.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    # ---------- bajar la más nueva de GitHub ----------

    def _leer(self, url, timeout=60):
        req = urllib.request.Request(url, headers=UA)
        with self._abrir(req, timeout=timeout) as r:
            return r.read()

    def actualizar(self):
        """Busca la versión «tv-…» más nueva en GitHub y, si es otra, la baja. -> mensaje para el registro o None."""
        versiones = json.loads(self._leer(VERSIONES))
        nueva = None
        for v in versiones if isinstance(versiones, list) else []:
            if v.get("draft") or not str(v.get("tag_name", "")).startswith("tv-"):
                continue
            archivos = {a.get("name"): a.get("browser_download_url") for a in v.get("assets") or []}
            if archivos.get(APK):
                nueva = (v["tag_name"], archivos)
                break   # GitHub las da de la más nueva a la más vieja
        if not nueva:
            return None
        tag, archivos = nueva
        if self._meta().get("tag") == tag and (self.dir / APK).is_file():
            return None
        datos = {}
        if archivos.get(DATOS):
            try:
                datos = json.loads(self._leer(archivos[DATOS]))
            except (OSError, ValueError):
                datos = {}
        apk = self._leer(archivos[APK], timeout=300)
        if not apk.startswith(b"PK"):   # un .apk es un .zip: si no empieza así, llegó otra cosa
            raise ValueError("lo que bajó de GitHub no es una app")
        self.dir.mkdir(parents=True, exist_ok=True)
        parcial = self.dir / (APK + ".parcial")
        parcial.write_bytes(apk)
        parcial.replace(self.dir / APK)
        version = str(datos.get("version") or re.sub(r"^tv-v?", "", tag))
        meta = {"tag": tag, "version": version, "version_code": int(datos.get("version_code") or 0), "at": time.time()}
        (self.dir / "version.json").write_text(json.dumps(meta), encoding="utf-8")
        return f"✓ App para Google TV / Android TV / Fire TV lista para instalar: versión {version}"

    def mantener_al_dia(self):
        """Tarea automática: revisa GitHub al arrancar y una vez al día. Nunca debe tumbar el servidor."""
        while True:
            try:
                msg = self.actualizar()
                if msg:
                    self.log(msg)
            except Exception as e:  # noqa: BLE001 - sin internet o GitHub no responde: se intenta mañana
                self.log(f"⚠ App para Google TV: no se pudo revisar si hay una versión nueva ({e})")
            time.sleep(CADA)


def pagina_sin_app():
    """Lo que ve quien escribe la dirección en «Downloader» cuando la computadora todavía no tiene la app."""
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>One TV para la TV</title>
<style>
  @font-face {{ font-family: "Archivo"; src: url("/fonts/Archivo-Regular.woff2") format("woff2"); font-weight: 400; }}
  @font-face {{ font-family: "Archivo"; src: url("/fonts/Archivo-Bold.woff2") format("woff2"); font-weight: 700; }}
  :root {{ --bg: #000000; --text: #F2F2EE; --text-soft: #C9C9C2; --lime: #A6E22E; }}
  body {{ background: var(--bg); color: var(--text); font: 28px/1.4 "Archivo", sans-serif; margin: 0; padding: 48px; }}
  h1 {{ font-size: 44px; margin: 0 0 24px; }}
  p {{ color: var(--text-soft); max-width: 40ch; }}
  b {{ color: var(--lime); font-weight: 700; }}
</style></head><body>
<h1>Todavía no hay app para esta TV</h1>
<p>La computadora con One TV aún no tiene la app para Google TV, Android TV y Fire TV. La baja sola de internet en
cuanto está publicada: prueba otra vez más tarde con esta misma dirección.</p>
<p>También puedes bajarla tú desde <b>{PAGINA}</b> (el archivo <b>{APK}</b>).</p>
</body></html>
"""
