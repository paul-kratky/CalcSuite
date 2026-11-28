# SPDX-License-Identifier: MIT
"""Self-test for the Solver builder (tools/solver_builder.py, tools/solver_ui.py): no
calculator.

- rearranging: known cases give the expected answer and method; for every ready-made set,
  every variable found from random values puts the equation back in balance
- the generated programs pass the editor's checkers with no errors and no warnings, the 84's
  tokenizes and reads back the same, the 89's converts with balanced blocks
- the generated Python gives the right numbers under tools/run_on_pc.py (direct, linear,
  numeric and degrees), and its own direct()/nsolve() agree with the rearranger
- typing mistakes say what's wrong
- the window with faked calculators: templates, preview, Send through the editor's queue, Save

    python -I tools/selftest/solver_checks.py      (run_selftest.py runs it too)
"""

import os
import random
import re
import subprocess
import sys
import shutil
import tempfile

for _stream in (sys.stdout, sys.stderr):  # An old console code page can't print every symbol
    try:
        _stream.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
KIT = os.path.dirname(TOOLS)
for _p in (TOOLS, os.path.join(TOOLS, "nspire_cli"), os.path.join(TOOLS, "ti84_cli"),
           os.path.join(TOOLS, "docs_build")):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def check(ok, what):
    print("%-4s %s" % ("PASS" if ok else "FAIL", what))
    return 0 if ok else 1


# (equation, variable, method, the answer as plain text or None to skip the text)
CASES = [
    ("V = I*R", "I", "direct", "I = V/R"),
    ("V = I*R", "V", "direct", "V = I*R"),
    ("P = V^2/R", "V", "direct", "V = sqrt(P*R)"),
    ("P = V^2/R", "R", "direct", "R = V^2/P"),
    ("P = I^2*R", "I", "direct", "I = sqrt(P/R)"),
    ("Vout = Vin*R2/(R1+R2)", "R1", "direct", "R1 = Vin*R2/Vout - R2"),
    ("Vout = Vin*R2/(R1+R2)", "R2", "linear", "R2 = Vout*R1/(Vin - Vout)"),
    ("Vout = Vin*R2/(R1+R2)", "Vin", "direct", "Vin = Vout*(R1 + R2)/R2"),
    ("sigma = M*y/I", "I", "direct", "I = M*y/sigma"),
    ("tau = R*C", "C", "direct", "C = tau/R"),
    ("Vc = Vs*(1 - exp(-t/tau))", "t", "direct", None),
    ("x = v0*t + a*t^2/2", "t", "numeric", None),
    ("x = v0*t + a*t^2/2", "a", "direct", None),
    ("y = m*x + b", "x", "direct", "x = (y - b)/m"),
    ("A = pi*r^2", "r", "direct", "r = sqrt(A/pi)"),
    ("f = 1/(2*pi*sqrt(L*C))", "C", "direct", None),
    ("N = N0*2^(t/T)", "t", "direct", None),
    ("dB = 20*log(V2/V1)", "V2", "direct", "V2 = 10^(dB/20)*V1"),
    ("R = R1*R2/(R1+R2)", "R1", "linear", None),
    ("y = abs(x)", "x", "numeric", None),
    ("a = b - c", "c", "direct", "c = b - a"),
    ("q = -k*x", "x", "direct", "x = -q/k"),
    ("E = m*c^2", "c", "direct", "c = sqrt(E/m)"),
    ("z = 2R + 3(x - 1)", "x", "direct", None),  # Implied multiplication
]

# (equation lines, what the error must say)
BAD = [
    ("V == I*R", "exactly one ="),
    ("V = I*R = 3", "exactly one ="),
    ("V = ", "empty side"),
    ("V = I*(R", "expected ')'"),
    ("V = I*R)", "unexpected"),
    ("V = 5", "at least two variables"),
    ("V = I•R", "can't be read"),
    ("V = sqrt I", "needs brackets"),
]


