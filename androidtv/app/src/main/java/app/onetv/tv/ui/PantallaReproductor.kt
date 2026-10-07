package app.onetv.tv.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.key
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.style.TextAlign
import app.onetv.tv.Capa
import app.onetv.tv.Estado
import app.onetv.tv.Reproductor
import app.onetv.tv.data.Entry
import app.onetv.tv.data.fmtClock
import app.onetv.tv.data.marquee

/** El video y lo que va encima: la barra de avance, el panel, «escuchando» con música y la cuenta atrás de lo siguiente. */
@Composable
fun PantallaReproductor(e: Estado, video: @Composable () -> Unit) {
    val p = e.reproductor
    val r = p.req ?: return
    Box(Modifier.fillMaxSize().background(C.bg)) {
        video()
        if (r.music) Escuchando(p)
        if (p.estadoTexto.isNotEmpty() && !r.music) Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            Texto(p.estadoTexto, font(32, color = C.muted))
        }
        p.notaCapitulo?.let { NotaCapituloUI(it) }
        when (p.capa) {
            Capa.BARRA -> BarraReproductor(p)
            Capa.PANEL -> PanelReproductor(e, p)
            Capa.NADA -> {}
        }
        if (p.aviso) AvisoSaltar(p.avisoTexto, p.avisoResto, conOk = true)
        else if (p.pausaApp) AvisoSaltar("En pausa", 0f, conOk = false)
        p.siguiente?.let { Siguiente(it) }
    }
}

private fun textoCapitulo(p: Reproductor, at: Double): String {
    val i = p.capituloEn(at)
    if (i < 0) return ""
    return "Capítulo ${i + 1} de ${p.capitulos.size}   ·   ${p.capitulos[i].title}"
}

@Composable
private fun BarraReproductor(p: Reproductor) {
    val r = p.req ?: return
    val at = p.posicion
    val d = if (p.duracion > 0) p.duracion else r.duration
    Box(Modifier.fillMaxSize()) {
        Box(Modifier.offset(0.u, 640.u).fillMaxWidth().height(440.u).background(Brush.verticalGradient(0f to Color.Transparent, 1f to C.bg)))
        // Con música el título ya está grande arriba (con el artista): la barra no lo repite.
        if (!r.music) Texto(r.title, font(38, Face.BOLD), Modifier.offset(110.u, 826.u).width(1300.u))
        val chapter = p.nota.ifEmpty { textoCapitulo(p, at) }
        Texto(chapter, font(32, Face.BOLD, C.lime), Modifier.offset(110.u, 880.u).width(1300.u))
        val time = when {
            r.live -> "EN VIVO"
            d <= 0 -> fmtClock(at)
            else -> fmtClock(at) + " / " + fmtClock(d)
        }
        Texto(time, font(32), Modifier.offset(1410.u, 880.u).width(400.u), align = TextAlign.End)
        Icono(if (p.pausado) "play" else "pause", C.text, Modifier.offset(110.u, 925.u).size(40.u))
        Barra(p, at, d, Modifier.offset(174.u, 940.u), alto = 10, conPunto = true)
        Texto(textoAyuda(r.live, p.capitulos.isNotEmpty(), p.pausado), font(24, color = C.muted), Modifier.offset(110.u, 972.u).width(1700.u))
    }
}

/** La ayuda de la barra (Player.brs, paintOsd): en pausa, «OK: seguir». */
fun textoAyuda(live: Boolean, capitulos: Boolean, pausado: Boolean): String {
    val rest = (if (pausado) "OK: seguir" else "OK: pausa") + "   ·   abajo: más opciones   ·   arriba: ocultar"
    return when {
        live -> rest
        capitulos -> "‹ ›: capítulo anterior o siguiente   ·   $rest"
        else -> "‹ ›: moverte en la barra   ·   $rest"
    }
}

/** El aviso para saltar (DESIGN.md, pieza 8): abajo a la derecha, panel negro al 92 % con borde limón, la tecla OK
 *  dibujada, el texto en letra de marquesina y la línea limón que se vacía en 8 s. En pausa: el ícono y EN PAUSA. */
@Composable
private fun AvisoSaltar(texto: String, resto: Float, conOk: Boolean) {
    Box(Modifier.fillMaxSize().padding(end = 110.u, bottom = 110.u), contentAlignment = Alignment.BottomEnd) {
        Box(Modifier.width(androidx.compose.foundation.layout.IntrinsicSize.Max).height(104.u).background(C.overlay).border(2.u, C.lime)) {
            Row(Modifier.fillMaxHeight().padding(start = 30.u, end = 34.u), verticalAlignment = Alignment.CenterVertically) {
                if (conOk) {
                    Box(Modifier.size(76.u, 52.u).border(2.u, C.lime, RoundedCornerShape(2.u)), contentAlignment = Alignment.Center) {
                        Texto("OK", font(27, Face.BOLD, C.lime))
                    }
                    Spacer(Modifier.width(24.u))
                } else {
                    Icono("pause", C.text, Modifier.size(40.u))
                    Spacer(Modifier.width(20.u))
                }
                Texto(marquee(texto), font(48, Face.DISPLAY), Modifier.widthIn(max = 900.u))
            }
            if (conOk) Box(Modifier.align(Alignment.BottomStart).padding(start = 18.u, end = 18.u, bottom = 12.u).fillMaxWidth().height(6.u)) {
                Box(Modifier.fillMaxHeight().fillMaxWidth(resto.coerceIn(0f, 1f)).background(C.lime))
            }
        }
    }
}

