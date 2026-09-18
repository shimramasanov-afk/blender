import Accelerate
import AppKit
import CoreMedia
import CoreVideo
import Foundation
import ScreenCaptureKit

final class LatestSample: @unchecked Sendable {
    private let lock = NSLock()
    private var buffer: CVPixelBuffer?
    private var ptsNs: Int64 = 0
    private(set) var drops = 0
    private(set) var puts = 0

    func put(_ pixelBuffer: CVPixelBuffer, ptsNs: Int64) {
        lock.lock()
        if buffer != nil {
            drops += 1
        }
        buffer = pixelBuffer
        self.ptsNs = ptsNs
        puts += 1
        lock.unlock()
    }

    func take() -> (CVPixelBuffer, Int64)? {
        lock.lock()
        defer { lock.unlock() }
        guard let buffer else { return nil }
        let pts = ptsNs
        self.buffer = nil
        return (buffer, pts)
    }

    var dropCount: Int {
        lock.lock()
        defer { lock.unlock() }
        return drops
    }
}

final class Streamer: NSObject, SCStreamOutput, SCStreamDelegate, @unchecked Sendable {
    private let windowID: CGWindowID
    private let fps: Int
    private let maxFrames: Int
    private let box = LatestSample()
    private var stream: SCStream?
    private var writer: Thread?
    private var stopFlag = false
    private let statsLock = NSLock()
    private var framesWritten = 0
    private var lastWidth = 0
    private var lastHeight = 0
    private var configWidth = 0
    private var configHeight = 0
    private var scale: CGFloat = 1
    private var started = ContinuousClock.now
    private var rssPeak: UInt64 = 0
    private var sourceLostReason: String?

    init(windowID: CGWindowID, fps: Int, maxFrames: Int) {
        self.windowID = windowID
        self.fps = max(1, min(fps, 60))
        self.maxFrames = maxFrames
    }

    func run() async throws {
        await MainActor.run { _ = NSApplication.shared }
        let permission = Permission.diagnose()
        if permission["status"] as? String != "granted" {
            try Packet.write(header: permission)
            throw ProbeError.permissionDenied
        }
        guard let window = try await findWindow(id: windowID, retries: 8) else {
            try Packet.write(header: [
                "kind": "source_lost",
                "reason": "window \(windowID) not among on-screen windows",
            ])
            throw ProbeError.windowNotFound(windowID)
        }
        scale = backingScale(for: window)
        let pixelW = max(8, Int((window.frame.width * scale).rounded()))
        let pixelH = max(8, Int((window.frame.height * scale).rounded()))
        configWidth = pixelW
        configHeight = pixelH
        let config = SCStreamConfiguration()
        config.width = pixelW
        config.height = pixelH
        config.scalesToFit = false
        config.showsCursor = false
        config.queueDepth = 2
        config.pixelFormat = kCVPixelFormatType_32BGRA
        config.minimumFrameInterval = CMTime(value: 1, timescale: CMTimeScale(fps))
        let filter = SCContentFilter(desktopIndependentWindow: window)
        let stream = SCStream(filter: filter, configuration: config, delegate: self)
        try stream.addStreamOutput(self, type: .screen, sampleHandlerQueue: DispatchQueue(label: "l2.sck"))
        self.stream = stream
        started = ContinuousClock.now
        try Packet.write(header: [
            "kind": "hello",
            "window_id": Int(windowID),
            "requested_fps": fps,
            "requested_fps_is_not_a_guarantee": true,
            "pixel_format": "rgb8",
            "scale": scale,
            "point_w": window.frame.width,
            "point_h": window.frame.height,
            "width": pixelW,
            "height": pixelH,
            "transport": "stdout_pipe",
            "copies_helper": 1,
            "macos": ProcessInfo.processInfo.operatingSystemVersionString,
            "sck_minimum": "12.3",
        ])
        let writer = Thread { [weak self] in
            self?.writeLoop()
        }
        writer.name = "l2.sck.writer"
        self.writer = writer
        writer.start()
        try await stream.startCapture()
        while !stopFlag {
            if let reason = sourceLostReason {
                try? Packet.write(header: ["kind": "source_lost", "reason": reason])
                break
            }
            if maxFrames > 0, writtenCount() >= maxFrames {
                break
            }
            if let live = try await findWindow(id: windowID, retries: 1) {
                try await refreshSize(stream: stream, window: live)
            } else if writtenCount() == 0 {
                try? Packet.write(header: [
                    "kind": "source_lost",
                    "reason": "window disappeared",
                ])
                break
            }
            try await Task.sleep(nanoseconds: 150_000_000)
        }
        await finish()
    }

