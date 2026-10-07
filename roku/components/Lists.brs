' Favoritos y listas de One TV (viven en la computadora, no en la cuenta de YouTube), lo que se hace con un video de la
' fila de reproducción (* sobre su tarjeta: verlo, subirlo, bajarlo o quitarlo), una lista entera a la fila y «Cargar
' más» en la búsqueda de YouTube. La lista para elegir es la de «Ver con otro» (MultiPicker): ctx "lists" o "queue".
' Contrato: GET /api/lists?video= -> {lists: [{id, title, count, source, has}]}; POST /api/lists/toggle {list, id, on,
' title}; POST /api/lists/create {title, id, video_title}; POST /api/queue/move {index, to}; POST /api/queue/add_list
' {id, front}; POST /api/yt/search {q, page} -> {results, page, more}.

' ---------- YouTube en vivo ----------

' «Agregar a En vivo» en la ficha de una transmisión: su canal queda en «En vivo» con esta transmisión mientras siga al
' aire y, cuando termine, la que el canal tenga en vivo.
sub addYouTubeLive()
    info = m.ytInfo[m.cur.vid]
    if info = invalid or info.channel_id = invalid or info.channel_id = "" then return
    showToast("Agregando el canal a En vivo…", true)
    post("/api/live/add", {url: "https://youtu.be/" + m.cur.vid}, "onYouTubeLiveAdded")   ' esta transmisión mientras siga al aire
end sub

sub onYouTubeLiveAdded(event as Object)
    task = event.getRoSGNode()
    r = task.result
    if task.error <> "" or r = invalid or r.ok <> true
        showToastTone(channelFailText("agregar el canal", task), true, "error")
        return
    end if
    showToast("«" + r.channel.name + "» ya está en En vivo.", true)
    loadLibrary()
end sub

' La ficha supo por la computadora (/api/yt/info) que el video es una transmisión en vivo: se rehace con lo de en vivo.
sub learnLiveInfo(vid as String, live as Boolean, viewers as Dynamic, channelId as Dynamic)
    info = m.ytInfo[vid]
    if info = invalid then info = {title: ytTitle(vid)}
    changed = (info.live = true) <> live
    info.live = live
    if viewers <> invalid then info.viewers = viewers
    if channelId <> invalid and channelId <> "" and info.channel_id <> channelId
        info.channel_id = channelId   ' de qué canal es: «Agregar a En vivo» lo necesita
        if live then changed = true
    end if
    m.ytInfo[vid] = info
    if changed then refreshYtDetail(vid)
end sub

' ---------- Favoritos ----------

function isFav(vid as String) as Boolean
    return m.favs[vid] = true
end function

function favButton(vid as String) as Object
    if isFav(vid) then return {id: "yt-fav", text: "En Favoritos", icon: "heart-filled"}
    return {id: "yt-fav", text: "Favorito", icon: "heart"}
end function

' Lo que dice la portada de YouTube: los que están en Favoritos (los más recientes).
sub learnFavorites(videos as Dynamic)
    if videos = invalid then return
    for each v in videos
        if v.id <> invalid then m.favs[v.id] = true
    end for
end sub

' El botón de la ficha cambia al instante; si la computadora no lo guarda, vuelve como estaba y lo dice.
sub pressFav()
    vid = m.cur.vid
    turnOn = not isFav(vid)
    m.favs[vid] = turnOn
    setListHas(vid, "fav", turnOn)
    buildYouTubeDetail(vid, true)
    post("/api/lists/toggle", {list: "fav", id: vid, on: turnOn, title: ytTitle(vid)}, "onFavToggled")
end sub

sub onFavToggled(event as Object)
    task = event.getRoSGNode()
    sent = sentBody(task)
    vid = sent["id"]
    wanted = sent["on"] = true
    r = task.result
    if task.error <> "" or r = invalid or r.ok <> true
        m.favs[vid] = not wanted
        setListHas(vid, "fav", not wanted)
        refreshYtDetail(vid)
        showToastTone(channelFailText("guardar en Favoritos", task), true, "error")
        return
    end if
    if wanted then showToast("Agregado a Favoritos.", true) else showToast("Quitado de Favoritos.", true)
    loadYouTubeHome()   ' la fila «Favoritos» y «Tus listas»
