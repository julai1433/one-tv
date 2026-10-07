' Tarjeta de filas y cuadrículas. El tamaño de la imagen llega en el contenido (w, h) y el estilo decide qué
' más se dibuja. El foco sigue una sola regla: lo que señalas se vuelve limón.
sub init()
    m.t = theme()
    m.pad = m.top.findNode("pad")
    p = tilePad()
    m.pad.translation = [p, p]
    m.body = m.top.findNode("body")
    m.card = m.top.findNode("card")
    m.fallback = m.top.findNode("fallback")
    m.fallbackTitle = m.top.findNode("fallbackTitle")
    m.poster = m.top.findNode("poster")
    m.initials = m.top.findNode("initials")
    m.avatar = m.top.findNode("avatar")
    m.avatar.observeField("loadStatus", "onAvatarLoad")
    m.bar = m.top.findNode("bar")
    m.barBg = m.top.findNode("barBg")
    m.tag = m.top.findNode("tag")
    m.tagBg = m.top.findNode("tagBg")
    m.tagEdge = m.top.findNode("tagEdge")
    m.title = m.top.findNode("title")
    m.subtitle = m.top.findNode("subtitle")
    m.scrim = m.top.findNode("scrim")
    m.ytIcon = m.top.findNode("ytIcon")
    m.ring = m.top.findNode("ring")
    m.setting = m.top.findNode("setting")
    m.bar.color = m.t.lime
    m.barBg.color = m.t.raise3
    m.fallback.color = m.t.raise3
    m.fallbackTitle.color = m.t.textSoft
    m.fallbackTitle.font = makeFont(38, "display")
    m.fallbackTitle.maxLines = 4
    m.tagBg.blendColor = m.t.guinda
    m.tagEdge.blendColor = m.t.esText
    m.tag.color = m.t.esText
    m.tag.font = makeFont(27, "bold")
    m.durBg = m.top.findNode("durBg")
    m.dur = m.top.findNode("dur")
    m.durBg.blendColor = m.t.badge
    m.durBg.opacity = m.t.badgeOpacity
    m.dur.color = m.t.text
    m.dur.font = makeFont(27, "bold")
    m.savedBg = m.top.findNode("savedBg")
    m.savedIcon = m.top.findNode("savedIcon")
    m.savedBg.blendColor = m.t.badge
    m.savedBg.opacity = m.t.badgeOpacity
    m.savedIcon.blendColor = m.t.text
    m.initials.font = makeFont(48, "display")
    m.ring.blendColor = m.t.lime
    m.card.blendColor = m.t.raise3
    m.pinMark = m.top.findNode("pinMark")
    m.top.findNode("pinEdge").blendColor = m.t.bg
    m.top.findNode("pinDot").blendColor = m.t.lime
    m.top.findNode("pinIcon").blendColor = m.t.onLime
    m.style = "poster"
    m.inRow = false
    m.listFocus = true     ' ¿la fila o cuadrícula tiene el foco? (si no, ni marco ni reflector)
    m.grows = false        ' ¿crece con el foco? (las imágenes sí; ajustes y vacíos no)
    m.empty = invalid
    m.poster.observeField("loadStatus", "onLoadStatus")
end sub

