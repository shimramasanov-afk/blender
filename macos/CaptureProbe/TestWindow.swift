import AppKit
import CoreGraphics

enum TestWindow {
    static let title = "L2BrainCaptureTest"

    static func show() -> NSWindow {
        let app = NSApplication.shared
        app.setActivationPolicy(.accessory)
        let window = NSWindow(
            contentRect: NSRect(x: 80, y: 80, width: 220, height: 140),
            styleMask: [.titled, .closable, .resizable],
            backing: .buffered,
            defer: false
        )
        window.title = title
        window.isReleasedWhenClosed = false
        window.contentView = PatternView(frame: NSRect(x: 0, y: 0, width: 220, height: 140))
        window.makeKeyAndOrderFront(nil)
        app.activate(ignoringOtherApps: true)
        return window
    }

    static func windowID(for window: NSWindow) -> CGWindowID {
        CGWindowID(window.windowNumber)
    }
}

final class PatternView: NSView {
    override func draw(_ dirtyRect: NSRect) {
        NSColor(red: 70 / 255, green: 72 / 255, blue: 80 / 255, alpha: 1).setFill()
        dirtyRect.fill()
        let red = NSRect(x: 8, y: 20, width: bounds.width * 0.34, height: bounds.height * 0.62)
        NSColor(red: 220 / 255, green: 36 / 255, blue: 36 / 255, alpha: 1).setFill()
        red.fill()
    }
}
