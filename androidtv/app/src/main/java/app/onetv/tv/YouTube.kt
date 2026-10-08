package app.onetv.tv

import app.onetv.tv.data.Entry
import app.onetv.tv.data.countText
import app.onetv.tv.data.parseChannels
import app.onetv.tv.data.parseEntry
import app.onetv.tv.data.parseHidden
import app.onetv.tv.data.parseVideos
import kotlinx.coroutines.launch
import org.json.JSONObject
import java.io.IOException

// YouTube completo, como roku/components/YouTube.brs, PlayerMenus.brs y Lists.brs: páginas de canal y de lista, anclar,
// silenciar y volver a mostrar un canal, «No me interesa», Favoritos y listas, las opciones de una tarjeta (OK sostenido,
// la tecla ✱ del Roku), lo que se hace con un video de la fila, «En vivo» y los ajustes generales.

/** «No se pudo silenciar el canal: sin conexión con la computadora.» (el texto de error del Roku, channelFailText). */
fun textoFallo(what: String, error: Exception?, r: JSONObject?): String {
    if (error != null) {
        if (error is IOException && error.message?.startsWith("El servidor respondió") == true) return "No se pudo $what: la computadora respondió con un error."
        return "No se pudo $what: sin conexión con la computadora."
    }
    val e = r?.optString("error", "").orEmpty()
    if (e.isNotEmpty()) return "No se pudo $what: $e"
    return "No se pudo $what."
}

/** POST que nunca falla: (respuesta, error). */
internal suspend fun Estado.enviar(path: String, body: JSONObject, timeoutMs: Int = 15000): Pair<JSONObject?, Exception?> = try {
    api.post(path, body.put("device_id", deviceId), timeoutMs) to null
} catch (e: Exception) {
    null to e
}

/** Título, canal y duración de cada video que pasa por la app (para la ficha y el reproductor). */
fun Estado.recordarYt(v: Entry) {
    val known = ytTitles[v.id]
    if (known == null) {
        ytTitles[v.id] = v
        return
    }
    ytTitles[v.id] = v.copy(
        title = v.title.ifEmpty { known.title }, channel = v.channel.ifEmpty { known.channel },
        duration = if (v.duration > 0) v.duration else known.duration, channelId = v.channelId.ifEmpty { known.channelId },
        published = if (v.published > 0) v.published else known.published, approx = if (v.published > 0) v.approx else known.approx,
        thumb = v.thumb.ifEmpty { known.thumb },
    )
}

/** El título de una tarjeta de la vista de ahora (para el título de la página que abre). */
fun Estado.tituloTarjeta(id: String): String = when (val v = vista) {
    is VistaFilas -> v.filas.flatMap { it.tarjetas }.firstOrNull { it.id == id }?.title
    is VistaCuadricula -> v.tarjetas.firstOrNull { it.id == id }?.title
    else -> null
}.orEmpty()

// ---------- páginas de canal y de lista ----------

fun Estado.cargarPagina(key: String, path: String, title: String) {
    val prev = paginaVideos[key]
    paginaVideos[key] = PaginaVideos(title = prev?.title ?: title, pinned = prev?.pinned ?: channels.orEmpty().any { it.id == key.substringAfter(":") && it.pinned })
    scope.launch {
        val got = try {
            api.get(path, 60000)
        } catch (_: Exception) {
            null
        }
        val old = paginaVideos[key] ?: PaginaVideos(title = title)
        paginaVideos[key] = when {
            got == null -> old.copy(videos = emptyList(), error = "No se pudo cargar: sin conexión con la computadora.")
            !got.optBoolean("ok", false) -> old.copy(videos = emptyList(), error = "YouTube: " + got.optString("error", ""),
                pinned = got.optBoolean("pinned", old.pinned), hidden = got.optBoolean("hidden", old.hidden))
            else -> {
                val videos = parseVideos(got.optJSONArray("videos"))
                for (v in videos) recordarYt(v)
                old.copy(videos = videos, error = "", title = got.optString("title", "").ifEmpty { old.title },
                    pinned = got.optBoolean("pinned", old.pinned), hidden = got.optBoolean("hidden", old.hidden))
            }
        }
    }
}

