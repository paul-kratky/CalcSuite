# SPDX-License-Identifier: MIT
"""The Solver builder: type equations once, get a solver program for each calculator. A frame
(SolverPanel) that lives in a main-window tab, or in a thin window of its own (SolverWindow).

    import solver_ui
    solver_ui.open_builder(editor)     # from the Program editor (its "Solver builder..." button)

It shows the program for the TI-Nspire (Python), the TI-84 Plus CE and the TI-89 Titanium
as you type, with what the editor's checkers say about each. Send hands the chosen
calculator's program to the Program editor, which checks, builds and sends it the usual way
(one link per calculator, through its Mirror). Save writes each source and its calculator
file (.tns, .8xp, .89p) to CalcSuite files\\programs\\<calculator>\\.

The logic is in solver_builder.py (pure, tested without a window).

    python tools/solver_ui.py          opens it on its own (no calculator: Save only)
"""

import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import solver_builder as sb  # noqa: E402
import ui_theme as th  # noqa: E402

DEBOUNCE_MS = 300
TAB_TITLES = {"python": "TI-Nspire Python", "ti84": "TI-84 Plus CE", "ti89": "TI-89 Titanium"}
FOLDER = {"python": "nspire", "ti84": "ti84", "ti89": "ti89"}
OWN = "(your own equations)"
EXAMPLE = {"name": "zzohm", "title": "Ohm's law", "equations": ["V = I*R", "P = V*I"],
           "vars": {"V": {"unit": "V", "desc": "voltage"}, "I": {"unit": "A", "desc": "current"},
                    "R": {"unit": "ohm", "desc": "resistance"}, "P": {"unit": "W", "desc": "power"}},
           "degrees": False}

_OPEN = []


def log_error(where):
    """mirror.log_error (CalcSuite files\\logs\\errors.log); never raises"""
    try:
        mod = sys.modules.get("mirror")
        if mod is None:
            import mirror as mod
        mod.log_error(where)
    except Exception:
        pass


def open_builder(editor):
    """The builder for this editor: an open one comes to the front. When the main window can
    hold it as a tab (host.open_tool_tab(key, title, make_frame) -> the frame), it goes there;
    otherwise in a thin window of its own (SolverWindow)."""
    for b in list(_OPEN):
        if b.editor is editor and b.alive():
            b.show()
            b.refresh_targets()
            return b
    host = getattr(editor, "host", None) if editor is not None else None
    opener = getattr(host, "open_tool_tab", None)
    if opener is not None:
        try:
            return opener("solver", "Solver builder", lambda parent: SolverPanel(parent, editor))
        except Exception:
            log_error("opening the Solver builder as a tab")
    return SolverWindow(editor).panel


class SolverWindow(object):
    """A thin window around a SolverPanel (until the main window holds it as a tab)"""
    def __init__(self, editor, master=None):
        master = master or (editor.win.winfo_toplevel() if editor is not None else None)
        self.top = top = tk.Toplevel(master)
        top.title("Solver builder")
        top.configure(bg=th.BG)
        top.geometry("1220x780")
        top.minsize(900, 560)
        self.panel = SolverPanel(top, editor, on_close=self.destroy)
        self.panel.pack(fill="both", expand=True)
        top.protocol("WM_DELETE_WINDOW", self.panel.close)
        top.bind("<Escape>", lambda e: self.panel.close())
        th.dark_title_bar_when_shown(top)

    def destroy(self):
        try:
            self.top.destroy()
        except tk.TclError:
            pass


