package app.onetv.tv.ui

import android.content.res.AssetManager
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.util.LruCache
import androidx.compose.foundation.Image
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ColorFilter
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.net.HttpURLConnection
import java.net.URL

/**
 * Pósters, miniaturas y portadas desde el servidor, con una memoria pequeña para no volver a bajarlos. Sin bibliotecas
 * aparte: se bajan con lo que trae Android y se achican al tamaño en que se dibujan.
 */
object Imagenes {
    private val cache = object : LruCache<String, ImageBitmap>(48 * 1024 * 1024) {
        override fun sizeOf(key: String, value: ImageBitmap) = value.width * value.height * 4
    }
    @OptIn(kotlinx.coroutines.ExperimentalCoroutinesApi::class)
    private val io = Dispatchers.IO.limitedParallelism(6)

    fun enMemoria(url: String) = cache.get(url)

    suspend fun cargar(url: String, maxLado: Int): ImageBitmap? {
        cache.get(url)?.let { return it }
        return withContext(io) {
            cache.get(url) ?: try {
                val c = URL(url).openConnection() as HttpURLConnection
                c.connectTimeout = 8000
                c.readTimeout = 15000
                val bytes = try {
                    if (c.responseCode !in 200..299) null else c.inputStream.use { it.readBytes() }
                } finally {
                    c.disconnect()
                }
                bytes?.let { decode(it, maxLado) }?.asImageBitmap()?.also { cache.put(url, it) }
            } catch (_: Exception) {
                null
            }
        }
    }

    private fun decode(bytes: ByteArray, maxLado: Int): Bitmap? {
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeByteArray(bytes, 0, bytes.size, bounds)
        var sample = 1
        while (bounds.outWidth / (sample * 2) >= maxLado && bounds.outHeight / (sample * 2) >= maxLado) sample *= 2
        return BitmapFactory.decodeByteArray(bytes, 0, bytes.size, BitmapFactory.Options().apply { inSampleSize = sample })
    }

    // ---------- íconos de la app (los de roku/images/icons, blancos: se tiñen) ----------
    private val iconos = HashMap<String, ImageBitmap?>()

    fun icono(assets: AssetManager, nombre: String): ImageBitmap? = synchronized(iconos) {
        iconos.getOrPut(nombre) {
            try {
                assets.open("$nombre.png").use { BitmapFactory.decodeStream(it) }?.asImageBitmap()
            } catch (_: Exception) {
                null
            }
        }
    }
}

/** Una imagen del servidor; mientras llega (o si no hay) no se dibuja nada y se ve lo de abajo. */
@Composable
fun ImagenRed(url: String?, modifier: Modifier = Modifier, maxLado: Int = 480, scale: ContentScale = ContentScale.Crop) {
    if (url.isNullOrEmpty()) return
    val bmp by produceState(Imagenes.enMemoria(url), url) { if (value == null) value = Imagenes.cargar(url, maxLado) }
    bmp?.let { Image(it, contentDescription = null, modifier = modifier, contentScale = scale) }
}

/** Un ícono (Lucide, trazo 2) teñido del color que se pida. */
@Composable
fun Icono(nombre: String, color: Color, modifier: Modifier = Modifier) {
    val assets = LocalContext.current.assets
    val bmp = remember(nombre) { Imagenes.icono(assets, nombre) } ?: return
    Image(bmp, contentDescription = null, modifier = modifier, colorFilter = ColorFilter.tint(color))
}

/** Una imagen fija de la app (la marca de One TV, la de YouTube), sin teñir. */
@Composable
fun ImagenApp(nombre: String, modifier: Modifier = Modifier) {
    val assets = LocalContext.current.assets
    val bmp = remember(nombre) { Imagenes.icono(assets, nombre) } ?: return
    Image(bmp, contentDescription = null, modifier = modifier)
}