def rearrange_checks(sb):
    f = 0
    for eq, var, how, text in CASES:
        lhs, rhs = sb.parse_equation(eq)
        got = sb.solve_for(lhs, rhs, var)
        shown = "%s = %s" % (var, sb.to_text(got[1])) if got[1] is not None else None
        ok = got[0] == how and (text is None or shown == text)
        if ok and got[1] is not None:
            ok = balanced(sb, lhs, rhs, var, got[1], seed=hash(eq) & 0xffff)
        f += check(ok, "rearranges %s for %s: %s%s" % (eq, var, how, " (%s)" % shown if shown else ""))
        if not ok:
            print("     got", got[0], shown)
    for eq, needle in BAD:
        try:
            sb.build({"name": "zzbad", "equations": [eq]})
            msg = ""
        except sb.SolverError as e:
            msg = str(e)
        f += check(needle in msg, "refuses %r: %s" % (eq, msg or "(no error)"))
    for name in ("Zz_x", "toolongname", "1abc", "", "solve"):
        try:
            sb.build({"name": name, "equations": ["V = I*R"]})
            msg = ""
        except sb.SolverError as e:
            msg = str(e)
        f += check(bool(msg), "refuses the program name %r" % name)
    return f


def balanced(sb, lhs, rhs, var, expr, seed=1, degrees=False, tries=12):
    """expr (var from the others) puts lhs = rhs back in balance for random values"""
    rnd = random.Random(seed)
    names = [v for v in sb.variables(lhs) + sb.variables(rhs) if v != var]
    good = 0
    for _ in range(tries * 4):
        env = {v: rnd.uniform(0.2, 3.0) for v in names}
        try:
            env[var] = sb.evaluate(expr, env, degrees)
            a, b = sb.evaluate(lhs, env, degrees), sb.evaluate(rhs, env, degrees)
        except (ValueError, ZeroDivisionError, OverflowError):
            continue  # Outside the domain (a root of a negative): another draw
        if abs(a - b) > 1e-9 * max(1.0, abs(a), abs(b)):
            return False
        good += 1
        if good >= tries:
            return True
    return good > 0


def template_checks(sb, cc, cf):
    import check_examples as ce
    f = 0
    for t in sb.TEMPLATES:
        plan = sb.build(sb.template_spec(t["key"]))
        bad = []
        for fm in plan["formulas"]:
            for v, (how, expr, note) in fm["solutions"].items():
                if expr is not None and not balanced(sb, fm["lhs"], fm["rhs"], v, expr,
                                                     degrees=plan["degrees"]):
                    bad.append("%s in %s" % (v, fm["text"]))
        f += check(not bad, "template %s: every rearranged variable balances its equation%s" % (
            t["key"], ": " + ", ".join(bad) if bad else ""))
        outs = sb.check_all(plan)
        for lang, o in outs.items():
            probs = [p for p in o["problems"] if p["severity"] in ("error", "warning")]
            f += check(not probs and not o["build_error"], "template %s: the %s program checks clean "
                       "(%d lines)" % (t["key"], lang, o["text"].count("\n")))
            for p in probs[:3]:
                print("     line %d: %s: %s" % (p["line"], p["severity"], p["message"]))
            if o["build_error"]:
                print("    ", o["build_error"])
        o = outs["ti84"]
        try:
            tok, back, same, sus = ce.check_84(o["text"], o["name"])
            ok = same and not sus
        except Exception as e:
            ok, sus = False, [str(e)]
        f += check(ok, "template %s: the 84's program tokenizes, reads back the same, no stray "
                   "letter tokens%s" % (t["key"], " %s" % sus if sus else ""))
        o = outs["ti89"]
        try:
            name, vtype, blob = cf.program_89p(o["text"], o["name"])
            errs = ce.check_89_structure(o["text"])
            ok = vtype == 0x12 and name == o["name"] and not errs
        except Exception as e:
            ok, errs = False, [str(e)]
        f += check(ok, "template %s: the 89's program converts (.89p) with balanced blocks%s" % (
            t["key"], " %s" % errs if errs else ""))
        ok = len(o["text"].encode("utf-8")) < 20000 and len(outs["python"]["text"]) < 20000
        f += check(ok, "template %s: the programs stay small (%d B Python, %d B 89)" % (
            t["key"], len(outs["python"]["text"]), len(o["text"].encode("utf-8"))))
        long_lines = [l for l in outs["python"]["text"].split("\n")
                      if re.match(r'^\s+print\("', l) and len(re.findall(r'"([^"]*)"', l)[0]) > 30]
        f += check(not long_lines, "template %s: Python's fixed printed lines fit 30 characters" % t["key"])
    return f


