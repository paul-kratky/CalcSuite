"""Make a picture (2026-11-28): the calculator picture formats byte for byte, the colours, the
fitting, the Nspire program, PC pictures in (GDI+ and Tk), and the window with its links faked.

- TI-84 Plus CE Image (.8ca) and Pic (.8ci): the variable headers, sizes and versions as TI
  Connect CE's own files have them (tivars_lib_cpp's testData, MIT), checksums, a round trip
  through our decoder and through the vendored tivars (an independent reader)
- TI-89 Titanium picture (.89i): exact bytes of a small one, checksum, round trip
- quantize / to_565 / median_cut / layout / resample / adjust
- the TI-Nspire program: the run code round trip, the program run on the PC with a fake
  ti_draw paints exactly the picture, it passes check_nspire, Auto stays under 20 KB
- picture_load: a PNG and a BMP (as the clipboard's DIB) read by Windows' GDI+, the Tk fallback
- the window: built with a faked calculator, a picture loaded, Send goes through the faked
  link (the 84's send_prepared, the Nspire's send_nspire_files), Save writes the files

    python -I tools/selftest/picture_checks.py
"""

import os
import struct
import sys
import tempfile
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)

import calc_files as cf  # noqa: E402
import picture_formats as pf  # noqa: E402
import picture_load as pl  # noqa: E402

OUT = os.path.join(os.path.dirname(TOOLS), "build", "selftest_pictures")


def check(ok, what):
    print("%-4s picture %s" % ("PASS" if ok else "FAIL", what))
    return 0 if ok else 1


