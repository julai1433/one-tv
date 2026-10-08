' Pantalla principal: navegación entre secciones y páginas, el menú lateral, el catálogo que manda la Mac y
' las órdenes que llegan del teléfono (ECP).

' Secciones del menú, en su orden.
function sectionNames() as Object
    return ["search", "home", "spanish", "movies", "series", "youtube", "music", "live", "queue"]
end function

sub init()
    m.t = theme()
    m.top.backgroundColor = m.t.bg
    m.top.backgroundURI = ""
    m.top.findNode("bg").color = m.t.bg
    m.server = CreateObject("roAppInfo").GetValue("server_url")
    m.deviceId = CreateObject("roDeviceInfo").GetChannelClientId()
    m.menu = m.top.findNode("menu")
    m.rows = m.top.findNode("rows")
    m.grid = m.top.findNode("grid")
    m.search = m.top.findNode("search")
    m.pageRows = m.top.findNode("pageRows")
    m.pageGrid = m.top.findNode("pageGrid")
    m.detail = m.top.findNode("detail")
    m.player = m.top.findNode("player")
    m.mosaic = m.top.findNode("mosaic")
    m.picker = m.top.findNode("picker")
    m.pick = {ctx: "", mode: ""}   ' la lista de «Ver con otro» abierta: desde dónde (player|detail|mosaic) y para qué
    m.toast = m.top.findNode("toast")
    m.toastText = m.top.findNode("toastText")
    m.toastText.font = makeFont(32)
    m.top.findNode("toastBg").color = m.t.raise2
    m.offline = m.top.findNode("offline")
    m.offline.observeField("event", "onOfflineEvent")
    m.help = m.top.findNode("help")
    setupHelp()
    m.retry = m.top.findNode("retryTimer")
    m.toastTimer = m.top.findNode("toastTimer")
    m.confirmTimer = m.top.findNode("confirmTimer")
    m.offConfirmTimer = m.top.findNode("offConfirmTimer")
    m.offTimer = m.top.findNode("offTimer")
    m.code = m.top.findNode("code")
    m.codeTimer = m.top.findNode("codeTimer")
    setupCode()

    m.lib = invalid
    m.ytHome = invalid        ' /api/yt/home: listas, nuevos, porque viste, seguir viendo, recientes
    m.skipNote = ""           ' por qué se saltó un video de YouTube (va en el aviso de lo siguiente)
    m.ytChannels = invalid    ' /api/yt/subscriptions: tus canales
    m.ytHomeAt = 0
    m.ytHidden = invalid      ' /api/yt/hidden: canales ocultos [{id, title}] (Fila de reproducción → Ajustes generales)
    m.hideArmed = ""          ' canal cuyo «Ocultar canal» espera el segundo OK
    m.hideAskText = ""        ' el aviso que lo pide (se quita si se deja pasar)
    m.offById = invalid       ' /api/offline: id de YouTube -> {state, progress, error, bytes…} (invalid hasta que llega)
    m.offVideos = []          ' /api/offline: los videos, como los manda la Mac
    m.offLists = []           ' /api/offline: las listas guardadas {id, title, count, done}
    m.offBusy = 0             ' cuántos están en la cola o bajándose
    m.offLoading = false      ' ¿hay una lectura de /api/offline en camino?
    m.offLoadAt = 0
    m.offSig = ""             ' lo último que se leyó (para rehacer solo si cambió algo)
    m.offCoarse = ""          ' lo mismo, con el avance de 10 en 10 %: lo que se ve en las filas
    m.offArmed = ""           ' "v:<id>" o "l:<id>": guardado cuyo botón espera el segundo OK para quitarlo
    m.offDoneText = ""        ' aviso que sigue a un «quitar» que salió bien
    m.offMsgOn = false        ' ¿el mensaje de la ficha es el motivo de un error al guardar?
    m.offRowAt = -1           ' lugar de la fila «Guardados» en YouTube (-1: no hay)
    m.followChannel = ""      ' canal recién anclado o desanclado: el foco de «Tus canales» lo sigue a su nuevo lugar
    m.favs = {}               ' id de YouTube -> true/false: está en Favoritos (portada de YouTube, /api/lists, lo cambiado aquí)
    m.favs.SetModeCaseSensitive()
    m.vidLists = invalid      ' /api/lists?video=: {vid, lists: [{id, title, count, source, has}]} del video de la ficha (Lists.brs)
    m.listsWant = ""          ' video cuya lista «Agregar a lista» se abre en cuanto lleguen sus listas
    m.newListDlg = invalid    ' el teclado de «Lista nueva»
    m.queueMenuAt = -1        ' video de la fila cuyo menú (*) está abierto
    m.listQueueId = ""        ' lista cuyo menú «A la fila» está abierto
    m.ytPage = 1              ' búsqueda de YouTube: la última página traída y si hay más («Cargar más»)
    m.ytMore = false
    m.ytMoreBusy = false
    m.ytLive = false          ' la búsqueda de YouTube es «Solo en vivo»
    m.ytInfo = {}             ' id de YouTube -> {title, channel, duration, thumb} de todo lo que se ha visto pasar
    m.ytProgress = {}         ' id de YouTube -> segundos donde se quedó
    m.progress = {}           ' id -> segundos donde se quedó (la Mac es la fuente de verdad)
    m.seen = {}
    m.prefs = {}              ' idioma de ESTE dispositivo (y ajustes generales como ytAutoplay)
    m.pending = invalid       ' orden recibida antes de tener el catálogo
    m.migrated = false
    m.tasks = []
    m.cur = invalid           ' lo que está en la ficha o reproduciéndose
    m.section = 1             ' Inicio
    m.pages = []              ' páginas abiertas encima de la sección (serie, canal, lista, búsqueda en YouTube)
    m.sectionFocus = {}
    m.view = invalid          ' la vista que se ve ahora (sección o página)
    m.searchQuery = ""

    reg = CreateObject("roRegistrySection", "filtros")
    m.filters = {movies: "all", series: "all"}
    for each key in ["movies", "series"]
        if reg.Exists(key) then m.filters[key] = reg.Read(key)
    end for

    for each view in [m.rows, m.grid, m.search, m.pageRows, m.pageGrid]
        view.observeField("event", "onViewEvent")
    end for
    m.rows.observeField("focus", "onMusicRowsFocus")          ' Música: más artistas o álbumes al llegar al final (Music.brs)
    m.pageGrid.observeField("focusIndex", "onMusicGridFocus")  ' y más canciones al bajar por un álbum, artista o lista
    m.menu.observeField("event", "onMenuEvent")
    m.detail.observeField("event", "onDetailEvent")
    m.player.observeField("event", "onPlayerEvent")
    m.mosaic.observeField("event", "onMosaicEvent")
    m.picker.observeField("event", "onPickerEvent")
    m.detail.server = m.server
    m.player.server = m.server
    m.mosaic.server = m.server
    m.player.deviceId = m.deviceId
    m.retry.observeField("fire", "loadLibrary")
    m.toastTimer.observeField("fire", "hideToast")
    m.confirmTimer.observeField("fire", "disarmHide")
    m.offConfirmTimer.observeField("fire", "disarmOffline")
    m.offTimer.observeField("fire", "onOffTick")
    m.codeTimer.observeField("fire", "hideCode")
    m.offTimer.control = "start"
    showSection(1, true)
