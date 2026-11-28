# -*- mode: python ; coding: utf-8 -*-
# The packaged app: a folder (dist/CalcSuite/: CalcSuite.exe and _internal/ with the link tools),
# zipped by the release workflow with the guides and licences. A folder, not one self-unpacking
# exe: nothing is unpacked into %TEMP% at each start (antivirus heuristics flag that pattern),
# and no UPX for the same reason.
#   pyinstaller --noconfirm --distpath dist --workpath build/pyi app.spec
# (Needs PyInstaller in a Python of your choice, and tools/bin/ built: tools/build_tools.py.
# build/version_info.txt comes from tools/release_files.py version-info.)
import os

a = Analysis(
    ['tools/mirror.py'],
    pathex=['tools', 'tools/nspire_cli', 'tools/ti84_cli', 'tools/third_party_py'],
    binaries=[('tools/bin/nspire-cli.exe', 'bin'), ('tools/bin/ti84-cli.exe', 'bin'),
              ('tools/bin/ti89-cli.exe', 'bin'),
              ('tools/bin/libusb-1.0.dll', 'bin'),
              # The connection doctor's driver helper (LGPL, its own process; docs/dev/DOCTOR.md)
              ('tools/bin/calcsuite-driver.exe', 'bin')],
    # tivars (TI-Toolkit, MIT): TI-Basic tokens for the 84 come from its token sheet
    datas=[('assets/app.png', 'assets'), ('assets/app.ico', 'assets'),
           # The Guide panel's guides and the Get programs list
           ('docs/TIBASIC_84.md', 'docs'), ('docs/TIBASIC_89.md', 'docs'),
           ('docs/PYTHON_NSPIRE_GUIDE.md', 'docs'), ('docs/EMULATORS.md', 'docs'),
           # Save as PDF in Guide and Functions (tools/docs_build/make_pdfs.py builds them)
           ('docs/pdf/*.pdf', 'docs/pdf'),
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
           # The TI-84 Plus CE's Fast mode program (ours, MIT; mirror.py FAST84_PRGM)
           ('tools/fast84/CSFAST.8xp', 'fast84'),
           ('tools/third_party_py/tivars/tokens/8X.xml', 'tivars/tokens'),
           ('tools/third_party_py/tivars/types/json', 'tivars/types/json'),
           ('tools/third_party_py/tivars/types/schema', 'tivars/types/schema'),
           ('tools/third_party_py/tivars/LICENSE', 'tivars')],
    hiddenimports=['tivars', 'calc_backup', 'calc_doctor', 'ui_panels', 'md_render',
                   'program_library', 'key_strip', 'calc_models', 'ui_theme',
                   'reference', 'pc_copy', 'editor', 'code_check', 'paths', 'tns_writer',
                   'solver_builder', 'solver_ui', 'picture_window', 'picture_load', 'picture_formats',
                   'data_bridge', 'tool_tabs', 'macros', 'macros_ui'],
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
    name='CalcSuite',
    icon='assets/app.ico',
    version='build/version_info.txt' if os.path.isfile('build/version_info.txt') else None,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
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
    upx=False,
    upx_exclude=[],
    name='CalcSuite',
)
