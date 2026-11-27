"""Self-test for the TI-84 Plus CE's Fast mode, PC side (no calculator): the frame format's
encoder/decoder round trip, deltas, torn frames, and that the committed CSFAST.8xp is the one
its .sha256 names (and, when the CE toolchain is there, the one the source builds)."""

import hashlib
import os
import random
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
FAST = os.path.join(TOOLS, "fast84")
sys.path.insert(0, FAST)
sys.path.insert(0, TOOLS)
import csnap  # noqa: E402


def _screen(seed):
    """A home screen-like picture: a grey bar, white, some 'text' and a red curve"""
    r = random.Random(seed)
    px = [0xFFFF] * (320 * 240)
    for y in range(30):
        px[y * 320:(y + 1) * 320] = [0x52AA] * 320
    for _ in range(400):
        x, y = r.randrange(320), r.randrange(40, 240)
        px[y * 320 + x] = 0x0000
    for x in range(320):
        y = 120 + (x * x) % 100
        px[min(y, 239) * 320 + x] = 0xF800
    return px


def main():
    failures = 0

    def check(ok, what):
        nonlocal failures
        print("%-4s fast84 %s" % ("PASS" if ok else "FAIL", what))
        failures += not ok

    a = _screen(1)
    snap, chunks, hashes = csnap.encode(a, seq=7)
    h, px = csnap.decode(snap, chunks)
    check(px == a and h["kind"] == csnap.KIND_FULL and h["seq_end"] == 7, "full frame round trip")
    check(csnap.chunks_needed(h) == len(chunks), "chunk count from the header")
    b = list(a)
    for x in range(40, 60):  # "Typing": a few rows change
        b[100 * 320 + x] = 0x001F
    snap2, chunks2, _ = csnap.encode(b, prev_hashes=hashes, delta=True, seq=8, base=7)
    h2, px2 = csnap.decode(snap2, chunks2, prev=px)
    rows = sum(bin(x).count("1") for x in snap2[16:46])
    check(px2 == b and h2["kind"] == csnap.KIND_DELTA and rows <= 2, "delta frame: %d row(s) sent" % rows)
    torn = bytearray(snap)
    torn[-2] ^= 1  # The stamp at CSSNAP's end says another seq
    try:
        csnap.decode(bytes(torn), chunks)
        check(False, "a torn frame is refused")
    except csnap.SnapError:
        check(True, "a torn frame is refused")
    if chunks:
        bad = bytearray(chunks[0])
        bad[0] ^= 1
        try:
            csnap.decode(snap, [bytes(bad)] + chunks[1:])
            check(False, "a chunk of another frame is refused")
        except csnap.SnapError:
            check(True, "a chunk of another frame is refused")
    prg = os.path.join(FAST, "CSFAST.8xp")
    with open(prg, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    with open(prg + ".sha256", encoding="ascii") as f:
        want = f.read().split()[0]
    check(digest == want, "CSFAST.8xp matches CSFAST.8xp.sha256")
    p = subprocess.run([sys.executable, "-I", os.path.join(FAST, "build.py"), "--check"],
                       capture_output=True, text=True)
    if p.returncode == 2:
        print("SKIP fast84 rebuild check (no CE toolchain)")
    else:
        check(p.returncode == 0, "CSFAST.8xp is what csfast.asm builds")
    return failures


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
