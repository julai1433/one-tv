' Sección YouTube (sin anuncios, lo trae la Mac): «Buscar en YouTube» arriba y las filas Tus listas, Nuevos
' de tus canales, Tus canales, Porque viste…, Seguir viendo y Vistos hace poco. Páginas de canal y de lista.
' Canales: anclar (salen primero en «Tus canales», con un punto limón), ocultar (con un segundo OK) y la página
' de canales ocultos (Fila de reproducción → Ajustes generales), donde OK vuelve a mostrar uno.

' ---------- datos ----------

sub loadYouTubeHome()
    apiGet("/api/yt/home?device_id=" + m.deviceId, "onYouTubeHome")
end sub

sub onYouTubeHome(event as Object)
    task = event.getRoSGNode()
    if task.error <> "" or task.result = invalid then return
    m.ytHome = task.result
    m.ytHomeAt = CreateObject("roDateTime").AsSeconds()
    h = m.ytHome
    for each name in ["continue", "new", "recent"]
        list = h[name]
        if list <> invalid
            for each v in list
                rememberYt(v, name = "continue")
            end for
        end if
    end for
    if h.because <> invalid
        for each group in h.because
            for each v in group.videos
                rememberYt(v, false)
            end for
        end for
    end if
    if h.favorites <> invalid
        for each v in h.favorites
            rememberYt(v, false)
        end for
        learnFavorites(h.favorites)   ' Lists.brs
    end if
    name = sectionNames()[m.section]
    if name = "home" or name = "youtube" then renderSection()
end sub

sub loadChannels()
    apiGet("/api/yt/subscriptions", "onChannels")
end sub

sub onChannels(event as Object)
    task = event.getRoSGNode()
    if task.error <> "" or task.result = invalid then return
    m.ytChannels = task.result.channels
    if m.ytChannels = invalid then m.ytChannels = []
    if sectionNames()[m.section] = "youtube" then renderSection()
    m.followChannel = ""   ' ya se dibujó con el orden nuevo
end sub

' Título, canal y duración de cada video que pasa por la app (para la ficha y el reproductor).
sub rememberYt(v as Object, withProgress as Boolean)
    if v = invalid or v.id = invalid then return
    known = m.ytInfo[v.id]
    info = {title: v.title, channel: v.channel, duration: v.duration, thumb: v.thumb, published: v.published, published_approx: v.published_approx,
            live: v.live = true, viewers: v.viewers, channel_id: v.channel_id}
    if known <> invalid
        if info.title = invalid or info.title = "" then info.title = known.title
        if info.channel = invalid or info.channel = "" then info.channel = known.channel
        if info.duration = invalid or info.duration = 0 then info.duration = known.duration
        if info.channel_id = invalid or info.channel_id = "" then info.channel_id = known.channel_id
        if info.published = invalid or info.published = 0
            info.published = known.published
            info.published_approx = known.published_approx
        end if
    end if
    m.ytInfo[v.id] = info
    if withProgress and v.p <> invalid and v.p > 0 then m.ytProgress[v.id] = v.p
end sub

function ytTitle(vid as String) as String
    info = m.ytInfo[vid]
    if info <> invalid and info.title <> invalid and info.title <> "" then return info.title
    return "YouTube"
end function

function ytList(name as String) as Object
    if m.ytHome = invalid or m.ytHome[name] = invalid then return []
    return m.ytHome[name]
end function

' ---------- tarjetas ----------

' El canal y, si se sabe, cuándo se publicó: «Canal · hace 3 días» (solo «hace 3 días» si no hay canal).
function channelAgo(v as Object) as String
    parts = []
    if v.channel <> invalid and v.channel <> "" then parts.Push(v.channel)
    if v.published <> invalid
        ago = agoText(v.published)
        if ago <> "" then parts.Push(ago)
    end if
    return parts.Join(" · ")
end function

' «Canal · hace 3 días · 17:09» y, si quedó a medias, «quedan 5 min».
function videoLine(v as Object) as String
    parts = []
    line = channelAgo(v)
    if line <> "" then parts.Push(line)
    p = m.ytProgress[v.id]
    if p <> invalid and v.duration <> invalid and v.duration > 0
        parts.Push(remainingText(p, v.duration))
    else if v.duration <> invalid and v.duration > 0
        parts.Push(fmtTime(v.duration))
    end if
    return parts.Join(" · ")
end function