sub onContent()
    c = m.top.itemContent
    if c = invalid then return
    m.style = field(c, "style", "poster")
    m.inRow = field(c, "inRow", false)
    w = field(c, "w", 213)
    h = field(c, "h", 320)
    m.w = w
    m.h = h
    m.body.visible = true
    m.setting.visible = false
    if m.empty <> invalid then m.empty.visible = false
    m.card.visible = false
    m.scrim.visible = false
    m.ytIcon.visible = false
    m.poster.visible = true
    m.initials.visible = false
    m.avatar.visible = false
    m.subtitle.visible = false
    m.title.visible = true
    m.poster.blendColor = "0xFFFFFFFF"
    m.poster.loadDisplayMode = "scaleToZoom"
    m.poster.translation = [0, 0]
    m.poster.width = w
    m.poster.height = h
    m.poster.loadWidth = w
    m.poster.loadHeight = h
    m.poster.loadingBitmapUri = ""
    m.poster.failedBitmapUri = ""
    uri = c.HDPosterUrl
    if uri = invalid then uri = ""
    m.poster.uri = uri
    imgH = h                       ' alto de la imagen (barra de avance, marco, centro del reflector)
    ringBox = [0, 0, w, h]         ' lo que rodea el marco de foco
    m.grows = true
    m.ring.uri = "pkg:/images/focus.9.png"
    m.title.text = c.title
    m.title.color = m.t.textSoft
    m.title.horizAlign = "left"
    m.title.vertAlign = "top"
    m.title.wrap = true
    m.title.height = 0
    m.subtitle.text = field(c, "line2", "")
    m.subtitle.color = m.t.muted
    m.subtitle.font = makeFont(27)
    m.subtitle.horizAlign = "left"
    m.pinMark.visible = false

    if m.style = "poster"
        m.title.visible = false     ' el título va en la línea de información de la vista
    else if m.style = "frame" or m.style = "video"
        m.title.translation = [0, h + 12]
        m.title.width = w
        m.title.maxLines = 1
        m.title.font = makeFont(32, "bold")
        m.subtitle.translation = [0, h + 52]
        m.subtitle.width = w
        m.subtitle.visible = m.subtitle.text <> ""
    else if m.style = "ytcard"
        ' Video de YouTube en un hueco de póster: la miniatura (grande) llena la tarjeta, recortada al centro, y
        ' abajo, sobre una franja oscura, «YouTube» y el canal. El título va en la línea de información, como los
        ' pósters (decisión de diseño del 29 sep 2026: opción A, imagen completa).
        m.scrim.visible = true
        m.scrim.width = w
        m.scrim.height = Int(h * 0.55)
        m.scrim.translation = [0, h - Int(h * 0.55)]
        m.ytIcon.visible = true
        m.ytIcon.width = 42
        m.ytIcon.height = 30
        m.ytIcon.translation = [14, h - 90]
        m.title.text = "YouTube"
        m.title.translation = [64, h - 92]
        m.title.width = w - 74
        m.title.wrap = false
        m.title.maxLines = 1
        m.title.font = makeFont(27, "bold")
        m.title.color = m.t.text
        m.subtitle.translation = [14, h - 56]
        m.subtitle.width = w - 28
        m.subtitle.color = m.t.textSoft
        m.subtitle.visible = true
    else if m.style = "channel"
        ' Canal: su foto en círculo (los canales son lo único redondo) y el nombre completo debajo. Mientras la foto
        ' llega, o si no tiene, el círculo con sus iniciales.
        m.poster.uri = "pkg:/images/circle.png"
        m.poster.loadDisplayMode = "scaleToFit"
        m.poster.height = w
        m.poster.loadHeight = w
        m.poster.blendColor = m.t.raise3
        m.initials.visible = true
        m.initials.text = field(c, "initials", "")
        m.initials.width = w
        m.initials.height = w
        m.initials.color = m.t.text
        photo = field(c, "avatar", "")
        if photo <> ""
            m.avatar.opacity = 1
            m.avatar.visible = true
            m.avatar.width = w
            m.avatar.height = w
            m.avatar.loadWidth = w
            m.avatar.loadHeight = w
            m.avatar.uri = photo
            if m.avatar.loadStatus = "ready" then m.initials.visible = false   ' la misma foto, ya cargada
        end if
        ' El nombre usa todo el ancho de la tarjeta (también su margen: la fila recorta lo que pase de ahí) y hasta
        ' tres renglones: se lee completo.
        m.title.translation = [-tilePad(), w + 12]
        m.title.width = w + 2 * tilePad()
        m.title.maxLines = 3
        m.title.horizAlign = "center"
        m.title.font = makeFont(24)
        imgH = w
        ringBox = [0, 0, w, w]
        m.ring.uri = "pkg:/images/circle_focus.png"
        ' Anclado: el punto (50 px con su borde negro) centrado sobre el círculo, a 45° arriba a la derecha.
        if field(c, "pinned", false) = true
            m.pinMark.visible = true
            m.pinMark.translation = [Int(w * 0.854) - 25, Int(w * 0.146) - 25]
        end if
    else if m.style = "setting"
        m.body.visible = false
        m.grows = false
        imgH = -1
        ringBox = invalid
        buildSetting(c)
    else if m.style = "empty"
        m.body.visible = false
        m.title.visible = false
        m.grows = false
        imgH = -1
        ringBox = invalid
        if m.empty = invalid then m.empty = m.pad.createChild("EmptyState")
        m.empty.visible = true
        m.empty.spec = {shape: field(c, "emptyShape", "poster"), width: w, height: h, phrase: c.title,
                        cause: field(c, "line2", ""), action: field(c, "actionText", ""), big: field(c, "big", false)}
    end if

    ' Póster que falta (o mientras llega): gris con el título en letra de marquesina.
    m.fallback.visible = imgH > 0 and m.style <> "channel"
    m.fallback.width = w
    m.fallback.height = imgH
    m.fallbackTitle.visible = false
    m.fallbackTitle.translation = [16, 16]
    m.fallbackTitle.width = w - 32
    m.fallbackTitle.height = imgH - 32
    m.fallbackTitle.text = ""
    m.fallbackText = marquee(bareTitle(field(c, "title", "")))
    if m.fallback.visible and uri = "" then showFallbackTitle()

    progress = field(c, "progress", 0.0)
    showBar = progress > 0.01 and imgH > 0
    m.barBg.visible = showBar
    m.bar.visible = showBar
    if showBar
        m.barBg.translation = [0, imgH - 6]
        m.barBg.width = w
        m.bar.translation = [0, imgH - 6]
        m.bar.width = Int(w * progress)
    end if
    spanish = field(c, "spanish", false) and imgH > 0
    if spanish
        tagW = 152
        tagH = 40
        m.tagEdge.width = tagW + 6
        m.tagEdge.height = tagH + 6
        m.tagBg.width = tagW
        m.tagBg.height = tagH
        m.tag.width = tagW
        m.tag.height = tagH
    end if
    m.tag.visible = spanish
    m.tagBg.visible = spanish
    m.tagEdge.visible = spanish
    showDuration(c, w, h, imgH, showBar)
    showSaved(c, w, imgH)

    m.ringBox = ringBox
    if ringBox <> invalid
        ' Marco de 6 px pegado al borde de la imagen, por dentro (lo de afuera lo recortaría la lista).
        m.ring.translation = [ringBox[0], ringBox[1]]
        m.ring.width = ringBox[2]
        m.ring.height = ringBox[3]
        ' Crece la imagen (la tarjeta entera en la de YouTube, que lleva el texto adentro); el texto de abajo solo
        ' se corre lo que baja la imagen, para que no se agrande ni se desalinee.
        m.body.scaleRotateCenter = [w / 2, imgH / 2]
        m.pad.scaleRotateCenter = [w / 2, h / 2]
    end if
    m.imgH = imgH
    m.titleAt = m.title.translation
    m.subtitleAt = m.subtitle.translation
    m.pad.scale = [1, 1]
    m.body.scale = [1, 1]
    onFocus()
