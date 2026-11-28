# SPDX-License-Identifier: MIT
"""Test a TI-84 Plus CE program in the PC copy before sending it to the real calculator.

CEmu (GPL-3.0, its own program) has an autotester: a JSON file names the program to send and
run, the keys to press and the memory to check (a CRC of the screen, for example). CalcSuite
writes that file and runs a second CEmu, separate from the one in the PC copy's tab, with the
user's own ROM and its own throwaway settings:

    CEmu --id CalcSuiteTest -g <its settings> --rom <ROM> --reload-rom -t <test.json> --no-test-dialog

CEmu resets the calculator, sends the program, starts it ("action|launch"), presses the keys,
and prints a line per check on its standard output ("[Test passed!] Hash #screen had a
matching CRC." / "[Test failed!] Hash #screen (...) did not match ..."); CalcSuite reads those,
asks the running CEmu for a screenshot (--id CalcSuiteTest --screenshot <png>) and closes it.
The calculator itself is never touched.

The JSON format: CEmu's tests/autotester/json_file_documentation.txt (CEmu v2.0); the key names:
valid_keys in tests/autotester/autotester.cpp. Nothing of CEmu's code is used here: only its
file format and its command line.

    python -I tools/pc_test.py PROGRAM.8xp [--keys "enter, wait 500, 2, enter"] [--expect CRC]
"""

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

TEST_ID = "CalcSuiteTest"
TEST_TITLE = r"^CEmu \| CalcSuiteTest$"
# The key names CEmu's autotester takes (autotester.cpp, valid_keys, CEmu v2.0)
VALID_KEYS = ("graph", "trace", "zoom", "window", "y=", "2nd", "mode", "del", "on", "sto", "ln", "log",
              "^2", "-1", "math", "alpha", "0", "1", "4", "7", ",", "sin", "apps", "xton", ".", "2", "5",
              "8", "(", "cos", "prgm", "stat", "(-)", "3", "6", "9", ")", "tan", "vars", "enter", "+",
              "-", "*", "/", "^", "clear", "down", "left", "right", "up")
# Friendlier spellings accepted in a key script -> the autotester's names
KEY_ALIASES = {"y =": "y=", "yequ": "y=", "x^2": "^2", "x2": "^2", "sq": "^2", "x^-1": "-1", "inv": "-1",
               "comma": ",", "dot": ".", "period": ".", "lpar": "(", "rpar": ")", "neg": "(-)",
               "negative": "(-)", "plus": "+", "minus": "-", "times": "*", "mul": "*", "div": "/",
               "divide": "/", "power": "^", "pow": "^", "clr": "clear", "sto>": "sto", "sto→": "sto",
               "x,t,θ,n": "xton", "xtn": "xton", "wind": "window", "second": "2nd"}
SCREEN = "screen"  # The check CalcSuite adds: the screen's CRC (vram_start, vram_16_size)
END = "end"        # The last check, made to fail: its line marks the end of the run
STEP_TIMEOUT_S = 60.0  # A test whose checks haven't all come in this long after the program started
SCREEN_RANGE = ("vram_start", "vram_16_size")


class TestError(Exception):
    pass


def parse_script(text):
    """A key script -> the autotester's sequence steps. Items are separated by commas or new
    lines: a key name ("enter", "2nd", "alpha", "1", "+", "clear" ...), "wait 500" (ms), "hold
    KEY" / "release KEY". Raises TestError naming an item it doesn't know."""
    steps = []
    for raw in re.split(r"[,\n]", text or ""):
        item = raw.strip()
        if not item:
            continue
        low = item.lower()
        m = re.match(r"^(?:wait|delay|pause)\s+(\d+)\s*(ms)?$", low)
        if m:
            ms = int(m.group(1))
            if not 0 < ms < 60000:
                raise TestError("\"%s\": a wait is 1 to 59999 ms" % item)
            steps.append("delay|%d" % ms)
            continue
        m = re.match(r"^(hold|release)\s+(.+)$", low)
        verb = m.group(1) if m else "key"
        name = (m.group(2) if m else low).strip()
        name = KEY_ALIASES.get(name, name)
        if name not in VALID_KEYS:
            raise TestError("\"%s\" isn't a key CEmu's tester knows (keys: %s; waits: wait 500)" % (
                item, ", ".join(VALID_KEYS)))
        steps.append("%s|%s" % (verb, name))
    return steps


