# SPDX-License-Identifier: MIT
"""Test in PC copy (the Program editor): a TI-84 Plus CE program run in CEmu with the user's own
ROM before it goes to the real calculator. The window: the keys to press after it starts, the
expected screen (optional), Run, then the screen it ended on and passed / failed.

The test itself: pc_test.py (CEmu's autotester, CEmu a separate program). The keys and the
expected screen of each program are kept beside its built file: <name>.pctest.json.
"""

import json
import os
import queue
import threading
import time
import tkinter as tk

import pc_test
import ui_theme as th

KEYS_HELP = ("Keys after the program starts, separated by commas: enter, 2nd, alpha, clear, 0-9, + - * /, "
             "(, ), up, down, left, right, prgm, math, sto ... and waits: wait 500 (ms).")


def log_error(where):
    try:
        import mirror
        mirror.log_error(where)
    except Exception:
        pass


def saved_test_path(program_file):
    return os.path.splitext(program_file)[0] + ".pctest.json"


def load_saved(program_file):
    try:
        with open(saved_test_path(program_file), encoding="utf-8") as fh:
            d = json.load(fh)
        return {"keys": str(d.get("keys", "")), "expected": str(d.get("expected", "")),
                "wait": int(d.get("wait", 1500))}
    except (OSError, ValueError, TypeError):
        return {"keys": "", "expected": "", "wait": 1500}


def save_saved(program_file, keys, expected, wait):
    try:
        with open(saved_test_path(program_file), "w", encoding="utf-8") as fh:
            json.dump({"keys": keys, "expected": expected, "wait": wait}, fh, indent=1)
    except OSError:
        log_error("saving the PC copy test of %s" % program_file)