' Debajo de la tarjeta: el canal con su fecha («Canal · hace 3 días») y, si quedó a medias, «quedan 5 min» en lugar de
' la fecha, para que quepa (la duración va en la etiqueta de la miniatura).
function videoSub(v as Object) as String
    parts = []
    p = m.ytProgress[v.id]
    if p <> invalid and v.duration <> invalid and v.duration > 0
        if v.channel <> invalid and v.channel <> "" then parts.Push(v.channel)
        parts.Push(remainingText(p, v.duration))
    else
        line = channelAgo(v)
        if line <> "" then parts.Push(line)
    end if
    return parts.Join(" · ")
end function

sub addVideoTile(row as Object, v as Object, shape as String, inRow as Boolean)
    rememberYt(v, false)
    tile = newTile(row, "yt:" + v.id, "video", shape, inRow)
    tile.title = v.title
    if v.private = true then tile.title = "Video privado"
    tile.line2 = videoSub(v)
    if v.private <> true then tile.dur = toInt(v.duration)
    if v.live = true
        tile.dur = 0
        tile.addFields({liveTag: true})   ' «EN VIVO» en rojo sobre la miniatura (PosterItem)
        tile.line2 = liveLine(v)
    end if
    tile.saved = isSaved(v)   ' guardado sin conexión: marca de descarga (Offline.brs)
    thumb = v.thumb
    if thumb = invalid or thumb = "" then thumb = "/yt/" + v.id + "/thumb.jpg"
    tile.HDPosterUrl = m.server + thumb
    p = m.ytProgress[v.id]
    if p <> invalid and v.duration <> invalid and v.duration > 0 then tile.progress = p / v.duration
    line = videoLine(v)
    if v.live = true then line = "En vivo ahora   ·   " + liveLine(v)
    if line <> "" then tile.info = tile.title + "   ·   " + line else tile.info = tile.title
    tile.info = tile.info + "   ·   *: opciones"
end sub

' «Canal · 5,2 mil viendo» de una transmisión en vivo.
function liveLine(v as Object) as String
    parts = []
    if v.channel <> invalid and v.channel <> "" then parts.Push(v.channel)
    w = viewersText(v.viewers)
    if w <> "" then parts.Push(w)
    return parts.Join(" · ")
end function

function viewersText(n as Dynamic) as String
    count = toInt(n)
    if count <= 0 then return ""
    if count < 1000 then return count.ToStr() + " viendo"
    tenths = Int(count / 100)
    text = Int(tenths / 10).ToStr()
    if tenths mod 10 <> 0 and count < 100000 then text = text + "," + (tenths mod 10).ToStr()
    return text + " mil viendo"
end function

' Video de YouTube dentro de la fila de pósters de «Seguir viendo».
sub addYtCardTile(row as Object, v as Object)
    rememberYt(v, true)
    tile = newTile(row, "yt:" + v.id, "ytcard", "poster", true)
    tile.title = v.title
    tile.line2 = "YouTube"
    line = channelAgo(v)
    if line <> "" then tile.line2 = line
    tile.HDPosterUrl = m.server + "/yt/" + v.id + "/thumb-hd.jpg"   ' grande: se agranda para llenar el póster
    tile.dur = toInt(v.duration)
    tile.saved = isSaved(v)
    if v.p <> invalid and v.duration <> invalid and v.duration > 0 then tile.progress = v.p / v.duration
    tile.info = v.title + "   ·   " + videoLine(v) + "   ·   *: opciones"
end sub

sub addPlaylistTile(row as Object, pl as Object)
    tile = newTile(row, "list:" + pl.id, "video", "video", true)
    tile.title = pl.title
    count = 0
    if pl.count <> invalid then count = pl.count
    tile.line2 = countText(count, "video", "videos")
    if pl.thumb <> invalid and pl.thumb <> "" then tile.HDPosterUrl = m.server + pl.thumb
    tile.info = pl.title + "   ·   " + tile.line2
end sub

' Canal de «Tus canales»; los anclados (ya vienen primero) llevan un punto limón con la chincheta.
sub addChannelTile(row as Object, ch as Object)
    tile = newTile(row, "chan:" + ch.id, "channel", "channel", true)
    tile.title = ch.title
    tile.initials = initialsOf(ch.title)
    tile.addFields({avatar: m.server + "/ytc/" + ch.id + "/avatar.png"})
    pinned = ch.pinned = true
    tile.addFields({pinned: pinned})
    if pinned
        tile.info = ch.title + "   ·   Anclado   ·   OK: ver sus videos"
    else
        tile.info = ch.title + "   ·   OK: ver sus videos"
    end if
end sub

