"""Calc Mirror: TI calculators' screens in windows, with your keyboard as their keypad.

    python -I tools/mirror.py            (or double-click "Nspire Mirror.bat")

One window opens for each calculator that is plugged in (and for one plugged in later):
a TI-Nspire CX II, a TI-84 Plus CE, a TI-89 Titanium. Each window has:

- the live picture (the Nspire about 10 frames a second, the 84 Plus CE about 1);
- the keyboard: what you type goes to that calculator (see the key list in its status line's
  tooltip row, or below);
- Screenshot (a PNG in captures/), Record (a GIF, and an MP4 when ffmpeg is installed),
  Send program (Nspire: a .py or .tns; 84 and 89: TI-Basic text or a TI file, send_ti.py),
  Files... (the calculator manager, calc_manager.py:
  what's on it, downloads, uploads, About this calculator with the OS update check),
  Reconnect, and Keyboard on/off.

TI-Nspire keys: letters, digits, symbols, Enter, Esc, Tab, Backspace, arrows; Ctrl+letter;
F1 Home, F2 Menu, F3 Doc, F4 Catalog, F5 Var. Mouse: wheel = up/down (Shift: left/right),
click = centre click, double click = Enter, right click = context menu, middle click = Menu;
a click on the X closes the document, on the page arrow/tabs changes page (the pointer itself
can't be moved from the PC).

TI-84 Plus CE keys: letters (typed lower case is the calculator's capital), digits, symbols,
Enter, arrows, Backspace (left + DEL), Delete = DEL, Insert = INS, Esc = CLEAR;
F1 Y=, F2 WINDOW, F3 ZOOM, F4 TRACE, F5 GRAPH, F6 MODE, F7 MATH, F8 APPS, F9 PRGM, F10 VARS,
F11 STAT, F12 QUIT. Mouse wheel = up/down.

TI-89 Titanium keys: letters (lower case as typed), digits,
symbols, Enter, Esc, arrows, Backspace, Delete = DEL, Insert = INS, Home = HOME; F1-F8 are
its F1-F8, F9 APPS, F10 MODE, F11 CATALOG, F12 CLEAR.

Every window: Ctrl+V types the PC clipboard's text into the calculator (new lines are Enter),
Ctrl+C copies the calculator's screen to the PC clipboard as a picture. On the Nspire,
Ctrl+Shift+C / Ctrl+Shift+V are the handheld's own copy and paste.
"""

import os
import sys
import tempfile
import threading
import time
import tkinter as tk
from tkinter import filedialog

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "nspire_cli"))
sys.path.insert(0, os.path.join(HERE, "ti84_cli"))
import nspire_link  # noqa: E402
import nspire_keys  # noqa: E402
import ti84_keys  # noqa: E402
import ti89_keys  # noqa: E402
import recorder  # noqa: E402
import calc_manager  # noqa: E402
import send_ti  # noqa: E402

import check_nspire  # noqa: E402
import py2tns  # noqa: E402

if getattr(sys, "frozen", False):
    # The packaged app: its tools are unpacked beside this file; what it makes goes to the
    # user's Documents
    KIT = os.path.join(os.path.expanduser("~"), "Documents", "Nspire Mirror")
    os.makedirs(os.path.join(KIT, "programs"), exist_ok=True)
    py2tns.BUILD = os.path.join(KIT, "build")
else:
    KIT = os.path.dirname(HERE)
SCALE = 2
PASTE_MAX = 4000  # Characters one paste may type
KEEPALIVE_S = 60  # A do-nothing key this often while a window is open and idle (0: never)


