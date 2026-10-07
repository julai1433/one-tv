' La ficha, reproducir (biblioteca, YouTube, en vivo), el idioma de este dispositivo, la fila de reproducción y
' lo que sigue al terminar un video.

' ---------- ficha ----------

sub showDetail(data as Object)
    m.menu.expanded = false
    m.detail.data = data
    m.detail.visible = true
    if m.view <> invalid then m.view.visible = false
    m.detail.setFocus(true)
end sub

sub closeDetail(focus as Boolean)
    if not m.detail.visible then return
    m.detail.visible = false
    disarmOffline()
    if m.view <> invalid
        m.view.visible = not m.player.visible
        if focus then m.view.setFocus(true)
    end if
end sub

sub onDetailEvent()
    e = m.detail.event
    if e.action = "close"
        closeDetail(true)
    else if e.action = "button"
        detailButton(e.id)
    else if e.action = "audio"
        m.cur.audio = e.index
        savePrefs("audio")
        openItemDetail(true)
    else if e.action = "sub"
        m.cur.sub = e.index
        savePrefs("sub")
        openItemDetail(true)
    else if e.action = "ytinfo"   ' lo que dijo /api/yt/info de un video de YouTube (en vivo o no)
        if m.cur <> invalid and m.cur.yt = true then learnLiveInfo(m.cur.vid, e.live = true, e.viewers, e.channelId)
    else if e.action = "findsubs"
        detailMessage("Buscando subtítulos en internet…", "ok")
        post("/api/subs/auto", {id: m.cur.id, lang: e.lang}, "onSubsFound")
    end if
end sub

sub detailButton(id as String)
    if id = "resume"
        play(resumePos(m.cur.id))
    else if id = "start"
        play(0)
    else if id = "queue" or id = "queue-next"
        post("/api/queue/add", {kind: "item", id: m.cur.id, front: id = "queue-next"}, "onQueued")
    else if id = "yt-play"
        playYouTube(m.cur.vid, 0)
    else if id = "yt-resume"
        playYouTube(m.cur.vid, -1)
    else if id = "yt-queue" or id = "yt-next"
        post("/api/queue/add", {kind: "yt", id: m.cur.vid, title: ytTitle(m.cur.vid), front: id = "yt-next"}, "onQueued")
    else if id = "yt-off"
        pressOfflineVideo()   ' «Guardar sin conexión» (Offline.brs)
    else if id = "yt-fav"
        pressFav()            ' Favoritos (Lists.brs)
    else if id = "yt-addlive"
        addYouTubeLive()      ' su canal a «En vivo» (Lists.brs)
    else if id = "yt-dismiss" or id = "yt-mute"
        ytDetailDismiss(m.cur.vid, id = "yt-mute")   ' PlayerMenus.brs
    else if id = "yt-lists"
        pressAddToList()      ' «Agregar a lista» (Lists.brs)
    else if id = "multi"
        openMultiFromDetail()   ' «Ver con otro» (Multi.brs)
    end if
end sub

' OK sobre una película o episodio: la ficha. ▶ (autoplay): directo, con el idioma de este dispositivo.
' options (opcional, desde el teléfono): audio, sub (-1 = sin subtítulos), start (segundos).
sub startItem(id as String, autoplay as Boolean, options as Dynamic)
    it = m.lib.items[id]
    if it = invalid then return
    m.cur = {id: id, item: it, audio: chooseAudio(it, m.prefs), sub: chooseSub(it, m.prefs)}
    startAt = resumePos(id)
    if options <> invalid
        if options.audio <> invalid then m.cur.audio = clampAudio(it, toInt(options.audio))
        if options.sub <> invalid then m.cur.sub = clampSub(it, toInt(options.sub))
        if options.start <> invalid then startAt = toInt(options.start)
    end if
    if autoplay then play(startAt) else openItemDetail(false)
end sub

