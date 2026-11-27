"""Connection doctor: why a TI calculator does or doesn't talk to CalcSuite, and the fix.

    python -I tools/calc_doctor.py                 the report, in plain English
    python -I tools/calc_doctor.py --json          the same as JSON (what diagnose() returns)
    python -I tools/calc_doctor.py --no-probe      don't test-open the calculators
    python -I tools/calc_doctor.py --install-winusb e008 [--dry-run]
    python -I tools/calc_doctor.py --restore-ti e008 [--dry-run]

Read-only unless --install-winusb / --restore-ti is given without --dry-run: those start
tools/bin/calcsuite-driver.exe elevated, so Windows shows its admin (UAC) prompt.

It puts together what Windows knows about each TI USB device (from calcsuite-driver.exe
"list", or PowerShell's Win32_PnPEntity when the helper is missing), what libusb sees
(ti84-cli.exe "devices", which opens nothing), and which TI programs are running.
How the app calls it: docs/dev/DOCTOR.md.

MIT licence (like the rest of the app). No third-party modules. Windows only; on other
systems diagnose() reports that it has nothing to check.
"""

import base64
import csv
import io
import json
import os
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
BIN = os.path.join(HERE, "bin")
HELPER = os.path.join(BIN, "calcsuite-driver.exe")
TI84_CLI = os.path.join(BIN, "ti84-cli.exe")

MODELS = {
    0xE008: "TI-84 Plus CE",
    0xE004: "TI-89 Titanium",
    0xE003: "TI-84 Plus",
    0xE022: "TI-Nspire CX II",
    0xE012: "TI-Nspire",
}

# Fix action ids (what the UI's button does)
INSTALL_WINUSB = "install_winusb"
RESTORE_TI = "restore_ti"
CLOSE_PROGRAM = "close_program"
NONE = "none"

# Programs that take a calculator's USB link. Matched against process image names, lower
# case, as substrings. The names of TI's executables are from TI's install folders as
# commonly reported; they were not checked on a PC with TI's software installed.
PROGRAMS = [
    ("ti connect ce", "TI Connect CE"),
    ("ticonnectce", "TI Connect CE"),
    ("ti connect", "TI Connect"),
    ("ticonnect", "TI Connect"),
    ("ti-nspire", "TI-Nspire software"),
    ("tinspire", "TI-Nspire software"),
    ("tilp", "TiLP"),
    ("nspire-cli", "CalcSuite's link helper (nspire-cli)"),
    ("ti84-cli", "CalcSuite's link helper (ti84-cli)"),
    ("ti89-cli", "CalcSuite's link helper (ti89-cli)"),
]
BROWSERS = {"chrome.exe": "Chrome", "msedge.exe": "Edge", "brave.exe": "Brave",
            "opera.exe": "Opera", "vivaldi.exe": "Vivaldi"}

# Windows Device Manager problem codes worth explaining
PROBLEMS = {
    1: "Windows set it up wrongly (code 1)",
    10: "the driver could not start it (code 10)",
    18: "Windows needs to reinstall its driver (code 18)",
    22: "it is disabled in Device Manager (code 22)",
    28: "it has no driver (code 28)",
    31: "the driver did not load (code 31)",
    39: "the driver is missing or damaged (code 39)",
    43: "the calculator reported a problem (code 43)",
    45: "it is not connected (code 45)",
    52: "Windows refused the driver's signature (code 52)",
}

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _run(cmd, timeout=20, cwd=None):
    """Runs a console program hidden; returns (exit code, stdout) or (None, error text)."""
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=timeout, cwd=cwd,
                           creationflags=_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, str(e)
    return p.returncode, p.stdout.decode("utf-8", "replace")


def _pid_hex(pid):
    return "%04x" % pid


# ---------- the sources ----------

def helper_list(probe=True):
    """calcsuite-driver.exe list: {"devices": [...], "packages": [...]} or None."""
    if not os.path.isfile(HELPER):
        return None
    code, out = _run([HELPER, "list"] + (["--probe"] if probe else []), cwd=BIN)
    if code is None or code != 0:
        return None
    devices, packages = [], []
    for line in out.splitlines():
        tag, _, rest = line.partition(" ")
        if tag not in ("DEVICE", "PACKAGE"):
            continue
        try:
            obj = json.loads(rest)
        except ValueError:
            continue
        if not isinstance(obj, dict):
            continue
        (devices if tag == "DEVICE" else packages).append(obj)
    return {"devices": devices, "packages": packages}