end sub

' ---------- arranque y órdenes desde el teléfono ----------

sub onLaunchArgs()
    args = m.top.launchArgs
    if args <> invalid
        if args.server <> invalid and args.server <> ""
            m.server = args.server
            m.detail.server = m.server
            m.player.server = m.server
            m.mosaic.server = m.server
        end if
        if args.contentId <> invalid then m.pending = args
    end if
    loadLibrary()
    if args = invalid or args.cmd = invalid then return
    if args.cmd = "codigo" then showCode(args.codigo)   ' se abrió para mostrar el código (mac/roku.py, show_code)
end sub

' Órdenes que llegan con la app abierta: actualizar, reproducir algo, cambiar pistas o saltar.
sub onInputArgs()
    args = m.top.inputArgs
    if args = invalid then return
    if args.server <> invalid and args.server <> "" then m.server = args.server
    cmd = ""
    if args.cmd <> invalid then cmd = args.cmd
    if cmd = "refresh"   ' la computadora avisa que algo cambió (biblioteca, canales anclados u ocultos desde la web)
        loadLibrary()
        loadYouTubeHome()
        loadChannels()
        return
    end if
    if cmd = "tracks"
        if m.player.visible then applyTracks(args)
        return
    end if
    if cmd = "song"   ' la computadora pide la canción anterior (dir=-1) o la siguiente (dir=1) de lo que suena
        if m.player.visible and m.cur <> invalid and m.cur.music = true and args.dir <> invalid then musicStep(Int(Val(args.dir)))
        return
    end if
    if cmd = "seek"
        if m.player.visible and args.t <> invalid then m.player.seekTo = Val(args.t)
        return
    end if
    if cmd = "codigo"   ' el código para cambiar la configuración desde otro aparato (mac/asistente.py)
        showCode(args.codigo)
        return
    end if
    if args.contentId = invalid then return
    id = args.contentId
    closePicker(false)
    closeDetail(false)
    if Left(id, 6) = "music:"   ' «Escuchar en la TV» desde la web: se piden las canciones (Music.brs)
        apiGet("/api/music/session?id=" + Mid(id, 7), "onMusicSession")
    else if Left(id, 7) = "mosaic:"
        openMosaic(Mid(id, 8), args.focus)
    else if Left(id, 3) = "yt:"
        m.pending = args   ' se recarga el catálogo para tener el título que la Mac acaba de guardar
        loadLibrary()
    else if m.lib <> invalid and Left(id, 5) = "live:"
        playLive(Mid(id, 6))
    else if m.lib <> invalid and m.lib.items[id] <> invalid
        startItem(id, true, args)
    else
        m.pending = args
        loadLibrary()
    end if
