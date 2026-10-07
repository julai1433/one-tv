' Guardar sin conexión (rutas /api/offline* de mac/server.py): lo que la computadora baja para verlo sin internet.
' Aquí: leer lo guardado (/api/offline) y refrescarlo solo mientras importa, el botón de la ficha de un video, el botón
' de la página de una lista, la fila «Guardados» y la marca de las tarjetas. Las mismas palabras que la web.
' Todo el estado vive en m.off* (se inicializa en MainScene.init). Las llamadas van por apiGet/post (ApiTask).

' ---------- leer lo guardado ----------

sub loadOffline()
    now = CreateObject("roDateTime").AsSeconds()
    ' Si una petición se perdió, a los 25 s se vuelve a pedir.
    if m.offLoading and now - m.offLoadAt < 25 then return
    m.offLoading = true
    m.offLoadAt = now
    apiGet("/api/offline", "onOffline")
end sub

sub onOffline(event as Object)
    m.offLoading = false
    task = event.getRoSGNode()
    r = task.result
    if task.error <> "" or r = invalid or r.ok <> true then return
    vids = r.videos
    if vids = invalid then vids = []
    lists = r.lists
    if lists = invalid then lists = []
    byId = {}
    busy = 0
    full = []
    coarse = []
    for each v in vids
        id = offStr(v, "id")
        if id <> ""
            byId[id] = v
            state = offStr(v, "state")
            if state = "pendiente" or state = "bajando" then busy = busy + 1
            pct = toInt(v.progress)
            full.Push(id + ":" + state + ":" + pct.ToStr() + ":" + offStr(v, "error"))
            coarse.Push(id + ":" + state + ":" + Int(pct / 10).ToStr())
        end if
    end for
    for each l in lists
        full.Push("l" + offStr(l, "id") + ":" + toInt(l.count).ToStr() + ":" + toInt(l.done).ToStr())
    end for
    fullSig = full.Join("|")
    coarseSig = coarse.Join("|")
    firstTime = m.offById = invalid
    m.offById = byId
    m.offVideos = vids
    m.offLists = lists
    m.offBusy = busy
    if fullSig = m.offSig and not firstTime then return
    m.offSig = fullSig
    refreshOfflineUi()
    ' Las filas se rehacen solo si cambió algo que se ve en ellas (la marca, «Guardados»); el avance, de 10 en 10 %.
    if coarseSig <> m.offCoarse or firstTime
        m.offCoarse = coarseSig
        name = sectionNames()[m.section]
        if name = "home" or name = "youtube" then renderSection()
    end if
end sub

' Cada 3 s, solo mientras importa verlo: la ficha de un video abierta, la página de una lista o la sección YouTube con
' algo bajándose.
sub onOffTick()
    if m.player.visible or m.mosaic.visible or m.picker.visible then return
    wanted = false
    if m.detail.visible
        wanted = m.cur <> invalid and m.cur.yt = true
    else
        top = topPage()
        if top <> invalid
            wanted = top.kind = "playlist"
        else if m.offBusy > 0
            wanted = sectionNames()[m.section] = "youtube"
        end if
    end if
    if wanted then loadOffline()
end sub

function offStr(aa as Object, key as String) as String
    v = aa[key]
    if v = invalid then return ""
    if type(v) = "roString" or type(v) = "String" then return v
    return ""
end function

' La entrada de un video en /api/offline, o invalid si no está en la cola ni guardado.
function offEntry(vid as String) as Dynamic
    if m.offById = invalid then return invalid
    return m.offById[vid]
end function

' ¿Se dibuja la marca de «guardado sin conexión»? Lo que dice /api/offline; mientras no llega, lo que traía el video.
function isSaved(v as Object) as Boolean
    id = offStr(v, "id")
    if id = "" then return false
    if v.private = true then return false
    if m.offById <> invalid
        e = m.offById[id]
        if e = invalid then return false
        return offStr(e, "state") = "listo"
    end if
    return offStr(v, "offline") = "listo"
end function

' La ficha y la página de lista abiertas se ponen al día con lo que llegó.
sub refreshOfflineUi()
    if m.detail.visible and m.cur <> invalid and m.cur.yt = true and m.cur.vid <> invalid
        buildYouTubeDetail(m.cur.vid, true)
        offDetailMessage(m.cur.vid)
    end if
    top = topPage()
    if top <> invalid and top.kind = "playlist" then updatePlaylistControls(top)
end sub

' ---------- un video: botón de la ficha ----------

