"""The PC copy's emulator tab, its guide and Test in PC copy, without a GUI or a real CEmu:

- emu_host: the window styles a hosted window gets (and gets back), where it goes in the frame,
  which window of a process is the emulator's, and EmuSession's whole life (start, its window
  appearing, embedded, a window Qt rebuilt, own window and back, closed by the user, closed by
  CalcSuite, a process that never shows a window, one that won't close) with a fake process and
  a fake window API
- emu_tabs: CEmu's settings for the tab (made in CalcSuite's folder, the minimal layout, nothing
  from the user's own CEmu), Qt's saved state and geometry, fresh or carry on
- emulator_keys and docs/EMULATORS.md: the guide's key tables are the module's tables, the guide
  is registered (the side panel, the PDF builder, the app's files) and its PDF is built
- portable: the emulators' folders resolve inside CalcSuite files
- pc_test: key scripts, the autotester's JSON, CEmu's output, a whole run with a faked CEmu
- the PC copy made in its tab: "Done: 100%", the bar full, the emulator starts by itself

    python -I tools/selftest/emu_checks.py
"""

import json
import os
import shutil
import struct
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
KIT = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)


def check(ok, what):
    print("%-4s %s" % ("PASS" if ok else "FAIL", what))
    return 0 if ok else 1


# ---- emu_host ----
class FakeProc(object):
    def __init__(self, pid=4242, closes=True):
        self.pid, self.code, self.closes = pid, None, closes
        self.terminated = False

    def poll(self):
        return self.code

    def terminate(self):
        self.terminated = True
        self.code = 1

    kill = terminate

    def wait(self, timeout=None):
        if self.code is None:
            raise RuntimeError("still running")
        return self.code


class FakeWin(object):
    """Windows' side: top-level windows of processes, styles, parents, rectangles"""

    def __init__(self):
        import emu_host as eh
        self.eh = eh
        self.wins = {}  # hwnd -> dict(pid, title, style, ex, parent, rect, visible, owner)
        self.closed = []
        self.refuse_parent = False
        self.focused = None

    def add(self, hwnd, pid, title, w=500, h=700):
        eh = self.eh
        self.wins[hwnd] = dict(pid=pid, title=title, style=eh.WS_VISIBLE | eh.WS_CAPTION | eh.WS_THICKFRAME |
                               eh.WS_SYSMENU | eh.WS_MINIMIZEBOX | eh.WS_MAXIMIZEBOX,
                               ex=eh.WS_EX_WINDOWEDGE | eh.WS_EX_APPWINDOW, parent=0, rect=(100, 100, w, h),
                               visible=True, owner=0)

    def windows_of(self, pid):
        return [{"hwnd": h, "title": d["title"], "visible": d["visible"], "owner": d["owner"],
                 "w": d["rect"][2], "h": d["rect"][3]}
                for h, d in self.wins.items() if d["pid"] == pid and not d["parent"]]

    def alive(self, hwnd):
        return hwnd in self.wins

    def style(self, hwnd):
        return self.wins[hwnd]["style"]

    def exstyle(self, hwnd):
        return self.wins[hwnd]["ex"]

    def set_styles(self, hwnd, style, ex):
        self.wins[hwnd]["style"], self.wins[hwnd]["ex"] = style, ex

    def parent(self, hwnd):
        return self.wins[hwnd]["parent"] if hwnd in self.wins else 0

    def set_parent(self, hwnd, parent):
        if parent and self.refuse_parent:
            return False
        self.wins[hwnd]["parent"] = parent or 0
        return True

    def rect(self, hwnd):
        x, y, w, h = self.wins[hwnd]["rect"]
        return x, y, x + w, y + h

    def child_rect(self, hwnd):
        return self.wins[hwnd]["rect"]

    def move(self, hwnd, x, y, w, h):
        self.wins[hwnd]["rect"] = (x, y, w, h)

    def redraw(self, hwnd):
        pass

    def show(self, hwnd, how=5):
        self.wins[hwnd]["visible"] = how != 0

    def focus(self, hwnd):
        self.focused = hwnd
        return True

    def foreground(self, hwnd):
        pass

    def close(self, hwnd):
        self.closed.append(hwnd)
        return True


