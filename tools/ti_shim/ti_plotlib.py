"""PC stand-in for the TI-Nspire ti_plotlib module (usually: import ti_plotlib as plt).

Logs every call; with run_on_pc.py --gui it also draws into the shared 318x212 canvas.
The default window here is -10..10 on both axes; always call plt.window(...) yourself.
lin_reg() really computes the slope/intercept and stores them in plt.m / plt.a and plt.b.
"""

import _ti_screen as S

xmin, xmax, ymin, ymax = -10.0, 10.0, -10.0, 10.0
m = a = b = 0.0
_color = (0, 0, 0)
_width = 1
_dash = ()
_ROWS = 12

_PEN_SIZES = {"thin": 1, "medium": 2, "thick": 3}
_PEN_STYLES = {"solid": (), "dot": (1, 3), "dotted": (1, 3), "dash": (5, 3), "dashed": (5, 3)}


def _px(x, y):
    return ((x - xmin) * S.W / (xmax - xmin) * S.SCALE,
            (ymax - y) * S.H / (ymax - ymin) * S.SCALE)


def _opts():
    o = {"fill": S.rgb(_color), "width": _width * S.SCALE}
    if _dash:
        o["dash"] = _dash
    return o


def cls():
    S.log("ti_plotlib", "cls")
    c = S.canvas()
    if c:
        c.delete("all")


def window(x0, x1, y0, y1):
    global xmin, xmax, ymin, ymax
    S.log("ti_plotlib", "window", (x0, x1, y0, y1))
    xmin, xmax, ymin, ymax = float(x0), float(x1), float(y0), float(y1)


def auto_window(xs, ys):
    S.log("ti_plotlib", "auto_window", (xs, ys))
    dx = (max(xs) - min(xs)) or 1.0
    dy = (max(ys) - min(ys)) or 1.0
    window(min(xs) - 0.1 * dx, max(xs) + 0.1 * dx, min(ys) - 0.1 * dy, max(ys) + 0.1 * dy)


def grid(xscale=1, yscale=1, style="dot"):
    S.log("ti_plotlib", "grid", (xscale, yscale, style))
    c = S.canvas()
    if not c:
        return
    import math
    x = math.ceil(xmin / xscale) * xscale
    while x <= xmax:
        c.create_line(*_px(x, ymin), *_px(x, ymax), fill="#cccccc", dash=(1, 3))
        x += xscale
    y = math.ceil(ymin / yscale) * yscale
    while y <= ymax:
        c.create_line(*_px(xmin, y), *_px(xmax, y), fill="#cccccc", dash=(1, 3))
        y += yscale


def axes(mode="axes"):
    S.log("ti_plotlib", "axes", (mode,))
    c = S.canvas()
    if c and mode != "off":
        if xmin <= 0 <= xmax:
            c.create_line(*_px(0, ymin), *_px(0, ymax), fill="black")
        if ymin <= 0 <= ymax:
            c.create_line(*_px(xmin, 0), *_px(xmax, 0), fill="black")


def labels(xlabel="", ylabel="", x=12, y=2):
    S.log("ti_plotlib", "labels", (xlabel, ylabel, x, y))
    text_at(x, xlabel, "right")
    text_at(y, ylabel, "left")


def title(text):
    S.log("ti_plotlib", "title", (text,))
    c = S.canvas()
    if c:
        c.create_text(S.W * S.SCALE / 2, 2 * S.SCALE, text=text, anchor="n",
                      font=("Helvetica", 7 * S.SCALE))


def show_plot():
    S.log("ti_plotlib", "show_plot")
    S.update()


def use_buffer():
    S.log("ti_plotlib", "use_buffer")


def color(r, g=None, bb=None):
    global _color
    S.log("ti_plotlib", "color", (r, g, bb) if g is not None else (r,))
    _color = tuple(r) if g is None else (r, g, bb)


def pen(size="thin", style="solid"):
    global _width, _dash
    S.log("ti_plotlib", "pen", (size, style))
    _width = _PEN_SIZES.get(size, 1)
    _dash = _PEN_STYLES.get(style, ())


def _mark(x, y, mark):
    c = S.canvas()
    if not c:
        return
    cx, cy = _px(x, y)
    r = 2 * S.SCALE
    if mark == "x":
        c.create_line(cx - r, cy - r, cx + r, cy + r, fill=S.rgb(_color))
        c.create_line(cx - r, cy + r, cx + r, cy - r, fill=S.rgb(_color))
    elif mark == "+":
        c.create_line(cx - r, cy, cx + r, cy, fill=S.rgb(_color))
        c.create_line(cx, cy - r, cx, cy + r, fill=S.rgb(_color))
    else:
        c.create_oval(cx - r, cy - r, cx + r, cy + r, outline=S.rgb(_color))


def scatter(xs, ys, mark="o"):
    S.log("ti_plotlib", "scatter", (xs, ys, mark))
    for x, y in zip(xs, ys):
        _mark(x, y, mark)


def plot(xs, ys, mark="o"):
    S.log("ti_plotlib", "plot", (xs, ys, mark))
    c = S.canvas()
    if isinstance(xs, (list, tuple)):
        if c:
            for i in range(1, min(len(xs), len(ys))):
                c.create_line(*_px(xs[i - 1], ys[i - 1]), *_px(xs[i], ys[i]), **_opts())
    else:
        _mark(xs, ys, mark)


def line(x1, y1, x2, y2, mode=""):
    S.log("ti_plotlib", "line", (x1, y1, x2, y2, mode))
    c = S.canvas()
    if c:
        o = _opts()
        if mode == "arrow":
            o["arrow"] = "last"
        c.create_line(*_px(x1, y1), *_px(x2, y2), **o)


def lin_reg(xs, ys, display="center", row=11):
    global m, a, b
    S.log("ti_plotlib", "lin_reg", (xs, ys, display, row))
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    m = a = sxy / sxx if sxx else 0.0
    b = my - m * mx
    line(xmin, m * xmin + b, xmax, m * xmax + b)
    text_at(row, "y=%.4gx+%.4g" % (m, b), display)


def text_at(row, text, align="left"):
    S.log("ti_plotlib", "text_at", (row, text, align))
    c = S.canvas()
    if c:
        y = (row - 0.5) * S.H / _ROWS * S.SCALE
        x, anchor = {"left": (2, "w"), "center": (S.W / 2, "center"),
                     "right": (S.W - 2, "e")}.get(align, (2, "w"))
        c.create_text(x * S.SCALE, y, text=str(text), anchor=anchor, fill=S.rgb(_color),
                      font=("Helvetica", 7 * S.SCALE))
