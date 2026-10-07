package app.onetv.tv

import app.onetv.tv.net.Busqueda
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.util.Collections

/** Encontrar la computadora con One TV en la red de la casa, sin configurar nada. */
class BusquedaTest {

    @Test
    fun reconoce_la_respuesta_de_one_tv() {
        // Lo que responde /api/status (mac/cine.py, App.status).
        val status = """{"roku": "192.0.2.10", "server": "", "items": 10, "iphone": null, "playing": null, "queue": 0, "dubbing": null}"""
        assertTrue(Busqueda.esOneTv(status))
    }

    @Test
    fun no_confunde_otras_respuestas_con_one_tv() {
        assertFalse(Busqueda.esOneTv("<html>router de la casa</html>"))
        assertFalse(Busqueda.esOneTv("""{"status": "ok"}"""))
        assertFalse(Busqueda.esOneTv("""{"items": "muchos", "queue": 0, "playing": null}"""))
        assertFalse(Busqueda.esOneTv(""))
    }

    @Test
    fun prueba_toda_la_red_menos_la_propia_y_empieza_por_las_cercanas() {
        val c = Busqueda.candidatas(listOf("192.0.2.40"))
        assertEquals(253, c.size)
        assertFalse("192.0.2.40" in c)
        assertEquals(listOf("192.0.2.39", "192.0.2.41"), c.take(2).sorted())
        assertTrue("192.0.2.1" in c && "192.0.2.254" in c)
        assertFalse("192.0.2.0" in c || "192.0.2.255" in c)
    }

    @Test
    fun ignora_direcciones_que_no_son_ipv4() {
        assertTrue(Busqueda.candidatas(listOf("fe80::1", "no es una dirección", "300.1.2.3")).isEmpty())
    }

    @Test
    fun encuentra_la_computadora_aunque_esten_lejos_en_la_red() = runBlocking {
        val probadas = Collections.synchronizedList(mutableListOf<String>())
        val found = Busqueda.buscar(null, listOf("192.0.2.200"), puerto = 8765) { url ->
            probadas += url
            delay(5)
            url == "http://192.0.2.7:8765"
        }
        assertEquals("http://192.0.2.7:8765", found)
    }

    @Test
    fun primero_prueba_la_direccion_recordada() = runBlocking {
        val probadas = Collections.synchronizedList(mutableListOf<String>())
        val found = Busqueda.buscar("http://192.0.2.50:8765", listOf("192.0.2.200")) { url ->
            probadas += url
            true
        }
        assertEquals("http://192.0.2.50:8765", found)
        assertEquals(listOf("http://192.0.2.50:8765"), probadas)
    }

    @Test
    fun si_cambio_de_direccion_la_vuelve_a_encontrar() = runBlocking {
        // La recordada ya no responde (la computadora cambió de dirección): se busca en toda la red.
        val found = Busqueda.buscar("http://192.0.2.50:8765", listOf("192.0.2.200")) { url -> url == "http://192.0.2.61:8765" }
        assertEquals("http://192.0.2.61:8765", found)
    }

    @Test
    fun sin_computadora_devuelve_nada() = runBlocking {
        assertNull(Busqueda.buscar(null, listOf("192.0.2.200")) { false })
    }

    @Test
    fun usa_el_puerto_que_se_pida() = runBlocking {
        val found = Busqueda.buscar(null, listOf("10.0.2.15"), puerto = 8797) { url -> url == "http://10.0.2.2:8797" }
        assertEquals("http://10.0.2.2:8797", found)
    }

    @Test
    fun entiende_la_direccion_escrita_a_mano() {
        assertEquals("http://192.0.2.5:8765", Busqueda.normalizar("192.0.2.5"))
        assertEquals("http://192.0.2.5:8765", Busqueda.normalizar("  192.0.2.5/ "))
        assertEquals("http://192.0.2.5:9000", Busqueda.normalizar("192.0.2.5:9000"))
        assertEquals("http://192.0.2.5:8765", Busqueda.normalizar("http://192.0.2.5:8765/"))
        assertNull(Busqueda.normalizar(""))
        assertNull(Busqueda.normalizar("192.0 .2.5"))
    }
}
