"""The calculators CalcSuite knows: what differs between them, with no window code.

One class per model (Nspire, Ti84, Ti89). Each one is the single source of truth for:

- tk_keys: a PC key (Tk keysym) -> the calculator keys it presses;
- key_groups(): those keys grouped for the Keys panel (Top row / Menus / Editing / Mouse);
- the mouse: wheel, double / right / middle click, and click(x, y, frame) for a click on the
  screen (in the calculator's own pixels);
- SYMBOLS: the Symbols panel (a symbol -> the keys that type it, or the nearest thing);
- paste_keys(text): a pasted text -> key codes, Unicode symbols included.

Everything here is pure (tools/selftest checks it): no Tk, no USB.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.join(HERE, "nspire_cli"), os.path.join(HERE, "ti84_cli")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import nspire_keys  # noqa: E402
import ti84_keys  # noqa: E402
import ti89_keys  # noqa: E402

CLI = os.path.join(HERE, "bin", "nspire-cli.exe")
CLI_84 = os.path.join(HERE, "bin", "ti84-cli.exe")
CLI_89 = os.path.join(HERE, "bin", "ti89-cli.exe")

# How a PC key is written on a keycap in the Keys panel
PC_LABEL = {
    "Return": "Enter", "KP_Enter": "Enter (pad)", "Escape": "Esc", "Tab": "Tab",
    "BackSpace": "Backspace", "Delete": "Delete", "Insert": "Insert", "Home": "Home",
    "Left": "←", "Right": "→", "Up": "↑", "Down": "↓",
}


def pc_label(keysym):
    return PC_LABEL.get(keysym, keysym)


class Calc(object):
    """What every model has; the subclasses fill it in"""
    pid = 0
    title = ""
    slug = ""
    cli = ""
    can_send = True
    key_fmt = "%x"
    shot_holdoff = 0.6
    zoom = 1          # Small screens are drawn this many times bigger before the window's scale
    native = (320, 240)
    tk_keys = {}
    key_labels = {}   # A calculator key name -> how its key is labelled
    top_row, menus = (), ()  # keysyms in the Keys panel's Top row / Menus groups
    wheel = ("up", "down", "left", "right")
    double_click = right_click = middle_click = None
    click_help = ()   # (what you do, what it presses) rows for clicks on the screen
    extra_keys = ()   # (group, PC key text, calculator key text) rows not in tk_keys
    SYMBOLS = ()      # (symbol, what it is, key names / codes or None, nearest or note)
    PASTE = {}        # A Unicode character -> key names / codes (beyond code_for)

    @classmethod
    def code_for(cls, name):
        raise NotImplementedError

    @classmethod
    def resolve(cls, item):
        """A key name, a character or an int code -> the code, or None"""
        if isinstance(item, int):
            return item
        return cls.code_for(item)

    @classmethod
    def calc_label(cls, name):
        """A calculator key name -> its label: 'graph' -> 'GRAPH'"""
        if name in cls.key_labels:
            return cls.key_labels[name]
        return name if len(name) == 1 else name.upper()

    @classmethod
    def keys_label(cls, names):
        """Key names -> one label; a run of the same key is written once with its count"""
        out, i = [], 0
        names = list(names)
        while i < len(names):
            j = i
            while j < len(names) and names[j] == names[i]:
                j += 1
            lab = cls.calc_label(names[i]) if isinstance(names[i], str) else "#%x" % names[i]
            out.append(" ".join([lab] * (j - i)) if j - i < 3 else "%s×%d" % (lab, j - i))
            i = j
        return " ".join(out)

    @classmethod
    def click(cls, x, y, frame=None):
        """A click at (x, y) on the screen, in the calculator's pixels; frame is (w, h, rgb)
        of the picture shown. Returns key names to press, or None."""
        return None

    @classmethod
    def key_groups(cls):
        """[(group, [(PC key, calculator key)])] for the Keys panel, from tk_keys and the
        mouse settings (so the panel can never disagree with what the keys do)"""
        groups = {"Top row": [], "Menus": [], "Editing": [], "Mouse": []}
        for keysym, names in cls.tk_keys.items():
            if keysym == "KP_Enter":
                continue  # Shown as Enter
            group = ("Top row" if keysym in cls.top_row else
                     "Menus" if keysym in cls.menus else "Editing")
            groups[group].append((pc_label(keysym), cls.keys_label(names), keysym))
        for group, pc, calc in cls.extra_keys:
            groups[group].append((pc, calc, None))
        groups["Editing"] += [("Ctrl+V", "types the PC's clipboard text", None),
                              ("Ctrl+C", "copies the screen as a picture", None)]
        up, down, left, right = cls.wheel
        groups["Mouse"].append(("Wheel", "%s / %s" % (cls.calc_label(up), cls.calc_label(down)), None))
        groups["Mouse"].append(("Shift+wheel", "%s / %s" % (cls.calc_label(left), cls.calc_label(right)), None))
        for what, name in (("Double click", cls.double_click), ("Right click", cls.right_click),
                           ("Middle click", cls.middle_click)):
            if name:
                groups["Mouse"].append((what, cls.calc_label(name), None))
        for what, does in cls.click_help:
            groups["Mouse"].append((what, does, None))
        order = ("Top row", "Menus", "Editing", "Mouse")
        return [(g, groups[g]) for g in order if groups[g]]

    @classmethod
    def describe_press(cls, keysym, char, names):
        """'F5 -> GRAPH' for the Last key line"""
        pc = pc_label(keysym) if keysym in cls.tk_keys or keysym in PC_LABEL else (char or keysym)
        return "%s → %s" % (pc, cls.keys_label(names))

    @classmethod
    def symbol_keys(cls, symbol):
        for sym, _what, keys, _near in cls.SYMBOLS:
            if sym == symbol:
                return keys
        return None

    @classmethod
    def paste_keys(cls, text):
        """Text -> ([codes], set of characters it can't type). New lines are Enter."""
        codes, missing = [], set()
        i = 0
        while i < len(text):
            ch = text[i]
            if text.startswith("⁻¹", i) and "⁻¹" in cls.PASTE:  # ⁻¹
                seq, step = cls.PASTE["⁻¹"], 2
            elif ch == "\n":
                seq, step = ["enter"], 1
            elif ch in cls.PASTE:
                seq, step = cls.PASTE[ch], 1
            else:
                seq, step = [ch], 1
            got = [cls.resolve(k) for k in seq]
            if any(c is None for c in got):
                missing.add(ch)
            else:
                codes += got
            i += step
        return codes, missing


class PaletteKeys(list):
    """The keys for a symbol in the Nspire's symbol palette, from anywhere in it (back to π
    first); .cell is its (row, column), for the short walk palette_keys() makes"""
    cell = None


def _palette(row, col):
    """The Nspire's keys for the symbol at row, col of its symbol palette (catalog, tab 4)"""
    keys = PaletteKeys(["catalog", "4"] + ["up"] * 60 + ["left"] * 10 + ["down"] * row +
                       ["right"] * col + ["enter"])
    keys.cell = (row, col)
    return keys


# The short walk (palette_keys) is off until it passes a clean bench test: on 2026-11-27 it
# typed the right symbols once, then lost an enter and left the palette open (in a Scratchpad
# that had just shown a syntax error). The long way passed 8 of 8.
PALETTE_SHORT_WALK = False


def palette_keys(keys, at):
    """A Symbols row's keys, the short way when it's in the palette and `at` (the cell the last
    pick left the palette on: it remembers) is known: (key names, the cell it leaves).
    The long way works wherever the palette was left; the short one is ~70 keys fewer
    (~2 s on a CX II) but types the wrong symbol if someone moved in the palette by hand."""
    cell = getattr(keys, "cell", None)
    if cell is None:
        return list(keys), at
    if at is None or not PALETTE_SHORT_WALK:
        return list(keys), cell
    dr, dc = cell[0] - at[0], cell[1] - at[1]
    walk = (["down"] * dr if dr > 0 else ["up"] * -dr) + (["right"] * dc if dc > 0 else ["left"] * -dc)
    return ["catalog", "4"] + walk + ["enter"], cell


class Nspire(Calc):
    """The TI-Nspire CX II"""
    pid = 0xE022
    title = "TI-Nspire"
    slug = "nspire"
    cli = CLI
    key_fmt = "%06x"
    shot_holdoff = 0.15  # Seconds after a key before the next picture (keys go first)
    keepalive_key = "000000"  # A key code that does nothing (tested: the screen stays the same)
    tk_keys = {
        "Return": ["enter"], "KP_Enter": ["enter"], "Escape": ["esc"], "Tab": ["tab"],
        "BackSpace": ["backspace"], "Left": ["left"], "Right": ["right"], "Up": ["up"],
        "Down": ["down"], "F1": ["home"], "F2": ["menu"], "F3": ["doc"], "F4": ["catalog"],
        "F5": ["var"],
    }
    key_labels = {"enter": "enter", "esc": "esc", "tab": "tab", "backspace": "del",
                  "left": "←", "right": "→", "up": "↑", "down": "↓",
                  "home": "home", "menu": "menu", "doc": "doc", "catalog": "catalog",
                  "var": "var", "click": "click", "ctrl+menu": "ctrl menu",
                  "ctrl+w": "ctrl W", "ctrl+left": "ctrl ←", "ctrl+right": "ctrl →"}
    menus = ("F1", "F2", "F3", "F4", "F5")
    double_click, right_click, middle_click = "enter", "ctrl+menu", "menu"
    click_help = (("Click", "click (the X: close the document; page tabs: next page)"),)
    extra_keys = (("Editing", "Ctrl+letter", "ctrl+letter"),
                  ("Editing", "Ctrl+Shift+C / V", "the handheld's own copy / paste"))
    # Each button types the real symbol (bench, CX II CAS, OS 6.40.74, 2026-11-27):
    # - ∫ d/dx Σ: the templates from the Calculus menu (menu 4, in a Calculator page or the
    #   Scratchpad's Calculate)
    # - the rest: the symbol palette (catalog, tab 4: a grid 11 wide that remembers its last
    #   pick, so each press goes back to π first: arrows stop at the edges, ~55 rows)
    # - Latin-1 characters (± °) type themselves: a key code with the character in its top byte
    # Pasted text (PASTE) still types the spellings, which the Nspire turns into symbols on Enter.
    SYMBOLS = (
        ("∫", "integral template (menu 4 3: Calculus > Integral)", ["menu", "4", "3"], None),
        ("d/dx", "derivative template (menu 4 1: Calculus > Derivative)", ["menu", "4", "1"], None),
        ("√", "square root (symbol palette)", _palette(2, 9), None),
        ("π", "pi (its own key)", ["pi"], None),
        ("θ", "theta (symbol palette)", _palette(0, 5), None),
        ("Σ", "sum template (menu 4 5: Calculus > Sum)", ["menu", "4", "5"], None),
        ("∞", "infinity (symbol palette)", _palette(0, 4), None),
        ("≤", "less or equal (symbol palette)", _palette(1, 6), None),
        ("≥", "greater or equal (symbol palette)", _palette(1, 8), None),
        ("≠", "not equal (symbol palette)", _palette(1, 4), None),
        ("→", "store (symbol palette)", _palette(0, 6), None),
        ("i", "imaginary unit (symbol palette)", _palette(0, 2), None),
        ("e", "e, the constant (symbol palette)", _palette(0, 1), None),
        ("∠", "angle, polar (symbol palette)", _palette(1, 2), None),
        ("°", "degrees", ["°"], None),
        ("²", "squared", ["square"], None),
        ("⁻¹", "inverse (symbol palette)", _palette(5, 9), None),
        ("‾", "negative sign", ["neg"], None),
        ("±", "plus or minus (shows; the Nspire can't calculate with it)", ["±"], None),
        ("×", "times", "*", None),
        ("÷", "divide", "/", None),
        ("^", "power", "^", None),
        ("E", "×10^ (symbol palette)", _palette(0, 3), None),
        ("!", "factorial", "!", None),
        ("►", "convert ► (symbol palette)", _palette(0, 8), None),
        ("|x|", "absolute value", "abs(", None),
    )
    PASTE = {"∫": "integral(", "√": "sqrt(", "π": "pi", "θ": "theta",
             "Σ": "sumSeq(", "∞": "infinity", "≤": "<=", "≥": ">=",
             "≠": "/=", "→": "=:", "\U0001d456": "@i", "ℯ": "@e", "∠": "@<",
             "°": "@d", "²": "^2", "⁻¹": "^-1", "×": "*", "÷": "/",
             "►": "@>", "▸": "@>", "ᴇ": "@E", "−": "-", "⁻": ["neg"],
             "∂": "derivative("}

    @classmethod
    def code_for(cls, name):
        if name == "\xa0":  # A no-break space (text copied from the web) is a space
            name = " "
        code = nspire_keys.code_for(name)
        if code is None and len(name) == 1 and (" " <= name <= "~" or name in "°±²×÷"):
            # Any other printable ASCII character, and the Latin-1 ones tried: its code in the
            # top byte (! @ _ { [ and ° ± ² × ÷ on a CX II CAS, OS 6.4: each typed itself).
            # Other Latin-1 characters (é, soft hyphen) are untested: paste reports them.
            code = ord(name) << 16
        return code

    @classmethod
    def resolve(cls, item):
        if isinstance(item, int):
            return item
        return cls.code_for(item)

    @classmethod
    def symbol_sequence(cls, keys):
        """A SYMBOLS / PASTE entry -> key names: a string is typed character by character"""
        return list(keys) if isinstance(keys, str) else keys

    @classmethod
    def paste_keys(cls, text):
        """As Calc's, plus: after ^ the exponent is closed with the right arrow (the Nspire's ^
        opens a raised box that would swallow the rest of the line)"""
        expanded = []
        for k, ch in enumerate(text):
            seq = cls.PASTE.get(ch)
            if seq is None:
                expanded.append(ch)
            elif isinstance(seq, str):
                if seq.endswith("(") and text[k + 1:k + 2] == "(":
                    seq = seq[:-1]  # "√(16)": the bracket is already there
                expanded.extend(seq)
            else:
                expanded.append(tuple(seq))
        right = cls.resolve("right")
        codes, missing, stack, exp_ends, typed = [], set(), [], [], ""
        for i, item in enumerate(expanded):
            while exp_ends and exp_ends[-1] <= i:  # The exponent ends here: leave its box
                codes.append(right)
                exp_ends.pop()
            if isinstance(item, tuple):
                codes += [cls.resolve(k) for k in item]
                typed = ""
                continue
            ch = item
            if ch == "\n":
                codes.append(cls.resolve("enter"))
                stack, typed = [], ""
                continue
            if ch == ")" and stack and stack[-1] == "box":
                codes.append(right)  # sqrt( is a radical box: the arrow leaves it, ")" wouldn't
                stack.pop()
                typed += ch
                continue
            c = cls.resolve(ch)
            if c is None:
                missing.add(ch)
                continue
            codes.append(c)
            if ch == "(":
                stack.append("box" if typed.lower().endswith("sqrt") else "(")
            elif ch == ")" and stack:
                stack.pop()
            typed = (typed + ch)[-8:]
            if ch == "^":
                exp_ends.append(exponent_end(expanded, i + 1))
        codes += [right] * len(exp_ends)
        return codes, missing

    @classmethod
    def click(cls, x, y, frame=None):
        """The pointer can't be placed: known spots send the key that does the same job"""
        if y < 24 and x >= 292:
            return ["ctrl+w"]      # The X: close the document
        if y < 24 and x < 14:
            return ["ctrl+left"]   # The left page arrow
        if y < 24 and x < 100:
            return ["ctrl+right"]  # The page tabs and the right arrow: next page
        return ["click"]


def exponent_end(chars, i):
    """In a list of characters, where the exponent that starts at i ends: a minus sign, then a
    run of letters, digits and dots, or one bracketed group"""
    j = i
    if j < len(chars) and chars[j] in ("-",):
        j += 1
    if j < len(chars) and chars[j] == "(":
        depth = 0
        while j < len(chars):
            if chars[j] == "(":
                depth += 1
            elif chars[j] == ")":
                depth -= 1
                if depth == 0:
                    return j + 1
            j += 1
        return j
    while j < len(chars) and isinstance(chars[j], str) and (chars[j].isalnum() or chars[j] == "."):
        j += 1
    return j


class Ti84(Calc):
    """The TI-84 Plus CE family"""
    pid = 0xE008
    title = "TI-84 Plus CE"
    slug = "ti84"
    cli = CLI_84
    key_fmt = "%x"
    shot_holdoff = 0.6  # A picture takes ~1.4 s and can't be cut short: never start one mid-typing
    keepalive_key = "0"  # Key code 0 does nothing (tested: only the blinking cursor differs)
    zoom = 3            # The monochrome 84's 96 x 64 screen (the CE's is 320 x 240)
    tk_keys = {
        "Return": ["enter"], "KP_Enter": ["enter"], "Escape": ["clear"],
        "BackSpace": ["left", "del"], "Delete": ["del"], "Insert": ["ins"],
        "Left": ["left"], "Right": ["right"], "Up": ["up"], "Down": ["down"],
        "F1": ["y="], "F2": ["window"], "F3": ["zoom"], "F4": ["trace"], "F5": ["graph"],
        "F6": ["mode"], "F7": ["math"], "F8": ["apps"], "F9": ["prgm"], "F10": ["vars"],
        "F11": ["stat"], "F12": ["quit"],
    }
    key_labels = {"left": "←", "right": "→", "up": "↑", "down": "↓",
                  "quit": "2nd QUIT"}
    top_row = ("F1", "F2", "F3", "F4", "F5")
    menus = ("F6", "F7", "F8", "F9", "F10", "F11", "F12")
    double_click, right_click, middle_click = "enter", "clear", None
    click_help = (("Click a menu line", "picks it (arrows to it, ENTER)"),)
    # Tried on a TI-84 Plus CE, OS 5.4.0 (MathPrint): each typed what its row says
    SYMBOLS = (
        ("∫", "integral: fnInt(", ["fnint"], None),
        ("d/dx", "derivative: nDeriv(", ["nderiv"], None),
        ("√", "square root √(", ["sqrt"], None),
        ("π", "pi", ["pi"], None),
        ("θ", "theta", ["theta"], None),
        ("Σ", "sum Σ( (MATH 0)", ["math", "0"], None),
        ("∞", "infinity", None, "no ∞: use 1ᴇ99"),
        ("≤", "less or equal", ["test<="], None),
        ("≥", "greater or equal", ["test>="], None),
        ("≠", "not equal", ["test!="], None),
        ("=", "equals (TEST)", ["test="], None),
        ("<", "less than", ["test<"], None),
        (">", "greater than", ["test>"], None),
        ("→", "store STO→", ["sto"], None),
        ("i", "imaginary unit", ["i"], None),
        ("e", "e, the constant", ["conste"], None),
        ("∠", "angle (polar)", None, "no ∠: use rℯ^(θi)"),
        ("°", "degrees", ["degree"], None),
        ("ʳ", "radians", ["radian"], None),
        ("²", "squared", ["square"], None),
        ("³", "cubed", ["cube"], None),
        ("³√", "cube root", ["cuberoot"], None),
        ("⁻¹", "inverse", ["inverse"], None),
        ("‾", "negative sign (-)", ["neg"], None),
        ("±", "plus or minus", None, "no ± key: type the two answers"),
        ("×", "times", ["*"], None),
        ("÷", "divide", ["/"], None),
        ("^", "power", ["^"], None),
        ("E", "×10^ (EE)", ["ee"], None),
        ("!", "factorial", ["factorial"], None),
        ("|x|", "absolute value abs(", ["abs"], None),
    )
    PASTE = {"=": ["test="], "<": ["test<"], ">": ["test>"], "≤": ["test<="],
             "≥": ["test>="], "≠": ["test!="], "→": ["sto"], "√": ["sqrt"],
             "π": ["pi"], "θ": ["theta"], "²": ["square"], "³": ["cube"],
             "⁻¹": ["inverse"], "⁻": ["neg"], "−": ["-"], "×": ["*"],
             "÷": ["/"], "ᴇ": ["ee"], "\U0001d456": ["i"], "ℯ": ["conste"],
             "°": ["degree"], "ʳ": ["radian"], "!": ["factorial"],
             "∫": ["fnint"], "Σ": ["math", "0"]}

    @classmethod
    def code_for(cls, name):
        return ti84_keys.code_for(name)

    # The CE's menus (MATH, PRGM, VARS, ...): measured on a TI-84 Plus CE, OS 5.4.0. Below the
    # status bar (rows 0-29) the menu's tab row is at rows 37-54; item n's line is rows
    # 57 + 20 (n - 1) to 20 rows more, its number ("1:") in columns 2-11 with the colon (or
    # the scroll arrow) in 15-21; the chosen line's number is drawn white on black.
    MENU_TOP, MENU_ROW, MENU_ROWS = 57, 20, 9

    @classmethod
    def menu_rows(cls, frame):
        """For a menu on the screen: (the highlighted line's index 0-8, [lines with a
        number]), else None"""
        if frame is None:
            return None
        w, h, rgb = frame
        if (w, h) != (320, 240):
            return None

        def dark(x, y):
            i = (y * w + x) * 3
            return rgb[i] + rgb[i + 1] + rgb[i + 2] < 300

        lines, high = [], None
        for n in range(cls.MENU_ROWS):
            y0 = cls.MENU_TOP + cls.MENU_ROW * n
            ys = range(y0 + 1, min(h, y0 + 17))
            block = sum(1 for y in ys for x in range(0, 20) if dark(x, y))
            if block > 0.75 * 20 * len(ys):  # The highlighted number: white on a dark block
                high = n
                lines.append(n)
                continue
            digit = any(dark(x, y) for y in ys for x in range(2, 12))
            gap = not any(dark(x, y) for y in ys for x in (0, 1, 12, 13))
            colon = any(dark(x, y) for y in ys for x in range(15, 22))
            if digit and gap and colon:
                lines.append(n)
        if high is None or not lines:
            return None
        return high, lines

    @classmethod
    def click(cls, x, y, frame=None):
        """A click on a numbered menu line moves there and picks it (arrows, then ENTER):
        this also works when the menu has scrolled or the line is 0: or A:"""
        found = cls.menu_rows(frame)
        if found is None or y < cls.MENU_TOP:
            return None
        n = (y - cls.MENU_TOP) // cls.MENU_ROW
        high, lines = found
        if n not in lines:
            return None
        move = n - high
        return (["down"] * move if move > 0 else ["up"] * -move) + ["enter"]


class Ti89(Calc):
    """The TI-89 Titanium"""
    pid = 0xE004
    title = "TI-89 Titanium"
    slug = "ti89"
    cli = CLI_89
    key_fmt = "%x"
    shot_holdoff = 0.6
    zoom = 2  # Its 160 x 100 screen: x 2 here, x the window's scale on top
    native = (160, 100)
    # No keepalive_key: key code 0 makes the 89 stop answering the link (tested twice, OS 3.10),
    # and the window's screenshots alone kept it on for 7 minutes (its auto power-off is
    # "several minutes" of no use, TI's guidebook p. 5)
    keepalive_key = None
    tk_keys = {
        "Return": ["enter"], "KP_Enter": ["enter"], "Escape": ["esc"],
        "BackSpace": ["backspace"], "Delete": ["del"], "Insert": ["ins"],
        "Left": ["left"], "Right": ["right"], "Up": ["up"], "Down": ["down"], "Home": ["home"],
        "F1": ["f1"], "F2": ["f2"], "F3": ["f3"], "F4": ["f4"], "F5": ["f5"], "F6": ["f6"],
        "F7": ["f7"], "F8": ["f8"], "F9": ["apps"], "F10": ["mode"], "F11": ["catalog"],
        "F12": ["clear"],
    }
    key_labels = {"left": "←", "right": "→", "up": "↑", "down": "↓",
                  "backspace": "BACKSPACE", "del": "DEL", "ins": "INS"}
    top_row = ("F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8")
    menus = ("F9", "F10", "F11", "F12", "Home")
    double_click, right_click, middle_click = "enter", "esc", "home"
    click_help = (("Click a toolbar tab", "its F key (F1, F2, ... by position)"),)
    # The toolbar, measured on a TI-89 Titanium, OS 3.10 (Home screen): rows 0-14 of the
    # 160 x 100 screen, a full dark line under it on row 15, the tabs split by dark columns
    # (there at x = 0, 20, 49, 66, 87, 113, 144, 159: F1 Tools ... F6 Clean Up). The tabs are
    # as wide as their names, so they are found in the picture; without one, six equal tabs.
    TOOLBAR_H = 15
    TABS = 6
    SYMBOLS = (
        ("∫", "integral ∫( (2nd 7)", ["integral"], None),
        ("d(", "derivative d( (2nd 8)", ["deriv"], None),
        ("√", "square root √( (2nd ×)", ["sqrt"], None),
        ("π", "pi", ["pi"], None),
        ("θ", "theta", ["theta"], None),
        ("Σ", "sum Σ(", ["sigma", "("], None),
        ("∞", "infinity", ["infinity"], None),
        ("≤", "less or equal", ["le"], None),
        ("≥", "greater or equal", ["ge"], None),
        ("≠", "not equal", ["ne"], None),
        ("→", "store STO→", ["sto"], None),
        ("i", "imaginary unit \U0001d456", ["imag"], None),
        ("e", "ℯ^( (2nd LN)", [150, "^", "("], None),
        ("∠", "angle (polar)", ["angle"], None),
        ("°", "degrees", ["degree"], None),
        ("²", "squared", ["^", "2"], None),
        ("⁻¹", "inverse", ["^", "neg", "1"], None),
        ("‾", "negative sign (-)", ["neg"], None),
        ("±", "plus or minus", None, "no ± key: type the two answers"),
        ("×", "times", ["*"], None),
        ("÷", "divide", ["/"], None),
        ("^", "power", ["^"], None),
        ("E", "×10^ (EE)", ["ee"], None),
        ("!", "factorial", ["!"], None),
        ("|x|", "absolute value", ["a", "b", "s", "("], None),
    )
    PASTE = {}  # Filled below from calc_files' character map: a character's key is its code

    @classmethod
    def code_for(cls, name):
        return ti89_keys.code_for(name)

    @classmethod
    def toolbar_tabs(cls, frame):
        """The toolbar's tabs as [(x0, x1)] from the picture, or None when there is none"""
        if frame is None:
            return None
        w, h, rgb = frame
        if (w, h) != (160, 100):
            return None

        def dark(x, y):
            i = (y * w + x) * 3
            return rgb[i] + rgb[i + 1] + rgb[i + 2] < 300
        if sum(1 for x in range(w) if dark(x, cls.TOOLBAR_H)) < 150:
            return None  # No line under a toolbar: a screen without one (a graph, a dialog)
        seps = [x for x in range(w) if dark(x, 13) and dark(x, 14) and dark(x, 7)]
        cuts = []
        for x in seps:  # A separator can be one or two pixels wide
            if not cuts or x > cuts[-1] + 1:
                cuts.append(x)
        tabs = [(a, b) for a, b in zip(cuts, cuts[1:]) if b - a >= 6]
        return tabs or None

    @classmethod
    def click(cls, x, y, frame=None):
        """A click on a toolbar tab presses its F key"""
        if not (0 <= y < cls.TOOLBAR_H and 0 <= x < 160):
            return None
        tabs = cls.toolbar_tabs(frame)
        if tabs is None:
            if frame is not None:
                return None  # A picture without a toolbar: nothing to click
            return ["f%d" % (min(cls.TABS - 1, int(x * cls.TABS // 160)) + 1)]
        for k, (a, b) in enumerate(tabs):
            if a <= x < b:
                return ["f%d" % (k + 1)] if k < 8 else None
        return None


def _paste_89():
    """Unicode -> the 89's character codes (calc_files.CHARS_89): a character's key code on the
    89 is its character code"""
    try:
        import calc_files
        table = dict(calc_files.CHARS_89)
    except Exception:  # calc_files needs nothing special, but never break the keys over it
        table = {}
    out = {k: [v] for k, v in table.items() if len(k) == 1}
    out["⁻¹"] = ["^", "neg", "1"]
    out["×"], out["÷"] = ["*"], ["/"]
    out["−"] = ["-"]
    return out


Ti89.PASTE = _paste_89()

CALCS = (Nspire, Ti84, Ti89)
BY_SLUG = {c.slug: c for c in CALCS}
BY_PID = {c.pid: c for c in CALCS}


def symbol_codes(calc, keys):
    """A Symbols row's keys -> codes (None when one can't be typed)"""
    seq = list(keys) if isinstance(keys, str) else list(keys)
    got = [calc.resolve(k) for k in seq]
    return None if any(c is None for c in got) else got