/** Los botones de arriba a la derecha de una página de canal o de lista. */
fun Estado.controlPagina(p: Pagina, id: String) {
    when (id) {
        "playall" -> if (p is Pagina.ListaYt) reproducirLista(p.id)
        "q-menu" -> if (p is Pagina.ListaYt) menuListaALaFila(p)
        "pin", "unpin" -> if (p is Pagina.Canal) anclar(p, id == "pin")
        "hide" -> if (p is Pagina.Canal) silenciarCanal(p)
        "unhide" -> if (p is Pagina.Canal) volverAMostrar(p.id)
    }
}

/** «Reproducir todo»: la computadora pone el primero ya y el resto al frente de la fila; si no puede, se hace aquí. */
fun Estado.reproducirLista(pid: String) {
    mostrarAviso("Preparando la lista…")
    scope.launch {
        val (r, _) = enviar("/api/yt/playlist/play", JSONObject().put("id", pid))
        if (r?.optBoolean("ok") == true) {
            mostrarAviso("Lista en la TV: " + countText(r.optInt("count"), "video", "videos") + " en camino.")
            return@launch
        }
        val got = try {
            api.get("/api/yt/playlist?id=$pid", 60000)
        } catch (_: Exception) {
            null
        }
        val videos = parseVideos(got?.optJSONArray("videos")).filter { !it.private }
        if (got?.optBoolean("ok") != true || videos.isEmpty()) {
            mostrarAviso("No se pudo reproducir la lista.", true)
            return@launch
        }
        for (v in videos) recordarYt(v)
        verYouTube(videos[0].id, 0.0)
        // El resto al frente de la fila, en orden: se agregan de uno en uno, del último al segundo.
        for (v in videos.drop(1).take(50).reversed()) {
            enviar("/api/queue/add", JSONObject().put("kind", "yt").put("id", v.id).put("title", v.title).put("front", true))
        }
        cargarBiblioteca()
    }
}

private fun Estado.anclar(p: Pagina.Canal, on: Boolean) {
    val key = "canal:" + p.id
    val title = paginaVideos[key]?.title?.ifEmpty { null } ?: p.title
    scope.launch {
        val (r, e) = enviar("/api/yt/channel/pin", JSONObject().put("id", p.id).put("title", title).put("on", on))
        if (r?.optBoolean("ok") != true) {
            mostrarAviso(textoFallo(if (on) "anclar el canal" else "desanclar el canal", e, r), true)
            return@launch
        }
        val pinned = r.optBoolean("pinned", on)
        paginaVideos[key]?.let { paginaVideos[key] = it.copy(pinned = pinned) }
        mostrarAviso(if (pinned) "Anclado: sale primero en Tus canales." else "Desanclado: vuelve a su lugar en Tus canales.")
        seguirCanal = p.id   // «Tus canales» se reordena (el orden lo pone la computadora) y el foco sigue al canal
        cargarCanales()
    }
}

/** Un OK silencia; se deshace en el mismo botón, que pasa a «Volver a mostrar». */
private fun Estado.silenciarCanal(p: Pagina.Canal) {
    val key = "canal:" + p.id
    val title = paginaVideos[key]?.title?.ifEmpty { null } ?: p.title
    mostrarAviso("Silenciando el canal…", auto = false)
    scope.launch {
        val (r, e) = enviar("/api/yt/channel/hide", JSONObject().put("id", p.id).put("title", title))
        if (r?.optBoolean("ok") != true) {
            mostrarAviso(textoFallo("silenciar el canal", e, r), true)
            return@launch
        }
        mostrarAviso("Canal silenciado: ya no sale en Tus canales, en lo nuevo ni en las recomendaciones.")
        channels = channels?.filter { it.id != p.id }
        paginaVideos[key]?.let { paginaVideos[key] = it.copy(hidden = true) }
        cargarCanales()
        cargarYouTube()
        cargarSilenciados()
    }
}

