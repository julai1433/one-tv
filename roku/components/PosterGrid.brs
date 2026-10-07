' Cuadrícula de tarjetas con cabecera, línea de información y controles arriba a la derecha.
' ⏪/⏩ los atiende la propia cuadrícula del Roku: sube o baja una pantalla (la última fila queda arriba).
sub init()
    m.t = theme()
    m.grid = m.top.findNode("grid")
    m.info = m.top.findNode("info")
    m.headerLabel = m.top.findNode("header")
    m.countLabel = m.top.findNode("count")
    m.controls = m.top.findNode("controls")
    m.empty = m.top.findNode("empty")
    m.emptyAction = false   ' antes de que llegue contenido (una página que aún carga) ya se pregunta por él
    m.headerLabel.font = makeFont(72, "black")
    m.headerLabel.color = m.t.text
    m.countLabel.font = makeFont(32)
    m.countLabel.color = m.t.muted
    m.info.font = makeFont(32)
    m.info.color = m.t.textSoft
    m.grid.observeField("itemFocused", "onItemFocused")
    m.empty.observeField("event", "onEmptyEvent")
    m.grid.observeField("itemSelected", "onItemSelected")
    m.controls.observeField("event", "onControlEvent")
    m.top.observeField("focusedChild", "onFocusChange")
    onShape()
end sub

sub onHeader()
    layoutHeader()
end sub

' Título y conteo en una línea; si no caben antes de los botones de arriba a la derecha, el título se acorta.
sub layoutHeader()
    m.headerLabel.width = 0
    m.headerLabel.text = marquee(m.top.header)
    m.countLabel.text = m.top.count
    w = m.headerLabel.boundingRect().width
    limit = 1840 - 168
    if m.controls.visible then limit = m.controls.translation[0] - 48 - 168
    countW = 0
    if m.top.count <> "" then countW = m.countLabel.boundingRect().width + 22
    if w + countW > limit
        w = limit - countW
        if w < 240 then w = 240
        m.headerLabel.width = w
    end if
    m.countLabel.translation = [168 + w + 22, 68]   ' sobre la misma línea de base que el título
end sub

sub onShape()
    spec = tileSpec(m.top.shape)
    m.spec = spec
    pad = tilePad()
    m.grid.itemSize = [spec.slotW + 2 * pad, spec.slotH + 2 * pad]
    m.grid.itemSpacing = [spec.gap - 2 * pad, 24 - 2 * pad]
    m.grid.translation = [168 - pad, 184 - pad]
    ' Columnas que caben entre el menú y el borde derecho (1752 de ancho).
    m.cols = Int((1752 + spec.gap) / (spec.slotW + spec.gap))
    m.grid.numColumns = m.cols
    m.grid.numRows = 3
end sub

sub onControls()
    list = m.top.controls
    m.controls.visible = list <> invalid and list.Count() > 0
    if m.controls.visible
        m.controls.style = m.top.controlStyle
        m.controls.primary = m.top.controlPrimary
        m.controls.buttons = list
        m.controls.selectedId = m.top.controlValue
        y = 38
        if m.top.controlStyle = "big" then y = 36
        m.controls.translation = [1840 - m.controls.rowWidth, y]
    end if
    layoutHeader()
end sub

sub onControlValue()
    m.controls.selectedId = m.top.controlValue
    ' El foco sigue en el filtro elegido.
    list = m.top.controls
    if list = invalid then return
    for i = 0 to list.Count() - 1
        if list[i].id = m.top.controlValue then m.controls.focusIndex = i
    end for
end sub

sub onContent()
    root = m.top.content
    count = 0
    if root <> invalid then count = root.getChildCount()
    m.grid.content = root
    m.grid.visible = count > 0
    m.empty.visible = count = 0
    m.emptyAction = false
    if count = 0
        e = m.top.emptySpec
        if e = invalid then e = {}
        spec = {shape: m.top.shape, width: 1672, height: m.spec.slotH, phrase: e.phrase, cause: e.cause,
                action: e.action, actionId: e.actionId}
        m.empty.spec = spec
        m.emptyAction = e.action <> invalid and e.action <> ""
    end if
    if count > 0
        index = m.top.focusIndex
        if index >= count then index = count - 1
        if index < 0 then index = 0
        m.grid.jumpToItem = index
        m.top.focusIndex = index
    end if
    updateInfo()
    ' Llegó el contenido con el foco en la vista (p. ej. una página que se estaba cargando): a la cuadrícula.
    if m.top.hasFocus()
        focusInside()
    else if m.top.isInFocusChain() and count = 0 and not m.controls.isInFocusChain() and not m.empty.hasFocus()
        focusInside()
    end if
    m.info.visible = m.grid.hasFocus()
end sub

' El foco entra a la cuadrícula; si está vacía, a la acción del vacío o a los filtros.
sub focusInside()
    if m.grid.content <> invalid and m.grid.content.getChildCount() > 0
        m.grid.setFocus(true)
    else if m.emptyAction
        m.empty.setFocus(true)
    else if m.controls.visible
        m.controls.setFocus(true)
    end if
end sub

sub onEmptyEvent()
    m.top.event = {type: "select", id: "empty:" + m.empty.event.action, index: 0}
end sub

sub onJump()
    root = m.grid.content
    if m.top.jumpTo < 0 or root = invalid or root.getChildCount() = 0 then return
    index = m.top.jumpTo
    if index >= root.getChildCount() then index = root.getChildCount() - 1
    m.grid.jumpToItem = index
    m.top.focusIndex = index
    updateInfo()
end sub

sub onFocusChange()
    if m.top.hasFocus() then focusInside()
    m.info.visible = m.grid.hasFocus()
end sub

sub onItemFocused()
    m.top.focusIndex = m.grid.itemFocused
    updateInfo()
end sub

sub updateInfo()
    tile = focusedTile()
    text = ""
    if tile <> invalid
        if tile.hasField("info") then text = tile.info else text = tile.title
    end if
    m.info.text = text
end sub

function focusedTile() as Dynamic
    root = m.grid.content
    if root = invalid or root.getChildCount() = 0 then return invalid
    index = m.top.focusIndex
    if index < 0 or index >= root.getChildCount() then return invalid
    return root.getChild(index)
end function

sub onItemSelected()
    tile = m.grid.content.getChild(m.grid.itemSelected)
    if tile <> invalid then m.top.event = {type: "select", id: tile.id, index: m.grid.itemSelected}
end sub

sub onControlEvent()
    e = m.controls.event
    m.top.event = {type: "control", id: e.id, index: e.index}
end sub

function onKeyEvent(key as String, press as Boolean) as Boolean
    if not press then return false
    gridFocused = m.grid.hasFocus()
    if gridFocused and key = "play"
        tile = focusedTile()
        if tile <> invalid then m.top.event = {type: "play", id: tile.id, index: m.top.focusIndex}
        return true
    end if
    if gridFocused and key = "options"   ' *: lo que se puede hacer con esa tarjeta (la escena arma el menú)
        tile = focusedTile()
        if tile <> invalid
            m.top.event = {type: "options", id: tile.id, index: m.top.focusIndex}
            return true
        end if
    end if
    if (gridFocused or m.empty.hasFocus()) and key = "up" and m.controls.visible
        m.controls.setFocus(true)
        m.info.visible = false
        return true
    end if
    if key = "down" and m.controls.isInFocusChain()
        if m.grid.visible
            m.grid.setFocus(true)
            m.info.visible = true
        else if m.emptyAction
            m.empty.setFocus(true)
        end if
        return true
    end if
    return false
end function
