' Reproductor. La escena manda qué reproducir (request); aquí se reproduce, se reporta el avance a la Mac, se
' ofrece saltar (marcas de /api/marks) y se muestra la cuenta atrás de lo siguiente.
sub init()
    m.t = theme()
    m.video = m.top.findNode("video")
    m.notice = m.top.findNode("notice")
    m.noticeText = m.top.findNode("noticeText")
    m.drain = m.top.findNode("drain")
    m.upNextGroup = m.top.findNode("upNextGroup")
    m.upNextTimer = m.top.findNode("upNextTimer")
    m.stallTimer = m.top.findNode("stallTimer")
    m.endTimer = m.top.findNode("endTimer")
    m.endAt = -1
    m.statusNote = m.top.findNode("statusNote")
    m.multiHint = m.top.findNode("multiHint")
    m.checkTask = invalid
    m.pendingContent = invalid
    m.tick = m.top.findNode("tickTimer")
    m.req = invalid
    m.marks = []
    m.markIndex = -1
    m.posts = []
    m.startedPlaying = false
    m.pauseAfterSeek = false
    m.finished = false
    m.subUrl = ""
    m.upNextLeft = 0
    m.appPaused = false      ' pausa hecha por la app desde el aviso (ver noticeKey)
    m.chapters = []          ' capítulos del video de YouTube: [{start, end, title}]
    m.chapterIndex = -1

    ' Aviso para saltar: panel negro al 92 %, borde limón, tecla OK dibujada y la línea que se vacía.
    m.top.findNode("noticeBg").color = m.t.overlay
    m.top.findNode("noticeEdge").blendColor = m.t.lime
    m.top.findNode("okEdge").blendColor = m.t.lime
    ok = m.top.findNode("okText")
    ok.font = makeFont(27, "bold")
    ok.color = m.t.lime
    m.noticeText.font = makeFont(48, "display")
    m.noticeText.color = m.t.text
    m.top.findNode("noticeIcon").blendColor = m.t.text
    m.drain.color = m.t.lime

    ' Lo siguiente: qué viene, el título, los segundos que faltan y la línea que se vacía.
    m.top.findNode("upNextBg").color = m.t.bg
    m.top.findNode("upNextFallback").color = m.t.raise3
    fallback = m.top.findNode("upNextFallbackTitle")
    fallback.font = makeFont(72, "black")
    fallback.color = m.t.textSoft
    what = m.top.findNode("upNextWhat")
    what.font = makeFont(48, "display")
    what.color = m.t.muted
    title = m.top.findNode("upNextTitle")
    title.font = makeFont(38, "bold")
    title.color = m.t.text
    count = m.top.findNode("upNextCount")
    count.font = makeFont(110, "black")
    count.color = m.t.text
    unit = m.top.findNode("upNextUnit")
    unit.font = makeFont(32)
    unit.color = m.t.muted
    m.top.findNode("upNextTrack").color = m.t.raise3
    m.top.findNode("upNextDrain").color = m.t.lime
    m.upNextAnim = m.top.findNode("upNextAnim")
    m.top.findNode("upNextPoster").observeField("loadStatus", "onUpNextPoster")

    ' Capítulos de YouTube: nombre al empezar y marcas en pausa.
    m.chapterNote = m.top.findNode("chapterNote")
    m.top.findNode("chapterNoteBg").color = m.t.overlay
    head = m.top.findNode("chapterNoteHead")
    head.font = makeFont(27, "bold")
    head.color = m.t.muted
    note = m.top.findNode("chapterNoteTitle")
    note.font = makeFont(38, "bold")
    note.color = m.t.text
    m.chapterTimer = m.top.findNode("chapterTimer")
    m.chapterTimer.observeField("fire", "hideChapterNote")

    ' Varios a la vez: «Armando…» mientras la computadora arma el mosaico (ver onNote).
    m.buildNote = m.top.findNode("buildNote")
    m.top.findNode("buildNoteBg").color = m.t.overlay
    head = m.top.findNode("buildNoteHead")
    head.font = makeFont(27, "bold")
    head.color = m.t.lime
    note = m.top.findNode("buildNoteText")
    note.font = makeFont(32)
    note.color = m.t.text
    m.buildNoteTimer = m.top.findNode("buildNoteTimer")
    m.buildNoteTimer.observeField("fire", "hideBuildNote")

    ' La barra de avance de la app y el panel (las teclas son de la app: ver onKeyEvent).
    m.osd = m.top.findNode("osd")
    m.top.findNode("osdShade").blendColor = m.t.bg   ' el degradado es blanco: se tiñe de negro
    m.osdTitle = m.top.findNode("osdTitle")
    m.osdTitle.font = makeFont(38, "bold")
    m.osdTitle.color = m.t.text
    m.osdChapter = m.top.findNode("osdChapter")
    m.osdChapter.font = makeFont(32, "bold")
    m.osdChapter.color = m.t.lime
    m.osdTime = m.top.findNode("osdTime")
    m.osdTime.font = makeFont(32)
    m.osdTime.color = m.t.text
    m.top.findNode("osdTrack").color = m.t.raise3
    m.osdFill = m.top.findNode("osdFill")
    m.osdFill.color = m.t.lime
    m.osdTicks = m.top.findNode("osdTicks")
    m.osdHint = m.top.findNode("osdHint")
    m.osdHint.font = makeFont(24)
    m.osdHint.color = m.t.muted
    m.osdPlay = m.top.findNode("osdPlay")
    m.osdPlay.blendColor = m.t.text
    m.osdKnob = m.top.findNode("osdKnob")
    m.osdKnob.blendColor = m.t.lime
    m.ui = "none"            ' lo que hay encima del video: none | bar (la barra de avance) | panel
    m.panelTimer = m.top.findNode("panelTimer")
    m.panelTimer.observeField("fire", "onPanelTimer")
    m.stepAt = 0             ' ◀ ▶ seguidas sin capítulos: cada vez saltan más (10, 20, 30… hasta 60 s)
    m.stepClock = CreateObject("roTimespan")
    m.osdTimer = m.top.findNode("osdTimer")
    m.osdTimer.observeField("fire", "onOsdTimer")
    m.seekTimer = m.top.findNode("seekTimer")
    m.seekTimer.observeField("fire", "doSeek")
    m.seekTarget = -1      ' a dónde se va (se acumulan las teclas seguidas; se salta al soltar un momento)
    m.ticksFor = -1
    m.panel = m.top.findNode("panel")
    m.panel.observeField("event", "onPanelEvent")
    m.panel.observeField("touched", "onPanelTouched")
    m.dubs = []            ' doblajes de YouTube que se pueden pedir: [{lang, name}]
    ' Escuchando música (request.music): la portada y los datos de la canción.
    m.musicView = m.top.findNode("musicView")
    m.top.findNode("musicBg").color = m.t.bg
    kicker = m.top.findNode("musicKicker")
    kicker.font = makeFont(27, "bold")
    kicker.color = m.t.lime
    title = m.top.findNode("musicTitle")
    title.font = makeFont(72, "display")
    title.color = m.t.text
    artist = m.top.findNode("musicArtist")
    artist.font = makeFont(38, "bold")
    artist.color = m.t.text
    album = m.top.findNode("musicAlbum")
    album.font = makeFont(32)
    album.color = m.t.textSoft
    nxt = m.top.findNode("musicNext")
    nxt.font = makeFont(27)
    nxt.color = m.t.muted
    m.video.enableTrickPlay = false

    m.video.notificationInterval = 0.5
    ' La barra de avance del propio reproductor del Roku, en limón.
    ' También las de «cargando» y «reanudando» que el Roku pone al empezar.
    for each bar in [m.video.trickPlayBar, m.video.bufferingBar, m.video.retrievingBar]
        if bar <> invalid and bar.hasField("filledBarBlendColor") then bar.filledBarBlendColor = m.t.lime
    end for
    m.video.observeField("state", "onVideoState")
    m.video.observeField("position", "onPosition")
    m.tick.observeField("fire", "onTick")
    m.upNextTimer.observeField("fire", "onUpNextTick")
    m.stallTimer.observeField("fire", "onStall")
    m.endTimer.observeField("fire", "onEndWatch")
    m.statusNote.font = makeFont(32)
    m.statusNote.color = m.t.muted
    note = m.top.findNode("upNextNote")
    note.font = makeFont(32, "bold")
    note.color = m.t.guindaLight

