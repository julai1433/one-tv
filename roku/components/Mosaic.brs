' Varios a la vez: la escena manda el id del mosaico (open) o la receta para pedir uno (build); aquí se espera a que
' la computadora lo tenga listo, se reproduce y las flechas mueven el foco (el marco limón) y con él la pista de
' audio que suena. ▼ abre la tira de abajo: agregar otro, cambiar o quitar el que suena (la lista para elegir es de
' la escena; lo elegido vuelve por edit y el mosaico se rearma con la receta nueva).
sub init()
    m.t = theme()
    m.video = m.top.findNode("video")
    m.panes = m.top.findNode("panes")
    m.wait = m.top.findNode("wait")
    m.waitTitle = m.top.findNode("waitTitle")
    m.waitText = m.top.findNode("waitText")
    m.hint = m.top.findNode("hint")
    m.hintBg = m.top.findNode("hintBg")
    m.strip = m.top.findNode("strip")
    m.stripButtons = m.top.findNode("stripButtons")
    m.pollTimer = m.top.findNode("pollTimer")
    m.hintTimer = m.top.findNode("hintTimer")
    m.behindTimer = m.top.findNode("behindTimer")
    m.noteTimer = m.top.findNode("noteTimer")
    m.note = m.top.findNode("note")
    m.behind = invalid      ' el que se arma detrás de lo que se ve: {id, focus, polls}
    m.behindTask = invalid  ' su POST /api/mosaic/start en camino
    m.behindPoll = invalid  ' su /api/mosaic/status en camino
    m.id = ""
    m.task = invalid
    m.startTask = invalid  ' POST /api/mosaic/start en camino
    m.buildFocus = 0       ' cuál suena en el que se está pidiendo
    m.posts = []           ' las peticiones en camino (si no se guardan, pueden desaparecer antes de terminar)
    m.sources = []     ' [{kind, id, title, audio, start}] en el orden del mosaico (la receta de la computadora)
    m.titles = []
    m.rects = []       ' [x, y, ancho, alto] de cada video dentro del cuadro de 1920×1080
    m.nodes = []       ' por video: {edge, chipBg, chipIcon, chipText}
    m.tracks = []      ' pista de audio (Track del Roku) de cada video, en el mismo orden
    m.focus = 0
    m.started = false
    m.failed = false
    m.polls = 0
    m.grid = false

    m.top.findNode("bg").color = m.t.bg
    m.waitTitle.font = makeFont(72, "black")
    m.waitTitle.color = m.t.text
    m.waitText.font = makeFont(32)
    m.waitText.color = m.t.textSoft
    m.top.findNode("noteBg").color = m.t.overlay
    m.top.findNode("noteHead").font = makeFont(27, "bold")
    m.top.findNode("noteText").font = makeFont(32)
    m.top.findNode("noteText").color = m.t.text
    m.hintBg.color = m.t.overlay
    m.top.findNode("stripBg").color = m.t.overlay
    m.stripButtons.primary = false   ' ninguno es el principal: solo el que tiene el foco va en limón
    drawKeys()

    ' Desde Roku OS 13: cambiar de pista de audio sin detener el video (solo en HLS).
    m.video.seamlessAudioTrackSelection = true
    m.video.observeField("state", "onVideoState")
    m.pollTimer.observeField("fire", "onPoll")
    m.hintTimer.observeField("fire", "onHintTimer")
    m.behindTimer.observeField("fire", "onBehindTimer")
    m.noteTimer.observeField("fire", "hideNote")
    m.stripButtons.observeField("event", "onStripButton")
end sub

sub onOpen()
    o = m.top.open
    if o = invalid or o.id = invalid or o.id = "" then return
    f = 0
    if o.focus <> invalid then f = toInt(o.focus)
    if o.background = true
        cancelBehind()
        watchBehind(o.id, f)
        return
    end if
    begin(o.id, f, "ARMANDO EL VIDEO", "")
end sub