' El botón de la ficha. Sin guardar → «Guardar sin conexión»; en la cola → «En la cola para guardar» (OK cancela);
' bajando → «Guardando… 45 %» (OK cancela); error → «Reintentar guardado» (el motivo va bajo los botones); listo →
' «Guardado sin conexión» (OK quita, con un segundo OK para confirmar).
function offVideoButton(vid as String) as Object
    if m.offArmed = "v:" + vid then return {id: "yt-off", text: "OK otra vez para quitar", icon: "check", danger: true}
    e = offEntry(vid)
    if e = invalid then return {id: "yt-off", text: "Guardar sin conexión", icon: "download"}
    state = offStr(e, "state")
    if state = "pendiente" then return {id: "yt-off", text: "En la cola para guardar", icon: "download"}
    if state = "bajando" then return {id: "yt-off", text: "Guardando… " + toInt(e.progress).ToStr() + " %", icon: "download"}
    if state = "error" then return {id: "yt-off", text: "Reintentar guardado", icon: "rotate-ccw"}
    return {id: "yt-off", text: "Guardado sin conexión", icon: "check"}
end function

' Bajo los botones: el motivo si falló (guinda claro); si no, se borra lo que se puso antes.
sub offDetailMessage(vid as String)
    e = offEntry(vid)
    if e <> invalid and offStr(e, "state") = "error"
        reason = offStr(e, "error")
        if reason = "" then reason = "No se pudo guardar este video."
        detailMessage(reason, "error")
        m.offMsgOn = true
    else if m.offMsgOn
        m.offMsgOn = false
        detailMessage("", "ok")
    end if
end sub

' OK sobre el botón de la ficha.
sub pressOfflineVideo()
    if m.cur = invalid or m.cur.vid = invalid then return
    vid = m.cur.vid
    e = offEntry(vid)
    state = ""
    if e <> invalid then state = offStr(e, "state")
    if e = invalid or state = "error"
        disarmOffline()
        if m.offById = invalid then m.offById = {}
        m.offById[vid] = {id: vid, state: "pendiente", progress: 0, error: "", bytes: 0}   ' se ve ya; la computadora confirma enseguida
        refreshOfflineUi()
        post("/api/offline/save", {id: vid}, "onOfflineVideoSaved")
    else if state = "listo"
        key = "v:" + vid
        if m.offArmed = key
            disarmOffline()
            removeOfflineVideo(vid, "Se quitó de lo guardado sin conexión.")
        else
            armOffline(key)
            showToast("Pulsa OK otra vez para quitarlo de lo guardado: se borra de la computadora.", true)
        end if
    else
        removeOfflineVideo(vid, "Se canceló: ya no se guarda sin conexión.")
    end if
end sub

sub removeOfflineVideo(vid as String, doneText as String)
    m.offDoneText = doneText
    if m.offById <> invalid then m.offById.Delete(vid)
    refreshOfflineUi()
    post("/api/offline/remove", {id: vid}, "onOfflineRemoved")
end sub

sub onOfflineVideoSaved(event as Object)
    task = event.getRoSGNode()
    r = task.result
    if task.error <> "" or r = invalid or r.ok <> true
        vid = offStr(sentBody(task), "id")
        if vid <> "" and m.offById <> invalid then m.offById.Delete(vid)
        refreshOfflineUi()
        showToastTone(offFailText("guardar el video", task), true, "error")
    else
        if offStr(r, "state") = "listo" then showToast("Ya estaba guardado sin conexión.", true) else showToast("En la cola para guardar sin conexión.", true)
    end if
    m.offSig = ""
    loadOffline()
end sub

sub onOfflineRemoved(event as Object)
    task = event.getRoSGNode()
    r = task.result
    if task.error <> "" or r = invalid or r.ok <> true
        showToastTone(offFailText("quitarlo", task), true, "error")
    else if m.offDoneText <> ""
        showToast(m.offDoneText, true)
    end if
    m.offDoneText = ""
    m.offSig = ""
    loadOffline()
end sub

' «No se pudo guardar el video: sin conexión con la computadora.»
function offFailText(what as String, task as Object) as String
    r = task.result
    if task.error <> ""
        if Left(task.error, 5) = "HTTP " then return "No se pudo " + what + ": la computadora respondió con un error."
        return "No se pudo " + what + ": sin conexión con la computadora."
    end if
    if r <> invalid and offStr(r, "error") <> "" then return "No se pudo " + what + ": " + offStr(r, "error")
    return "No se pudo " + what + "."
end function

' ---------- una lista: botón de su página ----------

' Los videos de /api/offline que vienen de esa lista.
function offOwn(listId as String) as Object
    own = []
    if m.offVideos = invalid then return own
    for each v in m.offVideos
        lists = v.lists
        if lists <> invalid
            for each l in lists
                if l = listId then own.Push(v)
            end for
        end if
    end for
    return own
