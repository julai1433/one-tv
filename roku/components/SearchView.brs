' Buscar. La escena arma los resultados (libContent / ytContent); aquí se escribe y se elige.
sub init()
    m.t = theme()
    m.keyboard = m.top.findNode("keyboard")
    m.ytButton = m.top.findNode("ytButton")
    m.results = m.top.findNode("results")
    m.resultsHead = m.top.findNode("resultsHead")
    m.info = m.top.findNode("info")
    m.empty = m.top.findNode("empty")
    m.fieldText = m.top.findNode("fieldText")
    m.fieldIcon = m.top.findNode("fieldIcon")
    m.fieldLine = m.top.findNode("fieldLine")
    m.cursor = m.top.findNode("cursor")
    m.micIcon = m.top.findNode("micIcon")
    header = m.top.findNode("header")
    header.font = makeFont(72, "black")
    header.color = m.t.text
    m.resultsHead.font = makeFont(38, "bold")
    m.resultsHead.color = m.t.text
    m.info.font = makeFont(32)
    m.info.color = m.t.textSoft
    m.top.findNode("fieldBg").color = m.t.bg
    m.fieldText.font = makeFont(44, "medium")
    m.cursor.color = m.t.lime
    m.micIcon.blendColor = m.t.muted
    voice = m.top.findNode("voiceHint")
    voice.font = makeFont(27)
    voice.color = m.t.muted
    m.ytButton.style = "big"
    m.ytButton.primary = false
    m.showing = "lib"
    m.placeholder = "Escribe un título"
    m.dictating = false

    ' El teclado con los colores de la app: teclas en gris oscuro, la del foco en limón con letra negra.
    palette = CreateObject("roSGNode", "RSGPalette")
    palette.colors = {KeyboardColor: m.t.raise3, PrimaryTextColor: m.t.text, SecondaryItemColor: m.t.muted,
                      FocusColor: m.t.lime, FocusItemColor: m.t.onLime, InputFieldColor: m.t.bg,
                      SecondaryTextColor: m.t.muted}
    if m.keyboard.hasField("palette") then m.keyboard.palette = palette
    grid = m.keyboard.keyGrid
    if grid <> invalid and grid.hasField("palette") then grid.palette = palette

    ' Entrada por voz: donde el control tiene micrófono se puede dictar; el teclado siempre funciona.
    editBox = m.keyboard.textEditBox
    if editBox <> invalid and editBox.hasField("voiceEnabled")
        editBox.voiceEnabled = true
        voice.text = "Si tu control tiene micrófono, mantén su botón y dilo en voz alta."
        m.micIcon.visible = true
        if editBox.hasField("isDictating") then editBox.observeField("isDictating", "onDictating")
    end if
    m.keyboard.observeField("text", "onText")
    m.ytButton.observeField("event", "onYtButton")
    m.results.observeField("itemFocused", "onItemFocused")
    m.results.observeField("itemSelected", "onItemSelected")
    m.top.observeField("focusedChild", "onFocusChange")
    onMode()
end sub

sub onMode()
    header = m.top.findNode("header")
    if m.top.mode = "youtube"
        header.text = "BUSCAR EN YOUTUBE"
        m.showing = "yt"
        m.placeholder = "Escribe qué buscar"
    else
        header.text = "BUSCAR"
        m.showing = "lib"
        m.placeholder = "Escribe un título"
    end if
    drawField()
    refresh()
end sub

sub onFocusChange()
    if m.top.hasFocus() then m.keyboard.setFocus(true)
    m.info.visible = m.results.hasFocus()
    drawField()
end sub

sub onDictating()
    m.dictating = m.keyboard.textEditBox.isDictating = true
    drawField()
end sub

' El campo: lupa, lo escrito en letra grande (o el marcador en gris), cursor limón y línea inferior que se
' vuelve limón mientras se escribe.
sub drawField()
    typing = m.keyboard.isInFocusChain()
    text = m.keyboard.text
    if m.dictating
        m.fieldText.text = "Te escucho…"
        m.fieldText.color = m.t.lime
    else if text = ""
        m.fieldText.text = m.placeholder
        m.fieldText.color = m.t.muted
    else
        ' Si no cabe, se ve el final (lo último que se escribió).
        avail = 460
        shown = text
        m.fieldText.width = 0
        m.fieldText.text = shown
        while m.fieldText.boundingRect().width > avail and Len(shown) > 1
            shown = Mid(shown, 2)
            m.fieldText.text = "…" + shown
        end while
        m.fieldText.color = m.t.text
    end if
    m.fieldText.width = 0
    textW = 0
    if text <> "" and not m.dictating then textW = m.fieldText.boundingRect().width
    m.fieldText.width = 470
    m.cursor.translation = [58 + textW + 4, 14]
    m.cursor.visible = typing and not m.dictating
    if typing
        m.fieldLine.color = m.t.lime
        m.fieldIcon.blendColor = m.t.lime
    else
        m.fieldLine.color = m.t.edge
        m.fieldIcon.blendColor = m.t.text
    end if
end sub

sub onText()
    text = m.keyboard.text
    m.top.query = text
    if m.top.mode <> "youtube"
        m.showing = "lib"
        m.top.event = {type: "query", text: text}
    end if
    drawField()
    refresh()
end sub

sub onStatus()
    refresh()
end sub

