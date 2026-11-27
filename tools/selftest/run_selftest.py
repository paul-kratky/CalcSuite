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

    failures += ti_basic_checks()
    print("\n%s" %("ALL PASSED" if not failures else "%d FAILURE(S)" % failures))
    return 1 if failures else 0


TI84_SOURCE = """:ClrHome
:Disp "HELLO, world"
:Input "N? ",N
:For(I,1,N)
:If I>=2 and I!=5 or not(I<=1)
:Then
:Disp sqrt(I),I^2,pi*theta,I^-1
:Else
:Output(1,1,-I)
:End
:End
:1.5E-3->A
:-A+2->B
:Repeat getKey
:End
:L1(1)->C
:Prompt X,Y
:While X<=10:X+1->X:End
:Disp "e is e"
:Lbl A
:Goto A"""


def ti_basic_checks():
    """TI-Basic text -> .8xp and .89p (tools/calc_files.py), checked against known bytes and
    the 84 detokenizer. No calculator needed."""
    sys.path.insert(0, os.path.join(KIT, "tools"))
    import calc_files as cf
    failures = 0

    def check(ok, what):
        print("%-4s %s" % ("PASS" if ok else "FAIL", what))
        return 0 if ok else 1

    tok = cf.tokenize_84(TI84_SOURCE)
    failures += check(tok.startswith(bytes.fromhex("e13fde2a48454c4c4f2b29bbc7bbbfbbc2bbbcbbb32a")),
                      "84 tokens: ClrHome, Disp, a string with lower case")
    failures += check(bytes.fromhex("313a353bb03304413f") in tok, "84 tokens: 1.5E-3->A (EE, (-), store)")
    failures += check(bytes.fromhex("b041703204423f") in tok, "84 tokens: -A+2->B starts with (-)")
    failures += check(bytes.fromhex("bc49112b490d2bac825b2b490c") in tok,
                      "84 tokens: sqrt( ^2 pi theta ^-1")
    text = cf.detokenize_84(tok)
    failures += check("If I≥2 and I≠5 or not(I≤1)" in text and "1.5ᴇ⁻3→A" in text,
                      "84 detokenizer reads the tokens back")
    failures += check(cf.tokenize_84(text) == tok, "84 round trip: tokenize(detokenize(x)) == x")
    blob = cf.program_8xp(":ClrHome\n:Disp 1+2", "ZZTEST")
    (t, name, _v, _a, data), = cf.read_ti8x(blob)
    failures += check(t == 5 and name == b"ZZTEST" and data == bytes.fromhex("0600e13fde317032"),
                      ".8xp: header, name, length and checksum read back")
    try:
        cf.program_8xp("Disp 1", "1BAD")
        failures += check(False, ".8xp refuses a bad name")
    except ValueError:
        failures += check(True, ".8xp refuses a bad name")
    # The 89: the bytes its own Program Editor stores for this program (read from a TI-89
    # Titanium, OS 3.10), but for the cursor position (0 here)
    n, vtype, data = cf.program_89_data("zztest()\nPrgm\nDisp 1+2\nEndPrgm")
    failures += check((n, vtype, data) == ("zztest", 0x12, bytes.fromhex(
        "002228290d5072676d0d4469737020312b320d456e645072676d00000019e4e5000008dc")),
        ".89 program as text, as the 89 keeps it")
    _n, _t, data = cf.program_89_data("Disp -3,2E-5\nx^2->y\nIf x>=1 and y!=2\nDisp sqrt(pi)", "abc")
    failures += check(b"Disp \xad3,2\x95\xad5\rx^2\x16y\rIf x\x9e1 and y\x9d2\rDisp \xa8(\x8c)" in data,
                      ".89 characters: (-), EE, ->, >=, !=, sqrt(, pi")
    _n, vtype, data = cf.program_89_data("f(x)\nFunc\nReturn x^2\nEndFunc")
    failures += check(vtype == 0x13 and data.endswith(b"\x17\xe4\xe5\x00\x00\x08\xdc"), ".89 function")
    name, _t, blob = cf.program_89p("Disp 1", "zztest")
    (folder, vname, t, _a, d2), = cf.read_ti89(blob)
    failures += check((folder, vname, t) == (b"main", b"zztest", 0x12) and
                      cf.program_89_text(d2) == "()\nPrgm\nDisp 1\nEndPrgm", ".89p read back")
    return failures


if __name__ == "__main__":
    sys.exit(main())
