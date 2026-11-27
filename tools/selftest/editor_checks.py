# SPDX-License-Identifier: MIT
"""Self-test for the program editor's pure parts (tools/code_check.py): no window, no
calculator.

- every example program (programs/ti84, programs/ti89, programs/*.py, the guides' complete
  programs, the Python guide's code) checks with zero errors
- each rule catches its mistake with the expected message at the exact span
- highlighting, completions, signature hints, hover, display indent, bracket match, the AI
  instructions and the problem text

    python -I tools/selftest/editor_checks.py      (run_selftest.py runs it too)
"""

import glob
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
KIT = os.path.dirname(TOOLS)
for _p in (TOOLS, os.path.join(TOOLS, "nspire_cli"), os.path.join(TOOLS, "ti84_cli")):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def check(ok, what):
    print("%-4s %s" % ("PASS" if ok else "FAIL", what))
    return 0 if ok else 1


# (language, text, program name, [(line, col, end_col, severity, part of the message)])
RULES = [
    # ---- TI-84 Plus CE ----
    ("ti84", "Disp 1\n\ttextcolor(1)", None, [(2, 0, 1, "error", "a tab"),
                                             (2, 1, 10, "error", "'textcolor(' isn't a TI-84 command")]),
    ("ti84", "Then\nDisp 1\nEnd", None, [(1, 0, 4, "error", "Then without an If")]),
    ("ti84", "Else", None, [(1, 0, 4, "error", "Else outside an If ... Then block")]),
    ("ti84", "End", None, [(1, 0, 3, "error", "End with no block to close")]),
    ("ti84", "For(I,1,5\nDisp I", None, [(1, 0, 4, "warning", "For( has no End")]),
    ("ti84", "Lbl ABC\nGoto Q", None, [(1, 0, 7, "error", "a label is 1 or 2 characters"),
                                      (2, 0, 6, "error", "no Lbl Q in the program")]),
    ("ti84", "Lbl A\nLbl A\nGoto A", None, [(2, 0, 5, "warning", "Lbl A is there twice")]),
    ("ti84", 'Menu("T","A",A,"B"\nLbl A', None, [(1, 0, 18, "error", "Menu( takes a title, then pairs")]),
    ("ti84", "A=5", None, [(1, 0, 3, "error", "A=... compares, it doesn't store")]),
    ("ti84", "5→3", None, [(1, 2, 3, "error", "can't be stored into")]),
    ("ti84", "5->A+1", None, [(1, 4, 6, "error", "a store ends the statement")]),
    ("ti84", "5→", None, [(1, 1, 2, "error", "nothing after →")]),
    ("ti84", "1+2)", None, [(1, 3, 4, "error", "a ) with nothing open")]),
    ("ti84", "randInt(1)", None, [(1, 0, 10, "error", "randInt( needs at least 2 arguments, it has 1")]),
    ("ti84", 'Output(11,1,"X")', None, [(1, 7, 9, "error", "Output( row 11 is off the screen")]),
    ("ti84", 'Output(1,27,"X")', None, [(1, 9, 11, "error", "Output( column 27 is off the screen")]),
    ("ti84", "For(L1,1,5)\nEnd", None, [(1, 4, 6, "error", "For('s counter must be a real variable")]),
    ("ti84", "Prompt A,5", None, [(1, 9, 10, "error", "Prompt takes variables")]),
    ("ti84", 'Input "X",5', None, [(1, 10, 11, "error", "Input's last argument must be a variable")]),
    ("ti84", "Input 5,X", None, [(1, 6, 7, "error", "Input's prompt must be a string")]),
    ("ti84", "DelVar 5", None, [(1, 7, 8, "error", "DelVar deletes a variable")]),
    ("ti84", "{1}->|LABCDEF", None, [(1, 5, 13, "error", "list name 'ABCDEF'")]),
    ("ti84", "X^23", None, [(1, 1, 4, "warning", "^23 is ^2 then 3")]),
    ("ti84", "Disp 1", "1BAD", [(1, 0, 1, "error", "can't be a TI-84 program name")]),
    ("ti84", 'Disp "HI\nDisp sin(1', None, [(1, 5, 8, "info", "the string isn't closed"),
                                          (2, 5, 9, "info", "bracket left open")]),
    ("ti84", "Goto A\nFor(I,1,2\nLbl A\nGoto A\nEnd", None, [(4, 0, 5, "info", "Goto out of a block")]),
    # ---- TI-89 Titanium ----
    ("ti89", "toolongname()\nPrgm\nEndPrgm", None, [(1, 0, 13, "error", "the 89 takes up to 8")]),
    ("ti89", "t()\nDisp 1", None, [(2, 0, 6, "error", "the next line is Prgm or Func")]),
    ("ti89", "t()\nPrgm\nDisp 1", None, [(3, 0, 6, "error", "has no EndPrgm at its end")]),
    ("ti89", "t()\nPrgm\nIf x>1 Then\nDisp 1\nEndPrgm", None, [(3, 0, 2, "error", "If ... Then has no EndIf")]),
    ("ti89", "t()\nPrgm\nFor i,1,2\nEndWhile\nEndFor\nEndPrgm", None,
     [(4, 0, 8, "error", "EndWhile, but the open block is For")]),
    ("ti89", "t()\nPrgm\nElse\nEndPrgm", None, [(3, 0, 4, "error", "Else outside If ... Then or Try")]),
    ("ti89", "t()\nPrgm\nEnd\nEndPrgm", None, [(3, 0, 3, "error", "End alone isn't a TI-89 command")]),
    ("ti89", "f(x)\nFunc\nDisp x\nReturn x\nEndFunc", None, [(3, 0, 4, "error", "isn't allowed in a function")]),
    ("ti89", "f(x)\nFunc\n2->y\nReturn y\nEndFunc", None, [(3, 3, 4, "error", "y isn't Local")]),
    ("ti89", "f(x)\nFunc\nLocal i\nFor j,1,2\nEndFor\nReturn 1\nEndFunc", None,
     [(4, 4, 5, "error", "the For counter j isn't Local")]),
    ("ti89", 'f(x)\nFunc\nLocal o\nsetMode("Angle","Degree")->o\nReturn 1\nEndFunc', None,
     [(4, 0, 8, "error", "setMode( isn't allowed in a function")]),
    ("ti89", "t()\nPrgm\nReturn 5\nEndPrgm", None, [(3, 0, 8, "error", "Return with a value in a program")]),
    ("ti89", "t()\nPrgm\nDisp nInt(x,x,0)\nEndPrgm", None, [(3, 5, 16, "error", "nInt( needs 4 arguments, it has 3")]),
    ("ti89", "t()\nPrgm\nDisp 10@>Foo\nEndPrgm", None, [(3, 7, 12, "error", "@> needs a conversion after it")]),
    ("ti89", "t()\nPrgm\n5->xmin\n5->solve\nEndPrgm", None, [(3, 3, 7, "error", "xmin is a built-in name"),
                                                         (4, 3, 8, "error", "solve is a built-in name")]),
    ("ti89", "t()\nPrgm\nLocal log\nEndPrgm", None, [(3, 6, 9, "error", "log is a built-in name")]),
    ("ti89", "t()\nPrgm\na=5\nEndPrgm", None, [(3, 0, 3, "error", "a=... compares")]),
    ("ti89", "t()\nPrgm\nDisp (1+2\nEndPrgm", None, [(3, 5, 6, "error", "1 bracket not closed")]),
    ("ti89", 't()\nPrgm\nDisp "hi\nEndPrgm', None, [(3, 5, 8, "error", "the string isn't closed")]),
    ("ti89", "t()\nPrgm\n5->abcdefghi\nEndPrgm", None, [(3, 3, 12, "error", "names are up to 8")]),
    ("ti89", "t()\nPrgm\nCycle\nEndPrgm", None, [(3, 0, 5, "error", "Cycle outside a loop")]),
    ("ti89", "t()\nPrgm\n1->a\nLocal a\nEndPrgm", None, [(4, 6, 7, "warning", "Local a comes after a is stored")]),
    ("ti89", "t()\nPrgm\nDisp “hi”\nEndPrgm", None, [(3, 5, 6, "error", "isn't a character the TI-89 has")]),
    ("ti89", 't()\nPrgm\nRequest "this prompt is far too long",s\nEndPrgm', None,
     [(3, 8, 37, "warning", "a Request prompt of 27 characters")]),
    # ---- TI-Nspire Python ----
    ("python", 'print(f"{1}")', None, [(1, 6, 12, "error", "f-string")]),
    ("python", "x = (1,", None, [(1, 4, 5, "error", "syntax error: '(' was never closed")]),
    ("python", "import numpy", None, [(1, 0, 12, "error", "module 'numpy' does not exist")]),
    ("python", "print(y)", None, [(1, 6, 7, "error", "'y' isn't defined")]),
    ("python", "from ti_draw import *\ndraw_line(1, 2)", None, [(2, 0, 15, "error", "draw_line() needs 4 arguments")]),
    ("python", "import ti_draw\nti_draw.draw_lines(1, 2, 3, 4)", None,
     [(2, 0, 18, "error", "'ti_draw.draw_lines' is not in TI's documented ti_draw menu")]),
    ("python", "def f(a, b=1):\n    return a\nf()\nf(1, 2, 3)", None,
     [(3, 0, 3, "error", "f() needs at least 1 argument"), (4, 0, 10, "error", "f() takes at most 2")]),
    ("python", "if 1:\n  x = 1", None, [(2, 0, 2, "warning", "an indent of 2 spaces")]),
    ("python", "x := 1", None, [(1, 2, 4, "error", "syntax error")]),
    ("python", "s = 'a'.ljust(3)", None, [(1, 4, 13, "warning", "'.ljust()'")]),
    ("python", "print(1)", "2bad", [(1, 0, 1, "error", "can't be the program's name")]),
]

