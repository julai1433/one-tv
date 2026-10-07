' Utilidades compartidas: tamaños de tarjetas, tiempos, nombres de pistas y la regla para elegir el idioma
' al empezar un video.

' «Varios a la vez» está archivado (6 oct 2026: primero pulir lo de todos los días y el repo para compartir).
' El código sigue (Multi.brs, Mosaic.*): para retomarlo, que esto diga true.
function multiViewOn() as Boolean
    return false
end function

' Tamaño de cada tipo de tarjeta (escala 1920×1080): imagen (w×h) y hueco que ocupa en la fila o cuadrícula.
' Una fila vacía conserva el alto de su forma y su tarjeta ocupa todo el ancho (ver EmptyState).
function tileSpec(shape as String) as Object
    if shape = "video" or shape = "frame" then return {w: 352, h: 198, slotW: 352, slotH: 282, gap: 28}
    if shape = "channel" then return {w: 176, h: 176, slotW: 176, slotH: 282, gap: 44}
    if shape = "setting" then return {w: 840, h: 150, slotW: 840, slotH: 150, gap: 36}
    if shape = "square" then return {w: 260, h: 260, slotW: 260, slotH: 344, gap: 28}       ' portadas de música
    if shape = "gridSquare" then return {w: 232, h: 232, slotW: 232, slotH: 316, gap: 24}
    if shape = "gridPoster" then return {w: 186, h: 279, slotW: 186, slotH: 279, gap: 24}
    if shape = "gridVideo" then return {w: 368, h: 207, slotW: 368, slotH: 289, gap: 32}
    if shape = "searchPoster" then return {w: 186, h: 279, slotW: 186, slotH: 279, gap: 24}
    if shape = "searchVideo" then return {w: 288, h: 162, slotW: 288, slotH: 246, gap: 24}
    return {w: 213, h: 320, slotW: 213, slotH: 320, gap: 24}   ' póster
end function

' Margen alrededor de cada tarjeta dentro de su hueco de la lista: las filas y cuadrículas del Roku recortan lo
' que se sale de cada tarjeta, y con el foco la imagen crece al 106 %. Las listas se corren este margen hacia
' arriba y a la izquierda, y el espacio entre tarjetas se achica lo mismo: a la vista no cambia nada.
function tilePad() as Integer
    return 12
end function

function fmtTime(seconds as Dynamic) as String
    total = Int(seconds)
    hours = Int(total / 3600)
    minutes = Int((total mod 3600) / 60)
    secs = total mod 60
    minText = minutes.ToStr()
    if hours > 0 and minutes < 10 then minText = "0" + minText
    secText = secs.ToStr()
    if secs < 10 then secText = "0" + secText
    if hours > 0 then return hours.ToStr() + ":" + minText + ":" + secText
    return minText + ":" + secText
end function

function fmtDuration(seconds as Dynamic) as String
    if seconds = invalid then return ""
    total = Int(seconds / 60)
    if total < 1 then return "menos de 1 min"
    if total < 60 then return total.ToStr() + " min"
    return Int(total / 60).ToStr() + " h " + (total mod 60).ToStr() + " min"
end function

' «quedan 31 min» a partir de la posición y la duración.
function remainingText(p as Dynamic, duration as Dynamic) as String
    if p = invalid or duration = invalid or duration <= 0 or p <= 0 then return ""
    remaining = duration - p
    if remaining < 60 then return "queda menos de 1 min"
    return "quedan " + fmtDuration(remaining)
end function

' Nombre claro de una pista («Español (latino)»); con una Mac anterior, lo que va antes de « · ».
function trackName(t as Object) as String
    if t.name <> invalid and t.name <> "" then return t.name
    name = t.label
    if name = invalid then return "Pista"
    cut = Instr(1, name, " · ")
    if cut > 0 then name = Left(name, cut - 1)
    return name
end function

' Detalles técnicos de la pista («EAC3 5.1»), solo para la sección de detalles técnicos.
function trackTech(t as Object) as String
    if t.tech <> invalid then return t.tech
    name = t.label
    if name = invalid then return ""
    cut = Instr(1, name, " · ")
    if cut > 0 then return Mid(name, cut + 3)
    return ""
end function

