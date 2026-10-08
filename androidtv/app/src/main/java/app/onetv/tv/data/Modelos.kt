package app.onetv.tv.data

import org.json.JSONArray
import org.json.JSONObject

// Lo que manda el servidor (mac/server.py), leído tal cual lo usa la app del Roku. Si falta un dato, se usa un valor
// vacío en lugar de fallar: un servidor un poco más viejo o más nuevo sigue funcionando.

data class Track(
    val name: String,
    val label: String,
    val lang: String,
    val original: Boolean? = null,
    val hls: String = "",        // audio: la dirección del video con esta pista (cuando no se reproduce directo)
    val ext: Boolean = false,    // audio: pista aparte (doblaje agregado), siempre llega por el servidor
    val url: String = "",        // subtítulos: dirección del archivo .srt
    val forced: Boolean = false,
)

data class Direct(val url: String, val format: String)

data class Item(
    val id: String,
    val title: String,
    val fullTitle: String,
    val kind: String,            // movie | episode
    val show: String = "",
    val season: Int = 0,
    val ep: String = "",
    val epTitle: String = "",
    val next: String = "",
    val duration: Double = 0.0,
    val poster: String = "",
    val art: String = "",
    val direct: Direct? = null,
    val audio: List<Track> = emptyList(),
    val subs: List<Track> = emptyList(),
    val audioDefault: Int = 0,
    val dub: Boolean = false,
    val mode: String = "",
    val convertReason: String = "",
)

data class Season(val title: String, val items: List<String>)

data class Show(val key: String, val title: String, val art: String, val poster: String, val dub: Boolean, val seasons: List<Season>)

/** Un renglón de «Seguir viendo», la fila, el historial o una fila de YouTube. */
data class Entry(
    val kind: String,            // item | yt | track
    val id: String,
    val title: String = "",
    val thumb: String = "",
    val p: Double = 0.0,
    val duration: Double = 0.0,
    val channel: String = "",
    val published: Long = 0,
    val live: Boolean = false,
    val whenText: String = "",   // historial: «hoy 21:04»
    val done: Boolean = false,
    val channelId: String = "",  // YouTube: el canal (para «Silenciar canal» y «Agregar a En vivo»)
    val viewers: Int = 0,        // transmisión en vivo: cuántos la ven
    val private: Boolean = false,
    val approx: Boolean = false, // la fecha de publicación es aproximada («hace 3 años»)
)

/** Un canal de «En vivo» (/api/library, campo live). */
data class LiveChannel(val id: String, val name: String, val host: String, val poster: String)

/** Una marca para saltar (la intro de una serie): de start a end, con su texto («Saltar intro»). */
data class Marca(val start: Double, val end: Double, val label: String)

/** Un doblaje de YouTube que se puede pedir (/api/yt/info, campo dubs). */
data class Doblaje(val lang: String, val name: String)

data class Library(
    val items: Map<String, Item>,
    val series: List<Show>,
    val recent: List<String>,            // «Recién agregadas» (películas)
    val cont: List<Entry>,               // «Seguir viendo»: biblioteca y YouTube juntos
    val keepWatching: List<Pair<String, Double>>,
    val progress: Map<String, Double>,   // id -> segundos donde se quedó
    val seen: Set<String>,
    val queue: List<Entry>,
    val history: List<Entry>,
    val prefs: Map<String, String>,
    val youtube: List<Entry>,
    val live: List<LiveChannel> = emptyList(),
)

data class Playlist(val id: String, val title: String, val count: Int, val thumb: String)
data class Channel(val id: String, val title: String, val pinned: Boolean)

/** Lo que se sabe de un canal silenciado (/api/yt/hidden). */
data class Silenciado(val id: String, val title: String)

data class YtHome(
    val cont: List<Entry>,
    val new: List<Entry>,
    val becauseSeed: String,
    val because: List<Entry>,
    val recent: List<Entry>,
    val playlists: List<Playlist>,
    val favorites: List<Entry>,
)

data class Song(val id: String, val title: String, val artist: String, val album: String, val duration: Double, val url: String, val art: String)

