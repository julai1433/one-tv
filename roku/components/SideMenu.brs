' Menú lateral: nueve secciones, siempre en el mismo orden.
sub init()
    m.t = theme()
    m.sections = [
        {text: "Buscar", icon: "search"},
        {text: "Inicio", icon: "house"},
        {text: "En español", icon: "languages"},
        {text: "Películas", icon: "clapper"},
        {text: "Series", icon: "monitor-play"},
        {text: "YouTube", icon: "square-play"},
        {text: "Música", icon: "music"},
        {text: "En vivo", icon: "radio"},
        {text: "Fila de reproducción", icon: "list-video"},
    ]
    m.top.findNode("shade").color = m.t.scrim
    m.top.findNode("rail").color = m.t.raise1
    m.top.findNode("panel").color = m.t.raise2
    caption = m.top.findNode("caption")
    caption.font = makeFont(48, "black")
    caption.color = m.t.text
    hint = m.top.findNode("hint")
    hint.font = makeFont(27)
    hint.color = m.t.muted
    m.top.findNode("stateIcon").blendColor = m.t.muted
    head = m.top.findNode("stateHead")
    head.font = makeFont(27, "bold")
    head.color = m.t.muted
    m.stateWord = m.top.findNode("stateWord")
    m.stateWord.font = makeFont(38, "display")
    m.stateWord.translation = [44 + Int(head.boundingRect().width) + 14, 0]
    m.index = 1
    m.rows = []
    group = m.top.findNode("items")
    y = 176
    for i = 0 to m.sections.Count() - 1
        s = m.sections[i]
        row = group.createChild("Group")
        row.translation = [0, y]
        fill = row.createChild("Poster")
        fill.uri = "pkg:/images/fill.9.png"
        fill.blendColor = m.t.lime
        icon = row.createChild("Poster")
        icon.uri = "pkg:/images/icons/" + s.icon + ".png"
        icon.width = 44
        icon.height = 44
        label = row.createChild("Label")
        label.text = s.text
        label.font = makeFont(32, "medium")
        label.translation = [112, 0]
        label.height = 72
        label.vertAlign = "center"
        count = row.createChild("Label")
        count.font = makeFont(27, "bold")
        count.horizAlign = "right"
        count.vertAlign = "center"
        count.translation = [440, 0]
        count.width = 72
        count.height = 72
        count.visible = false
        m.rows.Push({fill: fill, icon: icon, label: label, count: count})
        y = y + 80   ' con 9 secciones y 86 de separación, la última pisaba el estado de la computadora (abajo, en 900)
    end for
    onStatus()
end sub

sub render()
    open = m.top.expanded
    m.top.findNode("shade").visible = open
    m.top.findNode("panel").visible = open
    m.top.findNode("caption").visible = open
    m.top.findNode("brandMark").visible = open
    m.top.findNode("hint").visible = open
    m.top.findNode("state").visible = open
    m.top.findNode("rail").visible = not open
    for i = 0 to m.rows.Count() - 1
        r = m.rows[i]
        current = i = m.top.selected
        focused = open and i = m.index
        r.label.visible = open
        if open
            r.fill.translation = [28, 0]
            r.fill.width = 504
            r.icon.translation = [48, 14]
        else
            r.icon.translation = [38, 14]
        end if
        r.fill.height = 72
        r.fill.visible = focused
        if focused
            color = m.t.onLime
        else if current
            color = m.t.lime       ' sección actual: ícono y nombre en limón
        else
            color = m.t.text
        end if
        r.label.color = color
        r.icon.blendColor = color
        ' Cuántos hay en la fila de reproducción, junto a su nombre.
        showCount = open and i = 7 and m.top.badge > 0
        r.count.visible = showCount
        if showCount
            r.count.text = m.top.badge.ToStr()
            if focused then r.count.color = m.t.onLime else r.count.color = m.t.muted
        end if
    end for
end sub

' El estado de la Mac en palabras (DESIGN.md, pieza 3): CONECTADA · BUSCANDO · NO RESPONDE.
sub onStatus()
    status = m.top.status
    if status = "ok"
        m.stateWord.text = "CONECTADA"
        m.stateWord.color = m.t.lime
    else if status = "offline"
        m.stateWord.text = "NO RESPONDE"
        m.stateWord.color = m.t.guindaLight
    else
        m.stateWord.text = "BUSCANDO"
        m.stateWord.color = m.t.muted
    end if
    render()
end sub

' Al abrirse, el foco empieza en la sección actual.
sub onExpanded()
    if m.top.expanded then m.index = m.top.selected
    render()
end sub

function onKeyEvent(key as String, press as Boolean) as Boolean
    if not press then return false
    if key = "up"
        if m.index > 0 then m.index = m.index - 1
        render()
        return true
    else if key = "down"
        if m.index < m.sections.Count() - 1 then m.index = m.index + 1
        render()
        return true
    else if key = "OK"
        m.top.event = {type: "open", index: m.index}
        return true
    else if key = "right"
        m.top.event = {type: "close"}
        return true
    else if key = "left"
        return true
    end if
    return false   ' Atrás lo decide la pantalla principal
end function
