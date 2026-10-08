package app.onetv.tv

import android.content.SharedPreferences
import android.view.KeyEvent
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import app.onetv.tv.data.Entry
import app.onetv.tv.data.Item
import app.onetv.tv.data.Library
import app.onetv.tv.data.Music
import app.onetv.tv.data.YtHome
import app.onetv.tv.data.audioPref
import app.onetv.tv.data.bareTitle
import app.onetv.tv.data.chooseAudio
import app.onetv.tv.data.chooseSub
import app.onetv.tv.data.countText
import app.onetv.tv.data.fmtClock
import app.onetv.tv.data.fmtDuration
import app.onetv.tv.data.parseChannels
import app.onetv.tv.data.parseLibrary
import app.onetv.tv.data.parseYtHome
import app.onetv.tv.data.publishedText
import app.onetv.tv.data.spokenText
import app.onetv.tv.data.viewersText
import app.onetv.tv.data.trackName
import app.onetv.tv.data.yearOf
import app.onetv.tv.net.Busqueda
import app.onetv.tv.net.Encontrada
import app.onetv.tv.net.Servidor
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import org.json.JSONObject

/** Las teclas del control, con los nombres del Roku. */
enum class Tecla { ARRIBA, ABAJO, IZQ, DER, OK, ATRAS, PLAY, ADELANTAR, ATRASAR, REPETIR, OPCIONES }

fun teclaDe(code: Int): Tecla? = when (code) {
    KeyEvent.KEYCODE_DPAD_UP -> Tecla.ARRIBA
    KeyEvent.KEYCODE_DPAD_DOWN -> Tecla.ABAJO
    KeyEvent.KEYCODE_DPAD_LEFT -> Tecla.IZQ
    KeyEvent.KEYCODE_DPAD_RIGHT -> Tecla.DER
    KeyEvent.KEYCODE_DPAD_CENTER, KeyEvent.KEYCODE_ENTER, KeyEvent.KEYCODE_NUMPAD_ENTER, KeyEvent.KEYCODE_BUTTON_A -> Tecla.OK
    KeyEvent.KEYCODE_BACK, KeyEvent.KEYCODE_ESCAPE, KeyEvent.KEYCODE_BUTTON_B -> Tecla.ATRAS
    KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE, KeyEvent.KEYCODE_MEDIA_PLAY, KeyEvent.KEYCODE_MEDIA_PAUSE, KeyEvent.KEYCODE_SPACE -> Tecla.PLAY
    KeyEvent.KEYCODE_MEDIA_FAST_FORWARD, KeyEvent.KEYCODE_MEDIA_SKIP_FORWARD -> Tecla.ADELANTAR
    KeyEvent.KEYCODE_MEDIA_REWIND, KeyEvent.KEYCODE_MEDIA_SKIP_BACKWARD -> Tecla.ATRASAR
    KeyEvent.KEYCODE_MEDIA_PREVIOUS -> Tecla.REPETIR
    KeyEvent.KEYCODE_MENU, KeyEvent.KEYCODE_INFO -> Tecla.OPCIONES
    else -> null
}

/** BUSCANDO y NO_ENCONTRADA: al abrir. ELEGIR: hay más de una computadora con One TV (o se pidió «Cambiar»).
 *  ESCRIBIR: la dirección a mano. LISTA: conectada. */
enum class Conexion { BUSCANDO, NO_ENCONTRADA, ESCRIBIR, ELEGIR, LISTA }

/** La ficha de una película, un episodio o un video de YouTube (DetailView del Roku). */
data class Ficha(
    val kind: String,          // item | yt
    val id: String,            // id de la biblioteca, o el de YouTube
    val title: String,
    val subtitle: String,
    val meta: String,
    val spanish: Boolean,
    val langs: String,
    val image: String?,
    val buttons: List<Boton>,
    val tech: String = "",          // detalles técnicos (solo en la sinopsis completa)
)

/** Un renglón de una lista para elegir (Audio y subtítulos, las opciones de una tarjeta…): título, línea de apoyo, ícono
 *  y qué hace. Desactivado: en gris y el foco lo salta. */
data class Opcion(val title: String, val line: String, val icon: String, val accion: String, val disabled: Boolean = false)

/**
 * La lista a la derecha de la pantalla (MultiPicker del Roku). ctx dice qué se hace al elegir: «pistas» (audio y
 * subtítulos del reproductor), «tarjeta» (OK sostenido sobre una tarjeta), «fila» (un video de la fila), «listas»
 * (agregar a una lista) o «listq» (una lista entera a la fila).
 */
data class Lista(
    val title: String,
    val note: String,
    val opciones: List<Opcion>,
    val vacio: Vacio,
    val ctx: String = "pistas",
    val hint: String = "OK: elegir   ·   ‹ o Atrás: cerrar",
)

/** El panel «Idioma» de la ficha: audio a la izquierda y subtítulos a la derecha (como en el Roku). */
data class PanelIdioma(val col: Int = 0, val audio: Int = 0, val subs: Int = 0, val buscar: Boolean = false)

/** Lo que se ve o se escucha ahora: la pista elegida y el contexto (para el siguiente). */
data class Actual(
    val id: String,
    val item: Item? = null,
    var audio: Int = 0,
    var sub: Int = -1,
    val yt: Boolean = false,
    val music: Boolean = false,
)

/**
 * Todo el estado de la app y lo que hace cada tecla, como MainScene.brs del Roku. Las pantallas (Compose) solo dibujan
 * este estado; las teclas llegan todas aquí (MainActivity.dispatchKeyEvent), así se manejan igual que en el Roku.
 */