def python_function_checks(sb):
    """The generated Python's own direct() and nsolve() against the rearranger, in-process"""
    f = 0
    for t in sb.TEMPLATES:
        plan = sb.build(sb.template_spec(t["key"]))
        text = sb.generate_python(plan)
        ns = {}
        exec(compile(text.replace("\nmain()\n", "\n"), "<solver>", "exec"), ns)
        rnd = random.Random(7)
        bad = []
        for k, fm in enumerate(plan["formulas"]):
            for v in fm["vars"]:
                for _ in range(20):
                    env = {o: rnd.uniform(0.3, 2.5) for o in fm["vars"]}
                    try:
                        known = {o: env[o] for o in fm["vars"] if o != v}
                        x = ns["direct"](k, v, dict(known))
                        if x is None:
                            x = ns["nsolve"](k, v, dict(known), env[v])
                        known[v] = x
                        r = ns["residual"](k, known)
                    except (ValueError, ZeroDivisionError, OverflowError):
                        continue
                    if isinstance(x, complex):
                        continue
                    scale = max(1.0, abs(sb.evaluate(fm["lhs"], known, plan["degrees"])))
                    if abs(r) > 1e-8 * scale:
                        bad.append("%s in %s (residual %g)" % (v, fm["text"], r))
                    break
        f += check(not bad, "template %s: the Python program's direct()/nsolve() solve every "
                   "variable%s" % (t["key"], ": " + "; ".join(bad[:3]) if bad else ""))
    return f


# (template or spec, the program's input, what it must print)
RUNS = [
    ("zzohm", "1\n1\n2\n5\n0\n", "V = 10 V"),                       # V = I*R, I=2, R=5
    ("zzohm", "1\n3\n12\n4\n0\n", "R = 3 ohm"),                     # R = V/I
    ("zzohm", "3\n1\n12\n4\n0\n", "P = 36 W"),                      # P = V^2/R
    ("zzohm", "3\n2\n36\n4\n0\n", "V = 12 V"),                      # V = sqrt(P*R)
    ("vdiv", "3\n2.5\n5\n1000\n0\n", "R2 = 1000 ohm"),              # linear: from Vout, Vin, R1
    ("vdiv", "1\n5\n1000\n1000\n0\n", "Vout = 2.5 V"),
    ("kin", "2\n3\n50\n2\n3\n\n0\n", "t = 5.1452 s"),               # numeric: 1.5t^2+2t-50=0
    ("kin", "3\n4\n10\n0\n2\n0\n", "x = 25 m"),
    ("rc", "2\n3\n3.16060279\n5\n1\n0\n", "t = 1 s"),               # t from Vc = Vs*(1-e^(-t/tau))
    ("proj", "3\n10\n10\n0\n", "theta = 39.4066 deg"),              # degrees: asin(98.1/100)/2
    ("gas", "4\n101325\n0.0224\n1\n0\n", "T = 272.98"),
    ("zzohm", "1\n2\n10\nabc\n0\n\n0\n", "No answer for these values"),  # abc refused, then R=0
]


