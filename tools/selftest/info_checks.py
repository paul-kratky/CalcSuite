"""The Info panel always ends with an answer (2026-11-28): with every link and Windows query
faked, no calculator needed.

- calc_doctor._run: a program that never answers, and one whose child keeps the output pipe
  open after it is killed (subprocess.run's own timeout then waited forever)
- calc_doctor.diagnose: each source succeeding, raising, failing its query, or hanging: the
  report always comes, within its time limits, the problems listed in "errors"
- the Info panel's connection doctor: a check that hangs, fails, or succeeds always ends on a
  report or a plain error, and errors.log gets the problem
- nspire_link.Session: a helper that goes quiet is stopped after idle_timeout, never held
- calc_manager.Manager.job: a request left unanswered says why while it waits, then shows
  the answer when it comes
- mirror.link_problem_text: the TI-Nspire's "no answer" says to replug it

    python -I tools/selftest/info_checks.py
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

import calc_doctor  # noqa: E402


def check(ok, what):
    print("%-4s info %s" % ("PASS" if ok else "FAIL", what))
    return 0 if ok else 1


# ---- calc_doctor._run ----

GRANDCHILD = r"""
import subprocess, sys, time
# A child that inherits our stdout and outlives us: the pipe stays open after we're killed
subprocess.Popen([sys.executable, "-c", "import time; time.sleep(8)"])
time.sleep(30)
"""


def run_checks():
    f = 0
    t = time.time()
    code, why = calc_doctor._run([sys.executable, "-c", "import time; time.sleep(30)"], timeout=1)
    took = time.time() - t
    f += check(code is None and "didn't answer within 1 s" in why and took < 4,
               "_run: a program that never answers ends in %.1f s (%s)" % (took, why))
    t = time.time()
    code, why = calc_doctor._run([sys.executable, "-c", GRANDCHILD], timeout=1)
    took = time.time() - t
    f += check(code is None and took < 5,
               "_run: a killed program whose child holds the pipe ends in %.1f s" % took)
    code, out = calc_doctor._run([sys.executable, "-c", "print('DEVICE pid=e008')"], timeout=10)
    f += check(code == 0 and "pid=e008" in out, "_run: an answer comes through")
    code, why = calc_doctor._run([os.path.join(tempfile.gettempdir(), "no-such-program.exe")])
    f += check(code is None and why, "_run: a missing program is an error, not an exception")
    return f


# ---- calc_doctor.diagnose with the sources faked ----

HELPER_OK = {"devices": [{"pid": "e008", "present": True, "service": "WinUSB", "provider": "libwdi",
                          "problem": 0, "access": "not-probed", "instance": "USB\\VID_0451&PID_E008\\1",
                          "desc": "TI-84 Plus CE"}], "packages": []}
PNP_OK = [{"PNPDeviceID": "USB\\VID_0451&PID_E004\\2", "Name": "TI-89 Titanium",
           "Service": "WinUSB", "ConfigManagerErrorCode": 0, "Present": True}]


def diagnose_checks():
    f = 0
    names = ("running_programs", "helper_list", "libusb_pids", "pnp_devices")
    saved = {n: getattr(calc_doctor, n) for n in names}
    saved_consts = (calc_doctor.WINDOWS, calc_doctor.QUERY_TIMEOUT_S, calc_doctor.PROCESSES_TIMEOUT_S)
    release = threading.Event()

    def hang(*_a, **_k):
        release.wait(60)
        return None

    def boom(*_a, **_k):
        raise RuntimeError("WMI is broken")

    def no_answer(*_a, **_k):
        raise calc_doctor.QueryError("powershell.exe didn't answer within 8 s")

    def fake(programs=lambda: ([], []), helper=lambda probe=False: HELPER_OK,
             usb=lambda: {0xE008}, pnp=lambda: PNP_OK):
        calc_doctor.running_programs = programs
        calc_doctor.helper_list = helper
        calc_doctor.libusb_pids = usb
        calc_doctor.pnp_devices = pnp

    try:
        calc_doctor.WINDOWS = True
        calc_doctor.QUERY_TIMEOUT_S, calc_doctor.PROCESSES_TIMEOUT_S = 1, 1

        fake()
        r = calc_doctor.diagnose(probe=False)
        dev = [d for d in r["devices"] if d["pid"] == "e008"]
        f += check(dev and dev[0]["status"] == "ready" and not r["errors"],
                   "diagnose: every source answers -> the 84 is ready, no errors")

        fake(helper=hang)
        t = time.time()
        r = calc_doctor.diagnose(probe=False)
        took = time.time() - t
        f += check(took < 6 and any("driver helper" in e and "didn't answer" in e for e in r["errors"]),
                   "diagnose: the driver helper hangs -> the report in %.1f s, the hang listed" % took)
        f += check(any(d["pid"] == "e004" for d in r["devices"]),
                   "diagnose: ... and Windows' device list stands in for the helper")

        fake(programs=hang, helper=hang, usb=hang, pnp=hang)
        t = time.time()
        r = calc_doctor.diagnose(probe=False)
        took = time.time() - t
        f += check(took < 10 and len(r["errors"]) == 4 and r["devices"],
                   "diagnose: everything hangs -> a report in %.1f s with 4 errors" % took)

        fake(pnp=boom, usb=no_answer)
        r = calc_doctor.diagnose(probe=False)
        f += check(any("WMI is broken" in e for e in r["errors"]) and
                   any("powershell.exe didn't answer" in e for e in r["errors"]) and
                   any(d["pid"] == "e008" for d in r["devices"]),
                   "diagnose: a source that raises or whose query times out is listed, the rest used")
        text = calc_doctor.format_report(r)
        f += check("Not checked: " in text, "format_report lists what wasn't checked")
    finally:
        release.set()
        for n, fn in saved.items():
            setattr(calc_doctor, n, fn)
        calc_doctor.WINDOWS, calc_doctor.QUERY_TIMEOUT_S, calc_doctor.PROCESSES_TIMEOUT_S = saved_consts
    return f


# ---- The window: the Info panel's doctor and the Manager's requests ----

class FakeCalc(object):
    def __init__(self, slug="ti84", title="TI-84 Plus CE", pid=0xE008):
        self.slug, self.title, self.pid = slug, title, pid


class FakeLog(object):
    def __init__(self):
        self.lines = []

    def log_error(self, where, detail=None):
        self.lines.append((where, detail))


def pump(root, until, seconds):
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        if until():
            return True
        time.sleep(0.02)
    return until()


def labels(frame):
    out = []
    for w in frame.winfo_children():
        try:
            out.append(w.cget("text"))
        except Exception:
            pass
        out += labels(w)
    return out


def doctor_ui_checks(tk, root):
    import ui_panels
    f = 0
    saved = calc_doctor.diagnose
    release = threading.Event()
    try:
        for case, fn, want in (
                ("hangs", lambda probe=False: release.wait(60), "didn't finish within 1 s"),
                ("raises", lambda probe=False: (_ for _ in ()).throw(OSError("access denied")),
                 "Not checked: The check failed: OSError: access denied"),
                ("answers", lambda probe=False: {"devices": [
                    {"pid": "e008", "status": "ready", "headline": "Ready", "text": "Has WinUSB",
                     "present": True}], "notes": [], "errors": [], "programs": []}, "Ready")):
            calc_doctor.diagnose = fn
            info = ui_panels.InfoSection.__new__(ui_panels.InfoSection)
            info.frame = tk.Frame(root)
            info.doctor = tk.Frame(info.frame)
            info.doctor.pack()

            class M(object):
                calc = FakeCalc()
            info.m = M()
            info.mirror_mod = FakeLog()
            info.DOCTOR_WAIT_S = 1
            info.check()
            started = any("Checking Windows' drivers" in t for t in labels(info.doctor))
            ok = pump(root, lambda: any(want in t for t in labels(info.doctor)), 5)
            f += check(started and ok, "the doctor %s -> the panel shows %r" % (case, want))
            if case != "answers":
                f += check(bool(info.mirror_mod.lines), "the doctor %s -> errors.log gets it" % case)
            info.frame.destroy()
    finally:
        release.set()
        calc_doctor.diagnose = saved
    return f


class Status(object):
    def __init__(self):
        self.text = ""

    def set(self, text):
        self.text = text


def manager_checks(tk, root):
    import calc_manager
    f = 0

    class Link(object):
        def __init__(self, session):
            self.session = session
            self.calc = FakeCalc("nspire", "TI-Nspire", 0xE022)
            self.link_problem = None
            self.waiting = []

        def queue(self, line, note, done, progress):
            self.waiting.append((line, done))

    for connected in (True, False):
        mgr = calc_manager.Manager.__new__(calc_manager.Manager)
        mgr.m = Link(object() if connected else None)
        if not connected:
            mgr.m.link_problem = ("The TI-Nspire isn't answering: unplug it, wait 3 seconds, plug "
                                  "it back in (it allows one connection per plug-in)")
        mgr.calc, mgr.slug, mgr.open, mgr.pending = mgr.m.calc, "nspire", True, 0
        mgr.win = tk.Frame(root)
        mgr.status = Status()  # No Tk variable: one freed on another thread would abort Tcl
        mgr.LATE_S = 0.3
        logged = FakeLog()
        mgr.log_error = logged.log_error  # Never the real errors.log
        shown = []
        got = []
        mgr.job("info", lambda code, lines: got.append(code), late=shown.append)
        pump(root, lambda: shown, 3)
        if connected:
            f += check(bool(logged.lines), "Manager.job: a connected link that stays silent goes to errors.log")
            f += check(shown and "No answer yet" in shown[-1],
                       "Manager.job: an unanswered request says why after LATE_S (%r)" %
                       (shown[-1][:40] if shown else None))
        else:
            f += check(shown and "unplug it, wait 3 seconds" in shown[-1],
                       "Manager.job: waiting for a TI-Nspire that needs replugging says so")
        mgr.m.waiting[0][1](0, ["OK"])  # The answer comes after all
        pump(root, lambda: got, 2)
        n = len(shown)
        pump(root, lambda: False, 0.5)
        f += check(got == [0] and len(shown) == n, "Manager.job: the answer still shows, the waiting stops")
        mgr.win.destroy()
    return f


def window_checks():
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
    except Exception as e:
        print("SKIP info window checks (no Tk here: %s)" % e)
        return 0
    try:
        return doctor_ui_checks(tk, root) + manager_checks(tk, root)
    finally:
        import gc
        gc.collect()  # Free the Tk objects here, on Tk's thread, before the root goes
        root.destroy()
        del root
        gc.collect()


# ---- nspire_link.Session: a helper that goes quiet ----

FAKE_HELPER = r"""
import sys, time
print("END 0", flush=True)
for line in sys.stdin:
    cmd = line.strip()
    if cmd == "quit":
        break
    if cmd == "hang":
        time.sleep(60)
    print("INFO name=ZZFAKE", flush=True)
    print("END 0", flush=True)