end sub

' ---------- empezar ----------

sub onRequest()
    r = m.top.request
    if r = invalid or r.url = invalid then return
    ' Si ya se veía otra cosa, se guarda dónde quedó.
    ' (De una canción a la siguiente no: la computadora entendería que se dejó de escuchar y quitaría el control de la web.)
    changing = m.req <> invalid and m.req.music = true and r.music = true
    if m.req <> invalid and m.top.visible and not m.finished and m.startedPlaying and not changing then report("stop", false)
    m.req = r
    m.finished = false
    m.endTimer.control = "stop"
    m.endAt = -1
    m.appPaused = false
    hideNotice()
    m.upNextTimer.control = "stop"
    m.upNextGroup.visible = false
    content = CreateObject("roSGNode", "ContentNode")
    content.title = r.title
    content.url = r.url
    content.streamFormat = r.format
    if r.live = true then content.Live = true
    startAt = 0
    if r.startAt <> invalid then startAt = Int(r.startAt)
    if startAt > 0 then content.PlayStart = startAt
    if r.subtitleTracks <> invalid then content.SubtitleTracks = r.subtitleTracks
    print "[cine] reproducir "; r.url; " desde "; startAt
    m.subUrl = ""
    if r.subtitle <> invalid then m.subUrl = r.subtitle
    m.top.trackInfo = {audio: r.audio, sub: r.sub}
    m.startAt = startAt
    m.stallTimer.control = "stop"
    ' YouTube: antes de dárselo al reproductor se pregunta a la computadora si el video existe. Si no, la TV
    ' se quedaría en negro reintentando varios minutos; así se avisa y sigue lo siguiente.
    if r.yt = true and r.checked <> true
        m.video.control = "stop"
        m.pendingContent = content
        m.top.visible = true
        m.top.setFocus(true)
        m.statusNote.text = "Cargando «" + r.title + "»…"
        m.statusNote.visible = true
        m.checkTask = CreateObject("roSGNode", "ApiTask")
        m.checkTask.url = m.top.server + "/api/yt/check?id=" + Mid(r.id, 4)
        m.checkTask.observeField("done", "onYtChecked")
        m.checkTask.control = "RUN"
        return
    end if
    startContent(content)
end sub

sub onYtChecked(event as Object)
    task = event.getRoSGNode()
    if m.checkTask = invalid or not task.isSameNode(m.checkTask) or m.pendingContent = invalid then return   ' ya se pidió otra cosa
    content = m.pendingContent
    m.pendingContent = invalid
    m.checkTask = invalid
    r = task.result
    if task.error = "" and r <> invalid and r.ok <> true
        reason = "no se pudo abrir en YouTube"
        if r.gone = true then reason = "ya no está disponible en YouTube"
        youTubeFailed(reason)
        return
    end if
    if task.error = "" and r <> invalid and r.live = true
        ' Transmisión de YouTube en vivo: como directo (sin barra de avance), desde lo más reciente.
        content.Live = true
        content.PlayStart = 0
        m.startAt = 0
        m.req.live = true
    end if
    startContent(content)   ' existe (o no se pudo preguntar: que lo intente el reproductor)
end sub

