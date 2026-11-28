"""Pictures for the calculators: fitting a PC picture to a calculator's screen, its colours
(palettes, dithering), and the calculator's own picture files. Pure Python, no window, no
link (tools/picture_window.py is the window, tools/picture_load.py reads PC pictures).

The formats (our own code; the references are MIT or public documentation):

- TI-84 Plus CE Image variable (.8ca, Image1-Image0, a graph background): type 0x1A, name
  0x3C n, version 0x0A, archived. Its data: a 2-byte size (22245, little endian), 0x81, then
  83 rows of 133 pixels (RGB565, little endian) stored bottom row first, each row followed by
  2 unused bytes. The calculator shows each pixel 2 x 2. Checked against TI Connect CE's own
  file (tivars_lib_cpp's testData/Image1.8ca: TH_Picture.cpp, MIT).
- TI-84 Plus CE Pic variable (.8ci, Pic1-Pic0): type 0x07, name 0x60 n, version 0x0A,
  archived. Its data: a 2-byte size (21945), then 165 rows of 266 pixels, 2 per byte (high
  nibble left). A nibble is a colour: 1-15 are BLUE..DARKGRAY (the calculator's colours
  10-24), 0 draws nothing (RecallPic leaves what's under it). The graph screen is 265 wide:
  the 266th column is written as a copy of the 265th. Checked against tivars_lib_cpp's
  testData/Pic1.8ci.
- TI-89 Titanium picture (.89i): type 0x10. Its data (big endian, the 68000's order): a
  2-byte size (what follows), rows, columns, the bitmap (8 pixels a byte, the high bit left,
  1 = black, each row padded to a byte), then PIC_TAG 0xDF (TIGCC / GCC4TI docs: vat.h,
  graph.h's BITMAP).
- TI-Nspire CX II: a Python program (ti_draw) that paints the picture from its own data,
  a palette and run lengths in a printable string (nspire_program below): TI's ti_image only
  loads pictures TI's own software put into a document, which our .tns writer can't make.
"""

import re
import struct

import calc_files as cf

# ---- A picture in memory: w x h pixels, 3 bytes (R, G, B) each ----


class Img(object):
    __slots__ = ("w", "h", "px")

    def __init__(self, w, h, px=None, fill=(255, 255, 255)):
        self.w, self.h = int(w), int(h)
        self.px = bytearray(px) if px is not None else bytearray(bytes(fill) * (self.w * self.h))
        if len(self.px) != 3 * self.w * self.h:
            raise ValueError("a %d x %d picture needs %d bytes, not %d"
                             % (self.w, self.h, 3 * self.w * self.h, len(self.px)))

    def get(self, x, y):
        i = 3 * (y * self.w + x)
        return tuple(self.px[i:i + 3])

    def ppm(self, zoom=1):
        """As PPM bytes (Tk's PhotoImage reads them), each pixel zoom x zoom"""
        if zoom <= 1:
            return b"P6 %d %d 255\n" % (self.w, self.h) + bytes(self.px)
        rows = []
        for y in range(self.h):
            row = self.px[3 * y * self.w:3 * (y + 1) * self.w]
            wide = b"".join(bytes(row[i:i + 3]) * zoom for i in range(0, len(row), 3))
            rows.append(wide * zoom)
        return b"P6 %d %d 255\n" % (self.w * zoom, self.h * zoom) + b"".join(rows)


# ---- Fitting a picture to a screen ----

FIT, FILL, STRETCH = "fit", "fill", "stretch"


