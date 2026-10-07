' Lo que se abre encima de lo que se ve:
' - el panel del reproductor (PlayerPanel: ▼ con la barra a la vista), con la fila y lo visto que se le mandan aquí;
' - su botón «Audio y subtítulos» (la lista de la derecha, MultiPicker): audio original o doblaje de YouTube, audio y
'   subtítulos de la biblioteca;
' - * sobre una tarjeta (inicio, YouTube, búsquedas, canales, listas): verla, a la fila, a una lista, «No me
'   interesa» o «Silenciar canal», sin abrir la ficha.

' ---------- «Audio y subtítulos» (botón del panel) ----------

sub openPlayerOptions(e as Object)
    entries = []
    cur = m.cur
    if cur <> invalid and cur.yt = true and e.live <> true
        ' YouTube empieza siempre con el audio original; el doblaje (si YouTube lo tiene) se pide aquí.
        dub = ""
        if e.dub <> invalid then dub = e.dub
        dubs = e.dubs
        if dubs = invalid then dubs = []
        if dubs.Count() > 0
            entries.Push({title: "Audio original", line: nowText(dub = ""), icon: "audio", source: {kind: "dub", lang: ""}})
            for each d in dubs
                entries.Push({title: "Audio: " + d.name + " (doblaje)", line: dubLine(dub = d.lang), icon: "languages", source: {kind: "dub", lang: d.lang}})
            end for
        end if
    else if cur <> invalid and cur.item <> invalid and cur.live <> true
        it = cur.item
        if it.audio <> invalid and it.audio.Count() > 1
            for i = 0 to it.audio.Count() - 1
                entries.Push({title: "Audio: " + trackName(it.audio[i]), line: nowText(i = cur.audio), icon: "audio", source: {kind: "audio", index: i}})
            end for
        end if
        if it.subs <> invalid and it.subs.Count() > 0
            entries.Push({title: "Sin subtítulos", line: nowText(cur.sub < 0), icon: "captions", source: {kind: "sub", index: -1}})
            for i = 0 to it.subs.Count() - 1
                entries.Push({title: "Subtítulos: " + trackName(it.subs[i]), line: nowText(i = cur.sub), icon: "captions", source: {kind: "sub", index: i}})
            end for
        end if
    end if
    m.pick = {ctx: "player", mode: "opts"}
    m.player.covered = true
    m.picker.spec = {title: "Audio y subtítulos", note: curTitle(), sections: [{title: "", entries: entries}],
                     emptyPhrase: "Un solo audio", emptyCause: "Este video no tiene otros audios ni subtítulos."}
    m.picker.visible = true
    m.picker.setFocus(true)
end sub

function nowText(isNow as Boolean) as String
    if isNow then return "Es el que suena ahora"
    return ""
end function

function dubLine(isNow as Boolean) as String
    if isNow then return "Es el que suena ahora   ·   voz hecha por YouTube"
    return "Voz hecha por YouTube"
end function

sub onPlayerOptsPick(e as Object)
    closePicker(true)
    if e.type <> "pick" or e.source = invalid then return
    s = e.source
    if s.kind = "dub"
        playYouTubeDub(s.lang)
    else if s.kind = "audio"
        applyTracks({audio: s.index})
        savePrefs("audio")
    else if s.kind = "sub"
        applyTracks({sub: s.index})
        savePrefs("sub")
    end if
end sub

' El mismo video de YouTube, en el mismo segundo, con otro audio (lang "": el original).
sub playYouTubeDub(lang as String)
    if m.cur = invalid or m.cur.yt <> true then return
    req = ytRequest(m.cur.vid, Int(m.player.position))
    if lang <> "" then req.url = req.url + "?dub=" + lang
    req.dub = lang
    req.checked = true   ' ya se sabe que existe
    m.player.request = req
end sub

' ---------- el panel (▼ con la barra a la vista) ----------

