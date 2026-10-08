package app.onetv.tv

import app.onetv.tv.data.countText
import app.onetv.tv.net.Busqueda
import app.onetv.tv.net.Encontrada
import kotlinx.coroutines.launch

// Elegir la computadora cuando en la casa hay más de una con One TV (por ejemplo, la computadora de siempre y un NAS):
// al abrir la app, si encuentra varias y ninguna es la de antes, pregunta cuál (con su nombre y cuántos videos tiene);
// después se cambia en Fila de reproducción › Ajustes generales › Computadora › «Cambiar» (o desde «No encuentro la
// computadora»). La elegida se recuerda por su dirección y su nombre.

/** Lo que dice la TV cuando la computadora no tiene videos: sin nombres de archivos ni comandos. */
fun textoSinVideos(carpetasSinPermiso: Int): String =   // los mismos del Roku (MainScene.brs)
    if (carpetasSinPermiso > 0) "La computadora no puede leer tu carpeta de videos: abre One TV en ella y verás qué hacer."
    else "No hay videos todavía: copia tus películas y series a la carpeta de videos de la computadora."

/** Una línea de cada computadora en la lista: cuántos videos tiene y su dirección (sin «http://»). */
fun lineaComputadora(c: Encontrada, actual: Boolean): String =
    listOfNotNull(if (actual) "La de ahora" else null, countText(c.videos, "video", "videos"),
        c.direccion.removePrefix("http://")).joinToString("   ·   ")

/** Las opciones de la pantalla «Elige la computadora»: las encontradas y, al final, buscar otra vez y escribir. */
fun Estado.opcionesElegir(): List<Opcion> =
    encontradas.map { Opcion(it.nombre, lineaComputadora(it, lib != null && it.direccion == direccion), "laptop", "c") } +
        Opcion("Buscar otra vez", "", "refresh", "buscar") + Opcion("Escribir la dirección", "", "laptop", "escribir")

/** La de siempre no aparece al abrir (apagada, o se desinstaló): se dice cuál y se ofrecen las que sí hay. */
fun notaNoEncuentro(nombre: String) = "No encuentro «$nombre» (¿está apagada?). Puedes elegir otra:"

/** Al abrir, con más de una computadora y ninguna conocida (o sin la de siempre): se pregunta cuál. */
fun Estado.mostrarComputadoras(todas: List<Encontrada>, nota: String = "") {
    notaElegir = nota
    encontradas = todas
    elegirIndex = 0
    buscandoTodas = false
    conexion = Conexion.ELEGIR
}

/** «Cambiar» (Ajustes generales) o «Elegir otra computadora»: busca todas las de la red y deja elegir. */
fun Estado.cambiarComputadora() {
    notaElegir = ""
    conexion = Conexion.ELEGIR
    encontradas = emptyList()
    elegirIndex = 0
    buscarOtraVez()
}

private fun Estado.buscarOtraVez() {
    if (buscandoTodas) return
    buscandoTodas = true
    scope.launch {
        val todas = Busqueda.buscarTodas(direccion.ifEmpty { null }, direccionesDeLaTv(), puertosBusqueda) { leerComputadora(it) }
        buscandoTodas = false
        encontradas = todas
        elegirIndex = todas.indexOfFirst { lib != null && it.direccion == direccion }.coerceAtLeast(0)
    }
}

/** Las teclas en «Elige la computadora»: ▲ ▼ mueven, OK elige, Atrás vuelve a la de ahora (o sale, si no hay). */
fun Estado.teclaElegir(t: Tecla): Boolean {
    val n = if (buscandoTodas) 0 else opcionesElegir().size
    when (t) {
        Tecla.ARRIBA -> if (elegirIndex > 0) elegirIndex--
        Tecla.ABAJO -> if (elegirIndex < n - 1) elegirIndex++
        Tecla.OK -> if (n > 0) {
            val k = elegirIndex.coerceIn(0, n - 1)
            when {
                k < encontradas.size -> usarComputadora(encontradas[k])
                k == encontradas.size -> {
                    encontradas = emptyList()
                    elegirIndex = 0
                    buscarOtraVez()
                }
                else -> {
                    escribirDesde = Conexion.ELEGIR
                    conexion = Conexion.ESCRIBIR
                }
            }
        }
        Tecla.ATRAS -> if (lib != null) conexion = Conexion.LISTA else salir()
        else -> {}
    }
    return true
}

/**
 * Usar esa computadora. Si es otra (no la de ahora), se olvida lo de la anterior (catálogo, YouTube, música, páginas)
 * y se suelta su consulta de órdenes; se recuerda la nueva y se carga su biblioteca desde Inicio.
 */
fun Estado.usarComputadora(c: Encontrada) {
    busqueda?.cancel()
    busqueda = null
    if (lib == null || c.direccion == direccion) {
        if (lib != null) {   // la misma: solo vuelve
            if (c.nombre.isNotEmpty()) nombreServidor = c.nombre
            conexion = Conexion.LISTA
            return
        }
        conectar(c)
        return
    }
    val anterior = api.base
    if (reproductor.visible) reproductor.detener(conReporte = true)
    olvidarCatalogo()
    nombreServidor = ""
    conectar(c)
    cambioDeComputadora(anterior)
    mostrarAviso("Ahora ves «${c.nombre}».")
}
