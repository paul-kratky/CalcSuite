"""Build the two helper programs the automation needs, into tools/bin/:

    tools/bin/luna.exe         only with --luna: the self-test's reference for tools/tns_writer.py
                               (third_party/luna, MPL-1.1); CalcSuite itself doesn't use it
    tools/bin/nspire-cli.exe   USB link to the handheld (third_party/libnspire, GPL-3.0+)
    tools/bin/ti84-cli.exe     USB link to the TI-84 Plus CE and (as ti89-cli.exe) TI-89 Titanium
    tools/bin/libusb-1.0.dll   copied from the official libusb release (LGPL-2.1)
    tools/bin/calcsuite-driver.exe  USB driver helper on third_party/libwdi (LGPL-3.0+),
                               see tools/driver_helper/ and docs/dev/DOCTOR.md
    tools/fast84/CSFAST.8xp    the TI-84 Plus CE's Fast mode program (ours, MIT), only when the
                               CE toolchain's fasmg is there (tools/fast84/build.py); else the
                               committed .8xp stays

    python -I tools/build_tools.py            build what is missing
    python -I tools/build_tools.py --force    rebuild everything

Needs a MinGW-w64 gcc/g++. It uses MSYS2's UCRT64 toolchain (C:/msys64/ucrt64/bin)
with its zlib package, or a gcc found on PATH; the environment variable CALCSUITE_MINGW
(a bin folder with gcc.exe) overrides both. No admin rights, nothing is installed:
only files in tools/bin/ are written. The prebuilt .exe files are normally already
there, so you only need this after updating third_party/.
"""

import glob
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(HERE)
TP = os.path.join(KIT, "third_party")
BIN = os.path.join(HERE, "bin")
LUNA = os.path.join(TP, "luna")
LIBNSPIRE = os.path.join(TP, "libnspire", "src")
COMPAT = os.path.join(HERE, "nspire_cli", "compat")
CLI_SRC = os.path.join(HERE, "nspire_cli", "nspire_cli.c")


def find_libusb():
    dirs = sorted(glob.glob(os.path.join(TP, "libusb-*")))
    if not dirs:
        sys.exit("ERROR: third_party/libusb-<version>/ is missing (see third_party/README.md)")
    return dirs[-1]


def find_toolchain():
    # CALCSUITE_MINGW: a folder with gcc.exe/g++.exe, used first when set (CI: setup-msys2
    # installs MSYS2 elsewhere, see .github/workflows/release.yml)
    override = os.environ.get("CALCSUITE_MINGW")
    if override:
        if os.path.isfile(os.path.join(override, "gcc.exe")):
            return override
        sys.exit("ERROR: CALCSUITE_MINGW=%s has no gcc.exe" % override)
    candidates = [r"C:\msys64\ucrt64\bin", r"C:\msys64\mingw64\bin"]
    for d in candidates:
        if os.path.isfile(os.path.join(d, "gcc.exe")) and os.path.isfile(os.path.join(d, "g++.exe")):
            return d
    gcc = shutil.which("gcc")
    if gcc and shutil.which("g++"):
        return os.path.dirname(gcc)
    sys.exit("ERROR: no MinGW-w64 gcc/g++ found. Install MSYS2 (msys2.org, per-user install"
             " works) and run in its shell: pacman -S mingw-w64-ucrt-x86_64-gcc"
             " mingw-w64-ucrt-x86_64-zlib")


def run(cmd, tc):
    env = dict(os.environ)
    env["PATH"] = tc + os.pathsep + env.get("PATH", "")
    out_file = cmd[cmd.index("-o") + 1]
    print("  %s -> %s" % (os.path.basename(cmd[0]), os.path.relpath(out_file, KIT)))
    p = subprocess.run(cmd, env=env, capture_output=True, text=True)
    out = (p.stdout + p.stderr).strip()
    if p.returncode != 0:
        print("  $ " + " ".join(cmd))
        print(out)
        sys.exit("ERROR: build step failed")
    warnings = [l for l in out.splitlines() if "warning:" in l]
    if warnings:
        print("    (%d compiler warning(s) in third-party code, ignored)" % len(warnings))


