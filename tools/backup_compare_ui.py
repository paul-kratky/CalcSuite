"""The Compare window of the Files panel: two backups of this calculator (or a backup and the
calculator now) side by side, what was added, removed and changed, a program's text diff, and
"Restore this one" for a single item. The logic is backup_compare.py; this is only the window.

Everything that talks to the calculator goes through the Manager (its run_batch, on the
mirror's link thread) from a worker thread; window work comes back with after(). MIT licence.
"""

import threading
import tkinter as tk
from tkinter import messagebox, ttk

import backup_compare as bc
import calc_backup as cb
import calc_files as cf
import ui_theme as th

NOW_READ = "The calculator now (reads everything: exact, slower)"
NOW_LIST = "The calculator now (names and sizes only: quick)"
TAG_COLOURS = {bc.ADDED: th.MINT, bc.REMOVED: th.RED, bc.CHANGED: th.ACCENT, bc.SAME: th.DIM,
               bc.SAME_SIZE: th.FG}


def log_error(where):
    try:
        import mirror
        mirror.log_error(where)
    except Exception:
        pass


def option_menu(parent, var, values, command=None):
    """A dark drop-down list of texts"""
    m = tk.OptionMenu(parent, var, *values, command=command)
    m.configure(bg=th.PANEL2, fg=th.FG, activebackground=th.ACTIVE, activeforeground="#ffffff",
                highlightthickness=0, relief="flat", bd=0, anchor="w", cursor="hand2")
    m["menu"].configure(bg=th.PANEL2, fg=th.FG, activebackground=th.ACCENT,
                        activeforeground="#000000", bd=0)
    return m


