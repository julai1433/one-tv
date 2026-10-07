package app.onetv.tv

import app.onetv.tv.data.Marca
import app.onetv.tv.data.Silenciado
import app.onetv.tv.data.dateText
import app.onetv.tv.data.parseDubs
import app.onetv.tv.data.parseHidden
import app.onetv.tv.data.parseLibrary
import app.onetv.tv.data.parseMarks
import app.onetv.tv.data.parseVideos
import app.onetv.tv.data.plainText
import app.onetv.tv.data.publishedText
import app.onetv.tv.data.viewersText
import app.onetv.tv.ui.imagenPara
import app.onetv.tv.ui.textoAyuda
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.IOException
import java.util.TimeZone

/** Lo que la app de Android TV hace igual que la del Roku: buscar, YouTube, Saltar intro, el final que no llega, los
 *  ajustes generales y sus textos. */
class FuncionesRokuTest {

    // ---------- Saltar intro (Player.brs, onPosition) ----------

    @Test
    fun saltar_intro_se_ofrece_8_segundos_al_entrar_y_no_se_salta_solo() {
        val s = SaltarIntro(listOf(Marca(10.0, 60.0, "Saltar intro")))
        assertFalse(s.en(5.0, true))
        assertEquals(-1, s.actual)
        assertTrue(s.en(10.5, true))          // entra al tramo: se ofrece
        assertEquals(0, s.actual)
        s.en(14.5, true)
        assertEquals(0.5, s.resto, 0.01)      // la línea va a la mitad
        assertTrue(s.en(18.6, true))          // pasaron 8 s: se quita
        assertEquals(-1, s.actual)
        assertFalse(s.en(30.0, true))         // dentro del tramo ya no se vuelve a ofrecer
        s.en(70.0, true)                      // sale del tramo…
        assertTrue(s.en(12.0, true))          // …y al volver a entrar se ofrece otra vez
    }

    @Test
    fun saltar_intro_en_pausa_no_se_ofrece_y_ok_lleva_al_final_del_tramo() {
        val s = SaltarIntro(listOf(Marca(10.0, 60.0, "Saltar intro")))
        assertFalse(s.en(11.0, false))        // en pausa no aparece
        s.en(11.5, true)
        assertEquals(60.0, s.usar()!!, 0.0)
        assertEquals(-1, s.actual)
        assertNull(s.usar())
        assertFalse(s.en(12.0, true))         // ya se usó: no vuelve hasta salir del tramo
    }

    @Test
    fun saltar_intro_corta_dura_hasta_su_final() {
        val s = SaltarIntro(listOf(Marca(0.0, 5.0, "Saltar intro")))
        s.en(1.0, true)
        assertTrue(s.en(5.0, true))           // terminó el tramo antes de los 8 s
        assertEquals(-1, s.actual)
    }

    // ---------- el final que no llega (Player.brs, onEndWatch) ----------

    @Test
    fun fin_sin_aviso_se_da_por_terminado_si_no_avanza_cerca_del_final() {
        val f = FinSinAviso()
        assertFalse(f.muestra(100.0, 200.0, false))   // lejos del final
        assertFalse(f.muestra(199.4, 200.0, false))   // primera muestra cerca del final
        assertTrue(f.muestra(199.42, 200.0, false))   // 2 s después no se movió
        assertFalse(f.muestra(199.0, 200.0, false))
        assertFalse(f.muestra(199.5, 200.0, false))   // sí avanza: sigue
        assertFalse(f.muestra(199.5, 200.0, true))    // en pausa no cuenta
        assertFalse(f.muestra(199.5, 200.0, false))
        assertTrue(f.muestra(199.5, 200.0, false))
        assertFalse(f.muestra(0.0, 0.0, false))       // sin duración, nunca
    }

    // ---------- lectura ----------

    @Test
    fun lee_marcas_sin_capitulos_ni_tramos_vacios() {
        val o = JSONObject("""{"ok": true, "marks": [{"kind": "intro", "start": 3, "end": 60, "label": "Saltar intro"},
            {"kind": "chapter", "start": 0, "end": 10}, {"kind": "intro", "start": 5, "end": 5}]}""")
        assertEquals(listOf(Marca(3.0, 60.0, "Saltar intro")), parseMarks(o))
    }

