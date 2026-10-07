import SwiftUI

/// La ventanita que sale al abrir la app desde Spotlight: lo mismo que el menú del ícono.
struct ControlPanel: View {
    let monitor: ServiceMonitor

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Label(monitor.headline, systemImage: monitor.symbolName)
                .font(.headline)
            if let status = monitor.status {
                VStack(alignment: .leading, spacing: 4) {
                    StatusLines(status: status)
                }
                .foregroundStyle(.secondary)
            }
            ServerToggle(monitor: monitor)
                .toggleStyle(.switch)
            PanelActions(monitor: monitor)
            Text("El ícono también está en la barra de arriba, a la derecha.")
                .font(.footnote)
                .foregroundStyle(.tertiary)
        }
        .padding(20)
        .frame(width: 340, alignment: .leading)
    }
}

private struct PanelActions: View {
    let monitor: ServiceMonitor

    var body: some View {
        HStack {
            Button("Abrir la página") { monitor.openPage() }
                .disabled(monitor.status == nil)
            if let iphone = monitor.status?.iphone {
                Button("Copiar para iPhone") { monitor.copy(iphone) }
            }
            Button("Registro") { monitor.openLog() }
        }
    }
}
