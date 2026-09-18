import CoreGraphics
import Foundation
import ImageIO
import ScreenCaptureKit

@main
struct CaptureProbe {
    static func main() async {
        let args = Array(CommandLine.arguments.dropFirst())
        do {
            if args.contains("--permission") {
                try Packet.writeJSONObject(Permission.diagnose())
                return
            }
            if args.contains("--list-json") {
                try await listJSON()
                return
            }
            if args.contains("--self-test") {
                try await runSelfTest(args)
                return
            }
            if args.contains("--stream") {
                guard let windowID = intFlag(args, name: "--window-id") else {
                    throw ProbeError.usage("--stream requires --window-id")
                }
                let fps = intFlag(args, name: "--fps") ?? 60
                let maxFrames = intFlag(args, name: "--max-frames") ?? 0
                signal(SIGTERM, SIG_IGN)
                signal(SIGINT, SIG_IGN)
                let streamer = Streamer(windowID: CGWindowID(windowID), fps: fps, maxFrames: maxFrames)
                let source = DispatchSource.makeSignalSource(signal: SIGTERM, queue: .main)
                source.setEventHandler { streamer.requestStop() }
                source.resume()
                let source2 = DispatchSource.makeSignalSource(signal: SIGINT, queue: .main)
                source2.setEventHandler { streamer.requestStop() }
                source2.resume()
                try await streamer.run()
                return
            }
            try await listTextAndMaybeCapture(args)
        } catch {
            Packet.log("error: \(error)")
            if let probe = error as? ProbeError, case .permissionDenied = probe {
                exit(2)
            }
            exit(1)
        }
    }
}

func runSelfTest(_ args: [String]) async throws {
    let permission = Permission.diagnose()
    if permission["status"] as? String != "granted" {
        try Packet.writeJSONObject(permission)
        throw ProbeError.permissionDenied
    }
    let frames = intFlag(args, name: "--max-frames") ?? intFlag(args, name: "--frames") ?? 12
    let fps = intFlag(args, name: "--fps") ?? 30
    let resize = args.contains("--resize")
    let window = await MainActor.run { TestWindow.show() }
    try await Task.sleep(nanoseconds: 500_000_000)
    let windowID = await MainActor.run { TestWindow.windowID(for: window) }
    if resize {
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.35) {
            window.setContentSize(NSSize(width: 300, height: 180))
        }
    }
    let streamer = Streamer(windowID: windowID, fps: fps, maxFrames: frames)
    try await streamer.run()
    await MainActor.run { window.close() }
}

func listJSON() async throws {
    let permission = Permission.diagnose()
    let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: false)
    var windows: [[String: Any]] = []
    for window in content.windows {
        let bundle = window.owningApplication?.bundleIdentifier ?? ""
        if !window.isOnScreen, !bundle.contains("parallels") {
            continue
        }
        windows.append([
            "id": Int(window.windowID),
            "on_screen": window.isOnScreen,
            "title": window.title ?? "",
            "bundle": bundle,
            "owner": window.owningApplication?.applicationName ?? "",
            "width": window.frame.width,
            "height": window.frame.height,
            "x": window.frame.origin.x,
            "y": window.frame.origin.y,
        ])
    }
    try Packet.writeJSONObject([
        "kind": "windows",
        "permission": permission,
        "displays": content.displays.count,
        "windows": windows,
        "sck_minimum": "12.3",
        "transport_default": "stdout_pipe",
        "shared_memory": false,
    ])
}

func listTextAndMaybeCapture(_ args: [String]) async throws {
    let windowID = intFlag(args, name: "--window-id")
    let outPath = stringFlag(args, name: "--out")
    let content = try await SCShareableContent.excludingDesktopWindows(
        false,
        onScreenWindowsOnly: true
    )
    print("displays=\(content.displays.count) windows=\(content.windows.count)")
    for window in content.windows.prefix(30) {
        let title = window.title ?? "-"
        let bundle = window.owningApplication?.bundleIdentifier ?? "-"
        print(
            "window id=\(window.windowID) onScreen=\(window.isOnScreen) bundle=\(bundle) title=\(title)"
        )
    }
    if let windowID, let outPath {
        try await capture(windowID: CGWindowID(windowID), path: outPath, content: content)
    }
}

func capture(windowID: CGWindowID, path: String, content: SCShareableContent) async throws {
    guard let window = content.windows.first(where: { $0.windowID == windowID }) else {
        throw ProbeError.windowNotFound(windowID)
    }
    let filter = SCContentFilter(desktopIndependentWindow: window)
    let started = ContinuousClock.now
    let cgImage = try await SCScreenshotManager.captureImage(
        contentFilter: filter,
        configuration: SCStreamConfiguration()
    )
    let elapsedMs = started.duration(to: ContinuousClock.now) / .milliseconds(1)
    let url = URL(fileURLWithPath: path)
    let dest = CGImageDestinationCreateWithURL(url as CFURL, "public.png" as CFString, 1, nil)
    guard let dest else {
        throw ProbeError.cannotWrite(path)
    }
    CGImageDestinationAddImage(dest, cgImage, nil)
    guard CGImageDestinationFinalize(dest) else {
        throw ProbeError.cannotWrite(path)
    }
    print(
        "captured window=\(windowID) width=\(cgImage.width) height=\(cgImage.height) elapsed_ms=\(String(format: "%.2f", elapsedMs))"
    )
}

func intFlag(_ args: [String], name: String) -> Int? {
    guard let index = args.firstIndex(of: name), index + 1 < args.count else { return nil }
    return Int(args[index + 1])
}

func stringFlag(_ args: [String], name: String) -> String? {
    guard let index = args.firstIndex(of: name), index + 1 < args.count else { return nil }
    return args[index + 1]
}

enum ProbeError: Error, CustomStringConvertible {
    case windowNotFound(CGWindowID)
    case cannotWrite(String)
    case permissionDenied
    case usage(String)

    var description: String {
        switch self {
        case .windowNotFound(let id):
            return "window \(id) not found among on-screen windows"
        case .cannotWrite(let path):
            return "cannot write \(path)"
        case .permissionDenied:
            return "Screen Recording permission is denied; this tool does not request or change it"
        case .usage(let text):
            return text
        }
    }
}