fun Estado.volverAMostrar(cid: String) {
    scope.launch {
        val (r, e) = enviar("/api/yt/channel/unhide", JSONObject().put("id", cid))
        if (r?.optBoolean("ok") != true) {
            mostrarAviso(textoFallo("volver a mostrar el canal", e, r), true)
            return@launch
        }
        val title = hidden?.firstOrNull { it.id == cid }?.title?.ifEmpty { null } ?: paginaVideos["canal:$cid"]?.title?.ifEmpty { null }
        mostrarAviso(if (title == null) "El canal vuelve a salir en YouTube." else "«$title» vuelve a salir en YouTube.")
        hidden = hidden?.filter { it.id != cid }
        paginaVideos["canal:$cid"]?.let { paginaVideos["canal:$cid"] = it.copy(hidden = false) }
        cargarSilenciados()
        cargarCanales()
        cargarYouTube()
    }
}

fun Estado.cargarCanales() {
    scope.launch {
        try {
            channels = parseChannels(api.get("/api/yt/subscriptions"))
            val follow = seguirCanal
            if (follow.isNotEmpty()) {
                // Recién anclado o desanclado: el foco de «Tus canales» lo sigue a su nuevo lugar.
                val v = datos?.youtube(channels, ytProgress)
                val r = v?.filas?.indexOfFirst { it.title == "Tus canales" } ?: -1
                val c = channels?.indexOfFirst { it.id == follow } ?: -1
                if (r >= 0 && c >= 0) focoFilas["youtube"] = r to c
                seguirCanal = ""
            }
        } catch (_: Exception) {
        }
    }
}

fun Estado.cargarSilenciados() {
    scope.launch {
        try {
            hidden = parseHidden(api.get("/api/yt/hidden"))
            hiddenError = false
        } catch (_: Exception) {
            if (hidden == null) hiddenError = true
        }
    }
}

// ---------- «No me interesa» y «Silenciar canal» desde un video ----------

fun Estado.noMeInteresa(vid: String, desdeFicha: Boolean) {
    scope.launch {
        val (r, e) = enviar("/api/yt/dismiss", JSONObject().put("id", vid))
        if (r?.optBoolean("ok") != true) {
            val t = textoFallo("quitarlo de las recomendaciones", e, r)
            if (desdeFicha) mensajeFicha(t, true) else mostrarAviso(t, true)
            return@launch
        }
        if (desdeFicha) mensajeFicha("Listo: este video ya no se te va a recomendar.") else mostrarAviso("Listo: no se te volverá a recomendar.")
        cargarYouTube()
        cargarBiblioteca()
    }
}

fun Estado.silenciarDesdeVideo(vid: String, desdeFicha: Boolean) {
    if (desdeFicha) mensajeFicha("Silenciando el canal…") else mostrarAviso("Silenciando el canal…", auto = false)
    val info = ytTitles[vid]
    val body = JSONObject().put("video", vid)
    if (info != null && info.channelId.isNotEmpty()) body.put("id", info.channelId)
    if (info != null && info.channel.isNotEmpty()) body.put("title", info.channel)
    scope.launch {
        val (r, e) = enviar("/api/yt/channel/hide", body, 60000)
        if (r?.optBoolean("ok") != true) {
            val t = textoFallo("silenciar el canal", e, r)
            if (desdeFicha) mensajeFicha(t, true) else mostrarAviso(t, true)
            return@launch
        }
        val title = r.optString("title", "")
        val name = if (title.isNotEmpty()) "«$title»" else "El canal"
        if (desdeFicha) mensajeFicha("$name quedó silenciado: ya no sale en tus canales, en lo nuevo ni en las recomendaciones.")
        else mostrarAviso("$name ya no sale en tus canales, en lo nuevo ni en las recomendaciones.")
        val cid = r.optString("id", "")
        if (cid.isNotEmpty()) channels = channels?.filter { it.id != cid }
        cargarCanales()
        cargarYouTube()
        cargarSilenciados()
        cargarBiblioteca()
    }
}

/** «Agregar a En vivo» en la ficha de una transmisión: su canal queda en «En vivo». */
fun Estado.agregarAEnVivo(vid: String) {
    mostrarAviso("Agregando el canal a En vivo…")
    scope.launch {
        val (r, e) = enviar("/api/live/add", JSONObject().put("url", "https://youtu.be/$vid"), 60000)
        if (r?.optBoolean("ok") != true) {
            mostrarAviso(textoFallo("agregar el canal", e, r), true)
            return@launch
        }
        mostrarAviso("«" + (r.optJSONObject("channel")?.optString("name", "") ?: "") + "» ya está en En vivo.")
        cargarBiblioteca()
    }
}