' Espera a que la computadora tenga listo el mosaico «mid» y lo reproduce; «focus»: cuál suena al empezar.
sub begin(mid as String, focus as Integer, title as String, text as String)
    stopAll()
    resetScreen()
    m.id = mid
    m.focus = focus
    if text = "" and title = "ARMANDO EL VIDEO" then text = "La computadora está juntando los videos en uno solo. Tarda unos segundos."
    showWait(title, text, false)
    m.top.visible = true
    m.top.setFocus(true)
    poll()
    m.pollTimer.control = "start"
end sub

sub resetScreen()
    m.sources = []
    m.titles = []
    m.tracks = []
    m.started = false
    m.failed = false
    m.polls = 0
    m.panes.removeChildren(m.panes.getChildren(-1, 0))
    m.nodes = []
    m.hint.visible = false
    m.strip.visible = false
end sub

sub onStop()
    cancelBehind()
    stopAll()
    m.strip.visible = false
    m.top.visible = false
end sub

sub stopAll()
    m.pollTimer.control = "stop"
    m.hintTimer.control = "stop"
    m.task = invalid
    m.startTask = invalid
    m.video.control = "stop"
end sub

' ---------- pedir uno nuevo (desde la TV: «Ver con otro», agregar, cambiar, quitar) ----------

sub onBuild()
    b = m.top.build
    if b = invalid or b.sources = invalid then return
    f = 0
    if b.focus <> invalid then f = toInt(b.focus)
    if b.background = true then buildBehind(b.sources, f) else build(b.sources, f)
end sub

' Pide a la computadora un mosaico con esta receta. El que se veía deja de verse ya y se le pide que pare (la
' computadora arma uno a la vez: al llegar el nuevo también lo detendría).
sub build(sources as Object, focus as Integer)
    cancelBehind()
    old = m.id
    stopAll()
    resetScreen()
    m.id = ""
    if old <> "" then postJson("/api/mosaic/stop", {id: old}, "")
    m.buildFocus = focus
    showWait("ARMANDO EL VIDEO", "La computadora está juntando los videos en uno solo. Tarda unos segundos.", false)
    m.top.visible = true
    m.top.setFocus(true)
    m.startTask = postJson("/api/mosaic/start", {sources: sources, focus: focus}, "onStarted")
end sub

sub onStarted(event as Object)
    task = event.getRoSGNode()
    r = task.result
    if m.startTask = invalid or not task.isSameNode(m.startTask)
        ' Ya se salió (o se pidió otro): el que acaba de armar la computadora no lo ve nadie.
        if task.error = "" and r <> invalid and r.ok = true and r.id <> invalid then postJson("/api/mosaic/stop", {id: r.id}, "")
        return
    end if
    m.startTask = invalid
    if task.error <> "" or r = invalid
        fail("No hubo respuesta de la computadora.")
        return
    end if
    if r.ok <> true or r.id = invalid or r.id = ""
        msg = "La computadora no pudo armar el video."
        if r.error <> invalid and r.error <> "" then msg = r.error
        fail(msg)
        return
    end if
    begin(r.id, m.buildFocus, "ARMANDO EL VIDEO", "")
end sub

' ---------- armar el siguiente sin quitar lo de ahora ----------

' Lo que se ve (el reproductor, o este mismo mosaico al agregar, cambiar o quitar) sigue en pantalla mientras la
' computadora arma el nuevo; con keep, allá el anterior también sigue andando y los videos empiezan un poco más
' adelante (lo que siguieron avanzando aquí). Listo el nuevo: dentro del mosaico se cambia solo; si no se ve el
' mosaico, se avisa a la escena (ready), que deja el reproductor y manda reveal.
sub buildBehind(sources as Object, focus as Integer)
    cancelBehind()
    m.behind = {id: "", focus: focus, polls: 0}
    m.behindTask = postJson("/api/mosaic/start", {sources: sources, focus: focus, keep: true}, "onBehindStarted")
    if m.top.visible then showNote("ARMANDO EL VIDEO NUEVO", "Sigue este mientras tanto. Tarda unos segundos.", false)
end sub

