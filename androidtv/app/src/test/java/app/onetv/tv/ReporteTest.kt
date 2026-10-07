package app.onetv.tv

import app.onetv.tv.data.ProgressReport
import app.onetv.tv.data.reportState
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** El aviso de avance tiene el mismo formato que el del Roku (roku/components/Player.brs, report). */
class ReporteTest {

    @Test
    fun manda_los_mismos_datos_que_el_roku() {
        val o = ProgressReport("a3b6876915a4", 196.5, 600.0, "tick", 1, 0, "play", "androidtv-1").toJson()
        assertEquals(setOf("id", "p", "d", "ev", "audio", "sub", "state", "device_id"), o.keys().asSequence().toSet())
        assertEquals("a3b6876915a4", o.getString("id"))
        assertEquals(196.5, o.getDouble("p"), 0.0)
        assertEquals(600.0, o.getDouble("d"), 0.0)
        assertEquals("tick", o.getString("ev"))
        assertEquals(1, o.getInt("audio"))
        assertEquals(0, o.getInt("sub"))
        assertEquals("play", o.getString("state"))
        assertEquals("androidtv-1", o.getString("device_id"))
    }

    @Test
    fun sin_subtitulos_es_menos_uno() {
        val o = ProgressReport("x", 0.0, 0.0, "start", 0, -1, "play", "d").toJson()
        assertEquals(-1, o.getInt("sub"))
        assertFalse(o.has("song"))
    }

    @Test
    fun con_musica_dice_que_cancion_suena() {
        val o = ProgressReport("track:b25c5e83d244", 3.0, 20.0, "tick", 0, -1, "play", "d", songIndex = 2, songCount = 4).toJson()
        assertTrue(o.has("song"))
        assertEquals(2, o.getJSONObject("song").getInt("i"))
        assertEquals(4, o.getJSONObject("song").getInt("n"))
    }

    @Test
    fun el_estado_en_palabras_del_reporte() {
        assertEquals("play", reportState(playing = true, buffering = false))
        assertEquals("pause", reportState(playing = false, buffering = false))
        assertEquals("buffer", reportState(playing = true, buffering = true))
    }
}