function tileTitle(id as String) as String
    if m.view = invalid then return ""
    root = invalid
    if m.view.hasField("content") then root = m.view.content
    if root = invalid then return ""
    ' Filas (nietos) o cuadrícula (hijos).
    for i = 0 to root.getChildCount() - 1
        child = root.getChild(i)
        if child.id = id then return child.title
        for j = 0 to child.getChildCount() - 1
            if child.getChild(j).id = id then return child.getChild(j).title
        end for
    end for
    return ""
end function

' ---------- la sección ----------

sub buildYouTube()
    root = CreateObject("roSGNode", "ContentNode")
    lists = ytList("playlists")
    chans = m.ytChannels
    ' Sin cuenta (no hay Takeout importado): un solo vacío, como en la web, en lugar de tres filas que dicen lo mismo.
    if m.ytHome <> invalid and chans <> invalid and lists.Count() = 0 and chans.Count() = 0 and ytList("new").Count() = 0
        row = newRow(root, "Tu cuenta de YouTube", "video")
        emptyRow(row, "Conecta tu YouTube", "Tus listas, lo nuevo de tus canales y tus canales aparecen aquí en cuanto la computadora tenga tu cuenta (el archivo de Google Takeout).", "Cómo traer tu cuenta", "takeout")
        addFavoritesRow(root)
    else
        ' 1. Tus listas, como las ordena la Mac (la escuchada más recientemente primero).
        row = newRow(root, "Tus listas", "video")
        for each pl in ytList("playlists")
            addPlaylistTile(row, pl)
        end for
        if row.getChildCount() = 0 then emptyRow(row, "Todavía no hay listas", "Salen cuando traes tus listas de YouTube a la computadora.", "Cómo traer tus listas", "takeout")
        ' 1b. Favoritos (solo si hay alguno): los más recientes primero; la lista entera está en «Tus listas».
        addFavoritesRow(root)
        ' 2. Nuevos de tus canales.
        row = newRow(root, "Nuevos de tus canales", "video")
        fillNewVideos(row)
        ' 3. Tus canales.
        row = newRow(root, "Tus canales", "channel")
        chanRow = root.getChildCount() - 1
        if m.ytChannels <> invalid
            for each ch in m.ytChannels
                ' Recién anclado o desanclado: el foco lo sigue a su nuevo lugar.
                if m.followChannel <> "" and ch.id = m.followChannel then m.rows.focus = [chanRow, row.getChildCount()]
                addChannelTile(row, ch)
            end for
        end if
        if row.getChildCount() = 0
            if m.ytChannels = invalid
                emptyRow(row, "Cargando tus canales", "Pidiendo a la computadora tus suscripciones…", "", "")
            else
                emptyRow(row, "Todavía no hay canales", "Salen cuando traes tus suscripciones de YouTube a la computadora.", "Cómo traer tus suscripciones", "takeout")
            end if
        end if
    end if
    ' 4. Porque viste…
    row = newRow(root, becauseTitle(), "video")
    fillBecause(row)
    ' 5. Seguir viendo (solo YouTube).
    row = newRow(root, "Seguir viendo", "video")
    for each v in ytList("continue")
        addVideoTile(row, v, "video", true)
    end for
    if row.getChildCount() = 0 then emptyRow(row, "Ningún video a medias", "Si dejas un video a la mitad, sigue aquí.", "Buscar en YouTube", "ytsearch")
    ' 6. Guardados sin conexión (solo si hay algo; Offline.brs).
    addSavedRow(root)
    ' 7. Vistos hace poco.
    row = newRow(root, "Vistos hace poco", "video")
    recent = ytList("recent")
    if recent.Count() = 0 and m.lib.youtube <> invalid then recent = m.lib.youtube
    for each v in recent
        addVideoTile(row, v, "video", true)
    end for
    if row.getChildCount() = 0 then emptyRow(row, "Todavía no hay videos vistos", "Lo que veas de YouTube en la TV queda aquí.", "Buscar en YouTube", "ytsearch")
    m.rows.header = "YouTube"
    m.rows.topButton = "Buscar en YouTube"
    m.rows.content = root
end sub

sub addFavoritesRow(root as Object)
    favs = ytList("favorites")
    if favs.Count() = 0 then return
    row = newRow(root, "Favoritos", "video")
    for each v in favs
        addVideoTile(row, v, "video", true)
    end for
end sub

