package app.onetv.tv

import app.onetv.tv.data.Channel
import app.onetv.tv.data.Entry
import app.onetv.tv.data.Item
import app.onetv.tv.data.Library
import app.onetv.tv.data.Music
import app.onetv.tv.data.Show
import app.onetv.tv.data.YtHome
import app.onetv.tv.data.agoText
import app.onetv.tv.data.chooseAudio
import app.onetv.tv.data.chooseSub
import app.onetv.tv.data.countText
import app.onetv.tv.data.fmtClock
import app.onetv.tv.data.fmtDuration
import app.onetv.tv.data.initialsOf
import app.onetv.tv.data.langChoiceText
import app.onetv.tv.data.plainText
import app.onetv.tv.data.remainingText
import app.onetv.tv.data.Silenciado
import app.onetv.tv.data.viewersText

// Lo que muestra cada sección y cada página, armado con los datos del servidor como en roku/components/Catalog.brs,
// YouTube.brs y Music.brs: las mismas filas, los mismos textos y las mismas filas vacías que enseñan.

/** Tamaño de cada tipo de tarjeta en la escala de la TV (Util.brs, tileSpec): imagen w×h y hueco que ocupa. */
enum class Forma(val w: Int, val h: Int, val slotH: Int, val gap: Int) {
    POSTER(213, 320, 320, 24),
    VIDEO(352, 198, 282, 28),
    CANAL(176, 176, 282, 44),
    CUADRADO(260, 260, 344, 28),
    GRID_POSTER(186, 279, 279, 24),
    GRID_CUADRADO(232, 232, 316, 24),
    GRID_VIDEO(368, 207, 289, 32),
    AJUSTE(840, 150, 150, 36),
    BUSCAR_POSTER(186, 279, 279, 24),
    BUSCAR_VIDEO(288, 162, 246, 24),
}

enum class Estilo { POSTER, VIDEO, YTCARD, CANAL, AJUSTE }

/** Lo que dice cada tarjeta, después de lo suyo, para abrir sus opciones (la tecla ✱ del Roku: aquí, OK sostenido). */
const val OPCIONES = "mantén OK: opciones"

/** Un ajuste general: dos segmentos (la opción elegida en limón) o un botón. */
data class Ajuste(val segmentos: List<String>, val elegido: Int, val boton: String = "", val icon: String = "")

data class Tarjeta(
    val id: String,
    val title: String,
    val estilo: Estilo,
    val image: String? = null,
    val line2: String = "",
    val progress: Float = 0f,
    val spanish: Boolean = false,
    val dur: Int = 0,
    val info: String = "",
    val initials: String = "",
    val liveTag: Boolean = false,     // transmisión de YouTube en vivo: «EN VIVO» en rojo en lugar de la duración
    val pinned: Boolean = false,      // canal anclado: el punto limón
    val ajuste: Ajuste? = null,
    val menu: Boolean = false,        // OK sostenido abre sus opciones
)

/** Fila vacía que enseña (DESIGN.md, pieza 4): frase de marquesina, la causa y, si se puede, una acción. */
data class Vacio(val phrase: String, val cause: String, val action: String = "", val actionId: String = "")

data class Fila(val title: String, val forma: Forma, val tarjetas: List<Tarjeta>, val vacio: Vacio? = null)

data class Boton(val id: String, val text: String, val icon: String, val danger: Boolean = false)

sealed interface Vista {
    val key: String
    val header: String
}

/** topButton: el botón de arriba («Buscar en YouTube»), o "" si no hay. */
data class VistaFilas(override val key: String, override val header: String, val filas: List<Fila>, val topButton: String = "") : Vista

/** Buscar: en la biblioteca mientras se escribe (mode «all») o solo en YouTube (la página «Buscar en YouTube»). */
data class VistaBuscar(override val key: String, override val header: String, val youtube: Boolean) : Vista

/** chips: filtros (segmentos) de Películas y Series, o los botones de una página (Escuchar, Aleatorio…). */
data class VistaCuadricula(
    override val key: String,
    override val header: String,
    val count: String,
    val forma: Forma,
    val tarjetas: List<Tarjeta>,
    val vacio: Vacio,
    val chips: List<Boton> = emptyList(),
    val chipValue: String = "",
    val chipsSegmentos: Boolean = true,
    val chipsPrincipal: Boolean = true,   // botones: ¿el primero es el principal?
) : Vista

