"""The data bridge: lists and matrices between the calculators and the PC, and Copy answer.

- The side panel's Data section: the calculator's lists and matrices (84: L1-L6, named lists,
  [A]-[J]; 89: list and matrix variables in every folder), opened in a spreadsheet-style
  grid (edit, add or remove rows and columns, copy and paste tab-separated text with Excel,
  import and save CSV), sent back under a chosen name, and plotted (one list against its
  index, or two as x, y).
- The TI-Nspire keeps its variables inside its documents, which the link only moves as whole
  .tns files: lists go to it as a small Python program (a .tns in My Documents) that stores
  them with ti_system.store_list when it runs; reading them back isn't possible over the link.
- Copy answer (the tab's button row and the Data section): the last answer, with every digit
  the calculator keeps, on the PC clipboard. The 84: its Ans variable, read over the link. The
  89: its home screen history isn't a variable, so a tiny program (main\\zzans) stores ans(1)
  in zzv (and string(ans(1)) in zzs); CalcSuite runs it over the link and reads them. The
  Nspire's link has no such command: the button says so.

Every link command goes through the Mirror's link thread (run_batch, from a worker thread
here); widgets are only touched on Tk's thread (after()). The number formats are in
calc_files.py.
"""

import csv
import io
import os
import re
import tempfile
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import calc_files as cf
import ui_theme as th

LIST_TYPES = {"ti84": (0x01, 0x0D), "ti89": (0x04,)}
MATRIX_TYPES = {"ti84": (0x02,), "ti89": (0x06,)}
# Ans can hold any of these: tried in this order (the request names the type)
ANS_TYPES_84 = (0x00, 0x0C, 0x01, 0x0D, 0x02, 0x18, 0x1B, 0x1C, 0x1D, 0x20, 0x21, 0x1E, 0x1F, 0x04)
ANS_NAME_84 = b"Ans"
PROG_89 = ("zzans()\nPrgm\nTry\nans(1)→zzv\nstring(zzv)→zzs\nElse\nClrErr\n"
           "\"\"→zzs\nEndTry\nEndPrgm\n")
NSPIRE_NO_ANSWER = ("The TI-Nspire's USB link has no command that reads the last answer (TI's own "
                    "software can't either): its variables live inside its documents. Copy "
                    "screen puts a picture of the screen on the clipboard instead.")
NSPIRE_NO_READ = ("The TI-Nspire keeps lists and matrices inside its documents (.tns), which the "
                  "link only moves whole and TI encodes: CalcSuite can't read them out. It can "
                  "send lists the other way: make or import them here, then Send, and run the "
                  "program it puts in My Documents (ctrl+R) to store them in that document.")


def log_error(where, detail=None):
    """mirror.log_error (errors.log); never raises"""
    try:
        import sys
        sys.modules["mirror"].log_error(where, detail=detail)
    except Exception:
        pass


def on_tk(widget, fn, *args):
    try:
        widget.after(0, lambda: fn(*args))
    except (tk.TclError, RuntimeError):
        pass


# ---- Names ----

def display_name(slug, item):
    """An ls item -> how the calculator shows it (ʟ before an 84 named list, folder\\name)"""
    text = cf.name_text(item["name"])
    if slug == "ti89":
        return cf.name_text(item["folder"] or b"main") + "\\" + text
    if item["type"] in (0x01, 0x0D) and not re.match("^L[₁-₆]$", text):
        return "ʟ" + text
    return text


def calc_name(slug, kind, text):
    """What the user typed -> (folder, name) the calculator takes; ValueError says why not.
    84 lists: L1-L6 or up to 5 capitals/digits (a letter first); matrices [A]-[J]. 89: up to
    8 lower case letters, digits or _ (a letter first), optionally after folder\\."""
    s = (text or "").strip()
    if slug == "ti84":
        s = s.replace("ʟ", "").replace("|L", "").upper()
        if kind == "matrix":
            m = re.match(r"^\[?([A-J])\]?$", s)
            if not m:
                raise ValueError("a TI-84 matrix is [A] to [J]")
            return "", "[%s]" % m.group(1)
        m = re.match(r"^L([1-6₁-₆])$", s)
        if m:
            d = m.group(1)
            return "", "L" + (cf.SUB[int(d)] if d.isdigit() else d)
        if not re.match(r"^[A-Z][A-Z0-9]{0,4}$", s):
            raise ValueError("a TI-84 list is L1 to L6, or a name of up to 5 capitals and digits "
                             "starting with a letter (ZZX)")
        return "", s
    if slug == "ti89":
        folder, _, name = s.lower().rpartition("\\")
        folder = folder or "main"
        for part in (folder, name):
            if not cf.NAME_89.match(part):
                raise ValueError("a TI-89 name is up to 8 lower case letters, digits or _, a "
                                 "letter first (folder\\name or just name)")
        return folder, name
    if not re.match(r"^[A-Za-z][A-Za-z0-9_]{0,15}$", s):
        raise ValueError("a TI-Nspire name is letters, digits or _, a letter first")
    return "", s.lower()


# ---- The grid (no Tk): rows of cell texts ----