def layout(sw, sh, tw, th, mode):
    """Where a sw x sh picture goes on a tw x th screen: (source x, y, w, h) as floats and
    (target x, y, w, h) as ints. fit: all of it, bars around; fill: the screen covered, the
    edges cut off evenly; stretch: both, out of proportion."""
    if sw <= 0 or sh <= 0 or tw <= 0 or th <= 0:
        raise ValueError("an empty picture")
    if mode == STRETCH:
        return (0.0, 0.0, float(sw), float(sh)), (0, 0, tw, th)
    if mode == FILL:
        scale = max(tw / float(sw), th / float(sh))
        cw, ch = tw / scale, th / scale
        return ((sw - cw) / 2.0, (sh - ch) / 2.0, cw, ch), (0, 0, tw, th)
    scale = min(tw / float(sw), th / float(sh))
    dw = max(1, min(tw, int(round(sw * scale))))
    dh = max(1, min(th, int(round(sh * scale))))
    return (0.0, 0.0, float(sw), float(sh)), ((tw - dw) // 2, (th - dh) // 2, dw, dh)


def _spans(start, length, n):
    """n target cells over [start, start + length) of the source: [(first, last + 1)]"""
    out = []
    for k in range(n):
        a = start + length * k / n
        b = start + length * (k + 1) / n
        i0 = int(a)
        i1 = max(i0 + 1, int(b + 0.999999))
        out.append((i0, i1))
    return out


def resample(src, tw, th, mode=FIT, bg=(255, 255, 255)):
    """src (an Img) onto a tw x th Img: each target pixel the average of the source pixels it
    covers (the nearest one when enlarging). Pure Python: picture_load uses Windows' own
    scaling when it can, this is the fallback (and what the self-test checks)."""
    (sx, sy, sw, sh), (dx, dy, dw, dh) = layout(src.w, src.h, tw, th, mode)
    out = Img(tw, th, fill=bg)
    xs = [(max(0, min(a, src.w - 1)), max(1, min(b, src.w))) for a, b in _spans(sx, sw, dw)]
    ys = [(max(0, min(a, src.h - 1)), max(1, min(b, src.h))) for a, b in _spans(sy, sh, dh)]
    sp, op, W = src.px, out.px, src.w
    for j, (y0, y1) in enumerate(ys):
        o = 3 * ((dy + j) * tw + dx)
        for (x0, x1) in xs:
            r = g = b = 0
            for yy in range(y0, y1):
                base = 3 * (yy * W)
                for i in range(base + 3 * x0, base + 3 * x1, 3):
                    r += sp[i]
                    g += sp[i + 1]
                    b += sp[i + 2]
            n = (y1 - y0) * (x1 - x0)
            op[o] = (r + n // 2) // n
            op[o + 1] = (g + n // 2) // n
            op[o + 2] = (b + n // 2) // n
            o += 3
    return out


def adjust(img, brightness=0, contrast=0):
    """Brightness and contrast, each -100..100 (0: as it is), as a new Img"""
    if not brightness and not contrast:
        return Img(img.w, img.h, img.px)
    c = (100.0 + contrast) / 100.0 if contrast <= 0 else 100.0 / max(1.0, 100.0 - contrast * 0.95)
    lut = bytes(max(0, min(255, int(round((v - 128) * c + 128 + brightness * 1.28)))) for v in range(256))
    return Img(img.w, img.h, bytes(img.px).translate(lut))


def grey(img):
    """Each pixel its brightness (Rec. 601), as an Img"""
    p = img.px
    out = bytearray(len(p))
    for i in range(0, len(p), 3):
        v = (299 * p[i] + 587 * p[i + 1] + 114 * p[i + 2] + 500) // 1000
        out[i] = out[i + 1] = out[i + 2] = v
    return Img(img.w, img.h, out)


# ---- Colours: palettes and dithering ----

# The TI-84 Plus CE's 15 colours (BLUE..DARKGRAY, colour numbers 10-24), as the calculator's
# RGB565 values come out in 8-bit RGB. A Pic's nibble n is the colour CE_PALETTE[n - 1].
CE_NAMES = ("BLUE", "RED", "BLACK", "MAGENTA", "GREEN", "ORANGE", "BROWN", "NAVY", "LTBLUE",
            "YELLOW", "WHITE", "LTGRAY", "MEDGRAY", "GRAY", "DARKGRAY")
CE_PALETTE = ((0, 0, 255), (255, 0, 0), (0, 0, 0), (255, 0, 255), (0, 158, 0), (255, 142, 32),
              (182, 32, 0), (0, 0, 134), (0, 146, 255), (255, 255, 0), (255, 255, 255),
              (231, 227, 231), (199, 195, 199), (142, 138, 142), (81, 85, 81))
MONO = ((255, 255, 255), (0, 0, 0))

NONE, DIFFUSE, PATTERN = "none", "diffuse", "pattern"
_BAYER = (0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5)  # 4 x 4, 0..15


class Nearest(object):
    """The palette's nearest colour to (r, g, b), weighted for the eye, remembered"""

    def __init__(self, palette):
        self.pal = [tuple(int(v) for v in c) for c in palette]
        if not self.pal:
            raise ValueError("an empty palette")
        self.memo = {}

    def __call__(self, r, g, b):
        key = (r << 16) | (g << 8) | b
        k = self.memo.get(key)
        if k is None:
            best = None
            for n, (pr, pg, pb) in enumerate(self.pal):
                rm = (r + pr) >> 1
                d = ((512 + rm) * (r - pr) ** 2 >> 8) + 4 * (g - pg) ** 2 + \
                    ((767 - rm) * (b - pb) ** 2 >> 8)
                if best is None or d < best:
                    best, k = d, n
            self.memo[key] = k
        return k


def quantize(img, palette, dither=DIFFUSE, spread=None):
    """img -> [palette index] (row by row). dither: diffuse (Floyd-Steinberg, serpentine),
    pattern (a 4 x 4 Bayer pattern of `spread` levels around each colour), none."""
    near = Nearest(palette)
    pal, w, h, p = near.pal, img.w, img.h, img.px
    out = [0] * (w * h)
    if dither == PATTERN:
        if spread is None:
            spread = 255.0 if len(pal) <= 2 else 255.0 / max(1.5, len(pal) ** (1 / 3.0))
        offs = [(v + 0.5) / 16.0 - 0.5 for v in _BAYER]
        for y in range(h):
            row = 4 * (y & 3)
            for x in range(w):
                i = 3 * (y * w + x)
                o = offs[row + (x & 3)] * spread
                out[y * w + x] = near(_c(p[i] + o), _c(p[i + 1] + o), _c(p[i + 2] + o))
        return out
    if dither != DIFFUSE:
        for k in range(w * h):
            out[k] = near(p[3 * k], p[3 * k + 1], p[3 * k + 2])
        return out
    err = [0.0] * (3 * (w + 2))
    nxt = [0.0] * (3 * (w + 2))
    for y in range(h):
        left = (y & 1) == 0
        xs = range(w) if left else range(w - 1, -1, -1)
        d = 1 if left else -1
        for x in xs:
            i, e = 3 * (y * w + x), 3 * (x + 1)
            r = _c(p[i] + err[e])
            g = _c(p[i + 1] + err[e + 1])
            b = _c(p[i + 2] + err[e + 2])
            k = near(r, g, b)
            out[y * w + x] = k
            pr, pg, pb = pal[k]
            for c, q in ((0, r - pr), (1, g - pg), (2, b - pb)):
                if q:
                    err[e + 3 * d + c] += q * 0.4375
                    nxt[e - 3 * d + c] += q * 0.1875
                    nxt[e + c] += q * 0.3125
                    nxt[e + 3 * d + c] += q * 0.0625
        err, nxt = nxt, [0.0] * (3 * (w + 2))
    return out


def _c(v):
    v = int(v + 0.5) if v >= 0 else 0
    return 255 if v > 255 else v


def to_565(img, dither=NONE):
    """img -> [RGB565 value] (row by row), dithered between the 32/64/32 levels or rounded"""
    w, h, p = img.w, img.h, img.px
    out = [0] * (w * h)
    lv = (31, 63, 31)

    def q(v, c):
        n = int(v * lv[c] / 255.0 + 0.5)
        n = 0 if n < 0 else (lv[c] if n > lv[c] else n)
        return n, n * 255.0 / lv[c]
    err = [0.0] * (3 * (w + 2))
    nxt = [0.0] * (3 * (w + 2))
    for y in range(h):
        for x in range(w):
            i, e = 3 * (y * w + x), 3 * (x + 1)
            ns = []
            for c in range(3):
                v = p[i + c]
                if dither == PATTERN:
                    v += ((_BAYER[4 * (y & 3) + (x & 3)] + 0.5) / 16.0 - 0.5) * 255.0 / lv[c]
                elif dither == DIFFUSE:
                    v += err[e + c]
                n, back = q(v, c)
                ns.append(n)
                if dither == DIFFUSE:
                    d = v - back
                    err[e + 3 + c] += d * 0.4375
                    nxt[e - 3 + c] += d * 0.1875
                    nxt[e + c] += d * 0.3125
                    nxt[e + 3 + c] += d * 0.0625
            out[y * w + x] = (ns[0] << 11) | (ns[1] << 5) | ns[2]
        if dither == DIFFUSE:
            err, nxt = nxt, [0.0] * (3 * (w + 2))
    return out


def rgb565(v):
    """An RGB565 value as 8-bit (R, G, B)"""
    return ((v >> 11) * 255 // 31, ((v >> 5) & 63) * 255 // 63, (v & 31) * 255 // 31)


def median_cut(img, n):
    """A palette of up to n colours for img: boxes of its colours split at the median of their
    widest channel, each box's average"""
    p = img.px
    counts = {}
    for i in range(0, len(p), 3):
        key = (p[i] << 16) | (p[i + 1] << 8) | p[i + 2]
        counts[key] = counts.get(key, 0) + 1
    cols = [((k >> 16) & 255, (k >> 8) & 255, k & 255, c) for k, c in counts.items()]
    if len(cols) <= n:
        return [c[:3] for c in sorted(cols, key=lambda c: -c[3])]
    boxes = [cols]
    while len(boxes) < n:
        best, axis, widest = None, 0, -1
        for bi, box in enumerate(boxes):
            if len(box) < 2:
                continue
            for a in range(3):
                vals = [c[a] for c in box]
                span = (max(vals) - min(vals)) * (1 + len(box) ** 0.5 / 64.0)
                if span > widest:
                    best, axis, widest = bi, a, span
        if best is None or widest <= 0:
            break
        box = sorted(boxes.pop(best), key=lambda c: c[axis])
        total = sum(c[3] for c in box)
        run, cut = 0, 1
        for k, c in enumerate(box):
            run += c[3]
            if run * 2 >= total:
                cut = max(1, min(len(box) - 1, k + 1))
                break
        boxes += [box[:cut], box[cut:]]
    pal = []
    for box in boxes:
        t = sum(c[3] for c in box)
        pal.append(tuple((sum(c[a] * c[3] for c in box) + t // 2) // t for a in range(3)))
    return pal


def paint(w, h, indices, palette):
    """Palette indices back into an Img (the preview)"""
    lut = [bytes(c) for c in palette]
    return Img(w, h, b"".join(lut[k] for k in indices))


# ---- TI-84 Plus CE: Image (.8ca) and Pic (.8ci) ----

CE_IMAGE_W, CE_IMAGE_H = 133, 83
CE_PIC_W, CE_PIC_H = 265, 165       # What the screen shows (266 stored)
CE_PIC_STORED_W = 266
IMAGE_TYPE, PIC_TYPE_84, VERSION_CE_COLOUR = 0x1A, 0x07, 0x0A
IMAGE_SIZE = 1 + CE_IMAGE_H * (2 * CE_IMAGE_W + 2)     # 22245
PIC_SIZE_84 = CE_PIC_H * CE_PIC_STORED_W // 2          # 21945


def name_digit(name, word):
    """"Pic1".."Pic0" (or "Image1"..) -> the digit 1..9, 0. Raises ValueError."""
    m = re.match(r"^%s([0-9])$" % word, (name or "").strip(), re.I)
    if not m:
        raise ValueError("%s must be %s1 to %s9 or %s0" % (word, word, word, word))
    return int(m.group(1))


def ce_image_data(values):
    """133 x 83 RGB565 values (row by row, top first) -> the Image variable's data"""
    if len(values) != CE_IMAGE_W * CE_IMAGE_H:
        raise ValueError("an Image is %d x %d" % (CE_IMAGE_W, CE_IMAGE_H))
    rows = []
    for y in range(CE_IMAGE_H - 1, -1, -1):
        row = values[y * CE_IMAGE_W:(y + 1) * CE_IMAGE_W]
        rows.append(struct.pack("<%dH" % CE_IMAGE_W, *row) + b"\x00\x00")
    return struct.pack("<H", IMAGE_SIZE) + b"\x81" + b"".join(rows)


def ce_image_8ca(values, name="Image1", comment="Made by CalcSuite"):
    d = name_digit(name, "Image")
    return cf.ti8x_bytes([(IMAGE_TYPE, bytes((0x3C, cf._shift(d))), VERSION_CE_COLOUR, True,
                           ce_image_data(values))], comment)


def ce_pic_data(indices):
    """265 x 165 indices into CE_PALETTE (row by row) -> the Pic variable's data. An index
    of -1 is a pixel RecallPic leaves alone (nibble 0)."""
    if len(indices) != CE_PIC_W * CE_PIC_H:
        raise ValueError("a Pic is %d x %d" % (CE_PIC_W, CE_PIC_H))
    out = bytearray(struct.pack("<H", PIC_SIZE_84))
    for y in range(CE_PIC_H):
        row = [k + 1 for k in indices[y * CE_PIC_W:(y + 1) * CE_PIC_W]]
        row.append(row[-1])  # The 266th column: a copy of the 265th
        for x in range(0, CE_PIC_STORED_W, 2):
            out.append(((row[x] & 15) << 4) | (row[x + 1] & 15))
    return bytes(out)


def ce_pic_8ci(indices, name="Pic1", comment="Made by CalcSuite"):
    d = name_digit(name, "Pic")
    return cf.ti8x_bytes([(PIC_TYPE_84, bytes((0x60, cf._shift(d))), VERSION_CE_COLOUR, True,
                           ce_pic_data(indices))], comment)


# ---- TI-89 Titanium: PIC (.89i) ----

PIC_TYPE_89, PIC_TAG = 0x10, 0xDF
SIZES_89 = ((159, 77, "Graph screen"), (160, 100, "Whole screen"),
            (240, 128, "Voyage 200 / TI-92 size"))


def ti89_pic_data(bits, w, h):
    """w x h pixels (row by row, 1 = black) -> the PIC variable's data"""
    if len(bits) != w * h or not (1 <= w <= 240 and 1 <= h <= 128):
        raise ValueError("a TI-89 picture is up to 240 x 128")
    rb = (w + 7) // 8
    body = bytearray(struct.pack(">HH", h, w))
    for y in range(h):
        row = bytearray(rb)
        for x in range(w):
            if bits[y * w + x]:
                row[x >> 3] |= 0x80 >> (x & 7)
        body += row
    body.append(PIC_TAG)
    return struct.pack(">H", len(body)) + bytes(body)


def ti89_pic_89i(bits, w, h, name="zzpic", folder="main", comment="Made by CalcSuite"):
    if not cf.NAME_89.match(name or ""):
        raise ValueError("a TI-89 name is up to 8 lower-case letters or digits, a letter first")
    return cf.ti89_bytes(PIC_TYPE_89, folder.encode("ascii"), name.encode("ascii"), False,
                         ti89_pic_data(bits, w, h), comment)


# ---- Reading them back (the self-test's round trip, the fuzz harness, opening a TI file) ----

def read_picture(blob):
    """A .8ca, .8ci or .89i file -> (kind, name, Img). Raises ValueError."""
    if blob[:8] == b"**TI83F*":
        for vtype, name, _v, _a, data in cf.read_ti8x(blob):
            if vtype == IMAGE_TYPE:
                return "Image", cf.detokenize_name_84(name, vtype), decode_ce_image(data)
            if vtype == PIC_TYPE_84:
                return "Pic", cf.detokenize_name_84(name, vtype), decode_ce_pic(data)
        raise ValueError("no picture in the file")
    for _folder, name, vtype, _a, data in cf.read_ti89(blob):
        if vtype == PIC_TYPE_89:
            return "PIC", name.decode("latin-1"), decode_89_pic(data)
    raise ValueError("no picture in the file")


def decode_ce_image(data):
    if len(data) != 2 + IMAGE_SIZE or data[2] != 0x81 or struct.unpack_from("<H", data)[0] != IMAGE_SIZE:
        raise ValueError("not a TI-84 Plus CE Image")
    out = Img(CE_IMAGE_W, CE_IMAGE_H)
    stride = 2 * CE_IMAGE_W + 2
    for r in range(CE_IMAGE_H):
        y = CE_IMAGE_H - 1 - r
        vals = struct.unpack_from("<%dH" % CE_IMAGE_W, data, 3 + r * stride)
        out.px[3 * y * CE_IMAGE_W:3 * (y + 1) * CE_IMAGE_W] = b"".join(bytes(rgb565(v)) for v in vals)
    return out


def decode_ce_pic(data):
    if len(data) != 2 + PIC_SIZE_84 or struct.unpack_from("<H", data)[0] != PIC_SIZE_84:
        raise ValueError("not a TI-84 Plus CE Pic")
    pal = [(255, 255, 255)] + list(CE_PALETTE)  # Nibble 0 (nothing drawn) shows as white
    out = bytearray()
    for y in range(CE_PIC_H):
        row = data[2 + y * 133:2 + (y + 1) * 133]
        nib = []
        for b in row:
            nib += (b >> 4, b & 15)
        out += b"".join(bytes(pal[n]) for n in nib[:CE_PIC_W])
    return Img(CE_PIC_W, CE_PIC_H, out)


def ce_pic_indices(data):
    """A Pic's data -> its 265 x 165 indices into CE_PALETTE (-1 for nibble 0)"""
    img = []
    for y in range(CE_PIC_H):
        for b in data[2 + y * 133:2 + y * 133 + 133]:
            img += ((b >> 4) - 1, (b & 15) - 1)
        img.pop()
    return img


def decode_89_pic(data):
    if len(data) < 7:
        raise ValueError("not a TI-89 picture")
    size, h, w = struct.unpack_from(">HHH", data)
    rb = (w + 7) // 8
    if not (1 <= w <= 240 and 1 <= h <= 128) or size != 4 + rb * h + 1 or len(data) != size + 2 \
            or data[-1] != PIC_TAG:
        raise ValueError("not a TI-89 picture")
    out = bytearray()
    for y in range(h):
        row = data[6 + y * rb:6 + (y + 1) * rb]
        for x in range(w):
            out += b"\x00\x00\x00" if row[x >> 3] & (0x80 >> (x & 7)) else b"\xff\xff\xff"
    return Img(w, h, out)


# ---- TI-Nspire CX II: a Python program that paints the picture ----

NSPIRE_W, NSPIRE_H = 318, 212
NSPIRE_BUDGET = 20 * 1024     # The kit's size for a handheld program (check_nspire warns above)
NSPIRE_SCALES = (1, 2, 3, 4, 6)
ALPHABET = "".join(chr(c) for c in range(35, 127) if c != 92)  # 91 symbols, no " or \
_SYM = {c: k for k, c in enumerate(ALPHABET)}
B = len(ALPHABET)


def nspire_grid(scale):
    """The picture's size in cells when each is scale x scale pixels, and where it starts"""
    w, h = NSPIRE_W // scale, NSPIRE_H // scale
    return w, h, (NSPIRE_W - w * scale) // 2, (NSPIRE_H - h * scale) // 2


def encode_runs(indices, w, ncol):
    """Palette indices (rows of w) -> the run string. A symbol below ncol * R is one run
    (colour = s % ncol, length = s // ncol + 1); any other symbol starts a long run: the next
    symbol is the colour, the one after it the length - R - 1."""
    if not 1 <= ncol <= 64:
        raise ValueError("1 to 64 colours")
    R = (B - 1) // ncol
    out = []
    for y in range(len(indices) // w):
        row = indices[y * w:(y + 1) * w]
        x = 0
        while x < w:
            c, n = row[x], 1
            while x + n < w and row[x + n] == c:
                n += 1
            x += n
            while n > 0:
                if n <= R:
                    out.append(ALPHABET[(n - 1) * ncol + c])
                    n = 0
                else:
                    k = min(n, R + B)
                    out.append(ALPHABET[B - 1] + ALPHABET[c] + ALPHABET[k - R - 1])
                    n -= k
    return "".join(out)


def decode_runs(data, w, h, ncol):
    """The reverse of encode_runs (the self-test's round trip). Raises ValueError."""
    R = (B - 1) // ncol
    out, i = [], 0
    try:
        while i < len(data):
            s = _SYM[data[i]]
            if s < ncol * R:
                c, n = s % ncol, s // ncol + 1
                i += 1
            else:
                c, n = _SYM[data[i + 1]], _SYM[data[i + 2]] + R + 1
                i += 3
            if c >= ncol:
                raise ValueError("a colour that isn't in the palette")
            out += [c] * n
    except (KeyError, IndexError):
        raise ValueError("damaged picture data")
    if len(out) != w * h:
        raise ValueError("the picture data is %d pixels, not %d" % (len(out), w * h))
    return out


NSPIRE_NAME = re.compile(r"^[a-z][a-z0-9_]{0,15}$")

_PROGRAM = '''# %(name)s: a picture made by CalcSuite (%(w)d x %(h)d cells of %(s)d x %(s)d pixels)
# Run it: ctrl+R. Any key ends it.
from ti_draw import *
from ti_system import get_key

W = %(w)d
H = %(h)d
S = %(s)d
X0 = %(x0)d
Y0 = %(y0)d
N = %(n)d
R = %(r)d
BG = %(bg)d
P = (%(pal)s)
D = (%(data)s)


def v(c):
    k = ord(c) - 35
    if k > 57:
        k -= 1
    return k


def draw():
    use_buffer()
    c = P[BG]
    set_color(c[0], c[1], c[2])
    fill_rect(0, 0, 318, 212)
    cur = BG
    NR = N * R
    i = 0
    x = 0
    y = 0
    k = len(D)
    while i < k:
        s = v(D[i])
        if s < NR:
            col = s %% N
            run = s // N + 1
            i += 1
        else:
            col = v(D[i + 1])
            run = v(D[i + 2]) + R + 1
            i += 3
        if col != BG:
            if col != cur:
                c = P[col]
                set_color(c[0], c[1], c[2])
                cur = col
            fill_rect(X0 + x * S, Y0 + y * S, run * S, S)
        x += run
        if x >= W:
            x = 0
            y += 1
    paint_buffer()


draw()
get_key(1)
'''


def nspire_program(indices, palette, scale, name="zzpic"):
    """Palette indices (nspire_grid(scale) cells, row by row) -> the program's text"""
    if not NSPIRE_NAME.match(name or ""):
        raise ValueError("a program name is lower-case letters, digits and _, a letter first")
    w, h, x0, y0 = nspire_grid(scale)
    if len(indices) != w * h:
        raise ValueError("the picture is %d x %d cells at this size" % (w, h))
    n = len(palette)
    counts = [0] * n
    for k in indices:
        counts[k] += 1
    bg = counts.index(max(counts))
    data = encode_runs(indices, w, n)
    lines = ['"%s"' % data[i:i + 100] for i in range(0, len(data), 100)] or ['""']
    pal = []
    for k in range(0, n, 6):
        pal.append(", ".join("(%d, %d, %d)" % tuple(c) for c in palette[k:k + 6]))
    return _PROGRAM % dict(name=name, w=w, h=h, s=scale, x0=x0, y0=y0, n=n, r=(B - 1) // n,
                           bg=bg, pal=",\n     ".join(pal) + ("," if n == 1 else ""),
                           data="\n     ".join(lines))


def nspire_program_size(indices, w, ncol):
    """About how many bytes the program will be (for picking a size)"""
    data = encode_runs(indices, w, ncol)
    return len(data) + len(data) // 100 * 8 + 1300 + ncol * 16


def png_bytes(img):
    """An Img as a PNG file (the self-test's pictures, previews saved for a look)"""
    import zlib

    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + bytes(img.px[3 * y * img.w:3 * (y + 1) * img.w]) for y in range(img.h))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", img.w, img.h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))
