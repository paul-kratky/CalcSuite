"""Make a PC copy never hangs (2026-11-28): with the links faked, no calculator needed.

- mirror.py run as the program and imported by the panels is one module, so the window work
  workers ask for (after() from another thread) reaches App.pump's queue
- pc_copy: a link command that never answers is ended (CMD_IDLE_S), Cancel ends one at once,
  the TI-89 Titanium's whole dump runs through every stage with a scripted link
- the PC copy dialog: a mirror that never lets go, a worker whose after() calls are lost, a
  dump that never answers (Cancel), a worker that ignores Cancel (the dialog stops waiting),
  TiEmu's download and CEmu's start always end on a status

    python -I tools/selftest/pc_copy_checks.py
"""

import os
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)


def check(ok, what):
    print("%-4s %s" % ("PASS" if ok else "FAIL", what))
    return 0 if ok else 1


# ---- mirror.py: one module under both names ----

DOUBLE_IMPORT = r"""
import importlib.util, sys, threading
sys.path.insert(0, sys.argv[1])
def load(name):
    spec = importlib.util.spec_from_file_location(name, sys.argv[1] + "/mirror.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod
main = load("calcsuite_main")       # As `python tools/mirror.py` / CalcSuite.exe run it
import mirror                       # As ui_panels.InfoSection does
other = load("calcsuite_copy")      # A second copy all the same (another path)
import tkinter as tk
got = []
t = threading.Thread(target=lambda: tk.Misc.after(None, 0, got.append, 1))
t.start(); t.join()
print("same=%s shared=%s queued=%d" % (mirror is main, other._TK_QUEUE is main._TK_QUEUE,
                                       main._TK_QUEUE.qsize()))
"""


def double_import_checks():
    p = subprocess.run([sys.executable, "-I", "-c", DOUBLE_IMPORT, TOOLS], capture_output=True,
                       text=True, timeout=120)
    out = (p.stdout + p.stderr).strip()
    if "No module named" in out and "tkinter" in out:
        print("SKIP mirror.py import (no Tk here)")
        return 0
    f = check("same=True" in out, "mirror.py run as the program: `import mirror` gives the same module")
    f += check("shared=True queued=1" in out, "a second copy of mirror.py shares the after() queue App.pump "
               "runs (a worker's window work is never lost)")
    if f:
        print(out[-800:])
    return f


# ---- pc_copy: hung links, Cancel, the 89's whole run ----

class HangSession(object):
    """A link helper that never answers: cmd() waits until it's ended"""

    def __init__(self):
        self.ended = threading.Event()
        self.closed = False

    def cmd(self, line, progress=None):
        self.ended.wait(60)
        return 4, ["ERR no answer from the handheld"]

    def abort(self):
        self.ended.set()

    def close(self):
        self.closed = True
        self.ended.set()


def rom_89():
    rom = bytearray(b"\x5a" * 0x400000)
    rom[4:8] = (0x800400).to_bytes(4, "big")
    return bytes(rom)