// ---------- Favoritos y listas ----------

/** Al abrir la ficha: en qué listas está el video (Favoritos incluido), para su botón y para «Agregar a lista». */
fun Estado.cargarListasDelVideo(vid: String) {
    scope.launch {
        val got = try {
            api.get("/api/lists?video=$vid")
        } catch (_: Exception) {
            null
        }
        val arr = got?.optJSONArray("lists")
        if (got == null || !got.optBoolean("ok", true) || arr == null) {
            if (listsWant == vid) {
                listsWant = ""
                mostrarAviso("No se pudieron leer tus listas: sin conexión con la computadora.", true)
            }
            return@launch
        }
        val lists = (0 until arr.length()).mapNotNull { arr.optJSONObject(it) }
        vidLists = vid to lists
        lists.firstOrNull { it.optString("id") == "fav" }?.let { favs[vid] = it.optBoolean("has") }
        if (ficha?.kind == "yt" && ficha?.id == vid) fichaYouTube(vid, true)
        if (listsWant == vid) {
            listsWant = ""
            abrirListas(0)
        }
    }
}

private fun Estado.marcarEnLista(vid: String, listId: String, has: Boolean) {
    val (v, lists) = vidLists ?: return
    if (v != vid) return
    for (l in lists) if (l.optString("id") == listId && l.optBoolean("has") != has) {
        l.put("has", has)
        l.put("count", l.optInt("count") + if (has) 1 else -1)
    }
}

/** El botón Favorito cambia al instante; si la computadora no lo guarda, vuelve como estaba y lo dice. */
fun Estado.pulsarFavorito(vid: String) {
    val on = favs[vid] != true
    favs[vid] = on
    marcarEnLista(vid, "fav", on)
    fichaYouTube(vid, true)
    scope.launch {
        val (r, e) = enviar("/api/lists/toggle", JSONObject().put("list", "fav").put("id", vid).put("on", on).put("title", ytTitles[vid]?.title.orEmpty()))
        if (r?.optBoolean("ok") != true) {
            favs[vid] = !on
            marcarEnLista(vid, "fav", !on)
            if (ficha?.id == vid) fichaYouTube(vid, true)
            mostrarAviso(textoFallo("guardar en Favoritos", e, r), true)
            return@launch
        }
        mostrarAviso(if (on) "Agregado a Favoritos." else "Quitado de Favoritos.")
        cargarYouTube()
    }
}

/** «Agregar a lista»: la lista para elegir; si todavía no llegan las listas del video, se abre en cuanto lleguen. */
fun Estado.agregarALista(vid: String) {
    if (vidLists?.first != vid) {
        listsWant = vid
        mostrarAviso("Leyendo tus listas…")
        cargarListasDelVideo(vid)
        return
    }
    abrirListas(0)
}

private fun Estado.abrirListas(foco: Int) {
    val (vid, lists) = vidLists ?: return
    if (aviso == "Leyendo tus listas…") ocultarAviso()
    val opciones = listOf(Opcion("Lista nueva", "Escribir el nombre: este video queda en ella", "plus", "new")) + lists.map { l ->
        var count = countText(l.optInt("count"), "video", "videos")
        if (l.optString("source") == "takeout") count += "   ·   de tu cuenta de YouTube"
        val has = l.optBoolean("has")
        val id = l.optString("id")
        Opcion(if (id == "fav") "Favoritos" else l.optString("title"), if (has) "Está en esta lista   ·   $count" else count,
            if (has) "check" else if (id == "fav") "heart" else "list-video", "list:$id")
    }
    abrirLista(Lista("Agregar a lista", "«" + (ytTitles[vid]?.title ?: "YouTube") + "». Se guarda en la computadora: no cambia tu cuenta de YouTube.",
        opciones, Vacio("Todavía no hay listas", "Crea una desde la web de One TV."), ctx = "listas",
        hint = "OK: agregar o quitar   ·   ‹ o Atrás: cerrar"), foco)
}

