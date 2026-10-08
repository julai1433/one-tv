# El código de la TV para usar el asistente (/bienvenida) desde otro aparato cuando ya se terminó (mac/asistente.py,
# CodigoTele): se genera, llega al Roku y a las TV con Android (falsos), queda en el registro, vence, tiene pocos
# intentos y da una cookie que deja entrar un rato. Sin código no se puede; con código sí; la primera configuración y
# esta misma computadora siguen igual. Sin red ni TV.
# python3 -m unittest discover -s pruebas -p "test_codigo_tele.py"
import http.client, json, sys, threading, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mac"))
import asistente
from asistente import CODE_GAP, CODE_LIFE, CODE_TRIES, CODES_PER_HOUR, MAX_PASSES, PASS_LIFE, CodigoTele
from roku import Roku
from server import serve
from test_asistente import AppFalsa, ConCarpetasFalsas


class Reloj:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def azar(*numeros):
    """Un «secrets» que da estos números, en orden."""
    it = iter(numeros)
    return SimpleNamespace(randbelow=lambda n: next(it))


class ElCodigo(unittest.TestCase):
    def setUp(self):
        self.reloj = Reloj()

    def codigo(self, *numeros):
        return CodigoTele(clock=self.reloj, rng=azar(*numeros))

    def test_seis_cifras_y_una_sola_vez(self):
        c = self.codigo(4821, 999999)
        self.assertEqual(c.new(), ("004821", None))   # con los ceros de adelante
        token, error = c.check("004 821")              # con espacios también
        self.assertIsNone(error)
        self.assertGreaterEqual(len(token), 40)
        self.assertTrue(c.valid(token))
        self.assertEqual(c.check("004821"), (None, "Ese código ya no sirve. Pide otro."))   # ya se usó

    def test_pocos_intentos(self):
        c = self.codigo(123456)
        c.new()
        self.assertEqual(c.check("12345")[1], "Escribe los 6 números que aparecen en tu TV.")   # no cuenta como intento
        self.assertEqual(c.check("")[1], "Escribe los 6 números que aparecen en tu TV.")
        for falta in range(CODE_TRIES - 1, 1, -1):
            self.assertEqual(c.check("000000")[1], f"Ese no es el código. Te quedan {falta} intentos.")
        self.assertEqual(c.check("000000")[1], "Ese no es el código. Te queda 1 intento.")
        self.assertEqual(c.check("000000")[1], "Ese no es el código. Pide otro.")
        self.assertEqual(c.check("123456"), (None, "Ese código ya no sirve. Pide otro."))   # ni el bueno

    def test_vence(self):
        c = self.codigo(111111)
        c.new()
        self.reloj.t += CODE_LIFE + 1
        self.assertEqual(c.check("111111"), (None, "Ese código ya no sirve. Pide otro."))

    def test_pedir_otro_deja_sin_valor_al_anterior_y_hay_que_esperar(self):
        c = self.codigo(111111, 222222)
        c.new()
        codigo, error = c.new()
        self.assertIsNone(codigo)
        self.assertEqual(error, f"Espera {CODE_GAP} segundos para pedir otro código.")
        self.reloj.t += CODE_GAP
        self.assertEqual(c.new(), ("222222", None))
        self.assertEqual(c.check("111111")[1], "Ese no es el código. Te quedan 4 intentos.")
        self.assertIsNotNone(c.check("222222")[0])

    def test_pocos_codigos_por_hora(self):
        c = self.codigo(*range(100))
        for _ in range(CODES_PER_HOUR):
            self.assertIsNotNone(c.new()[0])
            self.reloj.t += CODE_GAP
        self.assertEqual(c.new(), (None, "Pediste muchos códigos seguidos. Prueba otra vez en un rato."))
        self.reloj.t += 3600
        self.assertIsNotNone(c.new()[0])

    def test_la_cookie_vale_un_rato(self):
        c = self.codigo(555555)
        c.new()
        token = c.check("555555")[0]
        self.reloj.t += PASS_LIFE - 1
        self.assertTrue(c.valid(token))
        self.reloj.t += 2
        self.assertFalse(c.valid(token))
        self.assertFalse(c.valid(""))
        self.assertFalse(c.valid("inventada"))

    def test_navegadores_autorizados_a_la_vez(self):
        c = self.codigo(*range(100))
        tokens = []
        for _ in range(MAX_PASSES + 1):
            c.asked.clear()   # (sin esperar entre un código y otro)
            tokens.append(c.check(c.new()[0])[0])
            self.reloj.t += 1
        self.assertFalse(c.valid(tokens[0]))   # el que vencía antes se olvida
        self.assertTrue(all(c.valid(t) for t in tokens[1:]))

    def test_la_cookie_en_la_cabecera(self):
        self.assertEqual(asistente.cookie_value("a=1; onetv_asistente=xyz-1_2; b=2"), "xyz-1_2")
        self.assertEqual(asistente.cookie_value("onetv_asistente_otra=no"), "")
        self.assertEqual(asistente.cookie_value(None), "")


