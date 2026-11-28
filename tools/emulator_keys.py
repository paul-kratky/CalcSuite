# SPDX-License-Identifier: MIT
"""The PC keys of the emulators the PC copy runs: one table for the emulator tab's Keys panel
and for docs/EMULATORS.md (the self-test checks the guide's tables against these).

CEMU_KEYS is CEmu's own Keybindings page, copied as it is (calculator key, then the PC keys
in its columns "Computer 1/2/3"; "" where the page has nothing):
  https://github.com/CE-Programming/CEmu/wiki/Keybindings (read 2026-11-28)
It is CEmu's "CEmu" key preset, the default (Settings dock > General > Key bindings; the
setting Keypad/map defaults to "cemu" in gui/qt/mainwindow.cpp of CEmu v2.0). One difference
with CEmu 2.0's source (gui/qt/keypad/keymap.cpp, tag v2.0): there "]" is subtract and "["
is multiply, the other way round from the wiki page (CEMU_SOURCE_NOTES).

TIEMU_KEYS is TiEmu's TI-89 key map file, skins/ti89.map, as TiEmu installs it (its last
change, 2007-11-15, is older than TiEmu 3.03; source: the TiEmu repository mirror
https://github.com/debrouxl/tiemu, tiemu/trunk/skins/ti89.map). Its Windows virtual key names
(PCKEY_OEM_3 ...) are written as the key on a US keyboard.
"""

CEMU_WIKI = "https://github.com/CE-Programming/CEmu/wiki/Keybindings"
CEMU_COLUMNS = ("Calculator", "Computer 1", "Computer 2", "Computer 3")
CEMU_KEYS = [
    ("enter", "Enter", "", ""),
    ("2nd", ";", "Tab", ""),
    ("alpha", "'", "", ""),
    ("sto→", ">", "X", ""),
    ("clear", "Esc", "", ""),
    ("del", "Delete", "Insert", ""),
    ("math", "=", "A", ""),
    ("apps", "Page Up", "B", ""),
    ("prgm", "Page Down", "C", ""),
    ("vars", "<", "|", ""),
    ("stat", "End", "", ""),
    ("mode", "Home", "Backspace", ""),
    ("x,ᴛ,θ,n", "_", "", ""),
    ("(-)", "~", "?", ""),
    ("+", "+", '"', ""),
    ("–", "-", "W", "["),
    ("×", "*", "R", "]"),
    ("÷", "/", "M", ""),
    ("^", "^", "H", ""),
    ("x²", "@", "I", ""),
    ("x⁻¹", "\\", "D", ""),
    ("ln", "`", "S", ""),
    ("log", "!", "N", ""),
    ("sin", "$", "E", ""),
    ("cos", "%", "F", ""),
    ("tan", "&", "G", ""),
    ("down", "Down", "", ""),
    ("left", "Left", "", ""),
    ("right", "Right", "", ""),
    ("up", "Up", "", ""),
    ("0", "0", "Space", ""),
    ("1", "1", "Y", ""),
    ("2", "2", "Z", ""),
    ("3", "3", "#", ""),
    ("4", "4", "T", ""),
    ("5", "5", "U", ""),
    ("6", "6", "V", ""),
    ("7", "7", "O", ""),
    ("8", "8", "P", ""),
    ("9", "9", "Q", ""),
    (".", ".", ":", ""),
    (",", ",", "J", ""),
    ("(", "(", "K", "{"),
    (")", ")", "L", "}"),
    ("y=", "F1", "", ""),
    ("window", "F2", "", ""),
    ("zoom", "F3", "", ""),
    ("trace", "F4", "", ""),
    ("graph", "F5", "", ""),
    ("on", "F12", "", ""),
]
CEMU_SOURCE_NOTES = [
    "In CEmu 2.0's own source, [ is × (multiply) and ] is – (subtract): the wiki has them the other "
    "way round. Try both if one doesn't do what you expect.",
]

