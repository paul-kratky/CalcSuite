# SPDX-License-Identifier: GPL-3.0-or-later
"""Key codes for the TI-84 Plus CE's remote key command (ti84-cli `key HEX`).

The codes are the TI-OS key codes TILP's libticalcs lists (keys83p.h, GPL-2.0-or-later;
https://github.com/debrouxl/tilibs). One-byte codes are plain keys; 0xFCxx / 0xFBxx / 0xFExx
are extended keys. Tried on a TI-84 Plus CE: digits, + and Enter work.

CHAR maps a typed character to its code, NAMED a key name (tools/mirror.py uses them).
"""

CHAR = {
    " ": 0x99, "+": 0x80, "-": 0x81, "*": 0x82, "/": 0x83, "^": 0x84, "(": 0x85, ")": 0x86,
    "[": 0x87, "]": 0x88, ",": 0x8B, ".": 0x8D, ":": 0xC6, '"': 0xCB, "?": 0xCA,
    "{": 0xEC, "}": 0xED, "'": 0xFE27, "%": 0xFB0C,
}
for _i in range(10):
    CHAR[str(_i)] = 0x8E + _i
for _i in range(26):
    CHAR[chr(ord("A") + _i)] = 0x9A + _i
    # Typed lower case is the calculator's capital too: TI-Basic and the home screen use
    # capitals, and the CE's real lower case (0xFCE2..) only matters inside strings
    CHAR[chr(ord("a") + _i)] = 0x9A + _i

NAMED = {
    "enter": 0x05, "right": 0x01, "left": 0x02, "up": 0x03, "down": 0x04,
    "clear": 0x09, "del": 0x0A, "ins": 0x0B, "quit": 0x40,
    "y=": 0x49, "window": 0x48, "zoom": 0x2E, "trace": 0x5A, "graph": 0x44,
    "mode": 0x45, "math": 0x32, "apps": 0x2C, "prgm": 0x2D, "vars": 0x35, "stat": 0x31,
    "table": 0x4A, "tblset": 0x4B, "format": 0x57, "catalog": 0x3E, "matrix": 0x37,
    "list": 0x3A, "test": 0x33, "angle": 0x39, "draw": 0x2F, "distr": 0x38, "calc": 0x3B,
    "mem": 0x36, "statplot": 0x30,
    "sto": 0x8A, "neg": 0x8C, "ee": 0x98, "x": 0xB4, "pi": 0xB5, "inverse": 0xB6,
    "sin": 0xB7, "cos": 0xB9, "tan": 0xBB, "square": 0xBD, "sqrt": 0xBE, "ln": 0xBF,
    "exp": 0xC0, "log": 0xC1, "tenpower": 0xC2, "ans": 0xC5, "theta": 0xCC,
    # From TILP's keys83p.h; each tried on a TI-84 Plus CE, OS 5.4.0 (CalcSuite's Symbols panel)
    "i": 0xEE, "imag": 0xFC83, "conste": 0xEF, "fnint": 0xC8, "nderiv": 0xC7,
    "test=": 0xFE0A, "test!=": 0xFE0B, "test>": 0xFE0C, "test>=": 0xFE0D, "test<": 0xFE0E,
    "test<=": 0xFE0F, "and": 0xFE10, "or": 0xFE11, "xor": 0xFE12, "not": 0xFE13,
    "abs": 0xFE09, "xroot": 0xFE15, "cube": 0xFE16, "cuberoot": 0xFE17, "factorial": 0xFE24,
    "radian": 0xFE25, "degree": 0xFE26, "colon": 0xC6,
}


def code_for(key):
    """The code of a character or a key name, or None"""
    if key in CHAR:
        return CHAR[key]
    return NAMED.get(key.lower())


def lower(ch):
    """The CE's real lower-case letter (for text inside strings)"""
    return 0xFCE2 + ord(ch) - ord("a") if "a" <= ch <= "z" else None