def host_checks():
    import emu_host as eh
    f = 0
    top = eh.WS_VISIBLE | eh.WS_CAPTION | eh.WS_THICKFRAME | eh.WS_SYSMENU | eh.WS_MAXIMIZEBOX | eh.WS_MAXIMIZE
    ch = eh.child_style(top)
    f += check(ch & eh.WS_CHILD and ch & eh.WS_VISIBLE and not ch & (eh.WS_CAPTION | eh.WS_THICKFRAME |
               eh.WS_SYSMENU | eh.WS_MAXIMIZEBOX | eh.WS_MAXIMIZE | eh.WS_POPUP),
               "emu_host: a hosted window: WS_CHILD, still visible, no caption/border/menu/maximized")
    f += check(not eh.child_exstyle(eh.WS_EX_APPWINDOW | eh.WS_EX_CLIENTEDGE | 0x8) & (
        eh.WS_EX_APPWINDOW | eh.WS_EX_CLIENTEDGE) and eh.child_exstyle(0x8) == 0x8,
        "emu_host: no taskbar button or edges, other extended styles kept")
    back = eh.top_style(ch, top)
    f += check(not back & eh.WS_CHILD and back & eh.WS_CAPTION and back & eh.WS_THICKFRAME and
               not back & eh.WS_MAXIMIZE, "emu_host: given back: its own caption and border, not WS_CHILD")
    f += check(eh.top_style(eh.WS_CHILD | eh.WS_VISIBLE, None) & eh.WS_CAPTION and
               eh.child_style(0x80000000 | eh.WS_CAPTION) & 0x80000000 == 0,
               "emu_host: a window never hosted gets an ordinary frame; WS_POPUP goes as a child")
    f += check(eh.fit_rect(800, 600) == (0, 0, 800, 600) and eh.fit_rect(0, -5) == (0, 0, 1, 1) and
               eh.fit_rect(1000, 700, 0.6) == (290, 0, 420, 700) and eh.fit_rect(300, 900, 0.6) == (0, 200, 300, 500),
               "emu_host: fills the frame, or the biggest calculator-shaped box, centred")
    f += check(eh._signed(0x80000000 | eh.WS_CHILD) < 0 and eh._signed(eh.WS_CHILD) == eh.WS_CHILD,
               "emu_host: styles as SetWindowLongPtrW's signed value")
    wins = [{"hwnd": 1, "title": "Information", "visible": True, "owner": 0, "w": 500, "h": 200},
            {"hwnd": 2, "title": "", "visible": False, "owner": 0, "w": 2000, "h": 1000},
            {"hwnd": 3, "title": "CEmu | CalcSuite", "visible": True, "owner": 0, "w": 400, "h": 700},
            {"hwnd": 4, "title": "Default IME", "visible": False, "owner": 3, "w": 0, "h": 0}]
    f += check(eh.pick_window(wins, r"^CEmu \| CalcSuite$") == 3 and eh.pick_window(wins) == 3 and
               eh.pick_window(wins[:2], r"^CEmu") is None,
               "emu_host: the emulator's window: visible, unowned, titled (not CEmu's welcome box)")
    return f + session_checks()


