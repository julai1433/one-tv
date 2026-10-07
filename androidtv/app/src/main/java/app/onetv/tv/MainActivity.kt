package app.onetv.tv

import android.content.Context
import android.net.ConnectivityManager
import android.net.LinkProperties
import android.net.Network
import android.os.Bundle
import android.view.KeyEvent
import android.view.ViewGroup
import android.widget.FrameLayout
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.remember
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.viewinterop.AndroidView
import androidx.lifecycle.lifecycleScope
import androidx.media3.common.util.UnstableApi
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.AspectRatioFrameLayout
import androidx.media3.ui.CaptionStyleCompat
import androidx.media3.ui.PlayerView
import app.onetv.tv.control.Control
import app.onetv.tv.control.nombreDeLaTv
import app.onetv.tv.control.versionPropia
import app.onetv.tv.ui.AppUI
import app.onetv.tv.ui.Fonts
import app.onetv.tv.ui.LocalFonts
import app.onetv.tv.ui.LocalScale
import app.onetv.tv.ui.Scale
import kotlinx.coroutines.launch
import java.net.Inet4Address
import java.net.NetworkInterface
import java.util.UUID

/**
 * La app de One TV en Google TV, Android TV y Fire TV. Una sola pantalla: todo lo que se ve lo dibuja Compose a partir
 * de [Estado], y todas las teclas del control llegan a [Estado.tecla] (como en el Roku).
 *
 * Para pruebas se le puede dar la dirección del servidor al abrirla (`--es servidor http://…`, como el «server» del Roku)
 * o el puerto donde buscarlo en la red (`--ei puerto 8797`). Como en el Roku, `--es contentId yt:<video>` o el id de una
 * película abre la app reproduciéndolo.
 */
@UnstableApi
class MainActivity : ComponentActivity() {
    private lateinit var estado: Estado
    private lateinit var player: ExoPlayer
    private lateinit var control: Control   // la computadora maneja esta TV como al Roku (control/Ordenes.kt)
    private var red: ConnectivityManager.NetworkCallback? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val prefs = getSharedPreferences("onetv", Context.MODE_PRIVATE)
        val deviceId = prefs.getString("device_id", null) ?: ("androidtv-" + UUID.randomUUID().toString().take(12)).also {
            prefs.edit().putString("device_id", it).apply()
        }
        estado = Estado(lifecycleScope, prefs, deviceId, ::direccionesPropias) { finish() }
        intent?.getStringExtra("servidor")?.takeIf { it.isNotBlank() }?.let { estado.fijada = it.trimEnd('/') }
        intent?.getIntExtra("puerto", 0)?.takeIf { it > 0 }?.let { estado.puertoBusqueda = it }
        intent?.getStringExtra("contentId")?.takeIf { it.isNotBlank() }?.let { estado.pendiente = it }
        control = Control(estado, nombreDeLaTv(this), versionPropia(this))
        player = ExoPlayer.Builder(this).build()
        estado.reproductor.player = player
        val fonts = Fonts(assets)

