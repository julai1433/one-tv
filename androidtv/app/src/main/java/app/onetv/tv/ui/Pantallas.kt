package app.onetv.tv.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.zIndex
import app.onetv.tv.Conexion
import app.onetv.tv.Estado
import app.onetv.tv.Fila
import app.onetv.tv.Seccion
import app.onetv.tv.Vacio
import app.onetv.tv.VistaBuscar
import app.onetv.tv.VistaCuadricula
import app.onetv.tv.VistaFilas
import app.onetv.tv.control.codigoLegible
import app.onetv.tv.opcionesElegir
import app.onetv.tv.data.marquee

/** Toda la app: el contenido, el menú lateral y lo que se abre encima (ficha, reproductor, listas, avisos). */
@Composable
fun AppUI(e: Estado, video: @Composable () -> Unit) {
    Box(Modifier.fillMaxSize().background(C.bg)) {
        if (e.conexion != Conexion.LISTA) {
            PantallaConexion(e)
        } else {
            if (e.sinServidor) PantallaSinServidor(e)
            else when (val v = e.vista) {
                is VistaFilas -> FilasUI(e, v)
                is VistaCuadricula -> CuadriculaUI(e, v)
                is VistaBuscar -> BuscarUI(e, v)
                null -> Texto(marquee(e.seccion.text), font(72, Face.BLACK), Modifier.offset(168.u, 26.u))
            }
            MenuLateral(e)
            e.ficha?.let { FichaUI(e, it) }
            if (e.ayuda) AyudaUI()
        }
        // El reproductor siempre está (para no rearmar el video), visible solo cuando se reproduce algo.
        Box(Modifier.fillMaxSize().zIndex(if (e.reproductor.visible) 5f else -1f)) {
            if (e.reproductor.visible) PantallaReproductor(e, video)
        }
        e.lista?.let { Box(Modifier.zIndex(6f)) { ListaUI(e, it) } }
        if (e.listaNueva != null) Box(Modifier.zIndex(6.5f)) { ListaNuevaUI(e) }
        if (e.aviso.isNotEmpty() && e.conexion != Conexion.ELEGIR) Box(Modifier.fillMaxSize().zIndex(7f), contentAlignment = Alignment.BottomCenter) {
            Box(Modifier.padding(bottom = 64.u).background(C.raise2).padding(horizontal = 28.u, vertical = 18.u)) {
                Texto(e.aviso, font(32, color = if (e.avisoError) C.guindaLight else C.text), maxLines = 2)
            }
        }
        if (e.codigo.isNotEmpty()) Box(Modifier.fillMaxSize().zIndex(8f)) { CodigoUI(e.codigo) }
    }
}

/** El código para cambiar la configuración desde otro aparato (como el del Roku, MainScene.xml): encima de todo. */
@Composable
fun CodigoUI(codigo: String) {
    Box(Modifier.fillMaxSize().background(C.scrim)) {
        Box(Modifier.offset(432.u, 300.u).size(1056.u, 480.u).background(C.raise2))
        Texto(codigoLegible(codigo), font(110, Face.BLACK, C.lime), Modifier.offset(432.u, 360.u).width(1056.u), align = TextAlign.Center)
        Texto("Código para cambiar la configuración de One TV desde otro aparato", font(38),
            Modifier.offset(512.u, 540.u).width(896.u), maxLines = 2, align = TextAlign.Center)
        Texto("OK o Atrás: cerrar", font(27, color = C.muted), Modifier.offset(432.u, 690.u).width(1056.u), align = TextAlign.Center)
    }
}

// ---------- menú lateral ----------

/** Cerrado: solo íconos, el de la sección actual en limón. Abierto: nombres, la opción con el foco en relleno limón,
 *  el estado de la computadora en palabras y el contenido detrás en penumbra. */
