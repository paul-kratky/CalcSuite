"""Check the CalcSuite TI-Basic examples without a calculator.

84: tokenize (calc_files.tokenize_84), build the .8xp, read it back, detokenize, re-tokenize and
compare; flag lower case letter tokens and statistics tokens outside strings (a misspelt or
unknown command tokenizes as letters and only fails on the calculator).
89: build the .89p (calc_files.program_89p), read it back, check names and balanced blocks.
Also checks the complete programs inside fenced blocks of the docs.
"""
import os
import re
import sys

KIT = r"C:\CalcSuite"
sys.path.insert(0, os.path.join(KIT, "tools"))
import calc_files as cf  # noqa: E402


def suspicious_84(tok):
    """Lower case letter tokens (BB B0..CA) or statistics variables (62 xx) outside strings"""
    bad, i, in_str = [], 0, False
    while i < len(tok):
        a = tok[i]
        if a == 0x2A:
            in_str = not in_str
            i += 1
            continue
        if a in (0x3F, 0x04):
            in_str = False
            i += 1
            continue
        if a in cf.TWO_BYTE and i + 1 < len(tok):
            b = tok[i + 1]
            if not in_str and ((a == 0xBB and 0xB0 <= b <= 0xCA) or a == 0x62):
                bad.append(cf._two(a, b))
            i += 2
            continue
        i += 1
    return bad


def check_84(text, name):
    tok = cf.tokenize_84(text)
    blob = cf.program_8xp(text, name)
    (t, vname, _v, _a, data), = cf.read_ti8x(blob)
    assert t == 5 and vname == name.encode(), (t, vname)
    back = cf.detokenize_84(data)
    tok2 = cf.tokenize_84(back)
    return tok, back, tok == tok2 and data[2:] == tok, suspicious_84(tok)


OPEN = {"prgm": "endprgm", "func": "endfunc", "for": "endfor", "while": "endwhile",
        "loop": "endloop", "try": "endtry", "dialog": "enddlog", "toolbar": "endtbar",
        "custom": "endcustm"}


def check_89_structure(text):
    lines = [l.strip() for l in text.replace("\r", "").split("\n")]
    stack, errs = [], []
    for n, l in enumerate(lines, 1):
        s = re.sub(r'"[^"]*"', '""', l)  # Strings out
        s = s.split("\u00a9")[0].strip()  # Comments out
        low = s.lower()
        word = re.match(r"[a-z]+", low)
        w = word.group(0) if word else ""
        if w in OPEN and not (w == "for" and False):
            stack.append((w, n))
        elif w == "if" and re.search(r"\bthen\s*$", low):
            stack.append(("if", n))
        elif w == "elseif" or (w == "else" and not stack):
            if not stack or stack[-1][0] != "if":
                errs.append("line %d: %s outside If..Then" % (n, w))
        elif w.startswith("end"):
            want = "if" if w == "endif" else next((k for k, v in OPEN.items() if v == w), None)
            if want is None:
                errs.append("line %d: unknown %s" % (n, w))
            elif not stack or stack[-1][0] != want:
                errs.append("line %d: %s doesn't close %s" % (n, w, stack[-1] if stack else None))
            else:
                stack.pop()
        if re.search(r"\b(local|define)\b", low) is None:
            pass
    if stack:
        errs.append("not closed: %s" % stack)
    names = set(re.findall(r"\bLocal\s+([^\n]+)", text))
    for group in names:
        for v in group.split(","):
            v = v.strip()
            if not re.match(r"^[a-z][a-z0-9_]{0,7}$", v):
                errs.append("bad local name %r" % v)
    return errs


def check_89(text, name=None):
    n, vtype, blob = cf.program_89p(text, name)
    (folder, vname, t, _a, d2), = cf.read_ti89(blob)
    shown = cf.program_89_text(d2)
    errs = check_89_structure(text)
    return n, vtype, shown is not None, errs


def main():
    fails = 0
    d84 = os.path.join(KIT, "programs", "ti84")
    for f in sorted(os.listdir(d84)):
        text = cf_text(os.path.join(d84, f))
        name = cf.name_84_from(os.path.splitext(f)[0])
        try:
            tok, back, ok, sus = check_84(text, name)
            print("%-4s 84 %-12s %4d bytes, round trip %s%s" % (
                "PASS" if ok and not sus else "FAIL", f, len(tok), ok,
                ("; letters/stat tokens outside strings: %s" % sus) if sus else ""))
            fails += not ok or bool(sus)
        except ValueError as e:
            print("FAIL 84 %-12s %s" % (f, e))
            fails += 1
    d89 = os.path.join(KIT, "programs", "ti89")
    for f in sorted(os.listdir(d89)):
        text = cf_text(os.path.join(d89, f))
        try:
            n, vtype, ok, errs = check_89(text)
            stem = os.path.splitext(f)[0]
            if n != stem:
                errs.append("name %s != file %s" % (n, stem))
            print("%-4s 89 %-12s name=%s type=%s text kept=%s %s" % (
                "PASS" if ok and not errs else "FAIL", f, n, "prgm" if vtype == 0x12 else "func",
                ok, "; ".join(errs)))
            fails += not ok or bool(errs)
        except ValueError as e:
            print("FAIL 89 %-12s %s" % (f, e))
            fails += 1
    # Fenced blocks in the docs
    for doc in ("TIBASIC_84.md", "TIBASIC_89.md"):
        p = os.path.join(KIT, "docs", doc)
        if not os.path.exists(p):
            continue
        src = open(p, encoding="utf-8").read()
        blocks = re.findall(r"^```(tibasic8[49])([^\n]*)\n(.*?)^```", src, re.S | re.M)
        nfull = nsnip = 0
        for lang, info, body in blocks:
            m = re.search(r"name=(\S+)", info)
            try:
                if lang == "tibasic84":
                    tok = cf.tokenize_84(body)
                    sus = suspicious_84(tok)
                    if m:
                        _t, _b, ok, sus = check_84(body, m.group(1))
                        nfull += 1
                        if not ok or sus:
                            raise ValueError("round trip %s, suspicious %s" % (ok, sus))
                    else:
                        nsnip += 1
                        if sus:
                            raise ValueError("suspicious %s" % sus)
                else:
                    if m:
                        n, _v, ok, errs = check_89(body, None)
                        nfull += 1
                        if n != m.group(1) or errs:
                            raise ValueError("name %s vs %s; %s" % (n, m.group(1), errs))
                    else:
                        nsnip += 1
                        for n_, l in enumerate(body.split("\n"), 1):
                            cf._line_89(l, n_)
            except (ValueError, AssertionError) as e:
                print("FAIL %s block %r: %s\n%s" % (doc, info, e, body[:200]))
                fails += 1
        print("%-4s %s: %d complete programs, %d snippets checked" % (
            "INFO", doc, nfull, nsnip))
    print("ALL PASSED" if not fails else "%d FAILURE(S)" % fails)
    return 1 if fails else 0


def cf_text(path):
    raw = open(path, "rb").read()
    return raw.decode("utf-8-sig")


if __name__ == "__main__":
    sys.exit(main())
