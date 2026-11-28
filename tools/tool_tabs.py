"""Tools in tabs of the main window, not windows of their own.

The main window (mirror.App) holds a tool as a closable tab (a ✕ like the PC copy's tab):
App.open_tool_tab(key, title, make_frame) makes the tab and puts make_frame(holder) in it;
the same key again shows the tab it has.

Tools that were written as windows (a Toplevel: Compare backups, the macro editor, Get all, a
program's text, ...) get a ToolFrame from window(master, key, title) instead: a Frame in that
tab that answers the window calls they make (title, geometry, protocol, lift, destroy), so
their code stays as it was. Without the main window (a tool started on its own, the
self-tests) window() is a plain Toplevel. File pickers, message boxes and yes/no questions stay
dialogs. MIT licence.
"""

import sys
import tkinter as tk

import ui_theme as th

PREFIX = "tool:"  # A tool tab's key in the App's tab strip


def app():
    """The main window (mirror.App) when it's running, else None"""
    mod = sys.modules.get("mirror")
    a = getattr(mod, "APP", None) if mod is not None else None
    try:
        if a is not None and a.root.winfo_exists():
            return a
    except (tk.TclError, AttributeError):
        pass
    return None


def tab_key(key):
    return key if key.startswith(PREFIX) else PREFIX + key


def is_tool_key(key):
    return isinstance(key, str) and key.startswith(PREFIX)


def focus(key):
    """Shows the tool tab with this key if one is open: True, else False"""
    a = app()
    if a is not None and tab_key(key) in getattr(a, "tools", {}):
        a.show_tab(tab_key(key))
        return True
    return False


def window(master, key, title):
    """Where a tool builds itself: a ToolFrame in a new tab of the main window (shown at once),
    or a Toplevel of master when there is no main window. A key already open gets a new tab
    of its own ("key#2")."""
    a = app()
    if a is None or not hasattr(a, "new_tool_frame"):
        return tk.Toplevel(master)
    k, n = tab_key(key), 2
    while k in a.tools:
        k = "%s#%d" % (tab_key(key), n)
        n += 1
    return a.new_tool_frame(k, title)


class ToolFrame(tk.Frame):
    """A tool's tab: a Frame that stands in for the tool's window. title() names the tab,
    protocol("WM_DELETE_WINDOW", fn) is what the tab's ✕ does, lift()/deiconify() show the
    tab, destroy() closes it; geometry, minsize and the like do nothing."""

    def __init__(self, parent, host, key, title):
        tk.Frame.__init__(self, parent, bg=th.BG)
        self._host, self._key, self._title = host, key, title
        self._on_close = None
        self._closed = False
        self.panel = None  # open_tool_tab's frame inside it (None: the tool built into this frame)
        self.popped = False

    # ---- what a tool calls on its window ----
    def title(self, text=None):
        if text is None:
            return self._title
        self._title = text
        try:
            self._host.tool_title(self._key, text)
        except (AttributeError, tk.TclError):
            pass
        return None

    wm_title = title

    def geometry(self, *a):
        return ""

    def minsize(self, *a):
        return None

    maxsize = resizable = transient = iconphoto = overrideredirect = minsize
    wm_geometry = geometry

    def attributes(self, *a):
        return ""

    def protocol(self, name=None, func=None):
        if name == "WM_DELETE_WINDOW" and func is not None:
            self._on_close = func
        return ""

    def state(self, *a):
        return "normal"

    def lift(self, *a):
        try:
            self._host.show_tab(self._key)
        except (AttributeError, tk.TclError):
            pass

    deiconify = tkraise = lift

    def withdraw(self):
        return None

    def iconify(self):
        return None

    # ---- the tab ----
    def request_close(self):
        """The tab's ✕: what the tool's window close did (it may ask first and stay open)"""
        if self._on_close is not None:
            self._on_close()
        elif self.panel is not None and hasattr(self.panel, "close"):
            self.panel.close()
            try:
                if self.winfo_exists() and not self.panel.winfo_exists():
                    self.destroy()
            except tk.TclError:
                pass
        else:
            self.destroy()

    def destroy(self):
        if self._closed:
            return
        self._closed = True
        try:
            tk.Frame.destroy(self)
        except tk.TclError:
            pass
        try:
            self._host.tool_closed(self._key)
        except Exception:
            try:
                sys.modules["mirror"].log_error("closing a tool's tab")
            except Exception:
                pass
