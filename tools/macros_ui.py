"""The Macros section of a calculator's side panel: record keys, save them by name, play them
back, pin them as buttons under the screen, give them Ctrl+1..9, edit, import and export. The
logic (recording, files, the replay plan, the warning rule, pins and hotkeys) is macros.py;
this is only the window.

Each calculator's tab has one MacroBox (box_for): the macros, the one playing, and play().
The Macros panel, the pinned buttons under the screen and the hotkeys all go through it.

A replay runs on a worker thread and goes through the tab's Mirror.queue like typed keys, so
the link helper paces it; window work comes back with after(). MIT licence.
"""

import os
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import macros as mc
import tool_tabs
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


def box_for(mirror, folder=None):
    """The calculator's MacroBox (one per Mirror; folder: the self-test's own, not kept)"""
    b = getattr(mirror, "macro_box", None)
    if b is None or b.folder != folder:
        b = MacroBox(mirror, folder)
        if folder is None:
            mirror.macro_box = b
    return b


class MacroBox(object):
    """One calculator's macros and their replay. listeners: fn() after the list, a pin or a
    hotkey changed (the pinned buttons, the Keys panel); notes: fn(text) for what it says
    (the Macros panel's note; the tab's status line gets it too); states: fn() when a replay
    starts or ends."""

    def __init__(self, mirror, folder=None):
        self.m, self.folder = mirror, folder
        self.slug, self.calc = mirror.calc.slug, mirror.calc
        self.macros = []
        self.player = None
        self.recording = False
        self.listeners, self.notes, self.states = [], [], []
        self.load_note = None
        self.load()

    # ---- the list ----
    def load(self):
        try:
            self.macros = mc.load_all(self.slug, self.folder)
        except mc.MacroError as e:
            log_error("reading the macros")
            path = mc.store_path(self.slug, self.folder)
            aside = path + ".unreadable-%s" % time.strftime("%Y%m%d-%H%M%S")
            try:
                os.replace(path, aside)
                self.load_note = "The macros file couldn't be read (%s): it was kept as %s" % (e, aside)
            except OSError:
                self.load_note = "The macros file couldn't be read: %s" % e
            self.macros = mc.builtins(self.slug)

    def store(self):
        """Saves the list (the user's macros, the built-ins' pins and hotkeys) and tells the
        listeners. False (and says why) when it can't be written."""
        ok = True
        try:
            mc.save(self.slug, self.macros, self.folder)
        except OSError as e:
            log_error("saving the macros")
            self.say("Couldn't save the macros: %s" % e, status=False)
            ok = False
        self.changed()
        return ok

    def changed(self):
        for fn in list(self.listeners):
            try:
                fn()
            except tk.TclError:
                try:
                    self.listeners.remove(fn)  # Its window is gone
                except ValueError:
                    pass
            except Exception:
                log_error("showing the macros")

    def user_macros(self):
        return [m for m in self.macros if not m.get("builtin")]

    def pinned(self):
        return mc.pinned(self.macros)

    def by_hotkey(self, n):
        return mc.by_hotkey(self.macros, n)

    def say(self, text, status=True):
        for fn in list(self.notes):
            try:
                fn(text)
            except tk.TclError:
                pass
        if status and hasattr(self.m, "set_status"):
            self.m.set_status(text)

    def state(self):
        for fn in list(self.states):
            try:
                fn()
            except tk.TclError:
                pass

    # ---- playing ----
    def hotkey(self, n, parent):
        """Ctrl+n on the calculator's tab: plays its macro. False when no macro has it (the
        key then goes to the calculator as before)."""
        m = self.by_hotkey(n)
        if m is None:
            return False
        self.play(m, parent)
        return True

    def play(self, m, parent):
        """Plays m (a pinned button, a hotkey, the panel's Play). parent: where a question
        hangs. True when it started."""
        if self.player is not None:
            self.say("Wait for the macro to finish (or Stop it)")
            return False
        if self.recording:
            self.say("Stop the recording first")
            return False
        if self.m.session is None:
            self.say("The %s isn't connected yet" % self.calc.title)
            return False
        if not self.m.keys_on.get():
            self.say("The keyboard is off for the %s (Keyboard, under the screen)" % self.calc.title)
            return False
        risky = mc.needs_warning(self.slug, m)
        if risky:
            listing = "\n".join("  %s" % why for _k, why in risky)
            if not messagebox.askyesno(
                    "Play this macro?", "%s presses keys that can delete or reset things on the %s:\n\n%s"
                    "\n\nWhat they do depends on the screen the calculator is on. Play it now? (You're "
                    "asked again only if keys like these are added.)" % (m["name"], self.calc.title, listing),
                    icon="warning", parent=parent.winfo_toplevel()):
                return False
            mc.accept_risky(self.slug, m)
            if not m.get("builtin"):
                self.store()
        try:
            segments = mc.plan(self.slug, m["steps"])
        except mc.MacroError as e:
            self.say(str(e))
            return False
        mirror = self.m
        fmt = self.calc.key_fmt

        def send(codes, done):
            if not mirror.running or mirror.session is None:
                return False
            mirror.queue("keys " + " ".join(fmt % c for c in codes), None,
                         lambda code, lines: done(code == 0))
            return True

        def ended(ok, why):
            try:
                parent.after(0, lambda: self.played(m, ok, why))
            except (tk.TclError, RuntimeError):
                pass
        self.player = mc.Player(segments, send, ended)
        self.say("Playing %s..." % m["name"])
        self.state()
        try:
            mirror.pressed(None, None, [], text="macro " + m["name"])
        except Exception:
            log_error("showing the macro's press")
        threading.Thread(target=self.player.run, daemon=True).start()
        return True

    def stop(self):
        if self.player is not None:
            self.player.stop()

    def played(self, m, ok, why):
        self.player = None
        self.say("Played %s" % m["name"] if ok else "%s stopped: %s" % (m["name"], why))
        self.state()


