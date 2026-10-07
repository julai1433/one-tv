' Todos los colores y la letra de la app, en un solo lugar (DESIGN.md: negro puro, grises neutros, limón y
' guinda; Big Shoulders Display para la marquesina y Archivo para lo demás). El limón es el único acento: sale
' de «lime» y se cambia en una línea.
function theme() as Object
    return {
        ' Fondos: negro y grises sin tinte
        bg: "0x000000FF",            ' fondo de todo
        raise1: "0x0C0C0CFF",        ' menú lateral cerrado
        raise2: "0x161616FF",        ' paneles (idioma, menú abierto, avisos breves)
        raise3: "0x222222FF",        ' pista de las barras de avance, pósters que faltan, fondo de los canales
        line: "0x2E2E2EFF",          ' líneas finas que solo separan
        edge: "0x5E5E58FF",          ' bordes de lo que se toca y huecos de una fila vacía
        edgePanel: "0x686862FF",     ' lo mismo encima de un panel raise2
        scrim: "0x000000B8",         ' velo detrás del menú abierto y del panel de idioma (72 %)
        overlay: "0x000000EB",       ' panel del aviso para saltar, encima del video (92 %)
        badge: "0x000000FF",         ' etiqueta de la duración sobre la miniatura de YouTube: negro…
        badgeOpacity: 0.85,          ' …al 85 % (se aplica como opacidad para conservar las esquinas de 2 px)

        ' Texto
        text: "0xF2F2EEFF",          ' texto principal
        textSoft: "0xC9C9C2FF",      ' sinopsis, línea de información
        muted: "0x8C8C85FF",         ' ayudas, conteos, textos de apoyo

        ' Acento: lo que señalas se vuelve limón
        lime: "0xA6E22EFF",          ' foco, botón principal, barras de avance, sección actual, estado bueno
        onLime: "0x0A0F00FF",        ' letra e íconos encima del limón

        ' Problemas y la etiqueta «Español»
        guindaLight: "0xE0507FFF",   ' SIN MAC, errores
        guinda: "0x7A1535FF",        ' fondo de la etiqueta «Español»
        esText: "0xC4F05AFF",        ' letra y contorno de la etiqueta «Español»
        ytRed: "0xFF0033FF"          ' solo lo de YouTube que se reconoce de un vistazo: «EN VIVO» (la marca es una imagen)
    }
end function

' Letra de la app en la escala de la tele (sobre 1920×1080): 27 (mínimo) · 32 · 38 · 48 · 72 · 110.
' face: "regular", "medium" o "bold" (Archivo, todo lo demás); "display" o "black" (Big Shoulders Display 800 y
' 900: títulos en mayúsculas, estado, vacíos y el aviso para saltar). Nunca la letra del sistema.
function makeFont(size as Integer, face = "regular" as String) as Object
    if m.fontCache = invalid then m.fontCache = {}
    key = face + size.ToStr()
    f = m.fontCache[key]
    if f <> invalid then return f
    files = {regular: "Archivo-Regular", medium: "Archivo-Medium", bold: "Archivo-Bold",
             display: "BigShouldersDisplay-ExtraBold", black: "BigShouldersDisplay-Black"}
    name = files[face]
    if name = invalid then name = files.regular
    f = CreateObject("roSGNode", "Font")
    f.uri = "pkg:/fonts/" + name + ".ttf"
    f.size = size
    m.fontCache[key] = f
    return f
end function

' Texto de marquesina: en mayúsculas, también las vocales con acento y la ñ.
function marquee(text as String) as String
    t = UCase(text)
    for each p in [["á", "Á"], ["é", "É"], ["í", "Í"], ["ó", "Ó"], ["ú", "Ú"], ["ü", "Ü"], ["ñ", "Ñ"]]
        t = t.Replace(p[0], p[1])
    end for
    return t
end function
