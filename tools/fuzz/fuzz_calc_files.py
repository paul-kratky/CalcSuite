"""Fuzz test for everything CalcSuite reads from outside: TI-84 and TI-89 files a user opens
(read_ti8x, read_ti89, the program/text readers), TI-Basic text (tokenize_84, program_89p), the
link helpers' listings (parse_nspire_ls, parse_dusb_ls) and TI's OS web page (parse_os_page).

A parser may refuse an input with ValueError (that's how they report a bad file); any other
exception or a hang is a bug.

  python tools/fuzz/fuzz_calc_files.py [atheris/libFuzzer args] [corpus dirs]
      With atheris installed (Linux, Python 3.12+; CI's fuzz.yml): coverage-guided fuzzing.
  python -I tools/fuzz/fuzz_calc_files.py --quick [N]
      Without atheris (any OS): N random mutations of the seed files (default 20000).
  python -I tools/fuzz/fuzz_calc_files.py --seeds DIR
      Writes the seed files (valid TI files, listings, an OS page) into DIR.
"""

import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

try:
    import atheris  # Only on the fuzz job: Linux wheels, not a CalcSuite dependency
except ImportError:
    atheris = None

if atheris:
    with atheris.instrument_imports():
        import calc_files as cf
else:
    import calc_files as cf

TARGETS = ("ti8x", "ti89", "tok84", "tok89", "nspire_ls", "dusb_ls", "os_page")


def fuzz_one(data):
    """One input: its first byte picks the parser, the rest is what that parser reads"""
    if not data:
        return
    target, body = TARGETS[data[0] % len(TARGETS)], data[1:]
    text = body.decode("utf-8", "replace")
    try:
        if target == "ti8x":
            for vtype, _name, _ver, _arch, var in cf.read_ti8x(body):
                cf.detokenize_84(var)
                cf.is_compiled_84(var)
        elif target == "ti89":
            for _folder, _name, vtype, _arch, var in cf.read_ti89(body):
                cf.ti89_text(vtype, var)
                cf.program_89_text(var)
        elif target == "tok84":
            cf.detokenize_84(cf.tokenize_84(text, []))
            cf.detokenize_84(body)
        elif target == "tok89":
            cf.program_89p(text, default="zzfuzz")
        elif target == "nspire_ls":
            cf.parse_nspire_ls(text.splitlines())
        elif target == "dusb_ls":
            for item in cf.parse_dusb_ls(text.splitlines()):
                cf.name_text(item["name"], "84")
                cf.name_text(item["name"], "89")
        elif target == "os_page":
            cf.parse_os_page(text)
    except ValueError:
        pass  # A refused input: fine


def seeds():
    """Valid inputs for each target, each led by its target byte"""
    out = []
    add = lambda t, b: out.append(bytes((TARGETS.index(t),)) + b)
    prog = "Disp \"HI\"\nFor(I,1,10)\nI^2->A\nEnd"
    add("ti8x", cf.program_8xp(prog, "ZZFUZZ"))
    add("ti8x", cf.ti8x_bytes([(0x04, b"\xaa\x00", 0, False, b"\x02\x00\x2a\x2a"),
                               (0x00, b"A", 0, True, b"\x00" * 9)]))
    add("ti89", cf.program_89p("zzfuzz()\nPrgm\nDisp \"hi\"\nEndPrgm")[2])
    add("ti89", cf.ti89_bytes(0x0C, b"main", b"zzs", False, b"\x00\x05\x00hi\x00\x2d"))
    add("tok84", prog.encode())
    add("tok89", "zzf(x)\nFunc\nReturn x^2+∫(x,x)\nEndFunc".encode())
    add("nspire_ls", b"ITEM dir 0 My Documents\nITEM file 1234 zz.tns\nERR 2\n")
    add("dusb_ls", b"ITEM type=05 size=12 arch=0 locked=0 folder=- name=5a5a\n")
    add("os_page", b'<tr><td><a href="/x/TI-NspireCXIICAS-6.4.0.74.tcc2" class="download-file">'
                   b'Operating System</a></td><td class="column-version"> 6.4 </td></tr>')
    return out


def mutate(rng, b):
    b = bytearray(b)
    for _ in range(rng.randint(1, 8)):
        op = rng.randrange(5)
        i = rng.randrange(len(b) + 1)
        if op == 0 and b:  # Flip a byte
            b[min(i, len(b) - 1)] = rng.randrange(256)
        elif op == 1:  # Insert bytes
            b[i:i] = bytes(rng.randrange(256) for _ in range(rng.randint(1, 8)))
        elif op == 2 and len(b) > 1:  # Cut
            del b[i:i + rng.randint(1, 16)]
        elif op == 3 and len(b) > 1:  # Truncate
            del b[rng.randint(1, len(b)):]
        elif op == 4 and b:  # An interesting value
            b[min(i, len(b) - 1)] = rng.choice((0, 1, 0x7F, 0x80, 0xFF, 0x0D, 0x3F))
    return bytes(b)


def quick(n):
    rng = random.Random(80)
    pool = seeds()
    for s in pool:
        fuzz_one(s)
    for k in range(n):
        x = mutate(rng, rng.choice(pool))
        try:
            fuzz_one(x)
        except Exception:
            print("FAILED on input %s" % x.hex())
            raise
        if k % 4 == 0:
            pool.append(x)
            if len(pool) > 2000:
                pool.pop(rng.randrange(len(seeds()), len(pool)))
    print("fuzz quick: %d inputs, no crash" % n)


def main():
    args = sys.argv[1:]
    if args[:1] == ["--seeds"]:
        os.makedirs(args[1], exist_ok=True)
        for i, s in enumerate(seeds()):
            with open(os.path.join(args[1], "seed%02d" % i), "wb") as f:
                f.write(s)
        return
    if args[:1] == ["--quick"] or atheris is None:
        quick(int(args[1]) if len(args) > 1 and args[0] == "--quick" else 20000)
        return
    atheris.Setup(sys.argv, fuzz_one)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
