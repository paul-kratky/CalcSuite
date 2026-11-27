# SPDX-License-Identifier: GPL-3.0-or-later
"""Key codes for the TI-89 Titanium's remote key command (ti89-cli `key HEX`).

The 89's codes are its OS's (AMS) key codes as TILP's libticalcs lists them (keys89.h,
keys89.cc; GPL-2.0-or-later, https://github.com/debrouxl/tilibs): a typed character is its
own character code (a = 97, A = 65, 1 = 49), the special keys are 257 and up, and 2nd adds
4096, diamond 8192 (so Y= is diamond + F1 = 8460). ti89-cli sends them high byte first.
Tried on a TI-89 Titanium, OS 3.10: letters, digits, symbols, arrows, Enter, ESC, HOME,
APPS, CLEAR.

CHAR maps a typed character to its code, NAMED a key name (tools/mirror.py uses them).
"""

CHAR = {}
# Letters (the 89 types lower case directly), digits and the symbols on its keys or in its
# character set; each is its character code
for _c in ("abcdefghijklmnopqrstuvwxyz" "ABCDEFGHIJKLMNOPQRSTUVWXYZ" "0123456789"
           " +-*/^(),.=<>[]{}:;!?\"'_|&@#$%\\~"):
    CHAR[_c] = ord(_c)

NAMED = {
    "enter": 13, "esc": 264, "backspace": 257, "del": 8449, "ins": 4353, "clear": 263,
    # The 89's own arrow codes (the TI-92 Plus has 337 left, 338 up, 340 right, 344 down);
    # tried on a TI-89 Titanium, OS 3.10
    "up": 337, "left": 338, "down": 340, "right": 344,
    "f1": 268, "f2": 269, "f3": 270, "f4": 271, "f5": 272, "f6": 273, "f7": 274, "f8": 275,
    "home": 277, "mode": 266, "catalog": 278, "apps": 265, "on": 267,
    "quit": 4360, "switch": 4361, "custom": 4373, "entry": 4109, "ans": 4372,
    "approx": 8205, "sto": 258, "neg": 173, "ee": 149,
    "y=": 8460, "window": 8461, "graph": 8462, "tblset": 8463, "table": 8464,
    "math": 4149, "mem": 4150, "units": 4147, "char": 4139, "var-link": 4141,
    "sin": 259, "cos": 260, "tan": 261, "ln": 262, "sqrt": 4138,
    "pi": 140, "theta": 136, "infinity": 190, "with": 124,
    "x": 120, "y": 121, "z": 122, "t": 116,
    # From TILP's keys89.cc (2nd 7, 2nd 8, 2nd LN) and the 89's character codes (a character's
    # key code is its code): CalcSuite's Symbols panel
    "integral": 4151, "deriv": 4152, "imag": 151, "angle": 159, "degree": 176,
    "le": 156, "ge": 158, "ne": 157, "sigma": 142, "store": 22,
}


def code_for(key):
    """The code of a character or a key name, or None"""
    if key in CHAR:
        return CHAR[key]
    return NAMED.get(key.lower())