def set_clipboard_image(w, h, rgb, scale):
    """Puts an RGB picture on the Windows clipboard (CF_DIB), enlarged by `scale`"""
    import ctypes
    import struct
    sw, sh = w * scale, h * scale
    stride = (sw * 3 + 3) & ~3
    rows = []
    for y in range(h - 1, -1, -1):  # A DIB stores the bottom row first
        line = bytearray()
        for x in range(w):
            r, g, b = rgb[(y * w + x) * 3:(y * w + x) * 3 + 3]
            line += bytes((b, g, r)) * scale
        line += b"\x00" * (stride - len(line))
        rows.extend([bytes(line)] * scale)
    data = struct.pack("<IiiHHIIiiII", 40, sw, sh, 1, 24, 0, stride * sh, 2835, 2835, 0, 0)
    data += b"".join(rows)
    k32, u32 = ctypes.windll.kernel32, ctypes.windll.user32
    k32.GlobalAlloc.restype = ctypes.c_void_p
    k32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    k32.GlobalLock.restype = ctypes.c_void_p
    k32.GlobalLock.argtypes = [ctypes.c_void_p]
    k32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    u32.SetClipboardData.restype = ctypes.c_void_p
    u32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
    u32.OpenClipboard.argtypes = [ctypes.c_void_p]
    handle = k32.GlobalAlloc(0x0002, len(data))  # GMEM_MOVEABLE
    ptr = k32.GlobalLock(handle)
    ctypes.memmove(ptr, data, len(data))
    k32.GlobalUnlock(handle)
    if not u32.OpenClipboard(None):
        raise OSError("the clipboard is busy")
    try:
        u32.EmptyClipboard()
        if not u32.SetClipboardData(8, handle):  # CF_DIB; Windows owns it from here
            raise OSError("the clipboard refused the picture")
    finally:
        u32.CloseClipboard()


class Nspire(object):
    """The TI-Nspire CX II: what differs from the other calculators"""
    pid = 0xE022
    title = "TI-Nspire"
    slug = "nspire"
    cli = nspire_link.CLI
    can_send = True
    key_fmt = "%06x"
    shot_holdoff = 0.15  # Seconds after a key before the next picture (keys go first)
    keepalive_key = "000000"  # A key code that does nothing (tested: the screen stays the same)
    tk_keys = {
        "Return": ["enter"], "KP_Enter": ["enter"], "Escape": ["esc"], "Tab": ["tab"],
        "BackSpace": ["backspace"], "Left": ["left"], "Right": ["right"], "Up": ["up"],
        "Down": ["down"], "F1": ["home"], "F2": ["menu"], "F3": ["doc"], "F4": ["catalog"],
        "F5": ["var"],
    }
    wheel = ("up", "down", "left", "right")
    double_click, right_click, middle_click = "enter", "ctrl+menu", "menu"

    @staticmethod
    def code_for(name):
        return nspire_keys.code_for(name)

    @staticmethod
    def click(x, y):
        """The pointer can't be placed: known spots send the key that does the same job"""
        if y < 24 and x >= 292:
            return "ctrl+w"      # The X: close the document
        if y < 24 and x < 14:
            return "ctrl+left"   # The left page arrow
        if y < 24 and x < 100:
            return "ctrl+right"  # The page tabs and the right arrow: next page
        return "click"


class Ti84(object):
    """The TI-84 Plus CE family"""
    pid = 0xE008
    title = "TI-84 Plus CE"
    slug = "ti84"
    cli = nspire_link.CLI_84
    can_send = True  # TI-Basic text (tokenized on the PC) or a TI file (send_ti.py)
    key_fmt = "%x"
    shot_holdoff = 0.6  # A picture takes ~1.4 s and can't be cut short: never start one mid-typing
    keepalive_key = "0"  # Key code 0 does nothing (tested: only the blinking cursor differs)
    tk_keys = {
        "Return": ["enter"], "KP_Enter": ["enter"], "Escape": ["clear"],
        "BackSpace": ["left", "del"], "Delete": ["del"], "Insert": ["ins"],
        "Left": ["left"], "Right": ["right"], "Up": ["up"], "Down": ["down"],
        "F1": ["y="], "F2": ["window"], "F3": ["zoom"], "F4": ["trace"], "F5": ["graph"],
        "F6": ["mode"], "F7": ["math"], "F8": ["apps"], "F9": ["prgm"], "F10": ["vars"],
        "F11": ["stat"], "F12": ["quit"],
    }
    wheel = ("up", "down", "left", "right")
    double_click, right_click, middle_click = "enter", None, None

    @staticmethod
    def code_for(name):
        return ti84_keys.code_for(name)

    @staticmethod
    def click(x, y):
        return None


