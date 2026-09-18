import Foundation

enum Packet {
    static let magic = Data([0x4C, 0x32, 0x46, 0x31]) // L2F1

    static func write(header: [String: Any], payload: Data = Data()) throws {
        let headerData = try JSONSerialization.data(withJSONObject: header, options: [])
        var packet = Data()
        packet.append(magic)
        var headerLen = UInt32(headerData.count).littleEndian
        var payloadLen = UInt32(payload.count).littleEndian
        packet.append(Data(bytes: &headerLen, count: 4))
        packet.append(Data(bytes: &payloadLen, count: 4))
        packet.append(headerData)
        packet.append(payload)
        try FileHandle.standardOutput.write(contentsOf: packet)
    }

    static func writeJSONObject(_ object: [String: Any]) throws {
        let data = try JSONSerialization.data(withJSONObject: object, options: [.prettyPrinted])
        FileHandle.standardOutput.write(data)
        FileHandle.standardOutput.write(Data("\n".utf8))
    }

    static func log(_ message: String) {
        FileHandle.standardError.write(Data("capture-probe: \(message)\n".utf8))
    }
}
