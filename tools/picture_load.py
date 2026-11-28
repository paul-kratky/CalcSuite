"""PC pictures in: a file (PNG, JPEG, BMP, GIF, TIFF, or a calculator's own .8ca/.8ci/.89i),
the clipboard, or files dropped on a window. Windows' own GDI+ (gdiplus.dll, part of every
Windows) decodes and scales them through ctypes; without it, Tk reads PNG, GIF and PPM and
picture_formats.resample scales. No Pillow: nothing for the packaged app to carry.

    pic = load_file(path)             # a Source; raises LoadError
    img = pic.render(318, 212, "fit") # picture_formats.Img at that size
"""

import ctypes
import os
import sys
from ctypes import wintypes

import picture_formats as pf

EXTS = "*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff *.8ca *.8ci *.89i"
TI_EXTS = (".8ca", ".8ci", ".89i")


class LoadError(Exception):
    pass


class Source(object):
    """A picture ready to be fitted to any size: from GDI+ (scaled by Windows) or an Img
    (scaled here)"""

    def __init__(self, w, h, name, img=None, gdi=None):
        self.w, self.h, self.name = w, h, name
        self.img, self.gdi = img, gdi
        self.cache = {}

    def render(self, tw, th, mode=pf.FIT, bg=(255, 255, 255)):
        key = (tw, th, mode, tuple(bg))
        if key not in self.cache:
            out = None
            if self.gdi is not None:
                try:
                    out = self.gdi.render(tw, th, mode, bg)
                except (OSError, LoadError):
                    out = None
            if out is None:
                if self.img is None:
                    self.img = self.gdi.whole()
                out = pf.resample(self.img, tw, th, mode, bg)
            if len(self.cache) > 8:
                self.cache.clear()
            self.cache[key] = out
        return self.cache[key]

    def close(self):
        if self.gdi is not None:
            self.gdi.close()
            self.gdi = None


def load_file(path):
    name = os.path.splitext(os.path.basename(path))[0]
    try:
        with open(path, "rb") as f:
            blob = f.read()
    except OSError as e:
        raise LoadError("can't read %s: %s" % (os.path.basename(path), e.strerror or e))
    return load_bytes(blob, name)


def load_bytes(blob, name="picture"):
    """Any picture's bytes -> a Source. Raises LoadError."""
    if not blob:
        raise LoadError("the file is empty")
    if blob[:4] == b"**TI":
        try:
            _kind, _vname, img = pf.read_picture(blob)
        except ValueError as e:
            raise LoadError("not a picture this can read: %s" % e)
        return Source(img.w, img.h, name, img=img)
    why = "Windows can't read it"
    if sys.platform == "win32":
        try:
            g = GdiImage.from_bytes(blob)
            return Source(g.w, g.h, name, gdi=g)
        except (OSError, LoadError) as e:
            why = str(e) or why
    img = _tk_decode(blob)
    if img is not None:
        return Source(img.w, img.h, name, img=img)
    raise LoadError("not a picture this can read (%s)" % why)


