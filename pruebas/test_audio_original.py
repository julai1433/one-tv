# Pruebas sin red: YouTube con su audio original (los doblajes solo si se piden). Uso:
# python3 -m unittest pruebas/test_audio_original.py
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mac"))
from youtube import dubs_of, filter_master


def pista(grupo, lang, nombre, kind, default):
    uri = f"https://manifest.googlevideo.com/api/manifest/hls_playlist/id/x/itag/{grupo}/sgoap/itag%3D139%3Bxtags%3Dacont%3D{kind}:lang%3D{lang}/file/index.m3u8"
    return (f'#EXT-X-MEDIA:URI="{uri}",TYPE=AUDIO,GROUP-ID="{grupo}",LANGUAGE="{lang}",NAME="{nombre}",'
            f'DEFAULT={"YES" if default else "NO"},AUTOSELECT=YES')


MAESTRA = "\n".join([
    "#EXTM3U",
    pista(233, "es", "Español - dubbed", "dubbed", False),
    pista(233, "fr", "Français - dubbed", "dubbed-auto", False),
    pista(233, "en-US", "American English - original", "original", True),
    pista(234, "es", "Español - dubbed", "dubbed", False),
    pista(234, "en-US", "American English - original", "original", True),
    '#EXT-X-STREAM-INF:BANDWIDTH=1,CODECS="avc1.4D401E,mp4a.40.2",RESOLUTION=640x360,AUDIO="234"',
    "https://manifest.googlevideo.com/v/360.m3u8",
    '#EXT-X-STREAM-INF:BANDWIDTH=2,CODECS="vp09.00.40.08",RESOLUTION=1920x1080,AUDIO="234"',
    "https://manifest.googlevideo.com/v/vp9.m3u8",
])


def audios(text):
    return [l for l in text.splitlines() if "TYPE=AUDIO" in l]


class AudioOriginal(unittest.TestCase):
    def test_por_omision_solo_el_original(self):
        a = audios(filter_master(MAESTRA))
        self.assertEqual(len(a), 2)   # uno por grupo
        self.assertTrue(all("original" in l and "DEFAULT=YES" in l for l in a))
        self.assertNotIn("vp09", filter_master(MAESTRA))

    def test_doblaje_pedido(self):
        a = audios(filter_master(MAESTRA, "es"))
        self.assertEqual(len(a), 2)
        self.assertTrue(all('LANGUAGE="es"' in l and "DEFAULT=YES" in l for l in a))

    def test_doblaje_que_no_existe_deja_el_original(self):
        a = audios(filter_master(MAESTRA, "de"))
        self.assertTrue(all("original" in l for l in a))
        # el grupo 234 no tiene francés: ahí queda el original
        a = audios(filter_master(MAESTRA, "fr"))
        self.assertIn("Français", a[0])
        self.assertIn("original", a[1])

    def test_sin_etiquetas_queda_el_default(self):
        plano = "\n".join(['#EXTM3U',
                           '#EXT-X-MEDIA:URI="a.m3u8",TYPE=AUDIO,GROUP-ID="g",LANGUAGE="es",NAME="Uno",DEFAULT=NO,AUTOSELECT=YES',
                           '#EXT-X-MEDIA:URI="b.m3u8",TYPE=AUDIO,GROUP-ID="g",LANGUAGE="en",NAME="Dos",DEFAULT=YES,AUTOSELECT=YES'])
        a = audios(filter_master(plano))
        self.assertEqual(len(a), 1)
        self.assertIn("Dos", a[0])

    def test_doblajes_que_se_ofrecen(self):
        data = {"formats": [
            {"vcodec": "none", "language": "es", "format_note": "Español - dubbed"},
            {"vcodec": "none", "language": "es", "format_note": "Español, medium"},
            {"vcodec": "none", "language": "fr", "format_note": "Français - dubbed"},
            {"vcodec": "none", "language": "en-US", "format_note": "American English - original (original)"},
            {"vcodec": "avc1", "language": "en-US", "format_note": "1080p"}]}
        self.assertEqual(dubs_of(data), [{"lang": "es", "name": "Español"}])
        self.assertEqual(dubs_of({"formats": []}), [])


if __name__ == "__main__":
    unittest.main()
