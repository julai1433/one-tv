package app.onetv.tv

import app.onetv.tv.data.agoText
import app.onetv.tv.data.bareTitle
import app.onetv.tv.data.countText
import app.onetv.tv.data.fmtClock
import app.onetv.tv.data.fmtDuration
import app.onetv.tv.data.initialsOf
import app.onetv.tv.data.joinAnd
import app.onetv.tv.data.marquee
import app.onetv.tv.data.remainingText
import app.onetv.tv.data.yearOf
import org.junit.Assert.assertEquals
import org.junit.Test

/** Los mismos textos que la app del Roku (roku/components/Util.brs). */
class TextosTest {

    @Test
    fun tiempos() {
        assertEquals("4:05", fmtClock(245.0))
        assertEquals("1:02:03", fmtClock(3723.0))
        assertEquals("0:00", fmtClock(-3.0))
        assertEquals("1 h 59 min", fmtDuration(7140.0))
        assertEquals("45 min", fmtDuration(2700.0))
        assertEquals("menos de 1 min", fmtDuration(30.0))
        assertEquals("quedan 6 min", remainingText(196.0, 600.0))
        assertEquals("queda menos de 1 min", remainingText(570.0, 600.0))
        assertEquals("", remainingText(0.0, 600.0))
    }

    @Test
    fun conteos_y_titulos() {
        assertEquals("1 película", countText(1, "película", "películas"))
        assertEquals("7 películas", countText(7, "película", "películas"))
        assertEquals("Rocky", bareTitle("Rocky (1976)"))
        assertEquals("1976", yearOf("Rocky (1976)"))
        assertEquals("", yearOf("Sin año"))
        assertEquals("PELÍCULAS Y AÑOS", marquee("Películas y años"))
        assertEquals("NM", initialsOf("NPR Music"))
        assertEquals("?", initialsOf("  "))
    }

    @Test
    fun y_cambia_a_e_antes_de_i() {
        assertEquals("español e inglés", joinAnd(listOf("español", "inglés")))
        assertEquals("inglés y español", joinAnd(listOf("inglés", "español")))
        assertEquals("a, b y c", joinAnd(listOf("a", "b", "c")))
    }

    @Test
    fun hace_cuanto() {
        val now = 1_000_000_000L
        assertEquals("hace 5 min", agoText(now - 300, now))
        assertEquals("hace 3 h", agoText(now - 3 * 3600, now))
        assertEquals("hace 1 día", agoText(now - 86400, now))
        assertEquals("hace 2 semanas", agoText(now - 15 * 86400, now))
        assertEquals("", agoText(0, now))
    }
}
