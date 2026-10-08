package app.onetv.tv.control

import android.content.Context
import android.os.Build
import android.provider.Settings
import androidx.core.content.pm.PackageInfoCompat
import app.onetv.tv.Capa
import app.onetv.tv.Conexion
import app.onetv.tv.Estado
import app.onetv.tv.Tecla
import app.onetv.tv.verEnVivo
import app.onetv.tv.data.Song
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import org.json.JSONObject
import java.net.URLEncoder

// Que la computadora maneje esta TV como maneja al Roku («Ver en la TV», pausa, avanzar, pistas, canción anterior o
// siguiente, salir, actualiza). El Roku tiene un control remoto de red; esta app, mientras está abierta, deja una
// consulta esperando en el servidor (GET /api/tv/ordenes, mac/teles.py) que se contesta en cuanto hay una orden, y la
// vuelve a hacer. Las órdenes son las mismas que recibe el Roku (onInputArgs en roku/components/MainScene.brs).

/** Una orden de la computadora. */
sealed interface Orden {
    /** Ver algo: el id de una película o episodio, «yt:<video>», «music:<sesión>», «live:<canal>» o «mosaic:<id>». */
    data class Ver(val contentId: String, val audio: Int? = null, val sub: Int? = null, val start: Double? = null) : Orden

    /** Una tecla del control con los nombres del Roku: Play (pausa o sigue), Back (salir), Fwd, Rev… */
    data class Boton(val nombre: String) : Orden

    /** Ir a ese segundo de lo que se ve. */
    data class IrA(val segundos: Double) : Orden

    /** Cambiar el audio o los subtítulos (sub = -1: sin subtítulos). */
    data class Pistas(val audio: Int?, val sub: Int?) : Orden

    /** La canción anterior (-1) o la siguiente (1). */
    data class Cancion(val dir: Int) : Orden

    /** Algo cambió en la computadora (la biblioteca, la fila): volver a leerla. */
    data object Actualiza : Orden

    /** El código para cambiar la configuración de One TV desde otro aparato (lo pide el asistente de la web). */
    data class Codigo(val codigo: String) : Orden
}

private fun JSONObject.entero(key: String): Int? =
    if (!has(key) || isNull(key)) null else optDouble(key, Double.NaN).takeIf { !it.isNaN() }?.toInt()

private fun JSONObject.numero(key: String): Double? =
    if (!has(key) || isNull(key)) null else optDouble(key, Double.NaN).takeIf { !it.isNaN() }

/** Una orden tal cual la manda el servidor ({"cmd": …}). Lo que no se entiende se ignora (null). */
fun leerOrden(o: JSONObject): Orden? = when (o.optString("cmd")) {
    "play" -> o.optString("contentId").takeIf { it.isNotBlank() }?.let {
        Orden.Ver(it, o.entero("audio"), o.entero("sub"), o.numero("start"))
    }
    "key" -> o.optString("key").takeIf { it.isNotBlank() }?.let { Orden.Boton(it) }
    "seek" -> o.numero("t")?.let { Orden.IrA(it.coerceAtLeast(0.0)) }
    "tracks" -> Orden.Pistas(o.entero("audio"), o.entero("sub")).takeIf { it.audio != null || it.sub != null }
    "song" -> Orden.Cancion(if ((o.entero("dir") ?: 1) < 0) -1 else 1)
    "refresh" -> Orden.Actualiza
    "codigo" -> o.optString("codigo").takeIf { CODIGO.matches(it) }?.let { Orden.Codigo(it) }
    else -> null
}

private val CODIGO = Regex("[0-9]{6}")

/** «482913» -> «482 913»: así se lee de lejos (y así lo escribe el registro de la computadora). */
fun codigoLegible(codigo: String): String = codigo.take(3) + " " + codigo.drop(3)

/** La respuesta de la consulta: {"ok": true, "ordenes": [...]}. */
fun leerOrdenes(o: JSONObject): List<Orden> {
    val arr = o.optJSONArray("ordenes") ?: return emptyList()
    return (0 until arr.length()).mapNotNull { i -> arr.optJSONObject(i)?.let(::leerOrden) }
}

/** Las teclas que la web manda con los nombres del Roku (además de Play y Back, que se atienden aparte). */
fun teclaDeOrden(nombre: String): Tecla? = when (nombre) {
    "Fwd" -> Tecla.ADELANTAR
    "Rev" -> Tecla.ATRASAR
    "InstantReplay" -> Tecla.REPETIR
    "Select" -> Tecla.OK
    "Up" -> Tecla.ARRIBA
    "Down" -> Tecla.ABAJO
    "Left" -> Tecla.IZQ
    "Right" -> Tecla.DER
    "Info" -> Tecla.OPCIONES
    else -> null
}

/** Lo que se mandó a la TV para escuchar (/api/music/session): las canciones, desde cuál y desde qué segundo. */
data class SesionMusica(val canciones: List<Song>, val index: Int, val start: Double)

