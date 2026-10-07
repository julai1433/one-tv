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
import app.onetv.tv.data.parseMusic
import app.onetv.tv.data.parseYtHome
import app.onetv.tv.data.spokenText
import app.onetv.tv.data.trackName
import app.onetv.tv.data.yearOf
import app.onetv.tv.net.Busqueda
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

enum class Conexion { BUSCANDO, NO_ENCONTRADA, ESCRIBIR, LISTA }

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
)

/** Un renglón de una lista para elegir (Audio y subtítulos, idioma): título, línea de apoyo y qué hace. */
data class Opcion(val title: String, val line: String, val icon: String, val accion: String)

/** La lista a la derecha de la pantalla (MultiPicker del Roku). */
data class Lista(val title: String, val note: String, val opciones: List<Opcion>, val vacio: Vacio)

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
    var puertoBusqueda = Busqueda.PUERTO
    var fijada: String? = null          // dirección dada al abrir la app (no se busca otra)

    var lib by mutableStateOf<Library?>(null)
    var ytHome by mutableStateOf<YtHome?>(null)
    var channels by mutableStateOf<List<app.onetv.tv.data.Channel>?>(null)
    var music by mutableStateOf<Music?>(null)
    var musicError by mutableStateOf(false)
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
        lib?.let { Datos(it, direccion, ytHome, music, musicError, filtros.toMap()) }
    }

    /** La vista que se ve ahora (la página de arriba o la sección). */
    val vista: Vista? by derivedStateOf {
        val d = datos ?: return@derivedStateOf null
        when (val p = paginas.lastOrNull()) {
            is Pagina.Serie -> d.serie(p.key)
            is Pagina.MusicaPagina -> d.musicaPagina(p)
            null -> when (seccion) {
                Seccion.INICIO -> d.inicio(ytProgress)
                Seccion.ESPANOL -> d.espanol()
                Seccion.PELICULAS -> d.peliculas()
                Seccion.SERIES -> d.series()
                Seccion.YOUTUBE -> d.youtube(channels, ytProgress)
                Seccion.MUSICA -> d.musica()
                Seccion.FILA -> d.fila()
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

    private var busqueda: Job? = null

    fun buscar() {
        if (busqueda?.isActive == true) return
        conexion = if (lib == null) Conexion.BUSCANDO else conexion
        busqueda = scope.launch {
            val recordada = prefs.getString("servidor", null)
            val found = Busqueda.buscar(recordada, direccionesPropias(), puertoBusqueda) { Servidor.esOneTv(it) }
            if (found != null) {
                conectar(found)
            } else if (lib == null) {
                conexion = Conexion.NO_ENCONTRADA
                delay(20_000)
                if (conexion == Conexion.NO_ENCONTRADA) {
                    busqueda = null
                    buscar()   // se sigue buscando sola mientras la pantalla esté a la vista
                }
            }
        }
    }

    fun conectar(base: String) {
        direccion = base
        api.base = base
        if (fijada == null) prefs.edit().putString("servidor", base).apply()
        conexion = Conexion.LISTA
        cargarBiblioteca()
    }

    /** Una dirección escrita a mano (pantalla «Escribir la dirección»). */
    fun probarEscrita(texto: String, listo: (String?) -> Unit) {
        val base = Busqueda.normalizar(texto)
        if (base == null) {
            listo("Escribe la dirección que muestra la computadora, por ejemplo 192.0.2.5")
            return
        }
        scope.launch {
            val ok = kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) { Servidor.esOneTv(base, 3000) }
            if (ok) {
                listo(null)
                conectar(base)
            } else listo("No hay un One TV en $base. Revisa la dirección y que la computadora esté encendida.")
        }
    }

    /** Cambió la red (otro Wi-Fi, se reconectó): si no hay servidor, se busca otra vez. */
    fun redCambio() {
        if (conexion != Conexion.LISTA || sinServidor) {
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
                    ytTitles[e.id] = e
                    if (e.p > 0) ytProgress[e.id] = e.p
                }
                for (e in l.youtube + l.queue) if (e.kind == "yt") ytTitles.putIfAbsent(e.id, e)
                if (sinServidor) sinServidor = false
                if (first) ocultarAviso()
                if (l.items.isEmpty()) mostrarAviso("No hay videos. Revisa «carpetas» en config.json de la computadora.", false, auto = false)
                cargarYouTube()
                if (first) cargarMusica()
                pendiente?.let {
                    pendiente = null
                    abrirContenido(it)
                }
            } catch (e: Exception) {
                fallos++
                if (lib == null) ocultarAviso()
                sinServidor = true
                reintento?.cancel()
                reintento = scope.launch {
                    delay(5000)
                    // La sigue buscando sola cada 5 segundos; si no responde varias veces, quizá cambió de dirección.
                    if (fallos >= 3 && fijada == null) {
                        val found = Busqueda.buscar(direccion, direccionesPropias(), puertoBusqueda) { Servidor.esOneTv(it) }
                        if (found != null && found != direccion) {
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
                for (e in h.cont + h.new + h.recent + h.because + h.favorites) ytTitles[e.id] = e
                for (e in h.cont) if (e.p > 0) ytProgress[e.id] = e.p
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

    fun cargarMusica() {
        scope.launch {
            try {
                val o = api.get("/api/music", 30000)
                if (o.optBoolean("ok", true)) music = parseMusic(o) else musicError = true
            } catch (_: Exception) {
                if (music == null) musicError = true
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

    fun mostrarAviso(text: String, error: Boolean = false, auto: Boolean = true) {
        aviso = text
        avisoError = error
        avisoJob?.cancel()
        if (auto) avisoJob = scope.launch {
            delay(4000)
            aviso = ""
        }
    }

    fun ocultarAviso() {
        avisoJob?.cancel()
        aviso = ""
    }

    // ---------- teclas ----------

    fun tecla(t: Tecla): Boolean {
        if (conexion != Conexion.LISTA) return teclaConexion(t)
        lista?.let { return teclaLista(t, it) }
        if (reproductor.visible) return reproductor.tecla(t)
        ficha?.let { return teclaFicha(t, it) }
        if (sinServidor) {
            if (t == Tecla.OK) {
                mostrarAviso("Buscando la computadora…")
                cargarBiblioteca()
            } else if (t == Tecla.ATRAS) salir()
            return true
        }
        if (menuAbierto) return teclaMenu(t)
        val v = vista ?: return t != Tecla.ATRAS || run { salir(); true }
        return when (v) {
            is VistaFilas -> teclaFilas(t, v)
            is VistaCuadricula -> teclaCuadricula(t, v)
        }
    }

    var conexionBoton by mutableStateOf(0)

    private fun teclaConexion(t: Tecla): Boolean {
        when (conexion) {
            Conexion.NO_ENCONTRADA -> when (t) {
                Tecla.IZQ, Tecla.DER -> conexionBoton = 1 - conexionBoton
                Tecla.OK -> if (conexionBoton == 0) {
                    busqueda?.cancel()
                    busqueda = null
                    conexion = Conexion.BUSCANDO
                    buscar()
                } else conexion = Conexion.ESCRIBIR
                Tecla.ATRAS -> salir()
                else -> {}
            }
            Conexion.ESCRIBIR -> {
                if (t == Tecla.ATRAS) {
                    conexion = Conexion.NO_ENCONTRADA
                    return true
                }
                return false   // el campo de texto y el teclado de la TV se encargan
            }
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
    }

    private fun atrasEnVista() {
        if (paginas.isNotEmpty()) paginas.removeAt(paginas.size - 1) else abrirMenu()
    }

    private fun teclaFilas(t: Tecla, v: VistaFilas): Boolean {
        if (v.filas.isEmpty()) {
            if (t == Tecla.ATRAS || t == Tecla.IZQ) atrasEnVista()
            return true
        }
        val (r0, c0) = focoFilas[v.key] ?: (0 to 0)
        val r = r0.coerceIn(0, v.filas.size - 1)
        val fila = v.filas[r]
        val n = if (fila.tarjetas.isEmpty()) 1 else fila.tarjetas.size
        val c = c0.coerceIn(0, n - 1)
        when (t) {
            Tecla.ARRIBA -> if (r > 0) focoFilas[v.key] = (r - 1) to colPara(v.filas[r - 1], c)
            Tecla.ABAJO -> if (r < v.filas.size - 1) focoFilas[v.key] = (r + 1) to colPara(v.filas[r + 1], c)
            Tecla.IZQ -> if (c > 0) focoFilas[v.key] = r to (c - 1) else abrirMenu()   // ← desde la primera columna
            Tecla.DER -> if (c < n - 1) focoFilas[v.key] = r to (c + 1)
            Tecla.OK, Tecla.PLAY -> {
                if (fila.tarjetas.isEmpty()) fila.vacio?.let { accionVacio(it.actionId) }
                else activar(fila.tarjetas[c].id, t == Tecla.PLAY)
            }
            Tecla.ATRAS -> atrasEnVista()
            Tecla.OPCIONES -> {
                mostrarAviso("Actualizando la biblioteca…")
                cargarBiblioteca()
            }
            else -> return false
        }
        return true
    }

    private fun colPara(f: Fila, c: Int) = if (f.tarjetas.isEmpty()) 0 else c.coerceIn(0, f.tarjetas.size - 1)

    fun columnas(v: VistaCuadricula) = if (v.forma == Forma.GRID_CUADRADO) 7 else 8

    private fun teclaCuadricula(t: Tecla, v: VistaCuadricula): Boolean {
        val cols = columnas(v)
        val n = v.tarjetas.size
        val hasChips = v.chips.isNotEmpty()
        var i = focoCuadricula[v.key] ?: (if (n == 0 && hasChips) -1 else 0)
        if (i >= n) i = n - 1
        if (i < 0 && !hasChips) i = 0
        if (i == -1) {   // en los botones de arriba
            val chip = focoChip[v.key] ?: v.chips.indexOfFirst { it.id == v.chipValue }.coerceAtLeast(0)
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
            Tecla.OPCIONES -> {
                mostrarAviso("Actualizando la biblioteca…")
                cargarBiblioteca()
            }
            else -> return false
        }
        return true
    }

    /** Filtros de Películas y Series (se recuerdan en esta TV) o los botones de una página de música. */
    private fun controlCuadricula(v: VistaCuadricula, id: String) {
        val p = paginas.lastOrNull()
        if (p is Pagina.MusicaPagina) {
            val ids = datos?.musicaPaginaTracks(p).orEmpty()
            if (ids.isEmpty()) return
            if (id == "m-play") escucharLista(ids, 0, false) else escucharLista(ids, ids.indices.random(), true)
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
                val ids = when (ctx) {
                    "recent" -> datos?.recientes().orEmpty()
                    else -> (paginas.lastOrNull() as? Pagina.MusicaPagina)?.let { datos?.musicaPaginaTracks(it) }.orEmpty()
                }
                escucharLista(ids, i, false)
            }
            id.startsWith("album:") || id.startsWith("mlist:") || id.startsWith("artist:") -> {
                val sub = when {
                    id.startsWith("album:") -> "album"
                    id.startsWith("mlist:") -> "list"
                    else -> "artist"
                }
                val rid = id.substringAfter(":")
                val m = music ?: return
                val title = when (sub) {
                    "album" -> m.albums.firstOrNull { it.id == rid }?.title
                    "list" -> m.playlists.firstOrNull { it.id == rid }?.title
                    else -> m.artists.firstOrNull { it.id == rid }?.name
                }.orEmpty()
                val page = Pagina.MusicaPagina(sub, rid, title)
                if (quick) {
                    val ids = datos?.musicaPaginaTracks(page).orEmpty()
                    if (ids.isNotEmpty()) escucharLista(ids, 0, false)
                } else {
                    focoCuadricula["musica:$sub:$rid"] = 0
                    paginas.add(page)
                }
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
            id.startsWith("list:") || id.startsWith("chan:") ->
                mostrarAviso("Las listas y los canales de YouTube se abren desde la web por ahora.")
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
        ficha = Ficha("item", c.id, title, subtitle, meta, it.dub, spokenText(it), datos?.abs(it.poster), buttons)
        if (!keepFocus) {
            fichaBoton = 0
            fichaMensaje = ""
            fichaDesc = ""
            scope.launch {
                try {
                    val d = api.get("/api/info?id=${c.id}").optString("desc", "")
                    if (ficha?.id == c.id) fichaDesc = d
                } catch (_: Exception) {
                }
            }
        }
    }

    private fun langButtonText(it: Item, c: Actual): String {
        var text = "Idioma"
        if (c.audio in it.audio.indices) text += ": " + trackName(it.audio[c.audio])
        if (c.sub >= 0) text += " + subtítulos"
        return text
    }

    fun fichaYouTube(vid: String) {
        val e = ytTitles[vid]
        cur = Actual("yt:$vid", yt = true)
        val p = ytProgress[vid] ?: 0.0
        val buttons = mutableListOf<Boton>()
        if (p > 30) {
            buttons += Boton("yt-resume", "Continuar desde " + fmtClock(p), "play")
            buttons += Boton("yt-play", "Desde el principio", "rotate-ccw")
        } else buttons += Boton("yt-play", "Reproducir", "play")
        buttons += Boton("yt-next", "A continuación", "list-start")
        buttons += Boton("yt-queue", "Al final de la fila", "list-plus")
        val meta = listOfNotNull(e?.channel?.ifEmpty { null }, e?.duration?.takeIf { it > 0 }?.let { fmtClock(it) }).joinToString("   ·   ")
        ficha = Ficha("yt", vid, e?.title?.ifEmpty { null } ?: "YouTube", "", meta, false, "", datos?.abs("/yt/$vid/thumb-hd.jpg"), buttons)
        fichaBoton = 0
        fichaMensaje = ""
        fichaDesc = ""
        scope.launch {
            try {
                val o = api.get("/api/yt/info?id=$vid", 30000)
                if (ficha?.id == vid) fichaDesc = o.optString("desc", "")
            } catch (_: Exception) {
            }
        }
    }

    private fun teclaFicha(t: Tecla, f: Ficha): Boolean {
        when (t) {
            Tecla.IZQ -> if (fichaBoton > 0) fichaBoton--
            Tecla.DER -> if (fichaBoton < f.buttons.size - 1) fichaBoton++
            Tecla.OK -> botonFicha(f, f.buttons[fichaBoton].id)
            Tecla.PLAY -> botonFicha(f, f.buttons[0].id)
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
        }
    }

    private fun alaFila(kind: String, id: String, title: String, front: Boolean) {
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

    private fun abrirIdioma() {
        listaDesdeReproductor = false
        abrirLista(Lista("Idioma", ficha?.title.orEmpty(), opcionesPistas(), Vacio("Un solo audio", "Este video no tiene otros audios ni subtítulos.")))
    }

    fun abrirAudioYSubtitulos() {
        listaDesdeReproductor = true
        abrirLista(Lista("Audio y subtítulos", reproductor.req?.title.orEmpty(), opcionesPistas(),
            Vacio("Un solo audio", "Este video no tiene otros audios ni subtítulos.")))
    }

    private fun abrirLista(l: Lista) {
        lista = l
        listaIndex = l.opciones.indexOfFirst { it.line.isNotEmpty() && it.accion.startsWith("audio") }.coerceAtLeast(0)
    }

    private fun teclaLista(t: Tecla, l: Lista): Boolean {
        when (t) {
            Tecla.ARRIBA -> if (listaIndex > 0) listaIndex--
            Tecla.ABAJO -> if (listaIndex < l.opciones.size - 1) listaIndex++
            Tecla.OK -> l.opciones.getOrNull(listaIndex)?.let { elegirPista(it.accion) }
            Tecla.ATRAS, Tecla.IZQ -> lista = null
            else -> if (listaDesdeReproductor) return reproductor.tecla(t)
        }
        return true
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
        if (listaDesdeReproductor) reproductor.cambiarPistas(c) else abrirFichaItem(true)
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
        reproductor.empezar(Peticion(id = "yt:$vid", title = e?.title?.ifEmpty { null } ?: "YouTube", url = api.url("/yt/$vid/index.m3u8"),
            hls = true, startAt = at, duration = e?.duration ?: 0.0, yt = true))
    }

    fun escucharLista(ids: List<String>, index: Int, shuffle: Boolean) {
        val m = music ?: return
        var tracks = ids.mapNotNull { m.tracks[it] }
        if (tracks.isEmpty()) return
        var i = index.coerceIn(0, tracks.size - 1)
        if (shuffle) {
            tracks = listOf(tracks[i]) + (tracks - tracks[i]).shuffled()
            i = 0
        }
        escucharEn(tracks, i, 0.0)
    }

    private fun escucharEn(tracks: List<app.onetv.tv.data.Song>, i: Int, startAt: Double) {
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

    private fun tomarDeLaFila(index: Int) {
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
            "track" -> music?.tracks?.get(e.id)?.let { escucharEn(listOf(it), 0, 0.0) }
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