end sub

' ---------- catálogo ----------

sub loadLibrary()
    if m.lib = invalid and not m.offline.visible then showToast("Conectando con la computadora…", false)
    apiGet("/api/library?device_id=" + m.deviceId, "onLibrary")
end sub

sub onLibrary(event as Object)
    task = event.getRoSGNode()
    if task.error <> "" or task.result = invalid
        print "[cine] catálogo: "; task.error
        m.menu.status = "offline"
        if m.lib = invalid
            hideToast()
            showOffline()
            m.retry.control = "start"
        end if
        return
    end if
    m.menu.status = "ok"
    hideOffline()
    first = m.lib = invalid
    m.lib = task.result
    m.progress = {}
    if m.lib.watching <> invalid
        for each w in m.lib.watching
            m.progress[w.id] = w.p
        end for
    end if
    m.seen = {}
    if m.lib.seen <> invalid
        for each id in m.lib.seen
            m.seen[id] = true
        end for
    end if
    if m.lib.prefs <> invalid then m.prefs = m.lib.prefs
    m.ytProgress = {}   ' se rehace con lo que manda la Mac (lo terminado deja de estar a medias)
    if m.lib.continue <> invalid
        for each e in m.lib.continue
            if e.kind = "yt" then rememberYt(e, true)
        end for
    end if
    for each list in [m.lib.youtube, m.lib.queue]
        if list <> invalid
            for each v in list
                if v.kind = invalid or v.kind = "yt" then rememberYt(v, false)
            end for
        end if
    end for
    queued = 0
    if m.lib.queue <> invalid then queued = m.lib.queue.Count()
    m.menu.badge = queued
    if first then hideToast()
    if m.lib.items.Count() = 0   ' sin nombres de archivos ni comandos: qué pasa y qué hacer (como la app de Google TV)
        if m.lib.sin_permiso <> invalid and m.lib.sin_permiso.Count() > 0
            showToast("La computadora no puede leer tu carpeta de videos: abre One TV en ella y verás qué hacer.", false)
        else
            showToast("No hay videos todavía: copia tus películas y series a la carpeta de videos de la computadora.", false)
        end if
    end if
    refreshView()
    loadYouTubeHome()
    if first then loadMusic()   ' Music.brs
    if m.pending <> invalid
        args = m.pending
        m.pending = invalid
        id = args.contentId
        if Left(id, 6) = "music:"
            apiGet("/api/music/session?id=" + Mid(id, 7), "onMusicSession")
        else if Left(id, 7) = "mosaic:"
            openMosaic(Mid(id, 8), args.focus)
        else if Left(id, 5) = "live:"
            playLive(Mid(id, 6))
        else if Left(id, 3) = "yt:"
            startAt = -1   ' donde se quedó, salvo que el teléfono diga desde dónde
            if args.start <> invalid then startAt = toInt(args.start)
            playYouTube(Mid(id, 4), startAt)
        else if m.lib.items[id] <> invalid
            startItem(id, true, args)
        end if
    end if
    if not m.migrated then migrateRegistry()
