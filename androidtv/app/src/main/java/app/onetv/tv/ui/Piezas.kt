package app.onetv.tv.ui

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
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
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicText
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.em
import app.onetv.tv.Boton
import app.onetv.tv.Estilo
import app.onetv.tv.Forma
import app.onetv.tv.Tarjeta
import app.onetv.tv.Vacio
import app.onetv.tv.data.fmtClock
import app.onetv.tv.data.marquee

// Las piezas que se repiten (DESIGN.md, «Piezas»): tarjetas, botones, etiquetas, barras y vacíos.

@Composable
fun Texto(text: String, style: TextStyle, modifier: Modifier = Modifier, maxLines: Int = 1, align: TextAlign? = null) {
    BasicText(text, modifier, style = if (align != null) style.copy(textAlign = align) else style, maxLines = maxLines, overflow = TextOverflow.Ellipsis)
}

/** Etiqueta «Español»: fondo guinda, letra y contorno limón claro, esquinas de 2. */
@Composable
fun EtiquetaEspanol(modifier: Modifier = Modifier, size: Int = 22) {
    Box(
        modifier.clip(RoundedCornerShape(2.u)).background(C.guinda).border(2.u, C.esText, RoundedCornerShape(2.u))
            .padding(horizontal = 10.u, vertical = 4.u),
    ) {
        Texto("ESPAÑOL", font(size, Face.BOLD, C.esText).copy(letterSpacing = 0.04.em))
    }
}

/** Barra de avance: pista raise-3 y avance limón, extremos rectos. */
@Composable
fun BarraAvance(f: Float, modifier: Modifier, alto: Int = 6) {
    Box(modifier.height(alto.u).background(C.raise3)) {
        Box(Modifier.fillMaxWidth(f.coerceIn(0f, 1f)).height(alto.u).background(C.lime))
    }
}

/** Duración de un video de YouTube sobre la miniatura (abajo a la derecha). */
@Composable
fun Duracion(seconds: Int, modifier: Modifier) {
    Box(modifier.clip(RoundedCornerShape(2.u)).background(C.badge).padding(horizontal = 8.u, vertical = 3.u)) {
        Texto(fmtClock(seconds.toDouble()), font(27, Face.BOLD))
    }
}

/**
 * Una tarjeta de las filas y las cuadrículas. Con el foco: marco limón de 5 pegado al borde, imagen al 106 % y el resto
 * al 55 % (el reflector). Transición de 120 ms.
 */
@Composable
fun TarjetaUI(t: Tarjeta, forma: Forma, foco: Boolean, atenuar: Boolean) {
    val scale by animateFloatAsState(if (foco) 1.06f else 1f, tween(120), label = "escala")
    val alpha by animateFloatAsState(if (atenuar && !foco) 0.55f else 1f, tween(120), label = "reflector")
    val w = forma.w
    val h = forma.h
    if (t.estilo == Estilo.CANAL) {
        Column(Modifier.width(w.u).alpha(alpha), horizontalAlignment = Alignment.CenterHorizontally) {
            Box(
                Modifier.size(w.u).graphicsLayer { scaleX = scale; scaleY = scale }.clip(CircleShape).background(C.raise3)
                    .then(if (foco) Modifier.border(5.u, C.lime, CircleShape) else Modifier),
                contentAlignment = Alignment.Center,
            ) {
                Texto(t.initials, font(48, Face.DISPLAY, C.textSoft))
                ImagenRed(t.image, Modifier.fillMaxSize().clip(CircleShape), maxLado = 256)
                if (foco) Box(Modifier.fillMaxSize().border(5.u, C.lime, CircleShape))
            }
            Texto(t.title, font(24, color = if (foco) C.lime else C.textSoft), Modifier.padding(top = 12.u), align = TextAlign.Center)
        }
        return
    }
    Column(Modifier.width(w.u).alpha(alpha)) {
        Box(
            Modifier.size(w.u, h.u).graphicsLayer { scaleX = scale; scaleY = scale }.clip(RoundedCornerShape(2.u)).background(C.raise3),
        ) {
            if (t.estilo == Estilo.POSTER || t.estilo == Estilo.YTCARD) {
                // Póster sin imagen: el título en letra de marquesina, nunca un rectángulo vacío.
                Texto(marquee(t.title), font(38, Face.DISPLAY, C.textSoft), Modifier.align(Alignment.BottomStart).padding(16.u), maxLines = 4)
            }
            ImagenRed(t.image, Modifier.fillMaxSize(), maxLado = if (t.estilo == Estilo.YTCARD) 640 else 400)
            if (t.estilo == Estilo.YTCARD) {
                Box(Modifier.fillMaxSize().background(Brush.verticalGradient(0.45f to Color.Transparent, 1f to C.bg)))
                Column(Modifier.align(Alignment.BottomStart).padding(14.u)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        ImagenApp("yt_mark", Modifier.size(42.u, 30.u))
                        Texto("YouTube", font(27, Face.BOLD), Modifier.padding(start = 8.u))
                    }
                    Texto(t.line2, font(27, color = C.textSoft), Modifier.padding(top = 4.u))
                }
            }
            if (t.spanish) EtiquetaEspanol(Modifier.padding(12.u))
            if (t.dur > 0) Duracion(t.dur, Modifier.align(if (t.estilo == Estilo.YTCARD) Alignment.TopEnd else Alignment.BottomEnd)
                .padding(bottom = if (t.progress > 0) 16.u else 10.u, end = 10.u, top = 10.u))
            if (t.progress > 0) BarraAvance(t.progress, Modifier.align(Alignment.BottomStart).fillMaxWidth())
            if (foco) Box(Modifier.fillMaxSize().border(5.u, C.lime, RoundedCornerShape(2.u)))
        }
        if (t.estilo == Estilo.VIDEO) {
            Texto(t.title, font(32, Face.BOLD, if (foco) C.text else C.text), Modifier.padding(top = 12.u))
            if (t.line2.isNotEmpty()) Texto(t.line2, font(27, color = C.textSoft), Modifier.padding(top = 4.u))
        }
    }
}

