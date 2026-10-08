package app.onetv.tv

import app.onetv.tv.data.Album
import app.onetv.tv.data.Artist
import app.onetv.tv.data.MusicList
import app.onetv.tv.data.MusicPage
import app.onetv.tv.data.Song
import app.onetv.tv.data.parseMusic
import app.onetv.tv.data.parseMusicItems
import app.onetv.tv.data.parseMusicPage
import app.onetv.tv.data.parseMusicViejo
import app.onetv.tv.data.parseSongs
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.net.URLEncoder

// Tu música por partes (mac/music.py), como en roku/components/Music.brs: con una biblioteca grande (70 000
// canciones) todo junto serían ~25 MB. Llega lo de la sección (/api/music/home); más artistas, álbumes o listas al
// acercarse al final de su fila (/api/music/more); cada álbum, artista o lista al abrirlo, con sus canciones por
// tandas al bajar (/api/music/page); y para escuchar algo grande de seguido o al azar, la computadora manda hasta 500
// (/api/music/mix).

private fun enc(s: String) = URLEncoder.encode(s, "UTF-8")

private fun pageKey(sub: String, id: String) = "$sub:$id"

/** Al volver a pedir la sección: lo que ya se había traído de más sigue si la música no cambió. */
private fun <T> conservar(vieja: List<T>, nueva: List<T>, id: (T) -> String): List<T> =
    if (vieja.size > nueva.size && nueva.indices.all { id(vieja[it]) == id(nueva[it]) }) nueva + vieja.drop(nueva.size) else nueva

fun Estado.cargarMusica() {
    scope.launch {
        try {
            val o = api.get("/api/music/home", 30000)
            if (!o.optBoolean("ok", true)) {
                musicError = true
                return@launch
            }
            val nueva = parseMusic(o)
            for (t in nueva.recent) canciones[t.id] = t
            val vieja = music
            music = if (vieja != null && vieja.counts == nueva.counts) nueva.copy(
                artists = conservar(vieja.artists, nueva.artists) { it.id },
                albums = conservar(vieja.albums, nueva.albums) { it.id },
                playlists = conservar(vieja.playlists, nueva.playlists) { it.id },
            ) else {
                paginasMusica.clear()
                nueva
            }
            musicError = false
            if (nueva.reading && !nueva.ready) {   // la primera vez con mucha música: se vuelve a preguntar en un rato
                delay(5000)
                cargarMusica()
            }
        } catch (e: Exception) {
            if (e.message?.contains("404") == true && cargarMusicaVieja()) return@launch
            if (music == null) musicError = true
        }
    }
}

/** Un servidor de antes de la música por partes (la app pudo llegar más nueva, de GitHub): todo junto, como antes. */
private suspend fun Estado.cargarMusicaVieja(): Boolean = try {
    val (m, pages) = parseMusicViejo(api.get("/api/music", 30000))
    for (pg in pages.values) for (t in pg.songs) canciones[t.id] = t
    paginasMusica.clear()
    paginasMusica.putAll(pages)
    music = m
    musicError = false
    true
} catch (_: Exception) {
    false
}

/** Otra tanda de artistas, álbumes o listas (kind: artists | albums | playlists), si quedan. */
fun Estado.masMusica(kind: String) {
    val m = music ?: return
    val (have, total) = m.cuantos(kind)
    if (have >= total || !pidiendoMusica.add("more:$kind")) return
    scope.launch {
        try {
            val o = api.get("/api/music/more?kind=$kind&offset=$have&limit=60")
            val cur = music ?: return@launch
            if (!o.optBoolean("ok", false) || o.optInt("offset", -1) != have || cur.cuantos(kind).first != have) return@launch
            val items = parseMusicItems(kind, o.optJSONArray("items"))
            music = when (kind) {
                "artists" -> cur.copy(artists = cur.artists + items.filterIsInstance<Artist>())
                "albums" -> cur.copy(albums = cur.albums + items.filterIsInstance<Album>())
                else -> cur.copy(playlists = cur.playlists + items.filterIsInstance<MusicList>())
            }
        } catch (_: Exception) {
        } finally {
            pidiendoMusica.remove("more:$kind")
        }
    }
}

/** La página de un álbum, un artista o una lista: la primera tanda al abrirla y las que siguen al bajar. */
fun Estado.cargarPaginaMusica(sub: String, id: String) {
    val key = pageKey(sub, id)
    val pg = paginasMusica[key]
    if (pg != null && (pg.completa || pg.error.isNotEmpty())) return
    val offset = pg?.songs?.size ?: 0
    if (!pidiendoMusica.add("page:$key")) return
    scope.launch {
        try {
            val nueva = parseMusicPage(api.get("/api/music/page?kind=$sub&id=${enc(id)}&offset=$offset"), sub, id)
            for (t in nueva.songs) canciones[t.id] = t
            val cur = paginasMusica[key]
            paginasMusica[key] = when {
                cur == null || offset == 0 -> nueva
                cur.songs.size == offset && nueva.error.isEmpty() -> cur.copy(songs = cur.songs + nueva.songs, total = nueva.total)
                else -> cur
            }
        } catch (_: Exception) {
            if (paginasMusica[key] == null) paginasMusica[key] = MusicPage(sub, id, "", 0, emptyList(), "conexion")
        } finally {
            pidiendoMusica.remove("page:$key")
        }
    }
}