end sub

' Versiones muy anteriores guardaban el progreso en el Roku: se sube una vez a la Mac y se borra.
sub migrateRegistry()
    m.migrated = true
    resumeReg = CreateObject("roRegistrySection", "resume")
    prefsReg = CreateObject("roRegistrySection", "prefs")
    if resumeReg.GetKeyList().Count() = 0 and prefsReg.GetKeyList().Count() = 0 then return
    entries = {}
    for each id in resumeReg.GetKeyList()
        raw = resumeReg.Read(id)
        if raw <> ""
            data = ParseJson(raw)
            if data <> invalid then entries[id] = {p: data.p, t: data.t}
        end if
    end for
    prefs = {}
    for each key in prefsReg.GetKeyList()
        prefs[key] = prefsReg.Read(key)
    end for
    post("/api/import", {progress: entries, prefs: prefs}, "onImported")
end sub

sub onImported(event as Object)
    if event.getRoSGNode().error <> "" then return
    for each name in ["resume", "prefs"]
        reg = CreateObject("roRegistrySection", name)
        for each key in reg.GetKeyList()
            reg.Delete(key)
        end for
        reg.Flush()
    end for
    loadLibrary()
end sub

' ---------- secciones y páginas ----------

sub showSection(index as Integer, focus as Boolean)
    disarmHide()
    disarmOffline()
    saveSectionFocus()
    m.section = index
    m.menu.selected = index
    m.pages = []
    m.pageRows.visible = false
    m.pageGrid.visible = false
    m.pageRows.content = invalid
    m.pageGrid.content = invalid
    restoreSectionFocus()
    renderSection()
    if focus then focusContent()
    name = sectionNames()[index]
    if (name = "home" or name = "youtube") and m.lib <> invalid then loadYouTubeHome()
    if name = "youtube" then loadChannels()
    if name = "queue" then loadHidden()   ' cuántos canales ocultos hay (Ajustes generales)
end sub

sub saveSectionFocus()
    view = sectionView(m.section)
    if view = invalid then return
    if view.isSameNode(m.grid) then m.sectionFocus[m.section.ToStr()] = m.grid.focusIndex
    if view.isSameNode(m.rows) then m.sectionFocus[m.section.ToStr()] = m.rows.focus
end sub

sub restoreSectionFocus()
    saved = m.sectionFocus[m.section.ToStr()]
    view = sectionView(m.section)
    if view = invalid then return
    if view.isSameNode(m.grid)
        if saved = invalid then m.grid.focusIndex = 0 else m.grid.focusIndex = saved
    else if view.isSameNode(m.rows)
        if saved = invalid then m.rows.focus = [0, 0] else m.rows.focus = saved
    end if
end sub

function sectionView(index as Integer) as Dynamic
    name = sectionNames()[index]
    if name = "search" then return m.search
    if name = "spanish" or name = "movies" or name = "series" then return m.grid
    return m.rows