class RokuQueRecuerda(Roku):
    """El Roku de mac/roku.py, sin red: anota lo que se le manda por el control remoto de red (ECP)."""

    def __init__(self, abierta):
        super().__init__("192.0.2.50")
        self.abierta, self.pedidos = abierta, []

    def _ecp(self, method, path, timeout=5):
        self.pedidos.append((method, path))
        if path == "/query/active-app":
            return f'<active-app><app id="{self.abierta}" type="appl">x</app></active-app>'
        return ""


class ALaTele(ConCarpetasFalsas):
    """El código llega a las TV conectadas y siempre al registro."""

    def setUp(self):
        super().setUp()
        self.app_ = self.app({"puerto": 8765, "carpetas": [str(self.biblio)], "bienvenida_hecha": True})
        self.registro = []
        w = self.app_.asistente
        w.log = self.registro.append
        w.codigo = CodigoTele(rng=azar(482913, 7))

    def test_sin_tele_queda_en_el_registro(self):
        self.assertEqual(self.app_.asistente.ask_code(), {"ok": True, "en_tele": False, "minutos": CODE_LIFE // 60})
        self.assertIn("482 913", self.registro[-1])

    def test_al_roku_con_one_tv_abierta_y_sin_ella(self):
        a = self.app_
        a.roku, a.roku_name, a.server_url = RokuQueRecuerda("dev"), "TV de la sala", "http://192.0.2.7:8765"
        self.assertTrue(a.asistente.ask_code()["en_tele"])
        self.assertEqual(a.roku.pedidos[-1], ("POST", "/input?cmd=codigo&codigo=482913"))
        self.assertIn("TV de la sala", self.registro[-1])
        a.roku = RokuQueRecuerda("12")   # viendo otra app: se abre One TV con el código
        a.asistente.codigo.asked.clear()
        a.asistente.ask_code()
        self.assertEqual(a.roku.pedidos[-1],
                         ("POST", "/launch/dev?cmd=codigo&codigo=000007&server=http%3A%2F%2F192.0.2.7%3A8765"))

    def test_el_roku_que_no_contesta_no_cuenta(self):
        class Apagado(RokuQueRecuerda):
            def _ecp(self, *a, **k):
                raise OSError("sin respuesta")
        a = self.app_
        a.roku, a.roku_name = Apagado("dev"), "TV de la sala"
        self.assertFalse(a.asistente.ask_code()["en_tele"])
        self.assertIn("482 913", self.registro[-1])

    def test_a_las_tv_con_android_conectadas(self):
        teles = self.app_.teles
        teles.esperar("androidtv-sala", "TV de la sala", espera=0)   # One TV abierta en esa TV
        self.assertTrue(self.app_.asistente.ask_code()["en_tele"])
        self.assertEqual(teles.esperar("androidtv-sala", espera=0), [{"cmd": "codigo", "codigo": "482913"}])
        self.assertIn("TV de la sala", self.registro[-1])


class PorLaRed(ConCarpetasFalsas):
    """Las rutas con un servidor de verdad (en 127.0.0.1), como si pidiera el teléfono (otro aparato)."""

    def servidor(self, cfg):
        cine_cfg = {"puerto": 8765, "carpetas": [str(self.biblio)], "roku_password": "kemu35", **cfg}
        app = self.app(cine_cfg)
        self.reloj = Reloj()
        app.asistente.codigo = CodigoTele(clock=self.reloj)
        app.asistente.log = lambda *_: None
        httpd = serve(app, 0, "127.0.0.1")
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        self.port = httpd.server_address[1]
        return app

    def pedir(self, metodo, ruta, cuerpo=None, host=None, cookie=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=20)
        headers = {"Content-Type": "application/json"} if cuerpo is not None else {}
        if host:
            headers["Host"] = host
        if cookie:
            headers["Cookie"] = cookie
        c.request(metodo, ruta, body=json.dumps(cuerpo) if cuerpo is not None else None, headers=headers)
        r = c.getresponse()
        datos = r.read()
        self.galleta = r.getheader("Set-Cookie")
        c.close()
        try:
            return r.status, json.loads(datos)
        except ValueError:
            return r.status, datos

    def entrar(self, app):
        """Pide un código y lo escribe bien. -> la cookie («onetv_asistente=…»)."""
        self.assertEqual(self.pedir("POST", "/api/asistente/codigo", {})[1]["ok"], True)
        codigo = app.asistente.codigo.code["valor"]
        self.assertEqual(self.pedir("POST", "/api/asistente/entrar", {"codigo": codigo})[1], {"ok": True})
        return self.galleta.split(";")[0]

    def test_sin_codigo_no_y_con_codigo_si(self):
        app = self.servidor({"bienvenida_hecha": True})
        with mock.patch.object(asistente, "is_local", return_value=False):
            st = self.pedir("GET", "/api/asistente/estado")[1]
            self.assertEqual(st, {"ok": True, "permitido": False, "local": False, "pendiente": False, "codigo": True})
            status, datos = self.pedir("GET", "/api/asistente/carpetas")
            self.assertEqual((status, datos["pedir_codigo"]), (403, True))
            # Un código equivocado no deja pasar ni da cookie.
            self.pedir("POST", "/api/asistente/codigo", {})
            datos = self.pedir("POST", "/api/asistente/entrar", {"codigo": "no-es"})[1]
            self.assertEqual(datos["ok"], False)
            self.assertIsNone(self.galleta)
            self.assertEqual(self.pedir("GET", "/api/asistente/carpetas", cookie="onetv_asistente=inventada")[0], 403)
            # El bueno sí: la cookie solo la lee el servidor, no se manda desde otros sitios y vale una hora.
            self.reloj.t += CODE_GAP
            cookie = self.entrar(app)
            self.assertIn("HttpOnly", self.galleta)
            self.assertIn("SameSite=Strict", self.galleta)
            self.assertIn(f"Max-Age={PASS_LIFE}", self.galleta)
            self.assertIn("Path=/", self.galleta)
            st = self.pedir("GET", "/api/asistente/estado", cookie=cookie)[1]
            self.assertEqual((st["permitido"], st["local"]), (True, False))
            self.assertEqual(st["roku"]["clave"], "kemu35")
            self.assertEqual(self.pedir("GET", "/api/asistente/carpetas", cookie=cookie)[0], 200)
            self.assertEqual(self.pedir("POST", "/api/asistente/carpetas", {"carpetas": [str(self.pelis)]},
                                        cookie=cookie)[1], {"ok": True, "carpetas": 1})
            # Lo que pasa en esta computadora y volver a abrirlo para todos: solo desde ella, con código o sin él.
            self.assertEqual(self.pedir("POST", "/api/asistente/permitir-red", {}, cookie=cookie)[0], 403)
            self.assertEqual(self.pedir("POST", "/api/asistente/fuera", {}, cookie=cookie)[0], 403)
            self.assertEqual(self.pedir("POST", "/api/bienvenida", {"hecha": False}, cookie=cookie)[0], 403)
            self.assertEqual(self.pedir("POST", "/api/bienvenida", {"hecha": True}, cookie=cookie)[1]["ok"], True)
            # Pasada la hora, otra vez el código.
            self.reloj.t += PASS_LIFE + 1
            self.assertEqual(self.pedir("GET", "/api/asistente/carpetas", cookie=cookie)[0], 403)
            self.assertEqual(self.pedir("GET", "/api/asistente/estado", cookie=cookie)[1]["permitido"], False)
        self.assertEqual(self.config()["carpetas"], [str(self.pelis)])

    def test_una_pagina_de_internet_no_pide_ni_usa_el_codigo(self):
        app = self.servidor({"bienvenida_hecha": True})
        with mock.patch.object(asistente, "is_local", return_value=False):
            cookie = self.entrar(app)
            malo = "evil.example.com"
            self.assertEqual(self.pedir("GET", "/api/asistente/estado", host=malo)[1]["codigo"], False)
            self.reloj.t += CODE_GAP
            self.assertEqual(self.pedir("POST", "/api/asistente/codigo", {}, host=malo)[0], 403)
            self.assertEqual(self.pedir("POST", "/api/asistente/entrar", {"codigo": "123456"}, host=malo)[0], 403)
            self.assertIsNone(app.asistente.codigo.code)   # no se pidió ninguno
            self.assertEqual(self.pedir("GET", "/api/asistente/carpetas", host=malo, cookie=cookie)[0], 403)
            self.assertEqual(self.pedir("GET", "/api/asistente/carpetas", host="nas.local:8765", cookie=cookie)[0], 200)

    def test_el_codigo_llega_a_la_tele_con_android(self):
        app = self.servidor({"bienvenida_hecha": True})
        app.teles.esperar("androidtv-sala", "TV de la sala", espera=0)
        with mock.patch.object(asistente, "is_local", return_value=False):
            self.assertEqual(self.pedir("POST", "/api/asistente/codigo", {})[1],
                             {"ok": True, "en_tele": True, "minutos": CODE_LIFE // 60})
            orden = app.teles.esperar("androidtv-sala", espera=0)
            self.assertEqual(orden, [{"cmd": "codigo", "codigo": app.asistente.codigo.code["valor"]}])
            datos = self.pedir("POST", "/api/asistente/codigo", {})[1]   # enseguida otro: hay que esperar
            self.assertEqual(datos["ok"], False)
            self.assertIn("Espera", datos["error"])

    def test_la_primera_configuracion_y_esta_computadora_siguen_igual(self):
        self.servidor({"bienvenida_hecha": False})
        with mock.patch.object(asistente, "is_local", return_value=False):   # otro aparato, sin código
            self.assertEqual(self.pedir("GET", "/api/asistente/estado")[1]["permitido"], True)
            self.assertEqual(self.pedir("GET", "/api/asistente/carpetas")[0], 200)
            self.assertEqual(self.pedir("POST", "/api/bienvenida", {"hecha": True})[1]["pendiente"], False)
            self.assertEqual(self.pedir("GET", "/api/asistente/carpetas")[0], 403)   # ya terminada: hace falta
        # Desde esta computadora, siempre y sin código.
        st = self.pedir("GET", "/api/asistente/estado")[1]
        self.assertEqual((st["permitido"], st["local"]), (True, True))
        self.assertNotIn("codigo", st)
        self.assertEqual(self.pedir("GET", "/api/asistente/carpetas")[0], 200)

    def config(self):
        import cine
        return json.loads(cine.CONFIG.read_text())


if __name__ == "__main__":
    unittest.main()