@Composable
fun MenuLateral(e: Estado) {
    val open = e.menuAbierto
    Box(Modifier.fillMaxSize()) {
        if (open) {
            Box(Modifier.fillMaxSize().background(C.scrim))
            Box(Modifier.width(560.u).fillMaxHeight().background(C.raise2))
            ImagenApp("marca", Modifier.offset(48.u, 46.u).size(60.u))
            Texto("ONE TV", font(48, Face.BLACK), Modifier.offset(124.u, 48.u))
        } else {
            Box(Modifier.width(120.u).fillMaxHeight().background(C.raise1))
        }
        Seccion.entries.forEachIndexed { i, s ->
            val current = s == e.seccion
            val focused = open && i == e.menuIndex
            val color = when {
                focused -> C.onLime
                current -> C.lime
                else -> C.text
            }
            val y = 176 + i * 80   // nueve secciones: caben sobre el estado de la computadora
            if (open) {
                Box(Modifier.offset(28.u, y.u).size(504.u, 72.u).clip(RoundedCornerShape(2.u)).background(if (focused) C.lime else Color.Transparent))
                Icono(s.icon, color, Modifier.offset(48.u, (y + 14).u).size(44.u))
                Box(Modifier.offset(112.u, y.u).height(72.u), contentAlignment = Alignment.CenterStart) {
                    Texto(s.text, font(32, Face.MEDIUM, color))
                }
                if (s == Seccion.FILA && (e.lib?.queue?.size ?: 0) > 0) {
                    Box(Modifier.offset(440.u, y.u).size(72.u), contentAlignment = Alignment.CenterEnd) {
                        Texto("${e.lib?.queue?.size}", font(27, Face.BOLD, if (focused) C.onLime else C.muted))
                    }
                }
            } else {
                Icono(s.icon, color, Modifier.offset(38.u, (y + 14).u).size(44.u))
            }
        }
        if (open) {
            // El estado de la computadora en palabras (DESIGN.md, pieza 3).
            Row(Modifier.offset(48.u, 900.u).height(56.u), verticalAlignment = Alignment.CenterVertically) {
                Icono("laptop", C.muted, Modifier.size(32.u))
                Texto("COMPUTADORA", font(27, Face.BOLD, C.muted), Modifier.padding(start = 12.u))
                val (word, color) = if (e.sinServidor) "NO RESPONDE" to C.guindaLight else "CONECTADA" to C.lime
                Texto(word, font(38, Face.DISPLAY, color), Modifier.padding(start = 14.u))
            }
            if (e.nombreServidor.isNotEmpty()) Texto(e.nombreServidor, font(27, color = C.textSoft), Modifier.offset(92.u, 950.u).width(440.u))
            Texto("OK: abrir   ·   ›: volver al contenido", font(27, color = C.muted), Modifier.offset(48.u, 990.u).width(500.u))
        }
    }
}

// ---------- filas ----------

/** Filas de tarjetas (Inicio, YouTube, Música, una serie). La fila elegida queda siempre arriba y bajo ella va la
 *  línea con lo que dice la tarjeta. */
@Composable
fun FilasUI(e: Estado, v: VistaFilas) {
    val (r0, c0) = e.focoFilas[v.key] ?: (0 to 0)
    val enBoton = r0 < 0 && v.topButton.isNotEmpty()
    val r = r0.coerceIn(0, (v.filas.size - 1).coerceAtLeast(0))
    val activo = !e.menuAbierto && e.ficha == null
    Box(Modifier.fillMaxSize()) {
        Texto(marquee(v.header), font(72, Face.BLACK), Modifier.offset(168.u, 26.u).width(1600.u))
        if (v.topButton.isNotEmpty()) Box(Modifier.offset(168.u, 128.u)) {
            BotonUI(app.onetv.tv.Boton("top", v.topButton, "search"), enBoton && activo)
        }
        Column(Modifier.offset(168.u, (if (v.topButton.isNotEmpty()) 250 else 150).u)) {
            for (ri in r until v.filas.size) {
                val fila = v.filas[ri]
                val focused = ri == r
                val c = if (fila.tarjetas.isEmpty()) 0 else c0.coerceIn(0, fila.tarjetas.size - 1)
                FilaUI(fila, if (focused && !enBoton) c else -1, activo && !enBoton)
                if (focused && !enBoton) {
                    val info = fila.tarjetas.getOrNull(c)?.info.orEmpty()
                    Box(Modifier.height(96.u).padding(top = 18.u)) {
                        if (activo) Texto(info, font(32, color = C.textSoft), Modifier.width(1640.u))
                    }
                } else Spacer(Modifier.height(56.u))
            }
        }
    }
}

