package app.onetv.tv

import android.net.Uri
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.media3.common.C
import androidx.media3.common.MediaItem
import androidx.media3.common.MimeTypes
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.common.TrackSelectionOverride
import androidx.media3.common.Tracks
import androidx.media3.exoplayer.ExoPlayer
import app.onetv.tv.data.Doblaje
import app.onetv.tv.data.ProgressReport
import app.onetv.tv.data.parseDubs
import app.onetv.tv.data.parseEntry
import app.onetv.tv.data.parseMarks
import app.onetv.tv.data.reportState
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import org.json.JSONObject

/** Lo que la app pide reproducir (el «request» del Player.brs del Roku). */
data class Peticion(
    val id: String,
    val title: String,
    val url: String,
    val hls: Boolean,
    val startAt: Double,
    val duration: Double,
    val audio: Int = 0,
    val sub: Int = -1,
    val audioTrack: Int = -1,                       // archivo directo: la pista de audio del archivo que suena
    val subs: List<Pair<String, String>> = emptyList(),   // (dirección, idioma) de cada subtítulo
    val hayPistas: Boolean = false,
    val next: String = "",                          // el episodio que sigue
    val yt: Boolean = false,
    val live: Boolean = false,
    val music: Boolean = false,
    val artist: String = "",
    val album: String = "",
    val art: String = "",
    val songIndex: Int = -1,
    val songCount: Int = 0,
    val last: Boolean = false,
    val position: String = "",
    val nextTitle: String = "",
    val dub: String = "",                           // YouTube: el doblaje pedido ("" = el audio original)
    val checked: Boolean = false,                   // YouTube: ya se sabe que existe (no se pregunta otra vez)
    val chapterTitles: Boolean = true,              // mostrar el nombre de cada capítulo al empezar (ajuste general)
)

data class Capitulo(val start: Double, val end: Double, val title: String)

/** Lo que hay encima del video: nada, la barra de avance o el panel. */
enum class Capa { NADA, BARRA, PANEL }

/** La cuenta atrás de lo siguiente; nota: por qué se saltó un video (en guinda claro, arriba). */
data class Siguiente(val what: String, val title: String, val thumb: String?, val back: String, val segundos: Int, val total: Int = segundos,
                     val nota: String = "")

/** El nombre del capítulo que empieza (unos segundos, abajo a la izquierda). */
data class NotaCapitulo(val head: String, val title: String)

/**
 * El reproductor, con el mismo modelo de teclas que el del Roku (roku/components/Player.brs):
 * OK pausa o sigue; ▼ muestra la barra de avance y un segundo ▼ abre el panel; ▲ regresa; ◀ ▶ el primer toque solo
 * muestra la barra y luego mueven la posición (por capítulos si hay); ⏪ ⏩ ±15 s; Atrás oculta y luego sale. La barra y
 * el panel se ocultan solos si el video sigue. Reporta el avance al servidor como el Roku (/api/progress).
 */
class Reproductor(private val app: Estado) {
    var player: ExoPlayer? = null
        set(value) {
            field = value
            value?.addListener(escucha)
        }

    var visible by mutableStateOf(false)
    var req by mutableStateOf<Peticion?>(null)
    var capa by mutableStateOf(Capa.NADA)
    var posicion by mutableStateOf(0.0)
    var duracion by mutableStateOf(0.0)
    var pausado by mutableStateOf(false)
    var cargando by mutableStateOf(true)
    var seekTarget by mutableStateOf(-1.0)
    var nota by mutableStateOf("")
    var capitulos by mutableStateOf<List<Capitulo>>(emptyList())
    var siguiente by mutableStateOf<Siguiente?>(null)
    var estadoTexto by mutableStateOf("")   // «Cargando…» antes de empezar
    var doblajes by mutableStateOf<List<Doblaje>>(emptyList())   // YouTube: los doblajes que se pueden pedir
    var aviso by mutableStateOf(false)       // «Saltar intro» a la vista
    var avisoTexto by mutableStateOf("")
    var avisoResto by mutableStateOf(1f)     // la línea limón que se vacía en 8 s
    var pausaApp by mutableStateOf(false)    // pausa hecha desde el aviso: «EN PAUSA» y cualquier tecla sigue
    var notaCapitulo by mutableStateOf<NotaCapitulo?>(null)
    private var saltar = SaltarIntro(emptyList())
    private val fin = FinSinAviso()
    private var finClock = 0L
    private var capituloActual = -1
    private var notaJob: Job? = null
    private var revisar: Job? = null
    private var notaSalto = ""                // por qué se saltó un video de YouTube (va en el aviso de lo siguiente)

