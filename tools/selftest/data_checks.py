"""The data bridge (data_bridge.py, the number formats in calc_files.py), no calculator needed:

- TI's numbers: 84 reals, complex numbers, lists, matrices and OS 5's exact forms; 89 integers,
  fractions, floats, complex numbers, lists and matrices: encode/decode round trips, the edge
  cases (zero, negatives, exponents +-99 / +-999, 14-digit rounding), bytes read from real
  backups, and tivars (TI-Toolkit) as a second opinion on the 84's bytes
- cell text: parse_number / number_text; the grid model; tab-separated and CSV text
- names, TI files for Send, the TI-Nspire program (passes check_nspire.py)
- Copy answer and the Data section against a faked link (an 84 with Ans, an 89 that runs
  typed on the home screen, the Nspire's "not possible")

    python -I tools/selftest/data_checks.py            (CALCSUITE_SHOTS=1: also screenshots
                                                       of the faked panel into build/screenshots)
"""

import os
import subprocess
import sys
import tempfile
import time

for _stream in (sys.stdout, sys.stderr):  # An old console code page: never crash on π
    try:
        _stream.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
KIT = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)

import calc_files as cf  # noqa: E402
import data_bridge as db  # noqa: E402

D, F, C = cf.Decimal, cf.Fraction, cf.TIComplex


def check(ok, what):
    print("%-4s data %s" % ("PASS" if ok else "FAIL", what))
    return 0 if ok else 1


def raises(fn, *a):
    try:
        fn(*a)
    except ValueError:
        return True
    return False


def r14(v):
    return cf._C14.plus(D(v)) if not isinstance(v, int) else D(v)


# ---- Numbers ----