end function

' Dibuja la sección actual (y, si hay, la página de arriba) con los datos de ahora, sin mover el foco.
sub renderSection()
    view = sectionView(m.section)
    for each other in [m.rows, m.grid, m.search]
        if not other.isSameNode(view) then other.visible = false
    end for
    name = sectionNames()[m.section]
    if name = "search"
        m.search.mode = "all"
        if m.lib <> invalid then updateSearchResults(m.searchQuery)
    else if m.lib <> invalid
        if name = "home" then buildHome()
        if name = "spanish" then buildSpanish()
        if name = "movies" then buildMovies()
        if name = "series" then buildSeries()
        if name = "youtube" then buildYouTube()
        if name = "music" then buildMusic()   ' Music.brs
        if name = "live" then buildLive()
        if name = "queue" then buildQueue()
    else
        loadingView(view, name)
    end if
    if m.pages.Count() = 0
        view.visible = not m.detail.visible and not m.player.visible and not m.offline.visible and not m.mosaic.visible
        m.view = view
    else
        view.visible = false
    end if
end sub

' Mientras llega el catálogo: la cabecera de la sección y nada más.
sub loadingView(view as Object, name as String)
    titles = {home: "Inicio", spanish: "En español", movies: "Películas", series: "Series", youtube: "YouTube", music: "Música", live: "En vivo", queue: "Fila de reproducción"}
    view.header = titles[name]
    view.content = invalid
end sub

sub refreshView()
    renderSection()
    if m.pages.Count() > 0 then renderPage(m.pages[m.pages.Count() - 1])
end sub

' Una página encima de la sección: {kind: series|channel|playlist|ytsearch|hidden, …}.
sub pushPage(page as Object)
    if m.view <> invalid then m.view.visible = false
    m.pages.Push(page)
    if page.kind = "playlist" then loadOffline()   ' para «Guardar la lista sin conexión»
    view = pageView(page)
    if page.kind = "series" then m.pageRows.focus = [0, 0]
    if page.kind = "channel" or page.kind = "playlist" or page.kind = "hidden" or page.kind = "music" then m.pageGrid.focusIndex = 0
    renderPage(page)
    view.visible = true
    m.view = view
    view.setFocus(true)
end sub

sub popPage()
    if m.pages.Count() = 0 then return
    disarmHide()
    disarmOffline()
    page = m.pages.Pop()
    view = pageView(page)
    view.visible = false
    if page.kind <> "ytsearch" then view.content = invalid
    if m.pages.Count() > 0
        top = m.pages[m.pages.Count() - 1]
        m.view = pageView(top)
    else
        m.view = sectionView(m.section)
    end if
    m.view.visible = true
    m.view.setFocus(true)
end sub

function pageView(page as Object) as Object
    if page.kind = "series" then return m.pageRows
    if page.kind = "ytsearch" then return m.search
    return m.pageGrid
end function

sub renderPage(page as Object)
    if page.kind = "series" then buildSeriesPage(page.key)
    if page.kind = "channel" then buildChannelPage(page)
    if page.kind = "playlist" then buildPlaylistPage(page)
    if page.kind = "ytsearch" then m.search.mode = "youtube"
    if page.kind = "hidden" then buildHiddenPage(page)
    if page.kind = "music" then buildMusicPage(page)   ' Music.brs
end sub

' La página de arriba, o invalid si se ve la sección.
function topPage() as Dynamic
    if m.pages.Count() = 0 then return invalid
    return m.pages[m.pages.Count() - 1]
end function

' ---------- menú lateral ----------

sub openMenu()
    m.menu.expanded = true
    m.menu.setFocus(true)
end sub

sub closeMenu()
    m.menu.expanded = false
    focusContent()
end sub

sub onMenuEvent()
    e = m.menu.event
    if e.type = "open"
        m.menu.expanded = false
        showSection(e.index, true)
    else if e.type = "close"
        closeMenu()
    end if
end sub

' ---------- lo que se elige en las vistas ----------