sub onLibContent()
    if m.showing = "lib" then refresh()
end sub

sub onYtContent()
    m.showing = "yt"
    refresh()
end sub

sub onJumpTo()
    content = m.results.content
    i = m.top.jumpTo
    if content = invalid or i < 0 or i >= content.getChildCount() then return
    m.results.jumpToItem = i
    if m.results.visible then m.results.setFocus(true)
    updateInfo()
end sub

' Encabezado de resultados, botón de YouTube y la cuadrícula que toca (o un vacío que dice qué hacer).
sub refresh()
    text = m.keyboard.text.Trim()
    m.ytButton.visible = text <> ""
    if text <> "" then m.ytButton.buttons = [{id: "yt", text: "Buscar «" + text + "» en YouTube", icon: "square-play"},
                                             {id: "ytlive", text: "Solo en vivo", icon: "radio"}]
    head = ""
    phrase = ""
    cause = ""
    if m.showing = "yt"
        shape = "searchVideo"
        content = m.top.ytContent
        status = m.top.status
        if content <> invalid and content.getChildCount() > 0 and Left(status, 8) <> "Buscando"
            head = status
        else
            content = invalid
            if status = ""
                phrase = "Escribe qué buscar"
                cause = "Luego elige «Buscar en YouTube», arriba."
            else if Left(status, 8) = "Buscando"
                phrase = "Buscando en YouTube"
                cause = status
            else if Left(status, 10) = "No se pudo"
                phrase = "No se pudo buscar"
                cause = "La computadora no responde. Revisa que esté encendida y vuelve a intentarlo."
            else
                phrase = "Sin resultados"
                cause = status
            end if
        end if
    else
        shape = "searchPoster"
        content = m.top.libContent
        if text = ""
            phrase = "Escribe un título"
            cause = "Busca en tus películas y series mientras escribes."
            content = invalid
        else if content = invalid or content.getChildCount() = 0
            phrase = "Nada con «" + text + "»"
            cause = "Prueba con menos letras, o búscalo en YouTube con el botón de arriba."
            content = invalid
        else
            head = "En tu biblioteca: " + countText(content.getChildCount(), "resultado", "resultados")
        end if
    end if
    setShape(shape)
    m.resultsHead.text = head
    m.results.content = content
    m.results.visible = content <> invalid
    m.empty.visible = content = invalid
    if content = invalid
        spec = tileSpec(shape)
        m.empty.spec = {shape: shape, width: 940, height: spec.slotH, phrase: phrase, cause: cause, layout: "stack"}
    end if
    updateInfo()
end sub

sub setShape(shape as String)
    spec = tileSpec(shape)
    pad = tilePad()
    m.results.itemSize = [spec.slotW + 2 * pad, spec.slotH + 2 * pad]
    m.results.itemSpacing = [spec.gap - 2 * pad, 24 - 2 * pad]
    m.results.translation = [900 - pad, 320 - pad]
    m.results.numColumns = Int((940 + spec.gap) / (spec.slotW + spec.gap))
end sub

sub onYtButton()
    text = m.keyboard.text.Trim()
    if text = "" then return
    live = m.ytButton.event <> invalid and m.ytButton.event.id = "ytlive"   ' «Solo en vivo»: transmisiones de ahora
    m.showing = "yt"
    m.top.status = "Buscando «" + text + "» en YouTube…"
    if live then m.top.status = "Buscando «" + text + "» en vivo…"
    m.top.event = {type: "ytsearch", text: text, live: live}
end sub

sub onItemFocused()
    m.top.focusIndex = m.results.itemFocused
    updateInfo()
end sub

sub updateInfo()
    tile = invalid
    content = m.results.content
    if content <> invalid and m.results.itemFocused >= 0 and m.results.itemFocused < content.getChildCount()
        tile = content.getChild(m.results.itemFocused)
    end if
    text = ""
    if tile <> invalid
        if tile.hasField("info") then text = tile.info else text = tile.title
    end if
    m.info.text = text
end sub

sub onItemSelected()
    tile = m.results.content.getChild(m.results.itemSelected)
    if tile <> invalid then m.top.event = {type: "select", id: tile.id}
end sub

function onKeyEvent(key as String, press as Boolean) as Boolean
    handled = moveFocus(key, press)
    drawField()   ' la línea y el cursor limón solo mientras se escribe
    return handled
end function

function moveFocus(key as String, press as Boolean) as Boolean
    if not press then return false
    if key = "right" and m.keyboard.isInFocusChain()
        if m.ytButton.visible
            m.ytButton.setFocus(true)
        else if m.results.visible
            m.results.setFocus(true)
        end if
        return true
    end if
    if key = "left" and (m.results.hasFocus() or m.ytButton.isInFocusChain())
        m.keyboard.setFocus(true)
        return true
    end if
    if key = "down" and m.ytButton.isInFocusChain() and m.results.visible
        m.results.setFocus(true)
        return true
    end if
    if key = "up" and m.results.hasFocus() and m.ytButton.visible
        m.ytButton.setFocus(true)
        return true
    end if
    if key = "play" and m.results.hasFocus()
        content = m.results.content
        if content <> invalid and m.results.itemFocused >= 0
            m.top.event = {type: "play", id: content.getChild(m.results.itemFocused).id}
        end if
        return true
    end if
    return false
end function
