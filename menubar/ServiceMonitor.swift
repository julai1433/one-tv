import AppKit
import Foundation
import Observation

/// Lo que responde el servidor en /api/status.
struct ServerStatus: Decodable, Sendable {
    struct Playing: Decodable, Sendable {
        let title: String
        let state: String
        let position: Double
        let duration: Double
    }

    let roku: String?
    let items: Int
    let iphone: String?
    let playing: Playing?
}

/// Vigila el servidor de One TV y lo enciende o apaga a través de launchd.
@MainActor
@Observable
final class ServiceMonitor {
    enum Phase: Equatable {
        case checking, on, off, starting, stopping, notInstalled
    }

    private(set) var status: ServerStatus?
    private(set) var phase: Phase = .checking

    private let label = "local.cine-roku"
    private let port: Int
    private let plistPath: String
    private let logURL: URL
    private var transitionStarted = Date.distantPast
    private var pollTask: Task<Void, Never>?

    init() {
        let home = FileManager.default.homeDirectoryForCurrentUser
        plistPath = home.appending(path: "Library/LaunchAgents/\(label).plist").path
        logURL = home.appending(path: "Library/Logs/cine-roku.log")
        port = Self.configuredPort(home: home)
        pollTask = Task { [weak self] in
            while !Task.isCancelled {
                await self?.refresh()
                try? await Task.sleep(for: .seconds(3))
            }
        }
    }

    // MARK: - Estado para la interfaz

    var isBusy: Bool { phase == .starting || phase == .stopping }
    var wantsOn: Bool { phase == .on || phase == .starting }

    var symbolName: String {
        switch phase {
        case .on: status?.playing != nil ? "play.tv.fill" : "play.tv"
        case .starting, .stopping, .checking: "hourglass"
        case .off, .notInstalled: "play.slash"
        }
    }

    var headline: String {
        switch phase {
        case .checking: "One TV: revisando…"
        case .on: "One TV: encendido"
        case .off: "One TV: apagado"
        case .starting: "One TV: encendiendo…"
        case .stopping: "One TV: apagando…"
        case .notInstalled: "Falta instalarlo: ./cine autoarranque"
        }
    }

    // MARK: - Acciones

    func refresh() async {
        let fetched = await Self.fetchStatus(port: port)
        status = fetched
        if isBusy {
            let reached = (phase == .starting) == (fetched != nil)
            let gaveUp = Date.now.timeIntervalSince(transitionStarted) > 60
            guard reached || gaveUp else { return }
        }
        if fetched == nil && !FileManager.default.fileExists(atPath: plistPath) {
            phase = .notInstalled
        } else {
            phase = fetched != nil ? .on : .off
        }
    }

    /// Encender deja el servicio activo (también tras reiniciar); apagar lo deja apagado hasta volver a encenderlo.
    func setRunning(_ on: Bool) async {
        phase = on ? .starting : .stopping
        transitionStarted = .now
        let domain = "gui/\(getuid())"
        if on {
            _ = await Self.launchctl(["enable", "\(domain)/\(label)"])
            _ = await Self.launchctl(["bootstrap", domain, plistPath])
        } else {
            _ = await Self.launchctl(["bootout", "\(domain)/\(label)"])
            _ = await Self.launchctl(["disable", "\(domain)/\(label)"])
        }
        await refresh()
    }

    func openPage() {
        guard let url = URL(string: "http://localhost:\(port)") else { return }
        NSWorkspace.shared.open(url)
    }

    func copy(_ text: String) {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(text, forType: .string)
    }

    func openLog() {
        NSWorkspace.shared.open(logURL)
    }

    // MARK: - Ayudantes (fuera del hilo principal)

    nonisolated private static func configuredPort(home: URL) -> Int {
        let config = home.appending(path: "Library/Application Support/cine-roku/config.json")
        guard let data = try? Data(contentsOf: config),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let port = json["puerto"] as? Int else { return 8765 }
        return port
    }

    nonisolated private static func fetchStatus(port: Int) async -> ServerStatus? {
        guard let url = URL(string: "http://127.0.0.1:\(port)/api/status") else { return nil }
        var request = URLRequest(url: url)
        request.timeoutInterval = 2
        guard let (data, response) = try? await URLSession.shared.data(for: request),
              (response as? HTTPURLResponse)?.statusCode == 200 else { return nil }
        return try? JSONDecoder().decode(ServerStatus.self, from: data)
    }

    nonisolated private static func launchctl(_ arguments: [String]) async -> Int32 {
        await withCheckedContinuation { continuation in
            let process = Process()
            process.executableURL = URL(fileURLWithPath: "/bin/launchctl")
            process.arguments = arguments
            process.standardOutput = FileHandle.nullDevice
            process.standardError = FileHandle.nullDevice
            process.terminationHandler = { continuation.resume(returning: $0.terminationStatus) }
            do {
                try process.run()
            } catch {
                continuation.resume(returning: -1)
            }
        }
    }
}
