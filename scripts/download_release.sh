#!/bin/bash
# Download the default release; the installer verifies publisher and Gatekeeper.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ARCH="$(uname -m)"
case "$ARCH" in arm64|x86_64) ;; *) echo "Unsupported Mac architecture: $ARCH" >&2; exit 1 ;; esac
STAGE="$(mktemp -d "${TMPDIR:-/tmp}/remctl-download.XXXXXX")"
MOUNT="$STAGE/mounted"
mkdir "$MOUNT"
cleanup() {
    /usr/bin/hdiutil detach "$MOUNT" -quiet >/dev/null 2>&1 || true
    /usr/bin/trash "$STAGE" >/dev/null 2>&1 || true
}
trap 'download_status=$?; cleanup; exit "$download_status"' EXIT
URL="https://github.com/viticci/remctl/releases/latest/download/RemCTL-$ARCH.dmg"
echo "Downloading the signed RemCTL release for ${ARCH}..."
if ! /usr/bin/curl --fail --location --silent --show-error --proto '=https' --tlsv1.2 "$URL" -o "$STAGE/RemCTL.dmg"; then
    echo "No downloadable release was available. To build this checkout for free, run ./install.sh --from-source." >&2
    exit 1
fi
/usr/bin/hdiutil attach "$STAGE/RemCTL.dmg" -readonly -nobrowse -mountpoint "$MOUNT" -quiet
/bin/bash "$ROOT/install.sh" --prebuilt "$MOUNT/RemCTL Capability Host.app" "$@"
