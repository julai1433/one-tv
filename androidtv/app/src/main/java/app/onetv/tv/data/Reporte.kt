package app.onetv.tv.data

import org.json.JSONObject

/**
 * El aviso de avance que la TV manda al servidor (POST /api/progress), con el mismo formato que el Roku
 * (roku/components/Player.brs, report): así «Seguir viendo», la barra «En la TV» de la web y su control funcionan igual.
 *
 * ev: start | tick | stop | end. state: play | pause | buffer. sub = -1: sin subtítulos.
 * song: con música, el lugar de la canción (desde 0) y cuántas hay; la música nunca deja avance guardado.
 */
data class ProgressReport(
    val id: String,
    val position: Double,
    val duration: Double,
    val event: String,
    val audio: Int,
    val sub: Int,
    val state: String,
    val deviceId: String,
    val songIndex: Int = -1,
    val songCount: Int = 0,
) {
    fun toJson(): JSONObject {
        val body = JSONObject()
        body.put("id", id)
        body.put("p", position)
        body.put("d", duration)
        body.put("ev", event)
        body.put("audio", audio)
        body.put("sub", sub)
        body.put("state", state)
        body.put("device_id", deviceId)
        // Sin «device», igual que el Roku: el servidor entiende «tv» (lo que se ve en la TV de la casa).
        if (songCount > 0) body.put("song", JSONObject().put("i", songIndex).put("n", songCount))
        return body
    }
}

/** El estado del reproductor en las palabras del reporte. */
fun reportState(playing: Boolean, buffering: Boolean) = when {
    buffering -> "buffer"
    playing -> "play"
    else -> "pause"
}
