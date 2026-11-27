# SPDX-License-Identifier: MIT
"""Build CSFAST.8xp (Fast mode for the TI-84 Plus CE) from csfast.asm.

    python -I tools/fast84/build.py            assemble, write CSFAST.8xp and CSFAST.8xp.sha256
    python -I tools/fast84/build.py --check    assemble and compare with the committed .8xp

Needs fasmg and the CE toolchain's eZ80 instruction macros (commands.alm, ez80.alm): the
CE-Programming toolchain release CEdev-Windows.zip v14.2 (its bin/fasmg.exe and meta/*.alm;
v15 has no fasmg). Found in, first to last: the environment variable CALCSUITE_CEDEV (a CEdev
folder), %LOCALAPPDATA%\\CalcSuite\\toolcache\\CEdev-v14.2\\CEdev, C:\\CEdev. Nothing is linked from
the toolchain (no LGPL libraries): fasmg only assembles our own source.

The .8xp is reproducible: the same source gives the same bytes (no date in it). The prebuilt
CSFAST.8xp is committed beside the source with its SHA-256, so users never need the toolchain.
Exit codes: 0 built (or --check matched), 2 no toolchain (skipped), 1 failed / --check differs.
"""

import hashlib
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import calc_files as cf  # noqa: E402

SRC = os.path.join(HERE, "csfast.asm")
OUT = os.path.join(HERE, "CSFAST.8xp")
NAME = b"CSFAST"
TYPE_PROT_PRGM = 0x06  # An assembly program, as the CE toolchain makes them (protected)


def find_cedev():
    cands = [os.environ.get("CALCSUITE_CEDEV"),
             os.path.join(os.environ.get("LOCALAPPDATA", ""), "CalcSuite", "toolcache", "CEdev-v14.2", "CEdev"),
             r"C:\CEdev"]
    for d in cands:
        if d and os.path.isfile(os.path.join(d, "bin", "fasmg.exe" if os.name == "nt" else "fasmg")) and \
                os.path.isfile(os.path.join(d, "meta", "ez80.alm")):
            return d
    return None


def assemble(cedev):
    fasmg = os.path.join(cedev, "bin", "fasmg.exe" if os.name == "nt" else "fasmg")
    env = dict(os.environ, INCLUDE=os.path.join(cedev, "meta"))
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "csfast.bin")
        p = subprocess.run([fasmg, SRC, out], env=env, capture_output=True, text=True)
        if p.returncode != 0:
            raise RuntimeError((p.stdout + p.stderr).strip())
        with open(out, "rb") as f:
            return f.read()


def to_8xp(binary):
    if binary[:2] != b"\xEF\x7B":
        raise RuntimeError("the program doesn't start with the eZ80 token EF 7B")
    data = len(binary).to_bytes(2, "little") + binary
    return cf.ti8x_bytes([(TYPE_PROT_PRGM, NAME, 0, False, data)], comment="CalcSuite Fast mode (MIT)")


def main(argv):
    cedev = find_cedev()
    if not cedev:
        print("fast84: no CE toolchain (fasmg + ez80.alm) found: skipped; the committed CSFAST.8xp stays")
        return 2
    try:
        blob = to_8xp(assemble(cedev))
    except RuntimeError as e:
        print("fast84: build failed:\n%s" % e)
        return 1
    digest = hashlib.sha256(blob).hexdigest()
    if "--check" in argv:
        with open(OUT, "rb") as f:
            same = f.read() == blob
        print("fast84: CSFAST.8xp %s the source (%s)" % ("matches" if same else "DIFFERS FROM", digest))
        return 0 if same else 1
    with open(OUT, "wb") as f:
        f.write(blob)
    with open(OUT + ".sha256", "w", encoding="ascii", newline="\n") as f:
        f.write("%s  CSFAST.8xp\n" % digest)
    print("fast84: CSFAST.8xp %d bytes, sha256 %s" % (len(blob), digest))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