def _tk_decode(blob):
    """PNG / GIF / PPM through Tk's PhotoImage (the fallback), or None"""
    try:
        import base64
        import tkinter as tk
        root = tk._default_root
        own = root is None
        if own:
            root = tk.Tk()
            root.withdraw()
        try:
            photo = tk.PhotoImage(master=root, data=base64.b64encode(blob).decode("ascii"))
            w, h = photo.width(), photo.height()
            if w * h > 4000 * 4000:
                return None
            step = max(1, min(w, h) // 1024)
            if step > 1:
                photo = photo.subsample(step)
                w, h = photo.width(), photo.height()
            rows = root.tk.call(photo, "data")
            if isinstance(rows, str):
                rows = root.tk.splitlist(rows)
            px = bytearray()
            for row in rows:
                for c in (root.tk.splitlist(row) if isinstance(row, str) else row):
                    c = str(c)
                    px += bytes.fromhex(c[1:7]) if c.startswith("#") else bytes(_named(root, c))
            return pf.Img(w, h, px)
        finally:
            if own:
                root.destroy()
    except Exception:
        return None


def _named(root, c):
    r, g, b = root.winfo_rgb(c)
    return (r >> 8, g >> 8, b >> 8)


# ---- GDI+ ----

class _Input(ctypes.Structure):
    _fields_ = [("version", ctypes.c_uint32), ("callback", ctypes.c_void_p),
                ("no_thread", wintypes.BOOL), ("no_codecs", wintypes.BOOL)]


class _Data(ctypes.Structure):
    _fields_ = [("w", ctypes.c_uint), ("h", ctypes.c_uint), ("stride", ctypes.c_int),
                ("fmt", ctypes.c_int), ("scan0", ctypes.c_void_p), ("res", ctypes.c_void_p)]


class _Rect(ctypes.Structure):
    _fields_ = [("x", ctypes.c_int), ("y", ctypes.c_int), ("w", ctypes.c_int), ("h", ctypes.c_int)]


ARGB32 = 0x26200A
_GDI = {}


def _gdi():
    """gdiplus.dll, started once: the DLL, or raises OSError"""
    if "dll" not in _GDI:
        dll = ctypes.WinDLL("gdiplus")
        token = ctypes.c_size_t()
        inp = _Input(1, None, False, False)
        st = dll.GdiplusStartup(ctypes.byref(token), ctypes.byref(inp), None)
        if st:
            raise OSError("GDI+ didn't start (%d)" % st)
        P = ctypes.c_void_p
        for fn, args in (
                ("GdipCreateBitmapFromStream", [P, ctypes.POINTER(P)]),
                ("GdipGetImageWidth", [P, ctypes.POINTER(ctypes.c_uint)]),
                ("GdipGetImageHeight", [P, ctypes.POINTER(ctypes.c_uint)]),
                ("GdipDisposeImage", [P]),
                ("GdipCreateBitmapFromScan0", [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                               P, ctypes.POINTER(P)]),
                ("GdipGetImageGraphicsContext", [P, ctypes.POINTER(P)]),
                ("GdipDeleteGraphics", [P]),
                ("GdipSetInterpolationMode", [P, ctypes.c_int]),
                ("GdipSetPixelOffsetMode", [P, ctypes.c_int]),
                ("GdipSetCompositingQuality", [P, ctypes.c_int]),
                ("GdipGraphicsClear", [P, ctypes.c_uint32]),
                ("GdipCreateImageAttributes", [ctypes.POINTER(P)]),
                ("GdipDisposeImageAttributes", [P]),
                ("GdipSetImageAttributesWrapMode", [P, ctypes.c_int, ctypes.c_uint32, wintypes.BOOL]),
                ("GdipDrawImageRectRect", [P, P, ctypes.c_float, ctypes.c_float, ctypes.c_float,
                                           ctypes.c_float, ctypes.c_float, ctypes.c_float,
                                           ctypes.c_float, ctypes.c_float, ctypes.c_int, P, P, P]),
                ("GdipBitmapLockBits", [P, ctypes.POINTER(_Rect), ctypes.c_uint, ctypes.c_int,
                                        ctypes.POINTER(_Data)]),
                ("GdipBitmapUnlockBits", [P, ctypes.POINTER(_Data)]),
                ("GdipGetPropertyItemSize", [P, ctypes.c_uint, ctypes.POINTER(ctypes.c_uint)]),
                ("GdipGetPropertyItem", [P, ctypes.c_uint, ctypes.c_uint, P]),
                ("GdipImageRotateFlip", [P, ctypes.c_int])):
            f = getattr(dll, fn)
            f.argtypes, f.restype = args, ctypes.c_int
        shl = ctypes.WinDLL("shlwapi")
        shl.SHCreateMemStream.argtypes = [ctypes.c_char_p, ctypes.c_uint]
        shl.SHCreateMemStream.restype = ctypes.c_void_p
        _GDI["dll"], _GDI["shl"], _GDI["token"] = dll, shl, token
    return _GDI["dll"]


def _release(com):
    """IUnknown::Release on a COM pointer (the memory stream)"""
    if com:
        vtbl = ctypes.cast(com, ctypes.POINTER(ctypes.c_void_p))[0]
        release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(
            ctypes.cast(vtbl, ctypes.POINTER(ctypes.c_void_p))[2])
        release(com)


# EXIF orientation (1-8) -> GDI+ RotateFlipType: phone photos come out the right way up
_ORIENT = {2: 4, 3: 2, 4: 6, 5: 5, 6: 1, 7: 7, 8: 3}


class GdiImage(object):
    def __init__(self, handle, stream, w, h):
        self.h_img, self.stream, self.w, self.h = handle, stream, w, h

    @classmethod
    def from_bytes(cls, blob):
        dll = _gdi()
        stream = _GDI["shl"].SHCreateMemStream(blob, len(blob))
        if not stream:
            raise OSError("no memory for the picture")
        img = ctypes.c_void_p()
        st = dll.GdipCreateBitmapFromStream(stream, ctypes.byref(img))
        if st or not img:
            _release(stream)
            raise LoadError("not a picture Windows can read")
        self = cls(img, stream, 0, 0)
        self._orient()
        w, h = ctypes.c_uint(), ctypes.c_uint()
        dll.GdipGetImageWidth(img, ctypes.byref(w))
        dll.GdipGetImageHeight(img, ctypes.byref(h))
        self.w, self.h = w.value, h.value
        if not self.w or not self.h:
            self.close()
            raise LoadError("an empty picture")
        return self

    def _orient(self):
        dll = _gdi()
        size = ctypes.c_uint()
        if dll.GdipGetPropertyItemSize(self.h_img, 0x0112, ctypes.byref(size)) or size.value < 18:
            return
        buf = ctypes.create_string_buffer(size.value)
        if dll.GdipGetPropertyItem(self.h_img, 0x0112, size.value, buf):
            return
        # PropertyItem: id (4), length (4), type (2), then a pointer to the value (a SHORT)
        ptr = ctypes.cast(buf, ctypes.POINTER(ctypes.c_void_p))[2 if ctypes.sizeof(ctypes.c_void_p) == 8 else 3]
        if ptr:
            o = ctypes.cast(ptr, ctypes.POINTER(ctypes.c_ushort))[0]
            if o in _ORIENT:
                dll.GdipImageRotateFlip(self.h_img, _ORIENT[o])

    def render(self, tw, th, mode, bg):
        """Scaled by GDI+ (high-quality bicubic) onto a tw x th Img"""
        dll = _gdi()
        (sx, sy, sw, sh), (dx, dy, dw, dh) = pf.layout(self.w, self.h, tw, th, mode)
        dst, g, attr = ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p()
        if dll.GdipCreateBitmapFromScan0(tw, th, 0, ARGB32, None, ctypes.byref(dst)):
            raise OSError("GDI+ couldn't make a picture")
        try:
            if dll.GdipGetImageGraphicsContext(dst, ctypes.byref(g)):
                raise OSError("GDI+ couldn't draw")
            try:
                dll.GdipSetInterpolationMode(g, 7)    # HighQualityBicubic
                dll.GdipSetPixelOffsetMode(g, 4)      # Half: pixel centres line up
                dll.GdipSetCompositingQuality(g, 2)
                r, gg, b = bg
                # The bars, and the colour under see-through pixels
                dll.GdipGraphicsClear(g, 0xFF000000 | (r << 16) | (gg << 8) | b)
                dll.GdipCreateImageAttributes(ctypes.byref(attr))
                if attr:
                    dll.GdipSetImageAttributesWrapMode(attr, 3, 0, False)  # TileFlipXY: clean edges
                st = dll.GdipDrawImageRectRect(g, self.h_img, dx, dy, dw, dh, sx, sy, sw, sh,
                                               2, attr, None, None)
                if st:
                    raise OSError("GDI+ couldn't scale the picture (%d)" % st)
            finally:
                if attr:
                    dll.GdipDisposeImageAttributes(attr)
                dll.GdipDeleteGraphics(g)
            return _read_pixels(dst, tw, th)
        finally:
            dll.GdipDisposeImage(dst)

    def whole(self):
        """The whole picture as an Img (at most 1024 on a side)"""
        k = max(1.0, max(self.w, self.h) / 1024.0)
        return self.render(max(1, int(self.w / k)), max(1, int(self.h / k)), pf.STRETCH,
                           (255, 255, 255))

    def close(self):
        if self.h_img:
            _gdi().GdipDisposeImage(self.h_img)
            self.h_img = None
        if self.stream:
            _release(self.stream)
            self.stream = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


def _read_pixels(bmp, w, h):
    dll = _gdi()
    data = _Data()
    rect = _Rect(0, 0, w, h)
    if dll.GdipBitmapLockBits(bmp, ctypes.byref(rect), 1, ARGB32, ctypes.byref(data)):
        raise OSError("GDI+ couldn't read the pixels")
    try:
        raw = bytearray(w * h * 3)
        for y in range(h):
            row = ctypes.string_at(data.scan0 + y * data.stride, 4 * w)
            raw[3 * w * y + 0:3 * w * (y + 1):3] = row[2::4]
            raw[3 * w * y + 1:3 * w * (y + 1):3] = row[1::4]
            raw[3 * w * y + 2:3 * w * (y + 1):3] = row[0::4]
        return pf.Img(w, h, raw)
    finally:
        dll.GdipBitmapUnlockBits(bmp, ctypes.byref(data))


# ---- The clipboard ----

CF_DIB, CF_HDROP = 8, 15


def _user32():
    u = ctypes.WinDLL("user32")
    k = ctypes.WinDLL("kernel32")
    u.OpenClipboard.argtypes = [wintypes.HWND]
    u.GetClipboardData.argtypes = [ctypes.c_uint]
    u.GetClipboardData.restype = ctypes.c_void_p
    u.IsClipboardFormatAvailable.argtypes = [ctypes.c_uint]
    u.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
    u.RegisterClipboardFormatW.restype = ctypes.c_uint
    k.GlobalLock.argtypes = [ctypes.c_void_p]
    k.GlobalLock.restype = ctypes.c_void_p
    k.GlobalUnlock.argtypes = [ctypes.c_void_p]
    k.GlobalSize.argtypes = [ctypes.c_void_p]
    k.GlobalSize.restype = ctypes.c_size_t
    return u, k


def _global_bytes(k, h):
    p = k.GlobalLock(h)
    if not p:
        return None
    try:
        return ctypes.string_at(p, k.GlobalSize(h))
    finally:
        k.GlobalUnlock(h)


def dib_to_bmp(dib):
    """A CF_DIB (BITMAPINFO + pixels) -> a .bmp file's bytes"""
    if len(dib) < 40:
        raise LoadError("an empty picture on the clipboard")
    size = int.from_bytes(dib[:4], "little")
    bits = int.from_bytes(dib[14:16], "little")
    compression = int.from_bytes(dib[16:20], "little")
    used = int.from_bytes(dib[32:36], "little")
    colours = used or (1 << bits if bits <= 8 else 0)
    masks = 12 if size == 40 and compression == 3 else 0
    offset = 14 + size + masks + 4 * colours
    return b"BM" + (14 + len(dib)).to_bytes(4, "little") + b"\0\0\0\0" + offset.to_bytes(4, "little") + dib


def from_clipboard():
    """The clipboard's picture (or a copied picture file) -> a Source, or None when it holds
    none. Raises LoadError for one that can't be read."""
    if sys.platform != "win32":
        return None
    u, k = _user32()
    if not u.OpenClipboard(None):
        raise LoadError("another program is using the clipboard: try again")
    blob, path = None, None
    try:
        png = u.RegisterClipboardFormatW("PNG")
        if png and u.IsClipboardFormatAvailable(png):
            h = u.GetClipboardData(png)
            blob = _global_bytes(k, h) if h else None
        if blob is None and u.IsClipboardFormatAvailable(CF_DIB):
            h = u.GetClipboardData(CF_DIB)
            dib = _global_bytes(k, h) if h else None
            blob = dib_to_bmp(dib) if dib else None
        if blob is None and u.IsClipboardFormatAvailable(CF_HDROP):
            h = u.GetClipboardData(CF_HDROP)
            files = _drop_files(h) if h else []
            path = next((f for f in files if os.path.isfile(f)), None)
    finally:
        u.CloseClipboard()
    if path:
        return load_file(path)
    if blob is None:
        return None
    return load_bytes(blob, "pasted")


def _drop_files(hdrop):
    sh = ctypes.WinDLL("shell32")
    sh.DragQueryFileW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_wchar_p, ctypes.c_uint]
    sh.DragQueryFileW.restype = ctypes.c_uint
    n = sh.DragQueryFileW(hdrop, 0xFFFFFFFF, None, 0)
    out = []
    for i in range(min(n, 64)):
        size = sh.DragQueryFileW(hdrop, i, None, 0) + 1
        buf = ctypes.create_unicode_buffer(size)
        sh.DragQueryFileW(hdrop, i, buf, size)
        out.append(buf.value)
    return out