class Grid(object):
    """kind "list": each column is a list, named by its header; "matrix": the cells are one
    matrix. Cells are text; numbers are read when they're sent or plotted."""

    def __init__(self, rows=None, headers=None, kind="list"):
        self.kind = kind
        self.rows = [[str(c) for c in r] for r in (rows or [])] or [[""]]
        self.headers = list(headers or [])
        self.normalize()

    def normalize(self):
        w = max([len(r) for r in self.rows] + [len(self.headers), 1])
        for r in self.rows:
            r.extend([""] * (w - len(r)))
        if not self.rows:
            self.rows = [[""] * w]
        n = len(self.headers)
        self.headers.extend("" for _ in range(w - n))
        for k in range(w):
            if not self.headers[k]:
                self.headers[k] = self.free_header()

    def free_header(self):
        used = set(self.headers)
        for k in range(1, 100):
            if "zz%d" % k not in used and "ZZ%d" % k not in used:
                return "ZZ%d" % k
        return "ZZ"

    @property
    def ncols(self):
        return len(self.rows[0])

    @property
    def nrows(self):
        return len(self.rows)

    def get(self, r, c):
        return self.rows[r][c] if r < self.nrows and c < self.ncols else ""

    def set(self, r, c, text):
        while r >= self.nrows:
            self.rows.append([""] * self.ncols)
        if c >= self.ncols:
            for row in self.rows:
                row.extend([""] * (c + 1 - self.ncols))
            self.normalize()
        self.rows[r][c] = text.strip()

    def insert_row(self, at=None):
        at = self.nrows if at is None else max(0, min(at, self.nrows))
        self.rows.insert(at, [""] * self.ncols)

    def delete_rows(self, which):
        keep = [r for k, r in enumerate(self.rows) if k not in set(which)]
        self.rows = keep or [[""] * self.ncols]

    def insert_col(self, at=None, header=""):
        at = self.ncols if at is None else max(0, min(at, self.ncols))
        for r in self.rows:
            r.insert(at, "")
        self.headers.insert(at, header or self.free_header())

    def delete_col(self, c):
        if self.ncols <= 1:
            self.rows = [[""] for _ in self.rows]
            return
        for r in self.rows:
            del r[c]
        del self.headers[c]

    def trimmed(self):
        """The rows without empty rows at the end and empty columns at the right"""
        rows = [list(r) for r in self.rows]
        while rows and not any(rows[-1]):
            rows.pop()
        w = max([max([k + 1 for k, c in enumerate(r) if c] + [0]) for r in rows] + [0])
        return [r[:w] for r in rows]

    def column_values(self, c):
        """A column as numbers: empty cells at its end don't count, one in between is an
        error (a list has no gaps)"""
        cells = [r[c] for r in self.rows]
        while cells and not cells[-1].strip():
            cells.pop()
        out = []
        for k, t in enumerate(cells):
            try:
                v = cf.parse_number(t)
            except ValueError as e:
                raise ValueError("%s, row %d: %s" % (self.headers[c], k + 1, e))
            if v is None:
                raise ValueError("%s, row %d is empty: a list has no gaps" % (self.headers[c], k + 1))
            out.append(v)
        return out

    def matrix_values(self):
        rows = self.trimmed()
        if not rows:
            raise ValueError("the grid is empty")
        out = []
        for i, r in enumerate(rows):
            row = []
            for j, t in enumerate(r):
                try:
                    v = cf.parse_number(t)
                except ValueError as e:
                    raise ValueError("row %d, column %d: %s" % (i + 1, j + 1, e))
                if v is None:
                    raise ValueError("row %d, column %d is empty: a matrix has every cell" % (i + 1, j + 1))
                row.append(v)
            out.append(row)
        return out

    def to_tsv(self, rows=None, header=False):
        """Tab-separated text (what Excel copies and pastes); rows: which rows (all)"""
        body = [self.rows[k] for k in rows] if rows is not None else self.trimmed()
        lines = (["\t".join(self.headers)] if header and self.kind == "list" else [])
        lines += ["\t".join(r) for r in body]
        return "\r\n".join(lines) + ("\r\n" if lines else "")

    def paste(self, text, r=0, c=0):
        """Tab-separated (or CSV) text into the grid from cell (r, c), growing it as needed"""
        for i, row in enumerate(parse_table(text)):
            for j, cell in enumerate(row):
                self.set(r + i, c + j, cell)

    def to_csv(self):
        out = io.StringIO()
        w = csv.writer(out, lineterminator="\r\n")
        if self.kind == "list":
            w.writerow(self.headers)
        for r in self.trimmed():
            w.writerow(r)
        return out.getvalue()


def parse_table(text):
    """Clipboard or CSV text -> rows of cells. Tabs (Excel's clipboard) when there are any,
    else the commas or semicolons of a CSV (a semicolon CSV may use decimal commas)."""
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    if text.startswith("﻿"):
        text = text[1:]
    lines = text.split("\n")
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        return []
    if any("\t" in l for l in lines):
        return [l.split("\t") for l in lines]
    sample = "\n".join(lines[:20])
    delim = ";" if sample.count(";") > 0 and sample.count(";") >= sample.count(",") / 2 else ","
    if delim == "," and not re.search(r",", sample):
        delim = ","
    return [list(r) for r in csv.reader(lines, delimiter=delim)]


def split_header(rows):
    """(headers or None, rows): a first row is a header when it isn't all numbers and the next
    rows have numbers in them"""
    if len(rows) < 1:
        return None, rows

    def numeric(cell):
        try:
            return cf.parse_number(cell) is not None
        except ValueError:
            return False
    first = rows[0]
    if any(c.strip() and not numeric(c) for c in first) and (
            len(rows) == 1 or any(numeric(c) for r in rows[1:] for c in r)):
        return [c.strip() for c in first], rows[1:]
    return None, rows


def grid_from_csv(text, kind="list"):
    headers, rows = split_header(parse_table(text))
    if kind == "list" and headers:
        headers = [_header_name(h) for h in headers]
    return Grid(rows or [[""]], headers if kind == "list" else None, kind)


def _header_name(h):
    s = re.sub(r"[^A-Za-z0-9_₁-₆\[\]\\θ]", "", h)
    return s[:12]


# ---- Calculator variables <-> the grid ----

def grid_from_value(slug, value, name=""):
    """A value read from a calculator (a list or a matrix) -> a Grid"""
    text = lambda v: cf.number_text(v, float_mark=slug == "ti89")
    if isinstance(value, list) and value and isinstance(value[0], list):
        return Grid([[text(v) for v in r] for r in value], kind="matrix")
    if isinstance(value, list):
        g = Grid([[text(v)] for v in value] or [[""]], [name or "ZZ1"], "list")
        return g
    raise ValueError("not a list or matrix")


def read_value(slug, vtype, data):
    """A variable's data -> its value (calc_files' readers); ValueError for what isn't data"""
    return cf.value89(data) if slug == "ti89" else cf.value84(vtype, data)


def var_file(slug, kind, values, name_text):
    """Numbers (a list) or rows (a matrix) -> (TI file bytes, the file extension, the shown
    name). ValueError says what's wrong (a name the calculator doesn't take, too big...)."""
    folder, name = calc_name(slug, kind, name_text)
    if slug == "ti84":
        if kind == "matrix":
            vtype, data = 0x02, cf.matrix84_data(values)
        else:
            if not values:
                raise ValueError("%s is empty" % name)
            vtype, data = cf.list84_data(values)
        blob = cf.ti8x_bytes([(vtype, cf.tokenize_name_84(name, vtype), 0, False, data)])
        shown = name if kind == "matrix" or re.match("^L[₁-₆]$", name) else "ʟ" + name
        return blob, cf.TYPES_84[vtype][1], shown
    if kind == "matrix":
        vtype, data = 0x06, cf.matrix89_data(values)
    else:
        vtype, data = 0x04, cf.list89_data(values)
    blob = cf.ti89_bytes(vtype, folder.encode("ascii"), name.encode("ascii"), False, data)
    return blob, cf.TYPES_89[vtype][1], "%s\\%s" % (folder, name)