def run_checks(sb):
    f = 0
    folder = tempfile.mkdtemp(prefix="solver_")
    for key, stdin_text, expect in RUNS:
        if key == "zzohm":
            spec = sb.template_spec("ohm", name="zzohm")
        else:
            spec = sb.template_spec(key)
        plan = sb.build(spec)
        path = os.path.join(folder, plan["name"] + ".py")
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(sb.generate_python(plan))
        p = subprocess.run([sys.executable, "-I", os.path.join(TOOLS, "run_on_pc.py"), "--quiet", path],
                           input=stdin_text, capture_output=True, text=True, cwd=KIT, timeout=60)
        out = p.stdout + p.stderr
        ok = expect in out and "Traceback" not in out
        f += check(ok, "runs on PC: %s with %r -> %r" % (plan["name"], stdin_text.replace("\n", ","), expect))
        if not ok:
            print(out[-800:])
        p = subprocess.run([sys.executable, "-I", os.path.join(TOOLS, "check_nspire.py"), path],
                           capture_output=True, text=True, cwd=KIT)
        if key in ("zzohm", "kin") and expect.startswith(("V = 10", "t =")):
            f += check(p.returncode == 0 and "0 warning" in p.stdout,
                       "check_nspire.py passes the generated %s.py" % plan["name"])
    return f


def misc_checks(sb):
    f = 0
    plan = sb.build({"name": "zzcase", "equations": ["F = m*a", "f = 1/T", "E = e*V", "i = I*2"]})
    n89 = plan["names89"]
    vals = [n89[v] for v in plan["order"]]
    f += check(len(set(vals)) == len(vals) and n89["e"] != "e" and n89["i"] != "i",
               "the 89's names stay apart though it ignores case, and avoid e and i: %s" % vals)
    l84 = plan["letters84"]
    vals = [l84[v] for v in plan["order"]]
    f += check(len(set(vals)) == len(vals) and l84[None] not in vals,
               "the 84's letters are all different, the guess has its own: %s" % vals)
    plan = sb.build({"name": "zzunits", "title": "Ω law µ", "equations": ["V = I*R"],
                     "vars": {"R": {"unit": "Ω", "desc": "\"quoted\" -> x"}}})
    outs = sb.check_all(plan)
    f += check(all(not o["errors"] and not o["build_error"] for o in outs.values()) and
               all(ord(c) < 128 for c in outs["python"]["text"]),
               "non-ASCII units (Ω, µ), quotes and arrows in a description stay safe in all three")
    try:
        sb.build({"name": "zzbig", "equations": ["a = b"] * 9})
        msg = ""
    except sb.SolverError as e:
        msg = str(e)
    f += check("up to 8" in msg, "more than 8 equations are refused (the 84's menu)")
    sp = sb.spec_from_text("zzx", "T", "V = I*R\n# a note\n\nP = V*I", "V [V] voltage\nI current\n")
    f += check(sp["equations"] == ["V = I*R", "P = V*I"] and sp["vars"]["V"] == {"unit": "V", "desc": "voltage"}
               and sp["vars"]["I"] == {"unit": "", "desc": "current"}, "the typed fields read back as a spec")
    t84 = sb.to_text(sb.parse("x^23 + 2^-1.5 + 110^(y)"), "ti84", {"x": "X", "y": "Y"})
    f += check(t84 == "X^(23)+2^(-1.5)+(110)^Y", "the 84's ^ traps are avoided: %s" % t84)
    t89 = sb.to_text(sb.parse("exp(-t/tau)*1.5e-3"), "ti89", {"t": "t", "tau": "tau"})
    f += check(t89 == "e^(-t/tau)*0.0015", "the 89's text: %s" % t89)
    tpy = sb.to_text(sb.parse("sin(theta)"), "python", degrees=True)
    f += check(tpy == 'math.sin(math.radians(v["theta"]))', "degrees in Python: %s" % tpy)
    return f


