"""What the calculator manager needs that has no link or window in it: the TI file formats
(.8xp and friends for the TI-84 Plus family, .89x for the TI-89 Titanium), variable names,
TI-Basic as text, the parsing of the link tools' listings, and TI's newest OS versions.

The file layouts follow TILP's libtifiles (files8x.cc, files9x.cc) and the name rules its
libticonv (tokens.cc); this file is our own code for them. The TI-Basic token names are the
ones the calculator shows: TI-Toolkit's token sheet for the TI-84 Plus CE (every token, as the
latest OS names it) through `tivars` (MIT, vendored in tools/third_party_py/), else the smaller
table below (set_token_source("builtin") picks it on purpose).
"""

import json
import os
import re
import struct
import sys
import time
import urllib.request

_TP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "third_party_py")
if os.path.isdir(_TP) and _TP not in sys.path:
    sys.path.append(_TP)  # tivars (the packaged app has it inside)

# ---- Listings from the link tools ----


def parse_nspire_ls(lines):
    """nspire-cli `ls` -> [{"name", "dir", "size"}], folders first, then by name"""
    items = []
    for l in lines:
        m = re.match(r"ITEM (dir|file) (\d+) (.*)$", l)
        if m:
            items.append({"name": m.group(3), "dir": m.group(1) == "dir", "size": int(m.group(2))})
    items.sort(key=lambda i: (not i["dir"], i["name"].lower()))
    return items


def parse_dusb_ls(lines):
    """ti84-cli `ls` -> [{"type", "size", "arch", "locked", "folder", "name" (bytes)}]"""
    items = []
    for l in lines:
        m = re.match(r"ITEM type=([0-9a-f]+) size=(\d+) arch=(\d) locked=(\d) "
                     r"folder=(-|[0-9a-f]+) name=(-|[0-9a-f]+)$", l)
        if m:
            unhex = lambda h: b"" if h == "-" else bytes.fromhex(h)
            items.append({"type": int(m.group(1), 16), "size": int(m.group(2)),
                          "arch": m.group(3) == "1", "locked": m.group(4) == "1",
                          "folder": unhex(m.group(5)), "name": unhex(m.group(6))})
    return items


def to_hex(b):
    return b.hex() if b else "-"


def human_size(n):
    if n < 1024:
        return "%d B" % n
    if n < 1024 * 1024:
        return "%.1f KB" % (n / 1024.0)
    return "%.1f MB" % (n / 1048576.0)


# ---- TI-84 Plus family (and TI-83 Premium CE): types, names, .8x? files ----

TYPES_84 = {  # type: (what it is, file extension)
    0x00: ("Real number", "8xn"), 0x01: ("List", "8xl"), 0x02: ("Matrix", "8xm"),
    0x03: ("Equation", "8xy"), 0x04: ("String", "8xs"), 0x05: ("Program", "8xp"),
    0x06: ("Program (locked)", "8xp"), 0x07: ("Picture", "8ci"), 0x08: ("Graph database", "8xd"),
    0x0B: ("Equation", "8xy"), 0x0C: ("Complex number", "8xc"), 0x0D: ("Complex list", "8xl"),
    0x0F: ("Window", "8xw"), 0x10: ("Zoom", "8xz"), 0x11: ("Table setup", "8xt"),
    0x13: ("Backup", "8xb"), 0x15: ("App variable", "8xv"), 0x16: ("Program (temporary)", "8xp"),
    0x17: ("Group", "8xg"), 0x18: ("Fraction", "8xn"), 0x1A: ("Image", "8ca"),
    0x1B: ("Exact complex", "8xc"), 0x1C: ("Exact real", "8xn"), 0x1D: ("Exact real", "8xn"),
    0x1E: ("Exact complex", "8xc"), 0x1F: ("Exact complex", "8xc"), 0x20: ("Exact real", "8xn"),
    0x21: ("Exact real", "8xn"), 0x23: ("Operating system", None), 0x24: ("App", None),
    0x25: ("Certificate", None), 0x26: ("ID list", None), 0x27: ("Certificate", None),
    0x29: ("Clock", None),
}
TEXT_TYPES_84 = (0x03, 0x04, 0x05, 0x06, 0x0B, 0x16)  # Tokenized: shown as TI-Basic text

SUB = "₀₁₂₃₄₅₆₇₈₉"  # Subscript 0-9


def _shift(d):
    """The calculator counts 1, 2, ..., 9, 0: Str1 is 0, Str0 is 9"""
    return 9 if d == 0 else d - 1


def name_text(raw, model="84"):
    """A name from the link (TI-UTF-8) as text for the window"""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def tokenize_name_84(name, vtype):
    """A name as the link gives it ("L₁", "Str1", "[A]", "PRGM1") -> the bytes a .8x? file
    holds (libticonv: ticonv_varname_tokenize)"""
    s = name
    sub = lambda c: SUB.index(c) if c in SUB else -1
    if len(s) == 2 and s[0] == "L" and 1 <= sub(s[1]) <= 6 and vtype in (0x01, 0x0D):
        return bytes((0x5D, sub(s[1]) - 1))
    if vtype in (0x01, 0x0D):  # A named list: its letters after the list token
        return b"\x5D" + s.lstrip("ʟ").encode("latin-1", "replace")[:7]
    if len(s) == 3 and s[0] == "[" and s[2] == "]" and "A" <= s[1] <= "J":
        return bytes((0x5C, ord(s[1]) - 65))
    if len(s) == 2 and s[0] == "Y" and sub(s[1]) >= 0:
        return bytes((0x5E, 0x10 + _shift(sub(s[1]))))
    if len(s) == 3 and s[0] in "XY" and 1 <= sub(s[1]) <= 6:
        return bytes((0x5E, 0x20 + 2 * (sub(s[1]) - 1) + (s[0] == "Y")))
    if len(s) == 2 and s[0] == "r" and 1 <= sub(s[1]) <= 6:
        return bytes((0x5E, 0x40 + sub(s[1]) - 1))
    if vtype in (0x03, 0x0B) and s in ("u", "v", "w"):
        return bytes((0x5E, 0x80 + "uvw".index(s)))
    for word, tok in (("Pic", 0x60), ("GDB", 0x61), ("Str", 0xAA), ("Image", 0x3C)):
        if s.startswith(word) and len(s) == len(word) + 1 and s[-1].isdigit():
            return bytes((tok, _shift(int(s[-1]))))
    return s.replace("θ", "[").encode("latin-1", "replace")  # theta is 0x5B


NAME_TOKENS = (0x3C, 0x5C, 0x5D, 0x5E, 0x60, 0x61, 0xAA)


def strip_name(raw):
    """A file's 8-byte name without its padding; "L1" is 5D 00, so a token keeps 2 bytes"""
    keep = 2 if raw[:1] and raw[0] in NAME_TOKENS else 0
    return raw[:keep] + raw[keep:].rstrip(b"\x00") if keep else raw.rstrip(b"\x00")


