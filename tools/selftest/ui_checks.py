"""Self-test for the app's pure parts (no calculator, no tools/bin, no window):
the Markdown renderer's parser, the key maps and the Keys panel made from them, the symbol and
paste maps, the clicks on the 84's menus and the 89's toolbar, the program library, the
key-press strip, and the move from Documents\\Nspire Mirror.

    python -I tools/selftest/ui_checks.py      (run_selftest.py runs it too)
"""

import io
import os
import shutil
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
KIT = os.path.dirname(TOOLS)
for _p in (TOOLS, os.path.join(TOOLS, "nspire_cli"), os.path.join(TOOLS, "ti84_cli")):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def check(ok, what):
    print("%-4s %s" % ("PASS" if ok else "FAIL", what))
    return 0 if ok else 1


MD = """# Title
Intro with `code`, **bold** and a [link](https://example.com).
<!-- screenshot: all-screens -->

## Section two

- one
- two with *stress*
  continued
  1. nested

| PC key | Calculator |
| --- | --- |
| `F5` | GRAPH \\| ZOOM |
| Esc | CLEAR |

```tibasic84 name=QUAD
:Disp 1
```

```python
print(1)
```
"""


def markdown_checks():
    import md_render as md
    f = 0
    blocks = md.parse(MD)
    kinds = [b[0] for b in blocks]
    f += check(kinds == ["h", "p", "h", "li", "li", "li", "table", "code", "code"],
               "Markdown: heading, paragraph, list, table, code blocks (got %s)" % kinds)
    p = blocks[1][1]
    f += check(("code", "code", None) in p and ("b", "bold", None) in p and
               ("link", "link", "https://example.com") in p, "Markdown: inline code, bold, link")
    f += check(blocks[3][3] == [("", "one", None)] and ("i", "stress", None) in blocks[4][3] and
               blocks[5][1] == 1 and blocks[5][2] == "1.", "Markdown: bullets, italic, nesting")
    f += check(md.plain(blocks[4][3]) == "two with stress continued", "Markdown: a list item's next line")
    t = blocks[6]
    f += check([md.plain(c) for c in t[1]] == ["PC key", "Calculator"] and
               [md.plain(c) for c in t[2][0]] == ["F5", "GRAPH | ZOOM"] and len(t[2]) == 2,
               "Markdown: pipe table, escaped |")
    f += check(blocks[7][1:] == ("tibasic84 name=QUAD", "QUAD", ":Disp 1") and blocks[8][2] is None,
               "Markdown: fenced code, name= from the info string")
    f += check(md.headings(blocks) == [(1, "Title", "title"), (2, "Section two", "section-two")],
               "Markdown: contents list and anchors")
    f += check(not any("screenshot" in md.plain(b[1]) for b in blocks if b[0] == "p"),
               "Markdown: HTML comments dropped")
    for name in ("TIBASIC_84.md", "TIBASIC_89.md", "PYTHON_NSPIRE_GUIDE.md"):
        path = os.path.join(KIT, "docs", name)
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as fh:
                b = md.parse(fh.read())
            named = [x[2] for x in b if x[0] == "code" and x[2]]
            f += check(len(named) >= 5 and len(md.headings(b)) > 10,
                       "Markdown: %s parses (%d named examples)" % (name, len(named)))
    return f