def nspire_program(lists):
    """{name: [numbers]} -> TI-Nspire Python that stores each list in the document it runs in
    (ti_system.store_list). Real numbers only: the Nspire's Python has no TI complex lists."""
    lines = ["# Made by CalcSuite: run it (ctrl+R) to store these lists in this document",
             "from ti_system import *", ""]
    for name, values in lists.items():
        nums = []
        for v in values:
            if isinstance(v, cf.TIComplex):
                raise ValueError("%s: the TI-Nspire's Python can't store complex numbers in a "
                                 "list" % name)
            nums.append(cf.number_text(v if not isinstance(v, cf.Fraction) else cf._decimal(v)))
        body = ",".join(n if re.search(r"[.E]", n) else n + ".0" for n in nums)
        lines.append('store_list("%s",[%s])' % (name, body.replace("E", "e")))
        lines.append('print("%s: %d numbers")' % (name, len(values)))
    lines.append('print("Stored. Use them on any page of this problem.")')
    return "\n".join(lines) + "\n"


def answer_text(value, slug):
    """The answer as clipboard text: a number in full; a list one per line; a matrix as
    tab-separated rows (pastes into Excel's cells); a string as it is"""
    t = lambda v: cf.number_text(v, float_mark=False)
    if isinstance(value, list) and value and isinstance(value[0], list):
        return "\r\n".join("\t".join(t(v) for v in r) for r in value)
    if isinstance(value, list):
        return "\r\n".join(t(v) for v in value)
    return t(value)


# ---- The link (worker threads only) ----

class LinkError(Exception):
    pass


def _why(lines):
    l = [x for x in lines if x.startswith(("OK", "ERR"))]
    l = l[-1] if l else (lines[-1] if lines else "no answer")
    return l[4:] if l.startswith("ERR ") else l


def run(m, line, timeout=120):
    return m.run_batch([(line, None)], timeout=timeout)[0]


def list_vars(m, slug, types=None):
    """The calculator's variables (ls), optionally only these types"""
    code, lines = run(m, "ls")
    if code:
        raise LinkError("couldn't read the list: %s" % _why(lines))
    items = cf.parse_dusb_ls(lines)
    if types is not None:
        items = [i for i in items if i["type"] in types]
    for i in items:
        i["text"] = display_name(slug, i)
    return items


def get_data(m, vtype, folder, name, size, tmp, quiet=False):
    """One variable's data, or None when the calculator says it isn't there (quiet)"""
    path = os.path.join(tmp, "zzdata_%d_%d.bin" % (os.getpid(), threading.get_ident()))
    line = "get %02x %s %s %d %s" % (vtype, cf.to_hex(folder), cf.to_hex(name), size, path)
    code, lines = run(m, line)
    if code:
        if quiet:
            return None
        raise LinkError(_why(lines))
    try:
        with open(path, "rb") as f:
            data = f.read()
        os.remove(path)
    except OSError as e:
        raise LinkError(str(e))
    return data


def send_blob(m, blob, ext, tmp, stem="zzdata"):
    path = os.path.join(tmp, "%s_%d.%s" % (stem, os.getpid(), ext))
    with open(path, "wb") as f:
        f.write(blob)
    code, lines = run(m, "send " + os.path.abspath(path))
    try:
        os.remove(path)
    except OSError:
        pass
    if code:
        raise LinkError(_why(lines))


def read_answer_84(m, tmp):
    for t in ANS_TYPES_84:
        data = get_data(m, t, b"", ANS_NAME_84, 0, tmp, quiet=True)
        if data is not None:
            return cf.value84(t, data)
    raise LinkError("the TI-84 Plus CE didn't hand over Ans over the link (it refused every "
                    "kind of answer). Store it in a variable (Ans→A, or Ans→ʟZZANS for a list) "
                    "and use Data > Open, or the Files panel")


def read_answer_89(m, tmp, wait_s=8.0):
    """Runs main\\zzans (sent first when it isn't there), which stores ans(1) in zzv and its
    text in zzs, and reads them. Returns the value (or the text when it isn't a number)."""
    items = list_vars(m, "ti89")
    for i in items:  # Old results: a stale zzs would look like this run's
        if i["name"] in (b"zzv", b"zzs"):
            run(m, "rm %02x %s %s" % (i["type"], cf.to_hex(i["name"]), cf.to_hex(i["folder"])))
    if not any(i["name"] == b"zzans" and i["type"] in (0x12, 0x13) and i["folder"] == b"main"
               for i in items):
        _name, _t, blob = cf.program_89p(PROG_89, folder="main")
        send_blob(m, blob, "89p", tmp, "zzans")
    run(m, "home")
    code, lines = run(m, "exec prgm %s %s" % (b"main".hex(), b"zzans".hex()))
    if code:
        raise LinkError("the 89 didn't run main\\zzans: %s" % _why(lines))
    t0 = time.time()
    while time.time() - t0 < wait_s:
        time.sleep(0.6)
        found = {i["name"]: i for i in list_vars(m, "ti89") if i["name"] in (b"zzv", b"zzs")}
        if b"zzs" not in found:
            continue
        s = found[b"zzs"]
        text = cf.value89(get_data(m, s["type"], s["folder"], s["name"], s["size"], tmp))
        if not isinstance(text, str) or not text:
            raise LinkError("the 89's last answer isn't something that can be stored (run a "
                            "calculation on its home screen first)")
        v = found.get(b"zzv")
        if v is not None:
            try:
                return cf.value89(get_data(m, v["type"], v["folder"], v["name"], v["size"], tmp))
            except (ValueError, LinkError):
                pass  # An expression with variables, a polar number: its text then
        return text
    raise LinkError("main\\zzans didn't store the answer within %d s (is the 89 busy, or on a "
                    "screen that isn't Home?)" % wait_s)


_ANSWER = {"busy": False, "last": None}  # last: (slug, text, time) of the last copy


def copy_answer(m, widget, say):
    """The Copy answer button: on Tk's thread; the link work runs in a worker, the clipboard is
    set back on Tk's thread. say(text): where the confirmation goes (the tab's status line)."""
    slug, title = m.calc.slug, m.calc.title
    if slug == "nspire":
        say(NSPIRE_NO_ANSWER)
        return
    if _ANSWER["busy"]:
        say("Still reading the answer...")
        return
    if getattr(m, "session", None) is None:
        say("The %s isn't connected: switch it on (its window connects by itself)" % title)
        return
    _ANSWER["busy"] = True
    say("Reading the %s's last answer..." % title)
    tmp = tempfile.gettempdir()

    def work():
        try:
            work_now()
        finally:
            _ANSWER["busy"] = False  # Even when the window has gone and done() never runs

    def work_now():
        try:
            value = read_answer_84(m, tmp) if slug == "ti84" else read_answer_89(m, tmp)
            text = answer_text(value, slug)
            last = _ANSWER["last"]
            if slug == "ti89" and text in ("Done", "\"Done\"") and last and last[0] == slug and \
                    getattr(m, "last_key", 0) < last[2]:
                text = last[1]  # Our own run of zzans made "Done" the newest answer
            on_tk(widget, done, text, None)
        except (LinkError, ValueError, OSError) as e:
            on_tk(widget, done, None, str(e))
        except Exception as e:
            log_error("copying the %s's answer" % title)
            on_tk(widget, done, None, "%s (errors.log has the details)" % e)

    def done(text, err):
        if err:
            say("Couldn't copy the answer: %s" % err)
            return
        try:
            widget.clipboard_clear()
            widget.clipboard_append(text)
        except tk.TclError as e:
            say("Couldn't put it on the clipboard: %s" % e)
            return
        _ANSWER["last"] = (slug, text, time.time())
        shown = text.replace("\r\n", "  ").replace("\t", " ")
        say("Copied %s from the %s" % (shown if len(shown) <= 60 else shown[:57] + "...", title))
    threading.Thread(target=work, daemon=True).start()


