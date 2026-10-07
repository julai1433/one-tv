# Pruebas sin red de lo que protege a la computadora de quien llegue al puerto del servidor:
# - las direcciones de las listas (las que la TV pide a través de la computadora) van firmadas: no se puede pedir
#   otra cosa, y menos un archivo de la computadora (file://);
# - las órdenes (POST) solo en JSON y sin permiso para otros sitios (una página web cualquiera no puede usarlas);
# - el Takeout solo se importa desde Descargas.
# Uso: python3 -m unittest pruebas/test_seguridad.py
import base64, json, sys, tempfile, threading, unittest, urllib.error, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mac"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import live
import youtube
from server import serve
from segcache import SegmentCache
from test_canales_ocultos import Base, Falso


def b64(text):
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


class Firmas(unittest.TestCase):
    def test_ida_y_vuelta(self):
        url = "https://manifest.googlevideo.com/api/x.m3u8?a=1"
        self.assertEqual(live.decode_url(live.encode_url(url)), url)

    def test_sin_firma_o_firma_falsa(self):
        for token in (b64("https://ejemplo.com/a.ts"), b64("https://ejemplo.com/a.ts") + "~AAAAAAAAAAAAAAAA"):
            with self.assertRaises(ValueError):
                live.decode_url(token)

    def test_nunca_archivos_de_la_computadora(self):
        token = b64("file:///etc/hosts") + "~" + live._sign("file:///etc/hosts")   # aunque estuviera firmado
        with self.assertRaises(ValueError):
            live.decode_url(token)
        for fetch in (lambda u: live.fetch(u, {}), lambda u: youtube.fetch4(u, {})):
            with self.assertRaises(ValueError):
                fetch("file:///etc/hosts")

    def test_otra_clave_no_sirve(self):
        token = live.encode_url("https://ejemplo.com/a.ts")
        old = live._sign_key
        try:
            live.set_sign_key(b"x" * 32)
            with self.assertRaises(ValueError):
                live.decode_url(token)
        finally:
            live.set_sign_key(old)


class Servidor(Base):
    def setUp(self):
        super().setUp()
        self.app = Falso(self.dir, self.acc)
        self.app.segments = SegmentCache()
        self.app.keep_awake = type("K", (), {"poke": lambda self: None})()
        self.httpd = serve(self.app, 0, "127.0.0.1")
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.addCleanup(self.httpd.shutdown)
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def get(self, path):
        try:
            with urllib.request.urlopen(self.base + path, timeout=5) as r:
                return r.status, r.headers, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read()

    def post(self, path, body, ctype="application/json"):
        req = urllib.request.Request(self.base + path, json.dumps(body).encode(), {"Content-Type": ctype})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def test_no_se_leen_archivos_por_las_listas(self):
        secret = Path(self.dir) / "secreto.txt"
        secret.write_text("NO-DEBE-SALIR")
        for token in (b64(f"file://{secret}"), b64(f"file://{secret}") + "~" + live._sign(f"file://{secret}")):
            code, _, body = self.get(f"/yt/dQw4w9WgXcQ/s/{token}.ts")
            self.assertNotIn(b"NO-DEBE-SALIR", body)
            self.assertNotEqual(code, 200)

    def test_sin_permiso_para_otros_sitios(self):
        code, headers, _ = self.get("/api/yt/hidden")
        self.assertIsNone(headers.get("Access-Control-Allow-Origin"))

    def test_ordenes_solo_en_json(self):
        code, _ = self.post("/api/queue/clear", {}, ctype="text/plain")
        self.assertEqual(code, 415)
        code, _ = self.post("/api/queue/clear", {})
        self.assertEqual(code, 200)

    def test_takeout_solo_desde_descargas(self):
        code, body = self.post("/api/yt/import", {"path": "/etc/hosts"})
        self.assertEqual(json.loads(body)["ok"], False)
        self.assertIn("Descargas", json.loads(body)["error"])


if __name__ == "__main__":
    unittest.main()