end sub

' Duración de un video de YouTube, como en YouTube: abajo a la derecha de la miniatura, en negro al 85 % con la
' cifra en Archivo 700 (27, el mínimo de la tele). Sube si hay barra de avance; en la tarjeta vertical («Seguir
' viendo») va justo encima de «YouTube» y el canal. La etiqueta «Español» (arriba a la izquierda) no se cruza.
sub showDuration(c as Object, w as Dynamic, h as Dynamic, imgH as Dynamic, showBar as Boolean)
    seconds = toInt(field(c, "dur", 0))
    live = field(c, "liveTag", false) = true   ' transmisión de YouTube en vivo: «EN VIVO» en rojo en lugar de la duración
    show = (seconds > 0 or live) and imgH > 0 and (m.style = "video" or m.style = "frame" or m.style = "ytcard")
    m.dur.visible = show
    m.durBg.visible = show
    if not show then return
    if live
        m.dur.text = "EN VIVO"
        m.durBg.blendColor = m.t.ytRed
        m.durBg.opacity = 1
    else
        m.dur.text = fmtTime(seconds)
        m.durBg.blendColor = m.t.badge
        m.durBg.opacity = m.t.badgeOpacity
    end if
    m.dur.width = 0
    m.dur.height = 0
    boxW = Int(m.dur.boundingRect().width) + 20
    boxH = 40
    x = w - boxW - 10
    y = imgH - boxH - 10
    if showBar then y = y - 6
    if m.style = "ytcard" then y = h - 92 - boxH - 8
    m.durBg.translation = [x, y]
    m.durBg.width = boxW
    m.durBg.height = boxH
    m.dur.translation = [x, y]
    m.dur.width = boxW
    m.dur.height = boxH
end sub

' Guardado sin conexión (offline = "listo"): cuadro de 40 px con el ícono de descarga, arriba a la derecha de la
' miniatura. Solo en los videos de YouTube (video, frame y ytcard); no choca con la duración (abajo), «Español» (arriba a
' la izquierda) ni la marca de YouTube (abajo a la izquierda).
sub showSaved(c as Object, w as Dynamic, imgH as Dynamic)
    show = field(c, "saved", false) = true and imgH > 0 and (m.style = "video" or m.style = "frame" or m.style = "ytcard")
    m.savedBg.visible = show
    m.savedIcon.visible = show
    if not show then return
    m.savedBg.width = 40
    m.savedBg.height = 40
    m.savedBg.translation = [w - 50, 10]
    m.savedIcon.translation = [w - 44, 16]
end sub

sub onLoadStatus()
    status = m.poster.loadStatus
    if status = "ready"
        m.fallback.visible = false
        m.fallbackTitle.visible = false
    else if status = "failed" and m.fallback.visible
        showFallbackTitle()
    end if
end sub

sub showFallbackTitle()
    m.fallbackTitle.text = m.fallbackText
    m.fallbackTitle.visible = true
end sub

