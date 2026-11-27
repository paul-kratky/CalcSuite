# This Source Code Form is subject to the terms of the Mozilla Public License, version 1.1
# (third_party/luna/LICENSE). It is a Python port of the .tns writing parts of Luna
# (third_party/luna/luna.c and its modified minizip), by Olivier Armand and contributors.
# CalcSuite's changes: written in Python with no third-party modules, Python programs only.
"""TI-Nspire Python documents (.tns) without luna.exe: a Python Editor page whose program is the
given .py file, exactly as Luna writes it (tests/selftest compare the bytes).

    data = tns_writer.python_tns("quadratic.py", source_bytes)

A .tns is a zip with three TI changes:
  * the first entry's local header starts with "*TIMLP" and the document version ("0500")
    instead of "PK\\3\\4"; the end-of-directory record starts with "TIPD" instead of "PK\\5\\6";
  * .xml entries use method 13: TI's 40-byte header, then the deflated XML XORed with a 3-DES
    keystream (TI's fixed keys; counter IVs from 0x6FE21307, wrapping every 1024 blocks);
  * the XML is TI's tag-compressed form (a closing tag is 0x0E and the opening tag's number).
"""

import struct
import zlib

TIVERSION = 0x0500

# ---- DES (FIPS 46-3), enough for TI's keystream: 3-DES ECB encrypt of 8-byte blocks ----
_PC1 = [57, 49, 41, 33, 25, 17, 9, 1, 58, 50, 42, 34, 26, 18, 10, 2, 59, 51, 43, 35, 27, 19, 11, 3,
        60, 52, 44, 36, 63, 55, 47, 39, 31, 23, 15, 7, 62, 54, 46, 38, 30, 22, 14, 6, 61, 53, 45,
        37, 29, 21, 13, 5, 28, 20, 12, 4]
_PC2 = [14, 17, 11, 24, 1, 5, 3, 28, 15, 6, 21, 10, 23, 19, 12, 4, 26, 8, 16, 7, 27, 20, 13, 2,
        41, 52, 31, 37, 47, 55, 30, 40, 51, 45, 33, 48, 44, 49, 39, 56, 34, 53, 46, 42, 50, 36,
        29, 32]
_SHIFTS = [1, 1, 2, 2, 2, 2, 2, 2, 1, 2, 2, 2, 2, 2, 2, 1]
_IP = [58, 50, 42, 34, 26, 18, 10, 2, 60, 52, 44, 36, 28, 20, 12, 4, 62, 54, 46, 38, 30, 22, 14, 6,
       64, 56, 48, 40, 32, 24, 16, 8, 57, 49, 41, 33, 25, 17, 9, 1, 59, 51, 43, 35, 27, 19, 11, 3,
       61, 53, 45, 37, 29, 21, 13, 5, 63, 55, 47, 39, 31, 23, 15, 7]
_FP = [40, 8, 48, 16, 56, 24, 64, 32, 39, 7, 47, 15, 55, 23, 63, 31, 38, 6, 46, 14, 54, 22, 62, 30,
       37, 5, 45, 13, 53, 21, 61, 29, 36, 4, 44, 12, 52, 20, 60, 28, 35, 3, 43, 11, 51, 19, 59, 27,
       34, 2, 42, 10, 50, 18, 58, 26, 33, 1, 41, 9, 49, 17, 57, 25]
_E = [32, 1, 2, 3, 4, 5, 4, 5, 6, 7, 8, 9, 8, 9, 10, 11, 12, 13, 12, 13, 14, 15, 16, 17, 16, 17, 18,
      19, 20, 21, 20, 21, 22, 23, 24, 25, 24, 25, 26, 27, 28, 29, 28, 29, 30, 31, 32, 1]
_P = [16, 7, 20, 21, 29, 12, 28, 17, 1, 15, 23, 26, 5, 18, 31, 10, 2, 8, 24, 14, 32, 27, 3, 9, 19,
      13, 30, 6, 22, 11, 4, 25]