@Composable
fun FilaUI(fila: Fila, foco: Int, activo: Boolean) {
    Column {
        Texto(fila.title, font(38, Face.BOLD), Modifier.height(58.u))
        if (fila.tarjetas.isEmpty()) {
            VacioUI(fila.vacio ?: Vacio("Nada por aquí", ""), fila.forma, foco >= 0 && activo)
            return@Column
        }
        val slot = fila.forma.w + fila.forma.gap
        val visibles = (1752 + fila.forma.gap) / slot
        val start = if (foco < 0) 0 else (foco - visibles + 1).coerceAtLeast(0)
        Row(horizontalArrangement = Arrangement.spacedBy(fila.forma.gap.u), modifier = Modifier.height(fila.forma.slotH.u)) {
            for (i in start until minOf(fila.tarjetas.size, start + visibles + 1)) {
                // Cada tarjeta ligada a su elemento (no a su lugar en la fila): su imagen no pasa a otra al correrse.
                key(fila.tarjetas[i].id) { TarjetaUI(fila.tarjetas[i], fila.forma, foco == i && activo, atenuar = activo) }
            }
        }
    }
}

// ---------- cuadrícula ----------

@Composable
fun CuadriculaUI(e: Estado, v: VistaCuadricula) {
    val n = v.tarjetas.size
    val cols = e.columnas(v)
    val iRaw = e.focoCuadricula[v.key] ?: (if (n == 0 && v.chips.isNotEmpty()) -1 else 0)
    val i = if (iRaw >= n) n - 1 else iRaw
    val activo = !e.menuAbierto && e.ficha == null
    Box(Modifier.fillMaxSize()) {
        Row(Modifier.offset(168.u, 26.u), verticalAlignment = Alignment.Bottom) {
            Texto(marquee(v.header), font(72, Face.BLACK), Modifier.padding(end = 22.u))
            Texto(v.count, font(32, color = C.muted), Modifier.padding(bottom = 10.u))
        }
        if (v.chips.isNotEmpty()) {
            val chipFoco = if (i == -1 && activo) (e.focoChip[v.key] ?: v.chips.indexOfFirst { it.id == v.chipValue }).coerceIn(0, v.chips.size - 1) else -1
            Row(Modifier.fillMaxWidth().padding(top = 40.u, end = 80.u), horizontalArrangement = Arrangement.End) {
                Row(horizontalArrangement = Arrangement.spacedBy(12.u)) {
                    v.chips.forEachIndexed { k, b ->
                        if (v.chipsSegmentos) Segmento(b, k == chipFoco, b.id == v.chipValue)
                        else BotonUI(b, k == chipFoco, principal = v.chipsPrincipal && k == 0)
                    }
                }
            }
        }
        val info = v.tarjetas.getOrNull(i)?.info.orEmpty()
        if (activo && i >= 0) Texto(info, font(32, color = C.textSoft), Modifier.offset(168.u, 124.u).width(1640.u))
        if (n == 0) {
            Box(Modifier.offset(168.u, 184.u)) { VacioUI(v.vacio, v.forma, activo, grande = true) }
            return@Box
        }
        val rowH = v.forma.slotH + 20
        val focusRow = if (i < 0) 0 else i / cols
        val firstRow = (focusRow - 2).coerceAtLeast(0)
        Column(Modifier.offset(168.u, 184.u), verticalArrangement = Arrangement.spacedBy(20.u)) {
            for (row in firstRow until minOf((n + cols - 1) / cols, firstRow + 4)) {
                Row(horizontalArrangement = Arrangement.spacedBy(24.u), modifier = Modifier.height((rowH - 20).u)) {
                    for (k in row * cols until minOf(n, row * cols + cols)) {
                        key(v.tarjetas[k].id) { TarjetaUI(v.tarjetas[k], v.forma, k == i && activo, atenuar = activo && i >= 0) }
                    }
                }
            }
        }
    }
}