    // El panel: 1 botones, 2 la fila de reproducción, 3 lo visto hace poco.
    var panelSeccion by mutableStateOf(1)
    var panelIndex by mutableStateOf(listOf(0, 0, 0, 0))
    var panelBotones by mutableStateOf<List<Boton>>(emptyList())

    private var started = false
    private var finished = false
    private var pausaTrasSalto = false
    private var pistasAplicadas = false
    private var stepAt = 0
    private var stepClock = 0L
    private var ocultar: Job? = null
    private var salto: Job? = null
    private var tick: Job? = null
    private var reloj: Job? = null
    private var cuenta: Job? = null
    private var siguienteEntrada: (() -> Unit)? = null
    private var siguienteCancelar: (() -> Unit)? = null

    private val escucha = object : Player.Listener {
        override fun onPlaybackStateChanged(state: Int) {
            val r = req ?: return
            cargando = state == Player.STATE_BUFFERING
            when (state) {
                Player.STATE_READY -> {
                    if (!started) {
                        started = true
                        estadoTexto = ""
                    }
                    if (pausaTrasSalto) {
                        pausaTrasSalto = false
                        player?.pause()
                    }
                    reportar("tick")
                }
                Player.STATE_ENDED -> if (!finished) terminado(r)
                else -> {}
            }
        }

        override fun onIsPlayingChanged(isPlaying: Boolean) {
            val p = player ?: return
            pausado = !p.playWhenReady
            // En pausa la barra aparece (si no había nada) y lo que esté a la vista se queda; al seguir, se va sola.
            if (pausado && started && !pausaApp && capa == Capa.NADA && siguiente == null) mostrarBarra()
            reiniciarOcultar()
            if (started) reportar("tick")
        }

        override fun onTracksChanged(tracks: Tracks) {
            if (!pistasAplicadas && tracks.groups.isNotEmpty()) {
                pistasAplicadas = true
                aplicarPistas()
            }
        }

        override fun onPlayerError(error: PlaybackException) {
            val r = req ?: return
            if (r.yt && !started && !r.live) {   // YouTube que no arrancó: aviso y lo siguiente de la fila
                noDisponible("no se pudo reproducir")
                return
            }
            detener(conReporte = false)
            app.alCerrarReproductor()
            val msg = if (r.live) "El canal «${r.title}» no responde ahora. Prueba otra vez en un rato."
            else "No se pudo reproducir «${r.title}». Prueba otra vez en un momento."
            app.mostrarAviso(msg, true)
        }
    }

    // ---------- empezar ----------