sub fillNewVideos(row as Object)
    for each v in ytList("new")
        addVideoTile(row, v, "video", true)
    end for
    if row.getChildCount() > 0 then return
    if m.ytHome = invalid
        emptyRow(row, "Cargando", "Pidiendo a la computadora lo nuevo de tus canales…", "", "")
    else if m.ytChannels <> invalid and m.ytChannels.Count() > 0
        emptyRow(row, "Nada nuevo en tus canales", "La computadora revisa tus canales cada hora.", "Buscar en YouTube", "ytsearch")
    else
        emptyRow(row, "Todavía no hay canales", "Salen cuando traes tus suscripciones de YouTube a la computadora.", "Cómo traer tus suscripciones", "takeout")
    end if
end sub

function becauseTitle() as String
    groups = ytList("because")
    if groups.Count() > 0 and groups[0].seed <> invalid
        seed = groups[0].seed.title
        if seed = invalid then seed = ""
        if Len(seed) > 44 then seed = Left(seed, 42).Trim() + "…"
        return "Porque viste «" + seed + "»"
    end if
    return "Porque viste…"
end function

sub fillBecause(row as Object)
    groups = ytList("because")
    if groups.Count() > 0
        for each v in groups[0].videos
            addVideoTile(row, v, "video", true)
        end for
    end if
    if row.getChildCount() > 0 then return
    if m.ytHome = invalid
        emptyRow(row, "Cargando", "Pidiendo a la computadora videos parecidos…", "", "")
    else
        emptyRow(row, "Todavía nada parecido", "Cuando veas videos de YouTube, aquí salen otros parecidos.", "Buscar en YouTube", "ytsearch")
    end if
end sub

' ---------- página de un canal o de una lista ----------

sub buildChannelPage(page as Object)
    m.pageGrid.shape = "gridVideo"
    m.pageGrid.header = page.title
    m.pageGrid.controlStyle = "big"
    m.pageGrid.controlPrimary = false
    if page.pinned = invalid then page.pinned = channelPinned(page.id)
    if page.videos = invalid
        ' Los botones (Anclar, Ocultar canal) salen cuando llegan los videos: así el foco entra a la cuadrícula.
        m.pageGrid.controls = []
        m.pageGrid.count = ""
        m.pageGrid.emptySpec = {phrase: "Cargando los videos", cause: "La primera vez tarda unos segundos."}
        m.pageGrid.content = CreateObject("roSGNode", "ContentNode")   ' nodo nuevo: si no, queda el vacío de la página anterior
        if page.loading <> true
            page.loading = true
            m.loadingPage = page
            apiGet("/api/yt/channel?id=" + page.id, "onPageVideos")
        end if
        return
    end if
    m.pageGrid.controls = channelControls(page)
    fillPageGrid(page, "Este canal no tiene videos")
end sub

sub buildPlaylistPage(page as Object)
    m.pageGrid.shape = "gridVideo"
    m.pageGrid.header = page.title
    m.pageGrid.controlStyle = "big"
    m.pageGrid.controlPrimary = true
    m.pageGrid.controls = playlistControls(page)   ' «Reproducir todo» y, con los videos cargados, «Guardar la lista sin conexión»
    if page.videos = invalid
        m.pageGrid.count = ""
        m.pageGrid.emptySpec = {phrase: "Cargando la lista", cause: "La primera vez tarda unos segundos."}
        m.pageGrid.content = CreateObject("roSGNode", "ContentNode")
        if page.loading <> true
            page.loading = true
            m.loadingPage = page
            apiGet("/api/yt/playlist?id=" + page.id, "onPageVideos")
        end if
        return
    end if
    fillPageGrid(page, "Esta lista no tiene videos")
end sub

sub onPageVideos(event as Object)
    task = event.getRoSGNode()
    page = m.loadingPage
    if page = invalid then return
    page.loading = false
    r = task.result
    if task.error <> "" or r = invalid
        page.videos = []
        page.error = "No se pudo cargar: sin conexión con la computadora."
    else if r.ok <> true
        page.videos = []
        page.error = "YouTube: " + r.error
    else
        page.videos = r.videos
        if r.title <> invalid and r.title <> "" then page.title = r.title
        if page.kind = "channel"
            if r.pinned <> invalid then page.pinned = r.pinned = true
            if r.hidden <> invalid then page.hidden = r.hidden = true
        end if
    end if
    if m.pages.Count() > 0 and m.pages[m.pages.Count() - 1].id = page.id then renderPage(page)
end sub

sub fillPageGrid(page as Object, emptyPhrase as String)
    root = CreateObject("roSGNode", "ContentNode")
    for each v in page.videos
        addVideoTile(root, v, "gridVideo", false)
    end for
    m.pageGrid.header = page.title
    m.pageGrid.count = countText(root.getChildCount(), "video", "videos")
    if page.error <> invalid
        m.pageGrid.emptySpec = {phrase: "No se pudo cargar", cause: page.error}
    else
        m.pageGrid.emptySpec = {phrase: emptyPhrase, cause: ""}
    end if
    m.pageGrid.content = root
