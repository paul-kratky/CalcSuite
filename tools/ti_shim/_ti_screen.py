"""Shared screen for the PC shim of ti_draw / ti_plotlib / ti_image.

By default every graphics call is only logged (to stderr). With GUI on (run_on_pc.py --gui)
the calls also draw into a tkinter window the size of the calculator's canvas (318 x 212),
scaled up so it is easy to see.
"""

import os
import sys

W, H = 318, 212          # TI-Nspire CX II Python canvas (ti_draw.get_screen_dim())
SCALE = 2                # PC window zoom
GUI = os.environ.get("TI_SHIM_GUI") == "1"
QUIET = os.environ.get("TI_SHIM_QUIET") == "1"

_root = None
_canvas = None


def log(module, name, args=(), kwargs=None):
    if QUIET:
        return
    parts = [repr(a) for a in args]
    if kwargs:
        parts += ["%s=%r" % kv for kv in kwargs.items()]
    text = ", ".join(parts)
    if len(text) > 120:
        text = text[:117] + "..."
    print("[%s] %s(%s)" % (module, name, text), file=sys.stderr)


def canvas():
    """The tkinter canvas, or None when GUI is off."""
    global _root, _canvas
    if not GUI:
        return None
    if _canvas is None:
        import tkinter
        _root = tkinter.Tk()
        _root.title("TI-Nspire canvas (PC shim) %dx%d" % (W, H))
        _canvas = tkinter.Canvas(_root, width=W * SCALE, height=H * SCALE, bg="white",
                                 highlightthickness=0)
        _canvas.pack()
    return _canvas


def rgb(c):
    r, g, b = (max(0, min(255, int(v))) for v in c)
    return "#%02x%02x%02x" % (r, g, b)


def update():
    if _root is not None:
        _root.update()


def mainloop():
    if _root is not None:
        print("[shim] Program finished. Close the canvas window to exit.", file=sys.stderr)
        _root.mainloop()