class Ti89(object):
    """The TI-89 Titanium"""
    pid = 0xE004
    title = "TI-89 Titanium"
    slug = "ti89"
    cli = nspire_link.CLI_89
    can_send = True  # TI-Basic text (the 89 tokenizes it when it first runs) or a TI file
    key_fmt = "%x"
    shot_holdoff = 0.6
    zoom = 2  # Its 160 x 100 screen: x 2 here, x SCALE in the window = x 4
    # No keepalive_key: key code 0 makes the 89 stop answering the link (tested twice, OS 3.10),
    # and the window's screenshots alone kept it on for 7 minutes (its auto power-off is
    # "several minutes" of no use, TI's guidebook p. 5)
    tk_keys = {
        "Return": ["enter"], "KP_Enter": ["enter"], "Escape": ["esc"],
        "BackSpace": ["backspace"], "Delete": ["del"], "Insert": ["ins"],
        "Left": ["left"], "Right": ["right"], "Up": ["up"], "Down": ["down"], "Home": ["home"],
        "F1": ["f1"], "F2": ["f2"], "F3": ["f3"], "F4": ["f4"], "F5": ["f5"], "F6": ["f6"],
        "F7": ["f7"], "F8": ["f8"], "F9": ["apps"], "F10": ["mode"], "F11": ["catalog"],
        "F12": ["clear"],
    }
    wheel = ("up", "down", "left", "right")
    double_click, right_click, middle_click = "enter", None, None

    @staticmethod
    def code_for(name):
        return ti89_keys.code_for(name)

    @staticmethod
    def click(x, y):
        return None


CALCS = (Nspire, Ti84, Ti89)


def prepare_for_nspire(path):
    """A .py checked and turned into a .tns (as tools/flash.py does), a .tns as it is.
    Returns (the file to send, None) or (None, why not)."""
    if not path.lower().endswith(".py"):
        return path, None
    errors = [f for f in check_nspire.check_file(path, set()) if f.level == "ERROR"]
    if errors:
        f = errors[0]
        more = " (+%d more)" % (len(errors) - 1) if len(errors) > 1 else ""
        return None, "Not sent, line %d: %s%s. Fix: %s" % (f.line, f.message, more, f.fix)
    try:
        return py2tns.convert(path, quiet=True), None
    except py2tns.TnsError as e:
        return None, "Not sent: %s" % e


