"""The calculator manager: one window per Mirror window ("Files..." button).

- TI-Nspire: browse the folders, download files to the PC, upload (.py checked and turned into
  a .tns, or a .tns), new folder, rename, delete.
- TI-84 Plus CE: its variables, programs and apps; download as TI files (.8xp etc.), TI-Basic
  programs shown as text, upload TI files or TI-Basic text (send_ti.py), delete.
- TI-89 Titanium: its variables by folder; download as TI files (.89p etc.), text, strings and
  not-yet-run programs shown as text, upload TI files or TI-Basic text, delete.
- Back up... (everything the link can read, into Documents\CalcSuite\backups\<model>-<date>\)
  and Restore... (pick a backup, choose what goes back; asks before replacing a name), in
  calc_backup.py.
- About this calculator: model, OS, free space, whether TI has a newer OS, the calculator's
  clock against the PC's (84 and 89: "Set the clock to the PC's time"), and Exit Press-to-Test
  (TI's own way only: TI-Nspire CX II Connect for the Nspire, TI's steps for the 84).

Every command goes through the Mirror's link thread (Mirror.queue), so the live picture keeps
running between them; nothing here talks to USB itself.
"""

import datetime
import locale
import os
import tempfile
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, simpledialog, ttk

import calc_backup as cb
import calc_files as cf
import ui_theme as th

BG, FG, DIM, BTN, BTN_ACTIVE, ACCENT = th.BG, th.FG, th.DIM, th.PANEL2, th.ACTIVE, th.ACCENT
BUTTON = dict(th.BUTTON)
ENCODING = locale.getpreferredencoding(False)  # What nspire_link's pipes use
NSPIRE_CONNECT = "https://nspireconnect.ti.com"  # TI-Nspire CX II Connect (TI's web app)
TI84_TEST_MODE = ("https://education.ti.com/html/webhelp/eg_ti84plusce/en/content/eg_gsguide/"
                  "m_exams/exm_out_of_test_mode.HTML")


def shown(name):
    """A handheld's (UTF-8) name as the pipe decoded it -> readable text"""
    try:
        return name.encode(ENCODING, "surrogateescape").decode("utf-8")
    except (UnicodeError, LookupError):
        return name


def unique_path(folder, file_name):
    """folder/file_name, or folder/stem (2).ext when that is taken: never overwrites"""
    stem, ext = os.path.splitext(file_name)
    path, n = os.path.join(folder, file_name), 2
    while os.path.exists(path):
        path = os.path.join(folder, "%s (%d)%s" % (stem, n, ext))
        n += 1
    return path


def last_line(lines):
    ok = [l for l in lines if l.startswith(("OK", "ERR"))]
    return ok[-1] if ok else (lines[-1] if lines else "no answer")


def why(lines):
    """An ERR line without its tag, for the status line"""
    l = last_line(lines)
    return l[4:] if l.startswith("ERR ") else l


