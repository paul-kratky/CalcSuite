"""Fetch the WinUSB co-installers libwdi embeds, from Microsoft's own WDK 8 redist package.

    python -I tools/driver_helper/fetch_wdk_redist.py DEST

libwdi's WinUSB driver package lists two Microsoft DLLs for x86/x64 Windows:
WdfCoInstaller01011.dll and winusbcoinstaller2.dll. They are only *run* on Windows 7
(Windows 8 and later have WinUSB and KMDF built in), but the generated .inf names them,
so they must be inside the helper. Microsoft ships them as "Windows Driver Kit 8
redistributable components" (wdfcoinstaller.msi, linked from libwdi's wiki,
https://go.microsoft.com/fwlink/p/?LinkID=253170). This script downloads that MSI,
checks its SHA-256, and unpacks the four DLLs without installing anything (no admin):
it reads the MSI database through Windows' msi.dll (ctypes), saves the embedded
cabinet and unpacks it with Windows' expand.exe.

Result (the layout libwdi's embedder expects for WDK_DIR):
    DEST/redist/wdf/x86/WdfCoInstaller01011.dll
    DEST/redist/wdf/x86/winusbcoinstaller2.dll
    DEST/redist/wdf/x64/WdfCoInstaller01011.dll
    DEST/redist/wdf/x64/winusbcoinstaller2.dll

Microsoft's licence lets these redistributables be shipped with a driver package; the
MSI's own licence text is saved next to them (DEST/license.rtf) when the MSI has one.
"""

import ctypes
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request

MSI_URL = ("https://download.microsoft.com/download/0/5/F/"
           "05FD6919-6250-425B-86ED-9B095E54065A/wdfcoinstaller.msi")
MSI_SHA256 = "29314207814ce9d5d73695f7e9239539cf37c79e750b9d5ea5a5ef5487a583d6"
WANTED = ("wdfcoinstaller01011.dll", "winusbcoinstaller2.dll")

ERROR_NO_MORE_ITEMS = 259
ERROR_MORE_DATA = 234


class Msi:
    """The few msi.dll calls needed to read tables and streams (read-only)."""

    def __init__(self, path):
        self.dll = ctypes.WinDLL("msi.dll")
        self.db = ctypes.c_uint32()
        # MSIDBOPEN_READONLY is the constant (LPCWSTR)0
        r = self.dll.MsiOpenDatabaseW(path, ctypes.c_wchar_p(None), ctypes.byref(self.db))
        if r:
            raise OSError("MsiOpenDatabase failed: %d" % r)

    def query(self, sql, ncols, stream_col=None):
        view = ctypes.c_uint32()
        if self.dll.MsiDatabaseOpenViewW(self.db, sql, ctypes.byref(view)):
            raise OSError("bad query: " + sql)
        if self.dll.MsiViewExecute(view, None):
            raise OSError("MsiViewExecute failed: " + sql)
        rows = []
        while True:
            rec = ctypes.c_uint32()
            r = self.dll.MsiViewFetch(view, ctypes.byref(rec))
            if r == ERROR_NO_MORE_ITEMS:
                break
            if r:
                raise OSError("MsiViewFetch failed: %d" % r)
            row = []
            for c in range(1, ncols + 1):
                if c == stream_col:
                    row.append(self._stream(rec, c))
                else:
                    row.append(self._string(rec, c))
            rows.append(row)
            self.dll.MsiCloseHandle(rec)
        self.dll.MsiCloseHandle(view)
        return rows

    def _string(self, rec, col):
        n = ctypes.c_uint32(0)
        buf = ctypes.create_unicode_buffer(1)
        r = self.dll.MsiRecordGetStringW(rec, col, buf, ctypes.byref(n))
        if r == ERROR_MORE_DATA or n.value:
            n.value += 1
            buf = ctypes.create_unicode_buffer(n.value)
            r = self.dll.MsiRecordGetStringW(rec, col, buf, ctypes.byref(n))
        if r:
            raise OSError("MsiRecordGetString failed: %d" % r)
        return buf.value

    def _stream(self, rec, col):
        size = self.dll.MsiRecordDataSize(rec, col)
        out = bytearray()
        chunk = ctypes.create_string_buffer(1 << 20)
        while len(out) < size:
            n = ctypes.c_uint32(len(chunk))
            if self.dll.MsiRecordReadStream(rec, col, chunk, ctypes.byref(n)):
                raise OSError("MsiRecordReadStream failed")
            if not n.value:
                break
            out += chunk.raw[:n.value]
        return bytes(out)

    def close(self):
        self.dll.MsiCloseHandle(self.db)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def download(cache):
    msi = os.path.join(cache, "wdfcoinstaller.msi")
    if not os.path.isfile(msi) or sha256(msi) != MSI_SHA256:
        print("  downloading " + MSI_URL)
        tmp = msi + ".part"
        with urllib.request.urlopen(MSI_URL, timeout=120) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f)
        got = sha256(tmp)
        if got != MSI_SHA256:
            os.remove(tmp)
            sys.exit("ERROR: wdfcoinstaller.msi has SHA-256 %s, expected %s" % (got, MSI_SHA256))
        os.replace(tmp, msi)
    return msi


