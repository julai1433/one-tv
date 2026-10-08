' Tu música en la TV (la de la computadora, mac/music.py): la sección «Música» con tus listas, lo agregado hace poco,
' los artistas y los álbumes; la página de un álbum, una lista o un artista con sus canciones; y escuchar: suena una
' canción con su portada en pantalla y siguen solas las demás de donde se eligió (‹ › anterior y siguiente).
' Llega por partes (con una biblioteca grande, todo junto serían ~25 MB y el Roku no puede leer eso): lo de la sección
' (/api/music/home), más artistas, álbumes o listas al acercarse al final de su fila (/api/music/more), cada página al
' abrirla con sus canciones por tandas al bajar (/api/music/page) y, para escuchar algo enorme de seguido o al azar,
' hasta 500 que arma la computadora (/api/music/mix).
' Estado: m.music (la sección), m.musicTracks (id -> canción ya traída), m.musicPages ("album:<id>" -> {kind, id,
' title, total, ids, loading, error}), m.musicLists (las canciones de cada fila o página, para saber qué sigue) y
' m.musicCtx (lo que suena: {tracks, index}).

sub loadMusic()
    apiGet("/api/music/home", "onMusic")
end sub

' Un pedido de música que recuerda para qué era (la fila o la página): task.musicKey.
sub musicGet(path as String, callback as String, key as String)
    task = CreateObject("roSGNode", "ApiTask")
    task.addFields({musicKey: key})
    task.url = m.server + path
    task.observeField("done", callback)
    task.control = "RUN"
    keepTask(task)
end sub

' Guarda las canciones que llegan (para escucharlas y saber qué sigue). -> sus ids
function keepSongs(list as Dynamic) as Object
    if m.musicTracks = invalid then m.musicTracks = {}
    ids = []
    if list = invalid then return ids
    for each t in list
        m.musicTracks[t.id] = t
        ids.Push(t.id)
    end for
    return ids
end function

sub onMusic(event as Object)
    task = event.getRoSGNode()
    r = task.result
    if task.error <> "" or r = invalid or r.ok <> true or r.counts = invalid
        if m.music = invalid then m.music = {error: true}
    else
        keepSongs(r.recent)
        old = m.music
        if old <> invalid and old.counts <> invalid and sameCounts(old.counts, r.counts)
            for each k in ["artists", "albums", "playlists"]   ' la misma música: lo traído de más sigue
                if old[k] <> invalid and old[k].Count() > r[k].Count() then r[k] = old[k]
            end for
        else
            m.musicPages = {}
        end if
        m.music = r
    end if
    if sectionNames()[m.section] = "music" and m.pages.Count() = 0 then renderSection()
end sub

function sameCounts(a as Object, b as Object) as Boolean
    return a.artists = b.artists and a.albums = b.albums and a.tracks = b.tracks and a.playlists = b.playlists
end function

function musicTrack(tid as String) as Dynamic
    if m.musicTracks = invalid then return invalid
    return m.musicTracks[tid]
end function

function musicReady() as Boolean
    return m.music <> invalid and m.music.counts <> invalid and m.music.counts.albums > 0
end function

' ---------- la sección ----------

sub buildMusic()
    root = CreateObject("roSGNode", "ContentNode")
    m.musicLists = {}
    if m.music = invalid
        row = newRow(root, "Música", "square")
        emptyRow(row, "Leyendo tu música", "La computadora está revisando la carpeta de música.", "", "")
        loadMusic()
    else if not musicReady()
        row = newRow(root, "Música", "square")
        if m.music.reading = true   ' la primera vez con mucha música: se vuelve a preguntar al volver a la sección
            emptyRow(row, "Leyendo tu música", "La primera vez, con mucha música, la computadora tarda unos minutos.", "", "")
            loadMusic()
        else
            cause = "Pon tu música en la carpeta Música › Biblioteca de la computadora y aparece aquí sola, con sus portadas."
            if m.music.error = true then cause = "No se pudo leer: sin conexión con la computadora."
            emptyRow(row, "Sin música todavía", cause, "", "")
        end if
    else
        if m.music.playlists.Count() > 0
            row = newRow(root, "Tus listas", "square")
            row.addFields({more: "playlists"})
            for each p in m.music.playlists
                addListTile(row, p)
            end for
        end if
        recent = []
        for each t in m.music.recent
            recent.Push(t.id)
        end for
        m.musicLists["recent"] = recent
        row = newRow(root, "Agregadas hace poco", "square")
        for i = 0 to recent.Count() - 1
            addSongTile(row, "recent", i)
        end for
        row = newRow(root, "Artistas", "channel")
        row.addFields({more: "artists"})
        for each ar in m.music.artists
            addArtistTile(row, ar)
        end for
        row = newRow(root, "Álbumes", "square")
        row.addFields({more: "albums"})
        for each a in m.music.albums
            addAlbumTile(row, a)
        end for
    end if
    m.rows.header = "Música"
    m.rows.topButton = ""
    m.rows.content = root
