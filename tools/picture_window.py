"""Make a picture: a PC picture (open, paste, or drag it onto the window) made into a
calculator's own picture, with a live preview at the calculator's resolution and colours.
Send it to the calculator of this tab, or save the file.

- TI-84 Plus CE: Image1-Image0 (.8ca, a graph background, 133 x 83 in full colour, shown
  2 x 2) or Pic1-Pic0 (.8ci, 265 x 165 in the calculator's 15 colours).
- TI-89 Titanium: a picture (.89i), black and white: the Graph screen's 159 x 77, the whole
  160 x 100, or 240 x 128.
- TI-Nspire CX II: a Python program that paints the picture (ti_draw, 318 x 212), its size
  picked to stay under 20 KB.

The conversion runs on a worker thread; its results come back through a queue the window
reads with after(), so no worker ever touches Tk. Formats: picture_formats.py; reading PC
pictures: picture_load.py.

    python tools/picture_window.py [picture]      the window alone (Save only)
"""

import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import picture_formats as pf  # noqa: E402
import picture_load as pl  # noqa: E402
import ui_theme as th  # noqa: E402

TITLES = {"ti84": "TI-84 Plus CE", "ti89": "TI-89 Titanium", "nspire": "TI-Nspire CX II"}
KINDS = {
    "ti84": (("image", "Image (background), 133 x 83, all colours"),
             ("pic", "Pic, 265 x 165, the 15 colours")),
    "ti89": tuple(("89:%dx%d" % (w, h), "%s, %d x %d" % (what, w, h)) for w, h, what in pf.SIZES_89),
    "nspire": (("program", "Python program that paints it, 318 x 212"),),
}
FITS = ((pf.FIT, "Whole picture (bars around)"), (pf.FILL, "Fill the screen (cut the edges)"),
        (pf.STRETCH, "Stretch to the screen"))
DITHERS = ((pf.DIFFUSE, "Smooth (blend dots)"), (pf.PATTERN, "Pattern"), (pf.NONE, "None (flat colours)"))
DETAILS = (("auto", "Best that fits 20 KB"), ("1", "Every pixel"), ("2", "2 x 2 pixels"),
           ("3", "3 x 3 pixels"), ("4", "4 x 4 pixels"), ("6", "6 x 6 pixels"))
COLOURS = ("8", "16", "32", "64")
PREVIEW_W, PREVIEW_H = 640, 430


class Result(object):
    """One conversion: what the calculator will show, the file, how to see it there"""

    def __init__(self, preview, blob, file_name, var, info, scale=1, py=None):
        self.preview, self.blob, self.file_name, self.var = preview, blob, file_name, var
        self.info, self.scale, self.py = info, scale, py


def default_settings(slug):
    return {"model": slug, "kind": KINDS[slug][0][0], "fit": pf.FIT, "bg": "white",
            "dither": pf.DIFFUSE, "brightness": 0, "contrast": 0,
            "name": default_name(slug, KINDS[slug][0][0]), "detail": "auto", "colours": "32"}


def default_name(slug, kind, stem=None):
    if slug == "ti84":
        return "Image1" if kind == "image" else "Pic1"
    s = "".join(c for c in (stem or "").lower() if c.isalnum() or c == "_").lstrip("0123456789_")
    if slug == "ti89":
        s = s.replace("_", "")[:8]
        return s if pf.cf.NAME_89.match(s) else "zzpic"
    return s[:16] if s and pf.NSPIRE_NAME.match(s[:16]) else "zzpic"