    fun empezar(r: Peticion) {
        val p = player ?: return
        // Si ya se veía otra cosa, se guarda dónde quedó (de una canción a la siguiente no: la computadora entendería
        // que se dejó de escuchar).
        val prev = req
        val changingSong = prev != null && prev.music && r.music
        if (prev != null && visible && !finished && started && !changingSong) reportar("stop")
        req = r
        finished = false
        started = false
        pistasAplicadas = false
        siguiente = null
        cuenta?.cancel()
        seekTarget = -1.0
        nota = ""
        capitulos = emptyList()
        doblajes = emptyList()
        saltar = SaltarIntro(emptyList())
        aviso = false
        pausaApp = false
        notaCapitulo = null
        capituloActual = -1
        fin.reiniciar()
        posicion = r.startAt.coerceAtLeast(0.0)
        duracion = r.duration
        estadoTexto = "Cargando «${r.title}»…"
        visible = true
        capa = Capa.NADA
        revisar?.cancel()
        // YouTube: antes de dárselo al reproductor se pregunta a la computadora si el video existe. Si no, la TV se
        // quedaría en negro reintentando; así se avisa y sigue lo siguiente.
        if (r.yt && !r.checked) {
            p.stop()
            p.clearMediaItems()
            revisar = app.scope.launch {
                val o = try {
                    app.api.get("/api/yt/check?id=" + r.id.removePrefix("yt:"), 30000)
                } catch (_: Exception) {
                    null   // no se pudo preguntar: que lo intente el reproductor
                }
                if (req !== r) return@launch
                if (o != null && !o.optBoolean("ok", true)) {
                    noDisponible(if (o.optBoolean("gone")) "ya no está disponible en YouTube" else "no se pudo abrir en YouTube")
                    return@launch
                }
                // Transmisión de YouTube en vivo: como directo (sin barra de avance), desde lo más reciente.
                val live = o?.optBoolean("live") == true
                val now = if (live) r.copy(live = true, startAt = 0.0, checked = true) else r.copy(checked = true)
                req = now
                arrancar(now)
            }
            return
        }
        arrancar(r)
    }

    private fun arrancar(r: Peticion) {
        val p = player ?: return
        val item = MediaItem.Builder().setUri(Uri.parse(r.url))
        if (r.hls) item.setMimeType(MimeTypes.APPLICATION_M3U8)
        if (r.subs.isNotEmpty()) item.setSubtitleConfigurations(r.subs.mapIndexed { i, (url, lang) ->
            MediaItem.SubtitleConfiguration.Builder(Uri.parse(url))
                .setMimeType(MimeTypes.APPLICATION_SUBRIP).setLanguage(lang).setId("sub$i").setLabel("sub$i")
                .setSelectionFlags(if (i == r.sub) C.SELECTION_FLAG_DEFAULT else 0).build()
        })
        p.setMediaItem(item.build(), (r.startAt * 1000).toLong().coerceAtLeast(0))
        p.prepare()
        p.playWhenReady = true
        visible = true
        capa = Capa.NADA
        if (r.music) mostrarBarra()   // con música la barra se ve al empezar
        if (r.yt) cargarCapitulos(r.id.removePrefix("yt:"))
        if (!r.live && !r.music) cargarMarcas(r.id)
        reportar("start")
        tick?.cancel()
        tick = app.scope.launch {
            while (isActive) {
                delay(10_000)
                if (visible && !finished) reportar("tick")
            }
        }
        reloj?.cancel()
        reloj = app.scope.launch {
            while (isActive) {
                player?.let { pl ->
                    if (seekTarget < 0) posicion = pl.currentPosition / 1000.0
                    val d = pl.duration
                    if (d != C.TIME_UNSET && d > 0) duracion = d / 1000.0
                    alPasarElTiempo(pl)
                }
                delay(250)
            }
        }
    }

    /** Cada cuarto de segundo: el aviso para saltar, el nombre del capítulo y el final que no llega. */
    private fun alPasarElTiempo(pl: ExoPlayer) {
        val r = req ?: return
        if (finished || !started) return
        val at = pl.currentPosition / 1000.0
        val playing = pl.isPlaying
        seguirCapitulo(at, playing)
        if (saltar.marcas.isNotEmpty() && app.lista == null) {
            if (saltar.en(at, playing)) {
                aviso = saltar.actual >= 0
                if (aviso) avisoTexto = saltar.marcas[saltar.actual].label
            }
            if (aviso) avisoResto = saltar.resto.toFloat()
        }
        // Cerca del final, cada 2 s: si el avance no se mueve, se da por terminado.
        val now = System.currentTimeMillis()
        if (duracion > 0 && at >= duracion - 2 && now - finClock >= 2000) {
            finClock = now
            if (fin.muestra(at, duracion, !pl.playWhenReady)) terminado(r)
        }
    }

    private fun cargarMarcas(id: String) {
        app.scope.launch {
            try {
                val list = parseMarks(app.api.get("/api/marks?id=" + Uri.encode(id), 15000))
                if (req?.id == id) saltar = SaltarIntro(list)
            } catch (_: Exception) {
            }
        }
    }