' Ajuste general: un título y debajo dos segmentos (la opción elegida en limón; con el foco, el control
' entero con contorno limón) o un botón secundario (con el foco, relleno limón).
sub buildSetting(c as Object)
    m.setting.removeChildren(m.setting.getChildren(-1, 0))
    m.setting.visible = true
    m.title.translation = [0, 0]
    m.title.width = m.w
    m.title.maxLines = 1
    m.title.font = makeFont(32, "bold")
    m.title.color = m.t.text
    m.kind = field(c, "kind", "button")
    m.chosen = field(c, "chosen", 0)
    font = makeFont(32, "bold")
    y = 62
    m.parts = []
    x = 0
    labels = field(c, "options", [])
    if m.kind = "button" then labels = [field(c, "buttonText", "")]
    for i = 0 to labels.Count() - 1
        g = m.setting.createChild("Group")
        g.translation = [x, y]
        bg = g.createChild("Poster")
        bg.uri = "pkg:/images/fill.9.png"
        edge = g.createChild("Poster")
        edge.uri = "pkg:/images/line.9.png"
        icon = invalid
        textX = 28
        if m.kind = "button"
            icon = g.createChild("Poster")
            icon.uri = field(c, "icon", "")
            icon.width = 36
            icon.height = 36
            icon.translation = [24, 14]
            textX = 72
        end if
        label = g.createChild("Label")
        label.font = font
        label.text = labels[i]
        label.translation = [textX, 0]
        label.height = 64
        label.vertAlign = "center"
        segW = textX + Int(label.boundingRect().width) + 28
        label.width = segW - textX - 24
        for each piece in [bg, edge]
            piece.width = segW
            piece.height = 64
        end for
        m.parts.Push({bg: bg, edge: edge, label: label, icon: icon})
        x = x + segW - 3   ' los segmentos comparten el borde
    end for
end sub

sub renderSetting(focused as Boolean)
    for i = 0 to m.parts.Count() - 1
        p = m.parts[i]
        if m.kind = "segments"
            lit = i = m.chosen      ' la opción elegida, siempre en limón
        else
            lit = focused           ' el botón, con el foco
        end if
        p.bg.visible = lit
        p.bg.blendColor = m.t.lime
        p.edge.visible = not lit
        ' Con el foco, el contorno del otro segmento también se vuelve limón: se enciende el control entero.
        if focused and m.kind = "segments" then p.edge.blendColor = m.t.lime else p.edge.blendColor = m.t.edge
        if lit then p.label.color = m.t.onLime else p.label.color = m.t.text
        if p.icon <> invalid then p.icon.blendColor = p.label.color
    end for
end sub

function field(c as Object, name as String, fallback as Dynamic) as Dynamic
    if c.hasField(name)
        v = c.getField(name)
        if v <> invalid then return v
    end if
    return fallback
end function

sub onListFocus()
    m.listFocus = m.top.rowListHasFocus
    onFocus()
end sub

sub onGridFocus()
    m.listFocus = m.top.gridHasFocus
    onFocus()
end sub

' f va de 0 a 1 mientras la lista mueve el foco: el marco aparece, la imagen crece al 106 % y lo demás queda
' al 55 % (reflector). Sin el foco en la lista, todo a pleno y sin marco.
sub onFocus()
    f = m.top.focusPercent
    if m.inRow then f = f * m.top.rowFocusPercent
    if not m.listFocus then f = 0.0
    focused = f > 0.5
    if m.listFocus then m.top.opacity = 0.55 + 0.45 * f else m.top.opacity = 1.0
    if m.style = "empty"
        if m.empty <> invalid then m.empty.focused = focused
        return
    end if
    if m.style = "setting"
        renderSetting(focused)
        return
    end if
    if m.grows
        s = 1.0 + 0.06 * f
        if m.style = "ytcard"
            m.pad.scale = [s, s]
        else
            m.body.scale = [s, s]
            dy = 0.03 * m.imgH * f
            m.title.translation = [m.titleAt[0], m.titleAt[1] + dy]
            m.subtitle.translation = [m.subtitleAt[0], m.subtitleAt[1] + dy]
        end if
    end if
    m.ring.visible = f > 0.02 and m.ringBox <> invalid
    m.ring.opacity = f
    if m.style <> "ytcard"
        if focused then m.title.color = m.t.text else m.title.color = m.t.textSoft
    end if
end sub

' La foto del canal llegó: las iniciales de abajo ya no hacen falta (si no, se transparentan al atenuarse la tarjeta).
' Si no llegó (el canal no tiene foto o no hubo internet), se quedan las iniciales.
sub onAvatarLoad()
    status = m.avatar.loadStatus
    if status = "ready" and m.avatar.visible then m.initials.visible = false
    if status = "failed" then m.avatar.visible = false
end sub