end sub

sub refreshYtDetail(vid as String)
    if m.detail.visible and m.cur <> invalid and m.cur.yt = true and m.cur.vid = vid then buildYouTubeDetail(vid, true)
end sub

' ---------- las listas de un video ----------

' Al abrir la ficha: en qué listas está (Favoritos incluido), para el botón y para «Agregar a lista».
sub loadVideoLists(vid as String)
    apiGet("/api/lists?video=" + vid, "onVideoLists")
end sub

sub onVideoLists(event as Object)
    task = event.getRoSGNode()
    r = task.result
    vid = Mid(task.url, Instr(1, task.url, "video=") + 6)
    if task.error <> "" or r = invalid or r.ok <> true or r.lists = invalid
        if m.listsWant = vid
            m.listsWant = ""
            showToastTone("No se pudieron leer tus listas: sin conexión con la computadora.", true, "error")
        end if
        return
    end if
    m.vidLists = {vid: vid, lists: r.lists}
    for each l in r.lists
        if l.id = "fav" then m.favs[vid] = l.has = true
    end for
    refreshYtDetail(vid)
    if m.listsWant = vid
        m.listsWant = ""
        openListsPicker(0)
    end if
end sub

sub setListHas(vid as String, listId as String, has as Boolean)
    if m.vidLists = invalid or m.vidLists.vid <> vid then return
    for each l in m.vidLists.lists
        if l.id = listId and (l.has = true) <> has
            l.has = has
            if has then l.count = toInt(l.count) + 1 else l.count = toInt(l.count) - 1
        end if
    end for
end sub

' «Agregar a lista» en la ficha: la lista para elegir, encima de la ficha. Si todavía no llegan las listas del video,
' se piden y se abre en cuanto lleguen.
sub pressAddToList()
    vid = m.cur.vid
    if m.vidLists = invalid or m.vidLists.vid <> vid
        m.listsWant = vid
        showToast("Leyendo tus listas…", true)
        loadVideoLists(vid)
        return
    end if
    openListsPicker(0)
end sub

sub openListsPicker(focus as Integer)
    m.pick = {ctx: "lists", mode: ""}
    m.picker.spec = listsSpec(focus)
    m.picker.visible = true
    m.picker.setFocus(true)
end sub

' «Lista nueva» arriba y luego Favoritos y tus listas (la usada más recientemente primero), con ✓ en las que ya lo tienen.
function listsSpec(focus as Integer) as Object
    vid = m.vidLists.vid
    entries = [{title: "Lista nueva", line: "Escribir el nombre: este video queda en ella", icon: "plus", source: {kind: "new"}}]
    for each l in m.vidLists.lists
        count = countText(toInt(l.count), "video", "videos")
        if l.source = "takeout" then count = count + "   ·   de tu cuenta de YouTube"
        line = count
        if l.has = true then line = "Está en esta lista   ·   " + count
        icon = "list-video"
        if l.id = "fav" then icon = "heart"
        if l.has = true then icon = "check"
        title = l.title
        if l.id = "fav" then title = "Favoritos"
        entries.Push({title: title, line: line, icon: icon, source: {kind: "list", id: l.id}})
    end for
    return {title: "Agregar a lista", note: "«" + ytTitle(vid) + "». Se guarda en la computadora: no cambia tu cuenta de YouTube.",
            hint: "OK: agregar o quitar   ·   ‹ o Atrás: cerrar", focus: focus,
            sections: [{title: "", entries: entries}]}
end function

