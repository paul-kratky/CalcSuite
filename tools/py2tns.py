"""Convert a TI-Nspire Python program (.py) to a TI-Nspire document (.tns), no TI software.

    python -I tools/py2tns.py programs/quadratic.py              -> build/quadratic.tns
    python -I tools/py2tns.py programs/quadratic.py -o out.tns
    python -I tools/py2tns.py --verify build/quadratic.tns       check an existing .tns

Uses Luna (third_party/luna, built to tools/bin/luna.exe by tools/build_tools.py).
The .tns holds one Python Editor page whose program name is the file name
(quadratic.py -> program "quadratic"), like a document saved by TI's own software.

Before packing, the source is normalised: UTF-8 BOM removed, CRLF/CR line ends turned
into LF, and a final newline added. After packing, the .tns is opened again and checked:
TI header, Document.xml and Problem1.xml present (TI-encrypted), the .py entry inflates
to exactly the normalised source with a matching CRC, and the zip directory is complete.

Exit code 0 = ok, 1 = error.
"""

import os
import re
import shutil
import struct
import subprocess
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(HERE)
LUNA = os.path.join(HERE, "bin", "luna.exe" if os.name == "nt" else "luna")
BUILD = os.path.join(KIT, "build")

NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


class TnsError(Exception):
    pass


def normalise(src_bytes):
    if src_bytes.startswith(b"\xef\xbb\xbf"):
        src_bytes = src_bytes[3:]
    src_bytes = src_bytes.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    if not src_bytes.endswith(b"\n"):
        src_bytes += b"\n"
    return src_bytes


def read_entries(data):
    """Parse the local entries of a .tns (a zip whose first signature is '*TIMLPnnnn')."""
    if not data.startswith(b"*TIMLP"):
        raise TnsError("not a TI-Nspire document: header is %r, expected '*TIMLP'" % data[:6])
    version = data[6:10].decode("ascii", "replace")
    entries = []
    p = 0
    while True:
        if p == 0:
            p = 10
        elif data[p:p + 4] == b"PK\x03\x04":
            p += 4
        else:
            break
        if p + 26 > len(data):
            raise TnsError("truncated entry header at byte %d" % p)
        (_ver, flags, method, _t, _d, crc, csize, usize, nlen,
         elen) = struct.unpack("<HHHHHIIIHH", data[p:p + 26])
        p += 26
        name = data[p:p + nlen].decode("utf-8", "replace")
        p += nlen + elen
        body = data[p:p + csize]
        if len(body) != csize:
            raise TnsError("entry %s is truncated" % name)
        p += csize
        if flags & 8:
            p += 16 if data[p:p + 4] == b"PK\x07\x08" else 12
        entries.append({"name": name, "method": method, "crc": crc, "csize": csize,
                        "usize": usize, "body": body})
    if data[p:p + 4] != b"PK\x01\x02":
        raise TnsError("zip central directory missing after the entries (byte %d)" % p)
    # TI replaces the zip end-of-directory signature PK\5\6 with "TIPD".
    eocd = max(data.rfind(b"TIPD"), data.rfind(b"PK\x05\x06"))
    if eocd < 0 or eocd + 22 > len(data):
        raise TnsError("zip end-of-directory record missing")
    total = struct.unpack("<H", data[eocd + 10:eocd + 12])[0]
    if total != len(entries):
        raise TnsError("zip directory lists %d entries, found %d" % (total, len(entries)))
    return version, entries


