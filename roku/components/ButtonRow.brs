sub init()
    m.t = theme()
    m.items = []
    m.shift = 0   ' cuánto se corrió la fila a la izquierda para que entre el botón con el foco
    ' Letra y relleno, del más cómodo al más apretado: se usa el primero que cabe en maxWidth.
    m.bigSizes = [{font: makeFont(32, "bold"), pad: 30, gap: 18}, {font: makeFont(27, "bold"), pad: 22, gap: 14}]
    m.segSize = {font: makeFont(32, "bold"), pad: 28, gap: -3}   ' los segmentos comparten el borde
    m.strip = m.top.createChild("Group")
    m.top.observeField("focusedChild", "render")
end sub

sub build()
    if m.top.style = "segments"
        layout(m.segSize, 60)
    else
        for each size in m.bigSizes
            layout(size, 64)
            if m.top.rowWidth <= m.top.maxWidth then exit for
        end for
    end if
    if m.top.focusIndex >= m.items.Count() then m.top.focusIndex = 0
    render()
end sub

sub layout(size as Object, height as Integer)
    m.strip.removeChildren(m.strip.getChildren(-1, 0))
    m.items = []
    big = m.top.style <> "segments"
    pad = size.pad
    x = 0
    for each b in m.top.buttons
        g = m.strip.createChild("Group")
        g.translation = [x, 0]
        bg = g.createChild("Poster")
        bg.uri = "pkg:/images/fill.9.png"
        edge = g.createChild("Poster")
        edge.uri = "pkg:/images/line.9.png"
        icon = invalid
        textX = pad
        if big and b.icon <> invalid and b.icon <> ""
            icon = g.createChild("Poster")
            icon.uri = "pkg:/images/icons/" + b.icon + ".png"
            icon.width = 36
            icon.height = 36
            icon.translation = [pad - 6, Int((height - 36) / 2)]
            textX = pad + 42
        end if
        label = g.createChild("Label")
        label.font = size.font
        label.text = b.text
        label.translation = [textX, 0]
        label.height = height
        label.vertAlign = "center"
        w = textX + Int(label.boundingRect().width) + pad
        label.width = w - textX - pad + 4
        for each piece in [bg, edge]
            piece.width = w
            piece.height = height
        end for
        m.items.Push({id: b.id, bg: bg, edge: edge, icon: icon, label: label, x: x, width: w, danger: b.danger = true})
        x = x + w + size.gap
    end for
    m.top.rowWidth = x - size.gap
end sub

sub render()
    hasFocus = m.top.isInFocusChain()
    segments = m.top.style = "segments"
    for i = 0 to m.items.Count() - 1
        it = m.items[i]
        focused = hasFocus and i = m.top.focusIndex
        it.bg.blendColor = m.t.lime
        it.bg.visible = focused
        it.edge.visible = not focused
        it.edge.blendColor = m.t.edge
        if focused
            it.label.color = m.t.onLime
        else if segments
            ' La opción elegida: letra limón, como la sección actual del menú.
            if it.id = m.top.selectedId then it.label.color = m.t.lime else it.label.color = m.t.textSoft
        else if i = 0 and m.top.primary
            ' El botón principal sin foco: contorno y letra limón (el relleno queda para el foco).
            it.edge.blendColor = m.t.lime
            it.label.color = m.t.lime
        else if it.danger
            it.label.color = m.t.guindaLight   ' peligroso: letra guinda claro (con el foco, limón como todo)
        else
            it.label.color = m.t.text
        end if
        if it.icon <> invalid then it.icon.blendColor = it.label.color
    end for
    ' Si aun así no cabe, la fila se desplaza lo mínimo para que el botón con el foco se vea entero: al ir a la derecha
    ' se corre a la izquierda y al volver solo se devuelve cuando el botón se saldría por ese lado (no salta de un lado a otro).
    if m.top.rowWidth <= m.top.maxWidth
        m.shift = 0
    else if m.top.focusIndex < m.items.Count()
        it = m.items[m.top.focusIndex]
        if it.x + m.shift < 0 then m.shift = -it.x
        if it.x + it.width + m.shift > m.top.maxWidth then m.shift = m.top.maxWidth - (it.x + it.width)
        least = m.top.maxWidth - m.top.rowWidth
        if m.shift < least then m.shift = least
        if m.shift > 0 then m.shift = 0
    end if
    m.strip.translation = [m.shift, 0]
end sub

function onKeyEvent(key as String, press as Boolean) as Boolean
    if not press then return false
    if key = "left"
        if m.top.focusIndex > 0
            m.top.focusIndex = m.top.focusIndex - 1
            return true
        end if
        return false
    else if key = "right"
        if m.top.focusIndex < m.items.Count() - 1 then m.top.focusIndex = m.top.focusIndex + 1
        return true
    else if key = "OK"
        if m.top.focusIndex < m.items.Count()
            m.top.event = {id: m.items[m.top.focusIndex].id, index: m.top.focusIndex}
        end if
        return true
    end if
    return false
end function