sub sendPanelData()
    queue = []
    if m.lib <> invalid and m.lib.queue <> invalid
        for each q in m.lib.queue
            queue.Push({title: q.title, thumb: serverUrl(q.thumb)})
        end for
    end if
    history = []
    if m.lib <> invalid and m.lib.history <> invalid
        for each h in m.lib.history
            if history.Count() >= 12 then exit for
            history.Push({title: h.title, thumb: serverUrl(h.thumb)})
        end for
    end if
    ' ¿Hay audio o subtítulos para elegir? (YouTube: el reproductor ya sabe sus doblajes)
    tracks = false
    if m.cur <> invalid and m.cur.item <> invalid and m.cur.yt <> true and m.cur.live <> true and m.cur.music <> true
        tracks = m.cur.item.audio.Count() > 1 or m.cur.item.subs.Count() > 0
    end if
    songPrev = false
    songNext = false
    if m.cur <> invalid and m.cur.music = true and m.musicCtx <> invalid
        songPrev = m.musicCtx.index > 0
        songNext = m.musicCtx.index + 1 < m.musicCtx.tracks.Count()
    end if
    m.player.panelData = {queue: queue, history: history, tracks: tracks, songPrev: songPrev, songNext: songNext}
end sub

function serverUrl(path as Dynamic) as String
    if path = invalid or path = "" then return ""
    if Left(path, 4) = "http" then return path
    return m.server + path
end function

sub playHistory(index as Integer)
    if m.lib = invalid or m.lib.history = invalid or index >= m.lib.history.Count() then return
    h = m.lib.history[index]
    playEntry({kind: h.kind, id: h.id, title: h.title})
end sub

' ---------- *: una tarjeta ----------

' -> false si esa tarjeta no tiene menú (la tecla hace lo de siempre).
function openTileMenu(id as String) as Boolean
    entries = []
    title = ""
    if Left(id, 3) = "yt:"
        vid = Mid(id, 4)
        title = ytTitle(vid)
        info = m.ytInfo[vid]
        channel = ""
        if info <> invalid and info.channel <> invalid then channel = info.channel
        live = info <> invalid and info.live = true
        entries.Push({title: "Ver ahora", line: "", icon: "play", source: {kind: "play"}})
        if not live
            entries.Push({title: "A continuación", line: "Sigue después de lo que se ve", icon: "list-start", source: {kind: "next"}})
            entries.Push({title: "Al final de la fila", line: "", icon: "list-plus", source: {kind: "end"}})
        end if
        entries.Push({title: "Agregar a una lista o a Favoritos", line: "", icon: "bookmark-plus", source: {kind: "lists"}})
        entries.Push({title: "No me interesa", line: "No se te vuelve a recomendar", icon: "ban", source: {kind: "dismiss"}})
        muteTitle = "Silenciar este canal"
        if channel <> "" then muteTitle = "Silenciar «" + channel + "»"
        entries.Push({title: muteTitle, line: "No sale en tus canales, en lo nuevo ni en las recomendaciones", icon: "eye-off", source: {kind: "mute"}})
        m.tileMenu = {kind: "yt", id: vid, title: title, channel: channel}
    else if Left(id, 5) = "song:"   ' una canción de tu música (Music.brs)
        parts = id.Split(":")
        if parts.Count() < 3 or m.musicLists = invalid or m.musicLists[parts[1]] = invalid then return false
        tid = m.musicLists[parts[1]][toInt(parts[2])]
        t = musicTrack(tid)
        if t = invalid then return false
        title = t.title + " · " + t.artist
        entries.Push({title: "Escuchar ahora", line: "Siguen las demás de aquí", icon: "play", source: {kind: "play"}})
        entries.Push({title: "A continuación", line: "Sigue después de lo que se ve", icon: "list-start", source: {kind: "next"}})
        entries.Push({title: "Al final de la fila", line: "", icon: "list-plus", source: {kind: "end"}})
        m.tileMenu = {kind: "track", id: tid, title: title, tile: id}
    else if m.lib <> invalid and m.lib.items[id] <> invalid
        it = m.lib.items[id]
        title = it.full_title
        entries.Push({title: "Ver ahora", line: "", icon: "play", source: {kind: "play"}})
        entries.Push({title: "A continuación", line: "Sigue después de lo que se ve", icon: "list-start", source: {kind: "next"}})
        entries.Push({title: "Al final de la fila", line: "", icon: "list-plus", source: {kind: "end"}})
        m.tileMenu = {kind: "item", id: id, title: title}
    else
        return false
    end if
    m.pick = {ctx: "tile", mode: ""}
    m.picker.spec = {title: "Opciones", note: title, sections: [{title: "", entries: entries}]}
    m.picker.visible = true
    m.picker.setFocus(true)
    return true
end function