/** OK sobre una lista: agrega o quita (la lista sigue abierta y el foco en el mismo renglón), o pide el nombre. */
fun Estado.elegirLista(accion: String) {
    val (vid, lists) = vidLists ?: return
    if (accion == "new") {
        listaNueva = ""
        return
    }
    val listId = accion.removePrefix("list:")
    val row = lists.indexOfFirst { it.optString("id") == listId } + 1   // el renglón 0 es «Lista nueva»
    val target = lists.getOrNull(row - 1) ?: return
    val on = !target.optBoolean("has")
    marcarEnLista(vid, listId, on)
    if (listId == "fav") {
        favs[vid] = on
        if (ficha?.id == vid) fichaYouTube(vid, true)
    }
    abrirListas(row)
    scope.launch {
        val (r, e) = enviar("/api/lists/toggle", JSONObject().put("list", listId).put("id", vid).put("on", on).put("title", ytTitles[vid]?.title.orEmpty()))
        if (r?.optBoolean("ok") != true) {
            marcarEnLista(vid, listId, !on)
            if (listId == "fav") favs[vid] = !on
            if (lista?.ctx == "listas") abrirListas(row)
            mostrarAviso(textoFallo("cambiar la lista", e, r), true)
            return@launch
        }
        cargarYouTube()
    }
}

// ---------- OK sostenido sobre una tarjeta ----------

/** -> false si esa tarjeta no tiene opciones. */
fun Estado.abrirMenuTarjeta(id: String): Boolean {
    if (id.startsWith("q:")) {
        menuFila(id.removePrefix("q:").toIntOrNull() ?: return false)
        return true
    }
    val opciones = mutableListOf<Opcion>()
    val title: String
    when {
        id.startsWith("yt:") -> {
            val vid = id.removePrefix("yt:")
            val info = ytTitles[vid]
            title = info?.title?.ifEmpty { null } ?: "YouTube"
            val channel = info?.channel.orEmpty()
            opciones += Opcion("Ver ahora", "", "play", "play")
            if (info?.live != true) {
                opciones += Opcion("A continuación", "Sigue después de lo que se ve", "list-start", "next")
                opciones += Opcion("Al final de la fila", "", "list-plus", "end")
            }
            opciones += Opcion("Agregar a una lista o a Favoritos", "", "bookmark-plus", "lists")
            opciones += Opcion("No me interesa", "No se te vuelve a recomendar", "ban", "dismiss")
            opciones += Opcion(if (channel.isNotEmpty()) "Silenciar «$channel»" else "Silenciar este canal",
                "No sale en tus canales, en lo nuevo ni en las recomendaciones", "eye-off", "mute")
            tileMenu = mapOf("kind" to "yt", "id" to vid, "title" to title)
        }
        id.startsWith("song:") -> {
            val parts = id.split(":")
            val ctx = parts.getOrNull(1) ?: return false
            val i = parts.getOrNull(2)?.toIntOrNull() ?: return false
            val songs = if (ctx == "recent") datos?.recientes().orEmpty() else cancionesDePagina()   // Musica.kt
            val t = songs.getOrNull(i) ?: return false
            title = t.title + " · " + t.artist
            opciones += Opcion("Escuchar ahora", "Siguen las demás de aquí", "play", "play")
            opciones += Opcion("A continuación", "Sigue después de lo que se ve", "list-start", "next")
            opciones += Opcion("Al final de la fila", "", "list-plus", "end")
            tileMenu = mapOf("kind" to "track", "id" to t.id, "title" to title, "tile" to id)
        }
        lib?.items?.containsKey(id) == true -> {
            title = lib?.items?.get(id)?.fullTitle.orEmpty()
            opciones += Opcion("Ver ahora", "", "play", "play")
            opciones += Opcion("A continuación", "Sigue después de lo que se ve", "list-start", "next")
            opciones += Opcion("Al final de la fila", "", "list-plus", "end")
            tileMenu = mapOf("kind" to "item", "id" to id, "title" to title)
        }
        else -> return false
    }
    abrirLista(Lista("Opciones", title, opciones, Vacio("", ""), ctx = "tarjeta"))
    return true
}

