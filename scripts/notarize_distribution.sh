#!/bin/bash
# Notarize a built Developer ID app and produce the verified downloadable DMG.
set -euo pipefail
if [[ $# != 2 ]]; then
    echo "Usage: scripts/notarize_distribution.sh BUILD_DIRECTORY KEYCHAIN_PROFILE|--asc" >&2
    exit 2
fi
BUILD="$(cd "$1" && pwd -P)"
PROFILE="$2"
APP="$BUILD/RemCTL Capability Host.app"
INSTALLER="$BUILD/Install RemCTL.app"
PUBLISHER='anchor apple generic and certificate leaf[field.1.2.840.113635.100.6.1.13] exists and certificate leaf[subject.OU] = "4W35M4UN6R"'
REQUIREMENT="=identifier \"net.macstories.remctl.capability-host\" and $PUBLISHER"
/usr/bin/codesign --verify --deep --strict -R "$REQUIREMENT" "$APP"
/usr/bin/codesign --verify --deep --strict -R "=identifier \"net.macstories.remctl.installer\" and $PUBLISHER" "$INSTALLER"
[[ "$(/usr/bin/codesign -dvvv "$APP" 2>&1)" == *"runtime"* ]] || { echo "Hardened runtime is required." >&2; exit 1; }
# Sign the disk image with the same publisher as its app. Notarization alone
# does not give an unsigned DMG a Gatekeeper-verifiable publisher signature.
/usr/bin/codesign --display --extract-certificates="$BUILD/notarization-certificate-" "$APP"
IDENTITY="$(/usr/bin/shasum -a 1 "$BUILD/notarization-certificate-0" | /usr/bin/awk '{print $1}')"
PYTHON="$APP/Contents/Resources/Python/bin/python3.13"
ARCH="$("$PYTHON" -B -I -S -c 'import json,sys; print(json.load(open(sys.argv[1]))["architecture"])' "$APP/Contents/Resources/distribution.json")"
case "$ARCH" in arm64|x86_64) ;; *) echo "Invalid release architecture" >&2; exit 1 ;; esac
DMG="$BUILD/RemCTL-$ARCH.dmg"
[[ ! -e "$DMG" ]] || { echo "Output already exists: $DMG" >&2; exit 1; }
# --asc uses the existing asc authentication profile without exporting its key.
submit() {
    local archive="$1" label="$2" result="$BUILD/notarization-$2.json" status id
    if [[ "$PROFILE" == "--asc" ]]; then
        asc notarization submit --file "$archive" --wait --output json > "$result" || true
    else
        /usr/bin/xcrun notarytool submit "$archive" --keychain-profile "$PROFILE" --wait --output-format json > "$result" || true
    fi
    status="$("$PYTHON" -B -I -S -c 'import json,sys; d=json.load(open(sys.argv[1])); d=d.get("data",d); print(d.get("attributes",d).get("status","Unknown"))' "$result")"
    if [[ "$status" != "Accepted" ]]; then
        id="$("$PYTHON" -B -I -S -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d.get("data",d).get("id",""))' "$result")"
        if [[ -n "$id" ]]; then
            if [[ "$PROFILE" == "--asc" ]]; then
                asc notarization log --id "$id" > "$BUILD/notarization-$label-log.json" || true
            else
                /usr/bin/xcrun notarytool log "$id" --keychain-profile "$PROFILE" > "$BUILD/notarization-$label-log.json" || true
            fi
        fi
        echo "Notarization was not accepted ($status); inspect $result and its log." >&2
        return 1
    fi
}
# Submit both apps first so their stapled tickets are inside the final disk image.
APPS="$(mktemp -d "$BUILD/notarization-apps.XXXXXX")"
/usr/bin/ditto "$APP" "$APPS/RemCTL Capability Host.app"
/usr/bin/ditto "$INSTALLER" "$APPS/Install RemCTL.app"
/usr/bin/ditto -c -k --keepParent "$APPS" "$BUILD/notarization.zip"
submit "$BUILD/notarization.zip" app
for bundle in "$APP" "$INSTALLER"; do
    /usr/bin/xcrun stapler staple "$bundle"
    /usr/bin/xcrun stapler validate "$bundle"
done
PAYLOAD="$(mktemp -d "$BUILD/dmg-payload.XXXXXX")"
/usr/bin/ditto "$APP" "$PAYLOAD/RemCTL Capability Host.app"
# The installer copies the host into place, so Finder shows only the installer.
/usr/bin/chflags hidden "$PAYLOAD/RemCTL Capability Host.app"
# Gatekeeper refuses unsigned scripts and notarization ignores signed ones, so
# the double-click entry point is a signed app (remctl-installer.swift).
/usr/bin/ditto "$INSTALLER" "$PAYLOAD/Install RemCTL.app"
/usr/bin/hdiutil create -volname RemCTL -srcfolder "$PAYLOAD" -format UDZO "$DMG"
/usr/bin/codesign --sign "$IDENTITY" --timestamp "$DMG"
/usr/bin/codesign --verify --strict -R "=$PUBLISHER" "$DMG"
submit "$DMG" dmg
/usr/bin/xcrun stapler staple "$DMG"
/usr/bin/xcrun stapler validate "$DMG"
/usr/sbin/spctl --assess --type execute "$APP"
/usr/sbin/spctl --assess --type execute "$INSTALLER"
/usr/sbin/spctl --assess --type open --context context:primary-signature "$DMG"
(cd "$BUILD" && /usr/bin/shasum -a 256 "$(basename "$DMG")" > "$(basename "$DMG").sha256")
echo "Notarized release ready: $DMG"