        setContent {
            val conf = LocalConfiguration.current
            val density = LocalDensity.current
            val scale = remember(conf.screenWidthDp, density.fontScale) { Scale(conf.screenWidthDp / 1920f, density.fontScale) }
            CompositionLocalProvider(LocalScale provides scale, LocalFonts provides fonts) {
                AppUI(estado) {
                    AndroidView(factory = { ctx ->
                        PlayerView(ctx).apply {
                            layoutParams = FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT)
                            useController = false
                            resizeMode = AspectRatioFrameLayout.RESIZE_MODE_FIT
                            setShutterBackgroundColor(android.graphics.Color.BLACK)
                            setKeepContentOnPlayerReset(false)
                            subtitleView?.setStyle(CaptionStyleCompat(
                                android.graphics.Color.WHITE, android.graphics.Color.TRANSPARENT, android.graphics.Color.TRANSPARENT,
                                CaptionStyleCompat.EDGE_TYPE_OUTLINE, android.graphics.Color.BLACK, null,
                            ))
                            this.player = this@MainActivity.player
                            isFocusable = false
                        }
                    })
                }
            }
        }
        estado.arrancar()
        vigilarRed()
    }

    /** Con la app abierta llega otra orden de ver algo («contentId», como las del Roku). */
    override fun onNewIntent(intent: android.content.Intent) {
        super.onNewIntent(intent)
        intent.getStringExtra("contentId")?.takeIf { it.isNotBlank() }?.let { estado.abrirContenido(it) }
    }

    /** Todas las teclas del control pasan por aquí: la app decide qué hace cada una, como en el Roku. */
    override fun dispatchKeyEvent(event: KeyEvent): Boolean {
        val t = teclaDe(event.keyCode)
        if (t == Tecla.OK && estado.conexion == Conexion.LISTA) return teclaOk(event)
        if (t != null) {
            if (event.action == KeyEvent.ACTION_DOWN) {
                if (estado.tecla(t)) return true
            } else if (event.action == KeyEvent.ACTION_UP && estado.conexion != Conexion.ESCRIBIR) {
                return true
            }
        }
        return super.dispatchKeyEvent(event)
    }

    private var okAbajo = false
    private var okLargo = false

    /**
     * OK. Donde hay opciones (tarjetas, la ficha), mantenerlo apretado es la tecla ✱ del Roku (el control de Android TV
     * no la tiene; en Fire TV también sirve la tecla ☰): el OK normal se da al soltar. Sostenido no se repite.
     */
    private fun teclaOk(event: KeyEvent): Boolean {
        val sostenible = estado.okSostenidoSirve()
        when (event.action) {
            KeyEvent.ACTION_DOWN -> if (event.repeatCount == 0) {
                okAbajo = true
                okLargo = false
                if (!sostenible) {
                    okAbajo = false
                    if (!estado.tecla(Tecla.OK)) return super.dispatchKeyEvent(event)
                }
            } else if (okAbajo && !okLargo && (event.isLongPress || event.repeatCount >= 1)) {
                okLargo = true
                estado.tecla(Tecla.OPCIONES)
            }
            KeyEvent.ACTION_UP -> {
                if (okAbajo && !okLargo) estado.tecla(Tecla.OK)
                okAbajo = false
                okLargo = false
            }
        }
        return true
    }

    /** Al cambiar de red (otro Wi-Fi, se reconectó), si no hay servidor se vuelve a buscar solo. */
    private fun vigilarRed() {
        val cm = getSystemService(ConnectivityManager::class.java) ?: return
        val cb = object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) {
                lifecycleScope.launch { estado.redCambio() }
            }

            override fun onLinkPropertiesChanged(network: Network, linkProperties: LinkProperties) {
                lifecycleScope.launch { estado.redCambio() }
            }
        }
        try {
            cm.registerDefaultNetworkCallback(cb)
            red = cb
        } catch (_: Exception) {
        }
    }

    /** Las direcciones IPv4 de la TV en la red de la casa (para buscar la computadora en la misma red). */
    private fun direccionesPropias(): List<String> = try {
        NetworkInterface.getNetworkInterfaces().toList().filter { it.isUp && !it.isLoopback }
            .flatMap { it.inetAddresses.toList() }.filterIsInstance<Inet4Address>()
            .filter { it.isSiteLocalAddress }.mapNotNull { it.hostAddress }
    } catch (_: Exception) {
        emptyList()
    }

    override fun onStart() {
        super.onStart()
        control.empezar()   // mientras se ve la app, la computadora le puede mandar órdenes
    }

    override fun onStop() {
        super.onStop()
        control.parar()
        // Se salió de la app (botón de inicio): se guarda dónde quedó y se detiene, como al salir con Atrás.
        if (estado.reproductor.visible) estado.reproductor.detener(conReporte = true)
    }

    override fun onDestroy() {
        super.onDestroy()
        red?.let { cb -> getSystemService(ConnectivityManager::class.java)?.unregisterNetworkCallback(cb) }
        player.release()
    }
}
