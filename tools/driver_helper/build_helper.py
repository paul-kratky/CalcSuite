"""Builds tools/bin/calcsuite-driver.exe (our helper on libwdi). Called by tools/build_tools.py.

Steps, all under build/ (nothing is installed, no admin):
  1. build/wdk_redist/: Microsoft's WinUSB co-installers (fetch_wdk_redist.py, pinned SHA-256)
  2. installer_x64.exe from libwdi/installer.c (libwdi runs it, elevated, to install a driver)
  3. embedder.exe from libwdi/embedder.c, then embedded.h: the co-installers, the installer
     and libwdi's .inf templates as C arrays
  4. libwdi's sources + our calcsuite_driver.c -> calcsuite-driver.exe (static, one file)

libwdi's own build is autotools; this is the same compile by hand, with
tools/driver_helper/compat/config.h standing in for the config.h ./configure writes.
Only WinUSB is embedded (no libusb0/libusbK), 64-bit x64 Windows only.
"""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def build(tc, force, run, bin_dir, kit):
    out = os.path.join(bin_dir, "calcsuite-driver.exe")
    if os.path.isfile(out) and not force:
        print("calcsuite-driver.exe: already built")
        return
    wdi = os.path.join(kit, "third_party", "libwdi", "libwdi")
    if not os.path.isfile(os.path.join(wdi, "libwdi.c")):
        print("calcsuite-driver.exe: skipped, third_party/libwdi is missing"
              " (git submodule update --init third_party/libwdi)")
        return
    print("Building calcsuite-driver.exe")
    obj = os.path.join(kit, "build", "driver_helper")
    redist = os.path.join(kit, "build", "wdk_redist")
    os.makedirs(obj, exist_ok=True)
    sys.stdout.flush()
    if subprocess.run([sys.executable, "-I", os.path.join(HERE, "fetch_wdk_redist.py"),
                       redist]).returncode:
        sys.exit("ERROR: could not get the WinUSB co-installers")
    gcc = os.path.join(tc, "gcc.exe")
    fwd = lambda p: p.replace("\\", "/")
    defs = ["-DWINVER=0x0601", "-D_WIN32_WINNT=0x0601", "-D_WIN32_IE=0x0700", "-DCOBJMACROS",
            '-DWDK_DIR="%s"' % fwd(redist), "-I", os.path.join(HERE, "compat")]
    run([gcc, "-O2", "-m64", "-D_WIN64"] + defs + ["-I", wdi, os.path.join(wdi, "installer.c"),
        "-static", "-lsetupapi", "-lnewdev", "-lole32",
        "-o", os.path.join(obj, "installer_x64.exe")], tc)
    embedder = os.path.join(obj, "embedder.exe")
    run([gcc, "-O2"] + defs + ['-DSOLUTIONDIR="%s"' % fwd(obj), "-I", wdi,
        os.path.join(wdi, "embedder.c"), "-o", embedder], tc)
    # The embedder finds the .inf templates relative to its working directory
    p = subprocess.run([embedder, os.path.join(obj, "embedded.h")], cwd=wdi,
                       capture_output=True, text=True)
    if p.returncode:
        print(p.stdout + p.stderr)
        sys.exit("ERROR: libwdi embedder failed")
    objs = []
    for s in ["logging", "tokenizer", "vid_data", "pki", "libwdi_dlg", "libwdi"]:
        o = os.path.join(obj, s + ".o")
        run([gcc, "-std=gnu99", "-O2"] + defs + ["-I", obj, "-I", wdi, "-c",
            os.path.join(wdi, s + ".c"), "-o", o], tc)  # libwdi's code: its warnings are ignored
        objs.append(o)
    windres = os.path.join(tc, "windres.exe")
    rc_objs = [(os.path.join(wdi, "libwdi.rc"), wdi, "libwdi_rc.o"),
               (os.path.join(HERE, "calcsuite_driver.rc"), HERE, "helper_rc.o")]
    for src, inc, name in rc_objs:
        o = os.path.join(obj, name)
        run([windres, "-I", inc, src, "-o", o], tc)
        objs.append(o)
    o = os.path.join(obj, "calcsuite_driver.o")
    run([gcc, "-std=gnu11", "-Wall", "-Wextra", "-Wformat", "-Werror", "-O2",
         "-DWINVER=0x0601", "-D_WIN32_WINNT=0x0601", "-I", wdi, "-c",
         os.path.join(HERE, "calcsuite_driver.c"), "-o", o], tc)
    objs.append(o)
    run([gcc] + objs + ["-static", "-lsetupapi", "-lcfgmgr32", "-lole32", "-lntdll",
        "-lshell32", "-lcrypt32", "-luuid", "-o", out], tc)