end sub

sub addListTile(row as Object, p as Object)
    tile = newTile(row, "mlist:" + p.id, "video", "square", true)
    tile.title = p.title
    tile.line2 = countText(toInt(p.count), "canción", "canciones")
    tile.HDPosterUrl = m.server + p.art
    tile.info = p.title + "   ·   " + tile.line2 + "   ·   OK: ver sus canciones   ·   Reproducir: escucharla"
end sub

sub addArtistTile(row as Object, ar as Object)
    tile = newTile(row, "artist:" + ar.id, "channel", "channel", true)
    tile.title = ar.name
    tile.initials = initialsOf(ar.name)
    tile.addFields({avatar: m.server + ar.art})
    tile.info = ar.name + "   ·   " + countText(toInt(ar.count), "álbum", "álbumes") + "   ·   OK: sus canciones"
end sub

sub addAlbumTile(row as Object, a as Object)
    tile = newTile(row, "album:" + a.id, "video", "square", true)
    tile.title = a.title
    tile.line2 = a.artist
    tile.HDPosterUrl = m.server + a.art
    info = a.title + "   ·   " + a.artist
    if a.year <> invalid and a.year > 0 then info = info + "   ·   " + a.year.ToStr()
    tile.info = info + "   ·   OK: ver sus canciones   ·   Reproducir: escucharlo"
end sub

sub addSongTile(row as Object, ctx as String, i as Integer)
    t = musicTrack(m.musicLists[ctx][i])
    if t = invalid then return
    tile = newTile(row, "song:" + ctx + ":" + i.ToStr(), "video", row.shape, ctx <> "page")
    tile.title = t.title
    tile.line2 = t.artist
    tile.HDPosterUrl = m.server + t.art
    tile.dur = toInt(t.duration)
    tile.info = t.title + "   ·   " + t.artist + "   ·   " + t.album + "   ·   *: opciones"
end sub

' El foco se movió en la sección (MainScene observa m.rows.focus): cerca del final de una fila que tiene más, la
' tanda que sigue se agrega a la misma fila (sin moverse de lugar).
sub onMusicRowsFocus()
    if sectionNames()[m.section] <> "music" or m.pages.Count() > 0 or not musicReady() then return
    f = m.rows.focus
    root = m.rows.content
    if f = invalid or f.Count() < 2 or root = invalid or f[0] >= root.getChildCount() then return
    row = root.getChild(f[0])
    if row.hasField("more") and f[1] >= row.getChildCount() - 12 then moreMusic(row.more)
end sub

sub moreMusic(kind as String)
    if m.musicMoreBusy = invalid then m.musicMoreBusy = {}
    have = m.music[kind]
    if have = invalid or m.musicMoreBusy[kind] = true or have.Count() >= toInt(m.music.counts[kind]) then return
    m.musicMoreBusy[kind] = true
    musicGet("/api/music/more?kind=" + kind + "&offset=" + have.Count().ToStr() + "&limit=60", "onMusicMore", kind)
end sub

