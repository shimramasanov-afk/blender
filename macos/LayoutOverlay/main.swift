import AppKit
import CoreGraphics
import Foundation

struct Slot: Decodable {
    let id: String
    let name: String
    let x: Double
    let y: Double
    let w: Double
    let h: Double
    let r: Double
    let g: Double
    let b: Double
}

struct Payload: Decodable {
    let slots: [Slot]
}

final class OverlayView: NSView {
    var slots: [Slot] = []

    override var isFlipped: Bool { true }
    override var isOpaque: Bool { false }

    override func draw(_ dirtyRect: NSRect) {
        NSColor.clear.setFill()
        dirtyRect.fill()
        for slot in slots {
            let rect = NSRect(x: slot.x, y: slot.y, width: slot.w, height: slot.h)
            let color = NSColor(srgbRed: slot.r, green: slot.g, blue: slot.b, alpha: 1)
            color.withAlphaComponent(0.16).setFill()
            NSBezierPath(rect: rect).fill()
            color.setStroke()
            let border = NSBezierPath(rect: rect.insetBy(dx: 1.5, dy: 1.5))
            border.lineWidth = 3
            border.stroke()
            let label = slot.name as NSString
            let attrs: [NSAttributedString.Key: Any] = [
                .font: NSFont.boldSystemFont(ofSize: 14),
                .foregroundColor: color,
            ]
            label.draw(at: NSPoint(x: rect.minX + 8, y: rect.minY + 6), withAttributes: attrs)
        }
        let hint = "перетащи окна L2 в рамки  ·  Ctrl+C в терминале закроет слой" as NSString
        hint.draw(
            at: NSPoint(x: 12, y: 8),
            withAttributes: [
                .font: NSFont.systemFont(ofSize: 12),
                .foregroundColor: NSColor.white,
            ]
        )
    }
}

func flag(_ args: [String], _ name: String) -> String? {
    guard let index = args.firstIndex(of: name), index + 1 < args.count else { return nil }
    return args[index + 1]
}

func cgNumber(_ value: Any?) -> CGFloat {
    if let number = value as? NSNumber {
        return CGFloat(truncating: number)
    }
    if let value = value as? Double {
        return CGFloat(value)
    }
    return 0
}

func windowBounds(id: CGWindowID) -> CGRect? {
    guard
        let raw = CGWindowListCopyWindowInfo([.optionIncludingWindow], id) as? [[String: Any]],
        let row = raw.first,
        let bounds = row[kCGWindowBounds as String] as? [String: Any]
    else {
        return nil
    }
    return CGRect(
        x: cgNumber(bounds["X"]),
        y: cgNumber(bounds["Y"]),
        width: cgNumber(bounds["Width"]),
        height: cgNumber(bounds["Height"])
    )
}

func cocoaRect(from cg: CGRect) -> NSRect {
    let top = NSScreen.screens.map(\.frame.maxY).max() ?? cg.height
    return NSRect(
        x: cg.origin.x,
        y: top - cg.origin.y - cg.size.height,
        width: cg.size.width,
        height: cg.size.height
    )
}

let args = Array(CommandLine.arguments.dropFirst())
guard let windowRaw = flag(args, "--window-id"), let windowId = UInt32(windowRaw) else {
    fputs("usage: layout-overlay --window-id N --seconds S --json PATH\n", stderr)
    exit(2)
}
guard let jsonPath = flag(args, "--json") else {
    fputs("layout-overlay: --json required\n", stderr)
    exit(2)
}
let seconds = Double(flag(args, "--seconds") ?? "180") ?? 180
let data = try Data(contentsOf: URL(fileURLWithPath: jsonPath))
let payload = try JSONDecoder().decode(Payload.self, from: data)
guard let first = windowBounds(id: CGWindowID(windowId)) else {
    fputs("layout-overlay: window \(windowId) not found\n", stderr)
    exit(3)
}

let app = NSApplication.shared
app.setActivationPolicy(.accessory)

let view = OverlayView(frame: NSRect(x: 0, y: 0, width: first.width, height: first.height))
view.slots = payload.slots

let window = NSWindow(
    contentRect: cocoaRect(from: first),
    styleMask: .borderless,
    backing: .buffered,
    defer: false
)
window.isOpaque = false
window.backgroundColor = .clear
window.hasShadow = false
window.level = .statusBar
window.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary]
window.ignoresMouseEvents = true
window.isReleasedWhenClosed = false
window.contentView = view
window.orderFrontRegardless()

Timer.scheduledTimer(withTimeInterval: 0.4, repeats: true) { _ in
    guard let bounds = windowBounds(id: CGWindowID(windowId)) else { return }
    window.setFrame(cocoaRect(from: bounds), display: true)
    view.frame = NSRect(x: 0, y: 0, width: bounds.width, height: bounds.height)
    view.needsDisplay = true
}

if seconds > 0 {
    DispatchQueue.main.asyncAfter(deadline: .now() + seconds) {
        app.terminate(nil)
    }
}

signal(SIGINT) { _ in
    DispatchQueue.main.async { NSApp.terminate(nil) }
}
signal(SIGTERM) { _ in
    DispatchQueue.main.async { NSApp.terminate(nil) }
}

app.run()
