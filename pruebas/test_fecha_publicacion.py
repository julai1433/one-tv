# Pruebas sin red de la fecha de publicación de los videos de YouTube: el caché (exacta vs. aproximada), de dónde se
# aprende (RSS, página del canal, relacionados, watch_videos, yt-dlp) y que llegue a las listas de la app.
# Uso: python3 -m unittest discover -s pruebas -p "test_fecha_publicacion.py"
import json, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mac"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from youtube import fetch_durations, page_dates, parse_related
from ytaccount import parse_channel_page, parse_feed
from ytdurations import DurationFiller, Durations, date_of, parse_ago
from test_duraciones import Base, Falso, pagina, panel, vid
from test_ytaccount import MKBHD

AHORA = 1_900_000_000
DIA = 86400


def lockup(v, meta2, dur="10:00"):
    """Tarjeta actual de YouTube: 1.ª fila el canal, 2.ª «vistas • hace N …»."""
    return {"lockupViewModel": {
        "contentId": v, "contentType": "LOCKUP_CONTENT_TYPE_VIDEO",
        "contentImage": {"thumbnailViewModel": {"overlays": [{"thumbnailOverlayBadgeViewModel": {
            "thumbnailBadges": [{"thumbnailBadgeViewModel": {"text": dur}}]}}]}},
        "metadata": {"lockupMetadataViewModel": {"title": {"content": "T " + v}, "metadata": {
            "contentMetadataViewModel": {"metadataRows": [
                {"metadataParts": [{"text": {"content": "Canal X"}}]},
                {"metadataParts": [{"text": {"content": "1,2 M de vistas"}}, {"text": {"content": meta2}}]}]}}}}}}


class Cache(Base):
    def test_exacta_no_se_pisa_con_aproximada_y_aproximada_solo_por_mas_precisa(self):
        d = self.cache()
        a = vid(1)
        d.learn_dates({a: (AHORA - 3 * 365 * DIA, 365 * DIA)})                # «hace 3 años»
        self.assertEqual(d.date(a), (AHORA - 3 * 365 * DIA, True))
        d.learn_dates({a: (AHORA - 400 * DIA, 365 * DIA)})                    # igual de gruesa: se queda la primera
        self.assertEqual(d.date(a)[0], AHORA - 3 * 365 * DIA)
        d.learn_dates({a: (AHORA - 5 * 30 * DIA, 30 * DIA)})                  # «hace 5 meses»: más fina
        self.assertEqual(d.date(a), (AHORA - 150 * DIA, True))
        d.learn_dates([{"id": a, "published": AHORA - 160 * DIA}])            # exacta
        self.assertEqual(d.date(a), (AHORA - 160 * DIA, False))
        d.learn_dates({a: (AHORA - 100 * DIA, DIA)})                          # aproximada: no la pisa
        self.assertEqual(d.date(a), (AHORA - 160 * DIA, False))
        d.learn_dates([{"id": a, "published": AHORA - 161 * DIA}])            # otra exacta sí
        self.assertEqual(d.date(a)[0], AHORA - 161 * DIA)

    def test_sobrevive_al_reinicio_y_lee_el_formato_viejo(self):
        d = self.cache()
        d.learn_dates([{"id": vid(2), "published": AHORA, "published_approx": True, "published_unit": 30 * DIA}])
        d.learn([{"id": vid(3), "duration": 90}])
        d2 = self.cache()
        self.assertEqual(d2.date(vid(2)), (AHORA, True))
        self.assertEqual(d2.get(vid(3)), 90)
        viejo = self.dir / "viejo.json"
        viejo.write_text(json.dumps({"durations": {vid(4): 60}, "unknown": {}, "filler": {}}))
        d3 = Durations(viejo, save_delay=0)
        self.assertEqual((d3.get(vid(4)), d3.date(vid(4))), (60, None))
        viejo.write_text(json.dumps({"durations": {}, "published": {vid(5): "basura", "x": [1, 2]}}))
        self.assertEqual(Durations(viejo).dates, {})

    def test_apply_pone_published_y_published_approx(self):
        d = self.cache()
        d.learn_dates({vid(1): (AHORA - DIA, 0), vid(2): (AHORA - 900 * DIA, 365 * DIA)})
        vs = [{"id": vid(1), "duration": 5}, {"id": vid(2), "duration": 5}, {"id": vid(3), "duration": 5}]
        d.apply(vs)
        self.assertEqual((vs[0]["published"], vs[0]["published_approx"]), (AHORA - DIA, False))
        self.assertEqual((vs[1]["published"], vs[1]["published_approx"]), (AHORA - 900 * DIA, True))
        self.assertNotIn("published", vs[2])
        self.assertNotIn("published_unit", vs[1])

    def test_apply_aprende_la_fecha_que_traen_los_videos(self):
        d = self.cache()
        d.apply([{"id": vid(1), "duration": 5, "published": AHORA, "published_approx": True, "published_unit": 3600}])
        self.assertEqual(d.date(vid(1)), (AHORA, True))
        d.apply([{"id": vid(2), "duration": 5, "published": 12}])   # basura (antes del 2000)
        self.assertIsNone(d.date(vid(2)))

    def test_parse_ago_y_fecha_de_yt_dlp(self):
        self.assertEqual(parse_ago("1,2 M de vistas • hace 3 años", AHORA), (AHORA - 3 * 365 * DIA, 365 * DIA))
        self.assertEqual(parse_ago("5 hours ago", AHORA), (AHORA - 5 * 3600, 3600))
        self.assertIsNone(parse_ago("12 mil vistas", AHORA))
        self.assertEqual(date_of({"timestamp": 1694500000}), 1694500000)
        self.assertEqual(date_of({"upload_date": "20230912"}), 1694520000)
        self.assertEqual(date_of({"upload_date": "basura"}), 0)


