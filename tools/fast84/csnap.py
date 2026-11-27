# SPDX-License-Identifier: MIT
"""CSSNAP frames (the TI-84 Plus CE's Fast mode, csfast.asm): the reference decoder.

ti84-cli's `snap` does the same in C; this one is for the tests and for tools that already
hold the AppVars' bytes. The layout is described at the top of csfast.asm.
"""

import struct

MAGIC = b"CSN1"
HDR = 16
BITMAP = 30
SNAP_SIZE = 2048
CHUNK_SIZE = 4096
W, H, HALF = 320, 240, 160
KIND_FULL, KIND_BIG, KIND_DELTA, KIND_READY, KIND_BUSY = 0, 1, 2, 4, 5
TRIG_FULL, TRIG_DELTA, TRIG_NOW = 0x22, 0x23, 0x24  # The key codes that ask for a frame
CHUNK_NAMES = [b"ZZSNP" + bytes((ord("A") + i,)) for i in range(12)]


class SnapError(ValueError):
    pass


def appvar_content(data):
    """An AppVar as `get` reads it (its 2-byte size first) -> its content"""
    if len(data) < 2:
        raise SnapError("short AppVar")
    n = struct.unpack_from("<H", data)[0]
    return data[2:2 + n]


def header(snap):
    """CSSNAP's content -> dict (magic checked)"""
    if len(snap) < HDR or snap[:4] != MAGIC:
        raise SnapError("not a CalcSuite frame (magic)")
    seq_b, seq_e, kind, avail, base = struct.unpack_from("<HHBBH", snap, 4)
    length = snap[12] | snap[13] << 8 | snap[14] << 16
    return {"seq_begin": seq_b, "seq_end": seq_e, "kind": kind, "chunks": avail & 0x0F,
            "idle": bool(avail & 0x80), "base": base, "length": length, "used": snap[15],
            "torn": seq_b != seq_e}


SNAP_ROOM = SNAP_SIZE - HDR - 2   # CSSNAP's payload: its last 2 bytes are a seq stamp
CHUNK_ROOM = CHUNK_SIZE - 4       # A chunk's payload: a seq stamp at each end


def chunks_needed(h):
    """How many ZZSNPn AppVars hold the rest of this frame's payload"""
    rest = h["length"] - SNAP_ROOM
    return 0 if rest <= 0 else (rest + CHUNK_ROOM - 1) // CHUNK_ROOM


def stamps_ok(snap, chunks, seq):
    """Every seq stamp says seq: nothing was read while a picture was being taken"""
    if len(snap) < SNAP_SIZE or struct.unpack_from("<H", snap, SNAP_SIZE - 2)[0] != seq:
        return False
    for c in chunks:
        if len(c) < CHUNK_SIZE or struct.unpack_from("<H", c, 0)[0] != seq or \
                struct.unpack_from("<H", c, CHUNK_SIZE - 2)[0] != seq:
            return False
    return True


def decode(snap, chunks, prev=None):
    """CSSNAP's content + the ZZSNPn contents -> (h, pixels) with pixels a list of 76800
    RGB565 values. A delta needs prev (the frame of seq h['base']); rows not sent are kept."""
    h = header(snap)
    if h["torn"]:
        raise SnapError("torn frame")
    if h["kind"] not in (KIND_FULL, KIND_DELTA):
        raise SnapError("no frame (kind %d)" % h["kind"])
    if not stamps_ok(snap, chunks, h["seq_end"]):
        raise SnapError("torn frame (a seq stamp differs)")
    payload = bytes(snap[HDR:HDR + SNAP_ROOM]) + b"".join(bytes(c[2:2 + CHUNK_ROOM]) for c in chunks)
    if len(payload) < h["length"]:
        raise SnapError("the payload is cut short")
    payload = payload[:h["length"]]
    bitmap, p = payload[:BITMAP], BITMAP
    if h["kind"] == KIND_DELTA:
        if prev is None:
            raise SnapError("a delta needs the frame before")
        px = list(prev)
    else:
        if any(b != 0xFF for b in bitmap):
            raise SnapError("a full frame without every row")
        px = [0] * (W * H)
    for y in range(H):
        if not bitmap[y >> 3] & (1 << (y & 7)):
            continue
        x = y * W
        for _half in range(2):
            left = HALF
            while left:
                if p + 3 > len(payload):
                    raise SnapError("the runs end early")
                n = payload[p] + 1
                c = payload[p + 1] | payload[p + 2] << 8
                p += 3
                if n > left:
                    raise SnapError("a run crosses a half row")
                px[x:x + n] = [c] * n
                x += n
                left -= n
    if p != len(payload):
        raise SnapError("bytes left over after the runs")
    return h, px


def to_ppm(px):
    out = bytearray(W * H * 3)
    for k, v in enumerate(px):
        r5, g6, b5 = (v >> 11) & 31, (v >> 5) & 63, v & 31
        out[3 * k] = (r5 << 3) | (r5 >> 2)
        out[3 * k + 1] = (g6 << 2) | (g6 >> 4)
        out[3 * k + 2] = (b5 << 3) | (b5 >> 2)
    return b"P6\n%d %d\n255\n" % (W, H) + bytes(out)


def row_sums(px, y):
    """The hook's row checksum: Fletcher sums (mod 2^24) of the 24-bit little-endian words in
    the 642 bytes from row y's start (2 of them the next row's; 0 after the last row); the
    low 16 bits of each"""
    raw = bytearray()
    for v in px[y * W:y * W + W + 1]:
        raw += bytes((v & 0xFF, v >> 8))
    raw = raw[:642].ljust(642, b"\0")
    s1 = s2 = 0
    for i in range(0, 642, 3):
        s1 = (s1 + (raw[i] | raw[i + 1] << 8 | raw[i + 2] << 16)) & 0xFFFFFF
        s2 = (s2 + s1) & 0xFFFFFF
    return s1 & 0xFFFF, s2 & 0xFFFF


def encode(px, prev_hashes=None, delta=False, seq=1, base=0, avail=6):
    """The hook's encoder, in Python (for the tests): pixels -> (CSSNAP content, [chunk
    contents], row hashes). Same runs, same row checksums as csfast.asm."""
    hashes, bitmap, runs = [], bytearray(BITMAP), bytearray()
    for y in range(H):
        row = bytearray()
        for half in range(2):
            seg = px[y * W + half * HALF:y * W + (half + 1) * HALF]
            i = 0
            while i < HALF:
                j = i + 1
                while j < HALF and seg[j] == seg[i]:
                    j += 1
                row += bytes((j - i - 1, seg[i] & 0xFF, seg[i] >> 8))
                i = j
        hv = row_sums(px, y)
        hashes.append(hv)
        if delta and prev_hashes is not None and prev_hashes[y] == hv:
            continue
        bitmap[y >> 3] |= 1 << (y & 7)
        runs += row
    payload = bytes(bitmap) + bytes(runs)
    st = struct.pack("<H", seq)
    first = payload[:SNAP_ROOM]
    head = MAGIC + struct.pack("<HHBBH", seq, seq, KIND_DELTA if delta else KIND_FULL, avail, base)
    rest = payload[SNAP_ROOM:]
    chunks = [st + rest[i:i + CHUNK_ROOM].ljust(CHUNK_ROOM, b"\0") + st
              for i in range(0, len(rest), CHUNK_ROOM)]
    head += bytes((len(payload) & 0xFF, len(payload) >> 8 & 0xFF, len(payload) >> 16, len(chunks)))
    return (head + first).ljust(SNAP_SIZE - 2, b"\0") + st, chunks, hashes
