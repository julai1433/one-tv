# El servidor dentro del contenedor de Docker (Dockerfile): con ONE_TV_CONTENEDOR=1 todo va en la carpeta de datos
# (/datos), config.json se lee de ahí y las variables de entorno (ROKU_IP, ROKU_PASSWORD, PUERTO, CODIFICADOR) ganan sobre él.
# Cada caso corre en un Python aparte porque hostos decide todo al importarse. Sin red ni Docker.
# python3 -m unittest discover -s pruebas -p "test_docker.py"
import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path

MAC = str(Path(__file__).resolve().parent.parent / "mac")
CODIGO = """
import json, sys
sys.path.insert(0, %r)
import cine, hostos
cfg = cine.load_config()
print(json.dumps({"cont": hostos.CONTAINER, "home": str(hostos.SERVICE_HOME), "cache": str(hostos.CACHE),
                  "log": str(hostos.LOG), "config": str(cine.CONFIG), "guia": hostos.guide(), "cfg": cfg}))
""" % MAC


def correr(datos, **env):
    base = {k: v for k, v in os.environ.items() if not k.startswith(("ONE_TV", "ROKU", "PUERTO", "CODIFICADOR"))}
    base.update(env)
    r = subprocess.run([sys.executable, "-c", CODIGO], env=base, capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


class Contenedor(unittest.TestCase):
    def test_sin_contenedor_no_cambia_nada(self):
        d = correr(None)
        self.assertFalse(d["cont"])
        self.assertTrue(d["config"].endswith("config.json"))
        self.assertNotIn("/datos", d["home"])

    def test_carpetas_en_los_datos(self):
        with tempfile.TemporaryDirectory() as t:
            d = correr(t, ONE_TV_CONTENEDOR="1", ONE_TV_DATOS=t)
            self.assertTrue(d["cont"])
            T = Path(t)   # con Path: en Windows las rutas van con «\» (las pruebas corren también allá)
            self.assertEqual((Path(d["home"]), Path(d["cache"]), Path(d["config"])), (T, T / "cache", T / "config.json"))
            self.assertEqual(Path(d["log"]), T / "registro.log")
            self.assertEqual(d["guia"], "docs/INSTALAR-DOCKER.md")
            self.assertEqual(d["cfg"]["carpetas"], ["/biblioteca"])
            self.assertEqual(d["cfg"]["musica"], ["/musica"])
            self.assertEqual(d["cfg"]["descargas"], [])
            self.assertEqual(Path(d["cfg"]["sin_conexion"]), T / "sin_conexion")

    def test_variables_ganan_sobre_config_json(self):
        with tempfile.TemporaryDirectory() as t:
            Path(t, "config.json").write_text(json.dumps(
                {"roku_ip": "10.0.0.1", "roku_password": "vieja", "puerto": 9000, "carpetas": ["/otra"]}))
            d = correr(t, ONE_TV_CONTENEDOR="1", ONE_TV_DATOS=t, ROKU_IP="192.168.1.50", ROKU_PASSWORD="nueva", PUERTO="8700")
            self.assertEqual((d["cfg"]["roku_ip"], d["cfg"]["roku_password"], d["cfg"]["puerto"]), ("192.168.1.50", "nueva", 8700))
            self.assertEqual(d["cfg"]["carpetas"], ["/otra"])   # lo demás de config.json se respeta
            d = correr(t, ONE_TV_CONTENEDOR="1", ONE_TV_DATOS=t)   # sin variables, manda config.json
            self.assertEqual((d["cfg"]["roku_ip"], d["cfg"]["puerto"]), ("10.0.0.1", 9000))

    def test_puerto_que_no_es_numero(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(subprocess.CalledProcessError):
                correr(t, ONE_TV_CONTENEDOR="1", ONE_TV_DATOS=t, PUERTO="abc")


if __name__ == "__main__":
    unittest.main()
