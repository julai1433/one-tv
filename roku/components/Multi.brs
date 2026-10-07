' Varios a la vez desde la TV: «Ver con otro» (▼ en el reproductor o el botón de la ficha) y, dentro del mosaico,
' agregar o cambiar uno. La lista para elegir (MultiPicker) sale de la biblioteca: En vivo, Fila de reproducción y
' Vistos hace poco; lo elegido se junta con lo de ahora en una receta y el mosaico (Mosaic) se la pide a la
' computadora. Contrato: POST /api/mosaic/start {sources: [{kind: live|yt|item, id, audio?, start?}], focus}.

' ---------- fuentes ----------

' La pista de audio de una película o episodio como la pide el mosaico: «a2», «x0» o «na». Sale de su dirección
' /hls/<id>/a2/index.m3u8 (lo inverso de audioPosition). "" si no se sabe.
function audioCode(it as Object, index as Integer) as String
    if it = invalid or it.audio = invalid or index < 0 or index >= it.audio.Count() then return ""
    hls = it.audio[index].hls
    if hls = invalid then return ""
    parts = hls.Split("/")   ' ["", "hls", "<id>", "a2", "index.m3u8"]
    if parts.Count() >= 5 and parts[1] = "hls" then return parts[3]
    return ""
end function

' Lo que se ve ahora (o lo que tiene la ficha) como fuente del mosaico, empezando en «at» segundos; invalid si no se
' puede (p. ej. la película ya no está en la biblioteca).
function curSource(at as Integer) as Dynamic
    c = m.cur
    if c = invalid then return invalid
    if c.live = true then return {kind: "live", id: Mid(c.id, 6)}
    if c.yt = true
        s = {kind: "yt", id: c.vid}
        if at > 0 then s["start"] = at
        return s
    end if
    if m.lib = invalid or c.id = invalid or m.lib.items[c.id] = invalid then return invalid
    s = {kind: "item", id: c.id}
    code = audioCode(m.lib.items[c.id], c.audio)
    if code <> "" then s["audio"] = code
    if at > 0 then s["start"] = at
    return s
end function

function curTitle() as String
    c = m.cur
    if c = invalid then return ""
    if c.yt = true then return ytTitle(c.vid)
    if c.item <> invalid and c.item.full_title <> invalid then return c.item.full_title
    return ""
end function

' Desde la ficha no se ve nada todavía: lo de la ficha empieza donde se quedó (como «Continuar»).
function detailStart() as Integer
    c = m.cur
    if c = invalid then return 0
    if c.yt = true
        p = m.ytProgress[c.vid]
        if p <> invalid and p > 30 then return Int(p)
        return 0
    end if
    if c.id = invalid then return 0
    return resumePos(c.id)
end function

' ---------- la lista para elegir ----------

' Secciones de la lista: En vivo, Fila de reproducción y Vistos hace poco (los 20 más recientes). Lo que sale en una
' sección no se repite en la siguiente; lo que ya está en pantalla (exclude: «kind:id») sale desactivado.
function multiSections(exclude as Object) as Object
    sections = []
    if m.lib = invalid then return sections
    seen = {}
    seen.SetModeCaseSensitive()   ' los ids de YouTube distinguen mayúsculas
    live = []
    if m.lib.live <> invalid
        for each c in m.lib.live
            detail = "En vivo"
            if c.host <> invalid and c.host <> "" then detail = detail + " · " + c.host
            pushChoice(live, seen, exclude, {kind: "live", id: c.id}, c.name, detail, c.poster)
        end for
    end if
    if live.Count() > 0 then sections.Push({title: "En vivo", entries: live})
    queue = []
    if m.lib.queue <> invalid
        for each q in m.lib.queue
            pushVideo(queue, seen, exclude, q)
        end for
    end if
    if queue.Count() > 0 then sections.Push({title: "Fila de reproducción", entries: queue})
    recent = []
    if m.lib.history <> invalid
        for each h in m.lib.history
            if recent.Count() >= 20 then exit for
            pushVideo(recent, seen, exclude, h)
        end for
    end if
    if recent.Count() > 0 then sections.Push({title: "Vistos hace poco", entries: recent})
    return sections
