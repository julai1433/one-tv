package app.onetv.tv.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.key
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextAlign
import app.onetv.tv.Estado
import app.onetv.tv.Ficha
import app.onetv.tv.Lista
import app.onetv.tv.PanelIdioma
import app.onetv.tv.Vacio
import app.onetv.tv.VistaBuscar
import app.onetv.tv.crearLista
import app.onetv.tv.data.marquee

// Lo que se abre encima: la lista de la derecha (MultiPicker del Roku), el panel «Idioma» de la ficha (DetailView), la
// sinopsis completa, el código QR, «Cómo traer tu YouTube» y Buscar (SearchView).

// ---------- la lista de la derecha ----------

/** Panel a la derecha, encima de todo: renglones con un cuadro con ícono, el título y una línea de apoyo. Lo desactivado
 *  va en gris. La lista se corre para que se vea el renglón con el foco. */
@Composable
fun ListaUI(e: Estado, l: Lista) {
    Box(Modifier.fillMaxSize()) {
        Box(Modifier.fillMaxSize().background(C.scrim))
        Box(Modifier.offset(820.u, 0.u).size(1100.u, 1080.u).background(C.raise2))
        Texto(marquee(l.title), font(72, Face.BLACK), Modifier.offset(880.u, 48.u).width(992.u))
        Texto(l.note, font(32, color = C.textSoft), Modifier.offset(880.u, 146.u).width(992.u), maxLines = 2)
        if (l.opciones.isEmpty()) {
            Box(Modifier.offset(880.u, 276.u)) { VacioUI(Vacio(l.vacio.phrase, l.vacio.cause), app.onetv.tv.Forma.VIDEO, false, ancho = 992) }
            Texto("Atrás: cerrar", font(27, color = C.muted), Modifier.offset(880.u, 990.u))
            return@Box
        }
        val rowH = 132
        val gap = 12
        val viewH = 708
        val focusY = e.listaIndex * (rowH + gap)
        val scroll = (focusY + rowH - viewH).coerceAtLeast(0)
        Box(Modifier.offset(868.u, 252.u).size(1004.u, viewH.u).clipToBounds()) {
            Column(Modifier.offset(0.u, (-scroll).u), verticalArrangement = Arrangement.spacedBy(gap.u)) {
                l.opciones.forEachIndexed { k, o ->
                    val lit = k == e.listaIndex && !o.disabled
                    Box(Modifier.size(1004.u, rowH.u).clip(RoundedCornerShape(2.u)).background(if (lit) C.lime else Color.Transparent)) {
                        Box(Modifier.offset(12.u, 12.u).size(192.u, 108.u).alpha(if (o.disabled) 0.4f else 1f).background(C.raise3),
                            contentAlignment = Alignment.Center) {
                            Icono(o.icon, if (o.disabled) C.muted else C.text, Modifier.size(56.u))
                        }
                        val titleColor = when {
                            o.disabled -> C.muted
                            lit -> C.onLime
                            else -> C.text
                        }
                        if (o.line.isEmpty()) {
                            Box(Modifier.offset(228.u, 0.u).size(752.u, rowH.u), contentAlignment = Alignment.CenterStart) {
                                Texto(o.title, font(32, Face.BOLD, titleColor))
                            }
                        } else {
                            Texto(o.title, font(32, Face.BOLD, titleColor), Modifier.offset(228.u, 24.u).width(752.u))
                            Texto(o.line, font(27, color = if (lit) C.onLime else C.muted), Modifier.offset(228.u, 74.u).width(752.u))
                        }
                    }
                }
            }
        }
        Texto(l.hint, font(27, color = C.muted), Modifier.offset(880.u, 990.u).width(992.u))
    }
}

// ---------- el panel «Idioma» de la ficha ----------

