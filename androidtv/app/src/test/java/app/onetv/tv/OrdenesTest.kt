package app.onetv.tv

import app.onetv.tv.control.Orden
import app.onetv.tv.control.hayVersionNueva
import app.onetv.tv.control.leerOrden
import app.onetv.tv.control.leerOrdenes
import app.onetv.tv.control.leerSesionMusica
import app.onetv.tv.control.teclaDeOrden
import app.onetv.tv.control.textoVersionNueva
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** Las órdenes que manda la computadora (mac/teles.py), las mismas que recibe el Roku en onInputArgs. */
class OrdenesTest {

    private fun orden(json: String) = leerOrden(JSONObject(json))

    @Test
    fun ver_algo_con_o_sin_pistas_y_desde_donde() {
        assertEquals(Orden.Ver("a3b6876915a4", 1, -1, 30.0), orden("""{"cmd":"play","contentId":"a3b6876915a4","audio":1,"sub":-1,"start":30}"""))
        assertEquals(Orden.Ver("yt:dQw4w9WgXcQ"), orden("""{"cmd":"play","contentId":"yt:dQw4w9WgXcQ"}"""))
        assertEquals(Orden.Ver("music:0123456789"), orden("""{"cmd":"play","contentId":"music:0123456789","audio":null}"""))
        assertNull(orden("""{"cmd":"play","contentId":""}"""))
    }

    @Test
    fun teclas_avanzar_pistas_cancion_y_actualiza() {
        assertEquals(Orden.Boton("Play"), orden("""{"cmd":"key","key":"Play"}"""))
        assertEquals(Orden.IrA(754.0), orden("""{"cmd":"seek","t":754}"""))
        assertEquals(Orden.IrA(0.0), orden("""{"cmd":"seek","t":-5}"""))
        assertNull(orden("""{"cmd":"seek"}"""))
        assertEquals(Orden.Pistas(2, null), orden("""{"cmd":"tracks","audio":2}"""))
        assertEquals(Orden.Pistas(null, -1), orden("""{"cmd":"tracks","sub":-1}"""))
        assertNull(orden("""{"cmd":"tracks"}"""))
        assertEquals(Orden.Cancion(-1), orden("""{"cmd":"song","dir":-1}"""))
        assertEquals(Orden.Cancion(1), orden("""{"cmd":"song","dir":"1"}"""))
        assertEquals(Orden.Actualiza, orden("""{"cmd":"refresh"}"""))
        assertNull(orden("""{"cmd":"algo-nuevo"}"""))   // un servidor más nuevo: lo que no se entiende se ignora
    }

    @Test
    fun la_respuesta_de_la_consulta() {
        val o = JSONObject("""{"ok":true,"ordenes":[{"cmd":"key","key":"Back"},{"cmd":"otra"},{"cmd":"refresh"}]}""")
        assertEquals(listOf(Orden.Boton("Back"), Orden.Actualiza), leerOrdenes(o))
        assertEquals(emptyList<Orden>(), leerOrdenes(JSONObject("""{"ok":true,"ordenes":[]}""")))
        assertEquals(emptyList<Orden>(), leerOrdenes(JSONObject("{}")))
    }

    @Test
    fun teclas_con_los_nombres_del_roku() {
        assertEquals(Tecla.ADELANTAR, teclaDeOrden("Fwd"))
        assertEquals(Tecla.ATRASAR, teclaDeOrden("Rev"))
        assertEquals(Tecla.REPETIR, teclaDeOrden("InstantReplay"))
        assertEquals(Tecla.OK, teclaDeOrden("Select"))
        assertEquals(Tecla.OPCIONES, teclaDeOrden("Info"))
        assertNull(teclaDeOrden("Play"))   // pausa o sigue: se atiende aparte
    }

    @Test
    fun la_musica_que_manda_la_computadora() {
        val s = leerSesionMusica(JSONObject("""{"ok":true,"index":1,"start":95,"tracks":[
            {"id":"t1","title":"Oh Yeah","artist":"Yello","album":"Stella","duration":180.5,"url":"/music/t1/audio","art":"/music/art/a1.jpg"},
            {"id":"t2","title":"Desire","artist":"Yello","album":"Stella","duration":200,"url":"/music/t2/audio","art":"/music/art/a1.jpg"},
            {"id":"","title":"sin id"}]}"""))!!
        assertEquals(listOf("Oh Yeah", "Desire"), s.canciones.map { it.title })
        assertEquals(1, s.index)
        assertEquals(95.0, s.start, 0.0)
        assertEquals("/music/t1/audio", s.canciones[0].url)
        assertEquals(180.5, s.canciones[0].duration, 0.0)
        assertNull(leerSesionMusica(JSONObject("""{"ok":false,"error":"Esa lista ya no está."}""")))
        assertEquals(0, leerSesionMusica(JSONObject("""{"ok":true,"index":9,"tracks":[{"id":"t","url":"/u"}]}"""))!!.index)
    }

    @Test
    fun avisa_solo_si_la_computadora_tiene_una_mas_nueva() {
        assertTrue(hayVersionNueva(5, JSONObject("""{"hay":true,"version":"0.1.7","version_code":8}""")))
        assertFalse(hayVersionNueva(8, JSONObject("""{"hay":true,"version":"0.1.7","version_code":8}""")))
        assertFalse(hayVersionNueva(1, JSONObject("""{"hay":false,"version_code":0}""")))
        assertFalse(hayVersionNueva(1, JSONObject("""{"hay":true,"version":"0.1","version_code":0}""")))   // sin número: no se molesta
        assertEquals("Hay una versión nueva de One TV (0.1.7). Para tenerla, abre Downloader y escribe otra vez http://192.0.2.5:8765/tv",
            textoVersionNueva("0.1.7", "http://192.0.2.5:8765/tv"))
    }
}
