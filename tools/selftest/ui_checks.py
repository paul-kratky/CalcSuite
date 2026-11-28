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
    f += nspire_symbol_checks()
    return f


def nspire_symbol_checks():
    """The Nspire's Symbols buttons and pasted symbols press its own keys, never a spelling"""
    import calc_models as cm
    N = cm.Nspire
    f = 0
    c = N.code_for
    cas = {"name": "TI-Nspire CX II CAS", "hw_type": "0x1c (unknown)"}
    plain = {"name": "TI-Nspire CX II", "hw_type": "0x1d (unknown)"}

    def keys(sym, info=cas):
        return list(N.keys_for(sym, info))

    want = {"∫": ["menu", "4", "3"], "d/dx": ["menu", "4", "1"], "Σ": ["menu", "4", "5"],
            "√": ["ctrl+square"], "π": ["pi"], "→": ["ctrl+var"], "E": ["ee"], "²": ["square"],
            "‾": ["neg"], "°": ["°"], "±": ["±"], "×": ["*"], "÷": ["/"], "^": ["^"], "!": ["!"]}
    got = {s: keys(s) for s in want}
    f += check(got == want, "Nspire Symbols: own keys; templates from menu 4 Calculus (%s)" %
               [s for s in want if got[s] != want[s]])
    f += check([keys(s, plain) for s in ("∫", "d/dx", "Σ")] ==
               [["menu", "4", "2"], ["menu", "4", "1"], ["menu", "4", "3"]] and
               keys("∫", {"name": "Mine", "hw_type": "0x1c (unknown)"}) == want["∫"] and
               keys("∫", {}) == want["∫"],
               "Nspire Symbols: a CX II without CAS gets its own Calculus numbers; unknown is a CAS")
    cells = {"θ": (0, 5), "∞": (0, 4), "≤": (1, 6), "≥": (1, 8), "≠": (1, 4), "i": (0, 2),
             "e": (0, 1), "∠": (1, 2), "⁻¹": (5, 9), "►": (0, 8)}
    f += check(all(getattr(N.keys_for(s), "cell", None) == rc for s, rc in cells.items()) and
               all(keys(s)[:2] == ["catalog", "4"] and keys(s)[-1] == "enter" for s in cells),
               "Nspire Symbols: the rest walk the symbol palette (catalog 4) to their cell")
    f += check(N.keys_for("|x|") == "abs(" and isinstance(N.keys_for("∫"), cm.TemplateKeys),
               "Nspire Symbols: |x| types abs( (the template tab's cell opened Create a Matrix on the bench)")
    spelled = [s for s, _w, k, _n in N.SYMBOLS if s != "|x|" and (isinstance(k, str) or
               (k and len(k) == 1 and len(k[0]) > 1 and N.code_for(k[0]) is None))]
    f += check(not spelled and all(cm.symbol_codes(N, keys(s)) for s, _w, _k, _n in N.SYMBOLS),
               "Nspire Symbols: every button but |x| is key presses with codes, none a spelling (%s)" % spelled)
    f += check(c("ctrl+square") == 0x009200 and c("ctrl+var") == 0x00A800 and c("ee") == 0x00A400,
               "Nspire keys: ctrl x², ctrl var and EE are TILP's codes")
    # Pasted symbols: the same keys; no @ spellings, no <= /= =: infinity
    at, lt, eq, slash = c("@"), c("<"), c("="), c("/")

    def paste(text, info=cas):
        codes, missing = N.paste_keys(text, info)
        return list(codes), missing

    codes, missing = paste("x≤3")
    walk = cm.symbol_codes(N, keys("≤"))
    f += check(not missing and codes == [c("x")] + walk + [c("3")] and lt not in codes,
               "Nspire paste: ≤ walks the palette (no <=)")
    codes, missing = paste("5→a")
    f += check(not missing and codes == [c("5"), c("ctrl+var"), c("a")], "Nspire paste: → is ctrl var")
    codes, missing = paste("2ᴇ3+\U0001d456+ℯ+∠+►+°+∞+≠+θ+π+x²+x⁻¹")
    f += check(not missing and at not in codes and eq not in codes and slash not in codes and
               c("ee") in codes and c("pi") in codes and c("square") in codes and
               c("^") not in codes and 0xB00000 in codes and codes.count(c("catalog")) == 8,
               "Nspire paste: 𝑖 ℯ ∠ ► ∞ ≠ θ ⁻¹ from the palette, ᴇ π ² ° by their keys, no @ spellings")
    codes, missing = paste("∫(x^2,x)")
    f += check(not missing and codes[:9] == [c(ch) for ch in "integral("] and c("menu") not in codes,
               "Nspire paste: ∫( stays TI's function form integral( (its arguments follow)")
    codes, missing = paste("∫")
    f += check(not missing and codes == [c("menu"), c("4"), c("3")], "Nspire paste: a lone ∫ is the template")
    codes, missing = paste("Σ", plain)
    f += check(not missing and codes == [c("menu"), c("4"), c("3")], "Nspire paste: Σ on a CX II without CAS")
    # A long paste is cut into commands between symbols, never inside a palette walk
    codes, _m = N.paste_keys("1+∞+" * 6 + "x≠2")
    runs = cm.chunks(codes, 64)
    spans, i = [], 0
    while i < len(codes):
        if codes[i] == c("catalog"):
            j = codes.index(c("enter"), i)
            spans.append((i, j))
            i = j
        i += 1
    cuts, n = [], 0
    for r in runs[:-1]:
        n += len(r)
        cuts.append(n)
    f += check(sum(runs, []) == list(codes) and len(runs) > 1 and all(len(r) <= 200 for r in runs) and
               len(spans) == 7 and not any(a < k <= b for k in cuts for a, b in spans),
               "Nspire paste: a long paste is cut between symbols (%d runs)" % len(runs))
    f += check(cm.chunks(list(range(130)), 64) == [list(range(64)), list(range(64, 128)), [128, 129]],
               "Paste runs: the 84's and 89's keys are cut every 64 as before")
    # The switch back to the bench-tested ways
    old = cm.NSPIRE_UNTRIED_KEYS
    try:
        cm.NSPIRE_UNTRIED_KEYS = False
        f += check(getattr(N.keys_for("√"), "cell", None) == (2, 9) and
                   getattr(N.keys_for("→"), "cell", None) == (0, 6) and
                   getattr(N.keys_for("E"), "cell", None) == (0, 3) and N.keys_for("|x|") == "abs(" and
                   c("ctrl+var") not in N.paste_keys("5→a")[0],
                   "Nspire: NSPIRE_UNTRIED_KEYS = False goes back to the palette and abs(")
    finally:
        cm.NSPIRE_UNTRIED_KEYS = old
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
        secs = [s for s, _g in pl.by_section(mine)]
        f += check(all(i.get("section") in pl.SECTIONS for i in mine) and "Games" in secs and
                   len(dict(pl.by_section(mine))["Games"]) >= 5 and
                   sum(len(g) for _s, g in pl.by_section(mine)) == len(mine),
                   "Program library (%s): every item in a known section, games among them (%s)" % (slug, secs))
        f += check(all(i.get("license") and i.get("info_url") and i.get("send") for i in mine),
                   "Program library (%s): every item has a licence note, a page and what it sends" % slug)
    f += check(all(i["action"] == "ti_page" for i in items if i.get("official")),
               "Program library: TI's own apps never download")
    ids = [i["id"] for i in items]
    f += check(len(ids) == len(set(ids)), "Program library: ids are unique")
    some = [{"name": "Beam Diagram", "description": "shear and moment", "section": "Mechanical"},
            {"name": "Tetris", "description": "falling blocks", "section": "Games"}]
    f += check([i["name"] for i in pl.search(some, "SHEAR beam")] == ["Beam Diagram"] and
               [i["name"] for i in pl.search(some, "games")] == ["Tetris"] and
               len(pl.search(some, "  ")) == 2 and not pl.search(some, "beam tetris"),
               "Program library: search by name, description and section, every word")
    f += check([s for s, _g in pl.by_section(some + [{"name": "x", "section": "Odd"}])] ==
               ["Mechanical", "Games", "Odd"], "Program library: sections in their order, unknown ones last")
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