def build_luna(tc, force):
    out = os.path.join(BIN, "luna.exe")
    if os.path.isfile(out) and not force:
        print("luna.exe: already built")
        return
    print("Building luna.exe")
    srcs = [os.path.join(LUNA, "luna.c"), os.path.join(LUNA, "minizip-1.1", "zip.c"),
            os.path.join(LUNA, "minizip-1.1", "ioapi.c"), os.path.join(LUNA, "DES.c")]
    run([os.path.join(tc, "gcc.exe"), "-O2", "-Wno-unused-parameter", "-DNOCRYPT",
         "-DUSE_FILE32API", "-I", os.path.join(LUNA, "minizip-1.1")] + srcs +
        ["-static", "-lz", "-o", out], tc)


APP_VERSION = (1, 0, 1)  # The helpers' version info (Windows shows it in Properties > Details)


def version_res(tc, name, description, licence):
    """A version-info resource for a helper exe, compiled with windres: an exe without one
    looks more suspicious to antivirus heuristics. Returns the .o to link in."""
    objdir = os.path.join(KIT, "build", "obj")
    os.makedirs(objdir, exist_ok=True)
    v = APP_VERSION
    dotted = "%d.%d.%d" % v
    rc = os.path.join(objdir, name + ".rc")
    with open(rc, "w", encoding="ascii") as fh:
        fh.write("""#include <winresrc.h>
VS_VERSION_INFO VERSIONINFO
 FILEVERSION %d,%d,%d,0
 PRODUCTVERSION %d,%d,%d,0
 FILEOS VOS_NT_WINDOWS32
 FILETYPE VFT_APP
BEGIN
  BLOCK "StringFileInfo"
  BEGIN
    BLOCK "040904b0"
    BEGIN
      VALUE "CompanyName", "CalcSuite"
      VALUE "FileDescription", "%s"
      VALUE "FileVersion", "%s"
      VALUE "InternalName", "%s"
      VALUE "LegalCopyright", "%s"
      VALUE "OriginalFilename", "%s.exe"
      VALUE "ProductName", "CalcSuite"
      VALUE "ProductVersion", "%s"
    END
  END
  BLOCK "VarFileInfo"
  BEGIN
    VALUE "Translation", 0x409, 1200
  END
END
""" % (v + v + (description, dotted, name, licence, name, dotted)))
    obj = os.path.join(objdir, name + "_res.o")
    run([os.path.join(tc, "windres.exe"), rc, "-O", "coff", "-o", obj], tc)
    return obj