sub openItemDetail(keepFocus as Boolean)
    it = m.cur.item
    id = m.cur.id
    ' La serie en letra de marquesina y el episodio debajo; una película, solo su título.
    subtitle = ""
    if it.kind = "episode"
        title = it.show
        subtitle = "T" + it.season.ToStr() + " " + it.ep
        if it.ep_title <> "" then subtitle = subtitle + " · " + it.ep_title
        meta = fmtDuration(it.duration)
    else
        title = bareTitle(it.title)
        meta = fmtDuration(it.duration)
        year = yearOf(it.title)
        if year <> "" then meta = year + "   ·   " + meta
    end if
    buttons = []
    atSecond = resumePos(id)
    if atSecond > 0
        buttons.Push({id: "resume", text: "Continuar desde " + fmtTime(atSecond), icon: "play"})
        buttons.Push({id: "start", text: "Desde el principio", icon: "rotate-ccw"})
    else
        buttons.Push({id: "start", text: "Reproducir", icon: "play"})
    end if
    if multiViewOn() then buttons.Push({id: "multi", text: "Ver con otro", icon: "tv"})
    buttons.Push({id: "queue-next", text: "A continuación", icon: "list-start"})
    buttons.Push({id: "queue", text: "Al final de la fila", icon: "list-plus"})
    buttons.Push({id: "lang", text: langButtonText(it), icon: "languages"})
    audio = []
    for each t in it.audio
        audio.Push(trackName(t))
    end for
    subs = []
    for each s in it.subs
        subs.Push(trackName(s))
    end for
    data = {kind: "item", title: title, subtitle: subtitle, meta: meta, spanish: it.dub = true, langs: spokenText(it),
            image: m.server + it.poster, descPath: "/api/info?id=" + id, tech: techText(it), buttons: buttons,
            audio: audio, subs: subs, audioIndex: m.cur.audio, subIndex: m.cur.sub, keepFocus: keepFocus}
    if keepFocus then m.detail.data = data else showDetail(data)
end sub

' «Idioma: Español (latino)» / «Idioma: Inglés (original) + subtítulos».
function langButtonText(it as Object) as String
    text = "Idioma"
    if m.cur.audio >= 0 and m.cur.audio < it.audio.Count() then text = text + ": " + trackName(it.audio[m.cur.audio])
    if m.cur.sub >= 0 then text = text + " + subtítulos"
    return text
end function

' Lo técnico, aparte (solo en la sinopsis completa).
function techText(it as Object) as String
    lines = []
    if it.mode = "copy"
        lines.Push("Video original; la computadora solo convierte el audio (" + it.convert_reason + ").")
    else if it.direct = invalid
        lines.Push("La computadora convierte el video mientras se ve (" + it.convert_reason + ").")
    else
        lines.Push("Se reproduce directo, sin convertir.")
    end if
    for each t in it.audio
        line = "Audio: " + trackName(t)
        tech = trackTech(t)
        if tech <> "" then line = line + " — " + tech
        if t.DoesExist("ext") then line = line + " (pista aparte, llega por la computadora)"
        lines.Push(line)
    end for
    for each s in it.subs
        lines.Push("Subtítulos: " + trackName(s))
    end for
    return lines.Join(chr(10))
end function

function clampAudio(it as Object, index as Integer) as Integer
    if index < 0 or index >= it.audio.Count() then return it.audio_default
    return index
end function

function clampSub(it as Object, index as Integer) as Integer
    if index < 0 or index >= it.subs.Count() then return -1
    return index
end function

' Elegir una pista a mano guarda la preferencia de ESTE dispositivo: "original" o el idioma.
sub savePrefs(which as String)
    it = m.cur.item
    prefs = {}
    if (which = "audio" or which = "both") and it.audio.Count() > 0 then prefs["audioLang"] = audioPref(it, m.cur.audio)
    if which = "sub" or which = "both"
        if m.cur.sub >= 0 and m.cur.sub < it.subs.Count() then prefs["subLang"] = it.subs[m.cur.sub].lang else prefs["subLang"] = "off"
    end if
    if prefs.Count() = 0 then return
    m.prefs.Append(prefs)
    post("/api/prefs", prefs, "")
end sub

sub onSubsFound(event as Object)
    task = event.getRoSGNode()
    r = task.result
    if task.error <> "" or r = invalid
        detailMessage("No se pudo buscar: sin conexión con la computadora.", "error")
    else if r.ok = true and m.cur <> invalid and r.item <> invalid and r.item.id = m.cur.id
        m.lib.items[m.cur.id] = r.item
        m.cur.item = r.item
        m.cur.sub = r.sub
        savePrefs("sub")
        detailMessage("Subtítulos descargados: " + r.label, "ok")
        if m.detail.visible then openItemDetail(true)
    else if r.error <> invalid
        detailMessage(r.error, "error")
    end if
