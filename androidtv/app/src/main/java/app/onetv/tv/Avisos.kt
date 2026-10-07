package app.onetv.tv

import app.onetv.tv.data.Marca

// Lo que el reproductor decide con el paso del tiempo, sin nada de Android (se prueba en la computadora): el aviso para
// saltar la intro (Player.brs, onPosition) y el final que no llega (Player.brs, onEndWatch).

/**
 * El aviso «Saltar intro»: se ofrece desde que se entra al tramo, durante 8 s (o hasta su final si es antes). Si se sale
 * del tramo y se vuelve a entrar, se ofrece otra vez. Nunca se salta solo.
 */
class SaltarIntro(val marcas: List<Marca>) {
    private enum class Est { FUERA, OFRECIDA, HECHA }

    private val estado = MutableList(marcas.size) { Est.FUERA }
    private val hasta = MutableList(marcas.size) { 0.0 }

    /** La marca que se está ofreciendo (-1: ninguna). */
    var actual = -1
        private set

    /** Cuánto falta de la línea que se vacía (1 lleno, 0 vacío). */
    var resto = 1.0
        private set

    /** Pasó el tiempo: at es la posición; playing, si el video avanza. -> true si cambió si el aviso se ve o no. */
    fun en(at: Double, playing: Boolean): Boolean {
        val antes = actual
        for (i in marcas.indices) {
            val m = marcas[i]
            val inside = at >= m.start && at < m.end
            when {
                !inside -> {
                    estado[i] = Est.FUERA
                    if (actual == i) actual = -1
                }
                estado[i] == Est.FUERA && playing && actual == -1 -> {
                    estado[i] = Est.OFRECIDA
                    hasta[i] = minOf(at + 8, m.end)
                    actual = i
                    resto = 1.0
                }
                estado[i] == Est.OFRECIDA && actual == i -> if (at >= hasta[i]) {
                    estado[i] = Est.HECHA
                    actual = -1
                } else resto = ((hasta[i] - at) / 8.0).coerceIn(0.0, 1.0)
            }
        }
        return antes != actual
    }

    /** Se apretó una tecla con el aviso a la vista: ya no se ofrece (hasta salir del tramo). -> a dónde saltar con OK. */
    fun usar(): Double? {
        val i = actual
        if (i < 0) return null
        estado[i] = Est.HECHA
        actual = -1
        return marcas[i].end
    }
}

/**
 * Algunas canciones (AAC convertido desde FLAC) se quedan a décimas del final sin que el reproductor avise que terminaron:
 * la TV se quedaba ahí para siempre, en silencio. A menos de 2 s del final, si en 2 s el avance no se movió (y no está en
 * pausa), se da por terminado. Se llama cada 2 s mientras se esté cerca del final.
 */
class FinSinAviso {
    private var antes = -1.0

    /** -> true: darlo por terminado. */
    fun muestra(at: Double, duration: Double, paused: Boolean): Boolean {
        if (duration <= 0 || at < duration - 2) {
            antes = -1.0
            return false
        }
        if (paused) {
            antes = -1.0
            return false
        }
        if (antes >= 0 && kotlin.math.abs(at - antes) < 0.05) {
            antes = -1.0
            return true
        }
        antes = at
        return false
    }

    fun reiniciar() {
        antes = -1.0
    }
}
