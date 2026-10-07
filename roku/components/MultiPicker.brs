' Lista para elegir de «varios a la vez». La escena manda las secciones ya armadas (spec); aquí se dibujan los
' renglones, se mueve el foco (saltando lo desactivado), se corre la lista para que se vea el renglón con el foco y
' se avisa lo elegido (event). La escena la esconde.
sub init()
    m.t = theme()
    m.top.findNode("shade").color = m.t.scrim
    m.top.findNode("panel").color = m.t.raise2
    m.title = m.top.findNode("title")
    m.title.font = makeFont(72, "black")
    m.title.color = m.t.text
    m.note = m.top.findNode("note")
    m.note.font = makeFont(32)
    m.note.color = m.t.textSoft
    m.viewport = m.top.findNode("viewport")
    m.list = m.top.findNode("list")
    m.empty = m.top.findNode("empty")
    m.hint = m.top.findNode("hint")
    m.hint.font = makeFont(27)
    m.hint.color = m.t.muted
    m.headFont = makeFont(32, "bold")
    m.titleFont = makeFont(32, "bold")
    m.lineFont = makeFont(27)
    m.rowH = 132        ' alto de un renglón (miniatura de 192×108 con 12 de aire)
    m.rowGap = 12
    m.viewH = 708       ' alto de la ventana de la lista (de y=252 a 960)
    m.rows = []         ' solo los que se pueden elegir: {bg, title, line, y, top, source, label}
    m.focus = -1
    m.scroll = 0
    m.done = false      ' ya se eligió o se cerró: no se aceptan más teclas hasta que llegue otra lista
    m.clock = CreateObject("roTimespan")
end sub

sub onSpec()
    s = m.top.spec
    if s = invalid then return
    m.title.text = marquee(textOf(s, "title"))
    m.note.text = textOf(s, "note")
    m.list.removeChildren(m.list.getChildren(-1, 0))
    m.rows = []
    m.focus = -1
    m.scroll = 0
    m.list.translation = [0, 0]
    m.done = false
    m.clock.Mark()
    sections = s.sections
    if sections = invalid then sections = []
    y = 0
    for each section in sections
        entries = section.entries
        if entries <> invalid and entries.Count() > 0
            if y > 0 then y = y + 24   ' más aire arriba de un título que abajo
            head = m.list.createChild("Label")
            head.font = m.headFont
            head.color = m.t.textSoft
            head.text = textOf(section, "title")
            head.translation = [12, y]
            head.width = 980
            head.height = 56
            head.vertAlign = "center"
            headY = y
            y = y + 56 + 8
            first = true
            for each e in entries
                addRow(e, y, headY, first)
                first = false
                y = y + m.rowH + m.rowGap
            end for
        end if
    end for
    hasRows = m.rows.Count() > 0
    m.viewport.visible = hasRows
    m.empty.visible = not hasRows
    if hasRows
        m.hint.text = textOf(s, "hint")
        if m.hint.text = "" then m.hint.text = "OK: elegir   ·   ‹ o Atrás: cerrar"
        first = 0
        if s.focus <> invalid then first = toInt(s.focus)
        if first < 0 or first >= m.rows.Count() then first = 0
        setFocusRow(first)
    else
        ' Vacío que enseña: los huecos de una fila de fotogramas, por qué no hay nada y qué hacer.
        cause = textOf(s, "emptyCause")
        if cause = "" then cause = "Aquí salen los canales en vivo, lo que está en la fila de reproducción y lo que viste hace poco."
        phrase = textOf(s, "emptyPhrase")
        if phrase = "" then phrase = "Nada más para elegir"
        m.empty.spec = {shape: "frame", width: 992, layout: "stack", phrase: phrase, cause: cause}
        m.hint.text = "Atrás: cerrar"
    end if
end sub

