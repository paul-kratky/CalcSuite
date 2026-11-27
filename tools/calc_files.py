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