class FakeCalc(object):
    def __init__(self, slug, title):
        self.slug, self.title, self.key_fmt, self.pid = slug, title, "%d", slug


class FakeMirror(object):
    """A connected calculator that answers every link command at once (nothing is sent)"""
    def __init__(self, slug, title):
        self.calc = FakeCalc(slug, title)
        self.info = {}
        self.lines = []

    def connected(self):
        return True

    def queue(self, line, note, done, progress):
        self.lines.append(line)
        if done:
            done(0, ["OK"] if line.startswith("send") else [])

    def send_nspire_files(self, files, done):
        self.lines.append("ls")  # The Nspire's own path lists, asks, then puts (here: at once)
        self.lines += ["send %s" % path for path, _folder in files]
        done(True, "sent")


def ui_checks(shots=None):
    """The window with three faked calculators. shots: a folder for screenshots, or None"""
    import tkinter as tk
    try:
        root = tk.Tk()
    except tk.TclError:
        print("SKIP the Solver builder window (no display)")
        return 0
    root.withdraw()
    import editor as ed
    import solver_ui as su
    f = 0
    mirrors = [FakeMirror("nspire", "TI-Nspire CX II CAS"), FakeMirror("ti84", "TI-84 Plus CE"),
               FakeMirror("ti89", "TI-89 Titanium")]
    saved_programs = ed.PROGRAMS
    ed.PROGRAMS = tempfile.mkdtemp(prefix="solver_builds_")  # Never the user's own folder
    e = ed.open_editor(root, mirrors, None)
    try:
        e.text.edit_modified(False)
        b = e.open_solver_builder()
        root.update()
        f += check(b.plan is not None and all(b.ready(l) for l in ("python", "ti84", "ti89")),
                   "window: the example (zzohm) builds and checks clean for all three")
        f += check(len(b.targets) == 3, "window: the three faked calculators are the Send targets")
        f += check(e.open_solver_builder() is b, "window: a second click brings the same window forward")
        b.template_box.set(next(t["label"] for t in su.sb.TEMPLATES if t["key"] == "kin"))
        b.use_template()
        root.update()
        rows = b.tree.get_children()
        hows = [b.tree.item(r, "values")[2] for r in rows]
        f += check(len(rows) == 12 and "numeric" in hows, "window: a template fills the fields and the "
                   "how-it's-found list (%d rows)" % len(rows))
        if shots:
            b.target_box.current(0)
            b.target_changed()
            grab(b.win, os.path.join(shots, "solver_builder_kinematics.png"))
        b._set(b.eq_text, "V = I*")
        b.rebuild()
        f += check(b.plan is None and b.send_button.cget("state") == "disabled" and "ends too soon"
                   in b.status_var.get(), "window: a broken equation disables Send and says why")
        b.load_spec({"name": "zzohm", "title": "Ohm's law", "equations": ["V = I*R", "P = V*I"],
                     "vars": {"V": {"unit": "V", "desc": "voltage"}, "I": {"unit": "A", "desc": "current"},
                              "R": {"unit": "ohm", "desc": "resistance"}, "P": {"unit": "W", "desc": "power"}}})
        root.update()
        if shots:
            for lang, k in (("python", 0), ("ti84", 1), ("ti89", 2)):
                b.target_box.current(k)
                b.target_changed()
                root.update()
                b.win.after(400)
                root.update()
                grab(b.win, os.path.join(shots, "solver_builder_%s.png" % lang))
        sent = {}
        for k, m in enumerate(mirrors):
            b.target_box.current(k)
            b.target_changed()
            before = len(m.lines)
            ok = b.send()
            for _ in range(20):
                root.update()
                e._pump()
            sent[m.calc.slug] = (ok, m.lines[before:])
        for slug, (ok, lines) in sent.items():
            path = lines[-1][5:] if lines and lines[-1].startswith("send ") else ""
            want = {"nspire": "zzohm.tns", "ti84": "ZZOHM.8xp", "ti89": "zzohm.89p"}[slug]
            f += check(ok and lines[:1] == ["ls"] and os.path.basename(path) == want and os.path.isfile(path),
                       "window: Send to the %s goes through the editor: ls, then send %s" % (slug, want))
        f += check(e.lang == "ti89" and e.program_name() == "zzohm" and "zzohm()" in e.get_text(),
                   "window: the editor holds the last program sent (89, zzohm)")
        out = tempfile.mkdtemp(prefix="solver_save_")
        written = b.save(folder=out, ask=False)
        names = sorted(os.path.relpath(p, out).replace("\\", "/") for p in written)
        f += check(names == ["nspire/zzohm.py", "nspire/zzohm.tns", "ti84/ZZOHM.8xp", "ti84/ZZOHM.txt",
                             "ti89/zzohm.89p", "ti89/zzohm.txt"] and all(os.path.getsize(p) for p in written),
                   "window: Save writes each source and its calculator file: %s" % ", ".join(names))
        top = b.winfo_toplevel()
        b.close()
        root.update()
        f += check(not b.alive() and not top.winfo_exists(), "window: Close takes the frame and its thin window away")
        # As a main-window tab: a host that offers open_tool_tab gets the frame, no window
        class Host(object):
            def __init__(self):
                self.root, self.tabs = root, {}

            def editor_title(self, text):
                pass

            def open_tool_tab(self, key, title, make):
                frame = tk.Frame(root)
                self.tabs[key] = (title, frame)
                panel = make(frame)
                panel.pack(fill="both", expand=True)
                return panel
        tops_before = len([w for w in root.winfo_children() if isinstance(w, tk.Toplevel)])
        e.host = Host()
        p = e.open_solver_builder()
        root.update()
        tops_after = len([w for w in root.winfo_children() if isinstance(w, tk.Toplevel)])
        f += check(isinstance(p, su.SolverPanel) and "solver" in e.host.tabs and tops_after == tops_before
                   and p.winfo_toplevel() is root and p.ready("ti84"),
                   "window: with a host that holds tabs, the builder is a frame in a tab (no pop-out)")
        p.close()
        e.host = None
    finally:
        e.close(force=True)
        root.destroy()
        ed.PROGRAMS = saved_programs
    return f


