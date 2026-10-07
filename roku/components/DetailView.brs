' Ficha de una película, episodio o video de YouTube. La pantalla principal decide qué hace cada botón;
' aquí solo se dibuja y se avisa lo que se eligió.
sub init()
    m.t = theme()
    t = m.t
    m.top.findNode("bg").color = t.bg
    m.top.findNode("fadeLeft").blendColor = t.bg
    m.top.findNode("fadeBottom").blendColor = t.bg
    m.backdrop = m.top.findNode("backdrop")
    m.texts = m.top.findNode("texts")
    m.title = m.top.findNode("title")
    m.subtitle = m.top.findNode("subtitle")
    m.meta = m.top.findNode("meta")
    m.metaRow = m.top.findNode("metaRow")
    m.tagGroup = m.top.findNode("tagGroup")
    m.langs = m.top.findNode("langs")
    m.langRow = m.top.findNode("langRow")
    m.desc = m.top.findNode("desc")
    m.buttons = m.top.findNode("buttons")
    m.messageLabel = m.top.findNode("message")
    m.hints = m.top.findNode("hints")
    m.panel = m.top.findNode("langPanel")
    m.audioList = m.top.findNode("audioList")
    m.subsList = m.top.findNode("subsList")
    m.descOverlay = m.top.findNode("descOverlay")
    m.descFull = m.top.findNode("descFull")
    m.qrOverlay = m.top.findNode("qrOverlay")

    m.bigTitle = makeFont(110, "black")
    m.midTitle = makeFont(72, "black")
    m.title.color = t.text
    m.subtitle.font = makeFont(38, "bold")
    m.subtitle.color = t.text
    m.meta.font = makeFont(32)
    m.meta.color = t.textSoft
    m.top.findNode("tagBg").blendColor = t.guinda
    m.top.findNode("tagEdge").blendColor = t.esText
    tag = m.top.findNode("tag")
    tag.font = makeFont(27, "bold")
    tag.color = t.esText
    m.top.findNode("langIcon").blendColor = t.text
    m.langs.font = makeFont(32)
    m.langs.color = t.text
    m.desc.font = makeFont(32)
    m.desc.color = t.textSoft
    m.messageLabel.font = makeFont(32, "bold")
    m.hints.font = makeFont(27)
    m.hints.color = t.muted
    m.hints.text = "OK: elegir   ·   *: sinopsis completa   ·   Atrás: volver"
    m.buttons.style = "big"
    m.buttons.primary = true

    m.top.findNode("panelBg").color = t.raise2
    m.top.findNode("panelShade").color = t.scrim
    m.top.findNode("panelTitle").font = makeFont(72, "black")
    m.top.findNode("panelTitle").color = t.text
    for each id in ["audioHead", "subsHead"]
        n = m.top.findNode(id)
        n.font = makeFont(32, "bold")
        n.color = t.textSoft
    end for
    m.top.findNode("audioIcon").blendColor = t.textSoft
    m.top.findNode("subsIcon").blendColor = t.textSoft
    m.top.findNode("panelMessage").font = makeFont(32, "bold")
    m.top.findNode("panelHint").font = makeFont(27)
    m.top.findNode("panelHint").color = t.muted

    m.top.findNode("descBg").color = t.bg
    m.top.findNode("descTitle").font = makeFont(72, "black")
    m.top.findNode("descTitle").color = t.text
    m.descFull.font = makeFont(32)
    m.descFull.color = t.text
    m.top.findNode("descHint").font = makeFont(27)
    m.top.findNode("descHint").color = t.muted

    m.top.findNode("qrBg").color = t.bg
    m.top.findNode("qrPaper").color = t.bg   ' el código ya viene en fondo oscuro (cuadritos claros)
    m.top.findNode("qrTitle").font = makeFont(72, "black")
    m.top.findNode("qrTitle").color = t.text
    m.top.findNode("qrText").font = makeFont(32)
    m.top.findNode("qrText").color = t.textSoft
    m.top.findNode("qrUrl").font = makeFont(38, "bold")
    m.top.findNode("qrUrl").color = t.text
    m.top.findNode("qrHint").font = makeFont(27)
    m.top.findNode("qrHint").color = t.muted

    m.descPath = ""
    m.fullDesc = ""
    m.metaBase = ""    ' la línea de datos sin la fecha de publicación
    m.publishedText = ""   ' «Publicado el 12 sep 2023» (YouTube), si se sabe
    m.subsMode = "list"
    m.buttons.observeField("event", "onButton")
    m.audioList.observeField("itemSelected", "onAudioSelected")
    m.subsList.observeField("itemSelected", "onSubsSelected")
    m.top.observeField("focusedChild", "onFocusChange")
end sub