end sub

' ---------- reproducir ----------

' ¿Se reproduce el archivo tal cual? Los doblajes agregados aparte siempre llegan por la Mac.
function playsDirect() as Boolean
    it = m.cur.item
    if it.direct = invalid then return false
    if m.cur.audio < it.audio.Count() and it.audio[m.cur.audio].DoesExist("ext") then return false
    return true
end function

function itemRequest(startAt as Integer) as Object
    it = m.cur.item
    req = {id: m.cur.id, title: it.full_title, startAt: startAt, report: true, duration: it.duration,
           audio: m.cur.audio, sub: m.cur.sub, audioTrack: -1, subtitle: ""}
    if playsDirect()
        req.url = m.server + it.direct.url
        req.format = it.direct.format
        if m.cur.audio <> it.audio_default then req.audioTrack = m.cur.audio
    else
        req.url = m.server + it.audio[m.cur.audio].hls
        req.format = "hls"
    end if
    tracks = []
    for each s in it.subs
        tracks.Push({Language: s.lang, TrackName: m.server + s.url, Description: trackName(s)})
    end for
    req.subtitleTracks = tracks
    if m.cur.sub >= 0 and m.cur.sub < it.subs.Count() then req.subtitle = m.server + it.subs[m.cur.sub].url
    return req
end function

sub play(startAt as Integer)
    startPlayer(itemRequest(startAt))
end sub

sub startPlayer(req as Object)
    closePicker(false)   ' una orden del teléfono puede llegar con la lista de «Ver con otro» abierta
    m.menu.expanded = false
    m.menu.visible = false
    m.detail.visible = false
    m.toast.visible = false
    if m.view <> invalid then m.view.visible = false
    m.player.request = req
end sub

' Se cerró el reproductor: de vuelta a la tarjeta de donde se salió.
sub onPlayerClosed()
    m.menu.visible = true
    if m.view <> invalid
        m.view.visible = true
        m.view.setFocus(true)
    end if
end sub

' startAt < 0: donde se quedó, si se quedó a medias.
sub playYouTube(vid as String, startAt as Integer)
    if startAt < 0
        startAt = 0
        p = m.ytProgress[vid]
        if p <> invalid and p > 30 then startAt = Int(p)
    end if
    req = ytRequest(vid, startAt)
    m.cur = {id: "yt:" + vid, yt: true, vid: vid, audio: 0, sub: -1,
             item: {full_title: req.title, subs: [], audio: [], direct: invalid, duration: req.duration, audio_default: 0}}
    startPlayer(req)
end sub

' Lo que el reproductor necesita para un video de YouTube (con su audio original; ver playYouTubeDub).
function ytRequest(vid as String, startAt as Integer) as Object
    duration = 0
    info = m.ytInfo[vid]
    if info <> invalid and info.duration <> invalid then duration = info.duration
    return {id: "yt:" + vid, title: ytTitle(vid), url: m.server + "/yt/" + vid + "/index.m3u8", format: "hls",
            startAt: startAt, report: true, yt: true, duration: duration, audio: 0, sub: -1, audioTrack: -1, subtitle: "",
            chapterTitles: chapterTitlesOn(), dub: ""}
end function

' Canal en vivo: la Mac trae el video de la página (sin anuncios) y la tele lo reproduce como directo.
sub playLive(cid as String)
    channel = invalid
    if m.lib <> invalid and m.lib.live <> invalid
        for each c in m.lib.live
            if c.id = cid then channel = c
        end for
    end if
    if channel = invalid then return
    m.cur = {id: "live:" + cid, live: true, audio: 0, sub: -1,
             item: {full_title: channel.name, subs: [], audio: [], direct: invalid, duration: 0, audio_default: 0}}
    startPlayer({id: "live:" + cid, title: channel.name, url: m.server + "/live/" + cid + "/index.m3u8", format: "hls",
                 live: true, report: false, audio: 0, sub: -1, audioTrack: -1, subtitle: ""})
end sub