// ---------- ficha ----------

@Composable
fun FichaUI(e: Estado, f: app.onetv.tv.Ficha) {
    Box(Modifier.fillMaxSize().background(C.bg)) {
        Box(Modifier.offset(560.u, 0.u).size(1360.u, 765.u)) {
            ImagenRed(f.image, Modifier.fillMaxSize(), maxLado = 1280)
            Box(Modifier.fillMaxSize().background(Brush.horizontalGradient(0f to C.bg, 0.6f to Color.Transparent)))
            Box(Modifier.fillMaxSize().background(Brush.verticalGradient(0.5f to Color.Transparent, 1f to C.bg)))
        }
        Column(Modifier.offset(110.u, 96.u).width(1300.u)) {
            val big = f.title.length <= 22
            Texto(marquee(f.title), font(if (big) 110 else 72, Face.BLACK), maxLines = 2)
            if (f.subtitle.isNotEmpty()) Texto(f.subtitle, font(38, Face.BOLD), Modifier.padding(top = 20.u))
            Row(Modifier.padding(top = 22.u), verticalAlignment = Alignment.CenterVertically) {
                Texto(listOf(f.meta, e.fichaWhen).filter { it.isNotEmpty() }.joinToString("   ·   "), font(32, color = C.textSoft))
                if (f.spanish) EtiquetaEspanol(Modifier.padding(start = 22.u), size = 27)
            }
            if (f.langs.isNotEmpty()) Row(Modifier.padding(top = 22.u), verticalAlignment = Alignment.CenterVertically) {
                Icono("audio", C.text, Modifier.size(34.u))
                Texto(f.langs, font(32), Modifier.padding(start = 14.u).width(1150.u))
            }
            if (e.fichaDesc.isNotEmpty()) Texto(e.fichaDesc, font(32, color = C.textSoft), Modifier.padding(top = 22.u).width(1150.u), maxLines = 3)
        }
        val libre = e.lista == null && e.idioma == null
        FilaBotones(f.buttons, if (libre) e.fichaBoton else -1, Modifier.offset(110.u, 740.u))
        if (e.fichaMensaje.isNotEmpty() && e.idioma == null) Texto(e.fichaMensaje, font(32, Face.BOLD, if (e.fichaMensajeError) C.guindaLight else C.lime),
            Modifier.offset(110.u, 840.u).width(1700.u))
        Texto("OK: elegir   ·   mantén OK: sinopsis completa   ·   Atrás: volver", font(27, color = C.muted), Modifier.offset(110.u, 990.u))
        e.idioma?.let { IdiomaUI(e, it) }
        if (e.sinopsis) SinopsisUI(e, f)
        if (e.qr) QrUI(e, f)
    }
}

// ---------- sin la computadora ----------