/** Audio a la izquierda, subtítulos a la derecha («Buscar subtítulos en internet» al final). */
@Composable
fun IdiomaUI(e: Estado, p: PanelIdioma) {
    val c = e.cur ?: return
    val it = c.item ?: return
    Box(Modifier.fillMaxSize()) {
        Box(Modifier.fillMaxSize().background(C.scrim))
        Box(Modifier.offset(820.u, 0.u).size(1100.u, 1080.u).background(C.raise2))
        Texto("IDIOMA", font(72, Face.BLACK), Modifier.offset(880.u, 48.u))
        Icono("audio", C.textSoft, Modifier.offset(880.u, 176.u).size(34.u))
        Box(Modifier.offset(928.u, 166.u).height(54.u), contentAlignment = Alignment.CenterStart) { Texto("Audio", font(32, Face.BOLD, C.textSoft)) }
        Icono("captions", C.textSoft, Modifier.offset(1390.u, 176.u).size(34.u))
        Box(Modifier.offset(1438.u, 166.u).height(54.u), contentAlignment = Alignment.CenterStart) {
            Texto(if (p.buscar) "¿En qué idioma?" else "Subtítulos", font(32, Face.BOLD, C.textSoft))
        }
        val audios = it.audio.map { a -> app.onetv.tv.data.trackName(a) }
        Columna(audios.mapIndexed { i, t -> Renglon(t, i == c.audio) }, if (p.col == 0) p.audio else -1, Modifier.offset(870.u, 236.u), 470)
        val subs = e.subsDelPanel(p)
        val renglones = if (p.buscar) listOf(Renglon(subs[0], false, "search"), Renglon(subs[1], false, "search"), Renglon(subs[2], false, "rotate-ccw"))
        else subs.mapIndexed { i, t ->
            when {
                i == subs.size - 1 -> Renglon(t, false, "search", more = true)
                else -> Renglon(t, i - 1 == c.sub)
            }
        }
        Columna(renglones, if (p.col == 1) p.subs else -1, Modifier.offset(1380.u, 236.u), 500)
        if (e.fichaMensaje.isNotEmpty()) Texto(e.fichaMensaje, font(32, Face.BOLD, if (e.fichaMensajeError) C.guindaLight else C.lime),
            Modifier.offset(880.u, 920.u).width(1000.u))
        Texto("OK: elegir   ·   ‹ ›: audio o subtítulos   ·   Atrás: cerrar", font(27, color = C.muted), Modifier.offset(880.u, 990.u).width(1000.u))
    }
}

/** Una opción: la elegida lleva palomita (y va en limón); lead pone otro ícono a la izquierda y more una flecha. */
private data class Renglon(val text: String, val current: Boolean, val lead: String = "", val more: Boolean = false)

@Composable
private fun Columna(list: List<Renglon>, foco: Int, modifier: Modifier, ancho: Int) {
    val first = (foco - 8).coerceAtLeast(0)
    Column(modifier, verticalArrangement = Arrangement.spacedBy(8.u)) {
        for (i in first until minOf(list.size, first + 9)) {
            val r = list[i]
            val lit = i == foco
            val color = when {
                lit -> C.onLime
                r.current -> C.lime
                else -> C.text
            }
            Box(Modifier.size(ancho.u, 64.u).clip(RoundedCornerShape(2.u)).background(if (lit) C.lime else Color.Transparent)) {
                val icon = r.lead.ifEmpty { if (r.current) "check" else "" }
                if (icon.isNotEmpty()) Icono(icon, color, Modifier.offset(20.u, 16.u).size(32.u))
                Box(Modifier.offset(68.u, 0.u).size((ancho - 124).u, 64.u), contentAlignment = Alignment.CenterStart) {
                    Texto(r.text, font(32, if (r.current) Face.BOLD else Face.REGULAR, color))
                }
                if (r.more) Icono("chevron-right", color, Modifier.offset((ancho - 48).u, 16.u).size(32.u))
            }
        }
    }
}

// ---------- sinopsis completa y código QR ----------