' Varios a la vez (lo manda el teléfono o la computadora): lo que se estaba viendo se detiene y se abre la pantalla
' del mosaico. focus: cuál suena al empezar.
sub openMosaic(mid as String, focus as Dynamic)
    f = 0
    if focus <> invalid then f = toInt(focus)
    if m.player.visible and not m.mosaic.visible
        ' Lo que se ve sigue hasta que la computadora lo tenga listo (onMosaicEvent «ready»).
        closePicker(false)
        m.player.note = {head: "VARIOS A LA VEZ", text: "La computadora está juntando los videos. Sigue este mientras tanto."}
        m.player.refocus = true
        m.mosaic.open = {id: mid, focus: f, background: true}
        return
    end if
    coverForMosaic()
    m.mosaic.open = {id: mid, focus: f}
end sub

' Lo que se veía se deja (el reproductor guarda dónde quedó) y solo queda el mosaico.
sub coverForMosaic()
    closePicker(false)
    if m.player.visible then m.player.stop = true   ' también detiene la cuenta atrás de lo siguiente
    m.menu.expanded = false
    m.menu.visible = false
    m.detail.visible = false
    m.toast.visible = false
    if m.view <> invalid then m.view.visible = false
end sub

' Se cerró el mosaico: la computadora deja de armarlo. «Ver solo este» abre esa fuente con el reproductor de siempre.
' «pick»: ▼ → «Agregar otro» o «Cambiar este» (la lista para elegir, encima del mosaico, que sigue).
sub onMosaicEvent()
    e = m.mosaic.event
    if e.type = "pick"
        openPickerForMosaic(e)
        return
    end if
    if e.type = "ready"   ' el armado detrás del reproductor ya está: se deja el reproductor y se ve el mosaico
        m.player.note = {}
        coverForMosaic()
        m.mosaic.reveal = true
        return
    end if
    if e.type = "buildError"
        msg = "La computadora no pudo armar el video."
        if e.message <> invalid then msg = e.message
        if m.player.visible
            m.player.note = {head: "NO SE PUDO VER VARIOS A LA VEZ", text: msg, autoHide: true, isError: true}
        else
            showToastTone("No se pudo ver varios a la vez: " + msg, true, "error")
        end if
        return
    end if
    if m.pick.ctx = "mosaic" then closePicker(false)
    if e.id <> invalid and e.id <> "" then post("/api/mosaic/stop", {id: e.id}, "")
    s = e.source
    if e.type = "solo" and s <> invalid
        ' Sigue en el mismo punto que se veía en el mosaico (cada fuente empezó en su «start»).
        at = 0
        if e.at <> invalid then at = toInt(e.at)
        if s.start <> invalid then at = at + toInt(s.start)
        if s.kind = "yt"
            playYouTube(s.id, at)
            return
        else if s.kind = "live" and liveExists(s.id)
            playLive(s.id)
            return
        else if s.kind = "item" and m.lib <> invalid and m.lib.items[s.id] <> invalid
            opts = {start: at}
            track = audioPosition(m.lib.items[s.id], s.audio)
            if track >= 0 then opts.audio = track
            startItem(s.id, true, opts)
            return
        end if
    end if
    onPlayerClosed()
end sub

' La pista que usó el mosaico (índice del archivo, «x0» o «na») -> su lugar en la lista de la biblioteca, o -1.
function audioPosition(it as Object, code as Dynamic) as Integer
    if code = invalid or it.audio = invalid then return -1
    if type(code) = "String" or type(code) = "roString" then key = code else key = "a" + toInt(code).ToStr()
    for i = 0 to it.audio.Count() - 1
        if audioCode(it, i) = key then return i
    end for
    return -1
end function

function liveExists(cid as String) as Boolean
    if m.lib = invalid or m.lib.live = invalid then return false
    for each c in m.lib.live
        if c.id = cid then return true
    end for
    return false
end function

