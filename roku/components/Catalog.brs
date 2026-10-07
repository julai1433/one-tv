' Lo que muestra cada sección de la biblioteca (Inicio, En español, Películas, Series, En vivo, Fila de
' reproducción, la página de una serie y los resultados de Buscar) y cómo se arma cada tarjeta.
' Las filas son siempre las mismas: una fila vacía enseña (huecos, frase, causa y acción) en lugar de desaparecer.

' ---------- piezas ----------

function newRow(root as Object, title as String, shape as String) as Object
    row = root.createChild("ContentNode")
    row.title = title
    row.addFields({shape: shape})
    return row
end function

function newTile(row as Object, id as String, style as String, shape as String, inRow as Boolean) as Object
    spec = tileSpec(shape)
    tile = row.createChild("ContentNode")
    tile.id = id
    ' dur: duración de un video de YouTube en segundos (la etiqueta sobre la miniatura; 0 = no se dibuja).
    ' saved: video de YouTube guardado sin conexión (marca de descarga arriba a la derecha).
    tile.addFields({style: style, w: spec.w, h: spec.h, inRow: inRow, progress: 0.0, spanish: false, line2: "", info: "", initials: "", icon: "", dur: 0, saved: false})
    return tile
end function

' Fila vacía que enseña (DESIGN.md, pieza 4): conserva la forma de la fila con huecos dibujados, una frase de
' marquesina, la causa y, si la tele puede hacer algo, la acción (OK la hace; ver emptyAction en MainScene).
sub emptyRow(row as Object, phrase as String, cause as String, action as String, actionId as String)
    fillEmpty(row, phrase, cause, action, actionId, false)
end sub

sub fillEmpty(row as Object, phrase as String, cause as String, action as String, actionId as String, big as Boolean)
    row.addFields({isEmpty: true, big: big})
    spec = tileSpec(row.shape)
    h = spec.slotH
    if big then h = h + 60
    tile = row.createChild("ContentNode")
    tile.id = "empty:" + actionId
    tile.title = phrase
    tile.addFields({style: "empty", w: 1752, h: h, inRow: true, line2: cause, actionText: action,
                    emptyShape: row.shape, big: big, info: ""})
end sub

' Película o episodio con su póster (el de la serie, si es un episodio).
sub addItemTile(row as Object, id as String, shape as String, inRow as Boolean)
    it = m.lib.items[id]
    if it = invalid then return
    tile = newTile(row, id, "poster", shape, inRow)
    tile.title = it.full_title
    tile.HDPosterUrl = m.server + artOf(it)
    tile.progress = progressOf(id, it.duration)
    tile.spanish = it.dub = true
    tile.info = itemInfo(id, it) + "   ·   *: opciones"
end sub

sub addShowTile(row as Object, show as Object, shape as String, inRow as Boolean)
    tile = newTile(row, "serie:" + show.key, "poster", shape, inRow)
    tile.title = show.title
    if show.art <> invalid
        tile.HDPosterUrl = m.server + show.art
    else if m.lib.items[show.poster] <> invalid
        tile.HDPosterUrl = m.server + m.lib.items[show.poster].poster
    end if
    tile.spanish = show.dub = true
    tile.info = showInfo(show)
end sub

' Fotograma con título debajo (episodios en la página de una serie, historial, en vivo).
function addFrameTile(row as Object, id as String, title as String, subtitle as String, thumb as String) as Object
    tile = newTile(row, id, "frame", "frame", true)
    tile.title = title
    tile.line2 = subtitle
    tile.HDPosterUrl = thumb
    return tile
end function

' Ajuste general: un título y debajo dos segmentos («kind: segments») o un botón («kind: button»).
function addSettingTile(row as Object, id as String, title as String) as Object
    tile = newTile(row, "set:" + id, "setting", "setting", true)
    tile.title = title
    return tile
end function