/** Abrir la página (OK) o escucharla ya (▶) de un álbum, un artista o una lista. */
fun Estado.abrirMusica(sub: String, id: String, title: String, quick: Boolean) {
    if (quick) {
        escucharColeccion(sub, id, 0, false)
        return
    }
    focoCuadricula["musica:$sub:$id"] = 0
    paginas.add(Pagina.MusicaPagina(sub, id, title))
    if (paginasMusica[pageKey(sub, id)]?.error?.isNotEmpty() == true) paginasMusica.remove(pageKey(sub, id))   // otra oportunidad
    cargarPaginaMusica(sub, id)
}

/** Escuchar desde la canción `index` (o al azar): si ya están todas aquí, como siempre; si no (algo enorme), la
 *  computadora manda las que siguen. */
fun Estado.escucharColeccion(sub: String, id: String, index: Int, shuffle: Boolean) {
    val pg = paginasMusica[pageKey(sub, id)]
    if (pg != null && pg.completa && pg.songs.isNotEmpty()) {
        escucharCanciones(pg.songs, index, shuffle)
        return
    }
    scope.launch {
        try {
            val o = api.get("/api/music/mix?kind=$sub&id=${enc(id)}&index=$index" + if (shuffle) "&shuffle=1" else "")
            val songs = parseSongs(o.optJSONArray("tracks"))
            if (!o.optBoolean("ok", false) || songs.isEmpty()) {
                mostrarAviso("Eso ya no está en tu música.", true)
                return@launch
            }
            for (t in songs) canciones[t.id] = t
            escucharEn(songs, o.optInt("index", 0).coerceIn(0, songs.size - 1), 0.0)
        } catch (_: Exception) {
            mostrarAviso("No se pudo: sin conexión con la computadora.", true)
        }
    }
}

/** «Aleatorio» en la página: desde una al azar, las demás mezcladas. */
fun Estado.aleatorioColeccion(sub: String, id: String) {
    val total = paginasMusica[pageKey(sub, id)]?.total ?: 0
    escucharColeccion(sub, id, if (total > 0) (0 until total).random() else 0, true)
}

/** Esas canciones desde la `index`; shuffle: esa primero y las demás al azar. */
fun Estado.escucharCanciones(songs: List<Song>, index: Int, shuffle: Boolean) {
    if (songs.isEmpty()) return
    var tracks = songs
    var i = index.coerceIn(0, tracks.size - 1)
    if (shuffle) {
        tracks = listOf(tracks[i]) + (tracks - tracks[i]).shuffled()
        i = 0
    }
    escucharEn(tracks, i, 0.0)
}

/** Una canción de la fila: la que ya se conoce o, si no, se pide por su id. */
fun Estado.escucharCancionSuelta(tid: String) {
    canciones[tid]?.let {
        escucharEn(listOf(it), 0, 0.0)
        return
    }
    scope.launch {
        try {
            val t = parseSongs(api.get("/api/music/tracks?ids=" + enc(tid)).optJSONArray("tracks")).firstOrNull()
            if (t != null) {
                canciones[t.id] = t
                escucharEn(listOf(t), 0, 0.0)
            }
        } catch (_: Exception) {
            mostrarAviso("No se pudo: sin conexión con la computadora.", true)
        }
    }
}

/** Al moverse por la sección Música: cerca del final de una fila que tiene más, se pide la tanda que sigue. */
fun Estado.musicaCercaDelFinal(v: VistaFilas) {
    if (v.key != "musica") return
    val (r, c) = focoFilas[v.key] ?: return
    val fila = v.filas.getOrNull(r) ?: return
    if (fila.mas.isNotEmpty() && c >= fila.tarjetas.size - 12) masMusica(fila.mas)
}

/** Al bajar por la página de un álbum, un artista o una lista: cerca del final, las canciones que siguen. */
fun Estado.paginaMusicaCercaDelFinal(v: VistaCuadricula) {
    val p = paginas.lastOrNull() as? Pagina.MusicaPagina ?: return
    val i = focoCuadricula[v.key] ?: 0
    if (i >= v.tarjetas.size - columnas(v) * 4) cargarPaginaMusica(p.sub, p.id)
}

/** Las canciones de la página de arriba, si es de música (para saber qué sigue y para su menú). */
fun Estado.cancionesDePagina(): List<Song> =
    (paginas.lastOrNull() as? Pagina.MusicaPagina)?.let { paginasMusica[pageKey(it.sub, it.id)]?.songs }.orEmpty()