def libusb_pids():
    """Product ids libusb sees (ti84-cli devices: lists descriptors, opens nothing)."""
    if not os.path.isfile(TI84_CLI):
        return None
    code, out = _run([TI84_CLI, "devices"], timeout=15, cwd=BIN)
    if code is None:
        return None
    pids = set()
    for line in out.splitlines():
        for word in line.split():
            if word.startswith("pid="):
                try:
                    pids.add(int(word[4:], 16))
                except ValueError:
                    pass
    return pids


_PNP_SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
$f = "PNPDeviceID LIKE 'USB\\VID_0451%' OR PNPDeviceID LIKE 'USB\\VID_0000&PID_0002%'"
@(Get-CimInstance -ClassName Win32_PnPEntity -Filter $f |
  Select-Object PNPDeviceID, Name, Service, ConfigManagerErrorCode, Present) |
  ConvertTo-Json -Compress
"""


def pnp_devices():
    """Plugged-in TI devices (and failed 'Unknown USB Device's) from Windows' PnP data,
    through PowerShell as JSON (no text parsing, so any Windows language works)."""
    enc = base64.b64encode(_PNP_SCRIPT.encode("utf-16-le")).decode("ascii")
    code, out = _run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy",
                      "Bypass", "-EncodedCommand", enc], timeout=30)
    if code is None:
        return None
    out = out.strip()
    if not out:
        return []
    try:
        data = json.loads(out)
    except ValueError:
        return None
    if isinstance(data, dict):
        data = [data]
    return [d for d in data if isinstance(d, dict)] if isinstance(data, list) else None


def running_programs():
    """(link programs, browsers) running now, by image name (tasklist, CSV)."""
    code, out = _run(["tasklist.exe", "/fo", "csv", "/nh"], timeout=20)
    if code is None:
        return None, None
    found, browsers = {}, set()
    for row in csv.reader(io.StringIO(out)):
        if not row:
            continue
        image = row[0].strip().lower()
        for needle, label in PROGRAMS:
            if needle in image:
                found.setdefault(label, set()).add(row[0])
                break
        if image in BROWSERS:
            browsers.add(BROWSERS[image])
    return sorted(found), sorted(browsers)


# ---------- putting it together ----------

def _pid_of_instance(instance):
    s = (instance or "").upper()
    if not s.startswith("USB\\VID_0451&PID_") or "&MI_" in s:
        return None
    try:
        return int(s[17:21], 16)
    except ValueError:
        return None


def _status(service, provider, problem, access, programs, browsers, pid):
    """(status id, headline, explanation, fix) for one plugged-in calculator."""
    service_l = (service or "").lower()
    model = MODELS.get(pid, "This calculator")
    if problem == 22:
        return ("disabled", "Turned off in Device Manager",
                "Windows has this device disabled. Enable it in Device Manager (right-click it,"
                " Enable device), then unplug and replug.", NONE)
    if not service or problem == 28:
        why = ("Windows has no driver for it, so no program can talk to it.")
        return ("no_driver", "No driver", why + " Install the WinUSB driver to use it here.",
                INSTALL_WINUSB)
    if service_l != "winusb":
        if "texas" in (provider or "").lower() or service_l.startswith("ti"):
            if pid == 0xE004:
                owner = "TI's driver (from TI Connect) has it"
            elif pid in (0xE022, 0xE012):
                owner = "TI's driver (from the TI-Nspire software) has it"
            else:
                owner = "TI's driver has it: TI Connect CE installed"
            return ("needs_winusb_ti", "Needs the WinUSB driver (%s)" % owner,
                    "Installing WinUSB lets CalcSuite use it. TI's program then no longer sees"
                    " this calculator until you switch it back (Restore TI's driver).",
                    INSTALL_WINUSB)
        return ("needs_winusb_other", "Needs the WinUSB driver (it has the %s driver)" % service,
                "Another driver (%s, from %s) owns it. Installing WinUSB lets CalcSuite use it."
                % (service, provider or "an unknown maker"), INSTALL_WINUSB)
    if problem:
        text = PROBLEMS.get(problem, "Windows reports problem code %d" % problem)
        fix = INSTALL_WINUSB if problem in (18, 31, 39, 52) else NONE
        advice = ("Install the WinUSB driver again." if fix == INSTALL_WINUSB else
                  "Unplug it, wait 3 seconds, plug it into another port, and turn it on.")
        return ("driver_problem", "Driver problem: " + text, advice, fix)
    if access == "busy":
        if programs:
            who = ", ".join(programs)
            return ("busy", "Busy: another program has it open",
                    "Close %s, then unplug and replug the calculator." % who, CLOSE_PROGRAM)
        tabs = (" %s is running: close any tab using TI-Nspire CX II Connect or another"
                " calculator web page." % " / ".join(browsers)) if browsers else ""
        return ("busy", "Busy: another program has it open",
                "Close TI Connect CE, the TI-Nspire software, or a browser tab using it"
                " (TI-Nspire CX II Connect in Chrome can't be detected from here)." + tabs +
                " A second CalcSuite window can hold it too. Then unplug and replug.",
                CLOSE_PROGRAM)
    note = ""
    if programs:
        note = " (%s is running: if a transfer fails, close it.)" % ", ".join(programs)
    if access == "free":
        return ("ready", "Ready", "%s has the WinUSB driver and is free.%s" % (model, note), NONE)
    return ("ready", "Ready", "%s has the WinUSB driver.%s" % (model, note), NONE)


def diagnose(probe=True):
    """What's plugged in and what to do about it.

    Returns a dict:
      "devices": one entry per TI calculator plugged in now, then one per calculator
          seen on this PC before but not plugged in now. Each entry:
          {"pid": "e008", "model": "TI-84 Plus CE", "present": True,
           "status": "ready" | "needs_winusb_ti" | "needs_winusb_other" | "no_driver" |
                     "busy" | "driver_problem" | "disabled" | "unknown" | "asleep" |
                     "no_device",
           "headline": "Ready", "text": "...", "fix": "none" | "install_winusb" |
                     "close_program",
           "alt_fix": "none" | "restore_ti",   # a second button: e.g. TI Connect CE is
                                                # running but can't see a WinUSB calculator
           "can_restore_ti": bool,   # our/Zadig's WinUSB is on it: restore_ti() can undo it
           "ti_driver_installed": bool, "driver": "WinUSB", "provider": "libwdi",
           "instance": "USB\\VID_0451&PID_E008\\...", "last_seen": "2026-11-27T15:27:36Z"}
          When nothing is plugged in, devices ends with one entry with pid None and
          status "no_device" (cable charges only, or the calculator is off).
      "usb_failures": [names of USB devices that failed to start (bad cable or port)]
      "programs": link programs running now; "browsers": browsers running now
      "sources": which checks ran (helper / pnp / libusb / processes: True or False)
      "notes": [plain-English caveats]
    probe=True test-opens each WinUSB calculator for an instant (nothing is sent) to see
    whether another program holds it. Turn it off while CalcSuite itself is connected.
    """
    report = {"devices": [], "usb_failures": [], "programs": [], "browsers": [],
              "sources": {}, "notes": []}
    if os.name != "nt":
        report["notes"].append("The connection doctor checks Windows drivers only.")
        return report
    # Processes first: the checks below start ti84-cli.exe, which must not count as running
    programs, browsers = running_programs()
    with ThreadPoolExecutor(max_workers=3) as pool:
        f_helper = pool.submit(helper_list, probe)
        f_libusb = pool.submit(libusb_pids)
        f_pnp = pool.submit(pnp_devices)
        helper, usb_pids, pnp = f_helper.result(), f_libusb.result(), f_pnp.result()
    report["sources"] = {"helper": helper is not None, "libusb": usb_pids is not None,
                         "pnp": pnp is not None, "processes": programs is not None}
    report["programs"] = programs or []
    report["browsers"] = browsers or []
    programs = programs or []
    browsers = browsers or []

    nodes = []  # normalised: pid, present, service, provider, problem, access, instance, ...
    packages = []
    if helper is not None:
        packages = helper["packages"]
        for d in helper["devices"]:
            try:
                pid = int(d.get("pid") or "", 16)
            except ValueError:
                continue
            nodes.append({"pid": pid, "present": bool(d.get("present")),
                          "service": d.get("service") or "", "provider": d.get("provider") or "",
                          "problem": int(d.get("problem") or 0), "access": d.get("access"),
                          "instance": d.get("instance") or "", "name": d.get("desc") or "",
                          "last_seen": d.get("last_arrival")})
    elif pnp is not None:
        report["notes"].append("tools/bin/calcsuite-driver.exe is missing: driver details come"
                               " from Windows' device list, and 'busy' can't be tested.")
        for d in pnp:
            pid = _pid_of_instance(d.get("PNPDeviceID"))
            if pid is None:
                continue
            nodes.append({"pid": pid, "present": d.get("Present") is not False,
                          "service": d.get("Service") or "", "provider": "",
                          "problem": int(d.get("ConfigManagerErrorCode") or 0),
                          "access": "n/a", "instance": d.get("PNPDeviceID") or "",
                          "name": d.get("Name") or "", "last_seen": None})
    else:
        report["notes"].append("Could not read Windows' device list.")
    for d in pnp or []:
        if (d.get("PNPDeviceID") or "").upper().startswith("USB\\VID_0000&PID_0002"):
            report["usb_failures"].append(d.get("Name") or "Unknown USB Device")

    present_pids = set(n["pid"] for n in nodes if n["present"])
    if usb_pids:
        for pid in sorted(usb_pids - present_pids):
            if pid in MODELS:  # libusb sees it but Windows' list didn't: report it plainly
                nodes.append({"pid": pid, "present": True, "service": "", "provider": "",
                              "problem": 0, "access": "n/a", "instance": "", "name": "",
                              "last_seen": None, "unknown": True})
                present_pids.add(pid)

    def pkg_info(pid):
        hexpid = _pid_hex(pid)
        ours = any(p.get("ours") and hexpid in (p.get("pids") or []) for p in packages)
        ti = any(not p.get("ours") and hexpid in (p.get("pids") or []) and
                 "texas" in (p.get("provider") or "").lower() for p in packages)
        return ours, ti

    for n in nodes:
        if not n["present"]:
            continue
        ours, ti = pkg_info(n["pid"])
        if n.get("unknown"):
            status, head, fix = "unknown", "Seen on USB, driver unknown", NONE
            text = ("libusb sees it, but Windows' device list did not show it. Unplug it,"
                    " wait 3 seconds, replug, and check again.")
        else:
            status, head, text, fix = _status(n["service"], n["provider"], n["problem"],
                                              n["access"], programs, browsers, n["pid"])
        can_restore = (n["provider"].lower() == "libwdi") or ours
        # TI's program can't see a calculator that has WinUSB: offer the way back
        alt_fix = NONE
        ti_running = [p for p in programs if not p.startswith("CalcSuite")]
        if can_restore and status == "ready" and ti_running:
            alt_fix = RESTORE_TI
            text += (" %s can't see it while it has WinUSB: to use %s instead, choose"
                     " Restore TI's driver." % (ti_running[0], ti_running[0]))
        report["devices"].append({
            "pid": _pid_hex(n["pid"]), "model": MODELS.get(n["pid"], n["name"] or "TI device"),
            "present": True, "status": status, "headline": head, "text": text, "fix": fix,
            "alt_fix": alt_fix, "can_restore_ti": can_restore,
            "ti_driver_installed": ti, "driver": n["service"] or None,
            "provider": n["provider"] or None, "instance": n["instance"],
            "last_seen": n["last_seen"]})

    # Calculators this PC has seen before but that aren't on USB now
    seen = {}
    for n in nodes:
        if not n["present"] and n["pid"] not in present_pids and n["pid"] in MODELS:
            if n["last_seen"] and (n["pid"] not in seen or
                                   (seen[n["pid"]]["last_seen"] or "") < n["last_seen"]):
                seen[n["pid"]] = n
            seen.setdefault(n["pid"], n)
    for pid, n in sorted(seen.items()):
        ours, ti = pkg_info(pid)
        when = (" (last connected %s UTC)" % n["last_seen"].replace("T", " ").rstrip("Z")
                if n["last_seen"] else "")
        report["devices"].append({
            "pid": _pid_hex(pid), "model": MODELS[pid], "present": False, "status": "asleep",
            "headline": "Switched off / asleep",
            "text": "Not on USB now%s. Turn it on (press ON) and wait a few seconds. If it"
                    " still doesn't show, the cable may only charge: try a data cable or"
                    " another port." % when,
            "fix": NONE, "alt_fix": NONE,
            "can_restore_ti": (n["provider"].lower() == "libwdi") or ours,
            "ti_driver_installed": ti, "driver": n["service"] or None,
            "provider": n["provider"] or None, "instance": n["instance"],
            "last_seen": n["last_seen"]})

    if not present_pids:
        text = ("No TI calculator is on USB. Turn it on and plug it in. If it charges but"
                " never shows up here, the cable only charges: use a data cable (the one"
                " that came with the calculator) or another USB port.")
        if report["usb_failures"]:
            text = ("A USB device failed to start (%s): usually a bad cable or port. Try"
                    " another cable or port." % ", ".join(report["usb_failures"]))
        report["devices"].append({
            "pid": None, "model": None, "present": False, "status": "no_device",
            "headline": "Cable charges only (or the calculator is off)", "text": text,
            "fix": NONE, "alt_fix": NONE, "can_restore_ti": False, "ti_driver_installed": False,
            "driver": None, "provider": None, "instance": "", "last_seen": None})
    if any(d["status"] == "busy" for d in report["devices"]) or not probe:
        report["notes"].append("Browser tabs (TI-Nspire CX II Connect, WebUSB pages) can't be"
                               " seen from here; close them if a calculator shows as busy.")
    return report


# ---------- fixes (they change drivers: admin prompt) ----------

def _shell_execute_runas(exe, params, timeout_s):
    """Starts exe elevated (UAC prompt), waits, returns (exit code, error text)."""
    import ctypes
    from ctypes import wintypes

    class SHELLEXECUTEINFOW(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("fMask", ctypes.c_ulong),
                    ("hwnd", wintypes.HWND), ("lpVerb", wintypes.LPCWSTR),
                    ("lpFile", wintypes.LPCWSTR), ("lpParameters", wintypes.LPCWSTR),
                    ("lpDirectory", wintypes.LPCWSTR), ("nShow", ctypes.c_int),
                    ("hInstApp", wintypes.HINSTANCE), ("lpIDList", ctypes.c_void_p),
                    ("lpClass", wintypes.LPCWSTR), ("hkeyClass", wintypes.HKEY),
                    ("dwHotKey", wintypes.DWORD), ("hIconOrMonitor", wintypes.HANDLE),
                    ("hProcess", wintypes.HANDLE)]

    SEE_MASK_NOCLOSEPROCESS = 0x40
    SEE_MASK_NOASYNC = 0x100
    SW_HIDE = 0
    info = SHELLEXECUTEINFOW()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = SEE_MASK_NOCLOSEPROCESS | SEE_MASK_NOASYNC
    info.lpVerb = "runas"
    info.lpFile = exe
    info.lpParameters = params
    info.lpDirectory = os.path.dirname(exe)
    info.nShow = SW_HIDE
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(SHELLEXECUTEINFOW)]
    shell32.ShellExecuteExW.restype = wintypes.BOOL
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    if not shell32.ShellExecuteExW(ctypes.byref(info)):
        e = ctypes.get_last_error()
        if e == 1223:  # ERROR_CANCELLED: the user said No to the UAC prompt
            return None, "cancelled"
        return None, "could not start the driver helper (Windows error %d)" % e
    if not info.hProcess:
        return None, "the driver helper did not start"
    try:
        r = kernel32.WaitForSingleObject(info.hProcess, int(timeout_s * 1000))
        if r != 0:  # WAIT_OBJECT_0
            return None, "timeout"
        code = wintypes.DWORD()
        kernel32.GetExitCodeProcess(info.hProcess, ctypes.byref(code))
        return code.value, ""
    finally:
        kernel32.CloseHandle(info.hProcess)


def _parse_helper_output(text):
    steps, errors, result = [], [], None
    for line in text.splitlines():
        tag, _, rest = line.partition(" ")
        if tag == "STEP":
            steps.append(rest.strip())
        elif tag == "ERR":
            errors.append(rest.strip())
        elif tag == "RESULT":
            result = rest.strip()
    return steps, errors, result


def _run_fix(command, pid, dry_run, timeout_s):
    """Runs calcsuite-driver COMMAND PID; elevated unless dry_run. Returns a dict:
    {"ok": bool, "result": "ok"|"already"|"nothing"|"dry-run"|None, "cancelled": bool,
     "exit_code": int|None, "steps": [...], "errors": [...], "log": "full output"}"""
    out = {"ok": False, "result": None, "cancelled": False, "exit_code": None,
           "steps": [], "errors": [], "log": ""}
    if os.name != "nt":
        out["errors"].append("not-windows Driver changes are for Windows only")
        return out
    if not os.path.isfile(HELPER):
        out["errors"].append("missing tools/bin/calcsuite-driver.exe is missing"
                             " (python -I tools/build_tools.py)")
        return out
    pid_s = _pid_hex(pid) if isinstance(pid, int) else str(pid).lower().replace("0x", "")
    if dry_run:
        code, text = _run([HELPER, command, pid_s, "--dry-run"], timeout=timeout_s, cwd=BIN)
        if code is None:
            out["errors"].append("failed " + text)
            return out
    else:
        fd, log = tempfile.mkstemp(prefix="calcsuite-driver-", suffix=".log")
        os.close(fd)
        try:
            params = subprocess.list2cmdline([command, pid_s, "--log", log])
            code, why = _shell_execute_runas(HELPER, params, timeout_s)
            if why == "cancelled":
                out["cancelled"] = True
                out["errors"].append("cancelled The admin prompt was declined")
            elif why:
                out["errors"].append("failed " + why)
            text = ""
            for _ in range(20):  # the log can lag the exit by a moment on slow disks
                try:
                    with open(log, "r", encoding="utf-8", errors="replace") as f:
                        text = f.read()
                    break
                except OSError:
                    time.sleep(0.1)
        finally:
            try:
                os.remove(log)
            except OSError:
                pass
        if code is None:
            out["log"] = text
            return out
    out["exit_code"] = code
    out["log"] = text
    out["steps"], errs, out["result"] = _parse_helper_output(text)
    out["errors"] += errs
    out["ok"] = code == 0 and out["result"] in ("ok", "already", "nothing", "dry-run")
    return out


def install_winusb(pid, dry_run=False, timeout_s=300):
    """Puts the WinUSB driver on the calculator with this USB product id (0xE008, "e008").
    Shows the admin prompt and blocks until done (call it off the UI thread)."""
    return _run_fix("install-winusb", pid, dry_run, timeout_s)


def restore_ti(pid, dry_run=False, timeout_s=300):
    """Takes CalcSuite's (or Zadig's) WinUSB driver off that calculator so Windows hands it
    back to TI's driver, if TI's software installed one. Admin prompt; blocks."""
    return _run_fix("restore-ti", pid, dry_run, timeout_s)


# ---------- command line ----------

def format_report(report):
    lines = []
    for d in report["devices"]:
        name = d["model"] or "Calculator"
        pid = " (0451:%s)" % d["pid"] if d["pid"] else ""
        lines.append("%s%s: %s" % (name, pid, d["headline"]))
        lines.append("    " + d["text"])
        if d["driver"] or d["provider"]:
            lines.append("    driver: %s from %s" % (d["driver"] or "none",
                                                     d["provider"] or "unknown"))
        if d["fix"] != NONE:
            lines.append("    fix: " + d["fix"])
        if d.get("alt_fix", NONE) != NONE:
            lines.append("    other fix: " + d["alt_fix"])
        if d["can_restore_ti"] and d["present"]:
            lines.append("    (restore_ti would give it back to %s)"
                         % ("TI's driver" if d["ti_driver_installed"] else
                            "Windows; no TI driver is installed, so it would have none"))
    if report["programs"]:
        lines.append("Running link programs: " + ", ".join(report["programs"]))
    for n in report["notes"]:
        lines.append("Note: " + n)
    missing = [k for k, v in report["sources"].items() if not v]
    if missing:
        lines.append("Checks that could not run: " + ", ".join(missing))
    return "\n".join(lines)


def _print_fix(res):
    for s in res["steps"]:
        print("  " + s)
    for e in res["errors"]:
        print("  ERROR " + e)
    print("Result: %s (exit %s)" % (res["result"] or "failed", res["exit_code"]))


def main(argv):
    args = list(argv)
    as_json = "--json" in args
    dry = "--dry-run" in args
    for cmd, fn in (("--install-winusb", install_winusb), ("--restore-ti", restore_ti)):
        if cmd in args:
            i = args.index(cmd)
            if i + 1 >= len(args):
                print("usage: %s PID [--dry-run]" % cmd)
                return 1
            res = fn(args[i + 1], dry_run=dry)
            if as_json:
                print(json.dumps(res, indent=2))
            else:
                _print_fix(res)
            return 0 if res["ok"] else 1
    report = diagnose(probe="--no-probe" not in args)
    print(json.dumps(report, indent=2) if as_json else format_report(report))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