    @Test
    fun lee_doblajes_canales_silenciados_y_videos() {
        assertEquals(listOf("es"), parseDubs(JSONObject("""{"dubs": [{"lang": "es", "name": "Español"}, {"lang": ""}]}""")).map { it.lang })
        assertEquals(listOf(Silenciado("UC1", "Un canal")), parseHidden(JSONObject("""{"channels": [{"id": "UC1", "title": "Un canal"}]}""")))
        val v = parseVideos(JSONArray("""[{"id": "abcdefghijk", "title": "En vivo", "live": true, "viewers": 5200, "channel_id": "UC1",
            "published": 1700000000, "published_approx": true}]""")).single()
        assertTrue(v.live)
        assertEquals("yt", v.kind)
        assertEquals(5200, v.viewers)
        assertEquals("UC1", v.channelId)
        assertTrue(v.approx)
    }

    @Test
    fun lee_los_canales_en_vivo_de_la_biblioteca() {
        val l = parseLibrary(JSONObject("""{"items": {}, "live": [{"id": "c1", "name": "Noticias", "host": "ejemplo.org", "poster": "/live/c1/poster.jpg"}]}"""))
        assertEquals("Noticias", l.live.single().name)
        val vista = Datos(l, "http://192.0.2.5:8765", null, null, false, emptyMap()).enVivo()
        val t = vista.filas.single().tarjetas.single()
        assertEquals("live:c1", t.id)
        assertEquals("Noticias   ·   en vivo, sin anuncios", t.info)
        assertEquals("Canales de hoy", vista.filas.single().title)
    }

    // ---------- textos ----------

    @Test
    fun textos_de_youtube_como_el_roku() {
        assertEquals("", viewersText(0))
        assertEquals("830 viendo", viewersText(830))
        assertEquals("5,2 mil viendo", viewersText(5230))
        assertEquals("120 mil viendo", viewersText(120400))
        val utc = TimeZone.getTimeZone("UTC")
        assertEquals("14 nov 2023", dateText(1700000000, utc))
        assertEquals("", publishedText(0, false))
        assertTrue(publishedText(1700000000, false).startsWith("Publicado el "))
        assertEquals("Publicado hace 3 días", publishedText(1700000000, true, now = 1700000000 + 3 * 86400))
    }

    @Test
    fun buscar_no_importan_acentos_ni_mayusculas() {
        assertEquals("el nino y la cancion", plainText("El Niño y la CANCIÓN"))
        val l = parseLibrary(JSONObject("""{"items": {
            "m1": {"id": "m1", "title": "Él (1953)", "full_title": "Él (1953)", "kind": "movie"},
            "m2": {"id": "m2", "title": "Metropolis (1927)", "full_title": "Metropolis (1927)", "kind": "movie"},
            "e1": {"id": "e1", "title": "T1 E1", "full_title": "Una serie · T1 E1", "kind": "episode"}},
            "series": [{"key": "s", "title": "El secreto", "seasons": [{"title": "Temporada 1", "items": [{"id": "e1"}]}]}]}"""))
        val d = Datos(l, "", null, null, false, emptyMap())
        assertEquals(setOf("Él (1953)", "El secreto"), d.buscarBiblioteca("el ").map { it.title }.toSet())
        assertEquals(listOf("Metropolis (1927)"), d.buscarBiblioteca("POLIS").map { it.title })
        assertTrue(d.buscarBiblioteca("   ").isEmpty())
        assertTrue(d.buscarBiblioteca("serie").isEmpty())   // los episodios no salen sueltos
    }

    @Test
    fun ayuda_del_reproductor_dice_ok_seguir_en_pausa() {
        assertEquals("‹ ›: moverte en la barra   ·   OK: pausa   ·   abajo: más opciones   ·   arriba: ocultar", textoAyuda(false, false, false))
        assertEquals("‹ ›: moverte en la barra   ·   OK: seguir   ·   abajo: más opciones   ·   arriba: ocultar", textoAyuda(false, false, true))
        assertEquals("‹ ›: capítulo anterior o siguiente   ·   OK: pausa   ·   abajo: más opciones   ·   arriba: ocultar", textoAyuda(false, true, false))
        assertEquals("OK: seguir   ·   abajo: más opciones   ·   arriba: ocultar", textoAyuda(true, false, true))
    }