sub onBehindStarted(event as Object)
    task = event.getRoSGNode()
    r = task.result
    if m.behindTask = invalid or not task.isSameNode(m.behindTask)
        ' Se canceló (o se pidió otro) mientras llegaba: el que armó la computadora no lo ve nadie.
        if task.error = "" and r <> invalid and r.ok = true and r.id <> invalid then postJson("/api/mosaic/stop", {id: r.id}, "")
        return
    end if
    m.behindTask = invalid
    if task.error <> "" or r = invalid
        behindFailed("No hubo respuesta de la computadora.")
        return
    end if
    if r.ok <> true or r.id = invalid or r.id = ""
        msg = "La computadora no pudo armar el video."
        if r.error <> invalid and r.error <> "" then msg = r.error
        behindFailed(msg)
        return
    end if
    watchBehind(r.id, m.behind.focus)
end sub

sub watchBehind(mid as String, focus as Integer)
    m.behind = {id: mid, focus: focus, polls: 0}
    m.behindTimer.control = "start"
    pollBehind()
end sub

sub onBehindTimer()
    if m.behind = invalid
        m.behindTimer.control = "stop"
        return
    end if
    m.behind.polls = m.behind.polls + 1
    if m.behind.polls > 45
        behindFailed("La computadora tardó demasiado en armar el video. Prueba otra vez en un momento.")
        return
    end if
    pollBehind()
end sub

sub pollBehind()
    if m.behindPoll <> invalid or m.behind = invalid or m.behind.id = "" then return
    m.behindPoll = CreateObject("roSGNode", "ApiTask")
    m.behindPoll.url = m.top.server + "/api/mosaic/status?id=" + m.behind.id
    m.behindPoll.observeField("done", "onBehindStatus")
    m.behindPoll.control = "RUN"
end sub

sub onBehindStatus(event as Object)
    task = event.getRoSGNode()
    if m.behindPoll = invalid or not task.isSameNode(m.behindPoll) then return
    m.behindPoll = invalid
    if m.behind = invalid then return
    r = task.result
    if task.error <> "" or r = invalid then return   ' se vuelve a preguntar en un segundo
    if r.ok <> true or (r.error <> invalid and r.error <> "")
        msg = "La computadora no pudo armar el video."
        if r.error <> invalid and r.error <> "" then msg = r.error
        behindFailed(msg)
        return
    end if
    if r.ready <> true then return
    m.behindTimer.control = "stop"
    if m.top.visible
        switchToBehind()
    else
        m.top.event = {type: "ready", id: m.behind.id}
    end if
end sub

' El de detrás ya está listo: se deja el de ahora y se abre ese (arranca enseguida).
sub switchToBehind()
    b = m.behind
    if b = invalid or b.id = "" then return
    m.behind = invalid
    old = m.id
    hideNote()
    m.strip.visible = false
    m.top.visible = true
    m.top.setFocus(true)
    begin(b.id, b.focus, "UN MOMENTO", "Abriendo el video nuevo.")
    if old <> "" and old <> b.id then postJson("/api/mosaic/stop", {id: old}, "")
end sub

sub onReveal()
    switchToBehind()
end sub

sub behindFailed(message as String)
    cancelBehind()
    if m.top.visible
        showNote("NO SE PUDO", message, true)
    else
        m.top.event = {type: "buildError", message: message}
    end if
end sub

' Ya no hace falta el de detrás (se salió, se pidió otro o falló): se le dice a la computadora que lo detenga.
sub cancelBehind()
    m.behindTimer.control = "stop"
    if m.behind <> invalid and m.behind.id <> "" then postJson("/api/mosaic/stop", {id: m.behind.id}, "")
    m.behind = invalid
    m.behindTask = invalid
    m.behindPoll = invalid
    hideNote()
end sub

sub showNote(head as String, text as String, isError as Boolean)
    h = m.top.findNode("noteHead")
    t = m.top.findNode("noteText")
    h.text = head
    if isError then h.color = m.t.guindaLight else h.color = m.t.lime
    t.text = text
    t.width = 0
    w = t.boundingRect().width
    if w > 1300 then w = 1300
    t.width = w + 2
    hw = h.boundingRect().width
    if hw > w then w = hw
    bg = m.top.findNode("noteBg")
    bg.width = w + 64
    bg.height = 116
    m.note.visible = true
    m.noteTimer.control = "stop"
    if isError then m.noteTimer.control = "start"