/** «No encuentro la computadora»: la forma de Inicio con huecos, qué revisar y un botón para buscar ya. */
@Composable
fun PantallaSinServidor(e: Estado) {
    Box(Modifier.fillMaxSize()) {
        Texto("INICIO", font(72, Face.BLACK), Modifier.offset(168.u, 26.u))
        Column(Modifier.offset(168.u, 184.u).width(1672.u), verticalArrangement = Arrangement.spacedBy(16.u)) {
            Texto("NO ENCUENTRO LA COMPUTADORA", font(72, Face.BLACK, C.guindaLight))
            Texto("Revisa que esté encendida, despierta y conectada al mismo Wi-Fi que la TV. La sigo buscando sola cada 5 segundos.",
                font(38, color = C.textSoft), maxLines = 3)
            Texto("Dirección: " + e.direccion.removePrefix("http://"), font(27, color = C.muted))
            Spacer(Modifier.height(12.u))
            Row(horizontalArrangement = Arrangement.spacedBy(16.u)) {
                BotonUI(app.onetv.tv.Boton("retry", "Buscar ahora", "refresh"), foco = !e.menuAbierto && e.conexionBoton == 0, principal = true)
                BotonUI(app.onetv.tv.Boton("otra", "Elegir otra computadora", "laptop"), foco = !e.menuAbierto && e.conexionBoton == 1)
            }
        }
    }
}

/** Al abrir: buscando la computadora en la red de la casa; si no está, buscar otra vez o escribir la dirección. */
@Composable
fun PantallaConexion(e: Estado) {
    Box(Modifier.fillMaxSize()) {
        Row(Modifier.offset(110.u, 96.u), verticalAlignment = Alignment.CenterVertically) {
            ImagenApp("marca", Modifier.size(72.u))
            Texto("ONE TV", font(72, Face.BLACK), Modifier.padding(start = 24.u))
        }
        val y = if (e.conexion == Conexion.ELEGIR) 220 else 300   // la lista necesita más alto
        Column(Modifier.offset(110.u, y.u).width(1500.u), verticalArrangement = Arrangement.spacedBy(20.u)) {
            when (e.conexion) {
                Conexion.BUSCANDO -> {
                    Texto("BUSCANDO LA COMPUTADORA", font(72, Face.BLACK))
                    Texto("Estoy buscando One TV en la red de la casa. Tarda unos segundos.", font(38, color = C.textSoft), maxLines = 2)
                }
                Conexion.NO_ENCONTRADA -> {
                    Texto("NO ENCUENTRO LA COMPUTADORA", font(72, Face.BLACK, C.guindaLight))
                    Texto("Revisa que la computadora con One TV esté encendida y conectada al mismo Wi-Fi que la TV. La sigo buscando sola.",
                        font(38, color = C.textSoft), maxLines = 3)
                    Spacer(Modifier.height(20.u))
                    Row(horizontalArrangement = Arrangement.spacedBy(16.u)) {
                        BotonUI(app.onetv.tv.Boton("buscar", "Buscar otra vez", "refresh"), e.conexionBoton == 0, principal = true)
                        BotonUI(app.onetv.tv.Boton("escribir", "Escribir la dirección", "laptop"), e.conexionBoton == 1)
                    }
                }
                Conexion.ESCRIBIR -> CampoDireccion(e)
                Conexion.ELEGIR -> ElegirComputadora(e)
                Conexion.LISTA -> {}
            }
        }
        val pie = when {
            e.conexion == Conexion.ESCRIBIR -> "OK: conectar   ·   Atrás: volver"
            e.conexion == Conexion.ELEGIR && e.lib != null -> "OK: elegir   ·   Atrás: seguir con la de ahora"
            else -> "OK: elegir   ·   Atrás: salir"
        }
        Texto(pie, font(27, color = C.muted), Modifier.offset(110.u, 990.u))
    }
}

/** «Elige la computadora»: las que tienen One TV en la casa, con su nombre, cuántos videos tienen y su dirección (la
 *  opción con el foco en relleno limón, como las listas para elegir), y al final buscar otra vez o escribir la dirección. */
