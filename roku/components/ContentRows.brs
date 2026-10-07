' Filas de tarjetas. La fila elegida queda siempre arriba (fixedFocus) y bajo ella va la línea de información.
sub init()
    m.t = theme()
    m.list = m.top.findNode("list")
    m.info = m.top.findNode("info")
    m.headerLabel = m.top.findNode("header")
    m.topBtn = m.top.findNode("top")
    m.headerLabel.font = makeFont(72, "black")
    m.headerLabel.color = m.t.text
    m.info.font = makeFont(32)
    m.info.color = m.t.textSoft
    m.list.rowLabelFont = makeFont(38, "bold")
    m.list.rowLabelColor = m.t.text
    m.labelSpace = 46        ' alto que ocupa el título de cada fila encima de sus tarjetas
    m.pad = tilePad()
    m.listY = 150
    placeList()
    m.slotHeights = []
    m.list.observeField("rowItemFocused", "onItemFocused")
    m.list.observeField("rowItemSelected", "onItemSelected")
    m.topBtn.observeField("event", "onTopEvent")
    m.top.observeField("focusedChild", "onFocusChange")
    m.top.focus = [0, 0]
end sub

sub onHeader()
    m.headerLabel.text = marquee(m.top.header)
end sub

sub onTopButton()
    text = m.top.topButton
    m.topBtn.visible = text <> ""
    if text <> ""
        m.topBtn.style = "big"
        m.topBtn.primary = false
        m.topBtn.buttons = [{id: "top", text: text, icon: "search"}]
        m.listY = 250
    else
        m.listY = 150
    end if
    placeList()
end sub

' La lista se corre el margen de las tarjetas para que las imágenes queden en x = 168.
sub placeList()
    m.list.translation = [168 - m.pad, m.listY - m.pad]
end sub

sub onContent()
    root = m.top.content
    if root = invalid
        m.list.content = invalid
        m.info.text = ""
        return
    end if
    sizes = []
    heights = []
    gaps = []
    m.slotHeights = []
    for i = 0 to root.getChildCount() - 1
        row = root.getChild(i)
        shape = "poster"
        if row.hasField("shape") then shape = row.shape
        spec = tileSpec(shape)
        slotH = spec.slotH
        pad2 = 2 * m.pad
        if row.hasField("isEmpty") and row.isEmpty = true
            ' Fila vacía: una sola tarjeta a todo el ancho; la de la fila de reproducción, más alta.
            if row.hasField("big") and row.big = true then slotH = slotH + 60
            sizes.Push([1752 + pad2, slotH + pad2])
        else
            sizes.Push([spec.slotW + pad2, slotH + pad2])
        end if
        heights.Push(slotH + pad2)
        gaps.Push([spec.gap - pad2, 0])
        m.slotHeights.Push(slotH)
    end for
    if sizes.Count() = 0 then return
    m.list.rowItemSize = sizes
    m.list.rowHeights = heights
    m.list.rowItemSpacing = gaps
    m.list.content = root
    f = m.top.focus
    if f <> invalid and f.Count() = 2 then jump(f[0], f[1])
    updateInfo()
end sub

sub onJump()
    f = m.top.jumpTo
    if f <> invalid and f.Count() = 2 then jump(f[0], f[1])
end sub

sub jump(row as Integer, col as Integer)
    root = m.list.content
    if root = invalid or root.getChildCount() = 0 then return
    if row >= root.getChildCount() then row = root.getChildCount() - 1
    if row < 0 then row = 0
    n = root.getChild(row).getChildCount()
    if col >= n then col = n - 1
    if col < 0 then col = 0
    m.list.jumpToRowItem = [row, col]
    m.top.focus = [row, col]
    updateInfo()
end sub

sub onFocusChange()
    if m.top.hasFocus()
        if m.topBtn.visible and m.list.content = invalid then m.topBtn.setFocus(true) else m.list.setFocus(true)
    end if
    m.info.visible = m.list.hasFocus()
end sub

sub onItemFocused()
    f = m.list.rowItemFocused
    if f = invalid or f.Count() < 2 then return
    m.top.focus = [f[0], f[1]]
    updateInfo()
end sub

' Lo que dice la tarjeta elegida, justo debajo de su fila.
sub updateInfo()
    tile = focusedTile()
    text = ""
    if tile <> invalid and tile.hasField("info") then text = tile.info
    m.info.text = text
    f = m.top.focus
    row = 0
    if f <> invalid and f.Count() = 2 then row = f[0]
    h = 320
    if row < m.slotHeights.Count() then h = m.slotHeights[row]
    m.info.translation = [168, m.listY + m.labelSpace + h + 20]   ' deja lugar al póster que crece
end sub

function focusedTile() as Dynamic
    root = m.list.content
    f = m.top.focus
    if root = invalid or f = invalid or f.Count() < 2 then return invalid
    if f[0] >= root.getChildCount() then return invalid
    return root.getChild(f[0]).getChild(f[1])
end function

sub onItemSelected()
    sel = m.list.rowItemSelected
    if sel = invalid or sel.Count() < 2 then return
    tile = m.list.content.getChild(sel[0]).getChild(sel[1])
    if tile = invalid then return
    m.top.event = {type: "select", id: tile.id, row: sel[0], col: sel[1]}
end sub

sub onTopEvent()
    m.top.event = {type: "top"}
end sub

function onKeyEvent(key as String, press as Boolean) as Boolean
    if not press then return false
    ' *: lo que se puede hacer con esa tarjeta (un video de la fila: moverlo o quitarlo). Las demás no tienen menú y
    ' la tecla sigue a la escena (actualizar la biblioteca).
    if key = "options" and m.list.hasFocus()
        tile = focusedTile()
        if tile <> invalid and tile.hasField("style") and tile.style <> "setting" and tile.style <> "empty"
            m.top.event = {type: "options", id: tile.id, row: m.top.focus[0], col: m.top.focus[1]}
            return true
        end if
        return false
    end if
    if key = "play" and m.list.hasFocus()
        tile = focusedTile()
        if tile <> invalid then m.top.event = {type: "play", id: tile.id, row: m.top.focus[0], col: m.top.focus[1]}
        return true
    end if
    if key = "up" and m.list.hasFocus() and m.topBtn.visible
        m.topBtn.setFocus(true)
        m.info.visible = false
        return true
    end if
    if key = "down" and m.topBtn.isInFocusChain() and m.list.content <> invalid
        m.list.setFocus(true)
        m.info.visible = true
        return true
    end if
    return false
end function
