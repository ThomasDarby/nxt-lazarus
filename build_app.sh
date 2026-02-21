#!/bin/bash
# Build NXT Lazarus as a standalone macOS .app
#
# Prerequisites:
#   pip install pyinstaller pyusb
#   brew install libusb
#
# Output: dist/NXT Lazarus.app

set -euo pipefail
cd "$(dirname "$0")"

APP_NAME="NXT Lazarus"

# Find libusb dylib
LIBUSB=""
for path in /opt/homebrew/lib/libusb-1.0.dylib /usr/local/lib/libusb-1.0.dylib; do
    if [ -f "$path" ]; then
        LIBUSB="$path"
        break
    fi
done

if [ -z "$LIBUSB" ]; then
    echo "Error: libusb not found. Install with: brew install libusb"
    exit 1
fi

echo "Using libusb: $LIBUSB"
echo "Building $APP_NAME..."

pyinstaller \
    --name "$APP_NAME" \
    --windowed \
    --onedir \
    --noconfirm \
    --add-binary "$LIBUSB:." \
    --add-binary "nbc:." \
    --add-data "examples:examples" \
    --add-data "nbc_include:nbc_include" \
    --hidden-import usb.backend.libusb1 \
    --hidden-import usb.backend.libusb0 \
    --hidden-import usb.backend.openusb \
    --hidden-import nxt_toolkit.compiler \
    --hidden-import nxt_toolkit.bytecode \
    --hidden-import nxt_toolkit.dataspace \
    --hidden-import nxt_toolkit.rxe_writer \
    --hidden-import nxt_toolkit.usb \
    --icon icon.icns \
    --osx-bundle-identifier com.nxttoolkit.app \
    nxt_toolkit/app.py

# Lower deployment target to macOS 12.0 (Monterey) so the app runs on
# older systems.  The Python and Homebrew dylibs are typically compiled
# against the host SDK, which embeds a high minos value even though no
# new APIs are actually used.  vtool rewrites the Mach-O load command.
MIN_MACOS="12.0"
echo ""
echo "Patching deployment target → macOS $MIN_MACOS ..."
PATCHED=0
while IFS= read -r binary; do
    if vtool -set-build-version macos "$MIN_MACOS" 15.5 -replace \
             -output "$binary.tmp" "$binary" 2>/dev/null; then
        mv "$binary.tmp" "$binary"
        chmod +x "$binary"
        PATCHED=$((PATCHED + 1))
    else
        rm -f "$binary.tmp"
    fi
done < <(find "dist/$APP_NAME.app" -type f \( -perm +111 -o -name '*.dylib' -o -name '*.so' \) -exec sh -c '
    file "$1" 2>/dev/null | grep -q "Mach-O" && {
        minos=$(vtool -show-build "$1" 2>/dev/null | grep "minos" | head -1 | awk "{print \$2}")
        major=${minos%%.*}
        [ -n "$major" ] && [ "$major" -gt 12 ] 2>/dev/null && echo "$1"
    }
' _ {} \;)
echo "Patched $PATCHED binaries"

# Re-sign after modifying binaries
codesign -fs - --deep "dist/$APP_NAME.app" 2>/dev/null
echo "Re-signed bundle"

echo ""
echo "Build complete!"
echo "App: dist/$APP_NAME.app"
echo ""
echo "To create a DMG:"
echo "  hdiutil create -volname '$APP_NAME' -srcfolder 'dist/$APP_NAME.app' -ov 'dist/$APP_NAME.dmg'"