' ¿Es la pista del idioma original? Sin el dato (Mac anterior): la predeterminada del archivo.
function isOriginal(it as Object, index as Integer) as Boolean
    if index < 0 or index >= it.audio.Count() then return false
    known = false
    for each t in it.audio
        if t.original <> invalid then known = true
    end for
    if known then return it.audio[index].original = true
    return index = it.audio_default
end function

function originalAudio(it as Object) as Integer
    for i = 0 to it.audio.Count() - 1
        if isOriginal(it, i) then return i
    end for
    if it.audio_default <> invalid and it.audio_default < it.audio.Count() then return it.audio_default
    return 0
end function

' Regla para EMPEZAR un video: "original" → la pista original; un idioma → la primera de ese idioma
' (si no hay, la original).
function chooseAudio(it as Object, prefs as Object) as Integer
    if it.audio.Count() = 0 then return 0
    pref = prefs["audioLang"]
    if pref <> invalid and pref <> "" and pref <> "original"
        for i = 0 to it.audio.Count() - 1
            if it.audio[i].lang = pref then return i
        end for
    end if
    return originalAudio(it)
end function

' "off" → sin subtítulos; un idioma → el completo de ese idioma antes que los forzados; si no hay, ninguno.
function chooseSub(it as Object, prefs as Object) as Integer
    pref = prefs["subLang"]
    if pref = invalid or pref = "" or pref = "off" then return -1
    forced = -1
    for i = 0 to it.subs.Count() - 1
        s = it.subs[i]
        if s.lang = pref
            if s.forced = true
                if forced = -1 then forced = i
            else
                return i
            end if
        end if
    end for
    return forced
end function

' Lo que se guarda al elegir una pista a mano: "original" si es la original, si no su idioma.
function audioPref(it as Object, index as Integer) as String
    if isOriginal(it, index) then return "original"
    return it.audio[index].lang
end function

' «Inglés, subtítulos en inglés» / «Español (latino)» / «Inglés (original), sin subtítulos».
function langChoiceText(it as Object, audio as Integer, subIndex as Integer) as String
    text = ""
    if audio >= 0 and audio < it.audio.Count() then text = trackName(it.audio[audio])
    if subIndex >= 0 and subIndex < it.subs.Count()
        if text <> "" then text = text + ", "
        text = text + "subtítulos: " + LCase(trackName(it.subs[subIndex]))
    end if
    return text
end function

' «Se oye en español (latino) e inglés · Subtítulos en inglés».
function spokenText(it as Object) as String
    names = uniqueLangs(it.audio)
    if names.Count() = 0
        text = "Sin audio"
    else
        text = "Se oye en " + joinAnd(names)
    end if
    subs = uniqueLangs(it.subs)
    if subs.Count() > 0
        text = text + "   ·   Subtítulos en " + joinAnd(subs)
    else
        text = text + "   ·   Sin subtítulos"
    end if
    return text
end function

' Idiomas sin repetir y en minúsculas: «español (latino)», «inglés».
function uniqueLangs(tracks as Object) as Object
    seen = {}
    out = []
    extras = CreateObject("roRegex", "\s*\((original|forzados|SDH)\)|,\s*de internet|\s+\d+$", "i")
    for each t in tracks
        if t.lang = invalid or t.lang = "" or t.lang = "und"
            name = "un idioma sin identificar"
            if t.original = true then name = "el idioma original"
        else
            name = LCase(extras.ReplaceAll(trackName(t), "")).Trim()
            name = name.Replace("(latino)", "latino").Replace("(", "").Replace(")", "")
        end if
        if name <> "" and not seen.DoesExist(name)
            seen[name] = true
            out.Push(name)
        end if
    end for
    return out
end function

function joinAnd(parts as Object) as String
    if parts.Count() = 0 then return ""
    if parts.Count() = 1 then return parts[0]
    text = ""
    for i = 0 to parts.Count() - 2
        if i > 0 then text = text + ", "
        text = text + parts[i]
    end for
    last = parts[parts.Count() - 1]
    joiner = " y "
    first = LCase(Left(last, 1))
    if first = "i" or first = "í" or Left(LCase(last), 2) = "hi" then joiner = " e "
    return text + joiner + last
end function