class Estado(
    val scope: CoroutineScope,
    private val prefs: SharedPreferences,
    val deviceId: String,
    private val direccionesPropias: () -> List<String>,
    val salir: () -> Unit,
) {
    val api = Servidor("")
    var conexion by mutableStateOf(Conexion.BUSCANDO)
    var direccion by mutableStateOf("")
    var nombreServidor by mutableStateOf("")   // el nombre de la computadora conectada («MacBook de Ana»)
    var puertosBusqueda = listOf(Busqueda.PUERTO)
    var fijada: String? = null          // dirección dada al abrir la app (no se busca otra)

    // Elegir la computadora (Computadoras.kt): las encontradas, cuál tiene el foco y si se está buscando.
    var encontradas by mutableStateOf<List<Encontrada>>(emptyList())
    var elegirIndex by mutableStateOf(0)
    var buscandoTodas by mutableStateOf(false)
    var notaElegir by mutableStateOf("")   // por qué se pregunta (vacío: el texto de siempre)
    internal var escribirDesde = Conexion.NO_ENCONTRADA   // a dónde vuelve Atrás desde «Escribir la dirección»
    /** Se pasó a otra computadora: MainActivity suelta la consulta de órdenes de la anterior (le dice adiós). */
    var cambioDeComputadora: (anterior: String) -> Unit = {}

    var lib by mutableStateOf<Library?>(null)
    var ytHome by mutableStateOf<YtHome?>(null)
    var channels by mutableStateOf<List<app.onetv.tv.data.Channel>?>(null)
    var music by mutableStateOf<Music?>(null)
    var musicError by mutableStateOf(false)
    val paginasMusica = mutableStateMapOf<String, app.onetv.tv.data.MusicPage>()   // "album:<id>" -> su página (Musica.kt)
    internal val canciones = HashMap<String, app.onetv.tv.data.Song>()             // id -> canción ya traída
    internal val pidiendoMusica = HashSet<String>()
    val ytProgress = mutableStateMapOf<String, Double>()
    val ytTitles = HashMap<String, Entry>()

    var sinServidor by mutableStateOf(false)    // se perdió la conexión: «No encuentro la computadora»
    var seccion by mutableStateOf(Seccion.INICIO)
    var menuAbierto by mutableStateOf(false)
    var menuIndex by mutableStateOf(0)
    val paginas = mutableStateListOf<Pagina>()
    val filtros = mutableStateMapOf<String, String>()

    // Dónde está el foco en cada vista: filas -> (fila, columna); cuadrícula -> índice (-1: los botones de arriba).
    val focoFilas = mutableStateMapOf<String, Pair<Int, Int>>()
    val focoCuadricula = mutableStateMapOf<String, Int>()
    val focoChip = mutableStateMapOf<String, Int>()

    var ficha by mutableStateOf<Ficha?>(null)
    var fichaBoton by mutableStateOf(0)
    var fichaDesc by mutableStateOf("")
    var fichaMensaje by mutableStateOf("")
    var fichaMensajeError by mutableStateOf(false)
    var lista by mutableStateOf<Lista?>(null)
    var listaIndex by mutableStateOf(0)
    private var listaDesdeReproductor = false
    var idioma by mutableStateOf<PanelIdioma?>(null)
    var sinopsis by mutableStateOf(false)      // la sinopsis completa encima de la ficha (OK sostenido)
    var sinopsisPaso by mutableStateOf(0)      // cuánto se bajó en ella
    var qr by mutableStateOf(false)            // «Compartir (código QR)»
    var fichaWhen by mutableStateOf("")        // YouTube: «Publicado el 12 sep 2023»
    var ayuda by mutableStateOf(false)         // «Cómo traer tu YouTube»

    // YouTube: canales silenciados, páginas de canal y de lista, y lo que se sabe de cada video.
    var hidden by mutableStateOf<List<app.onetv.tv.data.Silenciado>?>(null)
    var hiddenError by mutableStateOf(false)
    val paginaVideos = mutableStateMapOf<String, PaginaVideos>()
    val buscador = Buscador(this)
    internal val favs = HashMap<String, Boolean>()
    internal var vidLists: Pair<String, List<org.json.JSONObject>>? = null   // video -> sus listas (/api/lists?video=)
    internal var listsWant = ""
    internal var tileMenu: Map<String, String>? = null
    internal var queueMenuAt = -1
    internal var listQueueId = ""
    internal var seguirCanal = ""
    var listaNueva by mutableStateOf<String?>(null)   // «Lista nueva»: el nombre que se escribe (null: cerrado)
    var listaNuevaTeclado by mutableStateOf(0)        // cada vez que cambia, la pantalla abre el teclado

    var aviso by mutableStateOf("")
    var avisoError by mutableStateOf(false)
    private var avisoJob: Job? = null

    /** Lo que se pidió ver al abrir la app («contentId», como en el Roku): se reproduce en cuanto llega el catálogo. */
    var pendiente: String? = null

    var cur: Actual? = null
    val reproductor = Reproductor(this)

    private var musicCtx: Pair<List<app.onetv.tv.data.Song>, Int>? = null
    private var fallos = 0

    val datos by derivedStateOf {
        lib?.let { Datos(it, direccion, ytHome, music, musicError, filtros.toMap(), paginasMusica.toMap()) }
    }

    /** La vista que se ve ahora (la página de arriba o la sección). */
    val vista: Vista? by derivedStateOf {
        val d = datos ?: return@derivedStateOf null
        when (val p = paginas.lastOrNull()) {
            is Pagina.Serie -> d.serie(p.key)
            is Pagina.MusicaPagina -> d.musicaPagina(p)
            is Pagina.Canal -> d.canal(p, paginaVideos["canal:" + p.id], ytProgress)
            is Pagina.ListaYt -> d.listaYt(p, paginaVideos["lista:" + p.id], ytProgress)
            Pagina.BuscarYt -> VistaBuscar("buscar-yt", "Buscar en YouTube", true)
            Pagina.Silenciados -> d.silenciados(hidden, hiddenError)
            null -> when (seccion) {
                Seccion.BUSCAR -> VistaBuscar("buscar", "Buscar", false)
                Seccion.INICIO -> d.inicio(ytProgress)
                Seccion.ESPANOL -> d.espanol()
                Seccion.PELICULAS -> d.peliculas()
                Seccion.SERIES -> d.series()
                Seccion.YOUTUBE -> d.youtube(channels, ytProgress)
                Seccion.MUSICA -> d.musica()
                Seccion.EN_VIVO -> d.enVivo()
                Seccion.FILA -> d.fila(hidden, nombreServidor)
            }
        }
    }

    init {
        for (k in listOf("movies", "series")) prefs.getString("filtro_$k", null)?.let { filtros[k] = it }
    }

    // ---------- conectarse ----------

    /** Al abrir: la dirección dada (pruebas), la recordada o, si no responde, se busca en toda la red. */
    fun arrancar() {
        val dada = fijada
        if (dada != null) {
            conectar(dada)
            return
        }
        buscar()
    }

    internal var busqueda: Job? = null

    /**
     * Al abrir (o si se perdió): la recordada, si responde. Si no, todas las de la red: la de siempre (mismo nombre,
     * quizá con otra dirección) o la única que hay; con varias y ninguna conocida, se pregunta cuál (Computadoras.kt).
     */
    fun buscar() {
        if (busqueda?.isActive == true) return
        conexion = if (lib == null) Conexion.BUSCANDO else conexion
        busqueda = scope.launch {
            val recordada = prefs.getString("servidor", null)
            if (recordada != null) leerComputadora(recordada, 1500)?.let {
                conectar(it)
                return@launch
            }
            val todas = Busqueda.buscarTodas(recordada, direccionesPropias(), puertosBusqueda) { leerComputadora(it) }
            val nombre = prefs.getString("servidor_nombre", null)
            val misma = Busqueda.laMisma(todas, nombre)
            when {
                misma != null -> conectar(misma)
                todas.isNotEmpty() && lib == null -> mostrarComputadoras(todas, if (nombre != null) notaNoEncuentro(nombre) else "")
                lib == null -> {
                    conexion = Conexion.NO_ENCONTRADA
                    delay(20_000)
                    if (conexion == Conexion.NO_ENCONTRADA) {
                        busqueda = null
                        buscar()   // se sigue buscando sola mientras la pantalla esté a la vista
                    }
                }
            }
        }
    }

    fun conectar(base: String) = conectar(Encontrada(base, "", 0))

    fun conectar(c: Encontrada) {
        direccion = c.direccion
        api.base = c.direccion
        if (c.nombre.isNotEmpty()) nombreServidor = c.nombre
        if (fijada == null) {
            val ed = prefs.edit().putString("servidor", c.direccion)
            if (c.nombre.isNotEmpty()) ed.putString("servidor_nombre", c.nombre)
            ed.apply()
        }
        conexion = Conexion.LISTA
        cargarBiblioteca()
        if (c.nombre.isEmpty()) scope.launch {   // sin su nombre (dirección dada al abrir): se pide, para Ajustes generales
            val leida = leerComputadora(c.direccion, 3000) ?: return@launch
            if (direccion != leida.direccion) return@launch
            nombreServidor = leida.nombre
            if (fijada == null) prefs.edit().putString("servidor_nombre", leida.nombre).apply()
        }
    }

    internal fun direccionesDeLaTv() = direccionesPropias()

    /** Se pasó a otra computadora: lo de la anterior ya no sirve (su catálogo, YouTube, música, páginas abiertas). */
    internal fun olvidarCatalogo() {
        reintento?.cancel()
        fijarAviso("")
        fallos = 0
        sinServidor = false
        lib = null
        ytHome = null
        channels = null
        music = null
        musicError = false
        ytProgress.clear()
        ytTitles.clear()
        paginaVideos.clear()
        favs.clear()
        vidLists = null
        hidden = null
        hiddenError = false
        ficha = null
        lista = null
        idioma = null
        sinopsis = false
        qr = false
        ayuda = false
        listaNueva = null
        cur = null
        musicCtx = null
        menuAbierto = false
        paginas.clear()
        focoFilas.clear()
        focoCuadricula.clear()
        focoChip.clear()
        seccion = Seccion.INICIO
    }

    /** /api/status de esa dirección -> la computadora (nombre y videos) o null, sin trabar la pantalla. */
    suspend fun leerComputadora(base: String, timeoutMs: Int = 700): Encontrada? =
        kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) { Servidor.estado(base, timeoutMs) }

    /** Una dirección escrita a mano (pantalla «Escribir la dirección»). */
    fun probarEscrita(texto: String, listo: (String?) -> Unit) {
        val base = Busqueda.normalizar(texto)
        if (base == null) {
            listo("Escribe la dirección que muestra la computadora, por ejemplo 192.0.2.5")
            return
        }
        scope.launch {
            val c = leerComputadora(base, 3000)
            if (c != null) {
                listo(null)
                usarComputadora(c)
            } else listo("No hay un One TV en $base. Revisa la dirección y que la computadora esté encendida.")
        }
    }

    /** Cambió la red (otro Wi-Fi, se reconectó): si no hay servidor, se busca otra vez (no mientras se elige o se
     *  escribe la dirección). */
    fun redCambio() {
        if (conexion == Conexion.BUSCANDO || conexion == Conexion.NO_ENCONTRADA || (conexion == Conexion.LISTA && sinServidor)) {
            busqueda?.cancel()
            busqueda = null
            buscar()
        }
    }

    // ---------- catálogo ----------

    private var reintento: Job? = null

    fun cargarBiblioteca() {
        if (lib == null && !sinServidor) mostrarAviso("Conectando con la computadora…", false, auto = false)
        scope.launch {
            try {
                val o = api.get("/api/library?device_id=$deviceId")
                val first = lib == null
                val l = parseLibrary(o)
                lib = l
                fallos = 0
                for (e in l.cont) if (e.kind == "yt") {
                    recordarYt(e)
                    if (e.p > 0) ytProgress[e.id] = e.p
                }
                for (e in l.youtube + l.queue + l.history) if (e.kind == "yt") recordarYt(e)
                if (sinServidor) sinServidor = false
                if (first) ocultarAviso()
                fijarAviso(if (l.items.isEmpty()) textoSinVideos(o.optJSONArray("sin_permiso")?.length() ?: 0) else "")
                cargarYouTube()
                if (first) cargarMusica()
                pendiente?.let {
                    pendiente = null
                    abrirContenido(it)
                }
            } catch (e: Exception) {
                fallos++
                fijarAviso("")   // «No hay videos» ya no es lo que pasa: no se encuentra la computadora
                if (lib == null) ocultarAviso()
                sinServidor = true
                reintento?.cancel()
                reintento = scope.launch {
                    delay(5000)
                    // La sigue buscando sola cada 5 segundos; si no responde varias veces, quizá cambió de dirección: se
                    // busca la misma computadora (por su nombre), nunca otra.
                    if (fallos >= 3 && fijada == null) {
                        val todas = Busqueda.buscarTodas(null, direccionesPropias(), puertosBusqueda) { leerComputadora(it) }
                        val found = Busqueda.laMisma(todas, nombreServidor.ifEmpty { prefs.getString("servidor_nombre", null) })
                        if (found != null && found.direccion != direccion) {
                            conectar(found)
                            return@launch
                        }
                    }
                    cargarBiblioteca()
                }
            }
        }
    }

    fun cargarYouTube() {
        scope.launch {
            try {
                val h = parseYtHome(api.get("/api/yt/home?device_id=$deviceId"))
                for (e in h.cont + h.new + h.recent + h.because + h.favorites) recordarYt(e)
                for (e in h.cont) if (e.p > 0) ytProgress[e.id] = e.p
                for (e in h.favorites) favs[e.id] = true
                ytHome = h
            } catch (_: Exception) {
            }
        }
        scope.launch {
            try {
                channels = parseChannels(api.get("/api/yt/subscriptions"))
            } catch (_: Exception) {
            }
        }
    }

    /** «yt:<video>» o el id de una película o episodio: se reproduce ya (ficha y menú cerrados). */
    fun abrirContenido(id: String) {
        if (lib == null) {
            pendiente = id
            return
        }
        ficha = null
        lista = null
        menuAbierto = false
        if (id.startsWith("yt:")) verYouTube(id.removePrefix("yt:"), -1.0)
        else if (lib?.items?.containsKey(id) == true) empezarItem(id, true)
    }

    // ---------- avisos breves ----------

    /** El aviso que se queda mientras siga siendo cierto («No hay videos todavía…»): vuelve al quitarse otro encima. */
    private var avisoFijo = ""

    fun mostrarAviso(text: String, error: Boolean = false, auto: Boolean = true) {
        aviso = text
        avisoError = error
        avisoJob?.cancel()
        if (auto) avisoJob = scope.launch {
            delay(4000)
            ocultarAviso()
        }
    }

    fun ocultarAviso() {
        avisoJob?.cancel()
        aviso = avisoFijo
        avisoError = false
    }

    private fun fijarAviso(text: String) {
        val antes = avisoFijo
        avisoFijo = text
        if (text.isNotEmpty()) mostrarAviso(text, false, auto = false) else if (aviso == antes) ocultarAviso()
    }

    // ---------- teclas ----------

    fun tecla(t: Tecla): Boolean {
        if (conexion != Conexion.LISTA) return teclaConexion(t)
        if (ayuda) {
            if (t == Tecla.ATRAS) ayuda = false
            return true
        }
        if (listaNueva != null) {   // «Lista nueva»: el campo y el teclado de la TV
            when (t) {
                Tecla.ATRAS -> listaNueva = null
                Tecla.OK -> listaNuevaTeclado++
                else -> {}
            }
            return true
        }
        lista?.let { return teclaLista(t, it) }
        if (reproductor.visible) return reproductor.tecla(t)
        ficha?.let { return teclaFicha(t, it) }
        if (sinServidor) {   // «No encuentro la computadora»: «Buscar ahora» o «Elegir otra computadora»
            when (t) {
                Tecla.IZQ, Tecla.DER -> conexionBoton = 1 - conexionBoton
                Tecla.OK -> if (conexionBoton == 0) {
                    mostrarAviso("Buscando la computadora…")
                    cargarBiblioteca()
                } else cambiarComputadora()
                Tecla.ATRAS -> salir()
                else -> {}
            }
            return true
        }
        if (menuAbierto) return teclaMenu(t)
        val v = vista ?: return t != Tecla.ATRAS || run { salir(); true }
        return when (v) {
            is VistaFilas -> teclaFilas(t, v)
            is VistaCuadricula -> teclaCuadricula(t, v)
            is VistaBuscar -> buscador.tecla(t, v)
        }
    }

    var conexionBoton by mutableStateOf(0)

    /** ¿Aquí OK sostenido abre opciones? (tarjetas y la ficha; en el reproductor, las listas y el menú, OK es inmediato). */
    fun okSostenidoSirve() = conexion == Conexion.LISTA && !reproductor.visible && lista == null && !ayuda && !menuAbierto && listaNueva == null &&
        !sinServidor && idioma == null && !qr

    private fun teclaConexion(t: Tecla): Boolean {
        when (conexion) {
            Conexion.NO_ENCONTRADA -> when (t) {
                Tecla.IZQ, Tecla.DER -> conexionBoton = 1 - conexionBoton
                Tecla.OK -> if (conexionBoton == 0) {
                    busqueda?.cancel()
                    busqueda = null
                    conexion = Conexion.BUSCANDO
                    buscar()
                } else {
                    escribirDesde = Conexion.NO_ENCONTRADA
                    conexion = Conexion.ESCRIBIR
                }
                Tecla.ATRAS -> salir()
                else -> {}
            }
            Conexion.ESCRIBIR -> {
                if (t == Tecla.ATRAS) {
                    conexion = escribirDesde
                    return true
                }
                return false   // el campo de texto y el teclado de la TV se encargan
            }
            Conexion.ELEGIR -> return teclaElegir(t)
            else -> if (t == Tecla.ATRAS) salir()
        }
        return true
    }

    private fun teclaMenu(t: Tecla): Boolean {
        val n = Seccion.entries.size
        when (t) {
            Tecla.ARRIBA -> if (menuIndex > 0) menuIndex--
            Tecla.ABAJO -> if (menuIndex < n - 1) menuIndex++
            Tecla.OK -> {
                menuAbierto = false
                abrirSeccion(Seccion.entries[menuIndex])
            }
            Tecla.DER -> menuAbierto = false
            Tecla.ATRAS -> if (seccion != Seccion.INICIO) {
                menuAbierto = false
                abrirSeccion(Seccion.INICIO)
            } else salir()   // Atrás en el menú, ya en Inicio: se sale de la app
            else -> {}
        }
        return true
    }

    fun abrirMenu() {
        menuIndex = seccion.ordinal
        menuAbierto = true
    }

    fun abrirSeccion(s: Seccion) {
        seccion = s
        paginas.clear()
        if (s == Seccion.INICIO || s == Seccion.YOUTUBE) cargarYouTube()
        if (s == Seccion.MUSICA && music == null) cargarMusica()
        if (s == Seccion.FILA) cargarSilenciados()   // cuántos canales silenciados hay (Ajustes generales)
        if (s == Seccion.BUSCAR) buscador.abrir(false)
    }

    fun abrirPagina(p: Pagina) {
        paginas.add(p)
        when (p) {
            is Pagina.Canal -> {
                focoCuadricula["canal:" + p.id] = 0
                cargarPagina("canal:" + p.id, "/api/yt/channel?id=" + p.id, p.title)
            }
            is Pagina.ListaYt -> {
                focoCuadricula["lista:" + p.id] = 0
                cargarPagina("lista:" + p.id, "/api/yt/playlist?id=" + p.id, p.title)
            }
            Pagina.Silenciados -> {
                focoCuadricula["silenciados"] = 0
                cargarSilenciados()
            }
            Pagina.BuscarYt -> buscador.abrir(true)
            else -> {}
        }
    }

    internal fun atrasEnVista() {
        if (paginas.isNotEmpty()) paginas.removeAt(paginas.size - 1) else abrirMenu()
    }

    private fun teclaFilas(t: Tecla, v: VistaFilas): Boolean {
        if (v.filas.isEmpty()) {
            if (t == Tecla.ATRAS || t == Tecla.IZQ) atrasEnVista()
            return true
        }
        val (r0, c0) = focoFilas[v.key] ?: (0 to 0)
        if (r0 < 0) {   // en el botón de arriba («Buscar en YouTube»)
            when (t) {
                Tecla.ABAJO -> focoFilas[v.key] = 0 to 0
                Tecla.OK -> abrirPagina(Pagina.BuscarYt)
                Tecla.IZQ -> abrirMenu()
                Tecla.ATRAS -> atrasEnVista()
                else -> {}
            }
            return true
        }
        val r = r0.coerceIn(0, v.filas.size - 1)
        val fila = v.filas[r]
        val n = if (fila.tarjetas.isEmpty()) 1 else fila.tarjetas.size
        val c = c0.coerceIn(0, n - 1)
        when (t) {
            Tecla.ARRIBA -> if (r > 0) focoFilas[v.key] = (r - 1) to colPara(v.filas[r - 1], c)
            else if (v.topButton.isNotEmpty()) focoFilas[v.key] = -1 to c
            Tecla.ABAJO -> if (r < v.filas.size - 1) focoFilas[v.key] = (r + 1) to colPara(v.filas[r + 1], c)
            Tecla.IZQ -> if (c > 0) focoFilas[v.key] = r to (c - 1) else abrirMenu()   // ← desde la primera columna
            Tecla.DER -> if (c < n - 1) focoFilas[v.key] = r to (c + 1)
            Tecla.OK, Tecla.PLAY -> {
                if (fila.tarjetas.isEmpty()) fila.vacio?.let { accionVacio(it.actionId) }
                else activar(fila.tarjetas[c].id, t == Tecla.PLAY)
            }
            Tecla.ATRAS -> atrasEnVista()
            Tecla.OPCIONES -> opcionesTarjeta(fila.tarjetas.getOrNull(c))
            else -> return false
        }
        musicaCercaDelFinal(v)   // Música: más artistas o álbumes al acercarse al final (Musica.kt)
        return true
    }

    /** OK sostenido (la tecla ✱ del Roku) sobre una tarjeta: sus opciones; si no tiene, se actualiza la biblioteca. */
    private fun opcionesTarjeta(t: Tarjeta?) {
        if (t != null && t.menu && abrirMenuTarjeta(t.id)) return
        mostrarAviso("Actualizando la biblioteca…")
        cargarBiblioteca()
    }

    private fun colPara(f: Fila, c: Int) = if (f.tarjetas.isEmpty()) 0 else c.coerceIn(0, f.tarjetas.size - 1)

    /** Columnas que caben entre el menú y el borde derecho (1752 de ancho), como en el Roku. */
    fun columnas(v: VistaCuadricula) = (1752 + v.forma.gap) / (v.forma.w + v.forma.gap)

    private fun teclaCuadricula(t: Tecla, v: VistaCuadricula): Boolean {
        val cols = columnas(v)
        val n = v.tarjetas.size
        val hasChips = v.chips.isNotEmpty()
        var i = focoCuadricula[v.key] ?: (if (n == 0 && hasChips) -1 else 0)
        if (i >= n) i = n - 1
        if (i < 0 && !hasChips) i = 0
        if (i == -1) {   // en los botones de arriba
            val chip = (focoChip[v.key] ?: v.chips.indexOfFirst { it.id == v.chipValue }).coerceIn(0, v.chips.size - 1)
            when (t) {
                Tecla.IZQ -> if (chip > 0) focoChip[v.key] = chip - 1 else abrirMenu()
                Tecla.DER -> if (chip < v.chips.size - 1) focoChip[v.key] = chip + 1
                Tecla.ABAJO -> if (n > 0) focoCuadricula[v.key] = 0
                Tecla.OK -> controlCuadricula(v, v.chips[chip].id)
                Tecla.ATRAS -> atrasEnVista()
                else -> return t != Tecla.ARRIBA || true
            }
            return true
        }
        if (n == 0) {
            when (t) {
                Tecla.OK -> accionVacio(v.vacio.actionId)
                Tecla.ARRIBA -> if (hasChips) focoCuadricula[v.key] = -1
                Tecla.IZQ, Tecla.ATRAS -> atrasEnVista()
                else -> {}
            }
            return true
        }
        when (t) {
            Tecla.ARRIBA -> if (i >= cols) focoCuadricula[v.key] = i - cols else if (hasChips) {
                focoChip[v.key] = v.chips.indexOfFirst { it.id == v.chipValue }.coerceAtLeast(0)
                focoCuadricula[v.key] = -1
            }
            Tecla.ABAJO -> if (i + cols < n) focoCuadricula[v.key] = i + cols else if (i / cols < (n - 1) / cols) focoCuadricula[v.key] = n - 1
            Tecla.IZQ -> if (i % cols > 0) focoCuadricula[v.key] = i - 1 else abrirMenu()
            Tecla.DER -> if (i % cols < cols - 1 && i < n - 1) focoCuadricula[v.key] = i + 1
            Tecla.OK, Tecla.PLAY -> activar(v.tarjetas[i].id, t == Tecla.PLAY)
            Tecla.ADELANTAR -> focoCuadricula[v.key] = (i + cols * 3).coerceAtMost(n - 1)
            Tecla.ATRASAR -> focoCuadricula[v.key] = (i - cols * 3).coerceAtLeast(0)
            Tecla.ATRAS -> atrasEnVista()
            Tecla.OPCIONES -> opcionesTarjeta(v.tarjetas.getOrNull(i))
            else -> return false
        }
        paginaMusicaCercaDelFinal(v)   // un álbum, artista o lista: las canciones que siguen (Musica.kt)
        return true
    }

    /** Filtros de Películas y Series (se recuerdan en esta TV) o los botones de una página de música. */
    private fun controlCuadricula(v: VistaCuadricula, id: String) {
        val p = paginas.lastOrNull()
        if (p is Pagina.Canal || p is Pagina.ListaYt) {
            controlPagina(p, id)
            return
        }
        if (p is Pagina.MusicaPagina) {
            if (id == "m-play") escucharColeccion(p.sub, p.id, 0, false) else aleatorioColeccion(p.sub, p.id)
            return
        }
        val name = if (v.key == "peliculas") "movies" else if (v.key == "series") "series" else return
        filtros[name] = id
        prefs.edit().putString("filtro_$name", id).apply()
        focoCuadricula[v.key] = -1
    }

    private fun accionVacio(name: String) {
        when (name) {
            "movies" -> abrirSeccion(Seccion.PELICULAS)
            "home" -> abrirSeccion(Seccion.INICIO)
            "youtube" -> abrirSeccion(Seccion.YOUTUBE)
            "ytsearch" -> abrirPagina(Pagina.BuscarYt)
            "takeout" -> ayuda = true
            "refresh" -> {
                mostrarAviso("Buscando otra vez…")
                cargarBiblioteca()
            }
            "filter-all" -> (vista as? VistaCuadricula)?.let { controlCuadricula(it, "all") }
            "rescan" -> {
                mostrarAviso("Buscando películas y series nuevas…")
                scope.launch {
                    try {
                        api.post("/api/rescan", JSONObject().put("device_id", deviceId))
                    } catch (_: Exception) {
                    }
                    cargarBiblioteca()
                }
            }
        }
    }

    // ---------- lo que se elige ----------

    /** OK (quick = false) o ▶ (quick = true) sobre una tarjeta. */
    fun activar(id: String, quick: Boolean) {
        val l = lib ?: return
        when {
            id.startsWith("song:") -> {
                val parts = id.split(":")
                val ctx = parts.getOrNull(1) ?: return
                val i = parts.getOrNull(2)?.toIntOrNull() ?: return
                val page = paginas.lastOrNull() as? Pagina.MusicaPagina
                if (ctx == "recent" || page == null) escucharCanciones(datos?.recientes().orEmpty(), i, false)
                else escucharColeccion(page.sub, page.id, i, false)   // si es enorme, siguen las de la computadora
            }
            id.startsWith("album:") || id.startsWith("mlist:") || id.startsWith("artist:") -> {
                val sub = when {
                    id.startsWith("album:") -> "album"
                    id.startsWith("mlist:") -> "list"
                    else -> "artist"
                }
                abrirMusica(sub, id.substringAfter(":"), tituloTarjeta(id), quick)   // Musica.kt
            }
            id.startsWith("yt:") -> if (quick) verYouTube(id.removePrefix("yt:"), -1.0) else fichaYouTube(id.removePrefix("yt:"))
            id.startsWith("serie:") -> {
                val key = id.removePrefix("serie:")
                if (quick) {
                    l.series.firstOrNull { it.key == key }?.let { show -> datos?.nextUp(show)?.first?.let { empezarItem(it, true) } }
                } else {
                    focoFilas["serie:$key"] = 0 to 0
                    paginas.add(Pagina.Serie(key))
                }
            }
            id.startsWith("q:") -> tomarDeLaFila(id.removePrefix("q:").toIntOrNull() ?: 0)
            id.startsWith("chan:") -> abrirPagina(Pagina.Canal(id.removePrefix("chan:"), tituloTarjeta(id)))
            id.startsWith("list:") -> if (quick) reproducirLista(id.removePrefix("list:"))
            else abrirPagina(Pagina.ListaYt(id.removePrefix("list:"), tituloTarjeta(id)))
            id.startsWith("live:") -> verEnVivo(id.removePrefix("live:"))
            id.startsWith("unhide:") -> if (!quick) volverAMostrar(id.removePrefix("unhide:"))   // ▶ no lo vuelve a mostrar
            id.startsWith("set:") -> ajuste(id.removePrefix("set:"))
            id == "ytmore" -> buscador.cargarMas()
            l.items.containsKey(id) -> empezarItem(id, quick)
        }
    }

    // ---------- ficha ----------

    /** OK sobre una película o episodio: la ficha. ▶: directo, con el idioma de esta TV. */
    fun empezarItem(id: String, autoplay: Boolean, audio: Int? = null, sub: Int? = null, start: Double? = null) {
        val l = lib ?: return
        val it = l.items[id] ?: return
        val a = audio?.takeIf { x -> x in it.audio.indices } ?: chooseAudio(it, l.prefs)
        val s = if (sub != null) (if (sub in it.subs.indices) sub else -1) else chooseSub(it, l.prefs)
        cur = Actual(id, it, a, s)
        if (autoplay) reproducirItem(start ?: (l.progress[id] ?: 0.0)) else abrirFichaItem(false)
    }

    fun abrirFichaItem(keepFocus: Boolean) {
        val c = cur ?: return
        val it = c.item ?: return
        val l = lib ?: return
        val title: String
        var subtitle = ""
        var meta = fmtDuration(it.duration)
        if (it.kind == "episode") {
            title = it.show
            subtitle = "T${it.season} ${it.ep}" + if (it.epTitle.isNotEmpty()) " · " + it.epTitle else ""
        } else {
            title = bareTitle(it.title)
            val year = yearOf(it.title)
            if (year.isNotEmpty()) meta = "$year   ·   $meta"
        }
        val buttons = mutableListOf<Boton>()
        val at = l.progress[c.id] ?: 0.0
        if (at > 0) {
            buttons += Boton("resume", "Continuar desde " + fmtClock(at), "play")
            buttons += Boton("start", "Desde el principio", "rotate-ccw")
        } else buttons += Boton("start", "Reproducir", "play")
        buttons += Boton("queue-next", "A continuación", "list-start")
        buttons += Boton("queue", "Al final de la fila", "list-plus")
        buttons += Boton("lang", langButtonText(it, c), "languages")
        ficha = Ficha("item", c.id, title, subtitle, meta, it.dub, spokenText(it), datos?.abs(it.poster), buttons, techText(it))
        if (!keepFocus) {
            fichaBoton = 0
            fichaMensaje = ""
            fichaWhen = ""
            cerrarEncimaDeFicha()
            cargarSinopsis(c.id, "/api/info?id=${c.id}")
        }
    }

    /** La sinopsis se pide aparte (el catálogo no trae textos largos): mientras llega, «Buscando la sinopsis…». */
    private fun cargarSinopsis(id: String, path: String, alLlegar: (JSONObject) -> Unit = {}) {
        fichaDesc = "Buscando la sinopsis…"
        scope.launch {
            val o = try {
                api.get(path, 30000)
            } catch (_: Exception) {
                null
            }
            if (ficha?.id != id) return@launch
            fichaDesc = o?.optString("desc", "").orEmpty().ifEmpty { "Sin sinopsis todavía." }
            if (o != null) alLlegar(o)
        }
    }

    private fun cerrarEncimaDeFicha() {
        idioma = null
        sinopsis = false
        qr = false
    }

    /** Lo técnico, aparte (solo en la sinopsis completa). */
    private fun techText(it: Item): String {
        val lines = mutableListOf<String>()
        lines += when {
            it.mode == "copy" -> "Video original; la computadora solo convierte el audio (${it.convertReason})."
            it.direct == null -> "La computadora convierte el video mientras se ve (${it.convertReason})."
            else -> "Se reproduce directo, sin convertir."
        }
        for (t in it.audio) {
            var line = "Audio: " + trackName(t)
            val tech = t.label.substringAfter(" · ", "")
            if (tech.isNotEmpty()) line += " — $tech"
            if (t.ext) line += " (pista aparte, llega por la computadora)"
            lines += line
        }
        for (sub in it.subs) lines += "Subtítulos: " + trackName(sub)
        return lines.joinToString("\n")
    }

    private fun langButtonText(it: Item, c: Actual): String {
        var text = "Idioma"
        if (c.audio in it.audio.indices) text += ": " + trackName(it.audio[c.audio])
        if (c.sub >= 0) text += " + subtítulos"
        return text
    }

    /** La ficha de un video. keepFocus: solo se rehacen los textos y botones (Favorito cambió, se supo que es en vivo)
     *  sin mover el foco ni cerrar lo que esté abierto encima. */
    fun fichaYouTube(vid: String, keepFocus: Boolean = false) {
        val e = ytTitles[vid]
        if (!keepFocus) cur = Actual("yt:$vid", yt = true)
        val live = e?.live == true
        val meta = mutableListOf<String>()
        if (live) meta += "EN VIVO"
        e?.channel?.takeIf { it.isNotEmpty() }?.let { meta += it }
        if (live) viewersText(e?.viewers ?: 0).takeIf { it.isNotEmpty() }?.let { meta += it }
        if (!live) e?.duration?.takeIf { it > 0 }?.let { meta += fmtClock(it) }
        val p = ytProgress[vid] ?: 0.0
        val buttons = mutableListOf<Boton>()
        val fav = favs[vid] == true
        val favBtn = if (fav) Boton("yt-fav", "En Favoritos", "heart-filled") else Boton("yt-fav", "Favorito", "heart")
        if (live) {
            // Una transmisión en vivo no termina ni se retoma: no va a la fila; su canal puede ir a «En vivo».
            buttons += Boton("yt-play", "Ver en vivo", "play")
            if (e?.channelId?.isNotEmpty() == true) buttons += Boton("yt-addlive", "Agregar a En vivo", "radio")
            buttons += favBtn
            buttons += Boton("yt-lists", "Agregar a lista", "bookmark-plus")
            buttons += Boton("share", "Compartir (código QR)", "qr-code")
            buttons += Boton("yt-mute", "Silenciar canal", "eye-off", danger = true)
        } else {
            if (p > 30) {
                buttons += Boton("yt-resume", "Continuar desde " + fmtClock(p), "play")
                buttons += Boton("yt-play", "Desde el principio", "rotate-ccw")
            } else buttons += Boton("yt-play", "Reproducir ahora", "play")
            buttons += Boton("yt-next", "A continuación", "list-start")
            buttons += Boton("yt-queue", "Al final de la fila", "list-plus")
            buttons += favBtn
            buttons += Boton("yt-lists", "Agregar a lista", "bookmark-plus")
            buttons += Boton("share", "Compartir (código QR)", "qr-code")
            buttons += Boton("yt-dismiss", "No me interesa", "ban")
            buttons += Boton("yt-mute", "Silenciar canal", "eye-off", danger = true)
        }
        ficha = Ficha("yt", vid, e?.title?.ifEmpty { null } ?: "YouTube", "", meta.joinToString("   ·   "), false, "",
            datos?.abs("/yt/$vid/thumb-hd.jpg"), buttons)
        if (keepFocus) {
            fichaBoton = fichaBoton.coerceAtMost(buttons.size - 1)
            return
        }
        fichaBoton = 0
        fichaMensaje = ""
        fichaWhen = if (!live && e != null) publishedText(e.published, e.approx) else ""
        cerrarEncimaDeFicha()
        cargarListasDelVideo(vid)   // Favorito y «Agregar a lista»
        cargarSinopsis(vid, "/api/yt/info?id=$vid") { o ->
            // La ficha sabe por la computadora si es una transmisión en vivo (cambian los botones) y de qué canal.
            val known = ytTitles[vid] ?: Entry("yt", vid, title = o.optString("title", ""))
            val isLive = o.optBoolean("live", false)
            val chan = o.optString("channel_id", "")
            val learned = known.copy(live = isLive, viewers = o.optInt("viewers", known.viewers),
                channelId = chan.ifEmpty { known.channelId }, channel = known.channel.ifEmpty { o.optString("channel", "") },
                duration = if (known.duration > 0) known.duration else o.optDouble("duration", 0.0))
            ytTitles[vid] = learned
            val published = o.optLong("published", 0)
            if (published > 0 && !isLive) fichaWhen = publishedText(published, o.optBoolean("published_approx", false))
            if (learned != known) fichaYouTube(vid, true)
        }
    }

    private fun teclaFicha(t: Tecla, f: Ficha): Boolean {
        if (qr) {   // solo Atrás: el mismo OK que eligió «Compartir» no la cierra
            if (t == Tecla.ATRAS) qr = false
            return true
        }
        if (sinopsis) {
            when (t) {
                Tecla.ATRAS, Tecla.OPCIONES -> sinopsis = false
                Tecla.ABAJO -> sinopsisPaso++
                Tecla.ARRIBA -> if (sinopsisPaso > 0) sinopsisPaso--
                else -> {}
            }
            return true
        }
        idioma?.let {
            teclaIdioma(t, it)
            return true
        }
        when (t) {
            Tecla.IZQ -> if (fichaBoton > 0) fichaBoton--
            Tecla.DER -> if (fichaBoton < f.buttons.size - 1) fichaBoton++
            Tecla.OK -> botonFicha(f, f.buttons[fichaBoton].id)
            Tecla.PLAY -> botonFicha(f, f.buttons[0].id)
            Tecla.OPCIONES -> {
                sinopsisPaso = 0
                sinopsis = true
            }
            Tecla.ATRAS -> ficha = null
            else -> {}
        }
        return true
    }

    private fun botonFicha(f: Ficha, id: String) {
        val l = lib ?: return
        when (id) {
            "resume" -> reproducirItem(l.progress[f.id] ?: 0.0)
            "start" -> reproducirItem(0.0)
            "yt-play" -> verYouTube(f.id, 0.0)
            "yt-resume" -> verYouTube(f.id, -1.0)
            "queue", "queue-next" -> alaFila("item", f.id, "", id == "queue-next")
            "yt-queue", "yt-next" -> alaFila("yt", f.id, f.title, id == "yt-next")
            "lang" -> abrirIdioma()
            "share" -> qr = true
            "yt-fav" -> pulsarFavorito(f.id)
            "yt-lists" -> agregarALista(f.id)
            "yt-dismiss" -> noMeInteresa(f.id, desdeFicha = true)
            "yt-mute" -> silenciarDesdeVideo(f.id, desdeFicha = true)
            "yt-addlive" -> agregarAEnVivo(f.id)
        }
    }

    /** Mensaje bajo los botones de la ficha: en limón, o en guinda claro si es un problema. */
    fun mensajeFicha(text: String, error: Boolean = false) {
        fichaMensaje = text
        fichaMensajeError = error
    }

    internal fun alaFila(kind: String, id: String, title: String, front: Boolean) {
        scope.launch {
            try {
                val r = api.post("/api/queue/add", JSONObject().put("kind", kind).put("id", id).put("title", title).put("front", front).put("device_id", deviceId))
                if (r.optBoolean("ok")) {
                    fichaMensaje = "Listo: en la fila de reproducción (" + countText(r.optInt("count"), "en espera", "en espera") + ")."
                    fichaMensajeError = false
                    cargarBiblioteca()
                } else {
                    fichaMensaje = r.optString("error", "No se pudo agregar.")
                    fichaMensajeError = true
                }
            } catch (_: Exception) {
                fichaMensaje = "No se pudo agregar: sin conexión con la computadora."
                fichaMensajeError = true
            }
        }
    }

    // ---------- listas a la derecha: idioma de la ficha y «Audio y subtítulos» del reproductor ----------

    private fun opcionesPistas(): List<Opcion> {
        val c = cur ?: return emptyList()
        val it = c.item ?: return emptyList()
        val out = mutableListOf<Opcion>()
        fun now(b: Boolean) = if (b) "Es el que suena ahora" else ""
        if (it.audio.size > 1) it.audio.forEachIndexed { i, a -> out += Opcion("Audio: " + trackName(a), now(i == c.audio), "audio", "audio:$i") }
        if (it.subs.isNotEmpty()) {
            out += Opcion("Sin subtítulos", now(c.sub < 0), "captions", "sub:-1")
            it.subs.forEachIndexed { i, s -> out += Opcion("Subtítulos: " + trackName(s), now(i == c.sub), "captions", "sub:$i") }
        }
        return out
    }

    /** «Idioma» en la ficha: audio a la izquierda, subtítulos a la derecha; el foco empieza en lo elegido. */
    private fun abrirIdioma() {
        val c = cur ?: return
        val it = c.item ?: return
        idioma = PanelIdioma(col = if (it.audio.isEmpty()) 1 else 0, audio = c.audio.coerceAtLeast(0), subs = c.sub + 1)
    }

    /** Las opciones de la columna de subtítulos (también en modo «¿En qué idioma?» para buscarlos en internet). */
    fun subsDelPanel(p: PanelIdioma): List<String> {
        if (p.buscar) return listOf("En español", "En inglés", "Volver")
        val it = cur?.item ?: return emptyList()
        return listOf("Sin subtítulos") + it.subs.map { trackName(it) } + "Buscar subtítulos en internet"
    }

    private fun teclaIdioma(t: Tecla, p: PanelIdioma) {
        val c = cur ?: return
        val it = c.item ?: return
        val subs = subsDelPanel(p)
        when (t) {
            Tecla.ATRAS -> idioma = if (p.buscar) p.copy(buscar = false, subs = 0) else null
            Tecla.DER -> if (p.col == 0) idioma = p.copy(col = 1)
            Tecla.IZQ -> if (p.col == 1 && it.audio.isNotEmpty()) idioma = p.copy(col = 0)
            Tecla.ARRIBA -> idioma = if (p.col == 0) p.copy(audio = (p.audio - 1).coerceAtLeast(0)) else p.copy(subs = (p.subs - 1).coerceAtLeast(0))
            Tecla.ABAJO -> idioma = if (p.col == 0) p.copy(audio = (p.audio + 1).coerceAtMost(it.audio.size - 1))
            else p.copy(subs = (p.subs + 1).coerceAtMost(subs.size - 1))
            Tecla.OK -> if (p.col == 0) {
                if (p.audio in it.audio.indices) {
                    c.audio = p.audio
                    guardarPreferencia(it, "audio", p.audio)
                    abrirFichaItem(true)
                }
            } else if (p.buscar) {
                idioma = p.copy(buscar = false, subs = 0)
                if (p.subs == 0) buscarSubtitulos("spa") else if (p.subs == 1) buscarSubtitulos("eng")
            } else if (p.subs == subs.size - 1) {
                idioma = p.copy(buscar = true, subs = 0)
            } else {
                c.sub = p.subs - 1
                guardarPreferencia(it, "sub", c.sub)
                abrirFichaItem(true)
            }
            else -> {}
        }
    }

    /** Elegir una pista a mano guarda la preferencia de ESTA TV («original» o el idioma). */
    private fun guardarPreferencia(it: Item, kind: String, n: Int) {
        val body = JSONObject()
        if (kind == "audio") body.put("audioLang", audioPref(it, n))
        else body.put("subLang", if (n in it.subs.indices) it.subs[n].lang else "off")
        scope.launch {
            try {
                api.post("/api/prefs", body.put("device_id", deviceId))
            } catch (_: Exception) {
            }
        }
    }

    /** «Buscar subtítulos en internet»: la computadora los baja y quedan elegidos. */
    private fun buscarSubtitulos(lang: String) {
        val c = cur ?: return
        mensajeFicha("Buscando subtítulos en internet…")
        scope.launch {
            try {
                val r = api.post("/api/subs/auto", JSONObject().put("id", c.id).put("lang", lang).put("device_id", deviceId), 120000)
                val item = r.optJSONObject("item")
                if (r.optBoolean("ok") && item != null && cur?.id == c.id) {
                    val it = app.onetv.tv.data.parseItem(item)
                    lib = lib?.let { l -> l.copy(items = l.items + (c.id to it)) }
                    val now = Actual(c.id, it, c.audio, r.optInt("sub", -1))
                    cur = now
                    guardarPreferencia(it, "sub", now.sub)
                    mensajeFicha("Subtítulos descargados: " + r.optString("label", ""))
                    if (ficha != null) abrirFichaItem(true)
                } else mensajeFicha(r.optString("error", "No se encontraron subtítulos."), true)
            } catch (_: Exception) {
                mensajeFicha("No se pudo buscar: sin conexión con la computadora.", true)
            }
        }
    }

    /** «Audio y subtítulos» del panel del reproductor: con YouTube, el audio original o un doblaje (solo si se pide). */
    fun abrirAudioYSubtitulos() {
        listaDesdeReproductor = true
        val r = reproductor.req
        val opciones = if (r?.yt == true) {
            val dubs = reproductor.doblajes
            if (dubs.isEmpty()) emptyList() else listOf(Opcion("Audio original", nowText(r.dub.isEmpty()), "audio", "dub:")) +
                dubs.map { d -> Opcion("Audio: " + d.name + " (doblaje)", if (r.dub == d.lang) "Es el que suena ahora   ·   voz hecha por YouTube" else "Voz hecha por YouTube", "languages", "dub:" + d.lang) }
        } else opcionesPistas()
        abrirLista(Lista("Audio y subtítulos", r?.title.orEmpty(), opciones,
            Vacio("Un solo audio", "Este video no tiene otros audios ni subtítulos.")))
    }

    private fun nowText(b: Boolean) = if (b) "Es el que suena ahora" else ""

    /** Abre una lista a la derecha con el foco en la que suena ahora (o en la primera que se pueda elegir). */
    fun abrirLista(l: Lista, foco: Int = -1) {
        lista = l
        val now = l.opciones.indexOfFirst { it.line.startsWith("Es el que suena ahora") && (it.accion.startsWith("audio") || it.accion.startsWith("dub")) }
        val first = l.opciones.indexOfFirst { !it.disabled }
        listaIndex = if (foco in l.opciones.indices) foco else if (now >= 0) now else first.coerceAtLeast(0)
    }

    private fun teclaLista(t: Tecla, l: Lista): Boolean {
        when (t) {
            Tecla.ARRIBA -> (listaIndex - 1 downTo 0).firstOrNull { !l.opciones[it].disabled }?.let { listaIndex = it }
            Tecla.ABAJO -> (listaIndex + 1 until l.opciones.size).firstOrNull { !l.opciones[it].disabled }?.let { listaIndex = it }
            Tecla.OK -> l.opciones.getOrNull(listaIndex)?.takeIf { !it.disabled }?.let { elegirEnLista(l, it) }
            Tecla.ATRAS, Tecla.IZQ -> {
                lista = null
                if (l.ctx == "listas") listsWant = ""
            }
            else -> if (listaDesdeReproductor && l.ctx == "pistas") return reproductor.tecla(t)
        }
        return true
    }

    private fun elegirEnLista(l: Lista, o: Opcion) {
        when (l.ctx) {
            "tarjeta" -> elegirEnMenuTarjeta(o.accion)
            "fila" -> elegirEnMenuFila(o.accion)
            "listas" -> elegirLista(o.accion)
            "listq" -> elegirListaALaFila(o.accion)
            else -> if (o.accion.startsWith("dub:")) {
                lista = null
                reproductor.cambiarDoblaje(o.accion.removePrefix("dub:"))
            } else elegirPista(o.accion)
        }
    }

    private fun elegirPista(accion: String) {
        lista = null
        val c = cur ?: return
        val it = c.item ?: return
        val (kind, n) = accion.split(":").let { it[0] to (it[1].toIntOrNull() ?: 0) }
        val prefsBody = JSONObject()
        if (kind == "audio") {
            c.audio = n
            prefsBody.put("audioLang", audioPref(it, n))
        } else {
            c.sub = n
            prefsBody.put("subLang", if (n in it.subs.indices) it.subs[n].lang else "off")
        }
        // Elegir una pista a mano guarda la preferencia de ESTA TV («original» o el idioma).
        scope.launch {
            try {
                api.post("/api/prefs", prefsBody.put("device_id", deviceId))
            } catch (_: Exception) {
            }
        }
        reproductor.cambiarPistas(c)
    }

    // ---------- reproducir ----------

    fun reproducirItem(startAt: Double) {
        val c = cur ?: return
        ficha = null
        menuAbierto = false
        reproductor.empezar(peticionItem(c, startAt))
    }

    /** ¿Se reproduce el archivo tal cual? Los doblajes agregados aparte siempre llegan por el servidor. */
    fun directo(c: Actual): Boolean {
        val it = c.item ?: return false
        if (it.direct == null) return false
        return !(c.audio in it.audio.indices && it.audio[c.audio].ext)
    }

    fun peticionItem(c: Actual, startAt: Double): Peticion {
        val it = c.item!!
        val direct = directo(c)
        val url = if (direct) api.url(it.direct!!.url) else api.url(it.audio.getOrNull(c.audio)?.hls ?: it.audio.first().hls)
        return Peticion(
            id = c.id, title = it.fullTitle, url = url, hls = !direct || it.direct?.format == "hls", startAt = startAt,
            duration = it.duration, audio = c.audio, sub = c.sub, audioTrack = if (direct) c.audio else -1,
            subs = it.subs.map { s -> api.url(s.url) to s.lang },
            hayPistas = it.audio.size > 1 || it.subs.isNotEmpty(), next = it.next,
        )
    }

    /** startAt < 0: donde se quedó, si se quedó a medias. */
    fun verYouTube(vid: String, startAt: Double) {
        var at = startAt
        if (at < 0) at = (ytProgress[vid] ?: 0.0).let { if (it > 30) it else 0.0 }
        val e = ytTitles[vid]
        cur = Actual("yt:$vid", yt = true)
        ficha = null
        menuAbierto = false
        reproductor.empezar(peticionYouTube(vid, at))
    }

    /** Lo que el reproductor necesita para un video de YouTube, con su audio original (dub: un doblaje pedido). */
    fun peticionYouTube(vid: String, at: Double, dub: String = ""): Peticion {
        val e = ytTitles[vid]
        val url = api.url("/yt/$vid/index.m3u8") + if (dub.isNotEmpty()) "?dub=$dub" else ""
        return Peticion(id = "yt:$vid", title = e?.title?.ifEmpty { null } ?: "YouTube", url = url, hls = true, startAt = at,
            duration = e?.duration ?: 0.0, yt = true, live = e?.live == true, dub = dub, checked = dub.isNotEmpty(),
            chapterTitles = chapterTitlesOn(lib?.prefs.orEmpty()))
    }

    /** Escuchar esas canciones desde la `i` (también la música que manda la computadora, control/Ordenes.kt). */
    fun escucharEn(tracks: List<app.onetv.tv.data.Song>, i: Int, startAt: Double) {
        musicCtx = tracks to i
        val t = tracks[i]
        cur = Actual("track:" + t.id, music = true)
        val next = tracks.getOrNull(i + 1)
        reproductor.empezar(Peticion(
            id = "track:" + t.id, title = t.title, url = api.url(t.url), hls = false, startAt = startAt, duration = t.duration,
            music = true, artist = t.artist, album = t.album, art = api.url(t.art), songIndex = i, songCount = tracks.size,
            last = i + 1 >= tracks.size, position = "${i + 1} de ${tracks.size}",
            nextTitle = next?.let { it.title + " · " + it.artist }.orEmpty(),
        ))
    }

    /** La canción anterior (-1) o la siguiente (1). -> false si no hay. */
    fun pasoMusica(dir: Int): Boolean {
        val (tracks, i) = musicCtx ?: return false
        val j = i + dir
        if (j !in tracks.indices) return false
        escucharEn(tracks, j, 0.0)
        return true
    }

    fun hayCancion(dir: Int): Boolean {
        val (tracks, i) = musicCtx ?: return false
        return (i + dir) in tracks.indices
    }

    internal fun tomarDeLaFila(index: Int) {
        scope.launch {
            try {
                val r = api.post("/api/queue/take", JSONObject().put("index", index).put("device_id", deviceId))
                r.optJSONObject("entry")?.let { reproducirEntrada(app.onetv.tv.data.parseEntry(it)) }
            } catch (_: Exception) {
                mostrarAviso("No se pudo: sin conexión con la computadora.", true)
            }
            cargarBiblioteca()
        }
    }

    fun reproducirEntrada(e: Entry) {
        when (e.kind) {
            "yt" -> {
                ytTitles.putIfAbsent(e.id, e)
                verYouTube(e.id, -1.0)
            }
            "track" -> escucharCancionSuelta(e.id)   // Musica.kt
            else -> if (lib?.items?.containsKey(e.id) == true) empezarItem(e.id, true)
        }
    }

    /** Del panel del reproductor: lo de la fila (sale de la fila) o lo visto hace poco. */
    fun panelFila(index: Int) = tomarDeLaFila(index)

    fun panelVistos(index: Int) {
        val h = lib?.history?.getOrNull(index) ?: return
        reproducirEntrada(h)
    }

    /** Se cerró el reproductor: se trae «Seguir viendo» ya actualizado del servidor. */
    fun alCerrarReproductor() {
        cargarBiblioteca()
    }
}