end sub

sub hideNote()
    m.note.visible = false
    m.noteTimer.control = "stop"
end sub

' Lo elegido en la lista de la escena: se agrega al final (sigue sonando el mismo) o reemplaza al que suena (y suena
' el nuevo, en su lugar).
sub onEdit()
    e = m.top.edit
    sources = recipe()
    f = m.focus
    if f < 0 or f >= sources.Count() then f = 0
    if e = invalid or e.source = invalid or sources.Count() = 0
        onRefocus()   ' nada que hacer: el foco vuelve a la tira
        return
    end if
    if e.mode = "add" and sources.Count() < 4
        sources.Push(e.source)
    else if e.mode = "change"
        sources[f] = e.source
    else
        onRefocus()
        return
    end if
    rebuild(sources, f)
end sub

' Rearmar con otra receta: si este ya se está viendo, sigue en pantalla mientras se arma el nuevo.
sub rebuild(sources as Object, focus as Integer)
    if m.started and not m.failed
        m.strip.visible = false   ' se ve el mosaico de ahora con la nota «Armando el video nuevo»
        m.top.setFocus(true)
        buildBehind(sources, focus)
    else
        build(sources, focus)
    end if
end sub

' La receta de ahora para rearmarlo: cada video sigue en el segundo que va (su inicio más lo que lleva el mosaico);
' los canales en vivo, en vivo; las películas, con su pista de audio.
function recipe() as Object
    at = 0
    if m.started then at = Int(m.video.position)
    out = []
    for each s in m.sources
        o = {kind: s.kind, id: s.id}
        if s.kind <> "live"
            secs = at
            if s.start <> invalid then secs = secs + toInt(s.start)
            if secs > 0 then o["start"] = secs
        end if
        if s.kind = "item" and s.audio <> invalid then o["audio"] = s.audio
        out.Push(o)
    end for
    return out
end function

' POST con JSON a la computadora; devuelve la tarea.
function postJson(path as String, body as Object, callback as String) as Object
    task = CreateObject("roSGNode", "ApiTask")
    task.url = m.top.server + path
    task.body = FormatJson(body)
    if callback <> "" then task.observeField("done", callback)
    task.control = "RUN"
    m.posts.Push(task)
    if m.posts.Count() > 6 then m.posts.Shift()
    return task
end function

' ---------- esperar a la computadora ----------

sub onPoll()
    m.polls = m.polls + 1
    if m.polls > 45
        fail("La computadora tardó demasiado en armar el video. Prueba otra vez en un momento.")
        return
    end if
    poll()
end sub

sub poll()
    if m.task <> invalid then return   ' una pregunta a la vez
    m.task = CreateObject("roSGNode", "ApiTask")
    m.task.url = m.top.server + "/api/mosaic/status?id=" + m.id
    m.task.observeField("done", "onStatus")
    m.task.control = "RUN"
end sub

sub onStatus(event as Object)
    task = event.getRoSGNode()
    if m.task = invalid or not task.isSameNode(m.task) then return   ' ya se cerró o se abrió otro
    m.task = invalid
    r = task.result
    if task.error <> "" or r = invalid then return   ' se vuelve a preguntar en un segundo
    if r.ok <> true or (r.error <> invalid and r.error <> "")
        msg = "La computadora no pudo armar el video."
        if r.error <> invalid and r.error <> "" then msg = r.error
        fail(msg)
        return
    end if
    if m.sources.Count() = 0 and r.sources <> invalid and r.sources.Count() > 0
        m.sources = r.sources
        if r.tracks <> invalid then m.titles = r.tracks
        layoutPanes()
    end if
    if r.ready = true and not m.started then startVideo(r)
end sub

sub startVideo(r as Object)
    m.started = true
    m.pollTimer.control = "stop"
    url = m.top.server + "/mosaic/" + m.id + "/master.m3u8"
    if r.url <> invalid and r.url <> "" then url = m.top.server + r.url
    c = CreateObject("roSGNode", "ContentNode")
    c.url = url
    c.streamFormat = "hls"
    c.title = "Varios a la vez"
    c.Live = true
    print "[cine] mosaico: reproducir "; url
    m.video.content = c
    m.video.control = "play"