class Fake89(object):
    """The TI-89 Titanium as ti89-cli serve answers, scripted"""

    def __init__(self, log):
        self.log = log

    def cmd(self, line, progress=None):
        self.log.append(line.split()[0])
        if line == "info":
            return 0, ["INFO name=TI-89_Titanium os=3.10", "OK info"]
        if line.startswith("romdump "):
            rom = rom_89()
            for k in range(1, 5):
                if progress:
                    progress(k * len(rom) // 4, len(rom))
            with open(line.split(" ", 1)[1], "wb") as fh:
                fh.write(rom)
            return 0, ["OK romdump size=4194304"]
        return 0, ["OK"]

    def close(self):
        pass


def ce_appvars():
    """The CEmu dumper's AppVars for a made-up OS of 4 segments, whose ROM passes check_ce_rom"""
    import pc_copy as pc
    os_size = pc.CE_SEG * 4
    rom = bytearray(b"\x5a" * (pc.CE_SEG * 4))
    rom[0x20000:0x2000a] = bytes.fromhex("800f0000000480121300")  # Field 0x800F holding 0x8012 = 0x13
    out = {b"ROMData0": os_size.to_bytes(3, "little"), b"ROMData1": b"\x11" * pc.CE_SEG}
    for i in range(4):
        out[pc.ce_segment_name(i)] = bytes(rom[i * pc.CE_SEG:(i + 1) * pc.CE_SEG])
    return out


class FakeCE(object):
    """The TI-84 Plus CE as ti84-cli serve answers, scripted: the dumper's AppVars are there once
    Enter (key 05) has started it"""

    def __init__(self, log, state):
        self.log, self.state = log, state

    def cmd(self, line, progress=None):
        import calc_files as cf
        self.log.append(line.split()[0])
        if line == "info":
            return 0, ["INFO name=TI-84 Plus CE", "INFO os=5.4.0 ram_free=150000 storage_free=3000000", "OK"]
        if line == "key 05":
            self.state["dumped"] = True
        if line == "ls":
            items = []
            if self.state.get("dumped"):
                for n, data in sorted(ce_appvars().items()):
                    items.append("ITEM type=15 size=%d arch=1 locked=0 folder=- name=%s" %
                                 (len(data) + 2, cf.to_hex(n)))
            return 0, items + ["OK ls"]
        if line.startswith("get 15 "):
            name, local = line.split(" ")[3], line.split(" ", 5)[5]
            data = ce_appvars()[bytes.fromhex(name)]
            blob = len(data).to_bytes(2, "little") + data
            for k in (1, 2):
                if progress:
                    progress(k * len(blob) // 2, len(blob))
            with open(local, "wb") as fh:
                fh.write(blob)
            return 0, ["OK get"]
        return 0, ["OK"]

    def close(self):
        pass


def pc_copy_checks():
    import pc_copy as pc
    f = 0
    saved = (pc.CMD_IDLE_S, pc._backup, pc._write_rom)
    try:
        pc.CMD_IDLE_S = 0.6
        hung = HangSession()
        t0 = time.time()
        try:
            pc.dump_rom("89", connect=lambda: hung)
            err = None
        except pc.PcCopyError as e:
            err = e
        f += check(isinstance(err, pc.PcCopyError) and not isinstance(err, pc.Cancelled) and
                   err.stage == "connect" and "stopped answering" in str(err) and time.time() - t0 < 5
                   and hung.closed, "PC copy: a link command that never answers is ended (no hang)")

        pc.CMD_IDLE_S = 60
        hung, cancel, out = HangSession(), threading.Event(), {}

        def work():
            try:
                pc.dump_rom("84", cancel=cancel, connect=lambda: hung)
            except pc.PcCopyError as e:
                out["err"] = e
        w = threading.Thread(target=work, daemon=True)
        w.start()
        time.sleep(0.4)
        t0 = time.time()
        cancel.set()
        w.join(5)
        f += check(not w.is_alive() and isinstance(out.get("err"), pc.Cancelled) and time.time() - t0 < 2,
                   "PC copy: Cancel ends a command that hangs, at once")

        steps = pc._Steps(None, threading.Event())
        threading.Timer(0.3, steps.cancel.set).start()
        t0 = time.time()
        try:
            pc._wait_ce_dump(lambda: hung, steps, first_wait=60)
            got = None
        except pc.PcCopyError as e:
            got = e
        f += check(isinstance(got, pc.Cancelled) and time.time() - t0 < 2,
                   "PC copy: Cancel while the CE's dumper runs stops the waiting at once")

        tmp = tempfile.mkdtemp(prefix="calcsuite_pccopy_")
        pc._backup = lambda slug, s, info, steps, folder=None: (tmp, {"failed": []})

        def write_rom(slug, rom, meta):
            path = os.path.join(tmp, "zz.rom")
            with open(path, "wb") as fh:
                fh.write(rom)
            return path, dict(meta, sha256=pc.sha256_bytes(rom))
        pc._write_rom = write_rom
        seen, log = [], []
        res = pc.dump_rom("89", lambda st, text, d=None, t=None: seen.append((st, d, t)),
                          connect=lambda: Fake89(log))
        stages = []
        for st, _d, _t in seen:
            if not stages or stages[-1] != st:
                stages.append(st)
        f += check(res["ok"] and stages == ["connect", "check", "backup", "send", "run", "dump", "save",
                                            "clean", "done"] and
                   any(st == "dump" and d == t == 0x400000 for st, d, t in seen) and
                   log[:6] == ["info", "ls", "send", "home", "exec", "romdump"],
                   "PC copy: the 89's whole dump (scripted link) reports every stage and the bytes")
    finally:
        pc.CMD_IDLE_S, pc._backup, pc._write_rom = saved
    return f


# ---- The dialog ----

class FakeCalc(object):
    def __init__(self, slug):
        self.slug = slug
        self.title = {"ti84": "TI-84 Plus CE", "ti89": "TI-89 Titanium"}[slug]


class FakeMirror(object):
    def __init__(self, slug, lets_go=True):
        self.calc = FakeCalc(slug)
        self.session = object()
        self.let_go = threading.Event()
        self.lets_go = lets_go
        self.reconnects = 0

    def connected(self):
        return True

    def release(self):
        if self.lets_go:
            threading.Timer(0.2, self.let_go.set).start()

    def reconnect(self):
        self.reconnects += 1
        self.let_go.clear()

    def set_status(self, text):
        pass


class FakeSection(object):
    def __init__(self, root, m):
        import tkinter as tk
        self.m, self.frame = m, tk.Frame(root)

    def build_pc_copy(self):
        pass


def texts(widget):
    import tkinter as tk
    out = []
    for c in widget.winfo_children():
        try:
            if isinstance(c, tk.Label):
                out.append(str(c.cget("text")))
        except tk.TclError:
            pass
        out += texts(c)
    return out


def dialog_checks():
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
    except Exception as e:
        print("SKIP PC copy dialog (no Tk here: %s)" % e)
        return 0
    import ui_panels as up
    import pc_copy as pc
    from tkinter import messagebox
    f = 0
    logged = []
    saved = dict(ask=messagebox.askokcancel, log=up.log_error, wait=up.RELEASE_WAIT_S,
                 give_up=up.CANCEL_GIVE_UP_S, after=tk.Misc.after, dump=pc.dump_rom,
                 roms=up.existing_roms, folder=up.show_in_folder, get=pc.get_emulator,
                 open_=pc.open_in_emulator, tiemu=pc.tiemu_path, cemu=pc.cemu_path)
    real_after = tk.Misc.after
    main_thread = threading.current_thread()

    def lossy_after(self, ms, func=None, *args):  # What the bug did: a worker's after() is lost
        if func is not None and threading.current_thread() is not main_thread:
            return None
        return real_after(self, ms, func, *args)

    def until(cond, seconds):
        t0 = time.time()
        while time.time() - t0 < seconds:
            root.update()
            if cond():
                return True
            time.sleep(0.02)
        return False

    # Every dialog lives until the end: its Tk variables are then let go on this thread, not by
    # a worker dropping the last reference (Tk would print "main thread is not in main loop")
    keep = []

    def make(slug="ti89", lets_go=True):
        m = FakeMirror(slug, lets_go)
        d = up.PcCopyDialog(FakeSection(root, m), "make")
        keep.append(d)
        d.start()
        return m, d

    def shown(d, needle):
        try:
            return any(needle in t for t in texts(d.win))
        except tk.TclError:
            return False

    try:
        messagebox.askokcancel = lambda *a, **k: True
        up.log_error = lambda where: logged.append(where)
        tk.Misc.after = lossy_after

        # A mirror that never lets go
        up.RELEASE_WAIT_S = 1
        m, d = make(lets_go=False)
        ok = until(lambda: shown(d, "wasn't made"), 6)
        f += check(ok and shown(d, "didn't let go") and m.reconnects == 1 and logged,
                   "PC copy window: a mirror that never lets go ends in an error, the link given back, logged")
        d.close()
        up.RELEASE_WAIT_S = saved["wait"]

        # The real run's shape, with every worker after() lost: progress and the end still show
        seen_stage = []

        def dump_ok(model, report=None, cancel=None, connect=None):
            for st in ("connect", "check", "backup", "send", "run", "dump"):
                report(st, "step %s" % st, None, None)
                time.sleep(0.15)
            report("dump", "Reading the ROM: 50%", 2, 4)
            time.sleep(0.3)
            return {"ok": True, "rom": "C:\\zz\\ti89t-zz.rom", "size": 4194304, "os": "3.10",
                    "backup": None, "notes": [], "seconds": 3}
        pc.dump_rom = dump_ok
        pc.tiemu_path = lambda: None
        m, d = make()
        until(lambda: (seen_stage.append(str(d.stage.cget("text"))) or False) if d.running else True, 10)
        ok = shown(d, "Your PC copy is made")
        f += check(ok and "Reading the ROM..." in seen_stage and m.reconnects == 1,
                   "PC copy window: progress and the result arrive although the workers' after() is lost")
        d.close()

        # The whole real dump_rom (scripted 84 and 89 links): the one bar only moves forward, to 100%
        tmp = tempfile.mkdtemp(prefix="calcsuite_pcbar_")

        def write_rom(slug, rom, meta):
            path = os.path.join(tmp, "zz-%s.rom" % slug)
            with open(path, "wb") as fh:
                fh.write(rom)
            return path, dict(meta, sha256=pc.sha256_bytes(rom))
        bar_saved = (pc._default_connect, pc._backup, pc._write_rom, pc.CE_DUMP_WAIT)
        try:
            pc.dump_rom = saved["dump"]
            pc._backup = lambda slug, s, info, steps, folder=None: (tmp, {"failed": []})
            pc._write_rom = write_rom
            pc.CE_DUMP_WAIT = 1.0
            for slug in ("ti84", "ti89"):
                state, log = {}, []
                pc._default_connect = lambda sl, state=state, log=log: (
                    lambda: FakeCE(log, state) if sl == "ti84" else Fake89(log))
                m, d = make(slug)
                ended = until(lambda: not d.running, 30)
                vals = list(d.bar_values)
                f += check(ended and shown(d, "Your PC copy is made") and len(set(vals)) >= 8 and
                           all(b >= a for a, b in zip(vals, vals[1:])) and vals[-1] == up.BAR_MAX,
                           "PC copy window (%s, the whole dump): the bar never goes back and ends at 100%% "
                           "(%d values)" % (slug, len(vals)))
                d.close()
        finally:
            pc._default_connect, pc._backup, pc._write_rom, pc.CE_DUMP_WAIT = bar_saved
            pc.dump_rom = saved["dump"]
        f += check(up.overall_progress("ti84", "wait", 45, 90) > up.overall_progress("ti84", "tidy") and
                   up.overall_progress("ti89", "done") == 1.0 and up.overall_progress("ti89", "zz") is None,
                   "PC copy bar: stages weighted in order, done is 100%")

        # A dump that never answers: Cancel ends it
        def dump_hang(model, report=None, cancel=None, connect=None):
            report("wait", "The calculator is dumping its ROM", 1, 90)
            cancel.wait(60)
            raise pc.Cancelled("wait")
        pc.dump_rom = dump_hang
        m, d = make()
        until(lambda: "dump program" in str(d.stage.cget("text")), 5)
        d.do_cancel()
        ok = until(lambda: shown(d, "Cancelled"), 5)
        f += check(ok and m.reconnects == 1, "PC copy window: Cancel while the dump runs ends it, link given back")
        d.close()

        # A worker that ignores Cancel: the window stops waiting
        up.CANCEL_GIVE_UP_S = 1
        stuck = threading.Event()

        def dump_stuck(model, report=None, cancel=None, connect=None):
            report("backup", "Backing up", None, None)
            stuck.wait(60)
            raise pc.PcCopyError("backup", "late")
        pc.dump_rom = dump_stuck
        logged[:] = []
        m, d = make()
        until(lambda: "Backing up" in str(d.stage.cget("text")), 5)
        d.do_cancel()
        ok = until(lambda: shown(d, "stopped waiting"), 6)
        d.close()
        closed = until(lambda: not d.alive(), 2)
        stuck.set()
        f += check(ok and closed and m.reconnects >= 1 and logged,
                   "PC copy window: a worker that ignores Cancel: the window stops waiting, closes, logs it")
        up.CANCEL_GIVE_UP_S = saved["give_up"]

        # Open my PC copy: TiEmu's download shows its progress and always ends
        up.existing_roms = lambda slug: [{"path": "C:\\zz\\%s.rom" % slug, "made": time.time(), "info": {}}]
        up.show_in_folder = lambda path: None
        statuses = []

        def get_tiemu(model, report=None):
            for k in range(5):
                report("download", "Downloading: %d KB of 3000 KB" % (k * 750), k * 750, 3000)
                time.sleep(0.1)
            return {"ready": False, "path": "C:\\zz\\setup.exe", "todo": "Run zz setup yourself"}
        pc.get_emulator = get_tiemu
        d = up.PcCopyDialog(FakeSection(root, FakeMirror("ti89")), "open")
        keep.append(d)
        d.get_tiemu()
        until(lambda: statuses.append(d.status.get()) or "Run zz setup" in d.status.get(), 6)
        f += check("Run zz setup" in d.status.get() and any("(50%)" in s for s in statuses) and
                   str(d.emu_btn.cget("state")) == "normal",
                   "PC copy window: TiEmu's download shows a percentage and ends on what to do next")
        d.close()

        def get_fails(model, report=None):
            raise pc.PcCopyError("download", "zz checksum mismatch")
        pc.get_emulator = get_fails
        logged[:] = []
        d = up.PcCopyDialog(FakeSection(root, FakeMirror("ti89")), "open")
        keep.append(d)
        d.get_tiemu()
        ok = until(lambda: "zz checksum" in d.status.get(), 4)
        f += check(ok and logged, "PC copy window: a failed download says why and is logged")
        d.close()

        # CEmu: once it's started the status says so
        pc.get_emulator = lambda model, report=None: {"ready": True, "path": "C:\\zz\\CEmu.exe"}
        pc.open_in_emulator = lambda *a, **k: None
        pc.cemu_path = lambda: "C:\\zz\\CEmu.exe"
        d = up.PcCopyDialog(FakeSection(root, FakeMirror("ti84")), "open")
        keep.append(d)
        d.open_cemu()
        ok = until(lambda: "CEmu is opening" in d.status.get(), 4)
        f += check(ok, "PC copy window: Open in CEmu ends on \"CEmu is opening\"")
        d.close()
    finally:
        messagebox.askokcancel = saved["ask"]
        up.log_error = saved["log"]
        up.RELEASE_WAIT_S, up.CANCEL_GIVE_UP_S = saved["wait"], saved["give_up"]
        tk.Misc.after = saved["after"]
        pc.dump_rom, pc.get_emulator, pc.open_in_emulator = saved["dump"], saved["get"], saved["open_"]
        pc.tiemu_path, pc.cemu_path = saved["tiemu"], saved["cemu"]
        up.existing_roms, up.show_in_folder = saved["roms"], saved["folder"]
        time.sleep(0.3)  # The workers end (their last lines run without the dialogs)
        del keep[:]
        try:
            root.destroy()
        except tk.TclError:
            pass
    return f


def main():
    return double_import_checks() + pc_copy_checks() + dialog_checks()


if __name__ == "__main__":
    failures = main()
    print("\n%s" % ("ALL PASSED" if not failures else "%d FAILURE(S)" % failures))
    sys.exit(1 if failures else 0)
