"""CalcSuite: your TI calculators' screens in one window, with your keyboard as their keypad.

    python -I tools/mirror.py            (or double-click "CalcSuite.bat")

One window with a tab strip: "All screens" (every connected calculator side by side), then
one tab per calculator (a TI-Nspire CX II, a TI-84 Plus CE, a TI-89 Titanium). A calculator
plugged in later gets its tab; one unplugged greys out until it's back. "Open in its own
window" pops a calculator's tab out into a window of its own; closing that window docks it
back.

A calculator's tab: the live picture (the Nspire about 19 frames a second, the 84 Plus CE about
1), Screenshot, Copy screen, Paste text, Record, Send program, Keyboard on/off, and a panel
with Files (the calculator manager, calc_manager.py, with Back up / Restore), Keys, Symbols,
Guide, Get programs and Info (model, OS, clock, Exit Press-to-Test, the connection doctor).

Each calculator has one link thread, the only thing that talks to it (Mirror.link_loop):
keys go first, the picture catches up when you pause, a do-nothing key keeps it awake.
The keys each PC key presses: calc_models.py (and the Keys panel, made from the same table).
"""

import os
import shutil
import sys
import tempfile
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "nspire_cli"))
sys.path.insert(0, os.path.join(HERE, "ti84_cli"))
import nspire_link  # noqa: E402
import recorder  # noqa: E402
import calc_manager  # noqa: E402
import send_ti  # noqa: E402
import calc_models  # noqa: E402
import key_strip  # noqa: E402
import ui_theme as th  # noqa: E402

import check_nspire  # noqa: E402
import py2tns  # noqa: E402

from calc_models import Nspire, Ti84, Ti89, CALCS  # noqa: E402,F401  (the old names still work)

APP_NAME = "CalcSuite"
SPONSOR_URL = None  # A sponsor / funding page; the Info panel shows "Support CalcSuite" when set
DOCS = os.path.join(os.path.expanduser("~"), "Documents")
OLD_KIT = os.path.join(DOCS, "Nspire Mirror")  # Where the app kept its files before 1.0

if getattr(sys, "frozen", False):
    # The packaged app: its tools are unpacked beside this file; what it makes goes to the
    # user's Documents
    KIT = os.path.join(DOCS, "CalcSuite")
    py2tns.BUILD = os.path.join(KIT, "build")
else:
    KIT = os.path.dirname(HERE)
SCALE = 2
PASTE_MAX = 4000  # Characters one paste may type
KEEPALIVE_S = 60  # A do-nothing key this often while a calculator is connected and idle (0: never)
HISTORY = 8       # Keys the key-history strip shows


def resource(*parts):
    """A file shipped with the app: from the source tree, or unpacked beside the packaged exe"""
    for base in (os.path.dirname(HERE), getattr(sys, "_MEIPASS", HERE), HERE):
        p = os.path.join(base, *parts)
        if os.path.exists(p):
            return p
    return os.path.join(os.path.dirname(HERE), *parts)


