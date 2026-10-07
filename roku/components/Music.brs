' Tu música en la TV (la de la computadora, mac/music.py): la sección «Música» con tus listas, lo agregado hace poco,
' los artistas y los álbumes; la página de un álbum, una lista o un artista con sus canciones; y escuchar: suena una
' canción con su portada en pantalla y siguen solas las demás de donde se eligió (‹ › anterior y siguiente).
' Todo el estado vive en m.music (lo que manda /api/music), m.musicLists (las canciones de cada fila o página, para
' saber qué sigue) y m.musicCtx (lo que suena: {tracks, index}).

sub loadMusic()
    apiGet("/api/music", "onMusic")
end sub

sub onMusic(event as Object)
    task = event.getRoSGNode()
    r = task.result
    if task.error <> "" or r = invalid or r.ok <> true
        if m.music = invalid then m.music = {error: true}
    else
        m.music = r
    end if
    if sectionNames()[m.section] = "music" and m.pages.Count() = 0 then renderSection()
    top = topPage()
    if top <> invalid and top.kind = "music" then renderPage(top)
    if m.musicWant <> invalid
        want = m.musicWant
        m.musicWant = invalid
        playEntry(want)
    end if
end sub

function musicTrack(tid as String) as Dynamic
    if m.music = invalid or m.music.tracks = invalid then return invalid
    return m.music.tracks[tid]
end function

function musicReady() as Boolean
    return m.music <> invalid and m.music.albums <> invalid and m.music.albums.Count() > 0
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
        cause = "Pon tu música en la carpeta Música › Biblioteca de la computadora y aparece aquí sola, con sus portadas."
        if m.music.error = true then cause = "No se pudo leer: sin conexión con la computadora."
        emptyRow(row, "Sin música todavía", cause, "", "")
    else
        if m.music.playlists.Count() > 0
            row = newRow(root, "Tus listas", "square")
            for each p in m.music.playlists
                tile = newTile(row, "mlist:" + p.id, "video", "square", true)
                tile.title = p.title
                tile.line2 = countText(p.tracks.Count(), "canción", "canciones")
                tile.HDPosterUrl = m.server + p.art
                tile.info = p.title + "   ·   " + tile.line2 + "   ·   OK: ver sus canciones   ·   Reproducir: escucharla"
            end for
        end if
        recent = recentSongs(30)
        m.musicLists["recent"] = recent
        row = newRow(root, "Agregadas hace poco", "square")
        for i = 0 to recent.Count() - 1
            addSongTile(row, "recent", i)
        end for
        row = newRow(root, "Artistas", "channel")
        for each ar in m.music.artists
            tile = newTile(row, "artist:" + ar.id, "channel", "channel", true)
            tile.title = ar.name
            tile.initials = initialsOf(ar.name)
            tile.addFields({avatar: m.server + ar.art})
            tile.info = ar.name + "   ·   " + countText(ar.albums.Count(), "álbum", "álbumes") + "   ·   OK: sus canciones"
        end for
        row = newRow(root, "Álbumes", "square")
        for each a in m.music.albums
            tile = newTile(row, "album:" + a.id, "video", "square", true)
            tile.title = a.title
            tile.line2 = a.artist
            tile.HDPosterUrl = m.server + a.art
            info = a.title + "   ·   " + a.artist
            if a.year <> invalid and a.year > 0 then info = info + "   ·   " + a.year.ToStr()
            tile.info = info + "   ·   OK: ver sus canciones   ·   Reproducir: escucharlo"
        end for
    end if
    m.rows.header = "Música"
    m.rows.topButton = ""
    m.rows.content = root
end sub

' Las canciones de los álbumes más nuevos primero (cada álbum en su orden).
function recentSongs(n as Integer) as Object
    albums = []
    for each a in m.music.albums
        albums.Push(a)
    end for
    albums.SortBy("added", "r")
    out = []
    for each a in albums
        for each t in a.tracks
            if out.Count() >= n then return out
            out.Push(t)
        end for
    end for
    return out
end function

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

' ---------- página de un álbum, una lista o un artista ----------

sub buildMusicPage(page as Object)
    m.pageGrid.shape = "gridSquare"
    m.pageGrid.controlStyle = "big"
    m.pageGrid.controlPrimary = true
    if not musicReady()
        m.pageGrid.header = page.title
        m.pageGrid.controls = []
        m.pageGrid.emptySpec = {phrase: "Leyendo tu música", cause: "Un momento."}
        m.pageGrid.content = CreateObject("roSGNode", "ContentNode")
        return
    end if
    ids = musicPageTracks(page)
    m.musicLists["page"] = ids
    m.pageGrid.header = page.title
    m.pageGrid.count = countText(ids.Count(), "canción", "canciones")
    m.pageGrid.controls = [{id: "m-play", text: "Escuchar", icon: "play"}, {id: "m-shuffle", text: "Aleatorio", icon: "shuffle"},
                           {id: "m-queue", text: "A la fila", icon: "list-plus"}]
    root = CreateObject("roSGNode", "ContentNode")
    root.addFields({shape: "gridSquare"})
    for i = 0 to ids.Count() - 1
        addSongTile(root, "page", i)
    end for
    m.pageGrid.emptySpec = {phrase: "Sin canciones", cause: "Se movieron o se borraron de la carpeta de música."}
    m.pageGrid.content = root
end sub

function musicPageTracks(page as Object) as Object
    if page.sub = "album"
        for each a in m.music.albums
            if a.id = page.id then return a.tracks
        end for
    else if page.sub = "list"
        for each p in m.music.playlists
            if p.id = page.id then return p.tracks
        end for
    else if page.sub = "artist"
        ids = []
        for each ar in m.music.artists
            if ar.id = page.id
                for each aid in ar.albums
                    for each a in m.music.albums
                        if a.id = aid then ids.Append(a.tracks)
                    end for
                end for
            end if
        end for
        return ids
    end if
    return []
end function

' OK en la sección o en una página: una canción suena (y siguen las de su fila); lo demás abre su página.
' quick = ▶: escuchar ya (un álbum o una lista entera).
function activateMusic(id as String, quick as Boolean) as Boolean
    if Left(id, 5) = "song:"
        parts = id.Split(":")
        if parts.Count() < 3 then return true
        ctx = parts[1]
        if m.musicLists[ctx] = invalid then return true
        playMusicList(m.musicLists[ctx], toInt(parts[2]), false)
        return true
    end if
    kinds = {album: "album", mlist: "list", artist: "artist"}
    prefix = Left(id, Instr(1, id, ":") - 1)
    if kinds[prefix] = invalid then return false
    rest = Mid(id, Len(prefix) + 2)
    page = {kind: "music", sub: kinds[prefix], id: rest, title: tileTitle(id)}
    if quick
        ids = musicPageTracks(page)
        if ids.Count() > 0 then playMusicList(ids, 0, false)
    else
        pushPage(page)
    end if
    return true
end function

sub musicPageControl(page as Object, id as String)
    ids = musicPageTracks(page)
    if ids.Count() = 0 then return
    if id = "m-play"
        playMusicList(ids, 0, false)
    else if id = "m-shuffle"
        playMusicList(ids, Rnd(ids.Count()) - 1, true)
    else if id = "m-queue"
        post("/api/queue/add_tracks", {tracks: ids}, "onTracksQueued")
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
                 artist: t.artist, album: t.album, art: m.server + t.art, report: false, duration: t.duration, startAt: startAt,
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
    playMusicCtx(r.tracks, toInt(r.index), toInt(r.start))
end sub