end sub

sub onVideoState()
    state = m.video.state
    print "[cine] mosaico: "; state
    if not m.started then return
    if state = "playing"
        m.wait.visible = false
        m.panes.visible = true
        if m.tracks.Count() = 0
            readTracks()
            paintFocus()
            if not m.strip.visible then showHint()
        end if
    else if state = "error"
        print "[cine] mosaico: error "; m.video.errorCode; " "; m.video.errorMsg; " "; FormatJson(m.video.errorInfo)
        fail("El video armado se cortó. Prueba otra vez en un momento.")
    else if state = "finished"
        close("closed", -1)   ' se acabaron las fuentes (p. ej. dos videos que terminaron)
    end if
end sub

' Las pistas de audio que ve el Roku, en el orden de los videos: primero por nombre (la computadora le pone a cada
' pista el título de su video) y, si no coincide, por orden.
sub readTracks()
    found = m.video.availableAudioTracks
    print "[cine] mosaico: pistas "; FormatJson(found)
    m.tracks = []
    if found = invalid then return
    for i = 0 to m.sources.Count() - 1
        want = ""
        if i < m.titles.Count() then want = m.titles[i]
        track = invalid
        for each a in found
            if track = invalid and want <> "" and a.Name = want then track = a.Track
        end for
        if track = invalid and i < found.Count() then track = found[i].Track
        if track <> invalid then m.tracks.Push(track)
    end for
end sub

sub fail(message as String)
    if m.failed then return
    m.failed = true
    stopAll()
    m.panes.visible = false
    m.hint.visible = false
    m.strip.visible = false
    if m.stripButtons.hasFocus() then m.top.setFocus(true)
    showWait("NO SE PUDO", message + "  Atrás: volver.", true)
end sub

sub showWait(title as String, text as String, isError as Boolean)
    m.waitTitle.text = marquee(title)
    m.waitTitle.color = m.t.text
    if isError then m.waitTitle.color = m.t.guindaLight
    m.waitText.text = text
    m.wait.visible = true
    m.panes.visible = false
end sub

' ---------- dibujo ----------

' Mismo acomodo que arma la computadora (mac/mosaic.py): dos lado a lado a media altura; tres o cuatro en 2×2.
sub layoutPanes()
    n = m.sources.Count()
    m.grid = n > 2
    if m.grid
        m.rects = [[0, 0, 960, 540], [960, 0, 960, 540], [0, 540, 960, 540], [960, 540, 960, 540]]
        if n = 3 then m.rects[2] = [480, 540, 960, 540]   ' con tres, el tercero va centrado abajo (mac/mosaic.py: xstack)
    else
        m.rects = [[0, 270, 960, 540], [960, 270, 960, 540]]
    end if
    if m.focus >= n then m.focus = 0
    m.panes.removeChildren(m.panes.getChildren(-1, 0))
    m.nodes = []
    for i = 0 to n - 1
        r = m.rects[i]
        g = m.panes.createChild("Group")
        g.translation = [r[0], r[1]]
        edge = g.createChild("Poster")
        edge.width = r[2]
        edge.height = r[3]
        chipBg = g.createChild("Rectangle")
        chipBg.translation = [24, 24]
        chipBg.height = 56
        chipIcon = g.createChild("Poster")
        chipIcon.translation = [36, 36]
        chipIcon.width = 32
        chipIcon.height = 32
        chipText = g.createChild("Label")
        chipText.font = makeFont(27, "bold")
        chipText.translation = [80, 24]
        chipText.height = 56
        chipText.vertAlign = "center"
        chipText.text = paneTitle(i)
        textW = chipText.boundingRect().width
        maxW = r[2] - 48 - 56 - 20
        if textW > maxW then textW = maxW
        chipText.width = textW
        chipBg.width = 56 + textW + 20
        m.nodes.Push({edge: edge, chipBg: chipBg, chipIcon: chipIcon, chipText: chipText})
    end for
    ' Dos lado a lado: las teclas van en la franja negra de abajo, siempre. En cuadrícula, encima del video un rato.
    m.hintBg.visible = m.grid
    paintFocus()