def session_checks():
    import emu_host as eh
    f = 0
    clock = [0.0]
    states = []
    win = FakeWin()
    host = [(900, 1000, 700)]
    procs = []

    def popen():
        p = FakeProc(4242 + len(procs))
        procs.append(p)
        return p
    s = eh.EmuSession(win, lambda: host[0], popen, title_re=r"^CEmu \| CalcSuite$",
                      clock=lambda: clock[0], on_change=lambda st, why: states.append((st, why)), aspect=None)
    s.start()
    f += check(s.state == eh.STARTING and s.poll() == eh.STARTING, "session: starting until its window appears")
    win.add(77, s.pid(), "CEmu | CalcSuite")
    clock[0] = 1
    s.poll()
    w = win.wins[77]
    f += check(s.state == eh.EMBEDDED and w["parent"] == 900 and w["style"] & eh.WS_CHILD and
               not w["style"] & eh.WS_CAPTION and w["rect"] == (0, 0, 1000, 700),
               "session: its window goes into the frame, as a child, filling it")
    host[0] = (900, 800, 500)
    s.fit()
    f += check(w["rect"] == (0, 0, 800, 500), "session: the frame resized: so is the window")
    w["rect"] = (40, 40, 300, 300)  # Qt moved itself
    clock[0] = 2
    s.poll()
    f += check(w["rect"] == (0, 0, 800, 500), "session: a window that moves itself is put back")
    s.focus()
    f += check(win.focused == 77, "session: the keyboard to it")
    s.pop_out((10, 20, 800, 500))
    f += check(s.state == eh.OWN and w["parent"] == 0 and w["style"] & eh.WS_CAPTION and not w["style"] & eh.WS_CHILD
               and w["rect"] == (10, 20, 500, 700), "session: own window: its frame and its old size, where the tab was")
    f += check(s.dock() and s.state == eh.EMBEDDED and w["parent"] == 900, "session: back into the tab")
    # Qt made a new main window (its flags changed): the old one goes, a new one appears
    del win.wins[77]
    win.add(78, s.pid(), "CEmu | CalcSuite")
    clock[0] = 3
    s.poll()
    f += check(s.state == eh.EMBEDDED and win.wins[78]["parent"] == 900 and s.adoptions == 1,
               "session: a window Qt rebuilt is taken in again")
    # The user closes it (File > Exit)
    procs[-1].code = 0
    s.poll()
    f += check(s.state == eh.CLOSED and "closed" in s.why, "session: closed by the user: the tab says so")
    # Open again, then CalcSuite closes it: WM_CLOSE first, given back hidden
    s.start()
    win.add(79, s.pid(), "CEmu | CalcSuite")
    s.poll()
    s.close()
    f += check(win.closed[-1] == 79 and win.wins[79]["parent"] == 0 and not win.wins[79]["visible"],
               "session: closing: given back hidden, then WM_CLOSE (CEmu saves its state)")
    clock[0] = 3 + eh.CLOSE_WAIT_S + 1
    s.poll()
    f += check(procs[-1].terminated, "session: one that doesn't close in time is ended (only its own process)")
    s.poll()
    f += check(s.state == eh.CLOSED and "CalcSuite" in s.why, "session: closed by CalcSuite")
    # Never a window
    s2 = eh.EmuSession(FakeWin(), lambda: host[0], lambda: FakeProc(1), clock=lambda: clock[0], window_wait=5)
    s2.start()
    clock[0] += 10
    f += check(s2.poll() == eh.FAILED and "didn't appear" in s2.why, "session: no window in time: failed, says why")
    # Windows refuses the parent: it stays beside CalcSuite
    w3 = FakeWin()
    w3.refuse_parent = True
    s3 = eh.EmuSession(w3, lambda: host[0], lambda: FakeProc(5), clock=lambda: clock[0])
    s3.start()
    w3.add(90, 5, "TiEmu")
    s3.poll()
    f += check(s3.state == eh.OWN and w3.wins[90]["parent"] == 0 and w3.wins[90]["style"] & eh.WS_CAPTION,
               "session: embedding refused: a normal window beside CalcSuite (the fallback)")
    # embed=False: beside the window from the start
    s4 = eh.EmuSession(FakeWin(), lambda: host[0], lambda: FakeProc(6), clock=lambda: clock[0], embed=False)
    s4.start()
    s4.win.add(91, 6, "TiEmu")
    f += check(s4.poll() == eh.OWN, "session: embed=False opens it beside the window")
    # A start that fails
    s5 = eh.EmuSession(FakeWin(), lambda: host[0], lambda: (_ for _ in ()).throw(OSError("zz missing")))
    f += check(not s5.start() and s5.state == eh.FAILED and "zz missing" in s5.why, "session: a failed start says why")
    # close_wait (CalcSuite closing)
    w6 = FakeWin()
    p6 = FakeProc(7)
    s6 = eh.EmuSession(w6, lambda: host[0], lambda: p6)
    s6.start()
    w6.add(92, 7, "CEmu")
    s6.poll()
    threading.Timer(0.1, lambda: setattr(p6, "code", 0)).start()
    f += check(s6.close_wait(timeout=3) == "closed" and s6.state == eh.CLOSED, "session: close_wait: it closes")
    return f