' «Rocky (1976) · 1 h 59 min · Español (latino)» / «Ted Lasso · T4 E1 · quedan 31 min · Inglés, subtítulos: inglés».
function itemInfo(id as String, it as Object) as String
    parts = [it.full_title]
    p = resumePos(id)
    if p > 0 then parts.Push(remainingText(p, it.duration)) else parts.Push(fmtDuration(it.duration))
    lang = langChoiceText(it, chooseAudio(it, m.prefs), chooseSub(it, m.prefs))
    if lang <> "" then parts.Push(lang)
    return parts.Join("   ·   ")
end function

function showInfo(show as Object) as String
    seasons = show.seasons.Count()
    text = show.title + "   ·   " + countText(seasons, "temporada", "temporadas")
    nxt = nextUp(show)
    it = m.lib.items[nxt.id]
    if it <> invalid then text = text + "   ·   " + nxt.verb + ": T" + it.season.ToStr() + " " + it.ep
    return text
end function

' Póster de la película, o el de su serie si es un episodio; si no hay, el fotograma.
function artOf(it as Object) as String
    if it.art <> invalid then return it.art
    if it.kind = "episode" and m.lib.series <> invalid
        for each show in m.lib.series
            if show.title = it.show and show.art <> invalid then return show.art
        end for
    end if
    return it.poster
end function

function resumePos(id as String) as Integer
    if m.progress[id] = invalid then return 0
    return Int(m.progress[id])
end function

function progressOf(id as String, duration as Dynamic) as Float
    if duration = invalid or duration <= 0 then return 0.0
    return resumePos(id) / duration
end function

' ---------- Inicio ----------

sub buildHome()
    root = CreateObject("roSGNode", "ContentNode")
    ' 1. Seguir viendo: biblioteca y YouTube juntos, lo más reciente primero.
    row = newRow(root, "Seguir viendo", "poster")
    for each e in continueList()
        if e.kind = "yt"
            addYtCardTile(row, e)
        else
            addItemTile(row, e.id, "poster", true)
        end if
    end for
    if row.getChildCount() = 0 then emptyRow(row, "Nada a medias", "Lo que empieces a ver se queda aquí, justo donde lo dejaste.", "Ver películas", "movies")
    ' 2. En español.
    list = spanishList()
    row = newRow(root, "En español   ·   " + spanishCount(list), "poster")
    for each entry in list
        if entry.show <> invalid then addShowTile(row, entry.show, "poster", true) else addItemTile(row, entry.id, "poster", true)
    end for
    if row.getChildCount() = 0 then emptyRow(row, "Todavía nada en español", "Aquí salen las películas y series que se oyen en español.", "Ver películas", "movies")
    ' 3. Nuevos de tus canales.
    row = newRow(root, "Nuevos de tus canales", "video")
    fillNewVideos(row)
    ' 4. Porque viste…
    row = newRow(root, becauseTitle(), "video")
    fillBecause(row)
    ' 5. Recién agregadas.
    row = newRow(root, "Recién agregadas", "poster")
    if m.lib.movies <> invalid and m.lib.movies.Count() > 0 and m.lib.movies[0].title = "Recién agregadas"
        for each entry in m.lib.movies[0].items
            addItemTile(row, entry.id, "poster", true)
        end for
    end if
    if row.getChildCount() = 0 then emptyRow(row, "Nada nuevo", "Lo que agregues a la biblioteca sale aquí primero.", "Buscar películas nuevas", "rescan")
    m.rows.header = "Inicio"
    m.rows.topButton = ""
    m.rows.content = root
end sub

' «Seguir viendo» de la Mac (campo continue); con una Mac anterior, el de la biblioteca y luego el de YouTube.
function continueList() as Object
    if m.lib.continue <> invalid then return m.lib.continue
    out = []
    if m.lib.keep_watching <> invalid
        for each e in m.lib.keep_watching
            out.Push({kind: "item", id: e.id, p: e.p})
        end for
    end if
    if m.ytHome <> invalid and m.ytHome.continue <> invalid
        for each v in m.ytHome.continue
            out.Push({kind: "yt", id: v.id, title: v.title, channel: v.channel, thumb: v.thumb, p: v.p, duration: v.duration, published: v.published, published_approx: v.published_approx})
        end for
    end if
    return out