# ---- Files dropped on a window ----

WM_DROPFILES, WM_NCDESTROY, GWLP_WNDPROC = 0x0233, 0x0082, -4


class DropTarget(object):
    """Files dragged from Explorer onto a Tk widget (a window, or a frame / canvas inside one:
    each is a window of its own to Windows): on_drop([paths]) on Tk's thread (Windows calls
    the window procedure there). Nothing happens where Windows says no."""

    def __init__(self, widget, on_drop):
        self.ok = False
        if sys.platform != "win32":
            return
        try:
            import tkinter as tk
            widget.update_idletasks()
            top = isinstance(widget, (tk.Tk, tk.Toplevel))
            hwnd = int(widget.wm_frame(), 16) if top else widget.winfo_id()
            u, sh = ctypes.WinDLL("user32"), ctypes.WinDLL("shell32")
            LRESULT = ctypes.c_ssize_t
            self.proto = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, ctypes.c_uint,
                                            wintypes.WPARAM, wintypes.LPARAM)
            u.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
            u.SetWindowLongPtrW.restype = ctypes.c_void_p
            u.CallWindowProcW.argtypes = [ctypes.c_void_p, wintypes.HWND, ctypes.c_uint,
                                          wintypes.WPARAM, wintypes.LPARAM]
            u.CallWindowProcW.restype = LRESULT
            sh.DragAcceptFiles.argtypes = [wintypes.HWND, wintypes.BOOL]
            sh.DragFinish.argtypes = [ctypes.c_void_p]
            self.u, self.sh, self.hwnd, self.on_drop, self.tk = u, sh, hwnd, on_drop, widget

            def proc(hwnd, msg, wp, lp):
                if msg == WM_DROPFILES:
                    try:
                        files = _drop_files(wp)
                        sh.DragFinish(wp)
                        self.tk.after(0, lambda: self.on_drop(files))
                    except Exception:
                        pass
                    return 0
                old = self.old
                if msg == WM_NCDESTROY:
                    self.u.SetWindowLongPtrW(hwnd, GWLP_WNDPROC, old)
                return self.u.CallWindowProcW(old, hwnd, msg, wp, lp)
            self.proc = self.proto(proc)  # Kept: Windows calls it as long as the window lives
            self.old = u.SetWindowLongPtrW(hwnd, GWLP_WNDPROC, ctypes.cast(self.proc, ctypes.c_void_p))
            if not self.old:
                return
            sh.DragAcceptFiles(hwnd, True)
            self.ok = True
        except (OSError, AttributeError, ValueError, Exception):
            self.ok = False