end function

function offListEntry(listId as String) as Dynamic
    for each l in m.offLists
        if offStr(l, "id") = listId then return l
    end for
    return invalid
end function

' «Guardar la lista sin conexión» / «Guardando 3 de 12» (OK cancela) / «Lista guardada» (OK quita, con segundo OK) /
' «Reintentar guardar la lista» si quedó a medias.
function offListButton(listId as String) as Object
    if m.offArmed = "l:" + listId then return {id: "offlist", text: "OK otra vez para quitar la lista", icon: "check", danger: true}
    l = offListEntry(listId)
    if l = invalid then return {id: "offlist", text: "Guardar la lista sin conexión", icon: "download"}
    own = offOwn(listId)
    count = toInt(l.count)
    if count = 0 then count = own.Count()
    done = toInt(l.done)
    if done > count then done = count
    if count > 0 and done >= count then return {id: "offlist", text: "Lista guardada", icon: "check"}
    for each v in own
        state = offStr(v, "state")
        if state = "pendiente" or state = "bajando"
            return {id: "offlist", text: "Guardando " + done.ToStr() + " de " + count.ToStr(), icon: "download"}
        end if
    end for
    return {id: "offlist", text: "Guardada a medias (" + done.ToStr() + " de " + count.ToStr() + ")", icon: "download"}
end function

' Los botones de arriba a la derecha de la página de una lista. Sin los videos cargados solo «Reproducir todo».
function playlistControls(page as Object) as Object
    list = [{id: "playall", text: "Reproducir todo", icon: "play"}]
    if page.videos = invalid or page.videos.Count() = 0 then return list
    list.Push({id: "q-menu", text: "A la fila", icon: "list-plus"})   ' la lista entera a la fila: menú corto (Lists.brs)
    list.Push(offListButton(page.id))
    return list
end function

' Cambia solo los botones (sin volver a armar la cuadrícula), si esa página de lista sigue arriba y ya cargó.
sub updatePlaylistControls(page as Object)
    top = topPage()
    if top = invalid or top.kind <> "playlist" or top.id <> page.id or top.videos = invalid then return
    m.pageGrid.controls = playlistControls(top)
end sub

sub pressOfflineList(page as Object)
    listId = page.id
    l = offListEntry(listId)
    own = offOwn(listId)
    active = false
    for each v in own
        state = offStr(v, "state")
        if state = "pendiente" or state = "bajando" then active = true
    end for
    full = false
    if l <> invalid
        count = toInt(l.count)
        if count > 0 and toInt(l.done) >= count then full = true
    end if
    if l <> invalid and full
        key = "l:" + listId
        if m.offArmed = key
            disarmOffline()
            removeOfflineList(listId, "Se quitó la lista de lo guardado sin conexión.")
        else
            armOffline(key)
            showToast("Pulsa OK otra vez para quitar la lista de lo guardado: se borran sus videos de la computadora.", true)
        end if
    else if l <> invalid and active
        removeOfflineList(listId, "Se canceló: la lista ya no se guarda sin conexión.")
    else if l <> invalid
        openOfflineListMenu(listId, l, own)   ' a medias y detenida: reintentar lo que falta o quitar lo guardado
    else
        disarmOffline()
        showToast("Guardando la lista sin conexión…", false)
        post("/api/offline/save", {list: listId}, "onOfflineListSaved")
    end if
end sub

' Una lista que quedó a medias (algunos videos no se pudieron bajar): reintentar lo que falta o quitar lo guardado.
sub openOfflineListMenu(listId as String, l as Object, own as Object)
    count = toInt(l.count)
    if count = 0 then count = own.Count()
    done = toInt(l.done)
    if done > count then done = count
    m.offMenuList = listId
    entries = [{title: "Reintentar lo que falta", line: done.ToStr() + " de " + count.ToStr() + " guardados", icon: "rotate-ccw", source: {kind: "retry"}},
               {title: "Quitar lo guardado de esta lista", line: "Se borran sus videos de la computadora", icon: "x", source: {kind: "remove"}}]
    m.pick = {ctx: "offlist", mode: ""}
    m.picker.spec = {title: "Sin conexión", note: "La lista quedó a medias.", sections: [{title: "", entries: entries}]}
    m.picker.visible = true
    m.picker.setFocus(true)
end sub