' Un video de YouTube que no se puede ver: se deja de intentar y la escena avisa y sigue con lo siguiente.
sub youTubeFailed(reason as String)
    m.stallTimer.control = "stop"
    m.statusNote.visible = false
    m.video.control = "stop"
    m.top.event = {type: "unavailable", title: m.req.title, reason: reason}
end sub

sub onStall()
    if m.req <> invalid and m.req.yt = true and not m.startedPlaying and m.top.visible then youTubeFailed("no respondió en YouTube")
end sub

sub startContent(content as Object)
    r = m.req
    startAt = m.startAt
    m.statusNote.visible = false
    m.video.content = content
    applyCaptions()
    m.top.visible = true
    m.top.setFocus(true)
    m.video.control = "play"
    if r.yt = true then m.stallTimer.control = "start"
    m.startedPlaying = false
    m.marks = []
    m.markIndex = -1
    m.chapters = []
    m.chapterIndex = -1
    m.dubs = []
    m.seekTarget = -1
    m.ticksFor = -1
    hideChapterNote()
    hideOsd()
    closePanel()
    showMusic(r)
    if r.music = true
        showOsd()   ' con música la barra se queda: no hay video que tapar
        ' La computadora se entera de qué suena (para su barra «En la TV» y su control), pero no guarda avance.
        report("start", false)
        m.tick.control = "start"
        return
    end if
    if r.live <> true then loadMarks(r.id)
    if r.yt = true then loadChapters(Mid(r.id, 4))
    if r.report = true
        report("start", false)
        m.tick.control = "start"
    end if
end sub

sub loadMarks(id as String)
    m.marksTask = CreateObject("roSGNode", "ApiTask")
    m.marksTask.url = m.top.server + "/api/marks?id=" + id
    m.marksTask.observeField("done", "onMarks")
    m.marksTask.control = "RUN"
end sub

sub onMarks()
    r = m.marksTask.result
    m.marks = []
    if m.marksTask.error <> "" or r = invalid or r.marks = invalid then return
    for each mk in r.marks
        ' El aviso para saltar es solo para la intro de las series; los capítulos de YouTube van aparte.
        if mk.kind <> "chapter" and mk.start <> invalid and mk.end <> invalid and mk.end > mk.start
            m.marks.Push({start: mk.start, finish: mk["end"], label: mk.label, state: "out", until: 0})
        end if
    end for
    print "[cine] marcas: "; m.marks.Count()
end sub

' ---------- capítulos de YouTube ----------

sub loadChapters(vid as String)
    m.chaptersTask = CreateObject("roSGNode", "ApiTask")
    m.chaptersTask.url = m.top.server + "/api/yt/info?id=" + vid
    m.chaptersTask.observeField("done", "onChapters")
    m.chaptersTask.control = "RUN"
end sub

sub onChapters()
    r = m.chaptersTask.result
    m.chapters = []
    if m.chaptersTask.error <> "" or r = invalid or r.chapters = invalid then return
    for each c in r.chapters
        if c.start <> invalid and c["end"] <> invalid and c["end"] > c.start
            title = c.title
            if title = invalid then title = ""
            m.chapters.Push({start: c.start, finish: c["end"], title: title})
        end if
    end for
    m.chapterDuration = 0
    if r.duration <> invalid then m.chapterDuration = r.duration
    if r.dubs <> invalid then m.dubs = r.dubs
    m.ticksFor = -1
    print "[cine] capítulos: "; m.chapters.Count()
end sub

function chapterAt(at as Float) as Integer
    for i = 0 to m.chapters.Count() - 1
        if at >= m.chapters[i].start and at < m.chapters[i].finish then return i
    end for
    return -1
end function

' ¿Mostrar el nombre del capítulo al empezar? Ajuste general (por omisión, sí).
function chapterTitlesOn() as Boolean
    r = m.req
    if r = invalid or r.chapterTitles = invalid then return true
    return r.chapterTitles = true
end function

' Al entrar a un capítulo (también al empezar o al saltar a otro): su nombre unos segundos.
sub trackChapter(at as Float)
    if m.chapters.Count() = 0 then return
    i = chapterAt(at)
    if i = m.chapterIndex then return
    m.chapterIndex = i
    if i >= 0 and m.video.state = "playing" and chapterTitlesOn() and not m.notice.visible and not m.osd.visible then showChapterNote(i)
end sub

sub showChapterNote(i as Integer)
    head = m.top.findNode("chapterNoteHead")
    title = m.top.findNode("chapterNoteTitle")
    head.text = "CAPÍTULO " + (i + 1).ToStr() + " DE " + m.chapters.Count().ToStr()
    title.text = m.chapters[i].title
    title.width = 0
    w = title.boundingRect().width
    if w > 1100 then w = 1100
    title.width = w + 2
    hw = head.boundingRect().width
    if hw > w then w = hw
    head.translation = [32, 22]
    title.translation = [32, 58]
    bg = m.top.findNode("chapterNoteBg")
    bg.width = w + 64
    bg.height = 128
    m.chapterNote.translation = [110, 1080 - 110 - 128]
    m.chapterNote.visible = true
    m.chapterTimer.control = "stop"
    m.chapterTimer.control = "start"
end sub

sub hideChapterNote()
    m.chapterNote.visible = false
end sub

' Nota de «varios a la vez» (la manda la escena): título limón chico y una línea; {} la quita.
sub onNote()
    n = m.top.note
    if n = invalid or n.text = invalid or n.text = ""
        hideBuildNote()
        return
    end if
    head = m.top.findNode("buildNoteHead")
    text = m.top.findNode("buildNoteText")
    head.text = ""
    if n.head <> invalid then head.text = n.head
    if n.isError = true then head.color = m.t.guindaLight else head.color = m.t.lime
    text.text = n.text
    text.width = 0
    w = text.boundingRect().width
    if w > 1300 then w = 1300
    text.width = w + 2
    hw = head.boundingRect().width
    if hw > w then w = hw
    bg = m.top.findNode("buildNoteBg")
    bg.width = w + 64
    bg.height = 116
    m.buildNote.visible = true
    m.buildNoteTimer.control = "stop"
    if n.autoHide = true then m.buildNoteTimer.control = "start"