# Correct code that must give no errors (and, where noted, nothing at all)
CLEAN = [
    ("ti84", "DelVar ADelVar BDisp 1\n5→dim(L1)\n{1,2}→ʟRES\n0→Xmin\n\"HI\"→Str1\n"
             "For(I,1,3):Output(I,1,I):End\nMenu(\"T\",\"A\",A,\"B\",B)\nLbl A\nLbl B\nInput \"X=\",X\n"
             "Prompt A,B\nIf A=B:Then:Disp 1:Else:Disp 2:End\nRepeat getKey:End\nmean(L1)→M"),
    ("ti89", "t(n)\nPrgm\nLocal i,s\n0->s\nFor i,1,n\ns+i->s\nEndFor\nTry\nexpr(\"1\")->s\nElse\nClrErr\nEndTry\n"
             "If s>1 Then\nDisp s\nElseIf s<0 Then\nDisp -s\nElse\nDisp 0\nEndIf\nLoop\nExit\nEndLoop\n"
             "Disp 10@>Bin,3_m@>_ft,mat►list([1,2])\nEndPrgm"),
    ("python", "import math\nfrom ti_system import get_key\n\n\ndef area(r, k=1):\n    return k * math.pi * r ** 2\n\n\n"
               "print(area(2), area(2, 3))\nfor i in range(3):\n    print(i)\nget_key(1)\n"),
]