fun Estado.elegirEnMenuTarjeta(accion: String) {
    lista = null
    val t = tileMenu ?: return
    val kind = t["kind"].orEmpty()
    val id = t["id"].orEmpty()
    when (accion) {
        "play" -> when (kind) {
            "yt" -> verYouTube(id, -1.0)
            "track" -> activar(t["tile"].orEmpty(), false)
            else -> empezarItem(id, true)
        }
        "next", "end" -> scope.launch {
            val (r, e) = enviar("/api/queue/add", JSONObject().put("kind", kind).put("id", id).put("title", t["title"].orEmpty()).put("front", accion == "next"))
            when {
                e != null -> mostrarAviso("No se pudo agregar: sin conexión con la computadora.", true)
                r?.optBoolean("ok") == true -> {
                    val where = if (accion == "next") "Sigue después de lo que se ve" else "Al final de la fila"
                    mostrarAviso(where + " (" + countText(r.optInt("count"), "en espera", "en espera") + ").")
                    cargarBiblioteca()
                }
                else -> mostrarAviso(r?.optString("error", "").orEmpty().ifEmpty { "No se pudo agregar." }, true)
            }
        }
        "lists" -> {
            listsWant = id
            if (vidLists?.first == id) {
                listsWant = ""
                abrirListas(0)
            } else {
                mostrarAviso("Leyendo tus listas…")
                cargarListasDelVideo(id)
            }
        }
        "dismiss" -> noMeInteresa(id, desdeFicha = false)
        "mute" -> silenciarDesdeVideo(id, desdeFicha = false)
    }
}

// ---------- un video de la fila: verlo, subirlo, bajarlo o quitarlo ----------

private fun Estado.menuFila(index: Int) {
    val queue = lib?.queue.orEmpty()
    val q = queue.getOrNull(index) ?: return
    val last = queue.size - 1
    val place = if (index > 0) "En ${index + 1}.º lugar de ${queue.size}." else "Sigue después de lo que se ve ahora."
    queueMenuAt = index
    abrirLista(Lista("En la fila", "«${q.title}». $place", listOf(
        Opcion("Ver ahora", "Empieza en la TV y sale de la fila", "play", "take"),
        Opcion("Subir al principio", "Sigue después de lo que se ve ahora", "list-start", "move:0", disabled = index == 0),
        Opcion("Subir un lugar", "", "arrow-up", "move:${index - 1}", disabled = index == 0),
        Opcion("Bajar un lugar", "", "arrow-down", "move:${index + 1}", disabled = index == last),
        Opcion("Mover al final", "", "list-plus", "move:$last", disabled = index == last),
        Opcion("Quitar de la fila", "", "x", "remove"),
    ), Vacio("", ""), ctx = "fila"))
}

fun Estado.elegirEnMenuFila(accion: String) {
    lista = null
    val index = queueMenuAt
    queueMenuAt = -1
    if (index < 0) return
    if (accion == "take") {
        tomarDeLaFila(index)
        return
    }
    val (path, body) = if (accion == "remove") "/api/queue/remove" to JSONObject().put("index", index)
    else "/api/queue/move" to JSONObject().put("index", index).put("to", accion.removePrefix("move:").toIntOrNull() ?: return)
    scope.launch {
        val (r, e) = enviar(path, body)
        if (r?.optBoolean("ok") != true || r.optJSONArray("queue") == null) {
            mostrarAviso(textoFallo("cambiar la fila", e, r), true)
            return@launch
        }
        // La computadora manda la fila nueva: el foco queda en el video que se movió (o, si se quitó, en el que ocupa su lugar).
        val queue = r.optJSONArray("queue").let { arr -> (0 until arr!!.length()).mapNotNull { arr.optJSONObject(it) }.map { parseEntry(it, "item") } }
        lib = lib?.copy(queue = queue)
        val at = r.optInt("index", index).coerceAtMost((queue.size - 1).coerceAtLeast(0))
        if (seccion == Seccion.FILA && paginas.isEmpty() && queue.isNotEmpty()) focoFilas["fila"] = 0 to at
        cargarBiblioteca()
    }
}

// ---------- una lista entera a la fila ----------

private fun Estado.menuListaALaFila(p: Pagina.ListaYt) {
    listQueueId = p.id
    val title = paginaVideos["lista:" + p.id]?.title?.ifEmpty { null } ?: p.title
    abrirLista(Lista("A la fila", "La lista «$title» entera, sin reproducir nada.", listOf(
        Opcion("A continuación", "Después de lo que se ve ahora, en su orden", "list-start", "front"),
        Opcion("Al final de la fila", "Después de lo que ya está en la fila", "list-plus", "end"),
        Opcion("Al azar, al final de la fila", "En desorden", "shuffle", "shuffle"),
    ), Vacio("", ""), ctx = "listq"))
}

