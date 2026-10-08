package app.onetv.tv.net

import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.cancelChildren
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.joinAll
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withPermit
import kotlinx.coroutines.withContext
import org.json.JSONObject

/** Una computadora con One TV en la red: su dirección, su nombre («MacBook de Ana», «NAS de la sala») y cuántos videos
 *  tiene (para elegir entre varias). */
data class Encontrada(val direccion: String, val nombre: String, val videos: Int)

/**
 * Encontrar la computadora con One TV en la red de la casa, sin configurar nada: se prueba en paralelo
 * http://<cada dirección de la red>:8765/api/status con un tiempo límite corto y se reconoce la respuesta de One TV.
 * Si hay más de una (por ejemplo, una computadora y un NAS), [buscarTodas] las junta para que la persona elija.
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

    /** La respuesta de /api/status de `direccion` -> la computadora (nombre y videos), o null si no es One TV. Sin
     *  «nombre» (una versión vieja del servidor), se nombra por su dirección. */
    fun leerEstado(direccion: String, body: String): Encontrada? {
        if (!esOneTv(body)) return null
        val o = JSONObject(body)
        val nombre = o.optString("nombre", "").trim().ifEmpty { direccion.substringAfter("://").substringBefore(":") }
        return Encontrada(direccion, nombre, o.optInt("items", 0))
    }

    /** De las encontradas, «la de siempre»: la del nombre recordado o, si no se recuerda ninguno, la única que hay. */
    fun laMisma(todas: List<Encontrada>, nombre: String?): Encontrada? =
        if (nombre.isNullOrEmpty()) todas.singleOrNull() else todas.singleOrNull { it.nombre == nombre }

    /**
     * Todas las computadoras con One TV de la red (la recordada, si hay, y toda la red en cada puerto), de a `paralelo`
     * a la vez. -> primero las que tienen más videos; sin repetir dirección.
     */
    suspend fun buscarTodas(
        recordada: String?,
        propias: List<String>,
        puertos: List<Int> = listOf(PUERTO),
        paralelo: Int = 48,
        leer: suspend (String) -> Encontrada?,
    ): List<Encontrada> = withContext(Dispatchers.IO) {
        val urls = LinkedHashSet<String>()
        if (!recordada.isNullOrEmpty()) urls += recordada
        for (ip in candidatas(propias)) for (p in puertos) urls += direccion(ip, p)
        val gate = Semaphore(paralelo)
        val found = coroutineScope { urls.map { url -> async { gate.withPermit { leer(url) } } }.awaitAll() }
        found.filterNotNull().distinctBy { it.direccion }.sortedWith(compareByDescending<Encontrada> { it.videos }.thenBy { it.nombre })
    }

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
