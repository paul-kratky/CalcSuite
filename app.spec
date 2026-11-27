# -*- mode: python ; coding: utf-8 -*-
# The packaged app: one windowed exe with the link tools inside.
#   pyinstaller --noconfirm --distpath dist --workpath build/pyi app.spec
# (Needs PyInstaller in a Python of your choice, and tools/bin/ built: tools/build_tools.py.)

a = Analysis(
    ['tools/mirror.py'],
    pathex=['tools', 'tools/nspire_cli', 'tools/ti84_cli', 'tools/third_party_py'],
    binaries=[('tools/bin/nspire-cli.exe', 'bin'), ('tools/bin/ti84-cli.exe', 'bin'),
              ('tools/bin/ti89-cli.exe', 'bin'), ('tools/bin/luna.exe', 'bin'),
              ('tools/bin/libusb-1.0.dll', 'bin'),
              # The connection doctor's driver helper (LGPL, its own process; docs/dev/DOCTOR.md)
              ('tools/bin/calcsuite-driver.exe', 'bin')],
    # tivars (TI-Toolkit, MIT): TI-Basic tokens for the 84 come from its token sheet
    datas=[('assets/app.png', 'assets'),
           # The Guide panel's guides and the Get programs list
           ('docs/TIBASIC_84.md', 'docs'), ('docs/TIBASIC_89.md', 'docs'),
           ('docs/PYTHON_NSPIRE_GUIDE.md', 'docs'),
           ('tools/program_library.json', '.'),
           # The Functions panel's reference (tools/reference.py)
           ('tools/reference/ti84.json', 'reference'), ('tools/reference/ti89.json', 'reference'),
           ('tools/reference/nspire.json', 'reference'),
           # PC copy's ROM dumpers (GPL, sent to the calculator as files) and their licences
           ('tools/rom_dumpers/cemu_dump.8xp', 'rom_dumpers'),
           ('tools/rom_dumpers/romdump_89t.89z', 'rom_dumpers'),
           ('tools/rom_dumpers/COPYING.GPL-2.txt', 'rom_dumpers'),
           ('tools/rom_dumpers/COPYING.GPL-3.txt', 'rom_dumpers'),
           ('tools/rom_dumpers/LICENSE.CEmu.txt', 'rom_dumpers'),
           ('tools/rom_dumpers/README.md', 'rom_dumpers'),
           ('tools/third_party_py/tivars/tokens/8X.xml', 'tivars/tokens'),
           ('tools/third_party_py/tivars/types/json', 'tivars/types/json'),
           ('tools/third_party_py/tivars/types/schema', 'tivars/types/schema'),
           ('tools/third_party_py/tivars/LICENSE', 'tivars')],
    hiddenimports=['tivars', 'calc_backup', 'calc_doctor', 'ui_panels', 'md_render',
                   'program_library', 'key_strip', 'calc_models', 'ui_theme',
                   'reference'],
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
    name='CalcSuite',
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