fun leerSesionMusica(o: JSONObject): SesionMusica? {
    if (!o.optBoolean("ok", true)) return null
    val arr = o.optJSONArray("tracks") ?: return null
    val songs = (0 until arr.length()).mapNotNull { i ->
        arr.optJSONObject(i)?.let { t ->
            val id = t.optString("id")
            if (id.isEmpty() || t.optString("url").isEmpty()) null
            else Song(id, t.optString("title"), t.optString("artist"), t.optString("album"), t.optDouble("duration", 0.0).let { if (it.isNaN()) 0.0 else it },
                t.optString("url"), t.optString("art"))
        }
    }
    if (songs.isEmpty()) return null
    return SesionMusica(songs, o.optInt("index", 0).coerceIn(0, songs.size - 1), o.optDouble("start", 0.0).let { if (it.isNaN()) 0.0 else it.coerceAtLeast(0.0) })
}

/** ¿La computadora ofrece una versión más nueva que la instalada? (/api/tv/app) */
fun hayVersionNueva(propia: Long, o: JSONObject): Boolean =
    o.optBoolean("hay", false) && o.optLong("version_code", 0) > propia

/** El aviso, con la dirección que hay que escribir otra vez en «Downloader» (la misma con que se instaló). */
fun textoVersionNueva(version: String, direccion: String): String =
    "Hay una versión nueva de One TV" + (if (version.isNotBlank()) " ($version)" else "") +
        ". Para tenerla, abre Downloader y escribe otra vez $direccion"

/** El nombre de esta TV como lo puso la persona (Ajustes › Información › Nombre), o la marca y el modelo. */
fun nombreDeLaTv(ctx: Context): String {
    val puesto = try {
        if (Build.VERSION.SDK_INT >= 25) Settings.Global.getString(ctx.contentResolver, Settings.Global.DEVICE_NAME) else null
    } catch (_: Exception) {
        null
    }
    return puesto?.trim()?.takeIf { it.isNotEmpty() }
        ?: listOf(Build.MANUFACTURER, Build.MODEL).filter { !it.isNullOrBlank() }.joinToString(" ").ifBlank { "TV con Android" }
}

/** La versión instalada (versionCode), para saber si la computadora ofrece una más nueva. */
fun versionPropia(ctx: Context): Long = try {
    PackageInfoCompat.getLongVersionCode(ctx.packageManager.getPackageInfo(ctx.packageName, 0))
} catch (_: Exception) {
    0
}

/**
 * La consulta que espera las órdenes mientras la app está a la vista ([empezar] en onStart, [parar] en onStop) y lo
 * que hace cada orden, con lo que la app ya tiene (el reproductor, la música, el catálogo).
 */
class Control(private val e: Estado, private val nombre: String, private val version: Long) {
    private var trabajo: Job? = null
    private var revisada = ""   // a qué computadora ya se le preguntó si tiene una versión nueva de la app

    fun empezar() {
        if (trabajo?.isActive == true) return
        trabajo = e.scope.launch {
            while (isActive) {
                val base = e.api.base
                if (e.conexion != Conexion.LISTA || base.isBlank()) {
                    delay(1000)
                    continue
                }
                if (revisada != base) {
                    revisada = base
                    revisarVersion()
                }
                val ordenes = try {
                    val q = "device_id=" + enc(e.deviceId) + "&nombre=" + enc(nombre)
                    leerOrdenes(e.api.get("/api/tv/ordenes?$q", 35_000))
                } catch (ex: CancellationException) {
                    throw ex
                } catch (_: Exception) {
                    delay(3000)   // sin conexión por ahora: se vuelve a intentar sola
                    continue
                }
                for (o in ordenes) {
                    try {
                        ejecutar(o)
                    } catch (_: Exception) {
                    }
                }
            }
        }
    }

    /** La app se fue al fondo o se cerró: se deja de preguntar y se avisa, para que la web ya no la ofrezca. */
    fun parar() {
        trabajo?.cancel()
        trabajo = null
        revisada = ""   // al volver a la app se pregunta otra vez por una versión nueva (quizá el aviso no se vio)
        if (e.api.base.isBlank()) return
        e.scope.launch {
            try {
                e.api.post("/api/tv/adios", JSONObject().put("device_id", e.deviceId), 3000)
            } catch (_: Exception) {
            }
        }
    }

    /** Se pasó a otra computadora: adiós a la anterior (ya no ofrece esta TV) y las órdenes, desde la nueva. */
    fun reiniciar(anterior: String) {
        val seguia = trabajo != null
        trabajo?.cancel()
        trabajo = null
        revisada = ""
        if (anterior.isNotBlank()) e.scope.launch {
            try {
                e.api.post("$anterior/api/tv/adios", JSONObject().put("device_id", e.deviceId), 3000)
            } catch (_: Exception) {
            }
        }
        if (seguia) empezar()
    }