def number_checks():
    f = 0
    # Bytes from a TI-84 Plus CE backup (A = 16, B = 9, L1 = {1}) and from TI-89 Titanium OS 3.10
    f += check(cf.real84_bytes(16).hex() == "008116000000000000" and
               cf.real84_value(bytes.fromhex("008090000000000000")) == 9 and
               cf.list84_values(1, bytes.fromhex("0100008010000000000000")) == [1],
               "84: bytes as a real TI-84 Plus CE keeps them (16, 9, {1})")
    f += check(cf.value89(bytes.fromhex("00030c011f")) == 12 and
               cf.value89(bytes.fromhex("000a3ffc265150419962 9823".replace(" ", ""))) ==
               D("0.00026515041996298") and
               cf.value89(bytes.fromhex("000ee5e540000000000000000023d9d9")) == [[0]],
               "89: bytes as a real TI-89 Titanium keeps them (12, 2.6515041996298E-4, [[0.]])")
    f += check(cf.number89_data(12).hex() == "00030c011f" and
               cf.matrix89_data([[D(0)]]).hex() == "000ee5e540000000000000000023d9d9",
               "89: the same bytes written back")
    cases = [0, 1, -1, 16, D(1) / 3, D("-0.5"), D("9.9999999999999E99"), D("-9.9999999999999E99"),
             D("1E-99"), D("-1.5E-99"), D("123456789012345678"), D("2.718281828459045"), F(2, 3)]
    ok = all(cf.real84_value(cf.real84_bytes(v)) == r14(cf._decimal(v)) for v in cases)
    f += check(ok, "84 reals: round trips (zero, negatives, E99, E-99, rounding to 14 digits)")
    f += check(raises(cf.real84_bytes, D("1E100")) and raises(cf.real84_bytes, D("9.99999999999995E99")) and
               cf.real84_value(cf.real84_bytes(D("1E-100"))) == 0,
               "84 reals: past E99 is refused, under E-99 is 0")
    f += check(cf.real84_bytes(D("0.33333333333333")) == cf.real84_bytes(D(1) / 3) and
               cf.number_text(cf.real84_value(cf.real84_bytes(D(1) / 3))) == "0.33333333333333",
               "84: 1/3 keeps all 14 digits: 0.33333333333333")
    # tivars (TI-Toolkit, MIT) writes the same bytes
    try:
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            from tivars.types import TIReal
        same = True
        for text in ("16", "-0.5", "9.9999999999999E99", "1E-99", "-1.5E-99", "0.33333333333333", "0"):
            r = TIReal()
            r.load_string(text)
            mine = cf.real84_bytes(D(text))
            same &= bytes(r.calc_data)[1:] == mine[1:] and (bytes(r.calc_data)[0] & 0x80) == (mine[0] & 0x80)
        f += check(same, "84 reals: the same bytes as tivars writes")
    except Exception as e:
        print("SKIP data tivars comparison (%s)" % e)
    cs = [C(3, 2), C(D("-1.5E-99"), D("9.9E99")), C(0, -1), C(0, 0)]
    f += check(all(cf.complex84_value(cf.complex84_bytes(c)) == C(r14(c.re), r14(c.im)) for c in cs) and
               cf.complex84_bytes(C(3, 2))[0] == 0x0C and cf.complex84_bytes(C(3, 2))[9] == 0x0C,
               "84 complex: round trips, both halves typed 0x0C")
    vals = [1, D("-2.5"), D("1E-99"), F(1, 3)]
    t, data = cf.list84_data(vals)
    f += check(t == 0x01 and cf.list84_values(t, data) == [r14(cf._decimal(v)) for v in vals],
               "84 lists: a real list round trips")
    t, data = cf.list84_data([1, C(0, 1)])
    f += check(t == 0x0D and cf.list84_values(t, data) == [C(1, 0), C(0, 1)], "84 lists: a complex list (0x0D)")
    f += check(cf.list84_values(1, b"\x00\x00") == [] and raises(cf.list84_data, [0] * 1000) and
               raises(cf.list84_values, 1, b"\x03\x00" + bytes(9)), "84 lists: empty, too long, cut short")
    rows = [[1, 2, 3], [D("-4.5"), 5, 6]]
    data = cf.matrix84_data(rows)
    f += check(data[:2] == b"\x03\x02" and cf.matrix84_rows(data) == [[r14(v) for v in r] for r in rows],
               "84 matrices: columns, rows, then row by row; round trips")
    f += check(raises(cf.matrix84_data, [[1], [1, 2]]) and raises(cf.matrix84_data, [[C(1, 1)]]) and
               raises(cf.matrix84_data, [[0] * 100]), "84 matrices: ragged, complex, past 99 are refused")
    frac = bytes((0x18,)) + cf.real84_bytes(D(1) / 3)[1:]
    pi = bytes((0x20,)) + cf.real84_bytes(D("0.5"))[1:]
    rad = bytes((0x1C, 0x00)) + bytes.fromhex("03000002000003")
    f += check(cf.value84(0x18, frac) == r14(D(1) / 3) and cf.number_text(cf.value84(0x20, pi)) ==
               "1.5707963267949" and cf.number_text(cf.value84(0x1C, rad)) == "1.1547005383793",
               "84 exact forms (OS 5): 1/3, π/2, 2√3/3 read as their value")
    # The 89
    c89 = [0, 12, -12, 2 ** 100, -(2 ** 64), F(1, 3), F(-22, 7), D("2.5"), D("-1E-999"),
           D("9.9999999999999E999"), D(0), C(3, -2), C(D("1.5"), F(1, 2))]
    ok = True
    for v in c89:
        back = cf.value89(cf.number89_data(v))
        want = v if isinstance(v, (int, F, C)) else r14(v)
        ok &= back == want and type(back) is type(want) or (isinstance(v, D) and back == want)
    f += check(ok, "89 numbers: integers, fractions, floats (E+-999), complex round trip")
    f += check(cf.number89_bytes(F(1, 3)).hex() == "0301010121" and cf.number89_bytes(0).hex() == "001f" and
               cf.number89_bytes(-12).hex() == "0c0120", "89: 1/3 is denominator, numerator, 0x21; 0 has no bytes")
    f += check(raises(cf.number89_bytes, D("1E1000")) and cf.value89(cf.number89_data(D("1E-1000"))) == 0,
               "89: past E999 is refused, under E-999 is 0")
    lst = [1, F(-1, 3), D("2.5"), C(0, 1)]
    m = [[1, 2], [3, D("4.5")]]
    f += check(cf.value89(cf.list89_data(lst)) == lst and cf.value89(cf.matrix89_data(m)) == m and
               cf.value89(cf.list89_data([])) == [], "89 lists and matrices round trip (rows in order)")
    f += check(cf.value89(b"\x00\x05\x00hi\x00\x2d") == "hi" and cf.value89(bytes.fromhex("0002261f")[:0] +
                                                                        b"\x00\x01\x26") == C(0, 1),
               "89: a string, and i alone")
    bad = [b"", b"\x00\x05\x01", bytes.fromhex("000ee5e540000000000000000023d9"),
           bytes.fromhex("0003e3"), b"\x00\x02\x05\x1f", b"\x00\x03\x00\x00\x21"]
    f += check(all(raises(cf.value89, b) for b in bad), "89: cut short, unknown tags, a fraction over 0 refused")
    s_polar = bytes.fromhex("0016e5e53fff50000000000000" + "23c001450000000000002326e3d9d9")
    f += check(raises(cf.value89, s_polar), "89: a polar entry (tag E3) is refused, not misread")
    return f