class Mirror(object):
    def __init__(self, win, calc, on_close):
        self.root = win
        self.calc = calc
        self.on_close = on_close
        win.title(calc.title + " Mirror")
        win.configure(bg="#000000")
        self.session = None
        self.jobs = []          # Commands for the link thread (key presses, uploads)
        self.jobs_lock = threading.Lock()
        self.last_key = 0.0     # When a key was last queued (time.time())
        self.last_keepalive = time.time()
        self.running = True
        self.want_reconnect = False
        self.released = False   # Let go of the calculator for another program (until Reconnect)
        self.keys_on = tk.BooleanVar(master=win, value=True)
        self.status = tk.StringVar(master=win, value="Connecting...")
        self.photo = None
        self.blank = tk.PhotoImage(master=win, width=320 * SCALE, height=240 * SCALE)
        self.frame_path = os.path.join(tempfile.gettempdir(),
                                       "calc_mirror_%s_%d.ppm" % (calc.slug, os.getpid()))
        self.frames = 0
        self.t0 = time.time()
        self.rec = None         # A recorder.Recorder while recording
        self.rec_lock = threading.Lock()
        self.manager = None     # The calculator manager (calc_manager.Manager) when open
        self.info = {}          # The calculator's last "info" answer (name, OS, free space)

        self.canvas = tk.Label(win, bg="#000000", width=320 * SCALE, height=240 * SCALE,
                               image=self.blank)
        self.canvas.pack(padx=12, pady=(12, 6))
        bar = tk.Frame(win, bg="#000000")
        bar.pack(fill="x", padx=12)
        style = dict(bg="#111113", fg="#ece9e2", activebackground="#1c1c1f",
                     activeforeground="#ffffff", relief="flat", padx=10, pady=6, bd=0)
        tk.Button(bar, text="Screenshot", command=self.screenshot, **style).pack(side="left")
        self.rec_btn = tk.Button(bar, text="Record", command=self.toggle_record, **style)
        self.rec_btn.pack(side="left", padx=(6, 0))
        if calc.can_send:
            tk.Button(bar, text="Send program...", command=self.send_program, **style).pack(
                side="left", padx=(6, 0))
        tk.Button(bar, text="Files...", command=self.open_files, **style).pack(
            side="left", padx=(6, 0))
        tk.Button(bar, text="Reconnect", command=self.reconnect, **style).pack(side="left", padx=6)
        tk.Checkbutton(bar, text="Keyboard", variable=self.keys_on, bg="#000000", fg="#ece9e2",
                       selectcolor="#111113", activebackground="#000000",
                       activeforeground="#ffffff").pack(side="right")
        tk.Label(win, textvariable=self.status, bg="#000000", fg="#9a968d", anchor="w",
                 justify="left", wraplength=320 * SCALE).pack(fill="x", padx=12, pady=(6, 10))

        win.bind("<Key>", self.on_key)
        self.canvas.bind("<MouseWheel>", self.on_wheel)
        self.canvas.bind("<Button-1>", self.on_click)
        for event, name in (("<Double-Button-1>", calc.double_click),
                            ("<Button-3>", calc.right_click), ("<Button-2>", calc.middle_click)):
            if name:
                self.canvas.bind(event, lambda e, n=name: self.send_key(n))
        win.protocol("WM_DELETE_WINDOW", self.quit)
        threading.Thread(target=self.link_loop, daemon=True).start()
        self.root.after(1000, self.tick)

    # ---- The link thread: the only one that talks to the calculator ----
    def link_loop(self):
        while self.running:
            if self.released:  # Another program (TI's) has the calculator: wait for Reconnect
                if self.session is not None:
                    self.session.close()
                    self.session = None
                time.sleep(0.2)
                continue
            if self.session is None:
                try:
                    self.session = nspire_link.Session(cli=self.calc.cli)
                    code, lines = self.session.cmd("info")
                    d = nspire_link.info_dict(lines)
                    self.info = d
                    name =d.get("name", self.calc.title).replace("_", " ")
                    self.set_status("Connected: %s%s" % (name, ", OS %s" % d["os"] if "os" in d else ""))
                except nspire_link.LinkError:
                    self.session = None
                    self.set_status("Looking for the %s... (plugged in, switched on, TI's own "
                                    "software closed)" % self.calc.title)
                    self.wait_reconnect(2.0)  # Tries again by itself
                    continue
            with self.jobs_lock:
                jobs, self.jobs = self.jobs, []
            # Key presses that queued up while a picture was coming go out as one command
            merged = []
            for line, note, done, progress in jobs:
                if line.startswith("key ") and merged and merged[-1][0].startswith("keys "):
                    merged[-1] = (merged[-1][0] + " " + line[4:], note, None, None)
                elif line.startswith("key "):
                    merged.append(("keys " + line[4:], note, None, None))
                else:
                    merged.append((line, note, done, progress))
            for k, (line, note, done, progress) in enumerate(merged):
                code, lines = self.session.cmd(line, progress)
                if note:
                    ok = [l for l in lines if l.startswith(("OK", "ERR"))]
                    self.set_status("%s: %s" % (note, ok[-1] if ok else "exit %d" % code))
                if done is not None:
                    done(code, lines)  # On this thread: it hands any window work to Tk
                if code == 4 and self.link_dead():
                    for _, _, d, _ in merged[k + 1:]:  # Everyone waiting gets an answer
                        if d is not None:
                            d(4, ["ERR the link closed"])
                    break
            if self.session is None:
                continue
            # Keep-alive: the calculator switches itself off after a few idle minutes and only a
            # key press counts as use, so while its window is open a key that does nothing goes
            # out once a minute when you haven't typed
            ka = getattr(self.calc, "keepalive_key", None)
            if ka and KEEPALIVE_S and time.time() - max(self.last_key, self.last_keepalive) >= KEEPALIVE_S:
                self.last_keepalive = time.time()
                self.session.cmd("key " + ka)
            # While typing, keys go out as they come and the picture waits: a screenshot can't be
            # interrupted, so a key typed during one waits for all of it (1.4 s on the 84 Plus CE)
            if time.time() - self.last_key < self.calc.shot_holdoff:
                time.sleep(0.015)
                continue
            tmp = self.frame_path + ".new"
            code, lines = self.session.cmd("shot " + tmp)
            if code == 0:
                try:
                    os.replace(tmp, self.frame_path)
                    self.frames += 1
                    with self.rec_lock:
                        if self.rec is not None:
                            self.rec.add(self.frame_path)
                    self.root.after(0, self.draw_frame)  # Shown at once
                except OSError:
                    pass
            elif self.link_dead():
                continue
            else:
                time.sleep(0.5)

    def link_dead(self):
        if self.session is not None and self.session.p.poll() is not None:
            self.session = None
            self.set_status("The link closed (cable pulled?). Reconnecting when it's back...")
            self.wait_reconnect(2.0)
            return True
        return False

    def wait_reconnect(self, seconds):
        """Until the Reconnect button, or `seconds` have passed"""
        self.want_reconnect = False
        t = time.time()
        while self.running and not self.want_reconnect and time.time() - t < seconds:
            time.sleep(0.1)

    def reconnect(self):
        self.released = False
        if self.session is not None:
            self.session.close()
            self.session = None
        self.want_reconnect = True
        self.set_status("Connecting...")

    def release(self):
        """Lets go of the calculator so another program (TI's) can open it, until Reconnect"""
        self.released = True
        self.set_status("CalcSuite has let go of the %s so TI's software can use it. Close that, "
                        "then press Reconnect." % self.calc.title)

    def queue(self, line, note=None, done=None, progress=None):
        """A command for the link thread. done(code, lines) is called on the link thread when it
        has run; progress(bytes, total) during a transfer."""
        with self.jobs_lock:
            self.jobs.append((line, note, done, progress))
            if line.startswith(("key ", "keys ")):
                self.last_key = time.time()

    def set_status(self, text):
        if self.running:
            try:
                self.root.after(0, self.status.set, text)
            except (tk.TclError, RuntimeError):
                pass

    # ---- The window ----
    def draw_frame(self):
        if self.running and os.path.isfile(self.frame_path):
            try:
                img = tk.PhotoImage(master=self.root, file=self.frame_path)
                if img.width() < 320:  # The monochrome 84's 96 x 64 screen, the 89's 160 x 100
                    z = getattr(self.calc, "zoom", 3)
                    img = img.zoom(z, z)
                if SCALE > 1:
                    img = img.zoom(SCALE, SCALE)
                self.photo = img
                self.canvas.configure(image=img)
            except tk.TclError:
                pass  # Caught mid-write: the next frame has it

    def tick(self):
        if not self.running:
            return
        dt = time.time() - self.t0
        title = self.calc.title + " Mirror"
        if dt >= 5:
            if self.frames:
                self.fps = self.frames / dt
            self.frames, self.t0 = 0, time.time()
        if getattr(self, "fps", 0):
            title += "  -  %.1f frames/s" % self.fps
        with self.rec_lock:
            if self.rec is not None:
                secs = self.rec.seconds()
                title += "  -  REC %d:%02d" % (secs // 60, secs % 60)
                if secs >= recorder.MAX_SECONDS:
                    self.root.after(0, self.toggle_record)
        self.root.title(title)
        self.root.after(1000, self.tick)

    def key_names(self, ev):
        """The calculator key names for a PC key press"""
        names = self.calc.tk_keys.get(ev.keysym)
        if names is None and ev.char and ev.char.isprintable():
            names = [ev.char]
        if ev.state & 0x4:  # Ctrl
            key = ev.keysym.lower() if len(ev.keysym) == 1 else (names[0] if names else "")
            names = ["ctrl+" + key]
        return names or []

    def on_key(self, ev):
        ctrl, shift = ev.state & 0x4, ev.state & 0x1
        if ctrl and not shift and ev.keysym.lower() == "c":
            self.copy_screen()  # The PC's clipboard (Ctrl+Shift+C: the handheld's own copy)
            return
        if ctrl and not shift and ev.keysym.lower() == "v":
            self.paste_text()
            return
        if ctrl and shift and ev.keysym.lower() in ("c", "v"):
            ev.keysym = ev.keysym.lower()
        if not self.keys_on.get() or self.session is None:
            return
        for name in self.key_names(ev):
            code = self.calc.code_for(name)
            if code is None:
                self.set_status("No %s key for %r" % (self.calc.title, name))
                return
            self.queue("key " + self.calc.key_fmt % code, "Key %s" % name)

    def paste_text(self):
        """The PC clipboard's text typed into the calculator, key by key"""
        if self.session is None:
            self.set_status("Not connected yet")
            return
        try:
            text = self.root.clipboard_get()
        except tk.TclError:
            self.set_status("The clipboard has no text")
            return
        text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\t", "    ")
        if len(text) > PASTE_MAX:
            self.set_status("Too long to paste: %d characters (up to %d)" % (len(text), PASTE_MAX))
            return
        codes, missing = [], set()
        for ch in text:
            code = self.calc.code_for("enter" if ch == "\n" else ch)
            if code is None:
                missing.add(ch)
            else:
                codes.append(self.calc.key_fmt % code)
        if missing:
            shown = " ".join(sorted(repr(c) for c in missing))
            self.set_status("Can't type %s on the %s: nothing pasted" % (shown, self.calc.title))
            return
        for i in range(0, len(codes), 64):
            self.queue("keys " + " ".join(codes[i:i + 64]))
        self.set_status("Pasting %d characters..." % len(codes))

    def copy_screen(self):
        """The calculator's screen, as a picture, on the PC clipboard"""
        if not os.path.isfile(self.frame_path):
            self.set_status("No picture yet")
            return
        try:
            w, h, rgb = recorder.read_ppm(self.frame_path)
            set_clipboard_image(w, h, rgb, 2 if w >= 320 else 6)
            self.set_status("Screen copied: paste it anywhere (Ctrl+V)")
        except (OSError, ValueError) as e:
            self.set_status("Couldn't copy: %s" % e)

    def send_key(self, name):
        if not self.keys_on.get() or self.session is None or not name:
            return
        code = self.calc.code_for(name)
        if code is not None:
            self.queue("key " + self.calc.key_fmt % code, "Key %s" % name)

    def on_click(self, ev):
        ox = (self.canvas.winfo_width() - 320 * SCALE) // 2
        oy = (self.canvas.winfo_height() - 240 * SCALE) // 2
        self.send_key(self.calc.click((ev.x - ox) // SCALE, (ev.y - oy) // SCALE))

    def on_wheel(self, ev):
        if not self.keys_on.get() or self.session is None:
            return
        steps = max(1, min(5, abs(ev.delta) // 120))
        up, down, left, right = self.calc.wheel
        if ev.state & 0x1:  # Shift: sideways
            name = left if ev.delta > 0 else right
        else:
            name = up if ev.delta > 0 else down
        with self.jobs_lock:  # A spinning wheel never queues more than a screenful
            if len(self.jobs) > 12:
                return
        for _ in range(steps):
            self.send_key(name)

    def capture_stem(self):
        os.makedirs(os.path.join(KIT, "captures"), exist_ok=True)
        return os.path.join(KIT, "captures", time.strftime(self.calc.slug + "-%Y%m%d-%H%M%S"))

    def screenshot(self):
        if not os.path.isfile(self.frame_path):
            self.set_status("No picture yet")
            return
        out = self.capture_stem() + ".png"
        try:
            nspire_link.ppm_to_png(self.frame_path, out, 2)
            self.set_status("Saved %s" % out)
        except (OSError, ValueError) as e:
            self.set_status("Couldn't save: %s" % e)

    def toggle_record(self):
        with self.rec_lock:
            rec, self.rec = self.rec, (None if self.rec is not None else recorder.Recorder(SCALE))
            if rec is None and os.path.isfile(self.frame_path):
                self.rec.add(self.frame_path)  # The recording starts with what's on screen
        if rec is None:
            self.rec_btn.configure(text="Stop", fg="#ff6a5e")
            self.set_status("Recording (up to %d s)... press Stop to save" % recorder.MAX_SECONDS)
            self.offer_ffmpeg()
            return
        self.rec_btn.configure(text="Record", fg="#ece9e2")
        if not rec.frames:
            self.set_status("Nothing was recorded")
            return
        self.set_status("Saving the recording...")
        stem = self.capture_stem()

        def work():
            try:
                paths = rec.save(stem)
                self.set_status("Saved " + " and ".join(os.path.basename(p) for p in paths) +
                                " in " + os.path.dirname(stem))
            except Exception as e:  # A recording must never take the window down
                self.set_status("Couldn't save the recording: %s" % e)

        threading.Thread(target=work, daemon=True).start()

    _ffmpeg_asked = False  # Once per run, for every window

    def offer_ffmpeg(self):
        """No ffmpeg: offer to download it once, while the recording runs (MP4 needs it; GIF
        doesn't)"""
        if recorder.find_ffmpeg() or Mirror._ffmpeg_asked:
            return
        Mirror._ffmpeg_asked = True
        from tkinter import messagebox
        if not messagebox.askyesno(
                "MP4 recordings", "Recordings are saved as a GIF. For an MP4 as well, CalcSuite "
                "needs ffmpeg (free, about %d MB, downloaded once).\n\nDownload it now? It "
                "downloads while you record.\n\n(No: GIF only. OBS or any screen recorder works "
                "too.)" % recorder.FFMPEG_DOWNLOAD_MB, parent=self.root):
            return

        def work():
            shown = [-1]

            def progress(done, total):
                pct = done * 100 // total if total else -1
                if pct != shown[0] and pct % 5 == 0:  # Every 5 %, not every 64 KB
                    shown[0] = pct
                    self.set_status("Recording... downloading ffmpeg %d%%" % pct)
            try:
                recorder.download_ffmpeg(progress)
                self.set_status("Recording... ffmpeg is ready: the MP4 comes with the GIF")
            except Exception as e:  # Never takes the window down; GIF still works
                self.set_status("Recording... couldn't get ffmpeg (%s): GIF only" % e)

        threading.Thread(target=work, daemon=True).start()

    def send_program(self):
        if self.calc.slug != "nspire":  # The 84 and the 89: TI-Basic text or a TI file
            send_ti.send_from_window(self, KIT)
            return
        path = filedialog.askopenfilename(
            parent=self.root, title="Send to the handheld",
            initialdir=os.path.join(KIT, "programs"),
            filetypes=[("Python programs and TI documents", "*.py *.tns"), ("All files", "*.*")])
        if not path:
            return
        path, error = prepare_for_nspire(path)
        if error:
            self.set_status(error)
            return
        self.queue("put %s|/%s" % (os.path.abspath(path), os.path.basename(path)),
                   "Send %s" % os.path.basename(path))

    def open_files(self):
        """The calculator manager: files, calculator info, OS updates"""
        if self.manager is not None and self.manager.alive():
            self.manager.lift()
            return
        self.manager = calc_manager.Manager(self, KIT, prepare_for_nspire)

    def quit(self):
        if self.manager is not None and self.manager.alive():
            self.manager.close()
        self.running = False
        self.want_reconnect = True
        if self.session is not None:
            self.session.close()
        try:
            os.remove(self.frame_path)
        except OSError:
            pass
        self.root.destroy()
        self.on_close(self)


def set_app_icon(root):
    """The app icon (assets/app.png) on every window, and the taskbar's own for this app"""
    for path in (os.path.join(os.path.dirname(HERE), "assets", "app.png"),  # From the source
                 os.path.join(HERE, "assets", "app.png")):                  # The packaged app
        if os.path.isfile(path):
            try:
                root._app_icon = tk.PhotoImage(master=root, file=path)
                root.iconphoto(True, root._app_icon)  # True: every window made later too
            except tk.TclError:
                pass
            break
    try:  # Run from Python, the taskbar would group the windows under python.exe's icon
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("CalcMirror.App")
    except (AttributeError, OSError):
        pass
    # Every window (the calculators', Files, About, dialogs) gets a dark title bar when it appears
    root.bind_class("Toplevel", "<Map>", lambda e: dark_title_bar(e.widget), add="+")
    root.bind_class("Tk", "<Map>", lambda e: dark_title_bar(e.widget), add="+")


def dark_title_bar(win):
    """Windows 10 (2004+) and 11: the window's title bar in dark mode. Does nothing elsewhere."""
    if getattr(win, "_dark_done", False) or win.winfo_toplevel() is not win:
        return
    try:
        import ctypes
        from ctypes import wintypes
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        on = ctypes.c_int(1)
        for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE, and its number before Windows 10 2004
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(wintypes.HWND(hwnd), attr, ctypes.byref(on),
                                                          ctypes.sizeof(on)) == 0:
                break
        # Repaint the frame now (SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED)
        ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0020)
        win._dark_done = True
    except (AttributeError, OSError, tk.TclError):
        pass


class App(object):
    """One window per calculator; watches USB for calculators plugged in later"""

    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()  # Only the calculators' windows show
        set_app_icon(self.root)
        self.windows = {}     # pid -> Mirror
        self.closed = set()   # Calculators whose window the user closed: not reopened
        self.found = set()
        self.first_scan = True
        threading.Thread(target=self.scan_loop, daemon=True).start()
        self.root.after(300, self.sync)

    def scan_loop(self):
        while True:
            self.found = nspire_link.usb_calculators()
            self.scanned = True
            time.sleep(3)

    def sync(self):
        if getattr(self, "scanned", False):
            present = [c for c in CALCS if c.pid in self.found]
            if self.first_scan and not present:
                present = [Nspire]  # Nothing plugged in yet: a window that waits
            self.first_scan = False
            for calc in present:
                if calc.pid not in self.windows and calc.pid not in self.closed:
                    win = tk.Toplevel(self.root)
                    self.windows[calc.pid] = Mirror(win, calc, self.closed_window)
            for pid in list(self.closed):
                if pid not in self.found:
                    self.closed.discard(pid)  # Unplugged: plugging it in again opens it
        self.root.after(1000, self.sync)

    def closed_window(self, mirror):
        self.windows.pop(mirror.calc.pid, None)
        self.closed.add(mirror.calc.pid)
        if not self.windows:
            self.root.destroy()

    def run(self):
        self.root.mainloop()


def already_running():
    """One copy at a time: a second one would take the calculators away from the first, and
    both would go black"""
    if os.name != "nt":
        return False
    import ctypes
    global _mutex  # Kept for the life of the process
    _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "NspireMirror.single")
    return ctypes.windll.kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS


def main():
    if already_running():
        from tkinter import messagebox
        r = tk.Tk()
        r.withdraw()
        messagebox.showinfo("Calc Mirror", "The mirror is already open.")
        return
    App().run()


if __name__ == "__main__":
    main()
