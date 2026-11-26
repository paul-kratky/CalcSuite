"""PC stand-in for the TI-Nspire ti_image module.

new_image() and copy_image() work (pixels kept in memory). load_image() cannot reach images
inside a .tns document, so it returns a 100x100 gray placeholder and says so on stderr.
show_image() draws the image when run_on_pc.py --gui is used (slow for big images).
"""

import sys

import _ti_screen as S


class _Image:
    def __init__(self, w, h, color=(255, 255, 255), name=""):
        self.w = int(w)
        self.h = int(h)
        self.name = name
        self._px = [tuple(color)] * (self.w * self.h)

    def get_pixel(self, x, y):
        return self._px[int(y) * self.w + int(x)]

    def set_pixel(self, x, y, color):
        self._px[int(y) * self.w + int(x)] = tuple(color)

    def show_image(self, x, y):
        S.log("ti_image", "show_image", (x, y))
        c = S.canvas()
        if not c:
            return
        import tkinter
        img = tkinter.PhotoImage(width=self.w, height=self.h)
        rows = []
        for yy in range(self.h):
            row = self._px[yy * self.w:(yy + 1) * self.w]
            rows.append("{" + " ".join(S.rgb(p) for p in row) + "}")
        img.put(" ".join(rows))
        if S.SCALE > 1:
            img = img.zoom(S.SCALE)
        c.create_image(x * S.SCALE, y * S.SCALE, image=img, anchor="nw")
        c._keep = getattr(c, "_keep", []) + [img]


def new_image(w, h, color=(255, 255, 255)):
    S.log("ti_image", "new_image", (w, h, color))
    return _Image(w, h, color)


def load_image(name):
    S.log("ti_image", "load_image", (name,))
    print("[ti_image shim] load_image('%s'): images live inside the .tns document; "
          "using a 100x100 gray placeholder." % name, file=sys.stderr)
    return _Image(100, 100, (128, 128, 128), name)


def copy_image(image):
    S.log("ti_image", "copy_image")
    out = _Image(image.w, image.h, name=image.name)
    out._px = list(image._px)
    return out