def text_checks():
    f = 0
    cases = {"2.5": D("2.5"), "-2": -2, "1/3": F(1, 3), "1E5": D("1E5"), "2.": D("2"), "⁻3": -3,
             "−1.5ᴇ-3": D("-1.5E-3"), "3+2i": C(3, 2), "3-2i": C(3, -2), "-i": C(0, -1), "i": C(0, 1),
             "2,5": D("2.5"), " 4 ": 4, "": None, "1e-99": D("1E-99"), "2.5E3-1E-2i": C(D("2.5E3"), D("-1E-2")),
             "1E-5+3j": C(D("1E-5"), 3), "-2i": C(0, -2)}
    bad = [k for k, v in cases.items() if cf.parse_number(k) != v or type(cf.parse_number(k)) is not type(v)]
    f += check(not bad, "cells: numbers in every spelling (%s)" % (bad or "E, ᴇ, ⁻, 1/3, 3+2i, -i, 2,5"))
    f += check(all(raises(cf.parse_number, t) for t in ("abc", "1/0", "1..2", "1E", "3+2", "NaN", "inf", "2ii")),
               "cells: what isn't a number says so")
    texts = {D("0.33333333333333"): "0.33333333333333", D("-1.5E-99"): "-1.5E-99", D("1E15"): "1E15",
             D("12345678901234"): "12345678901234",
             D("123456789012345"): "123456789012350", D("16.000000000000"): "16", C(3, -2): "3-2i",
             C(0, 1): "i", C(D(2), D(1)): "2+i", F(-1, 3): "-1/3", D("0.00001"): "0.00001",
             D("0.000001"): "1E-6", 0: "0"}
    bad = [(v, cf.number_text(v)) for v, t in texts.items() if cf.number_text(v) != t]
    f += check(not bad, "cells: numbers shown with every digit, E past 15 digits (%s)" % (bad or "ok"))
    f += check(cf.number_text(D("2"), True) == "2." and cf.parse_number("2.") == D(2) and
               isinstance(cf.parse_number(cf.number_text(D(2), True)), D),
               "cells: an 89 float shows as 2. and reads back as a float")
    ok = all(cf.parse_number(cf.number_text(v)) == r14(v) for v in
             (D("1.2345678901234E-50"), D("-7.5E88"), D("0.1")))
    f += check(ok, "cells: text round trips")
    return f