# ---- emu_tabs: CEmu's settings ----
def settings_checks():
    import emu_tabs as et
    f = 0
    tmp = tempfile.mkdtemp(prefix="calcsuite_emu_")
    try:
        rom = os.path.join(tmp, "ti84ce-zz.rom")
        text = et.cemu_settings_text(tmp, rom, "v2.0", panels=False)
        g = lambda k: et.ini_get(text, k)  # noqa: E731
        f += check(g("General/image_path") == tmp.replace("\\", "/") + "/cemu_image.ce" and
                   g("Debugger/image_path").startswith(tmp.replace("\\", "/")) and g("General/rom_path") ==
                   rom.replace("\\", "/"), "CEmu settings: its state, debug file and the ROM in CalcSuite's folder")
        f += check(g("General/check_for_updates") == "0" and g("Recent/save_paths") == "false" and
                   g("General/first_run") == "true" and g("General/version") == "v2.0" and
                   g("Keypad/map") == "cemu" and g("CalcSuite/settings") == et.SETTINGS_MARK,
                   "CEmu settings: no update check, no remembered transfers, no welcome box, the CEmu keys")
        f += check(g("General/ui_edit_mode") == "false" and g("Window/menubar") == "true" and
                   g("Window/state", ).startswith('"@ByteArray(') and g("Window/geometry"),
                   "CEmu settings: just the calculator (docks locked, menu bar hidden, a saved layout)")
        p = et.cemu_settings_text(tmp, rom, panels=True)
        f += check(et.ini_get(p, "Window/state") is None and et.ini_get(p, "General/ui_edit_mode") == "true" and
                   et.ini_get(p, "Window/menubar") == "false", "CEmu settings: CEmu's panels: its own layout and menus")
        st = et.cemu_layout_state()
        f += check(st[:9] == struct.pack(">ii", 0xFF, 0) + b"\xfd" and st.count(b"\xfb") == len(et.CEMU_DOCKS) and
                   st.endswith(b"\xfc\x00\x00\x00\x00"), "Qt's saved state: every CEmu dock, the tool bar list")
        # The screen and keypad visible, every other dock hidden and floating
        vis = []
        for name in et.CEMU_DOCKS:
            q = et._qstring(name)
            i = st.index(b"\xfb" + q) + 1 + len(q)
            vis.append(st[i])
        f += check(vis[:2] == [1, 1] and set(vis[2:]) == {2}, "Qt's saved state: screen and keypad shown, the rest hidden")
        geo = et.cemu_geometry()
        f += check(len(geo) == 66 and geo[:8] == bytes.fromhex("01d9d0cb00030000"),
                   "Qt's saved geometry: format 3.0, 66 bytes (else CEmu opens every dock)")
        f += check(et.qt_bytearray(b"\x00\xff") == '"@ByteArray(\\x0\\xff)"', "a QByteArray as Qt's INI has it")
        t2 = et.ini_set("[A]\nx=1\ny=2\n\n[B]\nz=3\n", {"A/x": "9", "A/y": None, "C/w": "4"}, drop=("B",))
        f += check(t2 == "[A]\nx=9\n\n[C]\nw=4\n", "INI edits: set, remove, add, drop a section")
        ini = et.prepare_cemu_settings(rom, tmp)
        with open(ini, encoding="utf-8") as fh:
            t = fh.read()
        with open(ini, "w", encoding="utf-8") as fh:  # What CEmu writes when it remembers transfers
            fh.write(t.replace("[Recent]\nsave_paths=false", "[Recent]\nsave_paths=true\npaths=C:\\\\zz\\\\a.8xp"))
        et.prepare_cemu_settings(rom, tmp, panels=True)
        text3 = open(ini, encoding="utf-8").read()
        f += check(et.ini_get(text3, "Recent/paths") is None and et.ini_get(text3, "General/ui_edit_mode") == "true",
                   "CEmu settings kept by CEmu: transfers forgotten, the layout switched when asked")
        with open(ini, "w", encoding="utf-8") as fh:
            fh.write("[General]\nimage_path=C:/Users/zz/AppData/Local/cemu-dev/CEmu/cemu_image.ce\n")
        et.prepare_cemu_settings(rom, tmp)
        f += check(et.ini_get(open(ini, encoding="utf-8").read(), "General/image_path").startswith(
            tmp.replace("\\", "/")), "CEmu settings from an older CalcSuite (the user's own copied) are made again")
        f += check(et.start_fresh({}, rom, False) and et.start_fresh({"rom": "x"}, rom, True) and
                   not et.start_fresh({"rom": os.path.normcase(os.path.abspath(rom))}, rom, True),
                   "fresh the first time and after a new ROM, else CEmu carries on")
        f += check(et.cemu_scale_for(1014, 774) == 100 and et.cemu_scale_for(694, 634) == 75 and
                   et.cemu_scale_for(2000, 1400) == 125 and et.cemu_scale_for(100, 100) == 50,
                   "CEmu's screen scale: the biggest calculator that fits the tab")
        et.prepare_cemu_settings(rom, tmp, scale=75)
        f += check(et.ini_get(open(ini, encoding="utf-8").read(), "Screen/scale") == "75",
                   "CEmu's screen scale goes into its settings")
        f += check(et.cemu_env(96) == {} and et.cemu_env(144) == {"QT_QPA_PLATFORM": "windows:dpiawareness=0"},
                   "DPI: nothing at 100 %, CEmu DPI-unaware like CalcSuite above it")
        f += check(et.cemu_ipc("C:\\zz\\CEmu.exe", "--screenshot", "a.png")[1:4] == ["--id", "CalcSuite", "--screenshot"],
                   "commands for the running copy go to --id CalcSuite")
        import pc_copy
        cmd = pc_copy.emulator_command("84", rom, ["a.8xp"], emulator="C:\\zz\\CEmu.exe", fresh=True,
                                       extra=["--id", "CalcSuite", "-g", ini])
        f += check(cmd[:5] == ["C:\\zz\\CEmu.exe", "--id", "CalcSuite", "-g", ini] and "--reload-rom" in cmd and
                   cmd[-2:] == ["--send", "a.8xp"], "the tab's CEmu command line")
        f += check(pc_copy.emulator_command("89", rom, emulator="C:\\zz\\tiemu.exe") == ["C:\\zz\\tiemu.exe", "-rom=" + rom],
                   "TiEmu's command line (-rom=)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return f


# ---- The guide ----
def guide_checks():
    import emulator_keys as ek
    import ui_panels
    import emu_tabs
    f = 0
    path = os.path.join(KIT, "docs", "EMULATORS.md")
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    f += check(ek.table_rows(text, "Calculator") == [tuple(r) for r in ek.CEMU_KEYS],
               "guide: CEmu's key table is CEmu's wiki table, every key and column (emulator_keys.CEMU_KEYS)")
    f += check(len(ek.CEMU_KEYS) == 50 and all(len(r) == 4 for r in ek.CEMU_KEYS),
               "CEmu's keys: 50 calculator keys, three PC columns")
    f += check(ek.table_rows(text, "PC key") == [tuple(r) for r in ek.TIEMU_KEYS],
               "guide: TiEmu's key table is the module's (the panel's)")
    sc = ek.table_rows(text, "Keys")
    f += check(sc == [tuple(r) for r in ek.CEMU_SHORTCUTS], "guide: CEmu's shortcuts are the panel's")
    import md_render
    heads = [h for _l, h, _a in md_render.headings(md_render.parse(text))]
    f += check(heads[0] == "CalcSuite - PC copies (CEmu and TiEmu) guide" and "TiEmu's keys" in heads and
               "Testing a program in the PC copy" in heads and "Where everything is kept" in heads,
               "guide: title and sections")
    sys.path.insert(0, os.path.join(TOOLS, "docs_build"))
    try:
        import make_pdfs
        names = [g[0] for g in make_pdfs.GUIDES]
        srcs = [g[1] for g in make_pdfs.GUIDES]
    finally:
        sys.path.pop(0)
    f += check(ui_panels.EMULATOR_GUIDE_PDF in names and "docs/EMULATORS.md" in srcs and
               emu_tabs.GUIDE_PDF == ui_panels.EMULATOR_GUIDE_PDF and emu_tabs.GUIDE == ui_panels.EMULATOR_GUIDE,
               "guide: registered with the PDF builder, the panel's Guide and Calculator info")
    f += check(os.path.isfile(os.path.join(KIT, "docs", "pdf", ui_panels.EMULATOR_GUIDE_PDF)),
               "guide: its PDF is built (docs/pdf)")
    with open(os.path.join(KIT, "app.spec"), encoding="utf-8") as fh:
        spec = fh.read()
    f += check("('docs/EMULATORS.md', 'docs')" in spec, "guide: shipped with the app (app.spec)")
    links = sorted(set(l for l in __import__("re").findall(r"\]\(([^)#:]+\.md)", text)))
    f += check(all(os.path.isfile(os.path.join(KIT, "docs", l)) for l in links), "guide: its links to other guides exist")
    return f


# ---- Portable: everything inside CalcSuite files ----
def portable_checks():
    import paths
    import pc_copy
    import emu_tabs
    import pc_test
    f = 0
    tmp = tempfile.mkdtemp(prefix="calcsuite_portable_")
    saved = (paths._files, paths.app_dir)
    try:
        paths.app_dir = lambda: tmp
        paths._files = os.path.join(tmp, paths.FOLDER_NAME)
        inside = os.path.normcase(paths._files) + os.sep
        got = [pc_copy.emulators_folder(), emu_tabs.cemu_settings_folder(), pc_test.settings_folder(),
               pc_copy.roms_folder()]
        f += check(paths.is_portable() and all(os.path.normcase(g).startswith(inside) for g in got),
                   "portable: the emulators, the tab's CEmu settings and state, the tests and the ROMs are in "
                   "CalcSuite files")
    finally:
        paths._files, paths.app_dir = saved
        shutil.rmtree(tmp, ignore_errors=True)
    return f


# ---- pc_test ----
class FakeCemuProc(object):
    """A CEmu that prints the autotester's lines (CEmu 2.0's wording) and stays until closed"""

    def __init__(self, lines, delay=0.05):
        import io
        self.pid = 5151
        r, w = os.pipe()
        self.stdout = os.fdopen(r, "rb")
        self._w = os.fdopen(w, "wb")
        self.code = None

        def feed():
            for l in lines:
                time.sleep(delay)
                self._w.write((l + "\n").encode())
                self._w.flush()
        threading.Thread(target=feed, daemon=True).start()

    def poll(self):
        return self.code

    def terminate(self):
        self.code = 1
        try:
            self._w.close()
        except OSError:
            pass

    def wait(self, timeout=None):
        return self.code


def pc_test_checks():
    import pc_test as pt
    f = 0
    f += check(pt.parse_script("2, 1, Enter\nwait 500, hold alpha, release alpha, x^2, comma") ==
               ["key|2", "key|1", "key|enter", "delay|500", "hold|alpha", "release|alpha", "key|^2", "key|,"],
               "Test in PC copy: a key script -> the autotester's steps")
    try:
        pt.parse_script("enter, zzkey")
        f += check(False, "Test in PC copy: an unknown key is refused")
    except pt.TestError as e:
        f += check("zzkey" in str(e), "Test in PC copy: an unknown key is refused, named")
    cfg = pt.test_config("C:\\zz\\ZZTEST.8xp", "zztest", "2, enter", ["0xeda8daeb"], wait_ms=1000)
    f += check(cfg["target"] == {"name": "ZZTEST", "isASM": False} and cfg["transfer_files"] == ["ZZTEST.8xp"] and
               cfg["sequence"] == ["action|launch", "delay|1000", "key|2", "key|enter", "hash|screen", "hash|end"] and
               cfg["hashes"]["screen"]["expected_CRCs"] == ["EDA8DAEB"] and
               cfg["hashes"]["screen"]["start"] == "vram_start" and cfg["hashes"]["end"]["expected_CRCs"] == ["0"],
               "Test in PC copy: the autotester's JSON (launch, wait, keys, the screen's CRC, the end marker)")
    import zlib
    f += check(0 not in {zlib.crc32(bytes([b])) for b in range(256)},
               "Test in PC copy: the end check can't pass (no one-byte CRC-32 is 0)")
    for bad in ("1ABC", "TOOLONGNAME", ""):
        try:
            pt.check_name(bad)
            f += check(False, "Test in PC copy: %r refused" % bad)
        except pt.TestError:
            pass
    f += check(pt.check_name("zzθ1") == "ZZ@1", "Test in PC copy: program names (theta as @)")
    out_fail = ["C:/zz/test.json loaded and verified. 1 unique tests found.",
                '\t[Test failed!] Hash #screen ("The screen at the end") did not match the expected CRC 0 (got EDA8DAEB).',
                '\t[Test failed!] Hash #end ("CalcSuite: the end of the test") did not match the expected CRC 0 (got 1B2C3D4E).']
    r = pt.summarize(pt.parse_output(out_fail))
    f += check(r["ok"] is None and r["crc"] == "EDA8DAEB", "Test in PC copy: no expectation: the screen's real CRC")
    r = pt.summarize(pt.parse_output(out_fail), ["A0CDB485"])
    f += check(r["ok"] is False and r["crc"] == "EDA8DAEB", "Test in PC copy: another screen: failed, what came")
    r = pt.summarize(pt.parse_output([out_fail[0], out_fail[2]]), ["EDA8DAEB"])
    f += check(r["ok"] is True and r["crc"] == "EDA8DAEB",
               "Test in PC copy: the screen check silent, the end came: passed (CEmu's window prints only failures)")
    r = pt.summarize(pt.parse_output(out_fail[:1]), ["EDA8DAEB"])
    f += check(r["ok"] is False, "Test in PC copy: no end line: not passed")
    # A whole run with a faked CEmu (its window API absent, the screenshot faked)
    tmp = tempfile.mkdtemp(prefix="calcsuite_pctest_")
    saved_run = pt.subprocess.run
    try:
        prog = os.path.join(tmp, "ZZTEST.8xp")
        with open(prog, "wb") as fh:
            fh.write(b"**TI83F*zz")
        rom = os.path.join(tmp, "zz.rom")
        open(rom, "wb").close()
        started = []

        def fake_popen(cmd):
            started.append(cmd)
            return FakeCemuProc([out_fail[0], out_fail[2]])

        def fake_run(cmd, **k):  # --screenshot: the running copy saves its screen
            open(cmd[cmd.index("--screenshot") + 1], "wb").write(b"\x89PNG")
        pt.subprocess.run = fake_run
        res = pt.run_test(prog, "ZZTEST", "2, 1, enter", ["EDA8DAEB"], rom=rom, exe="C:\\zz\\CEmu.exe",
                          popen=fake_popen, win=None, folder=tmp, timeout=10)
        cmd = started[0]
        f += check(res["ok"] is True and res["screenshot"] and cmd[1:3] == ["--id", "CalcSuiteTest"] and
                   "-t" in cmd and "--no-test-dialog" in cmd and "--reload-rom" in cmd,
                   "Test in PC copy: a whole run (faked CEmu): its own CEmu id, the autotester, passed, a screenshot")
        js = json.load(open(cmd[cmd.index("-t") + 1], encoding="utf-8"))
        ini = open(cmd[cmd.index("-g") + 1], encoding="utf-8").read()
        import emu_tabs
        f += check(js["target"]["name"] == "ZZTEST" and emu_tabs.ini_get(ini, "General/save_on_close") == "false",
                   "Test in PC copy: its CEmu saves nothing (the PC copy's state isn't touched)")
        try:
            pt.run_test(prog, "ZZTEST", "", (), rom=rom, exe="C:\\zz\\CEmu.exe", win=None, folder=tmp, timeout=1,
                        popen=lambda cmd: FakeCemuProc([out_fail[0]]))
            f += check(False, "Test in PC copy: a program that never ends the test times out")
        except pt.TestError as e:
            f += check("no result within" in str(e), "Test in PC copy: a program that never ends the test times out")
    finally:
        pt.subprocess.run = saved_run
        shutil.rmtree(tmp, ignore_errors=True)
    return f


# ---- The PC copy made in its tab ----
def tab_copy_checks():
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
    except Exception as e:
        print("SKIP PC copy in its tab (no Tk here: %s)" % e)
        return 0
    import ui_panels as up
    import pc_copy as pc
    from tkinter import messagebox
    sys.path.insert(0, HERE)
    import pc_copy_checks as pcc
    f = 0
    saved = dict(ask=messagebox.askokcancel, dump=pc.dump_rom, log=up.log_error)
    made = []
    try:
        messagebox.askokcancel = lambda *a, **k: True
        up.log_error = lambda where: None

        def dump_ok(model, report=None, cancel=None, connect=None):
            for st in ("connect", "check", "backup", "send", "run", "dump", "save", "clean"):
                report(st, "step %s" % st, 1, 2)
                time.sleep(0.05)
            return {"ok": True, "rom": "C:\\zz\\ti84ce-zz.rom", "size": 4194304, "os": "5.4.0", "backup": None,
                    "notes": [], "seconds": 1, "ram_cleared": False, "missing": []}
        pc.dump_rom = dump_ok
        holder = tk.Frame(root)
        m = pcc.FakeMirror("ti84")
        d = up.PcCopyDialog(pcc.FakeSection(root, m), "make", parent=holder,
                            on_made=lambda rom, backup, auto: made.append((rom, auto)), on_close=lambda: None)
        d.start()
        t0 = time.time()
        while time.time() - t0 < 10 and not made:
            root.update()
            time.sleep(0.02)
        f += check(d.embedded and isinstance(d.win, tk.Frame) and any("Done: 100%" in t for t in pcc.texts(d.win)) and
                   d.bar_value == up.BAR_MAX and str(d.done_bar.cget("style")).startswith("CalcDone"),
                   "PC copy in its tab: when it's made it says Done: 100%, the bar full and green")
        f += check(made == [("C:\\zz\\ti84ce-zz.rom", True)] and m.reconnects == 1,
                   "PC copy in its tab: then the emulator starts there by itself; the link given back")
    finally:
        messagebox.askokcancel, pc.dump_rom, up.log_error = saved["ask"], saved["dump"], saved["log"]
        try:
            root.destroy()
        except tk.TclError:
            pass
    return f


def main():
    return host_checks() + settings_checks() + guide_checks() + portable_checks() + pc_test_checks() + \
        tab_copy_checks()


if __name__ == "__main__":
    n = main()
    print("ALL PASSED" if not n else "%d FAILED" % n)
    sys.exit(1 if n else 0)