end sub

sub hideBuildNote()
    m.buildNote.visible = false
    m.buildNoteTimer.control = "stop"
end sub

' 1:02:03 / 4:05
function fmtClock(seconds as Dynamic) as String
    total = Int(seconds)
    h = Int(total / 3600)
    mins = Int((total mod 3600) / 60)
    secs = total mod 60
    s = secs.ToStr()
    if secs < 10 then s = "0" + s
    if h > 0
        mm = mins.ToStr()
        if mins < 10 then mm = "0" + mm
        return h.ToStr() + ":" + mm + ":" + s
    end if
    return mins.ToStr() + ":" + s
end function

sub applyCaptions()
    if m.subUrl <> ""
        m.video.globalCaptionMode = "On"
        m.video.subtitleTrack = m.subUrl
    else
        m.video.globalCaptionMode = "Off"
    end if
end sub

sub onSubtitle()
    m.subUrl = m.top.subtitle
    applyCaptions()
end sub

' En archivos directos con varias pistas el Roku elige la predeterminada; aquí se cambia si hace falta.
sub onAudioTrack()
    selectAudio(m.top.audioTrack)
end sub

sub selectAudio(index as Integer)
    if index < 0 then return
    tracks = m.video.availableAudioTracks
    if tracks <> invalid and index < tracks.Count()
        m.video.audioTrack = tracks[index].Track
        print "[cine] audio del archivo: pista "; index
    end if
end sub

' ---------- estado del video ----------

sub onVideoState()
    state = m.video.state
    print "[cine] video: "; state
    if m.req = invalid then return
    if state = "playing" then m.stallTimer.control = "stop"
    if state = "playing" and not m.startedPlaying
        m.startedPlaying = true
        applyCaptions()
        if m.req.audioTrack <> invalid then selectAudio(m.req.audioTrack)
    end if
    if state = "playing" and m.pauseAfterSeek
        m.pauseAfterSeek = false
        m.video.control = "pause"
        return
    end if
    ' En pausa la barra de avance se queda; al seguir, se va sola en unos segundos.
    ' En pausa: la barra aparece (si no había nada) y lo que esté a la vista se queda; al seguir, se va sola.
    if state = "paused" and not m.appPaused and not m.upNextGroup.visible and m.startedPlaying and m.ui = "none" then showBar()
    if state = "paused" or state = "playing" then restartHideTimer()
    if m.ui = "bar" then paintOsd()
    if m.panel.open then panelStatus()
    if state = "playing" or state = "paused"
        report("tick", false)
    else if state = "error"
        print "[cine] error "; m.video.errorCode; " "; m.video.errorMsg; " "; FormatJson(m.video.errorInfo)
        message = m.video.errorMsg
        if m.req.yt = true and not m.startedPlaying   ' YouTube que no arrancó: aviso y lo siguiente de la fila
            youTubeFailed("no se pudo reproducir")
            return
        end if
        stopPlayback(false)
        m.top.event = {type: "error", message: message, title: m.req.title}
    else if state = "finished"
        finishPlayback()
    end if
end sub

' Terminó lo que se veía o escuchaba: se avisa y la escena sigue con lo siguiente (canción, episodio o la fila).
sub finishPlayback()
    if m.finished then return
    m.finished = true
    m.endTimer.control = "stop"
    ' Entre canciones no se avisa el final: solo al terminar la última (o la lista) la computadora quita su barra.
    if m.req.music <> true or m.req.last = true then report("end", true)
    m.tick.control = "stop"
    hideNotice()
    hideOsd()
    closePanel()
    m.video.control = "stop"
    m.top.event = {type: "finished"}
end sub

' Algunas canciones (AAC convertido desde FLAC) se quedan a décimas del final sin que el reproductor avise que
' terminaron: la TV se quedaba ahí para siempre, en silencio, sin pasar a la siguiente. A menos de 2 s del final, si
' en 2 s el avance no se movió (y no está en pausa), se da por terminado.
sub onEndWatch()
    duration = m.video.duration
    at = m.video.position
    if m.finished or m.req = invalid or not m.top.visible or duration <= 0 or at < duration - 2
        m.endTimer.control = "stop"
        m.endAt = -1
        return
    end if
    if m.video.state = "paused"
        m.endAt = -1
        return
    end if
    if m.endAt >= 0 and Abs(at - m.endAt) < 0.05
        m.endAt = -1
        finishPlayback()
        return
    end if
    m.endAt = at
end sub

sub onTick()
    if m.top.visible and not m.finished then report("tick", false) else m.tick.control = "stop"
end sub

sub onSeekTo()
    if not m.top.visible then return
    m.pauseAfterSeek = m.video.state = "paused"   ' saltar no debe quitar la pausa
    m.video.seek = m.top.seekTo
    m.tick.control = "start"
end sub

' La escena pide parar (se terminó todo, o hay que volver al catálogo).
sub onStop()
    stopPlayback(not m.finished)
end sub

sub stopPlayback(withReport as Boolean)
    m.appPaused = false
    m.musicView.visible = false
    if withReport and m.req <> invalid and m.startedPlaying then report("stop", true)
    m.tick.control = "stop"
    m.upNextTimer.control = "stop"
    m.upNextAnim.control = "stop"
    m.stallTimer.control = "stop"
    m.endTimer.control = "stop"
    m.statusNote.visible = false
    m.pendingContent = invalid
    m.checkTask = invalid
    hideNotice()
    hideChapterNote()
    hideBuildNote()
    hideOsd()
    closePanel()
    m.upNextGroup.visible = false
    m.multiHint.visible = false
    m.video.control = "stop"
    m.top.visible = false
end sub