def check_name(name):
    """A program name as the autotester takes it: [A-Z][A-Z0-9θ]{0,7} (θ written as @)"""
    n = (name or "").upper().replace("Θ", "@").replace("θ", "@")
    if not re.match(r"^[A-Z@][A-Z0-9@]{0,7}$", n):
        raise TestError("\"%s\" isn't a TI-84 Plus CE program name (A-Z, 0-9, θ; 8 at most)" % name)
    return n


def test_config(program_file, name, script="", expected=(), is_asm=False, wait_ms=1500,
                delay_after_key=100, delay_after_step=100):
    """The autotester's JSON (a dict): send program_file, launch NAME, wait wait_ms, press the
    script's keys, then check the screen's CRC against expected (hex strings; none given: a
    placeholder, so the run shows the screen's real CRC to keep as the expected one)."""
    steps = ["action|launch"]
    if wait_ms:
        steps.append("delay|%d" % int(wait_ms))
    steps += parse_script(script)
    steps += ["hash|%s" % SCREEN, "hash|%s" % END]
    crcs = []
    for c in expected or ():
        c = c.strip().upper()
        if c.startswith("0X"):
            c = c[2:]
        if not re.match(r"^[0-9A-F]{1,8}$", c):
            raise TestError("\"%s\" isn't a CRC (up to 8 hex digits)" % c)
        crcs.append(c)
    return {
        "rom": "",  # The GUI ignores it (the ROM comes from --rom)
        "transfer_files": [os.path.basename(program_file)],
        "target": {"name": check_name(name), "isASM": bool(is_asm)},
        "delay_after_key": int(delay_after_key),
        "delay_after_step": int(delay_after_step),
        "sequence": steps,
        "hashes": {SCREEN: {"description": "The screen at the end", "start": SCREEN_RANGE[0],
                            "size": SCREEN_RANGE[1], "expected_CRCs": crcs or ["0"]},
                   # CEmu's window prints a check only when it fails: this one always fails (no
                   # one-byte CRC-32 is 0), so its line says the test has ended
                   END: {"description": "CalcSuite: the end of the test", "start": SCREEN_RANGE[0],
                         "size": "1", "expected_CRCs": ["0"]}},
    }


_PASS = re.compile(r"\[Test passed!\] Hash #(\S+) had a matching CRC")


def parse_output(lines):
    """CEmu's autotester lines -> {"checks": [{"hash", "ok", "got", "expected"}], "errors": [...],
    "parsed": bool}. CEmu 2.0 prints, for example:
        <path>/test.json loaded and verified. 1 unique tests found.
        	[Test failed!] Hash #screen ("The screen at the end") did not match the expected CRC 0 (got EDA8DAEB).
        	[Test passed!] Hash #screen had a matching CRC."""
    out = {"checks": [], "errors": [], "parsed": False}
    for raw in lines:
        line = raw.strip()
        if "[OK] JSON parsed" in line or "loaded and verified" in line:
            out["parsed"] = True
        m = _PASS.search(line)
        if m:
            out["checks"].append({"hash": m.group(1), "ok": True, "got": None, "expected": None})
            continue
        if "[Test failed!]" in line:
            m = re.search(r"Hash #(\S+)", line)
            # "... did not match either one of the expected CRCs (...): got XXXX" or
            # "... did not match the expected CRC (AAAA), got BBBB"; take the last hex word as what came
            words = re.findall(r"\b[0-9A-Fa-f]{1,8}\b", line.split("did not match", 1)[-1])
            out["checks"].append({"hash": m.group(1) if m else "?", "ok": False,
                                  "got": words[-1].upper() if words else None,
                                  "expected": words[0].upper() if len(words) > 1 else None})
            continue
        if "[Error]" in line:
            out["errors"].append(line.replace("\t", " ").strip())
    return out