_S = [
    [14, 4, 13, 1, 2, 15, 11, 8, 3, 10, 6, 12, 5, 9, 0, 7, 0, 15, 7, 4, 14, 2, 13, 1, 10, 6, 12, 11,
     9, 5, 3, 8, 4, 1, 14, 8, 13, 6, 2, 11, 15, 12, 9, 7, 3, 10, 5, 0, 15, 12, 8, 2, 4, 9, 1, 7, 5,
     11, 3, 14, 10, 0, 6, 13],
    [15, 1, 8, 14, 6, 11, 3, 4, 9, 7, 2, 13, 12, 0, 5, 10, 3, 13, 4, 7, 15, 2, 8, 14, 12, 0, 1, 10,
     6, 9, 11, 5, 0, 14, 7, 11, 10, 4, 13, 1, 5, 8, 12, 6, 9, 3, 2, 15, 13, 8, 10, 1, 3, 15, 4, 2,
     11, 6, 7, 12, 0, 5, 14, 9],
    [10, 0, 9, 14, 6, 3, 15, 5, 1, 13, 12, 7, 11, 4, 2, 8, 13, 7, 0, 9, 3, 4, 6, 10, 2, 8, 5, 14,
     12, 11, 15, 1, 13, 6, 4, 9, 8, 15, 3, 0, 11, 1, 2, 12, 5, 10, 14, 7, 1, 10, 13, 0, 6, 9, 8, 7,
     4, 15, 14, 3, 11, 5, 2, 12],
    [7, 13, 14, 3, 0, 6, 9, 10, 1, 2, 8, 5, 11, 12, 4, 15, 13, 8, 11, 5, 6, 15, 0, 3, 4, 7, 2, 12,
     1, 10, 14, 9, 10, 6, 9, 0, 12, 11, 7, 13, 15, 1, 3, 14, 5, 2, 8, 4, 3, 15, 0, 6, 10, 1, 13, 8,
     9, 4, 5, 11, 12, 7, 2, 14],
    [2, 12, 4, 1, 7, 10, 11, 6, 8, 5, 3, 15, 13, 0, 14, 9, 14, 11, 2, 12, 4, 7, 13, 1, 5, 0, 15, 10,
     3, 9, 8, 6, 4, 2, 1, 11, 10, 13, 7, 8, 15, 9, 12, 5, 6, 3, 0, 14, 11, 8, 12, 7, 1, 14, 2, 13,
     6, 15, 0, 9, 10, 4, 5, 3],
    [12, 1, 10, 15, 9, 2, 6, 8, 0, 13, 3, 4, 14, 7, 5, 11, 10, 15, 4, 2, 7, 12, 9, 5, 6, 1, 13, 14,
     0, 11, 3, 8, 9, 14, 15, 5, 2, 8, 12, 3, 7, 0, 4, 10, 1, 13, 11, 6, 4, 3, 2, 12, 9, 5, 15, 10,
     11, 14, 1, 7, 6, 0, 8, 13],
    [4, 11, 2, 14, 15, 0, 8, 13, 3, 12, 9, 7, 5, 10, 6, 1, 13, 0, 11, 7, 4, 9, 1, 10, 14, 3, 5, 12,
     2, 15, 8, 6, 1, 4, 11, 13, 12, 3, 7, 14, 10, 15, 6, 8, 0, 5, 9, 2, 6, 11, 13, 8, 1, 4, 10, 7,
     9, 5, 0, 15, 14, 2, 3, 12],
    [13, 2, 8, 4, 6, 15, 11, 1, 10, 9, 3, 14, 5, 0, 12, 7, 1, 15, 13, 8, 10, 3, 7, 4, 12, 5, 6, 11,
     0, 14, 9, 2, 7, 11, 4, 1, 9, 12, 14, 2, 0, 6, 10, 13, 15, 3, 5, 8, 2, 1, 14, 7, 4, 10, 8, 13,
     15, 12, 9, 0, 3, 5, 6, 11],
]