' Cambio de audio o subtítulos pedido desde el teléfono mientras se ve algo.
sub applyTracks(args as Object)
    if m.cur = invalid or m.cur.item = invalid or m.cur.yt = true or m.cur.live = true then return
    if m.pick.ctx = "player" then closePicker(true)   ' cambiar de pista puede rearmar el video: el foco, a él
    it = m.cur.item
    if args.sub <> invalid
        m.cur.sub = clampSub(it, toInt(args.sub))
        if m.cur.sub >= 0 then m.player.subtitle = m.server + it.subs[m.cur.sub].url else m.player.subtitle = ""
    end if
    if args.audio <> invalid
        index = clampAudio(it, toInt(args.audio))
        if index <> m.cur.audio
            wasDirect = playsDirect()
            m.cur.audio = index
            if wasDirect and playsDirect()
                m.player.audioTrack = index
            else
                m.player.request = itemRequest(Int(m.player.position))   ' el audio va dentro del stream
            end if
        end if
    end if
    m.player.trackInfo = {audio: m.cur.audio, sub: m.cur.sub}
    savePrefs("both")
end sub

sub onPlayerEvent()
    e = m.player.event
    ' Lo que se abre encima desde el reproductor (PlayerMenus.brs); el video sigue.
    if e.type = "options"
        openPlayerOptions(e)
        return
    else if e.type = "panel"
        sendPanelData()
        return
    else if e.type = "panel-queue"
        post("/api/queue/take", {index: e.index}, "onQueueTaken")
        return
    else if e.type = "panel-history"
        playHistory(e.index)
        return
    else if e.type = "track"   ' ‹ › escuchando música
        if not musicStep(e.dir) and e.dir > 0 then post("/api/queue/next", {after: m.cur.id}, "onQueueNext")
        return
    end if
    if e.type = "finished" and m.cur <> invalid and m.cur.music = true
        if musicStep(1) then return   ' la canción que sigue, sin cuenta atrás
    end if
    ' Se acabó o falló lo que se veía con la lista abierta encima: se cierra (lo siguiente toma el foco).
    if e.type <> "saved" and m.pick.ctx = "player" then closePicker(true)
    if (e.type = "stopped" or e.type = "error") and not m.mosaic.visible then m.mosaic.stop = true   ' se salió mientras se armaba
    if e.type = "stopped"
        onPlayerClosed()
    else if e.type = "saved"
        loadLibrary()      ' trae «Seguir viendo» ya actualizado de la Mac
    else if e.type = "finished"
        m.finished = m.cur
        ' ¿Hay algo en la fila? Si no, y era YouTube, la Mac puede proponer un relacionado.
        post("/api/queue/next", {after: m.cur.id}, "onQueueNext")
    else if e.type = "unavailable"
        ' Un video de YouTube que no se puede ver (borrado, privado…): se avisa y sigue lo siguiente de la fila.
        m.finished = m.cur
        m.skipNote = "«" + e.title + "» " + e.reason + "."
        post("/api/queue/next", {after: m.cur.id}, "onQueueNext")
    else if e.type = "error"
        onPlayerClosed()
        msg = "No se pudo reproducir «" + e.title + "». Prueba otra vez en un momento."
        if m.cur <> invalid and m.cur.live = true then msg = "El canal «" + e.title + "» no responde ahora. Prueba otra vez en un rato."
        showToastTone(msg, true, "error")
    else if e.type = "upnext-play"
        playUpNext()
    else if e.type = "upnext-cancel"
        cancelUpNext()
    end if
end sub

' ---------- lo siguiente: la fila y, si no hay, el próximo episodio ----------

sub onQueueNext(event as Object)
    task = event.getRoSGNode()
    r = task.result
    ' La computadora ya se saltó videos de la fila que sabe que no existen: también se dice.
    if task.error = "" and r <> invalid and r.skipped <> invalid and r.skipped.Count() > 0
        skipped = "Se saltó «" + r.skipped[0] + "»"
        if r.skipped.Count() > 1 then skipped = "Se saltaron " + r.skipped.Count().ToStr() + " videos"
        skipped = skipped + ": ya no está disponible en YouTube."
        if m.skipNote <> invalid and m.skipNote <> "" then m.skipNote = m.skipNote + " " + skipped else m.skipNote = skipped
    end if
    if task.error = "" and r <> invalid and r.entry <> invalid
        source = "fila"
        if r.source <> invalid and r.source = "related" then source = "recomendado"
        showUpNext(r.entry, source)
        return
    end if
    if m.skipNote <> invalid and m.skipNote <> ""   ' no hay nada después del video que no se pudo ver
        m.player.stop = true
        onPlayerClosed()
        showToastTone(m.skipNote, true, "error")
        m.skipNote = ""
        return
    end if
    nxt = ""
    prev = m.finished
    if prev <> invalid and prev.item <> invalid and prev.item["next"] <> invalid then nxt = prev.item["next"]   ' "next" es palabra reservada
    if nxt <> "" and m.lib.items[nxt] <> invalid
        it = m.lib.items[nxt]
        showUpNext({kind: "item", id: nxt, title: it.full_title, thumb: it.poster}, "episodio")
    else
        m.player.stop = true
        onPlayerClosed()
    end if