# ---- The plot (a Tk Canvas) ----

def nice_ticks(lo, hi, n=5):
    """About n round tick values covering lo..hi"""
    import math
    if hi <= lo:
        lo, hi = lo - 1, hi + 1
    raw = (hi - lo) / max(n, 1)
    mag = 10 ** math.floor(math.log10(raw))
    step = next(s * mag for s in (1, 2, 2.5, 5, 10) if s * mag >= raw)
    first = math.ceil(lo / step) * step
    out, v = [], first
    while v <= hi + step * 1e-9 and len(out) < 50:
        out.append(0.0 if abs(v) < step * 1e-9 else v)
        v += step
    return out


def plot_points(xs, ys):
    """Numbers -> floats for the plot; complex and empty values are left out: (points, left out)"""
    pts, skipped = [], 0
    for x, y in zip(xs, ys):
        if isinstance(x, cf.TIComplex) or isinstance(y, cf.TIComplex) or x is None or y is None:
            skipped += 1
            continue
        pts.append((float(x), float(y)))
    return pts, skipped


class Plot(object):
    def __init__(self, parent, height=210):
        self.c = tk.Canvas(parent, bg="#0b0b0c", height=height, highlightthickness=0, bd=0)
        self.data = None
        self.c.bind("<Configure>", lambda e: self.draw())

    def show(self, pts, title, scatter):
        self.data = (pts, title, scatter)
        self.draw()

    def draw(self):
        c = self.c
        c.delete("all")
        w, h = max(c.winfo_width(), 50), max(c.winfo_height(), 50)
        if not self.data or not self.data[0]:
            c.create_text(w / 2, h / 2, text="Pick a list (or two: x, y) and Plot",
                          fill=th.DIM, font=(th.FONT, 9))
            return
        pts, title, scatter = self.data
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        xt, yt = nice_ticks(min(xs), max(xs)), nice_ticks(min(ys), max(ys))
        x0, x1 = min(xt[0], min(xs)), max(xt[-1], max(xs))
        y0, y1 = min(yt[0], min(ys)), max(yt[-1], max(ys))
        if x1 == x0:
            x0, x1 = x0 - 1, x1 + 1
        if y1 == y0:
            y0, y1 = y0 - 1, y1 + 1
        left, right, top, bottom = 48, 10, 20, 22
        sx = lambda x: left + (x - x0) / (x1 - x0) * (w - left - right)
        sy = lambda y: h - bottom - (y - y0) / (y1 - y0) * (h - top - bottom)
        lab = lambda v: ("%g" % v) if abs(v) < 1e5 else "%.2g" % v
        for x in xt:
            c.create_line(sx(x), top, sx(x), h - bottom, fill=th.LINE)
            c.create_text(sx(x), h - bottom + 4, text=lab(x), anchor="n", fill=th.DIM, font=(th.FONT, 8))
        for y in yt:
            c.create_line(left, sy(y), w - right, sy(y), fill=th.LINE)
            c.create_text(left - 4, sy(y), text=lab(y), anchor="e", fill=th.DIM, font=(th.FONT, 8))
        if x0 <= 0 <= x1:
            c.create_line(sx(0), top, sx(0), h - bottom, fill=th.GREY)
        if y0 <= 0 <= y1:
            c.create_line(left, sy(0), w - right, sy(0), fill=th.GREY)
        if not scatter and len(pts) > 1:
            c.create_line(*[v for p in pts for v in (sx(p[0]), sy(p[1]))], fill=th.ACCENT, width=1.5)
        r = 2.5 if len(pts) < 200 else 1.5
        for x, y in pts:
            c.create_oval(sx(x) - r, sy(y) - r, sx(x) + r, sy(y) + r, fill=th.ACCENT, outline="")
        c.create_text(left, 4, text=title, anchor="nw", fill=th.FG, font=(th.FONT, 9, "bold"))


# ---- The Data section of the side panel ----

def _heading(parent, text):
    tk.Label(parent, text=text.upper(), bg=th.PANEL, fg=th.DIM, font=(th.FONT, 8, "bold"),
             anchor="w").pack(fill="x", pady=(10, 4))


def _note(parent, text, fg=th.DIM, var=None):
    l = tk.Label(parent, text=text, textvariable=var, bg=th.PANEL, fg=fg, anchor="w",
                 justify="left", wraplength=400)
    l.pack(fill="x")
    return l