def test_image():
    """A deterministic colourful picture: gradients, a disc, stripes"""
    w, h = 300, 200
    px = bytearray()
    for y in range(h):
        for x in range(w):
            if (x - 200) ** 2 + (y - 100) ** 2 < 60 ** 2:
                c = (250, 200, 40)
            elif x < 60 and (y // 10) % 2:
                c = (0, 0, 0)
            else:
                c = (x * 255 // w, y * 255 // h, 255 - x * 255 // w)
            px += bytes(c)
    return pf.Img(w, h, px)


def formats_84():
    f = 0
    # Image: header as TI Connect CE writes it (type 1A, name 3C 00, version 0A, archived,
    # data 22247 bytes, size word 22245, 0x81)
    vals = [(k * 37) & 0xFFFF for k in range(133 * 83)]
    blob = pf.ce_image_8ca(vals, "Image1")
    f += check(len(blob) == 22321 and blob[53:75].hex() == "f8560d00e7561a3c000000000000000a80e756e55681",
               ".8ca header as TI Connect CE's (22321 bytes)")
    ents = cf.read_ti8x(blob)  # Raises on a wrong checksum
    f += check(len(ents) == 1 and ents[0][:4] == (0x1A, b"\x3c\x00", 0x0A, True), ".8ca entry, checksum")
    data = ents[0][4]
    f += check(struct.unpack_from("<H", data, 3 + 82 * 268)[0] == vals[0] and
               data[3 + 266:3 + 268] == b"\x00\x00", ".8ca rows bottom first, 2 pad bytes a row")
    img = pf.decode_ce_image(data)
    f += check(img.get(0, 0) == pf.rgb565(vals[0]) and img.get(132, 82) == pf.rgb565(vals[-1]),
               ".8ca decodes back")
    f += check(cf.detokenize_name_84(pf.ce_image_8ca(vals, "Image0")[60:68], 0x1A) == "Image0",
               ".8ca Image0 is name byte 9")
    # Pic: type 07, name 60 00, version 0A, archived, 21947 bytes, size word 21945
    idx = [(x // 7 + y // 11) % 15 for y in range(165) for x in range(265)]
    idx[5] = -1  # A pixel RecallPic leaves alone
    blob = pf.ce_pic_8ci(idx, "Pic2")
    f += check(len(blob) == 22021 and blob[53:74].hex() == "cc550d00bb550760010000000000000a80bb55b955",
               ".8ci header as TI Connect CE's (22021 bytes)")
    data = cf.read_ti8x(blob)[0][4]
    f += check(pf.ce_pic_indices(data) == idx, ".8ci round trip (indices, nibble 0 kept)")
    f += check(all(data[2 + y * 133 + 132] & 15 == (data[2 + y * 133 + 132] >> 4) for y in range(165)),
               ".8ci 266th column copies the 265th")
    f += check(data[2] >> 4 == 1 and data[4] & 15 == 0, ".8ci high nibble left, BLUE = 1, nothing = 0")
    for bad in ("Pic", "Pic10", "Image1", "pic 1x"):
        try:
            pf.ce_pic_8ci(idx, bad)
            f += check(False, ".8ci refuses the name %r" % bad)
        except ValueError:
            pass
    # Against the vendored tivars (its own reader of the same formats)
    try:
        import warnings
        warnings.simplefilter("ignore")
        from tivars.types.picture import TIPicture, TIImage
        tp = TIPicture()
        tp.data = data[2:]
        arr = tp.array()
        want = [(255, 255, 255) if k < 0 else pf.CE_PALETTE[k] for k in idx[:265]]
        f += check(arr[0][:265] == want, "tivars reads our Pic the same")
        ti = TIImage()
        idata = cf.read_ti8x(pf.ce_image_8ca(vals, "Image1"))[0][4]
        ti.data = idata[3:]
        f += check(ti.array()[0][0] == pf.rgb565(vals[0]) and ti.array()[82][132] == pf.rgb565(vals[-1]),
                   "tivars reads our Image the same")
    except ImportError as e:
        f += check(False, "tivars loads (%s)" % e)
    return f


def formats_89():
    f = 0
    bits = [1, 0, 0, 0, 0, 0, 0, 0, 1, 1,
            0, 1, 0, 0, 0, 0, 0, 0, 0, 1]  # 10 x 2
    data = pf.ti89_pic_data(bits, 10, 2)
    f += check(data.hex() == "0009" "0002" "000a" "80c0" "4040" "df", ".89i data: size, rows, cols, rows, DF")
    blob = pf.ti89_pic_89i(bits, 10, 2, "zzpic")
    got = cf.read_ti89(blob)
    f += check(got[0][:4] == (b"main", b"zzpic", 0x10, False) and got[0][4] == data, ".89i file, checksum")
    kind, name, img = pf.read_picture(blob)
    f += check(kind == "PIC" and name == "zzpic" and [img.get(x, y) == (0, 0, 0) for y in range(2)
                                                       for x in range(10)] == [bool(b) for b in bits],
               ".89i round trip")
    for w, h, _what in pf.SIZES_89:
        d = pf.ti89_pic_data([0] * (w * h), w, h)
        f += check(len(d) == 2 + 4 + (w + 7) // 8 * h + 1, ".89i %d x %d size" % (w, h))
    try:
        pf.ti89_pic_89i(bits, 10, 2, "ZZ Pic")
        f += check(False, ".89i refuses a bad name")
    except ValueError:
        pass
    return f


def colours():
    f = 0
    img = pf.Img(15, 1, b"".join(bytes(c) for c in pf.CE_PALETTE))
    for d in (pf.NONE, pf.DIFFUSE, pf.PATTERN):
        q = pf.quantize(img, pf.CE_PALETTE, d) if d != pf.PATTERN else pf.quantize(img, pf.CE_PALETTE, d, 0)
        f += check(q == list(range(15)), "quantize keeps the palette's own colours (%s)" % d)
    grey = pf.Img(64, 64, bytes([128, 128, 128]) * 4096)
    for d in (pf.DIFFUSE, pf.PATTERN):
        q = pf.quantize(grey, pf.MONO, d)
        frac = sum(q) / 4096.0
        f += check(0.4 < frac < 0.6, "50%% grey dithers to about half black (%s: %.2f)" % (d, frac))
    f += check(sum(pf.quantize(grey, pf.MONO, pf.NONE)) in (0, 4096), "no dithering: one colour")
    v = pf.to_565(pf.Img(2, 1, bytes([255, 255, 255, 255, 0, 0])))
    f += check(v == [0xFFFF, 0xF800], "RGB565: white, red")
    f += check(pf.rgb565(0xFFFF) == (255, 255, 255) and pf.rgb565(0x07E0) == (0, 255, 0), "RGB565 back")
    three = pf.Img(3, 2, bytes([1, 2, 3, 200, 0, 0, 1, 2, 3, 0, 0, 9, 0, 0, 9, 1, 2, 3]))
    f += check(sorted(pf.median_cut(three, 8)) == sorted([(1, 2, 3), (200, 0, 0), (0, 0, 9)]),
               "median cut keeps a few colours exactly")
    pal = pf.median_cut(test_image(), 16)
    f += check(len(pal) == 16 and all(len(c) == 3 and all(0 <= v <= 255 for v in c) for c in pal),
               "median cut: 16 colours")
    a = pf.adjust(pf.Img(1, 1, bytes([100, 128, 200])), 50, 0)
    f += check(a.px == bytearray([164, 192, 255]), "brightness +50")
    a = pf.adjust(pf.Img(1, 1, bytes([100, 128, 200])), 0, -100)
    f += check(a.px == bytearray([128, 128, 128]), "contrast -100: all grey")
    return f


def fitting():
    f = 0
    f += check(pf.layout(400, 200, 100, 100, pf.FIT) == ((0.0, 0.0, 400.0, 200.0), (0, 25, 100, 50)),
               "fit: bars above and below")
    f += check(pf.layout(400, 200, 100, 100, pf.FILL) == ((100.0, 0.0, 200.0, 200.0), (0, 0, 100, 100)),
               "fill: the sides cut off")
    f += check(pf.layout(400, 200, 100, 100, pf.STRETCH) == ((0.0, 0.0, 400.0, 200.0), (0, 0, 100, 100)),
               "stretch")
    src = pf.Img(4, 2, bytes([0, 0, 0, 255, 255, 255, 10, 10, 10, 30, 30, 30] * 2))
    out = pf.resample(src, 2, 1, pf.STRETCH)
    f += check(out.get(0, 0) == (128, 128, 128) and out.get(1, 0) == (20, 20, 20), "resample averages")
    out = pf.resample(src, 4, 4, pf.FIT, (9, 9, 9))
    f += check(out.get(0, 0) == (9, 9, 9) and out.get(0, 1) == (0, 0, 0) and out.get(1, 2) == (255, 255, 255),
               "resample fits with bars")
    big = pf.resample(pf.Img(2, 1, bytes([0, 0, 0, 255, 255, 255])), 4, 1, pf.STRETCH)
    f += check([big.get(x, 0)[0] for x in range(4)] == [0, 0, 255, 255], "resample enlarges (nearest)")
    return f


class FakeDraw(object):
    """ti_draw and ti_system for running a generated program on the PC"""

    def __init__(self):
        self.canvas = [[None] * pf.NSPIRE_W for _ in range(pf.NSPIRE_H)]
        self.colour, self.rects = None, 0

    def modules(self):
        td = types.ModuleType("ti_draw")
        td.use_buffer = td.paint_buffer = lambda: None
        td.set_color = lambda r, g, b: setattr(self, "colour", (r, g, b))

        def fill_rect(x, y, w, h):
            self.rects += 1
            for yy in range(max(0, y), min(pf.NSPIRE_H, y + h)):
                row = self.canvas[yy]
                for xx in range(max(0, x), min(pf.NSPIRE_W, x + w)):
                    row[xx] = self.colour
        td.fill_rect = fill_rect
        ts = types.ModuleType("ti_system")
        ts.get_key = lambda *a: "esc"
        return {"ti_draw": td, "ti_system": ts}


def run_program(text):
    fake = FakeDraw()
    saved = {k: sys.modules.get(k) for k in ("ti_draw", "ti_system")}
    sys.modules.update(fake.modules())
    try:
        exec(compile(text, "zzpic.py", "exec"), {"__name__": "__main__"})
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    return fake


def nspire():
    f = 0
    import random
    rng = random.Random(7)
    for ncol in (1, 2, 8, 16, 32, 64):
        w, h = 159, 3
        idx = [0] * 159 + [rng.randrange(ncol) for _ in range(159)] + [ncol - 1] * 100 + [0] * 59
        s = pf.encode_runs(idx, w, ncol)
        f += check(pf.decode_runs(s, w, h, ncol) == idx and '"' not in s and "\\" not in s,
                   "run code round trip, %d colours" % ncol)
    img = test_image()
    src = pl.Source(img.w, img.h, "zzpic", img=img)
    import picture_window as pw
    st = pw.default_settings("nspire")
    st.update(name="zzpic", detail="2", dither=pf.NONE)
    res = pw.convert(src, st)
    fake = run_program(res.py)
    w, h, x0, y0 = pf.nspire_grid(2)
    shown = res.preview
    bad = sum(1 for y in range(h) for x in range(w) if fake.canvas[y0 + 2 * y][x0 + 2 * x] != shown.get(x, y))
    f += check(bad == 0, "the program paints exactly the preview (%d rectangles)" % fake.rects)
    import check_nspire
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "zzpic.py")
    with open(path, "w", newline="\n") as fh:
        fh.write(res.py)
    found = check_nspire.check_file(path, set())
    f += check(not [x for x in found if x.level in ("ERROR", "WARN")],
               "the program passes check_nspire (%s)" % [x.message for x in found][:2])
    noisy = pf.Img(318, 212, bytes(rng.randrange(256) for _ in range(318 * 212 * 3)))
    st.update(detail="auto", dither=pf.DIFFUSE, colours="32")
    res = pw.convert(pl.Source(318, 212, "zz", img=noisy), st)
    f += check(len(res.py) <= pf.NSPIRE_BUDGET and res.scale > 1,
               "Auto keeps a noisy picture under 20 KB (%d bytes, %d x %d pixels)"
               % (len(res.py), res.scale, res.scale))
    st.update(detail="1", colours="64")
    res = pw.convert(pl.Source(318, 212, "zz", img=noisy), st)
    f += check(len(res.py) > pf.NSPIRE_BUDGET and "Over 20 KB" in res.info, "too big says so")
    try:
        st.update(name="Bad Name")
        pw.convert(src, st)
        f += check(False, "a bad program name is refused")
    except ValueError:
        pass
    return f


def loading():
    f = 0
    img = test_image()
    os.makedirs(OUT, exist_ok=True)
    png = os.path.join(OUT, "zztest.png")
    with open(png, "wb") as fh:
        fh.write(pf.png_bytes(img))
    s = pl.load_file(png)
    out = s.render(img.w, img.h, pf.STRETCH)
    diff = max(abs(a - b) for a, b in zip(out.px, img.px))
    f += check((s.w, s.h) == (300, 200) and diff <= 2, "a PNG read at its own size (%s, max diff %d)"
               % ("GDI+" if s.gdi else "Tk", diff))
    if sys.platform == "win32":
        f += check(s.gdi is not None, "Windows' GDI+ reads the PNG")
        small = s.render(100, 100, pf.FIT)
        f += check(small.get(50, 5) == (255, 255, 255) and small.get(50, 50) != (255, 255, 255),
                   "GDI+ fits with white bars")
        # A clipboard DIB: BITMAPINFOHEADER (bottom-up, 24 bits) + rows padded to 4 bytes
        w, h = 3, 2
        rows = b""
        for y in range(h - 1, -1, -1):
            row = b"".join(bytes(reversed(img.get(x * 50, y * 50))) for x in range(w))
            rows += row + b"\0" * ((4 - len(row) % 4) % 4)
        dib = struct.pack("<IiiHHIIiiII", 40, w, h, 1, 24, 0, len(rows), 0, 0, 0, 0) + rows
        b = pl.load_bytes(pl.dib_to_bmp(dib)).render(w, h, pf.STRETCH)
        f += check([b.get(x, y) for y in range(h) for x in range(w)] ==
                   [img.get(x * 50, y * 50) for y in range(h) for x in range(w)], "a clipboard DIB reads right")
    tk_img = pl._tk_decode(pf.png_bytes(img))
    f += check(tk_img is not None and tk_img.px == img.px, "the Tk fallback reads the PNG")
    try:
        pl.load_bytes(b"not a picture at all")
        f += check(False, "a non-picture is refused")
    except pl.LoadError:
        pass
    ti = pl.load_bytes(pf.ti89_pic_89i([1, 0] * 8, 4, 4, "zzpic"))
    f += check((ti.w, ti.h) == (4, 4), "a calculator's own picture file opens")
    return f


# ---- The window, links faked ----

class FakeCalc(object):
    def __init__(self, slug):
        import picture_window as pw
        self.slug, self.title = slug, pw.TITLES[slug]


class FakeMirror(object):
    def __init__(self, root, slug):
        self.root, self.calc = root, FakeCalc(slug)
        self.sent, self.status, self.nspire_files = [], [], []

    def connected(self):
        return True

    def set_status(self, text):
        self.status.append(text)

    def queue(self, line, _x=None, done=None, progress=None):
        if line == "ls":
            done(0, ["ITEM type=07 size=10 arch=0 locked=0 folder=- name=%s" % cf.to_hex("Pic9".encode())])
        else:  # Answered a moment later (the test drives Tk with update(), not mainloop())
            self.sent.append(line)
            self.root.after(10, lambda: done(0, ["OK sent"]))

    def send_nspire_files(self, files, done=None):
        self.nspire_files += files
        done(True, "Sent")


def wait(root, cond, s=20):
    t = time.time()
    while time.time() - t < s:
        root.update()
        if cond():
            return True
        time.sleep(0.02)
    return False


def window():
    f = 0
    import tkinter as tk
    import picture_window as pw
    root = tk.Tk()
    root.withdraw()
    os.makedirs(OUT, exist_ok=True)
    png = os.path.join(OUT, "zztest.png")
    try:
        m = FakeMirror(root, "ti84")
        win = pw.PictureWindow(root, m, OUT, path=png).panel
        ok = wait(root, lambda: win.result is not None and not win.busy and not win.dirty)
        f += check(ok and win.result.file_name == "Image1.8ca", "the window makes Image1 from a file")
        f += check(str(win.send_btn["state"]) == "normal", "Send is on for this tab's calculator")
        win.send()
        wait(root, lambda: "Sent Image1" in win.status.cget("text"), 5)
        sent = m.sent[0][5:] if m.sent else ""
        f += check(m.sent and os.path.isfile(sent) and open(sent, "rb").read() == win.result.blob,
                   "Send goes through the 84's link (send_prepared)")
        f += check("Sent Image1. On the 84" in win.status.cget("text"), "Send says how to see it (%s)" % win.status.cget("text")[:60])
        # Another calculator: Send off, Save still works
        win.st["model"] = "ti89"
        win.vars["combo_model"].current(1)
        win.model_changed()
        ok = wait(root, lambda: win.result is not None and win.result.file_name.endswith(".89i")
                  and not win.busy and not win.dirty)
        f += check(ok and str(win.send_btn["state"]) == "disabled", "a TI-89 picture from the 84's tab: Save only")
        win.name_var.set("Bad Name")
        ok = wait(root, lambda: win.error is not None and not win.busy and not win.dirty)
        f += check(ok and "Not ready" in win.status.cget("text"), "a bad name says why")
        win.close()
        f += check(not win.winfo_exists(), "Close closes the window around the panel")
        m = FakeMirror(root, "nspire")
        win = pw.PictureWindow(root, m, OUT, path=png).panel
        ok = wait(root, lambda: win.result is not None and not win.busy and not win.dirty)
        f += check(ok and win.result.py and win.st["name"] == "zztest", "the Nspire window makes a program")
        import mirror  # noqa: F401  prepare_for_nspire lives there (no window of its own made)
        win.send()
        f += check(len(m.nspire_files) == 1 and m.nspire_files[0][0].endswith("zztest.tns"),
                   "Send goes through the Nspire's send_nspire_files")
        win.close()
        # As a tab would hold it: a frame in the main window, no Close button of its own
        holder = tk.Frame(root)
        panel = pw.PicturePanel(holder, FakeMirror(root, "ti89"), OUT, path=png)
        panel.pack(fill="both", expand=True)
        ok = wait(root, lambda: panel.result is not None and not panel.busy and not panel.dirty)
        f += check(ok and panel.result.file_name == "zztest.89i" and panel.drops[0] is not None,
                   "the panel works inside a frame (a tab)")
        panel.shutdown()
        holder.destroy()
    finally:
        root.destroy()
    return f


def main():
    f = 0
    for part in (formats_84, formats_89, colours, fitting, nspire, loading, window):
        try:
            f += part()
        except Exception:
            import traceback
            traceback.print_exc()
            f += check(False, "%s raised" % part.__name__)
    return f


if __name__ == "__main__":
    n = main()
    print("picture checks: %s" % ("ALL PASSED" if not n else "%d FAILED" % n))
    sys.exit(1 if n else 0)