end function

' Un video de la fila o del historial: YouTube (empieza donde se quedó) o una película o episodio (donde se quedó y
' con el idioma de este dispositivo).
sub pushVideo(list as Object, seen as Object, exclude as Object, v as Object)
    if v.id = invalid then return
    if v.kind = "yt"
        info = m.ytInfo[v.id]
        parts = ["YouTube"]
        channel = v.channel
        if (channel = invalid or channel = "") and info <> invalid then channel = info.channel
        if channel <> invalid and channel <> "" then parts.Push(channel)
        duration = toInt(v.duration)
        if duration = 0 and info <> invalid then duration = toInt(info.duration)
        if duration > 0 then parts.Push(fmtTime(duration))
        src = {kind: "yt", id: v.id}
        p = m.ytProgress[v.id]
        if p <> invalid and p > 30 then src["start"] = Int(p)
        title = v.title
        if title = invalid or title = "" then title = ytTitle(v.id)
        thumb = v.thumb
        if thumb = invalid or thumb = "" then thumb = "/yt/" + v.id + "/thumb.jpg"
        pushChoice(list, seen, exclude, src, title, parts.Join(" · "), thumb)
        return
    end if
    if m.lib.items[v.id] = invalid then return   ' ya no está en la biblioteca
    it = m.lib.items[v.id]
    kindText = "Película"
    if it.kind = "episode" then kindText = "Episodio"
    p = resumePos(v.id)
    rest = fmtDuration(it.duration)
    if p > 0 then rest = remainingText(p, it.duration)
    detail = kindText
    if rest <> "" then detail = detail + " · " + rest
    src = {kind: "item", id: v.id}
    code = audioCode(it, chooseAudio(it, m.prefs))
    if code <> "" then src["audio"] = code
    if p > 0 then src["start"] = p
    pushChoice(list, seen, exclude, src, it.full_title, detail, it.poster)
end sub

sub pushChoice(list as Object, seen as Object, exclude as Object, src as Object, title as Dynamic, detail as String, thumb as Dynamic)
    key = src.kind + ":" + src.id
    if seen.DoesExist(key) then return
    seen[key] = true
    if title = invalid or title = "" then title = "Video"
    e = {title: title, line: detail, thumb: "", disabled: false, source: src}
    if thumb <> invalid and thumb <> "" then e["thumb"] = m.server + thumb
    if exclude.DoesExist(key)
        e["disabled"] = true
        e["line"] = "Ya está en pantalla"
    end if
    list.Push(e)
end sub

' Abre la lista encima de lo que se ve. ctx: player | detail | mosaic (a dónde vuelve el foco); mode: with | add |
' change; onScreen: las fuentes que ya están en pantalla.
sub openPicker(ctx as String, mode as String, onScreen as Object, note as String)
    exclude = {}
    exclude.SetModeCaseSensitive()
    for each s in onScreen
        if s <> invalid and s.kind <> invalid and s.id <> invalid then exclude[s.kind + ":" + s.id] = true
    end for
    title = "Ver con otro"
    if mode = "add" then title = "Agregar"
    if mode = "change" then title = "Cambiar por"
    m.pick = {ctx: ctx, mode: mode}
    if ctx = "player" then m.player.covered = true   ' el reproductor no ofrece «saltar intro» ni toma el foco
    m.picker.spec = {title: title, note: note, sections: multiSections(exclude)}
    m.picker.visible = true
    m.picker.setFocus(true)
end sub

' ▼ en el reproductor (YouTube, canal en vivo, película o episodio).
sub openMultiFromPlayer()
    src = curSource(0)
    if src = invalid then return
    openPicker("player", "with", [src], "Junto a «" + curTitle() + "». La pantalla se divide y sigue sonando lo que veías.")
end sub

