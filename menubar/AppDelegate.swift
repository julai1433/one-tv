import AppKit
import SwiftUI

/// Pone el ícono donde se ve y abre una ventanita de control cuando la app se abre a mano (Spotlight, Finder).
@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    let monitor = ServiceMonitor()
    private var panel: NSWindow?

    /// macOS pone los íconos nuevos a la izquierda de todos; en una Mac con muesca y la barra llena
    /// quedan detrás de la cámara. Con una posición guardada (puntos desde el borde derecho) va junto a la batería.
    static func placeStatusItem() {
        let key = "NSStatusItem Preferred Position Item-0"
        if UserDefaults.standard.object(forKey: key) == nil {
            UserDefaults.standard.set(440.0, forKey: key)
        }
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        // Al iniciar sesión la abre launchd y no debe salir ninguna ventana; abierta a mano, sí.
        if ProcessInfo.processInfo.environment["XPC_SERVICE_NAME"] != "local.cine-roku.barra" {
            showPanel()
        }
    }

    /// Abrirla otra vez desde Spotlight con la app ya corriendo.
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        showPanel()
        return false
    }

    private func showPanel() {
        if panel == nil {
            let host = NSHostingController(rootView: ControlPanel(monitor: monitor))
            host.sizingOptions = [.preferredContentSize]
            let window = NSWindow(contentViewController: host)
            window.title = "One TV"
            window.styleMask = [.titled, .closable]
            window.isReleasedWhenClosed = false
            window.center()
            panel = window
        }
        NSApp.activate()
        panel?.makeKeyAndOrderFront(nil)
    }
}