sub onViewEvent(event as Object)
    e = event.getData()
    view = event.getRoSGNode()
    if e.type = "select"
        activate(e.id, false)
    else if e.type = "play"
        activate(e.id, true)
    else if e.type = "top"
        pushPage({kind: "ytsearch"})
    else if e.type = "options"
        if Left(e.id, 2) = "q:"
            openQueueMenu(Int(Val(Mid(e.id, 3))))   ' Lists.brs
        else if not openTileMenu(e.id)          ' PlayerMenus.brs
            showToast("Actualizando la biblioteca…", true)
            loadLibrary()
        end if
    else if e.type = "control"
        onGridControl(view, e.id)
    else if e.type = "query"
        m.searchQuery = e.text
        updateSearchResults(e.text)
    else if e.type = "ytsearch"
        searchYouTube(e.text, e.live = true)
    end if
end sub

' OK (quick = false) o ▶ (quick = true) sobre una tarjeta.
sub activate(id as String, quick as Boolean)
    if id = "" then return
    if id = "ytmore"
        loadMoreYouTube()   ' Lists.brs
        return
    end if
    if activateMusic(id, quick) then return   ' canciones, álbumes, listas y artistas (Music.brs)
    if Left(id, 6) = "empty:"
        emptyAction(Mid(id, 7))
    else if Left(id, 3) = "yt:"
        if quick then playYouTube(Mid(id, 4), -1) else openYouTubeDetail(Mid(id, 4))
    else if Left(id, 2) = "q:"
        post("/api/queue/take", {index: Int(Val(Mid(id, 3)))}, "onQueueTaken")
    else if Left(id, 5) = "live:"
        playLive(Mid(id, 6))
    else if Left(id, 6) = "serie:"
        if quick then playSeries(Mid(id, 7)) else pushPage({kind: "series", key: Mid(id, 7)})
    else if Left(id, 5) = "chan:"
        pushPage({kind: "channel", id: Mid(id, 6), title: tileTitle(id)})
    else if Left(id, 5) = "list:"
        if quick then playPlaylist(Mid(id, 6)) else pushPage({kind: "playlist", id: Mid(id, 6), title: tileTitle(id)})
    else if Left(id, 7) = "unhide:"
        if not quick then unhideChannel(Mid(id, 8))   ' solo con OK: ▶ no lo vuelve a mostrar
    else if Left(id, 4) = "set:"
        runSetting(Mid(id, 5))
    else if m.lib <> invalid and m.lib.items[id] <> invalid
        startItem(id, quick, invalid)
    end if
end sub

' La acción de una fila vacía (OK sobre ella).
sub emptyAction(name as String)
    if name = "movies"
        showSection(3, true)
    else if name = "home"
        showSection(1, true)
    else if name = "ytsearch"
        pushPage({kind: "ytsearch"})
    else if name = "youtube"
        showSection(5, true)
    else if name = "takeout"
        showHelp()
    else if name = "rescan"
        runSetting("reload")
    else if name = "refresh"
        showToast("Buscando otra vez…", true)
        loadLibrary()
    else if name = "filter-all"
        onGridControl(m.grid, "all")
    end if
end sub

' ---------- sin la Mac ----------

' Pantalla «No encuentro la computadora»: la forma de Inicio con huecos, qué revisar y un botón para buscar ya.
sub showOffline()
    host = m.server.Replace("http://", "").Replace("https://", "")
    m.offline.spec = {shape: "poster", width: 1672, height: 320, phrase: "No encuentro la computadora", big: true,
                      cause: "Revisa que esté encendida, despierta y conectada al mismo Wi-Fi que la TV. La sigo buscando sola cada 5 segundos.",
                      detail: "Dirección: " + host, action: "Buscar ahora", actionId: "retry"}
    m.offline.visible = true
    for each view in [m.rows, m.grid, m.search, m.pageRows, m.pageGrid]
        view.visible = false
    end for
    if not m.menu.expanded and not m.detail.visible and not m.player.visible and not m.code.visible then m.offline.setFocus(true)
end sub