    /** Al entrar a un capítulo (también al empezar o al saltar a otro): su nombre unos segundos. */
    private fun seguirCapitulo(at: Double, playing: Boolean) {
        if (capitulos.isEmpty()) return
        val i = capituloEn(at)
        if (i == capituloActual) return
        capituloActual = i
        if (i >= 0 && playing && req?.chapterTitles != false && !aviso && capa == Capa.NADA) {
            notaCapitulo = NotaCapitulo("CAPÍTULO ${i + 1} DE ${capitulos.size}", capitulos[i].title)
            notaJob?.cancel()
            notaJob = app.scope.launch {
                delay(5000)
                notaCapitulo = null
            }
        }
    }

    /** El mismo video de YouTube, en el mismo segundo, con otro audio (lang "": el original). */
    fun cambiarDoblaje(lang: String) {
        val r = req ?: return
        if (!r.yt) return
        val at = (player?.currentPosition ?: 0) / 1000.0
        empezar(app.peticionYouTube(r.id.removePrefix("yt:"), at, lang).copy(checked = true, title = r.title))
    }

    /** Cambió el audio o los subtítulos desde «Audio y subtítulos». */
    fun cambiarPistas(c: Actual) {
        val r = req ?: return
        val p = player ?: return
        val it = c.item ?: return
        val eraDirecto = r.audioTrack >= 0
        val esDirecto = app.directo(c)
        if (c.audio != r.audio && !(eraDirecto && esDirecto)) {
            // El audio va dentro del video que manda el servidor: se pide el otro desde donde iba.
            empezar(app.peticionItem(c, p.currentPosition / 1000.0))
            return
        }
        req = r.copy(audio = c.audio, sub = c.sub, audioTrack = if (esDirecto) c.audio else -1)
        aplicarPistas()
        if (it.subs.isNotEmpty() || it.audio.size > 1) reportar("tick")
    }

    /** Elige en el reproductor la pista de audio del archivo y los subtítulos de la petición actual. */
    private fun aplicarPistas() {
        val r = req ?: return
        val p = player ?: return
        val b = p.trackSelectionParameters.buildUpon()
        val groups = p.currentTracks.groups
        if (r.audioTrack >= 0) {
            val audios = groups.filter { it.type == C.TRACK_TYPE_AUDIO }
            audios.getOrNull(r.audioTrack)?.let { g -> b.setOverrideForType(TrackSelectionOverride(g.mediaTrackGroup, 0)) }
        }
        if (r.sub < 0) {
            b.setTrackTypeDisabled(C.TRACK_TYPE_TEXT, true)
        } else {
            b.setTrackTypeDisabled(C.TRACK_TYPE_TEXT, false)
            val want = "sub${r.sub}"
            groups.firstOrNull { g ->
                g.type == C.TRACK_TYPE_TEXT && (0 until g.length).any { i ->
                    val f = g.getTrackFormat(i)
                    f.label == want || f.id?.endsWith(want) == true
                }
            }?.let { g -> b.setOverrideForType(TrackSelectionOverride(g.mediaTrackGroup, 0)) }
        }
        p.trackSelectionParameters = b.build()
    }

    private fun cargarCapitulos(vid: String) {
        app.scope.launch {
            try {
                val o = app.api.get("/api/yt/info?id=$vid", 30000)
                if (req?.id == "yt:$vid") doblajes = parseDubs(o)
                val arr = o.optJSONArray("chapters") ?: return@launch
                val out = mutableListOf<Capitulo>()
                for (i in 0 until arr.length()) {
                    val c = arr.optJSONObject(i) ?: continue
                    val s = c.optDouble("start", -1.0)
                    val e = c.optDouble("end", -1.0)
                    if (s >= 0 && e > s) out += Capitulo(s, e, c.optString("title", ""))
                }
                if (req?.id == "yt:$vid") {
                    capitulos = out
                    // Sin el título (se abrió desde fuera): el que dice YouTube, para la barra y el reporte.
                    val title = o.optString("title", "")
                    if (title.isNotEmpty() && req?.title == "YouTube") req = req?.copy(title = title)
                }
            } catch (_: Exception) {
            }
        }
    }

