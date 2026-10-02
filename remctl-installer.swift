// Install RemCTL: the double-click entry point of the release disk image.
//
// Gatekeeper refuses unsigned scripts from the internet, and notarization
// ignores signed ones, so the disk image ships this signed, notarized app
// instead of a .command file. It writes a one-time launcher, which macOS does
// not quarantine, and opens it in Terminal. The launcher checks the Capability
// Host's Developer ID and runs the installer bundled inside it.

import AppKit
import Foundation

let hostName = "RemCTL Capability Host.app"
let hostRequirement = #"=identifier "net.macstories.remctl.capability-host" and anchor apple generic and certificate leaf[field.1.2.840.113635.100.6.1.13] exists and certificate leaf[subject.OU] = "4W35M4UN6R""#

/// The folder this app was opened from. A quarantined app can run from a
/// randomized copy (App Translocation), so ask Security for the original path.
func originalFolder() -> URL {
    let bundle = Bundle.main.bundleURL
    typealias OriginalPath = @convention(c) (CFURL, UnsafeMutablePointer<Unmanaged<CFError>?>?) -> Unmanaged<CFURL>?
    if let security = dlopen("/System/Library/Frameworks/Security.framework/Security", RTLD_NOW),
       let symbol = dlsym(security, "SecTranslocateCreateOriginalPathForURL"),
       let original = unsafeBitCast(symbol, to: OriginalPath.self)(bundle as CFURL, nil)?.takeRetainedValue() {
        return (original as URL).deletingLastPathComponent()
    }
    return bundle.deletingLastPathComponent()
}

func quoted(_ value: String) -> String {
    "'" + value.replacingOccurrences(of: "'", with: #"'\''"#) + "'"
}

func stop(_ message: String) -> Never {
    NSApp.activate(ignoringOtherApps: true)
    let alert = NSAlert()
    alert.messageText = "RemCTL can't be installed"
    alert.informativeText = message
    alert.runModal()
    exit(1)
}

let application = NSApplication.shared
application.setActivationPolicy(.accessory)

let host = originalFolder().appendingPathComponent(hostName)
let installer = host.appendingPathComponent("Contents/Resources/Distribution/install.sh")
guard FileManager.default.isReadableFile(atPath: installer.path) else {
    stop("Open Install RemCTL from the RemCTL disk image, next to \(hostName).")
}

let launcher = FileManager.default.temporaryDirectory
    .appendingPathComponent("Install RemCTL \(UUID().uuidString.prefix(8)).command")
let script = """
#!/bin/bash
set -euo pipefail
rm -f "$0"
APP=\(quoted(host.path))
/usr/bin/codesign --verify --deep --strict -R \(quoted(hostRequirement)) "$APP"
exec /bin/bash "$APP/Contents/Resources/Distribution/install.sh" --prebuilt "$APP" --bootstrap

"""
do {
    try script.write(to: launcher, atomically: true, encoding: .utf8)
    try FileManager.default.setAttributes([.posixPermissions: 0o700], ofItemAtPath: launcher.path)
    removexattr(launcher.path, "com.apple.quarantine", 0)
} catch {
    stop("Could not prepare the installer: \(error.localizedDescription)")
}

guard let terminal = NSWorkspace.shared.urlForApplication(withBundleIdentifier: "com.apple.Terminal") else {
    stop("Terminal isn't available on this Mac.")
}
NSWorkspace.shared.open([launcher], withApplicationAt: terminal, configuration: NSWorkspace.OpenConfiguration()) { _, error in
    DispatchQueue.main.async {
        if let error { stop("Could not open Terminal: \(error.localizedDescription)") }
        exit(0)
    }
}
application.run()
