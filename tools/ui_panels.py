"""The side panel of a calculator's tab: Files, Keys, Symbols, Guide, Get programs, Info.

Each section is built the first time it's shown. Everything that talks to the calculator goes
through the tab's Mirror (its link thread); downloads and the connection doctor run in worker
threads, so the window never freezes.
"""

import os
import tempfile
import threading
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

import calc_models
import md_render
import program_library as plib
import ui_theme as th

SECTIONS = ("Files", "Keys", "Symbols", "Guide", "Get programs", "Info")
WIDTH = 450
GUIDES = {"nspire": ("docs", "PYTHON_NSPIRE_GUIDE.md"), "ti84": ("docs", "TIBASIC_84.md"),
          "ti89": ("docs", "TIBASIC_89.md")}


class SidePanel(object):
    def __init__(self, parent, app, mirror):
        self.app, self.m = app, mirror
        self.calc = mirror.calc
        self.frame = tk.Frame(parent, bg=th.PANEL, width=WIDTH)
        self.frame.pack_propagate(False)
        bar = tk.Frame(self.frame, bg=th.PANEL)
        bar.pack(fill="x", padx=10, pady=(10, 6))
        self.buttons = {}
        for k, name in enumerate(SECTIONS):
            b = tk.Label(bar, text=name, bg=th.PANEL, fg=th.DIM, font=(th.FONT, 9, "bold"),
                         padx=7, pady=4, cursor="hand2")
            b.grid(row=k // 3, column=k % 3, sticky="ew", padx=2, pady=2)
            b.bind("<Button-1>", lambda e, n=name: self.show(n))
            self.buttons[name] = b
        for c in range(3):
            bar.columnconfigure(c, weight=1)
        tk.Frame(self.frame, bg=th.LINE, height=1).pack(fill="x", padx=10)
        self.body = tk.Frame(self.frame, bg=th.PANEL)
        self.body.pack(fill="both", expand=True, padx=12, pady=10)
        self.sections = {}
        self.current = None
        self.show("Keys")

    def show(self, name):
        if self.current == name:
            return
        if self.current in self.sections:
            self.sections[self.current].frame.pack_forget()
        if name not in self.sections:
            cls = {"Files": FilesSection, "Keys": KeysSection, "Symbols": SymbolsSection,
                   "Guide": GuideSection, "Get programs": ProgramsSection,
                   "Info": InfoSection}[name]
            self.sections[name] = cls(self, self.body)
        self.sections[name].frame.pack(fill="both", expand=True)
        self.current = name
        for n, b in self.buttons.items():
            b.configure(bg=th.PANEL2 if n == name else th.PANEL, fg=th.ACCENT if n == name else th.DIM)
        if hasattr(self.sections[name], "shown"):
            self.sections[name].shown()


def heading(parent, text):
    tk.Label(parent, text=text.upper(), bg=th.PANEL, fg=th.DIM, font=(th.FONT, 8, "bold"),
             anchor="w").pack(fill="x", pady=(10, 4))


def scrolled(parent):
    """A frame inside a canvas with a scrollbar: (outer frame, inner frame)"""
    outer = tk.Frame(parent, bg=th.PANEL)
    canvas = tk.Canvas(outer, bg=th.PANEL, highlightthickness=0, bd=0)
    sb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview, style="Calc.Vertical.TScrollbar")
    inner = tk.Frame(canvas, bg=th.PANEL)
    win = canvas.create_window((0, 0), window=inner, anchor="nw")
    inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win, width=e.width))
    canvas.configure(yscrollcommand=sb.set)
    canvas.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")

    def wheel(e):
        canvas.yview_scroll(-1 if e.delta > 0 else 1, "units")
        return "break"
    for w in (canvas, inner):
        w.bind("<MouseWheel>", wheel)
    inner._wheel = wheel
    return outer, inner