def grid_checks():
    f = 0
    g = db.Grid([["1", "4"], ["2", "5"], ["3", ""]], ["ZZX", "ZZY"])
    f += check(g.column_values(0) == [1, 2, 3] and g.column_values(1) == [4, 5], "grid: columns as lists")
    g.set(5, 0, "9")
    f += check(g.nrows == 6 and raises(g.column_values, 0), "grid: a gap in a list is an error")
    g.delete_rows([3, 4])
    f += check(g.column_values(0) == [1, 2, 3, 9], "grid: delete rows")
    g.insert_col(1)
    f += check(g.ncols == 3 and g.headers[1] not in ("ZZX", "ZZY") and g.headers[2] == "ZZY",
               "grid: insert a column with a free name")
    g.delete_col(1)
    g.insert_row(0)
    f += check(g.rows[0] == ["", ""] and g.nrows == 5, "grid: insert a row")
    g = db.Grid([[""]], ["ZZX"])
    g.paste("1\t2\r\n3\t4\r\n", 1, 0)
    f += check(g.rows == [["", ""], ["1", "2"], ["3", "4"]], "grid: paste tab-separated text grows it")
    m = db.Grid([["1", "2"], ["3", "4"], ["", ""]], kind="matrix")
    f += check(m.matrix_values() == [[1, 2], [3, 4]] and m.to_tsv() == "1\t2\r\n3\t4\r\n",
               "grid: a matrix, and its tab-separated text for Excel")
    m.set(0, 3, "7")
    f += check(raises(m.matrix_values), "grid: a matrix with an empty cell is an error")
    f += check(db.parse_table("a;b\n1,5;2\n") == [["a", "b"], ["1,5", "2"]] and
               db.parse_table("x,y\r\n1,2\r\n\r\n") == [["x", "y"], ["1", "2"]] and
               db.parse_table('﻿"1","2"') == [["1", "2"]], "CSV: commas, semicolons, quotes, a BOM")
    g = db.grid_from_csv("time;volts\n0;1,5\n0,5;2\n")
    f += check(g.headers == ["time", "volts"] and g.column_values(1) == [D("1.5"), 2],
               "CSV: header row found, decimal commas read")
    g2 = db.grid_from_csv(g.to_csv())
    f += check(g2.headers == g.headers and g2.rows == g.trimmed(), "CSV: saved and read back the same")
    f += check(db.grid_from_csv("1,2\n3,4\n").headers[0] not in ("1",), "CSV: numbers aren't a header")
    return f


def name_checks():
    f = 0
    ok = (db.calc_name("ti84", "list", "L1") == ("", "L₁") and db.calc_name("ti84", "list", "ʟzzx") ==
          ("", "ZZX") and db.calc_name("ti84", "matrix", "a") == ("", "[A]") and
          db.calc_name("ti84", "matrix", "[J]") == ("", "[J]") and db.calc_name("ti89", "list", "zzx") ==
          ("main", "zzx") and db.calc_name("ti89", "list", "Work\\ZZ1") == ("work", "zz1"))
    f += check(ok, "names: L1 -> L₁, ʟZZX, [A], 89 folder\\name")
    f += check(all(raises(db.calc_name, s, k, n) for s, k, n in (
        ("ti84", "list", "TOOLONG"), ("ti84", "list", "1A"), ("ti84", "matrix", "[K]"),
        ("ti89", "list", "toolongname"), ("ti89", "list", "a b"))), "names: what the calculator refuses")
    blob, ext, shown = db.var_file("ti84", "list", [1, 2], "ZZX")
    (t, name, _v, _a, data), = cf.read_ti8x(blob)
    f += check(ext == "8xl" and shown == "ʟZZX" and t == 1 and name == b"\x5dZZX" and
               cf.list84_values(t, data) == [1, 2], "Send: an 84 named list as a .8xl")
    blob, ext, shown = db.var_file("ti84", "list", [C(1, 1)], "L6")
    (t, name, _v, _a, data), = cf.read_ti8x(blob)
    f += check(ext == "8xl" and t == 0x0D and name == b"\x5d\x05" and shown == "L₆", "Send: L6, complex")
    blob, ext, shown = db.var_file("ti84", "matrix", [[1, 2]], "J")
    (t, name, _v, _a, data), = cf.read_ti8x(blob)
    f += check(ext == "8xm" and name == b"\x5c\x09" and shown == "[J]", "Send: matrix [J] as a .8xm")
    blob, ext, shown = db.var_file("ti89", "matrix", [[1, F(1, 2)]], "zzm")
    (folder, name, t, _a, data), = cf.read_ti89(blob)
    f += check(ext == "89m" and folder == b"main" and name == b"zzm" and t == 6 and
               cf.value89(data) == [[1, F(1, 2)]], "Send: an 89 matrix as a .89m in main")
    src = db.nspire_program({"zzx": [1, D("2.5"), F(1, 4), D("1E-5")], "zzy": [3, 4, 5, 6]})
    path = os.path.join(tempfile.mkdtemp(), "zzdata.py")
    with open(path, "w", encoding="ascii") as fh:
        fh.write(src)
    p = subprocess.run([sys.executable, "-I", os.path.join(TOOLS, "check_nspire.py"), path],
                       capture_output=True, text=True)
    f += check(p.returncode == 0 and 'store_list("zzx",[1.0,2.5,0.25,0.00001])' in src,
               "Nspire: the program that stores the lists passes check_nspire.py")
    p = subprocess.run([sys.executable, "-I", os.path.join(TOOLS, "run_on_pc.py"), path],
                       capture_output=True, text=True)
    f += check(p.returncode == 0 and "zzy: 4 numbers" in p.stdout, "Nspire: ... and runs on the PC")
    f += check(raises(db.nspire_program, {"zz": [C(1, 1)]}), "Nspire: complex lists are refused")
    f += check(db.answer_text([[1, 2], [3, 4]], "ti84") == "1\t2\r\n3\t4" and
               db.answer_text([D("1.5"), 2], "ti84") == "1.5\r\n2", "answer text: lists and matrices for Excel")
    return f