' Cuenta a la Mac qué se ve y por dónde va (para «Seguir viendo» y el control desde el teléfono).
sub report(ev as String, notify as Boolean)
    r = m.req
    if r = invalid or r.report <> true then return
    atSecond = m.video.position
    if ev = "start" then atSecond = m.startAt
    duration = m.video.duration
    if duration <= 0 and r.duration <> invalid then duration = r.duration
    state = "play"
    if m.video.state = "paused" then state = "pause"
    if m.video.state = "buffering" then state = "buffer"
    info = m.top.trackInfo
    audio = 0
    subIndex = -1
    if info <> invalid
        if info.audio <> invalid then audio = info.audio
        if info["sub"] <> invalid then subIndex = info["sub"]
    end if
    body = {id: r.id, p: atSecond, d: duration, ev: ev, audio: audio, state: state, device_id: m.top.deviceId}
    body["sub"] = subIndex
    if r.music = true and r.songCount <> invalid then body.song = {i: r.songIndex, n: r.songCount}
    task = CreateObject("roSGNode", "ApiTask")
    task.url = m.top.server + "/api/progress"
    task.body = FormatJson(body)
    if notify then task.observeField("done", "onSaved")
    task.control = "RUN"
    m.posts.Push(task)
    if m.posts.Count() > 6 then m.posts.Shift()
end sub

sub onSaved()
    m.top.event = {type: "saved"}
end sub

' ---------- aviso para saltar la intro ----------

' Se ofrece desde que se entra al tramo, durante 8 s (o hasta su final si es antes). Si se sale del tramo y se
' vuelve a entrar, se ofrece otra vez. Nunca se salta solo.
sub onPosition()
    at = m.video.position
    m.top.position = at
    if not m.finished and m.video.duration > 0 and at >= m.video.duration - 2 then m.endTimer.control = "start"
    trackChapter(at)
    if m.osd.visible then paintOsd()
    if m.panel.open then panelStatus()
    if m.marks.Count() = 0 or m.top.covered then return
    playing = m.video.state = "playing"
    for i = 0 to m.marks.Count() - 1
        mk = m.marks[i]
        inside = at >= mk.start and at < mk.finish
        if not inside
            mk.state = "out"
            if m.markIndex = i then hideNotice()
        else if mk.state = "out" and playing and m.markIndex = -1
            mk.state = "offer"
            mk.until = at + 8
            if mk.until > mk.finish then mk.until = mk.finish
            showNotice(i)
        else if mk.state = "offer" and m.markIndex = i
            if at >= mk.until
                mk.state = "done"
                hideNotice()
            else
                drainTo((mk.until - at) / 8.0)
            end if
        end if
    end for
end sub

sub showNotice(i as Integer)
    mk = m.marks[i]
    m.markIndex = i
    layoutBadge(mk.label, true, "skip")
    drainTo(1.0)
    m.notice.visible = true
    m.notice.setFocus(true)   ' mientras se ve, el OK es de la app (salta) y no del video
end sub

' Arma el aviso de abajo a la derecha: [OK] TEXTO y la línea que se vacía; en pausa, [ícono] EN PAUSA.
sub layoutBadge(text as String, isNotice as Boolean, icon as String)
    h = 104
    x = 30
    okEdge = m.top.findNode("okEdge")
    ok = m.top.findNode("okText")
    iconNode = m.top.findNode("noticeIcon")
    okEdge.visible = isNotice
    ok.visible = isNotice
    iconNode.visible = not isNotice
    if isNotice
        okEdge.translation = [x, 26]
        okEdge.width = 76
        okEdge.height = 52
        ok.translation = [x, 26]
        ok.width = 76
        ok.height = 52
        x = x + 76 + 24
    else
        iconNode.uri = "pkg:/images/icons/" + icon + ".png"
        iconNode.translation = [x, 32]
        x = x + 40 + 20
    end if
    m.noticeText.width = 0
    m.noticeText.text = marquee(text)
    textW = m.noticeText.boundingRect().width
    if textW > 900 then textW = 900
    m.noticeText.translation = [x, 0]
    m.noticeText.width = textW + 4
    m.noticeText.height = h - 4
    w = x + textW + 34
    m.top.findNode("noticeBg").width = w
    m.top.findNode("noticeBg").height = h
    edge = m.top.findNode("noticeEdge")
    edge.width = w
    edge.height = h
    ' La única sombra de la app: el aviso flota encima del video.
    shadow = m.top.findNode("noticeShadow")
    shadow.translation = [-40, -40 + 14]
    shadow.width = w + 80
    shadow.height = h + 80
    m.drain.visible = isNotice
    m.drain.translation = [18, h - 18]
    m.drainFull = w - 36
    m.notice.translation = [1920 - 110 - w, 1080 - 110 - h]
end sub

sub drainTo(fraction as Float)
    if fraction < 0 then fraction = 0
    if fraction > 1 then fraction = 1
    m.drain.width = Int(m.drainFull * fraction)
end sub

sub hideNotice()
    wasVisible = m.notice.visible
    m.notice.visible = false
    m.markIndex = -1
    if m.appPaused then return   ' en pausa hecha por la app, las teclas siguen llegando aquí
    if wasVisible and m.top.visible and not m.upNextGroup.visible then m.top.setFocus(true)
end sub

' Con el aviso en pantalla: OK salta; ▶ pausa; ⏩/⏪ adelantan o atrasan 10 s; cualquier otra tecla lo esconde.
sub noticeKey(key as String)
    mk = m.marks[m.markIndex]
    mk.state = "done"
    at = m.video.position
    if key = "OK"
        m.pauseAfterSeek = m.video.state = "paused"
        m.video.seek = mk.finish
    else if key = "play"
        if m.video.state = "paused"
            m.video.control = "resume"
        else
            ' Si solo se pausara el video, su propio ▶ quedaría desfasado (habría que apretarlo dos veces):
            ' la app se queda con las teclas hasta que se reanude y muestra «En pausa».
            m.video.control = "pause"
            m.appPaused = true
        end if
    else if key = "fastforward"
        m.video.seek = at + 10
    else if key = "rewind" or key = "replay"
        target = at - 10
        if target < 0 then target = 0
        m.video.seek = target
    end if
    hideNotice()
    if m.appPaused
        layoutBadge("En pausa", false, "pause")
        m.notice.visible = true
    end if
    updateMultiHint()