"""


def session_checks():
    import nspire_link
    f = 0
    fd, path = tempfile.mkstemp(suffix=".py")
    with os.fdopen(fd, "w") as fh:
        fh.write(FAKE_HELPER)
    s = None
    try:
        s = nspire_link.Session(argv=[sys.executable, "-I", path], idle_timeout=1, cli=sys.executable)
        code, lines = s.cmd("info")
        f += check(code == 0 and "INFO name=ZZFAKE" in lines, "Session: a command answers")
        t = time.time()
        code, lines = s.cmd("hang")
        took = time.time() - t
        f += check(code == 4 and took < 4 and not s.alive() and s.dead,
                   "Session: a helper silent for idle_timeout is stopped (%.1f s: %s)" % (took, lines[-1]))
        code, lines = s.cmd("info")
        f += check(code == 4 and "closed" in lines[-1], "Session: after that every command says closed")
    finally:
        if s is not None:
            s.close(timeout=1)
        try:
            os.remove(path)
        except OSError:
            pass
    return f


def mirror_checks():
    try:
        import mirror
    except Exception as e:
        print("SKIP mirror.link_problem_text (mirror.py doesn't import here: %s)" % e)
        return 0
    f = 0
    t = mirror.link_problem_text(FakeCalc("nspire", "TI-Nspire", 0xE022), ["no answer from the handheld"])
    f += check(t and t.startswith("The TI-Nspire isn't answering: unplug it, wait 3 seconds, plug it "
                                  "back in (it allows one connection per plug-in)"),
               "mirror: the Nspire's 'no answer' says to replug it")
    f += check(mirror.link_problem_text(FakeCalc(), ["no answer from the handheld"]) is None,
               "mirror: the 84's 'no answer' keeps the usual text")
    f += check(mirror.QUIET_AFTER.get("setclock", 0) >= 2,
               "mirror: no picture for a moment after setclock")
    return f


def main():
    import gc
    # Tk objects other suites left behind are freed now, on Tk's thread: freed later by a
    # collection that happens to run on one of these checks' worker threads, Tcl aborts
    gc.collect()
    f = run_checks() + diagnose_checks() + session_checks() + window_checks() + mirror_checks()
    gc.collect()
    return f


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
