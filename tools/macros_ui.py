"""The Macros section of a calculator's side panel: record keys, save them by name, play them
back, edit, import and export. The logic (recording, files, the replay plan, the warning rule)
is macros.py; this is only the window.

A replay runs on a worker thread and goes through the tab's Mirror.queue like typed keys, so
the link helper paces it; window work comes back with after(). MIT licence.
"""

import os
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import macros as mc
import ui_theme as th


def log_error(where):
    try:
        import mirror
        mirror.log_error(where)
    except Exception:
        pass


def entry(parent, var, width=20):
    return tk.Entry(parent, textvariable=var, width=width, bg="#0b0b0c", fg=th.FG,
                    insertbackground=th.FG, relief="flat", highlightthickness=1,
                    highlightbackground=th.LINE, highlightcolor=th.ACCENT)


class MacrosSection(object):
    def __init__(self, panel, parent, folder=None):
        """folder: where the macros files are (default CalcSuite files\\macros; the self-test's own)"""
        import ui_panels as up
        self.panel, self.m = panel, panel.m
        self.slug, self.calc = self.m.calc.slug, self.m.calc
        self.folder = folder
        self.recorder = None
        self.player = None
        self.frame = tk.Frame(parent, bg=th.PANEL)
        outer, inner = up.scrolled(self.frame)
        outer.pack(fill="both", expand=True)
        self.inner = inner

        up.heading(inner, "Record")
        row = tk.Frame(inner, bg=th.PANEL)
        row.pack(fill="x")
        self.rec_btn = th.button(row, "Record", self.toggle_record)
        self.rec_btn.pack(side="left")
        self.keep_pauses = tk.BooleanVar(master=self.frame, value=False)
        th.check(row, "Keep the pauses as waits", self.keep_pauses, bg=th.PANEL).pack(side="left", padx=(10, 0))
        self.rec_note = tk.StringVar(master=self.frame, value=(
            "Record, then use the calculator as usual (keyboard, clicks on the screen, Symbols, paste): "
            "every key is kept. Stop recording, name it, Save."))
        tk.Label(inner, textvariable=self.rec_note, bg=th.PANEL, fg=th.DIM, anchor="w", justify="left",
                 wraplength=400).pack(fill="x", pady=(6, 0))
        self.save_row = tk.Frame(inner, bg=th.PANEL)
        self.name_var = tk.StringVar(master=self.frame)
        entry(self.save_row, self.name_var, 24).pack(side="left", fill="x", expand=True, ipady=3)
        th.button(self.save_row, "Save", self.save_recording).pack(side="left", padx=(6, 0))
        th.button(self.save_row, "Discard", self.discard_recording).pack(side="left", padx=(6, 0))
        self.recorded = None
        self.save_anchor = tk.Frame(inner, bg=th.PANEL, height=1)
        self.save_anchor.pack(fill="x")

        up.heading(inner, "Macros for the %s" % self.calc.title)
        mid = tk.Frame(inner, bg=th.PANEL)
        mid.pack(fill="x")
        tree = self.tree = ttk.Treeview(mid, columns=("keys", "time"), style="Calc.Treeview",
                                        selectmode="browse", height=8)
        tree.heading("#0", text="Name", anchor="w")
        tree.column("#0", width=220, anchor="w")
        tree.heading("keys", text="Keys", anchor="e")
        tree.column("keys", width=50, anchor="e", stretch=False)
        tree.heading("time", text="Waits", anchor="e")
        tree.column("time", width=60, anchor="e", stretch=False)
        tree.tag_configure("builtin", foreground=th.DIM)
        sb = ttk.Scrollbar(mid, orient="vertical", command=tree.yview, style="Calc.Vertical.TScrollbar")
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="x", expand=True)
        sb.pack(side="right", fill="y")
        tree.bind("<<TreeviewSelect>>", lambda e: self.picked())
        tree.bind("<Double-Button-1>", lambda e: self.play())
        self.detail = tk.StringVar(master=self.frame, value="")
        tk.Label(inner, textvariable=self.detail, bg=th.PANEL, fg=th.FG, anchor="w", justify="left",
                 wraplength=400).pack(fill="x", pady=(6, 0))
        b1 = tk.Frame(inner, bg=th.PANEL)
        b1.pack(fill="x", pady=(6, 0))
        self.play_btn = th.button(b1, "Play", self.play)
        self.play_btn.pack(side="left")
        self.stop_btn = th.button(b1, "Stop", self.stop, state="disabled")
        self.stop_btn.pack(side="left", padx=(6, 0))
        self.edit_btn = th.button(b1, "Edit...", self.edit)
        self.edit_btn.pack(side="left", padx=(6, 0))
        th.button(b1, "Duplicate", self.duplicate).pack(side="left", padx=(6, 0))
        b2 = tk.Frame(inner, bg=th.PANEL)
        b2.pack(fill="x", pady=(6, 0))
        self.del_btn = th.button(b2, "Delete", self.delete)
        self.del_btn.pack(side="left")
        th.button(b2, "Import...", self.import_).pack(side="left", padx=(6, 0))
        th.button(b2, "Export...", self.export).pack(side="left", padx=(6, 0))
        self.note = tk.StringVar(master=self.frame, value=(
            "Examples (grey) only move between screens; Duplicate one to change it. A macro with "
            "keys that delete, clear or open a reset menu asks before it first plays."))
        tk.Label(inner, textvariable=self.note, bg=th.PANEL, fg=th.DIM, anchor="w", justify="left",
                 wraplength=400).pack(fill="x", pady=(8, 0))
        up.bind_wheel(inner, inner)
        self.macros = []
        self.load()

    # ---- Plumbing ----
    def ui(self, fn, *args):
        try:
            self.frame.after(0, lambda: fn(*args))
        except (tk.TclError, RuntimeError):
            pass

    def user_macros(self):
        return [m for m in self.macros if not m.get("builtin")]

    def load(self):
        user = []
        try:
            user = mc.load(self.slug, self.folder)
        except mc.MacroError as e:
            log_error("reading the macros")
            path = mc.store_path(self.slug, self.folder)
            aside = path + ".unreadable-%s" % time.strftime("%Y%m%d-%H%M%S")
            try:
                os.replace(path, aside)
                self.note.set("The macros file couldn't be read (%s): it was kept as %s" % (e, aside))
            except OSError:
                self.note.set("The macros file couldn't be read: %s" % e)
        self.macros = mc.builtins(self.slug) + user
        self.fill()

    def store(self):
        try:
            mc.save(self.slug, self.user_macros(), self.folder)
            return True
        except OSError as e:
            log_error("saving the macros")
            self.note.set("Couldn't save the macros: %s" % e)
            return False

    def fill(self, pick=None):
        self.tree.delete(*self.tree.get_children())
        for k, m in enumerate(self.macros):
            waits = mc.total_ms(m)
            self.tree.insert("", "end", iid=str(k), text=m["name"] + ("  (example)" if m.get("builtin") else ""),
                             values=(len(m["steps"]), mc.seconds(waits) if waits else ""),
                             tags=("builtin",) if m.get("builtin") else ())
        if pick is not None and 0 <= pick < len(self.macros):
            self.tree.selection_set(str(pick))
            self.tree.see(str(pick))
        self.picked()

    def selected(self):
        sel = self.tree.selection()
        return (int(sel[0]), self.macros[int(sel[0])]) if sel else (None, None)

    def picked(self):
        _k, m = self.selected()
        self.detail.set(mc.describe(self.slug, m) if m else "")
        builtin = bool(m and m.get("builtin"))
        for b in (self.edit_btn, self.del_btn):
            b.configure(state="disabled" if builtin or m is None else "normal")

    # ---- Recording ----
    def toggle_record(self):
        if self.recorder is None:
            if self.player is not None:
                self.note.set("Wait for the macro to finish (or Stop it)")
                return
            self.recorder = mc.Recorder(self.slug, self.keep_pauses.get())
            self.m.key_taps.append(self.recorder.tap)
            self.rec_btn.configure(text="Stop recording", bg=th.RED, fg="#000000")
            self.play_btn.configure(state="disabled")
            self.save_row.pack_forget()
            self.tick()
            return
        rec, self.recorder = self.recorder, None
        try:
            self.m.key_taps.remove(rec.tap)
        except ValueError:
            pass
        self.rec_btn.configure(text="Record", bg=th.PANEL2, fg=th.FG)
        self.play_btn.configure(state="normal")
        steps = rec.result()
        if not steps:
            self.rec_note.set("Nothing recorded: no key went to the %s" % self.calc.title)
            return
        self.recorded = steps
        taken = [m["name"] for m in self.macros]
        self.name_var.set(mc.unique_name("Macro %d" % (len(self.user_macros()) + 1), taken))
        self.rec_note.set("%d key(s) recorded%s: %s. Name it and Save." % (
            len(steps), " (the most a macro holds)" if rec.full else "",
            mc.describe(self.slug, {"steps": steps}, 8)))
        self.save_row.pack(fill="x", pady=(6, 0), after=self.save_anchor)

    def tick(self):
        if self.recorder is None:
            return
        self.rec_note.set("Recording: %d key(s) so far. Press Stop recording when done." % self.recorder.count())
        self.frame.after(300, self.tick)

    def save_recording(self):
        if not self.recorded:
            return
        name = mc.unique_name(mc.clean_name(self.name_var.get()), [m["name"] for m in self.macros])
        m = mc.new_macro(self.slug, name, self.recorded)
        self.macros.append(m)
        if self.store():
            self.rec_note.set("Saved %s (%d keys)" % (name, len(m["steps"])))
        self.recorded = None
        self.save_row.pack_forget()
        self.fill(len(self.macros) - 1)

    def discard_recording(self):
        self.recorded = None
        self.save_row.pack_forget()
        self.rec_note.set("Recording discarded")

    # ---- Playing ----
    def play(self):
        k, m = self.selected()
        if m is None:
            self.note.set("Pick a macro first")
            return
        if self.player is not None or self.recorder is not None:
            self.note.set("Stop the %s first" % ("macro" if self.player else "recording"))
            return
        if self.m.session is None:
            self.note.set("The %s isn't connected yet" % self.calc.title)
            return
        if not self.m.keys_on.get():
            self.note.set("The keyboard is off for the %s (Keyboard, under the screen)" % self.calc.title)
            return
        risky = mc.needs_warning(self.slug, m)
        if risky:
            listing = "\n".join("  %s" % why for _k, why in risky)
            if not messagebox.askyesno(
                    "Play this macro?", "%s presses keys that can delete or reset things on the %s:\n\n%s"
                    "\n\nWhat they do depends on the screen the calculator is on. Play it now? (You're "
                    "asked again only if keys like these are added.)" % (m["name"], self.calc.title, listing),
                    icon="warning", parent=self.frame.winfo_toplevel()):
                return
            mc.accept_risky(self.slug, m)
            if not m.get("builtin"):
                self.store()
        try:
            segments = mc.plan(self.slug, m["steps"])
        except mc.MacroError as e:
            self.note.set(str(e))
            return
        mirror = self.m
        fmt = self.calc.key_fmt

        def send(codes, done):
            if not mirror.running or mirror.session is None:
                return False
            mirror.queue("keys " + " ".join(fmt % c for c in codes), None,
                         lambda code, lines: done(code == 0))
            return True

        self.player = mc.Player(segments, send, lambda ok, why: self.ui(self.played, m, ok, why))
        self.play_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.rec_btn.configure(state="disabled")
        self.note.set("Playing %s..." % m["name"])
        try:
            mirror.pressed(None, None, [], text="macro " + m["name"])
        except Exception:
            log_error("showing the macro's press")
        threading.Thread(target=self.player.run, daemon=True).start()

    def stop(self):
        if self.player is not None:
            self.player.stop()

    def played(self, m, ok, why):
        self.player = None
        self.play_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.rec_btn.configure(state="normal")
        self.note.set("Played %s" % m["name"] if ok else "%s stopped: %s" % (m["name"], why))

    # ---- Changing the list ----
    def duplicate(self):
        k, m = self.selected()
        if m is None:
            self.note.set("Pick a macro first")
            return
        copy = mc.new_macro(self.slug, mc.unique_name(m["name"], [x["name"] for x in self.macros]), m["steps"])
        self.macros.append(copy)
        self.store()
        self.fill(len(self.macros) - 1)
        self.note.set("Made %s: Edit... changes it" % copy["name"])

    def delete(self):
        k, m = self.selected()
        if m is None or m.get("builtin"):
            return
        if not messagebox.askyesno("Delete macro?", "Delete the macro %s? (Only the macro: nothing on "
                                   "the calculator.)" % m["name"], parent=self.frame.winfo_toplevel()):
            return
        del self.macros[k]
        self.store()
        self.fill(min(k, len(self.macros) - 1))
        self.note.set("Deleted %s" % m["name"])

    def edit(self):
        k, m = self.selected()
        if m is None or m.get("builtin"):
            return
        EditDialog(self, k)

    def edited(self, k, macro):
        self.macros[k] = macro
        self.store()
        self.fill(k)
        self.note.set("Saved %s" % macro["name"])

    def import_(self):
        path = filedialog.askopenfilename(parent=self.frame.winfo_toplevel(), title="Import macros",
                                          filetypes=[("CalcSuite macros", "*.json"), ("All files", "*.*")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                incoming = mc.from_json(self.slug, f.read())
        except (OSError, mc.MacroError) as e:
            self.note.set("Not imported: %s" % e)
            return
        if not incoming:
            self.note.set("That file has no macros")
            return
        self.macros, added = mc.merge(self.macros, incoming)
        self.store()
        self.fill(len(self.macros) - 1)
        self.note.set("Imported %d macro(s): %s" % (len(added), ", ".join(m["name"] for m in added)))

    def export(self):
        _k, m = self.selected()
        chosen = [dict(m, builtin=False)] if m is not None else self.user_macros()
        for c in chosen:
            c.pop("builtin", None)
        if not chosen:
            self.note.set("Nothing to export: record a macro first (or pick an example)")
            return
        name = mc.clean_name(chosen[0]["name"]) if len(chosen) == 1 else "%s macros" % self.calc.title
        path = filedialog.asksaveasfilename(
            parent=self.frame.winfo_toplevel(), title="Export macros", defaultextension=".json",
            initialfile="".join(ch if ch.isalnum() or ch in " -_()" else "_" for ch in name) + ".json",
            filetypes=[("CalcSuite macros", "*.json")])
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(mc.to_json(self.slug, chosen))
            self.note.set("Exported %d macro(s) to %s" % (len(chosen), path))
        except OSError as e:
            log_error("exporting macros")
            self.note.set("Couldn't export: %s" % e)


class EditDialog(object):
    """Rename a macro, reorder or remove its keys, add keys, change the waits"""

    def __init__(self, section, k):
        self.section, self.k = section, k
        self.slug = section.slug
        m = section.macros[k]
        self.steps = [dict(s) for s in m["steps"]]
        self.orig = m
        w = self.win = tk.Toplevel(section.frame.winfo_toplevel())
        w.title("Edit macro: %s" % m["name"])
        w.configure(bg=th.BG)
        w.geometry("560x520")
        w.minsize(460, 380)
        th.style_ttk(w)
        th.dark_title_bar_when_shown(w)
        top = tk.Frame(w, bg=th.BG)
        top.pack(fill="x", padx=12, pady=(12, 6))
        tk.Label(top, text="Name", bg=th.BG, fg=th.DIM).pack(side="left")
        self.name_var = tk.StringVar(master=w, value=m["name"])
        entry(top, self.name_var, 30).pack(side="left", fill="x", expand=True, padx=(8, 0), ipady=3)

        mid = tk.Frame(w, bg=th.BG)
        mid.pack(fill="both", expand=True, padx=12)
        tree = self.tree = ttk.Treeview(mid, columns=("key", "wait"), style="Calc.Treeview",
                                        selectmode="extended")
        tree.heading("#0", text="#", anchor="e")
        tree.column("#0", width=50, anchor="e", stretch=False)
        tree.heading("key", text="Key", anchor="w")
        tree.column("key", width=260, anchor="w")
        tree.heading("wait", text="Wait after it", anchor="e")
        tree.column("wait", width=110, anchor="e", stretch=False)
        tree.tag_configure("risky", foreground=th.RED)
        sb = ttk.Scrollbar(mid, orient="vertical", command=tree.yview, style="Calc.Vertical.TScrollbar")
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        tree.bind("<<TreeviewSelect>>", lambda e: self.picked())

        r1 = tk.Frame(w, bg=th.BG)
        r1.pack(fill="x", padx=12, pady=(8, 0))
        th.button(r1, "Move up", lambda: self.move(-1)).pack(side="left")
        th.button(r1, "Move down", lambda: self.move(1)).pack(side="left", padx=(6, 0))
        th.button(r1, "Remove", self.remove).pack(side="left", padx=(6, 0))
        tk.Label(r1, text="Wait (ms)", bg=th.BG, fg=th.DIM).pack(side="left", padx=(14, 4))
        self.wait_var = tk.StringVar(master=w, value="0")
        entry(r1, self.wait_var, 7).pack(side="left", ipady=3)
        th.button(r1, "Set", self.set_wait).pack(side="left", padx=(6, 0))
        r2 = tk.Frame(w, bg=th.BG)
        r2.pack(fill="x", padx=12, pady=(8, 0))
        tk.Label(r2, text="Add key", bg=th.BG, fg=th.DIM).pack(side="left")
        self.key_var = tk.StringVar(master=w)
        e = entry(r2, self.key_var, 16)
        e.pack(side="left", padx=(8, 0), ipady=3)
        e.bind("<Return>", lambda ev: self.add())
        th.button(r2, "Add after the picked one", self.add).pack(side="left", padx=(6, 0))
        self.note = tk.StringVar(master=w, value=(
            "Add key takes the names the Keys panel uses (enter, up, %s ...) or a character."
            % {"ti84": "quit, mode, math", "ti89": "home, f1, mode", "nspire": "home, menu, tab"}[self.slug]))
        tk.Label(w, textvariable=self.note, bg=th.BG, fg=th.DIM, anchor="w", justify="left",
                 wraplength=520).pack(fill="x", padx=12, pady=(8, 0))
        bar = tk.Frame(w, bg=th.BG)
        bar.pack(fill="x", padx=12, pady=(8, 12))
        th.button(bar, "Save", self.save).pack(side="right")
        th.button(bar, "Cancel", w.destroy).pack(side="right", padx=(0, 6))
        self.fill()

    def fill(self, pick=()):
        self.tree.delete(*self.tree.get_children())
        risky = set(mc.RISKY[self.slug])
        for k, s in enumerate(self.steps):
            bad = s["key"] in risky or s["key"].startswith("#")
            self.tree.insert("", "end", iid=str(k), text=str(k + 1), tags=("risky",) if bad else (),
                             values=("%s  (%s)" % (mc.label_of(self.slug, s["key"]), s["key"]),
                                     mc.seconds(s["wait_ms"]) if s["wait_ms"] else ""))
        for k in pick:
            if 0 <= k < len(self.steps):
                self.tree.selection_add(str(k))
                self.tree.see(str(k))

    def rows(self):
        return sorted(int(i) for i in self.tree.selection())

    def picked(self):
        rows = self.rows()
        if len(rows) == 1:
            self.wait_var.set(str(self.steps[rows[0]]["wait_ms"]))

    def move(self, d):
        rows = self.rows()
        if not rows:
            return
        if (d < 0 and rows[0] == 0) or (d > 0 and rows[-1] == len(self.steps) - 1):
            return
        for k in (rows if d < 0 else reversed(rows)):
            self.steps[k], self.steps[k + d] = self.steps[k + d], self.steps[k]
        self.fill([k + d for k in rows])

    def remove(self):
        rows = self.rows()
        for k in reversed(rows):
            del self.steps[k]
        self.fill([min(rows[0], len(self.steps) - 1)] if rows and self.steps else ())

    def set_wait(self):
        rows = self.rows()
        try:
            ms = int(self.wait_var.get().strip())
        except ValueError:
            self.note.set("A wait is a whole number of milliseconds (1000 = 1 s)")
            return
        ms = max(0, min(mc.WAIT_MAX_MS, ms))
        if not rows:
            self.note.set("Pick the key the wait comes after")
            return
        for k in rows:
            self.steps[k]["wait_ms"] = ms
        self.fill(rows)

    def add(self):
        key = self.key_var.get()
        key = key.strip() if len(key.strip()) > 0 else key  # A lone space stays a space
        if not key:
            return
        if mc.code_of(self.slug, key) is None:
            self.note.set("The %s has no key %r (the Keys panel lists the names)" % (
                self.section.calc.title, key))
            return
        if len(self.steps) >= mc.STEPS_MAX:
            self.note.set("A macro holds %d keys at most" % mc.STEPS_MAX)
            return
        rows = self.rows()
        at = rows[-1] + 1 if rows else len(self.steps)
        self.steps.insert(at, {"key": key, "wait_ms": 0})
        self.key_var.set("")
        self.fill([at])

    def save(self):
        if not self.steps:
            self.note.set("A macro needs at least one key (Delete removes the whole macro)")
            return
        taken = [m["name"] for i, m in enumerate(self.section.macros) if i != self.k]
        m = mc.new_macro(self.slug, mc.unique_name(mc.clean_name(self.name_var.get()), taken), self.steps)
        m["ok_risky"] = [k for k in self.orig.get("ok_risky", [])]  # Keys newly added ask again
        self.section.edited(self.k, m)
        self.win.destroy()