def no_calculator_checks():
    """Writing programs with no calculator at all (the faked scan found none): every model's
    language, the checkers, Build and Save work; Send is greyed with a hint, and comes alive
    once that model is plugged in"""
    import tkinter as tk
    try:
        root = tk.Tk()
    except tk.TclError:
        print("SKIP the editor without calculators (no display)")
        return 0
    root.withdraw()
    import editor as ed
    f = 0
    saved_programs = ed.PROGRAMS
    ed.PROGRAMS = tempfile.mkdtemp(prefix="nocalc_builds_")  # Never the user's own folder
    out = tempfile.mkdtemp(prefix="nocalc_saves_")
    e = ed.open_editor(root, [], None)
    try:
        root.update()
        labels = [t[0] for t in e.targets]
        f += check(labels == ["TI-Nspire CX II (not plugged in)", "TI-84 Plus CE (not plugged in)",
                              "TI-89 Titanium (not plugged in)", "No calculator: save only"],
                   "no calculator: every model can be chosen (%s)" % "; ".join(labels))
        programs = {
            "ti84": ("ti84", "ZZNOC", 'Disp "HI"\n', 'Goto Q\n', "TI-84 Plus CE"),
            "ti89": ("ti89", "zznoc", 'zznoc()\nPrgm\nDisp "hi"\nEndPrgm\n', 'zznoc()\nPrgm\nIf x>1 Then\n',
                     "TI-89 Titanium"),
            "python": ("nspire", "zznoc", 'print("hi")\n', 'print("hi"\nimport numpy\n', "TI-Nspire CX II"),
        }
        for lang, (slug, name, good, bad, title) in programs.items():
            k = next(i for i, t in enumerate(e.targets) if t[2] == lang)
            e.target_box.current(k)
            e.set_target(k)
            e.new(lang, ask=False)
            e.name_var.set(name)
            e.set_text(bad)
            e.run_check()
            errors = [p for p in e.problems if p["severity"] == "error"]
            e.set_text(good)
            e.run_check()
            clean = not [p for p in e.problems if p["severity"] == "error"]
            f += check(e.lang == lang and errors and clean,
                       "no calculator, %s: the checker finds the mistake, the good program is clean" % title)
            root.update()
            hint = str(e.send_hint.cget("text"))
            f += check(str(e.send_button.cget("state")) == "disabled" and str(e.run_button.cget("state")) == "disabled"
                       and hint.startswith("Plug in a %s to send:" % title),
                       "no calculator, %s: Send greyed, hint %r" % (title, hint))
            f += check(e.send() is False and "Plug in a %s" % title in e.status_var.get(),
                       "no calculator, %s: F5 says to plug it in, sends nothing" % title)
            built = e.build(quiet=True)
            f += check(built is not None and os.path.isfile(built["file"]) and
                       os.path.commonpath([built["file"], ed.PROGRAMS]) == ed.PROGRAMS,
                       "no calculator, %s: Build makes %s" % (title, os.path.basename(built["file"]) if built else "nothing"))
            path = os.path.join(out, "zznoc_%s.txt" % lang)
            e.write(path)
            with open(path, encoding="utf-8") as fh:
                f += check(fh.read() == good, "no calculator, %s: Save writes the file" % title)
        # The 84 is plugged in: the chosen model becomes it, Send comes alive
        k = next(i for i, t in enumerate(e.targets) if t[2] == "ti84")
        e.target_box.current(k)
        e.set_target(k)
        m = FakeMirror("ti84", "TI-84 Plus CE")
        e.calculators_changed([m])
        root.update()
        f += check(e.target() is m and str(e.send_button.cget("state")) == "normal" and
                   not e.send_hint.cget("text"), "a TI-84 Plus CE plugged in: Send is ready for it")
        e.calculators_changed([])
        f += check(e.target() is None and str(e.send_button.cget("state")) == "disabled",
                   "unplugged again: Send greyed again")
    finally:
        e.close(force=True)
        root.destroy()
        ed.PROGRAMS = saved_programs
        shutil.rmtree(out, ignore_errors=True)
    return f