end function

' Películas y series que se oyen en español, por título.
function spanishList() as Object
    movies = []
    for each id in m.lib.items
        it = m.lib.items[id]
        if it.kind = "movie" and it.dub = true then movies.Push({id: id, key: LCase(it.title)})
    end for
    movies.SortBy("key")
    if m.lib.series <> invalid
        for each show in m.lib.series
            if show.dub = true then movies.Push({show: show, key: LCase(show.title)})
        end for
    end if
    return movies
end function

function spanishCount(list as Object) as String
    movies = 0
    shows = 0
    for each e in list
        if e.show <> invalid then shows = shows + 1 else movies = movies + 1
    end for
    parts = [countText(movies, "película", "películas")]
    if shows > 0 then parts.Push(countText(shows, "serie", "series"))
    return parts.Join(" y ")
end function

' ---------- En español, Películas y Series (cuadrículas) ----------

sub buildSpanish()
    root = CreateObject("roSGNode", "ContentNode")
    list = spanishList()
    for each entry in list
        if entry.show <> invalid then addShowTile(root, entry.show, "gridPoster", false) else addItemTile(root, entry.id, "gridPoster", false)
    end for
    empty = {phrase: "Todavía nada en español", cause: "Aquí salen las películas y series que se oyen en español.", action: "Ver películas", actionId: "movies"}
    showGrid("En español", spanishCount(list), [], "", empty, root)
end sub

function languageChips() as Object
    return [{id: "all", text: "Todas"}, {id: "yes", text: "Con español"}, {id: "no", text: "Sin español"}]
end function

' ¿Pasa el filtro de idioma? "yes": se oye en español; "no": no se oye en español (para buscarle doblaje).
function passesFilter(filter as String, dub as Dynamic) as Boolean
    if filter = "yes" then return dub = true
    if filter = "no" then return dub <> true
    return true
end function

sub buildMovies()
    filter = m.filters.movies
    list = []
    for each id in m.lib.items
        it = m.lib.items[id]
        if it.kind = "movie" and passesFilter(filter, it.dub) then list.Push({id: id, key: LCase(it.title)})
    end for
    list.SortBy("key")
    root = CreateObject("roSGNode", "ContentNode")
    for each entry in list
        addItemTile(root, entry.id, "gridPoster", false)
    end for
    count = countText(list.Count(), "película", "películas")
    if filter = "yes" then count = count + " con español"
    if filter = "no" then count = count + " sin español"
    showGrid("Películas", count, languageChips(), filter, gridEmpty("película", "películas", filter), root)
end sub

sub buildSeries()
    filter = m.filters.series
    root = CreateObject("roSGNode", "ContentNode")
    n = 0
    if m.lib.series <> invalid
        for each show in m.lib.series
            if passesFilter(filter, show.dub)
                addShowTile(root, show, "gridPoster", false)
                n = n + 1
            end if
        end for
    end if
    count = countText(n, "serie", "series")
    if filter = "yes" then count = count + " con español"
    if filter = "no" then count = count + " sin español"
    showGrid("Series", count, languageChips(), filter, gridEmpty("serie", "series", filter), root)
end sub

' Vacío de Películas o Series: con un filtro puesto, «Ver todas»; sin filtro, la biblioteca está vacía.
function gridEmpty(one as String, many as String, filter as String) as Object
    if filter <> "all"
        phrase = "Ninguna " + one + " con este filtro"
        return {phrase: phrase, cause: "Cambia el filtro de arriba o mira todas.", action: "Ver todas", actionId: "filter-all"}
    end if
    return {phrase: "Todavía no hay " + many, cause: "Agrega " + many + " a la carpeta de la biblioteca y aparecen aquí solas.",
            action: "Buscar " + many + " nuevas", actionId: "rescan"}
