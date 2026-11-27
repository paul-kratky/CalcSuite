# -*- mode: python ; coding: utf-8 -*-
# The packaged app: one windowed exe with the link tools inside.
#   pyinstaller --noconfirm --distpath dist --workpath build/pyi app.spec
# (Needs PyInstaller in a Python of your choice, and tools/bin/ built: tools/build_tools.py.)

a = Analysis(
    ['tools/mirror.py'],
    pathex=['tools', 'tools/nspire_cli', 'tools/ti84_cli', 'tools/third_party_py'],
    binaries=[('tools/bin/nspire-cli.exe', 'bin'), ('tools/bin/ti84-cli.exe', 'bin'),
              ('tools/bin/ti89-cli.exe', 'bin'), ('tools/bin/luna.exe', 'bin'),
              ('tools/bin/libusb-1.0.dll', 'bin')],
    # tivars (TI-Toolkit, MIT): TI-Basic tokens for the 84 come from its token sheet
    datas=[('assets/app.png', 'assets'),
           ('tools/third_party_py/tivars/tokens/8X.xml', 'tivars/tokens'),
           ('tools/third_party_py/tivars/types/json', 'tivars/types/json'),
           ('tools/third_party_py/tivars/types/schema', 'tivars/types/schema'),
           ('tools/third_party_py/tivars/LICENSE', 'tivars')],
    hiddenimports=['tivars', 'calc_backup'],
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