' OK sobre un renglón: agrega o quita (la lista sigue abierta y el foco en el mismo renglón), o pide el nombre.
sub onListsPick(e as Object)
    if e.type <> "pick" or e.source = invalid
        closePicker(true)
        return
    end if
    if e.source.kind = "new"
        newListDialog()
        return
    end if
    vid = m.vidLists.vid
    row = 1
    target = invalid
    for i = 0 to m.vidLists.lists.Count() - 1
        if m.vidLists.lists[i].id = e.source.id
            target = m.vidLists.lists[i]
            row = i + 1
        end if
    end for
    if target = invalid then return
    turnOn = target.has <> true
    setListHas(vid, target.id, turnOn)
    if target.id = "fav"
        m.favs[vid] = turnOn
        refreshYtDetail(vid)
    end if
    m.picker.spec = listsSpec(row)
    post("/api/lists/toggle", {list: target.id, id: vid, on: turnOn, title: ytTitle(vid)}, "onListToggled")
end sub

sub onListToggled(event as Object)
    task = event.getRoSGNode()
    sent = sentBody(task)
    vid = sent["id"]
    listId = sent["list"]
    wanted = sent["on"] = true
    r = task.result
    if task.error <> "" or r = invalid or r.ok <> true
        setListHas(vid, listId, not wanted)
        if listId = "fav"
            m.favs[vid] = not wanted
            refreshYtDetail(vid)
        end if
        if m.picker.visible and m.pick.ctx = "lists" then m.picker.spec = listsSpec(listRow(listId))
        showToastTone(channelFailText("cambiar la lista", task), true, "error")
        return
    end if
    loadYouTubeHome()   ' «Tus listas» y Favoritos se ponen al día
end sub

function listRow(listId as String) as Integer
    if m.vidLists = invalid then return 0
    for i = 0 to m.vidLists.lists.Count() - 1
        if m.vidLists.lists[i].id = listId then return i + 1
    end for
    return 0
end function

' «Lista nueva»: el teclado del Roku pide el nombre; «Crear» la hace con este video adentro.
sub newListDialog()
    dlg = CreateObject("roSGNode", "StandardKeyboardDialog")
    dlg.title = "Lista nueva"
    dlg.message = ["El nombre de la lista. «" + ytTitle(m.vidLists.vid) + "» queda en ella."]
    dlg.buttons = ["Crear", "Cancelar"]
    dlg.palette = dialogPalette()
    dlg.observeField("buttonSelected", "onNewListButton")
    dlg.observeField("wasClosed", "onNewListClosed")
    m.newListDlg = dlg
    m.top.dialog = dlg
end sub

function dialogPalette() as Object
    p = CreateObject("roSGNode", "RSGPalette")
    p.colors = {DialogBackgroundColor: m.t.raise2, DialogItemColor: m.t.text, DialogTextColor: m.t.text,
                DialogFocusColor: m.t.lime, DialogFocusItemColor: m.t.onLime, DialogSecondaryTextColor: m.t.textSoft,
                DialogSecondaryItemColor: m.t.muted, DialogInputFieldColor: m.t.raise3, DialogKeyboardColor: m.t.raise3,
                DialogFootprintColor: m.t.lime}
    return p
end function

sub onNewListButton()
    dlg = m.newListDlg
    if dlg = invalid then return
    choice = dlg.buttonSelected
    name = dlg.text.Trim()
    if choice = 0 and name = "" then return   ' sin nombre no se crea: el teclado sigue abierto
    dlg.close = true
    if choice <> 0 then return
    vid = m.vidLists.vid
    post("/api/lists/create", {title: name, id: vid, video_title: ytTitle(vid)}, "onNewListCreated")
end sub

' El teclado se cerró (Crear, Cancelar o Atrás): la lista vuelve a recibir las teclas.
sub onNewListClosed()
    m.newListDlg = invalid
    if m.picker.visible and m.pick.ctx = "lists"
        m.picker.spec = listsSpec(0)
        m.picker.setFocus(true)
    end if
end sub

