"""The release's files: CalcSuite.exe's version info, and the one zip people download.

    python -I tools/release_files.py version-info 1.0.1     build/version_info.txt (app.spec)
    python -I tools/release_files.py package 1.0.1 [--libusb 1.0.29]
        dist/CalcSuite/ (PyInstaller's folder) + the guides + the licences
        -> out/CalcSuite-1.0.1-win64.zip and out/SHA256SUMS.txt

The zip unpacks to one folder, CalcSuite\\:
    CalcSuite.exe, _internal\\       the app and its link tools
    Guides\\                        the PDFs (also in the app: Save as PDF)
    Licences\\                      CalcSuite's and the helpers' licences, where their source is
    CalcSuite files\\               empty at first: everything the app saves goes here
    Read me first.txt

MIT licence (like the rest of the app).
"""

import glob
import hashlib
import os
import re
import sys
import zipfile

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def version_tuple(v):
    nums = [int(x) for x in re.findall(r"\d+", v)[:3]]
    return tuple(nums + [0] * (4 - len(nums)))


def version_info(version):
    t = version_tuple(version)
    text = """# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(filevers=%(t)r, prodvers=%(t)r, mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'CalcSuite'),
      StringStruct('FileDescription', 'CalcSuite: TI calculators on your PC'),
      StringStruct('FileVersion', '%(v)s'),
      StringStruct('InternalName', 'CalcSuite'),
      StringStruct('LegalCopyright', 'MIT licence; see Licences'),
      StringStruct('OriginalFilename', 'CalcSuite.exe'),
      StringStruct('ProductName', 'CalcSuite'),
      StringStruct('ProductVersion', '%(v)s')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
""" % {"t": t, "v": version.lstrip("v")}
    os.makedirs(os.path.join(KIT, "build"), exist_ok=True)
    path = os.path.join(KIT, "build", "version_info.txt")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    print("Wrote " + path)


README = """CalcSuite %(v)s
===============

1. Unzip this whole folder first (right-click the zip, Extract All), anywhere you like:
   Desktop, Documents, a USB stick. Don't run CalcSuite.exe from inside the zip.
2. Plug in your calculator, switch it on, and open CalcSuite.exe.
   The first time, CalcSuite offers to set up the calculator's USB driver (Windows asks for
   admin rights once).

Everything CalcSuite saves stays in this folder, in "CalcSuite files": screenshots, recordings
and GIFs, the programs you write, build and send, backups, ROMs for the PC copy, programs you
download, and what CalcSuite downloads for itself (ffmpeg, the emulators) in its "cache".
Moving the folder moves all of it; deleting the folder removes CalcSuite.
(The USB driver stays with Windows: Calculator info > Restore TI's driver gives TI's software its driver back.)

The guides are in "Guides" (also in the app: Guide, Functions, Save as PDF).

Help and new versions: https://github.com/paul-kratky/CalcSuite
"""

LICENCES = """Licences
========

CalcSuite (CalcSuite.exe and its Python code): MIT. LICENSE-CalcSuite.txt.
Its .tns writer (tools/tns_writer.py) is a port of Luna's and keeps Luna's MPL-1.1
(luna_MPL-1.1.txt); its source is in the repository below.

The link tools, each its own program in _internal\\bin\\, with their source:
- nspire-cli.exe: GPL-3.0-or-later (links libnspire). Source: tools/nspire_cli/ in
  https://github.com/paul-kratky/CalcSuite and libnspire commit 7d7d962
  (https://github.com/Vogtinator/libnspire). GPL-3.0.txt
- ti84-cli.exe, ti89-cli.exe (the same program): GPL-3.0-or-later. Source: tools/ti84_cli/ in
  https://github.com/paul-kratky/CalcSuite. GPL-3.0.txt
- calcsuite-driver.exe: LGPL-3.0-or-later (links libwdi statically,
  https://github.com/pbatard/libwdi commit 30df0c0). Source: tools/driver_helper/ in
  https://github.com/paul-kratky/CalcSuite. LGPL-3.0.txt (with GPL-3.0.txt, which it builds
  on). It contains Microsoft's WinUSB co-installers from the WDK 8 redistributable components,
  which Microsoft lets driver packages ship.
- libusb-1.0.dll: LGPL-2.1-or-later, the official libusb %(libusb)s release
  (https://github.com/libusb/libusb/releases/tag/v%(libusb)s). libusb_LGPL-2.1.txt
- tivars (TI-Toolkit, MIT): _internal\\tivars\\LICENSE.
- The PC copy's ROM dumpers (GPL, sent to the calculator as files): _internal\\rom_dumpers\\.
- Python and the other parts PyInstaller bundles: their licences are in _internal\\.
"""