end sub

' Pausa hecha por la app: cualquier tecla (salvo Atrás) reanuda y devuelve el control al video.
sub resumeFromAppPause()
    m.appPaused = false
    m.notice.visible = false
    m.video.control = "resume"
    m.top.setFocus(true)
    updateMultiHint()
end sub

' ---------- lo siguiente ----------

sub onUpNext()
    u = m.top.upNext
    if u = invalid or u.title = invalid then return
    m.upNextSource = u.source
    what = "Siguiente episodio"
    if u.source = "fila" then what = "Lo siguiente de la fila"
    if u.source = "recomendado" then what = "Recomendado por YouTube"
    m.top.findNode("upNextWhat").text = marquee(what)
    back = "Volver"
    if u.source = "recomendado" then back = "Detener"
    drawKeys(back)
    poster = m.top.findNode("upNextPoster")
    poster.uri = u.thumb
    fallback = m.top.findNode("upNextFallbackTitle")
    fallback.text = marquee(u.title)
    fallback.visible = u.thumb = invalid or u.thumb = ""
    m.top.findNode("upNextTitle").text = u.title
    note = m.top.findNode("upNextNote")
    note.text = ""
    if u.note <> invalid then note.text = u.note
    note.visible = note.text <> ""
    m.upNextLeft = 5
    if u.seconds <> invalid then m.upNextLeft = u.seconds
    m.upNextAnim.duration = m.upNextLeft
    updateUpNextCount()
    m.top.findNode("upNextDrain").width = 690
    m.top.visible = true
    hideOsd()
    closePanel()
    m.upNextGroup.visible = true
    m.multiHint.visible = false
    m.upNextGroup.setFocus(true)
    m.upNextTimer.control = "start"
    m.upNextAnim.control = "start"
end sub

sub onUpNextPoster()
    status = m.top.findNode("upNextPoster").loadStatus
    m.top.findNode("upNextFallbackTitle").visible = status <> "ready"
end sub

' Teclas dibujadas: [OK] Verlo ya   [Atrás] Volver.
sub drawKeys(back as String)
    group = m.top.findNode("upNextKeys")
    group.removeChildren(group.getChildren(-1, 0))
    x = 0
    for each k in [{key: "OK", text: "Verlo ya", color: m.t.lime}, {key: "Atrás", text: back, color: m.t.edge}]
        cap = group.createChild("Label")
        cap.font = makeFont(27, "bold")
        cap.text = k.key
        cap.color = k.color
        if k.color = m.t.edge then cap.color = m.t.text
        capW = Int(cap.boundingRect().width) + 32
        edge = group.createChild("Poster")
        edge.uri = "pkg:/images/line.9.png"
        edge.blendColor = k.color
        edge.translation = [x, 0]
        edge.width = capW
        edge.height = 52
        cap.translation = [x, 0]
        cap.width = capW
        cap.height = 52
        cap.horizAlign = "center"
        cap.vertAlign = "center"
        word = group.createChild("Label")
        word.font = makeFont(32)
        word.color = m.t.text
        word.text = k.text
        word.translation = [x + capW + 16, 0]
        word.height = 52
        word.vertAlign = "center"
        x = x + capW + 16 + Int(word.boundingRect().width) + 56
    end for
end sub

sub updateUpNextCount()
    count = m.top.findNode("upNextCount")
    count.text = m.upNextLeft.ToStr()
    unit = m.top.findNode("upNextUnit")
    if m.upNextLeft = 1 then unit.text = "segundo" else unit.text = "segundos"
    ' La unidad, sobre la misma línea de base que el número.
    unit.translation = [1124 + Int(count.boundingRect().width) + 16, 478 + 108 - 28]
end sub

sub onUpNextTick()
    m.upNextLeft = m.upNextLeft - 1
    if m.upNextLeft <= 0 then finishUpNext("upnext-play") else updateUpNextCount()
end sub

sub finishUpNext(kind as String)
    m.upNextTimer.control = "stop"
    m.upNextAnim.control = "stop"
    m.upNextGroup.visible = false
    m.top.event = {type: kind}
end sub

' ---------- control remoto ----------

' Las teclas del Roku, de la app (ver Player.xml): capítulos con ◀ ▶, adelantar/atrasar, pausa, el panel, la fila y
' las opciones.
function onKeyEvent(key as String, press as Boolean) as Boolean
    if not press then return false
    if m.upNextGroup.visible
        if key = "back"
            finishUpNext("upnext-cancel")
        else if key = "OK" or key = "play"
            finishUpNext("upnext-play")
        end if
        return true
    end if
    if m.notice.visible and m.markIndex >= 0
        noticeKey(key)
        return true
    end if
    if key = "back" and m.top.visible
        if m.ui <> "none"   ' primero se quita lo que hay encima; sin nada encima, Atrás sale
            hideAll()
            return true
        end if
        m.appPaused = false
        stopPlayback(true)
        m.top.event = {type: "stopped"}
        return true
    end if
    if m.appPaused
        resumeFromAppPause()
        return true
    end if
    if not m.top.visible or m.req = invalid or m.top.covered then return false
    if m.pendingContent <> invalid or m.finished then return true   ' cargando o terminado: nada que mover
    live = m.req.live = true
    if key = "play" or key = "OK"
        togglePause()
    else if key = "left" or key = "right"
        if m.ui <> "bar"
            showBar()   ' la primera vez solo se muestra la barra; después se mueve la posición
        else if not live
            dir = 1
            if key = "left" then dir = -1
            scrub(dir)
        end if
    else if key = "fastforward" or key = "rewind"
        dir = 1
        if key = "rewind" then dir = -1
        if not live then seekBy(15 * dir)
    else if key = "replay"
        if not live then seekBy(-10)
    else if key = "down"
        if m.ui = "bar"
            m.top.event = {type: "panel"}   ' la escena manda la fila y lo visto (panelData) y se abre
        else
            showBar()
        end if
    else if key = "up"
        if m.ui = "bar" then hideAll()
    else
        return false
    end if
    return true