# ---- A faked link ----

class FakeCalc(object):
    def __init__(self, slug):
        self.slug = slug
        self.title = {"ti84": "TI-84 Plus CE", "ti89": "TI-89 Titanium", "nspire": "TI-Nspire CX II"}[slug]


class FakeLinkMirror(object):
    """run_batch answering like the link helper: ls, get, send, rm, home, exec, put"""

    def __init__(self, slug, ans=None, refuse_ans=False):
        self.calc = FakeCalc(slug)
        self.session = object()
        self.vars = {}  # (type, folder, name) -> data
        self.ans, self.refuse_ans = ans, refuse_ans
        self.log, self.status, self.last_key, self.puts = [], [], 0, []
        if slug == "ti84" and ans is not None:
            t, data = ans
            self.vars[(t, b"", b"Ans")] = data

    def set_status(self, text):
        self.status.append(text)

    def run_batch(self, cmds, timeout=900):
        return [self.one(line) for line, _p in cmds]

    def one(self, line):
        self.log.append(line)
        word, _, rest = line.partition(" ")
        unhex = lambda h: b"" if h == "-" else bytes.fromhex(h)
        if word == "ls":
            out = ["ITEM type=%02x size=%d arch=0 locked=0 folder=%s name=%s" % (t, len(d), cf.to_hex(fo),
                                                                                 cf.to_hex(n))
                   for (t, fo, n), d in self.vars.items() if n != b"Ans"]
            return 0, out + ["OK %d item(s)" % len(out)]
        if word == "get":
            t, fo, n, _size, path = rest.split(" ", 4)
            key = (int(t, 16), unhex(fo), unhex(n))
            if key not in self.vars or (self.refuse_ans and key[2] == b"Ans"):
                return 4, ["ERR get: the calculator refused (0x0004, code 0x0012)"]
            with open(path, "wb") as fh:
                fh.write(self.vars[key])
            return 0, ["OK got size=%d arch=0 version=0" % len(self.vars[key])]
        if word == "send":
            with open(rest, "rb") as fh:
                blob = fh.read()
            if self.calc.slug == "ti89":
                for fo, n, t, _a, d in cf.read_ti89(blob):
                    self.vars[(t, fo, n)] = d
            else:
                for t, n, _v, _a, d in cf.read_ti8x(blob):
                    self.vars[(t, b"", cf.detokenize_name_84(n, t).encode("utf-8"))] = d
            return 0, ["OK sent 1 variable(s)"]
        if word == "rm":
            t, n, fo = rest.split(" ")
            self.vars.pop((int(t, 16), unhex(fo), unhex(n)), None)
            return 0, ["OK removed"]
        if word == "home":
            return 0, ["OK home"]
        if word == "keys":
            return self.keys([int(k, 16) for k in rest.split()])
        if word == "shot":  # The 89: a picture of its Home screen (or the Apps desktop)
            with open(rest, "wb") as fh:
                fh.write(b"P6\n160 100\n255\n" + self.screen_89())
            return 0, ["OK shot 160x100"]
        if word == "put":
            self.puts.append(rest)
            return 0, ["OK put"]
        return 4, ["ERR unknown"]

    screen = "home"  # The 89: "home", "busy" (text in the entry line) or "desktop"

    def screen_89(self):
        px = bytearray(b"\xff" * (160 * 100 * 3))

        def dot(x, y):
            i = (y * 160 + x) * 3
            px[i:i + 3] = b"\x00\x00\x00"
        cols = db.HOME_89_DIVIDERS if self.screen != "desktop" else (20, 21, 124, 125)
        for x in cols:
            for y in range(1, 15):
                dot(x, y)
        for x in range(160):  # The full line above the entry line
            dot(x, 83)
        if self.screen == "busy":
            for x in range(10, 60):
                dot(x, 86)
        if self.screen == "selected":  # The last entry, highlighted after ENTER (bench, OS 3.10)
            for x in range(0, 70):
                for y in range(84, 93):
                    if not (y in (87, 88) and x % 3 == 1) and not (y == 92 and x in (40, 41)):
                        dot(x, y)
        return bytes(px)

    def keys(self, codes):
        """The 84: QUIT, then {Ans}→ZZANS or Ans→ZZANS; the 89: ans(1)→zzv:string(zzv)→zzs"""
        if self.calc.slug == "ti84":
            from ti84_keys import CHAR, NAMED
            if codes[-1] != NAMED["enter"] or self.ans is None:
                return 0, ["OK keys %d" % len(codes)]
            t, data = self.ans
            braced = codes[0] == CHAR["{"]
            if braced and t in (0x00, 0x0C):  # A number: a list of one
                v = cf.value84(t, data)
                lt, ld = cf.list84_data([v])
                self.vars[(lt, b"", b"ZZANS")] = ld
            elif not braced and t in (0x01, 0x0D):  # A list as it is
                self.vars[(t, b"", b"ZZANS")] = data
            return 0, ["OK keys %d" % len(codes)]
        if self.ans is not None:
            self.vars[(0x00, b"main", b"zzv")] = cf.number89_data(self.ans)
            text = cf.number_text(self.ans).encode("latin-1")
            self.vars[(0x0C, b"main", b"zzs")] = cf.struct.pack(">H", len(text) + 3) + b"\x00" + text + b"\x00\x2d"
        return 0, ["OK keys %d" % len(codes)]


