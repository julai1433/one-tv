' El panel del reproductor: lo arma el reproductor con lo que se ve (data) y lo pone al día (status). Aquí se dibuja,
' se mueve el foco y se avisa lo elegido (event). La barra de avance de arriba solo se ve (se mueve desde la barra del
' reproductor). Partes que se eligen, de arriba abajo: los botones, la fila de reproducción y lo visto hace poco
' (solo las que tienen algo).
sub init()
    m.t = theme()
    m.top.findNode("shade").color = m.t.scrim
    m.top.findNode("sheetBg").color = m.t.raise2
    m.top.findNode("sheetLine").color = m.t.edge
    m.title = m.top.findNode("title")
    m.title.font = makeFont(38, "bold")
    m.title.color = m.t.text
    m.times = m.top.findNode("times")
    m.times.font = makeFont(32)
    m.times.color = m.t.textSoft
    m.chapter = m.top.findNode("chapter")
    m.chapter.font = makeFont(32, "bold")
    m.chapter.color = m.t.lime
    m.top.findNode("barTrack").color = m.t.raise3
    m.barFill = m.top.findNode("barFill")
    m.barFill.color = m.t.lime
    m.barPlay = m.top.findNode("barPlay")
    m.barPlay.blendColor = m.t.text
    m.barKnob = m.top.findNode("barKnob")
    m.barKnob.blendColor = m.t.lime
    m.barTicks = m.top.findNode("barTicks")
    m.buttonsGroup = m.top.findNode("buttons")
    for each id in ["queueHead", "historyHead"]
        head = m.top.findNode(id)
        head.font = makeFont(27, "bold")
        head.color = m.t.muted
    end for
    m.top.findNode("queueHead").text = "FILA DE REPRODUCCIÓN"
    m.top.findNode("historyHead").text = "VISTOS HACE POCO"
    m.queueEmpty = m.top.findNode("queueEmpty")
    m.queueEmpty.font = makeFont(27)
    m.queueEmpty.color = m.t.muted
    m.queueEmpty.text = "La fila está vacía. Desde el inicio, * sobre un video lo agrega."
    m.hint = m.top.findNode("hint")
    m.hint.font = makeFont(27)
    m.hint.color = m.t.muted
    m.sheet = m.top.findNode("sheet")
    m.slide = m.top.findNode("slide")
    m.slideInterp = m.top.findNode("slideInterp")
    m.section = 1        ' 1 botones, 2 fila, 3 vistos
    m.index = [0, 0, 0, 0]
    m.buttons = []       ' [{id, bg, icon, label}]
    m.rows = [invalid, invalid, [], []]   ' por parte: las tarjetas {group, ring}
    m.status = {position: 0, duration: 0, paused: false, chapter: ""}
end sub

sub onOpen()
    if m.top.open
        m.top.visible = true
        m.slideInterp.keyValue = [[0, 1080], [0, 270]]
        m.slide.control = "start"
        m.section = firstSection()
        paintFocus()
        m.top.setFocus(true)
    else
        m.top.visible = false
        m.sheet.translation = [0, 1080]
    end if
end sub

sub onData()
    d = m.top.data
    if d = invalid then return
    m.title.text = textOf(d, "title")
    m.chapters = d.chapters
    if m.chapters = invalid then m.chapters = []
    buildButtons(d.buttons)
    m.rows[2] = buildRow(m.top.findNode("queueRow"), d.queue)
    m.rows[3] = buildRow(m.top.findNode("historyRow"), d.history)
    hasQueue = m.rows[2].Count() > 0
    m.queueEmpty.visible = not hasQueue
    hasHistory = m.rows[3].Count() > 0
    m.top.findNode("historyHead").visible = hasHistory
    for i = 2 to 3
        if m.index[i] >= m.rows[i].Count() then m.index[i] = 0
    end for
    m.ticksFor = -1   ' las marcas de los capítulos se dibujan con la primera duración que llegue
    paintFocus()
