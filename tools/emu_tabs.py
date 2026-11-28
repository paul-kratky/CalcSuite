# SPDX-License-Identifier: MIT
"""The PC copy's emulator as a tab of the main window: "TI-84 Plus CE (PC copy)" runs CEmu
with the user's own CE ROM, "TI-89 Titanium (PC copy)" runs TiEmu with the 89's ROM.

The emulator is its own program (CEmu GPL-3.0, TiEmu GPL-2.0, never imported or linked):
CalcSuite starts it with its command line and hosts its window in the tab (emu_host.py). The
tab's side panel has the emulator's keys (emulator_keys.py, the same table as
docs/EMULATORS.md) and that guide.

CEmu in the tab has its own settings file (-g), separate from a CEmu the user starts by
itself: CalcSuite files\\cache\\emulators\\CEmu\\calcsuite\\cemu_config.ini (from the source:
%LOCALAPPDATA%\\CalcSuite\\emulators\\CEmu\\calcsuite), with its saved state beside it. CalcSuite
writes it itself (nothing from the user's own CEmu): just the calculator (Qt's saved window state
with the screen and keypad docks, every other dock hidden; the screen's scale chosen to fit the
tab), CEmu's online update check off (CalcSuite goes online only when asked), no remembered
transfers. "CEmu's panels" brings CEmu's own docks and menu bar back. --id CalcSuite names it,
so a CEmu the user runs by itself (id "Calculator") is never confused with it, and CalcSuite
sends it files and takes screenshots through CEmu's own command line (--id CalcSuite --send /
--screenshot reach the running one).

Make a PC copy runs here too: ui_panels.PcCopyDialog embedded in the tab (make_copy), then the
emulator starts in the same tab.
"""

import json
import os
import re
import struct
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox

import emu_host as eh
import emulator_keys as ek
import ui_theme as th

SPECS = {
    "ti84": {"key": "emu:ti84", "title": "TI-84 Plus CE (PC copy)", "emulator": "CEmu", "model": "84"},
    "ti89": {"key": "emu:ti89", "title": "TI-89 Titanium (PC copy)", "emulator": "TiEmu", "model": "89"},
}
TITLES = {"ti84": "TI-84 Plus CE", "ti89": "TI-89 Titanium"}
CEMU_ASPECT = 0.64  # CEmu with just the calculator (screen above keypad): width / height
CEMU_ID = "CalcSuite"
CEMU_TITLE = r"^CEmu \| CalcSuite$"
GUIDE = ("docs", "EMULATORS.md")
GUIDE_PDF = "CalcSuite - PC copies (CEmu and TiEmu) guide.pdf"
POLL_MS = 250


def key_of(slug):
    return SPECS[slug]["key"]


def is_emu_key(key):
    return isinstance(key, str) and key.startswith("emu:")


def log_error(where):
    try:
        import mirror
        mirror.log_error(where)
    except Exception:
        pass


# ---- CEmu's own settings for the tab (pure: the self-test runs these) ----
def _section_lines(text):
    """INI text -> [(section, [lines])] in order (section "" for lines before the first)"""
    out = [["", []]]
    for line in text.splitlines():
        m = re.match(r"^\s*\[([^\]]+)\]\s*$", line)
        if m:
            out.append([m.group(1), []])
        else:
            out[-1][1].append(line)
    return out


def ini_set(text, changes, drop=()):
    """INI text with keys set ({"Section/key": value}, added when missing; None removes the
    key) and whole sections dropped; Qt's own values (@ByteArray(...)) are kept as they are"""
    secs = _section_lines(text)
    want = {}
    for full, value in changes.items():
        sec, key = full.split("/", 1)
        want.setdefault(sec, {})[key] = value
    out = []
    for name, lines in secs:
        if name in drop:
            continue
        keep = []
        todo = dict(want.pop(name, {}))
        for line in lines:
            k = line.split("=", 1)[0].strip() if "=" in line else None
            if k is not None and k in todo:
                v = todo.pop(k)
                if v is not None:
                    keep.append("%s=%s" % (k, v))
            else:
                keep.append(line)
        while keep and not keep[-1].strip():
            keep.pop()
        keep += ["%s=%s" % (k, v) for k, v in todo.items() if v is not None]
        if name:
            out.append("[%s]" % name)
        if name or keep:
            out += keep + [""]
    for name, todo in want.items():
        items = ["%s=%s" % (k, v) for k, v in todo.items() if v is not None]
        if items:
            out += ["[%s]" % name] + items + [""]
    while out and not out[0].strip():
        out.pop(0)
    return "\n".join(out).rstrip("\n") + "\n"


# CEmu 2.0's docks (their Qt object names, as its saved window state lists them)
CEMU_DOCKS = ("screenDock", "keypadWidget_dock", "variablesWidget_dock", "captureWidget_dock",
              "settingsWidget_dock", "consoleWidget_dock", "stateWidget_dock",
              "tab_tibasic_debugger_dock", "debugControlWidget_dock", "debugCpuStatusWidget_dock",
              "debugDisassemblyWidget_dock", "debugMemoryWidget_dock", "debugTimerWidget_dock", "tab_dock",
              "tab_6_dock", "tab_7_dock", "debugOsWidget_dock", "debugOsStacksWidget_dock",
              "debugMiscWidget_dock", "debugAutoTesterWidget_dock")
