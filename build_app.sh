#!/bin/bash
# Build NXT Toolkit as a standalone macOS .app
#
# Prerequisites:
#   pip install pyinstaller pyusb
#   brew install libusb
#
# Output: dist/NXT Toolkit.app

set -euo pipefail
cd "$(dirname "$0")"

APP_NAME="NXT Toolkit"

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
    --add-data "examples:examples" \
    --hidden-import usb.backend.libusb1 \
    --hidden-import usb.backend.libusb0 \
    --hidden-import usb.backend.openusb \
    --hidden-import nxt_toolkit.compiler \
    --hidden-import nxt_toolkit.bytecode \
    --hidden-import nxt_toolkit.dataspace \
    --hidden-import nxt_toolkit.rxe_writer \
    --hidden-import nxt_toolkit.usb \
    --osx-bundle-identifier com.nxttoolkit.app \
    nxt_toolkit/app.py

echo ""
echo "Build complete!"
echo "App: dist/$APP_NAME.app"
echo ""
echo "To create a DMG:"
echo "  hdiutil create -volname '$APP_NAME' -srcfolder 'dist/$APP_NAME.app' -ov 'dist/$APP_NAME.dmg'"
