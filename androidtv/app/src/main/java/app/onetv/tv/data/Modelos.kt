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
data class Album(val id: String, val title: String, val artist: String, val year: Int, val tracks: List<String>, val art: String, val added: Long)
data class Artist(val id: String, val name: String, val albums: List<String>, val art: String)
data class MusicList(val id: String, val title: String, val tracks: List<String>, val art: String)

data class Music(val albums: List<Album>, val artists: List<Artist>, val playlists: List<MusicList>, val tracks: Map<String, Song>) {
    val ready get() = albums.isNotEmpty()
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

fun parseMusic(o: JSONObject): Music {
    val tracks = LinkedHashMap<String, Song>()
    o.optJSONObject("tracks")?.let { all ->
        for (key in all.keys()) all.optJSONObject(key)?.let { t ->
            tracks[key] = Song(t.str("id").ifEmpty { key }, t.str("title"), t.str("artist"), t.str("album"), t.num("duration"), t.str("url"), t.str("art"))
        }
    }
    return Music(
        albums = o.optJSONArray("albums").list { a ->
            Album(a.str("id"), a.str("title"), a.str("artist"), a.optInt("year", 0), a.optJSONArray("tracks").strings(), a.str("art"), a.optLong("added", 0))
        },
        artists = o.optJSONArray("artists").list { a -> Artist(a.str("id"), a.str("name"), a.optJSONArray("albums").strings(), a.str("art")) },
        playlists = o.optJSONArray("playlists").list { p -> MusicList(p.str("id"), p.str("title"), p.optJSONArray("tracks").strings(), p.str("art")) },
        tracks = tracks,
    )
}
