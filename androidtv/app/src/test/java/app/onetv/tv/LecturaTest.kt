package app.onetv.tv

import app.onetv.tv.data.chooseAudio
import app.onetv.tv.data.chooseSub
import app.onetv.tv.data.parseLibrary
import app.onetv.tv.data.parseMusic
import app.onetv.tv.data.parseMusicPage
import app.onetv.tv.data.parseMusicViejo
import app.onetv.tv.data.Totales
import app.onetv.tv.data.parseYtHome
import app.onetv.tv.data.spokenText
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** Lectura de lo que manda el servidor (/api/library, /api/yt/home, /api/music), como lo usa la app del Roku. */
class LecturaTest {

    // Un pedazo de /api/library de la biblioteca de ejemplo (pruebas/datos_demo.py).
    private val biblioteca = """
    {
      "rows": [], "live": [], "youtube": [],
      "movies": [{"title": "Recién agregadas", "items": [{"id": "m2", "label": "The Kid (1921)"}, {"id": "m1", "label": "Metropolis (1927)"}]},
                 {"title": "Películas", "items": [{"id": "m1"}, {"id": "m2"}]}],
      "series": [{"key": "theciscokid", "title": "The Cisco Kid", "poster": "e1", "episodes": 2, "dub": false,
                  "art": "/art/serie-theciscokid.jpg?v=1",
                  "seasons": [{"season": 1, "title": "Temporada 1", "items": [{"id": "e1", "label": "E1"}, {"id": "e2", "label": "E2"}]}]}],
      "items": {
        "m1": {"id": "m1", "title": "Metropolis (1927)", "full_title": "Metropolis (1927)", "kind": "movie", "show": "", "season": 0,
               "ep": "", "ep_title": "", "next": "", "duration": 600.0, "poster": "/poster/m1.jpg", "mode": "direct",
               "direct": {"url": "/media/m1.mp4", "format": "mp4"}, "convert_reason": "", "art": "/art/m1.jpg?v=1",
               "audio": [{"label": "Inglés · AAC estéreo", "lang": "eng", "hls": "/hls/m1/a1/index.m3u8", "name": "Inglés (original)", "tech": "AAC estéreo", "original": true},
                         {"label": "Español · AAC estéreo", "lang": "spa", "hls": "/hls/m1/a2/index.m3u8", "name": "Español", "tech": "AAC estéreo", "original": false}],
               "audio_default": 0, "dub": true,
               "subs": [{"label": "Español", "lang": "spa", "url": "/subs/m1/x1.srt", "forced": false, "name": "Español"},
                        {"label": "Inglés", "lang": "eng", "url": "/subs/m1/x0.srt", "forced": false, "name": "Inglés"}]},
        "m2": {"id": "m2", "title": "The Kid (1921)", "full_title": "The Kid (1921)", "kind": "movie", "duration": 600.0, "mode": "copy",
               "direct": null, "convert_reason": "audio AC3", "audio_default": 0, "dub": true, "subs": [],
               "audio": [{"label": "Inglés · AC3", "lang": "eng", "hls": "/hls/m2/a1/index.m3u8", "name": "Inglés (original)", "original": true}]},
        "e1": {"id": "e1", "title": "T1 E1 · Boomerang", "full_title": "The Cisco Kid · T1 E1 · Boomerang", "kind": "episode",
               "show": "The Cisco Kid", "season": 1, "ep": "E1", "ep_title": "Boomerang", "next": "e2", "duration": 600.0, "dub": false,
               "audio": [], "subs": []},
        "e2": {"id": "e2", "title": "T1 E2", "full_title": "The Cisco Kid · T1 E2", "kind": "episode", "duration": 600.0}
      },
      "watching": [{"id": "m1", "p": 196}],
      "seen": ["e1"],
      "keep_watching": [{"id": "m1", "p": 196}],
      "continue": [{"kind": "item", "id": "m1", "p": 196, "t": 1791364769.19},
                   {"kind": "yt", "id": "dQw4w9WgXcQ", "title": "Un video", "channel": "Un canal", "p": 30, "duration": 212}],
      "queue": [{"kind": "yt", "id": "abcdefghijk", "title": "En la fila", "thumb": "/yt/abcdefghijk/thumb.jpg", "duration": 100}],
      "history": [{"kind": "item", "id": "m1", "title": "Metropolis (1927)", "thumb": "/poster/m1.jpg", "when": "hoy 21:04", "p": 196, "duration": 600}],
      "prefs": {"audioLang": "original", "subLang": "off"}
    }
    """.trimIndent()