sub onMusicMore(event as Object)
    task = event.getRoSGNode()
    kind = task.musicKey
    m.musicMoreBusy[kind] = false
    r = task.result
    if task.error <> "" or r = invalid or r.ok <> true or m.music = invalid or r.items = invalid then return
    have = m.music[kind]
    if have = invalid or toInt(r.offset) <> have.Count() then return
    row = invalid   ' la fila que se ve, si se ve
    if sectionNames()[m.section] = "music" and m.rows.content <> invalid
        root = m.rows.content
        for i = 0 to root.getChildCount() - 1
            c = root.getChild(i)
            if c.hasField("more") and c.more = kind then row = c
        end for
    end if
    for each x in r.items
        have.Push(x)
        if row <> invalid
            if kind = "artists"
                addArtistTile(row, x)
            else if kind = "albums"
                addAlbumTile(row, x)
            else
                addListTile(row, x)
            end if
        end if
    end for
end sub

' ---------- página de un álbum, una lista o un artista ----------

sub buildMusicPage(page as Object)
    m.pageGrid.shape = "gridSquare"
    m.pageGrid.controlStyle = "big"
    m.pageGrid.controlPrimary = true
    m.pageGrid.header = page.title
    if m.musicPages = invalid then m.musicPages = {}
    key = page.sub + ":" + page.id
    if m.musicPages[key] = invalid then loadMusicPage(page.sub, page.id)
    pg = m.musicPages[key]
    m.musicPageRoot = invalid
    if pg.error <> "" or pg.ids.Count() = 0
        m.pageGrid.controls = []
        m.pageGrid.count = ""
        if pg.error = "conexion"
            m.pageGrid.emptySpec = {phrase: "Sin canciones", cause: "No se pudo leer: sin conexión con la computadora."}
            m.musicPages.Delete(key)   ' la próxima vez que se abra, se intenta otra vez
        else if pg.error <> ""
            m.pageGrid.emptySpec = {phrase: "Sin canciones", cause: "Se movieron o se borraron de la carpeta de música."}
        else
            m.pageGrid.emptySpec = {phrase: "Leyendo tu música", cause: "Un momento."}
        end if
        m.pageGrid.content = CreateObject("roSGNode", "ContentNode")
        return
    end if
    if page.title = "" then m.pageGrid.header = pg.title
    m.musicLists["page"] = pg.ids
    m.pageGrid.count = countText(pg.total, "canción", "canciones")
    m.pageGrid.controls = [{id: "m-play", text: "Escuchar", icon: "play"}, {id: "m-shuffle", text: "Aleatorio", icon: "shuffle"},
                           {id: "m-queue", text: "A la fila", icon: "list-plus"}]
    root = CreateObject("roSGNode", "ContentNode")
    root.addFields({shape: "gridSquare"})
    for i = 0 to pg.ids.Count() - 1
        addSongTile(root, "page", i)
    end for
    m.pageGrid.emptySpec = {phrase: "Sin canciones", cause: "Se movieron o se borraron de la carpeta de música."}
    m.pageGrid.content = root
    m.musicPageRoot = root   ' las canciones que lleguen después se le agregan (sin mover el foco)
end sub

' La primera tanda de canciones de una página, o la que sigue (si quedan y no se está pidiendo ya).
sub loadMusicPage(kind as String, id as String)
    if m.musicPages = invalid then m.musicPages = {}
    key = kind + ":" + id
    pg = m.musicPages[key]
    if pg = invalid
        pg = {kind: kind, id: id, title: "", total: 0, ids: [], loading: false, error: ""}
        m.musicPages[key] = pg
    end if
    if pg.loading or pg.error <> "" or (pg.total > 0 and pg.ids.Count() >= pg.total) then return
    pg.loading = true
    musicGet("/api/music/page?kind=" + kind + "&id=" + id + "&offset=" + pg.ids.Count().ToStr(), "onMusicPage", key)
end sub

