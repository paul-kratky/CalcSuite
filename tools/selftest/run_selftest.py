"""Self-test for the kit: examples must pass the checker, the bad sample must fail,
and the examples must run on the PC with the shim.

    python -I tools/selftest/run_selftest.py
"""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(os.path.dirname(HERE))
CHECK = os.path.join(KIT, "tools", "check_nspire.py")
RUN = os.path.join(KIT, "tools", "run_on_pc.py")
PY2TNS = os.path.join(KIT, "tools", "py2tns.py")
FLASH = os.path.join(KIT, "tools", "flash.py")
LUNA = os.path.join(KIT, "tools", "bin", "luna.exe")
PROGRAMS = os.path.join(KIT, "programs")

# Things bad_sample.py must be flagged for (substrings of the checker's messages).
MUST_FLAG = [
    "__future__", "module 'numpy'", "module 'os'", "type hints", "async def",
    "await is not supported", "type annotation on a variable", "f-string", "walrus",
    "match/case", "non-ASCII", "open() is not available", "math.hypot", ".ljust()",
    "list/string of 1000000", "calls itself",
]


def run(args, stdin_text=""):
    p = subprocess.run([sys.executable, "-I"] + args, input=stdin_text, capture_output=True,
                       text=True, cwd=KIT)
    return p.returncode, p.stdout + p.stderr


def main():
    failures = 0

    for name in sorted(os.listdir(PROGRAMS)):
        if name.endswith(".py"):
            code, out = run([CHECK, os.path.join(PROGRAMS, name)])
            ok = code == 0
            print("%-4s checker passes %s" % ("PASS" if ok else "FAIL", name))
            if not ok:
                print(out)
                failures += 1

    code, out = run([CHECK, os.path.join(HERE, "bad_sample.py")])
    print("%-4s checker rejects bad_sample.py" % ("PASS" if code == 1 else "FAIL"))
    failures += code != 1
    for needle in MUST_FLAG:
        found = needle in out
        if not found:
            print("FAIL   bad_sample.py not flagged for: %s" % needle)
            failures += 1
    if all(n in out for n in MUST_FLAG):
        print("PASS checker flags all %d planted problems" % len(MUST_FLAG))

    cases = [
        ("quadratic.py", "1\n-3\n2\n", "x1 = 2.0"),
        ("quadratic.py", "1\n2\n5\n", "-1.0 + 2.0i"),
        ("quadratic.py", "1\n2\n1\n", "One double root: x = -1.0"),
        ("quadratic.py", "0\n2\n-4\n", "Linear: x = 2.0"),
        ("draw_demo.py", "", "fill_circle(288, 30, 16)"),
        ("probe.py", "", "screen: (318, 212)"),
    ]
    for prog, stdin_text, expect in cases:
        code, out = run([RUN, os.path.join(PROGRAMS, prog)], stdin_text)
        ok = code == 0 and expect in out
        print("%-4s runs on PC: %s -> %r" % ("PASS" if ok else "FAIL", prog, expect))
        if not ok:
            print(out)
            failures += 1

    # .py -> .tns conversion and the one-step flash.py (dry run: no calculator needed).
    if os.path.isfile(LUNA):
        out_dir = os.path.join(KIT, "build", "selftest")
        for name in sorted(os.listdir(PROGRAMS)):
            if name.endswith(".py"):
                tns = os.path.join(out_dir, name[:-3] + ".tns")
                code, out = run([PY2TNS, os.path.join(PROGRAMS, name), "-o", tns])
                ok = code == 0 and "tns OK" in out
                print("%-4s converts to .tns: %s" % ("PASS" if ok else "FAIL", name))
                if not ok:
                    print(out)
                    failures += 1
        code, out = run([FLASH, os.path.join(PROGRAMS, "quadratic.py"), "--dry-run",
                         "--out", os.path.join(out_dir, "flash_quadratic.tns")])
        ok = code == 0 and "DRY RUN OK" in out
        print("%-4s flash.py --dry-run quadratic.py" % ("PASS" if ok else "FAIL"))
        if not ok:
            print(out)
            failures += 1
        code, out = run([FLASH, os.path.join(HERE, "bad_sample.py"), "--dry-run"])
        ok = code != 0 and "STOPPED: the checker" in out
        print("%-4s flash.py stops on checker errors" % ("PASS" if ok else "FAIL"))
        if not ok:
            print(out)
            failures += 1
    else:
        print("SKIP .tns tests: tools/bin/luna.exe missing (python -I tools/build_tools.py)")

    print("\n%s" % ("ALL PASSED" if not failures else "%d FAILURE(S)" % failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
