"""Nspire Mirror: the handheld's screen in a window, with your keyboard as its keypad.

    python -I tools/mirror.py            (or double-click "Nspire Mirror.bat")

- The picture refreshes as fast as the handheld sends it (a few frames a second).
- Type on the PC keyboard: letters, digits, + - * / ^ ( ) = , . and Enter, Esc, Tab,
  Backspace and the arrows go to the handheld. Ctrl+letter is the handheld's ctrl+letter.
  F1 Home, F2 Menu, F3 Doc, F4 Catalog, F5 Var.
- Mouse over the picture: the wheel is up/down (Shift+wheel left/right), a click is the
  centre click key, a double click Enter, a right click the context menu (ctrl+menu), a
  middle click Menu. The handheld's pointer itself can't be moved from the PC, so a few
  spots are shortcuts: a click on the X (top right) closes the document (ctrl+W), on the
  left page arrow goes to the previous page, on the page tabs to the next page.
- Buttons: Screenshot (a PNG in captures/), Send program (a .py or .tns from the PC),
  and Keyboard on/off.

The window connects by itself when the handheld is plugged in and switched on, and again
after the cable has been out.

Key presses use the handheld's key service with codes captured on early Nspire models; a
CX II on a current OS may ignore some or all of them (the status line says what was sent).
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
import nspire_link  # noqa: E402
import nspire_keys  # noqa: E402

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

# Tk key names -> handheld key names (nspire_keys.NAMED)
TK_KEYS = {
    "Return": "enter", "KP_Enter": "enter", "Escape": "esc", "Tab": "tab",
    "BackSpace": "backspace", "Left": "left", "Right": "right", "Up": "up", "Down": "down",
    "F1": "home", "F2": "menu", "F3": "doc", "F4": "catalog", "F5": "var",
}


class Mirror(object):
    def __init__(self, root):
        self.root = root
        root.title("Nspire Mirror")
        root.configure(bg="#000000")
        self.session = None
        self.jobs = []          # Commands for the link thread (key presses, uploads)
        self.jobs_lock = threading.Lock()
        self.running = True
        self.want_reconnect = False
        self.keys_on = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value="Connecting...")
        self.photo = None
        self.frame_path = os.path.join(tempfile.gettempdir(), "nspire_mirror_%d.ppm" % os.getpid())
        self.frames = 0
        self.t0 = time.time()

        self.canvas = tk.Label(root, bg="#000000", width=320 * SCALE, height=240 * SCALE,
                               image=tk.PhotoImage(width=320 * SCALE, height=240 * SCALE))
        self.canvas.pack(padx=12, pady=(12, 6))
        bar = tk.Frame(root, bg="#000000")
        bar.pack(fill="x", padx=12)
        style = dict(bg="#111113", fg="#ece9e2", activebackground="#1c1c1f",
                     activeforeground="#ffffff", relief="flat", padx=10, pady=6, bd=0)
        tk.Button(bar, text="Screenshot", command=self.screenshot, **style).pack(side="left")
        tk.Button(bar, text="Send program...", command=self.send_program, **style).pack(
            side="left", padx=6)
        tk.Button(bar, text="Reconnect", command=self.reconnect, **style).pack(side="left")
        tk.Checkbutton(bar, text="Keyboard", variable=self.keys_on, bg="#000000", fg="#ece9e2",
                       selectcolor="#111113", activebackground="#000000",
                       activeforeground="#ffffff").pack(side="right")
        tk.Label(root, textvariable=self.status, bg="#000000", fg="#9a968d", anchor="w",
                 justify="left", wraplength=320 * SCALE).pack(fill="x", padx=12, pady=(6, 10))

        root.bind("<Key>", self.on_key)
        # The mouse, as keys (the link has no way to place the handheld's pointer):
        # wheel = up/down, Shift+wheel = left/right, left click = the centre click key,
        # right click = the context menu (ctrl+menu), middle click = menu
        self.canvas.bind("<MouseWheel>", self.on_wheel)
        self.canvas.bind("<Button-1>", self.on_click)
        self.canvas.bind("<Double-Button-1>", lambda e: self.send_key("enter"))
        self.canvas.bind("<Button-3>", lambda e: self.send_key("ctrl+menu"))
        self.canvas.bind("<Button-2>", lambda e: self.send_key("menu"))
        root.protocol("WM_DELETE_WINDOW", self.quit)
        threading.Thread(target=self.link_loop, daemon=True).start()
        self.root.after(100, self.show_frame)

    # ---- The link thread: the only one that talks to the handheld ----
    def link_loop(self):
        while self.running:
            if self.session is None:
                try:
                    self.session = nspire_link.Session()
                    code, lines = self.session.cmd("info")
                    d = nspire_link.info_dict(lines)
                    self.set_status("Connected: %s, OS %s" % (d.get("name", "?"), d.get("os", "?")))
                except nspire_link.LinkError:
                    self.session = None
                    self.set_status("Looking for the handheld... (plugged in, switched on, "
                                    "TI's own software closed)")
                    self.wait_reconnect(2.0)  # Tries again by itself
                    continue
            with self.jobs_lock:
                jobs, self.jobs = self.jobs, []
            # Key presses that queued up while a picture was coming go out as one command
            merged = []
            for line, note in jobs:
                if line.startswith("key ") and merged and merged[-1][0].startswith("keys "):
                    merged[-1] = (merged[-1][0] + " " + line[4:], note)
                elif line.startswith("key "):
                    merged.append(("keys " + line[4:], note))
                else:
                    merged.append((line, note))
            for line, note in merged:
                code, lines = self.session.cmd(line)
                if note:
                    ok = [l for l in lines if l.startswith(("OK", "ERR"))]
                    self.set_status("%s: %s" % (note, ok[-1] if ok else "exit %d" % code))
                if code == 4 and self.link_dead():
                    break
            if self.session is None:
                continue
            tmp = self.frame_path + ".new"
            code, lines = self.session.cmd("shot " + tmp)
            if code == 0:
                try:
                    os.replace(tmp, self.frame_path)
                    self.frames += 1
                    self.root.after(0, self.draw_frame)  # Shown at once, not at the next tick
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
        if self.session is not None:
            self.session.close()
            self.session = None
        self.want_reconnect = True
        self.set_status("Connecting...")

    def queue(self, line, note=None):
        with self.jobs_lock:
            self.jobs.append((line, note))

    def set_status(self, text):
        self.root.after(0, self.status.set, text)

    # ---- The window ----
    def draw_frame(self):
        if self.running and os.path.isfile(self.frame_path):
            try:
                img = tk.PhotoImage(file=self.frame_path)
                if SCALE > 1:
                    img = img.zoom(SCALE, SCALE)
                self.photo = img
                self.canvas.configure(image=img)
            except tk.TclError:
                pass  # Caught mid-write: the next frame has it

    def show_frame(self):
        if not self.running:
            return
        dt = time.time() - self.t0
        if dt >= 5 and self.frames:
            self.root.title("Nspire Mirror  -  %.1f frames/s" % (self.frames / dt))
            self.frames, self.t0 = 0, time.time()
        self.root.after(1000, self.show_frame)

    def on_key(self, ev):
        if not self.keys_on.get() or self.session is None:
            return
        ctrl = bool(ev.state & 0x4)
        name = TK_KEYS.get(ev.keysym)
        if name is None and ev.char and ev.char.isprintable():
            name = ev.char
        if ctrl:
            key = ev.keysym.lower() if len(ev.keysym) == 1 else (name or "")
            name = "ctrl+" + key
        if not name:
            return
        code = nspire_keys.code_for(name)
        if code is None:
            self.set_status("No handheld key for %r" % name)
            return
        self.queue("key %06x" % code, "Key %s" % name)

    def send_key(self, name):
        if not self.keys_on.get() or self.session is None:
            return
        code = nspire_keys.code_for(name)
        if code is not None:
            self.queue("key %06x" % code, "Key %s" % name)

    def on_click(self, ev):
        """The pointer can't be placed, so known spots of the screen send the key that does
        the same job; anywhere else is the centre click key"""
        ox = (self.canvas.winfo_width() - 320 * SCALE) // 2
        oy = (self.canvas.winfo_height() - 240 * SCALE) // 2
        x, y = (ev.x - ox) // SCALE, (ev.y - oy) // SCALE
        if y < 24 and x >= 292:
            self.send_key("ctrl+w")      # The X: close the document
        elif y < 24 and x < 14:
            self.send_key("ctrl+left")   # The left page arrow
        elif y < 24 and x < 100:
            self.send_key("ctrl+right")  # The page tabs and the right arrow: next page
        else:
            self.send_key("click")

    def on_wheel(self, ev):
        if not self.keys_on.get() or self.session is None:
            return
        steps = max(1, min(5, abs(ev.delta) // 120))
        if ev.state & 0x1:  # Shift: sideways
            name = "left" if ev.delta > 0 else "right"
        else:
            name = "up" if ev.delta > 0 else "down"
        with self.jobs_lock:  # A spinning wheel never queues more than a screenful
            if len(self.jobs) > 12:
                return
        for _ in range(steps):
            self.send_key(name)

    def screenshot(self):
        if not os.path.isfile(self.frame_path):
            self.set_status("No picture yet")
            return
        os.makedirs(os.path.join(KIT, "captures"), exist_ok=True)
        out = os.path.join(KIT, "captures", time.strftime("nspire-%Y%m%d-%H%M%S.png"))
        try:
            nspire_link.ppm_to_png(self.frame_path, out, 2)
            self.set_status("Saved %s" % out)
        except (OSError, ValueError) as e:
            self.set_status("Couldn't save: %s" % e)

    def send_program(self):
        path = filedialog.askopenfilename(
            title="Send to the handheld", initialdir=os.path.join(KIT, "programs"),
            filetypes=[("Python programs and TI documents", "*.py *.tns"), ("All files", "*.*")])
        if not path:
            return
        if path.lower().endswith(".py"):
            # The same check and conversion as tools/flash.py, in this process
            errors = [f for f in check_nspire.check_file(path, set()) if f.level == "ERROR"]
            if errors:
                f = errors[0]
                more = " (+%d more)" % (len(errors) - 1) if len(errors) > 1 else ""
                self.set_status("Not sent, line %d: %s%s. Fix: %s" % (f.line, f.message, more, f.fix))
                return
            try:
                tns = py2tns.convert(path, quiet=True)
            except py2tns.TnsError as e:
                self.set_status("Not sent: %s" % e)
                return
            path = tns
        self.queue("put %s|/%s" % (os.path.abspath(path), os.path.basename(path)),
                   "Send %s" % os.path.basename(path))

    def quit(self):
        self.running = False
        self.want_reconnect = True
        if self.session is not None:
            self.session.close()
        try:
            os.remove(self.frame_path)
        except OSError:
            pass
        self.root.destroy()


def main():
    root = tk.Tk()
    Mirror(root)
    root.mainloop()


if __name__ == "__main__":
    main()
