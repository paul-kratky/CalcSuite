"""The key-press strip burnt into recordings: the last keys as keycaps under the picture.

    burn = Burner(lambda: ["2nd", "MATH", "9"])   # who to ask for the keys, newest last
    w, h, rgb = burn(w, h, rgb)                   # in Recorder.transform

A frame narrower than 320 pixels (the TI-89's 160 x 100) is enlarged by a whole number first,
so the keycaps stay readable; then a strip is added underneath. Keycap labels are drawn with
Windows' own font renderer (GDI, no smoothing, so the GIF keeps few colours); without it the
keycaps are drawn empty. compose() is pure (tools/selftest checks it).
"""

STRIP_H = 22
CAP_H = 16
MAX_KEYS = 8
BG = (10, 11, 13)
CAP = (38, 39, 44)
CAP_TEXT = (236, 233, 226)
LAST = (255, 122, 61)
LAST_TEXT = (0, 0, 0)

_masks = {}


def text_mask(text, px=11):
    """(w, h, bytes 0/1 per pixel) of text drawn by Windows, or None elsewhere"""
    key = (text, px)
    if key in _masks:
        return _masks[key]
    mask = None
    try:
        mask = _gdi_text(text, px)
    except Exception:  # No GDI (not Windows), or it failed: keycaps without labels
        mask = None
    _masks[key] = mask
    return mask