sub onData()
    d = m.top.data
    if d = invalid then return
    setTitle(textOf(d, "title"))
    m.subtitle.text = textOf(d, "subtitle")
    m.metaBase = textOf(d, "meta")
    m.publishedText = textOf(d, "when")
    showMeta()
    m.tagGroup.visible = d.spanish = true
    m.langs.text = textOf(d, "langs")
    ' Lo que no tiene contenido sale del acomodo para no dejar huecos (sin episodio, sin idiomas en YouTube).
    for each node in [m.subtitle, m.metaRow, m.langRow, m.desc]
        parent = node.getParent()
        if parent <> invalid then parent.removeChild(node)
    end for
    spacings = [10]
    if m.subtitle.text <> ""
        m.texts.appendChild(m.subtitle)
        spacings.Push(20)
    end if
    m.texts.appendChild(m.metaRow)
    spacings.Push(22)
    if m.langs.text <> ""
        m.texts.appendChild(m.langRow)
        spacings.Push(22)
    end if
    m.texts.appendChild(m.desc)
    m.texts.itemSpacings = spacings
    m.backdrop.uri = textOf(d, "image")
    ' Los botones se rehacen conservando el que tenía el foco.
    keep = m.buttons.focusIndex
    m.buttons.buttons = d.buttons
    if d.keepFocus = true
        if keep < d.buttons.Count() then m.buttons.focusIndex = keep
    else
        m.buttons.focusIndex = 0
        m.panel.visible = false
        m.descOverlay.visible = false
        m.qrOverlay.visible = false
        m.subsMode = "list"
        m.top.message = ""
    end if
    path = textOf(d, "descPath")
    if path <> m.descPath
        m.descPath = path
        loadDescription(path)
    end if
    if m.panel.visible then fillLists(true)
end sub

' Título en letra de marquesina: 110 si cabe en dos renglones, si no 72.
sub setTitle(text as String)
    m.title.text = marquee(text)
    m.title.font = m.bigTitle
    m.title.wrap = false
    m.title.width = 0
    wide = m.title.boundingRect().width
    if wide > 2 * 1300 * 0.9 then m.title.font = m.midTitle
    m.title.wrap = true
    m.title.width = 1300
end sub

function textOf(d as Object, key as String) as String
    v = d[key]
    if v = invalid then return ""
    return v
end function

' Confirmación en limón (estado bueno) o problema en guinda claro.
sub onMessage()
    color = m.t.lime
    if m.top.messageTone = "error" then color = m.t.guindaLight
    for each label in [m.messageLabel, m.top.findNode("panelMessage")]
        label.text = m.top.message
        label.color = color
    end for
end sub

sub onFocusChange()
    if not m.top.hasFocus() then return
    if m.qrOverlay.visible
        m.qrOverlay.setFocus(true)
    else if m.descOverlay.visible
        m.descFull.setFocus(true)
    else if m.panel.visible
        m.audioList.setFocus(true)
    else
        m.buttons.setFocus(true)
    end if
end sub

' ---------- sinopsis (se pide aparte: el catálogo no trae textos largos) ----------

sub loadDescription(path as String)
    m.fullDesc = ""
    m.desc.text = ""
    if path = "" then return
    m.desc.text = "Buscando la sinopsis…"
    m.descTask = CreateObject("roSGNode", "ApiTask")
    m.descTask.url = m.top.server + path
    m.descTask.observeField("done", "onDescription")
    m.descTask.control = "RUN"
end sub

sub onDescription()
    r = m.descTask.result
    text = ""
    if m.descTask.error = "" and r <> invalid and r.desc <> invalid then text = r.desc
    m.fullDesc = text
    if text = "" then text = "Sin sinopsis todavía."
    m.desc.text = text
    ' YouTube: la escena sabe si es una transmisión en vivo (cambian los botones) y de qué canal.
    if m.descTask.error = "" and r <> invalid and r.live <> invalid and textOf(m.top.data, "kind") = "yt"
        m.top.event = {action: "ytinfo", live: r.live = true, viewers: r.viewers, channelId: r.channel_id}
    end if
    ' La ficha de YouTube trae la fecha exacta de publicación (yt-dlp): reemplaza la aproximada de la tarjeta.
    if m.descTask.error = "" and r <> invalid and r.published <> invalid and r.published > 0 and r.live <> true
        m.publishedText = publishedText(r.published, r.published_approx)
        showMeta()
    end if
end sub

sub showMeta()
    parts = []
    if m.metaBase <> "" then parts.Push(m.metaBase)
    if m.publishedText <> "" then parts.Push(m.publishedText)
    m.meta.text = parts.Join("   ·   ")
end sub

sub showFullDescription()
    d = m.top.data
    title = textOf(d, "title")
    if textOf(d, "subtitle") <> "" then title = title + " · " + textOf(d, "subtitle")
    m.top.findNode("descTitle").text = marquee(title)
    text = m.fullDesc
    if text = "" then text = "Sin sinopsis todavía."
    tech = textOf(d, "tech")
    if tech <> "" then text = text + chr(10) + chr(10) + "Detalles técnicos" + chr(10) + tech
    m.descFull.text = text
    m.descOverlay.visible = true
    m.descFull.setFocus(true)
end sub

' ---------- botones ----------

sub onButton()
    id = m.buttons.event.id
    if id = "lang"
        openPanel()
    else if id = "share"
        showQr()
    else
        m.top.event = {action: "button", id: id}
    end if
end sub