end function

sub showGrid(title as String, count as String, chips as Object, value as String, empty as Object, root as Object)
    m.grid.shape = "gridPoster"
    m.grid.header = title
    m.grid.count = count
    m.grid.controlStyle = "segments"
    m.grid.controlValue = value
    m.grid.controls = chips
    m.grid.emptySpec = empty
    m.grid.content = root
end sub

' Filtros de Películas y Series: se recuerdan en este dispositivo. En una página, sus botones (ver YouTube.brs).
sub onGridControl(view as Object, id as String)
    if view.isSameNode(m.pageGrid)
        onPageControl(id)
        return
    end if
    name = sectionNames()[m.section]
    if name <> "movies" and name <> "series" then return
    m.filters[name] = id
    reg = CreateObject("roRegistrySection", "filtros")
    reg.Write(name, id)
    reg.Flush()
    m.grid.focusIndex = 0
    renderSection()
end sub

' ---------- una serie: lo que sigue y una fila por temporada ----------

function findShow(key as String) as Dynamic
    if m.lib = invalid or m.lib.series = invalid then return invalid
    for each show in m.lib.series
        if show.key = key then return show
    end for
    return invalid
end function

' El episodio a medias, o el siguiente al último visto, o el primero.
function nextUp(show as Object) as Object
    episodes = []
    for each season in show.seasons
        for each entry in season.items
            episodes.Push(entry.id)
        end for
    end for
    if m.lib.keep_watching <> invalid
        for each entry in m.lib.keep_watching
            for each ep in episodes
                if ep = entry.id
                    if entry.p > 0 then return {id: ep, verb: "Continuar"}
                    return {id: ep, verb: "Siguiente"}
                end if
            end for
        end for
    end if
    last = -1
    for i = 0 to episodes.Count() - 1
        if m.seen[episodes[i]] <> invalid then last = i
    end for
    if last = -1 then return {id: episodes[0], verb: "Empezar"}
    if last < episodes.Count() - 1 then return {id: episodes[last + 1], verb: "Siguiente"}
    return {id: episodes[0], verb: "Ver de nuevo"}
end function

sub buildSeriesPage(key as String)
    show = findShow(key)
    if show = invalid then return
    root = CreateObject("roSGNode", "ContentNode")
    nxt = nextUp(show)
    it = m.lib.items[nxt.id]
    row = newRow(root, nxt.verb, "frame")
    if it <> invalid then addEpisodeTile(row, nxt.id, it, "T" + it.season.ToStr() + " " + it.ep)
    for each season in show.seasons
        row = newRow(root, season.title, "frame")
        for each entry in season.items
            ep = m.lib.items[entry.id]
            if ep <> invalid then addEpisodeTile(row, entry.id, ep, "")
        end for
    end for
    m.pageRows.header = show.title
    m.pageRows.topButton = ""
    m.pageRows.content = root
end sub

sub addEpisodeTile(row as Object, id as String, it as Object, prefix as String)
    title = it.ep
    if prefix <> "" then title = prefix
    if it.ep_title <> "" then title = title + " · " + it.ep_title
    subtitle = fmtDuration(it.duration)
    p = resumePos(id)
    if p > 0 then subtitle = remainingText(p, it.duration)
    if m.seen[id] <> invalid then subtitle = "Visto"
    tile = addFrameTile(row, id, title, subtitle, m.server + it.poster)
    tile.progress = progressOf(id, it.duration)
    tile.spanish = it.dub = true
    tile.info = itemInfo(id, it) + "   ·   *: opciones"
end sub

' ▶ sobre una serie: el episodio que sigue, sin pasar por la ficha.
sub playSeries(key as String)
    show = findShow(key)
    if show = invalid then return
    startItem(nextUp(show).id, true, invalid)
end sub

' ---------- En vivo ----------

