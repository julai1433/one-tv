package app.onetv.tv.net

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

/** Hablar con el servidor de One TV: GET y POST con JSON (sin bibliotecas aparte: lo que trae Android). */
class Servidor(@Volatile var base: String) {

    fun url(path: String): String = if (path.startsWith("http://") || path.startsWith("https://")) path else base + path

    suspend fun get(path: String, timeoutMs: Int = 15000): JSONObject = withContext(Dispatchers.IO) {
        JSONObject(leer(url(path), null, timeoutMs))
    }

    /** POST con JSON (el servidor solo acepta órdenes en JSON). */
    suspend fun post(path: String, body: JSONObject, timeoutMs: Int = 15000): JSONObject = withContext(Dispatchers.IO) {
        val text = leer(url(path), body.toString(), timeoutMs)
        if (text.isBlank()) JSONObject() else JSONObject(text)
    }

    companion object {
        /** Lee una dirección y devuelve el texto; con `body`, lo manda como POST con JSON. Falla con IOException. */
        fun leer(url: String, body: String?, timeoutMs: Int): String {
            val c = URL(url).openConnection() as HttpURLConnection
            try {
                c.connectTimeout = timeoutMs
                c.readTimeout = timeoutMs
                c.useCaches = false
                if (body != null) {
                    c.requestMethod = "POST"
                    c.doOutput = true
                    c.setRequestProperty("Content-Type", "application/json")
                    c.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
                }
                val code = c.responseCode
                if (code !in 200..299) throw IOException("El servidor respondió $code")
                return c.inputStream.use { it.readBytes().toString(Charsets.UTF_8) }
            } finally {
                c.disconnect()
            }
        }

        /** ¿Hay un servidor de One TV en esta dirección? Con tiempo límite corto (para buscar en toda la red). */
        fun esOneTv(base: String, timeoutMs: Int = 700): Boolean = try {
            Busqueda.esOneTv(leer("$base/api/status", null, timeoutMs))
        } catch (_: Exception) {
            false
        }
    }
}
