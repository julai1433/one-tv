package app.onetv.tv

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import app.onetv.tv.data.Entry
import app.onetv.tv.data.countText
import app.onetv.tv.data.parseVideos
import kotlinx.coroutines.launch
import org.json.JSONObject

/**
 * Buscar (roku/components/SearchView.brs): mientras se escribe se busca en los títulos de la biblioteca; el botón
 * «Buscar «…» en YouTube» (o «Solo en vivo») busca lo mismo en YouTube. En la página «Buscar en YouTube» solo se
 * busca en YouTube. Se escribe con el teclado de la TV (OK sobre el campo lo abre).
 *
 * Partes con el foco: el campo (0), los dos botones de YouTube (1) y los resultados (2).
 */
class Buscador(private val app: Estado) {
    var texto by mutableStateOf("")
    var youtube by mutableStateOf(false)          // la página «Buscar en YouTube»
    var mostrando by mutableStateOf("lib")        // lib | yt: qué resultados se ven
    var zona by mutableStateOf(0)
    var boton by mutableStateOf(0)
    var foco by mutableStateOf(0)
    var editando by mutableStateOf(false)         // el teclado de la TV está abierto
    var pedirTeclado by mutableStateOf(0)         // cada vez que cambia, la pantalla abre el teclado

    // YouTube: la última búsqueda, sus resultados y si hay más («Cargar más resultados»).
    var estado by mutableStateOf("")              // «Buscando…», «En YouTube: «x»», «YouTube no encontró nada…»
    var resultados by mutableStateOf<List<Entry>?>(null)
    var mas by mutableStateOf(false)
    var masTexto by mutableStateOf("Cargar más resultados")
    var masLinea by mutableStateOf("OK: traer más")
    private var consulta = ""
    private var enVivo = false
    private var pagina = 1
    private var ocupado = false

    /** Al entrar a la sección (youtube = false) o a la página «Buscar en YouTube» (youtube = true). */
    fun abrir(yt: Boolean) {
        youtube = yt
        mostrando = if (yt) "yt" else "lib"
        zona = 0
        foco = 0
    }

    fun placeholder() = if (youtube) "Escribe qué buscar" else "Escribe un título"

    /** Llegó texto del teclado de la TV. */
    fun escribir(t: String) {
        texto = t
        if (!youtube) {
            mostrando = "lib"
            foco = 0
        }
    }

    fun editar() {
        zona = 0
        editando = true
        pedirTeclado++
    }

    fun terminarEdicion() {
        editando = false
    }

    // ---------- resultados ----------

    /** Las tarjetas que se ven ahora (biblioteca o YouTube) y su forma. */
    fun tarjetas(d: Datos?): Pair<Forma, List<Tarjeta>> {
        if (d == null) return Forma.BUSCAR_POSTER to emptyList()
        if (mostrando == "yt") {
            val list = resultados?.takeIf { !estado.startsWith("Buscando") }.orEmpty()
            val tiles = list.map { d.videoTile(it, app.ytProgress) }.toMutableList()
            if (mas && tiles.isNotEmpty()) tiles += Tarjeta("ytmore", masTexto, Estilo.VIDEO, null, masLinea, info = "Cargar más resultados de «$consulta»")
            return Forma.BUSCAR_VIDEO to tiles
        }
        return Forma.BUSCAR_POSTER to d.buscarBiblioteca(texto)
    }

    /** Lo de arriba de los resultados, o (sin resultados) el vacío que dice qué hacer. */
    fun cabecera(n: Int): String = when {
        n == 0 -> ""
        mostrando == "yt" -> estado
        else -> "En tu biblioteca: " + countText(n, "resultado", "resultados")
    }

    fun vacio(): Vacio {
        val t = texto.trim()
        if (mostrando == "yt") return when {
            estado.isEmpty() -> Vacio("Escribe qué buscar", "Luego elige «Buscar en YouTube», arriba.")
            estado.startsWith("Buscando") -> Vacio("Buscando en YouTube", estado)
            estado.startsWith("No se pudo") -> Vacio("No se pudo buscar", "La computadora no responde. Revisa que esté encendida y vuelve a intentarlo.")
            else -> Vacio("Sin resultados", estado)
        }
        if (t.isEmpty()) return Vacio("Escribe un título", "Busca en tus películas y series mientras escribes.")
        return Vacio("Nada con «$t»", "Prueba con menos letras, o búscalo en YouTube con el botón de arriba.")
    }

    fun columnas(forma: Forma) = (940 + forma.gap) / (forma.w + forma.gap)

    // ---------- YouTube ----------