sub onMusicPage(event as Object)
    task = event.getRoSGNode()
    key = task.musicKey
    pg = invalid
    if m.musicPages <> invalid then pg = m.musicPages[key]
    if pg = invalid then return
    pg.loading = false
    r = task.result
    top = topPage()
    showing = top <> invalid and top.kind = "music" and top.sub + ":" + top.id = key
    if task.error <> "" or r = invalid
        if pg.ids.Count() = 0 then pg.error = "conexion"
    else if r.ok <> true
        pg.error = "gone"
    else if toInt(r.offset) = pg.ids.Count()
        first = pg.ids.Count() = 0
        pg.total = toInt(r.total)
        pg.title = r.title
        fresh = keepSongs(r.tracks)
        if not first and showing and m.musicPageRoot <> invalid
            for each tid in fresh
                pg.ids.Push(tid)
                addSongTile(m.musicPageRoot, "page", pg.ids.Count() - 1)
            end for
            return
        end if
        pg.ids.Append(fresh)
    end if
    if showing then renderPage(top)
end sub

' El foco se movió en la página (MainScene observa m.pageGrid.focusIndex): cerca del final, las canciones que siguen.
sub onMusicGridFocus()
    top = topPage()
    if top = invalid or top.kind <> "music" or m.musicPages = invalid then return
    pg = m.musicPages[top.sub + ":" + top.id]
    if pg = invalid or pg.ids.Count() = 0 then return
    if m.pageGrid.focusIndex >= pg.ids.Count() - 32 then loadMusicPage(top.sub, top.id)
end sub

' OK en la sección o en una página: una canción suena (y siguen las de su fila); lo demás abre su página.
' quick = ▶: escuchar ya (un álbum o una lista entera).
function activateMusic(id as String, quick as Boolean) as Boolean
    if Left(id, 5) = "song:"
        parts = id.Split(":")
        if parts.Count() < 3 then return true
        ctx = parts[1]
        if m.musicLists[ctx] = invalid then return true
        top = topPage()
        if ctx = "page" and top <> invalid and top.kind = "music"
            playCollection(top.sub, top.id, toInt(parts[2]), false)   ' si es enorme, siguen las que mande la computadora
        else
            playMusicList(m.musicLists[ctx], toInt(parts[2]), false)
        end if
        return true
    end if
    kinds = {album: "album", mlist: "list", artist: "artist"}
    prefix = Left(id, Instr(1, id, ":") - 1)
    if kinds[prefix] = invalid then return false
    rest = Mid(id, Len(prefix) + 2)
    page = {kind: "music", sub: kinds[prefix], id: rest, title: tileTitle(id)}
    if quick
        playCollection(page.sub, page.id, 0, false)
    else
        pushPage(page)
    end if
    return true
end function

sub musicPageControl(page as Object, id as String)
    pg = invalid
    if m.musicPages <> invalid then pg = m.musicPages[page.sub + ":" + page.id]
    if pg = invalid or pg.total = 0 then return
    if id = "m-play"
        playCollection(page.sub, page.id, 0, false)
    else if id = "m-shuffle"
        playCollection(page.sub, page.id, Rnd(pg.total) - 1, true)
    else if id = "m-queue"   ' la computadora la arma (hasta 500): no se mandan las canciones
        post("/api/queue/add_tracks", {kind: page.sub, id: page.id}, "onTracksQueued")
    end if
end sub

sub onTracksQueued(event as Object)
    task = event.getRoSGNode()
    r = task.result
    if task.error <> "" or r = invalid or r.ok <> true
        showToastTone(channelFailText("agregarlas a la fila", task), true, "error")
        return
    end if
    showToast("A la fila: " + countText(toInt(r.added), "canción", "canciones") + ".", true)
    loadLibrary()
end sub

' ---------- escuchar ----------

' Un álbum, un artista o una lista desde la canción index (o al azar): si ya están todas aquí, como siempre; si no
' (algo enorme), la computadora manda hasta 500 desde esa.
sub playCollection(kind as String, id as String, index as Integer, shuffle as Boolean)
    pg = invalid
    if m.musicPages <> invalid then pg = m.musicPages[kind + ":" + id]
    if pg <> invalid and pg.total > 0 and pg.ids.Count() >= pg.total
        playMusicList(pg.ids, index, shuffle)
        return
    end if
    path = "/api/music/mix?kind=" + kind + "&id=" + id + "&index=" + index.ToStr()
    if shuffle then path = path + "&shuffle=1"
    apiGet(path, "onMusicMix")