    fun capituloEn(at: Double) = capitulos.indexOfFirst { at >= it.start && at < it.end }

    // ---------- reportes ----------

    /** Cuenta al servidor qué se ve y por dónde va (para «Seguir viendo» y el control desde el teléfono). */
    fun reportar(ev: String, alTerminar: (() -> Unit)? = null) {
        val r = req ?: return
        if (r.id.startsWith("live:")) return   // los canales de «En vivo» no dejan avance
        val p = player
        val at = if (ev == "start") r.startAt else (p?.currentPosition ?: 0) / 1000.0
        var d = (p?.duration ?: C.TIME_UNSET).let { if (it == C.TIME_UNSET || it <= 0) 0.0 else it / 1000.0 }
        if (d <= 0) d = r.duration
        val c = app.cur
        val body = ProgressReport(
            id = r.id, position = at, duration = d, event = ev, audio = c?.audio ?: r.audio, sub = c?.sub ?: r.sub,
            state = reportState(p?.playWhenReady == true, p?.playbackState == Player.STATE_BUFFERING), deviceId = app.deviceId,
            songIndex = if (r.music) r.songIndex else -1, songCount = if (r.music) r.songCount else 0,
        ).toJson()
        app.scope.launch {
            try {
                app.api.post("/api/progress", body, 8000)
            } catch (_: Exception) {
            }
            alTerminar?.invoke()
        }
    }

    // ---------- terminar ----------

    private fun terminado(r: Peticion) {
        if (finished) return
        finished = true
        // Entre canciones no se avisa el final: solo al terminar la última la computadora quita su barra.
        if (!r.music || r.last) reportar("end")
        tick?.cancel()
        ocultarTodo()
        aviso = false
        pausaApp = false
        notaCapitulo = null
        player?.stop()
        if (r.music && app.pasoMusica(1)) return
        loSiguiente(r)
    }

    /** Un video de YouTube que no se puede ver (borrado, privado…): se avisa y sigue lo siguiente de la fila. */
    private fun noDisponible(reason: String) {
        val r = req ?: return
        finished = true
        tick?.cancel()
        estadoTexto = ""
        player?.stop()
        notaSalto = "«${r.title}» $reason."
        loSiguiente(r)
    }

    /** ¿Hay algo en la fila? Si no (y era YouTube) la computadora puede proponer un relacionado; si no, el episodio que sigue. */
    private fun loSiguiente(r: Peticion) {
        app.scope.launch {
            val o = try {
                app.api.post("/api/queue/next", JSONObject().put("after", r.id).put("device_id", app.deviceId))
            } catch (_: Exception) {
                null
            }
            // La computadora ya se saltó videos de la fila que sabe que no existen: también se dice.
            val skipped = o?.optJSONArray("skipped")
            if (skipped != null && skipped.length() > 0) {
                val t = (if (skipped.length() > 1) "Se saltaron ${skipped.length()} videos" else "Se saltó «${skipped.optString(0)}»") +
                    ": ya no está disponible en YouTube."
                notaSalto = if (notaSalto.isNotEmpty()) "$notaSalto $t" else t
            }
            val entry = o?.optJSONObject("entry")?.let { parseEntry(it) to o.optString("source") }
            val note = notaSalto
            notaSalto = ""
            val secs = if (note.isNotEmpty()) 3 else 5   // se saltó uno: el motivo arriba y solo 3 segundos
            if (entry != null) {
                val (e, source) = entry
                val what = if (source == "related") "Recomendado por YouTube" else "Lo siguiente de la fila"
                cuentaAtras(Siguiente(what, e.title, app.datos?.abs(e.thumb), if (source == "related") "Detener" else "Volver", secs, nota = note),
                    { app.reproducirEntrada(e); app.cargarBiblioteca() },
                    {
                        if (source != "related") app.scope.launch {   // vuelve a su lugar en la fila para no perderlo
                            try {
                                app.api.post("/api/queue/add", JSONObject().put("kind", e.kind).put("id", e.id).put("title", e.title).put("front", true).put("device_id", app.deviceId))
                            } catch (_: Exception) {
                            }
                        }
                    })
                return@launch
            }
            if (note.isNotEmpty()) {   // no hay nada después del video que no se pudo ver
                detener(conReporte = false)
                app.alCerrarReproductor()
                app.mostrarAviso(note, true)
                return@launch
            }
            val nxt = r.next
            val it = app.lib?.items?.get(nxt)
            if (nxt.isNotEmpty() && it != null) {
                val c = app.cur
                cuentaAtras(Siguiente("Siguiente episodio", it.fullTitle, app.datos?.abs(it.poster), "Volver", 5),
                    { mismoIdioma(c, nxt) }, {})
            } else {
                detener(conReporte = false)
                app.alCerrarReproductor()
            }
        }
    }