end sub

' «Reproducir todo»: la Mac pone el primero ya y el resto al frente de la fila. Si esta Mac no sabe hacerlo
' (o no alcanza al Roku), la tele lo hace sola.
sub playPlaylist(pid as String)
    m.playlistId = pid
    showToast("Preparando la lista…", true)
    post("/api/yt/playlist/play", {id: pid}, "onPlaylistPlay")
end sub

sub onPlaylistPlay(event as Object)
    task = event.getRoSGNode()
    r = task.result
    if task.error = "" and r <> invalid and r.ok = true
        showToast("Lista en la TV: " + countText(r.count, "video", "videos") + " en camino.", true)
        return
    end if
    ' A mano: hacen falta los videos de la lista.
    apiGet("/api/yt/playlist?id=" + m.playlistId, "onPlaylistForPlay")
end sub

sub onPlaylistForPlay(event as Object)
    task = event.getRoSGNode()
    r = task.result
    if task.error <> "" or r = invalid or r.ok <> true or r.videos = invalid or r.videos.Count() = 0
        showToast("No se pudo reproducir la lista.", true)
        return
    end if
    videos = []
    for each v in r.videos
        if v.private <> true then videos.Push(v)
    end for
    if videos.Count() = 0 then return
    for each v in videos
        rememberYt(v, false)
    end for
    ' El resto al frente de la fila, en orden: se agregan de uno en uno, del último al segundo.
    m.chain = []
    for i = videos.Count() - 1 to 1 step -1
        if i <= 50 then m.chain.Push(videos[i])
    end for
    addNextInChain()
    playYouTube(videos[0].id, 0)
end sub

sub addNextInChain()
    if m.chain = invalid or m.chain.Count() = 0
        loadLibrary()
        return
    end if
    v = m.chain.Shift()
    post("/api/queue/add", {kind: "yt", id: v.id, title: v.title, front: true}, "addNextInChain")
end sub

' ---------- fijar, silenciar y volver a mostrar un canal ----------

' Los botones de una página (arriba a la derecha): «Reproducir todo» en una lista; en un canal, anclar y ocultar.
sub onPageControl(id as String)
    page = topPage()
    if page = invalid then return
    if page.kind = "music"
        musicPageControl(page, id)   ' Music.brs
        return
    end if
    if id = "playall"
        playPlaylist(page.id)
    else if id = "q-menu"
        openListQueueMenu(page)   ' la lista entera a la fila (Lists.brs)
    else if id = "offlist"
        pressOfflineList(page)
    else if id = "pin" or id = "unpin"
        pinChannel(page, id = "pin")
    else if id = "hide"
        askHideChannel(page)
    else if id = "unhide"
        unhideChannel(page.id)
    end if
end sub

' «Anclar» o «Desanclar» primero y «Silenciar canal» (en guinda claro; un solo OK: el botón cambia a «Volver a
' mostrar», así se deshace ahí mismo). Un canal silenciado solo ofrece volver a mostrarlo.
function channelControls(page as Object) as Object
    if page.hidden = true then return [{id: "unhide", text: "Volver a mostrar", icon: "eye"}]
    list = []
    if page.pinned = true
        list.Push({id: "unpin", text: "Desanclar", icon: "pin-off"})
    else
        list.Push({id: "pin", text: "Anclar", icon: "pin"})
    end if
    list.Push({id: "hide", text: "Silenciar canal", icon: "eye-off", danger: true})
    return list
end function

' Cambia solo los botones (sin volver a armar la cuadrícula), si esa página de canal sigue arriba y ya cargó.
sub updateChannelControls(page as Object)
    top = topPage()
    if top = invalid or top.kind <> "channel" or top.id <> page.id or top.videos = invalid then return
    m.pageGrid.controls = channelControls(top)
end sub

function channelPinned(id as String) as Boolean
    if m.ytChannels = invalid then return false
    for each ch in m.ytChannels
        if ch.id = id then return ch.pinned = true
    end for
    return false
end function

' Lo que se mandó en un POST (para saber a qué canal responde la Mac).
function sentBody(task as Object) as Object
    body = invalid
    if task.body <> "" then body = ParseJson(task.body)
    if body = invalid then body = {}
    return body
end function

