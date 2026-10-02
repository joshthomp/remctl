// Render this Mac's own Reminders symbols. No Apple artwork is shipped in RemCTL.
import AppKit

if CommandLine.arguments.dropFirst().first == "--thumbnails" {
    let input = FileHandle.standardInput.readDataToEndOfFile()
    let lists = try JSONSerialization.jsonObject(with: input) as? [[String: Any]] ?? []
    var output: [String: String] = [:]
    for list in lists {
        guard let id = list["id"] as? Int else { continue }
        let badge = list["badge"] as? [String: Any] ?? [:]
        let color = (list["color"] as? [String: Any])?["hex"] as? String ?? list["color"] as? String ?? "#007aff"
        let hex = UInt32(color.trimmingCharacters(in: CharacterSet(charactersIn: "#")), radix: 16) ?? 0x007aff
        let tint = NSColor(srgbRed: CGFloat((hex >> 16) & 255)/255, green: CGFloat((hex >> 8) & 255)/255, blue: CGFloat(hex & 255)/255, alpha: 1)
        let target = NSImage(size: NSSize(width: 64, height: 64))
        target.lockFocus()
        let scale = NSAffineTransform()
        scale.scale(by: 0.5)
        scale.concat()
        tint.setFill()
        NSBezierPath(roundedRect: NSRect(x: 0,y: 0,width: 128,height: 128), xRadius: 28,yRadius: 28).fill()
        if let emoji = badge["emoji"] as? String, !emoji.isEmpty {
            let text = NSAttributedString(string: emoji, attributes: [.font: NSFont(name: "Apple Color Emoji", size: 86) ?? NSFont.systemFont(ofSize: 86)])
            let size = text.size()
            text.draw(at: NSPoint(x: (128-size.width)/2, y: (128-size.height)/2))
        } else if let encoded = badge["image"] as? String,
                  let payload = encoded.split(separator: ",", maxSplits: 1).last,
                  let data = Data(base64Encoded: String(payload)), let source = NSImage(data: data) {
            let glyph = NSImage(size: NSSize(width: 80, height: 80))
            glyph.lockFocus()
            source.draw(in: NSRect(x: 0,y: 0,width: 80,height: 80))
            NSColor.white.setFill()
            NSRect(x: 0,y: 0,width: 80,height: 80).fill(using: .sourceAtop)
            glyph.unlockFocus()
            glyph.draw(in: NSRect(x: 24,y: 24,width: 80,height: 80))
        }
        target.unlockFocus()
        if let tiff = target.tiffRepresentation, let bitmap = NSBitmapImageRep(data: tiff), let png = bitmap.representation(using: .png, properties: [:]) {
            output[String(id)] = "data:image/png;base64," + png.base64EncodedString()
        }
    }
    FileHandle.standardOutput.write(try JSONSerialization.data(withJSONObject: output))
    exit(0)
}

let source = try String(contentsOfFile: CommandLine.arguments[1], encoding: .utf8)
let pattern = try NSRegularExpression(pattern: #"\("([a-z0-9]+)", "(ListBadge[^"]+)""#)
let bundle = Bundle(path: "/System/Library/PrivateFrameworks/RemindersUICore.framework")
var symbols: [String: String] = [:]
for match in pattern.matches(in: source, range: NSRange(source.startIndex..., in: source)) {
    let name = (source as NSString).substring(with: match.range(at: 1))
    let asset = (source as NSString).substring(with: match.range(at: 2))
    guard let image = bundle?.image(forResource: asset) else { continue }
    let target = NSImage(size: NSSize(width: 64, height: 64))
    target.lockFocus()
    image.draw(in: NSRect(x: 0, y: 0, width: 64, height: 64))
    target.unlockFocus()
    guard let tiff = target.tiffRepresentation,
          let bitmap = NSBitmapImageRep(data: tiff),
          let png = bitmap.representation(using: .png, properties: [:]) else { continue }
    symbols[name] = "data:image/png;base64," + png.base64EncodedString()
}
try JSONSerialization.data(withJSONObject: symbols, options: [.sortedKeys])
    .write(to: URL(fileURLWithPath: CommandLine.arguments[2]), options: .atomic)
print("Rendered \(symbols.count) Reminders list symbols")