@Composable
fun ElegirComputadora(e: Estado) {
    Texto("ELIGE LA COMPUTADORA", font(72, Face.BLACK))
    val nota = when {
        e.buscandoTodas -> "Buscando las computadoras con One TV de la casa. Tarda unos segundos."
        e.encontradas.isEmpty() -> "No encontré ninguna computadora con One TV. Revisa que esté encendida y en el mismo Wi-Fi que la TV."
        e.notaElegir.isNotEmpty() -> e.notaElegir
        e.lib == null -> "Hay más de una computadora con One TV en la casa. ¿Cuál quieres ver en esta TV?"
        else -> "Las computadoras con One TV de la casa. La que elijas se recuerda."
    }
    Texto(nota, font(38, color = C.textSoft), maxLines = 2)
    if (e.buscandoTodas) return
    val opciones = e.opcionesElegir()
    val rowH = 104
    val gap = 10
    val viewH = 4 * rowH + 3 * gap   // caben cuatro; con más, se corre para que se vea la elegida
    val k = e.elegirIndex.coerceIn(0, opciones.size - 1)
    val scroll = (k * (rowH + gap) + rowH - viewH).coerceAtLeast(0)
    Box(Modifier.padding(top = 8.u).size(1200.u, viewH.u).clipToBounds()) {
        Column(Modifier.offset(0.u, (-scroll).u), verticalArrangement = Arrangement.spacedBy(gap.u)) {
            opciones.forEachIndexed { i, o ->
                val lit = i == k
                Box(Modifier.size(1200.u, rowH.u).clip(RoundedCornerShape(2.u)).background(if (lit) C.lime else Color.Transparent)) {
                    Box(Modifier.offset(12.u, 12.u).size(142.u, 80.u).background(C.raise3), contentAlignment = Alignment.Center) {
                        Icono(o.icon, C.text, Modifier.size(48.u))
                    }
                    if (o.line.isEmpty()) {
                        Box(Modifier.offset(178.u, 0.u).size(998.u, rowH.u), contentAlignment = Alignment.CenterStart) {
                            Texto(o.title, font(38, Face.BOLD, if (lit) C.onLime else C.text))
                        }
                    } else {
                        Texto(o.title, font(38, Face.BOLD, if (lit) C.onLime else C.text), Modifier.offset(178.u, 10.u).width(998.u))
                        Texto(o.line, font(27, color = if (lit) C.onLime else C.muted), Modifier.offset(178.u, 62.u).width(998.u))
                    }
                }
            }
        }
    }
}

/** Campo de texto (DESIGN.md, pieza 1): sin caja, línea inferior que se vuelve limón al escribir, letra grande. */
@Composable
fun CampoDireccion(e: Estado) {
    var text by remember { mutableStateOf(e.direccion.removePrefix("http://")) }
    var error by remember { mutableStateOf("") }
    val focus = remember { FocusRequester() }
    Texto("ESCRIBE LA DIRECCIÓN", font(72, Face.BLACK))
    Texto("La muestra la computadora en la ventana de One TV (por ejemplo 192.0.2.5).", font(38, color = C.textSoft), maxLines = 2)
    Spacer(Modifier.height(20.u))
    BasicTextField(
        value = text, onValueChange = { text = it; error = "" }, singleLine = true,
        textStyle = font(44, Face.MEDIUM), cursorBrush = SolidColor(C.lime),
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri, imeAction = ImeAction.Go),
        keyboardActions = KeyboardActions(onGo = { e.probarEscrita(text) { error = it.orEmpty() } }),
        modifier = Modifier.width(900.u).focusRequester(focus),
        decorationBox = { inner ->
            Column {
                Box(Modifier.padding(vertical = 10.u)) {
                    if (text.isEmpty()) Texto("192.0.2.5", font(44, Face.MEDIUM, C.muted))
                    inner()
                }
                Box(Modifier.fillMaxWidth().height(2.u).background(C.lime))
            }
        },
    )
    if (error.isNotEmpty()) Texto(error, font(32, Face.BOLD, C.guindaLight), maxLines = 2)
    LaunchedEffect(Unit) { focus.requestFocus() }
}