' «No se pudo ocultar el canal: sin conexión con la computadora.»
function channelFailText(what as String, task as Object) as String
    r = task.result
    if task.error <> ""
        if Left(task.error, 5) = "HTTP " then return "No se pudo " + what + ": la computadora respondió con un error."
        return "No se pudo " + what + ": sin conexión con la computadora."
    end if
    if r <> invalid and r.error <> invalid and r.error <> "" then return "No se pudo " + what + ": " + r.error
    return "No se pudo " + what + "."
end function

function withoutChannel(list as Dynamic, id as String) as Dynamic
    if list = invalid then return invalid
    out = []
    for each ch in list
        if ch.id <> id then out.Push(ch)
    end for
    return out
end function

sub pinChannel(page as Object, turnOn as Boolean)
    disarmHide()
    post("/api/yt/channel/pin", {id: page.id, title: page.title, on: turnOn}, "onChannelPinned")
end sub

sub onChannelPinned(event as Object)
    task = event.getRoSGNode()
    sent = sentBody(task)
    wanted = sent["on"] = true
    r = task.result
    if task.error <> "" or r = invalid or r.ok <> true
        if wanted then what = "anclar el canal" else what = "desanclar el canal"
        showToastTone(channelFailText(what, task), true, "error")
        return
    end if
    pinned = wanted
    if r.pinned <> invalid then pinned = r.pinned = true
    id = sent.id
    if id = invalid then id = ""
    top = topPage()
    if top <> invalid and top.kind = "channel" and top.id = id
        top.pinned = pinned
        updateChannelControls(top)
    end if
    if pinned
        showToast("Anclado: sale primero en Tus canales.", true)
    else
        showToast("Desanclado: vuelve a su lugar en Tus canales.", true)
    end if
    ' «Tus canales» se reordena (el orden lo pone la Mac) y el foco sigue al canal.
    m.followChannel = id
    loadChannels()
end sub

' Un OK silencia (se deshace en el mismo botón, que pasa a «Volver a mostrar»).
sub askHideChannel(page as Object)
    disarmHide()
    hideChannel(page)
end sub

' Pasó el tiempo, se eligió otra cosa o se salió de la página: «Ocultar canal» vuelve a pedir dos OK.
sub disarmHide()
    if m.hideArmed = "" then return
    armed = m.hideArmed
    m.hideArmed = ""
    m.confirmTimer.control = "stop"
    if m.toast.visible and m.toastText.text = m.hideAskText then hideToast()
    updateChannelControls({id: armed})
end sub

sub hideChannel(page as Object)
    showToast("Silenciando el canal…", false)
    post("/api/yt/channel/hide", {id: page.id, title: page.title}, "onChannelHidden")
end sub

sub onChannelHidden(event as Object)
    task = event.getRoSGNode()
    r = task.result
    if task.error <> "" or r = invalid or r.ok <> true
        showToastTone(channelFailText("silenciar el canal", task), true, "error")
        return
    end if
    id = sentBody(task).id
    if id = invalid then id = ""
    showToast("Canal silenciado: ya no sale en Tus canales, en lo nuevo ni en las recomendaciones.", true)
    ' Sale ya de «Tus canales» (sin esperar a la computadora) y YouTube se recarga sin él. La página se queda, con
    ' «Volver a mostrar» por si fue sin querer.
    m.ytChannels = withoutChannel(m.ytChannels, id)
    if sectionNames()[m.section] = "youtube" then renderSection()
    top = topPage()
    if top <> invalid and top.kind = "channel" and top.id = id
        top.hidden = true
        updateChannelControls(top)
    end if
    loadChannels()
    loadYouTubeHome()
    loadHidden()
end sub

sub unhideChannel(id as String)
    post("/api/yt/channel/unhide", {id: id}, "onChannelUnhidden")
end sub

' Nombre de un canal oculto (de la lista de ocultos o de su página abierta).
function hiddenTitle(id as String) as String
    if m.ytHidden <> invalid
        for each ch in m.ytHidden
            if ch.id = id and ch.title <> invalid then return ch.title
        end for
    end if
    top = topPage()
    if top <> invalid and top.kind = "channel" and top.id = id and top.title <> invalid then return top.title
    return ""
end function

sub onChannelUnhidden(event as Object)
    task = event.getRoSGNode()
    r = task.result
    if task.error <> "" or r = invalid or r.ok <> true
        showToastTone(channelFailText("volver a mostrar el canal", task), true, "error")
        return
    end if
    id = sentBody(task).id
    if id = invalid then id = ""
    title = hiddenTitle(id)
    if title = "" then showToast("El canal vuelve a salir en YouTube.", true) else showToast("«" + title + "» vuelve a salir en YouTube.", true)
    ' Sale ya de la lista de ocultos; luego la Mac manda la lista y YouTube lo trae de nuevo.
    m.ytHidden = withoutChannel(m.ytHidden, id)
    top = topPage()
    if top <> invalid and top.kind = "hidden" then renderPage(top)
    if top <> invalid and top.kind = "channel" and top.id = id
        top.hidden = false
        updateChannelControls(top)
    end if
    loadHidden()
    loadChannels()
    loadYouTubeHome()