sub onTileMenuPick(e as Object)
    t = m.tileMenu
    closePicker(not (e.type = "pick" and e.source <> invalid and e.source.kind = "play"))   ' «Ver ahora»: el foco, al video
    if e.type <> "pick" or e.source = invalid or t = invalid then return
    k = e.source.kind
    if k = "play"
        if t.kind = "yt"
            playEntry({kind: "yt", id: t.id, title: t.title})
        else if t.kind = "track"
            activateMusic(t.tile, false)
        else
            startItem(t.id, true, invalid)
        end if
    else if k = "next" or k = "end"
        post("/api/queue/add", {kind: t.kind, id: t.id, title: t.title, front: k = "next"}, "onTileQueued")
    else if k = "lists"
        m.listsWant = t.id
        if m.vidLists <> invalid and m.vidLists.vid = t.id
            m.listsWant = ""
            openListsPicker(0)
        else
            showToast("Leyendo tus listas…", true)
            loadVideoLists(t.id)
        end if
    else if k = "dismiss"
        post("/api/yt/dismiss", {id: t.id}, "onTileDismissed")
    else if k = "mute"
        showToast("Silenciando el canal…", false)
        body = {video: t.id, title: t.channel}
        info = m.ytInfo[t.id]
        if info <> invalid and info.channel_id <> invalid then body["id"] = info.channel_id
        post("/api/yt/channel/hide", body, "onTileMuted")
    end if
end sub

' Desde la ficha de un video: «No me interesa» o «Silenciar canal» (el mensaje sale bajo los botones).
sub ytDetailDismiss(vid as String, mute as Boolean)
    if mute
        detailMessage("Silenciando el canal…", "ok")
        body = {video: vid}
        info = m.ytInfo[vid]
        if info <> invalid and info.channel_id <> invalid and info.channel_id <> "" then body["id"] = info.channel_id
        if info <> invalid and info.channel <> invalid then body["title"] = info.channel
        post("/api/yt/channel/hide", body, "onDetailMuted")
    else
        post("/api/yt/dismiss", {id: vid}, "onDetailDismissed")
    end if
end sub

sub onDetailDismissed(event as Object)
    task = event.getRoSGNode()
    r = task.result
    if task.error <> "" or r = invalid or r.ok <> true
        detailMessage(channelFailText("quitarlo de las recomendaciones", task), "error")
        return
    end if
    detailMessage("Listo: este video ya no se te va a recomendar.", "ok")
    loadYouTubeHome()
    loadLibrary()
end sub

sub onDetailMuted(event as Object)
    task = event.getRoSGNode()
    r = task.result
    if task.error <> "" or r = invalid or r.ok <> true
        detailMessage(channelFailText("silenciar el canal", task), "error")
        return
    end if
    name = "El canal"
    if r.title <> invalid and r.title <> "" then name = "«" + r.title + "»"
    detailMessage(name + " quedó silenciado: ya no sale en tus canales, en lo nuevo ni en las recomendaciones.", "ok")
    if r.id <> invalid then m.ytChannels = withoutChannel(m.ytChannels, r.id)
    loadChannels()
    loadYouTubeHome()
    loadHidden()
    loadLibrary()
end sub

sub onTileQueued(event as Object)
    task = event.getRoSGNode()
    r = task.result
    if task.error <> "" or r = invalid
        showToastTone("No se pudo agregar: sin conexión con la computadora.", true, "error")
    else if r.ok = true
        front = sentBody(task).front = true
        if front then where = "Sigue después de lo que se ve" else where = "Al final de la fila"
        showToast(where + " (" + countText(toInt(r.count), "en espera", "en espera") + ").", true)
        loadLibrary()
    else if r.error <> invalid
        showToastTone(r.error, true, "error")
    end if
end sub

sub onTileDismissed(event as Object)
    task = event.getRoSGNode()
    r = task.result
    if task.error <> "" or r = invalid or r.ok <> true
        showToastTone(channelFailText("quitarlo de las recomendaciones", task), true, "error")
        return
    end if
    showToast("Listo: no se te volverá a recomendar.", true)
    loadYouTubeHome()
    loadLibrary()
end sub

sub onTileMuted(event as Object)
    task = event.getRoSGNode()
    r = task.result
    if task.error <> "" or r = invalid or r.ok <> true
        showToastTone(channelFailText("silenciar el canal", task), true, "error")
        return
    end if
    name = "El canal"
    if r.title <> invalid and r.title <> "" then name = "«" + r.title + "»"
    showToast(name + " ya no sale en tus canales, en lo nuevo ni en las recomendaciones.", true)
    if r.id <> invalid then m.ytChannels = withoutChannel(m.ytChannels, r.id)
    loadChannels()
    loadYouTubeHome()
    loadHidden()
    loadLibrary()
end sub