' Un renglón: miniatura, título y la línea de apoyo. Desactivado (ya está en pantalla): todo en gris y el foco no
' se detiene en él.
sub addRow(e as Object, y as Integer, headY as Integer, first as Boolean)
    g = m.list.createChild("Group")
    g.translation = [0, y]
    bg = g.createChild("Poster")
    bg.uri = "pkg:/images/fill.9.png"
    bg.width = 1004
    bg.height = m.rowH
    bg.blendColor = m.t.lime
    bg.visible = false
    back = g.createChild("Rectangle")   ' mientras carga la miniatura, o si no hay
    back.translation = [12, 12]
    back.width = 192
    back.height = 108
    back.color = m.t.raise3
    thumb = g.createChild("Poster")
    iconNode = invalid
    if textOf(e, "icon") <> ""   ' un ícono al centro del cuadro (las opciones de un menú, «Lista nueva»)
        iconNode = thumb
        thumb.translation = [80, 38]
        thumb.width = 56
        thumb.height = 56
        thumb.uri = "pkg:/images/icons/" + textOf(e, "icon") + ".png"
        thumb.blendColor = m.t.text
    else
        thumb.translation = [12, 12]
        thumb.width = 192
        thumb.height = 108
        thumb.loadWidth = 192
        thumb.loadHeight = 108
        thumb.loadDisplayMode = "scaleToZoom"
        thumb.uri = textOf(e, "thumb")
    end if
    title = g.createChild("Label")
    title.font = m.titleFont
    title.text = textOf(e, "title")
    title.translation = [228, 20]
    title.width = 752
    title.height = 44
    title.vertAlign = "center"
    detail = g.createChild("Label")
    detail.font = m.lineFont
    detail.text = textOf(e, "line")
    detail.translation = [228, 70]
    detail.width = 752
    detail.height = 40
    detail.vertAlign = "center"
    detail.color = m.t.muted
    if detail.text = "" then title.translation = [228, 44]   ' sin línea de apoyo: el título al centro del renglón
    if e.disabled = true
        title.color = m.t.muted
        back.opacity = 0.4
        thumb.opacity = 0.4
        return
    end if
    title.color = m.t.text
    top = y
    if first then top = headY   ' el primero de su sección: al llegar a él se ve también el título
    m.rows.Push({bg: bg, title: title, line: detail, icon: iconNode, y: y, top: top, source: e.source, label: textOf(e, "title")})
end sub

sub setFocusRow(index as Integer)
    if index < 0 or index >= m.rows.Count() then return
    if m.focus >= 0 and m.focus < m.rows.Count() then paintRow(m.focus, false)
    m.focus = index
    paintRow(index, true)
    r = m.rows[index]
    top = r.top
    if index = 0 then top = 0
    bottom = r.y + m.rowH
    if top < m.scroll then m.scroll = top
    if bottom > m.scroll + m.viewH then m.scroll = bottom - m.viewH
    m.list.translation = [0, -m.scroll]
end sub

' Lo que señalas se vuelve limón: relleno limón y letra negra.
sub paintRow(index as Integer, lit as Boolean)
    r = m.rows[index]
    r.bg.visible = lit
    if lit
        r.title.color = m.t.onLime
        r.line.color = m.t.onLime
    else
        r.title.color = m.t.text
        r.line.color = m.t.muted
    end if
    if r.icon <> invalid then r.icon.blendColor = r.title.color
end sub

function textOf(d as Object, key as String) as String
    v = d[key]
    if v = invalid then return ""
    return v
end function

sub finish(e as Object)
    m.done = true
    m.top.event = e
end sub

function onKeyEvent(key as String, press as Boolean) as Boolean
    if not press then return false
    if m.done then return true
    ' La misma tecla que abrió la lista (▼ en el reproductor, OK en un botón) puede llegar aquí: se ignora.
    if m.clock.TotalMilliseconds() < 350 then return true
    if key = "back" or key = "left"
        finish({type: "close"})
    else if key = "up"
        setFocusRow(m.focus - 1)
    else if key = "down"
        setFocusRow(m.focus + 1)
    else if key = "OK" and m.focus >= 0 and m.focus < m.rows.Count()
        r = m.rows[m.focus]
        finish({type: "pick", source: r.source, title: r.label})
    end if
    return true   ' nada pasa a lo de abajo
end function