def get_all_checks():
    """Get programs > Get all: which items, their notes, the totals against the free space"""
    import calc_files as cf
    import program_library as pl
    f = 0
    items = pl.load()
    for slug in ("nspire", "ti84", "ti89"):
        send, skip = pl.get_all_plan(items, slug)
        mine = pl.for_calc(items, slug)
        f += check(len(send) + len(skip) == len(mine) and send and all(
            i["action"] == "download" and pl.host_ok(i["download_url"]) for i in send),
            "Get all (%s): %d to send, %d left out, nothing lost" % (slug, len(send), len(skip)))
        f += check(all(i["action"] != "download" or i.get("section") == "Games" for i, _r in skip)
                   and all(r for _i, r in skip),
                   "Get all (%s): only page, TI and game items left out, each with a reason" % slug)
    send84, skip84 = pl.get_all_plan(items, "ti84")
    ids84 = {i["id"] for i in send84}
    f += check("ce-khicas" in {i["id"] for i, _r in skip84} and not any(i.get("official") for i in send84),
               "Get all (ti84): KhiCAS (install steps) and TI's apps aren't sent")
    fake = [{"id": "a", "calculator": "ti84", "action": "download", "download_url":
             "https://www.ticalc.org/pub/a.zip", "name": "A"},
            {"id": "b", "calculator": "ti84", "action": "download", "download_url":
             "https://example.com/b.zip", "name": "B"},
            {"id": "c", "calculator": "ti84", "action": "ti_page", "name": "C", "official": True}]
    s, k = pl.get_all_plan(fake, "ti84")
    f += check([i["id"] for i in s] == ["a"] and sorted(i["id"] for i, _r in k) == ["b", "c"],
               "Get all: a download from another site is left out")
    f += check(pl.size_hint({"size": "71,077 B zip / 2,969 B program"}) == 2969 and
               pl.size_hint({"size": "568,975 B zip / 23,532 B .tns"}) == 23532 and
               pl.size_hint({"size": "71,664 B zip"}) is None and pl.size_hint({}) is None,
               "Get all: sizes from the list only when they're the program's")
    cesium = next(i for i in send84 if i["id"] == "ce-cesium")
    fl = pl.item_flags(cesium, "ti84", "5.8.2", 70000, ids84)
    f += check(("warn", "ASM: needs arTIfiCE on OS 5.8.2") in fl and
               any("run it once" in t for _l, t in fl), "Get all: ASM on OS 5.8 needs arTIfiCE; Cesium installs once")
    f += check(not any("ASM" in t for _l, t in pl.item_flags(cesium, "ti84", "5.4.0", 70000, ids84)),
               "Get all: no ASM flag on OS 5.4")
    f += check(any(l == "note" and "ASM" in t for l, t in pl.item_flags(cesium, "ti84", None, None, ids84)),
               "Get all: an unknown OS gets a note, not a warning")
    cedit = next(i for i in send84 if i["id"] == "ce-cedit")
    f += check(("note", "uses ce-clibs (in this set)") in pl.item_flags(cedit, "ti84", "5.4.0", 1, ids84)
               and ("warn", "needs ce-clibs (likely)") in pl.item_flags(cedit, "ti84", "5.4.0", 1, set()),
               "Get all: a dependency in the set is fine, one outside it is a warning")
    lib = next(i for i in pl.get_all_plan(items, "nspire")[0] if i["id"] == "nsp-mathlib")
    f += check(any("Refresh Libraries" in t for _l, t in pl.item_flags(lib, "nspire", None, 10)),
               "Get all: Nspire libraries say Refresh Libraries")
    f += check(any(t.startswith("large") for _l, t in pl.item_flags({}, "ti89", None, 600 * 1024)) and
               not pl.item_flags({}, "ti89", None, 10 * 1024), "Get all: a large item is flagged")
    big = {"special_handling": "Large: check memory first."}
    f += check(pl.item_flags(big, "ti89", None, None) and not pl.item_flags(big, "ti89", None, 20000),
               "Get all: the list's 'large' counts until the item is measured")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("cst-1.3/cst-1.3.89g/cst.89p", b"p")
        z.writestr("cst-1.3/cst-1.3-tools/kerno31/KerNO.89z", b"z")
    got = pl.pick_files(buf.getvalue(), {"calculator": "ti89", "send": [["cst-1.3.89g/*.89?", None]]})
    f += check([n for n, _d, _f in got] == ["cst.89p"], "Program library: a pattern matches inside a wrapping folder")
    prog = cf.ti8x_bytes([(0x05, b"ZZA", 0, False, b"\x01" * 100)])
    arch = cf.ti8x_bytes([(0x15, b"ZZB", 0, True, b"\x02" * 300)])
    f += check(pl.file_place(prog, "ti84") == ("ram", len(prog)) and
               pl.file_place(arch, "ti84") == ("archive", len(arch)) and
               pl.file_place(cf.ti89_bytes(0x12, b"main", b"zzc", True, b"\x00" * 40), "ti89")[0] == "archive"
               and pl.file_place(b"x" * 9, "nspire") == ("storage", 9),
               "Get all: a TI file's header says RAM or archive")
    info = {"ram_free": "150000", "storage_free": "3000000"}
    f += check(pl.fit_check(100000, 2000000, info, "ti84")[0] is True and
               pl.fit_check(200000, 100000, info, "ti84")[0] is None and
               pl.fit_check(100000, 4000000, info, "ti84")[0] is False and
               pl.fit_check(1, 1, {}, "ti84")[0] is None,
               "Get all: RAM and archive totals against the free space")
    f += check(pl.fit_check(0, 900, {"storage_free": "1000"}, "nspire")[0] is True and
               pl.fit_check(0, 1100, {"storage_free": "1000"}, "nspire")[0] is False,
               "Get all: the Nspire's storage")
    f += check(pl.nspire_clashes([("Bode.tns", "/"), ("lib.tns", "/MyLib"), ("x.tns", "/")],
                                 {"/": {"bode.tns"}, "/MyLib": set()}) == ["Bode.tns"],
               "Get all: names already on the Nspire (any case)")
    f += check(pl.save_dir_name({"name": 'KhiCAS (χCAS): "a/b"?'}) == "KhiCAS (χCAS)_ _a_b__" and
               pl.save_dir_name({"name": " . ", "id": "x"}) == "x", "Get all: safe folder names on the PC")
    tmp = tempfile.mkdtemp(prefix="calcsuite_getall_")
    try:
        item = {"calculator": "ti84", "download_url": "https://www.ticalc.org/pub/zz.zip",
                "send": [["*.8xp", None]]}
        f += check(pl.cached_files(item, tmp) is None, "Get all: nothing cached, no network")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("ZZA.8xp", prog)
            z.writestr("readme.txt", "x")
        with open(pl.cache_path(item["download_url"], tmp), "wb") as fh:
            fh.write(buf.getvalue())
        got = pl.cached_files(item, tmp)
        f += check(got and [(n, d) for n, d, _f in got] == [("ZZA.8xp", prog)],
                   "Get all: a cached download gives its files without the network")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
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
    for fn in (markdown_checks, key_checks, click_checks, library_checks, get_all_checks, strip_checks,
               migrate_checks):
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