QT_MAX = 0x00FFFFFF  # QWIDGETSIZE_MAX
SETTINGS_MARK = "2"  # [CalcSuite] settings=2 in the file: made by this version (CEmu keeps unknown keys)


def _qstring(s):
    b = s.encode("utf-16-be")
    return struct.pack(">I", len(b)) + b


def cemu_layout_state(screen=(440, 330), keypad=440):
    """Qt's saved window state (QMainWindow::saveState) for CEmu with just the calculator: the
    screen dock above the keypad dock, every other dock hidden. The format, as CEmu 2.0 (Qt 6)
    writes it: version marker, the dock areas (area, size, then a sequence of dock widgets:
    name, visible, position, size, minimum, maximum), the central widget's size, the corners and
    the (empty) tool bar list."""
    w, h_screen = screen
    items = [b"\xfb" + _qstring("screenDock") + b"\x01" + struct.pack(">iiii", 0, h_screen, 120, QT_MAX),
             b"\xfb" + _qstring("keypadWidget_dock") + b"\x01" +
             struct.pack(">iiii", h_screen + 4, keypad, 120, QT_MAX)]
    for name in CEMU_DOCKS[2:]:
        # Hidden *and floating*: hidden docks kept in the layout came back on screen in CEmu 2.0
        # (tried 2026-11-28); floating ones stay hidden, and Docks (right-click) shows one as its
        # own small window
        items.append(b"\xfb" + _qstring(name) + b"\x02" + struct.pack(">iiii", 120, 120, 480, 360))
    height = h_screen + 4 + keypad
    out = struct.pack(">ii", 0xFF, 0)                      # QMainWindow's version marker, version 0
    out += b"\xfd" + struct.pack(">i", 1)                  # The dock areas: one
    out += struct.pack(">iii", 0, w, height)               # The left area and its size
    out += b"\xfc\x02" + struct.pack(">i", len(items))     # A vertical sequence of the docks
    out += b"".join(items)
    out += struct.pack(">ii", 0, height)                   # The central widget (CEmu hides it)
    out += struct.pack(">iiii", 4, 4, 1, 2)                # The corners (Qt's defaults)
    out += b"\xfc" + struct.pack(">i", 0)                  # No tool bars
    return out


def cemu_geometry(x=100, y=100, w=520, h=780, screen_width=1920):
    """Qt's saved window geometry (QWidget::saveGeometry, format 3.0). CEmu uses its saved dock
    layout only when this one restores too (else it opens every dock), so the minimal layout
    needs it; where the window is doesn't matter (the tab places it)."""
    rect = struct.pack(">iiii", x, y, x + w - 1, y + h - 1)
    return (struct.pack(">IHH", 0x01D9D0CB, 3, 0) + rect + rect + struct.pack(">iBBi", 0, 0, 0, screen_width)
            + rect)


def qt_bytearray(b):
    """A QByteArray as Qt writes it in an INI file: "@ByteArray(\\x..)", every byte escaped"""
    return '"@ByteArray(%s)"' % "".join("\\x%x" % c for c in b)


def cemu_settings_text(folder, rom, version="v2.0", panels=False):
    """CEmu's settings for the tab, all in CalcSuite's own folder (nothing from the user's own
    CEmu): its saved state and debug file there, the ROM, CEmu's online update check off, no
    remembered transfers. panels=False: just the calculator (screen above keypad, every other
    dock hidden, docks locked, no menu bar or status bar: right-click the screen for CEmu's
    menus); True: CEmu's own first layout (every dock), its menu bar and dock editing on."""
    f = folder.replace("\\", "/")
    changes = {
        "General/version": version,
        "General/first_run": "true",
        "General/check_for_updates": "0",
        "General/rom_path": rom.replace("\\", "/"),
        "General/image_path": f + "/cemu_image.ce",
        "General/restore_on_open": "true",
        "General/save_on_close": "true",
        "General/always_on_top": "false",
        "General/pause_on_focus_change": "false",
        "Debugger/image_path": f + "/cemu_debug.ini",
        "Recent/save_paths": "false",
        "Keypad/map": "cemu",
        "Window/fullscreen": "0",
        "CalcSuite/settings": SETTINGS_MARK,
    }
    changes.update(cemu_layout_changes(panels))
    return ini_set("", changes)


def cemu_layout_changes(panels):
    """The settings that make the layout (Window/menubar and Window/statusbar *hide* them when
    true; ui_edit_mode shows the docks' title bars)"""
    if panels:
        return {"General/ui_edit_mode": "true", "Window/menubar": "false", "Window/statusbar": "false",
                "Window/state": None, "Window/geometry": None, "Window/position": None}
    return {"General/ui_edit_mode": "false", "Window/menubar": "true", "Window/statusbar": "true",
            "Window/state": qt_bytearray(cemu_layout_state()), "Window/geometry": qt_bytearray(cemu_geometry()),
            "Window/position": "@Point(100 100)"}


def cemu_settings_folder():
    import pc_copy
    return os.path.join(pc_copy.emulators_folder(), "CEmu", "calcsuite")


def cemu_version():
    """The CEmu version CalcSuite downloaded (its stamp), for the settings' version key: a
    different one makes CEmu ask about its settings"""
    import pc_copy
    try:
        with open(os.path.join(pc_copy.emulators_folder(), "CEmu", "calcsuite.json"), encoding="utf-8") as fh:
            return json.load(fh).get("version") or "v2.0"
    except (OSError, ValueError):
        return "v2.0"