sub onNewListCreated(event as Object)
    task = event.getRoSGNode()
    r = task.result
    if task.error <> "" or r = invalid or r.ok <> true
        showToastTone(channelFailText("crear la lista", task), true, "error")
        return
    end if
    showToast("Lista nueva: «" + r.list.title + "», con este video.", true)
    if m.vidLists <> invalid
        m.listsWant = m.vidLists.vid   ' se vuelve a abrir con la lista nueva marcada
        loadVideoLists(m.vidLists.vid)
    end if
    loadYouTubeHome()
end sub

' ---------- la fila de reproducción: * sobre un video ----------

sub openQueueMenu(index as Integer)
    queue = m.lib.queue
    if queue = invalid or index < 0 or index >= queue.Count() then return
    q = queue[index]
    last = queue.Count() - 1
    place = "Sigue después de lo que se ve ahora."
    if index > 0 then place = "En " + (index + 1).ToStr() + ".º lugar de " + queue.Count().ToStr() + "."
    entries = [{title: "Ver ahora", line: "Empieza en la TV y sale de la fila", icon: "play", source: {kind: "take"}}]
    entries.Push({title: "Subir al principio", line: "Sigue después de lo que se ve ahora", icon: "list-start", source: {kind: "move", to: 0}, disabled: index = 0})
    entries.Push({title: "Subir un lugar", line: "", icon: "arrow-up", source: {kind: "move", to: index - 1}, disabled: index = 0})
    entries.Push({title: "Bajar un lugar", line: "", icon: "arrow-down", source: {kind: "move", to: index + 1}, disabled: index = last})
    entries.Push({title: "Mover al final", line: "", icon: "list-plus", source: {kind: "move", to: last}, disabled: index = last})
    entries.Push({title: "Quitar de la fila", line: "", icon: "x", source: {kind: "remove"}})
    m.queueMenuAt = index
    m.pick = {ctx: "queue", mode: ""}
    m.picker.spec = {title: "En la fila", note: "«" + q.title + "». " + place, sections: [{title: "", entries: entries}]}
    m.picker.visible = true
    m.picker.setFocus(true)
end sub

sub onQueueMenuPick(e as Object)
    index = m.queueMenuAt
    m.queueMenuAt = -1
    closePicker(e.type <> "pick")
    if e.type <> "pick" or e.source = invalid or index < 0 then return
    if e.source.kind = "take"
        post("/api/queue/take", {index: index}, "onQueueTaken")
    else if e.source.kind = "move"
        post("/api/queue/move", {index: index, to: e.source.to}, "onQueueChanged")
    else if e.source.kind = "remove"
        post("/api/queue/remove", {index: index}, "onQueueChanged")
    end if
end sub

' La computadora manda la fila nueva: se vuelve a dibujar y el foco queda en el video que se movió (o, si se quitó,
' en el que ocupa su lugar).
sub onQueueChanged(event as Object)
    task = event.getRoSGNode()
    r = task.result
    if task.error <> "" or r = invalid or r.ok <> true or r.queue = invalid
        showToastTone(channelFailText("cambiar la fila", task), true, "error")
        focusContent()
        return
    end if
    sent = sentBody(task)
    at = toInt(sent["index"])
    if r.index <> invalid then at = toInt(r.index)
    m.lib.queue = r.queue
    if sectionNames()[m.section] = "queue" and m.pages.Count() = 0
        renderSection()
        if r.queue.Count() > 0 then m.rows.jumpTo = [0, at]
    end if
    focusContent()
end sub

' ---------- una lista entera a la fila ----------

' «A la fila» en la página de una lista: a continuación, al final o al azar al final (sin reproducir nada).
sub openListQueueMenu(page as Object)
    m.listQueueId = page.id
    title = ""
    if page.title <> invalid then title = page.title
    entries = [{title: "A continuación", line: "Después de lo que se ve ahora, en su orden", icon: "list-start", source: {front: true, shuffle: false}},
               {title: "Al final de la fila", line: "Después de lo que ya está en la fila", icon: "list-plus", source: {front: false, shuffle: false}},
               {title: "Al azar, al final de la fila", line: "En desorden", icon: "shuffle", source: {front: false, shuffle: true}}]
    m.pick = {ctx: "listq", mode: ""}
    m.picker.spec = {title: "A la fila", note: "La lista «" + title + "» entera, sin reproducir nada.", sections: [{title: "", entries: entries}]}
    m.picker.visible = true
    m.picker.setFocus(true)