    fun ejecutar(o: Orden) {
        val r = e.reproductor
        when (o) {
            is Orden.Ver -> ver(o)
            is Orden.Actualiza -> e.cargarBiblioteca()   // también vuelve a leer lo de YouTube
            is Orden.Boton -> when (o.nombre) {
                "Play" -> pausaOSigue()
                "Back", "Home" -> salir()
                else -> teclaDeOrden(o.nombre)?.let { e.tecla(it) }
            }
            is Orden.IrA -> irA(o.segundos)
            is Orden.Pistas -> pistas(o)
            is Orden.Cancion -> if (r.visible && r.req?.music == true) e.pasoMusica(o.dir)
            is Orden.Codigo -> e.mostrarCodigo(o.codigo)
        }
    }

    private fun ver(o: Orden.Ver) {
        val id = o.contentId
        if (e.lib == null) {   // todavía cargando el catálogo: se reproduce en cuanto llegue
            e.pendiente = id
            return
        }
        e.ficha = null
        e.lista = null
        e.menuAbierto = false
        when {
            id.startsWith("music:") -> escucharSesion(id.removePrefix("music:"))
            id.startsWith("yt:") -> e.verYouTube(id.removePrefix("yt:"), o.start ?: -1.0)
            id.startsWith("live:") -> enVivo(id.removePrefix("live:"))
            id.startsWith("mosaic:") -> e.mostrarAviso("«Varios a la vez» todavía no funciona en esta TV.", true)
            e.lib?.items?.containsKey(id) == true -> e.empezarItem(id, true, o.audio, o.sub, o.start)
            else -> {   // algo recién agregado a la biblioteca: se vuelve a leer y se reproduce
                e.pendiente = id
                e.cargarBiblioteca()
            }
        }
    }

    private fun escucharSesion(sid: String) {
        e.scope.launch {
            val s = try {
                leerSesionMusica(e.api.get("/api/music/session?id=" + enc(sid), 15_000))
            } catch (ex: CancellationException) {
                throw ex
            } catch (_: Exception) {
                null
            }
            if (s == null) e.mostrarAviso("No se pudo abrir esa música. Prueba otra vez desde la computadora.", true)
            else e.escucharEn(s.canciones, s.index, s.start)
        }
    }

    /** Un canal de «En vivo» (como playLive del Roku), con su nombre: la sección En vivo lo hace (YouTube.kt). */
    private fun enVivo(cid: String) = e.verEnVivo(cid)

    private fun pausaOSigue() {
        val r = e.reproductor
        val p = r.player ?: return
        if (!r.visible || r.siguiente != null) return
        p.playWhenReady = !p.playWhenReady
        r.pausado = !p.playWhenReady
        if (r.capa == Capa.NADA) r.mostrarBarra()
        r.reportar("tick")   // la barra «En la TV» de la web lo ve ya, sin esperar el siguiente aviso
    }

    private fun salir() {
        e.lista = null
        val r = e.reproductor
        if (r.visible) r.detener(conReporte = true)
    }

    private fun irA(segundos: Double) {
        val r = e.reproductor
        val p = r.player ?: return
        if (!r.visible || r.req?.live == true) return
        var t = segundos.coerceAtLeast(0.0)
        if (r.duracion > 2 && t > r.duracion - 2) t = r.duracion - 2
        p.seekTo((t * 1000).toLong())
        r.posicion = t
        if (r.capa == Capa.NADA) r.mostrarBarra()
        r.reportar("tick")
    }

    private fun pistas(o: Orden.Pistas) {
        val r = e.reproductor
        val c = e.cur ?: return
        val it = c.item ?: return
        if (!r.visible || r.req?.id != c.id) return
        o.audio?.let { a -> if (a in it.audio.indices) c.audio = a }
        o.sub?.let { s -> c.sub = if (s in it.subs.indices) s else -1 }
        e.lista = null
        r.cambiarPistas(c)
    }

    /** Cada vez que se abre la app (o se vuelve a ella): si la computadora ofrece una versión más nueva, se avisa
     *  cómo actualizar. */
    private fun revisarVersion() {
        e.scope.launch {
            try {
                val o = e.api.get("/api/tv/app", 8000)
                if (!hayVersionNueva(version, o)) return@launch
                var espera = 0
                while (e.lib == null && espera++ < 60) delay(500)   // después de «Conectando con la computadora…»
                val texto = textoVersionNueva(o.optString("version"), e.direccion + "/tv")
                e.mostrarAviso(texto, false, auto = false)
                delay(20_000)
                if (e.aviso == texto) e.ocultarAviso()
            } catch (ex: CancellationException) {
                throw ex
            } catch (_: Exception) {
            }
        }
    }

    private fun enc(s: String) = URLEncoder.encode(s, "UTF-8")
}