/** Las secciones del menú, en su orden (las de Roku que ya tiene esta app). */
enum class Seccion(val text: String, val icon: String) {
    BUSCAR("Buscar", "search"),
    INICIO("Inicio", "house"),
    ESPANOL("En español", "languages"),
    PELICULAS("Películas", "clapper"),
    SERIES("Series", "monitor-play"),
    YOUTUBE("YouTube", "square-play"),
    MUSICA("Música", "music"),
    EN_VIVO("En vivo", "radio"),
    FILA("Fila de reproducción", "list-video"),
}

sealed interface Pagina {
    data class Serie(val key: String) : Pagina
    data class MusicaPagina(val sub: String, val id: String, val title: String) : Pagina
    data class Canal(val id: String, val title: String) : Pagina
    data class ListaYt(val id: String, val title: String) : Pagina
    data object BuscarYt : Pagina
    data object Silenciados : Pagina
}

/** Los videos de la página de un canal o de una lista (llegan aparte). videos null: todavía cargando. */
data class PaginaVideos(
    val videos: List<Entry>? = null,
    val error: String = "",
    val title: String = "",
    val pinned: Boolean = false,
    val hidden: Boolean = false,
)

/** Los datos con los que se arman las vistas. */
class Datos(
    val lib: Library,
    val server: String,
    val ytHome: YtHome?,
    val music: Music?,
    val musicError: Boolean,
    val filtros: Map<String, String>,
) {
    fun abs(path: String?): String? = when {
        path.isNullOrEmpty() -> null
        path.startsWith("http") -> path
        else -> server + path
    }

    fun resumePos(id: String) = lib.progress[id] ?: 0.0

    // ---------- tarjetas ----------

    private fun artOf(it: Item): String {
        if (it.art.isNotEmpty()) return it.art
        if (it.kind == "episode") lib.series.firstOrNull { s -> s.title == it.show && s.art.isNotEmpty() }?.let { s -> return s.art }
        return it.poster
    }

    fun itemInfo(id: String, it: Item): String {
        val parts = mutableListOf(it.fullTitle)
        val p = resumePos(id)
        parts += if (p > 0) remainingText(p, it.duration) else fmtDuration(it.duration)
        val lang = langChoiceText(it, chooseAudio(it, lib.prefs), chooseSub(it, lib.prefs))
        if (lang.isNotEmpty()) parts += lang
        return parts.joinToString("   ·   ")
    }

    fun itemTile(id: String): Tarjeta? {
        val it = lib.items[id] ?: return null
        val p = resumePos(id)
        return Tarjeta(
            id = id, title = it.fullTitle, estilo = Estilo.POSTER, image = abs(artOf(it)),
            progress = if (it.duration > 0) (p / it.duration).toFloat() else 0f, spanish = it.dub,
            info = itemInfo(id, it) + "   ·   " + OPCIONES, menu = true,
        )
    }

    fun showTile(show: Show): Tarjeta {
        val art = show.art.ifEmpty { lib.items[show.poster]?.poster.orEmpty() }
        return Tarjeta(id = "serie:" + show.key, title = show.title, estilo = Estilo.POSTER, image = abs(art), spanish = show.dub, info = showInfo(show))
    }

    private fun showInfo(show: Show): String {
        var text = show.title + "   ·   " + countText(show.seasons.size, "temporada", "temporadas")
        val nxt = nextUp(show)
        lib.items[nxt.first]?.let { text += "   ·   " + nxt.second + ": T" + it.season + " " + it.ep }
        return text
    }

    /** El episodio a medias, o el siguiente al último visto, o el primero. -> (id, verbo) */
    fun nextUp(show: Show): Pair<String, String> {
        val episodes = show.seasons.flatMap { it.items }
        if (episodes.isEmpty()) return "" to "Empezar"
        for ((id, p) in lib.keepWatching) if (id in episodes) return id to (if (p > 0) "Continuar" else "Siguiente")
        val last = episodes.indexOfLast { it in lib.seen }
        if (last == -1) return episodes[0] to "Empezar"
        if (last < episodes.size - 1) return episodes[last + 1] to "Siguiente"
        return episodes[0] to "Ver de nuevo"
    }

    private fun channelAgo(v: Entry): String = listOfNotNull(v.channel.ifEmpty { null }, agoText(v.published).ifEmpty { null }).joinToString(" · ")

    fun videoTile(v: Entry, ytProgress: Map<String, Double>): Tarjeta {
        val p = ytProgress[v.id] ?: v.p
        val title = if (v.private) "Video privado" else v.title
        var sub = if (p > 0 && v.duration > 0) listOfNotNull(v.channel.ifEmpty { null }, remainingText(p, v.duration)).joinToString(" · ") else channelAgo(v)
        var line = listOfNotNull(channelAgo(v).ifEmpty { null }, if (v.duration > 0) (if (p > 0) remainingText(p, v.duration) else fmtClock(v.duration)) else null)
            .joinToString(" · ")
        if (v.live) {
            sub = liveLine(v)
            line = "En vivo ahora   ·   " + liveLine(v)
        }
        return Tarjeta(
            id = "yt:" + v.id, title = title, estilo = Estilo.VIDEO, image = abs(v.thumb.ifEmpty { "/yt/${v.id}/thumb.jpg" }),
            line2 = sub, dur = if (v.live || v.private) 0 else v.duration.toInt(), progress = if (p > 0 && v.duration > 0) (p / v.duration).toFloat() else 0f,
            info = (if (line.isNotEmpty()) title + "   ·   " + line else title) + "   ·   " + OPCIONES, liveTag = v.live, menu = true,
        )
    }

    /** «Canal · 5,2 mil viendo» de una transmisión en vivo. */
    private fun liveLine(v: Entry) = listOfNotNull(v.channel.ifEmpty { null }, viewersText(v.viewers).ifEmpty { null }).joinToString(" · ")

    /** Video de YouTube dentro de la fila de pósters de «Seguir viendo». */
    private fun ytCardTile(v: Entry): Tarjeta = Tarjeta(
        id = "yt:" + v.id, title = v.title, estilo = Estilo.YTCARD, image = abs("/yt/${v.id}/thumb-hd.jpg"),
        line2 = channelAgo(v).ifEmpty { "YouTube" }, dur = v.duration.toInt(),
        progress = if (v.duration > 0) (v.p / v.duration).toFloat() else 0f,
        info = v.title + "   ·   " + listOfNotNull(channelAgo(v).ifEmpty { null },
            if (v.duration > 0) (if (v.p > 0) remainingText(v.p, v.duration) else fmtClock(v.duration)) else null).joinToString(" · ") + "   ·   " + OPCIONES,
        menu = true,
    )

    // ---------- Inicio ----------

    fun spanishList(): List<Tarjeta> {
        val movies = lib.items.values.filter { it.kind == "movie" && it.dub }.sortedBy { it.title.lowercase() }.mapNotNull { itemTile(it.id) }
        val shows = lib.series.filter { it.dub }.sortedBy { it.title.lowercase() }.map { showTile(it) }
        return movies + shows
    }

    fun spanishCount(): String {
        val movies = lib.items.values.count { it.kind == "movie" && it.dub }
        val shows = lib.series.count { it.dub }
        val parts = mutableListOf(countText(movies, "película", "películas"))
        if (shows > 0) parts += countText(shows, "serie", "series")
        return parts.joinToString(" y ")
    }

    fun inicio(ytProgress: Map<String, Double>): VistaFilas {
        val filas = mutableListOf<Fila>()
        val cont = lib.cont.mapNotNull { e -> if (e.kind == "yt") ytCardTile(e) else itemTile(e.id) }
        filas += Fila("Seguir viendo", Forma.POSTER, cont,
            Vacio("Nada a medias", "Lo que empieces a ver se queda aquí, justo donde lo dejaste.", "Ver películas", "movies"))
        filas += Fila("En español   ·   " + spanishCount(), Forma.POSTER, spanishList(),
            Vacio("Todavía nada en español", "Aquí salen las películas y series que se oyen en español.", "Ver películas", "movies"))
        filas += Fila("Nuevos de tus canales", Forma.VIDEO, ytHome?.new.orEmpty().map { videoTile(it, ytProgress) }, vacioNuevos(null))
        filas += Fila(becauseTitle(), Forma.VIDEO, ytHome?.because.orEmpty().map { videoTile(it, ytProgress) }, vacioPorque())
        filas += Fila("Recién agregadas", Forma.POSTER, lib.recent.mapNotNull { itemTile(it) },
            Vacio("Nada nuevo", "Lo que agregues a la biblioteca sale aquí primero.", "Buscar películas nuevas", "rescan"))
        return VistaFilas("inicio", "Inicio", filas)
    }

    private fun vacioNuevos(channels: List<Channel>?) = when {
        ytHome == null -> Vacio("Cargando", "Pidiendo a la computadora lo nuevo de tus canales…")
        !channels.isNullOrEmpty() -> Vacio("Nada nuevo en tus canales", "La computadora revisa tus canales cada hora.", "Buscar en YouTube", "ytsearch")
        else -> Vacio("Todavía no hay canales", "Salen cuando traes tus suscripciones de YouTube a la computadora.", "Cómo traer tus suscripciones", "takeout")
    }

    private fun vacioPorque() = if (ytHome == null) Vacio("Cargando", "Pidiendo a la computadora videos parecidos…")
    else Vacio("Todavía nada parecido", "Cuando veas videos de YouTube, aquí salen otros parecidos.", "Buscar en YouTube", "ytsearch")

    private fun becauseTitle(): String {
        val seed = ytHome?.becauseSeed.orEmpty()
        if (seed.isEmpty()) return "Porque viste…"
        val s = if (seed.length > 44) seed.take(42).trim() + "…" else seed
        return "Porque viste «$s»"
    }

    // ---------- En español, Películas y Series ----------

    private fun chipsIdioma() = listOf(Boton("all", "Todas", ""), Boton("yes", "Con español", ""), Boton("no", "Sin español", ""))

    private fun pasa(filter: String, dub: Boolean) = when (filter) {
        "yes" -> dub
        "no" -> !dub
        else -> true
    }

    fun espanol() = VistaCuadricula("espanol", "En español", spanishCount(), Forma.GRID_POSTER, spanishList(),
        Vacio("Todavía nada en español", "Aquí salen las películas y series que se oyen en español.", "Ver películas", "movies"))

    fun peliculas(): VistaCuadricula {
        val f = filtros["movies"] ?: "all"
        val list = lib.items.values.filter { it.kind == "movie" && pasa(f, it.dub) }.sortedBy { it.title.lowercase() }.mapNotNull { itemTile(it.id) }
        return VistaCuadricula("peliculas", "Películas", countText(list.size, "película", "películas") + filtroTexto(f), Forma.GRID_POSTER,
            list, vacioCuadricula("película", "películas", f), chipsIdioma(), f)
    }

    fun series(): VistaCuadricula {
        val f = filtros["series"] ?: "all"
        val list = lib.series.filter { pasa(f, it.dub) }.map { showTile(it) }
        return VistaCuadricula("series", "Series", countText(list.size, "serie", "series") + filtroTexto(f), Forma.GRID_POSTER,
            list, vacioCuadricula("serie", "series", f), chipsIdioma(), f)
    }

    private fun filtroTexto(f: String) = when (f) {
        "yes" -> " con español"
        "no" -> " sin español"
        else -> ""
    }

    private fun vacioCuadricula(one: String, many: String, filter: String) = if (filter != "all")
        Vacio("Ninguna $one con este filtro", "Cambia el filtro de arriba o mira todas.", "Ver todas", "filter-all")
    else Vacio("Todavía no hay $many", "Agrega $many a la carpeta de la biblioteca y aparecen aquí solas.", "Buscar $many nuevas", "rescan")

    // ---------- una serie ----------

    fun serie(key: String): VistaFilas? {
        val show = lib.series.firstOrNull { it.key == key } ?: return null
        val filas = mutableListOf<Fila>()
        val (nid, verb) = nextUp(show)
        lib.items[nid]?.let { filas += Fila(verb, Forma.VIDEO, listOf(episodeTile(nid, it, "T${it.season} ${it.ep}"))) }
        for (season in show.seasons) {
            filas += Fila(season.title, Forma.VIDEO, season.items.mapNotNull { id -> lib.items[id]?.let { episodeTile(id, it, "") } })
        }
        return VistaFilas("serie:$key", show.title, filas)
    }

    private fun episodeTile(id: String, it: Item, prefix: String): Tarjeta {
        var title = prefix.ifEmpty { it.ep }
        if (it.epTitle.isNotEmpty()) title += " · " + it.epTitle
        val p = resumePos(id)
        var sub = if (p > 0) remainingText(p, it.duration) else fmtDuration(it.duration)
        if (id in lib.seen) sub = "Visto"
        return Tarjeta(id = id, title = title, estilo = Estilo.VIDEO, image = abs(it.poster), line2 = sub,
            progress = if (it.duration > 0) (p / it.duration).toFloat() else 0f, spanish = it.dub,
            info = itemInfo(id, it) + "   ·   " + OPCIONES, menu = true)
    }

    // ---------- YouTube ----------

    fun youtube(channels: List<Channel>?, ytProgress: Map<String, Double>): VistaFilas {
        val h = ytHome
        val filas = mutableListOf<Fila>()
        val lists = h?.playlists.orEmpty()
        val chans = channels
        // Sin cuenta (no hay Takeout importado): un solo vacío, como en la web, en lugar de tres filas que dicen lo mismo.
        if (h != null && chans != null && lists.isEmpty() && chans.isEmpty() && h.new.isEmpty()) {
            filas += Fila("Tu cuenta de YouTube", Forma.VIDEO, emptyList(), Vacio("Conecta tu YouTube",
                "Tus listas, lo nuevo de tus canales y tus canales aparecen aquí en cuanto la computadora tenga tu cuenta (el archivo de Google Takeout).",
                "Cómo traer tu cuenta", "takeout"))
            favoritos(filas, ytProgress)
        } else {
            filas += Fila("Tus listas", Forma.VIDEO, lists.map { pl ->
                val line = countText(pl.count, "video", "videos")
                Tarjeta("list:" + pl.id, pl.title, Estilo.VIDEO, abs(pl.thumb), line, info = pl.title + "   ·   " + line)
            }, Vacio("Todavía no hay listas", "Salen cuando traes tus listas de YouTube a la computadora.", "Cómo traer tus listas", "takeout"))
            favoritos(filas, ytProgress)
            filas += Fila("Nuevos de tus canales", Forma.VIDEO, h?.new.orEmpty().map { videoTile(it, ytProgress) }, vacioNuevos(chans))
            filas += Fila("Tus canales", Forma.CANAL, chans.orEmpty().map { channelTile(it) },
                if (chans == null) Vacio("Cargando tus canales", "Pidiendo a la computadora tus suscripciones…")
                else Vacio("Todavía no hay canales", "Salen cuando traes tus suscripciones de YouTube a la computadora.", "Cómo traer tus suscripciones", "takeout"))
        }
        filas += Fila(becauseTitle(), Forma.VIDEO, h?.because.orEmpty().map { videoTile(it, ytProgress) }, vacioPorque())
        filas += Fila("Seguir viendo", Forma.VIDEO, h?.cont.orEmpty().map { videoTile(it, ytProgress) },
            Vacio("Ningún video a medias", "Si dejas un video a la mitad, sigue aquí.", "Buscar en YouTube", "ytsearch"))
        val recent = h?.recent.orEmpty().ifEmpty { lib.youtube }
        filas += Fila("Vistos hace poco", Forma.VIDEO, recent.map { videoTile(it, ytProgress) },
            Vacio("Todavía no hay videos vistos", "Lo que veas de YouTube en la TV queda aquí.", "Buscar en YouTube", "ytsearch"))
        return VistaFilas("youtube", "YouTube", filas, topButton = "Buscar en YouTube")
    }

    /** Canal de «Tus canales»; los anclados (ya vienen primero) llevan un punto limón. */
    fun channelTile(ch: Channel) = Tarjeta("chan:" + ch.id, ch.title, Estilo.CANAL, abs("/ytc/${ch.id}/avatar.png"), initials = initialsOf(ch.title),
        info = ch.title + (if (ch.pinned) "   ·   Anclado" else "") + "   ·   OK: ver sus videos", pinned = ch.pinned)

    private fun favoritos(filas: MutableList<Fila>, ytProgress: Map<String, Double>) {
        val favs = ytHome?.favorites.orEmpty()
        if (favs.isNotEmpty()) filas += Fila("Favoritos", Forma.VIDEO, favs.map { videoTile(it, ytProgress) })
    }

    /** La página de un canal: sus videos y, cuando llegan, «Anclar» o «Desanclar» y «Silenciar canal» (o, ya silenciado,
     *  «Volver a mostrar»). */
    fun canal(p: Pagina.Canal, d: PaginaVideos?, ytProgress: Map<String, Double>): VistaCuadricula {
        val title = d?.title?.ifEmpty { null } ?: p.title
        val key = "canal:" + p.id
        if (d?.videos == null) return VistaCuadricula(key, title, "", Forma.GRID_VIDEO, emptyList(),
            Vacio("Cargando los videos", "La primera vez tarda unos segundos."), chipsSegmentos = false, chipsPrincipal = false)
        val chips = if (d.hidden) listOf(Boton("unhide", "Volver a mostrar", "eye"))
        else listOf(if (d.pinned) Boton("unpin", "Desanclar", "pin-off") else Boton("pin", "Anclar", "pin"),
            Boton("hide", "Silenciar canal", "eye-off", danger = true))
        val tiles = d.videos.map { videoTile(it, ytProgress) }
        val vacio = if (d.error.isNotEmpty()) Vacio("No se pudo cargar", d.error) else Vacio("Este canal no tiene videos", "")
        return VistaCuadricula(key, title, countText(tiles.size, "video", "videos"), Forma.GRID_VIDEO, tiles, vacio, chips,
            chipsSegmentos = false, chipsPrincipal = false)
    }

    /** La página de una lista de YouTube: «Reproducir todo» y «A la fila». */
    fun listaYt(p: Pagina.ListaYt, d: PaginaVideos?, ytProgress: Map<String, Double>): VistaCuadricula {
        val title = d?.title?.ifEmpty { null } ?: p.title
        val key = "lista:" + p.id
        val chips = listOf(Boton("playall", "Reproducir todo", "play"), Boton("q-menu", "A la fila", "list-plus"))
        if (d?.videos == null) return VistaCuadricula(key, title, "", Forma.GRID_VIDEO, emptyList(),
            Vacio("Cargando la lista", "La primera vez tarda unos segundos."), chips, chipsSegmentos = false)
        val tiles = d.videos.map { videoTile(it, ytProgress) }
        val vacio = if (d.error.isNotEmpty()) Vacio("No se pudo cargar", d.error) else Vacio("Esta lista no tiene videos", "")
        return VistaCuadricula(key, title, countText(tiles.size, "video", "videos"), Forma.GRID_VIDEO, tiles, vacio, chips, chipsSegmentos = false)
    }

    /** Los canales silenciados en círculos; OK sobre uno lo vuelve a mostrar. */
    fun silenciados(hidden: List<Silenciado>?, error: Boolean): VistaCuadricula {
        val key = "silenciados"
        if (hidden == null) return VistaCuadricula(key, "Canales silenciados", "", Forma.CANAL, emptyList(),
            if (error) Vacio("No se pudo cargar", "Sin conexión con la computadora. Vuelve a intentarlo en un momento.")
            else Vacio("Cargando", "Pidiendo a la computadora tus canales silenciados…"))
        val tiles = hidden.map { ch ->
            val title = ch.title.ifEmpty { "Canal sin nombre" }
            Tarjeta("unhide:" + ch.id, title, Estilo.CANAL, null, initials = initialsOf(title), info = "$title   ·   OK: volver a mostrarlo en YouTube")
        }
        return VistaCuadricula(key, "Canales silenciados", countText(tiles.size, "canal", "canales"), Forma.CANAL, tiles,
            Vacio("No hay canales silenciados", "En la página de un canal, o con OK sostenido sobre uno de sus videos, elige «Silenciar canal»: deja de salir en Tus canales, en lo nuevo y en las recomendaciones.",
                "Ir a YouTube", "youtube"))
    }

    // ---------- Buscar ----------

    /** Títulos de películas y series que contienen lo escrito (sin importar acentos ni mayúsculas). */
    fun buscarBiblioteca(text: String): List<Tarjeta> {
        val q = plainText(text.trim())
        if (q.isEmpty()) return emptyList()
        val found = mutableListOf<Pair<String, Tarjeta>>()
        for (it in lib.items.values) if (it.kind == "movie" && plainText(it.title).contains(q)) itemTile(it.id)?.let { t -> found += it.title.lowercase() to t }
        for (show in lib.series) if (plainText(show.title).contains(q)) found += show.title.lowercase() to showTile(show)
        return found.sortedBy { it.first }.map { it.second }
    }

    // ---------- En vivo ----------

    fun enVivo(): VistaFilas {
        val tiles = lib.live.map { c ->
            Tarjeta("live:" + c.id, c.name, Estilo.VIDEO, abs(c.poster), c.host, info = c.name + "   ·   en vivo, sin anuncios")
        }
        return VistaFilas("envivo", "En vivo", listOf(Fila("Canales de hoy", Forma.VIDEO, tiles,
            Vacio("No hay canales en vivo", "Se agregan desde la web de One TV, en «En vivo».", "Buscar otra vez", "refresh"))))
    }

    // ---------- Música ----------

    /** Las canciones de cada fila de la sección (para saber qué sigue al elegir una). */
    fun recientes(n: Int = 30): List<String> {
        val m = music ?: return emptyList()
        return m.albums.sortedByDescending { it.added }.flatMap { it.tracks }.take(n)
    }

    fun songTile(ctx: String, i: Int, tid: String): Tarjeta? {
        val t = music?.tracks?.get(tid) ?: return null
        return Tarjeta("song:$ctx:$i", t.title, Estilo.VIDEO, abs(t.art), t.artist, dur = t.duration.toInt(),
            info = t.title + "   ·   " + t.artist + "   ·   " + t.album + "   ·   " + OPCIONES, menu = true)
    }

    fun musica(): VistaFilas {
        val m = music
        val filas = mutableListOf<Fila>()
        if (m == null || !m.ready) {
            val vacio = when {
                m == null && !musicError -> Vacio("Leyendo tu música", "La computadora está revisando la carpeta de música.")
                musicError -> Vacio("Sin música todavía", "No se pudo leer: sin conexión con la computadora.")
                else -> Vacio("Sin música todavía", "Pon tu música en la carpeta Música › Biblioteca de la computadora y aparece aquí sola, con sus portadas.")
            }
            filas += Fila("Música", Forma.CUADRADO, emptyList(), vacio)
            return VistaFilas("musica", "Música", filas)
        }
        if (m.playlists.isNotEmpty()) filas += Fila("Tus listas", Forma.CUADRADO, m.playlists.map { p ->
            val line = countText(p.tracks.size, "canción", "canciones")
            Tarjeta("mlist:" + p.id, p.title, Estilo.VIDEO, abs(p.art), line,
                info = p.title + "   ·   " + line + "   ·   OK: ver sus canciones   ·   Reproducir: escucharla")
        })
        filas += Fila("Agregadas hace poco", Forma.CUADRADO, recientes().mapIndexedNotNull { i, tid -> songTile("recent", i, tid) })
        filas += Fila("Artistas", Forma.CANAL, m.artists.map { ar ->
            Tarjeta("artist:" + ar.id, ar.name, Estilo.CANAL, abs(ar.art), initials = initialsOf(ar.name),
                info = ar.name + "   ·   " + countText(ar.albums.size, "álbum", "álbumes") + "   ·   OK: sus canciones")
        })
        filas += Fila("Álbumes", Forma.CUADRADO, m.albums.map { a ->
            var info = a.title + "   ·   " + a.artist
            if (a.year > 0) info += "   ·   " + a.year
            Tarjeta("album:" + a.id, a.title, Estilo.VIDEO, abs(a.art), a.artist, info = "$info   ·   OK: ver sus canciones   ·   Reproducir: escucharlo")
        })
        return VistaFilas("musica", "Música", filas)
    }

    fun musicaPaginaTracks(p: Pagina.MusicaPagina): List<String> {
        val m = music ?: return emptyList()
        return when (p.sub) {
            "album" -> m.albums.firstOrNull { it.id == p.id }?.tracks.orEmpty()
            "list" -> m.playlists.firstOrNull { it.id == p.id }?.tracks.orEmpty()
            "artist" -> m.artists.firstOrNull { it.id == p.id }?.albums.orEmpty().flatMap { aid -> m.albums.firstOrNull { it.id == aid }?.tracks.orEmpty() }
            else -> emptyList()
        }
    }

    fun musicaPagina(p: Pagina.MusicaPagina): VistaCuadricula {
        val ids = musicaPaginaTracks(p)
        return VistaCuadricula("musica:${p.sub}:${p.id}", p.title, countText(ids.size, "canción", "canciones"), Forma.GRID_CUADRADO,
            ids.mapIndexedNotNull { i, tid -> songTile("page", i, tid) },
            Vacio("Sin canciones", "Se movieron o se borraron de la carpeta de música."),
            listOf(Boton("m-play", "Escuchar", "play"), Boton("m-shuffle", "Aleatorio", "shuffle")), chipsSegmentos = false)
    }

    // ---------- Fila de reproducción, historial y ajustes generales ----------

    fun fila(hidden: List<Silenciado>?): VistaFilas {
        val filas = mutableListOf<Fila>()
        val q = lib.queue
        val title = if (q.isEmpty()) "En espera" else "En espera   ·   " + countText(q.size, "video", "videos")
        filas += Fila(title, Forma.VIDEO, q.mapIndexed { i, e ->
            val dur = if (e.kind == "yt") e.duration.toInt() else 0
            var info = e.title
            if (dur > 0) info += "   ·   " + fmtClock(dur.toDouble())
            Tarjeta("q:$i", e.title, Estilo.VIDEO, abs(e.thumb), "OK: verlo ahora", dur = dur, info = "$info   ·   mantén OK: mover o quitar", menu = true)
        }, Vacio("La fila está vacía", "En la ficha de cualquier película o video elige «A continuación» o «Al final de la fila».", "Elegir algo en Inicio", "home"))
        filas += Fila("Historial", Forma.VIDEO, lib.history.mapNotNull { h ->
            val id = if (h.kind == "yt") "yt:" + h.id else h.id
            if (h.kind != "yt" && lib.items[h.id] == null) return@mapNotNull null
            var sub = h.whenText
            var progress = 0f
            if (h.done) sub += " · vista" else if (h.duration > 0) progress = (h.p / h.duration).toFloat()
            Tarjeta(id, h.title, Estilo.VIDEO, abs(h.thumb), sub, progress, spanish = lib.items[h.id]?.dub == true,
                dur = if (h.kind == "yt") h.duration.toInt() else 0, info = h.title + "   ·   " + sub + "   ·   " + OPCIONES, menu = true)
        }.take(30), Vacio("Todavía no has visto nada", "Lo que veas aquí se anota con el día y la hora."))
        // Ajustes generales: dos segmentos para «Al terminar la fila» y «Mostrar el nombre del capítulo», y botones
        // para los canales silenciados de YouTube y para buscar lo nuevo.
        val autoplay = ytAutoplayOn(lib.prefs)
        val names = chapterTitlesOn(lib.prefs)
        filas += Fila("Ajustes generales", Forma.AJUSTE, listOf(
            Tarjeta("set:autoplay", "Al terminar la fila", Estilo.AJUSTE,
                ajuste = Ajuste(listOf("Detenerse", "Seguir con recomendados"), if (autoplay) 1 else 0),
                info = if (autoplay) "OK: cambiar   ·   Al acabar la fila siguen videos recomendados por YouTube, uno tras otro."
                else "OK: cambiar   ·   Al acabar la fila, la reproducción se detiene."),
            Tarjeta("set:chapters", "Mostrar el nombre del capítulo", Estilo.AJUSTE,
                ajuste = Ajuste(listOf("Sí", "No"), if (names) 0 else 1),
                info = if (names) "OK: cambiar   ·   En los videos de YouTube con capítulos, su nombre aparece unos segundos al empezar cada uno."
                else "OK: cambiar   ·   El nombre del capítulo no aparece; ‹ › siguen saltando de capítulo."),
            Tarjeta("set:hidden", "Canales silenciados", Estilo.AJUSTE, ajuste = Ajuste(emptyList(), 0, hiddenButtonText(hidden), "eye-off"),
                info = "OK: ver los canales de YouTube que silenciaste y volver a mostrarlos."),
            Tarjeta("set:reload", "Biblioteca", Estilo.AJUSTE, ajuste = Ajuste(emptyList(), 0, "Buscar películas y series nuevas", "refresh"),
                info = "Revisa las carpetas de la biblioteca y agrega lo nuevo."),
        ))
        return VistaFilas("fila", "Fila de reproducción", filas)
    }
}

/** Mostrar el nombre del capítulo de YouTube al empezar cada uno (ajuste general; si falta, sí). */
fun chapterTitlesOn(prefs: Map<String, String>) = prefs["chapterTitles"]?.let { it == "true" } ?: true

/** Al terminar la fila, seguir con videos recomendados por YouTube (ajuste general; si falta, no). */
fun ytAutoplayOn(prefs: Map<String, String>) = prefs["ytAutoplay"] == "true"

/** El botón del ajuste «Canales silenciados»: cuántos hay. */
fun hiddenButtonText(hidden: List<Silenciado>?): String = when {
    hidden == null -> "Ver los canales"
    hidden.isEmpty() -> "Ninguno silenciado"
    else -> "Ver " + countText(hidden.size, "canal", "canales")
}
