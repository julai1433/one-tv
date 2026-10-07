package app.onetv.tv.data

import java.util.Locale

// Textos y reglas compartidas, iguales a las de roku/components/Util.brs: tiempos, conteos, nombres de pistas y la
// regla para elegir el idioma al empezar un video. Sin nada de Android: se prueban en la computadora.

/** 1:02:03 o 4:05 (reloj del reproductor y duración de los videos de YouTube). */
fun fmtClock(seconds: Double): String {
    val total = seconds.toLong().coerceAtLeast(0)
    val h = total / 3600
    val m = (total % 3600) / 60
    val s = total % 60
    return if (h > 0) String.format(Locale.ROOT, "%d:%02d:%02d", h, m, s) else String.format(Locale.ROOT, "%d:%02d", m, s)
}

/** «1 h 59 min», «45 min», «menos de 1 min». */
fun fmtDuration(seconds: Double): String {
    val total = (seconds / 60).toInt()
    if (total < 1) return "menos de 1 min"
    if (total < 60) return "$total min"
    return "${total / 60} h ${total % 60} min"
}

/** «quedan 31 min» a partir de la posición y la duración. */
fun remainingText(p: Double, duration: Double): String {
    if (duration <= 0 || p <= 0) return ""
    val remaining = duration - p
    if (remaining < 60) return "queda menos de 1 min"
    return "quedan " + fmtDuration(remaining)
}

fun countText(n: Int, one: String, many: String) = if (n == 1) "1 $one" else "$n $many"

/** Texto de marquesina: en mayúsculas, también las vocales con acento y la ñ. */
fun marquee(text: String) = text.uppercase(Locale.forLanguageTag("es"))

/** Título sin el año del final: «Rocky (1976)» → «Rocky». */
fun bareTitle(title: String) = title.replace(Regex("""\s*\((19|20)\d\d\)\s*$"""), "")

fun yearOf(title: String) = Regex("""\(((19|20)\d\d)\)\s*$""").find(title)?.groupValues?.get(1) ?: ""

/** Nombre claro de una pista («Español (latino)»); con un servidor anterior, lo que va antes de « · ». */
fun trackName(t: Track): String {
    if (t.name.isNotEmpty()) return t.name
    if (t.label.isEmpty()) return "Pista"
    return t.label.substringBefore(" · ")
}

/** ¿Es la pista del idioma original? Sin el dato (servidor anterior): la predeterminada del archivo. */
fun isOriginal(it: Item, index: Int): Boolean {
    if (index !in it.audio.indices) return false
    val known = it.audio.any { a -> a.original != null }
    return if (known) it.audio[index].original == true else index == it.audioDefault
}

fun originalAudio(it: Item): Int {
    for (i in it.audio.indices) if (isOriginal(it, i)) return i
    return if (it.audioDefault in it.audio.indices) it.audioDefault else 0
}

/** Regla para EMPEZAR un video: "original" → la pista original; un idioma → la primera de ese idioma (si no hay, la original). */
fun chooseAudio(it: Item, prefs: Map<String, String>): Int {
    if (it.audio.isEmpty()) return 0
    val pref = prefs["audioLang"].orEmpty()
    if (pref.isNotEmpty() && pref != "original") {
        val i = it.audio.indexOfFirst { a -> a.lang == pref }
        if (i >= 0) return i
    }
    return originalAudio(it)
}

/** "off" → sin subtítulos; un idioma → el completo de ese idioma antes que los forzados; si no hay, ninguno. */
fun chooseSub(it: Item, prefs: Map<String, String>): Int {
    val pref = prefs["subLang"].orEmpty()
    if (pref.isEmpty() || pref == "off") return -1
    var forced = -1
    for ((i, s) in it.subs.withIndex()) {
        if (s.lang != pref) continue
        if (s.forced) {
            if (forced == -1) forced = i
        } else return i
    }
    return forced
}

/** Lo que se guarda al elegir una pista a mano: "original" si es la original, si no su idioma. */
fun audioPref(it: Item, index: Int) = if (isOriginal(it, index)) "original" else it.audio[index].lang

/** «Inglés, subtítulos: inglés» / «Español (latino)». */
fun langChoiceText(it: Item, audio: Int, sub: Int): String {
    var text = if (audio in it.audio.indices) trackName(it.audio[audio]) else ""
    if (sub in it.subs.indices) {
        if (text.isNotEmpty()) text += ", "
        text += "subtítulos: " + trackName(it.subs[sub]).lowercase()
    }
    return text
}