' «Ver con otro» en la ficha de un video de YouTube, una película o un episodio.
sub openMultiFromDetail()
    src = curSource(0)
    if src = invalid then return
    openPicker("detail", "with", [src], "Junto a «" + curTitle() + "». La pantalla se divide en dos y suena este.")
end sub

' Se cierra la lista; refocus: el foco vuelve a donde estaba (si no, lo que sigue se queda con él).
sub closePicker(refocus as Boolean)
    if not m.picker.visible then return
    ctx = m.pick.ctx
    m.picker.visible = false
    m.pick = {ctx: "", mode: ""}
    m.player.covered = false
    if not refocus then return
    if ctx = "player" and m.player.visible
        m.player.refocus = true
    else if (ctx = "detail" or ctx = "lists") and m.detail.visible
        m.detail.setFocus(true)
    else if ctx = "mosaic" and m.mosaic.visible
        m.mosaic.refocus = true
    else
        focusContent()
    end if
end sub

sub onPickerEvent()
    e = m.picker.event
    ctx = m.pick.ctx
    mode = m.pick.mode
    if ctx = "" then return   ' la lista ya se había cerrado por otra cosa
    if ctx = "lists"   ' «Agregar a lista» y el menú de un video de la fila (Lists.brs)
        onListsPick(e)
        return
    end if
    if ctx = "queue"
        onQueueMenuPick(e)
        return
    end if
    if ctx = "listq"
        onListQueuePick(e)
        return
    end if
    if ctx = "player" and mode = "opts"    ' «Audio y subtítulos» en el panel del reproductor (PlayerMenus.brs)
        onPlayerOptsPick(e)
        return
    end if
    if ctx = "tile"                        ' * sobre una tarjeta
        onTileMenuPick(e)
        return
    end if
    if ctx = "offlist"                     ' una lista guardada a medias (Offline.brs)
        onOfflineListMenuPick(e)
        return
    end if
    if e.type <> "pick" or e.source = invalid
        closePicker(true)
        return
    end if
    if ctx = "mosaic"
        closePicker(false)
        m.mosaic.edit = {mode: mode, source: e.source}
        return
    end if
    ' Lo que se veía sigue en el segundo de ahora (o, desde la ficha, donde se quedó) y suena; lo elegido, al lado.
    at = 0
    if ctx = "player" then at = Int(m.player.position) else at = detailStart()
    first = curSource(at)
    if first = invalid
        closePicker(true)
        return
    end if
    closePicker(false)
    title = ""
    if e.title <> invalid then title = e.title
    startMulti([first, e.source], 0, title)
end sub

' ---------- armar el mosaico ----------

' Desde el reproductor, lo que se ve sigue (con una nota arriba) mientras la computadora arma el mosaico; listo, se
' pasa a él (onMosaicEvent «ready»). Desde la ficha no hay nada que seguir viendo: la pantalla de «Armando».
sub startMulti(sources as Object, focus as Integer, title as String)
    if m.player.visible
        text = "Juntando este video con otro. Sigue este mientras tanto."
        if title <> "" then text = "Juntando este video con «" + title + "». Sigue este mientras tanto."
        m.player.note = {head: "VARIOS A LA VEZ", text: text}
        m.player.refocus = true
        m.mosaic.build = {sources: sources, focus: focus, background: true}
        return
    end if
    coverForMosaic()
    m.mosaic.build = {sources: sources, focus: focus}
end sub

' El mosaico «Agregar otro» o «Cambiar este»: la lista encima del mosaico, que sigue sonando.
sub openPickerForMosaic(e as Object)
    sources = e.sources
    if sources = invalid then sources = []
    if e.mode = "change"
        title = ""
        if e.title <> invalid then title = e.title
        note = "En lugar de «" + title + "». Sigue sonando el que elijas."
    else
        note = "Se suma a los " + sources.Count().ToStr() + " que se ven ahora; sigue sonando el mismo."
    end if
    openPicker("mosaic", e.mode, sources, note)
end sub