def verify(tns_path, expect_name=None, expect_source=None, quiet=False):
    if not os.path.isfile(tns_path):
        raise TnsError("no such file: %s" % tns_path)
    with open(tns_path, "rb") as f:
        data = f.read()
    version, entries = read_entries(data)
    names = [e["name"] for e in entries]
    for need in ("Document.xml", "Problem1.xml"):
        if need not in names:
            raise TnsError("%s missing (entries: %s)" % (need, ", ".join(names)))
    for e in entries:
        if e["name"].endswith(".xml") and e["method"] != 13:
            raise TnsError("%s is not TI-encrypted (method %d)" % (e["name"], e["method"]))
    pys = [e for e in entries if e["name"].endswith(".py")]
    if not pys:
        raise TnsError("no .py program inside")
    py = pys[0]
    if expect_name and py["name"] != expect_name:
        raise TnsError("program file is %s, expected %s" % (py["name"], expect_name))
    if py["method"] == 8:
        raw = zlib.decompress(py["body"], -15)
    elif py["method"] == 0:
        raw = py["body"]
    else:
        raise TnsError("%s uses unknown compression %d" % (py["name"], py["method"]))
    if len(raw) != py["usize"] or (zlib.crc32(raw) & 0xFFFFFFFF) != py["crc"]:
        raise TnsError("%s fails its size/CRC check" % py["name"])
    if expect_source is not None and raw != expect_source:
        raise TnsError("%s inside the .tns differs from the source" % py["name"])
    summary = ("tns OK: %s (format %s, %d bytes): %s -> program '%s', %d bytes of Python"
               % (os.path.basename(tns_path), version, len(data), ", ".join(names),
                  py["name"][:-3], len(raw)))
    if not quiet:
        print(summary)
    return summary


def convert(py_path, out_path=None, quiet=False):
    """Convert py_path to a .tns. Returns the .tns path. Raises TnsError on failure."""
    if not os.path.isfile(py_path):
        raise TnsError("no such file: %s" % py_path)
    base = os.path.basename(py_path)
    stem, ext = os.path.splitext(base)
    if ext.lower() != ".py":
        raise TnsError("expected a .py file, got %s" % base)
    if not NAME_RE.match(stem):
        raise TnsError("program name '%s' must start with a letter and use only letters,"
                       " digits and _ (rename the file)" % stem)
    if not os.path.isfile(LUNA):
        raise TnsError("%s is missing: run python -I tools/build_tools.py" % LUNA)
    if out_path is None:
        out_path = os.path.join(BUILD, stem + ".tns")
    out_path = os.path.abspath(out_path)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    with open(py_path, "rb") as f:
        src = normalise(f.read())
    stage = os.path.join(BUILD, "stage")
    if os.path.isdir(stage):
        shutil.rmtree(stage)
    os.makedirs(stage)
    staged = os.path.join(stage, stem + ".py")
    with open(staged, "wb") as f:
        f.write(src)
    tmp_out = os.path.join(stage, stem + ".tns")
    # Run Luna inside the stage folder with bare file names: the name stored in the
    # .tns (and shown as the program name on the handheld) is then exactly "<stem>.py".
    p = subprocess.run([LUNA, stem + ".py", stem + ".tns"], cwd=stage, capture_output=True,
                       text=True)
    if p.returncode != 0 or not os.path.isfile(tmp_out):
        raise TnsError("luna failed (exit %d): %s" % (p.returncode, (p.stdout + p.stderr).strip()))
    verify(tmp_out, expect_name=stem + ".py", expect_source=src, quiet=True)
    if os.path.exists(out_path):
        os.remove(out_path)
    shutil.move(tmp_out, out_path)
    shutil.rmtree(stage, ignore_errors=True)
    if not quiet:
        verify(out_path, expect_name=stem + ".py", expect_source=src)
    return out_path


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0 if argv else 1
    try:
        if argv[0] == "--verify":
            if len(argv) != 2:
                print("usage: py2tns.py --verify FILE.tns")
                return 1
            verify(argv[1])
            return 0
        out = None
        if "-o" in argv:
            i = argv.index("-o")
            out = argv[i + 1]
            argv = argv[:i] + argv[i + 2:]
        if len(argv) != 1:
            print("usage: py2tns.py PROGRAM.py [-o OUT.tns]")
            return 1
        path = convert(argv[0], out)
        print("wrote %s" % path)
        return 0
    except TnsError as e:
        print("ERROR: %s" % e)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