    @Test
    fun ajustes_generales_y_sus_valores_por_omision() {
        assertTrue(chapterTitlesOn(emptyMap()))
        assertFalse(chapterTitlesOn(mapOf("chapterTitles" to "false")))
        assertFalse(ytAutoplayOn(emptyMap()))
        assertTrue(ytAutoplayOn(mapOf("ytAutoplay" to "true")))
        assertEquals("Ver los canales", hiddenButtonText(null))
        assertEquals("Ninguno silenciado", hiddenButtonText(emptyList()))
        assertEquals("Ver 2 canales", hiddenButtonText(listOf(Silenciado("a", ""), Silenciado("b", ""))))
    }

    @Test
    fun ajustes_en_la_fila_de_reproduccion() {
        val l = parseLibrary(JSONObject("""{"items": {}, "prefs": {"ytAutoplay": true, "chapterTitles": false}}"""))
        val fila = Datos(l, "", null, null, false, emptyMap()).fila(emptyList())
        val ajustes = fila.filas.last()
        assertEquals("Ajustes generales", ajustes.title)
        assertEquals(listOf("set:autoplay", "set:chapters", "set:hidden", "set:reload"), ajustes.tarjetas.map { it.id })
        assertEquals(1, ajustes.tarjetas[0].ajuste!!.elegido)   // «Seguir con recomendados»
        assertEquals(1, ajustes.tarjetas[1].ajuste!!.elegido)   // «No»
        assertEquals("Ninguno silenciado", ajustes.tarjetas[2].ajuste!!.boton)
    }

    @Test
    fun textos_de_los_errores_de_la_computadora() {
        assertEquals("No se pudo silenciar el canal: sin conexión con la computadora.", textoFallo("silenciar el canal", IOException("x"), null))
        assertEquals("No se pudo anclar el canal: la computadora respondió con un error.",
            textoFallo("anclar el canal", IOException("El servidor respondió 500"), null))
        assertEquals("No se pudo cambiar la fila: ya no está.", textoFallo("cambiar la fila", null, JSONObject("""{"ok": false, "error": "ya no está."}""")))
        assertEquals("No se pudo cambiar la fila.", textoFallo("cambiar la fila", null, JSONObject("{}")))
    }

    @Test
    fun las_tarjetas_que_tienen_opciones_lo_dicen() {
        val l = parseLibrary(JSONObject("""{"items": {"m1": {"id": "m1", "title": "Metropolis (1927)", "full_title": "Metropolis (1927)", "kind": "movie", "duration": 600}}}"""))
        val d = Datos(l, "", null, null, false, emptyMap())
        val t = d.itemTile("m1")!!
        assertTrue(t.menu)
        assertTrue(t.info.endsWith("mantén OK: opciones"))
        val v = d.videoTile(parseVideos(JSONArray("""[{"id": "abcdefghijk", "title": "Algo", "live": true, "channel": "Un canal", "viewers": 1500}]""")).single(), emptyMap())
        assertTrue(v.liveTag)
        assertEquals(0, v.dur)
        assertEquals("Un canal · 1,5 mil viendo", v.line2)
    }

    @Test
    fun cada_tarjeta_muestra_solo_la_imagen_de_su_direccion() {
        // Compose puede reutilizar el lugar de una tarjeta para otra (al correrse una fila o al volver de una ficha):
        // la imagen cargada para Metropolis no debe verse en el lugar de un video de YouTube.
        val metropolis = "/art/m1.jpg" to "póster de Metropolis"
        assertEquals("póster de Metropolis", imagenPara("/art/m1.jpg", metropolis))
        assertNull(imagenPara("/yt/S4Fnl8Z7X74/thumb.jpg", metropolis))
        assertNull(imagenPara("/art/m1.jpg", null))
    }
}