# CEmu's own shortcuts (CEmu 2.0: gui/qt/mainwindow.ui and mainwindow.cpp)
CEMU_SHORTCUTS = [
    ("Ctrl+Shift+O", "File > Open... (send files to the calculator)"),
    ("Ctrl+X", "Resend the files checked in the Variables dock"),
    ("Ctrl+Shift+X", "Start / stop recording an animated PNG"),
    ("Ctrl+Shift+C", "Copy the calculator's screen to the clipboard"),
    ("F11", "Full screen (application, then the screen only, then back)"),
    ("F10", "Debugger on / off"),
    ("Ctrl+Shift+Q", "Exit CEmu"),
]

TIEMU_SOURCE = "https://github.com/debrouxl/tiemu/blob/master/tiemu/trunk/skins/ti89.map"
TIEMU_COLUMNS = ("PC key", "TI-89 key")
# (PC key on a US keyboard, the TI-89 key(s) it presses), in the file's order and groups
TIEMU_KEYS = [
    ("A ... Z", "the letter (alpha + its key; T, X, Y, Z are their own keys)"),
    ("0 ... 9 (and the number pad)", "0 ... 9"),
    ("+ (number pad)", "+"),
    ("* (number pad)", "×"),
    ("/ (number pad)", "÷"),
    ("- (number pad)", "-"),
    ("Up, Down, Left, Right", "the arrows"),
    ("F1 ... F5", "F1 ... F5"),
    ("F6", "CATALOG"),
    ("Shift (left or right)", "↑ (shift)"),
    ("Ctrl (left or right)", "◆ (diamond)"),
    ("Alt", "2nd"),
    ("Caps Lock", "alpha"),
    ("Enter", "ENTER"),
    ("Esc", "ESC"),
    ("Backspace", "← (backspace)"),
    ("- (the minus key)", "(-) (negate)"),
    ("=", "="),
    ("[", "("),
    ("]", ")"),
    (",", ","),
    (". (and the number pad's .)", "."),
    ("/", "÷"),
    ("Space", "space (alpha + (-))"),
    ("Backtick, left of 1", "MODE"),
    ("\\", "| (with)"),
    ("F9", "APPS"),
    ("Tab", "STO▸"),
    ("Delete", "CLEAR"),
    ("Scroll Lock", "ON"),
    ("Insert", "EE"),
    ("Page Up", "^ (power)"),
    ("Home", "HOME"),
]
TIEMU_LETTERS = {  # The letters as the file maps them (alpha + this key)
    "A": "=", "B": "(", "C": ")", "D": ",", "E": "÷", "F": "|", "G": "7", "H": "8", "I": "9",
    "J": "×", "K": "EE", "L": "4", "M": "5", "N": "6", "O": "-", "P": "STO▸", "Q": "1", "R": "2",
    "S": "3", "U": "+", "V": "0", "W": ".",
}


def cemu_lookup():
    """{PC key: calculator key} from CEMU_KEYS (for the Keys panel's search)"""
    out = {}
    for row in CEMU_KEYS:
        for pc in row[1:]:
            if pc:
                out[pc] = row[0]
    return out


def code_cell(t):
    """A PC key as a Markdown code span in a table cell: `Enter`, `` ` ``, `\\|` (| escaped,
    as GitHub's tables need even inside code)"""
    if not t:
        return " "
    t = t.replace("|", "\\|")
    return "`` %s ``" % t if "`" in t else "`%s`" % t


def markdown_table(columns, rows, code_from=1):
    """A Markdown pipe table of rows, as docs/EMULATORS.md has it: the cells from column
    code_from on (the PC keys) as code spans"""
    def cell(k, t):
        if k >= code_from:
            return code_cell(t)
        return t.replace("|", "\\|") if t else " "
    lines = ["| " + " | ".join(columns) + " |", "|" + "|".join(" --- " for _ in columns) + "|"]
    for r in rows:
        lines.append("| " + " | ".join(cell(k, c) for k, c in enumerate(r)) + " |")
    return "\n".join(lines)


def table_rows(markdown, first_header):
    """The rows of the Markdown table whose first header cell is first_header, as plain text
    cells (code spans unwrapped, \\| unescaped): for the self-test's guide check"""
    import md_render
    for b in md_render.parse(markdown):
        if b[0] == "table" and b[1] and md_render.plain(b[1][0]) == first_header:
            return [tuple(md_render.plain(c) for c in row) for row in b[2]]
    return None