def grab(win, path):
    try:
        from PIL import ImageGrab
        import time
        win = win.winfo_toplevel()
        win.attributes("-topmost", True)  # Other windows on the desktop never cover the picture
        win.lift()
        win.update()
        time.sleep(0.3)
        win.update()
        x, y = win.winfo_rootx(), win.winfo_rooty()
        w, h = win.winfo_width(), win.winfo_height()
        ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True).save(path)
        win.attributes("-topmost", False)
        print("     screenshot: %s" % path)
    except Exception as e:
        print("     (no screenshot: %s)" % e)


def main(shots=None):
    import solver_builder as sb
    import code_check as cc
    import calc_files as cf
    f = 0
    f += rearrange_checks(sb)
    f += template_checks(sb, cc, cf)
    f += python_function_checks(sb)
    f += run_checks(sb)
    f += misc_checks(sb)
    f += ui_checks(shots)
    f += no_calculator_checks()
    return f


if __name__ == "__main__":
    shots = None
    if "--shots" in sys.argv:
        shots = sys.argv[sys.argv.index("--shots") + 1]
        os.makedirs(shots, exist_ok=True)
    n = main(shots)
    print("\n%s" % ("ALL PASSED" if not n else "%d FAILURE(S)" % n))
    sys.exit(1 if n else 0)