/** Botón: principal en limón (uno por pantalla), secundario con contorno; con el foco, relleno limón y letra negra. */
@Composable
fun BotonUI(b: Boton, foco: Boolean, principal: Boolean = false, alto: Int = 64, letra: Int = 32, fondo: Color? = null) {
    val shape = RoundedCornerShape(2.u)
    val color = if (foco) C.onLime else C.text
    val base = Modifier.height(alto.u).clip(shape)
    val m = when {
        foco -> base.background(C.lime)
        fondo != null -> base.background(fondo)
        principal -> base.border(2.u, C.lime, shape)
        else -> base.border(2.u, C.edge, shape)
    }
    Row(m.padding(horizontal = 24.u), verticalAlignment = Alignment.CenterVertically) {
        if (b.icon.isNotEmpty()) {
            Icono(b.icon, color, Modifier.size(36.u))
            Spacer(Modifier.width(14.u))
        }
        Texto(b.text, font(letra, Face.BOLD, color))
    }
}

/** Segmentos de un filtro (Todas · Con español · Sin español): el elegido en letra limón, el del foco en relleno limón. */
@Composable
fun Segmento(b: Boton, foco: Boolean, elegido: Boolean) {
    val shape = RoundedCornerShape(2.u)
    val base = Modifier.height(56.u).clip(shape)
    val m = if (foco) base.background(C.lime) else base.border(2.u, if (elegido) C.lime else C.edge, shape)
    Box(m.padding(horizontal = 22.u), contentAlignment = Alignment.Center) {
        Texto(b.text, font(27, Face.BOLD, if (foco) C.onLime else if (elegido) C.lime else C.text))
    }
}

/**
 * Vacío que enseña (DESIGN.md, pieza 4): la fila conserva su forma con huecos dibujados, y en sus primeros lugares la
 * frase de marquesina, la causa y la acción (con el foco, un botón limón).
 */
@Composable
fun VacioUI(v: Vacio, forma: Forma, foco: Boolean, grande: Boolean = false, ancho: Int = 1752) {
    val slotW = forma.w
    val h = forma.h
    Box(Modifier.width(ancho.u).height(h.u)) {
        Row(Modifier.fillMaxSize(), horizontalArrangement = Arrangement.spacedBy(forma.gap.u)) {
            var x = 0
            while (x + slotW <= ancho) {
                val shape = if (forma == Forma.CANAL) CircleShape else RoundedCornerShape(2.u)
                Box(Modifier.size(slotW.u, h.u).alpha(if (x < 760) 0f else 1f).border(2.u, C.edge, shape))
                x += slotW + forma.gap
            }
        }
        Column(Modifier.padding(start = 4.u, top = 4.u).width(740.u), verticalArrangement = Arrangement.spacedBy(10.u)) {
            Texto(marquee(v.phrase), font(if (grande) 72 else 48, if (grande) Face.BLACK else Face.DISPLAY), maxLines = 2)
            Texto(v.cause, font(if (grande) 38 else 32, color = C.textSoft), maxLines = 3)
            if (v.action.isNotEmpty()) {
                val shape = RoundedCornerShape(2.u)
                Row(
                    (if (foco) Modifier.clip(shape).background(C.lime) else Modifier).height(56.u).padding(horizontal = 20.u),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Texto(v.action, font(32, Face.BOLD, if (foco) C.onLime else C.lime))
                    Icono("chevron-right", if (foco) C.onLime else C.lime, Modifier.padding(start = 10.u).size(32.u))
                }
            }
        }
        if (foco && v.action.isEmpty()) Box(Modifier.offset((-12).u, (-12).u).size((ancho + 24).u, (h + 24).u).border(2.u, C.lime))
    }
}
