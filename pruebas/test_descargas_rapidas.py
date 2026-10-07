# Pruebas sin red: lo que termina de bajarse en Transmission entra a la biblioteca en menos de un minuto.
# Uso: python3 -m unittest pruebas/test_descargas_rapidas.py
import os, plistlib, sys, tempfile, time, unittest
from unittest import mock
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mac"))
import organizer
from organizer import Organizer


def video(path, age):
    """Un video «grande» (archivo disperso: no ocupa disco) que cambió hace `age` segundos."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.truncate(organizer.MIN_SIZE + 1)
    t = time.time() - age
    os.utime(path, (t, t))
    return path


class DescargasRapidas(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        d = Path(self._t.name)
        self.lib, self.down = d / "Biblioteca", d / "Torrents"
        self.lib.mkdir()
        self.down.mkdir()
        self.prefs = d / "org.m0k.transmission.plist"
        self.org = Organizer([str(self.lib)], [str(self.down)], d / "organizador.json", log=lambda m: None)
        p = mock.patch.object(organizer, "TRANSMISSION_PREFS", self.prefs)
        p.start()
        self.addCleanup(p.stop)

    def tearDown(self):
        self._t.cleanup()

    def found(self):
        return {(p.name, how) for p, how in self.org.candidates()}

    def test_terminado_en_transmission_entra_a_los_15_s(self):
        video(self.down / "Serie.S01E01.mkv", 20)
        video(self.down / "Serie.S01E02.mkv", 5)               # recién terminado: espera unos segundos más
        video(self.down / "Serie.S01E03.mkv.part", 300)        # todavía bajándose
        self.assertEqual(self.found(), {("Serie.S01E01.mkv", "link")})
        self.assertTrue(self.org.pending_downloads())

    def test_copiado_a_mano_a_la_biblioteca_sigue_esperando_2_min(self):
        video(self.lib / "Pelicula.2001.mkv", 20)
        self.assertEqual(self.found(), set())
        video(self.lib / "Otra.2002.mkv", 200)
        self.assertEqual(self.found(), {("Otra.2002.mkv", "move")})
        self.assertFalse(self.org.pending_downloads())

    def test_si_transmission_no_marca_lo_incompleto_espera_2_min(self):
        self.prefs.write_bytes(plistlib.dumps({"RenamePartialFiles": False}))
        video(self.down / "Serie.S01E01.mkv", 20)
        self.assertEqual(self.found(), set())
        self.prefs.write_bytes(plistlib.dumps({"RenamePartialFiles": True}))
        self.assertEqual(len(self.found()), 1)

    def test_preferencias_que_no_existen_o_rotas(self):
        self.assertTrue(organizer.transmission_marks_partial(self.prefs))   # Transmission de fábrica
        self.prefs.write_bytes(b"no es un plist")
        self.assertTrue(organizer.transmission_marks_partial(self.prefs))

    def test_lo_ya_ordenado_no_cuenta(self):
        p = video(self.down / "Serie.S01E01.mkv", 20)
        self.org.state["done"][str(p)] = "ya estaba"
        self.assertFalse(self.org.pending_downloads())


if __name__ == "__main__":
    unittest.main()