class SolverPanel(tk.Frame):
    """The whole builder as a frame: it lives in a main-window tab or in a SolverWindow"""
    def __init__(self, parent, editor=None, on_close=None):
        """editor: the Program editor (tools/editor.py) whose send path is used, or None (Save
        only). on_close: what Close does (the host takes the frame away); None: no Close button"""
        tk.Frame.__init__(self, parent, bg=th.BG)
        self.editor = editor
        self.on_close = on_close
        self.win = w = self
        th.style_ttk(w)
        st = ttk.Style(w)
        st.configure("Solver.TNotebook", background=th.BG, borderwidth=0)
        st.configure("Solver.TNotebook.Tab", background=th.PANEL2, foreground=th.DIM, padding=(12, 5),
                     borderwidth=0)
        st.map("Solver.TNotebook.Tab", background=[("selected", th.ACTIVE)],
               foreground=[("selected", "#ffffff")])
        st.configure("TCombobox", fieldbackground=th.PANEL2, background=th.PANEL2, foreground=th.FG,
                     arrowcolor=th.FG, bordercolor=th.LINE, lightcolor=th.PANEL2, darkcolor=th.PANEL2)
        st.map("TCombobox", fieldbackground=[("readonly", th.PANEL2)], foreground=[("readonly", th.FG)],
               selectbackground=[("readonly", th.PANEL2)], selectforeground=[("readonly", th.FG)])
        w.option_add("*TCombobox*Listbox.background", th.PANEL2)
        w.option_add("*TCombobox*Listbox.foreground", th.FG)
        w.option_add("*TCombobox*Listbox.selectBackground", th.ACCENT)
        self.plan = None
        self.outs = {}
        self.error = ""
        self._job = None
        self._loading = False
        self.saved = []        # For tests: the files the last Save wrote
        self.targets = []      # [(label, Mirror, language)] from the editor
        self._build()
        self.load_spec(EXAMPLE)
        self.refresh_targets()
        _OPEN.append(self)

    def alive(self):
        try:
            return bool(self.winfo_exists())
        except tk.TclError:
            return False

    def dialog_parent(self):
        return self.winfo_toplevel()

    def show(self):
        """Brings it forward: its own window, or its tab"""
        top = self.winfo_toplevel()
        host = getattr(self.editor, "host", None) if self.editor is not None else None
        if host is not None and top is getattr(host, "root", None) and hasattr(host, "show_tab"):
            try:
                host.show_tab("solver")
            except Exception:
                log_error("showing the Solver builder tab")
            return
        top.deiconify()
        top.lift()

    # ---- The window ----
    def _text(self, parent, height, mono=True, readonly=False):
        frame = tk.Frame(parent, bg=th.LINE, bd=0)
        t = tk.Text(frame, height=height, bg=th.PANEL, fg=th.FG, insertbackground=th.FG, relief="flat",
                    bd=0, padx=6, pady=4, wrap="none", undo=not readonly,
                    font=(th.MONO, 10) if mono else (th.FONT, 10), highlightthickness=0,
                    selectbackground="#264F78")
        sb_ = ttk.Scrollbar(frame, orient="vertical", command=t.yview, style="Calc.Vertical.TScrollbar")
        t.configure(yscrollcommand=sb_.set)
        sb_.pack(side="right", fill="y")
        t.pack(side="left", fill="both", expand=True, padx=1, pady=1)
        if readonly:
            t.configure(state="disabled")
        return frame, t

    def _entry(self, parent, var, width):
        return tk.Entry(parent, textvariable=var, width=width, bg=th.PANEL2, fg=th.FG,
                        insertbackground=th.FG, relief="flat", font=(th.MONO, 10))

    def _build(self):
        w = self.win
        bottom = tk.Frame(w, bg=th.BG)
        bottom.pack(side="bottom", fill="x", padx=10, pady=(4, 10))
        self.status_var = tk.StringVar(master=w, value="")
        self.status = tk.Label(bottom, textvariable=self.status_var, bg=th.BG, fg=th.FG, anchor="w",
                               justify="left", wraplength=520)
        self.status.pack(side="left", fill="x", expand=True)
        if self.on_close is not None:
            th.button(bottom, "Close", self.close).pack(side="right", padx=(6, 0))
        self.save_button = th.button(bottom, "Save files...", self.save)
        self.save_button.pack(side="right", padx=(6, 0))
        self.editor_button = th.button(bottom, "Open in the editor", self.open_in_editor)
        self.editor_button.pack(side="right", padx=(6, 0))
        self.send_button = th.button(bottom, "Send", self.send, bg="#0E639C", activebackground="#1177BB")
        self.send_button.pack(side="right", padx=(6, 0))
        self.target_var = tk.StringVar(master=w)
        self.target_box = ttk.Combobox(bottom, textvariable=self.target_var, state="readonly", width=36)
        self.target_box.pack(side="right", padx=(6, 0))
        self.target_box.bind("<<ComboboxSelected>>", lambda e: self.target_changed())
        th.label(bottom, "Send to", fg=th.DIM).pack(side="right", padx=(12, 0))

        pane = tk.PanedWindow(w, orient="horizontal", bg=th.LINE, sashwidth=4, bd=0)
        pane.pack(side="top", fill="both", expand=True, padx=10, pady=(10, 0))
        left = tk.Frame(pane, bg=th.BG)
        right = tk.Frame(pane, bg=th.BG)
        pane.add(left, minsize=360, width=470)
        pane.add(right, minsize=380, stretch="always")

        # ---- Left: what the user types ----
        row = tk.Frame(left, bg=th.BG)
        row.pack(fill="x", pady=(0, 6))
        th.label(row, "Start from", fg=th.DIM).pack(side="left")
        self.template_var = tk.StringVar(master=w, value=OWN)
        self.template_box = ttk.Combobox(row, textvariable=self.template_var, state="readonly", width=38,
                                         values=[OWN] + [t["label"] for t in sb.TEMPLATES])
        self.template_box.pack(side="left", padx=(6, 0))
        self.template_box.bind("<<ComboboxSelected>>", lambda e: self.use_template())

        row = tk.Frame(left, bg=th.BG)
        row.pack(fill="x", pady=(0, 6))
        th.label(row, "Name", fg=th.DIM).pack(side="left")
        self.name_var = tk.StringVar(master=w)
        self._entry(row, self.name_var, 10).pack(side="left", padx=(6, 12), ipady=3)
        th.label(row, "Title", fg=th.DIM).pack(side="left")
        self.title_var = tk.StringVar(master=w)
        self._entry(row, self.title_var, 24).pack(side="left", padx=(6, 0), fill="x", expand=True, ipady=3)
        self.degrees_var = tk.IntVar(master=w, value=0)
        th.check(left, "Angles in degrees (sin, cos, tan and their inverses)", self.degrees_var,
                 self.schedule).pack(anchor="w", pady=(0, 6))
        for var in (self.name_var, self.title_var):
            var.trace_add("write", lambda *a: self.schedule())

        th.label(left, "Equations, one per line (V = I*R; * to multiply, ^ for powers; sqrt, ln, "
                 "log, exp, sin, ... pi)", fg=th.DIM, wraplength=450, justify="left").pack(anchor="w")
        f, self.eq_text = self._text(left, 6)
        f.pack(fill="x", pady=(2, 6))
        row = tk.Frame(left, bg=th.BG)
        row.pack(fill="x")
        th.label(row, "Variables: name [unit] description", fg=th.DIM).pack(side="left")
        th.button(row, "Add the missing ones", self.add_missing_vars, pady=2).pack(side="right")
        f, self.vars_text = self._text(left, 7)
        f.pack(fill="x", pady=(2, 6))
        for t in (self.eq_text, self.vars_text):
            t.bind("<<Modified>>", self._modified)

        th.label(left, "How each variable is found", fg=th.DIM).pack(anchor="w")
        tf = tk.Frame(left, bg=th.BG)
        tf.pack(fill="both", expand=True, pady=(2, 0))
        cols = ("eq", "var", "how", "answer")
        self.tree = ttk.Treeview(tf, columns=cols, show="headings", style="Calc.Treeview", height=8)
        for c, title, width in (("eq", "Equation", 120), ("var", "Find", 60), ("how", "How", 70),
                                ("answer", "Answer", 260)):
            self.tree.heading(c, text=title)
            self.tree.column(c, width=width, stretch=(c == "answer"))
        tsb = ttk.Scrollbar(tf, orient="vertical", command=self.tree.yview, style="Calc.Vertical.TScrollbar")
        self.tree.configure(yscrollcommand=tsb.set)
        tsb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)

        # ---- Right: each calculator's program ----
        self.book = ttk.Notebook(right, style="Solver.TNotebook")
        self.book.pack(fill="both", expand=True)
        self.tabs = {}
        for lang in sb.LANGS:
            page = tk.Frame(self.book, bg=th.BG)
            head = tk.Label(page, text="", bg=th.BG, fg=th.DIM, anchor="w", justify="left", wraplength=640)
            head.pack(fill="x", pady=(6, 4))
            f, t = self._text(page, 20, readonly=True)
            f.pack(fill="both", expand=True)
            self.book.add(page, text=TAB_TITLES[lang])
            self.tabs[lang] = {"page": page, "head": head, "text": t}
        self.book.bind("<<NotebookTabChanged>>", lambda e: self.update_buttons())

    # ---- Loading and reading the fields ----
    def load_spec(self, spec, template=OWN):
        self._loading = True
        try:
            self.template_var.set(template)
            self.name_var.set(spec.get("name", ""))
            self.title_var.set(spec.get("title", ""))
            self.degrees_var.set(1 if spec.get("degrees") else 0)
            self._set(self.eq_text, "\n".join(spec.get("equations", [])))
            order = []
            for e in spec.get("equations", []):
                try:
                    l, r = sb.parse_equation(e)
                    order += [v for v in sb.variables(l) + sb.variables(r) if v not in order]
                except sb.SolverError:
                    pass
            self._set(self.vars_text, sb.vars_text(spec.get("vars", {}), order))
        finally:
            self._loading = False
        self.rebuild()

    @staticmethod
    def _set(t, text):
        t.delete("1.0", "end")
        t.insert("1.0", text)
        t.edit_modified(False)

    def spec(self):
        return sb.spec_from_text(self.name_var.get(), self.title_var.get(),
                                 self.eq_text.get("1.0", "end-1c"), self.vars_text.get("1.0", "end-1c"),
                                 self.degrees_var.get())

    def use_template(self):
        lab = self.template_var.get()
        t = next((t for t in sb.TEMPLATES if t["label"] == lab), None)
        if t is None:
            return
        self.load_spec(sb.template_spec(t["key"]), lab)
        self.set_status("Loaded %s. Change anything; the programs follow." % t["label"], th.MINT)

    def add_missing_vars(self):
        """Adds a line for each variable in the equations that has none yet"""
        try:
            spec = self.spec()
        except sb.SolverError as e:
            self.set_status(str(e), th.RED)
            return
        have = spec["vars"]
        missing = []
        for e in spec["equations"]:
            try:
                l, r = sb.parse_equation(e)
            except sb.SolverError:
                continue
            missing += [v for v in sb.variables(l) + sb.variables(r) if v not in have and v not in missing]
        if not missing:
            self.set_status("Every variable has its line", th.DIM)
            return
        text = self.vars_text.get("1.0", "end-1c").rstrip("\n")
        self._set(self.vars_text, (text + "\n" if text else "") + "\n".join("%s [] " % v for v in missing))
        self.rebuild()

    # ---- Rebuilding the programs ----
    def _modified(self, e):
        if e.widget.edit_modified():
            e.widget.edit_modified(False)
            self.schedule()

    def schedule(self):
        if self._loading:
            return
        if self._job is not None:
            try:
                self.win.after_cancel(self._job)
            except tk.TclError:
                pass
        self._job = self.win.after(DEBOUNCE_MS, self.rebuild)

    def rebuild(self):
        """The plan, every calculator's program and its check, from the fields now"""
        self._job = None
        self.error = ""
        try:
            self.plan = sb.build(self.spec())
            self.outs = sb.check_all(self.plan)
        except sb.SolverError as e:
            self.plan, self.outs, self.error = None, {}, str(e)
        except Exception as e:  # Never take the window down over one equation
            log_error("building a solver")
            self.plan, self.outs, self.error = None, {}, "Couldn't build it: %s" % e
        self.tree.delete(*self.tree.get_children())
        if self.plan:
            last = None
            for eq, v, how, text, note in sb.solution_rows(self.plan):
                self.tree.insert("", "end", values=(eq if eq != last else "", v, how,
                                                    text + ("  (%s)" % note if note else "")))
                last = eq
        for lang, tab in self.tabs.items():
            o = self.outs.get(lang)
            t = tab["text"]
            t.configure(state="normal")
            t.delete("1.0", "end")
            if o:
                t.insert("1.0", o["text"])
                ok = not o["errors"] and not o["build_error"]
                if o["build_error"]:
                    head = "Not ready: %s" % o["build_error"]
                elif o["errors"]:
                    p = next(p for p in o["problems"] if p["severity"] == "error")
                    head = "Not ready: %d error(s). Line %d: %s" % (o["errors"], p["line"], p["message"])
                else:
                    head = "%s, checked: no errors%s. %d lines, program %s" % (
                        TAB_TITLES[lang], ", %d warning(s)" % o["warnings"] if o["warnings"] else
                        ", no warnings", o["text"].count("\n"), o["name"])
                tab["head"].configure(text=head, fg=th.MINT if ok and not o["warnings"] else
                                      (th.ACCENT if ok else th.RED))
            else:
                t.insert("1.0", "Type an equation on the left (like V = I*R) and a name;\n"
                                "the program for this calculator shows here.")
                tab["head"].configure(text=self.error or "", fg=th.RED)
            t.configure(state="disabled")
        if self.error:
            self.set_status(self.error, th.RED)
        elif self.plan:
            numeric = sum(1 for r in sb.solution_rows(self.plan) if r[2] == "numeric")
            self.set_status("%d equation(s), %d variable(s)%s. Pick a calculator and Send, or Save." % (
                len(self.plan["formulas"]), len(self.plan["order"]),
                "; %d found numerically from a guess" % numeric if numeric else ""), th.DIM)
        self.update_buttons()

    def ready(self, lang):
        o = self.outs.get(lang)
        return bool(o) and not o["errors"] and not o["build_error"]

    def current_lang(self):
        try:
            return sb.LANGS[self.book.index(self.book.select())]
        except (tk.TclError, ValueError, IndexError):
            return sb.LANGS[0]

    def set_status(self, text, colour=None):
        self.status_var.set(text)
        self.status.configure(fg=colour or th.FG)

    # ---- Calculators ----
    def refresh_targets(self):
        """The editor's calculators that take a program (connected or not)"""
        self.targets = []
        if self.editor is not None:
            try:
                self.editor.targets = self.editor._targets()
                self.editor._fill_targets()
            except (AttributeError, tk.TclError):
                pass
            self.targets = [(l, m, lang) for (l, m, lang) in self.editor.targets if m is not None]
        labels = [t[0] for t in self.targets] or ["No calculator connected: Save only"]
        self.target_box.configure(values=labels)
        k = 0
        if self.editor is not None and self.targets:
            cur = self.editor.target()
            k = next((i for i, t in enumerate(self.targets) if t[1] is cur), 0)
        self.target_box.current(k)
        self.target_changed()

    def target(self):
        if not self.targets:
            return None
        k = self.target_box.current()
        return self.targets[k] if 0 <= k < len(self.targets) else None

    def target_changed(self):
        t = self.target()
        if t is not None:
            self.book.select(sb.LANGS.index(t[2]))
        self.update_buttons()

    def update_buttons(self):
        t = self.target()
        can_send = t is not None and self.ready(t[2])
        self.send_button.configure(state="normal" if can_send else "disabled")
        self.editor_button.configure(state="normal" if self.editor is not None and
                                     self.ready(self.current_lang()) else "disabled")
        self.save_button.configure(state="normal" if self.outs and all(self.ready(l) for l in sb.LANGS)
                                   else "disabled")

    # ---- Send, open, save ----
    def _hand_to_editor(self, lang, mirror=None):
        """Puts the program into the Program editor (asking first about unsaved changes there).
        True when it is there."""
        e = self.editor
        o = self.outs[lang]
        if not e.confirm_discard():
            self.set_status("Kept the editor's own program: nothing changed", th.DIM)
            return False
        e.path = None
        if mirror is not None:
            e.set_target(mirror)
        e.set_language(lang)
        e.name_var.set(o["name"])
        e.set_text(o["text"], modified=False)
        e.refresh_all()
        return True

    def send(self):
        if self._job is not None:
            self.rebuild()
        t = self.target()
        if t is None:
            self.set_status("No calculator connected: Save the files instead", th.ACCENT)
            return False
        label, m, lang = t
        if not self.ready(lang):
            self.set_status("The %s program isn't ready: see the line above its code" % TAB_TITLES[lang],
                            th.RED)
            return False
        if hasattr(m, "connected") and not m.connected():
            self.set_status("The %s isn't connected yet" % m.calc.title, th.ACCENT)
            return False
        if not self._hand_to_editor(lang, m):
            return False
        ok = self.editor.send(run=False)
        self.set_status("Sending %s to the %s through the Program editor (its status line says when "
                        "it's there)" % (self.outs[lang]["name"], m.calc.title) if ok else
                        "Not sent: the Program editor says why at its bottom", th.MINT if ok else th.RED)
        return ok

    def open_in_editor(self):
        lang = self.current_lang()
        if self.editor is None or not self.ready(lang):
            return False
        m = next((t[1] for t in self.targets if t[2] == lang), None)
        if not self._hand_to_editor(lang, m):
            return False
        host = getattr(self.editor, "host", None)
        if host is not None:
            try:
                host.show_tab("editor")
            except Exception:
                log_error("showing the Program editor")
        self.set_status("%s is in the Program editor" % self.outs[lang]["name"], th.MINT)
        return True

    def default_folder(self):
        try:
            import editor as ed
            return ed.PROGRAMS
        except Exception:
            import paths
            return os.path.join(paths.files_dir(), "programs")

    def save(self, folder=None, ask=True):
        """Each calculator's source and its file, in <folder>\\nspire, \\ti84, \\ti89 (the
        Program editor's builds folder by default). Returns the files written."""
        if self._job is not None:
            self.rebuild()
        if not self.outs or not all(self.ready(l) for l in sb.LANGS):
            self.set_status("Fix the problems first: every calculator's program must check clean", th.RED)
            return []
        if folder is None:
            base = self.default_folder()
            os.makedirs(base, exist_ok=True)
            folder = filedialog.askdirectory(parent=self.dialog_parent(), title="Save the solver programs in",
                                             initialdir=base, mustexist=False) if ask else base
            if not folder:
                return []
        plan = self.plan
        files = self.files_for(folder)
        there = [p for p, _d in files if os.path.exists(p)]
        if there and ask and not messagebox.askyesno(
                "Replace?", "%d of the files are there already (%s). Replace them?" % (
                    len(there), ", ".join(os.path.basename(p) for p in there[:4])), parent=self.dialog_parent()):
            self.set_status("Not saved", th.DIM)
            return []
        written = []
        try:
            for path, data in files:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                if data is None:  # The .tns: made from the .py beside it
                    import py2tns
                    py2tns.convert(path[:-4] + ".py", path, quiet=True)
                else:
                    with open(path, "wb") as fh:
                        fh.write(data)
                written.append(path)
        except Exception as e:
            log_error("saving the solver %s" % plan["name"])
            self.set_status("Not all saved: %s" % e, th.RED)
            self.saved = written
            return written
        self.saved = written
        self.set_status("Saved %d files in %s (nspire, ti84, ti89)" % (len(written), folder), th.MINT)
        return written

    def files_for(self, folder):
        """[(path, bytes or None for the .tns)]"""
        import calc_files as cf
        out = []
        for lang in sb.LANGS:
            o = self.outs[lang]
            sub = os.path.join(folder, FOLDER[lang])
            text = o["text"].encode("utf-8")
            if lang == "python":
                out.append((os.path.join(sub, o["name"] + ".py"), text))
                out.append((os.path.join(sub, o["name"] + ".tns"), None))
            elif lang == "ti84":
                out.append((os.path.join(sub, o["name"] + ".txt"), text))
                out.append((os.path.join(sub, o["name"] + ".8xp"), cf.program_8xp(o["text"], o["name"])))
            else:
                name, vtype, blob = cf.program_89p(o["text"], o["name"])
                out.append((os.path.join(sub, name + ".txt"), text))
                out.append((os.path.join(sub, name + ".89p"), blob))
        return out

    def close(self):
        """Close: the frame goes, then its host (window or tab) is told"""
        if self in _OPEN:
            _OPEN.remove(self)
        try:
            self.destroy()
        except tk.TclError:
            pass
        if self.on_close is not None:
            try:
                self.on_close()
            except Exception:
                log_error("closing the Solver builder")


def main(argv):
    """On its own: an editor without calculators behind it (Save, Open in the editor)"""
    import editor as ed
    root = tk.Tk()
    root.withdraw()
    e = ed.open_editor(root, [], None)
    w = SolverWindow(e)
    w.panel.on_close = lambda: (w.destroy(), root.destroy())
    root.mainloop()


if __name__ == "__main__":
    main(sys.argv[1:])