    @Test
    fun lee_peliculas_episodios_y_sus_pistas() {
        val l = parseLibrary(JSONObject(biblioteca))
        assertEquals(4, l.items.size)
        val m1 = l.items.getValue("m1")
        assertEquals("Metropolis (1927)", m1.fullTitle)
        assertEquals("/media/m1.mp4", m1.direct?.url)
        assertEquals(2, m1.audio.size)
        assertEquals(true, m1.audio[0].original)
        assertEquals("/hls/m1/a2/index.m3u8", m1.audio[1].hls)
        assertEquals("/subs/m1/x1.srt", m1.subs[0].url)
        assertTrue(m1.dub)
        assertNull(l.items.getValue("m2").direct)   // se convierte: llega por HLS
        val e1 = l.items.getValue("e1")
        assertEquals("e2", e1.next)
        assertEquals("Boomerang", e1.epTitle)
    }

    @Test
    fun lee_series_recientes_y_seguir_viendo() {
        val l = parseLibrary(JSONObject(biblioteca))
        assertEquals(listOf("m2", "m1"), l.recent)
        assertEquals(listOf("e1", "e2"), l.series[0].seasons[0].items)
        assertEquals(196.0, l.progress.getValue("m1"), 0.0)
        assertEquals(listOf("item", "yt"), l.cont.map { it.kind })
        assertEquals("Un canal", l.cont[1].channel)
        assertEquals("yt", l.queue[0].kind)
        assertEquals("hoy 21:04", l.history[0].whenText)
        assertTrue("e1" in l.seen)
        assertEquals("off", l.prefs["subLang"])
    }

    @Test
    fun un_dato_que_falta_no_rompe_la_lectura() {
        val l = parseLibrary(JSONObject("""{"items": {"x": {"id": "x", "title": "Algo"}}}"""))
        assertEquals("Algo", l.items.getValue("x").fullTitle)
        assertTrue(l.series.isEmpty() && l.cont.isEmpty() && l.recent.isEmpty())
    }

    @Test
    fun elige_el_idioma_como_el_roku() {
        val l = parseLibrary(JSONObject(biblioteca))
        val m1 = l.items.getValue("m1")
        assertEquals(0, chooseAudio(m1, mapOf("audioLang" to "original")))
        assertEquals(1, chooseAudio(m1, mapOf("audioLang" to "spa")))
        assertEquals(0, chooseAudio(m1, mapOf("audioLang" to "fra")))   // no hay: la original
        assertEquals(-1, chooseSub(m1, mapOf("subLang" to "off")))
        assertEquals(1, chooseSub(m1, mapOf("subLang" to "eng")))
        assertEquals("Se oye en inglés y español   ·   Subtítulos en español e inglés", spokenText(m1))
    }

    @Test
    fun lee_la_portada_de_youtube() {
        val h = parseYtHome(JSONObject("""{"continue": [{"id": "v1", "title": "A medias", "p": 40, "duration": 100}],
            "new": [], "because": [{"seed": {"title": "Un video visto"}, "videos": [{"id": "v2", "title": "Parecido"}]}],
            "recent": [], "playlists": [{"id": "PL1", "title": "Mi lista", "count": 3}], "favorites": []}"""))
        assertEquals("yt", h.cont[0].kind)
        assertEquals("Un video visto", h.becauseSeed)
        assertEquals("v2", h.because[0].id)
        assertEquals(3, h.playlists[0].count)
    }

