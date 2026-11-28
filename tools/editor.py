# SPDX-License-Identifier: MIT
"""CalcSuite's program editor: write TI-84 Plus CE TI-Basic, TI-89 Titanium TI-Basic or
TI-Nspire Python, check it as you type, send it to a calculator and run it.

    import editor
    editor.open_editor(app, mirrors, initial_target=mirror, path=None)

The checks, colours, completions and hints come from code_check.py (pure, tested without a
window); this file is the window. It talks to a calculator only through its Mirror (the
link thread's queue), never a second connection. docs/dev/EDITOR_API.md has the details.

F5: check, then send and run (the 84: Quit, Clear, Clear, prgm, its name, Enter; the 89:
the Home screen, name(), Enter; the Nspire: sent, then you open it). F6: check, then send.
"""

import os
import queue
import re
import sys
import tempfile
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.join(HERE, "ti84_cli"), os.path.join(HERE, "nspire_cli")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import calc_files as cf  # noqa: E402
import code_check as cc  # noqa: E402
import ui_theme as th  # noqa: E402

import paths  # noqa: E402

DOCS = paths.files_dir()  # Beside CalcSuite.exe (the zip), else Documents\CalcSuite
PROGRAMS = os.path.join(DOCS, "programs")
LANG_OF_SLUG = {"ti84": "ti84", "ti89": "ti89", "nspire": "python"}
SLUG_OF_LANG = {"ti84": "ti84", "ti89": "ti89", "python": "nspire"}
SHORT = {"ti84": "TI-84 Plus CE Basic", "ti89": "TI-89 Titanium Basic", "python": "Nspire Python"}
CALC_FOLDER = {"ti84": "ti84", "ti89": "ti89", "python": "nspire"}  # Builds: PROGRAMS\<this>
DEBOUNCE_MS = 300
INDENT_PX = 18
# VS Code's Dark+ theme
SEV_COLOUR = {"error": "#F14C4C", "warning": "#CCA700", "info": "#3794FF"}
SEV_ICON = {"error": "✖ Error", "warning": "▲ Warning", "info": "ℹ Info"}
COLOURS = {"control": "#C586C0", "storage": "#569CD6", "builtin": "#DCDCAA", "variable": "#9CDCFE",
           "sysvar": "#4EC9B0", "string": "#CE9178", "number": "#B5CEA8", "comment": "#6A9955",
           "symbol": "#4FC1FF"}
EDITOR_BG = "#1E1E1E"
EDITOR_FG = "#D4D4D4"   # Operators and punctuation
GUTTER_FG = "#858585"
CURRENT_LINE = "#2A2D2E"
BRACKET_BG = "#3A3D41"
PANEL_BG = "#252526"     # The bars around the editor (VS Code's side bar colour)
PROGRAM_TYPES = {"ti84": (0x05, 0x06), "ti89": (0x12, 0x13)}


def copy_file_to_clipboard(widget, path):
    """The file itself on the Windows clipboard (CF_HDROP), so it pastes into Discord, an
    e-mail or Explorer; elsewhere (or if that fails) its path as text. Returns "file" or "path"."""
    try:
        import ctypes
        from ctypes import wintypes
        k32, u32 = ctypes.windll.kernel32, ctypes.windll.user32
        k32.GlobalAlloc.restype = ctypes.c_void_p
        k32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
        k32.GlobalLock.restype = ctypes.c_void_p
        k32.GlobalLock.argtypes = [ctypes.c_void_p]
        k32.GlobalUnlock.argtypes = [ctypes.c_void_p]
        k32.GlobalFree.argtypes = [ctypes.c_void_p]
        u32.SetClipboardData.restype = ctypes.c_void_p
        u32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
        u32.OpenClipboard.argtypes = [wintypes.HWND]
        files = (os.path.abspath(path) + "\0\0").encode("utf-16-le")
        head = (20).to_bytes(4, "little") + b"\0" * 12 + (1).to_bytes(4, "little")  # DROPFILES, wide
        data = head + files
        h = k32.GlobalAlloc(0x0042, len(data))  # GMEM_MOVEABLE | GMEM_ZEROINIT
        p = k32.GlobalLock(h)
        ctypes.memmove(p, data, len(data))
        k32.GlobalUnlock(h)
        if not u32.OpenClipboard(None):
            k32.GlobalFree(h)
            raise OSError("the clipboard is busy")
        try:
            u32.EmptyClipboard()
            if not u32.SetClipboardData(15, h):  # CF_HDROP; Windows owns it from here
                raise OSError("the clipboard refused the file")
        finally:
            u32.CloseClipboard()
        return "file"
    except (AttributeError, OSError, ValueError):
        widget.clipboard_clear()
        widget.clipboard_append(os.path.abspath(path))
        return "path"


def open_folder(path):
    """Explorer with the file selected"""
    try:
        import subprocess
        subprocess.Popen(["explorer", "/select,", os.path.abspath(path)])
    except OSError:
        os.startfile(os.path.dirname(os.path.abspath(path)))


def open_editor(app_or_root, mirrors=(), initial_target=None, path=None):
    """The editor window. app_or_root: the App (its .root is used) or any Tk widget. mirrors:
    the connected calculators (Mirror objects) to offer as targets. initial_target: one of
    them, a slug ("ti84", "ti89", "nspire") or None (no calculator: save only). path: a file
    to open. Returns the Editor."""
    if hasattr(app_or_root, "open_editor_tab"):  # The main window: the editor is its tab
        return app_or_root.open_editor_tab(initial_target, path)
    master = getattr(app_or_root, "root", app_or_root)
    return Editor(master, list(mirrors or ()), initial_target, path)


def _dark_title_bar(win):
    """A dark title bar on this window, now and once it's on screen (ui_theme's helper: it works
    whether or not the main app is running, and retries until Windows has made the title bar)"""
    th.dark_title_bar_when_shown(win)


def detect_language(text, path=None):
    """A file's language: .py is Python; TI-Basic text with an 89 first line or Prgm is the 89's"""
    if path and path.lower().endswith(".py"):
        return "python"
    if path and path.lower().endswith((".89p", ".89f", ".89t")):
        return "ti89"
    if path and path.lower().endswith(".8xp"):
        return "ti84"
    lines = [l.strip().lstrip(":").strip() for l in text.split("\n") if l.strip()]
    low = [l.lower() for l in lines[:3]]
    if any(l in ("prgm", "func") for l in low) or (lines and re.match(r"^[a-z][a-z0-9_]{0,7}\([^)]*\)$", lines[0])):
        return "ti89"
    if any(re.match(r"^(import |from |def |print\()", l) for l in lines[:8]):
        return "python"
    return "ti84"


def strip_fences(text):
    """A chat AI's answer pasted whole: the code inside its ``` fence"""
    m = re.search(r"```[^\n]*\n(.*?)```", text, re.S)
    return m.group(1) if m else text


_OPEN = []  # The editor windows open now


def ask_save(parent, name):
    """The dark "Save changes to <name>?" dialog: "save", "discard" or "cancel". Modal; Esc
    and the window's X are Cancel. (Tests replace this function.)"""
    d = tk.Toplevel(parent)
    d.title("Save changes?")
    d.configure(bg=PANEL_BG)
    d.resizable(False, False)
    d.transient(parent)
    res = ["cancel"]

    def pick(v):
        res[0] = v
        d.destroy()
    tk.Label(d, text="Save changes to %s?" % name, bg=PANEL_BG, fg=EDITOR_FG, font=(th.FONT, 11, "bold"),
             padx=18, pady=(14)).pack(anchor="w")
    tk.Label(d, text="Your changes are lost if you don't save them.", bg=PANEL_BG, fg=th.DIM,
             padx=18).pack(anchor="w")
    row = tk.Frame(d, bg=PANEL_BG)
    row.pack(fill="x", padx=14, pady=14)
    save = th.button(row, "Save", lambda: pick("save"), bg="#0E639C", activebackground="#1177BB")
    save.pack(side="right", padx=4)
    th.button(row, "Don't save", lambda: pick("discard")).pack(side="right", padx=4)
    th.button(row, "Cancel", lambda: pick("cancel")).pack(side="right", padx=4)
    d.bind("<Escape>", lambda e: pick("cancel"))
    d.bind("<Return>", lambda e: pick("save"))
    d.protocol("WM_DELETE_WINDOW", lambda: pick("cancel"))
    d.update_idletasks()
    try:
        x = parent.winfo_rootx() + (parent.winfo_width() - d.winfo_width()) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - d.winfo_height()) // 3
        d.geometry("+%d+%d" % (max(0, x), max(0, y)))
    except tk.TclError:
        pass
    _dark_title_bar(d)
    save.focus_set()
    try:
        d.grab_set()
    except tk.TclError:
        pass
    parent.wait_window(d)
    return res[0]


def open_editors():
    """The editor windows open now"""
    return list(_OPEN)


def confirm_close_all(parent=None):
    """For App.quit(): asks about each editor with unsaved changes (Save / Don't save /
    Cancel). True: fine to quit (the editors are closed); False: the user cancelled, keep
    running (nothing was closed after the cancelled one)."""
    for e in list(_OPEN):
        if e.unsaved() and not e.confirm_discard():
            return False
    for e in list(_OPEN):
        e.close(force=True)
    return True