def convert(source, st):
    """source (a picture_load.Source) + the window's settings -> a Result. Raises ValueError
    for a bad name. Pure apart from source.render: the self-test calls it directly."""
    slug, kind = st["model"], st["kind"]
    bg = (0, 0, 0) if st.get("bg") == "black" else (255, 255, 255)
    fit, dither = st["fit"], st["dither"]
    look = lambda img: pf.adjust(img, st.get("brightness", 0), st.get("contrast", 0))
    name = (st.get("name") or "").strip()
    if slug == "ti84" and kind == "image":
        img = look(source.render(pf.CE_IMAGE_W, pf.CE_IMAGE_H, fit, bg))
        vals = pf.to_565(img, dither)
        blob = pf.ce_image_8ca(vals, name)
        shown = pf.Img(img.w, img.h, b"".join(bytes(pf.rgb565(v)) for v in vals))
        var = "Image%d" % pf.name_digit(name, "Image")
        return Result(shown, blob, var + ".8ca", var, (
            "%s (.8ca, %s, kept in Archive). On the 84: Graph, 2nd FORMAT, Background %s "
            "(or BackgroundOn %s in a program). Shown 2 x 2: 266 x 166."
            % (var, _kb(blob), var, var)), scale=2)
    if slug == "ti84":
        img = look(source.render(pf.CE_PIC_W, pf.CE_PIC_H, fit, bg))
        idx = pf.quantize(img, pf.CE_PALETTE, dither)
        blob = pf.ce_pic_8ci(idx, name)
        d = pf.name_digit(name, "Pic")
        return Result(pf.paint(img.w, img.h, idx, pf.CE_PALETTE), blob, "Pic%d.8ci" % d, "Pic%d" % d, (
            "Pic%d (.8ci, %s). On the 84: Graph, 2nd DRAW, STO, RecallPic %d, Enter "
            "(ClrDraw clears it)." % (d, _kb(blob), d)))
    if slug == "ti89":
        w, h = (int(v) for v in kind.split(":")[1].split("x"))
        img = pf.grey(look(source.render(w, h, fit, bg)))
        idx = pf.quantize(img, pf.MONO, dither)
        blob = pf.ti89_pic_89i(idx, w, h, name)
        return Result(pf.paint(w, h, idx, pf.MONO), blob, name + ".89i", name, (
            "%s (.89i, %s, %d x %d black and white). On the 89: Home screen, type RclPic %s "
            "and Enter, then open the Graph screen (diamond F3)." % (name, _kb(blob), w, h, name)))
    # TI-Nspire CX II
    if not pf.NSPIRE_NAME.match(name):
        raise ValueError("a program name is lower-case letters, digits and _ (up to 16), a letter first")
    ncol = int(st.get("colours", "16"))
    scales = pf.NSPIRE_SCALES if st.get("detail", "auto") == "auto" else (int(st["detail"]),)
    for scale in scales:
        w, h, _x0, _y0 = pf.nspire_grid(scale)
        img = look(source.render(w, h, fit, bg))
        pal = pf.median_cut(img, ncol)
        idx = pf.quantize(img, pal, dither)
        py = pf.nspire_program(idx, pal, scale, name)
        if len(py) <= pf.NSPIRE_BUDGET or scale == scales[-1]:
            break
    big = len(py) > pf.NSPIRE_BUDGET
    shown = pf.paint(w, h, idx, pal)
    return Result(shown, py.encode("ascii"), name + ".py", name, (
        "%s.tns (a Python program, %s of Python, %d colours, %s). On the handheld: My "
        "Documents > %s.tns, then ctrl+R; any key ends it.%s" % (
            name, _kb(py), len(pal), "every pixel" if scale == 1 else "%d x %d pixels" % (scale, scale),
            name, " Over 20 KB: slow to open on the handheld; pick bigger pixels or fewer colours."
            if big else "")), scale=scale, py=py)


def _kb(blob):
    n = len(blob)
    return "%d bytes" % n if n < 1024 else "%.1f KB" % (n / 1024.0)