/** El nombre del capítulo de YouTube que empieza: unos segundos, abajo a la izquierda; solo informa. */
@Composable
private fun NotaCapituloUI(n: app.onetv.tv.NotaCapitulo) {
    Box(Modifier.fillMaxSize().padding(start = 110.u, bottom = 110.u), contentAlignment = Alignment.BottomStart) {
        Column(Modifier.height(128.u).background(C.overlay).padding(horizontal = 32.u).padding(top = 22.u)) {
            Texto(n.head, font(27, Face.BOLD, C.muted))
            Texto(n.title, font(38, Face.BOLD), Modifier.padding(top = 4.u).widthIn(max = 1100.u))
        }
    }
}

/** La barra de avance del reproductor: lo visto en limón, las marcas de los capítulos y el punto. */
@Composable
private fun Barra(p: Reproductor, at: Double, d: Double, modifier: Modifier, alto: Int, conPunto: Boolean) {
    val f = if (d > 0) (at / d).toFloat().coerceIn(0f, 1f) else 0f
    Box(modifier.size(1636.u, 28.u)) {
        Box(Modifier.offset(0.u, ((28 - alto) / 2).u).size(1636.u, alto.u).background(C.raise3)) {
            Box(Modifier.fillMaxHeight().fillMaxWidth(f).background(C.lime))
            if (d > 0) for (c in p.capitulos.drop(1)) {
                Box(Modifier.offset((1636 * c.start / d - 3).toInt().u, 0.u).size(6.u, alto.u).background(C.bg))
            }
        }
        if (conPunto && d > 0 && p.req?.live != true) {
            Box(Modifier.offset((1636 * f - 14).toInt().u, 0.u).size(28.u).clip(CircleShape).background(C.lime))
        }
    }
}

/** El panel (▼ con la barra a la vista): lo que se ve, su barra, los botones, la fila de reproducción y lo visto. */
@Composable
private fun PanelReproductor(e: Estado, p: Reproductor) {
    val r = p.req ?: return
    val at = p.posicion
    val d = if (r.live) 0.0 else if (p.duracion > 0) p.duracion else r.duration
    Box(Modifier.fillMaxSize()) {
        Box(Modifier.fillMaxSize().background(C.scrim))
        Box(Modifier.offset(0.u, 270.u).fillMaxWidth().height(810.u).background(C.raise2)) {
            Box(Modifier.fillMaxWidth().height(2.u).background(C.edge))
            Texto(r.title, font(38, Face.BOLD), Modifier.offset(110.u, 30.u).width(1300.u))
            Texto(if (d > 0) fmtClock(at) + " / " + fmtClock(d) else fmtClock(at), font(32, color = C.textSoft),
                Modifier.offset(1410.u, 34.u).width(400.u), align = TextAlign.End)
            Texto(textoCapitulo(p, at), font(32, Face.BOLD, C.lime), Modifier.offset(110.u, 82.u).width(1700.u))
            Icono(if (p.pausado) "play" else "pause", C.text, Modifier.offset(110.u, 125.u).size(40.u))
            Barra(p, at, d, Modifier.offset(174.u, 124.u), alto = 12, conPunto = p.panelSeccion == 0)
            Row(Modifier.offset(110.u, 184.u), horizontalArrangement = Arrangement.spacedBy(16.u)) {
                p.panelBotones.forEachIndexed { i, b ->
                    BotonUI(b, p.panelSeccion == 1 && p.panelIndex[1] == i, alto = 64, letra = 27, fondo = C.raise3)
                }
            }
            Texto("FILA DE REPRODUCCIÓN", font(27, Face.BOLD, C.muted), Modifier.offset(110.u, 278.u))
            val fila = p.panelFila()
            if (fila.isEmpty()) Texto("La fila está vacía. Desde el inicio, OK sostenido sobre un video lo agrega.",
                font(27, color = C.muted), Modifier.offset(110.u, 326.u).width(1700.u))
            else FilaPanel(e, fila, if (p.panelSeccion == 2) p.panelIndex[2] else -1, Modifier.offset(110.u, 318.u))
            val vistos = p.panelVistos()
            if (vistos.isNotEmpty()) {
                Texto("VISTOS HACE POCO", font(27, Face.BOLD, C.muted), Modifier.offset(110.u, 518.u))
                FilaPanel(e, vistos, if (p.panelSeccion == 3) p.panelIndex[3] else -1, Modifier.offset(110.u, 558.u))
            }
            val hint = when (p.panelSeccion) {
                1 -> "OK: elegir   ·   arriba: volver a la barra   ·   Atrás: ocultar"
                2 -> "OK: verlo ya (sale de la fila)   ·   Atrás: ocultar"
                else -> "OK: verlo ya   ·   Atrás: ocultar"
            }
            Texto(hint, font(27, color = C.muted), Modifier.offset(110.u, 762.u).width(1700.u))
        }
    }
}

