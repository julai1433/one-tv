package app.onetv.tv.ui

import android.content.res.AssetManager
import androidx.compose.runtime.Composable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.em
import androidx.compose.ui.unit.sp

// Todos los colores y la letra de la app, en un solo lugar (DESIGN.md y roku/components/Theme.brs: negro puro, grises
// neutros, limón y guinda; Big Shoulders Display para la marquesina y Archivo para lo demás).
object C {
    val bg = Color(0xFF000000)          // fondo de todo
    val raise1 = Color(0xFF0C0C0C)      // menú lateral cerrado
    val raise2 = Color(0xFF161616)      // paneles (idioma, menú abierto, avisos breves)
    val raise3 = Color(0xFF222222)      // pista de las barras de avance, pósters que faltan
    val line = Color(0xFF2E2E2E)        // líneas finas que solo separan
    val edge = Color(0xFF5E5E58)        // bordes de lo que se toca y huecos de una fila vacía
    val edgePanel = Color(0xFF686862)   // lo mismo encima de un panel raise2
    val scrim = Color(0xB8000000)       // velo detrás del menú abierto y de los paneles (72 %)
    val overlay = Color(0xEB000000)     // aviso encima del video (92 %)
    val badge = Color(0xD9000000)       // etiqueta de la duración sobre la miniatura (85 %)
    val text = Color(0xFFF2F2EE)        // texto principal
    val textSoft = Color(0xFFC9C9C2)    // sinopsis, línea de información
    val muted = Color(0xFF8C8C85)       // ayudas, conteos, textos de apoyo
    val lime = Color(0xFFA6E22E)        // foco, botón principal, barras de avance, sección actual
    val onLime = Color(0xFF0A0F00)      // letra e íconos encima del limón
    val guindaLight = Color(0xFFE0507F)  // problemas: NO RESPONDE, errores
    val guinda = Color(0xFF7A1535)      // fondo de la etiqueta «Español»
    val esText = Color(0xFFC4F05A)      // letra y contorno de la etiqueta «Español»
    val ytRed = Color(0xFFFF0033)       // solo lo de YouTube que se reconoce de un vistazo («EN VIVO»)
}

/** Las dos letras del proyecto, leídas de los archivos de roku/fonts (van dentro de la app). */
class Fonts(assets: AssetManager) {
    val archivo = FontFamily(
        Font("Archivo-Regular.ttf", assets, FontWeight.Normal),
        Font("Archivo-Medium.ttf", assets, FontWeight.Medium),
        Font("Archivo-Bold.ttf", assets, FontWeight.Bold),
    )
    val display = FontFamily(
        Font("BigShouldersDisplay-ExtraBold.ttf", assets, FontWeight.ExtraBold),
        Font("BigShouldersDisplay-Black.ttf", assets, FontWeight.Black),
    )
}

/**
 * Todo se mide como en la app del Roku: en puntos de una pantalla de 1920 × 1080. `perUnit` convierte uno de esos
 * puntos a dp según la pantalla real (en una TV de 1080p o 4K, 0,5 dp).
 */
class Scale(val perUnit: Float, val fontScale: Float)

val LocalScale = staticCompositionLocalOf { Scale(0.5f, 1f) }
val LocalFonts = staticCompositionLocalOf<Fonts> { error("Sin letras") }

/** Medida de la escala de la TV (sobre 1920 × 1080) en dp. */
val Number.u: Dp
    @Composable get() = (toFloat() * LocalScale.current.perUnit).dp

/** Tamaño de letra de la escala de la TV (27 mínimo · 32 · 38 · 48 · 72 · 110), sin el ajuste de letra del sistema. */
val Number.ut: TextUnit
    @Composable get() = (toFloat() * LocalScale.current.perUnit / LocalScale.current.fontScale).sp

enum class Face { REGULAR, MEDIUM, BOLD, DISPLAY, BLACK }

/** Igual que makeFont() del Roku: tamaño en la escala de la TV y cara de la letra. */
@Composable
fun font(size: Int, face: Face = Face.REGULAR, color: Color = C.text): TextStyle {
    val f = LocalFonts.current
    val (family, weight) = when (face) {
        Face.REGULAR -> f.archivo to FontWeight.Normal
        Face.MEDIUM -> f.archivo to FontWeight.Medium
        Face.BOLD -> f.archivo to FontWeight.Bold
        Face.DISPLAY -> f.display to FontWeight.ExtraBold
        Face.BLACK -> f.display to FontWeight.Black
    }
    val display = face == Face.DISPLAY || face == Face.BLACK
    return TextStyle(
        fontFamily = family, fontWeight = weight, fontSize = size.ut, color = color,
        letterSpacing = if (display) (-0.01).em else 0.em,
        lineHeight = (size * if (display) 1.0f else 1.25f).ut,
    )
}