// La música llega por partes (mac/music.py): álbumes, artistas y listas sin sus canciones (solo cuántas tienen).
data class Album(val id: String, val title: String, val artist: String, val year: Int, val count: Int, val art: String, val added: Long)
data class Artist(val id: String, val name: String, val count: Int, val art: String)
data class MusicList(val id: String, val title: String, val count: Int, val art: String)
data class Totales(val artists: Int = 0, val albums: Int = 0, val tracks: Int = 0, val playlists: Int = 0)

/** Lo de la sección Música (/api/music/home): tus listas, lo agregado hace poco (ya con sus canciones), la primera
 *  tanda de artistas y de álbumes y cuántos hay de cada cosa. Lo demás llega con /api/music/more. */
data class Music(
    val counts: Totales,
    val playlists: List<MusicList>,
    val recent: List<Song>,
    val artists: List<Artist>,
    val albums: List<Album>,
    val reading: Boolean = false,   // la primera vez con mucha música: la computadora todavía la está leyendo
) {
    val ready get() = counts.albums > 0
    fun cuantos(kind: String) = when (kind) {
        "artists" -> artists.size to counts.artists
        "albums" -> albums.size to counts.albums
        else -> playlists.size to counts.playlists
    }
}

/** La página de un álbum, un artista o una lista (/api/music/page): las canciones traídas hasta ahora (llegan por
 *  tandas) y cuántas tiene. error: no se pudo leer ("conexion") o ya no está ("gone"). */
data class MusicPage(
    val kind: String,
    val id: String,
    val title: String,
    val total: Int,
    val songs: List<Song>,
    val error: String = "",
) {
    val completa get() = songs.size >= total
}

// ---------- lectura ----------

private fun JSONObject.str(key: String) = if (isNull(key)) "" else optString(key, "")
private fun JSONObject.num(key: String) = if (isNull(key)) 0.0 else optDouble(key, 0.0).let { if (it.isNaN()) 0.0 else it }
private fun JSONObject.flag(key: String) = optBoolean(key, false)

private inline fun <T> JSONArray?.list(block: (JSONObject) -> T?): List<T> {
    if (this == null) return emptyList()
    val out = ArrayList<T>(length())
    for (i in 0 until length()) {
        val o = optJSONObject(i) ?: continue
        block(o)?.let(out::add)
    }
    return out
}

private fun JSONArray?.strings(): List<String> {
    if (this == null) return emptyList()
    return (0 until length()).mapNotNull { i -> optString(i, "").ifEmpty { null } }
}

fun parseTrack(o: JSONObject) = Track(
    name = o.str("name"), label = o.str("label"), lang = o.str("lang"),
    original = if (o.has("original") && !o.isNull("original")) o.optBoolean("original") else null,
    hls = o.str("hls"), ext = o.flag("ext"), url = o.str("url"), forced = o.flag("forced"),
)

fun parseItem(o: JSONObject): Item {
    val direct = o.optJSONObject("direct")?.let { Direct(it.str("url"), it.str("format")) }
    return Item(
        id = o.str("id"), title = o.str("title"), fullTitle = o.str("full_title").ifEmpty { o.str("title") },
        kind = o.str("kind"), show = o.str("show"), season = o.optInt("season", 0), ep = o.str("ep"),
        epTitle = o.str("ep_title"), next = o.str("next"), duration = o.num("duration"), poster = o.str("poster"),
        art = o.str("art"), direct = direct, audio = o.optJSONArray("audio").list(::parseTrack),
        subs = o.optJSONArray("subs").list(::parseTrack), audioDefault = o.optInt("audio_default", 0),
        dub = o.flag("dub"), mode = o.str("mode"), convertReason = o.str("convert_reason"),
    )
}

fun parseEntry(o: JSONObject, defaultKind: String = "item") = Entry(
    kind = o.str("kind").ifEmpty { defaultKind }, id = o.str("id"), title = o.str("title"), thumb = o.str("thumb"),
    p = o.num("p"), duration = o.num("duration"), channel = o.str("channel"), published = o.optLong("published", 0),
    live = o.flag("live"), whenText = o.str("when"), done = o.flag("done"), channelId = o.str("channel_id"),
    viewers = o.optInt("viewers", 0), private = o.flag("private"), approx = o.flag("published_approx"),
)

