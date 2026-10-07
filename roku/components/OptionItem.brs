' Contenido: title, current (la elegida), lead (ícono de la izquierda en vez de la palomita), more (›).
sub init()
    m.t = theme()
    m.bg = m.top.findNode("bg")
    m.icon = m.top.findNode("icon")
    m.label = m.top.findNode("label")
    m.chevron = m.top.findNode("chevron")
    m.bg.blendColor = m.t.lime
    m.regular = makeFont(32)
    m.bold = makeFont(32, "bold")
    m.current = false
end sub

sub onSize()
    w = m.top.width
    h = m.top.height
    m.bg.width = w
    m.bg.height = h
    m.label.height = h
    m.label.width = w - 68 - 56
    m.icon.translation = [20, Int((h - 32) / 2)]
    m.chevron.translation = [w - 48, Int((h - 32) / 2)]
end sub

sub onContent()
    c = m.top.itemContent
    if c = invalid then return
    m.label.text = c.title
    m.current = c.hasField("current") and c.current = true
    lead = ""
    if c.hasField("lead") then lead = c.lead
    if lead <> ""
        m.icon.uri = "pkg:/images/icons/" + lead + ".png"
        m.icon.visible = true
    else
        m.icon.uri = "pkg:/images/icons/check.png"
        m.icon.visible = m.current
    end if
    m.chevron.visible = c.hasField("more") and c.more = true
    if m.current then m.label.font = m.bold else m.label.font = m.regular
    render()
end sub

sub render()
    focused = m.top.listHasFocus and m.top.focusPercent > 0.5
    m.bg.visible = focused
    if focused
        color = m.t.onLime
    else if m.current
        color = m.t.lime
    else
        color = m.t.text
    end if
    m.label.color = color
    m.icon.blendColor = color
    m.chevron.blendColor = color
end sub
