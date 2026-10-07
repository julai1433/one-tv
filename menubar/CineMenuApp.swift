import SwiftUI

/// Ícono de One TV en la barra de menú: muestra si el servidor está encendido y permite encenderlo o apagarlo.
@main
struct CineMenuApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate

    init() {
        AppDelegate.placeStatusItem()   // antes de que exista el ícono
    }

    var body: some Scene {
        MenuBarExtra {
            MenuContent(monitor: appDelegate.monitor)
        } label: {
            MenuBarIcon(monitor: appDelegate.monitor)
        }
        .menuBarExtraStyle(.menu)
    }
}

/// Vista propia para que el ícono cambie solo al cambiar el estado.
private struct MenuBarIcon: View {
    let monitor: ServiceMonitor

    var body: some View {
        Image(systemName: monitor.symbolName)
            .accessibilityLabel("One TV")
    }
}
