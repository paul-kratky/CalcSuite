"""One step from program to handheld: check, convert to .tns, send over USB.

    python -I tools/flash.py programs/quadratic.py
    python -I tools/flash.py programs/quadratic.py --dry-run      stop before sending
    python -I tools/flash.py programs/quadratic.py --folder Python
    python -I tools/flash.py programs/mylib_user.py --allow mylib --strict

Steps:
  1. tools/check_nspire.py  (any ERROR stops here; --strict makes warnings stop it too)
  2. tools/py2tns.py        -> build/<name>.tns, re-opened and verified
  3. tools/send_to_calc.py  -> My Documents/<name>.tns (or --folder), read back and compared

Options: --dry-run, --folder NAME, --strict, --allow MODULE (repeatable), --out FILE.tns.
Exit code 0 = done (or dry run passed), otherwise the failing step's code.
"""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import py2tns  # noqa: E402
import send_to_calc  # noqa: E402

CHECK = os.path.join(HERE, "check_nspire.py")


def parse(argv):
    opts = {"dry": False, "folder": None, "strict": False, "allow": [], "out": None, "prog": None}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--dry-run":
            opts["dry"] = True
        elif a == "--strict":
            opts["strict"] = True
        elif a in ("--folder", "--allow", "--out"):
            if i + 1 >= len(argv):
                raise SystemExit("ERROR: %s needs a value" % a)
            i += 1
            if a == "--allow":
                opts["allow"].append(argv[i])
            else:
                opts[a[2:]] = argv[i]
        elif a.startswith("-"):
            raise SystemExit("ERROR: unknown option %s (see --help)" % a)
        elif opts["prog"] is None:
            opts["prog"] = a
        else:
            raise SystemExit("ERROR: give one program at a time")
        i += 1
    if not opts["prog"]:
        raise SystemExit("usage: flash.py PROGRAM.py [--dry-run] [--folder NAME]")
    return opts


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0 if argv else 1
    o = parse(argv)
    prog = o["prog"]
    name = os.path.splitext(os.path.basename(prog))[0]

    print("[1/3] Checking %s for the calculator's Python" % prog)
    args = [sys.executable, "-I", CHECK]
    if o["strict"]:
        args.append("--strict")
    for m in o["allow"]:
        args += ["--allow", m]
    p = subprocess.run(args + [prog], capture_output=True, text=True)
    out = (p.stdout + p.stderr).strip()
    if out:
        print("\n".join("      " + l for l in out.splitlines() if l.strip()))
    if p.returncode != 0:
        print("STOPPED: the checker found problems. Fix them and run flash.py again.")
        return p.returncode or 1

    print("[2/3] Converting to .tns")
    try:
        tns = py2tns.convert(prog, o["out"], quiet=True)
        print("      " + py2tns.verify(tns, expect_name=name + ".py", quiet=True))
    except py2tns.TnsError as e:
        print("STOPPED: conversion failed: %s" % e)
        return 1
    print("      wrote %s" % tns)

    if o["dry"]:
        print("[3/3] Dry run: not sending.")
        code, _ = send_to_calc.run_cli(["devices"])
        if code == 0:
            print("      A handheld is connected; run without --dry-run to send.")
        elif code == 2:
            print("      (No handheld connected right now.)")
        else:
            print("      A TI device is on USB but cannot be opened (driver?): see README.")
        print("DRY RUN OK: %s" % tns)
        return 0

    print("[3/3] Sending over USB")
    code = send_to_calc.send(tns, o["folder"])
    if code:
        print("STOPPED: not sent. The .tns is ready at %s (you can also drag it into"
              " TI-Nspire CX II Connect)." % tns)
        return code
    where = ("My Documents > %s > %s.tns" % (o["folder"].strip("/"), name)) if o["folder"] \
        else "My Documents > %s.tns" % name
    print("DONE. On the handheld: [home/on] > My Documents, open %s," % where)
    print("      then menu > Run > Run (ctrl+R). If it was already open, close it first"
          " (doc > File > Close) so the new version loads.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