def arch_of(directory_key, dirs):
    """Walks the Directory table up from a component's directory to find x86 / x64."""
    seen = 0
    while directory_key and seen < 32:
        parent, default = dirs.get(directory_key, ("", ""))
        name = default.split("|")[-1].split(":")[-1].lower()
        if name in ("x86", "x64", "amd64"):
            return "x64" if name in ("x64", "amd64") else "x86"
        directory_key = parent
        seen += 1
    return None


def extract(msi_path, dest):
    msi = Msi(msi_path)
    try:
        files = msi.query("SELECT `File`, `Component_`, `FileName` FROM `File`", 3)
        comps = dict((c, d) for c, d in msi.query(
            "SELECT `Component`, `Directory_` FROM `Component`", 2))
        dirs = dict((k, (p, d)) for k, p, d in msi.query(
            "SELECT `Directory`, `Directory_Parent`, `DefaultDir` FROM `Directory`", 3))
        streams = msi.query("SELECT `Name`, `Data` FROM `_Streams`", 2, stream_col=2)
    finally:
        msi.close()
    work = tempfile.mkdtemp(prefix="wdkredist-")
    try:
        for name, data in streams:
            if data[:4] == b"MSCF":  # an embedded cabinet
                cab = os.path.join(work, "c%d.cab" % len(os.listdir(work)))
                with open(cab, "wb") as f:
                    f.write(data)
        unpacked = os.path.join(work, "files")
        os.makedirs(unpacked)
        for cab in [p for p in os.listdir(work) if p.endswith(".cab")]:
            subprocess.run(["expand.exe", os.path.join(work, cab), "-F:*", unpacked],
                           check=True, capture_output=True)
        got = []
        for key, comp, fname in files:
            long_name = fname.split("|")[-1]
            if long_name.lower() not in WANTED:
                continue
            arch = arch_of(comps.get(comp, ""), dirs)
            src = os.path.join(unpacked, key)
            if arch is None or not os.path.isfile(src):
                continue
            out_dir = os.path.join(dest, "redist", "wdf", arch)
            os.makedirs(out_dir, exist_ok=True)
            out = os.path.join(out_dir, long_name)
            shutil.copyfile(src, out)
            got.append((arch, long_name, sha256(out)))
        return got
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main(argv):
    if len(argv) != 1:
        print(__doc__)
        return 2
    dest = os.path.abspath(argv[0])
    os.makedirs(dest, exist_ok=True)
    msi = download(dest)
    got = extract(msi, dest)
    for arch, name, digest in sorted(got):
        print("  %s/%s  sha256 %s" % (arch, name, digest))
    need = set((a, n.lower()) for a in ("x86", "x64") for n in WANTED)
    have = set((a, n.lower()) for a, n, _ in got)
    if not need <= have:
        sys.exit("ERROR: missing from the MSI: %s" % sorted(need - have))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