def ended(parsed):
    """The run has ended: the END check's (failed) line came"""
    return any(c["hash"] == END for c in parsed["checks"])


def summarize(parsed, expected=()):
    """{"ok", "crc", "checks"} from parse_output's result. The window prints only failed checks:
    after END, a check without a failed line passed. ok: True/False against the expected
    screen CRCs; None when none were given (crc is then the screen's real CRC)."""
    fails = {c["hash"]: c for c in parsed["checks"] if not c["ok"] and c["hash"] != END}
    given = [c.strip().upper().replace("0X", "", 1) for c in expected or () if c.strip()]
    screen_fail = fails.get(SCREEN)
    if screen_fail is not None:
        crc = screen_fail["got"]
    else:
        crc = given[0] if given and ended(parsed) else None
    if not given:
        ok = None
    elif not ended(parsed):
        ok = False
    else:
        ok = screen_fail is None
    checks = [{"hash": SCREEN, "ok": (screen_fail is None) if ended(parsed) else False, "got": crc,
               "expected": ", ".join(given) or None}]
    return {"ok": ok, "crc": crc, "checks": checks}


def settings_folder():
    import pc_copy
    return os.path.join(pc_copy.emulators_folder(), "CEmu", "calcsuite-test")


def prepare(program_file, name, rom, script="", expected=(), wait_ms=1500, folder=None):
    """Writes the test's files into a fresh folder (the program, test.json, CEmu's settings for
    the test: nothing saved when it closes). Returns (folder, json path, settings path, config)."""
    import emu_tabs
    base = folder or settings_folder()
    work = os.path.join(base, "run")
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work, exist_ok=True)
    shutil.copyfile(program_file, os.path.join(work, os.path.basename(program_file)))
    cfg = test_config(program_file, name, script, expected, wait_ms=wait_ms)
    js = os.path.join(work, "test.json")
    with open(js, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=1)
    text = emu_tabs.cemu_settings_text(work, rom, emu_tabs.cemu_version(), panels=False)
    text = emu_tabs.ini_set(text, {"General/save_on_close": "false", "General/restore_on_open": "false"})
    ini = os.path.join(work, "cemu_config.ini")
    with open(ini, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return work, js, ini, cfg


def command(exe, ini, rom, js):
    return [exe, "--id", TEST_ID, "-g", ini, "--rom", rom, "--reload-rom", "-t", js, "--no-test-dialog"]


def run_test(program_file, name, script="", expected=(), rom=None, exe=None, report=None, cancel=None,
             wait_ms=1500, popen=None, win=None, folder=None, timeout=None):
    """Runs the test in a CEmu of its own (moved off the screen while it runs) and closes it.
    Returns {"ok": True/False, "checks", "errors", "screenshot" (a PNG or None), "crc" (the
    screen's CRC), "log" [lines], "seconds"}. ok is False when a check failed; with no expected
    CRC given, ok is None (nothing to compare: the screenshot and crc say what came).
    Raises TestError when it can't run (no ROM, no CEmu, CEmu ended without an answer)."""
    import pc_copy
    import emu_host as eh
    say = report or (lambda text: None)
    t0 = time.time()
    if rom is None:
        roms = pc_copy.list_roms("84")
        if not roms:
            raise TestError("there's no PC copy of the TI-84 Plus CE yet: make one first (Calculator info)")
        rom = roms[0]["path"]
    exe = exe or pc_copy.cemu_path()
    if not exe:
        raise TestError("CEmu isn't downloaded yet: open the PC copy once (it gets CEmu)")
    work, js, ini, cfg = prepare(program_file, name, rom, script, expected, wait_ms, folder)
    lines = []
    say("Starting CEmu with your ROM (it resets, sends %s and runs it)..." % cfg["target"]["name"])
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    start = popen or (lambda cmd: subprocess.Popen(cmd, cwd=work, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                                   stdin=subprocess.DEVNULL, creationflags=flags))
    p = start(command(exe, ini, rom, js))

    def read():
        for raw in iter(p.stdout.readline, b""):
            lines.append(raw.decode("utf-8", "replace").rstrip())
    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    win = win if win is not None else _win()
    hidden = False
    shown_s = [-1]
    limit = timeout or (STEP_TIMEOUT_S + cfg["sequence"].__len__() * 2 + 15)
    shot = os.path.join(work, "screen.png")
    try:
        while True:
            if cancel is not None and cancel.is_set():
                raise TestError("cancelled")
            res = parse_output(lines)
            if ended(res):
                break
            if p.poll() is not None:
                reader.join(1)
                res = parse_output(lines)
                if ended(res):
                    break
                raise TestError("CEmu ended without a result%s" % (
                    ": " + "; ".join(res["errors"][:3]) if res["errors"] else ""))
            if time.time() - t0 > limit:
                raise TestError("no result within %d s (does the program wait for a key? add it to the "
                                "keys, or a longer wait)" % limit)
            if not hidden and win is not None:
                hwnd = eh.pick_window(win.windows_of(p.pid), TEST_TITLE)
                if hwnd:
                    win.move(hwnd, -32000, -32000, 520, 780)  # Off the screen: it runs, unseen
                    hidden = True
            if int(time.time() - t0) != shown_s[0]:
                shown_s[0] = int(time.time() - t0)
                say("Running the test... (%d s)" % shown_s[0])
            time.sleep(0.2)
        say("Taking the screenshot...")
        try:
            subprocess.run([exe, "--id", TEST_ID, "--screenshot", shot], timeout=20, cwd=work,
                           creationflags=flags, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError):
            pass
        for _ in range(40):
            if os.path.isfile(shot) and os.path.getsize(shot) > 0:
                break
            time.sleep(0.05)
    finally:
        _close(p, win)
    res = parse_output(lines)
    s = summarize(res, cfg["hashes"][SCREEN]["expected_CRCs"] if expected else ())
    return {"ok": s["ok"], "checks": s["checks"], "errors": res["errors"], "crc": s["crc"],
            "screenshot": shot if os.path.isfile(shot) else None, "log": lines,
            "seconds": round(time.time() - t0, 1), "folder": work, "config": cfg}


def _win():
    try:
        import emu_host as eh
        return eh.Win32()
    except (AttributeError, OSError):
        return None


def _close(p, win):
    """Closes the test's CEmu (only that process): WM_CLOSE, then ended after 5 s"""
    if p.poll() is not None:
        return
    import emu_host as eh
    try:
        hwnd = eh.pick_window(win.windows_of(p.pid), TEST_TITLE) if win is not None else None
        if hwnd:
            win.close(hwnd)
            p.wait(5)
    except Exception:
        pass
    if p.poll() is None:
        try:
            p.terminate()
            p.wait(3)
        except Exception:
            pass


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(description="Test a TI-84 Plus CE program in the PC copy (CEmu)")
    ap.add_argument("program", help="the .8xp")
    ap.add_argument("--name", help="its name on the calculator (default: from the file name)")
    ap.add_argument("--keys", default="", help='keys after it starts: "enter, wait 500, 2, enter"')
    ap.add_argument("--expect", action="append", default=[], help="the screen's expected CRC (hex)")
    ap.add_argument("--wait", type=int, default=1500, help="ms after launching, before the keys")
    a = ap.parse_args(argv)
    name = a.name or os.path.splitext(os.path.basename(a.program))[0]
    try:
        r = run_test(a.program, name, a.keys, a.expect, wait_ms=a.wait,
                     report=lambda t: print("  " + t, flush=True))
    except TestError as e:
        print("ERROR: %s" % e)
        return 4
    print(json.dumps({k: v for k, v in r.items() if k not in ("log", "config")}, indent=1))
    for l in r["log"]:
        print("  | " + l)
    return 0 if r["ok"] in (True, None) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