    /** El siguiente episodio con el mismo idioma de audio y subtítulos que el anterior. */
    private fun mismoIdioma(prev: Actual?, nextId: String) {
        val it = app.lib?.items?.get(nextId) ?: return
        val pi = prev?.item
        var audio: Int? = null
        var sub: Int? = -1
        if (pi != null && pi.audio.isNotEmpty()) {
            val lang = pi.audio.getOrNull(prev.audio)?.lang
            audio = it.audio.indexOfFirst { a -> a.lang == lang }.takeIf { i -> i >= 0 }
            if (prev.sub >= 0) {
                val sl = pi.subs.getOrNull(prev.sub)?.lang
                sub = it.subs.indexOfFirst { s -> s.lang == sl }
            }
        }
        app.empezarItem(nextId, true, audio, sub)
    }

    private fun cuentaAtras(s: Siguiente, ver: () -> Unit, cancelar: () -> Unit) {
        siguiente = s
        siguienteEntrada = ver
        siguienteCancelar = cancelar
        cuenta?.cancel()
        cuenta = app.scope.launch {
            var left = s.segundos
            while (left > 0) {
                delay(1000)
                left--
                siguiente = siguiente?.copy(segundos = left)
            }
            terminarSiguiente(true)
        }
    }

    private fun terminarSiguiente(ver: Boolean) {
        cuenta?.cancel()
        siguiente = null
        if (ver) siguienteEntrada?.invoke() else {
            siguienteCancelar?.invoke()
            detener(conReporte = false)
            app.alCerrarReproductor()
        }
        siguienteEntrada = null
        siguienteCancelar = null
    }

    fun detener(conReporte: Boolean) {
        if (conReporte && req != null && started && !finished) reportar("stop") { app.alCerrarReproductor() }
        tick?.cancel()
        reloj?.cancel()
        cuenta?.cancel()
        revisar?.cancel()
        ocultarTodo()
        siguiente = null
        aviso = false
        pausaApp = false
        notaCapitulo = null
        estadoTexto = ""
        // Primero se olvida lo que se veía: al parar el video el reproductor avisa que ya no reproduce, y ese aviso
        // no debe mandar otro reporte después del «stop» (la computadora creería que sigue en la TV).
        visible = false
        req = null
        player?.stop()
        player?.clearMediaItems()
    }

    // ---------- teclas ----------