@Composable
fun SinopsisUI(e: Estado, f: Ficha) {
    val scroll = rememberScrollState()
    LaunchedEffect(e.sinopsisPaso) {
        val target = (e.sinopsisPaso * 300).coerceAtMost(scroll.maxValue)
        if (target < e.sinopsisPaso * 300 && e.sinopsisPaso > 0 && scroll.maxValue > 0) e.sinopsisPaso = (scroll.maxValue + 299) / 300
        scroll.animateScrollTo(target)
    }
    Box(Modifier.fillMaxSize().background(C.bg)) {
        val title = if (f.subtitle.isNotEmpty()) f.title + " · " + f.subtitle else f.title
        Texto(marquee(title), font(72, Face.BLACK), Modifier.offset(110.u, 64.u).width(1700.u), maxLines = 2)
        var text = e.fichaDesc.takeIf { it.isNotEmpty() && it != "Buscando la sinopsis…" } ?: "Sin sinopsis todavía."
        if (f.tech.isNotEmpty()) text += "\n\nDetalles técnicos\n" + f.tech
        Box(Modifier.offset(110.u, 200.u).size(1700.u, 760.u).verticalScroll(scroll)) {
            androidx.compose.foundation.text.BasicText(text, style = font(32).copy(lineHeight = 46.ut))
        }
        Texto("Arriba / abajo: desplazar   ·   Atrás o mantén OK: cerrar", font(27, color = C.muted), Modifier.offset(110.u, 990.u))
    }
}

/** Compartir un video de YouTube: código QR para abrirlo desde el teléfono. */
@Composable
fun QrUI(e: Estado, f: Ficha) {
    Box(Modifier.fillMaxSize().background(C.bg)) {
        Texto(marquee(f.title), font(72, Face.BLACK), Modifier.offset(110.u, 80.u).width(1700.u), maxLines = 2)
        Box(Modifier.offset(98.u, 248.u).size(648.u).background(C.bg))
        ImagenRed(e.datos?.abs("/yt/${f.id}/qr.png"), Modifier.offset(110.u, 260.u).size(624.u), maxLado = 640,
            scale = androidx.compose.ui.layout.ContentScale.Fit)
        Texto("Apunta la cámara del teléfono al código: se abre el video en YouTube y desde ahí lo compartes por WhatsApp, mensaje o lo que quieras.",
            font(32, color = C.textSoft), Modifier.offset(820.u, 300.u).width(1000.u), maxLines = 4)
        Texto("youtu.be/" + f.id, font(38, Face.BOLD), Modifier.offset(820.u, 560.u).width(1000.u))
        Texto("Atrás: volver", font(27, color = C.muted), Modifier.offset(820.u, 820.u).width(1000.u))
    }
}

// ---------- cómo traer YouTube ----------

@Composable
fun AyudaUI() {
    Box(Modifier.fillMaxSize().background(C.bg)) {
        Texto("CÓMO TRAER TU YOUTUBE", font(72, Face.BLACK), Modifier.offset(168.u, 72.u))
        Texto("Tu historial, tus listas y tus suscripciones llegan con una exportación de Google. Se hace una sola vez, desde una computadora:",
            font(32, color = C.textSoft), Modifier.offset(168.u, 190.u).width(1116.u), maxLines = 2)
        val pasos = listOf(
            "Entra a takeout.google.com (o escanea el código) y pulsa «Anular selección».",
            "Marca solo «YouTube y YouTube Music». En sus opciones deja historial, listas y suscripciones, quita «vídeos» y pon el historial en JSON.",
            "Crea una sola exportación en .zip. Cuando llegue el correo, descárgala en la computadora donde corre One TV.",
            "Déjala en Descargas sin cambiarle el nombre: One TV la importa sola en unos minutos.",
        )
        Column(Modifier.offset(168.u, 320.u), verticalArrangement = Arrangement.spacedBy(36.u)) {
            pasos.forEachIndexed { i, t ->
                Row {
                    Texto("${i + 1}", font(72, Face.BLACK, C.muted), Modifier.width(96.u).offset(0.u, (-6).u))
                    Texto(t, font(38).copy(lineHeight = 46.ut), Modifier.width(1020.u), maxLines = 3)
                }
            }
        }
        ImagenApp("qr_takeout", Modifier.offset(1356.u, 320.u).size(396.u))
        Texto("takeout.google.com", font(32, Face.BOLD), Modifier.offset(1356.u, 736.u).width(396.u), align = TextAlign.Center)
        Texto("Escanéalo con tu teléfono", font(27, color = C.muted), Modifier.offset(1356.u, 786.u).width(396.u), align = TextAlign.Center)
        Texto("Atrás: volver", font(27, color = C.muted), Modifier.offset(168.u, 990.u))
    }
}