sub onOfflineListMenuPick(e as Object)
    listId = m.offMenuList
    closePicker(true)
    if e.type <> "pick" or e.source = invalid or listId = invalid then return
    if e.source.kind = "retry"
        showToast("Guardando lo que falta de la lista…", false)
        post("/api/offline/save", {list: listId}, "onOfflineListSaved")
    else
        removeOfflineList(listId, "Se quitó la lista de lo guardado sin conexión.")
    end if
end sub

sub removeOfflineList(listId as String, doneText as String)
    m.offDoneText = doneText
    post("/api/offline/remove", {list: listId}, "onOfflineRemoved")
end sub

sub onOfflineListSaved(event as Object)
    task = event.getRoSGNode()
    r = task.result
    if task.error <> "" or r = invalid or r.ok <> true
        showToastTone(offFailText("guardar la lista", task), true, "error")
    else
        showToast("Se empezó a guardar la lista sin conexión.", true)
    end if
    m.offSig = ""
    loadOffline()
end sub

' ---------- segundo OK para quitar ----------

' Primer OK sobre un guardado: el botón pide otro OK unos segundos (como «Ocultar canal»).
sub armOffline(key as String)
    m.offArmed = key
    m.offConfirmTimer.control = "stop"
    m.offConfirmTimer.control = "start"
    refreshOfflineUi()
end sub

' Pasó el tiempo, se cerró la ficha o la página: el botón vuelve a su texto.
sub disarmOffline()
    if m.offArmed = "" then return
    m.offArmed = ""
    m.offConfirmTimer.control = "stop"
    refreshOfflineUi()
end sub

' ---------- fila «Guardados» ----------

' Lo guardado: primero lo que se baja o está en la cola, luego lo que falló, luego lo guardado; lo más nuevo primero.
function offSorted() as Object
    vids = m.offVideos
    if vids = invalid then return []
    n = vids.Count()
    stamped = false
    for each v in vids
        if toInt(v.saved_at) > 0 or toInt(v.added) > 0 then stamped = true
    end for
    buckets = [[], [], []]
    for i = 0 to n - 1
        v = vids[i]
        state = offStr(v, "state")
        rank = 2
        if state = "pendiente" or state = "bajando"
            rank = 0
        else if state = "error"
            rank = 1
        end if
        ' Sin fecha, la computadora los da del más viejo al más nuevo: se invierte.
        order = n - 1 - i
        if stamped
            t = toInt(v.saved_at)
            if t = 0 then t = toInt(v.added)
            order = 2000000000 - t
        end if
        buckets[rank].Push({o: order * 1000# + i, v: v})
    end for
    out = []
    for each b in buckets
        b.SortBy("o")
        for each x in b
            out.Push(x.v)
        end for
    end for
    return out
end function

' Lo que dice debajo de la tarjeta.
function offSavedLine(e as Object) as String
    state = offStr(e, "state")
    if state = "bajando" then return "Guardando… " + toInt(e.progress).ToStr() + " %"
    if state = "pendiente" then return "En la cola para guardar"
    if state = "error"
        if offStr(e, "error") <> "" then return offStr(e, "error")
        return "No se pudo guardar"
    end if
    if offStr(e, "channel") <> "" then return offStr(e, "channel")
    return "Guardado sin conexión"
end function

sub addSavedTile(row as Object, e as Object)
    title = offStr(e, "title")
    if title = "" then title = "Video de YouTube"
    v = {id: offStr(e, "id"), title: title, channel: offStr(e, "channel"), duration: toInt(e.duration), thumb: offStr(e, "thumb")}
    addVideoTile(row, v, "video", true)
    tile = row.getChild(row.getChildCount() - 1)
    tile.line2 = offSavedLine(e)
    tile.info = title + "   ·   " + tile.line2
end sub

' La fila va entre «Seguir viendo» y «Vistos hace poco», como en la web, y solo si hay algo. Si aparece o desaparece,
' el foco guardado se corre una fila para seguir en la misma tarjeta.
sub addSavedRow(root as Object)
    prev = m.offRowAt
    m.offRowAt = -1
    vids = offSorted()
    if vids.Count() > 0
        row = newRow(root, "Guardados", "video")
        m.offRowAt = root.getChildCount() - 1
        for i = 0 to vids.Count() - 1
            if i >= 12 then exit for
            addSavedTile(row, vids[i])
        end for
    end if
    if prev = m.offRowAt then return
    f = m.rows.focus
    if f = invalid or f.Count() <> 2 then return
    if prev < 0 and f[0] >= m.offRowAt
        m.rows.focus = [f[0] + 1, f[1]]
    else if m.offRowAt < 0 and f[0] > prev
        m.rows.focus = [f[0] - 1, f[1]]
    end if
end sub