class DataSection(object):
    def __init__(self, panel, parent):
        self.panel, self.m = panel, panel.m
        self.slug, self.title = self.m.calc.slug, self.m.calc.title
        self.items = []
        self.tmp = tempfile.gettempdir()
        self.frame = tk.Frame(parent, bg=th.PANEL)
        th.style_ttk(self.frame)
        self.status = tk.StringVar(master=self.frame, value="")
        f = self.frame

        _heading(f, "Last answer")
        row = tk.Frame(f, bg=th.PANEL)
        row.pack(fill="x")
        th.button(row, "Copy answer", self.copy_answer).pack(side="left")
        self.answer = tk.StringVar(master=f, value={
            "ti84": "Ans with all 14 digits, onto the PC clipboard",
            "ti89": "Runs main\\zzans on the 89 (sent once) to read ans(1) in full",
            "nspire": "Not possible over the TI-Nspire's link (click for why)"}[self.slug])
        tk.Label(row, textvariable=self.answer, bg=th.PANEL, fg=th.DIM, anchor="w", justify="left",
                 wraplength=300).pack(side="left", fill="x", expand=True, padx=(8, 0))

        # The plot stays at the bottom; above it the list, or the grid editor in its place
        plot_box = tk.Frame(f, bg=th.PANEL)
        plot_box.pack(side="bottom", fill="x")
        lp = self.list_page = tk.Frame(f, bg=th.PANEL)
        lp.pack(fill="both", expand=True)
        self.editor = None
        _heading(lp, "Lists and matrices")
        if self.slug == "nspire":
            _note(lp, NSPIRE_NO_READ)
            self.tree = None
        else:
            mid = tk.Frame(lp, bg=th.BG)
            mid.pack(fill="both", expand=True)
            tree = self.tree = ttk.Treeview(mid, columns=("kind", "size"), style="Calc.Treeview",
                                            selectmode="extended", height=7)
            tree.heading("#0", text="Name", anchor="w")
            tree.column("#0", width=150, anchor="w")
            tree.heading("kind", text="Kind", anchor="w")
            tree.column("kind", width=110, anchor="w")
            tree.heading("size", text="Size", anchor="e")
            tree.column("size", width=60, anchor="e")
            sb = ttk.Scrollbar(mid, orient="vertical", command=tree.yview,
                               style="Calc.Vertical.TScrollbar")
            tree.configure(yscrollcommand=sb.set)
            tree.pack(side="left", fill="both", expand=True)
            sb.pack(side="right", fill="y")
            tree.bind("<Double-Button-1>", lambda e: self.open_selected())
            tree.bind("<Return>", lambda e: self.open_selected())
        bar = tk.Frame(lp, bg=th.PANEL)
        bar.pack(fill="x", pady=(6, 0))
        if self.tree is not None:
            for text, cmd in (("Refresh", self.refresh), ("Open", self.open_selected),
                              ("Plot", self.plot_selected)):
                th.button(bar, text, cmd).pack(side="left", padx=(0, 6))
        bar2 = tk.Frame(lp, bg=th.PANEL)
        bar2.pack(fill="x", pady=(6, 0))
        th.button(bar2, "New list", lambda: self.new("list")).pack(side="left")
        if self.slug != "nspire":
            th.button(bar2, "New matrix", lambda: self.new("matrix")).pack(side="left", padx=(6, 0))
        th.button(bar2, "Import CSV...", self.import_csv).pack(side="left", padx=(6, 0))
        _note(lp, "", var=self.status)

        _heading(plot_box, "Plot")
        self.plot = Plot(plot_box, height=180)
        self.plot.c.pack(fill="x")
        self.listed = False

    def open_editor(self, grid, name):
        """The grid editor in the section, in the list's place (Close brings the list back)"""
        self.close_editor()
        self.list_page.pack_forget()
        self.editor = GridEditor(self.frame, self, grid, name, on_close=self.close_editor)
        self.editor.pack(fill="both", expand=True)

    def close_editor(self):
        if self.editor is not None:
            try:
                self.editor.destroy()
            except tk.TclError:
                pass
            self.editor = None
            self.list_page.pack(fill="both", expand=True)

    def shown(self):
        if not self.listed and self.tree is not None:
            self.listed = True
            self.refresh()

    def say(self, text):
        self.status.set(text)

    def work(self, fn, ok, what):
        """fn() in a worker; ok(result) or the error on Tk's thread"""
        def run_it():
            try:
                res = fn()
                on_tk(self.frame, ok, res)
            except (LinkError, ValueError, OSError) as e:
                on_tk(self.frame, self.say, "%s: %s" % (what, e))
            except Exception as e:
                log_error(what.lower())
                on_tk(self.frame, self.say, "%s: %s (errors.log has the details)" % (what, e))
        threading.Thread(target=run_it, daemon=True).start()

    def copy_answer(self):
        copy_answer(self.m, self.frame, lambda t: on_tk(self.frame, self.answer_said, t))

    def answer_said(self, text):
        self.answer.set(text)
        try:
            self.m.set_status(text)
        except Exception:
            pass

    # ---- The list on the calculator ----
    def refresh(self):
        if self.tree is None:
            return
        if getattr(self.m, "session", None) is None:
            self.say("Waiting for the %s to connect (Refresh when it is)" % self.title)
        else:
            self.say("Reading the list...")
        types = LIST_TYPES[self.slug] + MATRIX_TYPES[self.slug]
        self.work(lambda: list_vars(self.m, self.slug, types), self.listed_items, "Couldn't read the list")

    def listed_items(self, items):
        items.sort(key=lambda i: (i["type"] in MATRIX_TYPES[self.slug], i["text"].lower()))
        self.items = items
        self.tree.delete(*self.tree.get_children())
        types = cf.TYPES_89 if self.slug == "ti89" else cf.TYPES_84
        for k, i in enumerate(items):
            self.tree.insert("", "end", iid=str(k), text=i["text"],
                             values=(types.get(i["type"], ("?",))[0], cf.human_size(i["size"])))
        self.say("%d list(s) and matrices. Double-click one to open it." % len(items)
                 if items else "No lists or matrices on the %s yet: New list makes one" % self.title)

    def selected(self):
        return [self.items[int(i)] for i in self.tree.selection()] if self.tree else []

    def read_item(self, item):
        data = get_data(self.m, item["type"], item["folder"], item["name"], item["size"], self.tmp)
        return read_value(self.slug, item["type"], data)

    def open_selected(self):
        sel = self.selected()
        if len(sel) != 1:
            self.say("Pick one list or matrix")
            return
        item = sel[0]
        self.say("Reading %s..." % item["text"])

        def ok(value):
            name = item["text"].replace("ʟ", "") if self.slug == "ti84" else item["text"]
            try:
                g = grid_from_value(self.slug, value, name)
            except ValueError as e:
                self.say("%s: %s" % (item["text"], e))
                return
            self.say("Opened %s" % item["text"])
            self.open_editor(g, name)
        self.work(lambda: self.read_item(item), ok, "Couldn't read %s" % item["text"])

    def plot_selected(self):
        sel = self.selected()
        if not 1 <= len(sel) <= 2:
            self.say("Pick one list (y against its index) or two (x, then y: Ctrl+click)")
            return

        def fetch():
            return [self.read_item(i) for i in sel]

        def ok(values):
            if any(isinstance(v, list) and v and isinstance(v[0], list) for v in values):
                if len(values) == 1 and values[0] and len(values[0][0]) >= 2:  # A matrix: x, y columns
                    rows = values[0]
                    self.show_plot([r[0] for r in rows], [r[1] for r in rows],
                                   "%s: column 1, column 2" % sel[0]["text"], True)
                    return
                self.say("Plot a list, or a matrix of two columns")
                return
            if len(values) == 1:
                self.show_plot(list(range(1, len(values[0]) + 1)), values[0], sel[0]["text"], False)
            else:
                n = min(len(values[0]), len(values[1]))
                self.show_plot(values[0][:n], values[1][:n],
                               "%s against %s" % (sel[1]["text"], sel[0]["text"]), True)
        self.say("Reading...")
        self.work(fetch, ok, "Couldn't plot")

    def show_plot(self, xs, ys, title, scatter):
        pts, skipped = plot_points(xs, ys)
        self.plot.show(pts, title, scatter)
        self.say("%d point(s)%s" % (len(pts), ", %d complex or empty left out" % skipped if skipped else ""))

    # ---- New, import ----
    def new(self, kind):
        if kind == "matrix":
            g = Grid([["", ""], ["", ""]], kind="matrix")
            name = "[J]" if self.slug == "ti84" else "zzm"
        else:
            name = {"ti84": "ZZX", "ti89": "zzx", "nspire": "zzx"}[self.slug]
            g = Grid([[""] for _ in range(5)], [name], "list")
        self.open_editor(g, name)

    def import_csv(self):
        p = filedialog.askopenfilename(parent=self.frame, title="Import a CSV file",
                                       filetypes=[("CSV and text", "*.csv *.txt *.tsv"), ("All files", "*.*")])
        if not p:
            return
        try:
            text = read_text_file(p)
        except OSError as e:
            self.say("Couldn't read %s: %s" % (os.path.basename(p), e))
            return
        g = grid_from_csv(text)
        if self.slug == "ti89":
            g.headers = [h.lower() for h in g.headers]
        self.open_editor(g, g.headers[0] if g.headers else "")
        self.say("Imported %s: %d row(s), %d column(s)" % (os.path.basename(p), g.nrows, g.ncols))