    fun tecla(t: Tecla): Boolean {
        val r = req ?: return true
        if (siguiente != null) {
            when (t) {
                Tecla.ATRAS -> terminarSiguiente(false)
                Tecla.OK, Tecla.PLAY -> terminarSiguiente(true)
                else -> {}
            }
            return true
        }
        if (aviso) {   // con «Saltar intro» a la vista: OK salta; ⏯ pausa; ⏩ ⏪ 10 s; cualquier otra tecla lo esconde
            teclaAviso(t)
            return true
        }
        if (capa == Capa.PANEL) return teclaPanel(t)
        if (t == Tecla.ATRAS) {
            pausaApp = false
            if (capa != Capa.NADA) ocultarTodo()   // primero se quita lo que hay encima; sin nada encima, Atrás sale
            else detener(conReporte = true)
            return true
        }
        if (pausaApp) {   // pausa hecha desde el aviso: cualquier tecla (salvo Atrás) sigue
            pausaApp = false
            player?.play()
            return true
        }
        if (finished || !started && r.yt && !r.checked) return true   // cargando o terminado: nada que mover
        val p = player ?: return true
        when (t) {
            Tecla.OK, Tecla.PLAY -> {
                if (p.playWhenReady) p.pause() else p.play()
                pausado = !p.playWhenReady
                if (capa == Capa.NADA) mostrarBarra() else reiniciarOcultar()
            }
            Tecla.IZQ, Tecla.DER -> {
                if (capa != Capa.BARRA) mostrarBarra()   // la primera vez solo se muestra la barra
                else if (!r.live) recorrer(if (t == Tecla.IZQ) -1 else 1)
            }
            Tecla.ADELANTAR, Tecla.ATRASAR -> if (!r.live) saltarPor(if (t == Tecla.ADELANTAR) 15.0 else -15.0)
            Tecla.REPETIR -> if (!r.live) saltarPor(-10.0)
            Tecla.ABAJO -> if (capa == Capa.BARRA) abrirPanel() else mostrarBarra()
            Tecla.ARRIBA -> if (capa == Capa.BARRA) ocultarTodo()
            else -> return false
        }
        return true
    }

    private fun teclaAviso(t: Tecla) {
        val p = player ?: return
        val target = saltar.usar()
        aviso = false
        val at = p.currentPosition / 1000.0
        when (t) {
            Tecla.OK -> if (target != null) {
                pausaTrasSalto = !p.playWhenReady
                p.seekTo((target * 1000).toLong())
            }
            Tecla.PLAY -> if (!p.playWhenReady) p.play() else {
                // La app se queda con las teclas hasta que se siga y muestra «En pausa».
                pausaApp = true
                p.pause()
            }
            Tecla.ADELANTAR -> p.seekTo(((at + 10) * 1000).toLong())
            Tecla.ATRASAR, Tecla.REPETIR -> p.seekTo(((at - 10).coerceAtLeast(0.0) * 1000).toLong())
            else -> {}
        }
    }

    /** ◀ ▶ con la barra a la vista: con capítulos, al principio del actual o al siguiente; sin capítulos, 10 s y, si
     *  se aprietan seguidas, cada vez más (hasta 60 s). Las teclas seguidas se suman y se salta al soltar medio segundo. */
    private fun recorrer(dir: Int) {
        val at = if (seekTarget >= 0) seekTarget else posicion
        if (capitulos.isEmpty()) {
            val now = System.currentTimeMillis()
            stepAt = if (now - stepClock < 900) stepAt + 1 else 0
            stepClock = now
            val jump = (10 * (stepAt + 1)).coerceAtMost(60)
            saltarDespues(at + jump * dir)
            return
        }
        val i = capituloEn(at)
        val target = if (dir > 0) {
            if (i >= capitulos.size - 1) {
                mostrarNota("Es el último capítulo")
                return
            }
            capitulos[i + 1].start
        } else when {
            i >= 0 && at - capitulos[i].start > 3 -> capitulos[i].start
            i > 0 -> capitulos[i - 1].start
            else -> 0.0
        }
        saltarDespues(target)
    }

    private fun saltarPor(seconds: Double) {
        val at = if (seekTarget >= 0) seekTarget else posicion
        saltarDespues(at + seconds)
    }

    private fun saltarDespues(target0: Double) {
        var target = target0.coerceAtLeast(0.0)
        if (duracion > 0 && target > duracion - 2) target = duracion - 2
        seekTarget = target
        posicion = target
        nota = ""
        if (capa != Capa.BARRA) mostrarBarra()
        ocultar?.cancel()
        salto?.cancel()
        salto = app.scope.launch {
            delay(500)
            val p = player ?: return@launch
            pausaTrasSalto = !p.playWhenReady   // saltar no quita la pausa
            p.seekTo((seekTarget * 1000).toLong())
            seekTarget = -1.0
            reiniciarOcultar()
        }
    }