def answer_checks(root):
    f = 0

    def copy(m):
        said = []
        db.copy_answer(m, root, said.append)
        pump(root, lambda: said and not said[-1].startswith("Reading"), 20)
        clip = root.clipboard_get() if said and said[-1].startswith("Copied") else None
        return said[-1] if said else "", clip

    m = FakeLinkMirror("ti84", ans=(0x00, cf.real84_bytes(D(1) / 3)))
    said, clip = copy(m)
    f += check(clip == "0.33333333333333" and said == "Copied 0.33333333333333 from the TI-84 Plus CE",
               "Copy answer 84: Ans after 1/3 -> %r" % said)
    f += check(not any(k[2] == b"ZZANS" for k in m.vars), "Copy answer 84: ZZANS removed afterwards")
    m = FakeLinkMirror("ti84", ans=(0x0D, cf.list84_data([C(1, 2), 3])[1]))
    said, clip = copy(m)
    f += check(clip == "1+2i\r\n3", "Copy answer 84: a complex list in Ans (Ans→ZZANS) -> %r" % said)
    m = FakeLinkMirror("ti84", ans=(0x02, cf.matrix84_data([[1, 2], [3, 4]])))
    said, clip = copy(m)
    f += check(clip is None and "isn't a number or a list" in said,
               "Copy answer 84: a matrix says what to do instead")
    m = FakeLinkMirror("ti89", ans=F(1, 3))
    said, clip = copy(m)
    f += check(clip == "1/3" and said.endswith("from the TI-89 Titanium") and
               not [l for l in m.log if l.startswith(("send", "exec"))] and
               not any(k[2] in (b"zzv", b"zzs") for k in m.vars),
               "Copy answer 89: typed on Home, 1/3 read exactly, zzv/zzs removed")
    m.ans = D("0.33333333333333")
    said, clip = copy(m)
    f += check(clip == "0.33333333333333", "Copy answer 89: a float in full")
    m.screen = "desktop"
    said, clip = copy(m)
    f += check(clip is None and "Home screen first" in said and not [l for l in m.log[-3:] if l.startswith("keys")],
               "Copy answer 89: on the Apps desktop it types nothing and says so")
    m.screen = "busy"
    said, clip = copy(m)
    f += check(clip is None and "entry line" in said, "Copy answer 89: text in the entry line: says so")
    m.screen, m.ans = "selected", F(1, 3)
    said, clip = copy(m)
    f += check(clip == "1/3", "Copy answer 89: the last entry highlighted after ENTER is typed over (%s)" % said)
    m.screen, m.ans = "home", None
    said, clip = copy(m)
    f += check(clip is None and "didn't store" in said, "Copy answer 89: no answer says so (%s)" % said)
    m = FakeLinkMirror("nspire")
    said, clip = copy(m)
    f += check(clip is None and "no command" in said and not m.log, "Copy answer Nspire: says it isn't possible")
    return f