def key_checks():
    import calc_models as cm
    f = 0
    for calc in cm.CALCS:
        groups = calc.key_groups()
        shown = [k for _g, rows in groups for _pc, _c, k in rows if k]
        want = [k for k in calc.tk_keys if k != "KP_Enter"]
        f += check(sorted(shown) == sorted(want) and len(shown) == len(set(shown)),
                   "Keys panel (%s): every PC key once, from tk_keys" % calc.slug)
        f += check([g for g, _r in groups][-1] == "Mouse" and
                   all(calc.code_for(n) is not None for names in calc.tk_keys.values() for n in names),
                   "Keys panel (%s): a Mouse group; every key name has a code" % calc.slug)
        bad = []
        for sym, _what, keys, near in calc.SYMBOLS:
            if keys is None:
                if not near:
                    bad.append(sym)
                continue
            codes = (calc.paste_keys(keys)[0] if isinstance(keys, str) and not calc.paste_keys(keys)[1]
                     else None) if isinstance(keys, str) else cm.symbol_codes(calc, keys)
            if not codes:
                bad.append(sym)
        f += check(not bad, "Symbols (%s): every symbol types, or says what to use (%s)" % (calc.slug, bad))
    f += check(cm.Ti84.describe_press("F5", "", ["graph"]) == "F5 → GRAPH", "Last key line: F5 -> GRAPH")
    f += check(cm.Ti84.keys_label(["down"] * 7 + ["enter"]) == "↓×7 ENTER", "Repeated keys shown once")
    codes, missing = cm.Ti84.paste_keys("X≤3→A")
    f += check(not missing and codes == [0xB1, 0xFE0F, 0x91, 0x8A, 0x9A], "84 paste: X≤3→A")
    codes, missing = cm.Ti84.paste_keys("∫(X,X,0,1)=2!")
    f += check(not missing and codes[0] == 0xC8 and 0xFE0A in codes and codes[-1] == 0xFE24,
               "84 paste: ∫ = !")
    codes, missing = cm.Ti89.paste_keys("∫(x,x)≠π")
    f += check(not missing and codes == [189, 40, 120, 44, 120, 41, 157, 140], "89 paste: ∫ ≠ π")
    right = cm.Nspire.code_for("right")
    codes, missing = cm.Nspire.paste_keys("x^2+1")
    f += check(not missing and codes[3] == right and len(codes) == 6, "Nspire paste: x^2+1 leaves the exponent")
    codes, missing = cm.Nspire.paste_keys("√(16)+1")
    f += check(not missing and codes.count(cm.Nspire.code_for("(")) == 1 and right in codes and
               cm.Nspire.code_for(")") not in codes, "Nspire paste: √(16) closes its box with the arrow")
    codes, missing = cm.Nspire.paste_keys("3!@")
    f += check(not missing and codes[1:] == [0x210000, 0x400000], "Nspire: any ASCII as its code << 16")
    return f


def frame(w, h, dark_at):
    px = bytearray(b"\xff" * (w * h * 3))
    for x, y in dark_at:
        i = (y * w + x) * 3
        px[i:i + 3] = b"\x00\x00\x00"
    return w, h, bytes(px)


def click_checks():
    import calc_models as cm
    f = 0
    # An 84 menu: line 1 highlighted (a dark block), lines 2-4 with a number and a colon
    dots = []
    for n in range(4):
        y0 = 57 + 20 * n
        for y in range(y0 + 2, y0 + 16):
            if n == 0:
                dots += [(x, y) for x in range(0, 20)]
            else:
                dots += [(x, y) for x in range(3, 10)] + [(17, y)]
    fr = frame(320, 240, dots)
    f += check(cm.Ti84.menu_rows(fr) == (0, [0, 1, 2, 3]), "84 menu: lines found")
    f += check(cm.Ti84.click(40, 57 + 20 * 2 + 5, fr) == ["down", "down", "enter"], "84 menu: click line 3")
    f += check(cm.Ti84.click(40, 57 + 20 * 6 + 5, fr) is None, "84 menu: a line without a number does nothing")
    f += check(cm.Ti84.click(40, 100, frame(320, 240, [])) is None, "84: no menu, no click")
    # The 89's toolbar: a line under it on row 15, separators down rows 0-14
    seps = (0, 20, 49, 66, 87, 113, 144, 159)
    dots = [(x, 15) for x in range(160)] + [(x, y) for x in seps for y in range(1, 15)]
    fr = frame(160, 100, dots)
    f += check(cm.Ti89.toolbar_tabs(fr) == list(zip(seps, seps[1:])), "89 toolbar: tabs found")
    f += check([cm.Ti89.click(x, 6, fr) for x in (5, 30, 55, 100, 130)] == [["f1"], ["f2"], ["f3"], ["f5"], ["f6"]],
               "89 toolbar: a click presses its tab's F key")
    f += check(cm.Ti89.click(50, 50, fr) is None and cm.Ti89.click(50, 5, frame(160, 100, [])) is None,
               "89: below the toolbar, or no toolbar, nothing")
    f += check(cm.Nspire.click(300, 10) == ["ctrl+w"] and cm.Nspire.click(150, 150) == ["click"],
               "Nspire clicks: the X, the middle")
    return f