def _permute(value, table, width):
    """Bit permutation; table positions count from 1 at the most significant of `width` bits"""
    out = 0
    for pos in table:
        out = (out << 1) | ((value >> (width - pos)) & 1)
    return out


def _subkeys(key8):
    k = _permute(int.from_bytes(key8, "big"), _PC1, 64)
    c, d = k >> 28, k & 0xFFFFFFF
    keys = []
    for s in _SHIFTS:
        c = ((c << s) | (c >> (28 - s))) & 0xFFFFFFF
        d = ((d << s) | (d >> (28 - s))) & 0xFFFFFFF
        keys.append(_permute((c << 28) | d, _PC2, 56))
    return keys


def _feistel(r, k):
    x = _permute(r, _E, 32) ^ k
    out = 0
    for i in range(8):
        six = (x >> (42 - 6 * i)) & 0x3F
        row = ((six >> 4) & 2) | (six & 1)
        col = (six >> 1) & 0xF
        out = (out << 4) | _S[i][row * 16 + col]
    return _permute(out, _P, 32)


def _des(block, keys):
    b = _permute(block, _IP, 64)
    l, r = b >> 32, b & 0xFFFFFFFF
    for k in keys:
        l, r = r, l ^ _feistel(r, k)
    return _permute((r << 32) | l, _FP, 64)


def des_encrypt(key8, block8):
    return _des(int.from_bytes(block8, "big"), _subkeys(key8)).to_bytes(8, "big")


_K1 = _subkeys(bytes([0x16, 0xA7, 0xA7, 0x32, 0x68, 0xA7, 0xBA, 0x73]))
_K2 = _subkeys(bytes([0xD9, 0xA8, 0x86, 0xA4, 0x34, 0x45, 0x94, 0x10]))
_K3 = _subkeys(bytes([0x3D, 0x80, 0x8C, 0xB5, 0xDF, 0xB3, 0x80, 0x6B]))
_IVEC_BASE = 0x6FE21307
_stream = bytearray()