sub hideOffline()
    if not m.offline.visible then return
    hadFocus = m.offline.hasFocus()
    m.offline.visible = false
    if m.view <> invalid
        m.view.visible = not m.detail.visible and not m.player.visible
        if hadFocus then m.view.setFocus(true)
    end if
end sub

sub onOfflineEvent()
    showToast("Buscando la computadora…", true)
    loadLibrary()
end sub

' El foco vuelve al contenido: la vista actual o, sin la Mac, el botón «Buscar ahora».
sub focusContent()
    if m.offline.visible
        m.offline.setFocus(true)
    else if m.view <> invalid
        m.view.setFocus(true)
    end if
end sub

' ---------- cómo traer YouTube ----------

sub setupHelp()
    m.top.findNode("helpBg").color = m.t.bg
    title = m.top.findNode("helpTitle")
    title.font = makeFont(72, "black")
    title.color = m.t.text
    intro = m.top.findNode("helpIntro")
    intro.font = makeFont(32)
    intro.color = m.t.textSoft
    intro.text = "Tu historial, tus listas y tus suscripciones llegan con una exportación de Google. Se hace una sola vez, desde una computadora:"
    hint = m.top.findNode("helpHint")
    hint.font = makeFont(27)
    hint.color = m.t.muted
    qrUrl = m.top.findNode("helpQrUrl")
    qrUrl.font = makeFont(32, "bold")
    qrUrl.color = m.t.text
    qrNote = m.top.findNode("helpQrNote")
    qrNote.font = makeFont(27)
    qrNote.color = m.t.muted
    steps = [
        "Entra a takeout.google.com (o escanea el código) y pulsa «Anular selección».",
        "Marca solo «YouTube y YouTube Music». En sus opciones deja historial, listas y suscripciones, quita «vídeos» y pon el historial en JSON.",
        "Crea una sola exportación en .zip. Cuando llegue el correo, descárgala en la computadora donde corre One TV.",
        "Déjala en Descargas sin cambiarle el nombre: One TV la importa sola en unos minutos."
    ]
    ' Pasos de 1020 px de ancho (de x=264 a 1284); el código QR empieza en x=1356, así que no se tocan.
    ' Cada paso mide lo que ocupa (2 o 3 líneas) y el siguiente baja debajo de él: el peor caso (3+3+3+2
    ' líneas de 46 px más 3 separaciones de 36) termina antes de y=990, donde está «Atrás: volver».
    group = m.top.findNode("helpSteps")
    y = 0
    for i = 0 to steps.Count() - 1
        number = group.createChild("Label")
        number.font = makeFont(72, "black")
        number.color = m.t.muted
        number.text = (i + 1).ToStr()
        number.translation = [0, y - 6]
        text = group.createChild("Label")
        text.font = makeFont(38)
        text.color = m.t.text
        text.wrap = true
        text.width = 1020
        text.maxLines = 3
        text.text = steps[i]
        text.translation = [96, y]
        y = y + Int(text.boundingRect().height) + 36
    end for
end sub

sub showHelp()
    m.help.visible = true
    m.help.setFocus(true)
end sub

sub hideHelp()
    m.help.visible = false
    focusContent()
end sub

' ---------- control remoto ----------

function onKeyEvent(key as String, press as Boolean) as Boolean
    if not press then return false
    if m.code.visible   ' el código de la TV: OK o Atrás lo quitan; lo demás no hace nada mientras se ve
        if key = "OK" or key = "back" then hideCode()
        return true
    end if
    if m.player.visible or m.detail.visible or m.mosaic.visible or m.picker.visible then return false
    if m.help.visible
        if key = "back" then hideHelp()
        return true
    end if
    if m.menu.expanded
        if key = "back"
            if m.section <> 1
                m.menu.expanded = false
                showSection(1, true)
                return true
            end if
            return false   ' Atrás en el menú, ya en Inicio: se sale de la app
        end if
        return true
    end if
    if key = "left"
        openMenu()     ' ← desde la primera columna
        return true
    end if
    if key = "back"
        if m.pages.Count() > 0 then popPage() else openMenu()
        return true
    end if
    if key = "options"
        showToast("Actualizando la biblioteca…", true)
        loadLibrary()
        return true
    end if
    return false