def bind_wheel(widget, inner):
    widget.bind("<MouseWheel>", inner._wheel)
    for c in widget.winfo_children():
        bind_wheel(c, inner)


# ---- Files: the calculator manager, inside the panel ----
class FilesSection(object):
    def __init__(self, panel, parent):
        import calc_manager
        import mirror as mirror_mod
        self.frame = tk.Frame(parent, bg=th.PANEL)
        holder = tk.Frame(self.frame, bg=th.BG)
        holder.pack(fill="both", expand=True)
        m = panel.m
        m.manager = calc_manager.Manager(m, mirror_mod.KIT, mirror_mod.prepare_for_nspire,
                                         parent=holder, about_cb=lambda: panel.show("Info"))
        m.manager.win.pack(fill="both", expand=True)


# ---- Keys: generated from the calculator's own key table ----
class KeysSection(object):
    def __init__(self, panel, parent):
        self.m = panel.m
        self.frame = tk.Frame(parent, bg=th.PANEL)
        outer, inner = scrolled(self.frame)
        outer.pack(fill="both", expand=True)
        self.caps = {}  # keysym -> (keycap label, calculator label)
        self.lit = None
        for group, rows in self.m.calc.key_groups():
            heading(inner, group)
            for pc, calc, keysym in rows:
                r = tk.Frame(inner, bg=th.PANEL)
                r.pack(fill="x", pady=1)
                cap = th.keycap(r, pc)
                cap.pack(side="left")
                tk.Label(r, text="→", bg=th.PANEL, fg=th.DIM).pack(side="left", padx=6)
                out = tk.Label(r, text=calc, bg=th.PANEL, fg=th.FG, anchor="w", justify="left",
                               wraplength=300)
                out.pack(side="left", fill="x")
                if keysym:
                    self.caps[keysym] = (cap, out)
                    if keysym == "Return":
                        self.caps["KP_Enter"] = (cap, out)
        heading(inner, "Typing")
        tk.Label(inner, text="Letters, digits and symbols type themselves%s. Ctrl+V types the "
                 "clipboard: the Symbols panel's symbols too." % (
                     " (lower case is the 84's capital)" if self.m.calc.slug == "ti84" else ""),
                 bg=th.PANEL, fg=th.DIM, wraplength=400, justify="left", anchor="w").pack(fill="x")
        bind_wheel(inner, inner)
        self.m.listeners.append(self.pressed)

    def pressed(self, keysym):
        if self.lit is not None:
            cap, out = self.lit
            cap.configure(bg=th.KEYCAP, fg=th.FG)
            out.configure(fg=th.FG)
            self.lit = None
        if keysym in self.caps:
            cap, out = self.caps[keysym]
            cap.configure(bg=th.ACCENT, fg="#000000")
            out.configure(fg=th.ACCENT)
            self.lit = (cap, out)