def build_cli(tc, force):
    out = os.path.join(BIN, "nspire-cli.exe")
    usb = find_libusb()
    dll_src = os.path.join(usb, "MinGW64", "dll", "libusb-1.0.dll")
    dll_dst = os.path.join(BIN, "libusb-1.0.dll")
    if not os.path.isfile(dll_dst) or force:
        shutil.copyfile(dll_src, dll_dst)
        print("Copied libusb-1.0.dll from " + os.path.basename(usb))
    if os.path.isfile(out) and not force:
        print("nspire-cli.exe: already built")
        return
    print("Building nspire-cli.exe")
    objdir = os.path.join(KIT, "build", "obj")
    os.makedirs(objdir, exist_ok=True)
    inc = ["-I", COMPAT, "-I", LIBNSPIRE, "-I", os.path.join(LIBNSPIRE, "api"),
           "-I", os.path.join(usb, "include")]
    # -mno-ms-bitfields: libnspire relies on GCC's packed-struct layout.
    common = ["-O2", "-mno-ms-bitfields", "-DHAVE_CONFIG_H"] + inc
    c_srcs = ["data.c", "error.c", "init.c", "packet.c", "service.c", "usb.c",
              "services/devinfo.c", "services/dir.c", "services/file.c", "services/os.c",
              "services/screenshot.c"]
    objs = []
    for s in c_srcs:
        o = os.path.join(objdir, s.replace("/", "_").replace(".c", ".o"))
        run([os.path.join(tc, "gcc.exe"), "-std=gnu11", "-c"] + common +
            [os.path.join(LIBNSPIRE, s), "-o", o], tc)
        objs.append(o)
    o = os.path.join(objdir, "cx2.o")
    run([os.path.join(tc, "g++.exe"), "-std=gnu++20", "-c"] + common +
        [os.path.join(HERE, "nspire_cli", "cx2_resume.cpp"), "-o", o], tc)  # Our copy: reconnects
    objs.append(o)
    o = os.path.join(objdir, "nspire_cli.o")
    run([os.path.join(tc, "gcc.exe"), "-std=gnu11", "-Wall", "-Wextra", "-c"] + common +
        [CLI_SRC, "-o", o], tc)
    objs.append(o)
    objs.append(version_res(tc, "nspire-cli", "CalcSuite's TI-Nspire USB link (libnspire)",
                            "GPL-3.0-or-later; includes libnspire (GPL-3.0-or-later)"))
    run([os.path.join(tc, "g++.exe")] + objs +
        [os.path.join(usb, "MinGW64", "static", "libusb-1.0.dll.a"),
         "-static-libgcc", "-static-libstdc++", "-Wl,-Bstatic", "-lwinpthread",
         "-Wl,-Bdynamic", "-lws2_32", "-o", out], tc)


def build_ti84(tc, force):
    out = os.path.join(BIN, "ti84-cli.exe")
    out89 = os.path.join(BIN, "ti89-cli.exe")  # The same program: its name picks the TI-89 Titanium
    if os.path.isfile(out) and os.path.isfile(out89) and not force:
        print("ti84-cli.exe, ti89-cli.exe: already built")
        return
    # Built again when ti89-cli.exe is missing: a ti84-cli.exe without it predates the 89
    print("Building ti84-cli.exe")
    usb = find_libusb()
    run([os.path.join(tc, "gcc.exe"), "-std=gnu11", "-Wall", "-Wextra", "-O2",
         "-I", os.path.join(usb, "include"), os.path.join(HERE, "ti84_cli", "ti84_cli.c"),
         version_res(tc, "ti84-cli", "CalcSuite's TI-84 Plus CE and TI-89 Titanium USB link",
                     "GPL-3.0-or-later"),
         os.path.join(usb, "MinGW64", "static", "libusb-1.0.dll.a"), "-o", out], tc)
    shutil.copyfile(out, out89)
    print("Copied ti84-cli.exe to ti89-cli.exe")


def build_driver_helper(tc, force):
    import importlib.util
    path = os.path.join(HERE, "driver_helper", "build_helper.py")
    spec = importlib.util.spec_from_file_location("build_helper", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.build(tc, force, run, BIN, KIT)


def build_fast84():
    """CSFAST.8xp from tools/fast84/csfast.asm with fasmg; skipped without the CE toolchain"""
    p = subprocess.run([sys.executable, "-I", os.path.join(HERE, "fast84", "build.py")],
                       capture_output=True, text=True)
    print((p.stdout + p.stderr).strip())
    if p.returncode not in (0, 2):
        sys.exit("ERROR: build step failed")


def main(argv):
    force = "--force" in argv
    os.makedirs(BIN, exist_ok=True)
    tc = find_toolchain()
    print("Toolchain: " + tc)
    if "--luna" in argv:  # Only the self-test's reference now: tools/tns_writer.py writes .tns
        build_luna(tc, force)
    build_cli(tc, force)
    build_ti84(tc, force)
    build_driver_helper(tc, force)
    build_fast84()
    print("Done: " + BIN)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