sub showQr()
    qr = m.top.data.qr
    if qr = invalid then return
    m.top.findNode("qrTitle").text = marquee(qr.title)
    m.top.findNode("qrImage").uri = qr.image
    m.top.findNode("qrUrl").text = qr.url
    m.qrOverlay.visible = true
    m.qrOverlay.setFocus(true)
end sub

' ---------- panel de idioma ----------

sub openPanel()
    m.subsMode = "list"
    fillLists(false)
    m.panel.visible = true
    m.audioList.setFocus(true)
    if m.audioList.content.getChildCount() = 0 then m.subsList.setFocus(true)
end sub

sub fillLists(keep as Boolean)
    d = m.top.data
    audioFocus = m.audioList.itemFocused
    subsFocus = m.subsList.itemFocused
    content = CreateObject("roSGNode", "ContentNode")
    names = d.audio
    if names = invalid then names = []
    for i = 0 to names.Count() - 1
        addLine(content, names[i], i = d.audioIndex, "", false)
    end for
    m.audioList.content = content
    if keep and audioFocus >= 0 and audioFocus < names.Count()
        m.audioList.jumpToItem = audioFocus
    else if d.audioIndex <> invalid and d.audioIndex >= 0 and d.audioIndex < names.Count()
        m.audioList.jumpToItem = d.audioIndex
    end if
    fillSubs(keep, subsFocus)
end sub

sub fillSubs(keep as Boolean, subsFocus as Integer)
    d = m.top.data
    content = CreateObject("roSGNode", "ContentNode")
    head = m.top.findNode("subsHead")
    if m.subsMode = "find"
        head.text = "¿En qué idioma?"
        addLine(content, "En español", false, "search", false)
        addLine(content, "En inglés", false, "search", false)
        addLine(content, "Volver", false, "rotate-ccw", false)
        m.subsList.content = content
        m.subsList.jumpToItem = 0
        return
    end if
    head.text = "Subtítulos"
    names = d.subs
    if names = invalid then names = []
    addLine(content, "Sin subtítulos", d.subIndex = -1, "", false)
    for i = 0 to names.Count() - 1
        addLine(content, names[i], i = d.subIndex, "", false)
    end for
    addLine(content, "Buscar subtítulos en internet", false, "search", true)
    m.subsList.content = content
    if keep and subsFocus >= 0 and subsFocus < content.getChildCount()
        m.subsList.jumpToItem = subsFocus
    else if d.subIndex <> invalid
        m.subsList.jumpToItem = d.subIndex + 1
    end if
end sub

' Una opción: la elegida lleva palomita; «lead» pone otro ícono a la izquierda y «more» una flecha.
sub addLine(content as Object, text as String, current as Boolean, lead as String, more as Boolean)
    item = content.createChild("ContentNode")
    item.title = text
    item.addFields({current: current, lead: lead, more: more})
end sub

sub onAudioSelected()
    m.top.event = {action: "audio", index: m.audioList.itemSelected}
end sub

sub onSubsSelected()
    index = m.subsList.itemSelected
    if m.subsMode = "find"
        m.subsMode = "list"
        if index = 0 then m.top.event = {action: "findsubs", lang: "spa"}
        if index = 1 then m.top.event = {action: "findsubs", lang: "eng"}
        fillSubs(false, 0)
        return
    end if
    names = m.top.data.subs
    count = 0
    if names <> invalid then count = names.Count()
    if index = count + 1
        m.subsMode = "find"
        fillSubs(false, 0)
    else
        m.top.event = {action: "sub", index: index - 1}
    end if
end sub

function onKeyEvent(key as String, press as Boolean) as Boolean
    if not press then return false
    if m.qrOverlay.visible
        ' Solo Atrás: el mismo OK que eligió «Compartir» llega aquí y la cerraría al instante.
        if key = "back"
            m.qrOverlay.visible = false
            m.buttons.setFocus(true)
        end if
        return true
    end if
    if m.descOverlay.visible
        if key = "back" or key = "options"
            m.descOverlay.visible = false
            if m.panel.visible then m.audioList.setFocus(true) else m.buttons.setFocus(true)
        end if
        return true
    end if
    if m.panel.visible
        if key = "back"
            if m.subsMode = "find"
                m.subsMode = "list"
                fillSubs(false, 0)
            else
                m.panel.visible = false
                m.buttons.setFocus(true)
            end if
            return true
        else if key = "right" and m.audioList.hasFocus()
            m.subsList.setFocus(true)
            return true
        else if key = "left" and m.subsList.hasFocus() and m.audioList.content.getChildCount() > 0
            m.audioList.setFocus(true)
            return true
        end if
        return true
    end if
    if key = "options"
        showFullDescription()
        return true
    end if
    if key = "play"   ' ▶ en la ficha: lo mismo que el primer botón (Reproducir / Continuar)
        list = m.top.data.buttons
        if list <> invalid and list.Count() > 0 then m.top.event = {action: "button", id: list[0].id}
        return true
    end if
    if key = "back"
        m.top.event = {action: "close"}
        return true
    end if
    return true   ' la ficha no deja pasar teclas al catálogo de abajo
end function