end sub

function paneTitle(i as Integer) as String
    if i < 0 or i >= m.sources.Count() then return ""
    s = m.sources[i]
    if s.title <> invalid and s.title <> "" then return s.title
    if i < m.titles.Count() then return m.titles[i]
    return "Video " + (i + 1).ToStr()
end function

' El que suena: marco de foco limón y etiqueta limón con el ícono de sonido. Los demás: línea fina y «sin sonido».
sub paintFocus()
    for i = 0 to m.nodes.Count() - 1
        n = m.nodes[i]
        isOn = (i = m.focus)
        if isOn
            n.edge.uri = "pkg:/images/focus.9.png"
            n.edge.blendColor = m.t.lime
            n.chipBg.color = m.t.lime
            n.chipIcon.uri = "pkg:/images/icons/sound.png"
            n.chipIcon.blendColor = m.t.onLime
            n.chipText.color = m.t.onLime
        else
            n.edge.uri = "pkg:/images/line.9.png"
            n.edge.blendColor = m.t.line
            n.chipBg.color = m.t.overlay
            n.chipIcon.uri = "pkg:/images/icons/mute.png"
            n.chipIcon.blendColor = m.t.textSoft
            n.chipText.color = m.t.textSoft
        end if
    end for
    if m.focus < m.tracks.Count()
        want = m.tracks[m.focus]
        if m.video.audioTrack <> want
            print "[cine] mosaico: suena "; m.focus; " (pista "; want; ")"
            m.video.audioTrack = want
        end if
    end if
end sub

' Teclas: flechas (dibujadas), OK, ▼ y Atrás, con el estilo del resto de la app (pieza «tecla» de DESIGN.md).
sub drawKeys()
    group = m.top.findNode("hintKeys")
    x = 0
    keys = [{key: "arrows", text: "Cambiar cuál suena"}, {key: "OK", text: "Ver solo este"},
            {key: "down", text: "Más opciones"}, {key: "Atrás", text: "Salir"}]
    for each k in keys
        capW = 76
        edge = group.createChild("Poster")
        edge.uri = "pkg:/images/line.9.png"
        edge.blendColor = m.t.edge
        edge.translation = [x, 0]
        edge.height = 52
        if k.key = "arrows"
            capW = 104
            for j = 0 to 1
                arrow = group.createChild("Poster")
                arrow.uri = "pkg:/images/icons/chevron-right.png"
                arrow.blendColor = m.t.text
                arrow.width = 32
                arrow.height = 32
                arrow.translation = [x + 16 + j * 40, 10]
                if j = 0
                    arrow.scaleRotateCenter = [16, 16]
                    arrow.rotation = 3.14159
                end if
            end for
        else if k.key = "down"
            capW = 64
            arrow = group.createChild("Poster")
            arrow.uri = "pkg:/images/icons/chevron-right.png"
            arrow.blendColor = m.t.text
            arrow.width = 32
            arrow.height = 32
            arrow.translation = [x + 16, 10]
            arrow.scaleRotateCenter = [16, 16]
            arrow.rotation = -1.5708   ' la flecha › girada un cuarto de vuelta: ▼
        else
            cap = group.createChild("Label")
            cap.font = makeFont(27, "bold")
            cap.color = m.t.text
            cap.text = k.key
            capW = Int(cap.boundingRect().width) + 32
            cap.translation = [x, 0]
            cap.width = capW
            cap.height = 52
            cap.horizAlign = "center"
            cap.vertAlign = "center"
        end if
        edge.width = capW
        word = group.createChild("Label")
        word.font = makeFont(32)
        word.color = m.t.text
        word.text = k.text
        word.translation = [x + capW + 16, 0]
        word.height = 52
        word.vertAlign = "center"
        x = x + capW + 16 + Int(word.boundingRect().width) + 56
    end for
end sub