    private fun buscarYouTube(live: Boolean) {
        val t = texto.trim()
        if (t.isEmpty()) return
        mostrando = "yt"
        consulta = t
        enVivo = live
        pagina = 1
        mas = false
        ocupado = false
        estado = if (live) "Buscando «$t» en vivo…" else "Buscando «$t» en YouTube…"
        foco = 0
        app.scope.launch {
            val r = try {
                app.api.post("/api/yt/search", JSONObject().put("q", t).put("live", live).put("device_id", app.deviceId), 60000)
            } catch (_: Exception) {
                null
            }
            if (consulta != t) return@launch   // ya se buscó otra cosa
            when {
                r == null -> estado = "No se pudo buscar: sin conexión con la computadora."
                !r.optBoolean("ok") -> estado = "YouTube: " + r.optString("error", "")
                else -> {
                    val list = parseVideos(r.optJSONArray("results"))
                    for (v in list) app.recordarYt(v)
                    resultados = list
                    pagina = r.optInt("page", 1)
                    mas = r.optBoolean("more") && list.isNotEmpty()
                    masTexto = "Cargar más resultados"
                    masLinea = "OK: traer más"
                    estado = when {
                        list.isEmpty() && live -> "Nadie transmite en vivo ahora con «$t»."
                        list.isEmpty() -> "YouTube no encontró nada con «$t»."
                        live -> "En vivo en YouTube: «$t»"
                        else -> "En YouTube: «$t»"
                    }
                    if (list.isNotEmpty() && !editando) zona = 2
                }
            }
        }
    }

    /** La tarjeta del final: OK trae la página siguiente; los nuevos se agregan al final (sin repetir). */
    fun cargarMas() {
        if (ocupado || !mas) return
        ocupado = true
        masTexto = "Cargando…"
        masLinea = ""
        val q = consulta
        app.scope.launch {
            val r = try {
                app.api.post("/api/yt/search", JSONObject().put("q", q).put("page", pagina + 1).put("live", enVivo).put("device_id", app.deviceId), 60000)
            } catch (_: Exception) {
                null
            }
            ocupado = false
            if (consulta != q) return@launch
            if (r == null || !r.optBoolean("ok")) {
                masTexto = "Cargar más resultados"
                masLinea = "No se pudo: OK para reintentar"
                return@launch
            }
            val have = resultados.orEmpty()
            val ids = have.map { it.id }.toHashSet()
            val nuevos = parseVideos(r.optJSONArray("results")).filter { it.id !in ids }
            for (v in nuevos) app.recordarYt(v)
            resultados = have + nuevos
            pagina = r.optInt("page", pagina + 1)
            mas = r.optBoolean("more")
            masTexto = "Cargar más resultados"
            masLinea = "OK: traer más"
            if (nuevos.isNotEmpty()) foco = have.size   // el foco, en el primero de los nuevos
        }
    }

    // ---------- teclas ----------

    fun tecla(t: Tecla, v: VistaBuscar): Boolean {
        if (editando) terminarEdicion()   // llegó una tecla: el teclado de la TV ya se cerró
        val (forma, tiles) = tarjetas(app.datos)
        val hayBotones = texto.trim().isNotEmpty()
        val hayResultados = tiles.isNotEmpty()
        if (zona == 2 && !hayResultados) zona = 0
        if (zona == 1 && !hayBotones) zona = 0
        when (zona) {
            0 -> when (t) {
                Tecla.OK -> editar()
                Tecla.DER -> if (hayBotones) zona = 1 else if (hayResultados) zona = 2
                Tecla.ABAJO -> if (hayResultados) zona = 2
                Tecla.IZQ -> app.abrirMenu()
                Tecla.ATRAS -> app.atrasEnVista()
                else -> {}
            }
            1 -> when (t) {
                Tecla.IZQ -> if (boton > 0) boton-- else zona = 0
                Tecla.DER -> if (boton < 1) boton++
                Tecla.ABAJO -> if (hayResultados) zona = 2
                Tecla.OK -> buscarYouTube(boton == 1)
                Tecla.ATRAS -> app.atrasEnVista()
                else -> {}
            }
            else -> {
                val cols = columnas(forma)
                val i = foco.coerceIn(0, tiles.size - 1)
                when (t) {
                    Tecla.IZQ -> if (i % cols > 0) foco = i - 1 else zona = 0
                    Tecla.DER -> if (i % cols < cols - 1 && i < tiles.size - 1) foco = i + 1
                    Tecla.ARRIBA -> if (i >= cols) foco = i - cols else if (hayBotones) zona = 1 else zona = 0
                    Tecla.ABAJO -> if (i + cols < tiles.size) foco = i + cols else if (i / cols < (tiles.size - 1) / cols) foco = tiles.size - 1
                    Tecla.OK -> app.activar(tiles[i].id, false)
                    Tecla.PLAY -> app.activar(tiles[i].id, true)
                    Tecla.OPCIONES -> if (!(tiles[i].menu && app.abrirMenuTarjeta(tiles[i].id))) {
                        app.mostrarAviso("Actualizando la biblioteca…")
                        app.cargarBiblioteca()
                    }
                    Tecla.ATRAS -> app.atrasEnVista()
                    else -> return false
                }
            }
        }
        return true
    }
}