class PicturePanel(tk.Frame):
    """The picture maker as a frame: it lives in a tab of the main window, or in PictureWindow
    (a thin window around it). on_close: what Close does (nothing given: no Close button)."""

    def __init__(self, parent, mirror=None, kit=None, slug=None, path=None, on_close=None):
        tk.Frame.__init__(self, parent, bg=th.BG, takefocus=1)
        self.m, self.kit, self.on_close = mirror, kit, on_close
        self.slug = slug or (mirror.calc.slug if mirror is not None else "ti84")
        self.source = None
        self.result = None
        self.error = None
        self.gen = 0
        self.busy = False
        self.dirty = False
        self.results = queue.Queue()
        self.job = None
        self.photo = None
        self.win = self  # Where after(), dialogs and pictures belong
        style = th.style_ttk(self)
        style.configure("Pic.TCombobox", fieldbackground=th.PANEL2, background=th.PANEL2, foreground=th.FG,
                        arrowcolor=th.FG, bordercolor=th.LINE, lightcolor=th.PANEL2, darkcolor=th.PANEL2)
        style.map("Pic.TCombobox", fieldbackground=[("readonly", th.PANEL2)], foreground=[("readonly", th.FG)],
                  selectbackground=[("readonly", th.PANEL2)], selectforeground=[("readonly", th.FG)])
        style.configure("Pic.Horizontal.TScale", background=th.DIM, troughcolor=th.PANEL2,
                        bordercolor=th.PANEL, lightcolor=th.DIM, darkcolor=th.DIM)
        style.map("Pic.Horizontal.TScale", background=[("active", th.ACCENT)])
        self.option_add("*TCombobox*Listbox.background", th.PANEL2)
        self.option_add("*TCombobox*Listbox.foreground", th.FG)
        self.option_add("*TCombobox*Listbox.selectBackground", th.ACCENT)
        self.st = default_settings(self.slug)
        self.vars = {}
        self.build()
        # Dropped files: on the preview and on the whole panel
        self.drops = [pl.DropTarget(w, self.dropped) for w in (self, self.canvas)]
        # Keys work while the panel has the focus (a click on it gives it): never the mirror's
        for seq, fn in (("<Control-v>", self.paste), ("<Control-o>", self.open_file), ("<Control-s>", self.save)):
            self.bind(seq, lambda e, fn=fn: (fn(), "break")[1])
        self.canvas.bind("<Button-1>", lambda e: self.focus_set(), add="+")
        self.bind("<Button-1>", lambda e: self.focus_set(), add="+")
        self.poll()
        if path:
            self.load(lambda: pl.load_file(path))

    # ---- The window ----
    def build(self):
        win = self.win
        left = tk.Frame(self, bg=th.PANEL, width=330)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        right = tk.Frame(self, bg=th.BG)
        right.pack(side="left", fill="both", expand=True)
        box = tk.Frame(left, bg=th.PANEL)
        box.pack(fill="both", expand=True, padx=14, pady=12)

        row = tk.Frame(box, bg=th.PANEL)
        row.pack(fill="x")
        th.button(row, "Open picture...", self.open_file).pack(side="left")
        th.button(row, "Paste", self.paste).pack(side="left", padx=(6, 0))
        self.hint = tk.Label(box, text="PNG, JPEG, BMP, GIF or TIFF: open one, paste one (ctrl+V), "
                             "or drag one onto this window.", bg=th.PANEL, fg=th.DIM, anchor="w",
                             justify="left", wraplength=300)
        self.hint.pack(fill="x", pady=(6, 0))

        self.models = [s for s in ("ti84", "ti89", "nspire")]
        self.combo(box, "For the", "model", [(s, TITLES[s]) for s in self.models], self.model_changed)
        self.kind_box = self.combo(box, "As", "kind", KINDS[self.slug], self.kind_changed)
        self.name_row = tk.Frame(box, bg=th.PANEL)
        self.name_row.pack(fill="x", pady=(8, 0))
        self.name_label = tk.Label(self.name_row, text="Name", bg=th.PANEL, fg=th.DIM, width=9, anchor="w")
        self.name_label.pack(side="left")
        self.name_var = tk.StringVar(master=win, value=self.st["name"])
        self.name_digits = ttk.Combobox(self.name_row, state="readonly", width=12, style="Pic.TCombobox")
        self.name_entry = tk.Entry(self.name_row, textvariable=self.name_var, bg=th.PANEL2, fg=th.FG,
                                   insertbackground=th.FG, relief="flat", width=18)
        self.name_digits.bind("<<ComboboxSelected>>", lambda e: (self.name_var.set(self.name_digits.get()),
                                                                 self.changed()))
        self.name_var.trace_add("write", lambda *a: self.changed())
        self.combo(box, "Fit", "fit", FITS, self.changed)
        self.combo(box, "Bars", "bg", (("white", "White"), ("black", "Black")), self.changed)
        self.user_dither = False  # Until the user picks one, each calculator gets its own default
        self.combo(box, "Dots", "dither", DITHERS, lambda: (setattr(self, "user_dither", True), self.changed()))
        self.ns_rows = [self.combo(box, "Detail", "detail", DETAILS, self.changed, keep=True),
                        self.combo(box, "Colours", "colours", [(c, c) for c in COLOURS], self.changed, keep=True)]
        for key, text in (("brightness", "Brightness"), ("contrast", "Contrast")):
            r = tk.Frame(box, bg=th.PANEL)
            r.pack(fill="x", pady=(8, 0))
            tk.Label(r, text=text, bg=th.PANEL, fg=th.DIM, width=9, anchor="w").pack(side="left")
            v = tk.DoubleVar(master=win, value=0)
            s = ttk.Scale(r, from_=-100, to=100, orient="horizontal", variable=v,
                          style="Pic.Horizontal.TScale",
                          command=lambda _v, k=key, var=v: self.set(k, int(round(var.get()))))
            s.pack(side="left", fill="x", expand=True)
            s.bind("<Double-Button-1>", lambda e, var=v, k=key: (var.set(0), self.set(k, 0)))
            self.vars[key] = v

        bar = tk.Frame(box, bg=th.PANEL)
        bar.pack(fill="x", side="bottom")
        self.send_btn = th.button(bar, "Send", self.send)
        self.send_btn.pack(side="left")
        self.save_btn = th.button(bar, "Save...", self.save)
        self.save_btn.pack(side="left", padx=(6, 0))
        if self.on_close is not None:
            th.button(bar, "Close", self.close).pack(side="right")

        self.canvas = tk.Canvas(right, bg=th.BG, highlightthickness=0, width=PREVIEW_W, height=PREVIEW_H)
        self.canvas.pack(fill="both", expand=True, padx=16, pady=(16, 8))
        self.info = tk.Label(right, text="", bg=th.BG, fg=th.FG, anchor="w", justify="left", wraplength=620)
        self.info.pack(fill="x", padx=16)
        self.status = tk.Label(right, text="", bg=th.BG, fg=th.DIM, anchor="w", justify="left", wraplength=620)
        self.status.pack(fill="x", padx=16, pady=(4, 14))
        self.canvas.bind("<Configure>", lambda e: self.draw())
        self.model_changed()

    def combo(self, parent, text, key, choices, on_change, keep=False):
        r = tk.Frame(parent, bg=th.PANEL)
        r.pack(fill="x", pady=(8, 0))
        tk.Label(r, text=text, bg=th.PANEL, fg=th.DIM, width=9, anchor="w").pack(side="left")
        c = ttk.Combobox(r, state="readonly", style="Pic.TCombobox")
        c.pack(side="left", fill="x", expand=True)
        c.choices = list(choices)
        c["values"] = [t for _k, t in c.choices]
        c.current([k for k, _t in c.choices].index(self.st[key]))
        c.key = key
        c.row = r

        def picked(_e):
            self.st[key] = c.choices[c.current()][0]
            on_change()
        c.bind("<<ComboboxSelected>>", picked)
        self.vars["combo_" + key] = c
        return c

    def set_choices(self, key, choices, value):
        c = self.vars["combo_" + key]
        c.choices = list(choices)
        c["values"] = [t for _k, t in c.choices]
        keys = [k for k, _t in c.choices]
        self.st[key] = value if value in keys else keys[0]
        c.current(keys.index(self.st[key]))

    def set(self, key, value):
        if self.st.get(key) != value:
            self.st[key] = value
            self.changed()

    def model_changed(self):
        model = self.st["model"]
        self.set_choices("kind", KINDS[model], self.st["kind"])
        for c in self.ns_rows:
            if model == "nspire":
                c.row.pack(fill="x", pady=(8, 0), after=self.vars["combo_dither"].row)
            else:
                c.row.pack_forget()
        if not self.user_dither:
            self.set_choices("dither", DITHERS, default_settings(model)["dither"])
        self.kind_changed(rename=True)
        here = self.m is not None and model == self.m.calc.slug
        self.send_btn.configure(text="Send to the %s" % TITLES[model] if here else "Send (this tab is the %s)"
                                % TITLES[self.slug], state="normal" if here else "disabled")

    def kind_changed(self, rename=True):
        model, kind = self.st["model"], self.st["kind"]
        self.name_digits.pack_forget()
        self.name_entry.pack_forget()
        if model == "ti84":
            word = "Image" if kind == "image" else "Pic"
            names = ["%s%d" % (word, d) for d in (1, 2, 3, 4, 5, 6, 7, 8, 9, 0)]
            self.name_digits["values"] = names
            cur = self.name_var.get()
            if cur not in names:
                cur = names[0]
            self.name_digits.set(cur)
            self.name_var.set(cur)
            self.name_digits.pack(side="left")
        else:
            cur = self.name_var.get()
            ok = pf.cf.NAME_89.match(cur) if model == "ti89" else pf.NSPIRE_NAME.match(cur)
            if not ok:
                self.name_var.set(default_name(model, kind, self.source.name if self.source else None))
            self.name_entry.pack(side="left", fill="x", expand=True)
        self.changed()

    # ---- Pictures in ----
    def open_file(self):
        start = self.kit if self.kit and os.path.isdir(self.kit) else os.path.expanduser("~")
        pics = os.path.join(os.path.expanduser("~"), "Pictures")
        path = filedialog.askopenfilename(
            parent=self.win, title="Open a picture", initialdir=pics if os.path.isdir(pics) else start,
            filetypes=[("Pictures", pl.EXTS), ("All files", "*.*")])
        if path:
            self.load(lambda: pl.load_file(path))

    def paste(self):
        def get():
            s = pl.from_clipboard()
            if s is None:
                raise pl.LoadError("the clipboard has no picture: copy one (or a picture file) first")
            return s
        self.load(get)

    def dropped(self, files):
        files = [f for f in files if os.path.isfile(f)]
        if files:
            self.load(lambda: pl.load_file(files[0]))

    def load(self, how):
        try:
            src = how()
        except pl.LoadError as e:
            self.say("Not opened: %s" % e)
            return
        except Exception:
            log_error("opening a picture")
            self.say("Not opened: that picture couldn't be read (the error is in errors.log)")
            return
        if self.source is not None:
            self.source.close()
        self.source = src
        if self.st["model"] != "ti84":
            self.name_var.set(default_name(self.st["model"], self.st["kind"], src.name))
        self.say("%s: %d x %d" % (src.name, src.w, src.h))
        self.changed()

    # ---- Converting (a worker) ----
    def changed(self):
        self.st["name"] = self.name_var.get().strip()
        if self.source is None:
            self.result = None
            self.draw()
            return
        self.dirty = True
        if self.job is None:
            self.job = self.win.after(120, self.start)

    def start(self):
        self.job = None
        if self.busy or not self.dirty or self.source is None:
            return
        self.dirty = False
        self.busy = True
        self.gen += 1
        gen, st, src = self.gen, dict(self.st), self.source
        self.say("Making the picture...")

        def work():
            try:
                self.results.put((gen, convert(src, st), None))
            except ValueError as e:
                self.results.put((gen, None, str(e)))
            except Exception:
                log_error("making a calculator picture")
                self.results.put((gen, None, "couldn't make it (the error is in errors.log)"))
        threading.Thread(target=work, daemon=True).start()

    def poll(self):
        try:
            while True:
                gen, res, err = self.results.get_nowait()
                self.busy = False
                if gen == self.gen:
                    self.result, self.error = res, err
                    self.say("Not ready: %s" % err if err else "")
                    self.draw()
        except queue.Empty:
            pass
        try:
            if self.dirty and not self.busy and self.job is None:
                self.start()
            self.win.after(60, self.poll)
        except tk.TclError:
            pass

    def draw(self):
        c = self.canvas
        c.delete("all")
        cw, ch = max(c.winfo_width(), 50), max(c.winfo_height(), 50)
        model = self.st["model"]
        res = self.result
        if res is None:
            c.create_text(cw // 2, ch // 2, fill=th.DIM, font=(th.FONT, 11), text=(
                "Open, paste or drag a picture here" if self.source is None else "..."))
            self.info.configure(text="")
            self.update_buttons()
            return
        img = res.preview
        base = res.scale if model in ("ti84", "nspire") else 1
        zoom = max(1, min((cw - 8) // (img.w * base), (ch - 8) // (img.h * base)))
        try:
            ph = tk.PhotoImage(master=self.win, data=img.ppm(base), format="ppm")
            if zoom > 1:
                ph = ph.zoom(zoom)
        except tk.TclError:
            log_error("showing a picture preview")
            return
        self.photo = ph
        w, h = ph.width(), ph.height()
        x, y = (cw - w) // 2, (ch - h) // 2
        c.create_rectangle(x - 3, y - 3, x + w + 2, y + h + 2, outline=th.LINE)
        c.create_image(x, y, image=ph, anchor="nw")
        self.info.configure(text=res.info)
        self.update_buttons()

    def update_buttons(self):
        ok = self.result is not None
        self.save_btn.configure(state="normal" if ok else "disabled")
        here = self.m is not None and self.st["model"] == self.m.calc.slug
        self.send_btn.configure(state="normal" if ok and here else "disabled")

    def say(self, text):
        try:
            self.status.configure(text=text)
        except tk.TclError:
            pass

    # ---- Out: save, send ----
    def current(self):
        if self.busy or self.dirty:
            self.say("Still making the picture: a moment")
            return None
        if self.result is None:
            self.say(self.error and "Not ready: %s" % self.error or "Open a picture first")
            return None
        return self.result

    def save(self):
        res = self.current()
        if res is None:
            return
        ext = os.path.splitext(res.file_name)[1]
        nspire = self.st["model"] == "nspire"
        path = filedialog.asksaveasfilename(
            parent=self.win, title="Save the picture", initialdir=out_folder(self.kit, "pictures"),
            initialfile=res.var + (".tns" if nspire else ext),
            defaultextension=".tns" if nspire else ext,
            filetypes=([("TI-Nspire document", "*.tns"), ("Python program", "*.py")] if nspire
                       else [("TI file", "*" + ext)]))
        if not path:
            return
        try:
            if nspire and path.lower().endswith(".tns"):
                import tns_writer
                blob = tns_writer.python_tns(res.var + ".py", res.blob)
            else:
                blob = res.blob
            with open(path, "wb") as f:
                f.write(blob)
            self.say("Saved %s" % path)
        except (OSError, ValueError) as e:
            log_error("saving a calculator picture")
            self.say("Not saved: %s" % e)

    def send(self):
        res = self.current()
        m = self.m
        if res is None or m is None:
            return
        if not m.connected():
            self.say("The %s isn't connected" % m.calc.title)
            return
        folder = out_folder(self.kit, "build", "pictures")
        path = os.path.join(folder, res.file_name)
        try:
            with open(path, "wb") as f:
                f.write(res.blob)
        except OSError as e:
            log_error("writing a picture to send")
            self.say("Not sent: %s" % e)
            return
        done = lambda ok, msg: self.say(msg)
        mod = mirror_module()
        if m.calc.slug == "nspire":
            tns, error = mod.prepare_for_nspire(path)
            if error:
                self.say(error)
                return
            self.say("Sending %s.tns..." % res.var)
            m.send_nspire_files([(tns, "/")], lambda ok, msg: self.say(
                msg + (". Run it: My Documents > %s, then ctrl+R" % res.var if ok else "")))
            return
        import send_ti
        try:
            wanted = send_ti.variables(res.blob, m.calc.slug)
        except ValueError as e:
            self.say("Not sent: %s" % e)
            return
        self.say("Sending %s..." % res.var)
        send_ti.send_prepared(m, [(path, wanted)], lambda ok, msg: self.say(
            ("Sent %s. %s" % (res.var, res.info.split(". ", 1)[1])) if ok else msg))

    def close(self):
        """Close: stop, let the picture go, then the host's on_close"""
        self.shutdown()
        if self.on_close is not None:
            self.on_close()

    def shutdown(self):
        if self.job is not None:
            try:
                self.after_cancel(self.job)
            except tk.TclError:
                pass
            self.job = None
        if self.source is not None:
            self.source.close()
            self.source = None


class PictureWindow(object):
    """A thin window around a PicturePanel (until the panel gets its own tab)"""

    def __init__(self, root, mirror=None, kit=None, slug=None, path=None):
        slug = slug or (mirror.calc.slug if mirror is not None else "ti84")
        win = self.win = tk.Toplevel(root)
        win.title("Make a picture for the %s" % TITLES[slug])
        win.configure(bg=th.BG)
        win.minsize(900, 560)
        th.dark_title_bar_when_shown(win)
        self.panel = PicturePanel(win, mirror, kit, slug, path, on_close=self.destroy)
        self.panel.pack(fill="both", expand=True)
        win.bind("<Escape>", lambda e: self.panel.close())
        win.protocol("WM_DELETE_WINDOW", self.panel.close)
        self.panel.focus_set()

    def destroy(self):
        try:
            self.win.destroy()
        except tk.TclError:
            pass


def mirror_module():
    return sys.modules.get("mirror") or __import__("mirror")


def out_folder(kit, *parts):
    try:
        import paths
        return paths.user_path(*parts)
    except Exception:
        path = os.path.join(kit or os.path.expanduser("~"), *parts)
        os.makedirs(path, exist_ok=True)
        return path


def log_error(where):
    """mirror.log_error (CalcSuite files\\logs\\errors.log): never raises"""
    try:
        mirror_module().log_error(where)
    except Exception:
        pass


def open_for(mirror, kit):
    """The Files panel's "Make a picture..." (one per calculator, shown again): a tab of the
    main window (tool_tabs), else a window of its own"""
    import tool_tabs
    app = tool_tabs.app()
    if app is not None and hasattr(app, "open_tool_tab"):
        key = "picture:%s" % mirror.calc.slug
        return app.open_tool_tab(key, "Make a picture (%s)" % mirror.calc.title,
                                 lambda parent: PicturePanel(parent, mirror, kit,
                                                             on_close=lambda: app.drop_tool_tab(key)))
    win = getattr(mirror, "picture_window", None)
    try:
        if win is not None and win.win.winfo_exists():
            win.win.deiconify()
            win.win.lift()
            return win
    except tk.TclError:
        pass
    mirror.picture_window = PictureWindow(mirror.root, mirror, kit)
    return mirror.picture_window


if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    w = PictureWindow(root, path=sys.argv[1] if len(sys.argv) > 1 else None)
    w.win.bind("<Destroy>", lambda e: root.destroy() if e.widget is w.win else None)
    root.mainloop()