def examples():
    """Every example program shipped with CalcSuite: (language, label, text, name)"""
    import calc_files as cf
    out = []
    for f in sorted(glob.glob(os.path.join(KIT, "programs", "ti84", "*.txt"))):
        stem = os.path.splitext(os.path.basename(f))[0]
        out.append(("ti84", "programs/ti84/" + os.path.basename(f), open(f, encoding="utf-8-sig").read(),
                    cf.name_84_from(stem)))
    for f in sorted(glob.glob(os.path.join(KIT, "programs", "ti89", "*.txt"))):
        out.append(("ti89", "programs/ti89/" + os.path.basename(f), open(f, encoding="utf-8-sig").read(), None))
    for f in sorted(glob.glob(os.path.join(KIT, "programs", "*.py"))):
        out.append(("python", "programs/" + os.path.basename(f), open(f, encoding="utf-8").read(),
                    os.path.splitext(os.path.basename(f))[0]))
    for doc, lang in (("TIBASIC_84.md", "ti84"), ("TIBASIC_89.md", "ti89")):
        p = os.path.join(KIT, "docs", doc)
        if os.path.isfile(p):
            src = open(p, encoding="utf-8").read()
            for info, body in re.findall(r"^```tibasic8[49]([^\n]*)\n(.*?)^```", src, re.S | re.M):
                m = re.search(r"name=(\S+)", info)
                if m:
                    out.append((lang, "%s %s" % (doc, m.group(1)), body, m.group(1) if lang == "ti84" else None))
    p = os.path.join(KIT, "docs", "PYTHON_NSPIRE_GUIDE.md")
    if os.path.isfile(p):
        src = open(p, encoding="utf-8").read()
        for k, body in enumerate(re.findall(r"^```python[^\n]*\n(.*?)^```", src, re.S | re.M)):
            out.append(("python", "PYTHON_NSPIRE_GUIDE.md block %d" % (k + 1), body, None))
    return out


