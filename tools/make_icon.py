"""Draws the app icon (a monitor with an orange calculator in front) into assets/.

    python -I tools/make_icon.py      (needs Pillow; only for whoever changes the icon)

Writes assets/app.ico (16 to 256 px, each size drawn on its own so small ones stay sharp) and
assets/app.png (256 px, the window's icon). Drawn on a 128-unit grid, like the design canvas.
"""

import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "assets")

TILE = (17, 22, 28, 255)       # #11161c
MONITOR = (90, 102, 117, 255)  # #5a6675
CALC = (255, 122, 61, 255)     # #ff7a3d
SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)
SS = 8                         # Supersampling


def draw(size):
    big = size * SS
    k = big / 128.0
    im = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)

    def box(x, y, w, h):
        return [x * k, y * k, (x + w) * k, (y + h) * k]

    d.rounded_rectangle(box(6, 6, 116, 116), radius=(22 if size <= 20 else 26) * k, fill=TILE)
    stroke = 6 if size >= 48 else 8 if size >= 24 else 12
    d.rounded_rectangle(box(18, 24, 66, 48), radius=6 * k, outline=MONITOR, width=max(1, round(stroke * k)))
    d.rounded_rectangle(box(60, 42, 48, 70), radius=9 * k, fill=CALC)
    if size >= 24:
        d.rounded_rectangle(box(67, 50, 34, 22), radius=3 * k, fill=TILE)  # Its screen
    if size >= 48:
        for cy in (84, 97):
            for cx in (74, 84, 94):
                r = 3.5 * k
                d.ellipse([cx * k - r, cy * k - r, cx * k + r, cy * k + r], fill=TILE)
    return im.resize((size, size), Image.LANCZOS)


def main():
    os.makedirs(OUT, exist_ok=True)
    images = [draw(s) for s in SIZES]
    images[-1].save(os.path.join(OUT, "app.png"))
    images[-1].save(os.path.join(OUT, "app.ico"), sizes=[(s, s) for s in SIZES],
                    append_images=images[:-1])
    print("wrote", os.path.join(OUT, "app.ico"), "and app.png")


if __name__ == "__main__":
    main()