end sub

sub onMusicMix(event as Object)
    task = event.getRoSGNode()
    r = task.result
    if task.error <> "" or r = invalid or r.ok <> true or r.tracks = invalid or r.tracks.Count() = 0
        showToastTone("No se pudo escuchar: la computadora no mandó las canciones.", true, "error")
        return
    end if
    keepSongs(r.tracks)
    playMusicCtx(r.tracks, toInt(r.index), 0)
end sub

' Una canción de la fila que no está aquí todavía: se pide por su id.
sub loadMusicTrack(tid as String)
    apiGet("/api/music/tracks?ids=" + tid, "onMusicTrack")
end sub

sub onMusicTrack(event as Object)
    task = event.getRoSGNode()
    r = task.result
    if task.error <> "" or r = invalid or r.tracks = invalid or r.tracks.Count() = 0
        showToastTone("Esa canción ya no está en tu música.", true, "error")
        return
    end if
    keepSongs(r.tracks)
    playMusicCtx([r.tracks[0]], 0, 0)
end sub

' ids: canciones (ids); index: la que suena primero; shuffle: las demás al azar.
sub playMusicList(ids as Object, index as Integer, shuffle as Boolean)
    tracks = []
    for each tid in ids
        t = musicTrack(tid)
        if t <> invalid then tracks.Push(t)
    end for
    if tracks.Count() = 0 then return
    if index < 0 or index >= tracks.Count() then index = 0
    if shuffle
        first = tracks[index]
        rest = []
        for i = 0 to tracks.Count() - 1
            if i <> index then rest.Push(tracks[i])
        end for
        for i = rest.Count() - 1 to 1 step -1   ' Fisher–Yates
            j = Rnd(i + 1) - 1
            tmp = rest[i]
            rest[i] = rest[j]
            rest[j] = tmp
        end for
        tracks = [first]
        tracks.Append(rest)
        index = 0
    end if
    playMusicCtx(tracks, index, 0)
end sub

' startAt: el segundo donde empieza la primera (cuando se manda desde la web, sigue donde iba ahí).
sub playMusicCtx(tracks as Object, index as Integer, startAt as Integer)
    m.musicCtx = {tracks: tracks, index: index}
    t = tracks[index]
    m.cur = {id: "track:" + t.id, music: true, audio: 0, sub: -1,
             item: {full_title: t.title, subs: [], audio: [], direct: invalid, duration: t.duration, audio_default: 0}}
    format = "mp4"
    if t.format <> invalid and t.format <> "" then format = t.format
    nextTitle = ""
    if index + 1 < tracks.Count() then nextTitle = tracks[index + 1].title + " · " + tracks[index + 1].artist
    startPlayer({id: "track:" + t.id, title: t.title, url: m.server + t.url, format: format, music: true,
                 artist: t.artist, album: t.album, art: m.server + t.art, report: true, duration: t.duration, startAt: startAt,
                 songIndex: index, songCount: tracks.Count(), last: index + 1 >= tracks.Count(),
                 audio: 0, sub: -1, audioTrack: -1, subtitle: "", position: (index + 1).ToStr() + " de " + tracks.Count().ToStr(),
                 nextTitle: nextTitle})
end sub

' ‹ › en el reproductor (o lo que terminó): la anterior o la siguiente. -> false si no hay.
function musicStep(dir as Integer) as Boolean
    c = m.musicCtx
    if c = invalid then return false
    j = c.index + dir
    if j < 0 or j >= c.tracks.Count() then return false
    playMusicCtx(c.tracks, j, 0)
    return true
end function

' Lo que se mandó desde la web o el teléfono («Escuchar en la TV»).
sub onMusicSession(event as Object)
    task = event.getRoSGNode()
    r = task.result
    if task.error <> "" or r = invalid or r.ok <> true or r.tracks = invalid or r.tracks.Count() = 0
        showToastTone("No se pudo escuchar en la TV: la computadora no mandó las canciones.", true, "error")
        return
    end if
    keepSongs(r.tracks)
    playMusicCtx(r.tracks, toInt(r.index), toInt(r.start))
end sub