sub buildLive()
    root = CreateObject("roSGNode", "ContentNode")
    row = newRow(root, "Canales de hoy", "frame")
    if m.lib.live <> invalid
        for each channel in m.lib.live
            tile = addFrameTile(row, "live:" + channel.id, channel.name, channel.host, m.server + channel.poster)
            tile.info = channel.name + "   ·   en vivo, sin anuncios"
        end for
    end if
    if row.getChildCount() = 0 then emptyRow(row, "No hay canales en vivo", "Se agregan desde la web de One TV, en «En vivo».", "Buscar otra vez", "refresh")
    m.rows.header = "En vivo"
    m.rows.topButton = ""
    m.rows.content = root
end sub

' ---------- Fila de reproducción, historial y ajustes generales ----------

sub buildQueue()
    root = CreateObject("roSGNode", "ContentNode")
    queue = m.lib.queue
    if queue = invalid then queue = []
    title = "En espera"
    if queue.Count() > 0 then title = "En espera   ·   " + countText(queue.Count(), "video", "videos")
    row = newRow(root, title, "video")
    for i = 0 to queue.Count() - 1
        q = queue[i]
        tile = newTile(row, "q:" + i.ToStr(), "video", "video", true)
        tile.title = q.title
        tile.line2 = "OK: verlo ahora"
        tile.addFields({menu: true})   ' *: subir, bajar o quitar (Lists.brs)
        if q.thumb <> invalid then tile.HDPosterUrl = m.server + q.thumb
        if q.kind = "yt" then tile.dur = toInt(q.duration)
        tile.info = q.title
        if tile.dur > 0 then tile.info = q.title + "   ·   " + fmtTime(tile.dur)
        tile.info = tile.info + "   ·   *: mover o quitar"
    end for
    if row.getChildCount() = 0
        fillEmpty(row, "La fila está vacía", "En la ficha de cualquier película o video elige «A continuación» o «Al final de la fila».", "Elegir algo en Inicio", "home", true)
    end if
    row = newRow(root, "Historial", "frame")
    if m.lib.history <> invalid
        for each h in m.lib.history
            if row.getChildCount() >= 30 then exit for
            addHistoryTile(row, h)
        end for
    end if
    if row.getChildCount() = 0 then emptyRow(row, "Todavía no has visto nada", "Lo que veas aquí se anota con el día y la hora.", "", "")
    ' Ajustes generales: dos segmentos para «Al terminar la fila» y «Mostrar el nombre del capítulo», y botones
    ' para los canales ocultos de YouTube y para buscar lo nuevo.
    row = newRow(root, "Ajustes generales", "setting")
    autoplay = ytAutoplayOn()
    tile = addSettingTile(row, "autoplay", "Al terminar la fila")
    chosen = 0
    if autoplay then chosen = 1
    tile.addFields({kind: "segments", options: ["Detenerse", "Seguir con recomendados"], chosen: chosen})
    if autoplay
        tile.info = "OK: cambiar   ·   Al acabar la fila siguen videos recomendados por YouTube, uno tras otro."
    else
        tile.info = "OK: cambiar   ·   Al acabar la fila, la reproducción se detiene."
    end if
    showNames = chapterTitlesOn()
    tile = addSettingTile(row, "chapters", "Mostrar el nombre del capítulo")
    chosen = 1
    if showNames then chosen = 0
    tile.addFields({kind: "segments", options: ["Sí", "No"], chosen: chosen})
    if showNames
        tile.info = "OK: cambiar   ·   En los videos de YouTube con capítulos, su nombre aparece unos segundos al empezar cada uno."
    else
        tile.info = "OK: cambiar   ·   El nombre del capítulo no aparece; ‹ › siguen saltando de capítulo."
    end if
    tile = addSettingTile(row, "hidden", "Canales silenciados")
    tile.addFields({kind: "button", buttonText: hiddenButtonText()})
    tile.icon = "pkg:/images/icons/eye-off.png"
    tile.info = "OK: ver los canales de YouTube que silenciaste y volver a mostrarlos."
    tile = addSettingTile(row, "reload", "Biblioteca")
    tile.addFields({kind: "button", buttonText: "Buscar películas y series nuevas"})
    tile.icon = "pkg:/images/icons/refresh.png"
    tile.info = "Revisa las carpetas de la biblioteca y agrega lo nuevo."
    m.rows.header = "Fila de reproducción"
    m.rows.topButton = ""
    m.rows.content = root