class Manager(object):
    def __init__(self, mirror, kit, prepare=None, parent=None, about_cb=None):
        """prepare(path) -> (file to send, None) or (None, why not): the Mirror's .py check.
        parent: a frame to build the file list in (the Files panel of the calculator's tab)
        instead of a window of its own; about_cb: what "About this calculator" does then."""
        self.m = mirror
        self.prepare = prepare or (lambda p: (p, None))
        self.calc = mirror.calc
        self.slug = mirror.calc.slug
        self.nspire = self.slug == "nspire"
        self.can_write = True  # Uploads and deletes on all three
        self.dest = os.path.join(kit, "from-calc")
        self.cwd = "/"
        self.items = []
        self.open = True
        self.pending = 0
        self.about_win = None
        self.embedded = parent is not None
        self.about_cb = about_cb
        self.tmp = os.path.join(tempfile.gettempdir(), "calc_mirror_files_%d" % os.getpid())
        os.makedirs(self.tmp, exist_ok=True)

        if self.embedded:
            win = self.win = tk.Frame(parent, bg=BG)
        else:
            win = self.win = tk.Toplevel(mirror.root)
            win.title("Files on the %s" % self.calc.title)
            win.configure(bg=BG)
            win.geometry("640x520")
            win.minsize(520, 360)
            win.protocol("WM_DELETE_WINDOW", self.close)
        th.style_ttk(win)
        pad = 0 if self.embedded else 12

        top = tk.Frame(win, bg=BG)
        top.pack(fill="x", padx=pad, pady=(pad, 6))
        if self.nspire:
            self.up_btn = tk.Button(top, text="Up", command=self.go_up, **BUTTON)
            self.up_btn.pack(side="left")
        self.where = tk.StringVar(master=win)
        tk.Label(top, textvariable=self.where, bg=BG, fg=FG, anchor="w").pack(
            side="left", fill="x", expand=True, padx=8)
        if not self.embedded:
            tk.Button(top, text="About this calculator", command=self.about, **BUTTON).pack(side="right")
        self.restore_btn = tk.Button(top, text="Restore...", command=self.restore, **BUTTON)
        self.restore_btn.pack(side="right", padx=(0, 6))
        self.backup_btn = tk.Button(top, text="Back up...", command=self.backup, **BUTTON)
        self.backup_btn.pack(side="right", padx=(0, 6))
        self.busy = None  # "backup" / "restore" while one runs

        mid = tk.Frame(win, bg=BG)
        mid.pack(fill="both", expand=True, padx=pad)
        cols = ("type", "size", "where") if not self.nspire else ("type", "size")
        tree = self.tree = ttk.Treeview(mid, columns=cols, style="Calc.Treeview",
                                        selectmode="extended")
        tree.heading("#0", text="Name", anchor="w")
        narrow = self.embedded
        tree.column("#0", width=170 if narrow else 300, anchor="w")
        tree.heading("type", text="Kind", anchor="w")
        tree.column("type", width=100 if narrow else 140, anchor="w")
        tree.heading("size", text="Size", anchor="e")
        tree.column("size", width=70 if narrow else 90, anchor="e")
        if not self.nspire:
            tree.heading("where", text="Stored in", anchor="w")
            tree.column("where", width=70 if narrow else 90, anchor="w")
        sb = ttk.Scrollbar(mid, orient="vertical", command=tree.yview,
                           style="Calc.Vertical.TScrollbar")
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        tree.bind("<Double-Button-1>", self.on_double)
        tree.bind("<Delete>", lambda e: self.delete())
        tree.bind("<Return>", self.on_double)

        bar = tk.Frame(win, bg=BG)
        bar.pack(fill="x", padx=pad, pady=(8, 0))
        buttons = [("Refresh", self.refresh), ("Download...", self.download)]
        if not self.nspire:
            buttons.append(("Show as text", self.view_text))
        if self.can_write:
            buttons.append(("Upload...", self.upload))
        if self.nspire:
            buttons += [("New folder...", self.new_folder), ("Rename...", self.rename)]
        if self.can_write:
            buttons.append(("Delete", self.delete))
        if self.embedded:  # Two rows in the narrow panel
            bar2 = tk.Frame(win, bg=BG)
            bar2.pack(fill="x", padx=pad, pady=(6, 0))
        else:
            bar2 = bar
        for i, (text, cmd) in enumerate(buttons):
            row = bar if (not self.embedded or i < 3) else bar2
            first = i == 0 or (self.embedded and i == 3)
            tk.Button(row, text=text, command=cmd, **BUTTON).pack(side="left", padx=(0 if first else 6, 0))
        tk.Button(bar2, text="Open folder", command=self.open_dest, **BUTTON).pack(side="right")

        self.status = tk.StringVar(master=win, value="")
        tk.Label(win, textvariable=self.status, bg=BG, fg=DIM, anchor="w", justify="left",
                 wraplength=420 if self.embedded else 600).pack(fill="x", padx=pad, pady=(8, pad))
        if not self.embedded:  # In the tab, F5 is the calculator's key
            win.bind("<F5>", lambda e: self.refresh())
        self.refresh()

    # ---- Plumbing ----
    def alive(self):
        return self.open

    def lift(self):
        if self.embedded:
            return
        self.win.deiconify()
        self.win.lift()
        self.win.focus_force()

    def close(self):
        self.open = False
        for w in (self.about_win, self.win):
            try:
                if w is not None:
                    w.destroy()
            except tk.TclError:
                pass

    def ui(self, fn, *args):
        """Runs fn on the window's thread (callbacks arrive on the link thread)"""
        if not self.open:
            return
        try:
            self.win.after(0, lambda: self.open and fn(*args))
        except (tk.TclError, RuntimeError):
            pass

    def say(self, text):
        self.ui(self.status.set, text)

    def waiting_text(self, doing):
        """What a request shows while it waits: the link runs it once the calculator is connected,
        so a calculator that isn't says so instead of looking stuck"""
        if self.m.session is not None:
            return doing
        problem = getattr(self.m, "link_problem", None)
        if problem:  # The last connect failed in a way the user can fix (the Nspire: replug)
            return "%s %s." % (doing.rstrip("."), problem[0].lower() + problem[1:])
        return ("%s waiting for the %s to connect (plugged in, switched on, no other program using "
                "it; Reconnect tries again)" % (doing.rstrip("."), self.calc.title))

    LATE_S = 8  # A request not answered by then says why it's still waiting (every 2 s after)

    @staticmethod
    def log_error(where, detail=None):
        """mirror.log_error (errors.log); never raises (the self-test swaps it for a fake)"""
        try:
            import mirror
            mirror.log_error(where, detail=detail)
        except Exception:
            pass

    def late_text(self, line, waited, logged):
        """What a request still waiting after `waited` seconds shows; the first time the link is
        connected but silent, errors.log gets a line too"""
        if self.m.session is None:
            return self.waiting_text("Waiting for an answer")
        if not logged[0]:
            logged[0] = True
            self.log_error("waiting for the %s" % self.calc.title,
                           detail="%r not answered after %d s" % (line.split(" ", 1)[0], waited))
        return ("No answer yet after %d s: the link is busy or stuck (CalcSuite restarts a link "
                "that stays silent for 2 minutes; Reconnect does it now)" % waited)

    def job(self, line, done=None, what=None, late=None, late_s=None):
        """One command on the link thread; done(code, lines) back on the window's thread.
        `what` names a transfer whose progress the status line shows. late(text): called on the
        window's thread while the answer is late_s (LATE_S) seconds or more overdue, with why."""
        self.pending += 1
        if self.m.session is None:
            self.status.set("Waiting for the %s to connect..." % self.calc.title)
        state = {"done": False}

        def finished(code, lines):
            def back():
                state["done"] = True
                self.pending -= 1
                if done is not None:
                    done(code, lines)
            self.ui(back)

        progress = None
        if what:
            t0 = [time.time()]

            def progress(n, total):
                if time.time() - t0[0] < 0.2 and n < total:
                    return
                t0[0] = time.time()
                pct = 100 * n // total if total else 0
                self.say("%s: %d%% (%s of %s)" % (what, min(pct, 100), cf.human_size(n),
                                                   cf.human_size(total)))
        self.m.queue(line, None, finished, progress)
        if late is not None:
            t0, logged = time.time(), [False]

            def check():
                if state["done"] or not self.open:
                    return
                try:
                    late(self.late_text(line, time.time() - t0, logged))
                    self.win.after(2000, check)
                except tk.TclError:
                    pass  # Its window was closed
            self.win.after(int((late_s or self.LATE_S) * 1000), check)

    def run_batch(self, cmds, timeout=900):
        """Runs [(line, progress)] on the link thread and waits for all of them: [(code,
        lines)]. For a worker thread only (never Tk's): the live picture goes on between
        batches."""
        results = [None] * len(cmds)
        left = [len(cmds)]
        ev = threading.Event()
        for k, (line, progress) in enumerate(cmds):
            def done(code, lines, k=k):
                results[k] = (code, lines)
                left[0] -= 1
                if left[0] == 0:
                    ev.set()
            self.m.queue(line, None, done, progress)
        t0 = time.time()
        while cmds and not ev.wait(0.5):
            if not self.m.running or time.time() - t0 > timeout:
                break
        return [r or (4, ["ERR no answer (the window closed, or the cable?)"]) for r in results]

    def selected(self):
        return [self.items[int(i)] for i in self.tree.selection()]

    def open_dest(self):
        os.makedirs(self.dest, exist_ok=True)
        try:
            os.startfile(self.dest)
        except (AttributeError, OSError) as e:
            self.status.set("Couldn't open %s: %s" % (self.dest, e))

    def pick_dest(self):
        os.makedirs(self.dest, exist_ok=True)
        d = filedialog.askdirectory(parent=self.win, title="Save to which folder?",
                                    initialdir=self.dest, mustexist=False)
        if not d:
            return None
        os.makedirs(d, exist_ok=True)
        self.dest = os.path.normpath(d)
        return self.dest

    # ---- The listing ----
    def refresh(self):
        if self.nspire:
            self.where.set("My Documents" + ("" if self.cwd == "/" else self.cwd.replace("/", " / ")))
            self.up_btn.configure(state="normal" if self.cwd != "/" else "disabled")
            self.status.set("Reading the folder...")
            cwd = self.cwd
            self.job("ls " + cwd, lambda code, lines: self.listed(cwd, code, lines))
        else:
            self.where.set("Variables, programs and apps")
            self.status.set("Reading the list...")
            self.job("ls", lambda code, lines: self.listed(None, code, lines))

    def listed(self, cwd, code, lines):
        if code:
            self.status.set("Couldn't read the list: %s" % why(lines))
            return
        if self.nspire:
            if cwd != self.cwd:
                return  # The user moved on meanwhile
            items = cf.parse_nspire_ls(lines)
        else:
            items = [i for i in cf.parse_dusb_ls(lines) if not (self.slug == "ti89" and i["type"] == 0x1F)]
            types = cf.TYPES_89 if self.slug == "ti89" else cf.TYPES_84
            for i in items:
                i["text"] = cf.name_text(i["name"])
                if self.slug == "ti89" and i["folder"]:
                    i["text"] = cf.name_text(i["folder"]) + "\\" + i["text"]
                i["kind"], i["ext"] = types.get(i["type"], ("Type %02X" % i["type"], None))
            order = {0x05: 0, 0x06: 0, 0x12: 0, 0x15: 1, 0x24: 9, 0x23: 9}
            items.sort(key=lambda i: (order.get(i["type"], 5), i["text"].lower()))
        self.items = items
        self.tree.delete(*self.tree.get_children())
        for k, i in enumerate(items):
            if self.nspire:
                vals = ("Folder", "") if i["dir"] else (self.kind_nspire(i["name"]), cf.human_size(i["size"]))
                self.tree.insert("", "end", iid=str(k), text=shown(i["name"]) + ("/" if i["dir"] else ""),
                                 values=vals)
            else:
                where = "Archive" if i["arch"] else "RAM"
                if i["type"] in (0x23, 0x24):
                    where = "Archive"
                self.tree.insert("", "end", iid=str(k), text=i["text"],
                                 values=(i["kind"], cf.human_size(i["size"]), where))
        free = self.m.info.get("storage_free")
        extra = ", %s free" % cf.human_size(int(free)) if free and free.isdigit() else ""
        self.status.set("%d item(s)%s" % (len(items), extra))

    @staticmethod
    def kind_nspire(name):
        ext = os.path.splitext(name)[1].lower()
        return {".tns": "TI-Nspire document", ".py": "Python", ".tco": "OS", ".tcc": "OS",
                ".tco2": "OS", ".tcc2": "OS", ".zip": "Archive", ".csv": "Table (CSV)",
                ".txt": "Text"}.get(ext, ext[1:].upper() + " file" if ext else "File")

    def on_double(self, ev=None):
        sel = self.selected()
        if len(sel) != 1:
            return
        if self.nspire and sel[0]["dir"]:
            self.cwd = self.cwd.rstrip("/") + "/" + sel[0]["name"]
            self.refresh()
        elif self.nspire:
            self.download()  # A document: save it to the PC
        else:
            self.view_text()

    def go_up(self):
        if self.cwd != "/":
            self.cwd = self.cwd.rsplit("/", 1)[0] or "/"
            self.refresh()

    def remote(self, name):
        return self.cwd.rstrip("/") + "/" + name

    # ---- Download ----
    def download(self):
        sel = self.selected()
        if not sel:
            self.status.set("Pick one or more files first")
            return
        if self.nspire:
            files = [i for i in sel if not i["dir"]]
            if not files:
                self.status.set("Folders aren't downloaded whole: open one and pick its files")
                return
        else:
            files = [i for i in sel if i["ext"]]
            if not files:
                self.status.set("Apps and the OS can't be downloaded here; pick variables or programs")
                return
        dest = self.pick_dest()
        if not dest:
            return
        state = {"left": len(files), "ok": 0, "errors": []}

        def one_done(name, ok, err=None):
            state["left"] -= 1
            if ok:
                state["ok"] += 1
            else:
                state["errors"].append("%s: %s" % (name, err))
            if state["left"] == 0:
                msg = "Saved %d file(s) in %s" % (state["ok"], dest)
                if state["errors"]:
                    msg += ". Not saved: " + "; ".join(state["errors"][:3])
                self.status.set(msg)
        for i in files:
            if self.nspire:
                self.get_nspire(i, dest, one_done)
            else:
                self.get_var(i, lambda raw, info, i=i: self.save_var(i, raw, info, dest, one_done),
                             lambda err, i=i: one_done(i["text"], False, err))

    def get_nspire(self, item, dest, one_done):
        name = shown(item["name"])
        local = unique_path(dest, name)
        part = local + ".part"

        def done(code, lines):
            if code == 0:
                try:
                    os.replace(part, local)
                    one_done(name, True)
                    return
                except OSError as e:
                    one_done(name, False, e)
                    return
            one_done(name, False, why(lines))
        self.job("get %s|%s" % (self.remote(item["name"]), part), done, "Downloading %s" % name)

    def get_var(self, item, ok, fail):
        """The variable's data from an 84/89; ok(raw bytes, {"arch", "version"}) or fail(why)"""
        raw_path = os.path.join(self.tmp, "var%d.bin" % id(item))
        line = "get %02x %s %s %d %s" % (item["type"], cf.to_hex(item["folder"]),
                                          cf.to_hex(item["name"]), item["size"], raw_path)

        def done(code, lines):
            if code:
                fail(why(lines))
                return
            info = {"arch": item["arch"], "version": 0}
            for l in lines:
                if l.startswith("OK got"):
                    for kv in l.split()[2:]:
                        k, _, v = kv.partition("=")
                        if k == "arch":
                            info["arch"] = v == "1"
                        elif k == "version" and v.isdigit():
                            info["version"] = int(v)
            try:
                with open(raw_path, "rb") as f:
                    raw = f.read()
                os.remove(raw_path)
            except OSError as e:
                fail(str(e))
                return
            ok(raw, info)
        self.job(line, done, "Downloading %s" % item["text"])

    def save_var(self, item, raw, info, dest, one_done):
        """Writes the TI file: the header and checksum TI's own software writes too"""
        try:
            if self.slug == "ti89":
                blob = cf.ti89_bytes(item["type"], item["folder"], item["name"], info["arch"], raw)
            else:
                name = cf.tokenize_name_84(item["text"], item["type"])
                blob = cf.ti8x_bytes([(item["type"], name, info["version"], info["arch"], raw)])
            path = unique_path(dest, cf.safe_file_name(cf.name_text(item["name"])) + "." + item["ext"])
            with open(path, "wb") as f:
                f.write(blob)
            one_done(item["text"], True)
        except (OSError, ValueError) as e:
            one_done(item["text"], False, e)

    # ---- TI-Basic / text ----
    def view_text(self):
        sel = self.selected()
        if len(sel) != 1:
            self.status.set("Pick one program, string or text")
            return
        i = sel[0]
        text_types = cf.TEXT_TYPES_89 + (0x12, 0x13) if self.slug == "ti89" else cf.TEXT_TYPES_84
        if i["type"] not in text_types:
            self.status.set("%s is a %s: only programs, strings, equations and texts show as "
                            "text" % (i["text"], i["kind"].lower()))
            return
        if i["type"] == 0x06:
            self.status.set("%s is locked: shown anyway" % i["text"])

        def ok(raw, info):
            if self.slug == "ti89" and i["type"] in (0x12, 0x13):
                text = cf.program_89_text(raw)
                if text is None:  # Run once: the 89 keeps it tokenized, which isn't read here
                    self.status.set("%s has run on the calculator, so the 89 keeps it compiled: "
                                    "its text can't be shown here (open it in the 89's Program "
                                    "Editor)" % i["text"])
                    return
            elif self.slug == "ti89":
                text = cf.ti89_text(i["type"], raw) or ""
            elif cf.is_compiled_84(raw):
                self.status.set("%s is a compiled (assembly or C) program: it has no TI-Basic text"
                                % i["text"])
                return
            else:
                text = cf.detokenize_84(raw)
            self.show_text(i, text)
            self.status.set("%s: %d line(s)" % (i["text"], text.count("\n") + 1))
        self.get_var(i, ok, lambda err: self.status.set("Couldn't read %s: %s" % (i["text"], err)))

    def show_text(self, item, text):
        w = tk.Toplevel(self.win)
        w.title(item["text"])
        w.configure(bg=BG)
        w.geometry("560x480")
        bar = tk.Frame(w, bg=BG)
        bar.pack(side="bottom", fill="x", padx=12, pady=(6, 12))
        box = tk.Text(w, bg="#0b0b0c", fg=FG, insertbackground=FG, relief="flat", wrap="none",
                      font=("Consolas", 11), padx=8, pady=8)
        box.pack(fill="both", expand=True, padx=12, pady=(12, 0))
        box.insert("1.0", text)
        box.configure(state="disabled")

        def save():
            os.makedirs(self.dest, exist_ok=True)
            p = filedialog.asksaveasfilename(
                parent=w, initialdir=self.dest, defaultextension=".txt",
                initialfile=cf.safe_file_name(item["text"]) + ".txt",
                filetypes=[("Text", "*.txt"), ("All files", "*.*")])
            if p:
                with open(p, "w", encoding="utf-8") as f:
                    f.write(text)
                note.set("Saved %s" % p)

        def copy():
            w.clipboard_clear()
            w.clipboard_append(text)
            note.set("Copied")
        tk.Button(bar, text="Save as .txt...", command=save, **BUTTON).pack(side="left")
        tk.Button(bar, text="Copy", command=copy, **BUTTON).pack(side="left", padx=6)
        note = tk.StringVar(master=w, value="Tokens this viewer doesn't know show as [hex]."
                            if self.slug != "ti89" else "")
        tk.Label(bar, textvariable=note, bg=BG, fg=DIM).pack(side="left", padx=6)

    # ---- Upload ----
    def upload(self):
        if self.nspire:
            paths = filedialog.askopenfilenames(
                parent=self.win, title="Upload to %s" % (self.where.get()),
                initialdir=os.path.join(os.path.dirname(self.dest), "programs"),
                filetypes=[("Python programs and TI documents", "*.py *.tns"), ("All files", "*.*")])
            names = {i["name"].lower() for i in self.items}
            for p in paths:
                tns, error = self.prepare(p)
                if error:
                    self.status.set("%s: %s" % (os.path.basename(p), error))
                    continue
                base = os.path.basename(tns)
                if base.lower() in names and not messagebox.askyesno(
                        "Replace?", "%s is already in this folder. Replace it?" % base, parent=self.win):
                    continue
                self.job("put %s|%s" % (os.path.abspath(tns), self.remote(base)),
                         lambda code, lines, b=base: self.uploaded(b, code, lines), "Uploading %s" % base)
            return
        # The 84 and the 89: TI files, or TI-Basic text made into a program (send_ti.py). A
        # variable of the same name is replaced by the send itself, after asking.
        import send_ti
        paths = filedialog.askopenfilenames(
            parent=self.win, title="Send to the %s" % self.calc.title,
            initialdir=self.dest,
            filetypes=[("TI files and TI-Basic text", send_ti.TI_EXTS[self.slug] + " *.txt *.tib *.bas"),
                       ("All files", "*.*")])
        for p in paths:
            ti, wanted = send_ti.prepare_asking(p, self.slug, self.win, self.tmp, self.status.set,
                                                simpledialog)
            if not ti:
                continue
            listing = ["ITEM type=%02x size=%d arch=0 locked=0 folder=%s name=%s"
                       % (i["type"], i["size"], cf.to_hex(i["folder"]), cf.to_hex(i["name"]))
                       for i in self.items]
            same = send_ti.clashes(wanted, listing, self.slug)
            if same and not messagebox.askyesno(
                    "Replace?", "%s %s already on the calculator. Replace?" % (
                        ", ".join(same), "is" if len(same) == 1 else "are"), parent=self.win):
                continue
            name = ", ".join(cf.name_text(n) for _f, n, _t in wanted)
            self.job("send " + os.path.abspath(ti),
                     lambda code, lines, n=name: self.uploaded(n, code, lines), "Sending %s" % name)

    def uploaded(self, name, code, lines):
        if code:
            self.status.set("%s not sent: %s" % (name, why(lines)))
            return
        self.status.set("Sent %s" % name)
        if self.pending == 0:
            self.refresh()

    # ---- Delete, new folder, rename ----
    def delete(self):
        if not self.can_write:
            self.status.set("Deleting on the %s isn't built yet" % self.calc.title)
            return
        sel = self.selected()
        if not sel:
            self.status.set("Pick what to delete first")
            return
        if not self.nspire:
            sel = [i for i in sel if i["type"] not in (0x23, 0x24, 0x25)]
            if not sel:
                self.status.set("Apps and the OS aren't deleted here (the calculator's own "
                                "memory menu does that)")
                return
        names = [shown(i["name"]) if self.nspire else i["text"] for i in sel]
        listing = "\n".join(names[:12]) + ("\n... and %d more" % (len(names) - 12) if len(names) > 12 else "")
        if not messagebox.askyesno("Delete from the calculator?",
                                   "Delete these from the %s? This can't be undone.\n\n%s"
                                   % (self.calc.title, listing), icon="warning", parent=self.win):
            return
        state = {"left": len(sel), "errors": []}

        def done(name, code, lines):
            state["left"] -= 1
            if code:
                state["errors"].append("%s: %s" % (name, why(lines)))
            if state["left"] == 0:
                self.refresh()
                if state["errors"]:
                    self.win.after(400, self.status.set, "Not deleted: " + "; ".join(state["errors"][:3]))
        for i, n in zip(sel, names):
            line = ("rm " + self.remote(i["name"]) if self.nspire
                    else "rm %02x %s %s" % (i["type"], cf.to_hex(i["name"]), cf.to_hex(i["folder"])))
            self.job(line, lambda code, lines, n=n: done(n, code, lines))

    def new_folder(self):
        name = simpledialog.askstring("New folder", "Folder name:", parent=self.win)
        if not name:
            return
        name = name.strip()
        if not name or "/" in name or "\\" in name:
            self.status.set("A folder name can't have / or \\ in it")
            return

        def done(code, lines):
            self.status.set("Folder %s made" % name if code == 0 else "Couldn't make it: %s" % why(lines))
            self.refresh()
        self.job("mkdir " + self.remote(name), done)

    def rename(self):
        sel = self.selected()
        if len(sel) != 1:
            self.status.set("Pick one file or folder to rename")
            return
        old = sel[0]["name"]
        new = simpledialog.askstring("Rename", "New name:", initialvalue=shown(old), parent=self.win)
        if not new or new.strip() == shown(old):
            return
        new = new.strip()
        if "/" in new or "\\" in new:
            self.status.set("A name can't have / or \\ in it")
            return
        if not sel[0]["dir"] and old.lower().endswith(".tns") and not new.lower().endswith(".tns"):
            new += ".tns"  # Without it the handheld doesn't show the document
        new_raw = new.encode("utf-8").decode(ENCODING, "surrogateescape")

        def done(code, lines):
            self.status.set("Renamed to %s" % new if code == 0 else "Couldn't rename: %s" % why(lines))
            self.refresh()
        self.job("mv %s|%s" % (self.remote(old), self.remote(new_raw)), done)

    # ---- Backup and restore (calc_backup.py) ----
    def set_busy(self, what):
        self.busy = what
        state = "disabled" if what else "normal"
        for b in (self.backup_btn, self.restore_btn):
            try:
                b.configure(state=state)
            except tk.TclError:
                pass

    def connected(self):
        if self.m.session is None:
            self.status.set("The %s isn't connected: switch it on (its window connects by itself)"
                            % self.calc.title)
            return False
        return True

    def backup(self):
        if self.busy or not self.connected():
            return
        folder = cb.new_backup_folder(self.slug)
        self.set_busy("backup")
        self.status.set("Backing up to %s..." % folder)

        def work():
            try:
                code, lines = self.run_batch([("info", None)])[0]
                import nspire_link
                info = nspire_link.info_dict(lines) if code == 0 else dict(self.m.info)
                man = cb.backup(self.slug, self.run_batch, info, folder, self.say)
                self.ui(self.backed_up, folder, man, None)
            except Exception as e:  # A backup must never take the window down
                self.ui(self.backed_up, folder, None, e)
        threading.Thread(target=work, daemon=True).start()

    def backed_up(self, folder, man, error):
        self.set_busy(None)
        if man is None:
            try:
                os.rmdir(folder)  # Only when nothing was saved in it
                where = ""
            except OSError:
                where = " (what was saved so far is in %s)" % folder
            self.status.set("Backup stopped: %s%s" % (error, where))
            return
        lines = cb.summary(man)
        self.status.set("Backed up %d item(s) to %s" % (len(man["items"]), folder))
        if messagebox.askyesno("Backup finished", "\n".join(lines) + "\n\nIn %s\n\nOpen the folder?"
                               % folder, parent=self.win):
            try:
                os.startfile(folder)
            except (AttributeError, OSError):
                pass

    def restore(self):
        if self.busy or not self.connected():
            return
        root = cb.backups_root()
        os.makedirs(root, exist_ok=True)
        folder = filedialog.askdirectory(parent=self.win, title="Restore which backup? (its folder)",
                                         initialdir=root, mustexist=True)
        if not folder:
            return
        try:
            man = cb.load(folder)
        except ValueError as e:
            self.status.set(str(e))
            return
        if man["calculator"]["slug"] != self.slug:
            self.status.set("That backup is of a %s, not this %s" % (man["calculator"]["model"],
                                                                     self.calc.title))
            return
        if not man["items"]:
            self.status.set("That backup has nothing in it to send")
            return
        RestoreDialog(self, folder, man)

    # ---- About this calculator ----
    def about(self):
        if self.about_cb is not None:  # In the tab: the Info panel
            self.about_cb()
            return
        if self.about_win is not None:
            try:
                self.about_win.lift()
                return
            except tk.TclError:
                pass
        w = tk.Toplevel(self.win)
        w.title("About this calculator")
        w.configure(bg=BG)
        w.resizable(False, False)
        w.protocol("WM_DELETE_WINDOW", self.close_about)
        self.build_about(w)

    def build_about(self, w):
        """The calculator's model, OS, free space, the OS update check, the clock and Exit
        Press-to-Test, built into w (a window, or the Info panel's frame)"""
        for c in w.winfo_children():
            c.destroy()
        self.about_win = w
        self.about_rows = tk.Frame(w, bg=BG)
        self.about_rows.pack(fill="x", padx=16, pady=(16, 8))
        self.os_line = tk.Frame(w, bg=BG)
        self.os_line.pack(fill="x", padx=16, pady=(0, 16))
        wait = tk.Label(self.about_rows, text=self.waiting_text("Asking the calculator..."), bg=BG,
                        fg=DIM, justify="left", wraplength=380)
        wait.pack(anchor="w")
        self.job("info", self.got_info, late=lambda text: wait.winfo_exists() and wait.configure(
            text="Asking the calculator... " + text))
        self.about_extras()

    # ---- The clock and Exit Press-to-Test (in About) ----
    def about_extras(self):
        """The clock row and the Exit Press-to-Test button, under the OS line"""
        w = self.about_win
        self.clock_line = tk.Frame(w, bg=BG)
        self.clock_line.pack(fill="x", padx=16, pady=(0, 8))
        bar = tk.Frame(w, bg=BG)
        bar.pack(fill="x", padx=16, pady=(0, 16))
        if self.nspire:
            tk.Label(self.clock_line, text="Clock: the handheld's clock can't be read or set over USB "
                     "(no known command for it); set it on the handheld (its Settings).", bg=BG,
                     fg=DIM, justify="left", wraplength=380).pack(anchor="w")
        else:
            self.clock_text = tk.StringVar(master=w, value=self.waiting_text("Clock: reading..."))
            tk.Label(self.clock_line, textvariable=self.clock_text, bg=BG, fg=FG, justify="left",
                     wraplength=380).pack(anchor="w")
            self.clock_btn = tk.Button(bar, text="Set the clock to the PC's time", command=self.set_clock,
                                       **BUTTON)
            self.clock_btn.pack(side="left", padx=(0, 6))
            self.job("clock", self.got_clock, late=self.clock_late)
        tk.Button(bar, text="Exit Press-to-Test...", command=self.exit_test_mode, **BUTTON).pack(side="left")
        # Clearing the calculator: both back up the whole calculator first
        erase = tk.Frame(w, bg=BG)
        erase.pack(fill="x", padx=16, pady=(0, 16))
        tk.Button(erase, text="Delete all documents..." if self.nspire else "Delete all programs...",
                  command=self.delete_all_programs, **BUTTON).pack(side="left", padx=(0, 6))
        tk.Button(erase, text="Reset the calculator...", command=self.reset_calculator,
                  **BUTTON).pack(side="left")

    def clock_late(self, text):
        self.clock_text.set("Clock: %s" % text)

    def got_clock(self, code, lines):
        if self.about_win is None:
            return
        import nspire_link
        pc = datetime.datetime.now().replace(microsecond=0)
        d = nspire_link.info_dict(lines)
        if code or "clock_date" not in d:
            self.clock_text.set("Clock: couldn't read it (%s)" % why(lines))
            return
        try:
            calc = datetime.datetime.strptime(d["clock_date"] + " " + d["clock_time"], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            self.clock_text.set("Clock: it reads %s %s" % (d["clock_date"], d["clock_time"]))
            return
        diff = int((calc - pc).total_seconds())
        if abs(diff) <= 2:
            how = "the same as the PC's"
        else:
            a = abs(diff)
            parts = [(a // 86400, "day"), (a % 86400 // 3600, "h"), (a % 3600 // 60, "min"), (a % 60, "s")]
            text = " ".join("%d %s%s" % (n, u, "s" if u == "day" and n > 1 else "") for n, u in parts if n)
            how = "%s %s the PC's (%s)" % (text, "ahead of" if diff > 0 else "behind",
                                           pc.strftime("%Y-%m-%d %H:%M:%S"))
        off = "" if d.get("on") != "0" else " (the calculator's clock display is off)"
        self.clock_text.set("Clock: %s, %s%s" % (calc.strftime("%Y-%m-%d %H:%M:%S"), how, off))

    def set_clock(self):
        self.clock_btn.configure(state="disabled")
        self.clock_text.set(self.waiting_text("Setting the clock..."))

        def done(code, lines):
            try:
                self.clock_btn.configure(state="normal")
            except tk.TclError:
                return
            if code:
                self.clock_text.set("Clock: not set (%s)" % why(lines))
                return
            self.job("clock", self.got_clock, late=self.clock_late)
        # "now": the PC's time when the link gets to it (a picture may be on its way first).
        # The TI-84 Plus CE takes about 1.5 s a field (ti84-cli: clock_write_field)
        self.job("setclock now", done, late_s=25,
                 late=lambda text: self.clock_text.set("Setting the clock... %s" % text))

    # ---- Delete all programs, reset (Info) ----
    # 84: Program and locked Program; 89: Program and Function; Nspire: every document (.tns/.py)
    PROGRAM_TYPES = {"ti84": (0x05, 0x06), "ti89": (0x12, 0x13)}
    # The calculator's own reset menus, one key at a time. TI-84 Plus CE (checked on OS 5.4):
    # 2nd MEM > 7:Reset... (tabs RAM / ARCHIVE / ALL) > 1:All RAM... or ALL 1:All Memory... >
    # RESET screen 1:No 2:Reset
    RESET_KEYS = {
        "ti84": {"ram": ["quit", "clear", "mem", "7", "1", "2"],
                 "all": ["quit", "clear", "mem", "7", "right", "right", "1", "2"]},
    }

    def programs_on_calc(self):
        """Worker thread: [(rm command, name shown)] for every program (document) on it"""
        if self.nspire:
            files, _folders, errors = cb.nspire_tree(self.run_batch)
            if errors and not files:
                raise OSError("couldn't read My Documents: %s" % errors[0][1])
            return [("rm " + path, cb.nspire_text(path).lstrip("/")) for path, _size in files
                    if path.lower().endswith((".tns", ".py"))]
        want = self.PROGRAM_TYPES[self.slug]
        out = []
        for i in cb.dusb_items(self.run_batch, self.slug):
            if i["type"] in want:
                name = (i["folder_text"] + "\\" if i["folder_text"] else "") + i["text"]
                out.append(("rm %02x %s %s" % (i["type"], cf.to_hex(i["name"]), cf.to_hex(i["folder"])),
                            name))
        return out

    def backup_first(self, then, what):
        """The whole calculator into a new backup folder, then then(folder) on the window's thread;
        a failed backup stops here"""
        folder = cb.new_backup_folder(self.slug)
        self.status.set("Backing up the whole %s first, into %s..." % (self.calc.title, folder))

        def work():
            try:
                code, lines = self.run_batch([("info", None)])[0]
                import nspire_link
                info = nspire_link.info_dict(lines) if code == 0 else dict(self.m.info)
                cb.backup(self.slug, self.run_batch, info, folder, self.say)
            except Exception as e:
                self.ui(self.status.set, "Backup failed, so nothing was %s: %s" % (what, e))
                self.ui(self.set_busy, None)
                return
            self.ui(then, folder)
        threading.Thread(target=work, daemon=True).start()

    def delete_all_programs(self):
        if self.busy or not self.connected():
            return
        self.set_busy("delete all")
        self.status.set("Looking for the programs...")

        def work():
            try:
                found = self.programs_on_calc()
            except Exception as e:
                self.ui(self.status.set, "Couldn't read the list: %s" % e)
                self.ui(self.set_busy, None)
                return
            self.ui(self.confirm_delete_all, found)
        threading.Thread(target=work, daemon=True).start()

    def confirm_delete_all(self, found):
        what = "documents" if self.nspire else "programs"
        if not found:
            self.status.set("No %s on the %s" % (what, self.calc.title))
            self.set_busy(None)
            return
        names = [n for _l, n in found]
        listing = "\n".join(names[:12]) + ("\n... and %d more" % (len(names) - 12) if len(names) > 12 else "")
        keep = ("Folders and other files stay." if self.nspire else
                "Apps, the OS and your other variables (lists, matrices, AppVars...) stay.")
        if not messagebox.askyesno(
                "Delete all %s?" % what,
                "Delete all %d %s from the %s?\n\n%s\n\n%s CalcSuite backs up the whole calculator "
                "first (CalcSuite files\\backups), so Restore... can bring them back."
                % (len(found), what, self.calc.title, listing, keep), icon="warning",
                parent=self.about_win or self.win):
            self.set_busy(None)
            self.status.set("Nothing deleted")
            return

        def after_backup(folder):
            def work():
                res = self.run_batch([(line, None) for line, _n in found])
                failed = [n for (code, _lines), (_l, n) in zip(res, found) if code]
                self.ui(self.deleted_all, len(found) - len(failed), failed, folder)
            threading.Thread(target=work, daemon=True).start()
        self.backup_first(after_backup, "deleted")

    def deleted_all(self, done, failed, folder):
        self.set_busy(None)
        msg = "Deleted %d; the backup is in %s" % (done, folder)
        if failed:
            msg += ". Not deleted: " + ", ".join(failed[:5])
        self.status.set(msg)
        try:
            self.refresh()
        except tk.TclError:
            pass

    def reset_calculator(self):
        """TI's own reset, pressed for you on the 84 (and later the 89); the Nspire's is on the
        handheld only"""
        parent = self.about_win or self.win
        if self.nspire:
            messagebox.showinfo(
                "Reset the TI-Nspire CX II",
                "TI lets the handheld reset only from the handheld itself, not over USB.\n\n"
                "To clear everything: with the handheld on, hold doc, enter and EE together, press "
                "the reset button on the back with a paper clip, keep holding the three keys until the "
                "Maintenance Menu shows, then choose Reset All (TI's guide: \"Maintenance Menu\").\n\n"
                "Back up first (Files > Back up...). To clear only your documents, use Delete all "
                "documents... here.", parent=parent)
            return
        keys = self.RESET_KEYS.get(self.slug)
        if not keys:
            messagebox.showinfo(
                "Reset the %s" % self.calc.title,
                "Not built for the %s yet. On the calculator: 2nd MEM (2nd 6), F1 Reset, then choose "
                "RAM, Flash ROM or All Memory. Back up first (Files > Back up...)." % self.calc.title,
                parent=parent)
            return
        if self.busy or not self.connected():
            return
        win = tk.Toplevel(parent)
        win.title("Reset the %s" % self.calc.title)
        win.configure(bg=BG)
        win.transient(parent)
        try:
            th.dark_title_bar_when_shown(win)
        except Exception:
            pass
        choice = tk.StringVar(master=win, value="ram")
        tk.Label(win, text="Reset the %s with its own reset menu (CalcSuite presses the keys)."
                 % self.calc.title, bg=BG, fg=FG, justify="left", wraplength=420).pack(
            anchor="w", padx=16, pady=(16, 8))
        for val, text in (("ram", "Clear RAM: programs, variables and settings in RAM. Archived "
                                  "programs and apps stay."),
                          ("all", "Everything (like new): RAM and Archive, programs and apps. Only "
                                  "the OS stays.")):
            tk.Radiobutton(win, text=text, variable=choice, value=val, bg=BG, fg=FG, selectcolor=BG,
                           activebackground=BG, activeforeground=FG, justify="left", wraplength=400,
                           anchor="w").pack(fill="x", padx=16, pady=2)
        tk.Label(win, text="CalcSuite backs up the whole calculator first (CalcSuite files\\backups). "
                 "Type RESET to go ahead:", bg=BG, fg=DIM, justify="left", wraplength=420).pack(
            anchor="w", padx=16, pady=(10, 4))
        typed = tk.StringVar(master=win)
        entry = tk.Entry(win, textvariable=typed, bg="#1a1a1a", fg=FG, insertbackground=FG, relief="flat")
        entry.pack(fill="x", padx=16)
        row = tk.Frame(win, bg=BG)
        row.pack(fill="x", padx=16, pady=16)
        go = tk.Button(row, text="Back up and reset", state="disabled", **BUTTON)
        go.pack(side="right")
        tk.Button(row, text="Cancel", command=win.destroy, **BUTTON).pack(side="right", padx=(0, 6))
        typed.trace_add("write", lambda *a: go.configure(
            state="normal" if typed.get().strip().upper() == "RESET" else "disabled"))

        def start():
            seq = keys[choice.get()]
            win.destroy()
            self.set_busy("reset")

            def after_backup(folder):
                self.status.set("Backed up to %s. Resetting the %s..." % (folder, self.calc.title))

                def work():
                    for name in seq:
                        code = self.calc.resolve(name)
                        self.run_batch([("key " + self.calc.key_fmt % code, None)])
                        time.sleep(0.7)  # Each menu draws before the next key
                    self.ui(self.set_busy, None)
                    self.ui(self.status.set, "Reset sent. The %s starts again; its backup is in %s"
                            % (self.calc.title, folder))
                threading.Thread(target=work, daemon=True).start()
            self.backup_first(after_backup, "reset")
        go.configure(command=start)
        entry.focus_set()

    def exit_test_mode(self):
        """TI's own ways out of Press-to-Test: CalcSuite sends no test-mode command"""
        title = "Exit Press-to-Test"
        if self.nspire:
            if not messagebox.askokcancel(
                    title, "TI's TI-Nspire CX II Connect (a web page, in Chrome or Edge) takes the "
                    "handheld out of Press-to-Test.\n\nOnly one program can use the handheld, so "
                    "CalcSuite lets go of it now and opens TI's page: connect the handheld there and "
                    "choose Exit Press-to-Test. When you're done, close TI's page and press Reconnect "
                    "(the %s tab, Info)." % self.calc.title, parent=self.about_win or self.win):
                return
            self.m.release()
            webbrowser.open(NSPIRE_CONNECT)
            self.status.set("Let go of the handheld for TI-Nspire CX II Connect: press Reconnect in "
                            "CalcSuite afterwards")
            return
        if self.slug == "ti84":
            if messagebox.askyesno(
                    title, "TI's ways to bring a TI-84 Plus CE out of Press-to-Test (TI's \"Getting "
                    "Started with the TI-84 Plus CE\", Bringing a Calculator Out of Test Mode, p. 60):"
                    "\n\n- Link it to another TI-84 Plus CE with a unit-to-unit USB cable and send it a "
                    "file (2nd LINK, SEND RECEIVE).\n- In TI Connect CE: Actions > Quit Exam Mode on "
                    "Connected CE Calculators.\n- Send it a calculator file with TI Connect CE.\n\n"
                    "TI Connect CE needs TI's own driver, not WinUSB, and CalcSuite must be closed "
                    "while it runs.\n\nOpen TI's page with these steps?", parent=self.about_win or self.win):
                webbrowser.open(TI84_TEST_MODE)
            return
        messagebox.showinfo(
            title, "The TI-89 Titanium has no Press-to-Test mode: TI's TI-89 Titanium guidebook has "
            "none (TI's Press-to-Test is on the TI-84 Plus family and the TI-Nspire), so there is "
            "nothing to exit.", parent=self.about_win or self.win)

    def close_about(self):
        try:
            self.about_win.destroy()
        except tk.TclError:
            pass
        self.about_win = None

    def got_info(self, code, lines):
        import nspire_link
        if self.about_win is None:
            return
        d = nspire_link.info_dict(lines) if code == 0 else dict(self.m.info)
        if code == 0:
            self.m.info = d
        for c in self.about_rows.winfo_children():
            c.destroy()
        if not d:
            tk.Label(self.about_rows, text="The calculator didn't answer: %s" % why(lines),
                     bg=BG, fg=FG).pack(anchor="w")
            return
        # The Nspire reports the handheld's own name (its owner can change it)
        rows = [("Name" if self.nspire else "Model", d.get("name", self.calc.title).replace("_", " "))]
        if "os" in d:
            rows.append(("OS", d["os"]))
        if d.get("storage_free", "").isdigit():
            free = cf.human_size(int(d["storage_free"]))
            if d.get("storage_total", "").isdigit():
                free += " of %s" % cf.human_size(int(d["storage_total"]))
            rows.append(("Free storage" if self.nspire else "Free archive", free))
        if d.get("ram_free", "0").isdigit() and int(d.get("ram_free", "0")) > 0:
            rows.append(("Free RAM", cf.human_size(int(d["ram_free"]))))
        if d.get("battery") and d["battery"] != "unknown":
            rows.append(("Battery", d["battery"] + (", charging" if d.get("charging") == "1" else "")))
        for k, v in rows:
            r = tk.Frame(self.about_rows, bg=BG)
            r.pack(fill="x", anchor="w")
            tk.Label(r, text=k, width=14, anchor="w", bg=BG, fg=DIM).pack(side="left")
            tk.Label(r, text=v, anchor="w", bg=BG, fg=FG).pack(side="left")
        page = cf.os_page_for(self.slug, d)
        for c in self.os_line.winfo_children():
            c.destroy()
        if page is None:
            tk.Label(self.os_line, text="OS updates: no TI page known for this model", bg=BG,
                     fg=DIM).pack(anchor="w")
            return
        msg = tk.Label(self.os_line, text="Checking TI's website for a newer OS...", bg=BG, fg=DIM)
        msg.pack(anchor="w")
        installed = d.get("os", "")

        def work():
            newest, url = cf.newest_os(page)
            self.ui(self.show_update, installed, newest, url)
        threading.Thread(target=work, daemon=True).start()

    def show_update(self, installed, newest, url):
        if self.about_win is None:
            return
        for c in self.os_line.winfo_children():
            c.destroy()
        line = tk.Frame(self.os_line, bg=BG)
        line.pack(anchor="w")
        have = cf.version_tuple(self.slug, installed)
        new = cf.version_tuple(self.slug, newest)
        if new is None or have is None:
            text, link = "Couldn't check for a newer OS:", "TI's download page"
        elif have >= new:
            text, link = "Up to date (%s)." % installed, "TI's page"
        elif self.slug == "ti84" and have < (5, 5, 0) <= new:
            # An 84 CE that still runs assembly: TI's update blocks it (the arTIfiCE jailbreak plus
            # Cesium brings it back, re-run after every RAM reset) and the CE can't go back to an
            # older OS, so this is a warning, not an offer
            text, link = ("Keep OS %s if you can: TI's newer OS %s blocks assembly and C programs "
                          "(the arTIfiCE jailbreak and Cesium bring them back, re-run after every "
                          "RAM reset), and the 84 CE can't go back to an older OS."
                          % (installed, cf.nice_version(self.slug, newest)), None)
        else:
            text, link = "TI has OS %s:" % cf.nice_version(self.slug, newest), "download page"
        tk.Label(line, text=text, bg=BG, fg=FG if link else th.ACCENT, wraplength=420,
                 justify="left").pack(side="left")
        if link:
            a = tk.Label(line, text=link, bg=BG, fg=th.MINT, cursor="hand2",
                         font=("Segoe UI", 9, "underline"))
            a.pack(side="left", padx=(6, 0))
            a.bind("<Button-1>", lambda e: webbrowser.open(url))


class RestoreDialog(object):
    """Shows what's in a backup and what's on the calculator already; sends what's picked"""

    def __init__(self, mgr, folder, man):
        self.mgr, self.man, self.slug = mgr, man, mgr.slug
        w = self.win = tk.Toplevel(mgr.win)
        w.title("Restore to the %s" % mgr.calc.title)
        w.configure(bg=BG)
        w.geometry("640x480")
        tk.Label(w, text="\n".join(cb.summary(man)), bg=BG, fg=FG, justify="left", anchor="w",
                 wraplength=600).pack(fill="x", padx=12, pady=(12, 4))
        tk.Label(w, text="Picked rows are sent (Ctrl+click or Shift+click to change). Nothing else "
                 "on the calculator is touched.", bg=BG, fg=DIM, anchor="w", justify="left",
                 wraplength=600).pack(fill="x", padx=12)
        mid = tk.Frame(w, bg=BG)
        mid.pack(fill="both", expand=True, padx=12, pady=6)
        tree = self.tree = ttk.Treeview(mid, columns=("kind", "size", "there"), style="Calc.Treeview",
                                        selectmode="extended")
        for col, text, width, anchor in (("#0", "Name", 260, "w"), ("kind", "Kind", 120, "w"),
                                         ("size", "Size", 80, "e"), ("there", "On the calculator", 130, "w")):
            tree.heading(col, text=text, anchor=anchor)
            tree.column(col, width=width, anchor=anchor)
        sb = ttk.Scrollbar(mid, orient="vertical", command=tree.yview, style="Calc.Vertical.TScrollbar")
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.items = man["items"]
        for k, i in enumerate(self.items):
            tree.insert("", "end", iid=str(k), text=cb.item_label(self.slug, i),
                        values=(i.get("kind", mgr.kind_nspire(i["path"]) if self.slug == "nspire" else ""),
                                cf.human_size(i["size"]), "checking..."))
        tree.selection_set(tree.get_children())
        bar = tk.Frame(w, bg=BG)
        bar.pack(fill="x", padx=12, pady=(0, 6))
        self.send_btn = tk.Button(bar, text="Send picked", command=self.send, state="disabled", **BUTTON)
        self.send_btn.pack(side="left")
        tk.Button(bar, text="Close", command=w.destroy, **BUTTON).pack(side="right")
        self.note = tk.StringVar(master=w, value="Reading what's on the calculator...")
        tk.Label(w, textvariable=self.note, bg=BG, fg=DIM, anchor="w", justify="left",
                 wraplength=600).pack(fill="x", padx=12, pady=(0, 12))
        self.there = []  # For each row: is that name on the calculator now?

        def work():
            try:
                there = cb.on_calculator(self.slug, mgr.run_batch, man)
                mgr.ui(self.checked, there, None)
            except Exception as e:
                mgr.ui(self.checked, None, e)
        threading.Thread(target=work, daemon=True).start()

    def alive(self):
        try:
            return bool(self.win.winfo_exists())
        except tk.TclError:
            return False

    def checked(self, there, error):
        if not self.alive():
            return
        if there is None:
            self.note.set("Couldn't read what's on the calculator: %s" % error)
            return
        self.there = there
        for k, t in enumerate(there):
            self.tree.set(str(k), "there", "already there" if t else "")
        n = sum(1 for t in there if t)
        self.note.set("%d of %d already on the calculator (you'll be asked before any is replaced)"
                      % (n, len(self.items)) if n else "None of these is on the calculator now")
        self.send_btn.configure(state="normal")

    def send(self):
        rows = [int(k) for k in self.tree.selection()]
        if not rows:
            self.note.set("Pick what to send first")
            return
        if len(self.there) != len(self.items):
            self.note.set("Still reading what's on the calculator")
            return
        picked = [self.items[k] for k in rows]
        same = ["%s (%s)" % (cb.item_label(self.slug, self.items[k]), self.items[k].get("kind", "file"))
                for k in rows if self.there[k]]
        if same:
            listing = "\n".join(same[:12]) + ("\n... and %d more" % (len(same) - 12) if len(same) > 12 else "")
            ans = messagebox.askyesnocancel(
                "Replace?", "%d of these %s already on the %s:\n\n%s\n\nYes: replace them with the "
                "backup's. No: send only the others. Cancel: send nothing."
                % (len(same), "is" if len(same) == 1 else "are", self.mgr.calc.title, listing),
                icon="warning", parent=self.win)
            if ans is None:
                return
            if not ans:
                picked = [self.items[k] for k in rows if not self.there[k]]
                if not picked:
                    self.note.set("Nothing sent: everything picked is already there")
                    return
        mgr = self.mgr
        if mgr.busy:
            self.note.set("Wait for the %s to finish" % mgr.busy)
            return
        mgr.set_busy("restore")
        self.send_btn.configure(state="disabled")
        say = lambda t: (mgr.say(t), mgr.ui(lambda: self.alive() and self.note.set(t)))

        def work():
            try:
                sent, failed = cb.restore(self.slug, mgr.run_batch, self.man, cb.with_safe_paths(picked), say)
                mgr.ui(self.done, sent, failed, None)
            except Exception as e:
                mgr.ui(self.done, [], [], e)
        threading.Thread(target=work, daemon=True).start()

    def done(self, sent, failed, error):
        self.mgr.set_busy(None)
        text = ("Restore stopped: %s" % error if error else
                "Sent %d item(s)%s" % (len(sent), ". Not sent: " + "; ".join("%s (%s)" % f for f in failed[:4])
                                       if failed else ""))
        self.mgr.status.set(text)
        if self.alive():
            self.note.set(text)
            self.send_btn.configure(state="normal")
        self.mgr.refresh()