/** «Se oye en español e inglés   ·   Subtítulos en inglés». */
fun spokenText(it: Item): String {
    val names = uniqueLangs(it.audio)
    var text = if (names.isEmpty()) "Sin audio" else "Se oye en " + joinAnd(names)
    val subs = uniqueLangs(it.subs)
    text += if (subs.isNotEmpty()) "   ·   Subtítulos en " + joinAnd(subs) else "   ·   Sin subtítulos"
    return text
}

private fun uniqueLangs(tracks: List<Track>): List<String> {
    val out = LinkedHashSet<String>()
    val extras = Regex("""\s*\((original|forzados|SDH)\)|,\s*de internet|\s+\d+$""", RegexOption.IGNORE_CASE)
    for (t in tracks) {
        val name = if (t.lang.isEmpty() || t.lang == "und") {
            if (t.original == true) "el idioma original" else "un idioma sin identificar"
        } else {
            trackName(t).replace(extras, "").lowercase().trim()
                .replace("(latino)", "latino").replace("(", "").replace(")", "")
        }
        if (name.isNotEmpty()) out.add(name)
    }
    return out.toList()
}

/** «a, b y c»; «y» cambia a «e» antes de «i» o «hi» («español e inglés»). */
fun joinAnd(parts: List<String>): String {
    if (parts.isEmpty()) return ""
    if (parts.size == 1) return parts[0]
    val last = parts.last()
    val l = last.lowercase()
    val joiner = if (l.startsWith("i") || l.startsWith("í") || l.startsWith("hi")) " e " else " y "
    return parts.dropLast(1).joinToString(", ") + joiner + last
}

/** Iniciales de un canal o artista para su círculo: «NPR Music» → «NM». */
fun initialsOf(name: String): String {
    val out = name.trim().split(" ").filter { it.isNotEmpty() }.take(2).joinToString("") { it.take(1).uppercase() }
    return out.ifEmpty { "?" }
}

/** «hace 5 min», «hace 3 h», «hace 2 días», «hace 3 semanas», «hace 4 meses», «hace 2 años»; "" si no se sabe. */
fun agoText(epoch: Long, now: Long = System.currentTimeMillis() / 1000): String {
    if (epoch <= 0) return ""
    val secs = (now - epoch).coerceAtLeast(0)
    if (secs < 60) return "hace un momento"
    if (secs < 3600) return "hace ${secs / 60} min"
    if (secs < 86400) return "hace ${secs / 3600} h"
    val days = secs / 86400
    val (n, one, many) = when {
        days < 7 -> Triple(days, "día", "días")
        days < 30 -> Triple(days / 7, "semana", "semanas")
        days < 365 -> Triple((days / 30.4375).toLong(), "mes", "meses")
        else -> Triple(days / 365, "año", "años")
    }
    return if (n == 1L) "hace 1 $one" else "hace $n $many"
}

/** «5,2 mil viendo», «830 viendo»; "" si no se sabe. */
fun viewersText(n: Int): String {
    if (n <= 0) return ""
    if (n < 1000) return "$n viendo"
    val tenths = n / 100
    var text = (tenths / 10).toString()
    if (tenths % 10 != 0 && n < 100000) text += "," + (tenths % 10)
    return "$text mil viendo"
}

/** «12 sep 2023», en la hora de la TV. */
fun dateText(epoch: Long, zone: java.util.TimeZone = java.util.TimeZone.getDefault()): String {
    val c = java.util.Calendar.getInstance(zone)
    c.timeInMillis = epoch * 1000
    val months = listOf("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")
    return "${c.get(java.util.Calendar.DAY_OF_MONTH)} ${months[c.get(java.util.Calendar.MONTH)]} ${c.get(java.util.Calendar.YEAR)}"
}

/** Para la ficha: «Publicado el 12 sep 2023» si se sabe exacta, «Publicado hace 3 años» si es aproximada, "" si no. */
fun publishedText(epoch: Long, approx: Boolean, now: Long = System.currentTimeMillis() / 1000): String {
    if (epoch <= 0) return ""
    return if (approx) "Publicado " + agoText(epoch, now) else "Publicado el " + dateText(epoch)
}

/** Texto para buscar: minúsculas y sin acentos («Él» → «el»). */
fun plainText(text: String): String {
    var t = text.lowercase(Locale.forLanguageTag("es"))
    for ((a, b) in listOf("á" to "a", "é" to "e", "í" to "i", "ó" to "o", "ú" to "u", "ü" to "u", "ñ" to "n")) t = t.replace(a, b)
    return t
}