end function

function dubOf(r as Object) as String
    if r = invalid or r.dub = invalid then return ""
    return r.dub
end function

sub togglePause()
    if m.video.state = "paused"
        m.video.control = "resume"
    else
        m.video.control = "pause"
    end if
    if m.ui = "none" then showBar() else paintOsd()
end sub

' ◀ ▶ con la barra a la vista: con capítulos, al principio del actual (o del anterior si ya se está al principio) o
' al siguiente; sin capítulos, 10 s y, si se aprietan seguidas, cada vez más (hasta 60 s). Las teclas seguidas se
' suman y se salta al soltar medio segundo.
sub scrub(dir as Integer)
    at = m.video.position
    if m.seekTarget >= 0 then at = m.seekTarget
    if m.chapters.Count() = 0
        if m.stepClock.TotalMilliseconds() < 900 then m.stepAt = m.stepAt + 1 else m.stepAt = 0
        m.stepClock.Mark()
        jump = 10 * (m.stepAt + 1)
        if jump > 60 then jump = 60
        seekLater(at + jump * dir)
        return
    end if
    i = chapterAt(at)
    if dir > 0
        if i >= m.chapters.Count() - 1
            showOsdNote("Es el último capítulo")
            return
        end if
        target = m.chapters[i + 1].start
    else
        if i >= 0 and at - m.chapters[i].start > 3
            target = m.chapters[i].start
        else if i > 0
            target = m.chapters[i - 1].start
        else
            target = 0
        end if
    end if
    seekLater(target)
end sub

sub seekBy(seconds as Integer)
    at = m.video.position
    if m.seekTarget >= 0 then at = m.seekTarget
    seekLater(at + seconds)
end sub

sub seekLater(target as Float)
    duration = m.video.duration
    if target < 0 then target = 0
    if duration > 0 and target > duration - 2 then target = duration - 2
    m.seekTarget = target
    m.osdNote = ""
    if m.ui <> "bar" then showBar() else paintOsd()
    m.osdTimer.control = "stop"
    m.seekTimer.control = "stop"
    m.seekTimer.control = "start"
end sub

sub doSeek()
    if m.seekTarget < 0 then return
    m.pauseAfterSeek = m.video.state = "paused"   ' saltar no quita la pausa
    m.video.seek = m.seekTarget
    m.seekTarget = -1
    m.tick.control = "start"
    restartHideTimer()
end sub

' ---------- escuchando música ----------

sub showMusic(r as Object)
    music = r.music = true
    m.musicView.visible = music
    if not music then return
    m.top.findNode("musicArt").uri = r.art
    kicker = "ESCUCHANDO"
    if r.position <> invalid and r.position <> "" then kicker = kicker + "   ·   " + r.position
    m.top.findNode("musicKicker").text = kicker
    m.top.findNode("musicTitle").text = r.title
    m.top.findNode("musicArtist").text = r.artist
    m.top.findNode("musicAlbum").text = r.album
    nxt = ""
    if r.nextTitle <> invalid and r.nextTitle <> "" then nxt = "Sigue: " + r.nextTitle
    m.top.findNode("musicNext").text = nxt
end sub

' ---------- lo que hay encima del video: nada, la barra de avance o el panel ----------

sub showBar()
    if m.req = invalid then return
    if m.panel.open then m.panel.open = false
    hideChapterNote()   ' la barra ya dice el capítulo
    m.osdTitle.text = m.req.title
    if m.req.music = true and m.req.artist <> invalid then m.osdTitle.text = m.req.title + "   ·   " + m.req.artist
    m.osdNote = ""
    m.ui = "bar"
    paintOsd()
    m.osd.visible = true
    m.top.setFocus(true)
    restartHideTimer()
end sub

sub showOsd()   ' (nombre de antes, lo usa startContent y el estado del video)
    showBar()
end sub

sub showOsdNote(text as String)
    if m.ui <> "bar" then showBar()
    m.osdNote = text
    paintOsd()
end sub

sub hideOsd()
    hideAll()
end sub

sub hideAll()
    m.osd.visible = false
    m.osdTimer.control = "stop"
    m.panelTimer.control = "stop"
    if m.panel <> invalid and m.panel.open then m.panel.open = false
    m.ui = "none"
    if m.top.visible and not m.upNextGroup.visible and not m.notice.visible then m.top.setFocus(true)
end sub

' Se ocultan solos si el video sigue; en pausa (o mientras se está moviendo la posición) se quedan.
sub restartHideTimer()
    m.osdTimer.control = "stop"
    m.panelTimer.control = "stop"
    if m.video.state = "paused" or m.seekTarget >= 0 then return
    if m.ui = "bar" then m.osdTimer.control = "start"
    if m.ui = "panel" then m.panelTimer.control = "start"
end sub

sub onOsdTimer()
    if m.ui <> "bar" or m.video.state = "paused" or m.seekTarget >= 0 then return
    hideAll()
end sub

sub onPanelTimer()
    if m.ui <> "panel" or m.video.state = "paused" then return
    hideAll()
end sub

sub onPanelTouched()
    if m.ui = "panel" then restartHideTimer()
end sub