end sub

sub showUpNext(entry as Object, source as String)
    m.upNextEntry = entry
    m.upNextSource = source
    thumb = ""
    if entry.thumb <> invalid then thumb = m.server + entry.thumb
    if entry.kind = "yt" then rememberYt({id: entry.id, title: entry.title}, false)
    upNext = {title: entry.title, thumb: thumb, source: source}
    if m.skipNote <> invalid and m.skipNote <> ""   ' se saltó uno: el motivo arriba y solo 3 segundos
        upNext.note = m.skipNote
        upNext.seconds = 3
        m.skipNote = ""
    end if
    m.player.upNext = upNext
end sub

sub playUpNext()
    entry = m.upNextEntry
    if entry.kind = "item" and m.lib.items[entry.id] <> invalid and m.upNextSource = "episodio"
        startItem(entry.id, true, sameTracks(m.finished, m.lib.items[entry.id]))
    else
        playEntry(entry)
    end if
    if m.upNextSource = "fila" then loadLibrary()   ' la fila ya tiene uno menos
end sub

sub cancelUpNext()
    ' Si venía de la fila, vuelve a su lugar para no perderlo.
    e = m.upNextEntry
    if m.upNextSource = "fila" then post("/api/queue/add", {kind: e.kind, id: e.id, title: e.title, front: true}, "")
    m.player.stop = true
    onPlayerClosed()
end sub

' El mismo idioma de audio y subtítulos que el episodio anterior (el orden de pistas puede cambiar).
function sameTracks(prev as Object, it as Object) as Object
    options = {}
    if prev = invalid or prev.item = invalid or prev.item.audio.Count() = 0 then return options
    lang = prev.item.audio[prev.audio].lang
    for i = 0 to it.audio.Count() - 1
        if it.audio[i].lang = lang
            options.audio = i.ToStr()
            exit for
        end if
    end for
    options.sub = "-1"
    if prev.sub >= 0
        lang = prev.item.subs[prev.sub].lang
        for i = 0 to it.subs.Count() - 1
            if it.subs[i].lang = lang
                options.sub = i.ToStr()
                exit for
            end if
        end for
    end if
    return options
end function

sub playEntry(entry as Object)
    if entry.kind = "track"   ' una canción de la fila (Music.brs)
        t = musicTrack(entry.id)
        if t <> invalid
            playMusicCtx([t], 0, 0)
        else
            m.musicWant = entry
            loadMusic()
        end if
    else if entry.kind = "yt"
        rememberYt({id: entry.id, title: entry.title}, false)
        playYouTube(entry.id, -1)
    else if m.lib.items[entry.id] <> invalid
        startItem(entry.id, true, invalid)
    end if
end sub

' ---------- fila de reproducción ----------

' Se eligió algo de la fila: la Mac lo quita de la fila y se reproduce ya.
sub onQueueTaken(event as Object)
    r = event.getRoSGNode().result
    if r <> invalid and r.entry <> invalid then playEntry(r.entry)
    loadLibrary()
end sub

sub onQueued(event as Object)
    task = event.getRoSGNode()
    r = task.result
    if task.error <> "" or r = invalid
        detailMessage("No se pudo agregar: sin conexión con la computadora.", "error")
    else if r.ok = true
        detailMessage("Listo: en la fila de reproducción (" + countText(r.count, "en espera", "en espera") + ").", "ok")
        loadLibrary()
    else
        detailMessage(r.error, "error")
    end if
end sub

' Mensaje bajo los botones de la ficha: "ok" en limón, "error" en guinda claro.
sub detailMessage(text as String, tone as String)
    m.detail.messageTone = tone
    m.detail.message = text
end sub