fun parseLibrary(o: JSONObject): Library {
    val items = LinkedHashMap<String, Item>()
    o.optJSONObject("items")?.let { all ->
        for (key in all.keys()) all.optJSONObject(key)?.let { items[key] = parseItem(it) }
    }
    val series = o.optJSONArray("series").list { s ->
        Show(
            key = s.str("key"), title = s.str("title"), art = s.str("art"), poster = s.str("poster"), dub = s.flag("dub"),
            seasons = s.optJSONArray("seasons").list { se ->
                Season(se.str("title"), se.optJSONArray("items").list { e -> e.str("id").ifEmpty { null } })
            },
        )
    }
    val movieRows = o.optJSONArray("movies").list { r -> r }
    val recent = movieRows.firstOrNull { it.str("title") == "Recién agregadas" }
        ?.optJSONArray("items").list { e -> e.str("id").ifEmpty { null } }
    val progress = HashMap<String, Double>()
    o.optJSONArray("watching").list { w -> progress[w.str("id")] = w.num("p") }
    val prefs = HashMap<String, String>()
    o.optJSONObject("prefs")?.let { p -> for (k in p.keys()) prefs[k] = p.optString(k, "") }
    return Library(
        items = items, series = series, recent = recent,
        cont = o.optJSONArray("continue").list { parseEntry(it) },
        keepWatching = o.optJSONArray("keep_watching").list { k -> k.str("id") to k.num("p") },
        progress = progress, seen = o.optJSONArray("seen").strings().toSet(),
        queue = o.optJSONArray("queue").list { parseEntry(it, "item") },
        history = o.optJSONArray("history").list { parseEntry(it, "item") },
        prefs = prefs, youtube = o.optJSONArray("youtube").list { parseEntry(it, "yt") },
        live = o.optJSONArray("live").list { c -> LiveChannel(c.str("id"), c.str("name"), c.str("host"), c.str("poster")) },
    )
}

fun parseYtHome(o: JSONObject): YtHome {
    val because = o.optJSONArray("because").list { it }.firstOrNull()
    return YtHome(
        cont = o.optJSONArray("continue").list { parseEntry(it, "yt") },
        new = o.optJSONArray("new").list { parseEntry(it, "yt") },
        becauseSeed = because?.optJSONObject("seed")?.str("title").orEmpty(),
        because = because?.optJSONArray("videos").list { parseEntry(it, "yt") },
        recent = o.optJSONArray("recent").list { parseEntry(it, "yt") },
        playlists = o.optJSONArray("playlists").list { p -> Playlist(p.str("id"), p.str("title"), p.optInt("count", 0), p.str("thumb")) },
        favorites = o.optJSONArray("favorites").list { parseEntry(it, "yt") },
    )
}

fun parseChannels(o: JSONObject) = o.optJSONArray("channels").list { c -> Channel(c.str("id"), c.str("title"), c.flag("pinned")) }

fun parseHidden(o: JSONObject) = o.optJSONArray("channels").list { c -> Silenciado(c.str("id"), c.str("title")) }

/** Videos de un canal, de una lista o de una búsqueda (/api/yt/channel, /api/yt/playlist, /api/yt/search). */
fun parseVideos(arr: JSONArray?) = arr.list { parseEntry(it, "yt") }

/** /api/marks: solo lo que se puede saltar (la intro); los capítulos de YouTube van aparte. */
fun parseMarks(o: JSONObject) = o.optJSONArray("marks").list { m ->
    val start = m.num("start")
    val end = m.num("end")
    if (m.str("kind") == "chapter" || !m.has("start") || !m.has("end") || end <= start) null
    else Marca(start, end, m.str("label").ifEmpty { "Saltar intro" })
}

fun parseDubs(o: JSONObject) = o.optJSONArray("dubs").list { d -> d.str("lang").ifEmpty { null }?.let { Doblaje(it, d.str("name").ifEmpty { it }) } }

fun parseSong(t: JSONObject) = Song(t.str("id"), t.str("title"), t.str("artist"), t.str("album"), t.num("duration"), t.str("url"), t.str("art"))