' Título sin el año del final: «Rocky (1976)» → «Rocky».
function bareTitle(title as String) as String
    return CreateObject("roRegex", "\s*\((19|20)\d\d\)\s*$", "").ReplaceAll(title, "")
end function

function yearOf(title as String) as String
    m = CreateObject("roRegex", "\(((19|20)\d\d)\)\s*$", "").Match(title)
    if m.Count() > 1 then return m[1]
    return ""
end function

' Texto para buscar: minúsculas y sin acentos.
function plainText(text as String) as String
    t = LCase(text)
    pairs = [["á", "a"], ["é", "e"], ["í", "i"], ["ó", "o"], ["ú", "u"], ["ü", "u"], ["ñ", "n"], ["Á", "a"], ["É", "e"], ["Í", "i"], ["Ó", "o"], ["Ú", "u"], ["Ñ", "n"]]
    for each p in pairs
        t = t.Replace(p[0], p[1])
    end for
    return t
end function

' Número que puede llegar como texto (órdenes del teléfono) o como número.
' Cualquier número (o texto con un número) -> entero; lo demás, 0. Se pregunta por la interfaz y no por el nombre del
' tipo: lo que llega de la computadora (ParseJson) viene como roInt/roFloat/roLongInteger según el valor, y con la lista
' de nombres de antes las duraciones y las fechas de YouTube daban 0 (no se veían en la TV).
function toInt(v as Dynamic) as Integer
    if v = invalid then return 0
    if GetInterface(v, "ifString") <> invalid then return Int(Val(v))
    if GetInterface(v, "ifInt") <> invalid or GetInterface(v, "ifFloat") <> invalid or GetInterface(v, "ifDouble") <> invalid or GetInterface(v, "ifLongInt") <> invalid then return Int(v)
    return 0
end function

function countText(n as Integer, one as String, many as String) as String
    if n = 1 then return "1 " + one
    return n.ToStr() + " " + many
end function

' Iniciales de un canal para su círculo: «NPR Music» → «NM», «Darkan» → «D».
function initialsOf(name as String) as String
    words = name.Trim().Split(" ")
    out = ""
    for each w in words
        if w <> "" and Len(out) < 2 then out = out + UCase(Left(w, 1))
    end for
    if out = "" then out = "?"
    return out
end function

' ---------- fecha de publicación de un video de YouTube ----------

' «hace 5 min», «hace 3 h», «hace 2 días», «hace 3 semanas», «hace 4 meses», «hace 2 años»; "" si no se sabe.
function agoText(epoch as Dynamic) as String
    when = toInt(epoch)
    if when <= 0 then return ""
    secs = CreateObject("roDateTime").AsSeconds() - when
    if secs < 0 then secs = 0
    if secs < 60 then return "hace un momento"
    if secs < 3600 then return "hace " + Int(secs / 60).ToStr() + " min"
    if secs < 86400 then return "hace " + Int(secs / 3600).ToStr() + " h"
    days = Int(secs / 86400)
    if days < 7
        n = days
        unit = "día"
        units = "días"
    else if days < 30
        n = Int(days / 7)
        unit = "semana"
        units = "semanas"
    else if days < 365
        n = Int(days / 30.4375)
        unit = "mes"
        units = "meses"
    else
        n = Int(days / 365)
        unit = "año"
        units = "años"
    end if
    if n = 1 then return "hace 1 " + unit
    return "hace " + n.ToStr() + " " + units
end function

' «12 sep 2023» (en la hora de la TV).
function dateText(epoch as Dynamic) as String
    when = CreateObject("roDateTime")
    when.FromSeconds(toInt(epoch))
    when.ToLocalTime()
    months = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
    return when.GetDayOfMonth().ToStr() + " " + months[when.GetMonth() - 1] + " " + when.GetYear().ToStr()
end function

' Para la ficha: «Publicado el 12 sep 2023» si se sabe exacta, «Publicado hace 3 años» si solo es aproximada, "" si no.
function publishedText(epoch as Dynamic, approx as Dynamic) as String
    if toInt(epoch) <= 0 then return ""
    if approx <> invalid
        if approx = true then return "Publicado " + agoText(epoch)
    end if
    return "Publicado el " + dateText(epoch)
end function
