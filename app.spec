# -*- mode: python ; coding: utf-8 -*-
# The packaged app: one windowed exe with the link tools inside.
#   pyinstaller --noconfirm --distpath dist --workpath build/pyi app.spec
# (Needs PyInstaller in a Python of your choice, and tools/bin/ built: tools/build_tools.py.)

a = Analysis(
    ['tools/mirror.py'],
    pathex=['tools', 'tools/nspire_cli', 'tools/ti84_cli'],
    binaries=[('tools/bin/nspire-cli.exe', 'bin'), ('tools/bin/ti84-cli.exe', 'bin'),
              ('tools/bin/ti89-cli.exe', 'bin'), ('tools/bin/luna.exe', 'bin'),
              ('tools/bin/libusb-1.0.dll', 'bin')],
    datas=[('assets/app.png', 'assets')],
    hiddenimports=[],
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
    a.binaries,
    a.datas,
    [],
    name='Nspire Mirror',
    icon='assets/app.ico',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
