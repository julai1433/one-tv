' Vacío que enseña: frase de marquesina, causa y acción, y a su lado los huecos con la forma de la fila.
sub init()
    m.t = theme()
    m.slots = m.top.findNode("slots")
    m.frame = m.top.findNode("frame")
    m.phrase = m.top.findNode("phrase")
    m.cause = m.top.findNode("cause")
    m.detail = m.top.findNode("detail")
    m.action = m.top.findNode("action")
    m.actionBg = m.top.findNode("actionBg")
    m.actionText = m.top.findNode("actionText")
    m.actionIcon = m.top.findNode("actionIcon")
    m.hasAction = false
    m.frame.blendColor = m.t.lime
    m.phrase.color = m.t.text
    m.cause.color = m.t.textSoft
    m.detail.color = m.t.muted
    m.detail.font = makeFont(27)
    m.actionText.font = makeFont(32, "bold")
    m.top.observeField("focusedChild", "onFocusChange")
end sub

sub build()
    s = m.top.spec
    if s = invalid then return
    width = valueOf(s, "width", 1752)
    height = valueOf(s, "height", 320)
    big = valueOf(s, "big", false)
    stack = valueOf(s, "layout", "side") = "stack"   ' en un lugar angosto (Buscar): el texto arriba de los huecos

    ' El texto: frase, causa, detalle y acción, uno debajo del otro.
    if big
        m.phrase.font = makeFont(72, "black")
        m.cause.font = makeFont(38)
        m.cause.maxLines = 3
    else
        m.phrase.font = makeFont(48, "display")
        m.cause.font = makeFont(32)
        m.cause.maxLines = 2
    end if
    maxW = 820
    if big then maxW = 1000
    if maxW > width then maxW = width
    m.phrase.text = marquee(valueOf(s, "phrase", ""))
    m.phrase.width = 0
    phraseW = m.phrase.boundingRect().width
    if phraseW > maxW then phraseW = maxW
    m.phrase.width = phraseW + 2
    m.cause.text = valueOf(s, "cause", "")
    causeW = 0
    if m.cause.text <> ""
        m.cause.wrap = false
        m.cause.width = 0
        causeW = m.cause.boundingRect().width
        m.cause.wrap = true
        if causeW > maxW then causeW = maxW
        m.cause.width = causeW + 2
    end if
    m.detail.text = valueOf(s, "detail", "")
    m.detail.width = maxW
    detailW = 0
    if m.detail.text <> ""
        m.detail.width = 0
        detailW = m.detail.boundingRect().width
        m.detail.width = detailW + 2
    end if
    actionLabel = valueOf(s, "action", "")
    m.hasAction = actionLabel <> ""
    m.action.visible = m.hasAction
    actionW = 0
    if m.hasAction
        m.actionText.text = actionLabel
        m.actionText.width = 0
        textW = m.actionText.boundingRect().width
        m.actionText.translation = [20, 0]
        m.actionText.width = textW + 2
        m.actionText.height = 56
        m.actionIcon.translation = [20 + textW + 10, 12]
        actionW = 20 + textW + 10 + 32 + 16
        m.actionBg.width = actionW
        m.actionBg.height = 56
    end if

    parts = []
    parts.Push({node: m.phrase, h: m.phrase.boundingRect().height, gap: 0})
    if m.cause.text <> "" then parts.Push({node: m.cause, h: m.cause.boundingRect().height, gap: 6})
    if m.detail.text <> "" then parts.Push({node: m.detail, h: m.detail.boundingRect().height, gap: 12})
    if m.hasAction then parts.Push({node: m.action, h: 56, gap: 22})
    total = 0
    for each p in parts
        total = total + p.gap + p.h
    end for
    contentW = phraseW
    for each w in [causeW, detailW, actionW]
        if w > contentW then contentW = w
    end for

    ' Al lado (filas, cuadrículas, sin Mac): el texto a la izquierda, centrado en el alto de la fila, y los huecos
    ' siguen a su derecha hasta el borde, como una fila que continúa. Encima de los huecos (Buscar): el texto arriba.
    shape = valueOf(s, "shape", "")
    if stack
        y = 0
        slotsX = 0
        slotsY = total + 36
    else
        y = Int((height - total) / 2)
        if y < 0 then y = 0
        slotsX = contentW + 96
        if slotsX < 940 then slotsX = 940   ' misma columna en todas las filas vacías
        slotsY = 0
    end if
    x = 0
    top = y
    for each p in parts
        y = y + p.gap
        shift = 0
        if p.shift <> invalid then shift = p.shift
        p.node.translation = [x + shift, y]
        y = y + p.h
    end for
    drawSlots(shape, width, slotsX, slotsY, stack)
    m.frame.translation = [x - 12, top - 12]
    m.frame.width = contentW + 24
    m.frame.height = y - top + 24
    render()