sub showHint()
    m.hint.visible = true
    if m.grid
        m.hintTimer.control = "stop"
        m.hintTimer.control = "start"
    end if
end sub

sub onHintTimer()
    if m.grid then m.hint.visible = false
end sub

' ---------- la tira de abajo (▼) ----------

sub openStrip()
    buttons = []
    if m.sources.Count() < 4 then buttons.Push({id: "add", text: "Agregar otro", icon: "list-plus"})
    buttons.Push({id: "change", text: "Cambiar este", icon: "refresh"})
    buttons.Push({id: "remove", text: "Quitar este", icon: "eye-off"})
    m.stripButtons.buttons = buttons
    m.stripButtons.focusIndex = 0
    m.hintTimer.control = "stop"
    m.hint.visible = false
    m.strip.visible = true
    m.stripButtons.setFocus(true)
end sub

sub closeStrip()
    m.strip.visible = false
    m.top.setFocus(true)
    showHint()
end sub

' «Este» es el que suena (el del marco limón).
sub onStripButton()
    id = m.stripButtons.event.id
    if id = "add"
        m.top.event = {type: "pick", mode: "add", id: m.id, sources: m.sources, title: ""}
    else if id = "change"
        m.top.event = {type: "pick", mode: "change", id: m.id, sources: m.sources, title: paneTitle(m.focus)}
    else if id = "remove"
        removeFocused()
    end if
end sub

' Quitar el que suena: con dos, el otro sigue solo con el reproductor de siempre, en el mismo segundo (como OK); con
' tres o cuatro, se rearma sin él y suena el que queda en su lugar.
sub removeFocused()
    n = m.sources.Count()
    if n < 2 then return
    if n = 2
        close("solo", 1 - m.focus)
        return
    end if
    sources = recipe()
    rest = []
    for i = 0 to n - 1
        if i <> m.focus then rest.Push(sources[i])
    end for
    f = m.focus
    if f >= rest.Count() then f = rest.Count() - 1
    rebuild(rest, f)
end sub

' La lista de la escena se cerró sin elegir: el foco vuelve a la tira (o al mosaico).
sub onRefocus()
    if not m.top.visible then return
    if m.strip.visible then m.stripButtons.setFocus(true) else m.top.setFocus(true)
end sub

' ---------- teclas ----------

' ◀ ▶: el anterior o el siguiente, en orden de lectura (también en la cuadrícula; ▼ es de la tira).
sub move(key as String)
    n = m.sources.Count()
    if n = 0 then return
    target = m.focus
    if key = "left" and m.focus > 0 then target = m.focus - 1
    if key = "right" and m.focus < n - 1 then target = m.focus + 1
    if target <> m.focus
        m.focus = target
        paintFocus()
    end if
end sub

sub togglePause()
    if m.video.state = "paused" then m.video.control = "resume" else m.video.control = "pause"
end sub

' Salir (closed) o ver uno solo (solo: el de «index») en el mismo punto.
sub close(kind as String, index as Integer)
    cancelBehind()
    at = 0
    if m.started then at = Int(m.video.position)   ' segundos que lleva el mosaico: «ver solo este» sigue ahí
    stopAll()
    source = invalid
    if kind = "solo" and index >= 0 and index < m.sources.Count() then source = m.sources[index]
    m.strip.visible = false
    m.top.visible = false
    m.top.event = {type: kind, id: m.id, source: source, at: at}
end sub

function onKeyEvent(key as String, press as Boolean) as Boolean
    if not press then return false
    if m.strip.visible
        if key = "back" or key = "up"
            closeStrip()
        else if key = "play"
            togglePause()
        end if
        return true   ' ◀ ▶ y OK son de la fila de botones; ▼ no hace nada
    end if
    if key = "back"
        close("closed", -1)
        return true
    end if
    if m.failed or not m.started then return true   ' mientras se arma (o si falló) solo sirve Atrás
    if key = "left" or key = "right"
        move(key)
        showHint()
    else if key = "down"
        openStrip()
    else if key = "OK"
        close("solo", m.focus)
    else if key = "play"
        togglePause()
        showHint()
    end if
    return true
end function
