# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['nxt_toolkit/app.py'],
    pathex=[],
    binaries=[
        ('/opt/homebrew/lib/libusb-1.0.dylib', '.'),
        ('nbc', '.'),
    ],
    datas=[
        ('examples', 'examples'),
        ('nbc_include', 'nbc_include'),
    ],
    hiddenimports=['usb.backend.libusb1', 'usb.backend.libusb0', 'usb.backend.openusb', 'nxt_toolkit.compiler', 'nxt_toolkit.usb'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='NXT Toolkit',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='NXT Toolkit',
)
app = BUNDLE(
    coll,
    name='NXT Toolkit.app',
    icon=None,
    bundle_identifier='com.nxttoolkit.app',
)