    func requestStop() {
        stopFlag = true
    }

    func stream(_ stream: SCStream, didOutputSampleBuffer sampleBuffer: CMSampleBuffer, of type: SCStreamOutputType) {
        guard type == .screen, let pixel = CMSampleBufferGetImageBuffer(sampleBuffer) else { return }
        let pts = CMSampleBufferGetPresentationTimeStamp(sampleBuffer)
        let ptsNs = pts.timescale == 0 ? 0 : Int64(Double(pts.value) / Double(pts.timescale) * 1_000_000_000.0)
        box.put(pixel, ptsNs: ptsNs)
    }

    func stream(_ stream: SCStream, didStopWithError error: Error) {
        sourceLostReason = error.localizedDescription
        stopFlag = true
    }

    private func writeLoop() {
        while !stopFlag {
            if maxFrames > 0, writtenCount() >= maxFrames {
                stopFlag = true
                break
            }
            guard let (pixel, ptsNs) = box.take() else {
                Thread.sleep(forTimeInterval: 0.002)
                continue
            }
            let t0 = ContinuousClock.now
            guard let rgb = Self.bgraToRGB(pixel) else { continue }
            let copyMs = t0.duration(to: ContinuousClock.now) / .milliseconds(1)
            let width = CVPixelBufferGetWidth(pixel)
            let height = CVPixelBufferGetHeight(pixel)
            if width != lastWidth || height != lastHeight, writtenCount() > 0 {
                try? Packet.write(header: [
                    "kind": "resize",
                    "width": width,
                    "height": height,
                    "prev_width": lastWidth,
                    "prev_height": lastHeight,
                ])
            }
            lastWidth = width
            lastHeight = height
            var ts = timespec()
            clock_gettime(CLOCK_REALTIME, &ts)
            let hostNs = Int(ts.tv_sec) * 1_000_000_000 + Int(ts.tv_nsec)
            rssPeak = max(rssPeak, residentBytes())
            let header: [String: Any] = [
                "kind": "frame",
                "width": width,
                "height": height,
                "pixel_format": "rgb8",
                "stride": width * 3,
                "seq": framesWritten,
                "window_id": Int(windowID),
                "host_unix_ns": hostNs,
                "sck_pts_ns": ptsNs,
                "sck_pts_clock": "cmtime",
                "copy_ms": copyMs,
                "copies": 1,
                "scale": Double(scale),
                "bytes": rgb.count,
                "drops": box.dropCount,
                "source_id": "sck.window",
            ]
            do {
                try Packet.write(header: header, payload: rgb)
                statsLock.lock()
                framesWritten += 1
                statsLock.unlock()
            } catch {
                sourceLostReason = "stdout write failed"
                stopFlag = true
            }
        }
    }

    private func finish() async {
        stopFlag = true
        if let stream {
            try? await stream.stopCapture()
        }
        writer?.cancel()
        let written = writtenCount()
        let elapsed = started.duration(to: .now) / .milliseconds(1)
        let interval = written > 1 ? elapsed / Double(written - 1) : 0
        try? Packet.write(header: [
            "kind": "stats",
            "frames": written,
            "drops": box.dropCount,
            "puts": box.puts,
            "elapsed_ms": elapsed,
            "mean_interval_ms": interval,
            "requested_fps": fps,
            "achieved_fps": interval > 0 ? 1000.0 / interval : 0,
            "requested_fps_is_not_a_guarantee": true,
            "pixel_format": "rgb8",
            "copies_helper": 1,
            "rss_peak_bytes": rssPeak,
            "cpu_user_s": cpuUserSeconds(),
            "transport": "stdout_pipe",
        ])
    }

