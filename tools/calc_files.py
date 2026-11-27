"""What the calculator manager needs that has no link or window in it: the TI file formats
(.8xp and friends for the TI-84 Plus family, .89x for the TI-89 Titanium), variable names,
TI-Basic as text, the parsing of the link tools' listings, and TI's newest OS versions.

The file layouts follow TILP's libtifiles (files8x.cc, files9x.cc) and the name rules its
libticonv (tokens.cc); this file is our own code for them. The TI-Basic token names are the
ones the calculator shows.
"""

import json
import os
import re
import struct
import time
import urllib.request

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


def ti8x_bytes(entries, comment="Saved by Calc Mirror"):
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


def ti89_bytes(vtype, folder, name, archived, data, comment="Saved by Calc Mirror"):
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
_FORMAT = ["Sequential", "Simul", "PolarGC", "RectGC", "CoordOn", "CoordOff", "Connected", "Dot",
           "AxesOn", "AxesOff", "GridOn", "GridOff", "LabelOn", "LabelOff", "Web", "Time",
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
       0x36: "MATHPRINT", 0x37: "CLASSIC", 0x3A: "AUTO", 0x3B: "DEC", 0x3C: "FRAC",
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


def detokenize_84(data):
    """A TI-84 Plus program, string or equation (its variable data: a 2-byte length, then the
    tokens) as text. A token this table doesn't know shows as [hex]."""
    if len(data) >= 2:
        n = struct.unpack_from("<H", data)[0]
        if n <= len(data) - 2:
            data = data[2:2 + n]
    out, i = [], 0
    while i < len(data):
        a = data[i]
        if a in TWO_BYTE and i + 1 < len(data):
            t = _two(a, data[i + 1])
            out.append(t if t is not None else "[%02X%02X]" % (a, data[i + 1]))
            i += 2
            continue
        t = _ONE.get(a)
        out.append(t if t is not None else "[%02X]" % a)
        i += 1
    return "".join(out)


# ---- TI-Basic text -> a TI-84 Plus program (.8xp) ----

# Spellings a PC keyboard has, for the tokens it hasn't (outside strings only)
ASCII_84 = {
    "->": b"\x04", "<=": b"\x6D", ">=": b"\x6E", "!=": b"\x6F", "sqrt(": b"\xBC",
    "cbrt(": b"\xBD", "pi": b"\xAC", "theta": b"\x5B", "^2": b"\x0D", "^3": b"\x0F",
    "^-1": b"\x0C", "~": b"\xB0", "10^(": b"\xC1", "sin^-1(": b"\xC3", "cos^-1(": b"\xC5",
    "tan^-1(": b"\xC7", "sinh^-1(": b"\xC9", "cosh^-1(": b"\xCB", "tanh^-1(": b"\xCD",
    "|L": b"\xEB", "@": b"\x2C",
}
for _d in range(1, 7):
    ASCII_84["L%d" % _d] = bytes((0x5D, _d - 1))           # L1 = L₁
for _d in range(10):
    ASCII_84["Y%d" % _d] = bytes((0x5E, 0x10 + _shift(_d)))  # Y1 = Y₁
# After these a "-" is a negative sign (the 84's (-) key), not a minus
_UNARY_AFTER = set("(,{[→=<>≤≥≠+-*/^:\n⁻ᴇ") | {"·", "﹢"}
_TOK84 = None


def _tokens_84():
    """{text: token bytes}, built from the detokenizer's tables (so the two agree)"""
    global _TOK84
    if _TOK84 is not None:
        return _TOK84
    t = {}
    for b, s in _ONE.items():
        t.setdefault(s, bytes((b,)))
    for a in TWO_BYTE:
        for b in range(256):
            s = _two(a, b)
            if s:
                t.setdefault(s, bytes((a, b)))
    for i in range(26):  # Lower case letters are their own tokens (not the statistics' a, b, n)
        if chr(97 + i) != "e":  # e is the constant e (its letter: in strings)
            t[chr(97 + i)] = _lower_84(chr(97 + i))
    for s, tok in list(t.items()):  # "Disp" without its space (at a line's end)
        if s.endswith(" ") and s.strip() and s.rstrip() not in t:
            t[s.rstrip()] = tok
    t.pop(" ", None)  # Spaces outside strings are dropped
    _TOK84 = t
    return t


def _lower_84(c):
    i = ord(c) - 97
    return bytes((0xBB, 0xB0 + i if i < 11 else 0xBC + i - 11))


def tokenize_84(text):
    """TI-Basic as text (the calculator's own names: Disp, →, ≤, √(, π, ...; or the PC
    spellings ->, <=, >=, !=, sqrt(, pi, theta, ^2, ^-1, L1, Y1; E in a number for the EE;
    a leading ':' on a line is dropped) -> the program's tokens. Raises ValueError naming
    the line of anything it can't turn into a token."""
    table = _tokens_84()
    longest = max(len(k) for k in list(table) + list(ASCII_84))
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    lines = [l[1:] if l.startswith(":") else l for l in (x.rstrip() for x in lines)]
    while lines and not lines[-1]:
        lines.pop()
    out = bytearray()
    for n, line in enumerate(lines, 1):
        if n > 1:
            out.append(0x3F)
        in_str, prev, i = False, None, 0
        while i < len(line):
            c = line[i]
            if in_str and c == '"':
                out.append(0x2A)
                in_str, prev, i = False, '"', i + 1
                continue
            if in_str and ("a" <= c <= "z" or c == " "):  # A string keeps its letters and spaces
                out += _lower_84(c) if c != " " else b"\x29"
                i += 1
                continue
            if not in_str:
                if c == " " and not any(line.startswith(k, i) for k in (" or ", " and ", " xor ",
                                                                       " nPr ", " nCr ")):
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
                    tok, size = table[piece], k
                    break
            if tok is None:
                raise ValueError("line %d: %r isn't a TI-84 Plus token or character" % (n, c))
            out += tok
            piece = line[i:i + size]
            if tok == b"\x2A":
                in_str = True
            elif tok == b"\x04":
                in_str = False  # → ends a string too
            prev, i = piece, i + size
    return bytes(out)


NAME_84 = re.compile(r"^[A-Zθ][A-Z0-9θ]{0,7}$")


def name_84_from(stem):
    """A file name -> a program name the 84 takes (A-Z, 0-9, θ; up to 8; a letter first), or
    None"""
    s = re.sub(r"[^A-Z0-9θ]", "", stem.upper().replace("THETA", "θ"))[:8]
    return s if NAME_84.match(s) else None


def program_8xp(text, name, comment="Made by CalcSuite"):
    """TI-Basic text -> the bytes of a .8xp file (TI's header, the name, the checksum)"""
    name = name.upper()
    if not NAME_84.match(name):
        raise ValueError("%r can't be a TI-84 program name: up to 8 capitals A-Z, digits or θ, "
                         "a letter first" % name)
    tokens = tokenize_84(text)
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
    "°": 0xB0,
}
ASCII_89 = {"->": 0x16, "<=": 0x9C, ">=": 0x9E, "!=": 0x9D, "/=": 0x9D}
_WORDS_89 = {"sqrt(": b"\xA8(", "pi": b"\x8C", "theta": b"\x88", "e^(": b"\x96^("}
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
            hit = next((k for k in _WORDS_89 if line.startswith(k, i) and not word(i - 1) and
                        (k.endswith("(") or not word(i + len(k)))), None)
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
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "CalcMirror", "os_versions.json")


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