fun Estado.elegirListaALaFila(accion: String) {
    lista = null
    val front = accion == "front"
    mostrarAviso("Agregando la lista a la fila…")
    scope.launch {
        val (r, e) = enviar("/api/queue/add_list", JSONObject().put("id", listQueueId).put("front", front).put("shuffle", accion == "shuffle"), 60000)
        if (r?.optBoolean("ok") != true) {
            mostrarAviso(textoFallo("agregar la lista a la fila", e, r), true)
            return@launch
        }
        val where = if (front) "a continuación" else "al final de la fila"
        val added = r.optInt("added")
        val total = r.optInt("total", added)
        mostrarAviso(if (added < total) "$added de $total videos $where (la fila ya no tiene lugar)." else countText(added, "video", "videos") + " $where.")
        cargarBiblioteca()
    }
}

// ---------- En vivo y ajustes generales ----------

/** Canal en vivo: la computadora trae el video de la página (sin anuncios) y la TV lo reproduce como directo. */
fun Estado.verEnVivo(cid: String) {
    // Su nombre, si la biblioteca ya lo trae (una orden de la computadora puede llegar con un canal recién agregado).
    val name = lib?.live?.firstOrNull { it.id == cid }?.name?.ifEmpty { null } ?: "En vivo"
    cur = Actual("live:$cid")
    ficha = null
    menuAbierto = false
    reproductor.empezar(Peticion(id = "live:$cid", title = name, url = api.url("/live/" + java.net.URLEncoder.encode(cid, "UTF-8") + "/index.m3u8"),
        hls = true, startAt = 0.0, duration = 0.0, live = true))
}

fun Estado.ajuste(name: String) {
    val l = lib ?: return
    when (name) {
        "autoplay" -> {
            val on = !ytAutoplayOn(l.prefs)
            lib = l.copy(prefs = l.prefs + ("ytAutoplay" to on.toString()))
            scope.launch { enviar("/api/yt/autoplay", JSONObject().put("on", on)) }
            mostrarAviso(if (on) "Al terminar la fila seguirán videos recomendados por YouTube, uno tras otro." else "Al terminar la fila se detiene la reproducción.")
        }
        "chapters" -> {
            val on = !chapterTitlesOn(l.prefs)
            lib = l.copy(prefs = l.prefs + ("chapterTitles" to on.toString()))
            scope.launch { enviar("/api/prefs", JSONObject().put("chapterTitles", on)) }
            mostrarAviso(if (on) "En los videos de YouTube con capítulos, su nombre aparecerá al empezar cada uno."
            else "El nombre del capítulo ya no aparecerá; al pausar se ven los capítulos sobre la barra.")
        }
        "hidden" -> abrirPagina(Pagina.Silenciados)
        "computadora" -> cambiarComputadora()
        "reload" -> {
            mostrarAviso("Actualizando la biblioteca…")
            scope.launch {
                enviar("/api/rescan", JSONObject(), 120000)
                mostrarAviso("Biblioteca actualizada.")
                cargarBiblioteca()
            }
        }
    }
}

/** «Lista nueva»: con el nombre escrito se crea con este video adentro; la lista para elegir vuelve con ella marcada. */
fun Estado.crearLista(nombre: String) {
    val name = nombre.trim()
    if (name.isEmpty()) return   // sin nombre no se crea: el campo sigue abierto
    val vid = vidLists?.first ?: return
    listaNueva = null
    scope.launch {
        val (r, e) = enviar("/api/lists/create", JSONObject().put("title", name).put("id", vid).put("video_title", ytTitles[vid]?.title.orEmpty()))
        if (r?.optBoolean("ok") != true) {
            mostrarAviso(textoFallo("crear la lista", e, r), true)
            return@launch
        }
        mostrarAviso("Lista nueva: «" + (r.optJSONObject("list")?.optString("title", name) ?: name) + "», con este video.")
        listsWant = vid   // se vuelve a abrir con la lista nueva marcada
        cargarListasDelVideo(vid)
        cargarYouTube()
    }
}
