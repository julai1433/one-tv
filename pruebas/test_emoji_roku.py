# Lo que la computadora le manda a la TV va sin emojis (las letras del Roku no los tienen: saldrían cuadritos).
# python3 -m unittest discover -s pruebas -p "test_emoji_roku.py"
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mac"))
from server import without_emoji


class SinEmoji(unittest.TestCase):
    def test_textos_sin_emoji_y_direcciones_intactas(self):
        data = {"playlists": [{"id": "PL💧x", "title": "💧PaYasabesQue💧", "thumb": "/yt/a💧/thumb.jpg"},
                              {"title": "Musicota ♠️", "channel_url": "https://x/💧"}],
                "title": "FKJ 🎹  live", "note": "Café – «hola» … • 1:02"}
        out = without_emoji(data)
        self.assertEqual(out["playlists"][0], {"id": "PL💧x", "title": "PaYasabesQue", "thumb": "/yt/a💧/thumb.jpg"})
        self.assertEqual(out["playlists"][1], {"title": "Musicota", "channel_url": "https://x/💧"})
        self.assertEqual(out["title"], "FKJ live")
        self.assertEqual(out["note"], "Café – «hola» … • 1:02")   # la puntuación que sí traen las letras se queda

    def test_si_no_queda_nada_se_deja_el_original(self):
        self.assertEqual(without_emoji({"title": "🐾"}), {"title": "🐾"})


if __name__ == "__main__":
    unittest.main()
