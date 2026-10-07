package app.onetv.tv.net

import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.cancelChildren
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.joinAll
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withPermit
import kotlinx.coroutines.withContext
import org.json.JSONObject

/**
 * Encontrar la computadora con One TV en la red de la casa, sin configurar nada: se prueba en paralelo
 * http://<cada dirección de la red>:8765/api/status con un tiempo límite corto y se reconoce la respuesta de One TV.
 */
object Busqueda {
    const val PUERTO = 8765

    /** ¿Esta respuesta de /api/status es de One TV? (mac/cine.py, App.status: items, queue, playing…) */
    fun esOneTv(body: String): Boolean = try {
        val o = JSONObject(body)
        o.has("items") && o.has("queue") && o.has("playing") && o.opt("items") is Number
    } catch (_: Exception) {
        false
    }

    /**
     * Las direcciones a probar: la red /24 de cada dirección propia (sin la propia), empezando por las más cercanas
     * a la propia (las computadoras suelen tener números parecidos a los de la TV).
     */
    fun candidatas(propias: List<String>): List<String> {
        val out = LinkedHashSet<String>()
        for (ip in propias) {
            val parts = ip.split(".")
            if (parts.size != 4) continue
            val last = parts[3].toIntOrNull() ?: continue
            if (parts.take(3).any { it.toIntOrNull() !in 0..255 }) continue
            val base = parts.take(3).joinToString(".")
            (1..254).filter { it != last }.sortedBy { kotlin.math.abs(it - last) }.forEach { out.add("$base.$it") }
        }
        return out.toList()
    }

    fun direccion(ip: String, puerto: Int) = "http://$ip:$puerto"

    /**
     * Prueba primero la dirección recordada (si hay) y después toda la red, de a `paralelo` a la vez. La primera que
     * responda como One TV gana y se dejan de probar las demás. -> la dirección del servidor o null.
     */
    suspend fun buscar(
        recordada: String?,
        propias: List<String>,
        puerto: Int = PUERTO,
        paralelo: Int = 48,
        probar: suspend (String) -> Boolean,
    ): String? = withContext(Dispatchers.IO) {
        if (!recordada.isNullOrEmpty() && probar(recordada)) return@withContext recordada
        val result = CompletableDeferred<String?>()
        val gate = Semaphore(paralelo)
        coroutineScope {
            val jobs = candidatas(propias).map { ip ->
                launch {
                    gate.withPermit {
                        if (result.isCompleted) return@withPermit
                        val url = direccion(ip, puerto)
                        if (probar(url)) result.complete(url)
                    }
                }
            }
            launch {
                jobs.joinAll()
                result.complete(null)
            }
            val found = result.await()
            coroutineContext.cancelChildren()   // ya se encontró: se dejan de probar las demás
            found
        }
    }

    /** Lo que una persona escribe («192.0.2.5», «192.0.2.5:8765», «http://…») -> la dirección completa, o null. */
    fun normalizar(texto: String): String? {
        var t = texto.trim().trimEnd('/')
        if (t.isEmpty()) return null
        if (!t.startsWith("http://") && !t.startsWith("https://")) t = "http://$t"
        val host = t.substringAfter("://").substringBefore("/")
        if (host.isEmpty() || host.any { it.isWhitespace() }) return null
        val sinPuerto = host.substringBefore(":")
        if (sinPuerto.isEmpty()) return null
        val conPuerto = if (host.contains(":")) host else "$host:$PUERTO"
        return t.substringBefore("://") + "://" + conPuerto
    }
}