class MacrosSection(object):
    def __init__(self, panel, parent, folder=None):
        """folder: where the macros files are (default CalcSuite files\\macros; the self-test's own)"""
        import ui_panels as up
        self.panel, self.m = panel, panel.m
        self.slug, self.calc = self.m.calc.slug, self.m.calc
        self.folder = folder
        self.box = box_for(self.m, folder)
        self.recorder = None
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
        th.hint(inner, textvariable=self.rec_note).pack(fill="x", pady=(6, 0))
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
        tree = self.tree = ttk.Treeview(mid, columns=("pin", "hotkey", "keys", "time"), style="Calc.Treeview",
                                        selectmode="browse", height=10)
        tree.heading("#0", text="Name", anchor="w")
        tree.column("#0", width=200, anchor="w")
        tree.heading("pin", text="Pinned", anchor="center")
        tree.column("pin", width=60, anchor="center", stretch=False)
        tree.heading("hotkey", text="Hotkey", anchor="w")
        tree.column("hotkey", width=64, anchor="w", stretch=False)
        tree.heading("keys", text="Keys", anchor="e")
        tree.column("keys", width=46, anchor="e", stretch=False)
        tree.heading("time", text="Waits", anchor="e")
        tree.column("time", width=54, anchor="e", stretch=False)
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
        self.pin_btn = th.button(b1, "Pin under the screen", self.toggle_pin)
        self.pin_btn.pack(side="left", padx=(6, 0))
        self.hot_btn = th.button(b1, "Hotkey ▾", self.hotkey_menu)
        self.hot_btn.pack(side="left", padx=(6, 0))
        b2 = tk.Frame(inner, bg=th.PANEL)
        b2.pack(fill="x", pady=(6, 0))
        self.edit_btn = th.button(b2, "Edit...", self.edit)
        self.edit_btn.pack(side="left")
        th.button(b2, "Duplicate", self.duplicate).pack(side="left", padx=(6, 0))
        self.del_btn = th.button(b2, "Delete", self.delete)
        self.del_btn.pack(side="left", padx=(6, 0))
        th.button(b2, "Import...", self.import_).pack(side="left", padx=(6, 0))
        th.button(b2, "Export...", self.export).pack(side="left", padx=(6, 0))
        self.note = tk.StringVar(master=self.frame, value=self.box.load_note or (
            "The \"Go to\" macros only open a screen or a menu. Pin one to get a button under the "
            "screen, or give it Ctrl+1 to Ctrl+9 (on this tab). Examples (grey) can't be changed: "
            "Duplicate one to change it. A macro with keys that delete, clear or open a reset menu "
            "asks before it first plays."))
        th.hint(inner, textvariable=self.note).pack(fill="x", pady=(8, 0))
        up.bind_wheel(inner, inner)
        self.box.notes.append(self.note.set)
        self.box.states.append(self.play_state)
        self.box.listeners.append(self.refill)
        self.fill()

    # ---- Plumbing ----
    @property
    def macros(self):
        return self.box.macros

    @macros.setter
    def macros(self, value):
        self.box.macros = value

    @property
    def player(self):
        return self.box.player

    def ui(self, fn, *args):
        try:
            self.frame.after(0, lambda: fn(*args))
        except (tk.TclError, RuntimeError):
            pass

    def user_macros(self):
        return self.box.user_macros()

    def load(self):
        self.box.load()
        if self.box.load_note:
            self.note.set(self.box.load_note)
        self.fill()

    def store(self):
        return self.box.store()

    def refill(self):
        """The box's list changed (here or elsewhere): the list shows it, the pick stays"""
        k, _m = self.selected()
        self.fill(k)

    def fill(self, pick=None):
        self.tree.delete(*self.tree.get_children())
        for k, m in enumerate(self.macros):
            waits = mc.total_ms(m)
            self.tree.insert("", "end", iid=str(k), text=m["name"] + (
                "" if m.get("go") or not m.get("builtin") else "  (example)"),
                values=("●" if m.get("pinned") else "", "Ctrl+%d" % m["hotkey"] if m.get("hotkey") else "",
                        len(m["steps"]), mc.seconds(waits) if waits else ""),
                tags=("builtin",) if m.get("builtin") and not m.get("go") else ())
        if pick is not None and 0 <= pick < len(self.macros):
            self.tree.selection_set(str(pick))
            self.tree.see(str(pick))
        self.picked()

    def selected(self):
        try:
            sel = self.tree.selection()
        except tk.TclError:
            return None, None
        if not sel or int(sel[0]) >= len(self.macros):
            return None, None
        return int(sel[0]), self.macros[int(sel[0])]

    def picked(self):
        _k, m = self.selected()
        self.detail.set(mc.describe(self.slug, m) if m else "")
        builtin = bool(m and m.get("builtin"))
        for b in (self.edit_btn, self.del_btn):
            b.configure(state="disabled" if builtin or m is None else "normal")
        self.pin_btn.configure(text="Unpin" if m and m.get("pinned") else "Pin under the screen",
                               state="normal" if m else "disabled")
        self.hot_btn.configure(text="Ctrl+%d ▾" % m["hotkey"] if m and m.get("hotkey") else "Hotkey ▾",
                               state="normal" if m else "disabled")

    def play_state(self):
        playing = self.box.player is not None
        self.play_btn.configure(state="disabled" if playing or self.recorder is not None else "normal")
        self.stop_btn.configure(state="normal" if playing else "disabled")
        self.rec_btn.configure(state="disabled" if playing else "normal")

    # ---- Pins and hotkeys ----
    def toggle_pin(self):
        k, m = self.selected()
        if m is None:
            self.note.set("Pick a macro first")
            return
        if m.get("pinned"):
            m.pop("pinned", None)
            text = "%s isn't pinned any more" % m["name"]
        else:
            m["pinned"] = True
            text = "%s is a button under the screen now" % m["name"]
        self.store()
        self.fill(k)
        self.note.set(text)

    def hotkey_menu(self):
        k, m = self.selected()
        if m is None:
            self.note.set("Pick a macro first")
            return
        menu = th.menu(self.frame)
        menu.add_command(label="No hotkey", command=lambda: self.set_hotkey(None))
        menu.add_separator()
        for n in mc.HOTKEYS:
            other = self.box.by_hotkey(n)
            menu.add_command(label="Ctrl+%d%s" % (n, "" if other is None else "   (%s)" % other["name"]),
                             command=lambda n=n: self.set_hotkey(n))
        b = self.hot_btn
        try:
            menu.tk_popup(b.winfo_rootx(), b.winfo_rooty() + b.winfo_height())
        finally:
            menu.grab_release()

    def set_hotkey(self, n, ask=True):
        """Gives the picked macro Ctrl+n (None: none). A key another macro has: asked first,
        then moved."""
        k, m = self.selected()
        if m is None:
            return False
        other = self.box.by_hotkey(n) if n is not None else None
        if other is not None and other is not m and ask and not messagebox.askyesno(
                "Move the hotkey?", "Ctrl+%d plays %s now. Give it to %s instead?" % (
                    n, other["name"], m["name"]), parent=self.frame.winfo_toplevel()):
            return False
        try:
            was = mc.set_hotkey(self.macros, m, n)
        except mc.MacroError as e:
            self.note.set(str(e))
            return False
        self.store()
        self.fill(k)
        if n is None:
            self.note.set("%s has no hotkey now" % m["name"])
        else:
            self.note.set("Ctrl+%d plays %s on this tab%s" % (
                n, m["name"], " (%s has none now)" % was["name"] if was is not None else ""))
        return True

    # ---- Recording ----
    def toggle_record(self):
        if self.recorder is None:
            if self.box.player is not None:
                self.note.set("Wait for the macro to finish (or Stop it)")
                return
            self.recorder = mc.Recorder(self.slug, self.keep_pauses.get())
            self.box.recording = True
            self.m.key_taps.append(self.recorder.tap)
            self.rec_btn.configure(text="Stop recording", bg=th.RED, fg="#000000")
            self.play_btn.configure(state="disabled")
            self.save_row.pack_forget()
            self.tick()
            return
        rec, self.recorder = self.recorder, None
        self.box.recording = False
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
        if self.box.player is not None or self.recorder is not None:
            self.note.set("Stop the %s first" % ("macro" if self.box.player else "recording"))
            return
        self.box.play(m, self.frame)

    def stop(self):
        self.box.stop()

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
            c.pop("go", None)
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
        # A tab of the main window (a window of its own without it)
        w = self.win = tool_tabs.window(section.frame.winfo_toplevel(), "macro:%s" % self.slug,
                                        "Edit macro: %s" % m["name"])
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
        mc.set_prefs(m, self.orig)  # Its pin and hotkey stay
        self.section.edited(self.k, m)
        self.win.destroy()