// ---------- Buscar ----------

/** El campo (lupa, lo escrito en letra grande, cursor limón y línea que se vuelve limón), los botones de YouTube, los
 *  resultados (o un vacío que dice qué hacer) y la línea con lo que dice el resultado elegido. */
@Composable
fun BuscarUI(e: Estado, v: VistaBuscar) {
    val b = e.buscador
    LaunchedEffect(v.youtube) { if (b.youtube != v.youtube) b.abrir(v.youtube) }
    val activo = !e.menuAbierto && e.ficha == null && e.lista == null
    val enCampo = activo && b.zona == 0
    val focus = remember { FocusRequester() }
    val keyboard = LocalSoftwareKeyboardController.current
    val focusManager = LocalFocusManager.current
    LaunchedEffect(b.pedirTeclado, b.editando) {
        if (b.pedirTeclado > 0 && b.editando) {
            kotlinx.coroutines.delay(50)   // el campo recién se armó
            try {
                focus.requestFocus()
            } catch (_: IllegalStateException) {
            }
            keyboard?.show()
        }
    }
    LaunchedEffect(b.editando) {
        if (!b.editando) {
            keyboard?.hide()
            focusManager.clearFocus()
        }
    }
    Box(Modifier.fillMaxSize()) {
        Texto(if (v.youtube) "BUSCAR EN YOUTUBE" else "BUSCAR", font(72, Face.BLACK), Modifier.offset(168.u, 26.u))
        // El campo (DESIGN.md, pieza 1): sin caja, línea inferior, letra grande, cursor limón.
        Box(Modifier.offset(168.u, 144.u).size(574.u, 80.u)) {
            Icono("search", if (enCampo) C.lime else C.text, Modifier.offset(0.u, 18.u).size(40.u))
            // El campo de texto existe solo mientras el teclado de la TV está abierto: así, cerrado, el teclado no
            // vuelve a abrirse con el OK que es para otra cosa.
            if (b.editando) BasicTextField(
                value = b.texto, onValueChange = { b.escribir(it) }, singleLine = true,
                textStyle = font(44, Face.MEDIUM), cursorBrush = SolidColor(C.lime),
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
                keyboardActions = KeyboardActions(onSearch = { b.terminarEdicion() }, onDone = { b.terminarEdicion() }),
                modifier = Modifier.offset(58.u, 0.u).size(470.u, 76.u).focusRequester(focus),
                decorationBox = { inner ->
                    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.CenterStart) {
                        if (b.texto.isEmpty()) Texto(b.placeholder(), font(44, Face.MEDIUM, C.muted))
                        inner()
                    }
                },
            ) else Row(Modifier.offset(58.u, 0.u).size(470.u, 76.u), verticalAlignment = Alignment.CenterVertically) {
                // Si no cabe, se ve el final (lo último que se escribió).
                if (b.texto.isEmpty()) {
                    if (enCampo) Box(Modifier.padding(end = 4.u).size(4.u, 48.u).background(C.lime))
                    Texto(b.placeholder(), font(44, Face.MEDIUM, C.muted))
                } else {
                    val shown = if (b.texto.length > 18) "…" + b.texto.takeLast(17) else b.texto
                    Texto(shown, font(44, Face.MEDIUM))
                    if (enCampo) Box(Modifier.padding(start = 4.u).size(4.u, 48.u).background(C.lime))
                }
            }
            Box(Modifier.offset(0.u, 74.u).size(572.u, 3.u).background(if (enCampo) C.lime else C.edge))
        }
        Texto(if (enCampo) "OK: abrir el teclado de la TV. Si tu control tiene micrófono, también puedes dictar." else "",
            font(27, color = C.muted), Modifier.offset(168.u, 900.u).width(660.u), maxLines = 2)
        val t = b.texto.trim()
        if (t.isNotEmpty()) {
            FilaBotones(listOf(app.onetv.tv.Boton("yt", "Buscar «$t» en YouTube", "square-play"), app.onetv.tv.Boton("ytlive", "Solo en vivo", "radio")),
                if (activo && b.zona == 1) b.boton else -1, Modifier.offset(900.u, 150.u), principal = false, maxAncho = 940)
        }
        val (forma, tiles) = b.tarjetas(e.datos)
        if (tiles.isEmpty()) {
            Box(Modifier.offset(900.u, 320.u)) {
                val vacio = b.vacio()
                Column(Modifier.width(940.u), verticalArrangement = Arrangement.spacedBy(10.u)) {
                    Texto(marquee(vacio.phrase), font(48, Face.DISPLAY), maxLines = 2)
                    Texto(vacio.cause, font(32, color = C.textSoft), maxLines = 3)
                    Spacer(Modifier.height(14.u))
                    Row(horizontalArrangement = Arrangement.spacedBy(forma.gap.u)) {
                        repeat(b.columnas(forma)) { Box(Modifier.size(forma.w.u, forma.h.u).border(2.u, C.edge, RoundedCornerShape(2.u))) }
                    }
                }
            }
            return@Box
        }
        Texto(b.cabecera(tiles.size), font(38, Face.BOLD), Modifier.offset(900.u, 250.u).width(940.u))
        val cols = b.columnas(forma)
        val enResultados = activo && b.zona == 2
        val i = b.foco.coerceIn(0, tiles.size - 1)
        val firstRow = ((i / cols) - 1).coerceAtLeast(0)
        Column(Modifier.offset(900.u, 320.u), verticalArrangement = Arrangement.spacedBy(24.u)) {
            for (row in firstRow until minOf((tiles.size + cols - 1) / cols, firstRow + 2)) {
                Row(horizontalArrangement = Arrangement.spacedBy(forma.gap.u), modifier = Modifier.height(forma.slotH.u)) {
                    for (k in row * cols until minOf(tiles.size, row * cols + cols)) key(tiles[k].id) {
                        TarjetaUI(tiles[k], forma, enResultados && k == i, atenuar = enResultados)
                    }
                }
            }
        }
        if (enResultados) Texto(tiles[i].info, font(32, color = C.textSoft), Modifier.offset(900.u, 930.u).width(940.u), maxLines = 2)
    }
}