fun parseSongs(arr: JSONArray?) = arr.list { t -> parseSong(t).takeIf { it.id.isNotEmpty() } }

fun parseAlbum(a: JSONObject) = Album(a.str("id"), a.str("title"), a.str("artist"), a.optInt("year", 0), a.optInt("count", 0), a.str("art"), a.optLong("added", 0))

fun parseArtist(a: JSONObject) = Artist(a.str("id"), a.str("name"), a.optInt("count", 0), a.str("art"))

fun parseMusicList(p: JSONObject) = MusicList(p.str("id"), p.str("title"), p.optInt("count", 0), p.str("art"))

/** Una tanda de /api/music/more (artistas, álbumes o listas). */
fun parseMusicItems(kind: String, arr: JSONArray?): List<Any> = when (kind) {
    "artists" -> arr.list { parseArtist(it) }
    "albums" -> arr.list { parseAlbum(it) }
    else -> arr.list { parseMusicList(it) }
}

/** /api/music/home. */
fun parseMusic(o: JSONObject): Music {
    val c = o.optJSONObject("counts") ?: JSONObject()
    return Music(
        counts = Totales(c.optInt("artists", 0), c.optInt("albums", 0), c.optInt("tracks", 0), c.optInt("playlists", 0)),
        playlists = o.optJSONArray("playlists").list { parseMusicList(it) },
        recent = parseSongs(o.optJSONArray("recent")),
        artists = o.optJSONArray("artists").list { parseArtist(it) },
        albums = o.optJSONArray("albums").list { parseAlbum(it) },
        reading = o.flag("reading"),
    )
}

/** /api/music/page: la página con su tanda de canciones (o la marca de que ya no está). */
fun parseMusicPage(o: JSONObject, kind: String, id: String): MusicPage =
    if (!o.optBoolean("ok", false)) MusicPage(kind, id, "", 0, emptyList(), "gone")
    else MusicPage(kind, id, o.str("title"), o.optInt("total", 0), parseSongs(o.optJSONArray("tracks")))

/** /api/music de un servidor de antes (todo junto): lo mismo que la sección, con cada álbum, artista y lista ya
 *  completo (no hay que pedir nada más). -> la sección y sus páginas ("album:<id>", "artist:<id>", "list:<id>"). */
fun parseMusicViejo(o: JSONObject): Pair<Music, Map<String, MusicPage>> {
    val songs = LinkedHashMap<String, Song>()
    o.optJSONObject("tracks")?.let { all ->
        for (key in all.keys()) all.optJSONObject(key)?.let { t -> songs[key] = parseSong(t).let { s -> if (s.id.isEmpty()) s.copy(id = key) else s } }
    }
    val pages = HashMap<String, MusicPage>()
    fun page(kind: String, id: String, title: String, ids: List<String>) {
        val list = ids.mapNotNull { songs[it] }
        pages["$kind:$id"] = MusicPage(kind, id, title, list.size, list)
    }
    val albumTracks = HashMap<String, List<String>>()
    val albums = o.optJSONArray("albums").list { a ->
        val ids = a.optJSONArray("tracks").strings()
        albumTracks[a.str("id")] = ids
        page("album", a.str("id"), a.str("title"), ids)
        Album(a.str("id"), a.str("title"), a.str("artist"), a.optInt("year", 0), ids.size, a.str("art"), a.optLong("added", 0))
    }
    val artists = o.optJSONArray("artists").list { a ->
        val ids = a.optJSONArray("albums").strings()
        page("artist", a.str("id"), a.str("name"), ids.flatMap { albumTracks[it].orEmpty() })
        Artist(a.str("id"), a.str("name"), ids.size, a.str("art"))
    }
    val lists = o.optJSONArray("playlists").list { p ->
        val ids = p.optJSONArray("tracks").strings()
        page("list", p.str("id"), p.str("title"), ids)
        MusicList(p.str("id"), p.str("title"), ids.size, p.str("art"))
    }
    val recent = albums.sortedByDescending { it.added }.flatMap { albumTracks[it.id].orEmpty() }.take(40).mapNotNull { songs[it] }
    val m = Music(Totales(artists.size, albums.size, songs.size, lists.size), lists, recent, artists, albums)
    return m to pages
}