sub paintOsd()
    at = m.video.position
    if m.seekTarget >= 0 then at = m.seekTarget
    duration = m.video.duration
    if duration <= 0 and m.req.duration <> invalid then duration = m.req.duration
    live = m.req.live = true
    paused = m.video.state = "paused"
    if paused then m.osdPlay.uri = "pkg:/images/icons/play.png" else m.osdPlay.uri = "pkg:/images/icons/pause.png"
    if live or duration <= 0
        m.osdFill.width = 0
        m.osdKnob.visible = false
        if live then m.osdTime.text = "EN VIVO" else m.osdTime.text = fmtClock(at)
    else
        f = at / duration
        if f > 1 then f = 1
        m.osdFill.width = Int(1636 * f)
        m.osdKnob.visible = true
        m.osdKnob.translation = [174 + Int(1636 * f) - 14, 931]
        m.osdTime.text = fmtClock(at) + " / " + fmtClock(duration)
        if m.ticksFor <> duration then drawOsdTicks(duration)
    end if
    text = ""
    i = chapterAt(at)
    if i >= 0 then text = "Capítulo " + (i + 1).ToStr() + " de " + m.chapters.Count().ToStr() + "   ·   " + m.chapters[i].title
    if m.osdNote <> invalid and m.osdNote <> "" then text = m.osdNote
    m.osdChapter.text = text
    ok = "OK: pausa"
    if paused then ok = "OK: seguir"
    rest = ok + "   ·   abajo: más opciones   ·   arriba: ocultar"
    if live
        m.osdHint.text = rest
    else if m.chapters.Count() > 0
        m.osdHint.text = "‹ ›: capítulo anterior o siguiente   ·   " + rest
    else
        m.osdHint.text = "‹ ›: moverte en la barra   ·   " + rest
    end if
end sub

sub drawOsdTicks(duration as Float)
    m.ticksFor = duration
    m.osdTicks.removeChildren(m.osdTicks.getChildren(-1, 0))
    for i = 1 to m.chapters.Count() - 1
        t = m.osdTicks.createChild("Rectangle")
        t.width = 6
        t.height = 10
        t.color = m.t.bg
        t.translation = [Int(1636 * m.chapters[i].start / duration) - 3, 0]
    end for
end sub

' ---------- el panel (▼ con la barra a la vista) ----------

' La escena mandó la fila y lo visto: se arma el panel y se abre. Botones: solo lo que no hacen ya las teclas del
' control (el siguiente de la fila, audio y subtítulos; con música, la canción anterior o la siguiente).
sub onPanelData()
    d = m.top.panelData
    if d = invalid or not m.top.visible or m.req = invalid then return
    buttons = []
    if m.req.music = true
        if d.songPrev = true then buttons.Push({id: "song-prev", text: "Canción anterior", icon: "skip-back"})
        if d.songNext = true then buttons.Push({id: "song-next", text: "Siguiente canción", icon: "skip"})
    end if
    queue = d.queue
    if queue <> invalid and queue.Count() > 0 then buttons.Push({id: "next", text: "Siguiente de la fila", icon: "list-video"})
    if m.dubs.Count() > 0 or d.tracks = true then buttons.Push({id: "tracks", text: "Audio y subtítulos", icon: "audio"})
    m.panel.data = {title: m.req.title, queue: queue, history: d.history, buttons: buttons, chapters: m.chapters}
    panelStatus()
    m.osd.visible = false   ' el panel trae su propia barra
    m.osdTimer.control = "stop"
    m.ui = "panel"
    m.panel.open = true
    restartHideTimer()
end sub

sub panelStatus()
    at = m.video.position
    text = ""
    i = chapterAt(at)
    if i >= 0 then text = "Capítulo " + (i + 1).ToStr() + " de " + m.chapters.Count().ToStr() + "   ·   " + m.chapters[i].title
    duration = m.video.duration
    if duration <= 0 and m.req <> invalid and m.req.duration <> invalid then duration = m.req.duration
    if m.req <> invalid and m.req.live = true then duration = 0
    m.panel.status = {position: at, duration: duration, paused: m.video.state = "paused", chapter: text}
end sub

sub closePanel()
    if m.panel = invalid or not m.panel.open then return
    hideAll()
end sub

sub onPanelEvent()
    e = m.panel.event
    if e.type = "close"          ' Atrás
        hideAll()
    else if e.type = "up"        ' ▲ desde arriba del panel: de vuelta a la barra
        showBar()
    else if e.type = "pause"     ' ⏯ con el panel abierto
        if m.video.state = "paused" then m.video.control = "resume" else m.video.control = "pause"
    else if e.type = "button"
        id = e.id
        if id = "next"
            hideAll()
            m.top.event = {type: "panel-queue", index: 0}
        else if id = "tracks"
            hideAll()
            m.top.event = {type: "options", dubs: m.dubs, dub: dubOf(m.req), live: m.req.live = true}
        else if id = "song-prev" or id = "song-next"
            hideAll()
            dir = 1
            if id = "song-prev" then dir = -1
            m.top.event = {type: "track", dir: dir}
        end if
    else if e.type = "queue"
        hideAll()
        m.top.event = {type: "panel-queue", index: e.index}
    else if e.type = "history"
        hideAll()
        m.top.event = {type: "panel-history", index: e.index}
    end if
end sub

' ---------- varios a la vez (archivado) ----------

function canMulti() as Boolean
    return false
end function

sub updateMultiHint()
    m.multiHint.visible = false
end sub

sub onCovered()
    if m.multiHint = invalid then return
    if m.top.covered then hideOsd()
end sub

' Se cerró la lista: el foco vuelve a lo que estaba en pantalla (la cuenta atrás, el aviso o el video).
sub onRefocus()
    if not m.top.visible then return
    if m.upNextGroup.visible
        m.upNextGroup.setFocus(true)
    else if m.notice.visible
        m.notice.setFocus(true)
    else if m.panel.open
        m.panel.setFocus(true)
    else
        m.top.setFocus(true)
    end if
end sub