def library_checks():
    import program_library as pl
    f = 0
    items = pl.load()
    f += check(len(items) >= 40, "Program library: tools/program_library.json loads (%d items)" % len(items))
    for slug in ("nspire", "ti84", "ti89"):
        mine = pl.for_calc(items, slug)
        ver = [i.get("verified") for i in mine]
        f += check(mine and all(i["calculator"] == slug for i in mine) and ver == sorted(ver, reverse=True),
                   "Program library (%s): only its items, verified first" % slug)
        f += check(all(i["action"] != "download" or pl.host_ok(i["download_url"]) for i in mine),
                   "Program library (%s): downloads only from ticalc.org / GitHub" % slug)
    f += check(all(i["action"] == "ti_page" for i in items if i.get("official")),
               "Program library: TI's own apps never download")
    asm = {"calculator": "ti84", "needs_asm": True}
    f += check(pl.needs_old_os(asm, "ti84", "5.4.0")[0] is False and pl.needs_old_os(asm, "ti84", "5.8.5")[0] is True
               and pl.needs_old_os(asm, "ti84", None)[0] is None, "Program library: ASM needs OS 5.4 or older")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("readme.txt", "x")
        z.writestr("bin/LOGiCE.8xp", b"**TI83F*")
        z.writestr("src/main.c", "x")
        z.writestr("MyLib/lib.tns", b"t")
        z.writestr("Workspaces/doc.tns", b"d")
    data = buf.getvalue()
    got = pl.pick_files(data, {"calculator": "ti84", "send": [["bin/logice.8xp", None]]})
    f += check([(n, d) for n, d, _f in got] == [("LOGiCE.8xp", b"**TI83F*")], "Program library: picks files from a zip")
    got = pl.pick_files(data, {"calculator": "nspire", "send": [["mylib/*.tns", "/MyLib"], ["*.tns", "/"]]})
    f += check(sorted((n, fo) for n, _d, fo in got) == [("doc.tns", "/"), ("lib.tns", "/MyLib")],
               "Program library: Nspire files go to their folders")
    f += check(pl.USER_AGENT.startswith("CalcSuite/1.0 (+https://github.com/paul-kratky/CalcSuite)"),
               "Program library: an honest User-Agent")
    return f


def strip_checks():
    import key_strip as ks
    f = 0
    fake = lambda label: (len(label) * 6, 8, b"\x01" * (len(label) * 6 * 8))
    px = ks.compose(320, ["2nd", "MATH", "ENTER"], fake)
    f += check(len(px) == 320 * ks.STRIP_H * 3 and bytes(ks.LAST) in px and bytes(ks.CAP) in px,
               "Key strip: keycaps, the newest in the accent colour")
    burn = ks.Burner(lambda: ["F1"])
    burn_mask = ks.text_mask
    ks.text_mask = fake
    try:
        w, h, rgb = ks.Burner(lambda: ["F1"])(160, 100, b"\x00" * (160 * 100 * 3))
    finally:
        ks.text_mask = burn_mask
    f += check((w, h, len(rgb)) == (320, 200 + ks.STRIP_H, 320 * (200 + ks.STRIP_H) * 3),
               "Key strip: the 89's 160 x 100 frame doubled, the strip under it")
    del burn
    return f


def migrate_checks():
    f = 0
    try:
        import mirror
    except Exception as e:  # No Tk here: say so rather than fail
        print("SKIP Documents move (mirror.py can't load: %s)" % e)
        return 0
    tmp = tempfile.mkdtemp(prefix="calcsuite_selftest_")
    try:
        old, new = os.path.join(tmp, "Nspire Mirror"), os.path.join(tmp, "CalcSuite")
        os.makedirs(os.path.join(old, "captures"))
        os.makedirs(os.path.join(new, "captures"))
        for p, t in ((os.path.join(old, "captures", "a.png"), "old a"),
                     (os.path.join(old, "captures", "b.png"), "old b"),
                     (os.path.join(new, "captures", "b.png"), "new b")):
            with open(p, "w") as fh:
                fh.write(t)
        n = mirror.migrate_documents(old, new)
        with open(os.path.join(new, "captures", "b.png")) as fh:
            kept = fh.read() == "new b"
        f += check(n == 1 and kept and os.path.isfile(os.path.join(new, "captures", "a.png")) and
                   os.path.isfile(os.path.join(old, "captures", "a.png")) and
                   os.path.isfile(os.path.join(old, "Moved to CalcSuite.txt")),
                   "Documents move: copies, never overwrites or deletes, leaves a note")
        f += check(mirror.migrate_documents(old, new) is None, "Documents move: only once")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return f


def main():
    f = 0
    for fn in (markdown_checks, key_checks, click_checks, library_checks, strip_checks, migrate_checks):
        f += fn()
    return f


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    failures = main()
    print("\n%s" % ("ALL PASSED" if not failures else "%d FAILURE(S)" % failures))
    sys.exit(1 if failures else 0)