class Fuentes(unittest.TestCase):
    def test_rss_trae_la_fecha_exacta(self):
        xml = (b'<feed xmlns="http://www.w3.org/2005/Atom" xmlns:yt="http://www.youtube.com/xml/schemas/2015">'
               b'<title>C</title><entry><yt:videoId>hXI8RQYC36Q</yt:videoId><title>T</title>'
               b'<published>2023-09-12T10:00:00+00:00</published></entry></feed>')
        self.assertEqual(parse_feed(xml)[0]["published"], 1694512800)

    def test_relacionados_traen_la_fecha_aproximada(self):
        data = {"contents": {"twoColumnWatchNextResults": {"secondaryResults": {"results": [
            lockup("hXI8RQYC36Q", "hace 3 años"), lockup("GnmatfBhzyo", "hace 2 semanas"),
            lockup("CJRLSuK8aoI", "En vivo")]}}}}
        rel = {v["id"]: v for v in parse_related(pagina(data))}
        self.assertTrue(rel["hXI8RQYC36Q"]["published_approx"])
        self.assertEqual(rel["hXI8RQYC36Q"]["published_unit"], 365 * DIA)
        self.assertEqual(rel["GnmatfBhzyo"]["published_unit"], 7 * DIA)
        self.assertNotIn("published", rel["CJRLSuK8aoI"])

    def test_page_dates_de_lockups_y_del_formato_anterior(self):
        data = {"contents": {"twoColumnWatchNextResults": {"secondaryResults": {"results": [
            lockup("hXI8RQYC36Q", "hace 1 mes"),
            {"compactVideoRenderer": {"videoId": "JGwWNGJdvx8", "publishedTimeText": {"simpleText": "hace 4 días"}}},
            {"compactVideoRenderer": {"videoId": "s5IIWKZr_2w"}}]}}}}
        got = page_dates(pagina(data))
        self.assertEqual(set(got), {"hXI8RQYC36Q", "JGwWNGJdvx8"})
        self.assertEqual(got["JGwWNGJdvx8"][1], DIA)
        self.assertEqual(page_dates("<html>nada</html>"), {})

    def test_pagina_del_canal_marca_la_fecha_como_aproximada(self):
        item = {"richItemRenderer": {"content": {"lockupViewModel": {
            "contentId": "rayrrXot17M", "contentType": "LOCKUP_CONTENT_TYPE_VIDEO", "contentImage": {},
            "metadata": {"lockupMetadataViewModel": {"title": {"content": "T"}, "metadata": {"contentMetadataViewModel": {
                "metadataRows": [{"metadataParts": [{"text": {"content": "?"}, "accessibilityLabel": "hace 2 semanas"}]}]}}}}}}}}
        data = {"metadata": {"channelMetadataRenderer": {"title": "MKBHD"}}, "contents": {"items": [item]}}
        v = parse_channel_page(pagina(data), MKBHD, now=AHORA)[0]
        self.assertEqual((v["published"], v["published_approx"], v["published_unit"]), (AHORA - 14 * DIA, True, 7 * DIA))

    def test_watch_videos_y_el_rellenador_aprende_las_fechas_que_trae(self):
        with tempfile.TemporaryDirectory() as t:
            d = Durations(Path(t) / "d.json", save_delay=0)
            html = panel([("GnmatfBhzyo", "8:04")]).encode()
            f = fetch_durations(["GnmatfBhzyo"], lambda url: (html, "https://www.youtube.com/watch?v=x"))
            self.assertEqual(f.dates, {})   # el panel de la lista no trae fechas: no se inventa nada
            f.dates = {"GnmatfBhzyo": (AHORA - 3 * DIA, DIA)}
            filler = DurationFiller(d, lambda ids: f, log=lambda m: None, background=False, clock=lambda: 1_000_000.0)
            filler.want(["GnmatfBhzyo"])
            self.assertEqual(filler.step(), "ok")
            self.assertEqual(d.date("GnmatfBhzyo"), (AHORA - 3 * DIA, True))


class EnLaApp(Base):
    def setUp(self):
        super().setUp()
        self.app = Falso(self.dir)

    def test_la_fecha_llega_a_nuevos_seguir_viendo_e_historial(self):
        acc = self.app.account
        acc.feeds = {MKBHD: {"videos": [
            {"id": vid(1), "title": "A", "published": AHORA - DIA, "duration": 60},
            {"id": vid(2), "title": "B", "published": AHORA - 9 * DIA, "published_approx": True, "published_unit": DIA,
             "duration": 60}], "t": 1, "status": "ok"}}
        acc.pinned = {MKBHD: {"title": "MKBHD", "at": 1}}
        nuevos = {v["id"]: v for v in self.app.yt_home()["new"]}
        self.assertEqual((nuevos[vid(1)]["published"], nuevos[vid(1)]["published_approx"]), (AHORA - DIA, False))
        self.assertEqual((nuevos[vid(2)]["published"], nuevos[vid(2)]["published_approx"]), (AHORA - 9 * DIA, True))
        self.app.store.progress["yt:" + vid(1)] = {"p": 30, "t": 100}
        self.assertEqual(self.app.history()[0]["published"], AHORA - DIA)
        seguir = [e for e in self.app.continue_watching({}) if e["kind"] == "yt"]
        self.assertEqual((seguir[0]["published"], seguir[0]["published_approx"]), (AHORA - DIA, False))

    def test_sin_fecha_no_se_inventa(self):
        self.app.store.progress["yt:" + vid(9)] = {"p": 30, "t": 100}
        e = [e for e in self.app.continue_watching({}) if e["kind"] == "yt"][0]
        self.assertNotIn("published", e)


if __name__ == "__main__":
    unittest.main()