end sub

sub onStatus()
    s = m.top.status
    if s = invalid then return
    m.status = s
    paintBar()
end sub

sub paintBar()
    s = m.status
    duration = s.duration
    at = s.position
    if s.paused = true then m.barPlay.uri = "pkg:/images/icons/play.png" else m.barPlay.uri = "pkg:/images/icons/pause.png"
    if duration = invalid or duration <= 0
        m.barFill.width = 0
        m.times.text = fmtClockP(at)
    else
        f = at / duration
        if f < 0 then f = 0
        if f > 1 then f = 1
        m.barFill.width = Int(1636 * f)
        m.barKnob.translation = [Int(1636 * f) - 14, -8]
        m.times.text = fmtClockP(at) + " / " + fmtClockP(duration)
        if m.ticksFor <> duration then drawTicks(duration)
    end if
    m.chapter.text = textOf(s, "chapter")
end sub

sub drawTicks(duration as Float)
    m.ticksFor = duration
    m.barTicks.removeChildren(m.barTicks.getChildren(-1, 0))
    for i = 1 to m.chapters.Count() - 1
        t = m.barTicks.createChild("Rectangle")
        t.width = 6
        t.height = 12
        t.color = m.t.raise2
        t.translation = [Int(1636 * m.chapters[i].start / duration) - 3, 0]
    end for
end sub

' ---------- botones ----------

sub buildButtons(list as Dynamic)
    m.buttonsGroup.removeChildren(m.buttonsGroup.getChildren(-1, 0))
    m.buttons = []
    if list = invalid then return
    x = 0
    for each b in list
        g = m.buttonsGroup.createChild("Group")
        g.translation = [x, 0]
        bg = g.createChild("Poster")
        bg.uri = "pkg:/images/fill.9.png"
        bg.blendColor = m.t.raise3
        icon = g.createChild("Poster")
        icon.uri = "pkg:/images/icons/" + b.icon + ".png"
        icon.width = 36
        icon.height = 36
        icon.translation = [24, 14]
        icon.blendColor = m.t.text
        label = g.createChild("Label")
        label.font = makeFont(27, "bold")
        label.color = m.t.text
        label.text = b.text
        label.translation = [72, 0]
        label.height = 64
        label.vertAlign = "center"
        w = 72 + Int(label.boundingRect().width) + 28
        bg.width = w
        bg.height = 64
        m.buttons.Push({id: b.id, bg: bg, icon: icon, label: label})
        x = x + w + 16
    end for
    if m.index[1] >= m.buttons.Count() then m.index[1] = 0
end sub

' ---------- filas (la fila de reproducción y lo visto) ----------

function buildRow(group as Object, list as Dynamic) as Object
    group.removeChildren(group.getChildren(-1, 0))
    cards = []
    if list = invalid then return cards
    x = 0
    for each e in list
        g = group.createChild("Group")
        g.translation = [x, 0]
        back = g.createChild("Rectangle")
        back.width = 240
        back.height = 135
        back.color = m.t.raise3
        thumb = g.createChild("Poster")
        thumb.width = 240
        thumb.height = 135
        thumb.loadWidth = 240
        thumb.loadHeight = 135
        thumb.loadDisplayMode = "scaleToZoom"
        thumb.uri = textOf(e, "thumb")
        title = g.createChild("Label")
        title.font = makeFont(24, "bold")
        title.color = m.t.textSoft
        title.text = textOf(e, "title")
        title.translation = [0, 143]
        title.width = 240
        ring = g.createChild("Poster")
        ring.uri = "pkg:/images/focus.9.png"
        ring.blendColor = m.t.lime
        ring.width = 240
        ring.height = 135
        ring.visible = false
        cards.Push({group: g, ring: ring, title: title})
        x = x + 240 + 24
    end for
    return cards
end function