end sub

' Huecos con la forma de las tarjetas de la fila, en el color de los bordes, desde «startX» hasta el borde; el
' último puede quedar cortado, como en una fila de verdad. En Buscar («onlyWhole»): hasta 4 enteros.
sub drawSlots(shape as String, width as Integer, startX as Integer, y as Integer, onlyWhole as Boolean)
    m.slots.removeChildren(m.slots.getChildren(-1, 0))
    m.slots.translation = [0, y]
    if shape = "" then return
    spec = tileSpec(shape)
    pitch = spec.slotW + spec.gap
    video = shape = "video" or shape = "frame" or shape = "gridVideo" or shape = "searchVideo"
    count = 0
    while true
        x = startX + count * pitch
        if onlyWhole
            if x + spec.slotW > width or count >= 4 then exit while
        else
            if x >= width then exit while
        end if
        if shape = "channel"
            ring = m.slots.createChild("Poster")
            ring.uri = "pkg:/images/circle_line.png"
            ring.width = spec.w
            ring.height = spec.w
            ring.translation = [x, 0]
            ring.blendColor = m.t.edge
            bar(x + Int(spec.w * 0.2), spec.w + 20, Int(spec.w * 0.6), 12)
        else
            hollow = m.slots.createChild("Poster")
            hollow.uri = "pkg:/images/line.9.png"
            hollow.translation = [x, 0]
            hollow.width = spec.w
            hollow.height = spec.h
            hollow.blendColor = m.t.edge
            if video
                bar(x, spec.h + 18, Int(spec.w * 0.72), 14)
                bar(x, spec.h + 44, Int(spec.w * 0.46), 12)
            end if
        end if
        count = count + 1
    end while
end sub

' Renglón de título dibujado bajo un hueco (el lugar donde iría el nombre).
sub bar(x as Integer, y as Integer, w as Integer, h as Integer)
    r = m.slots.createChild("Rectangle")
    r.translation = [x, y]
    r.width = w
    r.height = h
    r.color = m.t.raise3
end sub

function valueOf(s as Object, key as String, fallback as Dynamic) as Dynamic
    v = s[key]
    if v = invalid then return fallback
    return v
end function

sub onFocusChange()
    if m.top.hasFocus() <> m.top.focused then m.top.focused = m.top.hasFocus()
end sub

' Con el foco, la acción se vuelve un botón limón; sin acción, la placa se enmarca en limón.
sub render()
    focused = m.top.focused
    if m.hasAction = true
        m.frame.visible = false
        m.actionBg.visible = focused
        if focused
            m.actionBg.blendColor = m.t.lime
            m.actionText.color = m.t.onLime
            m.actionIcon.blendColor = m.t.onLime
        else
            m.actionText.color = m.t.lime
            m.actionIcon.blendColor = m.t.lime
        end if
    else
        m.frame.visible = focused
    end if
end sub

function onKeyEvent(key as String, press as Boolean) as Boolean
    if not press then return false
    if key = "OK" and m.hasAction = true
        m.top.event = {action: valueOf(m.top.spec, "actionId", "")}
        return true
    end if
    return false
end function