    @Test
    fun lee_la_musica() {
        // /api/music/home: lo de la sección, sin las canciones de cada álbum (llegan por partes).
        val m = parseMusic(JSONObject("""{"ok": true, "counts": {"artists": 3851, "albums": 7153, "tracks": 70000, "playlists": 1},
            "albums": [{"id": "a1", "title": "Ondas", "artist": "Orquesta", "year": 2019, "count": 12, "art": "/music/art/a1.jpg", "added": 5}],
            "artists": [{"id": "r1", "name": "Orquesta", "count": 2, "art": "/music/art/a1.jpg"}],
            "playlists": [{"id": "p1", "title": "Para correr", "count": 60, "art": "/music/art/a1.jpg"}],
            "recent": [{"id": "t1", "title": "Seno", "artist": "Orquesta", "album": "Ondas", "duration": 20.0,
            "url": "/music/t1/audio", "art": "/music/art/a1.jpg"}]}"""))
        assertTrue(m.ready)
        assertEquals("/music/t1/audio", m.recent[0].url)
        assertEquals(12, m.albums[0].count)
        assertEquals(2, m.artists[0].count)
        assertEquals(1 to 3851, m.cuantos("artists"))      // quedan muchos por pedir
        assertEquals(1 to 1, m.cuantos("playlists"))
        assertFalse(parseMusic(JSONObject("""{"ok": true, "counts": {"albums": 0}}""")).ready)
        assertTrue(parseMusic(JSONObject("""{"ok": true, "reading": true}""")).reading)
    }

    @Test
    fun lee_la_musica_de_un_servidor_de_antes() {
        // Un servidor que todavía manda todo junto (/api/music): la sección y cada página, ya completas.
        val (m, pages) = parseMusicViejo(JSONObject("""{"ok": true, "albums": [{"id": "a1", "title": "Ondas", "artist": "Orquesta",
            "year": 2019, "tracks": ["t1", "t2"], "art": "/music/art/a1.jpg", "added": 5}],
            "artists": [{"id": "r1", "name": "Orquesta", "albums": ["a1"], "art": "/music/art/a1.jpg"}],
            "playlists": [{"id": "p1", "title": "Favoritas", "tracks": ["t2"], "art": "/music/art/a1.jpg"}],
            "tracks": {"t1": {"id": "t1", "title": "Seno", "artist": "Orquesta", "album": "Ondas", "duration": 20.0,
            "url": "/music/t1/audio", "art": "/music/art/a1.jpg"}, "t2": {"id": "t2", "title": "Coseno", "artist": "Orquesta",
            "album": "Ondas", "duration": 30.0, "url": "/music/t2/audio", "art": "/music/art/a1.jpg"}}}"""))
        assertTrue(m.ready)
        assertEquals(Totales(1, 1, 2, 1), m.counts)
        assertEquals(listOf("t1", "t2"), m.recent.map { it.id })
        assertEquals(2, m.albums[0].count)
        assertEquals(listOf("t1", "t2"), pages.getValue("artist:r1").songs.map { it.id })
        assertTrue(pages.getValue("list:p1").completa)
    }

    @Test
    fun lee_la_pagina_de_un_album_por_tandas() {
        val p = parseMusicPage(JSONObject("""{"ok": true, "kind": "artist", "id": "r1", "title": "Varios", "total": 2945,
            "offset": 0, "tracks": [{"id": "t1", "title": "Seno", "artist": "A", "album": "B", "duration": 3,
            "url": "/music/t1/audio", "art": "/music/art/a1.jpg"}, {"title": "sin id"}]}"""), "artist", "r1")
        assertEquals(listOf("t1"), p.songs.map { it.id })    // sin id no se puede escuchar
        assertEquals(2945, p.total)
        assertFalse(p.completa)
        val gone = parseMusicPage(JSONObject("""{"ok": false, "error": "Eso ya no está en tu música."}"""), "album", "x")
        assertEquals("gone", gone.error)
    }
}