class CompareDialog(object):
    def __init__(self, mgr, root=None):
        """mgr: the calculator's calc_manager.Manager (its slug, run_batch, ui, busy).
        root: the backups folder (default CalcSuite files\\backups; the self-test's own)"""
        self.mgr, self.slug, self.root = mgr, mgr.slug, root
        self.title = mgr.calc.title
        self.backups = bc.list_backups(self.slug, root)
        self.mans = {"before": None, "after": None}  # The manifests compared now
        self.rows, self.shown = [], []
        self.busy = False
        w = self.win = tk.Toplevel(mgr.win)
        w.title("Compare backups of the %s" % self.title)
        w.configure(bg=th.BG)
        w.geometry("900x580")
        w.minsize(640, 400)
        th.style_ttk(w)
        th.dark_title_bar_when_shown(w)
        w.bind("<Destroy>", self.destroyed, add="+")

        names = [bc.backup_title(f, m) for f, m in self.backups]
        self.before_var = tk.StringVar(master=w)
        self.after_var = tk.StringVar(master=w)
        pick = tk.Frame(w, bg=th.BG)
        pick.pack(fill="x", padx=12, pady=(12, 4))
        pick.columnconfigure(1, weight=1)
        tk.Label(pick, text="Before", bg=th.BG, fg=th.DIM).grid(row=0, column=0, sticky="w", padx=(0, 8))
        tk.Label(pick, text="After", bg=th.BG, fg=th.DIM).grid(row=1, column=0, sticky="w", padx=(0, 8),
                                                                pady=(4, 0))
        if names:
            option_menu(pick, self.before_var, names).grid(row=0, column=1, sticky="ew")
            option_menu(pick, self.after_var, names + [NOW_READ, NOW_LIST]).grid(row=1, column=1, sticky="ew",
                                                                                 pady=(4, 0))
            self.before_var.set(names[1] if len(names) > 1 else names[0])
            self.after_var.set(names[0] if len(names) > 1 else NOW_READ)
        else:
            tk.Label(pick, text="No backup of this %s yet: press Back up... in the Files panel first"
                     % self.title, bg=th.BG, fg=th.FG, anchor="w").grid(row=0, column=1, sticky="w")
        self.compare_btn = th.button(pick, "Compare", self.compare, state="normal" if names else "disabled")
        self.compare_btn.grid(row=0, column=2, rowspan=2, sticky="ns", padx=(10, 0))

        opts = tk.Frame(w, bg=th.BG)
        opts.pack(fill="x", padx=12, pady=(4, 4))
        self.hide_same = tk.BooleanVar(master=w, value=True)
        th.check(opts, "Hide unchanged", self.hide_same, self.fill).pack(side="left")
        self.counts = tk.StringVar(master=w, value="")
        tk.Label(opts, textvariable=self.counts, bg=th.BG, fg=th.FG, anchor="e").pack(side="right")

        mid = tk.Frame(w, bg=th.BG)
        mid.pack(fill="both", expand=True, padx=12)
        cols = ("status", "kind", "before", "after")
        tree = self.tree = ttk.Treeview(mid, columns=cols, style="Calc.Treeview", selectmode="browse")
        for col, text, width, anchor in (("#0", "Name", 240, "w"), ("status", "What", 130, "w"),
                                         ("kind", "Kind", 110, "w"), ("before", "Before", 180, "e"),
                                         ("after", "After", 180, "e")):
            tree.heading(col, text=text, anchor=anchor)
            tree.column(col, width=width, anchor=anchor, stretch=col == "#0")
        for status, colour in TAG_COLOURS.items():
            tree.tag_configure(status, foreground=colour)
        sb = ttk.Scrollbar(mid, orient="vertical", command=tree.yview, style="Calc.Vertical.TScrollbar")
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        tree.bind("<<TreeviewSelect>>", lambda e: self.picked())
        tree.bind("<Double-Button-1>", lambda e: self.show_diff())

        bar = tk.Frame(w, bg=th.BG)
        bar.pack(fill="x", padx=12, pady=(8, 0))
        self.diff_btn = th.button(bar, "Show the difference", self.show_diff, state="disabled")
        self.diff_btn.pack(side="left")
        self.restore_before = th.button(bar, "Restore this one (before)", lambda: self.restore("before"),
                                        state="disabled")
        self.restore_before.pack(side="left", padx=(6, 0))
        self.restore_after = th.button(bar, "Restore this one (after)", lambda: self.restore("after"),
                                       state="disabled")
        self.restore_after.pack(side="left", padx=(6, 0))
        th.button(bar, "Close", w.destroy).pack(side="right")
        self.note = tk.StringVar(master=w, value=(
            "Pick two backups (or a backup and the calculator now), then Compare." if names else
            "Nothing to compare yet."))
        tk.Label(w, textvariable=self.note, bg=th.BG, fg=th.DIM, anchor="w", justify="left",
                 wraplength=860).pack(fill="x", padx=12, pady=(8, 12))
        self.alive_flag = True

    # ---- Plumbing ----
    def destroyed(self, ev):
        if ev.widget is self.win:
            self.alive_flag = False
            for side in ("before", "after"):
                bc.discard(self.mans.get(side))  # A snapshot's temporary folder goes

    def alive(self):
        return self.alive_flag

    def ui(self, fn, *args):
        """fn(*args) on Tk's thread (from a worker: mirror's after() queues it)"""
        try:
            self.win.after(0, lambda: self.alive() and fn(*args))
        except (tk.TclError, RuntimeError):
            pass

    def say(self, text):
        self.ui(self.note.set, text)

    def ask(self, fn):
        """fn() on Tk's thread, waited for from a worker: its answer (None when closed)"""
        box, ev = {}, threading.Event()

        def run():
            try:
                box["r"] = fn()
            finally:
                ev.set()
        self.ui(run)
        while not ev.wait(0.2):
            if not self.alive():
                return None
        return box.get("r")

    def chosen(self, text):
        for (folder, man), name in zip(self.backups, [bc.backup_title(f, m) for f, m in self.backups]):
            if name == text:
                return folder, man
        return None

    # ---- Comparing ----
    def compare(self):
        if self.busy:
            return
        before = self.chosen(self.before_var.get())
        after_text = self.after_var.get()
        if before is None:
            self.note.set("Pick the backup to compare from")
            return
        if after_text in (NOW_READ, NOW_LIST):
            if self.mgr.busy:
                self.note.set("Wait for the %s to finish" % self.mgr.busy)
                return
            if not self.mgr.connected():
                self.note.set("The %s isn't connected: switch it on, then Compare again" % self.title)
                return
            self.start_now(before[1], after_text == NOW_READ)
            return
        after = self.chosen(after_text)
        if after is None or after[0] == before[0]:
            self.note.set("Pick two different backups")
            return
        self.set_compared(before[1], after[1])

    def start_now(self, before, read_all):
        self.busy = True
        self.compare_btn.configure(state="disabled")
        self.note.set("Reading the %s%s..." % (self.title, " (every item)" if read_all else "'s list"))
        mgr = self.mgr
        if read_all:
            mgr.set_busy("compare")

        def work():
            try:
                if read_all:
                    code, lines = mgr.run_batch([("info", None)])[0]
                    import nspire_link
                    info = nspire_link.info_dict(lines) if code == 0 else dict(getattr(mgr.m, "info", {}))
                    _folder, man = bc.snapshot(self.slug, mgr.run_batch, info, self.say)
                else:
                    man = bc.listing_manifest(self.slug, mgr.run_batch)
                self.ui(self.now_read, before, man, None)
            except Exception as e:  # Never takes the window down
                log_error("reading the calculator to compare")
                self.ui(self.now_read, before, None, e)
            finally:
                if read_all:
                    mgr.ui(mgr.set_busy, None)
        threading.Thread(target=work, daemon=True).start()

    def now_read(self, before, man, error):
        self.busy = False
        self.compare_btn.configure(state="normal")
        if man is None:
            self.note.set("Couldn't read the %s: %s" % (self.title, error))
            return
        self.set_compared(before, man)

    def set_compared(self, before, after):
        old = self.mans.get("after")
        if old is not None and old is not after:
            bc.discard(old)
        self.mans = {"before": before, "after": after}
        self.rows = bc.compare(self.slug, before, after)
        self.tree.heading("before", text="Before (%s)" % short_date(before))
        self.tree.heading("after", text="After (%s)" % short_date(after))
        self.counts.set(bc.summary_line(self.rows))
        self.fill()
        changed = [r for r in self.rows if r["status"] != bc.SAME]
        self.note.set("Nothing changed between them." if not changed else
                      "Pick a row: Show the difference (programs and texts), or Restore this one sends "
                      "that copy back to the calculator (you're asked before anything is replaced).")

    def fill(self):
        self.tree.delete(*self.tree.get_children())
        hide = self.hide_same.get()
        self.shown = [r for r in self.rows if not (hide and r["status"] == bc.SAME)]
        for k, r in enumerate(self.shown):
            self.tree.insert("", "end", iid=str(k), text=r["label"], tags=(r["status"],),
                             values=(bc.STATUS_TEXT[r["status"]], r["kind"], size_of(r["before"]),
                                     size_of(r["after"])))
        self.picked()

    def row(self):
        sel = self.tree.selection()
        return self.shown[int(sel[0])] if sel else None

    def picked(self):
        r = self.row()
        for b in (self.diff_btn, self.restore_before, self.restore_after):
            b.configure(state="disabled")
        if r is None:
            return
        self.diff_btn.configure(state="normal")
        for side, b in (("before", self.restore_before), ("after", self.restore_after)):
            man = self.mans.get(side)
            if r[side] is not None and man is not None and not man.get("snapshot"):
                b.configure(state="normal")

    # ---- The text diff ----
    def show_diff(self):
        r = self.row()
        if r is None:
            self.note.set("Pick a row first")
            return
        a, b, why = bc.texts_for(self.slug, r)
        if why:
            self.note.set("%s: no text to compare (%s). %s" % (
                r["label"], why, "Its contents differ (by SHA-256)." if r["status"] == bc.CHANGED else
                "Its size: %s." % (size_of(r["after"] or r["before"]))))
            return
        DiffWindow(self.win, r["label"], a, b, "before (%s)" % short_date(self.mans["before"]),
                   "after (%s)" % short_date(self.mans["after"]))

    # ---- One item back ----
    def restore(self, side):
        r = self.row()
        man = self.mans.get(side)
        if r is None or r[side] is None or man is None or man.get("snapshot"):
            return
        mgr = self.mgr
        if mgr.busy:
            self.note.set("Wait for the %s to finish" % mgr.busy)
            return
        if not mgr.connected():
            return
        item, label = r[side], r["label"]
        mgr.set_busy("restore")
        self.note.set("Checking whether %s is on the %s..." % (label, self.title))

        def ask_replace(name):
            return self.ask(lambda: messagebox.askyesno(
                "Replace?", "%s is on the %s now.\n\nReplace it with the %s copy (from %s)?"
                % (name, self.title, side, short_date(man)), icon="warning", parent=self.win))

        def work():
            try:
                ok, why = bc.restore_one(self.slug, mgr.run_batch, man, item, ask_replace, self.say)
            except Exception as e:
                log_error("restoring one item")
                ok, why = False, str(e)
            self.ui(self.restored, label, ok, why)
            mgr.ui(mgr.set_busy, None)
        threading.Thread(target=work, daemon=True).start()

    def restored(self, label, ok, why):
        self.note.set("Sent %s to the %s" % (label, self.title) if ok else "Not sent: %s" % why)
        try:
            self.mgr.ui(self.mgr.refresh)
        except Exception:
            pass


