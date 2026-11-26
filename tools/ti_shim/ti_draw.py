"""PC stand-in for the TI-Nspire ti_draw module.

Logs every call; with run_on_pc.py --gui it also draws into a 318x212 tkinter canvas.
Default coordinates match the calculator: (0,0) top left, y grows downward.
set_window(xmin, xmax, ymin, ymax) switches to math coordinates (y grows upward).
"""

import _ti_screen as S

_color = (0, 0, 0)
_width = 1
_dash = ()
_win = None   # (xmin, xmax, ymin, ymax) or None for pixels

_PEN_SIZES = {"thin": 1, "medium": 2, "thick": 3}
_PEN_STYLES = {"solid": (), "dotted": (1, 3), "dashed": (5, 3)}


def _px(x, y):
    if _win is not None:
        xmin, xmax, ymin, ymax = _win
        x = (x - xmin) * S.W / (xmax - xmin)
        y = (ymax - y) * S.H / (ymax - ymin)
    return x * S.SCALE, y * S.SCALE


def _len_x(d):
    if _win is not None:
        d = d * S.W / (_win[1] - _win[0])
    return abs(d) * S.SCALE


def _box(x, y, w, h):
    x1, y1 = _px(x, y)
    if _win is not None:   # math coords: (x,y) is a corner; h measured upward
        x2, y2 = _px(x + w, y + h)
    else:
        x2, y2 = x1 + w * S.SCALE, y1 + h * S.SCALE
    return min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)


def _line_opts():
    o = {"fill": S.rgb(_color), "width": _width * S.SCALE}
    if _dash:
        o["dash"] = _dash
    return o


def _outline_opts():
    o = {"outline": S.rgb(_color), "width": _width * S.SCALE}
    if _dash:
        o["dash"] = _dash
    return o


def draw_line(x1, y1, x2, y2):
    S.log("ti_draw", "draw_line", (x1, y1, x2, y2))
    c = S.canvas()
    if c:
        c.create_line(*_px(x1, y1), *_px(x2, y2), **_line_opts())


def draw_rect(x, y, w, h):
    S.log("ti_draw", "draw_rect", (x, y, w, h))
    c = S.canvas()
    if c:
        c.create_rectangle(*_box(x, y, w, h), **_outline_opts())


def fill_rect(x, y, w, h):
    S.log("ti_draw", "fill_rect", (x, y, w, h))
    c = S.canvas()
    if c:
        c.create_rectangle(*_box(x, y, w, h), fill=S.rgb(_color), outline="")


def _circle_box(x, y, r):
    cx, cy = _px(x, y)
    rr = _len_x(r)
    return cx - rr, cy - rr, cx + rr, cy + rr


def draw_circle(x, y, r):
    S.log("ti_draw", "draw_circle", (x, y, r))
    c = S.canvas()
    if c:
        c.create_oval(*_circle_box(x, y, r), **_outline_opts())


def fill_circle(x, y, r):
    S.log("ti_draw", "fill_circle", (x, y, r))
    c = S.canvas()
    if c:
        c.create_oval(*_circle_box(x, y, r), fill=S.rgb(_color), outline="")


def draw_text(x, y, *text):
    S.log("ti_draw", "draw_text", (x, y) + text)
    c = S.canvas()
    if c:
        c.create_text(*_px(x, y), text=" ".join(str(t) for t in text), anchor="sw",
                      fill=S.rgb(_color), font=("Helvetica", 7 * S.SCALE))


def draw_arc(x, y, w, h, start, extent):
    S.log("ti_draw", "draw_arc", (x, y, w, h, start, extent))
    c = S.canvas()
    if c:
        c.create_arc(*_box(x, y, w, h), start=start, extent=extent, style="arc",
                     **_outline_opts())


def fill_arc(x, y, w, h, start, extent):
    S.log("ti_draw", "fill_arc", (x, y, w, h, start, extent))
    c = S.canvas()
    if c:
        c.create_arc(*_box(x, y, w, h), start=start, extent=extent, style="pieslice",
                     fill=S.rgb(_color), outline="")


def _poly_points(xs, ys):
    pts = []
    for x, y in zip(xs, ys):
        pts.extend(_px(x, y))
    return pts


def draw_poly(xs, ys):
    S.log("ti_draw", "draw_poly", (xs, ys))
    c = S.canvas()
    if c and len(xs) > 1:
        pts = _poly_points(xs, ys)
        c.create_line(*(pts + pts[:2]), **_line_opts())


def fill_poly(xs, ys):
    S.log("ti_draw", "fill_poly", (xs, ys))
    c = S.canvas()
    if c and len(xs) > 2:
        c.create_polygon(*_poly_points(xs, ys), fill=S.rgb(_color), outline="")


def plot_xy(x, y, shape=1):
    S.log("ti_draw", "plot_xy", (x, y, shape))
    c = S.canvas()
    if c:
        cx, cy = _px(x, y)
        r = 2 * S.SCALE
        c.create_oval(cx - r, cy - r, cx + r, cy + r, outline=S.rgb(_color))


def clear(*rect):
    S.log("ti_draw", "clear", rect)
    c = S.canvas()
    if c:
        if len(rect) == 4:
            clear_rect(*rect)
        else:
            c.delete("all")


def clear_rect(x, y, w, h):
    S.log("ti_draw", "clear_rect", (x, y, w, h))
    c = S.canvas()
    if c:
        c.create_rectangle(*_box(x, y, w, h), fill="white", outline="")


def set_color(r, g=None, b=None):
    global _color
    S.log("ti_draw", "set_color", (r, g, b) if g is not None else (r,))
    _color = tuple(r) if g is None else (r, g, b)


def set_pen(size="thin", style="solid"):
    global _width, _dash
    S.log("ti_draw", "set_pen", (size, style))
    _width = _PEN_SIZES.get(size, 1)
    _dash = _PEN_STYLES.get(style, ())


def set_window(xmin, xmax, ymin, ymax):
    global _win
    S.log("ti_draw", "set_window", (xmin, xmax, ymin, ymax))
    _win = (xmin, xmax, ymin, ymax)


def get_screen_dim():
    return (S.W, S.H)


def use_buffer():
    S.log("ti_draw", "use_buffer")


def paint_buffer():
    S.log("ti_draw", "paint_buffer")
    S.update()