end sub

' ---------- canales ocultos (Fila de reproducción → Ajustes generales) ----------

sub loadHidden()
    apiGet("/api/yt/hidden", "onHidden")
end sub

sub onHidden(event as Object)
    task = event.getRoSGNode()
    top = topPage()
    if task.error <> "" or task.result = invalid
        if top <> invalid and top.kind = "hidden" and m.ytHidden = invalid
            top.error = true
            renderPage(top)
        end if
        return
    end if
    list = task.result.channels
    if list = invalid then list = []
    m.ytHidden = list
    if sectionNames()[m.section] = "queue" then renderSection()   ' el número del botón
    if top <> invalid and top.kind = "hidden"
        top.error = false
        renderPage(top)
    end if
end sub

' Botón del ajuste «Canales ocultos»: cuántos hay.
function hiddenButtonText() as String
    if m.ytHidden = invalid then return "Ver los canales"
    n = m.ytHidden.Count()
    if n = 0 then return "Ninguno silenciado"
    return "Ver " + countText(n, "canal", "canales")
end function

' Los canales ocultos en círculos; OK sobre uno lo vuelve a mostrar. Sin ninguno: el vacío que enseña.
sub buildHiddenPage(page as Object)
    m.pageGrid.shape = "channel"
    m.pageGrid.header = "Canales silenciados"
    m.pageGrid.controls = []
    if m.ytHidden = invalid
        m.pageGrid.count = ""
        if page.error = true
            m.pageGrid.emptySpec = {phrase: "No se pudo cargar", cause: "Sin conexión con la computadora. Vuelve a intentarlo en un momento."}
        else
            m.pageGrid.emptySpec = {phrase: "Cargando", cause: "Pidiendo a la computadora tus canales silenciados…"}
        end if
        m.pageGrid.content = CreateObject("roSGNode", "ContentNode")   ' nodo nuevo: el vacío se vuelve a dibujar
        return
    end if
    root = CreateObject("roSGNode", "ContentNode")
    for each ch in m.ytHidden
        title = ch.title
        if title = invalid or title = "" then title = "Canal sin nombre"
        tile = newTile(root, "unhide:" + ch.id, "channel", "channel", false)
        tile.title = title
        tile.initials = initialsOf(title)
        tile.info = title + "   ·   OK: volver a mostrarlo en YouTube"
    end for
    m.pageGrid.count = countText(root.getChildCount(), "canal", "canales")
    m.pageGrid.emptySpec = {phrase: "No hay canales silenciados", cause: "En la página de un canal, o con * sobre uno de sus videos, elige «Silenciar canal»: deja de salir en Tus canales, en lo nuevo y en las recomendaciones.",
                            action: "Ir a YouTube", actionId: "youtube"}
    m.pageGrid.content = root
end sub

' ---------- buscar en YouTube ----------

sub searchYouTube(text as String, live as Boolean)
    m.ytQuery = text
    m.ytLive = live   ' «Solo en vivo»: también para «Cargar más»
    m.ytPage = 1
    m.ytMore = false
    m.ytMoreBusy = false
    post("/api/yt/search", {q: text, live: live}, "onYouTubeResults")
end sub

sub onYouTubeResults(event as Object)
    task = event.getRoSGNode()
    r = task.result
    if task.error <> "" or r = invalid
        m.search.status = "No se pudo buscar: sin conexión con la computadora."
        return
    end if
    if r.ok <> true
        m.search.status = "YouTube: " + r.error
        return
    end if
    if sentBody(task)["q"] <> m.ytQuery then return   ' ya se buscó otra cosa
    root = CreateObject("roSGNode", "ContentNode")
    for each v in r.results
        addVideoTile(root, v, "searchVideo", false)
    end for
    m.ytPage = 1
    if r.page <> invalid then m.ytPage = toInt(r.page)
    m.ytMore = r.more = true and root.getChildCount() > 0
    if m.ytMore then addMoreTile(root)   ' «Cargar más resultados» (Lists.brs)
    if root.getChildCount() = 0
        m.search.status = "YouTube no encontró nada con «" + m.ytQuery + "»."
        if m.ytLive then m.search.status = "Nadie transmite en vivo ahora con «" + m.ytQuery + "»."
    else
        m.search.status = "En YouTube: «" + m.ytQuery + "»"
        if m.ytLive then m.search.status = "En vivo en YouTube: «" + m.ytQuery + "»"
    end if
    m.search.ytContent = root