class FakePanel(object):
    def __init__(self, m):
        self.m, self.calc = m, m.calc


def pump(root, until, s=10):
    """Runs Tk's main loop (workers' after() calls need it) until until() or s seconds"""
    t0 = time.time()

    import tkinter as tk
    q = getattr(tk.Misc.after, "calcsuite_queue", None)  # mirror's: App.pump runs it in the app

    def poll():
        while q is not None and not q.empty():
            fn, args = q.get()
            fn(*args)
        if until() or time.time() - t0 > s:
            root.quit()
        else:
            root.after(20, poll)
    root.after(20, poll)
    root.mainloop()
    root.update()


def shot(win, name):
    if not os.environ.get("CALCSUITE_SHOTS"):
        return None
    try:
        from PIL import ImageGrab
        win.update()
        time.sleep(0.3)
        win.update()
        x, y = win.winfo_rootx(), win.winfo_rooty()
        w, h = win.winfo_width(), win.winfo_height()
        out = os.path.join(KIT, "build", "screenshots")
        os.makedirs(out, exist_ok=True)
        path = os.path.join(out, name + ".png")
        ImageGrab.grab((x, y, x + w, y + h), all_screens=True).save(path)
        print("     screenshot %s" % path)
        return path
    except Exception as e:
        print("SKIP screenshot %s (%s)" % (name, e))
        return None