// ---------- «Lista nueva» ----------

/** El nombre de una lista nueva: panel a la derecha con el campo (línea limón, letra grande) y el teclado de la TV. */
@Composable
fun ListaNuevaUI(e: Estado) {
    val focus = remember { FocusRequester() }
    val keyboard = LocalSoftwareKeyboardController.current
    LaunchedEffect(e.listaNuevaTeclado) {
        kotlinx.coroutines.delay(50)
        try {
            focus.requestFocus()
        } catch (_: IllegalStateException) {
        }
        keyboard?.show()
    }
    val title = e.vidLists?.first?.let { e.ytTitles[it]?.title }.orEmpty()
    Box(Modifier.fillMaxSize()) {
        Box(Modifier.fillMaxSize().background(C.scrim))
        Box(Modifier.offset(820.u, 0.u).size(1100.u, 1080.u).background(C.raise2))
        Texto("LISTA NUEVA", font(72, Face.BLACK), Modifier.offset(880.u, 48.u))
        Texto("El nombre de la lista. «$title» queda en ella.", font(32, color = C.textSoft), Modifier.offset(880.u, 146.u).width(992.u), maxLines = 2)
        BasicTextField(
            value = e.listaNueva.orEmpty(), onValueChange = { e.listaNueva = it }, singleLine = true,
            textStyle = font(44, Face.MEDIUM), cursorBrush = SolidColor(C.lime),
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
            keyboardActions = KeyboardActions(onDone = { e.crearLista(e.listaNueva.orEmpty()) }),
            modifier = Modifier.offset(880.u, 270.u).width(960.u).focusRequester(focus),
            decorationBox = { inner ->
                Column {
                    Box(Modifier.padding(vertical = 10.u)) {
                        if (e.listaNueva.isNullOrEmpty()) Texto("Escribe el nombre", font(44, Face.MEDIUM, C.muted))
                        inner()
                    }
                    Box(Modifier.fillMaxWidth().height(3.u).background(C.lime))
                }
            },
        )
        Texto("OK: escribir   ·   Listo en el teclado: crear   ·   Atrás: cancelar", font(27, color = C.muted), Modifier.offset(880.u, 990.u).width(992.u))
    }
}