end sub

' ---------- ficha de un video ----------

sub openYouTubeDetail(vid as String)
    m.offMsgOn = false
    if m.vidLists <> invalid and m.vidLists.vid <> vid then m.vidLists = invalid
    m.listsWant = ""
    buildYouTubeDetail(vid, false)
    loadVideoLists(vid)   ' Favorito y «Agregar a lista» (Lists.brs)
    offDetailMessage(vid)
    loadOffline()   ' el botón «Guardar sin conexión» se pone al día en cuanto llega
end sub

' La ficha de un video. keepFocus = true: solo se rehacen los textos y botones (el estado de «sin conexión» cambió) sin
' mover el foco ni cerrar lo que esté abierto encima (el código QR, la sinopsis).
sub buildYouTubeDetail(vid as String, keepFocus as Boolean)
    info = m.ytInfo[vid]
    if info = invalid then info = {title: "YouTube"}
    live = info.live = true
    meta = []
    if live then meta.Push("EN VIVO")
    if info.channel <> invalid and info.channel <> "" then meta.Push(info.channel)
    if live and viewersText(info.viewers) <> "" then meta.Push(viewersText(info.viewers))
    if not live and info.duration <> invalid and info.duration > 0 then meta.Push(fmtTime(info.duration))
    when = ""
    if not live and info.published <> invalid then when = publishedText(info.published, info.published_approx)
    buttons = []
    p = m.ytProgress[vid]
    if live
        ' Una transmisión en vivo no termina ni se retoma: no va a la fila ni se guarda; su canal puede ir a «En vivo».
        buttons.Push({id: "yt-play", text: "Ver en vivo", icon: "play"})
        if multiViewOn() then buttons.Push({id: "multi", text: "Ver con otro", icon: "tv"})
        if info.channel_id <> invalid and info.channel_id <> "" then buttons.Push({id: "yt-addlive", text: "Agregar a En vivo", icon: "radio"})
        buttons.Push(favButton(vid))
        buttons.Push({id: "yt-lists", text: "Agregar a lista", icon: "bookmark-plus"})
        buttons.Push({id: "share", text: "Compartir (código QR)", icon: "qr-code"})
        buttons.Push({id: "yt-mute", text: "Silenciar canal", icon: "eye-off", danger: true})
    else if p <> invalid and p > 30
        buttons.Push({id: "yt-resume", text: "Continuar desde " + fmtTime(p), icon: "play"})
        buttons.Push({id: "yt-play", text: "Desde el principio", icon: "rotate-ccw"})
    else
        buttons.Push({id: "yt-play", text: "Reproducir ahora", icon: "play"})
    end if
    if not live
        if multiViewOn() then buttons.Push({id: "multi", text: "Ver con otro", icon: "tv"})   ' varios a la vez (Multi.brs)
        buttons.Push({id: "yt-next", text: "A continuación", icon: "list-start"})
        buttons.Push({id: "yt-queue", text: "Al final de la fila", icon: "list-plus"})
        buttons.Push(favButton(vid))   ' Favoritos y listas de One TV (Lists.brs)
        buttons.Push({id: "yt-lists", text: "Agregar a lista", icon: "bookmark-plus"})
        buttons.Push(offVideoButton(vid))   ' guardar sin conexión (Offline.brs)
        buttons.Push({id: "share", text: "Compartir (código QR)", icon: "qr-code"})
        buttons.Push({id: "yt-dismiss", text: "No me interesa", icon: "ban"})
        buttons.Push({id: "yt-mute", text: "Silenciar canal", icon: "eye-off", danger: true})
    end if
    if not keepFocus then m.cur = {id: "yt:" + vid, yt: true, vid: vid}
    data = {kind: "yt", title: ytTitle(vid), subtitle: "", meta: meta.Join("   ·   "), when: when, spanish: false,
            langs: "", image: m.server + "/yt/" + vid + "/thumb.jpg", descPath: "/api/yt/info?id=" + vid,
            tech: "", buttons: buttons, keepFocus: keepFocus,
            qr: {title: ytTitle(vid), image: m.server + "/yt/" + vid + "/qr.png", url: "youtu.be/" + vid}}
    if keepFocus then m.detail.data = data else showDetail(data)
end sub