def package(version, libusb):
    v = version.lstrip("v")
    src = os.path.join(KIT, "dist", "CalcSuite")
    if not os.path.isfile(os.path.join(src, "CalcSuite.exe")):
        sys.exit("dist/CalcSuite/CalcSuite.exe is missing: run PyInstaller with app.spec first")
    out = os.path.join(KIT, "out")
    os.makedirs(out, exist_ok=True)
    zname = "CalcSuite-%s-win64.zip" % v
    zpath = os.path.join(out, zname)
    root = "CalcSuite"
    licences = [
        ("LICENSE-CalcSuite.txt", os.path.join(KIT, "LICENSE")),
        ("LICENSING.md", os.path.join(KIT, "LICENSING.md")),
        ("GPL-3.0.txt", os.path.join(KIT, "tools", "nspire_cli", "COPYING")),
        ("LGPL-3.0.txt", os.path.join(KIT, "third_party", "libwdi", "COPYING-LGPL")),
        ("luna_MPL-1.1.txt", os.path.join(KIT, "third_party", "luna", "LICENSE")),
        ("libusb_LGPL-2.1.txt", os.path.join(KIT, "build", "libusb_COPYING.txt")),
    ]
    count = 0
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for dirpath, _dirs, files in os.walk(src):
            for f in files:
                full = os.path.join(dirpath, f)
                z.write(full, os.path.join(root, os.path.relpath(full, src)))
                count += 1
        pdfs = sorted(glob.glob(os.path.join(KIT, "docs", "pdf", "*.pdf")))
        if not pdfs:
            sys.exit("No PDFs in docs/pdf: run tools/docs_build/make_pdfs.py")
        for p in pdfs:
            name = os.path.basename(p).replace("CalcSuite - ", "")
            z.write(p, os.path.join(root, "Guides", name))
        for name, path in licences:
            if os.path.isfile(path):
                z.write(path, os.path.join(root, "Licences", name))
            else:
                print("NOTE: licence file missing, not packed: " + path)
        z.writestr(os.path.join(root, "Licences", "README.txt"),
                   (LICENCES % {"libusb": libusb}).replace("\n", "\r\n"))
        z.writestr(os.path.join(root, "Read me first.txt"),
                   (README % {"v": v}).replace("\n", "\r\n"))
        z.writestr(os.path.join(root, "CalcSuite files", "What goes here.txt"),
                   ("CalcSuite saves everything here: captures, programs, backups, ROMs, "
                    "downloads.\n").replace("\n", "\r\n"))
    data = open(zpath, "rb").read()
    sums = "%s  %s\n" % (hashlib.sha256(data).hexdigest(), zname)
    with open(os.path.join(out, "SHA256SUMS.txt"), "w", newline="\n") as fh:
        fh.write(sums)
    print("%s: %d app files, %d PDFs, %.1f MB" % (zname, count, len(pdfs), len(data) / 1e6))
    print(sums.strip())


def main(argv):
    if len(argv) >= 2 and argv[0] == "version-info":
        version_info(argv[1])
    elif len(argv) >= 2 and argv[0] == "package":
        libusb = argv[argv.index("--libusb") + 1] if "--libusb" in argv else "1.0.29"
        package(argv[1], libusb)
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