class PcTestDialog(object):
    """One program's test. Workers never touch Tk: their results go through self.inbox, which
    drain() runs on Tk's thread."""

    def __init__(self, parent, program_file, name, run_now=True):
        self.file, self.name = program_file, name
        self.inbox = queue.SimpleQueue()
        self.cancel = threading.Event()
        self.worker = None
        self.gone = False
        self.photo = None
        self.result = None
        # A tab of the main window (a window of its own without it)
        import tool_tabs
        w = self.win = tool_tabs.window(parent, "pctest:%s" % name, "Test %s" % name)
        w.title("Test %s in the PC copy" % name)
        w.configure(bg=th.BG)
        w.geometry("760x860")
        w.minsize(620, 520)
        w.protocol("WM_DELETE_WINDOW", self.close)
        w.bind("<Destroy>", lambda e: setattr(self, "gone", True) if e.widget is w else None, add="+")
        th.dark_title_bar_when_shown(w)
        saved = load_saved(program_file)
        body = tk.Frame(w, bg=th.BG)
        body.pack(fill="both", expand=True, padx=16, pady=14)
        tk.Label(body, text="Test %s in your PC copy (CEmu)" % name, bg=th.BG, fg=th.FG,
                 font=(th.FONT, 12, "bold"), anchor="w").pack(fill="x")
        tk.Label(body, text="CEmu starts with your own ROM (a separate copy: your PC copy's state isn't "
                 "touched), resets, gets %s, runs it, presses your keys and checks the screen. Your "
                 "calculator isn't touched." % os.path.basename(program_file), bg=th.BG, fg=th.DIM,
                 anchor="w", justify="left", wraplength=700).pack(fill="x", pady=(4, 10))
        form = tk.Frame(body, bg=th.BG)
        form.pack(fill="x")

        def entry(row, label, value, width=60):
            tk.Label(form, text=label, bg=th.BG, fg=th.DIM, anchor="w").grid(row=row, column=0, sticky="w",
                                                                           pady=3, padx=(0, 8))
            var = tk.StringVar(master=w, value=value)
            e = tk.Entry(form, textvariable=var, width=width, bg=th.PANEL2, fg=th.FG, insertbackground=th.FG,
                         relief="flat", font=(th.MONO, 10))
            e.grid(row=row, column=1, sticky="we", pady=3, ipady=3)
            return var, e
        form.columnconfigure(1, weight=1)
        self.keys_var, self.keys_entry = entry(0, "Keys", saved["keys"])
        self.wait_var, _e = entry(1, "Wait before the keys (ms)", str(saved["wait"]), 8)
        _e.grid(sticky="w")
        self.expect_var, _e = entry(2, "Expected screen (CRC)", saved["expected"], 12)
        _e.grid(sticky="w")
        tk.Label(body, text=KEYS_HELP + " No expected screen: the run shows what came, and \"Expect this "
                 "screen\" keeps it for next time.", bg=th.BG, fg=th.DIM, anchor="w", justify="left",
                 wraplength=700).pack(fill="x", pady=(6, 8))
        row = tk.Frame(body, bg=th.BG)
        row.pack(fill="x")
        self.run_btn = th.button(row, "Run the test", self.run)
        self.run_btn.pack(side="left")
        self.keep_btn = th.button(row, "Expect this screen", self.keep, state="disabled")
        self.keep_btn.pack(side="left", padx=(6, 0))
        self.folder_btn = th.button(row, "Show the files", self.show_files, state="disabled")
        self.folder_btn.pack(side="left", padx=(6, 0))
        th.button(row, "Close", self.close).pack(side="right")
        self.verdict = tk.Label(body, text="", bg=th.BG, fg=th.FG, font=(th.FONT, 14, "bold"), anchor="w")
        self.verdict.pack(fill="x", pady=(12, 2))
        self.status = tk.Label(body, text="", bg=th.BG, fg=th.DIM, anchor="w", justify="left", wraplength=700)
        self.status.pack(fill="x")
        self.screen = tk.Label(body, bg=th.BG, bd=0)
        self.screen.pack(anchor="w", pady=(8, 0))
        self.drain()
        if run_now:
            w.after(200, self.run)

    def alive(self):
        return not self.gone

    def ui(self, fn, *args):
        if not self.gone:
            self.inbox.put((fn, args))

    def drain(self):
        if self.gone:
            return
        try:
            for _ in range(50):
                try:
                    fn, args = self.inbox.get_nowait()
                except queue.Empty:
                    break
                try:
                    fn(*args)
                except Exception:
                    log_error("the PC copy test window")
        finally:
            if not self.gone:
                try:
                    self.win.after(50, self.drain)
                except tk.TclError:
                    pass

    def close(self):
        self.cancel.set()  # A running test ends its CEmu (pc_test closes only the one it started)
        try:
            self.win.destroy()
        except tk.TclError:
            pass

    def run(self):
        if self.worker is not None and self.worker.is_alive():
            return
        keys, expected = self.keys_var.get().strip(), self.expect_var.get().strip()
        try:
            wait = int(self.wait_var.get().strip() or "0")
            pc_test.parse_script(keys)
            pc_test.test_config(self.file, self.name, keys, [expected] if expected else ())
        except (ValueError, pc_test.TestError) as e:
            self.verdict.configure(text="Can't run it", fg=th.RED)
            self.status.configure(text=str(e))
            return
        save_saved(self.file, keys, expected, wait)
        self.cancel.clear()
        self.run_btn.configure(state="disabled")
        self.keep_btn.configure(state="disabled")
        self.verdict.configure(text="Running...", fg=th.ACCENT)
        self.status.configure(text="Starting CEmu...")
        t0 = time.time()

        def work():
            try:
                res = pc_test.run_test(self.file, self.name, keys, [expected] if expected else (), wait_ms=wait,
                                       report=lambda t: self.ui(self.status.configure, {"text": t}),
                                       cancel=self.cancel)
                self.ui(self.done, res, None)
            except pc_test.TestError as e:
                self.ui(self.done, None, e)
            except Exception as e:
                log_error("testing %s in the PC copy" % self.name)
                self.ui(self.done, None, e)
        self.t0 = t0
        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def done(self, res, err):
        self.run_btn.configure(state="normal")
        if err is not None:
            self.verdict.configure(text="The test didn't run", fg=th.RED)
            self.status.configure(text=str(err)[:1].upper() + str(err)[1:])
            return
        self.result = res
        self.folder_btn.configure(state="normal")
        if res["ok"] is True:
            self.verdict.configure(text="Passed: the screen is the expected one", fg=th.FG)
        elif res["ok"] is False:
            self.verdict.configure(text="Failed: the screen isn't the expected one", fg=th.RED)
        else:
            self.verdict.configure(text="Ran: this is the screen it ended on", fg=th.FG)
        self.status.configure(text="In %.0f s. The screen's CRC: %s%s." % (
            res["seconds"], res["crc"] or "?",
            "" if res["ok"] is not False else " (expected %s)" % self.expect_var.get().strip()))
        if res["crc"] and res["ok"] is not True:
            self.keep_btn.configure(state="normal")
        if res["screenshot"]:
            try:
                img = tk.PhotoImage(master=self.win, file=res["screenshot"])
                self.photo = img.zoom(2, 2) if img.width() <= 320 else img
                self.screen.configure(image=self.photo)
            except tk.TclError:
                log_error("showing the PC copy test's screenshot")

    def keep(self):
        if self.result and self.result.get("crc"):
            self.expect_var.set(self.result["crc"])
            save_saved(self.file, self.keys_var.get().strip(), self.result["crc"],
                       int(self.wait_var.get().strip() or "0"))
            self.keep_btn.configure(state="disabled")
            self.status.configure(text="Kept: the next run passes when the screen ends like this (%s)."
                                  % self.result["crc"])

    def show_files(self):
        if self.result:
            try:
                os.startfile(self.result["folder"])
            except OSError:
                log_error("opening the PC copy test's folder")