    private func refreshSize(stream: SCStream, window: SCWindow) async throws {
        scale = backingScale(for: window)
        let pixelW = max(8, Int((window.frame.width * scale).rounded()))
        let pixelH = max(8, Int((window.frame.height * scale).rounded()))
        if pixelW == configWidth, pixelH == configHeight {
            return
        }
        let config = SCStreamConfiguration()
        config.width = pixelW
        config.height = pixelH
        config.scalesToFit = false
        config.showsCursor = false
        config.queueDepth = 2
        config.pixelFormat = kCVPixelFormatType_32BGRA
        config.minimumFrameInterval = CMTime(value: 1, timescale: CMTimeScale(fps))
        try await stream.updateConfiguration(config)
        configWidth = pixelW
        configHeight = pixelH
        try Packet.write(header: [
            "kind": "resize",
            "width": pixelW,
            "height": pixelH,
            "point_w": window.frame.width,
            "point_h": window.frame.height,
            "scale": Double(scale),
        ])
    }

    private func writtenCount() -> Int {
        statsLock.lock()
        defer { statsLock.unlock() }
        return framesWritten
    }

    private func findWindow(id: CGWindowID, retries: Int) async throws -> SCWindow? {
        let attempts = max(1, retries)
        for attempt in 0..<attempts {
            if let match = try await lookupWindow(id: id, onScreenOnly: true) {
                return match
            }
            if retries > 1, let match = try await lookupWindow(id: id, onScreenOnly: false) {
                return match
            }
            if attempt + 1 < attempts {
                try await Task.sleep(nanoseconds: 200_000_000)
            }
        }
        return nil
    }

    private func lookupWindow(id: CGWindowID, onScreenOnly: Bool) async throws -> SCWindow? {
        let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: onScreenOnly)
        if let match = content.windows.first(where: { $0.windowID == id && $0.isOnScreen }) {
            return match
        }
        return content.windows.first(where: {
            $0.isOnScreen
                && $0.owningApplication?.bundleIdentifier == "com.parallels.desktop.console"
                && ($0.title == "Windows 11")
                && $0.frame.height >= 200
        })
    }

    private func backingScale(for window: SCWindow) -> CGFloat {
        let screens = NSScreen.screens
        let match = screens.first { NSMouseInRect(window.frame.origin, $0.frame, false) }
        return match?.backingScaleFactor ?? NSScreen.main?.backingScaleFactor ?? 1
    }

    static func bgraToRGB(_ pixel: CVPixelBuffer) -> Data? {
        let format = CVPixelBufferGetPixelFormatType(pixel)
        guard format == kCVPixelFormatType_32BGRA else { return nil }
        CVPixelBufferLockBaseAddress(pixel, .readOnly)
        defer { CVPixelBufferUnlockBaseAddress(pixel, .readOnly) }
        guard let src = CVPixelBufferGetBaseAddress(pixel) else { return nil }
        let width = CVPixelBufferGetWidth(pixel)
        let height = CVPixelBufferGetHeight(pixel)
        let srcStride = CVPixelBufferGetBytesPerRow(pixel)
        var srcBuf = vImage_Buffer(
            data: src,
            height: vImagePixelCount(height),
            width: vImagePixelCount(width),
            rowBytes: srcStride
        )
        let dstStride = width * 3
        var data = Data(count: dstStride * height)
        let err: vImage_Error = data.withUnsafeMutableBytes { raw in
            guard let dest = raw.baseAddress else { return vImage_Error(kvImageNullPointerArgument) }
            var dstBuf = vImage_Buffer(
                data: dest,
                height: vImagePixelCount(height),
                width: vImagePixelCount(width),
                rowBytes: dstStride
            )
            return vImageConvert_BGRA8888toRGB888(&srcBuf, &dstBuf, vImage_Flags(kvImageNoFlags))
        }
        return err == kvImageNoError ? data : nil
    }
}

func residentBytes() -> UInt64 {
    var info = mach_task_basic_info()
    var count = mach_msg_type_number_t(MemoryLayout<mach_task_basic_info>.size / MemoryLayout<natural_t>.size)
    let result = withUnsafeMutablePointer(to: &info) { ptr -> kern_return_t in
        ptr.withMemoryRebound(to: integer_t.self, capacity: Int(count)) { rebound in
            task_info(mach_task_self_, task_flavor_t(MACH_TASK_BASIC_INFO), rebound, &count)
        }
    }
    return result == KERN_SUCCESS ? UInt64(info.resident_size) : 0
}

func cpuUserSeconds() -> Double {
    var usage = rusage()
    getrusage(RUSAGE_SELF, &usage)
    return Double(usage.ru_utime.tv_sec) + Double(usage.ru_utime.tv_usec) / 1_000_000.0
}