function rowCount(section as Integer) as Integer
    if section = 1 then return m.buttons.Count()
    return m.rows[section].Count()
end function

function firstSection() as Integer
    for s = 1 to 3
        if rowCount(s) > 0 then return s
    end for
    return 1
end function

' ---------- foco ----------

sub paintFocus()
    for i = 0 to m.buttons.Count() - 1
        b = m.buttons[i]
        lit = m.section = 1 and i = m.index[1]
        if lit then b.bg.blendColor = m.t.lime else b.bg.blendColor = m.t.raise3
        if lit then b.label.color = m.t.onLime else b.label.color = m.t.text
        b.icon.blendColor = b.label.color
    end for
    for s = 2 to 3
        cards = m.rows[s]
        for i = 0 to cards.Count() - 1
            lit = m.section = s and i = m.index[s]
            cards[i].ring.visible = lit
            if lit then cards[i].title.color = m.t.lime else cards[i].title.color = m.t.textSoft
        end for
        ' La fila se corre para que la tarjeta con el foco se vea (caben 5).
        if cards.Count() > 0
            first = 0
            if m.section = s and m.index[s] > 4 then first = m.index[s] - 4
            if s = 2 then row = m.top.findNode("queueRow") else row = m.top.findNode("historyRow")
            row.translation = [110 - first * 264, row.translation[1]]
            for i = 0 to cards.Count() - 1
                cards[i].group.visible = i >= first and i < first + 7
            end for
        end if
    end for
    hints = ["", "OK: elegir   ·   arriba: volver a la barra   ·   Atrás: ocultar", "OK: verlo ya (sale de la fila)   ·   Atrás: ocultar", "OK: verlo ya   ·   Atrás: ocultar"]
    m.hint.text = hints[m.section]
end sub

sub move(dSection as Integer, dIndex as Integer)
    if dSection <> 0
        s = m.section + dSection
        while s >= 1 and s <= 3 and rowCount(s) = 0
            s = s + dSection
        end while
        if s < 1   ' ▲ desde la parte de arriba: de vuelta a la barra de avance
            m.top.event = {type: "up"}
            return
        end if
        if s > 3 then return
        m.section = s
    else
        i = m.index[m.section] + dIndex
        if i < 0 or i >= rowCount(m.section) then return
        m.index[m.section] = i
    end if
    paintFocus()
end sub

function onKeyEvent(key as String, press as Boolean) as Boolean
    if not press or not m.top.open then return false
    m.top.touched = true
    if key = "back"
        m.top.event = {type: "close"}
    else if key = "up"
        move(-1, 0)
    else if key = "down"
        move(1, 0)
    else if key = "left"
        move(0, -1)
    else if key = "right"
        move(0, 1)
    else if key = "play"
        m.top.event = {type: "pause"}
    else if key = "OK"
        if m.section = 1 and m.buttons.Count() > 0
            m.top.event = {type: "button", id: m.buttons[m.index[1]].id}
        else if m.section = 2 and rowCount(2) > 0
            m.top.event = {type: "queue", index: m.index[2]}
        else if m.section = 3 and rowCount(3) > 0
            m.top.event = {type: "history", index: m.index[3]}
        end if
    end if
    return true   ' nada pasa al video de abajo
end function

function textOf(d as Object, key as String) as String
    v = d[key]
    if v = invalid then return ""
    return v
end function

' 1:02:03 / 4:05
function fmtClockP(seconds as Dynamic) as String
    if seconds = invalid then seconds = 0
    total = Int(seconds)
    h = Int(total / 3600)
    mins = Int((total mod 3600) / 60)
    secs = total mod 60
    s = secs.ToStr()
    if secs < 10 then s = "0" + s
    if h > 0
        mm = mins.ToStr()
        if mins < 10 then mm = "0" + mm
        return h.ToStr() + ":" + mm + ":" + s
    end if
    return mins.ToStr() + ":" + s
end function