def read_text_file(path):
    with open(path, "rb") as f:
        raw = f.read(20 * 1024 * 1024)
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


# ---- The grid editor: a Frame, inside the Data section (or any parent: a tab, a window) ----

def open_window(section, grid, name):
    """The editor in a window of its own (optional: the Data section shows it in place)"""
    w = tk.Toplevel(section.frame)
    w.title("%s - %s" % (name or "New", section.title))
    w.configure(bg=th.BG)
    w.geometry("620x560")
    th.dark_title_bar_when_shown(w)
    ed = GridEditor(w, section, grid, name, on_close=w.destroy, bg=th.BG)
    ed.pack(fill="both", expand=True, padx=12, pady=12)
    return ed


class GridEditor(tk.Frame):
    """A spreadsheet-style grid: edit cells (double-click, Enter, F2 or just type), add and
    remove rows and columns, copy and paste with Excel, CSV in and out, plot, send."""

    def __init__(self, parent, section, grid, name, on_close=None, bg=th.PANEL):
        tk.Frame.__init__(self, parent, bg=bg)
        self.s, self.g = section, grid
        self.slug, self.title = section.slug, section.title
        self.on_close = on_close
        self.win = self  # Clipboard, after() and dialogs' parent
        th.style_ttk(self)
        self.cur = (0, 0)
        self.edit = None
        w = self

        head = tk.Frame(w, bg=bg)
        head.pack(fill="x", pady=(0, 4))
        self.caption = tk.Label(head, text=(name or "New") + "  (changes reach the calculator with Send)",
                                bg=bg, fg=th.FG, font=(th.FONT, 10, "bold"), anchor="w")
        self.caption.pack(side="left", fill="x", expand=True)
        if on_close is not None:
            th.button(head, "Close", on_close).pack(side="right")
        top = tk.Frame(w, bg=bg)
        top.pack(fill="x", pady=(0, 4))
        self.kind = tk.StringVar(master=w, value=grid.kind)
        if self.slug != "nspire":
            for text, val in (("Lists (one per column)", "list"), ("One matrix", "matrix")):
                tk.Radiobutton(top, text=text, value=val, variable=self.kind, command=self.kind_changed,
                               bg=bg, fg=th.FG, selectcolor=th.PANEL2, activebackground=bg,
                               activeforeground="#ffffff", highlightthickness=0, bd=0).pack(side="left", padx=(0, 10))
        self.cell = tk.StringVar(master=w, value="")
        tk.Label(w, textvariable=self.cell, bg=bg, fg=th.DIM, anchor="w").pack(fill="x")

        mid = tk.Frame(w, bg=th.BG)
        mid.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(mid, style="Calc.Treeview", show="headings", selectmode="extended",
                                 height=8)
        ys = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview, style="Calc.Vertical.TScrollbar")
        xs = ttk.Scrollbar(mid, orient="horizontal", command=self.tree.xview,
                           style="Calc.Horizontal.TScrollbar")
        self.tree.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        ys.grid(row=0, column=1, sticky="ns")
        xs.grid(row=1, column=0, sticky="ew")
        mid.rowconfigure(0, weight=1)
        mid.columnconfigure(0, weight=1)
        t = self.tree
        t.bind("<Button-1>", self.click, add="+")
        t.bind("<Double-Button-1>", self.double)
        t.bind("<Return>", lambda e: self.start_edit())
        t.bind("<F2>", lambda e: self.start_edit())
        t.bind("<Key>", self.key)
        t.bind("<Control-c>", lambda e: self.copy_sel())
        t.bind("<Control-v>", lambda e: self.paste())
        t.bind("<Delete>", lambda e: self.clear_cell())
        for k, (dr, dc) in {"<Left>": (0, -1), "<Right>": (0, 1), "<Up>": (-1, 0),
                            "<Down>": (1, 0), "<Tab>": (0, 1)}.items():
            t.bind(k, lambda e, dr=dr, dc=dc: self.move(dr, dc))

        bar = tk.Frame(w, bg=bg)
        bar.pack(fill="x", pady=(6, 0))
        for text, cmd in (("+ Row", self.add_row), ("- Row", self.del_row), ("+ Column", self.add_col),
                          ("- Column", self.del_col), ("Plot", self.plot)):
            th.button(bar, text, cmd).pack(side="left", padx=(0, 6))
        bar2 = tk.Frame(w, bg=bg)
        bar2.pack(fill="x", pady=(6, 0))
        for text, cmd in (("Copy all", self.copy_all), ("Paste", self.paste), ("Import CSV...", self.import_csv),
                          ("Save CSV...", self.save_csv)):
            th.button(bar2, text, cmd).pack(side="left", padx=(0, 6))

        entry = dict(bg="#0b0b0c", fg=th.FG, insertbackground=th.FG, relief="flat", width=12)
        names = tk.Frame(w, bg=bg)
        names.pack(fill="x", pady=(8, 0))
        # A list's name is its column's title: edited here for the column the cursor is in
        self.col_label = tk.Label(names, text="This column's list:", bg=bg, fg=th.FG)
        self.col_name = tk.StringVar(master=w, value="")
        self.col_entry = tk.Entry(names, textvariable=self.col_name, **entry)
        self.col_entry.bind("<Return>", lambda e: self.rename_col())
        self.col_entry.bind("<FocusOut>", lambda e: self.rename_col())
        # The matrix's name, or on the Nspire the program (document) that carries the lists
        self.name_label = tk.Label(names, text="", bg=bg, fg=th.FG)
        self.name = tk.StringVar(master=w, value=name if grid.kind == "matrix" else
                                 ("zzdata" if self.slug == "nspire" else ""))
        self.name_entry = tk.Entry(names, textvariable=self.name, **entry)
        send = tk.Frame(w, bg=bg)
        send.pack(fill="x", pady=(8, 0))
        th.button(send, "Send to the %s" % self.title, self.send).pack(side="left")
        self.status = tk.StringVar(master=w, value="Double-click a cell (or just type) to edit it. "
                                   "Ctrl+C / Ctrl+V copy and paste with Excel.")
        tk.Label(w, textvariable=self.status, bg=bg, fg=th.DIM, anchor="w", justify="left",
                 wraplength=400).pack(fill="x", pady=(8, 0))
        self.kind_changed(rebuild=False)
        self.rebuild()
        w.after(50, lambda: self.alive() and self.tree.focus_set())

    def alive(self):
        try:
            return bool(self.winfo_exists())
        except tk.TclError:
            return False

    # ---- Showing the grid ----
    def rebuild(self):
        t, g = self.tree, self.g
        g.normalize()
        cols = ["#"] + ["c%d" % k for k in range(g.ncols)]
        t.configure(columns=cols)
        t.heading("#", text="", anchor="e")
        t.column("#", width=42, minwidth=36, anchor="e", stretch=False)
        for k in range(g.ncols):
            head = g.headers[k] if g.kind == "list" else "%d" % (k + 1)
            t.heading("c%d" % k, text=head, anchor="w", command=lambda k=k: self.rename_col(k))
            t.column("c%d" % k, width=120, minwidth=60, anchor="w", stretch=True)
        t.delete(*t.get_children())
        for r in range(g.nrows):
            t.insert("", "end", iid=str(r), values=[r + 1] + g.rows[r])
        self.show_cur()

    def refresh_row(self, r):
        if self.tree.exists(str(r)):
            self.tree.item(str(r), values=[r + 1] + self.g.rows[r])
        else:
            self.rebuild()

    def show_cur(self):
        r, c = self.cur
        r, c = max(0, min(r, self.g.nrows - 1)), max(0, min(c, self.g.ncols - 1))
        self.cur = (r, c)
        if self.tree.exists(str(r)):
            self.tree.selection_set(str(r))
            self.tree.focus(str(r))
            self.tree.see(str(r))
        col = self.g.headers[c] if self.g.kind == "list" else "column %d" % (c + 1)
        self.cell.set("Row %d, %s: %s" % (r + 1, col, self.g.get(r, c) or "(empty)"))
        if self.g.kind == "list" and self.focus_get() is not self.col_entry:
            self.col_name.set(self.g.headers[c])

    def kind_changed(self, rebuild=True):
        self.g.kind = self.kind.get()
        for wdg in (self.col_label, self.col_entry, self.name_label, self.name_entry):
            wdg.pack_forget()
        if self.g.kind == "list":
            self.col_label.pack(side="left")
            self.col_entry.pack(side="left", padx=(6, 12))
        if self.g.kind == "matrix" or self.slug == "nspire":
            self.name_label.configure(text="Matrix name:" if self.g.kind == "matrix" else "Program:")
            self.name_label.pack(side="left")
            self.name_entry.pack(side="left", padx=6)
            if not self.name.get():
                self.name.set("[J]" if self.slug == "ti84" else "zzm")
        if rebuild:
            self.rebuild()

    # ---- Cells ----
    def cell_at(self, ev):
        row, col = self.tree.identify_row(ev.y), self.tree.identify_column(ev.x)
        if not row or not col or col == "#1":
            return None
        return int(row), int(col[1:]) - 2

    def click(self, ev):
        self.commit()
        if self.tree.identify_region(ev.x, ev.y) == "heading":
            return
        at = self.cell_at(ev)
        if at:
            self.cur = at
            self.win.after(1, self.show_cur)

    def double(self, ev):
        if self.tree.identify_region(ev.x, ev.y) == "heading":
            return "break"
        at = self.cell_at(ev)
        if at:
            self.cur = at
            self.start_edit()
        return "break"

    def key(self, ev):
        if ev.char and ev.char.isprintable() and not (ev.state & 0x4):
            self.start_edit(ev.char)
            return "break"

    def move(self, dr, dc):
        self.commit()
        r, c = self.cur
        r, c = r + dr, c + dc
        if r >= self.g.nrows:
            self.g.insert_row()
            self.rebuild()
        if c >= self.g.ncols:
            c = self.g.ncols - 1
        self.cur = (max(0, r), max(0, c))
        self.show_cur()
        return "break"

    def start_edit(self, first=None):
        self.commit()
        r, c = self.cur
        self.tree.see(str(r))
        self.tree.update_idletasks()
        box = self.tree.bbox(str(r), "c%d" % c)
        if not box:
            return "break"
        x, y, w, h = box
        e = tk.Entry(self.tree, bg="#1b1c20", fg=th.FG, insertbackground=th.FG, relief="flat",
                     font=(th.FONT, 10))
        e.place(x=x, y=y, width=w, height=h)
        e.insert(0, self.g.get(r, c) if first is None else first)
        e.focus_set()
        if first is None:
            e.select_range(0, "end")
        e.bind("<Return>", lambda ev: self.move(1, 0) or "break")
        e.bind("<Tab>", lambda ev: self.move(0, 1) or "break")
        e.bind("<Escape>", lambda ev: self.cancel_edit())
        e.bind("<FocusOut>", lambda ev: self.commit())
        self.edit = (e, r, c)
        return "break"

    def commit(self):
        if not self.edit:
            return
        e, r, c = self.edit
        self.edit = None
        try:
            text = e.get()
            e.destroy()
        except tk.TclError:
            return
        self.g.set(r, c, text)
        self.check_cell(r, c)
        self.refresh_row(r)
        self.tree.focus_set()

    def cancel_edit(self):
        if self.edit:
            e = self.edit[0]
            self.edit = None
            e.destroy()
            self.tree.focus_set()
        return "break"

    def check_cell(self, r, c):
        try:
            cf.parse_number(self.g.get(r, c))
            self.status.set("")
        except ValueError as ex:
            self.status.set("Row %d: %s (numbers like 2.5, -1E-5, 1/3 or 3+2i)" % (r + 1, ex))

    def clear_cell(self):
        r, c = self.cur
        self.g.set(r, c, "")
        self.refresh_row(r)
        self.show_cur()

    def rename_col(self, k=None):
        """The column's title (its list's name) from the entry, or a click on the title"""
        if self.g.kind != "list":
            return
        if k is not None:  # A click on a column's title: the cursor goes there, edit its name
            self.cur = (self.cur[0], k)
            self.show_cur()
            self.col_entry.focus_set()
            self.col_entry.select_range(0, "end")
            return
        new = self.col_name.get().strip()
        c = self.cur[1]
        if new and c < self.g.ncols and new != self.g.headers[c]:
            self.g.headers[c] = new
            self.rebuild()

    # ---- Rows and columns ----
    def add_row(self):
        self.commit()
        self.g.insert_row(self.cur[0] + 1)
        self.cur = (self.cur[0] + 1, self.cur[1])
        self.rebuild()

    def del_row(self):
        self.commit()
        rows = sorted(int(i) for i in self.tree.selection()) or [self.cur[0]]
        self.g.delete_rows(rows)
        self.rebuild()

    def add_col(self):
        self.commit()
        self.g.insert_col(self.cur[1] + 1)
        self.cur = (self.cur[0], self.cur[1] + 1)
        self.rebuild()

    def del_col(self):
        self.commit()
        self.g.delete_col(self.cur[1])
        self.rebuild()

    # ---- Clipboard, CSV ----
    def clip(self, text, what):
        self.win.clipboard_clear()
        self.win.clipboard_append(text)
        self.status.set("Copied %s: paste it into Excel or any spreadsheet" % what)

    def copy_all(self):
        self.commit()
        self.clip(self.g.to_tsv(header=True), "the whole grid")

    def copy_sel(self):
        self.commit()
        rows = sorted(int(i) for i in self.tree.selection())
        if len(rows) <= 1:
            r, c = self.cur
            self.clip(self.g.get(r, c), "the cell")
        else:
            self.clip(self.g.to_tsv(rows), "%d rows" % len(rows))
        return "break"

    def paste(self):
        self.commit()
        try:
            text = self.win.clipboard_get()
        except tk.TclError:
            self.status.set("The clipboard has no text")
            return "break"
        r, c = self.cur
        n = len(parse_table(text))
        self.g.paste(text, r, c)
        self.rebuild()
        self.status.set("Pasted %d row(s) at row %d" % (n, r + 1))
        return "break"

    def import_csv(self):
        p = filedialog.askopenfilename(parent=self.win, title="Import a CSV file",
                                       filetypes=[("CSV and text", "*.csv *.txt *.tsv"), ("All files", "*.*")])
        if not p:
            return
        try:
            g = grid_from_csv(read_text_file(p), self.g.kind)
        except OSError as e:
            self.status.set("Couldn't read it: %s" % e)
            return
        self.g = g
        self.cur = (0, 0)
        self.rebuild()
        self.status.set("Imported %s" % os.path.basename(p))

    def save_csv(self):
        self.commit()
        import paths
        p = filedialog.asksaveasfilename(parent=self.win, defaultextension=".csv",
                                         initialdir=paths.user_path("from-calc"),
                                         initialfile=cf.safe_file_name(self.name.get() or
                                                                       self.g.headers[0]) + ".csv",
                                         filetypes=[("CSV", "*.csv"), ("All files", "*.*")])
        if not p:
            return
        try:
            with open(p, "w", encoding="utf-8-sig", newline="") as f:
                f.write(self.g.to_csv())
            self.status.set("Saved %s" % p)
        except OSError as e:
            self.status.set("Couldn't save: %s" % e)

    # ---- Plot, send ----
    def plot(self):
        self.commit()
        g = self.g
        try:
            if g.ncols == 1:
                ys = g.column_values(0)
                self.s.show_plot(list(range(1, len(ys) + 1)), ys, g.headers[0], False)
            else:
                xs, ys = g.column_values(0), g.column_values(1)
                n = min(len(xs), len(ys))
                title = "%s against %s" % (g.headers[1], g.headers[0]) if g.kind == "list" else \
                    "column 2 against column 1"
                self.s.show_plot(xs[:n], ys[:n], title, True)
        except ValueError as e:
            self.status.set("Can't plot: %s" % e)
            return
        self.status.set("Plotted in the Data panel")

    def sends(self):
        """[(TI file or None, extension, shown name)]; the Nspire: one program"""
        g = self.g
        if self.slug == "nspire":
            lists = {}
            for k in range(g.ncols):
                vals = g.column_values(k)
                if vals:
                    lists[calc_name("nspire", "list", g.headers[k])[1]] = vals
            if not lists:
                raise ValueError("the grid is empty")
            return lists
        if g.kind == "matrix":
            return [var_file(self.slug, "matrix", g.matrix_values(), self.name.get())]
        out = []
        for k in range(g.ncols):
            vals = g.column_values(k)
            if vals:
                out.append(var_file(self.slug, "list", vals, g.headers[k]))
        if not out:
            raise ValueError("the grid is empty")
        return out

    def send(self):
        self.commit()
        try:
            files = self.sends()
        except ValueError as e:
            self.status.set("Not sent: %s" % e)
            return
        m = self.s.m
        if getattr(m, "session", None) is None:
            self.status.set("The %s isn't connected" % self.title)
            return
        if self.slug == "nspire":
            return self.send_nspire(files)
        there = {i["text"].lower() for i in self.s.items}
        same = [n for _b, _e, n in files if n.lower() in there]
        if same and not messagebox.askyesno("Replace?", "%s %s already on the %s. Replace?" % (
                ", ".join(same), "is" if len(same) == 1 else "are", self.title), parent=self.win):
            return
        self.status.set("Sending %s..." % ", ".join(n for _b, _e, n in files))

        def work():
            for blob, ext, _n in files:
                send_blob(m, blob, ext, self.s.tmp)
            return [n for _b, _e, n in files]

        def ok(names):
            if self.alive():
                self.status.set("Sent %s to the %s" % (", ".join(names), self.title))
                self.caption.configure(text=", ".join(names))
            self.s.refresh()
        self.work(work, ok)

    def send_nspire(self, lists):
        doc = self.name.get().strip().lower()
        if not re.match(r"^[a-z][a-z0-9_]{0,15}$", doc):
            self.status.set("A name of lower case letters, digits or _, a letter first")
            return
        import tns_writer
        try:
            src = nspire_program(lists).encode("ascii")
        except (ValueError, UnicodeEncodeError) as e:
            self.status.set("Not sent: %s" % e)
            return
        m, tmp = self.s.m, self.s.tmp
        self.status.set("Sending %s.tns..." % doc)

        def work():
            path = os.path.join(tmp, "%s_%d.tns" % (doc, os.getpid()))
            with open(path, "wb") as f:
                f.write(tns_writer.python_tns(doc + ".py", src))
            code, lines = run(m, "put %s|/%s.tns" % (os.path.abspath(path), doc))
            os.remove(path)
            if code:
                raise LinkError(_why(lines))
            return doc

        def ok(d):
            if self.alive():
                self.status.set("Sent %s.tns to My Documents: open it on the handheld and run it "
                                "(ctrl+R) to store %s in that document" % (d, ", ".join(lists)))
        self.work(work, ok)

    def work(self, fn, ok):
        def run_it():
            try:
                res = fn()
                on_tk(self.win, ok, res)
            except (LinkError, ValueError, OSError) as e:
                on_tk(self.win, self.say, "Not sent: %s" % e)
            except Exception as e:
                log_error("sending data to the %s" % self.title)
                on_tk(self.win, self.say, "Not sent: %s (errors.log has the details)" % e)
        threading.Thread(target=run_it, daemon=True).start()

    def say(self, text):
        if self.alive():
            self.status.set(text)
