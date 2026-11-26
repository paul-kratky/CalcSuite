# ti_draw demo: axes, a sine wave and a sun on the 318x212 canvas.
# Press a key (or esc) to finish.
from ti_draw import *
from ti_system import get_key
from math import sin, pi

w, h = get_screen_dim()        # 318, 212 on the handheld
mid = h // 2

use_buffer()                   # draw off-screen, then show at once
clear()

# Axes
set_color(150, 150, 150)
set_pen("thin", "dotted")
draw_line(0, mid, w, mid)
draw_line(10, 0, 10, h)

# One period of sin(x) from x = 0 to 2*pi, built from short line segments
set_color(0, 90, 200)
set_pen("medium", "solid")
amp = 60
steps = 60
px = 10
py = mid
for i in range(1, steps + 1):
    x = 10 + i * (w - 20) // steps
    y = mid - int(amp * sin(2 * pi * i / steps))
    draw_line(px, py, x, y)
    px = x
    py = y

# A sun in the corner
set_color(255, 190, 0)
fill_circle(w - 30, 30, 16)

set_color(0, 0, 0)
draw_text(14, 20, "y = sin(x)")
draw_text(14, h - 6, "Press any key")
paint_buffer()

get_key(1)                     # wait for a key so the picture stays up