def section_checks(root):
    import tkinter as tk
    import ui_theme as th
    f = 0
    for slug in ("ti84", "ti89", "nspire"):
        m = FakeLinkMirror(slug)
        if slug == "ti84":
            m.vars[(0x01, b"", "L₁".encode())] = cf.list84_data([1, 2, 3, 4, 5])[1]
            m.vars[(0x01, b"", "L₂".encode())] = cf.list84_data([1, 4, 9, 16, 25])[1]
            m.vars[(0x02, b"", b"[A]")] = cf.matrix84_data([[1, 2], [3, 4]])
            m.vars[(0x00, b"", b"A")] = cf.real84_bytes(16)
        elif slug == "ti89":
            m.vars[(0x04, b"main", b"zzx")] = cf.list89_data([D("0.5"), 1, F(3, 2)])
            m.vars[(0x06, b"main", b"zzm")] = cf.matrix89_data([[1, 2], [3, 4]])
        win = tk.Toplevel(root)
        win.title("Data - %s (faked link)" % m.calc.title)
        win.configure(bg=th.PANEL)
        win.geometry("470x820+40+20")
        sec = db.DataSection(FakePanel(m), win)
        sec.frame.pack(fill="both", expand=True, padx=12, pady=10)
        sec.shown()
        if slug != "nspire":
            pump(root, lambda: sec.items)
            names = sorted(i["text"] for i in sec.items)
            want = ["L₁", "L₂", "[A]"] if slug == "ti84" else ["main\\zzm", "main\\zzx"]
            f += check(names == want, "%s section: lists and matrices only (%s)" % (slug, names))
            if slug == "ti84":
                sec.tree.selection_set(["0", "1"])
                sec.plot_selected()
                pump(root, lambda: sec.plot.data)
                f += check(sec.plot.data and len(sec.plot.data[0]) == 5 and
                           len(sec.plot.c.find_all()) > 20, "84 section: L₂ against L₁ plotted")
                shot(win, "data-ti84-list-plot")
            k = next(str(n) for n, i in enumerate(sec.items) if i["type"] in (0x01, 0x04))
            sec.tree.selection_set([k])
            sec.open_selected()
            pump(root, lambda: sec.editor is not None)
            ed = sec.editor
            f += check(ed is not None and not sec.list_page.winfo_ismapped() and ed.g.ncols == 1,
                       "%s section: Open shows the grid in the panel, in the list's place" % slug)
            if ed is None:
                continue
            if slug == "ti89":
                f += check(ed.g.rows[0] == ["0.5"] and ed.g.rows[2] == ["3/2"], "89 grid: exact 3/2 kept")
            ed.cur = (ed.g.nrows, 0)
            ed.g.set(ed.g.nrows, 0, "36")
            ed.rebuild()
            ed.col_name.set("ZZY" if slug == "ti84" else "zzy")
            ed.rename_col()
            ed.send()
            pump(root, lambda: ed.status.get().startswith(("Sent", "Not sent")))
            key = (0x01, b"", b"ZZY") if slug == "ti84" else (0x04, b"main", b"zzy")
            got = read = None
            if key in m.vars:
                read = db.read_value(slug, key[0], m.vars[key])
                got = read[-1] == 36
            f += check(bool(got), "%s grid: a row added, renamed, sent back (%s)" % (slug, ed.status.get()))
            shot(win, "data-%s-grid" % slug)
            ed.kind.set("matrix")
            ed.kind_changed()
            f += check(ed.name_entry.winfo_ismapped() or ed.name.get(), "%s grid: matrix mode names it" % slug)
            sec.close_editor()
            root.update()
            f += check(sec.editor is None and sec.list_page.winfo_ismapped(), "%s section: Close brings the list back" % slug)
        else:
            sec.new("list")
            ed = sec.editor
            for r, v in enumerate(("1", "2.5", "1/4")):
                ed.g.set(r, 0, v)
            ed.rebuild()
            ed.send()
            pump(root, lambda: ed.status.get().startswith(("Sent", "Not sent")))
            f += check(m.puts and m.puts[0].endswith("|/zzdata.tns"), "Nspire grid: Send puts zzdata.tns (%s)"
                       % ed.status.get())
            shot(win, "data-nspire")
        win.destroy()
    return f


def ui_checks():
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
    except Exception as e:
        print("SKIP data UI (no Tk here: %s)" % e)
        return 0
    f = 0
    try:
        f += answer_checks(root)
        f += section_checks(root)
    finally:
        root.destroy()
    return f


def main():
    f = number_checks() + text_checks() + grid_checks() + name_checks() + ui_checks()
    return f


if __name__ == "__main__":
    n = main()
    print("\n%s" % ("ALL PASSED" if not n else "%d FAILURE(S)" % n))
    sys.exit(1 if n else 0)