def migrate_documents(old=OLD_KIT, new=None):
    """Documents\\Nspire Mirror -> Documents\\CalcSuite, once: copies what isn't there yet
    (captures, programs, from-calc, ...), never overwrites, never deletes; leaves a note in the
    old folder. Returns the number of files copied (or None when there was nothing to do)."""
    new = new or os.path.join(DOCS, "CalcSuite")
    note = os.path.join(old, "Moved to CalcSuite.txt")
    if not os.path.isdir(old) or os.path.exists(note):
        return None
    copied = 0
    for dirpath, _dirs, files in os.walk(old):
        rel = os.path.relpath(dirpath, old)
        dest_dir = os.path.normpath(os.path.join(new, rel))
        for f in files:
            src, dst = os.path.join(dirpath, f), os.path.join(dest_dir, f)
            if os.path.exists(dst):
                continue
            try:
                os.makedirs(dest_dir, exist_ok=True)
                shutil.copy2(src, dst)
                copied += 1
            except OSError:
                pass
    try:
        with open(note, "w", encoding="utf-8") as fh:
            fh.write("Nspire Mirror is now CalcSuite.\n\nIts files are now in %s: everything in "
                     "this folder was copied there (%d files; nothing that was already there was "
                     "replaced).\nThis folder was left as it was: delete it yourself when you "
                     "no longer need it.\n" % (new, copied))
    except OSError:
        pass
    return copied


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
    """One calculator: its link thread, its frames, its keys. The views (its tab, its tile in
    All screens) draw what it has."""

    def __init__(self, app, calc):
        self.app = app
        self.calc = calc
        self.root = app.root    # Where dialogs hang and after() runs: the tab's frame, later
        self.session = None
        self.jobs = []          # Commands for the link thread (key presses, uploads)
        self.jobs_lock = threading.Lock()
        self.last_key = 0.0     # When a key was last queued (time.time())
        self.last_keepalive = time.time()
        self.running = True
        self.present = True     # On USB now (the App's scan says)
        self.want_reconnect = False
        self.released = False   # Let go of the calculator for another program (until Reconnect)
        self.keys_on = tk.BooleanVar(master=app.root, value=True)
        self.status = tk.StringVar(master=app.root, value="Connecting...")
        self.frame_path = os.path.join(tempfile.gettempdir(),
                                       "calc_mirror_%s_%d.ppm" % (calc.slug, os.getpid()))
        self.frames = 0
        self.frames_total = 0
        self.fps = 0.0
        self.t0 = time.time()
        self.rec = None         # A recorder.Recorder while recording
        self.rec_lock = threading.Lock()
        self.manager = None     # The calculator manager (calc_manager.Manager) when open
        self.info = {}          # The calculator's last "info" answer (name, OS, free space)
        self.views = []         # ScreenViews showing this calculator
        self.image = None       # The last frame as a PhotoImage, the calculator's own size
        self.native = None      # Its (w, h)
        self.history = []       # The last keys pressed, as labels (newest last)
        self.last_press = tk.StringVar(master=app.root, value="Last key: none yet")
        self.listeners = []     # fn(keysym) called after a key press (the Keys panel)
        self.click_acted = 0.0  # When a single click last pressed keys (double click skips)
        threading.Thread(target=self.link_loop, daemon=True).start()

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
                if not self.present:  # Unplugged: wait for the scan to see it again
                    self.set_status("Not plugged in")
                    self.wait_reconnect(1.0)
                    continue
                try:
                    self.session = nspire_link.Session(cli=self.calc.cli)
                    code, lines = self.session.cmd("info")
                    d = nspire_link.info_dict(lines)
                    self.info = d
                    name = d.get("name", self.calc.title).replace("_", " ")
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
                    try:
                        done(code, lines)  # On this thread: it hands any window work to Tk
                    except Exception:  # A caller's mistake must never stop the link
                        pass
                if code == 4 and self.link_dead():
                    for _, _, d, _ in merged[k + 1:]:  # Everyone waiting gets an answer
                        if d is not None:
                            d(4, ["ERR the link closed"])
                    break
            if self.session is None:
                continue
            # Keep-alive: the calculator switches itself off after a few idle minutes and only a
            # key press counts as use, so while it's connected a key that does nothing goes out
            # once a minute when you haven't typed
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
                    self.frames_total += 1
                    with self.rec_lock:
                        if self.rec is not None:
                            self.rec.add(self.frame_path)
                    self.app.root.after(0, self.draw_frame)  # Shown at once
                except (OSError, RuntimeError):
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
                        "then press Reconnect (Info)." % self.calc.title)

    def queue(self, line, note=None, done=None, progress=None):
        """A command for the link thread. done(code, lines) is called on the link thread when it
        has run; progress(bytes, total) during a transfer."""
        with self.jobs_lock:
            self.jobs.append((line, note, done, progress))
            if line.startswith(("key ", "keys ")):
                self.last_key = time.time()

    def run_batch(self, cmds, timeout=900):
        """[(line, progress)] on the link thread, waited for: [(code, lines)]. For a worker
        thread only (never Tk's)."""
        results = [None] * len(cmds)
        left = [len(cmds)]
        ev = threading.Event()
        for k, (line, progress) in enumerate(cmds):
            def done(code, lines, k=k):
                results[k] = (code, lines)
                left[0] -= 1
                if left[0] == 0:
                    ev.set()
            self.queue(line, None, done, progress)
        t0 = time.time()
        while cmds and not ev.wait(0.5):
            if not self.running or time.time() - t0 > timeout:
                break
        return [r or (4, ["ERR no answer (closed, or the cable?)"]) for r in results]

    def set_status(self, text):
        if self.running:
            try:
                self.app.root.after(0, self.status.set, text)
            except (tk.TclError, RuntimeError):
                pass

    def connected(self):
        return self.session is not None

    # ---- Frames ----
    def draw_frame(self):
        if not (self.running and os.path.isfile(self.frame_path)):
            return
        visible = [v for v in self.views if v.visible()]
        try:
            img = tk.PhotoImage(master=self.app.root, file=self.frame_path)
        except tk.TclError:
            return  # Caught mid-write: the next frame has it
        self.image = img
        self.native = (img.width(), img.height())
        for v in visible:
            v.show(img)

    def frame_rgb(self):
        try:
            return recorder.read_ppm(self.frame_path)
        except (OSError, ValueError):
            return None

    def tick(self):
        """Once a second (the App's tick): the frame rate, the recording's time limit"""
        dt = time.time() - self.t0
        if dt >= 5:
            self.fps = self.frames / dt if self.frames else 0.0
            self.frames, self.t0 = 0, time.time()
        if self.session is None:
            self.fps = 0.0
        with self.rec_lock:
            if self.rec is not None and self.rec.seconds() >= recorder.MAX_SECONDS:
                self.app.root.after(0, self.toggle_record)

    def rec_seconds(self):
        with self.rec_lock:
            return None if self.rec is None else self.rec.seconds()

    # ---- Keys ----
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
        if ev.keysym in ("Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R",
                         "Caps_Lock", "Win_L", "Win_R", "Num_Lock"):
            return
        if not self.keys_on.get() or self.session is None:
            return
        names = self.key_names(ev)
        codes = []
        for name in names:
            code = self.calc.code_for(name)
            if code is None:
                self.set_status("No %s key for %r" % (self.calc.title, name))
                return
            codes.append(code)
        for name, code in zip(names, codes):
            self.queue("key " + self.calc.key_fmt % code, "Key %s" % name)
        if names:
            self.pressed(ev.keysym, ev.char, names)

    def pressed(self, keysym, char, names, text=None):
        """Remembers a press for the Last key line, the key-history strip and the Keys panel"""
        label = self.calc.keys_label(names) if names else (text or "")
        self.history.append(label)
        del self.history[:-HISTORY]
        self.last_press.set("Last key: " + (text or self.calc.describe_press(keysym, char, names)))
        for fn in list(self.listeners):
            try:
                fn(keysym)
            except tk.TclError:
                pass

    def send_key(self, name):
        if not self.keys_on.get() or self.session is None or not name:
            return False
        code = self.calc.code_for(name)
        if code is not None:
            self.queue("key " + self.calc.key_fmt % code, "Key %s" % name)
            return True
        return False

    def send_names(self, names, what=None):
        """Several key names (a mouse action, a symbol), in order; remembered as one press"""
        if not names or not self.keys_on.get() or self.session is None:
            return False
        codes = [self.calc.resolve(n) for n in names]
        if any(c is None for c in codes):
            return False
        self.queue("keys " + " ".join(self.calc.key_fmt % c for c in codes))
        self.pressed(None, None, names, text=what)
        return True

    def send_codes(self, codes, what):
        if self.session is None:
            self.set_status("Not connected yet")
            return False
        if not self.keys_on.get():
            self.set_status("The keyboard is off for the %s (Keyboard)" % self.calc.title)
            return False
        for i in range(0, len(codes), 64):
            self.queue("keys " + " ".join(self.calc.key_fmt % c for c in codes[i:i + 64]))
        self.history.append(what)
        del self.history[:-HISTORY]
        self.last_press.set("Last key: " + what)
        for fn in list(self.listeners):
            fn(None)
        return True

    def paste_text(self, text=None):
        """The PC clipboard's text typed into the calculator, key by key"""
        if self.session is None:
            self.set_status("Not connected yet")
            return
        if text is None:
            try:
                text = self.app.root.clipboard_get()
            except tk.TclError:
                self.set_status("The clipboard has no text")
                return
        text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\t", "    ")
        if len(text) > PASTE_MAX:
            self.set_status("Too long to paste: %d characters (up to %d)" % (len(text), PASTE_MAX))
            return
        codes, missing = self.calc.paste_keys(text)
        if missing:
            shown = " ".join(sorted(repr(c) for c in missing))
            self.set_status("Can't type %s on the %s: nothing pasted" % (shown, self.calc.title))
            return
        for i in range(0, len(codes), 64):
            self.queue("keys " + " ".join(self.calc.key_fmt % c for c in codes[i:i + 64]))
        self.set_status("Pasting %d characters..." % len(text))
        shown = text.replace("\n", " ↵ ")
        self.pressed(None, None, [], text="paste " + (shown[:24] + "..." if len(shown) > 24 else shown))

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

    # ---- The mouse on the screen (x, y in the calculator's pixels) ----
    def on_click(self, x, y):
        names = self.calc.click(x, y, self.frame_rgb())
        if names and self.send_names(names, "click → " + self.calc.keys_label(names)):
            self.click_acted = time.time()

    def on_double(self):
        if time.time() - self.click_acted < 0.6:
            return  # The single click already picked (an 84 menu line)
        if self.calc.double_click:
            self.send_names([self.calc.double_click], "double click → " +
                            self.calc.calc_label(self.calc.double_click))

    def on_button(self, which):
        name = {"right": self.calc.right_click, "middle": self.calc.middle_click}[which]
        if name:
            self.send_names([name], "%s click → %s" % (which, self.calc.calc_label(name)))

    def on_wheel(self, delta, shift):
        if not self.keys_on.get() or self.session is None:
            return
        steps = max(1, min(5, abs(delta) // 120))
        up, down, left, right = self.calc.wheel
        name = (left if delta > 0 else right) if shift else (up if delta > 0 else down)
        with self.jobs_lock:  # A spinning wheel never queues more than a screenful
            if len(self.jobs) > 12:
                return
        for _ in range(steps):
            self.send_key(name)
        self.pressed(None, None, [name], text="wheel → " + self.calc.calc_label(name))

    # ---- Screenshots, recordings ----
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
            rec = self.rec
            if rec is None:
                if self.app.burn_keys.get():  # The key strip in every frame, from the start
                    burner = key_strip.Burner(lambda: list(self.history))
                    w = self.native[0] if self.native else 320
                    scale = max(1, SCALE // burner.zoom_for(w))
                    self.rec = recorder.Recorder(scale, burner)
                else:
                    self.rec = recorder.Recorder(SCALE)
                if os.path.isfile(self.frame_path):
                    self.rec.add(self.frame_path)  # The recording starts with what's on screen
            else:
                self.rec = None
        self.app.recording_changed(self)
        if rec is None:
            self.set_status("Recording (up to %d s)... press Stop to save" % recorder.MAX_SECONDS)
            self.offer_ffmpeg()
            return
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

    _ffmpeg_asked = False  # Once per run, for every calculator

    def offer_ffmpeg(self):
        """No ffmpeg: offer to download it once, while the recording runs (MP4 needs it; GIF
        doesn't)"""
        if recorder.find_ffmpeg() or Mirror._ffmpeg_asked:
            return
        Mirror._ffmpeg_asked = True
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

    # ---- Sending ----
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
        self.send_nspire_files([(path, "/")])

    def send_nspire_files(self, files, done=None):
        """[(local file, calculator folder)] to the Nspire: makes a missing folder, asks before
        replacing a file of the same name. done(ok, message) on Tk's thread."""
        folders = sorted(set(f for _p, f in files))

        def work():
            names = {}
            for folder in folders:
                code, lines = self.run_batch([("ls " + folder, None)])[0]
                if code and folder != "/":
                    self.run_batch([("mkdir " + folder, None)])
                    code, lines = 0, []
                import calc_files as cf
                names[folder] = {calc_manager.shown(i["name"]).lower()
                                 for i in cf.parse_nspire_ls(lines)} if code == 0 else set()
            self.app.root.after(0, lambda: ask(names))

        def ask(names):
            same = [os.path.basename(p) for p, f in files if os.path.basename(p).lower() in names[f]]
            if same and not messagebox.askyesno(
                    "Replace?", "%s %s already on the handheld. Replace?" % (
                        ", ".join(same[:12]), "is" if len(same) == 1 else "are"), parent=self.root):
                self.set_status("Not sent")
                if done:
                    done(False, "Not sent")
                return
            state = {"left": len(files), "errors": []}
            for p, folder in files:
                base = os.path.basename(p)
                remote = folder.rstrip("/") + "/" + base

                def sent(code, lines, base=base):
                    if code:
                        ok = [l for l in lines if l.startswith("ERR")]
                        state["errors"].append("%s: %s" % (base, ok[-1][4:] if ok else code))
                    state["left"] -= 1
                    if state["left"] == 0:
                        msg = ("Sent %s" % ", ".join(os.path.basename(p) for p, _f in files[:4]) +
                               (" and %d more" % (len(files) - 4) if len(files) > 4 else "")
                               if not state["errors"] else "Not sent: " + "; ".join(state["errors"][:3]))
                        self.set_status(msg)
                        if done:
                            self.app.root.after(0, done, not state["errors"], msg)

                def progress(n, total, base=base):
                    self.set_status("Sending %s: %d%%" % (base, 100 * n // total if total else 0))
                self.queue("put %s|%s" % (os.path.abspath(p), remote), None, sent, progress)
        threading.Thread(target=work, daemon=True).start()

    def open_files(self):
        """The Files panel of this calculator's tab"""
        self.app.show_tab(self.calc.pid)
        self.app.tabs[self.calc.pid].show_section("Files")

    def stop(self):
        if self.manager is not None and self.manager.alive():
            self.manager.close()
        self.running = False
        self.want_reconnect = True
        with self.rec_lock:
            rec, self.rec = self.rec, None
        if rec is not None and rec.frames:  # Closing mid-recording keeps what was recorded
            try:
                rec.save(self.capture_stem())
            except Exception:
                pass
        if self.session is not None:
            self.session.close()
        try:
            os.remove(self.frame_path)
        except OSError:
            pass


class ScreenView(object):
    """A calculator's picture in a Label, scaled by a whole number to fit its space"""

    def __init__(self, parent, mirror, big, visible, fit, bg=th.BG):
        self.m = mirror
        self.big = big
        self.visible = visible   # () -> True when it's on screen
        self.fit = fit           # () -> (width, height) it may use
        self.zoom = None         # (zoom, subsample) of the shown picture
        self.photo = None
        self.label = tk.Label(parent, bg=bg, bd=0, highlightthickness=0, cursor="crosshair" if big else "hand2")
        mirror.views.append(self)

    def scale_for(self, w, h):
        """(zoom, subsample) for a w x h picture in the space fit() gives"""
        aw, ah = self.fit()
        z = max(0, min(aw // max(1, w), ah // max(1, h)))
        if self.big:
            z = min(z, 6)
        else:
            z = min(z, 3)
        if z >= 1:
            return z, 1
        return 1, 2

    def show(self, img=None):
        img = img or self.m.image
        if img is None:
            return
        w, h = img.width(), img.height()
        z, sub = self.scale_for(w, h)
        shown = img.zoom(z, z) if z > 1 else (img.subsample(sub, sub) if sub > 1 else img)
        self.zoom = (z, sub)
        self.photo = shown
        try:
            self.label.configure(image=shown)
        except tk.TclError:
            pass

    def to_calc(self, ev):
        """A mouse event -> (x, y) in the calculator's pixels, or None outside the picture"""
        if self.photo is None or self.zoom is None or self.m.native is None:
            return None
        pw, ph = self.photo.width(), self.photo.height()
        ox = (self.label.winfo_width() - pw) // 2
        oy = (self.label.winfo_height() - ph) // 2
        x, y = ev.x - ox, ev.y - oy
        if not (0 <= x < pw and 0 <= y < ph):
            return None
        nw, nh = self.m.native
        return x * nw // pw, y * nh // ph


class Tab(object):
    """A calculator's tab: the big screen, its buttons and the side panel"""

    def __init__(self, app, mirror):
        import ui_panels
        self.app = app
        self.m = mirror
        calc = mirror.calc
        self.frame = tk.Frame(app.content, bg=th.BG)
        mirror.root = self.frame
        self.popped = False
        left = tk.Frame(self.frame, bg=th.BG)
        left.pack(side="left", fill="both", expand=True, padx=(14, 8), pady=(10, 10))
        self.screen_box = tk.Frame(left, bg=th.BG, width=640, height=480)
        self.screen_box.pack(fill="both", expand=True)
        self.screen_box.pack_propagate(False)
        self.view = ScreenView(self.screen_box, mirror, True, self.visible, self.fit)
        self.view.label.pack(fill="both", expand=True)
        lab = self.view.label
        lab.bind("<Button-1>", self.on_click)
        lab.bind("<Double-Button-1>", lambda e: mirror.on_double())
        lab.bind("<Button-3>", lambda e: mirror.on_button("right"))
        lab.bind("<Button-2>", lambda e: mirror.on_button("middle"))
        lab.bind("<MouseWheel>", lambda e: mirror.on_wheel(e.delta, e.state & 0x1))
        self.screen_box.bind("<Configure>", lambda e: self.view.show())

        self.strip = tk.Frame(left, bg=th.BG, height=26)  # The key history
        self.strip_on = False
        line = tk.Frame(left, bg=th.BG)
        line.pack(fill="x", pady=(6, 0))
        tk.Label(line, textvariable=mirror.last_press, bg=th.BG, fg=th.FG, anchor="w",
                 font=(th.FONT, 10)).pack(side="left")
        self.hist_var = tk.BooleanVar(master=self.frame, value=False)
        th.check(line, "Key history", self.hist_var, self.toggle_history).pack(side="right")
        th.check(line, "Show keys in recordings", app.burn_keys).pack(side="right", padx=(0, 10))
        bar = tk.Frame(left, bg=th.BG)
        bar.pack(fill="x", pady=(8, 0))
        th.button(bar, "Screenshot", mirror.screenshot).pack(side="left")
        th.button(bar, "Copy screen", mirror.copy_screen).pack(side="left", padx=(6, 0))
        th.button(bar, "Paste text", lambda: mirror.paste_text()).pack(side="left", padx=(6, 0))
        self.rec_btn = th.button(bar, "Record", mirror.toggle_record)
        self.rec_btn.pack(side="left", padx=(6, 0))
        th.button(bar, "Send program...", mirror.send_program).pack(side="left", padx=(6, 0))
        th.check(bar, "Keyboard", mirror.keys_on).pack(side="right")
        tk.Label(left, textvariable=mirror.status, bg=th.BG, fg=th.DIM, anchor="w", justify="left",
                 wraplength=640).pack(fill="x", pady=(8, 0))
        self.left = left
        self.panel = ui_panels.SidePanel(self.frame, app, mirror)
        self.panel.frame.pack(side="right", fill="y", padx=(8, 14), pady=(10, 10))
        mirror.listeners.append(self.key_pressed)

    def fit(self):
        return max(1, self.screen_box.winfo_width()), max(1, self.screen_box.winfo_height())

    def visible(self):
        return self.popped or self.app.current == self.m.calc.pid

    def on_click(self, ev):
        self.view.label.focus_set()
        p = self.view.to_calc(ev)
        if p is not None:
            self.m.on_click(*p)

    def show_section(self, name):
        self.panel.show(name)

    def toggle_history(self):
        if self.hist_var.get():
            self.strip.pack(fill="x", pady=(6, 0), after=self.screen_box)
            self.draw_history()
        else:
            self.strip.pack_forget()

    def key_pressed(self, keysym):
        if self.hist_var.get():
            self.draw_history()

    def draw_history(self):
        for c in self.strip.winfo_children():
            c.destroy()
        keys = self.m.history[-HISTORY:]
        for k, label in enumerate(keys):
            th.keycap(self.strip, label, accent=k == len(keys) - 1).pack(side="left", padx=(0, 4))

    def recording(self, on):
        self.rec_btn.configure(text="Stop" if on else "Record", fg=th.RED if on else th.FG)


class AllScreens(object):
    """Every connected calculator's live screen side by side"""

    def __init__(self, app):
        self.app = app
        self.frame = tk.Frame(app.content, bg=th.BG)
        self.grid = tk.Frame(self.frame, bg=th.BG)
        self.grid.pack(fill="both", expand=True, padx=14, pady=(14, 6))
        self.empty = tk.Label(self.grid, bg=th.BG, fg=th.DIM, justify="center", font=(th.FONT, 11),
                              text="No calculator is plugged in yet.\n\nPlug one in and switch it on: "
                                   "its screen appears here by itself.\nTI's own software must be "
                                   "closed, and each calculator needs the WinUSB driver (README).")
        tk.Label(self.frame, text="Click a screen to type on it. Double click opens its tab.",
                 bg=th.BG, fg=th.DIM, anchor="w").pack(fill="x", padx=14, pady=(0, 10))
        self.tiles = {}  # pid -> (frame, view, name label, fps label, outline)
        self.grid.bind("<Configure>", lambda e: self.layout())

    def add(self, mirror):
        pid = mirror.calc.pid
        outer = tk.Frame(self.grid, bg=th.BG, highlightthickness=2, highlightbackground=th.BG)
        head = tk.Frame(outer, bg=th.PANEL)
        head.pack(fill="x")
        name = tk.Label(head, text=mirror.calc.title, bg=th.PANEL, fg=th.FG, font=(th.FONT, 10, "bold"))
        name.pack(side="left", padx=8, pady=4)
        kb = tk.Label(head, text="KEYBOARD", bg=th.ACCENT, fg="#000000", font=(th.FONT, 8, "bold"), padx=5)
        fps = tk.Label(head, text="", bg=th.PANEL, fg=th.DIM)
        fps.pack(side="left")
        th.button(head, "Record", mirror.toggle_record, pady=2).pack(side="right", padx=(4, 6), pady=3)
        th.button(head, "Screenshot", mirror.screenshot, pady=2).pack(side="right", pady=3)
        box = tk.Frame(outer, bg=th.PANEL, width=330, height=250)
        box.pack(fill="both", expand=True)
        box.pack_propagate(False)
        view = ScreenView(box, mirror, False, lambda: self.app.current == "all",
                          lambda b=box: (b.winfo_width() - 8, b.winfo_height() - 8), bg=th.PANEL)
        view.label.pack(fill="both", expand=True, padx=4, pady=4)
        view.label.bind("<Button-1>", lambda e: self.app.set_target(pid))
        view.label.bind("<Double-Button-1>", lambda e: self.app.show_tab(pid))
        box.bind("<Configure>", lambda e: view.show())
        self.tiles[pid] = dict(frame=outer, view=view, name=name, fps=fps, kb=kb)
        self.layout()

    def remove(self, pid):
        t = self.tiles.pop(pid, None)
        if t:
            t["frame"].destroy()
            self.layout()

    def layout(self):
        tiles = [self.tiles[p] for p in sorted(self.tiles, key=self.app.order)]
        for t in tiles:
            t["frame"].grid_forget()
        if not tiles:
            self.empty.place(relx=0.5, rely=0.45, anchor="center")
            return
        self.empty.place_forget()
        n = len(tiles)
        for k, t in enumerate(tiles):
            t["frame"].grid(row=0, column=k, sticky="nsew", padx=6, pady=6)
        for k in range(4):
            self.grid.columnconfigure(k, weight=1 if k < n else 0, uniform="tiles" if k < n else "")
        self.grid.rowconfigure(0, weight=1)

    def update(self):
        for pid, t in self.tiles.items():
            m = self.app.mirrors[pid]
            here = m.present and m.session is not None
            target = self.app.target == pid
            t["frame"].configure(highlightbackground=th.ACCENT if target else th.BG)
            if target:
                t["kb"].pack(side="left", padx=(6, 0), after=t["name"])
            else:
                t["kb"].pack_forget()
            sec = m.rec_seconds()
            text = ("%.1f fps" % m.fps if here and m.fps else
                    "not plugged in" if not m.present else "connecting..." if not here else "")
            if sec is not None:
                text += "   REC %d:%02d" % (sec // 60, sec % 60)
            t["fps"].configure(text=text, fg=th.RED if sec is not None else th.DIM)
            t["name"].configure(fg=th.FG if m.present else th.GREY)


class App(object):
    """The one window: the tab strip, All screens, a tab per calculator; watches USB"""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.configure(bg=th.BG)
        self.root.geometry("1200x780")
        self.root.minsize(900, 600)
        set_app_icon(self.root)
        th.style_ttk(self.root)
        self.burn_keys = tk.BooleanVar(master=self.root, value=False)
        self.mirrors = {}     # pid -> Mirror
        self.tabs = {}        # pid -> Tab
        self.found = set()
        self.scanned = False
        self.current = "all"  # "all" or a pid
        self.target = None    # The keyboard target on All screens (a pid)

        strip = tk.Frame(self.root, bg=th.PANEL)
        strip.pack(fill="x")
        self.strip = tk.Frame(strip, bg=th.PANEL)
        self.strip.pack(side="left", fill="y")
        self.pop_btn = th.button(strip, "Open in its own window", self.pop_out, bg=th.PANEL)
        self.pop_btn.pack(side="right", padx=10, pady=6)
        tk.Frame(self.root, bg=th.LINE, height=1).pack(fill="x")
        self.content = tk.Frame(self.root, bg=th.BG)
        self.content.pack(fill="both", expand=True)
        self.tab_widgets = {}  # "all" / pid -> dict(frame, dot, name, fps, line)
        self.all = AllScreens(self)
        self.make_tab_button("all", "All screens")
        self.show_tab("all")

        self.root.bind_all("<Key>", self.on_key)
        self.root.bind_all("<Tab>", self.on_key)
        self.root.protocol("WM_DELETE_WINDOW", self.quit)
        threading.Thread(target=self.scan_loop, daemon=True).start()
        self.root.after(300, self.sync)
        self.root.after(1000, self.tick)

    @staticmethod
    def order(pid):
        return [c.pid for c in CALCS].index(pid) if pid in [c.pid for c in CALCS] else 9

    # ---- The tab strip ----
    def make_tab_button(self, key, text):
        f = tk.Frame(self.strip, bg=th.PANEL, cursor="hand2")
        f.pack(side="left")
        inner = tk.Frame(f, bg=th.PANEL)
        inner.pack(padx=14, pady=(8, 6))
        dot = tk.Canvas(inner, width=10, height=10, bg=th.PANEL, highlightthickness=0)
        if key != "all":
            dot.create_oval(1, 1, 9, 9, fill=th.GREY, outline="")
            dot.pack(side="left", padx=(0, 6))
        name = tk.Label(inner, text=text, bg=th.PANEL, fg=th.FG, font=(th.FONT, 10, "bold"))
        name.pack(side="left")
        fps = tk.Label(inner, text="", bg=th.PANEL, fg=th.DIM, font=(th.FONT, 9))
        fps.pack(side="left", padx=(8, 0))
        line = tk.Frame(f, bg=th.PANEL, height=2)
        line.pack(fill="x", side="bottom")
        for w in (f, inner, dot, name, fps):
            w.bind("<Button-1>", lambda e, k=key: self.show_tab(k))
        self.tab_widgets[key] = dict(frame=f, dot=dot, name=name, fps=fps, line=line, inner=inner)

    def show_tab(self, key):
        if key != "all" and key in self.tabs and self.tabs[key].popped:
            top = self.tabs[key].frame
            try:
                self.root.tk.call("wm", "deiconify", top._w)
                self.root.tk.call("raise", top._w)
            except tk.TclError:
                pass
            return
        old = self.current
        self.current = key
        for k, w in self.tab_widgets.items():
            sel = k == key
            for part in ("frame", "inner", "dot", "name", "fps"):
                w[part].configure(bg=th.PANEL2 if sel else th.PANEL)
            w["line"].configure(bg=th.ACCENT if sel else th.PANEL)
        frames = [self.all.frame] + [t.frame for t in self.tabs.values() if not t.popped]
        want = self.all.frame if key == "all" else self.tabs[key].frame
        for f in frames:
            if f is not want:
                f.pack_forget()
        want.pack(fill="both", expand=True)
        self.pop_btn.configure(state="normal" if key != "all" else "disabled")
        if key != "all":
            self.target = key
            self.tabs[key].view.show()
        elif old != "all":
            for t in self.all.tiles.values():
                t["view"].show()
        self.all.update()

    def set_target(self, pid):
        self.target = pid
        self.all.update()
        try:
            self.all.tiles[pid]["view"].label.focus_set()
        except (KeyError, tk.TclError):
            pass

    def pop_out(self):
        key = self.current
        if key == "all" or key not in self.tabs:
            return
        tab = self.tabs[key]
        f = tab.frame
        f.pack_forget()
        try:
            self.root.tk.call("wm", "manage", f._w)
        except tk.TclError as e:
            messagebox.showinfo(APP_NAME, "Couldn't open a window: %s" % e, parent=self.root)
            f.pack(fill="both", expand=True)
            return
        tab.popped = True
        name = self.root.register(lambda k=key: self.dock(k))
        self.root.tk.call("wm", "protocol", f._w, "WM_DELETE_WINDOW", name)
        self.root.tk.call("wm", "title", f._w, "%s - %s" % (tab.m.calc.title, APP_NAME))
        try:
            self.root.tk.call("wm", "iconphoto", f._w, self.root._app_icon)
        except (tk.TclError, AttributeError):
            pass
        f.after(50, lambda: dark_title_bar_path(self.root, f))
        self.tab_widgets[key]["fps"].configure(text="own window")
        self.show_tab("all")
        tab.view.show()

    def dock(self, key):
        tab = self.tabs.get(key)
        if tab is None or not tab.popped:
            return
        try:
            self.root.tk.call("wm", "forget", tab.frame._w)
        except tk.TclError:
            pass
        tab.popped = False
        self.show_tab(key)

    def popped_frame_of(self, widget):
        """The popped-out tab a widget sits in, else None"""
        for pid, t in self.tabs.items():
            if t.popped:
                w = widget
                while w is not None:
                    if w is t.frame:
                        return pid
                    w = getattr(w, "master", None)
        return None

    # ---- Keys: to the keyboard target ----
    def on_key(self, ev):
        w = ev.widget
        try:
            cls = w.winfo_class()
        except (AttributeError, tk.TclError):
            return None
        if cls in ("Entry", "TEntry", "Text", "Treeview", "TCombobox", "Listbox", "Spinbox"):
            return None  # Typing into CalcSuite itself (search box, file list)
        try:
            top = w.winfo_toplevel()
        except tk.TclError:
            return None
        pid = self.popped_frame_of(w)
        if pid is None:
            if top is not self.root:
                return None  # A dialog
            pid = self.current if self.current != "all" else self.target
        m = self.mirrors.get(pid)
        if m is None:
            return None
        m.on_key(ev)
        return "break"

    # ---- USB: calculators come and go ----
    def scan_loop(self):
        while True:
            self.found = nspire_link.usb_calculators()
            self.scanned = True
            time.sleep(3)

    def sync(self):
        if self.scanned:
            for calc in CALCS:
                present = calc.pid in self.found
                m = self.mirrors.get(calc.pid)
                if present and m is None:
                    self.add(calc)
                elif m is not None and m.present != present:
                    m.present = present
                    if present:
                        m.want_reconnect = True
        self.root.after(1000, self.sync)

    def add(self, calc):
        m = Mirror(self, calc)
        self.mirrors[calc.pid] = m
        self.make_tab_button(calc.pid, calc.title)
        # Tabs in a fixed order: Nspire, 84, 89
        for pid in sorted(self.tab_widgets, key=lambda k: -1 if k == "all" else self.order(k)):
            self.tab_widgets[pid]["frame"].pack_forget()
            self.tab_widgets[pid]["frame"].pack(side="left")
        self.tabs[calc.pid] = Tab(self, m)
        self.all.add(m)
        if self.target is None:
            self.target = calc.pid
        self.all.update()

    def recording_changed(self, m):
        tab = self.tabs.get(m.calc.pid)
        if tab:
            tab.recording(m.rec_seconds() is not None)

    def tick(self):
        for pid, m in self.mirrors.items():
            m.tick()
            w = self.tab_widgets[pid]
            here = m.present and m.session is not None
            colour = th.MINT if here else (th.GREY if not m.present else th.ACCENT)
            w["dot"].itemconfigure(1, fill=colour)
            w["name"].configure(fg=th.FG if m.present else th.GREY)
            sec = m.rec_seconds()
            if self.tabs[pid].popped:
                text = "own window"
            elif not m.present:
                text = "not plugged in"
            elif here:
                text = "%.1f fps" % m.fps if m.fps else ""
            else:
                text = "connecting"
            if sec is not None:
                text = "REC %d:%02d" % (sec // 60, sec % 60)
            w["fps"].configure(text=text, fg=th.RED if sec is not None else th.DIM)
            if self.tabs[pid].popped:
                fps = " - %.1f frames/s" % m.fps if m.fps else ""
                try:
                    self.root.tk.call("wm", "title", self.tabs[pid].frame._w,
                                      "%s%s - %s" % (m.calc.title, fps, APP_NAME))
                except tk.TclError:
                    pass
        self.all.update()
        self.root.after(1000, self.tick)

    def quit(self):
        for m in self.mirrors.values():
            m.stop()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


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
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("CalcSuite.App")
    except (AttributeError, OSError):
        pass
    # Every window (the main one, popped-out tabs, dialogs) gets a dark title bar when it appears
    root.bind_class("Toplevel", "<Map>", lambda e: dark_title_bar(e.widget), add="+")
    root.bind_class("Tk", "<Map>", lambda e: dark_title_bar(e.widget), add="+")


def dark_title_bar(win):
    """Windows 10 (2004+) and 11: the window's title bar in dark mode. Does nothing elsewhere."""
    if getattr(win, "_dark_done", False) or win.winfo_toplevel() is not win:
        return
    try:
        import ctypes
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        _dark_hwnd(hwnd)
        win._dark_done = True
    except (AttributeError, OSError, tk.TclError):
        pass


def dark_title_bar_path(root, frame):
    """The same for a frame made a window by `wm manage` (a popped-out tab)"""
    try:
        import ctypes
        hwnd = int(root.tk.call("wm", "frame", frame._w), 16)
        _dark_hwnd(hwnd)
    except (AttributeError, OSError, ValueError, tk.TclError):
        pass


def _dark_hwnd(hwnd):
    import ctypes
    from ctypes import wintypes
    on = ctypes.c_int(1)
    for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE, and its number before Windows 10 2004
        if ctypes.windll.dwmapi.DwmSetWindowAttribute(wintypes.HWND(hwnd), attr, ctypes.byref(on),
                                                      ctypes.sizeof(on)) == 0:
            break
    # Repaint the frame now (SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED)
    ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0020)


MUTEX_NAMES = ("CalcSuite.single", "NspireMirror.single")  # The second: versions before 1.0


def already_running():
    """One copy at a time: a second one would take the calculators away from the first, and
    both would go black. Checks the old app's name too (Nspire Mirror), and holds both so an
    old copy started later sees this one."""
    if os.name != "nt":
        return False
    import ctypes
    global _mutexes  # Kept for the life of the process
    _mutexes = []
    taken = False
    for name in MUTEX_NAMES:
        h = ctypes.windll.kernel32.CreateMutexW(None, False, name)
        if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            taken = True
        _mutexes.append(h)
    return taken


def main():
    if already_running():
        r = tk.Tk()
        r.withdraw()
        messagebox.showinfo(APP_NAME, "CalcSuite is already open.")
        return
    if getattr(sys, "frozen", False):
        migrate_documents()
        os.makedirs(os.path.join(KIT, "programs"), exist_ok=True)
    App().run()


if __name__ == "__main__":
    main()
