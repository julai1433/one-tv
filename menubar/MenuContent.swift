import SwiftUI

/// El menú que se abre al hacer clic en el ícono de la barra.
struct MenuContent: View {
    let monitor: ServiceMonitor

    var body: some View {
        Text(monitor.headline)
        if let status = monitor.status {
            StatusLines(status: status)
        }
        Divider()
        ServerToggle(monitor: monitor)
        Divider()
        Button("Abrir la página") { monitor.openPage() }
            .disabled(monitor.status == nil)
        if let iphone = monitor.status?.iphone {
            Button("Copiar dirección para el iPhone") { monitor.copy(iphone) }
        }
        Button("Ver registro") { monitor.openLog() }
        Divider()
        Button("Cerrar este ícono") { NSApplication.shared.terminate(nil) }
    }
}

/// El interruptor del servidor (en el menú sale como opción con ✓; en la ventanita, como interruptor).
struct ServerToggle: View {
    let monitor: ServiceMonitor

    var body: some View {
        Toggle("Servidor encendido", isOn: Binding(
            get: { monitor.wantsOn },
            set: { newValue in Task { await monitor.setRunning(newValue) } }
        ))
        .disabled(monitor.isBusy || monitor.phase == .notInstalled)
    }
}

struct StatusLines: View {
    let status: ServerStatus

    var body: some View {
        Text(status.roku.map { "Roku conectado (\($0))" } ?? "Roku no encontrado todavía")
        Text("\(status.items) videos en la biblioteca")
        if let playing = status.playing {
            Text("En la TV: \(playing.title)")
            Text("\(playing.state == "pause" ? "En pausa" : "Reproduciendo") · \(clock(playing.position)) de \(clock(playing.duration))")
        }
    }

    private func clock(_ seconds: Double) -> String {
        let total = Int(seconds)
        let (hours, minutes, secs) = (total / 3600, total % 3600 / 60, total % 60)
        return hours > 0
            ? String(format: "%d:%02d:%02d", hours, minutes, secs)
            : String(format: "%d:%02d", minutes, secs)
    }
}