def main():
    import code_check as cc
    f = 0
    # Examples: zero errors
    bad, slow = [], 0.0
    exs = examples()
    for lang in cc.LANGS:  # The token tables load once (tivars' sheet: a few hundred ms)
        cc.check(lang, "x")
    for lang, label, text, name in exs:
        t0 = time.perf_counter()
        errs = [p for p in cc.check(lang, text, name) if p["severity"] == "error"]
        slow = max(slow, time.perf_counter() - t0)
        if errs:
            bad.append("%s line %d: %s" % (label, errs[0]["line"], errs[0]["message"]))
    f += check(not bad and len(exs) >= 20, "every example program (%d) checks with zero errors%s" % (
        len(exs), (": " + "; ".join(bad[:4])) if bad else ""))
    f += check(slow < 0.3, "each example checks in under 300 ms (slowest %.0f ms)" % (slow * 1000))
    # Reference examples: no wrong argument counts
    import reference
    bad = []
    for slug in ("ti84", "ti89"):
        for e in reference.load(slug)["entries"]:
            ex = e.get("example") or ""
            for p in cc.check(slug, ex):
                if "argument" in p["message"]:
                    bad.append("%s %s: %s" % (slug, ex, p["message"]))
    f += check(not bad, "the reference's own examples have the right argument counts%s" % (
        (": " + "; ".join(bad[:3])) if bad else ""))
    for lang, text in CLEAN:
        errs = [p for p in cc.check(lang, text) if p["severity"] in ("error", "warning")]
        f += check(not errs, "%s: correct code passes (%s)" % (lang, "; ".join(
            "%d:%d %s" % (p["line"], p["col"], p["message"]) for p in errs[:3]) or "no errors, no warnings"))
    # Every rule: the expected message, exact span
    for lang, text, name, want in RULES:
        got = cc.check(lang, text, name)
        for line, col, end, sev, part in want:
            hit = [p for p in got if part in p["message"]]
            ok = any((p["line"], p["col"], p["end_col"], p["severity"]) == (line, col, end, sev) for p in hit)
            f += check(ok, "%s %r: %s %d:%d-%d %r%s" % (
                lang, text[:28], sev, line, col, end, part, "" if ok else "  GOT %s" % [
                    (p["line"], p["col"], p["end_col"], p["severity"], p["message"][:50]) for p in got]))
    # The problem dicts' shape
    p = cc.check("ti84", "End")[0]
    f += check(set(p) == {"line", "col", "end_col", "severity", "message", "fix"} and p["fix"], "problem shape and fix")
    txt = cc.problems_text(cc.check("ti84", "A=5"), "ti84", "DEMO")
    f += check("line 1, col 1: ERROR: A=..." in txt and "fix: 5→A" in txt, "problems as text for an AI")

    # Highlighting (VS Code Dark+ classes)
    h = {(t, l, c, e) for t, l, c, e in cc.highlight("ti84", 'For(I,1,3)\nDisp "HI",L1,Str1\nEnd\n5->A')}
    f += check({("control", 1, 0, 4), ("variable", 1, 4, 5), ("number", 1, 6, 7), ("builtin", 2, 0, 5),
                ("string", 2, 5, 9), ("sysvar", 2, 10, 12), ("sysvar", 2, 13, 17), ("control", 3, 0, 3),
                ("symbol", 4, 1, 3)} <= h, "84 highlight classes")
    h = {(t, l, c, e) for t, l, c, e in cc.highlight("ti89", "Local a\nIf a>1 Then© note\nDisp nInt(a,a,0,1)")}
    f += check({("storage", 1, 0, 5), ("control", 2, 0, 2), ("comment", 2, 11, 17), ("builtin", 3, 0, 4),
                ("builtin", 3, 5, 10), ("variable", 1, 6, 7)} <= h, "89 highlight classes")
    h = {(t, l, c, e) for t, l, c, e in cc.highlight("python", "def f(x):  # hi\n    return 'a' + 1")}
    f += check({("storage", 1, 0, 3), ("comment", 1, 11, 15), ("control", 2, 4, 10), ("string", 2, 11, 14),
                ("number", 2, 17, 18)} <= h, "Python highlight classes")
    f += check(cc.block_depths("ti84", "If A\nThen\nFor(I,1,2\nDisp I\nEnd\nElse\nDisp 2\nEnd") ==
               [0, 0, 1, 2, 1, 0, 1, 0], "84 display indent per line")
    f += check(cc.block_depths("ti89", "t()\nPrgm\nIf a Then\nDisp 1\nElse\nDisp 2\nEndIf\nEndPrgm") ==
               [0, 0, 0, 1, 0, 1, 0, 0], "89 display indent per line")
    f += check(cc.bracket_match("a(b(c)d)", 1) == (1, 7) and cc.bracket_match("a(b(c)d)", 8) == (1, 7),
               "bracket match both ways")

    # Completions
    def labels(lang, text):
        return [c["label"] for c in cc.completions(lang, text, len(text))]
    f += check("nInt(" in labels("ti89", "nIn"), "89 completions for nIn: %s" % labels("ti89", "nIn")[:4])
    f += check("fnInt(" in labels("ti84", "fnI"), "84 completions for fnI")
    f += check(labels("ti84", "Disp")[:1] == ["DispGraph"] or "DispTable" in labels("ti84", "Disp"),
               "84 completions for Disp: %s" % labels("ti84", "Disp")[:4])
    f += check("total" in labels("ti89", "Local total\ntot"), "89 completions include the file's variables")
    f += check({"draw_line", "draw_text"} <= set(labels("python", "import ti_draw\nti_draw.dra")),
               "Python module members")
    f += check("radius" in labels("python", "radius = 2\nrad"), "Python file names")
    f += check(labels("ti84", "") == [], "no word, no list")

    # Signature hints
    def sig(lang, text):
        s = cc.signature_at(lang, text, len(text))
        return s and (s["name"], s["arg"], s["syntax"][s["span"][0]:s["span"][1]] if s["span"] else None)
    f += check(sig("ti84", "Disp fnInt(X^2,X,") == ("fnInt(", 2, "lower"), "84 hint: fnInt( third argument")
    f += check(sig("ti84", "Disp fnInt(sin(X),") == ("fnInt(", 1, "variable"), "84 hint: nesting counted right")
    f += check(sig("ti84", "Output(1,") == ("Output(", 1, "column"), "84 hint: Output( column")
    f += check(sig("ti89", "Disp nInt(x^2,x,") == ("nInt(", 2, "lower"), "89 hint: nInt( third argument")
    f += check(sig("ti89", "For i,1,") is not None and sig("ti89", "For i,1,")[1] == 2, "89 hint: For without brackets")
    s = sig("python", "import ti_draw\nti_draw.draw_rect(1, 2, ")
    f += check(s and s[1:] == (2, "width"), "Python hint: draw_rect width (%s)" % (s,))
    s = sig("ti84", 'Disp "A,B",')
    f += check(s and s[1] == 1, "84 hint: commas inside a string don't count (%s)" % (s,))
    f += check(sig("python", "x = 1") is None, "no hint outside a call")
    hv = cc.hover_at("ti89", "Disp nInt(x,x,0,1)", 6)
    f += check(hv and hv["name"] == "nInt(" and "Numeric" in hv["summary"], "hover card for nInt(")

    # Instructions for chat AIs
    for lang in cc.LANGS:
        t = cc.ai_instructions(lang)
        n = len(t.split("\n"))
        need = {"ti84": ["->", "<=", "sqrt(", "8", "End", "code block"],
                "ti89": ["@>", "@int(", "EndPrgm", "Local", "©", "name()"],
                "python": ["f-strings", "ti_draw", "MicroPython", "code block"]}[lang]
        f += check(n <= 40 and all(x in t for x in need), "AI instructions for %s: %d lines, the rules in it" % (lang, n))
    return f


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    sys.exit(1 if main() else 0)