def _keystream(n):
    """TI's keystream: E(k1), D(k2), E(k3) of counter blocks (4 zero bytes, then the counter LE);
    it repeats after 1024 blocks. Made once, as far as needed."""
    while len(_stream) < n and len(_stream) < 8192:
        i = len(_stream) // 8
        iv = bytes(4) + ((_IVEC_BASE + i) & 0xFFFFFFFF).to_bytes(4, "little")
        v = _des(int.from_bytes(iv, "big"), _K1)
        v = _des(v, _K2[::-1])
        v = _des(v, _K3)
        _stream.extend(v.to_bytes(8, "big"))
    if n <= len(_stream):
        return bytes(_stream[:n])
    reps = -(-n // 8192)
    return (bytes(_stream) * reps)[:n]


def _deflate(data):
    c = zlib.compressobj(zlib.Z_DEFAULT_COMPRESSION, zlib.DEFLATED, -15, 8, zlib.Z_DEFAULT_STRATEGY)
    return c.compress(data) + c.flush()


# ---- TI's XML entries (from Luna) ----
_TIEN_HEADER = bytes.fromhex(
    "0FCED8D28106865B99DDA23DD9E94BD431BB50B64DB32924706049381C30F899004B9264E458E6BC")
_DOCUMENT_XML = bytes.fromhex(
    "0FCED8D28106865B4A4AC5CEA916F2D51DA82F6E0022F2F0C1A606774D7EA6C03AF05C74BAAA4460"
    "CD58E670D740F69C17DCF09477BFCADEF70209C962B15DEF22FA5137A0819148E1834DAD08312DD0"
    "D3E32D60AB13C2982BED395B092439922F0C7A4C9574913B0CF460CC7327CB077E7FA91787E2ACA2"
    "3BCCA0C4E38E89F0C0519FC2BECE2845C3D41190A6EC53A0FB5B466B41ADE953BB97DBB1D268E2F6"
    "360F2636759BE91F48ADE929670058 19C3C01276A04A73F3B1D30918D606DD9724533E22A4FB8250"
    "7B7C12884E7D4180FE72922987E85C5672FF29168C425B8B9BA7D2086DD398FF91A99EF393A82E1C"
    "B2A96B6ADFF6CE2D1517CE6EC04F9A9C0EDF198D2DFA699F11D22012E07914044E628F0A2A18725A"
    "8B80B33C9BD567594B514DE0C33828C3DCCD3922128C4055".replace(" ", ""))
_PY_HEADER = (b'TIXC0100-1.0?><prob xmlns="urn:TI.Problem" ver="1.0" pbname="">'
              b'<sym>\x0e\x01<card clay="0" h1="10000" h2="10000" w1="10000" '
              b'w2="10000"><isDummyCard>0\x0e\x03<flag>0\x0e\x04<wdgt xmlns:py="urn:'
              b'TI.PythonEditor" type="TI.PythonEditor" ver="1.0"><py:data><py:name>')
_PY_FOOTER = (b"\x0e\x07<py:dirf>-10000000\x0e\x08\x0e\x06<py:mFlags>1024\x0e\x09"
              b"<py:value>10\x0e\x0a\x0e\x05\x0e\x02\x0e\x00")


def _crypted_xml(xmlc):
    d = _deflate(xmlc)
    return _TIEN_HEADER + bytes(a ^ b for a, b in zip(d, _keystream(len(d))))


_DOSDATE = 0x0020  # minizip's "no date" (all-zero fields): month 1 of 1980

# ---- The zip, TI's way (Luna's modified minizip: no dates, version 20, nothing extra) ----
def _is_text(data):
    """zlib's detect_data_type: minizip marks a deflated entry as text (internal attribute 1)
    when it has no control bytes outside tab, line feed, carriage return and 7-27 except 14-25"""
    black = set(range(0, 7)) | set(range(14, 26)) | set(range(28, 32))
    seen = set(data)
    if seen & black:
        return False
    return any(b in (9, 10, 13) or b >= 32 for b in seen)


def _zip(entries, tiversion=TIVERSION):
    """entries: [(name, method, stored bytes, crc, uncompressed size, text)] -> the .tns bytes"""
    out = bytearray()
    central = bytearray()
    for i, (name, method, body, crc, usize, text) in enumerate(entries):
        nb = name.encode("utf-8")
        offset = len(out)
        magic = b"*TIMLP" + ("%04X" % tiversion).encode("ascii") if i == 0 else b"PK\x03\x04"
        out += magic + struct.pack("<HHHHHIIIHH", 20, 0, method, 0, _DOSDATE, crc, len(body), usize,
                                   len(nb), 0)
        out += nb + body
        central += b"PK\x01\x02" + struct.pack("<HHHHHHIIIHHHHHII", 0, 20, 0, method, 0, _DOSDATE, crc,
                                               len(body), usize, len(nb), 0, 0, 0, 1 if text else 0, 0, offset)
        central += nb
    cd_off = len(out)
    out += central
    out += b"TIPD" + struct.pack("<HHHHIIH", 0, 0, len(entries), len(entries), len(central),
                                 cd_off, 0)
    return bytes(out)


def python_tns(py_name, source):
    """A .tns with one Python Editor page whose program is `py_name` ("quadratic.py")"""
    nb = py_name.encode("utf-8")
    if len(nb) > 240:
        raise ValueError("Python file names are limited to 240 characters")
    problem = _crypted_xml(_PY_HEADER + nb + _PY_FOOTER)
    py = _deflate(source)
    crc = lambda b: zlib.crc32(b) & 0xFFFFFFFF
    return _zip([
        ("Document.xml", 13, _DOCUMENT_XML, crc(_DOCUMENT_XML), len(_DOCUMENT_XML), False),
        ("Problem1.xml", 13, problem, crc(problem), len(problem), False),
        (py_name, 8, py, crc(source), len(source), _is_text(source)),
    ])