@Composable
private fun FilaPanel(e: Estado, list: List<Entry>, foco: Int, modifier: Modifier) {
    val first = if (foco > 4) foco - 4 else 0
    Row(modifier, horizontalArrangement = Arrangement.spacedBy(24.u)) {
        for (i in first until minOf(list.size, first + 7)) key(i, list[i].kind, list[i].id) {
            val en = list[i]
            Column(Modifier.width(240.u)) {
                Box(Modifier.size(240.u, 135.u).background(C.raise3)) {
                    ImagenRed(e.datos?.abs(en.thumb), Modifier.fillMaxSize(), maxLado = 320)
                    if (i == foco) Box(Modifier.fillMaxSize().border(5.u, C.lime))
                }
                Texto(en.title, font(24, Face.BOLD, if (i == foco) C.lime else C.textSoft), Modifier.padding(top = 8.u))
            }
        }
    }
}

/** Escuchando música: la portada y los datos de la canción. */
@Composable
private fun Escuchando(p: Reproductor) {
    val r = p.req ?: return
    Box(Modifier.fillMaxSize().background(C.bg)) {
        Box(Modifier.offset(110.u, 150.u).size(560.u).background(C.raise3)) {
            ImagenRed(r.art, Modifier.fillMaxSize(), maxLado = 600)
        }
        var kicker = "ESCUCHANDO"
        if (r.position.isNotEmpty()) kicker += "   ·   " + r.position
        Texto(kicker, font(27, Face.BOLD, C.lime), Modifier.offset(740.u, 190.u))
        Texto(r.title, font(72, Face.DISPLAY), Modifier.offset(740.u, 236.u).width(1070.u), maxLines = 2)
        Texto(r.artist, font(38, Face.BOLD), Modifier.offset(740.u, 420.u).width(1070.u))
        Texto(r.album, font(32, color = C.textSoft), Modifier.offset(740.u, 474.u).width(1070.u))
        if (r.nextTitle.isNotEmpty()) Texto("Sigue: " + r.nextTitle, font(27, color = C.muted), Modifier.offset(740.u, 620.u).width(1070.u))
    }
}

/** Lo siguiente: qué viene, el título, los segundos que faltan y las teclas dibujadas. */
@Composable
private fun Siguiente(s: app.onetv.tv.Siguiente) {
    Box(Modifier.fillMaxSize().background(C.bg)) {
        Box(Modifier.offset(110.u, 270.u).size(960.u, 540.u).background(C.raise3)) {
            Texto(marquee(s.title), font(72, Face.BLACK, C.textSoft), Modifier.align(Alignment.BottomStart).padding(24.u), maxLines = 3)
            ImagenRed(s.thumb, Modifier.fillMaxSize(), maxLado = 960)
        }
        // Si se saltó un video (ya no está en YouTube): el motivo, en guinda claro, arriba de lo siguiente.
        if (s.nota.isNotEmpty()) Texto(s.nota, font(32, Face.BOLD, C.guindaLight), Modifier.offset(1130.u, 150.u).width(690.u), maxLines = 3)
        Column(Modifier.offset(1124.u, 300.u).width(700.u), verticalArrangement = Arrangement.spacedBy(16.u)) {
            Texto(marquee(s.what), font(48, Face.DISPLAY, C.muted))
            Texto(s.title, font(38, Face.BOLD), maxLines = 2)
            Row(verticalAlignment = Alignment.Bottom) {
                Texto("${s.segundos}", font(110, Face.BLACK))
                Texto(if (s.segundos == 1) "segundo" else "segundos", font(32, color = C.muted), Modifier.padding(start = 16.u, bottom = 18.u))
            }
            Box(Modifier.size(690.u, 6.u).background(C.raise3)) {
                Box(Modifier.fillMaxHeight().fillMaxWidth(s.segundos / s.total.coerceAtLeast(1).toFloat()).background(C.lime))
            }
            Row(Modifier.padding(top = 24.u), verticalAlignment = Alignment.CenterVertically) {
                Tecla("OK", C.lime)
                Texto("Verlo ya", font(32), Modifier.padding(start = 16.u, end = 56.u))
                Tecla("Atrás", C.edge)
                Texto(s.back, font(32), Modifier.padding(start = 16.u))
            }
        }
    }
}

@Composable
private fun Tecla(text: String, color: Color) {
    Box(Modifier.height(52.u).border(2.u, color, RoundedCornerShape(2.u)).padding(horizontal = 16.u), contentAlignment = Alignment.Center) {
        Texto(text, font(27, Face.BOLD, if (color == C.lime) C.lime else C.text))
    }
}
