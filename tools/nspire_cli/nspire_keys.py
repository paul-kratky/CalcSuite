# SPDX-License-Identifier: GPL-3.0-or-later
"""Key codes for the TI-Nspire's key-press service (nspire-cli `key HEX`).

The 3-byte codes are the ones TILP's libticalcs lists (keysnsp.h, GPL-2.0-or-later;
https://github.com/debrouxl/tilibs). They were captured on the first Nspire models: whether a
CX II on a current OS still takes them has to be tried on the handheld.

CHAR maps a typed character to its code; NAMED maps a key name (as tools/mirror.py and
tools/typekeys.py use them) to its code.
"""

CHAR = {
    "a": 0x616600, "b": 0x624600, "c": 0x632600, "d": 0x648500, "e": 0x656500, "f": 0x664500,
    "g": 0x672500, "h": 0x688400, "i": 0x696400, "j": 0x6A4400, "k": 0x6B2400, "l": 0x6C8300,
    "m": 0x6D6300, "n": 0x6E4300, "o": 0x6F2300, "p": 0x708200, "q": 0x716200, "r": 0x724200,
    "s": 0x732200, "t": 0x748100, "u": 0x756100, "v": 0x764100, "w": 0x772100, "x": 0x788000,
    "y": 0x796000, "z": 0x7A4000,
    "A": 0x416600, "B": 0x424600, "C": 0x432600, "D": 0x448500, "E": 0x456500, "F": 0x464500,
    "G": 0x472500, "H": 0x488400, "I": 0x496400, "J": 0x4A4400, "K": 0x4B2400, "L": 0x4C8300,
    "M": 0x4D6300, "N": 0x4E4300, "O": 0x4F2300, "P": 0x508200, "Q": 0x516200, "R": 0x524200,
    "S": 0x532200, "T": 0x548100, "U": 0x556100, "V": 0x564100, "W": 0x572100, "X": 0x588000,
    "Y": 0x596000, "Z": 0x5A4000,
    "0": 0x305000, "1": 0x317300, "2": 0x325300, "3": 0x333300, "4": 0x347200, "5": 0x355200,
    "6": 0x363200, "7": 0x377100, "8": 0x385100, "9": 0x393100,
    " ": 0x202000, ".": 0x2E7000, ",": 0x2CA000, "+": 0x2B1100, "-": 0x2D1200, "*": 0x2A1300,
    "/": 0x2F1400, "^": 0x5E9300, "(": 0x285500, ")": 0x293500, "=": 0x3D7500, "<": 0x3CA600,
    ">": 0x3E8600, ":": 0x3A0100, ";": 0x3B0200, "?": 0x3F0300, '"': 0x22A100, "'": 0x27F500,
    "$": 0x240500, "|": 0x7CED00,
}

NAMED = {
    "enter": 0x0D1000, "esc": 0x1B9600, "tab": 0x099500, "backspace": 0x081500,
    "left": 0x000700, "right": 0x002700, "up": 0x001700, "down": 0x003700,
    "home": 0x00FD00, "menu": 0x003600, "click": 0x00AD00, "ctrl+menu": 0x00CE00,
    "doc": 0x00A700, "var": 0x00AF00, "catalog": 0x009100, "newline": 0x000A00,
    "pi": 0x00A300, "neg": 0xB13000, "sin": 0x007400, "cos": 0x005400, "tan": 0x003400,
    "square": 0x009300, "exp": 0x00CA00, "tenpower": 0x00EC00, "ee": 0x00A400,
    "ctrl+left": 0x00DA00, "ctrl+right": 0x00DB00, "ctrl+up": 0x00DC00, "ctrl+down": 0x00DD00,
    "ctrl+enter": 0x00A600, "ctrl+esc": 0x00EF00, "ctrl+tab": 0x00ED00, "ctrl+home": 0x00FE00,
    "ctrl+a": 0x616600, "ctrl+b": 0x02B100, "ctrl+c": 0x03B200, "ctrl+d": 0x04B300,
    "ctrl+e": 0x05B400, "ctrl+f": 0x06B500, "ctrl+g": 0x07B600, "ctrl+i": 0x09B800,
    "ctrl+k": 0x0BBA00, "ctrl+m": 0x0DBC00, "ctrl+n": 0x0EBD00, "ctrl+o": 0x0FBE00,
    "ctrl+p": 0x10BF00, "ctrl+r": 0x12C100, "ctrl+s": 0x13C200, "ctrl+t": 0x14C300,
    "ctrl+v": 0x16C500, "ctrl+w": 0x17C600, "ctrl+x": 0x18C700, "ctrl+y": 0x19C800,
    "ctrl+z": 0x1AC900,
}


def code_for(key):
    """The code of a character or a key name, or None"""
    if key in CHAR:
        return CHAR[key]
    return NAMED.get(key.lower())