def detokenize_name_84(raw, vtype):
    """The bytes of a .8x? file's name -> the name the link wants (the reverse of the above)"""
    raw = strip_name(raw)
    if len(raw) == 2:
        a, b = raw[0], raw[1]
        unshift = lambda v: 0 if v == 9 else v + 1
        if a == 0x5C and b <= 9:
            return "[%s]" % chr(65 + b)
        if a == 0x5D and b <= 5:
            return "L" + SUB[b + 1]
        if a == 0x5E and 0x10 <= b <= 0x19:
            return "Y" + SUB[unshift(b - 0x10)]
        if a == 0x5E and 0x20 <= b <= 0x2B:
            return "XY"[(b - 0x20) & 1] + SUB[(b - 0x20) // 2 + 1] + "ᴛ"
        if a == 0x5E and 0x40 <= b <= 0x45:
            return "r" + SUB[b - 0x40 + 1]
        if a == 0x5E and 0x80 <= b <= 0x82:
            return "uvw"[b - 0x80]
        for word, tok in (("Pic", 0x60), ("GDB", 0x61), ("Str", 0xAA), ("Image", 0x3C)):
            if a == tok and b <= 9:
                return "%s%d" % (word, unshift(b))
    if raw[:1] == b"\x5D":
        return raw[1:].decode("latin-1")
    return raw.decode("latin-1").replace("[", "θ")


def safe_file_name(name):
    """A calculator name as part of a PC file name"""
    out = []
    for c in name:
        if c in SUB:
            out.append(str(SUB.index(c)))
        elif c == "θ":
            out.append("theta")
        elif c.isalnum() or c in "-_.":
            out.append(c)
        elif c in "[]":
            continue
        else:
            out.append("_")
    return "".join(out) or "var"


def ti8x_bytes(entries, comment="Saved by CalcSuite"):
    """A .8x? file (the TI-83 Plus / 84 Plus family's format, "**TI83F*"). entries: list of
    (type, name bytes, version, archived, data)."""
    body = b""
    for vtype, name, version, archived, data in entries:
        name = (name + b"\x00" * 8)[:8]
        body += struct.pack("<HHB", 0x0D, len(data), vtype) + name
        body += bytes((version & 0xFF, 0x80 if archived else 0x00))
        body += struct.pack("<H", len(data)) + data
    if len(body) > 65535:
        raise ValueError("too big for one TI file")
    head = b"**TI83F*\x1a\x0a\x00" + comment.encode("ascii")[:42].ljust(42, b"\x00")
    return head + struct.pack("<H", len(body)) + body + struct.pack("<H", sum(body) & 0xFFFF)


def read_ti8x(blob):
    """A .8x? file -> [(type, name bytes, version, archived, data)]. Raises ValueError."""
    if len(blob) < 57 or blob[:8] not in (b"**TI83F*", b"**TI83**", b"**TI82**"):
        raise ValueError("not a TI-83 Plus / 84 Plus file")
    if blob[:8] != b"**TI83F*":
        raise ValueError("a file for an older calculator (%s)" % blob[:8].decode("ascii", "replace"))
    length = struct.unpack_from("<H", blob, 53)[0]
    body = blob[55:55 + length]
    if len(body) != length:
        raise ValueError("the file is cut short")
    if len(blob) >= 57 + length and struct.unpack_from("<H", blob, 55 + length)[0] != sum(body) & 0xFFFF:
        raise ValueError("the file's checksum is wrong")
    entries, p = [], 0
    while p + 4 <= len(body):
        hlen, dlen = struct.unpack_from("<HH", body, p)
        if hlen not in (0x0B, 0x0D) or p + 2 + hlen + 2 + dlen > len(body):
            raise ValueError("a variable in the file can't be read")
        vtype = body[p + 4]
        name = strip_name(body[p + 5:p + 13])
        version, flag = (body[p + 13], body[p + 14]) if hlen == 0x0D else (0, 0)
        p += 2 + hlen
        dlen2 = struct.unpack_from("<H", body, p)[0]
        data = body[p + 2:p + 2 + dlen2]
        entries.append((vtype, name, version, bool(flag & 0x80), data))
        p += 2 + dlen2
    if not entries:
        raise ValueError("no variable in the file")
    return entries


# ---- TI-89 Titanium: types, .89? files ----

TYPES_89 = {
    0x00: ("Expression", "89e"), 0x04: ("List", "89l"), 0x06: ("Matrix", "89m"),
    0x0A: ("Data", "89c"), 0x0B: ("Text", "89t"), 0x0C: ("String", "89s"),
    0x0D: ("Graph database", "89d"), 0x0E: ("Figure", "89a"), 0x10: ("Picture", "89i"),
    0x12: ("Program", "89p"), 0x13: ("Function", "89f"), 0x14: ("Macro", "89x"),
    0x18: ("Clock", None), 0x1C: ("Other (zipped etc.)", "89y"), 0x1D: ("Backup", None),
    0x1F: ("Folder", None), 0x21: ("Assembly program", "89z"), 0x22: ("ID list", None),
    0x23: ("Operating system", None), 0x24: ("App", None),
}
TEXT_TYPES_89 = (0x0B, 0x0C)


def ti89_bytes(vtype, folder, name, archived, data, comment="Saved by CalcSuite"):
    """A single-variable .89? file (libtifiles: ti9x_file_write_regular)"""
    pad8 = lambda b: (b + b"\x00" * 8)[:8]
    head = b"**TI89**" + b"\x01\x00" + pad8(folder) + comment.encode("ascii")[:40].ljust(40, b"\x00")
    head += struct.pack("<H", 1)
    head += struct.pack("<I", 0x52) + pad8(name) + bytes((vtype, 3 if archived else 0)) + b"\x00\x00"
    head += struct.pack("<I", 0x52 + 4 + len(data) + 2) + struct.pack("<H", 0x5AA5)
    assert len(head) == 0x52
    return head + b"\x00\x00\x00\x00" + data + struct.pack("<H", sum(data) & 0xFFFF)


def ti89_text(vtype, data):
    """A TI-89 Text or String variable as text, or None"""
    if len(data) < 4:
        return None
    body = data[2:]  # Its size, big endian
    if vtype == 0x0C:  # String: 0, the text, 0, the type tag 0x2D
        return body[1:].split(b"\x00")[0].decode("latin-1")
    if vtype == 0x0B:  # Text: a cursor offset, then lines that start with a command byte
        lines = body[2:].split(b"\x00")[0].split(b"\r")
        return "\n".join(l[1:].decode("latin-1") for l in lines)
    return None


# ---- Numbers, lists and matrices (the data bridge: data_bridge.py) ----
#
# The 84 family keeps a real number in 9 bytes: a type byte (bits 0-5 the type: 0x00 real, 0x0C
# a complex number's part; bit 7 the sign), the exponent + 0x80, then 14 BCD digits d.ddd...
# (16 is 00 81 16 00..., read from a TI-84 Plus CE backup). A complex number is two of them
# (real, imaginary; both typed 0x0C). A list (0x01 real, 0x0D complex): its length (2 bytes,
# little endian), then its numbers; a matrix (0x02, real only): columns, rows (a byte each),
# then the numbers row by row. OS 5.x's exact forms (what Ans can hold in MATHPRINT) are read
# as their value: 0x18/0x1B fractions (a float), 0x1C/0x1D radicals ((±a√b ± c√d)/e in BCD
# nibbles), 0x20/0x21 and 0x1E/0x1F multiples of π (TI-Toolkit's tivars documents them).
#
# The 89 keeps an expression backwards, its tag last (TIGCC's estack documentation; checked
# against TI-89 Titanium OS 3.10 backups): an integer is its bytes (little endian), their count,
# then 0x1F (0x20: negative; 0 has no bytes); a fraction its denominator then its numerator
# (each an integer without the tag), then 0x21 (0x22: negative); a float a 2-byte exponent
# (+0x4000, bit 15 the sign, big endian) and 14 BCD digits d.ddd..., then 0x23; a complex
# number its real then its imaginary part, then 0x9D; i alone is 0x26; a list 0xE5, its
# elements last first, then 0xD9; a matrix is a list of lists (its rows). The variable's data
# starts with the expression's size (2 bytes, big endian).

import collections as _collections
from decimal import Decimal, Context, ROUND_HALF_UP, InvalidOperation
from fractions import Fraction

TIComplex = _collections.namedtuple("TIComplex", "re im")
_C14 = Context(prec=14, rounding=ROUND_HALF_UP)
_C40 = Context(prec=40)
_PI = Decimal("3.14159265358979323846264338327950288419716939937510")
REAL_TYPES_84 = (0x00, 0x18, 0x1C, 0x20, 0x21)
COMPLEX_TYPES_84 = (0x0C, 0x1B, 0x1D, 0x1E, 0x1F)
LIST_MAX_84, MATRIX_MAX_84 = 999, 99


def _bcd(b):
    s = b.hex()
    if not s.isdigit():
        raise ValueError("not a TI number (a digit isn't 0-9)")
    return s


def _sci(v):
    """A non-zero Decimal rounded to 14 digits -> (negative, 14 digits as text, exponent)"""
    t = _C14.plus(abs(Decimal(v)))
    digits = "".join(str(d) for d in t.as_tuple().digits)
    return v < 0, (digits + "0" * 14)[:14], t.adjusted()


def _decimal(v):
    """int, Fraction or Decimal -> Decimal (a fraction to 40 digits: rounded to 14 later)"""
    if isinstance(v, Fraction):
        return _C40.divide(Decimal(v.numerator), Decimal(v.denominator))
    if isinstance(v, (int, Decimal)) and not isinstance(v, bool):
        d = Decimal(v)
        if not d.is_finite():
            raise ValueError("%s isn't a number a calculator keeps" % v)
        return d
    raise ValueError("%r isn't a real number" % (v,))


def real84_bytes(v, part=False):
    """A real number -> its 9 bytes on the 84 (part: as half of a complex number, type 0x0C).
    Rounds to 14 digits; past 9.9999999999999E99 raises ValueError, under 1E-99 is 0."""
    d = _decimal(v)
    kind = 0x0C if part else 0x00
    if d == 0:
        return bytes((kind, 0x80)) + bytes(7)
    neg, digits, exp = _sci(d)
    if exp > 99:
        raise ValueError("%s is too big for the TI-84 Plus (up to 9.9999999999999E99)" % number_text(d))
    if exp < -99:
        return bytes((kind, 0x80)) + bytes(7)
    return bytes((kind | (0x80 if neg else 0), 0x80 + exp)) + bytes.fromhex(digits)


def _radical84(b):
    d = b[1:9].hex()
    if not d[1:].isdigit() or d[0] not in "0123":
        raise ValueError("not a TI radical (a digit isn't 0-9)")
    sign = int(d[0])
    den, rs, ls, rr, lr = (int(d[i:i + 3]) for i in (1, 4, 7, 10, 13))
    if den == 0:
        raise ValueError("a TI radical over 0")
    left = _C40.multiply(Decimal(-ls if sign & 1 else ls), _C40.sqrt(Decimal(lr)))
    right = _C40.multiply(Decimal(-rs if sign & 2 else rs), _C40.sqrt(Decimal(rr)))
    return _C14.divide(_C40.add(left, right), Decimal(den))


def real84_value(b):
    """9 bytes of an 84 number (any real type, or a complex number's half) -> Decimal"""
    if len(b) < 9:
        raise ValueError("a TI-84 number is 9 bytes")
    kind = b[0] & 0x3F
    if kind in (0x1C, 0x1D):
        return _radical84(b)
    v = Decimal(int(_bcd(b[2:9]))).scaleb(b[1] - 0x80 - 13)
    if b[0] & 0x80:
        v = -v
    if kind in (0x20, 0x21, 0x1E, 0x1F):  # A multiple of π
        v = _C14.multiply(v, _PI)
    return v


def complex84_bytes(v):
    if not isinstance(v, TIComplex):
        v = TIComplex(v, 0)
    return real84_bytes(v.re, True) + real84_bytes(v.im, True)


def complex84_value(b):
    if len(b) < 18:
        raise ValueError("a TI-84 complex number is 18 bytes")
    return TIComplex(real84_value(b[:9]), real84_value(b[9:18]))


def list84_data(values):
    """Numbers -> (type 0x01 real list or 0x0D complex list, the variable's data)"""
    values = list(values)
    if len(values) > LIST_MAX_84:
        raise ValueError("a TI-84 list holds up to %d numbers (this has %d)" % (LIST_MAX_84, len(values)))
    cplx = any(isinstance(v, TIComplex) for v in values)
    one = complex84_bytes if cplx else real84_bytes
    return (0x0D if cplx else 0x01), struct.pack("<H", len(values)) + b"".join(one(v) for v in values)


def list84_values(vtype, data):
    """A list's data (0x01 or 0x0D) -> [Decimal or TIComplex]"""
    if len(data) < 2:
        raise ValueError("the list is cut short")
    n = struct.unpack_from("<H", data)[0]
    size = 18 if vtype == 0x0D else 9
    if len(data) < 2 + n * size:
        raise ValueError("the list is cut short (%d numbers said, %d bytes)" % (n, len(data)))
    one = complex84_value if vtype == 0x0D else real84_value
    return [one(data[2 + k * size:2 + (k + 1) * size]) for k in range(n)]


def _rect(rows, most=None, what="matrix"):
    rows = [list(r) for r in rows]
    if not rows or not rows[0]:
        raise ValueError("a %s needs at least one row and one column" % what)
    if any(len(r) != len(rows[0]) for r in rows):
        raise ValueError("every row of a %s has the same number of columns" % what)
    if most and (len(rows) > most or len(rows[0]) > most):
        raise ValueError("a TI-84 matrix is up to %d x %d" % (most, most))
    return rows


def matrix84_data(rows):
    """Rows of real numbers -> a matrix's data (type 0x02)"""
    rows = _rect(rows, MATRIX_MAX_84)
    if any(isinstance(v, TIComplex) for r in rows for v in r):
        raise ValueError("the TI-84's matrices hold real numbers only")
    return bytes((len(rows[0]), len(rows))) + b"".join(real84_bytes(v) for r in rows for v in r)


def matrix84_rows(data):
    if len(data) < 2:
        raise ValueError("the matrix is cut short")
    cols, nrows = data[0], data[1]
    if len(data) < 2 + cols * nrows * 9:
        raise ValueError("the matrix is cut short")
    return [[real84_value(data[2 + (r * cols + c) * 9:2 + (r * cols + c + 1) * 9]) for c in range(cols)]
            for r in range(nrows)]


def value84(vtype, data):
    """An 84 variable as a value: Decimal (a real, the exact forms as their value), TIComplex,
    a list of them, a matrix (a list of rows) or a str (a string's text). ValueError else."""
    if vtype in REAL_TYPES_84:
        return real84_value(data)
    if vtype in COMPLEX_TYPES_84:
        return complex84_value(data)
    if vtype in (0x01, 0x0D):
        return list84_values(vtype, data)
    if vtype == 0x02:
        return matrix84_rows(data)
    if vtype == 0x04:
        return detokenize_84(data)
    raise ValueError("a %s isn't a number, list or matrix"
                     % TYPES_84.get(vtype, ("type %02X" % vtype,))[0].lower())


def _int89_at(b, p):
    """The integer whose byte count is at b[p] -> (value, the index below it)"""
    if p < 0:
        raise ValueError("the expression is cut short")
    n = b[p]
    if p - n < 0:
        raise ValueError("the expression is cut short")
    return int.from_bytes(b[p - n:p], "little"), p - n - 1


def _read89(b, p, depth):
    """The value whose tag is at b[p] -> (value, the index below it)"""
    if p < 0:
        raise ValueError("the expression is cut short")
    tag = b[p]
    if tag in (0x1F, 0x20):
        v, q = _int89_at(b, p - 1)
        return (-v if tag == 0x20 else v), q
    if tag in (0x21, 0x22):
        num, q = _int89_at(b, p - 1)
        den, q = _int89_at(b, q)
        if den == 0:
            raise ValueError("a fraction over 0")
        return Fraction(-num if tag == 0x22 else num, den), q
    if tag == 0x23:
        if p < 9:
            raise ValueError("the expression is cut short")
        e = (b[p - 9] << 8) | b[p - 8]
        v = Decimal(int(_bcd(b[p - 7:p]))).scaleb((e & 0x7FFF) - 0x4000 - 13)
        return (-v if e & 0x8000 else v), p - 10
    if tag == 0x9D:
        im, q = _read89(b, p - 1, 9)
        re_, q = _read89(b, q, 9)
        if any(isinstance(x, (TIComplex, list, str)) for x in (re_, im)):
            raise ValueError("a complex number whose parts aren't numbers")
        return TIComplex(re_, im), q
    if tag == 0x26:
        return TIComplex(0, 1), p - 1
    if tag == 0xD9:
        if depth > 1:
            raise ValueError("a list too deep for a list or matrix")
        items, q = [], p - 1
        while True:
            if q < 0:
                raise ValueError("a list without its end")
            if b[q] == 0xE5:
                return items, q - 1
            v, q = _read89(b, q, depth + 1)
            items.append(v)
    if tag == 0x2D and depth == 0:  # A string: 0, the text, 0, then the tag
        if p < 2 or b[p - 1] != 0:
            raise ValueError("a string without its end")
        s = b.rfind(b"\x00", 0, p - 1)
        if s < 0:
            raise ValueError("a string without its start")
        back = {c: u for u, c in CHARS_89.items()}
        back[0xAD] = "-"
        return "".join(back.get(c, chr(c)) for c in b[s + 1:p - 1]), s - 1
    raise ValueError("an expression (tag %02X), not a number, list or matrix" % tag)


def value89(data):
    """A TI-89 variable's data (expression 0x00, list 0x04, matrix 0x06, string 0x0C) -> int,
    Fraction, Decimal (a float), TIComplex, a list of them, a matrix (a list of rows) or a str.
    ValueError for anything else (an expression with variables, a polar number...)."""
    if len(data) < 3:
        raise ValueError("the variable is cut short")
    n = struct.unpack_from(">H", data)[0]
    body = data[2:2 + n]
    if len(body) != n or n == 0:
        raise ValueError("the variable is cut short")
    v, q = _read89(body, n - 1, 0)
    if q != -1:
        raise ValueError("more than one value in the variable")
    if isinstance(v, list) and v and isinstance(v[0], list):
        if any(not isinstance(r, list) or len(r) != len(v[0]) for r in v):
            raise ValueError("a matrix whose rows aren't the same length")
    elif isinstance(v, list) and any(isinstance(x, list) for x in v):
        raise ValueError("a list of lists that isn't a matrix")
    return v


def _int89_bytes(n):
    mag = abs(n)
    bs = mag.to_bytes((mag.bit_length() + 7) // 8, "little")
    if len(bs) > 255:
        raise ValueError("the integer is too long for the TI-89")
    return bs + bytes((len(bs), 0x20 if n < 0 else 0x1F))


def number89_bytes(v):
    """One number -> its bytes in an 89 expression: an int (exact), a Fraction (exact), a
    Decimal (a float, 14 digits, up to 9.9999999999999E999) or a TIComplex of them"""
    if isinstance(v, TIComplex):
        if isinstance(v.re, TIComplex) or isinstance(v.im, TIComplex):
            raise ValueError("a complex number's parts are real")
        return number89_bytes(v.re) + number89_bytes(v.im) + b"\x9D"
    if isinstance(v, bool):
        raise ValueError("not a number")
    if isinstance(v, int):
        return _int89_bytes(v)
    if isinstance(v, Fraction):
        if v.denominator == 1:
            return _int89_bytes(v.numerator)
        den = _int89_bytes(v.denominator)[:-1]
        num = _int89_bytes(abs(v.numerator))[:-1]
        return den + num + (b"\x22" if v < 0 else b"\x21")
    d = _decimal(v)
    zero = b"\x40\x00" + bytes(7) + b"\x23"
    if d == 0:
        return zero
    neg, digits, exp = _sci(d)
    if exp > 999:
        raise ValueError("%s is too big for the TI-89 (up to 9.9999999999999E999)" % number_text(d))
    if exp < -999:
        return zero
    e = (0x4000 + exp) | (0x8000 if neg else 0)
    return struct.pack(">H", e) + bytes.fromhex(digits) + b"\x23"


def _sized89(body):
    if len(body) > 65000:
        raise ValueError("too big for one TI-89 variable (%d bytes)" % len(body))
    return struct.pack(">H", len(body)) + body


def list89_data(values):
    """Numbers -> a TI-89 list's data (type 0x04)"""
    return _sized89(b"\xE5" + b"".join(number89_bytes(v) for v in reversed(list(values))) + b"\xD9")


def matrix89_data(rows):
    """Rows of numbers -> a TI-89 matrix's data (type 0x06)"""
    rows = _rect(rows)
    body = b"".join(b"\xE5" + b"".join(number89_bytes(v) for v in reversed(r)) + b"\xD9"
                    for r in reversed(rows))
    return _sized89(b"\xE5" + body + b"\xD9")


def number89_data(v):
    """One number -> a TI-89 expression variable's data (type 0x00)"""
    return _sized89(number89_bytes(v))


_NUM_RE = r"(?:\d+\.?\d*|\.\d+)(?:E[+-]?\d+)?"
_REAL_RE = re.compile(r"^[+-]?" + _NUM_RE + "$")
_FRAC_RE = re.compile(r"^([+-]?\d+)/(\d+)$")


def parse_number(text):
    """A cell's text -> int (digits only), Fraction ("1/3"), Decimal ("2.5", "1E-5", "2."),
    TIComplex ("3+2i", "-i", "2.5E3-1E-2i"), or None for an empty cell. Takes the calculators'
    own minus signs (⁻ −), ᴇ for E, 𝑖 or j for i, and a decimal comma ("2,5"). ValueError
    names what it can't read."""
    raw = text
    s = (text or "").strip().replace(" ", "").replace(" ", "")
    if not s:
        return None
    if len(s) > 400:
        raise ValueError("%r... is too long for a number" % s[:20])
    for a, b in (("−", "-"), ("⁻", "-"), ("‐", "-"), ("ᴇ", "E"), ("e", "E"), ("𝑖", "i"),
                 ("ⅈ", "i"), ("j", "i"), ("﹢", "+")):
        s = s.replace(a, b)
    if "," in s and "." not in s and s.count(",") == 1:
        s = s.replace(",", ".")
    if s.endswith("i"):
        body = s[:-1]
        cut = max((k for k in range(1, len(body)) if body[k] in "+-" and body[k - 1] != "E"),
                  default=0)
        re_text, im_text = body[:cut], body[cut:]
        if im_text in ("", "+", "-"):
            im_text += "1"
        try:
            re_v = parse_number(re_text) if re_text else 0
            im_v = parse_number(im_text)
        except ValueError:
            raise ValueError("%r isn't a number" % raw)
        if isinstance(re_v, TIComplex) or isinstance(im_v, TIComplex) or im_v is None:
            raise ValueError("%r isn't a number" % raw)
        return TIComplex(re_v, im_v)
    m = _FRAC_RE.match(s)
    if m:
        if int(m.group(2)) == 0:
            raise ValueError("%r divides by 0" % raw)
        return Fraction(int(m.group(1)), int(m.group(2)))
    if not _REAL_RE.match(s):
        raise ValueError("%r isn't a number" % raw)
    if "." not in s and "E" not in s:
        return int(s)
    try:
        return Decimal(s)
    except InvalidOperation:
        raise ValueError("%r isn't a number" % raw)


def number_text(v, float_mark=False):
    """A value -> text with every digit the calculator keeps: 0.33333333333333, 1.5E-99,
    3+2i, 1/3. float_mark: an approximate whole number gets a point ("2.", as the 89 shows a
    float), so it reads back as a float"""
    if isinstance(v, TIComplex):
        re_t, im_t = number_text(v.re, float_mark), number_text(v.im, float_mark)
        if im_t in ("0", "0."):
            return re_t
        if im_t in ("1", "-1"):
            im_t = im_t[:-1]
        if re_t == "0":
            return im_t + "i"
        return re_t + ("" if im_t.startswith("-") else "+") + im_t + "i"
    if isinstance(v, Fraction):
        return str(v.numerator) if v.denominator == 1 else "%d/%d" % (v.numerator, v.denominator)
    if isinstance(v, int):
        return str(v)
    if isinstance(v, str):
        return v
    d = Decimal(v)
    if d == 0:
        return "0." if float_mark else "0"
    t = _C14.plus(d)
    adj = t.adjusted()
    if -5 <= adj < 15:
        s = format(t, "f")
        if "." in s:
            s = s.rstrip("0").rstrip(".")
        if float_mark and "." not in s:
            s += "."
        return s
    neg, digits, exp = _sci(t)
    digits = digits.rstrip("0") or "0"
    mant = digits[0] + ("." + digits[1:] if len(digits) > 1 else "")
    return "%s%sE%d" % ("-" if neg else "", mant, exp)


# ---- TI-Basic (TI-84 Plus family) as text ----

_ONE = {
    0x01: "►DMS", 0x02: "►Dec", 0x03: "►Frac", 0x04: "→", 0x05: "Boxplot",
    0x06: "[", 0x07: "]", 0x08: "{", 0x09: "}", 0x0A: "ʳ", 0x0B: "°", 0x0C: "⁻¹",
    0x0D: "²", 0x0E: "ᵀ", 0x0F: "³", 0x10: "(", 0x11: ")", 0x12: "round(",
    0x13: "pxl-Test(", 0x14: "augment(", 0x15: "rowSwap(", 0x16: "row+(", 0x17: "*row(",
    0x18: "*row+(", 0x19: "max(", 0x1A: "min(", 0x1B: "R►Pr(", 0x1C: "R►Pθ(",
    0x1D: "P►Rx(", 0x1E: "P►Ry(", 0x1F: "median(", 0x20: "randM(", 0x21: "mean(",
    0x22: "solve(", 0x23: "seq(", 0x24: "fnInt(", 0x25: "nDeriv(", 0x27: "fMin(", 0x28: "fMax(",
    0x29: " ", 0x2A: '"', 0x2B: ",", 0x2C: "\U0001d456", 0x2D: "!", 0x2E: "CubicReg ",
    0x2F: "QuartReg ", 0x3A: ".", 0x3B: "ᴇ", 0x3C: " or ", 0x3D: " xor ", 0x3E: ":",
    0x3F: "\n", 0x40: " and ", 0x5B: "θ", 0x5F: "prgm", 0x64: "Radian", 0x65: "Degree",
    0x66: "Normal", 0x67: "Sci", 0x68: "Eng", 0x69: "Float", 0x6A: "=", 0x6B: "<", 0x6C: ">",
    0x6D: "≤", 0x6E: "≥", 0x6F: "≠", 0x70: "+", 0x71: "-", 0x72: "Ans",
    0x73: "Fix ", 0x74: "Horiz", 0x75: "Full", 0x76: "Func", 0x77: "Param", 0x78: "Polar",
    0x79: "Seq", 0x7A: "IndpntAuto", 0x7B: "IndpntAsk", 0x7C: "DependAuto", 0x7D: "DependAsk",
    0x7F: "□", 0x80: "﹢", 0x81: "·", 0x82: "*", 0x83: "/", 0x84: "Trace",
    0x85: "ClrDraw", 0x86: "ZStandard", 0x87: "ZTrig", 0x88: "ZBox", 0x89: "Zoom In",
    0x8A: "Zoom Out", 0x8B: "ZSquare", 0x8C: "ZInteger", 0x8D: "ZPrevious", 0x8E: "ZDecimal",
    0x8F: "ZoomStat", 0x90: "ZoomRcl", 0x91: "PrintScreen", 0x92: "ZoomSto", 0x93: "Text(",
    0x94: " nPr ", 0x95: " nCr ", 0x96: "FnOn ", 0x97: "FnOff ", 0x98: "StorePic ",
    0x99: "RecallPic ", 0x9A: "StoreGDB ", 0x9B: "RecallGDB ", 0x9C: "Line(", 0x9D: "Vertical ",
    0x9E: "Pt-On(", 0x9F: "Pt-Off(", 0xA0: "Pt-Change(", 0xA1: "Pxl-On(", 0xA2: "Pxl-Off(",
    0xA3: "Pxl-Change(", 0xA4: "Shade(", 0xA5: "Circle(", 0xA6: "Horizontal ", 0xA7: "Tangent(",
    0xA8: "DrawInv ", 0xA9: "DrawF ", 0xAB: "rand", 0xAC: "π", 0xAD: "getKey", 0xAE: "'",
    0xAF: "?", 0xB0: "⁻", 0xB1: "int(", 0xB2: "abs(", 0xB3: "det(", 0xB4: "identity(",
    0xB5: "dim(", 0xB6: "sum(", 0xB7: "prod(", 0xB8: "not(", 0xB9: "iPart(", 0xBA: "fPart(",
    0xBC: "√(", 0xBD: "³√(", 0xBE: "ln(", 0xBF: "e^(", 0xC0: "log(",
    0xC1: "⏨^(", 0xC2: "sin(", 0xC3: "sin⁻¹(", 0xC4: "cos(",
    0xC5: "cos⁻¹(", 0xC6: "tan(", 0xC7: "tan⁻¹(", 0xC8: "sinh(",
    0xC9: "sinh⁻¹(", 0xCA: "cosh(", 0xCB: "cosh⁻¹(", 0xCC: "tanh(",
    0xCD: "tanh⁻¹(", 0xCE: "If ", 0xCF: "Then", 0xD0: "Else", 0xD1: "While ",
    0xD2: "Repeat ", 0xD3: "For(", 0xD4: "End", 0xD5: "Return", 0xD6: "Lbl ", 0xD7: "Goto ",
    0xD8: "Pause ", 0xD9: "Stop", 0xDA: "IS>(", 0xDB: "DS<(", 0xDC: "Input ", 0xDD: "Prompt ",
    0xDE: "Disp ", 0xDF: "DispGraph", 0xE0: "Output(", 0xE1: "ClrHome", 0xE2: "Fill(",
    0xE3: "SortA(", 0xE4: "SortD(", 0xE5: "DispTable", 0xE6: "Menu(", 0xE7: "Send(",
    0xE8: "Get(", 0xE9: "PlotsOn ", 0xEA: "PlotsOff ", 0xEB: "ʟ", 0xEC: "Plot1(",
    0xED: "Plot2(", 0xEE: "Plot3(", 0xF0: "^", 0xF1: "ˣ√", 0xF2: "1-Var Stats ",
    0xF3: "2-Var Stats ", 0xF4: "LinReg(a+bx) ", 0xF5: "ExpReg ", 0xF6: "LnReg ",
    0xF7: "PwrReg ", 0xF8: "Med-Med ", 0xF9: "QuadReg ", 0xFA: "ClrList ", 0xFB: "ClrTable",
    0xFC: "Histogram", 0xFD: "xyLine", 0xFE: "Scatter", 0xFF: "LinReg(ax+b) ",
}
for _i in range(10):
    _ONE[0x30 + _i] = str(_i)
for _i in range(26):
    _ONE[0x41 + _i] = chr(65 + _i)

_STAT = ["", "RegEQ", "n", "x̄", "Σx", "Σx²", "Sx", "σx", "minX", "maxX",
         "minY", "maxY", "ȳ", "Σy", "Σy²", "Sy", "σy", "Σxy", "r",
         "Med", "Q₁", "Q₃", "a", "b", "c", "d", "e"]
_WINDOW = {0x0A: "Xmin", 0x0B: "Xmax", 0x0C: "Ymin", 0x0D: "Ymax", 0x0E: "Tmin", 0x0F: "Tmax",
           0x10: "θmin", 0x11: "θmax", 0x1A: "TblStart", 0x21: "ΔTbl",
           0x22: "Tstep", 0x23: "θstep", 0x02: "Xscl", 0x03: "Yscl"}
_FORMAT = ["Sequential", "Simul", "PolarGC", "RectGC", "CoordOn", "CoordOff", "Thick", "Dot-Thick",
           "AxesOn ", "AxesOff", "GridDot ", "GridOff", "LabelOn", "LabelOff", "Web", "Time",
           "uvAxes", "vwAxes", "uwAxes"]
_BB = ["npv(", "irr(", "bal(", "ΣPrn(", "ΣInt(", "►Nom(", "►Eff(", "dbd(",
       "lcm(", "gcd(", "randInt(", "randBin(", "sub(", "stdDev(", "variance(", "inString(",
       "normalcdf(", "invNorm(", "tcdf(", "χ²cdf(", "Fcdf(", "binompdf(", "binomcdf(",
       "poissonpdf(", "poissoncdf(", "geometpdf(", "geometcdf(", "normalpdf(", "tpdf(",
       "χ²pdf(", "Fpdf(", "randNorm(", "tvm_Pmt", "tvm_I%", "tvm_PV", "tvm_N", "tvm_FV",
       "conj(", "real(", "imag(", "angle(", "cumSum(", "expr(", "length(", "ΔList(", "ref(",
       "rref(", "►Rect", "►Polar", "e", "SinReg ", "Logistic ", "LinRegTTest ",
       "ShadeNorm(", "Shade_t(", "Shadeχ²(", "ShadeF(", "Matr►list(",
       "List►matr(", "Z-Test(", "T-Test ", "2-SampZTest(", "1-PropZTest(", "2-PropZTest(",
       "χ²-Test(", "ZInterval ", "2-SampZInt(", "1-PropZInt(", "2-PropZInt(",
       "GraphStyle(", "2-SampTTest ", "2-SampFTest ", "TInterval ", "2-SampTInt ",
       "SetUpEditor ", "Pmt_End", "Pmt_Bgn", "Real", "re^θ\U0001d456", "a+b\U0001d456",
       "ExprOn", "ExprOff", "ClrAllLists", "GetCalc(", "DelVar ", "Equ►String(",
       "String►Equ(", "Clear Entries", "Select(", "ANOVA(", "ModBoxplot", "NormProbPlot"]
_BB_MORE = {0x64: "G-T", 0x65: "ZoomFit", 0x66: "DiagnosticOn", 0x67: "DiagnosticOff",
            0x68: "Archive ", 0x69: "UnArchive ", 0x6A: "Asm(", 0x6B: "AsmComp(", 0x6C: "AsmPrgm"}
for _i in range(11):
    _BB_MORE[0xB0 + _i] = chr(97 + _i)          # a-k
for _i in range(15):
    _BB_MORE[0xBC + _i] = chr(108 + _i)         # l-z
_EF = {0x00: "setDate(", 0x01: "setTime(", 0x02: "checkTmr(", 0x03: "setDtFmt(",
       0x04: "setTmFmt(", 0x05: "timeCnv(", 0x06: "dayOfWk(", 0x07: "getDtStr(",
       0x08: "getTmStr(", 0x09: "getDate", 0x0A: "getTime", 0x0B: "startTmr", 0x0C: "getDtFmt",
       0x0D: "getTmFmt", 0x0E: "isClockOn", 0x0F: "ClockOff", 0x10: "ClockOn", 0x11: "OpenLib(",
       0x12: "ExecLib", 0x13: "invT(", 0x14: "χ²GOF-Test(", 0x15: "LinRegTInt ",
       0x16: "Manual-Fit ", 0x17: "ZQuadrant1", 0x18: "ZFrac1/2", 0x19: "ZFrac1/3",
       0x1A: "ZFrac1/4", 0x1B: "ZFrac1/5", 0x1C: "ZFrac1/8", 0x1D: "ZFrac1/10",
       0x32: "remainder(", 0x33: "Σ(", 0x34: "logBASE(", 0x35: "randIntNoRep(",
       0x37: "MATHPRINT", 0x38: "CLASSIC", 0x39: "n/d", 0x3A: "Un/d", 0x3B: "AUTO", 0x3C: "DEC",
       0x3D: "FRAC-APPROX",
       0x41: "BLUE", 0x42: "RED", 0x43: "BLACK", 0x44: "MAGENTA", 0x45: "GREEN", 0x46: "ORANGE",
       0x47: "BROWN", 0x48: "NAVY", 0x49: "LTBLUE", 0x4A: "YELLOW", 0x4B: "WHITE",
       0x4C: "LTGRAY", 0x4D: "MEDGRAY", 0x4E: "GRAY", 0x4F: "DARKGRAY", 0x96: "Wait ",
       0x97: "toString(", 0x98: "eval("}


def _two(a, b):
    if a == 0x5C:
        return "[%s]" % chr(65 + b) if b <= 9 else None
    if a == 0x5D:
        return "L" + SUB[b + 1] if b <= 5 else None
    if a == 0x5E:
        if 0x10 <= b <= 0x19:
            return "Y" + SUB[(b - 0x10 + 1) % 10]
        if 0x20 <= b <= 0x2B:
            return "XY"[(b - 0x20) & 1] + SUB[(b - 0x20) // 2 + 1] + "ᴛ"
        if 0x40 <= b <= 0x45:
            return "r" + SUB[b - 0x40 + 1]
        if 0x80 <= b <= 0x82:
            return "uvw"[b - 0x80]
        return None
    for tok, word in ((0x60, "Pic"), (0x61, "GDB"), (0xAA, "Str")):
        if a == tok:
            return "%s%d" % (word, (b + 1) % 10) if b <= 9 else None
    if a == 0x62:
        return _STAT[b] if 0 < b < len(_STAT) else None
    if a == 0x63:
        return _WINDOW.get(b)
    if a == 0x7E:
        return _FORMAT[b] if b < len(_FORMAT) else None
    if a == 0xBB:
        return _BB[b] if b < len(_BB) else _BB_MORE.get(b)
    if a == 0xEF:
        return _EF.get(b)
    return None


TWO_BYTE = (0x5C, 0x5D, 0x5E, 0x60, 0x61, 0x62, 0x63, 0x7E, 0xAA, 0xBB, 0xEF)


# ---- Where the token names come from: tivars (TI-Toolkit's sheet) or the table above ----

_SOURCE = ["tivars"]  # "tivars" (when it can be loaded) or "builtin"
_TIVARS = [None]      # The tivars token map, False when it can't be loaded


def set_token_source(source):
    """"tivars" (the default: TI-Toolkit's complete token sheet, when tools/third_party_py has
    it) or "builtin" (this file's own table). For tests."""
    global _TOK84, _DETOK84
    if source not in ("tivars", "builtin"):
        raise ValueError(source)
    _SOURCE[0] = source
    _TOK84 = _DETOK84 = None


def token_source():
    """What tokenize_84 / detokenize_84 use now: "tivars 1.1.1" or "builtin"."""
    if _SOURCE[0] == "tivars" and _tivars_tokens() is not None:
        import tivars
        return "tivars " + getattr(tivars, "__version__", "1.1.1")
    return "builtin"


def _tivars_tokens():
    """{token bytes: (display, accessible, variants)} for the TI-84 Plus CE's latest OS, from
    tivars; None when tivars can't be loaded (then the table above does the job)"""
    if _TIVARS[0] is None:
        try:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                from tivars.models import TI_84PCE
                _TIVARS[0] = {b: (t.display, t.accessible, list(t.translation.variants))
                              for b, t in TI_84PCE.tokens.bytes.items()}
        except Exception:  # Missing, or a Python too old for it: the builtin table
            _TIVARS[0] = False
    return _TIVARS[0] or None


def _names_84():
    """[(token bytes, [names, the one to show first])] from the chosen source"""
    tv = _tivars_tokens() if _SOURCE[0] == "tivars" else None
    if tv:
        return [(b, [d, a] + v) for b, (d, a, v) in tv.items()]
    out = [(bytes((b,)), [n]) for b, n in _ONE.items()]
    for a in TWO_BYTE:
        for b in range(256):
            n = _two(a, b)
            if n:
                out.append((bytes((a, b)), [n]))
    return out


_DETOK84 = None
_ALTS84 = None  # {token bytes: every name it has}, for the detokenizer's second choices
# Tokens the text form handles itself: the line break, ':', a space, the quote
_FIXED_TEXT = {b"\x3f": "\n", b"\x3e": ":", b"\x29": " ", b"\x2a": '"'}


def _detokens_84():
    """{token bytes: text}: each token's name as the calculator shows it, unless that name
    reads back as another token (the statistics' n, a, b... and the lower case letters share
    names): then a name that reads back as this one (TI-Toolkit's typing names: [n], [|a])"""
    global _DETOK84, _ALTS84
    if _DETOK84 is not None:
        return _DETOK84
    table = _tokens_84()
    d, alts, rev = dict(_FIXED_TEXT), {}, {}
    for name, tb in table.items():  # Our own spellings too ("−" for a minus)
        rev.setdefault(tb, []).append(name)
    for b, names in _names_84():
        if b in d:
            continue
        good = [n for n in names if n and "\\" not in n and table.get(n) == b and
                ASCII_84.get(n, b) == b]  # Not a PC spelling of another ("~" is the (-) key)
        d[b] = good[0] if good else names[0]
        alts[b] = [n for n in dict.fromkeys(good + names + rev.get(b, [])) if n and "\n" not in n]
    _DETOK84, _ALTS84 = d, alts
    return d


def _split_tokens_84(data):
    """Token bytes -> [token bytes], each one or two bytes"""
    out, i = [], 0
    while i < len(data):
        k = 2 if data[i] in TWO_BYTE and i + 1 < len(data) else 1
        out.append(data[i:i + k])
        i += k
    return out


def is_compiled_84(data):
    """A program's variable data (2-byte length, then the bytes) holds machine code, not
    TI-Basic: it starts with the AsmPrgm tokens (EF 7B on the CE, BB 6C / BB 6D before)"""
    body = data[2:] if len(data) >= 2 and struct.unpack_from("<H", data)[0] <= len(data) - 2 else data
    return body[:2] in (b"\xef\x7b", b"\xbb\x6c", b"\xbb\x6d")


def detokenize_84(data):
    """A TI-84 Plus program, string or equation (its variable data: a 2-byte length, then the
    tokens) as text. A token the table doesn't know shows as [hex]. Each line is read back
    through tokenize_84: where the plain names would come back as other tokens (X^2 typed as
    ^ and 2 would read as X²; a minus after "(" as a negative), a space between them or the
    token's other name makes the text say exactly what the calculator has."""
    if len(data) >= 2:
        n = struct.unpack_from("<H", data)[0]
        if n <= len(data) - 2:
            data = data[2:2 + n]
    names = _detokens_84()
    lines, cur = [], []
    for t in _split_tokens_84(data):
        if t == b"\x3f":
            lines.append(cur)
            cur = []
        else:
            cur.append(t)
    lines.append(cur)
    return "\n".join(_fit_line_84(toks, names) for toks in lines)


def _fit_line_84(toks, names):
    texts = [names.get(t) for t in toks]
    if any(x is None for x in texts):  # Unknown tokens: shown as hex, can't be read back anyway
        return "".join(x if x is not None else "[%s]" % t.hex().upper() for x, t in zip(texts, toks))
    want = b"".join(toks)
    if texts and texts[0] == ":":
        texts[0] = " :"  # A ':' starting a line is dropped when read; one after a space isn't

    def first_diff(txts):
        try:
            got = _line_84("".join(txts), 1)
        except ValueError:
            return 0
        if got == want:
            return None
        return next((k for k in range(min(len(got), len(want))) if got[k] != want[k]),
                    min(len(got), len(want)))

    pos = first_diff(texts)
    for _ in range(4 * len(toks) + 4):
        if pos is None:
            break
        # The token at the first wrong byte, and the one before it: try a space before it, or
        # its other names, until the first wrong byte moves on
        at, k = 0, 0
        while k < len(toks) and at + len(toks[k]) <= pos:
            at += len(toks[k])
            k += 1
        ends = [sum(len(t) for t in toks[:j + 1]) for j in range(len(toks))]
        tries = []
        for j in (k, k - 1, k + 1):
            if 0 <= j < len(toks):
                if not texts[j].startswith(" "):
                    tries.append((j, " " + texts[j]))
                for alt in _ALTS84.get(toks[j], []):
                    if alt != texts[j]:
                        tries.append((j, alt))
                        tries.append((j, " " + alt))
        best = None
        for j, alt in tries:
            cand = texts[:j] + [alt] + texts[j + 1:]
            p = first_diff(cand)
            # Right at least through the token changed and the one that was wrong
            if p is None or p >= ends[min(max(j, k), len(toks) - 1)]:
                best = (cand, p)
                break
        if best is None:
            break
        texts, pos = best
    return "".join(texts)


# ---- TI-Basic text -> a TI-84 Plus program (.8xp) ----

# Spellings a PC keyboard has, for the tokens it hasn't (outside strings only)
ASCII_84 = {
    "->": b"\x04", "<=": b"\x6D", ">=": b"\x6E", "!=": b"\x6F", "sqrt(": b"\xBC",
    "cbrt(": b"\xBD", "pi": b"\xAC", "theta": b"\x5B", "^2": b"\x0D", "^3": b"\x0F",
    "^-1": b"\x0C", "~": b"\xB0", "10^(": b"\xC1", "sin^-1(": b"\xC3", "cos^-1(": b"\xC5",
    "tan^-1(": b"\xC7", "sinh^-1(": b"\xC9", "cosh^-1(": b"\xCB", "tanh^-1(": b"\xCD",
    "|L": b"\xEB", "@": b"\x2C", "e^(": b"\xBF",
}
for _d in range(1, 7):
    ASCII_84["L%d" % _d] = bytes((0x5D, _d - 1))           # L1 = L₁
for _d in range(10):
    ASCII_84["Y%d" % _d] = bytes((0x5E, 0x10 + _shift(_d)))  # Y1 = Y₁
# After these a "-" is a negative sign (the 84's (-) key), not a minus
_UNARY_AFTER = set("(,{[→=<>≤≥≠+-*/^:\n⁻ᴇ") | {"·", "﹢"}
_TOK84 = None
_TOK84_INFO = None  # (longest name, names that start with a space)


def _tokens_84():
    """{text: token bytes}: every name of every token (the shown name first; with tivars also
    TI-Toolkit's typing names and variants), lower case letters as letters, the constant e as
    e, and "Disp" without its space (at a line's end)"""
    global _TOK84, _TOK84_INFO
    if _TOK84 is not None:
        return _TOK84
    t = {}
    ordered = sorted(_names_84(), key=lambda bn: (len(bn[0]), bn[0]))  # 1-byte tokens win
    for b, names in ordered:  # Shown names first: they win over another token's typing name
        if names[0]:
            t.setdefault(names[0], b)
    for b, names in ordered:
        for n in names[1:]:
            if n:
                t.setdefault(n, b)
    for i in range(26):  # Lower case letters are their own tokens (not the statistics' a, b, n)
        if chr(97 + i) != "e":  # e is the constant e (its letter: in strings)
            t[chr(97 + i)] = _lower_84(chr(97 + i))
    t["e"] = b"\xBB\x31"
    t.setdefault("−", b"\x71")  # U+2212: a minus where "-" would read as the (-) key ("(−X")
    for s, tok in list(t.items()):  # "Disp" without its space (at a line's end)
        if s.endswith(" ") and s.strip() and s.rstrip() not in t:
            t[s.rstrip()] = tok
    for k in [k for k in t if "\n" in k or "\r" in k]:
        del t[k]  # Lines are split before tokens are looked up
    t.pop(" ", None)  # Spaces outside strings are dropped
    _TOK84 = t
    _TOK84_INFO = (max(len(k) for k in list(t) + list(ASCII_84)),
                   tuple(k for k in t if k.startswith(" ")))  # " or ", " and ", " nPr ", ...
    return t


def _lower_84(c):
    i = ord(c) - 97
    return bytes((0xBB, 0xB0 + i if i < 11 else 0xBC + i - 11))


def tokenize_84(text, warnings=None):
    """TI-Basic as text (the calculator's own names: Disp, →, ≤, √(, π, ...; or the PC
    spellings ->, <=, >=, !=, sqrt(, pi, theta, ^2, ^-1, L1, Y1; E in a number for the EE;
    a leading ':' on a line is dropped) -> the program's tokens. Raises ValueError naming
    the line of anything it can't turn into a token. A list as `warnings` gets a line for each
    word outside a string that isn't a command but has lower case letters in it ("textcolor(",
    "GridOn"): those become lower case letters, which the calculator stops at (ERR:SYNTAX)."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    while lines and not lines[-1].strip():
        lines.pop()
    out = []
    for n, l in enumerate(lines, 1):
        line = l[1:] if l.startswith(":") else l
        found = [] if warnings is not None else None
        out.append(_line_84(line, n, found))
        if found:
            warnings.extend(_misspelt_84(line, n, found))
    return b"\x3f".join(out)


def _misspelt_84(line, n, positions):
    """Messages for the words around `positions` (lower case letters left as letters, outside
    strings), with the command meant when one is spelt the same but for the case"""
    table = _tokens_84()
    by_lower = {}
    for name in table:
        key = name.strip().lower()
        if len(key) > 1 and key[:-1].replace(" ", "").isalnum() or key.endswith("("):
            by_lower.setdefault(key, name.strip())
    out, done = [], set()
    for p in positions:
        a = b = p
        while a > 0 and line[a - 1].isalpha():
            a -= 1
        while b < len(line) and line[b].isalpha():
            b += 1
        if a in done:
            continue
        done.add(a)
        word = line[a:b] + ("(" if line[b:b + 1] == "(" else "")
        hint = by_lower.get(word.lower())
        if not hint:
            stem = word.rstrip("(").lower()[:4]
            close = sorted({v for k, v in by_lower.items() if len(stem) >= 3 and k.startswith(stem)})
            hint = " or ".join(close[:4]) if close else None
        out.append("line %d: %r isn't a TI-84 command; outside a string its lower case letters stay "
                   "letters and the calculator will stop there (ERR:SYNTAX)%s" % (
                       n, word, ". Did you mean %s?" % hint if hint else ""))
    return out


def _line_84(line, n, lower=None):
    """One line of TI-Basic -> its tokens. Outside strings spaces are dropped (but for the
    tokens that start with one: " or ", " and "...); inside them they count, trailing ones too.
    After a → that ends a string without its closing quote, spaces count too (some programs
    keep → inside a string they show), unless only spaces are left."""
    table = _tokens_84()
    longest, spaced = _TOK84_INFO
    out = bytearray()
    mode, prev, i = 0, None, 0  # mode 0: code, 1: in a string, 2: after a → that ended one
    while i < len(line):
        c = line[i]
        in_str = mode == 1
        if c == '"' and mode == 1:  # After a → that ended a string, a quote starts one
            out.append(0x2A)
            mode, prev, i = 0, '"', i + 1
            continue
        if in_str and ("a" <= c <= "z" or c == " "):  # A string keeps its letters and spaces,
            # but a function at a word's start stays its token: "sin(X)" for expr( or Y=
            fn = c != " " and not (i and line[i - 1].isalnum()) and any(
                line[i + k - 1] == "(" and line[i:i + k] in table
                for k in range(2, min(longest, len(line) - i) + 1))
            if not fn:
                out += _lower_84(c) if c != " " else b"\x29"
                i += 1
                continue
        if not in_str:
            if c == " " and not any(line.startswith(k, i) for k in spaced):
                if mode == 2 and line[i:].strip():
                    out.append(0x29)
                i += 1
                continue
            # 1E5, 2.5E-3: the EE key
            if c == "E" and prev and (prev[-1].isdigit() or prev[-1] == ".") and i + 1 < len(line) \
                    and (line[i + 1].isdigit() or line[i + 1] in "-⁻"):
                out.append(0x3B)
                prev, i = "ᴇ", i + 1
                continue
            if c == "-" and (prev is None or prev[-1] in _UNARY_AFTER or prev.endswith(" ")):
                out.append(0xB0)  # A negative number, not a subtraction
                prev, i = "⁻", i + 1
                continue
        tok, size = None, 0
        for k in range(min(longest, len(line) - i), 0, -1):
            piece = line[i:i + k]
            if not in_str and piece in ASCII_84:
                if piece in ("pi", "theta") and (line[i + k:i + k + 1].isalpha() or
                                                 (i and line[i - 1].isalpha())):
                    continue  # Part of a longer word
                tok, size = ASCII_84[piece], k
                break
            if piece in table:
                # In a string, a word of several letters stays letters when it is part of a
                # longer word ("REDUCE" is letters, "RED WINS" the colour token), so text
                # reads as typed; a function at a word's start ("sin(") stays its token
                if in_str and k > 1 and ((piece[0].isalnum() and i and line[i - 1].isalnum()) or
                                         (piece[-1].isalnum() and line[i + k:i + k + 1].isalnum())):
                    continue
                tok, size = table[piece], k
                break
        if tok is None:
            raise ValueError("line %d: %r isn't a TI-84 Plus token or character" % (n, c))
        if lower is not None and not in_str and size == 1 and "a" <= c <= "z" and c != "e":
            lower.append(i)  # A lower case letter in code: a misspelt command, most likely
        out += tok
        piece = line[i:i + size]
        if tok == b"\x2A":
            mode = 1
        elif tok == b"\x04":
            mode = 2 if mode == 1 else 0  # → ends a string too
        prev, i = piece, i + size
    return bytes(out)


NAME_84 = re.compile(r"^[A-Zθ][A-Z0-9θ]{0,7}$")


def name_84_from(stem):
    """A file name -> a program name the 84 takes (A-Z, 0-9, θ; up to 8; a letter first), or
    None"""
    s = re.sub(r"[^A-Z0-9θ]", "", stem.upper().replace("THETA", "θ"))[:8]
    return s if NAME_84.match(s) else None


def program_8xp(text, name, comment="Made by CalcSuite", warnings=None):
    """TI-Basic text -> the bytes of a .8xp file (TI's header, the name, the checksum).
    `warnings`: see tokenize_84."""
    name = name.upper()
    if not NAME_84.match(name):
        raise ValueError("%r can't be a TI-84 program name: up to 8 capitals A-Z, digits or θ, "
                         "a letter first" % name)
    tokens = tokenize_84(text, warnings)
    if len(tokens) > 65000:
        raise ValueError("the program is too big (%d bytes)" % len(tokens))
    data = struct.pack("<H", len(tokens)) + tokens
    return ti8x_bytes([(0x05, tokenize_name_84(name, 0x05), 0, False, data)], comment)


# ---- TI-Basic text -> a TI-89 Titanium program (.89p) ----
#
# The 89 keeps a program as text until it first runs, then tokenizes it itself (as one made in
# its own Program Editor: read back from a TI-89 Titanium, OS 3.10, it holds
# "(args)\rPrgm\r...\rEndPrgm", 0, a 2-byte cursor offset, then 19 E4 E5 00 00 08 DC). So the
# PC sends the text in that form and the calculator does the tokenizing: nothing to get wrong
# in a table of the 89's tokens.

CHARS_89 = {  # Unicode -> the 89's character set (libticonv: ti9x_charset)
    "→": 0x16, "α": 0x80, "β": 0x81, "Γ": 0x82, "γ": 0x83, "Δ": 0x84, "δ": 0x85, "ε": 0x86,
    "ζ": 0x87, "θ": 0x88, "λ": 0x89, "ξ": 0x8A, "Π": 0x8B, "π": 0x8C, "ρ": 0x8D, "Σ": 0x8E,
    "σ": 0x8F, "τ": 0x90, "φ": 0x91, "ψ": 0x92, "Ω": 0x93, "ω": 0x94, "ᴇ": 0x95, "ℯ": 0x96,
    "𝑖": 0x97, "ʳ": 0x98, "≤": 0x9C, "≠": 0x9D, "≥": 0x9E, "∠": 0x9F, "…": 0xA0, "√": 0xA8,
    "−": 0xAD, "⁻": 0xAD, "²": 0xB2, "³": 0xB3, "⁻¹": 0xB4, "∂": 0xBC, "∫": 0xBD, "∞": 0xBE,
    "°": 0xB0, "▸": 0x12, "►": 0x12,  # The conversion operator (libticonv: 0x12, U+25B8)
}
# PC spellings. "@>" is the conversion operator (►: 10@>Bin, 3_m@>_ft): '@' only starts the
# 89's own constants (@1, @n1), never followed by '>'
ASCII_89 = {"->": 0x16, "<=": 0x9C, ">=": 0x9E, "!=": 0x9D, "/=": 0x9D, "@>": 0x12}
# Longest first: "@int(" before "@i"
_WORDS_89 = {"sqrt(": b"\xA8(", "pi": b"\x8C", "theta": b"\x88", "e^(": b"\x96^(",
             "@int(": b"\xBD(", "@sum(": b"\x8E(", "@angle": b"\x9F", "@d(": b"\xBC(",
             "@i": b"\x97"}
NAME_89 = re.compile(r"^[a-z][a-z0-9_]{0,7}$")
_HEAD_89 = re.compile(r"^\s*(?:define\s+)?([A-Za-z][A-Za-z0-9_]{0,7})\s*\(([^)]*)\)\s*(?:=\s*(prgm|func))?\s*$",
                      re.I)


def _line_89(line, n):
    """One line of 89 TI-Basic -> the 89's characters"""
    out, in_str, i = bytearray(), False, 0
    word = lambda j: 0 <= j < len(line) and (line[j].isalnum() or line[j] == "_")
    while i < len(line):
        c = line[i]
        if c == '"':
            in_str = not in_str
        if not in_str:
            hit = next((k for k in ASCII_89 if line.startswith(k, i)), None)
            if hit:
                out.append(ASCII_89[hit])
                i += len(hit)
                continue
            hit = next((k for k in _WORDS_89 if line.startswith(k, i) and
                        (k[0] == "@" or not word(i - 1)) and  # 5@angle30, 3@i
                        (k.endswith("(") or k == "@angle" or not word(i + len(k)))), None)
            if hit:
                out += _WORDS_89[hit]
                i += len(hit)
                continue
            # 1E5, 2.5E-3: the EE key; a minus after it and at an expression's start: negative
            if c in "Ee" and out and (chr(out[-1]).isdigit() or out[-1] == 0x2E) and \
                    i + 1 < len(line) and (line[i + 1].isdigit() or line[i + 1] in "-⁻−"):
                out.append(0x95)
                i += 1
                continue
            prev = next((b for b in reversed(out) if b != 0x20), None)
            if c == "-" and (prev is None or prev == 0x95 or chr(prev) in "(,{[=<>+-*/^:|" or
                             prev in (0x16, 0x9C, 0x9D, 0x9E, 0xAD) or
                             re.search(r"(?i)(^|[^a-z0-9_])(disp|return|output|if|elseif|while|"
                                       r"and|or|xor|not)\s*$", out.decode("latin-1"))):
                out.append(0xAD)
                i += 1
                continue
        if line.startswith("⁻¹", i):
            out.append(0xB4)
            i += 2
            continue
        if c in CHARS_89:
            out.append(CHARS_89[c])
        elif " " <= c <= "~":
            out.append(ord(c))
        elif "¡" <= c <= "ÿ" and ord(c) not in (0xA8, 0xAD, 0xB2, 0xB3, 0xB4, 0xB8,
                                                          0xBC, 0xBD, 0xBE):
            out.append(ord(c))
        else:
            raise ValueError("line %d: %r isn't a TI-89 character" % (n, c))
        i += 1
    return bytes(out)


def program_89_data(text, name=None, default=None):
    """TI-Basic text for the 89 -> (name, type 0x12 program or 0x13 function, the variable's
    data). The text may start with the program's own line, "zztest()" or "zztest(a,b)" (TI's
    Program Editor shows it), then Prgm ... EndPrgm (or Func ... EndFunc); without them it
    is the body of a program with no arguments. A leading ':' on a line is dropped. The name:
    `name`, else the text's own line, else `default`."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    lines = [l[1:] if l.startswith(":") else l for l in (x.rstrip() for x in lines)]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    args, kind = "", None
    m = _HEAD_89.match(lines[0]) if lines else None
    if m:
        name = name or m.group(1)
        args = m.group(2).replace(" ", "")
        lines.pop(0)
        if m.group(3):
            kind = m.group(3).lower()
            lines.insert(0, "Prgm" if kind == "prgm" else "Func")
    first = lines[0].strip().lower() if lines else ""
    last = lines[-1].strip().lower() if lines else ""
    if first in ("prgm", "func"):
        kind = first
        if last != "end" + first:
            raise ValueError("the %s has no End%s at its end" % ("program" if kind == "prgm" else
                                                                 "function", first.capitalize()))
    else:
        kind = "prgm"
        lines = ["Prgm"] + lines + ["EndPrgm"]
    name = name or default
    if not name:
        raise ValueError("no program name: give one, or start the text with name()")
    name = name.lower()
    if not NAME_89.match(name):
        raise ValueError("%r can't be a TI-89 name: up to 8 letters, digits or _, a letter first"
                         % name)
    body = ("(%s)" % args).encode("ascii") + b"\r" + b"\r".join(
        _line_89(l, n) for n, l in enumerate(lines, 2 if m else 1))
    tail = (b"\x19" if kind == "prgm" else b"\x17") + b"\xE4\xE5\x00\x00\x08\xDC"
    inner = body + b"\x00" + struct.pack(">H", 0) + tail
    if len(inner) > 65000:
        raise ValueError("the program is too big (%d bytes)" % len(inner))
    return name, (0x12 if kind == "prgm" else 0x13), struct.pack(">H", len(inner)) + inner


def name_89_from(stem):
    """A file name -> a name the 89 takes (lower case, up to 8), or None"""
    s = re.sub(r"[^a-z0-9_]", "", stem.lower())[:8]
    return s if NAME_89.match(s) else None


def program_89p(text, name=None, folder="main", comment="Made by CalcSuite", default=None):
    """TI-Basic text -> (name, type, the bytes of a .89p file: .89f for a function)"""
    name, vtype, data = program_89_data(text, name, default)
    return name, vtype, ti89_bytes(vtype, folder.encode("ascii"), name.encode("ascii"), False, data,
                                   comment)


def program_89_text(data):
    """A TI-89 program kept as text (not yet run) -> its text as the Program Editor shows it,
    or None when the calculator has tokenized it"""
    if len(data) < 12 or data[-1] != 0xDC or not data[-2] & 0x08:
        return None
    end = data.find(b"\x00", 2)
    if end < 0:
        return None
    back = {v: k for k, v in CHARS_89.items()}
    back[0xAD] = "-"
    back[0xB4] = "⁻¹"
    return "".join(back.get(b, chr(b)) for b in data[2:end]).replace("\r", "\n")


def read_ti89(blob):
    """A .89? file -> [(folder bytes, name bytes, type, archived, data)]. Raises ValueError."""
    if len(blob) < 0x3C or blob[:8] not in (b"**TI89**", b"**TI92P*"):
        if blob[:8] == b"**TI83F*":
            raise ValueError("a TI-84 Plus file, not a TI-89 one")
        raise ValueError("not a TI-89 file")
    folder = blob[0x0A:0x12].rstrip(b"\x00")
    n = struct.unpack_from("<H", blob, 0x3A)[0]
    out, t = [], 0x3C
    for _ in range(n):
        if t + 20 > len(blob):
            raise ValueError("the file is cut short")
        off, = struct.unpack_from("<I", blob, t)
        name = blob[t + 4:t + 12].rstrip(b"\x00")
        vtype, attr = blob[t + 12], blob[t + 13]
        nxt, = struct.unpack_from("<I", blob, t + 16)
        t += 16
        if vtype == 0x1F:
            folder = name
            continue
        if off + 6 > nxt or nxt > len(blob):
            raise ValueError("a variable in the file can't be read")
        data = blob[off + 4:nxt - 2]
        if struct.unpack_from("<H", blob, nxt - 2)[0] != sum(data) & 0xFFFF:
            raise ValueError("the file's checksum is wrong")
        out.append((folder or b"main", name, vtype, attr in (2, 3), data))
    if not out:
        raise ValueError("no variable in the file")
    return out


# ---- TI's newest OS versions (education.ti.com) ----

OS_PAGES = {
    "nspire_cx2_cas": "https://education.ti.com/en/software/details/en/"
                      "8CBC7A5F94D447B39E7C8C7F8178DB28/TI-NspireCXIICAS_OS",
    "nspire_cx2": "https://education.ti.com/en/software/details/en/"
                  "2726D6FC251C40648FDEE5AFABED3B95/TI-NspireCXII_OS",
    "ti84ce": "https://education.ti.com/en/software/details/en/"
              "158B7669E4C0493A84D33D9A22FDBD3C/ti-84plusceoperatingsystem",
    "ti89t": "https://education.ti.com/en/software/details/en/"
             "6633925F6176419197BF6CA051F5F7B4/89ti89tioperatingsystem",
}
CACHE_SECONDS = 24 * 3600
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"  # Generic: nothing about the user


def os_page_for(slug, info):
    """Which TI page lists the newest OS for this calculator, or None"""
    name = info.get("name", "").replace("_", " ")
    if slug == "nspire":  # USB id E022: the CX II family
        if "CX II-T" in name or "CX II-C" in name:
            return None  # The regional models have their own pages
        if "CX II" in name:
            return "nspire_cx2_cas" if "CAS" in name else "nspire_cx2"
        # A handheld renamed by its owner: its hardware type (0x1c seen on a CX II CAS)
        return "nspire_cx2_cas" if info.get("hw_type", "").startswith("0x1c") else None
    if slug == "ti84":
        return "ti84ce" if "CE" in name else None
    if slug == "ti89":
        return "ti89t"
    return None


def parse_os_page(html):
    """The newest OS version on one of TI's software pages, or None. Takes the version in the
    OS file's name (TI-NspireCXIICAS-6.4.0.74.tcc2) when it has one, else the row's Version
    column."""
    for row in re.findall(r"<tr>(.*?)</tr>", html, re.S):
        a = re.search(r'<a [^>]*href="([^"]*)"[^>]*class="download-file"[^>]*>(.*?)</a>', row, re.S)
        if not a or "operating system" not in a.group(2).lower():
            continue
        m = re.search(r"-(\d+(?:\.\d+){1,3})\.(?:tc\w*|tco\w*|8eu|8xu|8cu|89u)\b", a.group(1), re.I)
        if m:
            return m.group(1)
        v = re.search(r'class="column-version">\s*([0-9][0-9.]*)\s*<', row)
        if v:
            return v.group(1)
    return None


def version_tuple(slug, text):
    """A version as numbers that compare right: the Nspire calls 6.4.0.74 "6.40.74", the 84
    reports 5.4.0 (TI's pages add a build: 5.8.5.0074), the 89 3.10"""
    nums = [int(x) for x in re.findall(r"\d+", text or "")]
    if not nums:
        return None
    if slug == "nspire":
        if len(nums) == 3 and nums[1] >= 10:  # From the handheld: major.minor-and-patch.build
            nums = [nums[0], nums[1] // 10, nums[1] % 10, nums[2]]
        return tuple((nums + [0, 0, 0, 0])[:4])
    if slug == "ti84":
        return tuple((nums + [0, 0, 0])[:3])
    return tuple((nums + [0, 0])[:2])


def nice_version(slug, text):
    """The version the way TI writes it"""
    t = version_tuple(slug, text)
    if t is None:
        return text
    return ".".join(str(x) for x in t)


def _cache_path():
    import paths
    return os.path.join(paths.cache_dir(), "os_versions.json")


def newest_os(page_key, timeout=8):
    """(version or None, page URL). Asks TI's website at most once a day; never raises."""
    url = OS_PAGES[page_key]
    path = _cache_path()
    cache = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            cache = json.load(f)
        hit = cache.get(page_key)
        if hit and time.time() - hit["t"] < CACHE_SECONDS and hit.get("v"):
            return hit["v"], url
    except (OSError, ValueError, KeyError, TypeError):
        cache = {}
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            html = r.read(2000000).decode("utf-8", "replace")
        v = parse_os_page(html)
    except Exception:  # Offline, TI's site down or changed: "couldn't check"
        return None, url
    if v:
        try:
            cache[page_key] = {"v": v, "t": time.time()}
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(cache, f)
        except OSError:
            pass
    return v, url