def short_date(man):
    if man is None:
        return ""
    if man.get("snapshot"):
        return "now"
    return man.get("made", "?").replace("T", " ")[:16]


def size_of(item):
    return cf.human_size(item["size"]) if item is not None and "size" in item else ""


class DiffWindow(object):
    """Two texts compared: side by side (changed lines lit) or as a unified diff"""

    def __init__(self, parent, title, a, b, name_a="before", name_b="after"):
        self.a, self.b, self.names = a, b, (name_a, name_b)
        w = self.win = tk.Toplevel(parent)
        w.title("%s: what changed" % title)
        w.configure(bg=th.BG)
        w.geometry("980x600")
        th.style_ttk(w)
        th.dark_title_bar_when_shown(w)
        top = tk.Frame(w, bg=th.BG)
        top.pack(fill="x", padx=12, pady=(12, 6))
        self.mode = tk.StringVar(master=w, value="side")
        for value, text in (("side", "Side by side"), ("unified", "Unified")):
            tk.Radiobutton(top, text=text, variable=self.mode, value=value, command=self.draw,
                           indicatoron=0, bg=th.PANEL2, fg=th.FG, selectcolor=th.ACCENT,
                           activebackground=th.ACTIVE, activeforeground="#ffffff", bd=0, padx=10,
                           pady=4, highlightthickness=0, cursor="hand2").pack(side="left", padx=(0, 6))
        same = a == b
        self.info = tk.Label(top, text="The texts are the same" if same else
                             "%s  vs  %s" % (name_a, name_b), bg=th.BG, fg=th.DIM)
        self.info.pack(side="left", padx=10)
        th.button(top, "Copy the unified diff", self.copy).pack(side="right")
        self.body = tk.Frame(w, bg=th.BG)
        self.body.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.draw()

    def text_box(self, parent):
        t = tk.Text(parent, bg="#0b0b0c", fg=th.FG, insertbackground=th.FG, relief="flat", wrap="none",
                    font=(th.MONO, 10), padx=6, pady=6, bd=0, highlightthickness=0)
        t.tag_configure("added", background="#0f2a20", foreground=th.MINT)
        t.tag_configure("removed", background="#2e1210", foreground=th.RED)
        t.tag_configure("changed", background="#2a1a0c", foreground=th.ACCENT)
        t.tag_configure("blank", background="#141416")
        t.tag_configure("head", foreground=th.DIM)
        return t

    def draw(self):
        for c in self.body.winfo_children():
            c.destroy()
        if self.mode.get() == "unified":
            self.draw_unified()
        else:
            self.draw_side()

    def draw_unified(self):
        t = self.text_box(self.body)
        sy = ttk.Scrollbar(self.body, orient="vertical", command=t.yview, style="Calc.Vertical.TScrollbar")
        sx = ttk.Scrollbar(self.body, orient="horizontal", command=t.xview, style="Calc.Horizontal.TScrollbar")
        t.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        sx.pack(side="bottom", fill="x")
        sy.pack(side="right", fill="y")
        t.pack(side="left", fill="both", expand=True)
        lines = bc.unified(self.a, self.b, *self.names)
        if not lines:
            t.insert("end", "No difference.")
        for l in lines:
            tag = ("head" if l.startswith(("---", "+++", "@@")) else "added" if l.startswith("+") else
                   "removed" if l.startswith("-") else None)
            t.insert("end", l + "\n", tag)
        t.configure(state="disabled")
        self.boxes = (t,)

    def draw_side(self):
        rows = bc.side_by_side(self.a, self.b)
        holder = tk.Frame(self.body, bg=th.BG)
        holder.pack(side="top", fill="both", expand=True)
        left, right = self.text_box(holder), self.text_box(holder)
        sy = ttk.Scrollbar(holder, orient="vertical", style="Calc.Vertical.TScrollbar")

        def both(*args):
            left.yview(*args)
            right.yview(*args)

        def moved(first, last):
            sy.set(first, last)
            for t in (left, right):
                if abs(t.yview()[0] - float(first)) > 1e-6:
                    t.yview_moveto(first)
        sy.configure(command=both)
        left.configure(yscrollcommand=moved)
        right.configure(yscrollcommand=moved)
        sx = ttk.Scrollbar(self.body, orient="horizontal", style="Calc.Horizontal.TScrollbar",
                           command=lambda *a: (left.xview(*a), right.xview(*a)))
        left.configure(xscrollcommand=sx.set)
        sx.pack(side="bottom", fill="x")
        sy.pack(side="right", fill="y")
        left.pack(side="left", fill="both", expand=True)
        tk.Frame(holder, bg=th.LINE, width=1).pack(side="left", fill="y")
        right.pack(side="left", fill="both", expand=True)
        na = nb = 0
        for l, r, tag in rows:
            if l is not None:
                na += 1
                left.insert("end", "%4d  %s\n" % (na, l), None if tag == "same" else tag)
            else:
                left.insert("end", "\n", "blank")
            if r is not None:
                nb += 1
                right.insert("end", "%4d  %s\n" % (nb, r), None if tag == "same" else tag)
            else:
                right.insert("end", "\n", "blank")
        for t in (left, right):
            t.configure(state="disabled")
            t.bind("<MouseWheel>", lambda e: (both("scroll", -1 if e.delta > 0 else 1, "units"), "break")[1])
        self.boxes = (left, right)

    def copy(self):
        self.win.clipboard_clear()
        self.win.clipboard_append("\n".join(bc.unified(self.a, self.b, *self.names)))
        self.info.configure(text="Copied the unified diff")
