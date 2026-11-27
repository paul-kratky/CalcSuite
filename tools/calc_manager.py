"""The calculator manager: one window per Mirror window ("Files..." button).

- TI-Nspire: browse the folders, download files to the PC, upload (.py checked and turned into
  a .tns, or a .tns), new folder, rename, delete.
- TI-84 Plus CE: its variables, programs and apps; download as TI files (.8xp etc.), TI-Basic
  programs shown as text, upload TI files, delete.
- TI-89 Titanium: its variables by folder; download as TI files (.89p etc.), text and strings
  shown as text.
- About this calculator: model, OS, free space, and whether TI has a newer OS.

Every command goes through the Mirror's link thread (Mirror.queue), so the live picture keeps
running between them; nothing here talks to USB itself.
"""

import locale
import os
import tempfile
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, simpledialog, ttk

import calc_files as cf

BG, FG, DIM, BTN, BTN_ACTIVE, ACCENT = "#000000", "#ece9e2", "#9a968d", "#111113", "#1c1c1f", "#7fb4ff"
BUTTON = dict(bg=BTN, fg=FG, activebackground=BTN_ACTIVE, activeforeground="#ffffff",
              relief="flat", padx=10, pady=6, bd=0, disabledforeground="#55534e")
ENCODING = locale.getpreferredencoding(False)  # What nspire_link's pipes use


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
    def __init__(self, mirror, kit, prepare=None):
        """prepare(path) -> (file to send, None) or (None, why not): the Mirror's .py check"""
        self.m = mirror
        self.prepare = prepare or (lambda p: (p, None))
        self.calc = mirror.calc
        self.slug = mirror.calc.slug
        self.nspire = self.slug == "nspire"
        self.can_write = self.slug in ("nspire", "ti84")  # The 89: listing and downloads only
        self.dest = os.path.join(kit, "from-calc")
        self.cwd = "/"
        self.items = []
        self.open = True
        self.pending = 0
        self.about_win = None
        self.tmp = os.path.join(tempfile.gettempdir(), "calc_mirror_files_%d" % os.getpid())
        os.makedirs(self.tmp, exist_ok=True)

        win = self.win = tk.Toplevel(mirror.root)
        win.title("Files on the %s" % self.calc.title)
        win.configure(bg=BG)
        win.geometry("640x520")
        win.minsize(520, 360)
        win.protocol("WM_DELETE_WINDOW", self.close)

        style = ttk.Style(win)
        try:
            style.theme_use("clam")  # The one theme whose colours can all be set
        except tk.TclError:
            pass
        style.configure("Calc.Treeview", background="#0b0b0c", fieldbackground="#0b0b0c",
                        foreground=FG, rowheight=22, borderwidth=0)
        style.map("Calc.Treeview", background=[("selected", "#2b2b33")],
                  foreground=[("selected", "#ffffff")])
        style.configure("Calc.Treeview.Heading", background=BTN, foreground=FG, relief="flat")
        style.map("Calc.Treeview.Heading", background=[("active", BTN_ACTIVE)])
        style.configure("Calc.Vertical.TScrollbar", background=BTN, troughcolor=BG,
                        arrowcolor=FG, bordercolor=BG)

        top = tk.Frame(win, bg=BG)
        top.pack(fill="x", padx=12, pady=(12, 6))
        if self.nspire:
            self.up_btn = tk.Button(top, text="Up", command=self.go_up, **BUTTON)
            self.up_btn.pack(side="left")
        self.where = tk.StringVar(master=win)
        tk.Label(top, textvariable=self.where, bg=BG, fg=FG, anchor="w").pack(
            side="left", fill="x", expand=True, padx=8)
        tk.Button(top, text="About this calculator", command=self.about, **BUTTON).pack(side="right")

        mid = tk.Frame(win, bg=BG)
        mid.pack(fill="both", expand=True, padx=12)
        cols = ("type", "size", "where") if not self.nspire else ("type", "size")
        tree = self.tree = ttk.Treeview(mid, columns=cols, style="Calc.Treeview",
                                        selectmode="extended")
        tree.heading("#0", text="Name", anchor="w")
        tree.column("#0", width=300, anchor="w")
        tree.heading("type", text="Kind", anchor="w")
        tree.column("type", width=140, anchor="w")
        tree.heading("size", text="Size", anchor="e")
        tree.column("size", width=90, anchor="e")
        if not self.nspire:
            tree.heading("where", text="Stored in", anchor="w")
            tree.column("where", width=90, anchor="w")
        sb = ttk.Scrollbar(mid, orient="vertical", command=tree.yview,
                           style="Calc.Vertical.TScrollbar")
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        tree.bind("<Double-Button-1>", self.on_double)
        tree.bind("<Delete>", lambda e: self.delete())
        tree.bind("<Return>", self.on_double)

        bar = tk.Frame(win, bg=BG)
        bar.pack(fill="x", padx=12, pady=(8, 0))
        buttons = [("Refresh", self.refresh), ("Download...", self.download)]
        if not self.nspire:
            buttons.append(("Show as text", self.view_text))
        if self.can_write:
            buttons.append(("Upload...", self.upload))
        if self.nspire:
            buttons += [("New folder...", self.new_folder), ("Rename...", self.rename)]
        if self.can_write:
            buttons.append(("Delete", self.delete))
        for i, (text, cmd) in enumerate(buttons):
            tk.Button(bar, text=text, command=cmd, **BUTTON).pack(side="left", padx=(0 if i == 0 else 6, 0))
        tk.Button(bar, text="Open folder", command=self.open_dest, **BUTTON).pack(side="right")

        self.status = tk.StringVar(master=win, value="")
        tk.Label(win, textvariable=self.status, bg=BG, fg=DIM, anchor="w", justify="left",
                 wraplength=600).pack(fill="x", padx=12, pady=(8, 12))
        win.bind("<Configure>", lambda e: None)
        win.bind("<F5>", lambda e: self.refresh())
        self.refresh()

    # ---- Plumbing ----
    def alive(self):
        return self.open

    def lift(self):
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

    def job(self, line, done=None, what=None):
        """One command on the link thread; done(code, lines) back on the window's thread.
        `what` names a transfer whose progress the status line shows."""
        self.pending += 1
        if self.m.session is None:
            self.status.set("Waiting for the %s to connect..." % self.calc.title)

        def finished(code, lines):
            def back():
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
        elif not self.nspire:
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
        text_types = cf.TEXT_TYPES_89 if self.slug == "ti89" else cf.TEXT_TYPES_84
        if i["type"] not in text_types:
            self.status.set("%s is a %s: only programs, strings, equations and texts show as "
                            "text%s" % (i["text"], i["kind"].lower(),
                                        " (TI-89 programs are stored compiled)" if self.slug == "ti89" else ""))
            return
        if i["type"] == 0x06:
            self.status.set("%s is locked: shown anyway" % i["text"])

        def ok(raw, info):
            if self.slug == "ti89":
                text = cf.ti89_text(i["type"], raw) or ""
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
        paths = filedialog.askopenfilenames(
            parent=self.win, title="Send TI files to the %s" % self.calc.title,
            initialdir=self.dest,
            filetypes=[("TI-84 Plus files", "*.8xp *.8xv *.8xl *.8xm *.8xn *.8xs *.8xy *.8xc "
                        "*.8ci *.8ca *.8xd *.8xg"), ("All files", "*.*")])
        for p in paths:
            try:
                with open(p, "rb") as f:
                    entries = cf.read_ti8x(f.read())
            except (OSError, ValueError) as e:
                self.status.set("%s: %s" % (os.path.basename(p), e))
                continue
            for vtype, tname, version, archived, data in entries:
                if vtype in (0x13, 0x17, 0x23, 0x24, 0x25):
                    self.status.set("%s: backups, groups, apps and OS files can't be sent here"
                                    % os.path.basename(p))
                    continue
                name = cf.detokenize_name_84(tname, vtype)
                raw = name.encode("utf-8")
                same = [i for i in self.items if i["name"] == raw and i["type"] == vtype]
                if same and not messagebox.askyesno(
                        "Replace?", "%s is already on the calculator. Replace it?" % name, parent=self.win):
                    continue
                if same:
                    self.job("rm %02x %s" % (vtype, cf.to_hex(raw)))
                tmp = os.path.join(self.tmp, "up%d_%d.bin" % (id(entries), vtype))
                with open(tmp, "wb") as f:
                    f.write(data)
                self.job("put %02x %d %d %s %s" % (vtype, 1 if archived else 0, version,
                                                    cf.to_hex(raw), tmp),
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
                    else "rm %02x %s" % (i["type"], cf.to_hex(i["name"])))
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

    # ---- About this calculator ----
    def about(self):
        if self.about_win is not None:
            try:
                self.about_win.lift()
                return
            except tk.TclError:
                pass
        w = self.about_win = tk.Toplevel(self.win)
        w.title("About this calculator")
        w.configure(bg=BG)
        w.resizable(False, False)
        self.about_rows = tk.Frame(w, bg=BG)
        self.about_rows.pack(fill="x", padx=16, pady=(16, 8))
        self.os_line = tk.Frame(w, bg=BG)
        self.os_line.pack(fill="x", padx=16, pady=(0, 16))
        tk.Label(self.about_rows, text="Asking the calculator...", bg=BG, fg=DIM).pack(anchor="w")
        w.protocol("WM_DELETE_WINDOW", self.close_about)
        self.job("info", self.got_info)

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
        else:
            text, link = "TI has OS %s:" % cf.nice_version(self.slug, newest), "download page"
        tk.Label(line, text=text, bg=BG, fg=FG).pack(side="left")
        a = tk.Label(line, text=link, bg=BG, fg=ACCENT, cursor="hand2",
                     font=("Segoe UI", 9, "underline"))
        a.pack(side="left", padx=(6, 0))
        a.bind("<Button-1>", lambda e: webbrowser.open(url))
        if self.slug == "ti84" and have and new and have < (5, 5, 0) <= new:
            tk.Label(self.os_line, text="Note: OS 5.5 and later don't run assembly (ASM) programs.",
                     bg=BG, fg=DIM).pack(anchor="w", pady=(4, 0))