# ---- Symbols ----
class SymbolsSection(object):
    COLS = 6

    def __init__(self, panel, parent):
        self.m = panel.m
        calc = self.m.calc
        self.frame = tk.Frame(parent, bg=th.PANEL)
        tk.Label(self.frame, text="Click a symbol to type it on the %s." % calc.title, bg=th.PANEL,
                 fg=th.DIM, anchor="w").pack(fill="x", pady=(0, 8))
        grid = tk.Frame(self.frame, bg=th.PANEL)
        grid.pack(fill="x")
        self.hint = tk.StringVar(master=self.frame, value="")
        for k, (sym, what, keys, near) in enumerate(calc.SYMBOLS):
            codes = calc_models.symbol_codes(calc, keys) if keys is not None else None
            if calc.slug == "nspire" and isinstance(keys, str):
                codes, missing = calc.paste_keys(keys)
                codes = None if missing else codes
            ok = codes is not None
            b = tk.Label(grid, text=sym, bg=th.KEYCAP if ok else th.PANEL, fg=th.FG if ok else th.GREY,
                         font=(th.FONT, 13), width=4, pady=6, cursor="hand2" if ok else "arrow",
                         highlightthickness=1, highlightbackground=th.KEYCAP_EDGE)
            b.grid(row=k // self.COLS, column=k % self.COLS, padx=2, pady=2, sticky="nsew")
            text = "%s: %s" % (sym, what) + ("" if ok else " (not on the %s: %s)" % (calc.title, near))
            if ok:
                seq = (" ".join(calc.calc_label(x) if isinstance(x, str) and len(x) > 1 else str(x)
                                for x in keys) if not isinstance(keys, str) else keys)
                text += "   keys: " + seq
                b.bind("<Button-1>", lambda e, c=codes, s=sym, b=b: self.send(c, s, b))
            b.bind("<Enter>", lambda e, t=text: self.hint.set(t))
            b.bind("<Leave>", lambda e: self.hint.set(""))
        for c in range(self.COLS):
            grid.columnconfigure(c, weight=1)
        tk.Label(self.frame, textvariable=self.hint, bg=th.PANEL, fg=th.FG, anchor="w", justify="left",
                 wraplength=410, height=3).pack(fill="x", pady=(10, 0))
        tk.Label(self.frame, text="Greyed: the calculator has no such symbol; the hint says what "
                 "to use instead. Pasting text with these symbols (Ctrl+V) types them the same way.",
                 bg=th.PANEL, fg=th.DIM, anchor="w", justify="left", wraplength=410).pack(fill="x", pady=(6, 0))

    def send(self, codes, sym, b):
        if self.m.send_codes(codes, sym):
            b.configure(bg=th.ACCENT, fg="#000000")
            b.after(250, lambda: b.configure(bg=th.KEYCAP, fg=th.FG))


# ---- Guide: the calculator's guide, rendered ----
class GuideSection(object):
    def __init__(self, panel, parent):
        import mirror as mirror_mod
        self.panel, self.m = panel, panel.m
        self.mirror_mod = mirror_mod
        self.frame = tk.Frame(parent, bg=th.PANEL)
        top = tk.Frame(self.frame, bg=th.PANEL)
        top.pack(fill="x", pady=(0, 6))
        self.contents = tk.Menubutton(top, text="Contents ▾", bg=th.PANEL2, fg=th.FG,
                                      activebackground=th.ACTIVE, activeforeground="#ffffff",
                                      relief="flat", bd=0, padx=8, pady=4, takefocus=0)
        self.contents.pack(side="left")
        self.search = tk.Entry(top, bg=th.PANEL2, fg=th.FG, insertbackground=th.FG, relief="flat",
                               width=18)
        self.search.pack(side="left", padx=(8, 4), ipady=3)
        self.search.bind("<Return>", lambda e: self.find())
        th.button(top, "Find", self.find, pady=2).pack(side="left")
        self.found = tk.Label(top, text="", bg=th.PANEL, fg=th.DIM)
        self.found.pack(side="left", padx=6)
        mid = tk.Frame(self.frame, bg=th.PANEL)
        mid.pack(fill="both", expand=True)
        self.box = tk.Text(mid, bg=th.BG, fg=th.FG, relief="flat", wrap="word", padx=10, pady=8,
                           highlightthickness=0, bd=0, cursor="arrow", insertwidth=0)
        sb = ttk.Scrollbar(mid, orient="vertical", command=self.box.yview, style="Calc.Vertical.TScrollbar")
        self.box.configure(yscrollcommand=sb.set)
        self.box.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.note = tk.StringVar(master=self.frame, value="")
        tk.Label(self.frame, textvariable=self.note, bg=th.PANEL, fg=th.DIM, anchor="w",
                 justify="left", wraplength=410).pack(fill="x", pady=(6, 0))
        self.last_find = ("", "1.0")
        self.loaded = False

    def shown(self):
        if not self.loaded:
            self.loaded = True
            self.frame.after(10, self.load)

    def load(self):
        folder, name = GUIDES[self.m.calc.slug]
        path = self.mirror_mod.resource(folder, name)
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except OSError as e:
            self.note.set("The guide isn't there: %s" % e)
            return
        blocks = md_render.parse(text)
        colors = dict(fg=th.FG, dim=th.DIM, accent=th.ACCENT, code_bg="#121317", link=th.MINT,
                      rule=th.LINE, bg=th.BG)
        fonts = dict(body=(th.FONT, 10), bold=(th.FONT, 10, "bold"), italic=(th.FONT, 10, "italic"),
                     code=(th.MONO, 10), h1=(th.FONT, 16, "bold"), h2=(th.FONT, 13, "bold"),
                     h3=(th.FONT, 11, "bold"))
        self.anchors = md_render.render(self.box, blocks, {"copy": self.copy, "send": self.send},
                                        colors, fonts)
        menu = th.menu(self.contents)
        for level, text_, anchor in md_render.headings(blocks, 3):
            if level == 1:
                continue
            menu.add_command(label=("    " if level == 3 else "") + text_,
                             command=lambda a=anchor: self.box.yview("h_" + a))
        self.contents.configure(menu=menu)
        self.note.set("%s. Examples with a name have Send to calculator." % name)

    def find(self):
        q = self.search.get().strip()
        self.box.tag_remove("found", "1.0", "end")
        if not q:
            self.found.configure(text="")
            return
        start = self.last_find[1] if self.last_find[0] == q else "1.0"
        idx = self.box.search(q, start, nocase=True, stopindex="end")
        if not idx and start != "1.0":
            idx = self.box.search(q, "1.0", nocase=True, stopindex="end")
        if not idx:
            self.found.configure(text="not found")
            return
        end = "%s+%dc" % (idx, len(q))
        self.box.tag_add("found", idx, end)
        self.box.see(idx)
        count = len(self.box.tag_ranges("found"))
        total, pos = 0, "1.0"
        while True:
            pos = self.box.search(q, pos, nocase=True, stopindex="end")
            if not pos:
                break
            total += 1
            pos = "%s+%dc" % (pos, len(q))
        self.found.configure(text="%d found (Enter: next)" % total if count else "")
        self.last_find = (q, end)

    def copy(self, text):
        self.box.clipboard_clear()
        self.box.clipboard_append(text)
        self.note.set("Copied")

    def send(self, name, info, text):
        m, slug = self.m, self.m.calc.slug
        if not m.connected():
            self.note.set("The %s isn't connected" % m.calc.title)
            return
        folder = os.path.join(tempfile.gettempdir(), "calcsuite_guide")
        os.makedirs(folder, exist_ok=True)
        if slug == "nspire":
            path = os.path.join(folder, name + ".py")
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(text + "\n")
            tns, error = self.mirror_mod.prepare_for_nspire(path)
            if error:
                self.note.set(error)
                return
            self.note.set("Sending %s.tns..." % name)
            m.send_nspire_files([(tns, "/")], lambda ok, msg: self.note.set(
                msg + (". Run it: My Documents > %s, then ctrl+R" % name if ok else "")))
            return
        import send_ti
        path = os.path.join(folder, name + ".txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        self.note.set("Sending %s..." % name)
        send_ti.send_path(m, path, self.mirror_mod.KIT, lambda ok, msg: self.note.set(msg), name=name)


# ---- Get programs ----
class ProgramsSection(object):
    def __init__(self, panel, parent):
        import mirror as mirror_mod
        self.m = panel.m
        self.kit = mirror_mod.KIT
        slug = self.m.calc.slug
        self.items = plib.for_calc(plib.load(), slug)
        self.frame = tk.Frame(parent, bg=th.PANEL)
        tk.Label(self.frame, text="Picked for engineering work. Downloads happen only when you "
                 "click, from ticalc.org or GitHub.", bg=th.PANEL, fg=th.DIM, anchor="w",
                 justify="left", wraplength=410).pack(fill="x", pady=(0, 6))
        mid = tk.Frame(self.frame, bg=th.PANEL)
        mid.pack(fill="both", expand=True)
        tree = self.tree = ttk.Treeview(mid, columns=("cat",), style="Calc.Treeview",
                                        selectmode="browse", height=9)
        tree.heading("#0", text="Program", anchor="w")
        tree.column("#0", width=270, anchor="w")
        tree.heading("cat", text="Category", anchor="w")
        tree.column("cat", width=110, anchor="w")
        sb = ttk.Scrollbar(mid, orient="vertical", command=tree.yview, style="Calc.Vertical.TScrollbar")
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        tree.tag_configure("unverified", foreground=th.DIM)
        for k, i in enumerate(self.items):
            name = i["name"] + ("" if i.get("verified") else "  (unverified)")
            tree.insert("", "end", iid=str(k), text=name, values=(i.get("category", ""),),
                        tags=(() if i.get("verified") else ("unverified",)))
        tree.bind("<<TreeviewSelect>>", lambda e: self.picked())
        self.detail = tk.Text(self.frame, bg=th.BG, fg=th.FG, relief="flat", wrap="word", height=11,
                              padx=8, pady=6, highlightthickness=0, bd=0, font=(th.FONT, 9))
        self.detail.pack(fill="x", pady=(8, 0))
        self.detail.tag_configure("b", font=(th.FONT, 10, "bold"))
        self.detail.tag_configure("dim", foreground=th.DIM)
        self.detail.tag_configure("warn", foreground=th.ACCENT)
        self.detail.tag_configure("link", foreground=th.MINT, underline=True)
        bar = tk.Frame(self.frame, bg=th.PANEL)
        bar.pack(fill="x", pady=(6, 0))
        self.act = th.button(bar, "Download and send", self.act_on, state="disabled")
        self.act.pack(side="left")
        self.info_btn = th.button(bar, "Info page", self.open_info, state="disabled")
        self.info_btn.pack(side="left", padx=(6, 0))
        self.status = tk.StringVar(master=self.frame, value="%d programs for the %s" % (
            len(self.items), self.m.calc.title))
        tk.Label(self.frame, textvariable=self.status, bg=th.PANEL, fg=th.DIM, anchor="w",
                 justify="left", wraplength=410).pack(fill="x", pady=(6, 0))
        self.item = None
        self.busy = False

    def picked(self):
        sel = self.tree.selection()
        if not sel:
            return
        i = self.item = self.items[int(sel[0])]
        d = self.detail
        d.configure(state="normal")
        d.delete("1.0", "end")
        d.insert("end", i["name"] + "\n", "b")
        d.insert("end", (i.get("description") or "") + "\n")
        d.insert("end", "%s  ·  by %s  ·  licence: %s\n" % (
            i.get("category", ""), i.get("author") or "not checked", i.get("license") or "not stated"), "dim")
        d.insert("end", "Source: %s%s\n" % (i.get("source_site") or "", "" if i.get("verified")
                                             else "  (unverified: from a directory listing)"), "dim")
        flag, note = plib.needs_old_os(i, self.m.calc.slug, self.m.info.get("os"))
        if note:
            d.insert("end", note + "\n", "warn" if flag or flag is None else "dim")
        if i.get("dependencies"):
            d.insert("end", "Needs: %s\n" % ", ".join(i["dependencies"]), "warn")
        if i.get("special_handling"):
            d.insert("end", "Note: %s\n" % i["special_handling"], "dim")
        if i.get("action") == "ti_page":
            d.insert("end", "TI's own app: TI's page has its licence; download it there and send "
                     "it with Files > Upload. CalcSuite never downloads TI files.\n", "dim")
        elif i.get("action") == "page":
            d.insert("end", "Opens its page: CalcSuite can't send this one itself (an app, or an "
                     "install with steps on the calculator).\n", "dim")
        d.configure(state="disabled")
        self.act.configure(text=plib.action_text(i), state="normal" if not self.busy else "disabled")
        self.info_btn.configure(state="normal" if i.get("info_url") else "disabled")

    def open_info(self):
        if self.item and self.item.get("info_url"):
            webbrowser.open(self.item["info_url"])

    def act_on(self):
        i = self.item
        if i is None:
            return
        if i.get("action") == "ti_page":
            if messagebox.askokcancel("TI's page", "TI's own apps come with TI's licence, which "
                                      "you accept on TI's page when you download. Open it in your "
                                      "browser?", parent=self.frame):
                webbrowser.open(i.get("info_url") or "https://education.ti.com/en/software/search")
            return
        if i.get("action") != "download":
            webbrowser.open(i.get("info_url") or i.get("download_url"))
            return
        if not self.m.connected():
            self.status.set("The %s isn't connected" % self.m.calc.title)
            return
        flag, note = plib.needs_old_os(i, self.m.calc.slug, self.m.info.get("os"))
        if flag and not messagebox.askyesno("Assembly program", note + "\n\nSend it anyway?",
                                            icon="warning", parent=self.frame):
            return
        self.busy = True
        self.act.configure(state="disabled")
        self.status.set("Downloading %s..." % i["name"])

        def progress(done, total):
            self.say("Downloading %s: %s%s" % (i["name"], human(done),
                                                " of %s" % human(total) if total else ""))

        def work():
            try:
                path = plib.download(i["download_url"], progress)
                files = plib.pick_files(path, i)
            except Exception as e:
                alt = i.get("alt_download_url")
                try:
                    if not alt:
                        raise
                    path = plib.download(alt, progress)
                    files = plib.pick_files(path, i)
                except Exception:
                    self.ui(self.done, False, "Couldn't get it: %s" % e)
                    return
            out = os.path.join(plib.CACHE, "files", i["id"])
            os.makedirs(out, exist_ok=True)
            local = []
            for name, data, folder in files:
                p = os.path.join(out, name)
                with open(p, "wb") as f:
                    f.write(data)
                local.append((p, folder))
            self.ui(self.send_files, local)
        threading.Thread(target=work, daemon=True).start()

    def say(self, text):
        self.ui(self.status.set, text)

    def ui(self, fn, *args):
        try:
            self.frame.after(0, lambda: fn(*args))
        except (tk.TclError, RuntimeError):
            pass

    def send_files(self, local):
        m = self.m
        names = ", ".join(os.path.basename(p) for p, _f in local[:4])
        more = " and %d more" % (len(local) - 4) if len(local) > 4 else ""
        if not messagebox.askyesno("Send to the %s?" % m.calc.title, "Send %s%s to the %s?%s" % (
                names, more, m.calc.title, "\n\nNspire: into %s" % ", ".join(sorted(set(f or "/" for _p, f in local)))
                if m.calc.slug == "nspire" else ""), parent=self.frame):
            self.done(False, "Downloaded, not sent (it's kept in %s)" % plib.CACHE)
            return
        self.status.set("Sending %d file(s)..." % len(local))
        if m.calc.slug == "nspire":
            m.send_nspire_files([(p, f or "/") for p, f in local],
                                lambda ok, msg: self.done(ok, msg + (self.after_note() if ok else "")))
            return
        import send_ti
        prepared = []
        for p, _f in local:
            try:
                prepared.append(send_ti.prepare(p, m.calc.slug))
            except (OSError, ValueError) as e:
                self.done(False, "%s can't be sent: %s" % (os.path.basename(p), e))
                return
        send_ti.send_prepared(m, prepared, lambda ok, msg: self.done(ok, msg + (self.after_note() if ok else "")))

    def after_note(self):
        sh = (self.item or {}).get("special_handling") or ""
        if "MyLib" in sh or "Refresh Libraries" in sh:
            return ". Library: on the handheld, doc > Refresh Libraries (or restart it)"
        if "install()" in sh:
            return ". Then run install() on the 89"
        return ""

    def done(self, ok, msg):
        self.busy = False
        self.status.set(msg)
        if self.item is not None:
            self.act.configure(state="normal")


def human(n):
    for unit in ("B", "KB", "MB"):
        if n < 1024 or unit == "MB":
            return ("%d %s" % (n, unit)) if unit == "B" else "%.1f %s" % (n, unit)
        n /= 1024.0


# ---- Info: About, the clock, Press-to-Test, the connection doctor ----
class InfoSection(object):
    def __init__(self, panel, parent):
        import mirror as mirror_mod
        self.panel, self.m = panel, panel.m
        self.mirror_mod = mirror_mod
        self.frame = tk.Frame(parent, bg=th.PANEL)
        outer, inner = scrolled(self.frame)
        outer.pack(fill="both", expand=True)
        self.inner = inner
        heading(inner, "This calculator")
        self.about = tk.Frame(inner, bg=th.BG)
        self.about.pack(fill="x")
        row = tk.Frame(inner, bg=th.PANEL)
        row.pack(fill="x", pady=(8, 0))
        th.button(row, "Refresh", self.refresh_about).pack(side="left")
        th.button(row, "Reconnect", self.m.reconnect).pack(side="left", padx=(6, 0))
        heading(inner, "Connection doctor")
        self.doctor = tk.Frame(inner, bg=th.PANEL)
        self.doctor.pack(fill="x")
        th.button(inner, "Check again", self.check).pack(anchor="w", pady=(6, 0))
        if mirror_mod.SPONSOR_URL:
            heading(inner, "CalcSuite")
            a = tk.Label(inner, text="Support CalcSuite", bg=th.PANEL, fg=th.MINT, cursor="hand2",
                         font=(th.FONT, 10, "underline"))
            a.pack(anchor="w")
            a.bind("<Button-1>", lambda e: webbrowser.open(mirror_mod.SPONSOR_URL))
        self.inner_wheel = inner
        self.built = False

    def shown(self):
        if not self.built:
            self.built = True
            self.refresh_about()
            self.check()

    def manager(self):
        m = self.m
        if "Files" not in self.panel.sections:  # Builds the manager (its file list, not shown)
            self.panel.sections["Files"] = FilesSection(self.panel, self.panel.body)
        return m.manager

    def refresh_about(self):
        mgr = self.manager()
        mgr.build_about(self.about)

    # ---- The connection doctor ----
    def check(self):
        for c in self.doctor.winfo_children():
            c.destroy()
        tk.Label(self.doctor, text="Checking Windows' drivers...", bg=th.PANEL, fg=th.DIM).pack(anchor="w")

        def work():
            import calc_doctor
            try:
                # probe=False: CalcSuite itself holds the calculator (it would show as busy)
                report = calc_doctor.diagnose(probe=False)
            except Exception as e:
                report = {"devices": [], "notes": ["The check failed: %s" % e]}
            try:
                self.frame.after(0, lambda: self.show_doctor(report))
            except (tk.TclError, RuntimeError):
                pass
        threading.Thread(target=work, daemon=True).start()

    def show_doctor(self, report):
        for c in self.doctor.winfo_children():
            c.destroy()
        pid = "%04x" % self.m.calc.pid
        mine = [d for d in report.get("devices", []) if d.get("pid") == pid]
        if not mine:
            tk.Label(self.doctor, text="Windows doesn't list this calculator now.", bg=th.PANEL,
                     fg=th.FG, anchor="w").pack(fill="x")
        for d in mine[:1]:
            ok = d.get("status") == "ready"
            line = tk.Frame(self.doctor, bg=th.PANEL)
            line.pack(fill="x")
            dot = tk.Canvas(line, width=10, height=10, bg=th.PANEL, highlightthickness=0)
            dot.create_oval(1, 1, 9, 9, fill=th.MINT if ok else th.ACCENT, outline="")
            dot.pack(side="left", padx=(0, 6))
            tk.Label(line, text=d.get("headline", ""), bg=th.PANEL, fg=th.MINT if ok else th.ACCENT,
                     font=(th.FONT, 10, "bold")).pack(side="left")
            text = d.get("text", "")
            if all(p.startswith("CalcSuite") for p in report.get("programs", [])):
                # The link programs running are CalcSuite's own (this window's): no advice needed
                import re
                text = re.sub(r" \([^()]*(\([^()]*\)[^()]*)*is running: if a transfer fails, close it\.\)",
                              "", text)
            tk.Label(self.doctor, text=text, bg=th.PANEL, fg=th.FG, anchor="w",
                     justify="left", wraplength=400).pack(fill="x", pady=(2, 0))
            if d.get("driver"):
                tk.Label(self.doctor, text="Driver: %s (%s)" % (d["driver"], d.get("provider") or "unknown"),
                         bg=th.PANEL, fg=th.DIM, anchor="w").pack(fill="x")
            row = tk.Frame(self.doctor, bg=th.PANEL)
            row.pack(fill="x", pady=(6, 0))
            if d.get("fix") == "install_winusb":
                th.button(row, "Install the WinUSB driver...",
                          lambda d=d: self.fix("install", d)).pack(side="left", padx=(0, 6))
            if d.get("alt_fix") == "restore_ti" or (d.get("can_restore_ti") and d.get("present")):
                th.button(row, "Restore TI's driver...",
                          lambda d=d: self.fix("restore", d)).pack(side="left")
        for n in report.get("notes", [])[:2]:
            tk.Label(self.doctor, text=n, bg=th.PANEL, fg=th.DIM, anchor="w", justify="left",
                     wraplength=400).pack(fill="x", pady=(4, 0))

    def fix(self, which, d):
        """Shows the helper's dry run first; the real change (admin prompt) only on OK"""
        import calc_doctor
        fn = calc_doctor.install_winusb if which == "install" else calc_doctor.restore_ti
        for c in self.doctor.winfo_children():
            if isinstance(c, tk.Frame):
                for b in c.winfo_children():
                    if isinstance(b, tk.Button):
                        b.configure(state="disabled")

        def dry():
            res = fn(d["pid"], dry_run=True)
            self.frame.after(0, lambda: self.confirm(which, d, fn, res))
        threading.Thread(target=dry, daemon=True).start()

    def confirm(self, which, d, fn, res):
        steps = "\n".join("- " + s for s in res.get("steps", [])[:12]) or "(the helper listed no steps)"
        errs = "\n".join(res.get("errors", [])[:4])
        what = ("put the WinUSB driver on the %s" % d["model"] if which == "install" else
                "take CalcSuite's WinUSB driver off the %s" % d["model"])
        warn = ""
        if which == "restore" and not d.get("ti_driver_installed"):
            warn = ("\n\nTI's own driver isn't installed on this PC: the calculator will have no "
                    "driver until TI's software is installed again.")
        if not messagebox.askokcancel(
                "Change the driver?", "This will %s. Windows asks for admin rights.\n\nWhat it "
                "will do:\n%s%s%s\n\nCalcSuite lets go of the calculator while it runs." % (
                    what, steps, "\n\nNote: " + errs if errs else "", warn),
                icon="warning", parent=self.frame):
            self.check()
            return
        self.m.release()

        def work():
            r = fn(d["pid"])
            self.frame.after(0, lambda: self.fixed(r))
        threading.Thread(target=work, daemon=True).start()

    def fixed(self, res):
        if res.get("cancelled"):
            msg = "Not changed (the admin prompt was declined)"
        elif res.get("ok"):
            msg = "Done: %s" % res.get("result")
        else:
            msg = "Didn't work: %s" % "; ".join(res.get("errors", [])[:2])
        self.m.set_status(msg)
        self.m.reconnect()
        self.check()