def _gdi_text(text, px):
    import ctypes
    from ctypes import wintypes
    gdi = ctypes.WinDLL("gdi32")
    gdi.CreateFontW.restype = wintypes.HFONT
    gdi.CreateCompatibleDC.restype = wintypes.HDC
    gdi.SelectObject.restype = wintypes.HGDIOBJ
    gdi.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    gdi.CreateDIBSection.restype = wintypes.HBITMAP
    gdi.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.c_void_p, ctypes.c_uint,
                                     ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD]
    gdi.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    gdi.DeleteDC.argtypes = [wintypes.HDC]
    gdi.GetTextExtentPoint32W.argtypes = [wintypes.HDC, wintypes.LPCWSTR, ctypes.c_int,
                                          ctypes.POINTER(wintypes.SIZE)]
    gdi.TextOutW.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.LPCWSTR, ctypes.c_int]
    gdi.SetBkColor.argtypes = [wintypes.HDC, wintypes.COLORREF]
    gdi.SetTextColor.argtypes = [wintypes.HDC, wintypes.COLORREF]
    gdi.SetBkMode.argtypes = [wintypes.HDC, ctypes.c_int]
    dc = gdi.CreateCompatibleDC(None)
    font = gdi.CreateFontW(-px, 0, 0, 0, 700, 0, 0, 0, 1, 0, 0, 3, 0, "Segoe UI")  # NONANTIALIASED
    old_font = gdi.SelectObject(dc, font)
    size = wintypes.SIZE()
    gdi.GetTextExtentPoint32W(dc, text, len(text), ctypes.byref(size))
    w, h = max(1, size.cx), max(1, size.cy)

    class BMI(ctypes.Structure):
        _fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32),
                    ("biHeight", ctypes.c_int32), ("biPlanes", ctypes.c_uint16),
                    ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
                    ("biSizeImage", ctypes.c_uint32), ("x", ctypes.c_int32), ("y", ctypes.c_int32),
                    ("used", ctypes.c_uint32), ("important", ctypes.c_uint32),
                    ("colors", ctypes.c_uint32 * 3)]
    bmi = BMI()
    bmi.biSize, bmi.biWidth, bmi.biHeight = 40, w, -h  # Top-down
    bmi.biPlanes, bmi.biBitCount = 1, 32
    bits = ctypes.c_void_p()
    bmp = gdi.CreateDIBSection(dc, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
    old_bmp = gdi.SelectObject(dc, bmp)
    try:
        gdi.SetBkColor(dc, 0)
        gdi.SetTextColor(dc, 0xFFFFFF)
        gdi.SetBkMode(dc, 2)  # OPAQUE
        gdi.TextOutW(dc, 0, 0, text, len(text))
        gdi.GdiFlush()
        raw = ctypes.string_at(bits, w * h * 4)
    finally:
        gdi.SelectObject(dc, old_bmp)
        gdi.SelectObject(dc, old_font)
        gdi.DeleteObject(bmp)
        gdi.DeleteObject(font)
        gdi.DeleteDC(dc)
    mask = bytes(1 if raw[i * 4] > 127 else 0 for i in range(w * h))
    # Trim empty rows top and bottom (the font's leading)
    rows = [mask[y * w:(y + 1) * w] for y in range(h)]
    while len(rows) > 1 and not any(rows[0]):
        rows.pop(0)
    while len(rows) > 1 and not any(rows[-1]):
        rows.pop()
    return w, len(rows), b"".join(rows)


def compose(width, labels, mask_for=text_mask, height=STRIP_H):
    """The strip as RGB bytes (width x height): keycaps right-aligned, newest at the right in
    the accent colour; the oldest drop off the left when they don't fit"""
    px = bytearray(bytes(BG) * (width * height))

    def fill(x0, y0, x1, y1, c):
        x0, x1 = max(0, x0), min(width, x1)
        if x1 <= x0:
            return
        row = bytes(c) * (x1 - x0)
        for y in range(max(0, y0), min(height, y1)):
            i = (y * width + x0) * 3
            px[i:i + len(row)] = row

    caps = []
    for k, label in enumerate(labels[-MAX_KEYS:]):
        m = mask_for(label)
        tw = m[0] if m else 6 * len(label)
        caps.append((label, m, tw + 8, k == len(labels[-MAX_KEYS:]) - 1))
    x = width - 4
    y0 = (height - CAP_H) // 2
    for label, m, cw, last in reversed(caps):
        if x - cw < 2:
            break
        x0 = x - cw
        fill(x0 + 1, y0, x - 1, y0 + CAP_H, LAST if last else CAP)  # Rounded look: corners cut
        fill(x0, y0 + 1, x0 + 1, y0 + CAP_H - 1, LAST if last else CAP)
        fill(x - 1, y0 + 1, x, y0 + CAP_H - 1, LAST if last else CAP)
        if m:
            mw, mh, bits = m
            tx = x0 + (cw - mw) // 2
            ty = y0 + (CAP_H - mh) // 2
            col = bytes(LAST_TEXT if last else CAP_TEXT)
            for yy in range(mh):
                for xx in range(mw):
                    if bits[yy * mw + xx]:
                        X, Y = tx + xx, ty + yy
                        if 0 <= X < width and 0 <= Y < height:
                            i = (Y * width + X) * 3
                            px[i:i + 3] = col
        x = x0 - 4
    return bytes(px)


def enlarge(w, h, rgb, z):
    """Each pixel z x z"""
    if z <= 1:
        return w, h, rgb
    rows = []
    for y in range(h):
        row = rgb[y * w * 3:(y + 1) * w * 3]
        wide = b"".join(row[i:i + 3] * z for i in range(0, len(row), 3))
        rows.extend([wide] * z)
    return w * z, h * z, b"".join(rows)


class Burner(object):
    """A Recorder.transform: enlarges small screens, adds the strip. keys() gives the labels."""

    def __init__(self, keys):
        self.keys = keys
        self._cache = (None, None)

    @staticmethod
    def zoom_for(w):
        return max(1, 320 // max(1, w))

    def __call__(self, w, h, rgb):
        z = self.zoom_for(w)
        w, h, rgb = enlarge(w, h, rgb, z)
        labels = tuple(self.keys())
        key = (w, labels)
        if self._cache[0] != key:
            self._cache = (key, compose(w, list(labels)))
        return w, h + STRIP_H, rgb + self._cache[1]
