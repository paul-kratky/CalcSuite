# SPDX-License-Identifier: MIT
"""An emulator's own window inside a CalcSuite tab (the PC copy's CEmu and TiEmu).

The emulators stay separate programs (CEmu is GPL-3.0, TiEmu GPL-2.0): CalcSuite starts them
with their own command line and only moves their finished top-level window into a Tk frame,
the way Windows lets any program host another one's window:

  1. find the process's main window (EnumWindows: visible, no owner, the title we expect),
  2. make it a child: WS_POPUP / WS_CAPTION / WS_THICKFRAME / the system menu off, WS_CHILD on
     (child_style), then SetParent into the frame's own window (Tk's winfo_id()),
  3. keep it filling the frame (MoveWindow on every <Configure>, and again whenever the
     emulator moves itself: Qt restores its saved geometry, docks, full screen),
  4. give it back as a normal window (Open in its own window / closing the tab): the styles it
     had, SetParent(NULL), its old size.

Keyboard: a child window of another process shares our input queue (Windows attaches the two
threads), so clicking into it gives it the keyboard and our own key bindings never see those
keys; switching to another tab hides the frame (and the window in it) and hands the keyboard
back to Tk.

Nothing here touches Tk: EmuSession is driven from Tk's thread by the tab (poll() about every
250 ms) and works on window handles and a process only, so the self-test runs it with a fake
process and a fake window API (FakeWin in tools/selftest/emu_checks.py).
"""

import os
import re
import subprocess
import time

# ---- Window styles (winuser.h) ----
WS_CHILD = 0x40000000
WS_POPUP = 0x80000000
WS_VISIBLE = 0x10000000
WS_MINIMIZE = 0x20000000
WS_MAXIMIZE = 0x01000000
WS_CLIPSIBLINGS = 0x04000000
WS_CLIPCHILDREN = 0x02000000
WS_CAPTION = 0x00C00000
WS_THICKFRAME = 0x00040000
WS_SYSMENU = 0x00080000
WS_MINIMIZEBOX = 0x00020000
WS_MAXIMIZEBOX = 0x00010000
WS_EX_DLGMODALFRAME = 0x00000001
WS_EX_WINDOWEDGE = 0x00000100
WS_EX_CLIENTEDGE = 0x00000200
WS_EX_STATICEDGE = 0x00020000
WS_EX_APPWINDOW = 0x00040000
GWL_STYLE, GWL_EXSTYLE = -16, -20
WM_CLOSE = 0x0010

_FRAME = WS_POPUP | WS_CAPTION | WS_THICKFRAME | WS_SYSMENU | WS_MINIMIZEBOX | WS_MAXIMIZEBOX
_FRAME_EX = WS_EX_DLGMODALFRAME | WS_EX_WINDOWEDGE | WS_EX_CLIENTEDGE | WS_EX_STATICEDGE | WS_EX_APPWINDOW


def child_style(style):
    """A top-level window's style -> the style it gets as a child of our frame: no caption,
    border, system menu or min/max box, not minimized or maximized, WS_CHILD (kept visible)"""
    style &= 0xFFFFFFFF
    return ((style & ~(_FRAME | WS_MINIMIZE | WS_MAXIMIZE)) | WS_CHILD | WS_CLIPSIBLINGS) & 0xFFFFFFFF


def child_exstyle(ex):
    """The extended style as a child: no edges, not in the taskbar (WS_EX_APPWINDOW off)"""
    return (ex & 0xFFFFFFFF) & ~_FRAME_EX


def top_style(child, original):
    """Back to a top-level window: the style it had before (original), minus WS_CHILD; when
    there is none (a window that was never embedded), an ordinary resizable window"""
    if original is None:
        original = (child & ~WS_CHILD) | WS_CAPTION | WS_THICKFRAME | WS_SYSMENU | WS_MINIMIZEBOX | WS_MAXIMIZEBOX
    return (original & ~WS_CHILD & ~WS_MINIMIZE & ~WS_MAXIMIZE) & 0xFFFFFFFF


def fit_rect(w, h, aspect=None):
    """Where the child goes in a frame of w x h (client pixels): all of it, or (aspect: its
    width / height, e.g. a calculator's) the biggest such rectangle, centred. At least 1 x 1."""
    w, h = max(1, int(w)), max(1, int(h))
    if not aspect:
        return 0, 0, w, h
    cw = min(w, int(round(h * aspect)))
    ch = min(h, int(round(cw / aspect)))
    cw, ch = max(1, cw), max(1, ch)
    return (w - cw) // 2, (h - ch) // 2, cw, ch


