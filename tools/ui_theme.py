"""CalcSuite's look: one dark palette and hand-styled Tk widgets (no theme package needed)."""

import tkinter as tk
from tkinter import ttk

BG = "#000000"        # The window: true black
PANEL = "#0a0b0d"     # Panels
PANEL2 = "#111113"    # Buttons, raised things
LINE = "#1d1f24"      # Hairlines
FG = "#ece9e2"        # Text
DIM = "#8a929b"       # Secondary text
ACCENT = "#ff7a3d"    # The selected calculator / keyboard target
MINT = "#8ff0cf"      # OK states
RED = "#ff6a5e"       # Recording
GREY = "#4a4f57"      # Not plugged in
KEYCAP = "#1b1c20"
KEYCAP_EDGE = "#2c2e34"
ACTIVE = "#1c1d21"
FONT = "Segoe UI"
MONO = "Consolas"

BUTTON = dict(bg=PANEL2, fg=FG, activebackground=ACTIVE, activeforeground="#ffffff",
              relief="flat", padx=10, pady=5, bd=0, highlightthickness=0,
              disabledforeground="#55534e", takefocus=0, cursor="hand2")


def button(parent, text, command=None, **kw):
    opts = dict(BUTTON)
    opts.update(kw)
    return tk.Button(parent, text=text, command=command, **opts)


def check(parent, text, variable, command=None, bg=BG):
    return tk.Checkbutton(parent, text=text, variable=variable, command=command, bg=bg, fg=FG,
                          selectcolor=PANEL2, activebackground=bg, activeforeground="#ffffff",
                          highlightthickness=0, bd=0, takefocus=0, cursor="hand2")


def label(parent, text="", fg=FG, bg=BG, **kw):
    return tk.Label(parent, text=text, fg=fg, bg=bg, **kw)


def keycap(parent, text, bg=PANEL, accent=False):
    """A PC key drawn as a keycap"""
    return tk.Label(parent, text=text, bg=ACCENT if accent else KEYCAP,
                    fg="#000000" if accent else FG, font=(FONT, 9, "bold"), padx=7, pady=1,
                    highlightthickness=1, highlightbackground=KEYCAP_EDGE, bd=0)


def style_ttk(root):
    """ttk widgets (the file lists, scrollbars) in the same dark colours"""
    style = ttk.Style(root)
    try:
        style.theme_use("clam")  # The one theme whose colours can all be set
    except tk.TclError:
        pass
    style.configure("Calc.Treeview", background="#0b0b0c", fieldbackground="#0b0b0c",
                    foreground=FG, rowheight=22, borderwidth=0)
    style.map("Calc.Treeview", background=[("selected", "#2b2b33")],
              foreground=[("selected", "#ffffff")])
    style.configure("Calc.Treeview.Heading", background=PANEL2, foreground=FG, relief="flat")
    style.map("Calc.Treeview.Heading", background=[("active", ACTIVE)])
    for orient in ("Vertical", "Horizontal"):
        style.configure("Calc.%s.TScrollbar" % orient, background=PANEL2, troughcolor=BG,
                        arrowcolor=DIM, bordercolor=BG, lightcolor=PANEL2, darkcolor=PANEL2)
        style.map("Calc.%s.TScrollbar" % orient, background=[("active", ACTIVE)])
    return style


def menu(parent):
    return tk.Menu(parent, tearoff=0, bg=PANEL2, fg=FG, activebackground=ACCENT,
                   activeforeground="#000000", bd=0)