end function

' ---------- el código para cambiar la configuración desde otro aparato ----------

sub setupCode()
    m.top.findNode("codeScrim").color = m.t.scrim
    m.top.findNode("codeBg").color = m.t.raise2
    value = m.top.findNode("codeValue")
    value.font = makeFont(110, "black")
    value.color = m.t.lime
    note = m.top.findNode("codeNote")
    note.font = makeFont(38)
    note.color = m.t.text
    hint = m.top.findNode("codeHint")
    hint.font = makeFont(27)
    hint.color = m.t.muted
end sub

' Lo pide la web (el asistente, desde otro aparato): el código grande, encima de todo, con el foco para que OK o Atrás
' lo quiten. Solo seis cifras; otra cosa no se muestra.
sub showCode(code as Dynamic)
    if code = invalid then return
    code = code.ToStr()
    if not CreateObject("roRegex", "^[0-9]{6}$", "").IsMatch(code) then return
    m.top.findNode("codeValue").text = Left(code, 3) + " " + Mid(code, 4)
    m.player.covered = true   ' el reproductor no toma el foco ni ofrece «saltar intro» mientras se ve
    m.code.visible = true
    m.code.setFocus(true)
    m.codeTimer.control = "stop"
    m.codeTimer.control = "start"
end sub

' Se quita (solo, o con OK o Atrás) y el foco vuelve a lo que se veía.
sub hideCode()
    if not m.code.visible then return
    hadFocus = m.code.hasFocus()
    m.code.visible = false
    m.codeTimer.control = "stop"
    if not m.picker.visible then m.player.covered = false
    if not hadFocus then return   ' algo más ya tomó el foco
    if m.picker.visible
        m.picker.setFocus(true)
    else if m.player.visible
        m.player.refocus = true
    else if m.mosaic.visible
        m.mosaic.refocus = true
    else if m.detail.visible
        m.detail.setFocus(true)
    else if m.help.visible
        m.help.setFocus(true)
    else if m.menu.expanded
        m.menu.setFocus(true)
    else
        focusContent()
    end if
end sub

' ---------- avisos breves ----------

sub showToast(text as String, autoHide as Boolean)
    showToastTone(text, autoHide, "ok")
end sub

' Aviso breve sobre una barra gris; los problemas, en guinda claro.
sub showToastTone(text as String, autoHide as Boolean, tone as String)
    m.toastText.text = text
    m.toastText.width = 0
    w = m.toastText.boundingRect().width
    if w > 1560 then w = 1560
    m.toastText.width = w + 2
    m.top.findNode("toastBg").width = w + 56
    if tone = "error" then m.toastText.color = m.t.guindaLight else m.toastText.color = m.t.text
    m.toast.visible = true
    if autoHide then m.toastTimer.control = "start" else m.toastTimer.control = "stop"
end sub

sub hideToast()
    m.toast.visible = false
end sub

' ---------- hablar con la Mac ----------

sub apiGet(path as String, callback as String)
    task = CreateObject("roSGNode", "ApiTask")
    task.url = m.server + path
    if callback <> "" then task.observeField("done", callback)
    task.control = "RUN"
    keepTask(task)
end sub

' POST con JSON; siempre lleva el id de este dispositivo.
sub post(path as String, body as Object, callback as String)
    body["device_id"] = m.deviceId
    task = CreateObject("roSGNode", "ApiTask")
    task.url = m.server + path
    task.body = FormatJson(body)
    if callback <> "" then task.observeField("done", callback)
    task.control = "RUN"
    keepTask(task)
end sub

' Se guarda la referencia hasta que termine (si no, la tarea puede desaparecer antes).
sub keepTask(task as Object)
    m.tasks.Push(task)
    if m.tasks.Count() > 16 then m.tasks.Shift()
end sub
