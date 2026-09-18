import CoreGraphics
import Foundation

enum Permission {
    /// Diagnose only. Does not call CGRequestScreenCaptureAccess.
    static func diagnose() -> [String: Any] {
        let version = ProcessInfo.processInfo.operatingSystemVersion
        let preflight = CGPreflightScreenCaptureAccess()
        return [
            "kind": "permission",
            "status": preflight ? "granted" : "denied",
            "preflight": preflight,
            "requested_permission": false,
            "macos": ProcessInfo.processInfo.operatingSystemVersionString,
            "macos_major": version.majorVersion,
            "sck_minimum": "12.3",
            "sck_minimum_ok": version.majorVersion > 12
                || (version.majorVersion == 12 && version.minorVersion >= 3),
            "hint": "System Settings → Privacy & Security → Screen Recording. This tool does not change permissions.",
        ]
    }
}