def pick_window(windows, title_re=None):
    """The emulator's main window among a process's top-level windows [{hwnd, title, visible,
    owner, w, h}]: visible, unowned, with a title (matching title_re when given); the biggest.
    None when there is none yet."""
    pat = re.compile(title_re) if title_re else None
    cands = [w for w in windows if w.get("visible") and not w.get("owner") and w.get("title")
             and (pat is None or pat.search(w["title"]))]
    if not cands:
        return None
    return max(cands, key=lambda w: w.get("w", 0) * w.get("h", 0))["hwnd"]


def _signed(v):
    """A 32-bit style as the signed LONG_PTR SetWindowLongPtrW takes"""
    v &= 0xFFFFFFFF
    return v - (1 << 32) if v & 0x80000000 else v


# ---- The Win32 calls (ctypes; a fake stands in for them in the self-test) ----
class Win32(object):
    """The few user32 calls embedding needs. Every call is safe on a window that has gone
    (it returns 0/False/None)."""

    def __init__(self):
        import ctypes
        from ctypes import wintypes
        self.ct, self.wt = ctypes, wintypes
        u = self.u = ctypes.windll.user32
        LONG_PTR = ctypes.c_ssize_t
        self.EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        u.EnumWindows.argtypes = [self.EnumProc, wintypes.LPARAM]
        u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        u.GetWindowThreadProcessId.restype = wintypes.DWORD
        u.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
        u.GetWindowLongPtrW.restype = LONG_PTR
        u.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, LONG_PTR]
        u.SetWindowLongPtrW.restype = LONG_PTR
        u.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]
        u.SetParent.restype = wintypes.HWND
        u.GetParent.argtypes = [wintypes.HWND]
        u.GetParent.restype = wintypes.HWND
        u.GetAncestor.argtypes = [wintypes.HWND, ctypes.c_uint]
        u.GetAncestor.restype = wintypes.HWND
        u.GetWindow.argtypes = [wintypes.HWND, ctypes.c_uint]
        u.GetWindow.restype = wintypes.HWND
        u.IsWindow.argtypes = [wintypes.HWND]
        u.IsWindowVisible.argtypes = [wintypes.HWND]
        u.MoveWindow.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                 wintypes.BOOL]
        u.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_uint]
        u.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        u.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        u.PostMessageW.argtypes = [wintypes.HWND, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM]
        u.SetFocus.argtypes = [wintypes.HWND]
        u.SetFocus.restype = wintypes.HWND
        u.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        u.SetForegroundWindow.argtypes = [wintypes.HWND]
        u.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        u.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        u.ScreenToClient.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
        u.RedrawWindow.argtypes = [wintypes.HWND, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint]

    def windows_of(self, pid):
        """The top-level windows of a process: [{hwnd, title, visible, owner, w, h}]"""
        out = []
        u, wt, ct = self.u, self.wt, self.ct

        def each(hwnd, _l):
            owner = wt.DWORD()
            u.GetWindowThreadProcessId(hwnd, ct.byref(owner))
            if owner.value == pid:
                n = u.GetWindowTextLengthW(hwnd)
                buf = ct.create_unicode_buffer(n + 1)
                u.GetWindowTextW(hwnd, buf, n + 1)
                x0, y0, x1, y1 = self.rect(hwnd)
                out.append({"hwnd": int(hwnd), "title": buf.value, "visible": bool(u.IsWindowVisible(hwnd)),
                            "owner": int(u.GetWindow(hwnd, 4) or 0), "w": x1 - x0, "h": y1 - y0})
            return True
        u.EnumWindows(self.EnumProc(each), 0)
        return out

    def alive(self, hwnd):
        return bool(hwnd) and bool(self.u.IsWindow(hwnd))

    def style(self, hwnd):
        return self.u.GetWindowLongPtrW(hwnd, GWL_STYLE) & 0xFFFFFFFF

    def exstyle(self, hwnd):
        return self.u.GetWindowLongPtrW(hwnd, GWL_EXSTYLE) & 0xFFFFFFFF

    def set_styles(self, hwnd, style, ex):
        self.u.SetWindowLongPtrW(hwnd, GWL_STYLE, _signed(style))
        self.u.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, _signed(ex))
        # SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED
        self.u.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020)

    def parent(self, hwnd):
        return int(self.u.GetParent(hwnd) or 0)

    def set_parent(self, hwnd, parent):
        self.u.SetParent(hwnd, parent or None)
        return self.parent(hwnd) == (parent or 0) or not parent

    def rect(self, hwnd):
        r = self.wt.RECT()
        if not self.u.GetWindowRect(hwnd, self.ct.byref(r)):
            return 0, 0, 0, 0
        return r.left, r.top, r.right, r.bottom

    def client_size(self, hwnd):
        r = self.wt.RECT()
        if not self.u.GetClientRect(hwnd, self.ct.byref(r)):
            return 0, 0
        return r.right - r.left, r.bottom - r.top

    def child_rect(self, hwnd):
        """The window's rectangle in its parent's client coordinates"""
        x0, y0, x1, y1 = self.rect(hwnd)
        p = self.parent(hwnd)
        if not p:
            return x0, y0, x1 - x0, y1 - y0
        pt = (self.wt.POINT * 1)()
        pt[0].x, pt[0].y = x0, y0
        self.u.ScreenToClient(p, pt)
        return pt[0].x, pt[0].y, x1 - x0, y1 - y0

    def move(self, hwnd, x, y, w, h):
        self.u.MoveWindow(hwnd, int(x), int(y), int(w), int(h), True)

    def redraw(self, hwnd):
        """Repaint a window and its children (RDW_ERASE | RDW_INVALIDATE | RDW_ALLCHILDREN)"""
        self.u.RedrawWindow(hwnd, None, None, 0x0004 | 0x0001 | 0x0080)

    def show(self, hwnd, how=5):  # SW_SHOW
        self.u.ShowWindow(hwnd, how)

    def focus(self, hwnd):
        return bool(self.u.SetFocus(hwnd))

    def foreground(self, hwnd):
        self.u.SetForegroundWindow(hwnd)

    def close(self, hwnd):
        return bool(self.u.PostMessageW(hwnd, WM_CLOSE, 0, 0))

    def clip_children(self, hwnd):
        """The host frame mustn't paint over the child (WS_CLIPCHILDREN on it)"""
        s = self.style(hwnd)
        if not s & WS_CLIPCHILDREN:
            self.u.SetWindowLongPtrW(hwnd, GWL_STYLE, _signed(s | WS_CLIPCHILDREN))

    def system_dpi(self):
        """The system DPI (96 at 100 %): what a DPI-unaware window like Tk's is scaled by"""
        try:
            u, wt = self.u, self.wt
            u.GetDC.argtypes = [wt.HWND]
            u.GetDC.restype = wt.HDC
            u.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
            g = self.ct.windll.gdi32
            g.GetDeviceCaps.argtypes = [wt.HDC, self.ct.c_int]
            dc = u.GetDC(None)
            dpi = g.GetDeviceCaps(dc, 88)  # LOGPIXELSX
            u.ReleaseDC(None, dc)
            return int(dpi) or 96
        except (AttributeError, OSError, self.ct.ArgumentError):
            return 96