    // ---------- barra y panel ----------

    fun mostrarBarra() {
        capa = Capa.BARRA
        nota = ""
        notaCapitulo = null   // la barra ya dice el capítulo
        reiniciarOcultar()
    }

    private fun mostrarNota(text: String) {
        if (capa != Capa.BARRA) mostrarBarra()
        nota = text
    }

    fun ocultarTodo() {
        ocultar?.cancel()
        capa = Capa.NADA
    }

    /** Se ocultan solos si el video sigue; en pausa (o mientras se mueve la posición) se quedan. Con música, igual que
     *  en el Roku: así ‹ › la primera vez solo muestran la barra. */
    private fun reiniciarOcultar() {
        ocultar?.cancel()
        val p = player ?: return
        if (!p.playWhenReady || seekTarget >= 0 || capa == Capa.NADA) return
        val wait = if (capa == Capa.PANEL) 8000L else 5000L
        ocultar = app.scope.launch {
            delay(wait)
            if (player?.playWhenReady == true && seekTarget < 0) ocultarTodo()
        }
    }

    private fun abrirPanel() {
        val r = req ?: return
        val l = app.lib
        val buttons = mutableListOf<Boton>()
        if (r.music) {
            if (app.hayCancion(-1)) buttons += Boton("song-prev", "Canción anterior", "skip-back")
            if (app.hayCancion(1)) buttons += Boton("song-next", "Siguiente canción", "skip")
        }
        if (!l?.queue.isNullOrEmpty()) buttons += Boton("next", "Siguiente de la fila", "list-video")
        if ((r.hayPistas && !r.yt && !r.live && !r.music) || (r.yt && doblajes.isNotEmpty())) buttons += Boton("tracks", "Audio y subtítulos", "audio")
        panelBotones = buttons
        capa = Capa.PANEL
        panelSeccion = (1..3).firstOrNull { cuantos(it) > 0 } ?: 1
        reiniciarOcultar()
    }

    fun panelFila() = app.lib?.queue.orEmpty()
    fun panelVistos() = app.lib?.history.orEmpty().take(12)

    private fun cuantos(s: Int) = when (s) {
        1 -> panelBotones.size
        2 -> panelFila().size
        else -> panelVistos().size
    }

    private fun teclaPanel(t: Tecla): Boolean {
        reiniciarOcultar()
        when (t) {
            Tecla.ATRAS -> ocultarTodo()
            Tecla.ARRIBA, Tecla.ABAJO -> {
                val d = if (t == Tecla.ARRIBA) -1 else 1
                var s = panelSeccion + d
                while (s in 1..3 && cuantos(s) == 0) s += d
                if (s < 1) mostrarBarra()   // ▲ desde la parte de arriba: de vuelta a la barra de avance
                else if (s <= 3) panelSeccion = s
            }
            Tecla.IZQ, Tecla.DER -> {
                val i = panelIndex[panelSeccion] + if (t == Tecla.IZQ) -1 else 1
                if (i in 0 until cuantos(panelSeccion)) panelIndex = panelIndex.toMutableList().also { it[panelSeccion] = i }
            }
            Tecla.PLAY -> player?.let { if (it.playWhenReady) it.pause() else it.play() }
            Tecla.OK -> {
                val i = panelIndex[panelSeccion]
                when (panelSeccion) {
                    1 -> panelBotones.getOrNull(i)?.let { b ->
                        ocultarTodo()
                        when (b.id) {
                            "next" -> app.panelFila(0)
                            "tracks" -> app.abrirAudioYSubtitulos()
                            "song-prev" -> app.pasoMusica(-1)
                            "song-next" -> app.pasoMusica(1)
                        }
                    }
                    2 -> {
                        ocultarTodo()
                        app.panelFila(i)
                    }
                    3 -> {
                        ocultarTodo()
                        app.panelVistos(i)
                    }
                }
            }
            else -> {}
        }
        return true
    }
}