end sub

sub onListQueuePick(e as Object)
    closePicker(e.type <> "pick")
    if e.type <> "pick" or e.source = invalid then return
    listToQueue(m.listQueueId, e.source.front = true, e.source.shuffle = true)
    focusContent()
end sub

sub listToQueue(pid as String, front as Boolean, shuffle as Boolean)
    showToast("Agregando la lista a la fila…", true)
    post("/api/queue/add_list", {id: pid, front: front, shuffle: shuffle}, "onListQueued")
end sub

sub onListQueued(event as Object)
    task = event.getRoSGNode()
    r = task.result
    if task.error <> "" or r = invalid or r.ok <> true
        showToastTone(channelFailText("agregar la lista a la fila", task), true, "error")
        return
    end if
    sent = sentBody(task)
    where = "al final de la fila"
    if sent["front"] = true then where = "a continuación"
    added = toInt(r.added)
    if added < toInt(r.total)
        showToast(added.ToStr() + " de " + toInt(r.total).ToStr() + " videos " + where + " (la fila ya no tiene lugar).", true)
    else
        showToast(countText(added, "video", "videos") + " " + where + ".", true)
    end if
    loadLibrary()   ' la fila nueva
end sub

' ---------- búsqueda de YouTube: «Cargar más» ----------

' La tarjeta del final de los resultados (si YouTube tiene más): OK trae la página siguiente.
sub addMoreTile(root as Object)
    tile = newTile(root, "ytmore", "video", "searchVideo", false)
    tile.title = "Cargar más resultados"
    tile.line2 = "OK: traer más"
    tile.info = "Cargar más resultados de «" + m.ytQuery + "»"
end sub

sub loadMoreYouTube()
    if m.ytMoreBusy or not m.ytMore then return
    m.ytMoreBusy = true
    content = m.search.ytContent
    if content <> invalid
        tile = content.getChild(content.getChildCount() - 1)
        if tile <> invalid and tile.id = "ytmore"
            tile.title = "Cargando…"
            tile.line2 = ""
        end if
    end if
    post("/api/yt/search", {q: m.ytQuery, page: m.ytPage + 1, live: m.ytLive}, "onMoreYouTube")
end sub

' Los nuevos se agregan al final (sin repetir) y el foco queda en el primero de ellos.
sub onMoreYouTube(event as Object)
    m.ytMoreBusy = false
    task = event.getRoSGNode()
    r = task.result
    sent = sentBody(task)
    if sent["q"] <> m.ytQuery then return   ' ya se buscó otra cosa
    content = m.search.ytContent
    if content = invalid then return
    last = content.getChild(content.getChildCount() - 1)
    if task.error <> "" or r = invalid or r.ok <> true
        if last <> invalid and last.id = "ytmore"
            last.title = "Cargar más resultados"
            last.line2 = "No se pudo: OK para reintentar"
        end if
        return
    end if
    if last <> invalid and last.id = "ytmore" then content.removeChild(last)
    have = {}
    have.SetModeCaseSensitive()
    for i = 0 to content.getChildCount() - 1
        have[content.getChild(i).id] = true
    end for
    first = content.getChildCount()
    for each v in r.results
        if not have.DoesExist("yt:" + v.id) then addVideoTile(content, v, "searchVideo", false)
    end for
    m.ytPage = toInt(r.page)
    m.ytMore = r.more = true
    if m.ytMore then addMoreTile(content)
    m.search.ytContent = content   ' la búsqueda vuelve a dibujar la cuadrícula
    if first < content.getChildCount() then m.search.jumpTo = first
end sub