# The calculator's size in CEmu 2.0 (screen with its skin above the keypad) at a Screen/scale:
# 100 and 75 measured (2026-11-28: about 456 x 690 and 368 x 590), 125 and 50 estimated
CEMU_SIZES = ((125, 570, 860), (100, 460, 700), (75, 370, 600), (50, 290, 500))


def cemu_scale_for(w, h):
    """The biggest screen scale whose calculator fits a w x h tab (50 at the least): CEmu's
    screen doesn't shrink below its scale, so a smaller tab would cut it off"""
    for scale, cw, ch in CEMU_SIZES:
        if w >= cw and h >= ch:
            return scale
    return CEMU_SIZES[-1][0]


def prepare_cemu_settings(rom, folder=None, panels=None, scale=None):
    """The tab's CEmu settings file: made the first time; later CEmu keeps it itself (what the
    user changes in it stays), except that the ROM is this one, the transfers aren't remembered
    and, when panels is True/False, the layout is set again. Returns its path."""
    folder = folder or cemu_settings_folder()
    os.makedirs(folder, exist_ok=True)
    ini = os.path.join(folder, "cemu_config.ini")
    text = None
    if os.path.isfile(ini):
        with open(ini, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        if ini_get(text, "CalcSuite/settings") != SETTINGS_MARK:
            text = None  # Made by an older CalcSuite (from the user's own CEmu settings): made again
    if text is None:
        text = cemu_settings_text(folder, rom, cemu_version(), bool(panels))
    else:
        changes = {"General/rom_path": rom.replace("\\", "/"), "Recent/save_paths": "false",
                   "Recent/paths": None, "Recent/selected": None,
                   "General/image_path": folder.replace("\\", "/") + "/cemu_image.ce"}
        if panels is not None:
            changes.update(cemu_layout_changes(panels))
        text = ini_set(text, changes)
    if scale:  # The screen's size, so the calculator fits the tab (scale: cemu_scale_for)
        text = ini_set(text, {"Screen/scale": str(int(scale))})
    with open(ini + ".part", "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(ini + ".part", ini)
    return ini


def ini_get(text, full):
    """The value of "Section/key" in INI text, or None"""
    sec, key = full.split("/", 1)
    for name, lines in _section_lines(text):
        if name == sec:
            for line in lines:
                if "=" in line and line.split("=", 1)[0].strip() == key:
                    return line.split("=", 1)[1].strip()
    return None


def state_file(folder=None):
    return os.path.join(folder or cemu_settings_folder(), "calcsuite_state.json")


def load_state(folder=None):
    """CalcSuite's note about the tab's CEmu ({rom, backup, panels, started}; {} when none)"""
    try:
        with open(state_file(folder), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def save_state(state, folder=None):
    try:
        os.makedirs(folder or cemu_settings_folder(), exist_ok=True)
        with open(state_file(folder), "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=1)
    except OSError:
        log_error("saving the tab's CEmu note")


def start_fresh(state, rom, image_exists):
    """Boot the ROM afresh (with the backup's files) or carry on from CEmu's saved state: afresh
    the first time, after a new ROM, or when there is no saved state"""
    return not image_exists or not state or state.get("rom") != os.path.normcase(os.path.abspath(rom))


def cemu_env(dpi):
    """CEmu (Qt 6) is per-monitor DPI aware and CalcSuite's Tk window isn't: with Windows'
    scaling above 100 % the two would disagree about sizes inside the tab, so the tab's CEmu
    runs DPI-unaware too (Windows scales both alike). Nothing changes at 100 %."""
    return {"QT_QPA_PLATFORM": "windows:dpiawareness=0"} if dpi and dpi != 96 else {}


def cemu_ipc(exe, *args):
    """A command for the running tab CEmu (--id CalcSuite): CEmu hands it to the running one
    and exits (gui/qt/main.cpp, IPC)"""
    return [exe, "--id", CEMU_ID] + list(args)


# ---- The tab ----
class EmuTab(object):
    """One emulator tab: a bar, the emulator's window (or a message where it would be) and a
    side panel with its keys and the guide"""

    def __init__(self, app, slug, rom, backup=None):
        import ui_panels
        self.app, self.slug = app, slug
        self.spec = SPECS[slug]
        self.key = self.spec["key"]
        self.name = self.spec["emulator"]
        self.rom, self.backup = rom, backup
        self.gone = False
        self.restart_mode = None     # Once the running one has closed: start again (True: from the backup)
        self.popped = False          # (App's tab code looks at .popped)
        self.frame = tk.Frame(app.content, bg=th.BG)
        self.status = tk.StringVar(master=self.frame, value="")
        bar = tk.Frame(self.frame, bg=th.BG)
        bar.pack(fill="x", padx=14, pady=(10, 0))
        self.bar = bar
        self.btn_send = th.button(bar, "Send files...", self.send_files)
        self.btn_shot = th.button(bar, "Screenshot", self.screenshot)
        self.btn_fresh = th.button(bar, "Start again from the backup", self.start_again)
        self.btn_pop = th.button(bar, "Open in its own window", self.toggle_pop)
        self.btn_rom = th.button(bar, "Show the ROM", self.show_rom)
        self.btn_close = th.button(bar, "Close %s" % self.name, self.close_emulator)
        items = ([self.btn_send, self.btn_shot, self.btn_fresh] if slug == "ti84" else []) + \
            [self.btn_pop, self.btn_rom, self.btn_close]
        for k, b in enumerate(items):
            b.pack(side="left", padx=(0 if k == 0 else 6, 0))
        for b in (self.btn_send, self.btn_shot, self.btn_pop, self.btn_close):
            b.configure(state="disabled")  # Until the emulator runs (changed() turns them on)
        self.copy_view = None    # The PC copy being made, shown in this tab (ui_panels.PcCopyDialog)
        self.section = None      # The calculator's Calculator info section it was made from
        self.layout_change = None  # CEmu's panels on/off: the layout to set when CEmu starts next
        self.panels_var = tk.BooleanVar(master=self.frame, value=bool(load_state().get("panels")))
        if slug == "ti84":
            th.check(bar, "CEmu's panels", self.panels_var, self.toggle_panels).pack(side="right")
        tk.Label(self.frame, textvariable=self.status, bg=th.BG, fg=th.DIM, anchor="w", justify="left",
                 wraplength=900).pack(fill="x", padx=14, pady=(6, 0))
        body = tk.Frame(self.frame, bg=th.BG)
        body.pack(fill="both", expand=True)
        self.panel = EmuPanel(body, self)
        self.panel.frame.pack(side="right", fill="y", pady=(10, 0))
        # The emulator's window goes into this frame (its own Windows window: winfo_id)
        self.host = tk.Frame(body, bg="#050506", highlightthickness=0, bd=0)
        self.host.pack(side="left", fill="both", expand=True, padx=(14, 8), pady=(10, 10))
        self.host.bind("<Configure>", self.host_resized)
        self.scale = None  # CEmu's screen scale this run (None: CEmu's panels, or not running)
        self.note = tk.Frame(self.host, bg="#050506")  # What's here when the window isn't
        self.session = None
        try:
            self.win = eh.Win32()
        except (AttributeError, OSError):
            self.win = None
        self.frame.after(POLL_MS, self.loop)
        self.frame.bind("<Destroy>", self.destroyed, add="+")

    # ---- plumbing ----
    def destroyed(self, ev):
        if ev.widget is self.frame:
            self.gone = True

    def ui(self, fn, *args):
        """From a worker: fn(*args) on Tk's thread (mirror's after() queue)"""
        if not self.gone:
            self.app.root.after(0, fn, *args)

    def host_info(self):
        """(the frame's window handle, width, height), or None while it isn't laid out"""
        try:
            w, h = self.host.winfo_width(), self.host.winfo_height()
            if w <= 1:
                self.host.update_idletasks()
                w, h = self.host.winfo_width(), self.host.winfo_height()
            if w <= 1:
                return None
            hwnd = self.host.winfo_id()
            if self.win is not None:
                self.win.clip_children(hwnd)
            return hwnd, w, h
        except tk.TclError:
            return None

    def host_resized(self, ev):
        """The tab changed size: the window follows; CEmu's screen keeps the size it started
        with, so when another one would fit better the status says how to get it"""
        s = self.session
        if s is None:
            return
        s.fit()
        if self.scale and s.state == eh.EMBEDDED:
            want = cemu_scale_for(ev.width, ev.height)
            if want != self.scale:
                self.status.set("The calculator is sized for a %s tab: Close CEmu, then Open again, and it "
                                "fits this one." % ("bigger" if want < self.scale else "smaller"))

    def loop(self):
        if self.gone:
            return
        try:
            if self.session is not None:
                self.session.poll()
        except Exception:
            log_error("watching the %s window" % self.name)
        finally:
            if not self.gone:
                self.frame.after(POLL_MS, self.loop)

    # ---- starting ----
    def start(self, fresh=None):
        """Starts the emulator (downloading CEmu first when it isn't there yet). fresh: boot
        the ROM with the backup's files (None: CalcSuite decides, start_fresh())."""
        if self.win is None:
            self.message("The emulator tab needs Windows.", [])
            return
        if self.session is not None and self.session.running():
            return
        if self.copy_view is not None:
            return  # A PC copy is being made here: the emulator starts when it's done
        if not self.rom:
            self.message("There's no PC copy of the %s yet." % TITLES[self.slug],
                         [("Make a PC copy...", self.make_copy)] if self.section is not None else [])
            return
        import pc_copy
        if self.slug == "ti84":
            exe = pc_copy.cemu_path()
            if not exe:
                self.message("Getting CEmu ready (the first time: about 19 MB from CEmu's GitHub "
                             "release, checked against its SHA-256)...", [])
                self.work(lambda: pc_copy.get_emulator("84", self.dl_report), lambda emu: self.start(fresh))
                return
            self._start_cemu(exe, fresh)
        else:
            exe = pc_copy.tiemu_path()
            if not exe:
                self.missing_tiemu()
                return
            cmd = pc_copy.emulator_command("89", self.rom, emulator=exe)
            self._launch(cmd, None, None, "TiEmu is starting (the first time it turns the ROM into its own "
                         "image: give it a moment)...")

    def _start_cemu(self, exe, fresh):
        import pc_copy
        folder = cemu_settings_folder()
        panels = bool(self.panels_var.get())
        hi = self.host_info()
        scale = None if panels or hi is None else cemu_scale_for(hi[1], hi[2])
        self.scale = scale
        try:
            ini = prepare_cemu_settings(self.rom, folder, panels=self.layout_change, scale=scale)
        except OSError as e:
            log_error("making the tab's CEmu settings")
            self.message("CEmu's settings couldn't be made: %s" % e, [("Try again", self.start)])
            return
        self.layout_change = None
        state = load_state(folder)
        if fresh is None:
            fresh = start_fresh(state, self.rom, os.path.isfile(os.path.join(folder, "cemu_image.ce")))
        files = []
        if fresh:
            b = self.backup or pc_copy.latest_backup("84")
            if b and os.path.isdir(b):
                try:
                    files = pc_copy.backup_files(b)
                except (OSError, ValueError, KeyError):
                    log_error("reading the backup %s for CEmu" % b)
        cmd = pc_copy.emulator_command("84", self.rom, files, emulator=exe, fresh=fresh,
                                       extra=["--id", CEMU_ID, "-g", ini])
        save_state({"rom": os.path.normcase(os.path.abspath(self.rom)), "backup": self.backup,
                    "panels": panels, "started": time.strftime("%Y-%m-%d %H:%M:%S")}, folder)
        env = cemu_env(self.win.system_dpi())
        what = ("CEmu is starting: it boots your ROM and gets %d programs and variables from the backup "
                "(about 10 s)..." % len(files)) if fresh and files else \
            "CEmu is starting: it boots your ROM..." if fresh else \
            "CEmu is starting: it carries on where you left it..."
        self._launch(cmd, env, CEMU_TITLE, what, None if panels else CEMU_ASPECT)

    def _launch(self, cmd, env, title_re, what, aspect=None):
        self.session = eh.EmuSession(self.win, self.host_info, lambda: eh.popen_detached(cmd, env),
                                     title_re=title_re, on_change=self.changed, aspect=aspect)
        self.message(what, [])
        self.session.start()

    def work(self, fn, then):
        def run():
            try:
                res = fn()
            except Exception as e:
                log_error("getting %s ready" % self.name)
                self.ui(self.message, "%s couldn't be made ready: %s" % (self.name, e),
                        [("Try again", self.start)])
                return
            self.ui(then, res)
        threading.Thread(target=run, daemon=True).start()

    def dl_report(self, stage, text, done=None, total=None):
        if text:
            if total and done is not None and "%" not in text:
                text = "%s (%d%%)" % (text, 100 * min(done, total) // total)
            self.ui(self.status.set, text)

    def missing_tiemu(self):
        import pc_copy
        setup = os.path.join(pc_copy.emulators_folder(), "TiEmu", "setup.exe")
        have = os.path.isfile(setup)
        self.message(
            "TiEmu isn't installed yet.\n\nTiEmu, the TI-89 Titanium emulator, was last released in 2010 "
            "(3.03). Its Windows installer is that old, unsigned setup.exe, so CalcSuite doesn't run it for "
            "you: %s\n\nOnce it's installed, press Check again." % (
                "it's ready in %s. Run it yourself (double-click), keep its folder as it suggests." % setup
                if have else "Download TiEmu's installer (3 MB from SourceForge, checked against its "
                "checksums), then run it yourself."),
            [("Show the installer" if have else "Download TiEmu's installer", self.get_tiemu),
             ("Check again", self.start)])
        self.set_dot("absent")

    def get_tiemu(self):
        import pc_copy
        import ui_panels

        def go():
            emu = pc_copy.get_emulator("89", self.dl_report)
            if not emu.get("ready"):
                ui_panels.show_in_folder(emu["path"])
            return emu

        def then(emu):
            if emu.get("ready"):
                self.start()
            else:
                self.status.set(emu.get("todo") or "Run %s yourself to install TiEmu." % emu["path"])
        self.status.set("Getting TiEmu's installer...")
        self.work(go, then)

    # ---- what the tab shows ----
    def message(self, text, buttons):
        if self.copy_view is not None:
            return  # The PC copy being made has the tab until it's done
        for c in self.note.winfo_children():
            c.destroy()
        tk.Label(self.note, text=text, bg="#050506", fg=th.FG, justify="left", anchor="w",
                 wraplength=560, font=(th.FONT, 11)).pack(anchor="w")
        row = tk.Frame(self.note, bg="#050506")
        row.pack(anchor="w", pady=(14, 0))
        for k, (label, cmd) in enumerate(buttons):
            th.button(row, label, cmd).pack(side="left", padx=(0 if k == 0 else 6, 0))
        self.note.place(relx=0.5, rely=0.45, anchor="center")
        self.note.lift()

    def changed(self, state, why):
        """The session's state changed (Tk's thread: poll() and the buttons call this)"""
        name = self.name
        self.popped = False
        self.btn_pop.configure(text="Open in its own window",
                               state="normal" if state in (eh.EMBEDDED, eh.OWN) else "disabled")
        running = state in (eh.STARTING, eh.EMBEDDED, eh.OWN)
        for b in (self.btn_send, self.btn_shot, self.btn_close):
            b.configure(state="normal" if running else "disabled")
        if state == eh.EMBEDDED:
            self.note.place_forget()
            # The message that was there goes: the frame around the window repaints
            self.frame.after(120, lambda: self.win is not None and self.win.redraw(self.host.winfo_id()))
            self.set_dot("connected")
            self.status.set("%s is running here: click into it to type on it (its keys are in the panel); "
                            "the rest of CalcSuite works as usual." % name)
            if self.app.current == self.key:
                self.frame.after(60, self.focus)
        elif state == eh.STARTING:
            self.set_dot("connecting")
            if why:
                self.message("%s: %s..." % (name, why), [])
        elif state == eh.OWN:
            self.set_dot("connected")
            self.btn_pop.configure(text="Back into the tab")
            self.message("%s is in its own window%s." % (
                name, "" if why == "in its own window" else " (%s)" % why),
                [("Back into the tab", self.dock), ("Show it", self.raise_own)])
            self.status.set("%s is in its own window. Back into the tab puts it here again." % name)
        elif state == eh.CLOSED:
            self.set_dot("absent")
            self.btn_pop.configure(state="disabled")
            if self.restart_mode is not None:
                fresh, self.restart_mode = self.restart_mode, None
                self.start(fresh=fresh)
                return
            buttons = [("Open again", lambda: self.start(fresh=False if self.slug == "ti84" else None))]
            if self.slug == "ti84":
                buttons.append(("Start again from the backup", lambda: self.start(fresh=True)))
            self.message("%s was closed%s.\n\n%s" % (
                name, "" if why in ("it was closed", "closed by CalcSuite") else " (%s)" % why,
                "Open again carries on where it was (CEmu saved its state)." if self.slug == "ti84"
                else "Open again starts it with your ROM."), buttons)
            self.status.set("%s is closed." % name)
        elif state == eh.FAILED:
            self.set_dot("failed")
            self.message("%s didn't start: %s." % (name, why), [("Try again", self.start)])
            try:
                raise RuntimeError(why)
            except RuntimeError:
                log_error("starting %s in its tab" % name)

    def set_dot(self, state):
        """The tab's dot: "connected", "connecting", "absent" or "failed" (mirror.set_dot)"""
        w = self.app.tab_widgets.get(self.key)
        if w:
            try:
                th.set_dot(w["dot"], state)
                state = self.session.state if self.session else None
                w["fps"].configure(text={eh.OWN: "own window", eh.CLOSED: "closed", eh.STARTING: "starting",
                                         eh.FAILED: "didn't start"}.get(state, ""))
            except tk.TclError:
                pass

    # ---- focus ----
    def shown(self):
        """App.show_tab made this tab visible"""
        if self.session is not None:
            self.session.fit()
            self.frame.after(80, self.focus)

    def hidden(self):
        """Another tab is shown: the keyboard comes back to CalcSuite (the emulator's window is
        hidden with the tab, and a hidden window must not keep the keys)"""
        try:
            if self.win is not None:
                # Windows' own focus first (Tk may think it still has it and do nothing)
                self.win.focus(self.app.root.winfo_id())
            self.app.root.focus_force()
        except tk.TclError:
            pass

    def focus(self):
        if self.session is not None and self.app.current == self.key:
            self.session.focus()

    # ---- the bar ----
    def toggle_pop(self):
        s = self.session
        if s is None:
            return
        if s.state == eh.EMBEDDED:
            self.pop_out()
        elif s.state == eh.OWN:
            self.dock()

    def pop_out(self):
        s = self.session
        if s is None or s.state != eh.EMBEDDED:
            return False
        x, y = self.host.winfo_rootx(), self.host.winfo_rooty()
        ok = s.pop_out((x, y, self.host.winfo_width(), self.host.winfo_height()))
        self.hidden()
        if ok and s.hwnd:
            self.win.foreground(s.hwnd)
        return ok

    def dock(self):
        s = self.session
        if s is not None and s.dock():
            self.focus()

    def raise_own(self):
        s = self.session
        if s is not None and s.hwnd:
            self.win.show(s.hwnd, 9)  # SW_RESTORE
            self.win.foreground(s.hwnd)

    def close_emulator(self):
        if self.session is not None and self.session.running():
            self.status.set("Closing %s%s..." % (self.name, " (it saves its state first)" if self.slug == "ti84" else ""))
            self.session.close()

    def start_again(self):
        """Start again from the backup: the ROM booted afresh with the backup's programs and
        variables (CEmu's saved state of this copy is replaced)"""
        if not messagebox.askokcancel(
                "Start again from the backup",
                "Restart the PC copy from your ROM, with the programs and variables of the backup?\n\n"
                "What you did in the copy since is replaced (your real calculator isn't touched).",
                parent=self.app.root):
            return
        if self.session is not None and self.session.running():
            self.restart_mode = True
            self.close_emulator()
        else:
            self.start(fresh=True)

    def toggle_panels(self):
        """CEmu's panels: its docks (Variables, Capture, Settings, the debugger...) and menu bar, or
        just the calculator. CEmu takes the layout when it starts: a running one restarts (it
        carries on where it was)."""
        on = bool(self.panels_var.get())
        self.layout_change = on
        st = load_state()
        st["panels"] = on
        save_state(st)
        if self.session is not None and self.session.running():
            self.status.set("CEmu restarts with %s (it carries on where it was)..." % (
                "its panels" if on else "just the calculator"))
            self.restart_mode = False
            self.close_emulator()
        else:
            self.status.set("CEmu starts with %s next time." % ("its panels" if on else "just the calculator"))

    # ---- Making the PC copy, here in the tab ----
    def make_copy(self, section=None, mode="make"):
        """Make a PC copy (Calculator info): the steps, one overall bar, Cancel and the result in
        this tab (ui_panels.PcCopyDialog, embedded); once it's made the emulator starts here"""
        import ui_panels
        section = section or self.section
        if section is None:
            return
        self.section = section
        if self.copy_view is not None and self.copy_view.alive():
            return
        if self.session is not None and self.session.running():
            if not messagebox.askokcancel(
                    "Make a PC copy", "%s closes first (it saves where it was). Then make a new PC copy "
                    "of the %s?" % (self.name, TITLES[self.slug]), parent=self.app.root):
                return
            self.close_emulator()
        self.note.place_forget()
        holder = tk.Frame(self.host, bg=th.BG)
        holder.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.copy_holder = holder
        self.status.set("Making a PC copy of the %s." % TITLES[self.slug])
        self.set_dot("connecting")
        self.copy_view = ui_panels.PcCopyDialog(section, mode, parent=holder, on_made=self.copy_made,
                                                on_close=self.copy_closed)

    def _drop_copy_view(self):
        self.copy_view = None
        try:
            self.copy_holder.destroy()
        except (AttributeError, tk.TclError):
            pass

    def copy_made(self, rom, backup, auto):
        """The PC copy is made (or Open the PC copy here was pressed): the emulator starts here"""
        if self.copy_view is None:
            return
        self._drop_copy_view()
        self.rom, self.backup = rom, backup
        self.start(fresh=True)

    def copy_closed(self):
        """Close / Cancel in the PC copy view"""
        self._drop_copy_view()
        if self.rom:
            self.message("No new PC copy was made. Your PC copy from before is still here.",
                         [("Open it", lambda: self.start())])
            self.status.set("")
        else:
            self.message("No PC copy was made.", [("Make a PC copy...", self.make_copy)])
        self.set_dot("absent")

    def show_rom(self):
        import ui_panels
        if self.rom:
            ui_panels.show_in_folder(self.rom)

    def cemu_exe(self):
        import pc_copy
        return pc_copy.cemu_path()

    def run_ipc(self, args, done, what):
        """A command to the running tab CEmu, on a worker (CEmu's second process hands it over)"""
        exe = self.cemu_exe()
        if not exe or self.session is None or not self.session.running():
            self.status.set("CEmu isn't running.")
            return
        cmd = cemu_ipc(exe, *args)

        def run():
            import subprocess
            try:
                p = eh.popen_detached(cmd)
                p.wait(30)
                self.ui(done, None)
            except (OSError, subprocess.SubprocessError) as e:
                log_error(what)
                self.ui(done, e)
        threading.Thread(target=run, daemon=True).start()

    def send_files(self):
        import pc_copy
        start = self.backup or pc_copy.latest_backup("84") or os.path.expanduser("~")
        files = filedialog.askopenfilenames(
            parent=self.app.root, title="Send to the PC copy (CEmu)", initialdir=start,
            filetypes=[("TI-84 Plus CE files", "*.8xp *.8xv *.8xl *.8xm *.8xn *.8xs *.8xy *.8xg *.8xi *.8ca "
                        "*.8cg *.8ci *.8ek *.8xe *.8xz *.8xw *.8xc *.8xo *.8xd *.8xu *.8pu *.b84 *.b83"),
                       ("All files", "*.*")])
        if not files:
            return
        args = []
        for f in files:
            args += ["--send", os.path.normpath(f)]
        self.status.set("Sending %d file(s) to CEmu (best from the home screen)..." % len(files))
        self.run_ipc(args + ["--no-reset"], lambda err: self.status.set(
            "Sent %d file(s) to CEmu." % len(files) if err is None else "Couldn't send: %s" % err),
            "sending files to CEmu")

    def screenshot(self):
        import mirror
        folder = os.path.join(mirror.KIT, "captures")
        os.makedirs(folder, exist_ok=True)
        out = os.path.join(folder, time.strftime("ti84-pc-copy-%Y%m%d-%H%M%S.png"))

        def done(err):
            for _ in range(20):
                if os.path.isfile(out):
                    break
                time.sleep(0.05)
            if err is None and os.path.isfile(out):
                self.status.set("Saved %s" % out)
            else:
                self.status.set("No screenshot came back%s." % (": %s" % err if err else ""))
        self.run_ipc(["--screenshot", out], done, "taking CEmu's screenshot")

    # ---- closing ----
    def close_tab(self):
        """The ✕ on the tab: closes the emulator (CEmu saves its state) and the tab"""
        if self.copy_view is not None and self.copy_view.running:
            if not messagebox.askokcancel("Close the tab", "A PC copy is being made: cancel it and close "
                                          "the tab?", parent=self.app.root):
                return
            self.copy_view.do_cancel()  # Its worker ends the step and gives the link back
        self.hidden()
        s = self.session
        if s is not None and s.running():
            s.close()
            proc = s.proc

            def reap():  # The tab is gone, so nothing polls: end it here if it doesn't close
                try:
                    proc.wait(eh.CLOSE_WAIT_S)
                except Exception:
                    try:
                        proc.terminate()
                    except OSError:
                        pass
            threading.Thread(target=reap, daemon=True).start()
        self.app.emulator_tab_closed(self)
        self.gone = True
        try:
            self.frame.destroy()
        except tk.TclError:
            pass

    def stop_for_quit(self):
        """CalcSuite is closing: ask the emulator to close (only the process this tab started)"""
        if self.session is not None and self.session.running():
            self.session.close()
            return self.session
        return None


# ---- The tab's side panel: Keys, Guide ----
class EmuPanel(object):
    SECTIONS = ("Keys", "Guide")

    def __init__(self, parent, tab):
        import ui_panels
        self.tab, self.app = tab, tab.app
        self.m = None
        self.guide = (GUIDE[0], GUIDE[1], GUIDE_PDF)
        # The same icon strip as a calculator's tab (ui_panels.panel_frame)
        self.frame, self.strip, self.head, self.body = ui_panels.panel_frame(
            parent, self.SECTIONS, self.show, full={"Keys": "Keys: %s's own" % self.tab.name,
                                                    "Guide": "Guide: PC copies"})
        self.buttons = self.strip.items
        self.sections = {}
        self.current = None
        self.show("Keys")

    def show(self, name):
        import ui_panels
        if self.current == name:
            return
        if self.current in self.sections:
            self.sections[self.current].frame.pack_forget()
        if name not in self.sections:
            if name == "Keys":
                self.sections[name] = EmuKeys(self, self.body)
            else:
                self.sections[name] = ui_panels.GuideSection(self, self.body)
        self.sections[name].frame.pack(fill="both", expand=True)
        self.current = name
        self.head.configure(text={"Keys": "%s's keys" % self.tab.name, "Guide": "PC copies guide"}[name])
        self.strip.select(name)
        if hasattr(self.sections[name], "shown"):
            self.sections[name].shown()


class EmuKeys(object):
    """The emulator's PC keys: emulator_keys.py (the same table as docs/EMULATORS.md)"""

    def __init__(self, panel, parent):
        import ui_panels
        import webbrowser
        self.frame = tk.Frame(parent, bg=th.PANEL)
        outer, inner = ui_panels.scrolled(self.frame)
        outer.pack(fill="both", expand=True)
        slug = panel.tab.slug

        def text(t, fg=th.DIM, pady=(0, 4)):
            tk.Label(inner, text=t, bg=th.PANEL, fg=fg, anchor="w", justify="left",
                     wraplength=400).pack(fill="x", pady=pady)

        def link(t, url):
            a = tk.Label(inner, text=t, bg=th.PANEL, fg=th.MINT, cursor="hand2", anchor="w",
                         font=(th.FONT, 9, "underline"))
            a.pack(fill="x", pady=(0, 6))
            a.bind("<Button-1>", lambda e: webbrowser.open(url))

        if slug == "ti84":
            ui_panels.heading(inner, "How to use it")
            text("Click into CEmu, then type: the keys below press the calculator's. Click a calculator "
                 "key with the mouse too. Right-click its screen for all of CEmu's menus.", fg=th.FG)
            text("These are CEmu's own keys (its default \"CEmu\" preset; change it in CEmu's Settings "
                 "dock > General > Key bindings). CalcSuite's own key shortcuts don't apply in here.")
            link("CEmu's keybindings page", ek.CEMU_WIKI)
            ui_panels.heading(inner, "Calculator key: PC keys")
            for row in ek.CEMU_KEYS:
                r = tk.Frame(inner, bg=th.PANEL)
                r.pack(fill="x", pady=1)
                tk.Label(r, text=row[0], bg=th.PANEL, fg=th.FG, width=9, anchor="w",
                         font=(th.FONT, 10, "bold")).pack(side="left")
                for pc in row[1:]:
                    if pc:
                        th.keycap(r, pc).pack(side="left", padx=(0, 4))
            for n in ek.CEMU_SOURCE_NOTES:
                text(n, pady=(6, 4))
            ui_panels.heading(inner, "CEmu's shortcuts")
            for keys, what in ek.CEMU_SHORTCUTS:
                r = tk.Frame(inner, bg=th.PANEL)
                r.pack(fill="x", pady=1)
                th.keycap(r, keys).pack(side="left")
                tk.Label(r, text=what, bg=th.PANEL, fg=th.FG, anchor="w", justify="left",
                         wraplength=280).pack(side="left", padx=(8, 0), fill="x", expand=True)
        else:
            ui_panels.heading(inner, "How to use it")
            text("Click into TiEmu, then type: the keys below press the calculator's. Right-click TiEmu's "
                 "window for its menu (send a file, screenshots, save the state).", fg=th.FG)
            text("From TiEmu's key map file (skins\\ti89.map, unchanged since 2007, so the one TiEmu 3.03 "
                 "installs); not yet checked on an installed TiEmu.")
            link("TiEmu's ti89.map", ek.TIEMU_SOURCE)
            ui_panels.heading(inner, "PC key: TI-89 key")
            for pc, calc in ek.TIEMU_KEYS:
                r = tk.Frame(inner, bg=th.PANEL)
                r.pack(fill="x", pady=1)
                th.keycap(r, pc).pack(side="left")
                tk.Label(r, text=calc, bg=th.PANEL, fg=th.FG, anchor="w", justify="left",
                         wraplength=240).pack(side="left", padx=(8, 0), fill="x", expand=True)
            ui_panels.heading(inner, "Letters (alpha + this key)")
            text("  ".join("%s %s" % (k, v) for k, v in sorted(ek.TIEMU_LETTERS.items())), fg=th.FG)
        ui_panels.heading(inner, "The guide")
        text("The Guide tab here has everything about PC copies: making one, CEmu's keys and menus, "
             "sending files, screenshots, saving the state, TiEmu.")
        ui_panels.bind_wheel(inner, inner)