# ---- One emulator, from start to close ----
# The states (EmuSession.state)
MISSING = "missing"     # The emulator isn't installed: the tab says how to get it
STARTING = "starting"   # The process runs; its window hasn't appeared yet
EMBEDDED = "embedded"   # Its window is in the tab
OWN = "own window"      # Its window is a normal window again (Open in its own window, or the fallback)
CLOSED = "closed"       # The process has ended (closed by the user, or by CalcSuite)
FAILED = "failed"       # It didn't start, or never showed a window

WINDOW_WAIT_S = 30.0    # The window has this long to appear (CEmu: ~1-3 s; TiEmu converts a ROM first)
CLOSE_WAIT_S = 6.0     # After WM_CLOSE (CEmu saves its state), then the process is ended
KEEP_EVERY_S = 0.5      # How often poll() puts a window that moved itself back in place


class EmuSession(object):
    """One emulator process and its window. Driven from one thread (Tk's): start(), then
    poll() every ~250 ms; embed() / pop_out() / close().

    win: Win32() or a fake with the same methods. host(): the frame's window handle and its
    size (hwnd, w, h), or None while it isn't laid out. popen(): starts the process (a
    subprocess.Popen or a fake with .pid, .poll(), .terminate(), .kill(), .wait()).
    title_re: what the main window's title matches (CEmu: "^CEmu \\| <id>$"). embed: False
    opens it beside the window (the fallback) instead of in the tab."""

    def __init__(self, win, host, popen, title_re=None, embed=True, clock=time.monotonic,
                 on_change=None, window_wait=WINDOW_WAIT_S, aspect=None):
        self.win, self.host, self.popen = win, host, popen
        self.aspect = aspect  # The window's width / height in the frame (None: fill the frame)
        self.title_re, self.want_embed = title_re, embed
        self.clock = clock
        self.on_change = on_change or (lambda state, why: None)
        self.window_wait = window_wait
        self.proc = None
        self.hwnd = None
        self.state = None
        self.why = ""
        self.saved = None       # (style, exstyle, (x, y, w, h)) from before embedding
        self.t_start = None
        self.t_keep = 0.0
        self.closing = None     # When close() posted WM_CLOSE
        self.exit_code = None
        self.adoptions = 0      # Windows taken in (a new main window after Qt rebuilt its own counts)

    # ---- state ----
    def _set(self, state, why=""):
        if state != self.state or why != self.why:
            self.state, self.why = state, why
            self.on_change(state, why)

    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def pid(self):
        return getattr(self.proc, "pid", None)

    # ---- start ----
    def start(self):
        """Starts the process. Returns True; on an OSError the state is FAILED (why says it)."""
        try:
            self.proc = self.popen()
        except (OSError, ValueError) as e:
            self.proc = None
            self._set(FAILED, "it didn't start: %s" % e)
            return False
        self.hwnd, self.saved, self.closing, self.exit_code = None, None, None, None
        self.t_start = self.clock()
        self._set(STARTING, "")
        return True

    # ---- the loop ----
    def poll(self):
        """Tk's thread, every ~250 ms: notices the process ending, takes its window in when it
        appears (or a new one: Qt makes a new main window when it changes its flags), keeps the
        embedded window filling the frame. Returns the state."""
        if self.proc is None:
            return self.state
        code = self.proc.poll()
        if code is not None:
            if self.state != CLOSED:
                self.exit_code = code
                self.hwnd = None
                self._set(CLOSED, "closed by CalcSuite" if self.closing is not None else
                          "it was closed" if code == 0 else "it ended (exit code %s)" % code)
            return self.state
        if self.closing is not None:
            if self.clock() - self.closing > CLOSE_WAIT_S:
                self.kill()
            return self.state
        if self.state == STARTING:
            hwnd = pick_window(self.win.windows_of(self.proc.pid), self.title_re)
            if hwnd:
                self.hwnd = hwnd
                if self.want_embed:
                    self.embed()
                else:
                    self._set(OWN, "beside CalcSuite")
            elif self.clock() - self.t_start > self.window_wait:
                self._set(FAILED, "its window didn't appear within %d s" % self.window_wait)
            return self.state
        if self.state == EMBEDDED:
            if not self.win.alive(self.hwnd) or not self._ours():
                # Gone or taken back (Qt rebuilt it): adopt the process's main window again
                hwnd = pick_window(self.win.windows_of(self.proc.pid), self.title_re)
                if hwnd:
                    if hwnd != self.hwnd:
                        self.hwnd, self.saved = hwnd, None
                    self.adoptions += 1
                    self.embed()
                else:
                    self.hwnd = None
                    self._set(STARTING, "waiting for its window again")
                    self.t_start = self.clock()
            elif self.clock() - self.t_keep > KEEP_EVERY_S:
                self.t_keep = self.clock()
                self.fit(force=False)
        elif self.state == OWN and self.hwnd and not self.win.alive(self.hwnd):
            hwnd = pick_window(self.win.windows_of(self.proc.pid), self.title_re)
            self.hwnd = hwnd
        return self.state

    def _ours(self):
        h = self.host()
        return bool(h) and self.win.parent(self.hwnd) == h[0]

    # ---- embedding ----
    def embed(self):
        """Takes the window into the frame. False (and OWN, why says so) when Windows refused:
        the window stays a normal window beside CalcSuite."""
        h = self.host()
        if not self.hwnd or not self.win.alive(self.hwnd):
            return False
        if not h:
            self._set(STARTING, "waiting for the tab")
            return False
        parent, w, hgt = h
        style, ex = self.win.style(self.hwnd), self.win.exstyle(self.hwnd)
        if not style & WS_CHILD:
            x0, y0, x1, y1 = self.win.rect(self.hwnd)
            self.saved = (style, ex, (x0, y0, x1 - x0, y1 - y0))
        self.win.set_styles(self.hwnd, child_style(style), child_exstyle(ex))
        ok = self.win.set_parent(self.hwnd, parent)
        if not ok or self.win.parent(self.hwnd) != parent:
            self._restore_top()
            self._set(OWN, "Windows didn't let CalcSuite put it in the tab: it's beside the window")
            return False
        self.win.move(self.hwnd, *fit_rect(w, hgt, self.aspect))
        self.win.redraw(parent)
        self.win.show(self.hwnd)
        self._set(EMBEDDED, "")
        return True

    def fit(self, force=True):
        """The embedded window fills the frame (on <Configure>; poll() calls it with
        force=False, which moves it only when it isn't where it belongs)"""
        if self.state != EMBEDDED or not self.hwnd:
            return
        h = self.host()
        if not h:
            return
        want = fit_rect(h[1], h[2], self.aspect)
        if force or tuple(self.win.child_rect(self.hwnd)) != want:
            self.win.move(self.hwnd, *want)
            self.win.redraw(h[0])  # The frame around it repaints (no trails of the old place)

    def _restore_top(self, near=None, show=True):
        style, ex, rect = self.saved if self.saved else (None, None, None)
        cur = self.win.style(self.hwnd)
        self.win.set_parent(self.hwnd, 0)
        self.win.set_styles(self.hwnd, top_style(cur, style),
                            ex if ex is not None else (self.win.exstyle(self.hwnd) | WS_EX_APPWINDOW))
        if near is not None:
            x, y = near[0], near[1]
            w, h = (rect[2], rect[3]) if rect else (near[2], near[3])
            self.win.move(self.hwnd, x, y, w, h)
        elif rect:
            self.win.move(self.hwnd, *rect)
        if show:
            self.win.show(self.hwnd)

    def pop_out(self, near=None):
        """Gives the window back as a normal window (near: (x, y, w, h) on the screen to put it
        at, e.g. over the tab). Its saved style and size come back."""
        if self.state != EMBEDDED or not self.hwnd:
            return False
        self._restore_top(near)
        self.win.foreground(self.hwnd)
        self._set(OWN, "in its own window")
        return True

    def dock(self):
        """Back into the tab (from OWN)"""
        if self.state != OWN or not self.running():
            return False
        if not self.hwnd or not self.win.alive(self.hwnd):
            self.hwnd = pick_window(self.win.windows_of(self.proc.pid), self.title_re)
        return self.embed()

    def focus(self):
        """The keyboard to the emulator (its window shares our input queue while embedded)"""
        if self.state == EMBEDDED and self.hwnd:
            return self.win.focus(self.hwnd)
        return False

    # ---- closing ----
    def close(self, release=True):
        """Asks the emulator to close (WM_CLOSE: CEmu saves its state first); poll() ends the
        process after CLOSE_WAIT_S if it's still there. release: first give the window back
        hidden at its old size (so the emulator saves its own geometry, not the tab's)."""
        if not self.running():
            return False
        if self.hwnd and self.win.alive(self.hwnd):
            if release and self.state == EMBEDDED:
                self.win.show(self.hwnd, 0)  # SW_HIDE first: it's closing, nothing flashes
                self._restore_top(show=False)
            self.win.close(self.hwnd)
        else:
            self.kill()
        self.closing = self.clock()
        return True

    def kill(self):
        """Ends the process (only ours: the one start() made)"""
        if self.proc is None or self.proc.poll() is not None:
            return
        try:
            self.proc.terminate()
        except OSError:
            pass

    def close_wait(self, timeout=CLOSE_WAIT_S, sleep=time.sleep):
        """close(), then wait for the process (CalcSuite closing); kills it at the end.
        Returns how it ended: "closed", "killed" or "not running"."""
        if not self.running():
            return "not running"
        self.close()
        t = self.clock()
        while self.clock() - t < timeout:
            if self.proc.poll() is not None:
                self.poll()
                return "closed"
            sleep(0.05)
        self.kill()
        try:
            self.proc.wait(2)
        except Exception:
            pass
        self.poll()
        return "killed"


def popen_detached(cmd, env=None):
    """Starts a GUI program without a console; returns its Popen (stopped only by its pid)"""
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    e = None
    if env:
        e = dict(os.environ)
        e.update(env)
    return subprocess.Popen(cmd, cwd=os.path.dirname(cmd[0]) or None, creationflags=flags,
                            close_fds=True, env=e)