class Editor(object):
    def __init__(self, master, mirrors, initial_target=None, path=None, host=None):
        """host: the main window (mirror.App) when the editor is its tab; None: its own window
        (python tools/editor.py)"""
        self.master = master
        self.host = host
        self._key_tag = "EditorKeys%d" % id(self)  # The shortcuts' bind tag in a tab
        self.mirrors = mirrors
        self.path = None           # The text file being edited (never a .8xp)
        self.lang = "ti84"
        self.problems = []
        self.sent_names = set()    # Names this window has sent (no Replace? question again)
        self._inbox = queue.SimpleQueue()  # Work from the link thread for Tk's thread
        self._check_job = None
        self._hover_job = None
        self._hover_win = None
        self._popup = None
        self._popup_items = []
        self._closed = False
        _OPEN.append(self)
        self.last_queued = []      # For tests: what this window asked the link for
        if host is not None:
            self.win = w = host.editor_frame  # A tab of the main window
            w.configure(bg=PANEL_BG)
        else:
            self.win = w = tk.Toplevel(master)
            w.title("Program editor")
            w.configure(bg=PANEL_BG)
            w.geometry("1000x720")
            w.minsize(640, 420)
        st = th.style_ttk(w)
        st.configure("Editor.Treeview", background=PANEL_BG, fieldbackground=PANEL_BG, foreground=EDITOR_FG,
                     rowheight=22, borderwidth=0, bordercolor=PANEL_BG, lightcolor=PANEL_BG, darkcolor=PANEL_BG)
        st.layout("Editor.Treeview", [("Editor.Treeview.treearea", {"sticky": "nswe"})])
        st.map("Editor.Treeview", background=[("selected", "#04395E")], foreground=[("selected", "#ffffff")])
        st.configure("Editor.Treeview.Heading", background=PANEL_BG, foreground=th.DIM, relief="flat")
        st.configure("TCombobox", fieldbackground=th.PANEL2, background=th.PANEL2, foreground=th.FG,
                     arrowcolor=th.FG, bordercolor=th.LINE, lightcolor=th.PANEL2, darkcolor=th.PANEL2)
        st.map("TCombobox", fieldbackground=[("readonly", th.PANEL2)], foreground=[("readonly", th.FG)],
               selectbackground=[("readonly", th.PANEL2)], selectforeground=[("readonly", th.FG)])
        w.option_add("*TCombobox*Listbox.background", th.PANEL2)
        w.option_add("*TCombobox*Listbox.foreground", th.FG)
        w.option_add("*TCombobox*Listbox.selectBackground", th.ACCENT)
        self._build()
        self.targets = self._targets()
        self._fill_targets()
        self.target_index = len(self.targets) - 1
        self.set_target(initial_target)
        if path:
            self.open_path(path)
        else:
            self.new(self.lang, ask=False)
        if host is None:
            w.protocol("WM_DELETE_WINDOW", self.close)
            w.after(10, lambda: _dark_title_bar(w))
        else:
            self._tag_keys(w)
        w.after(40, self._pump)
        self.text.focus_set()

    def _tag_keys(self, widget):
        """In a tab, the window-wide shortcuts (Ctrl+S, F5...) are bound to a tag every widget
        of the editor carries (a Toplevel's own tag does that for the editor's own window)"""
        tags = list(widget.bindtags())
        if self._key_tag not in tags:
            widget.bindtags(tuple(tags[:1] + [self._key_tag] + tags[1:]))
        for child in widget.winfo_children():
            self._tag_keys(child)

    # ---- Building the window ----
    def _build(self):
        w = self.win
        bar = tk.Frame(w, bg=PANEL_BG)
        bar.pack(side="top", fill="x")
        self.menus = {}
        for title, items in self._menu_items():
            mb = tk.Menubutton(bar, text=title, bg=PANEL_BG, fg=th.FG, activebackground=th.ACTIVE,
                               activeforeground="#ffffff", relief="flat", padx=10, pady=4, bd=0,
                               highlightthickness=0, cursor="hand2")
            m = th.menu(mb)
            for it in items:
                if it is None:
                    m.add_separator()
                elif it[0] == "radio":
                    m.add_radiobutton(label=it[1], variable=it[2], value=it[3], command=it[4])
                elif it[0] == "cascade":
                    sub = th.menu(m)
                    for lab, cmd in it[2]:
                        sub.add_command(label=lab, command=cmd)
                    m.add_cascade(label=it[1], menu=sub)
                else:
                    m.add_command(label=it[0], command=it[1], accelerator=it[2] if len(it) > 2 else "")
            mb.configure(menu=m)
            mb.pack(side="left")
            self.menus[title] = m

        top = tk.Frame(w, bg=PANEL_BG)
        top.pack(side="top", fill="x", padx=8, pady=(6, 4))
        th.label(top, "Calculator", fg=th.DIM, bg=PANEL_BG).pack(side="left")
        self.target_var = tk.StringVar(master=w)
        self.target_box = ttk.Combobox(top, textvariable=self.target_var, state="readonly", width=34)
        self.target_box.pack(side="left", padx=(6, 12))
        self.target_box.bind("<<ComboboxSelected>>", lambda e: self.set_target(self.target_box.current()))
        th.label(top, "Name", fg=th.DIM, bg=PANEL_BG).pack(side="left")
        self.name_var = tk.StringVar(master=w)
        self.name_entry = tk.Entry(top, textvariable=self.name_var, width=10, bg=th.PANEL2, fg=th.FG,
                                   insertbackground=th.FG, relief="flat", font=(th.MONO, 10))
        self.name_entry.pack(side="left", padx=(6, 12), ipady=3)
        self.name_var.trace_add("write", lambda *a: self.schedule_check())
        self.lang_label = th.label(top, "", fg=th.DIM, bg=PANEL_BG)
        for text, cmd in (("Copy AI instructions", self.copy_ai_instructions),
                          ("Build (Ctrl+B)", self.build),
                          ("Send (F6)", lambda: self.send(run=False)),
                          ("Send and run (F5)", lambda: self.send(run=True)),
                          ("Check", self.check_now),
                          ("Solver builder...", self.open_solver_builder)):
            b = th.button(top, text, cmd)
            b.pack(side="right", padx=(6, 0))
            if text.startswith("Send and run"):
                self.run_button = b

        self.find_bar = tk.Frame(w, bg=PANEL_BG)
        th.label(self.find_bar, "Find", fg=th.DIM, bg=PANEL_BG).pack(side="left", padx=(8, 4))
        self.find_var = tk.StringVar(master=w)
        self.find_entry = tk.Entry(self.find_bar, textvariable=self.find_var, width=30, bg=th.PANEL2,
                                   fg=th.FG, insertbackground=th.FG, relief="flat")
        self.find_entry.pack(side="left", pady=4, ipady=2)
        self.find_entry.bind("<Return>", lambda e: self.find_next())
        self.find_entry.bind("<Shift-Return>", lambda e: self.find_next(back=True))
        self.find_entry.bind("<Escape>", lambda e: self.hide_find())
        self.find_var.trace_add("write", lambda *a: self.mark_finds())
        th.button(self.find_bar, "Next", self.find_next).pack(side="left", padx=4)
        th.button(self.find_bar, "Previous", lambda: self.find_next(back=True)).pack(side="left")
        th.button(self.find_bar, "Close", self.hide_find).pack(side="left", padx=4)
        self.find_count = th.label(self.find_bar, "", fg=th.DIM, bg=PANEL_BG)
        self.find_count.pack(side="left", padx=6)

        self.status_var = tk.StringVar(master=w, value="")
        status = tk.Frame(w, bg=PANEL_BG)
        status.pack(side="bottom", fill="x")
        self.pos_var = tk.StringVar(master=w, value="")
        tk.Label(status, textvariable=self.pos_var, bg=PANEL_BG, fg=th.DIM, padx=8).pack(side="right")
        self.count_label = tk.Label(status, text="", bg=PANEL_BG, fg=th.DIM, padx=8, cursor="hand2")
        self.count_label.pack(side="right")
        self.count_label.bind("<Button-1>", lambda e: self.next_problem())
        self.status_label = tk.Label(status, textvariable=self.status_var, bg=PANEL_BG, fg=th.FG,
                                     anchor="w", padx=8, pady=4)
        self.status_label.pack(side="left", fill="x", expand=True)
        self.copy_problems_button = th.button(status, "Copy problems for the AI", self.copy_problems)
        self.copy_file_button = th.button(status, "Copy file", self.copy_built_file)
        self.open_folder_button = th.button(status, "Open folder", self.open_built_folder)
        self.built = None  # The last build's file

        pane = tk.PanedWindow(w, orient="vertical", bg=th.LINE, sashwidth=4, bd=0)
        pane.pack(side="top", fill="both", expand=True)
        self.find_anchor = pane
        upper = tk.Frame(pane, bg=th.BG)
        lower = tk.Frame(pane, bg=th.BG)
        pane.add(upper, stretch="always", minsize=160)
        pane.add(lower, minsize=80, height=150)

        self.sig = tk.Text(upper, height=1, bg=PANEL_BG, fg=th.DIM, relief="flat", bd=0, padx=8, pady=4,
                           font=(th.MONO, 10), wrap="none", cursor="arrow", highlightthickness=0)
        self.sig.tag_configure("cur", foreground="#ffffff", font=(th.MONO, 10, "bold"))
        self.sig.tag_configure("name", foreground=COLOURS["builtin"])
        self.sig.pack(side="bottom", fill="x")
        self.sig.configure(state="disabled")

        body = tk.Frame(upper, bg=EDITOR_BG)
        body.pack(side="top", fill="both", expand=True)
        self.gutter = tk.Canvas(body, width=56, bg=EDITOR_BG, highlightthickness=0, bd=0)
        self.gutter.pack(side="left", fill="y")
        sb = ttk.Scrollbar(body, orient="vertical", style="Calc.Vertical.TScrollbar")
        sb.pack(side="right", fill="y")
        self.text = tk.Text(body, bg=EDITOR_BG, fg=EDITOR_FG, insertbackground="#AEAFAD", undo=True,
                            autoseparators=True, maxundo=-1, wrap="none", relief="flat", bd=0,
                            font=(th.MONO, 11), padx=8, pady=4, selectbackground="#264F78",
                            inactiveselectbackground="#3A3D41", highlightthickness=0, tabs=("4c",))
        self.text.pack(side="left", fill="both", expand=True)

        def yscroll(a, b):
            sb.set(a, b)
            self.draw_gutter()
        self.text.configure(yscrollcommand=yscroll)
        sb.configure(command=self.text.yview)
        self.text.tag_configure("curline", background=CURRENT_LINE)
        for tag, colour in COLOURS.items():
            self.text.tag_configure(tag, foreground=colour)
        self.text.tag_configure("comment", foreground=COLOURS["comment"], font=(th.MONO, 11, "italic"))
        for sev, colour in SEV_COLOUR.items():
            self.text.tag_configure("p_" + sev, underline=True, underlinefg=colour)
        self.text.tag_configure("bracket", background=BRACKET_BG, borderwidth=1, relief="solid")
        self.text.tag_configure("find", background="#613214")
        self.text.tag_configure("jump", background="#264F78")
        self.text.tag_lower("curline")
        self.text.tag_raise("sel")

        cols = ("sev", "where", "message")
        self.tree = ttk.Treeview(lower, columns=cols, show="headings", style="Editor.Treeview", height=5)
        self.tree.heading("sev", text="")
        self.tree.heading("where", text="Line:col")
        self.tree.heading("message", text="Problem and fix")
        self.tree.column("sev", width=96, stretch=False)
        self.tree.column("where", width=72, anchor="e", stretch=False)
        self.tree.column("message", width=800)
        for sev, colour in SEV_COLOUR.items():
            self.tree.tag_configure(sev, foreground=colour)
        tsb = ttk.Scrollbar(lower, orient="vertical", command=self.tree.yview, style="Calc.Vertical.TScrollbar")
        self.tree.configure(yscrollcommand=tsb.set)
        tsb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.jump_to_selected())

        t = self.text
        t.bind("<<Modified>>", self._modified)
        t.bind("<KeyRelease>", self._key_release)
        t.bind("<ButtonRelease-1>", lambda e: (self.hide_popup(), self.update_signature(), self.update_pos()))
        t.bind("<Key>", self._key)
        t.bind("<Return>", self._return)
        t.bind("<Tab>", self._tab)
        t.bind("<BackSpace>", self._backspace)
        t.bind("<Escape>", lambda e: (self.hide_popup(), self.hide_find(), "break")[-1])
        t.bind("<Control-space>", lambda e: (self.show_completions(force=True), "break")[-1])
        t.bind("<Control-slash>", lambda e: (self.toggle_comment(), "break")[-1])
        # A word at a time, like VS Code: Ctrl+Backspace before the cursor, Ctrl+Delete after it
        t.bind("<Control-BackSpace>", lambda e: (self.delete_word(-1), "break")[-1])
        t.bind("<Control-Delete>", lambda e: (self.delete_word(1), "break")[-1])
        t.bind("<<Paste>>", self._paste)
        t.bind("<Motion>", self._motion)
        t.bind("<Leave>", lambda e: self.hide_hover())
        t.bind("<Configure>", lambda e: self.draw_gutter())
        t.bind("<FocusOut>", lambda e: self.win.after(150, self._focus_check))
        t.bind("<Control-y>", lambda e: (self.redo(), "break")[-1])
        t.bind("<Control-Shift-Z>", lambda e: (self.redo(), "break")[-1])
        t.bind("<Control-z>", lambda e: (self.undo(), "break")[-1])
        for seq, fn in (("<F5>", lambda e: self.send(run=True)), ("<F6>", lambda e: self.send(run=False)),
                        ("<Control-s>", lambda e: self.save()), ("<Control-S>", lambda e: self.save_as()),
                        ("<Control-o>", lambda e: self.open_dialog()), ("<Control-n>", lambda e: self.new()), ("<Control-w>", lambda e: self.close()),
                        ("<Control-f>", lambda e: self.show_find()), ("<F7>", lambda e: self.check_now()),
                        ("<F3>", lambda e: self.find_next()), ("<Control-b>", lambda e: self.build()),
                        ("<F8>", lambda e: self.next_problem()),
                        ("<Shift-F8>", lambda e: self.next_problem(back=True))):
            if self.host is None:
                w.bind(seq, lambda e, fn=fn: (fn(e), "break")[-1])
            else:
                w.bind_class(self._key_tag, seq, lambda e, fn=fn: (fn(e), "break")[-1])

    def _menu_items(self):
        self.lang_var = tk.StringVar(master=self.win, value="ti84")
        new_items = [("TI-84 Plus CE TI-Basic", lambda: self.new("ti84")),
                     ("TI-89 Titanium TI-Basic", lambda: self.new("ti89")),
                     ("TI-Nspire Python", lambda: self.new("python"))]
        return [
            ("File", [("cascade", "New", new_items),
                      ("Open...", self.open_dialog, "Ctrl+O"),
                      ("Open from calculator...", self.open_from_calc),
                      None,
                      ("Save", self.save, "Ctrl+S"),
                      ("Save as...", self.save_as, "Ctrl+Shift+S"),
                      None,
                      ("Close", self.close)]),
            ("Edit", [("Undo", self.undo, "Ctrl+Z"), ("Redo", self.redo, "Ctrl+Y"), None,
                      ("Cut", lambda: self.text.event_generate("<<Cut>>"), "Ctrl+X"),
                      ("Copy", lambda: self.text.event_generate("<<Copy>>"), "Ctrl+C"),
                      ("Paste", lambda: self.text.event_generate("<<Paste>>"), "Ctrl+V"),
                      ("Select all", lambda: self.text.tag_add("sel", "1.0", "end-1c"), "Ctrl+A"), None,
                      ("Find...", self.show_find, "Ctrl+F"),
                      ("Comment / uncomment", self.toggle_comment, "Ctrl+/"),
                      ("Complete the word", lambda: self.show_completions(force=True), "Ctrl+Space")]),
            ("Run", [("Check now", self.check_now, "F7"),
                     ("Next problem", self.next_problem, "F8"),
                     ("Previous problem", lambda: self.next_problem(back=True), "Shift+F8"), None,
                     ("Build (make the calculator file)", self.build, "Ctrl+B"),
                     ("Send and run", lambda: self.send(run=True), "F5"),
                     ("Send only", lambda: self.send(run=False), "F6"), None,
                     ("Open the builds folder", self.open_built_folder),
                     ("Copy the built file", self.copy_built_file)]),
            ("Language", [("radio", cc.TITLES[l], self.lang_var, l, lambda: self.set_language(self.lang_var.get()))
                          for l in cc.LANGS]),
            ("Help", [("Copy AI instructions", self.copy_ai_instructions),
                      ("Copy problems for the AI", self.copy_problems), None,
                      ("Keys", self.show_keys)]),
        ]

    def open_solver_builder(self):
        """Equations once -> a solver for each calculator (tools/solver_ui.py)"""
        import solver_ui
        return solver_ui.open_builder(self)

    # ---- Targets ----
    def _targets(self):
        out = []
        for m in self.mirrors:
            calc = m.calc
            lang = LANG_OF_SLUG.get(calc.slug)
            if lang is None:
                continue
            on = m.connected() if hasattr(m, "connected") else True
            name = (getattr(m, "info", {}) or {}).get("name", "").replace("_", " ")
            label = "%s%s%s" % (calc.title, " (%s)" % name if name and name != calc.title else "",
                                "" if on else " - not connected")
            out.append((label, m, lang))
        out.append(("No calculator: save only", None, None))
        return out

    def _fill_targets(self):
        self.target_box.configure(values=[t[0] for t in self.targets])

    def set_target(self, which):
        """which: an index into the targets, a Mirror, a slug or None"""
        k = len(self.targets) - 1
        if isinstance(which, int) and 0 <= which < len(self.targets):
            k = which
        elif which is not None:
            for i, (_l, m, lang) in enumerate(self.targets):
                if m is which or (isinstance(which, str) and m is not None and m.calc.slug == which):
                    k = i
                    break
            else:
                if isinstance(which, str) and which in ("ti84", "ti89", "nspire", "python"):
                    self.set_language(LANG_OF_SLUG.get(which, which))
        self.target_index = k
        self.target_box.current(k)
        _l, m, lang = self.targets[k]
        if lang and lang != self.lang:
            self.set_language(lang)
        self.update_run_label()

    def target(self):
        return self.targets[self.target_index][1]

    def set_language(self, lang):
        lang = cc.lang_of(lang)
        self.lang = lang
        self.lang_var.set(lang)
        self.lang_label.configure(text=SHORT[lang])
        m = self.target()
        if m is not None and LANG_OF_SLUG.get(m.calc.slug) != lang:
            self.target_index = len(self.targets) - 1  # Another language: no calculator
            self.target_box.current(self.target_index)
        self.update_run_label()
        self.refresh_all()

    def update_run_label(self):
        try:
            self.run_button.configure(text="Send (F5)" if self.lang == "python" else "Send and run (F5)")
        except (AttributeError, tk.TclError):
            pass

    # ---- Text helpers ----
    def get_text(self):
        return self.text.get("1.0", "end-1c")

    def set_text(self, text, modified=False):
        self.text.delete("1.0", "end")
        self.text.insert("1.0", text)
        self.text.edit_reset()
        self.text.edit_modified(modified)
        self.text.mark_set("insert", "1.0")
        self.refresh_all()

    def offset(self, index="insert"):
        n = self.text.count("1.0", index, "chars")
        return n[0] if n else 0

    def index_of(self, line, col):
        return "%d.%d" % (line, col)

    def set_status(self, text, colour=None):
        self.status_var.set(text)
        self.status_label.configure(fg=colour or th.FG)

    def program_name(self):
        n = self.name_var.get().strip()
        if self.lang == "ti84":
            return n.upper() or None
        if self.lang == "ti89":
            return cc.program_name("ti89", self.get_text()) or (n.lower() or None)
        return n.lower() or None

    def _sync_name(self):
        if self.lang == "ti89":
            n = cc.program_name("ti89", self.get_text(), self.path)
            if n and n != self.name_var.get():
                self.name_var.set(n)

    def update_title(self):
        base = os.path.basename(self.path) if self.path else "untitled%s" % cc.EXTS[self.lang]
        star = "• " if self.unsaved() else ""
        if self.host is not None:
            self.host.editor_title("%s%s" % (star, base))
            return
        self.win.title("%s%s - Program editor (%s)" % (star, base, SHORT[self.lang]))

    # ---- Events ----
    def _modified(self, _e=None):
        if self.text.edit_modified():
            self.update_title()
        self.schedule_check()

    def schedule_check(self):
        if self._check_job is not None:
            self.win.after_cancel(self._check_job)
        self._check_job = self.win.after(DEBOUNCE_MS, self.refresh_all)

    def _key(self, e):
        if self._popup is not None:
            if e.keysym in ("Down", "Up"):
                lb = self._popup_list
                cur = (lb.curselection() or (0,))[0]
                nxt = max(0, min(lb.size() - 1, cur + (1 if e.keysym == "Down" else -1)))
                lb.selection_clear(0, "end")
                lb.selection_set(nxt)
                lb.see(nxt)
                return "break"
            if e.keysym in ("Prior", "Next", "Home", "End"):
                self.hide_popup()
        return None

    def _key_release(self, e):
        self.update_pos()
        if e.keysym in ("Up", "Down") and self._popup is not None:
            return
        if e.keysym in ("Escape", "Return", "Tab", "Left", "Right", "Up", "Down", "Home", "End",
                        "Control_L", "Control_R", "Shift_L", "Shift_R", "Prior", "Next"):
            if e.keysym not in ("Shift_L", "Shift_R", "Control_L", "Control_R"):
                self.update_signature()
            return
        if e.state & 0x4:  # Ctrl shortcuts
            return
        self.highlight_line()
        if e.char and (e.char.isalnum() or e.char in "_.(|@") or e.keysym == "BackSpace":
            self.show_completions()
        else:
            self.hide_popup()
        self.update_signature()

    def _return(self, e):
        if self._popup is not None:
            self.accept_completion()
            return "break"
        line = self.text.get("insert linestart", "insert")
        indent = re.match(r"[ ]*", line).group(0)
        if self.lang == "python":
            if line.rstrip().endswith(":"):
                indent += "    "
            self.text.insert("insert", "\n" + indent)
            self.text.see("insert")
            return "break"
        self.text.insert("insert", "\n")  # TI-Basic: the editor shows the indent itself
        self.text.see("insert")
        return "break"

    def _tab(self, e):
        if self._popup is not None:
            self.accept_completion()
            return "break"
        if self.lang == "python":
            col = int(self.text.index("insert").split(".")[1])
            self.text.insert("insert", " " * (4 - col % 4))
        else:
            self.set_status("TI-Basic has no tabs: the editor shows blocks indented for you (the file stays clean)")
        return "break"

    def _backspace(self, e):
        if self.lang != "python" or self.text.tag_ranges("sel"):
            return None
        before = self.text.get("insert linestart", "insert")
        if before and not before.strip() and len(before) >= 4:
            n = len(before) % 4 or 4
            self.text.delete("insert -%dc" % n, "insert")
            return "break"
        return None

    def _paste(self, e):
        empty = not self.get_text().strip()
        try:
            clip = self.win.clipboard_get()
        except tk.TclError:
            return None
        if not empty:
            return None
        text = strip_fences(clip).replace("\r\n", "\n").replace("\t", "    ")
        self.paste_into_empty(text)
        return "break"

    def paste_into_empty(self, text):
        """A whole program pasted (from a chat AI) into an empty editor: checked at once; when
        something is wrong, the problems can go back to the AI with one button"""
        lang = detect_language(text) if self.target() is None else self.lang
        if lang != self.lang:
            self.set_language(lang)
        self.text.insert("1.0", text)
        self.text.edit_modified(True)
        self.refresh_all()
        c = cc.counts(self.problems)
        if c["error"] or c["warning"]:
            self.set_status("Pasted %d lines: %d error(s), %d warning(s). Copy them for the AI to fix?" % (
                text.count("\n") + 1, c["error"], c["warning"]), SEV_COLOUR["error" if c["error"] else "warning"])
            self.copy_problems_button.pack(side="right", padx=6, pady=2)
        else:
            self.set_status("Pasted %d lines: no problems found" % (text.count("\n") + 1), th.MINT)

    def _focus_check(self):
        if self._popup is not None:
            try:
                f = self.win.focus_get()
            except (tk.TclError, KeyError):
                f = None
            if f is not self.text and f is not getattr(self, "_popup_list", None):
                self.hide_popup()

    # ---- Checking, colours, markers ----
    def refresh_all(self):
        self._check_job = None
        if self._closed:
            return
        self._sync_name()
        text = self.get_text()
        t0 = time.perf_counter()
        self.highlight(text)
        self.apply_indent(text)
        self.run_check(text)
        self.check_ms = (time.perf_counter() - t0) * 1000
        self.update_signature()
        self.update_title()
        self.update_pos()

    def run_check(self, text=None):
        text = self.get_text() if text is None else text
        name = self.program_name() if self.lang in ("ti84", "python") else None
        self.problems = cc.check(self.lang, text, name=name)
        t = self.text
        for sev in SEV_COLOUR:
            t.tag_remove("p_" + sev, "1.0", "end")
        for p in self.problems:  # Exactly the span the checker names
            t.tag_add("p_" + p["severity"], self.index_of(p["line"], p["col"]), self.index_of(p["line"], p["end_col"]))
        self.tree.delete(*self.tree.get_children())
        for k, p in enumerate(self.problems):
            msg = p["message"] + ("   Fix: " + p["fix"] if p["fix"] else "")
            self.tree.insert("", "end", iid=str(k), tags=(p["severity"],),
                             values=(SEV_ICON[p["severity"]], "%d:%d" % (p["line"], p["col"] + 1), msg))
        self.draw_gutter()
        c = cc.counts(self.problems)
        self.count_label.configure(text=self.count_text(c), fg=SEV_COLOUR["error"] if c["error"] else
                                   SEV_COLOUR["warning"] if c["warning"] else th.DIM)
        if not c["error"] and not c["warning"]:
            self.copy_problems_button.pack_forget()
        return self.problems

    @staticmethod
    def count_text(c):
        parts = ["%d error%s" % (c["error"], "" if c["error"] == 1 else "s"),
                 "%d warning%s" % (c["warning"], "" if c["warning"] == 1 else "s")]
        if c["info"]:
            parts.append("%d note%s" % (c["info"], "" if c["info"] == 1 else "s"))
        return ", ".join(parts)

    def next_problem(self, back=False):
        """F8 / Shift+F8: the next (previous) problem after the cursor, round the end"""
        if not self.problems:
            self.set_status("No problems")
            return None
        line, col = (int(x) for x in self.text.index("insert").split("."))
        here = (line, col)
        order = sorted(range(len(self.problems)), key=lambda k: (self.problems[k]["line"], self.problems[k]["col"]))
        if back:
            cand = [k for k in order if (self.problems[k]["line"], self.problems[k]["col"]) < here]
            k = cand[-1] if cand else order[-1]
        else:
            cand = [k for k in order if (self.problems[k]["line"], self.problems[k]["col"]) > here]
            k = cand[0] if cand else order[0]
        self.tree.selection_set(str(k))
        self.tree.see(str(k))
        self.jump_to_selected()
        return k

    def problems_at(self, line, col):
        return [p for p in self.problems if p["line"] == line and p["col"] <= col < p["end_col"]]

    def check_now(self):
        self.refresh_all()
        c = cc.counts(self.problems)
        if c["error"]:
            self.set_status("%d error(s), %d warning(s): see the list below" % (c["error"], c["warning"]),
                            SEV_COLOUR["error"])
        elif c["warning"]:
            self.set_status("No errors; %d warning(s)" % c["warning"], SEV_COLOUR["warning"])
        else:
            self.set_status("No problems found", th.MINT)

    def highlight(self, text=None):
        text = self.get_text() if text is None else text
        t = self.text
        for tag in COLOURS:
            t.tag_remove(tag, "1.0", "end")
        for tag, line, c, e in cc.highlight(self.lang, text):
            t.tag_add(tag, "%d.%d" % (line, c), "%d.%d" % (line, e))

    def highlight_line(self):
        """While typing: the current line coloured at once (the whole text on the pause)"""
        line_no = int(self.text.index("insert").split(".")[0])
        line = self.text.get("%d.0" % line_no, "%d.end" % line_no)
        if self.lang == "python" and ('"""' in line or "'''" in line):
            return
        for tag in COLOURS:
            self.text.tag_remove(tag, "%d.0" % line_no, "%d.end" % line_no)
        for tag, _l, c, e in cc.highlight(self.lang, line):
            self.text.tag_add(tag, "%d.%d" % (line_no, c), "%d.%d" % (line_no, e))

    def apply_indent(self, text):
        t = self.text
        for tag in t.tag_names():
            if tag.startswith("ind"):
                t.tag_remove(tag, "1.0", "end")
        if self.lang == "python":
            return
        for n, d in enumerate(cc.block_depths(self.lang, text), 1):
            if d:
                tag = "ind%d" % min(d, 12)
                t.tag_configure(tag, lmargin1=d * INDENT_PX, lmargin2=d * INDENT_PX)
                t.tag_add(tag, "%d.0" % n, "%d.0" % (n + 1))

    def draw_gutter(self):
        g = self.gutter
        g.delete("all")
        worst = {}
        for p in self.problems:
            cur = worst.get(p["line"])
            if cur is None or cc._ORDER[p["severity"]] < cc._ORDER[cur]:
                worst[p["line"]] = p["severity"]
        idx = self.text.index("@0,0")
        while True:
            d = self.text.dlineinfo(idx)
            if d is None:
                break
            y = d[1]
            n = int(idx.split(".")[0])
            g.create_text(46, y + d[3] // 2, anchor="e", text=str(n), fill="#C6C6C6" if n == self._cur_line() else GUTTER_FG, font=(th.MONO, 9))
            sev = worst.get(n)
            if sev:
                cy = y + d[3] // 2
                g.create_oval(4, cy - 4, 12, cy + 4, fill=SEV_COLOUR[sev], outline="", tags=("mark", "m%d" % n))
            nxt = self.text.index("%s+1line" % idx)
            if nxt == idx:
                break
            idx = nxt
        g.tag_bind("mark", "<Button-1>", self._gutter_click)

    def _gutter_click(self, e):
        for tag in self.gutter.gettags("current"):
            if tag.startswith("m") and tag[1:].isdigit():
                n = int(tag[1:])
                for k, p in enumerate(self.problems):
                    if p["line"] == n:
                        self.tree.selection_set(str(k))
                        self.tree.see(str(k))
                        break

    def jump_to_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        p = self.problems[int(sel[0])]
        self.jump(p["line"], p["col"], p["end_col"])
        self.set_status("Line %d: %s%s" % (p["line"], p["message"], ("  Fix: " + p["fix"]) if p["fix"] else ""),
                        SEV_COLOUR[p["severity"]])

    def jump(self, line, col, end_col=None):
        t = self.text
        t.tag_remove("jump", "1.0", "end")
        t.mark_set("insert", self.index_of(line, col))
        if end_col:
            t.tag_add("jump", self.index_of(line, col), self.index_of(line, end_col))
            self.win.after(1200, lambda: t.tag_remove("jump", "1.0", "end"))
        t.see("insert")
        t.focus_set()
        self.update_pos()

    def update_pos(self):
        """The position in the status bar, the current line's highlight, the matching bracket"""
        t = self.text
        line, col = t.index("insert").split(".")
        self.pos_var.set("Ln %s, Col %d" % (line, int(col) + 1))
        t.tag_remove("curline", "1.0", "end")
        t.tag_add("curline", "insert linestart", "insert lineend +1c")
        t.tag_remove("bracket", "1.0", "end")
        text = self.get_text()
        m = cc.bracket_match(text, self.offset("insert"))
        self.bracket = m
        if m:
            for k in m:
                t.tag_add("bracket", "1.0 +%dc" % k, "1.0 +%dc" % (k + 1))

    # ---- Autocomplete ----
    def show_completions(self, force=False):
        text = self.get_text()
        off = self.offset("insert")
        word = cc.word_before(self.lang, text, off)
        if not force and len(word) < 2:
            self.hide_popup()
            return []
        items = cc.completions(self.lang, text, off)
        self._popup_items = items
        self._popup_word = word.rpartition(".")[2] if self.lang == "python" else word
        if not items:
            self.hide_popup()
            return []
        if self._popup is None:
            p = self._popup = tk.Toplevel(self.win)
            p.overrideredirect(True)
            p.configure(bg=th.LINE)
            self._popup_list = lb = tk.Listbox(p, bg=PANEL_BG, fg=EDITOR_FG, selectbackground="#04395E",
                                               selectforeground="#ffffff", relief="flat", bd=0,
                                               highlightthickness=0, font=(th.MONO, 10), activestyle="none",
                                               width=46, height=8)
            lb.pack(padx=1, pady=1)
            lb.bind("<Double-Button-1>", lambda e: self.accept_completion())
            lb.bind("<Return>", lambda e: self.accept_completion())
            lb.bind("<Escape>", lambda e: self.hide_popup())
        lb = self._popup_list
        lb.delete(0, "end")
        for it in items:
            detail = it["detail"]
            lb.insert("end", "%-16s %s" % (it["label"], detail[:40] if detail else it["kind"]))
        lb.configure(height=min(8, len(items)))
        lb.selection_set(0)
        bbox = self.text.bbox("insert")
        if bbox:
            x = self.text.winfo_rootx() + bbox[0]
            y = self.text.winfo_rooty() + bbox[1] + bbox[3] + 2
            self._popup.geometry("+%d+%d" % (x, y))
        self._popup.lift()
        return items

    def accept_completion(self, k=None):
        if self._popup is None and k is None:
            return
        items = self._popup_items
        if k is None:
            sel = self._popup_list.curselection()
            k = sel[0] if sel else 0
        if not items:
            self.hide_popup()
            return
        it = items[k]
        word = self._popup_word
        t = self.text
        t.edit_separator()
        if word:
            t.delete("insert -%dc" % len(word), "insert")
        t.insert("insert", it["insert"])
        t.edit_separator()
        self.hide_popup()
        self.highlight_line()
        self.update_signature()
        self.schedule_check()

    def hide_popup(self):
        if self._popup is not None:
            self._popup.destroy()
            self._popup = None

    # ---- Signature hints and hover ----
    def update_signature(self):
        sig = cc.signature_at(self.lang, self.get_text(), self.offset("insert"))
        self.current_signature = sig
        s = self.sig
        s.configure(state="normal")
        s.delete("1.0", "end")
        if sig:
            syn = sig["syntax"]
            span = sig.get("span")
            if span:
                s.insert("end", syn[:span[0]])
                s.insert("end", syn[span[0]:span[1]], "cur")
                s.insert("end", syn[span[1]:])
            else:
                s.insert("end", syn)
            if sig.get("summary"):
                s.insert("end", "    " + sig["summary"])
        s.configure(state="disabled")

    def _motion(self, e):
        if self._hover_job is not None:
            self.win.after_cancel(self._hover_job)
        self.hide_hover()
        self._hover_job = self.win.after(600, lambda: self.show_hover(e.x, e.y))

    def show_hover(self, x, y):
        self._hover_job = None
        idx = self.text.index("@%d,%d" % (x, y))
        bbox = self.text.bbox(idx)
        if not bbox or not (bbox[0] <= x <= bbox[0] + bbox[2] + 2):
            return
        line, col = (int(v) for v in idx.split("."))
        here = self.problems_at(line, col)
        info = cc.hover_at(self.lang, self.get_text(), self.offset(idx))
        if not info and not here:
            return
        self.hide_hover()
        h = self._hover_win = tk.Toplevel(self.win)
        h.overrideredirect(True)
        h.configure(bg="#454545")
        f = tk.Frame(h, bg=PANEL_BG, padx=8, pady=6)
        f.pack(padx=1, pady=1)
        for p in here:  # The problem under the mouse first, as a compiler shows it
            tk.Label(f, text="%s  %s" % (SEV_ICON[p["severity"]].split()[0], p["message"]), bg=PANEL_BG,
                     fg=SEV_COLOUR[p["severity"]], wraplength=460, justify="left").pack(anchor="w")
            if p["fix"]:
                tk.Label(f, text="Fix: " + p["fix"], bg=PANEL_BG, fg=EDITOR_FG, wraplength=460,
                         justify="left").pack(anchor="w", pady=(0, 4))
        if info:
            tk.Label(f, text=info["syntax"], bg=PANEL_BG, fg=COLOURS["builtin"], font=(th.MONO, 10),
                     justify="left").pack(anchor="w")
            if info.get("summary"):
                tk.Label(f, text=info["summary"], bg=PANEL_BG, fg=EDITOR_FG, wraplength=460,
                         justify="left").pack(anchor="w", pady=(4, 0))
        self.hover_problems = here
        h.geometry("+%d+%d" % (self.text.winfo_rootx() + x + 12, self.text.winfo_rooty() + y + 18))

    def hide_hover(self):
        if self._hover_win is not None:
            self._hover_win.destroy()
            self._hover_win = None

    # ---- Find ----
    def show_find(self):
        sel = self.text.tag_ranges("sel")
        if sel:
            self.find_var.set(self.text.get(sel[0], sel[1]).split("\n")[0])
        self.find_bar.pack(side="top", fill="x", before=self.find_anchor)
        self.find_entry.focus_set()
        self.find_entry.select_range(0, "end")
        self.mark_finds()

    def hide_find(self):
        self.find_bar.pack_forget()
        self.text.tag_remove("find", "1.0", "end")
        self.text.focus_set()

    def mark_finds(self):
        t = self.text
        t.tag_remove("find", "1.0", "end")
        q = self.find_var.get()
        n = 0
        if q:
            idx = "1.0"
            while True:
                idx = t.search(q, idx, "end", nocase=True)
                if not idx:
                    break
                end = "%s+%dc" % (idx, len(q))
                t.tag_add("find", idx, end)
                idx = end
                n += 1
        self.find_count.configure(text="%d found" % n if q else "")
        return n

    def find_next(self, back=False):
        q = self.find_var.get()
        if not q:
            self.show_find()
            return None
        t = self.text
        if back:
            idx = t.search(q, "insert -1c", "1.0", nocase=True, backwards=True) or \
                t.search(q, "end", "1.0", nocase=True, backwards=True)
        else:
            idx = t.search(q, "insert +1c", "end", nocase=True) or t.search(q, "1.0", "end", nocase=True)
        if idx:
            t.mark_set("insert", idx)
            t.tag_remove("sel", "1.0", "end")
            t.tag_add("sel", idx, "%s+%dc" % (idx, len(q)))
            t.see(idx)
        return idx

    # ---- Editing commands ----
    def undo(self):
        try:
            self.text.edit_undo()
        except tk.TclError:
            pass
        self.schedule_check()

    def redo(self):
        try:
            self.text.edit_redo()
        except tk.TclError:
            pass
        self.schedule_check()

    def delete_word(self, direction):
        """Ctrl+Backspace (direction -1) / Ctrl+Delete (+1): a selection goes as a whole;
        otherwise the spaces next to the cursor, then one word (letters, digits, _) or one run
        of symbols; at a line's start or end, just the line break. One undo step."""
        t = self.text
        if t.tag_ranges("sel"):
            t.edit_separator()
            t.delete("sel.first", "sel.last")
            t.edit_separator()
            return
        line = t.get("insert linestart", "insert lineend")
        col = int(t.index("insert").split(".")[1])

        def is_word(ch):
            return ch.isalnum() or ch == "_"
        if direction < 0:
            if col == 0:
                start, end = "insert -1c", "insert"  # The line break before
            else:
                i = col
                while i > 0 and line[i - 1] in " \t":
                    i -= 1
                if i > 0:
                    kind = is_word(line[i - 1])
                    while i > 0 and line[i - 1] not in " \t" and is_word(line[i - 1]) == kind:
                        i -= 1
                start, end = "insert linestart +%dc" % i, "insert"
        else:
            if col >= len(line):
                start, end = "insert", "insert +1c"  # The line break after
            else:
                i = col
                while i < len(line) and line[i] in " \t":
                    i += 1
                if i < len(line):
                    kind = is_word(line[i])
                    while i < len(line) and line[i] not in " \t" and is_word(line[i]) == kind:
                        i += 1
                start, end = "insert", "insert linestart +%dc" % i
        if t.compare(start, "<", end):
            t.edit_separator()
            t.delete(start, end)
            t.edit_separator()

    def toggle_comment(self):
        mark = cc.COMMENT[self.lang]
        if not mark:
            self.set_status("The TI-84 has no comments: a string on its own line works as one "
                            "(it changes Ans)", SEV_COLOUR["info"])
            return
        t = self.text
        sel = t.tag_ranges("sel")
        a = int(t.index(sel[0] if sel else "insert").split(".")[0])
        b = int(t.index(sel[1] if sel else "insert").split(".")[0])
        if sel and t.index(sel[1]).endswith(".0") and b > a:
            b -= 1
        lines = [t.get("%d.0" % n, "%d.end" % n) for n in range(a, b + 1)]
        prefix = mark + " " if mark == "#" else mark
        all_commented = all(l.lstrip().startswith(mark) for l in lines if l.strip())
        t.edit_separator()
        for n, l in zip(range(a, b + 1), lines):
            if not l.strip():
                continue
            ind = len(l) - len(l.lstrip())
            if all_commented:
                cut = len(prefix) if l[ind:].startswith(prefix) else len(mark)
                t.delete("%d.%d" % (n, ind), "%d.%d" % (n, ind + cut))
            else:
                t.insert("%d.%d" % (n, ind), prefix)
        t.edit_separator()
        self.schedule_check()

    def show_keys(self):
        messagebox.showinfo("Program editor keys", (
            "F5  check, send and run (the Nspire: send)\nF6  check and send\nF7  check now\n"
            "Ctrl+Space  complete the word (Tab or Enter takes it, Esc closes)\nCtrl+/  comment / uncomment\n"
            "Ctrl+F  find (Enter next, Shift+Enter previous)\nCtrl+Z / Ctrl+Y  undo / redo\n"
            "Ctrl+S  save, Ctrl+Shift+S  save as, Ctrl+O  open"), parent=self.win)

    def copy_ai_instructions(self):
        text = cc.ai_instructions(self.lang)
        self.win.clipboard_clear()
        self.win.clipboard_append(text)
        self.set_status("Copied instructions for a chat AI (%s): paste them before your request" % SHORT[self.lang],
                        th.MINT)
        return text

    def copy_problems(self):
        text = cc.problems_text([p for p in self.problems if p["severity"] != "info"] or self.problems,
                                self.lang, self.program_name())
        self.win.clipboard_clear()
        self.win.clipboard_append(text)
        self.set_status("Copied %d problem(s): paste them into the chat and ask it to fix them" % len(self.problems),
                        th.MINT)
        return text

    # ---- Files ----
    def display_name(self):
        return os.path.basename(self.path) if self.path else (self.program_name() or "untitled") + cc.EXTS[self.lang]

    def unsaved(self):
        """True when closing would lose something: changed since opened or saved"""
        if self._closed or not self.text.edit_modified():
            return False
        return bool(self.get_text().strip()) or bool(self.path)

    def confirm_discard(self):
        """Before the text goes (close, New, Open, quitting the app): Save / Don't save /
        Cancel. True when it's fine to go on."""
        if not self.unsaved():
            return True
        if self.host is not None:
            self.host.show_tab("editor")
        else:
            self.win.deiconify()
            self.win.lift()
        ans = ask_save(self.win, self.display_name())
        if ans == "save":
            return self.save()
        return ans == "discard"

    def new(self, lang=None, ask=True):
        if ask and not self.confirm_discard():
            return
        if lang:
            self.set_language(lang)
        self.path = None
        self.name_var.set({"ti84": "NEW", "ti89": "newprog", "python": "newprog"}[self.lang])
        self.set_text(cc.TEMPLATES[self.lang])
        self.set_status("A new %s program" % SHORT[self.lang])

    def open_dialog(self):
        if not self.confirm_discard():
            return
        os.makedirs(PROGRAMS, exist_ok=True)
        path = filedialog.askopenfilename(parent=self.win, title="Open a program", initialdir=PROGRAMS,
                                          filetypes=[("Programs", "*.txt *.tib *.bas *.8xp *.89p *.89f *.py"),
                                                     ("All files", "*.*")])
        if path:
            self.open_path(path)

    def open_path(self, path):
        """A text file, a .8xp (detokenized) or a .89p/.89f (as the 89 keeps it). Returns True
        when it opened."""
        ext = os.path.splitext(path)[1].lower()
        try:
            with open(path, "rb") as f:
                raw = f.read()
        except OSError as e:
            self.set_status("Couldn't open %s: %s" % (os.path.basename(path), e), SEV_COLOUR["error"])
            return False
        if ext == ".tns":
            self.set_status("A .tns can't be opened here: open the .py it was made from", SEV_COLOUR["warning"])
            return False
        if raw[:8] == b"**TI83F*":
            try:
                entries = cf.read_ti8x(raw)
            except ValueError as e:
                self.set_status("Couldn't read %s: %s" % (os.path.basename(path), e), SEV_COLOUR["error"])
                return False
            vtype, name, _v, _a, data = entries[0]
            if vtype not in cf.TEXT_TYPES_84:
                self.set_status("%s isn't a program" % os.path.basename(path), SEV_COLOUR["error"])
                return False
            if cf.is_compiled_84(data):
                self.set_status("%s is a compiled (assembly or C) program: it has no TI-Basic text"
                                % os.path.basename(path), SEV_COLOUR["error"])
                return False
            self._load(cf.detokenize_84(data), "ti84", None, cf.detokenize_name_84(name, vtype),
                       "%s (from %s: Save makes a .txt)" % (os.path.basename(path), ext))
            return True
        if raw[:8] in (b"**TI89**", b"**TI92P*"):
            try:
                entries = cf.read_ti89(raw)
            except ValueError as e:
                self.set_status("Couldn't read %s: %s" % (os.path.basename(path), e), SEV_COLOUR["error"])
                return False
            _folder, name, vtype, _a, data = entries[0]
            text = cf.program_89_text(data) if vtype in (0x12, 0x13) else cf.ti89_text(vtype, data)
            if text is None:
                self.set_status("%s has run on a calculator, so the 89 keeps it compiled: its text can't be "
                                "read here (open it in the 89's Program Editor)" % os.path.basename(path),
                                SEV_COLOUR["error"])
                return False
            name = name.decode("latin-1")
            if vtype in (0x12, 0x13) and text.startswith("("):
                text = name + text
            self._load(text, "ti89", None, name, "%s (from %s: Save makes a .txt)" % (os.path.basename(path), ext))
            return True
        text = None
        for enc in ("utf-8-sig", "cp1252"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            text = raw.decode("latin-1")
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        lang = detect_language(text, path)
        stem = os.path.splitext(os.path.basename(path))[0]
        name = (cf.name_84_from(stem) if lang == "ti84" else stem.lower())
        self._load(text, lang, path, name, os.path.basename(path))
        return True

    def _load(self, text, lang, path, name, what):
        m = self.target()
        if m is not None and LANG_OF_SLUG.get(m.calc.slug) != lang:
            # Another calculator's program: pick a target for it if one is connected
            k = next((i for i, (_l, mm, l2) in enumerate(self.targets) if l2 == lang), len(self.targets) - 1)
            self.target_index = k
            self.target_box.current(k)
        self.set_language(lang)
        self.path = path
        self.name_var.set(name or "")
        self.set_text(text)
        c = cc.counts(self.problems)
        self.set_status("Opened %s: %d line(s), %d error(s), %d warning(s)" % (
            what, text.count("\n") + 1, c["error"], c["warning"]))

    def save(self):
        if not self.path:
            return self.save_as()
        return self.write(self.path)

    def save_as(self):
        os.makedirs(PROGRAMS, exist_ok=True)
        ext = cc.EXTS[self.lang]
        name = self.program_name() or "program"
        path = filedialog.asksaveasfilename(
            parent=self.win, title="Save the program", initialdir=PROGRAMS, initialfile=name + ext,
            defaultextension=ext, filetypes=[("Python", "*.py")] if self.lang == "python" else
            [("TI-Basic text", "*.txt"), ("All files", "*.*")])
        if not path:
            return False
        return self.write(path)

    def write(self, path):
        """Saves the text as UTF-8 (no BOM), as it is: no indentation is added"""
        text = self.get_text()
        if not text.endswith("\n"):
            text += "\n"
        try:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
        except OSError as e:
            self.set_status("Not saved: %s" % e, SEV_COLOUR["error"])
            return False
        self.path = path
        if self.lang == "ti84" and not self.name_var.get().strip():
            self.name_var.set(cf.name_84_from(os.path.splitext(os.path.basename(path))[0]) or "")
        self.text.edit_modified(False)
        self.update_title()
        self.set_status("Saved %s" % path, th.MINT)
        return True

    def close(self, force=False):
        """Closes the window, asking first about unsaved changes (force: don't ask). True when
        it closed."""
        if not force and not self.confirm_discard():
            return False
        self._closed = True
        if self in _OPEN:
            _OPEN.remove(self)
        self.hide_popup()
        self.hide_hover()
        if self.host is not None:
            self.host.editor_closed(self)  # Takes the tab away (and its frame)
            return True
        try:
            self.win.destroy()
        except tk.TclError:
            pass
        return True

    # ---- The link: everything goes through the Mirror's queue ----
    def _pump(self):
        if self._closed:
            return
        while True:
            try:
                fn, args = self._inbox.get_nowait()
            except queue.Empty:
                break
            try:
                fn(*args)
            except Exception as e:  # Never take the window down over one answer
                self.set_status("Problem: %s" % e, SEV_COLOUR["error"])
        self.win.after(40, self._pump)

    def _later(self, fn):
        """A done(code, lines) for the link thread that runs fn on Tk's thread"""
        return lambda code, lines: self._inbox.put((fn, (code, lines)))

    def _queue(self, m, line, done=None, progress=None):
        self.last_queued.append(line)
        m.queue(line, None, self._later(done) if done else None, progress)

    def _key_line(self, m, codes):
        return "keys " + " ".join(m.calc.key_fmt % c for c in codes)

    def _cur_line(self):
        return int(self.text.index("insert").split(".")[0])

    def _usable_target(self):
        m = self.target()
        if m is None:
            self.set_status("No calculator chosen: pick one at the top, or Save (Ctrl+S)", SEV_COLOUR["warning"])
            return None
        if hasattr(m, "connected") and not m.connected():
            self.set_status("The %s isn't connected yet" % m.calc.title, SEV_COLOUR["warning"])
            return None
        return m

    # ---- Build: the calculator's own file, kept where it can be shared ----
    def build_folder(self, lang=None):
        return os.path.join(PROGRAMS, CALC_FOLDER[lang or self.lang])

    def build(self, quiet=False):
        """Ctrl+B: check; refuse on errors, ask on warnings; then make the calculator's file
        (.8xp, .89p/.89f, .tns) in CalcSuite files\\programs\\<calculator>\\ with the source
        beside it. Returns {"file", "source", "name", "lang", "wanted"} or None."""
        self.hide_popup()
        self.refresh_all()
        c = cc.counts(self.problems)
        errors = [p for p in self.problems if p["severity"] == "error"]
        if errors:
            p = errors[0]
            self.tree.selection_set(str(self.problems.index(p)))
            self.tree.see(str(self.problems.index(p)))
            self.set_status("Not built: %s. Line %d: %s (F8 goes to each)" % (
                self.count_text(c), p["line"], p["message"]), SEV_COLOUR["error"])
            return None
        if c["warning"] and not messagebox.askyesno(
                "Warnings", "%s. Build it anyway?\n\nThe first one, line %d:\n%s" % (
                    self.count_text(c), next(p for p in self.problems if p["severity"] == "warning")["line"],
                    next(p for p in self.problems if p["severity"] == "warning")["message"]),
                icon="warning", parent=self.win):
            self.set_status("Not built: fix the warnings, or build anyway", SEV_COLOUR["warning"])
            return None
        name = self.program_name()
        if not name:
            self.set_status("Give the program a name first (the Name box)", SEV_COLOUR["error"])
            self.name_entry.focus_set()
            return None
        folder = self.build_folder()
        text = self.get_text()
        if not text.endswith("\n"):
            text += "\n"
        try:
            os.makedirs(folder, exist_ok=True)
            if self.lang == "python":
                import py2tns
                src = os.path.join(folder, name + ".py")
                with open(src, "w", encoding="utf-8", newline="\n") as f:
                    f.write(text)
                out = py2tns.convert(src, os.path.join(folder, name + ".tns"), quiet=True)
                wanted = []
            else:
                import send_ti
                slug = SLUG_OF_LANG[self.lang]
                stem = name.replace("\u03b8", "theta") if slug == "ti84" else name
                src = os.path.join(folder, stem + ".txt")
                with open(src, "w", encoding="utf-8", newline="\n") as f:
                    f.write(text)
                out, wanted = send_ti.prepare(src, slug, name, folder, [])
        except Exception as e:  # OSError, ValueError, py2tns.TnsError: never take the window down
            self.set_status("Not built: %s" % e, SEV_COLOUR["error"])
            return None
        self.built = {"file": out, "source": src, "name": name, "lang": self.lang, "wanted": wanted,
                      "warnings": c["warning"]}
        self.show_build_buttons()
        if not quiet:
            self.set_status("Built %s (%s)%s" % (out, cf.human_size(os.path.getsize(out)),
                                                  "; %d warning(s)" % c["warning"] if c["warning"] else ""), th.MINT)
        return self.built

    def show_build_buttons(self):
        self.copy_file_button.pack(side="right", padx=(0, 6), pady=2)
        self.open_folder_button.pack(side="right", padx=(0, 6), pady=2)

    def open_built_folder(self):
        if self.built and os.path.isfile(self.built["file"]):
            open_folder(self.built["file"])
        else:
            os.makedirs(self.build_folder(), exist_ok=True)
            os.startfile(self.build_folder())

    def copy_built_file(self):
        if not (self.built and os.path.isfile(self.built["file"])):
            self.set_status("Nothing built yet: Build (Ctrl+B) first", SEV_COLOUR["warning"])
            return None
        how = copy_file_to_clipboard(self.win, self.built["file"])
        self.set_status(("Copied %s: paste it into Discord, an e-mail or a folder" if how == "file" else
                         "Copied the path of %s") % os.path.basename(self.built["file"]), th.MINT)
        return how

    def send(self, run=True):
        """F5 (run=True): check, build, send, run (the 84, the 89) or send (the Nspire). F6: check,
        build, send. Everything goes through the target Mirror's link thread."""
        m = self.target()
        if m is not None and LANG_OF_SLUG.get(m.calc.slug) != self.lang:
            m = None
        if m is None:
            self.set_status("No calculator chosen: pick one at the top (Build, Ctrl+B, only makes the file)",
                            SEV_COLOUR["warning"])
            return False
        if hasattr(m, "connected") and not m.connected():
            self.set_status("The %s isn't connected yet" % m.calc.title, SEV_COLOUR["warning"])
            return False
        built = self.build(quiet=True)
        if built is None:
            return False
        name, out = built["name"], built["file"]
        if self.lang == "python":
            return self._send_nspire(m, out)
        import send_ti
        slug, wanted = m.calc.slug, built["wanted"]
        warn = built["warnings"]
        args = self._run_args(self.get_text()) if slug == "ti89" else ""
        self.set_status("Built %s; checking what's on the %s..." % (out, m.calc.title))

        def listed(code, lines):
            if code:
                self.set_status("Not sent: couldn't read the calculator's list (%s)" % "; ".join(lines[-1:]),
                                SEV_COLOUR["error"])
                return
            same = send_ti.clashes(wanted, lines, slug)
            key = (slug, name.lower())
            if same and key not in self.sent_names and not messagebox.askyesno(
                    "Replace?", "%s is already on the %s. Replace it?" % (", ".join(same), m.calc.title),
                    parent=self.win):
                self.set_status("Not sent (built: %s)" % out)
                return
            self._queue(m, "send " + os.path.abspath(out), sent, progress)

        def progress(n, total):
            self._inbox.put((self.set_status, ("Sending %s: %d%%" % (os.path.basename(out), 100 * n // total if total else 0),)))

        def sent(code, lines):
            if code:
                last = [l for l in lines if l.startswith(("OK", "ERR"))]
                self.set_status("Not sent: %s" % (last[-1][4:] if last else "exit %d" % code), SEV_COLOUR["error"])
                return
            self.sent_names.add((slug, name.lower()))
            note = " (%d warning(s))" % warn if warn else ""
            if not run:
                self.set_status("Sent %s to the %s%s. %s. File: %s" % (
                    name, m.calc.title, note, send_ti.how_to_run(slug, wanted), out), th.MINT)
                return
            self.run_on_calc(m, name, args, note)
        self._queue(m, "ls", listed)
        return True

    @staticmethod
    def _run_args(text):
        first = next((l for l in text.split("\n") if l.strip()), "")
        mm = cc._HEAD.match(first.lstrip(":"))
        return mm.group(2).strip() if mm else ""

    def run_keys(self, m, name, args=""):
        """The key commands that start a program: [(line)]"""
        calc = m.calc
        if calc.slug == "ti84":
            # Quit, Clear, Clear, the prgm token, the name (pc_copy.py starts ZZDUMP the same way)
            codes = [0x40, 0x09, 0x09, 0xDA]
            for ch in name:
                c = calc.code_for("theta" if ch == "θ" else ch)
                if c is None:
                    return None
                codes.append(c)
            return [self._key_line(m, codes), self._key_line(m, [0x05])]
        # The 89: the Home screen (as pc_copy.py does), clear its entry line, name() and Enter
        typed, missing = calc.paste_keys(name + ("(" if args else "()"))
        if missing:
            return None
        # With the Apps desktop on (the OS 3 default), the link's "home" leaves the 89 on the
        # desktop, where the typed name picks apps (it opened Table on the bench, 2026-11-27):
        # the HOME key then goes to the Home screen itself (and does nothing when already there)
        clear, home = calc.code_for("clear"), calc.code_for("home")
        lines = ["home", self._key_line(m, [home, clear] + typed)]
        if not args:
            lines.append(self._key_line(m, [calc.code_for("enter")]))
        return lines

    def run_on_calc(self, m, name, args, note=""):
        lines = self.run_keys(m, name, args)
        if lines is None:
            self.set_status("Sent %s, but its name can't be typed: run it on the calculator" % name)
            return
        state = {"left": len(lines), "err": None}

        def done(k, code, out):
            state["left"] -= 1
            # The last Enter starts the program, which can keep the calculator from answering:
            # only the keys before it count
            if code and state["err"] is None and (k < len(lines) - 1 or args):
                state["err"] = ([l[4:] for l in out if l.startswith("ERR")] or ["exit %d" % code])[-1]
            if state["left"]:
                return
            if state["err"]:
                self.set_status("Sent %s%s, but typing its name failed (%s): run it on the calculator" % (
                    name, note, state["err"]), SEV_COLOUR["warning"])
            elif m.calc.slug == "ti89" and args:
                self.set_status("Sent %s%s. On the 89: type its arguments after %s( and press ENTER" % (
                    name, note, name), th.MINT)
            else:
                self.set_status("Sent and started %s%s: watch the calculator's screen" % (name, note), th.MINT)
        for k, line in enumerate(lines):
            self._queue(m, line, lambda code, out, k=k: done(k, code, out))

    def _send_nspire(self, m, tns):
        """The built .tns to My Documents through the Mirror's own Nspire send path (it asks
        before replacing); the handheld can't be told to run it, so the status says how"""
        self.last_queued.append("put %s|/%s" % (tns, os.path.basename(tns)))
        self.set_status("Sending %s to the handheld..." % os.path.basename(tns))
        base = os.path.basename(tns)

        def done(ok, msg):
            if ok:
                self.set_status("Sent %s to My Documents. On the handheld: home > My Documents > %s, then "
                                "ctrl+R runs it (close it first if it was open). File: %s" % (base, base, tns), th.MINT)
            else:
                self.set_status(msg, SEV_COLOUR["error"])
        m.send_nspire_files([(tns, "/")], lambda ok, msg: self._inbox.put((done, (ok, msg))))
        return True

    # ---- Open from calculator ----
    def open_from_calc(self):
        m = self._usable_target()
        if m is None:
            return
        slug = m.calc.slug
        if slug == "nspire":
            self.set_status("The Nspire keeps Python inside .tns documents: open the .py on the PC "
                            "(or the handheld's own editor)", SEV_COLOUR["info"])
            return
        if not self.confirm_discard():
            return
        self.set_status("Reading the %s's list..." % m.calc.title)

        def listed(code, lines):
            if code:
                self.set_status("Couldn't read the list: %s" % "; ".join(lines[-1:]), SEV_COLOUR["error"])
                return
            items = [i for i in cf.parse_dusb_ls(lines) if i["type"] in PROGRAM_TYPES[slug]]
            for i in items:
                i["text"] = cf.name_text(i["name"])
                if slug == "ti89" and i["folder"]:
                    i["text"] = cf.name_text(i["folder"]) + "\\" + i["text"]
            items.sort(key=lambda i: i["text"].lower())
            if not items:
                self.set_status("No programs on the %s" % m.calc.title)
                return
            self.pick_program(m, items)
        self._queue(m, "ls", listed)

    def pick_program(self, m, items):
        d = tk.Toplevel(self.win)
        d.title("Open from the %s" % m.calc.title)
        d.configure(bg=PANEL_BG)
        d.transient(self.win)
        d.geometry("380x420")
        tree = ttk.Treeview(d, columns=("size",), style="Calc.Treeview")
        tree.heading("#0", text="Program")
        tree.heading("size", text="Size")
        tree.column("size", width=80, anchor="e")
        for k, i in enumerate(items):
            tree.insert("", "end", iid=str(k), text=i["text"] + ("  (locked)" if i["type"] == 0x06 else ""),
                        values=(cf.human_size(i["size"]),))
        tree.pack(fill="both", expand=True, padx=8, pady=8)

        def go(_e=None):
            sel = tree.selection()
            if sel:
                d.destroy()
                self.pull_program(m, items[int(sel[0])])
        tree.bind("<Double-Button-1>", go)
        tree.bind("<Return>", go)
        th.button(d, "Open", go).pack(pady=(0, 8))
        _dark_title_bar(d)
        self.picker = (d, tree, go)

    def pull_program(self, m, item):
        slug = m.calc.slug
        raw_path = os.path.join(tempfile.gettempdir(), "calcsuite_editor_%d.bin" % os.getpid())
        line = "get %02x %s %s %d %s" % (item["type"], cf.to_hex(item["folder"]), cf.to_hex(item["name"]),
                                         item["size"], raw_path)
        self.set_status("Reading %s..." % item["text"])

        def got(code, lines):
            if code:
                self.set_status("Couldn't read %s: %s" % (item["text"], "; ".join(lines[-1:])), SEV_COLOUR["error"])
                return
            try:
                with open(raw_path, "rb") as f:
                    raw = f.read()
                os.remove(raw_path)
            except OSError as e:
                self.set_status("Couldn't read %s: %s" % (item["text"], e), SEV_COLOUR["error"])
                return
            name = cf.name_text(item["name"])
            if slug == "ti89":
                text = cf.program_89_text(raw)
                if text is None:
                    self.set_status("%s has run on the calculator, so the 89 keeps it compiled: its text can't "
                                    "be read here (open it in the 89's Program Editor)" % name, SEV_COLOUR["error"])
                    return
                text = name + text if text.startswith("(") else text
                self._load(text, "ti89", None, name, "%s from the %s" % (name, m.calc.title))
            else:
                if cf.is_compiled_84(raw):
                    self.set_status("%s is a compiled (assembly or C) program: it has no TI-Basic text" % name,
                                    SEV_COLOUR["error"])
                    return
                self._load(cf.detokenize_84(raw), "ti84", None, name, "%s from the %s" % (name, m.calc.title))
            self.text.edit_modified(True)
            self.update_title()
        self._queue(m, line, got)


def main(argv):
    """Opens the editor on its own (no calculator): python -I tools/editor.py [file]"""
    root = tk.Tk()
    root.withdraw()
    e = open_editor(root, [], None, argv[0] if argv else None)
    e.win.protocol("WM_DELETE_WINDOW", lambda: (e.close(), root.destroy() if e._closed else None))
    root.mainloop()


if __name__ == "__main__":
    main(sys.argv[1:])