end sub

sub addHistoryTile(row as Object, h as Object)
    spanish = false
    if h.kind = "yt"
        id = "yt:" + h.id
        rememberYt(h, false)
    else
        it = m.lib.items[h.id]
        if it = invalid then return
        id = h.id
        spanish = it.dub = true
    end if
    progress = 0.0
    subtitle = h.when
    if h.done = true
        subtitle = subtitle + " · vista"
    else if h.duration <> invalid and h.duration > 0
        progress = h.p / h.duration
    end if
    tile = addFrameTile(row, id, h.title, subtitle, m.server + h.thumb)
    tile.progress = progress
    tile.spanish = spanish
    if h.kind = "yt" then tile.dur = toInt(h.duration)
    tile.info = h.title + "   ·   " + subtitle + "   ·   *: opciones"
end sub

' Mostrar el nombre del capítulo de YouTube al empezar cada uno (ajuste general; si falta, sí).
function chapterTitlesOn() as Boolean
    v = m.prefs["chapterTitles"]
    if v = invalid then return true
    return v = true
end function

function ytAutoplayOn() as Boolean
    v = m.prefs["ytAutoplay"]
    if v = invalid then return false
    return v = true
end function

sub runSetting(name as String)
    if name = "autoplay"
        turnOn = not ytAutoplayOn()
        m.prefs["ytAutoplay"] = turnOn
        post("/api/yt/autoplay", {on: turnOn}, "")
        renderSection()
        if turnOn
            showToast("Al terminar la fila seguirán videos recomendados por YouTube, uno tras otro.", true)
        else
            showToast("Al terminar la fila se detiene la reproducción.", true)
        end if
    else if name = "chapters"
        turnOn = not chapterTitlesOn()
        m.prefs["chapterTitles"] = turnOn
        post("/api/prefs", {chapterTitles: turnOn}, "")
        renderSection()
        if turnOn
            showToast("En los videos de YouTube con capítulos, su nombre aparecerá al empezar cada uno.", true)
        else
            showToast("El nombre del capítulo ya no aparecerá; al pausar se ven los capítulos sobre la barra.", true)
        end if
    else if name = "hidden"
        pushPage({kind: "hidden"})
        loadHidden()
    else if name = "reload"
        showToast("Actualizando la biblioteca…", true)
        post("/api/rescan", {}, "onRescanned")
    end if
end sub

sub onRescanned()
    showToast("Biblioteca actualizada.", true)
    loadLibrary()
end sub

' ---------- Buscar ----------

' Títulos de películas y series que contienen lo escrito (sin importar acentos ni mayúsculas).
sub updateSearchResults(text as String)
    query = plainText(text.Trim())
    if query = "" or m.lib = invalid
        m.search.libContent = invalid
        return
    end if
    root = CreateObject("roSGNode", "ContentNode")
    found = []
    for each id in m.lib.items
        it = m.lib.items[id]
        if it.kind = "movie" and Instr(1, plainText(it.title), query) > 0 then found.Push({id: id, key: LCase(it.title)})
    end for
    if m.lib.series <> invalid
        for each show in m.lib.series
            if Instr(1, plainText(show.title), query) > 0 then found.Push({show: show, key: LCase(show.title)})
        end for
    end if
    found.SortBy("key")
    for each entry in found
        if entry.show <> invalid then addShowTile(root, entry.show, "searchPoster", false) else addItemTile(root, entry.id, "searchPoster", false)
    end for
    m.search.libContent = root
end sub
