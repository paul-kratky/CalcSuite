# SPDX-License-Identifier: MIT
"""Solver builder: equations typed once -> a menu-driven solver program for each calculator.

    import solver_builder as sb
    spec = sb.spec_from_text("zzohm", "Ohm's law", "V = I*R\\nP = V*I", "V [V] voltage\\nI [A]")
    plan = sb.build(spec)              # rearranges every equation for every variable
    text = sb.generate("python", plan) # or "ti84", "ti89"
    outs = sb.check_all(plan)          # {lang: {"text", "name", "problems", "errors"}}

The generated program asks which equation (when there are several) and which variable to
find, asks for the others, solves and shows the answer with its unit.

Solving happens on the PC where it can (no sympy: our own small rearranger):
- "direct": the variable appears once and every step on the way to it can be undone
  (+ - * / ^, unary minus, sqrt, ln, log, exp, sin/cos/tan and their inverses);
- "linear": it appears several times but the equation is linear in it once the fractions are
  cleared (a voltage divider's R2 in Vout = Vin*R2/(R1+R2));
- "numeric": anything else (x = v0*t + a*t^2/2 for t): the program asks for a guess and finds
  the root with the secant method (Python and the TI-89) or the 84's own solve(.

Pure: no window, no calculator. Tested by tools/selftest/solver_checks.py.
"""

import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

LANGS = ("python", "ti84", "ti89")
TITLES = {"python": "TI-Nspire CX II Python", "ti84": "TI-84 Plus CE TI-Basic",
          "ti89": "TI-89 Titanium TI-Basic"}
FUNCS = ("sqrt", "sin", "cos", "tan", "asin", "acos", "atan", "ln", "log", "exp", "abs")
FUNC_ALIASES = {"arcsin": "asin", "arccos": "acos", "arctan": "atan", "log10": "log"}
NAME = re.compile(r"^[a-z][a-z0-9]{0,7}$")  # A name all three calculators take
MAX_FORMULAS = 8   # The 84's Menu( shows 9 entries: 8 and Quit
MAX_VARS = 8       # Per equation, for the same reason


class SolverError(ValueError):
    """A mistake in what was typed, said so the user can fix it"""


# ---------------------------------------------------------------------------
# Parsing: text -> a tree of tuples
#   ("num", value) ("var", name) ("pi",) ("neg", a) ("fn", name, a)
#   ("add", a, b) ("sub", a, b) ("mul", a, b) ("div", a, b) ("pow", a, b)
# ---------------------------------------------------------------------------

_TOKEN = re.compile(r"\s*(?:(\d+\.?\d*(?:[eE][+-]?\d+)?|\.\d+(?:[eE][+-]?\d+)?)|"
                    r"([A-Za-z_][A-Za-z0-9_]*)|(\*\*|[-+*/^(),=]))")


def _tokens(text):
    out, i = [], 0
    text = text.replace("−", "-").replace("×", "*").replace("·", "*")
    while i < len(text):
        if text[i:].strip() == "":
            break
        m = _TOKEN.match(text, i)
        if not m:
            ch = text[i:].lstrip()[:1]
            raise SolverError("%r can't be read in %r (use + - * / ^ and brackets; Greek letters "
                              "by name: sigma, theta)" % (ch, text.strip()))
        if m.group(1):
            s = m.group(1)
            v = float(s) if any(c in s for c in ".eE") else int(s)
            out.append(("num", v))
        elif m.group(2):
            out.append(("name", m.group(2)))
        else:
            out.append(("op", "^" if m.group(3) == "**" else m.group(3)))
        i = m.end()
    return out


class _Parser(object):
    def __init__(self, text):
        self.text = text
        self.toks = _tokens(text)
        self.k = 0

    def peek(self):
        return self.toks[self.k] if self.k < len(self.toks) else ("end", None)

    def take(self):
        t = self.peek()
        self.k += 1
        return t

    def expect(self, op):
        t = self.take()
        if t != ("op", op):
            raise SolverError("expected %r in %r" % (op, self.text.strip()))

    def expr(self):
        a = self.term()
        while self.peek() in (("op", "+"), ("op", "-")):
            op = self.take()[1]
            a = ("add" if op == "+" else "sub", a, self.term())
        return a

    def term(self):
        a = self.unary()
        while True:
            t = self.peek()
            if t in (("op", "*"), ("op", "/")):
                self.take()
                a = ("mul" if t[1] == "*" else "div", a, self.unary())
            elif t[0] in ("num", "name") or t == ("op", "("):
                a = ("mul", a, self.unary())  # 2R, 2(a+b), (a)(b): an implied multiply
            else:
                return a

    def unary(self):
        t = self.peek()
        if t == ("op", "-"):
            self.take()
            return ("neg", self.unary())
        if t == ("op", "+"):
            self.take()
            return self.unary()
        return self.power()

    def power(self):
        a = self.atom()
        if self.peek() == ("op", "^"):
            self.take()
            return ("pow", a, self.unary())
        return a

    def atom(self):
        t = self.take()
        if t[0] == "num":
            return ("num", t[1])
        if t == ("op", "("):
            a = self.expr()
            self.expect(")")
            return a
        if t[0] == "name":
            name = t[1]
            low = FUNC_ALIASES.get(name.lower(), name.lower())
            if self.peek() == ("op", "(") and low in FUNCS:
                self.take()
                a = self.expr()
                self.expect(")")
                return ("fn", low, a)
            if name.lower() == "pi":
                return ("pi",)
            if low in FUNCS:
                raise SolverError("%s needs brackets: %s(x)" % (name, low))
            return ("var", name)
        if t[0] == "end":
            raise SolverError("%r ends too soon" % self.text.strip())
        raise SolverError("unexpected %r in %r" % (t[1], self.text.strip()))


def parse(text):
    """An expression -> its tree"""
    p = _Parser(text)
    if p.peek()[0] == "end":
        raise SolverError("an empty side in %r" % text.strip())
    a = p.expr()
    if p.peek()[0] != "end":
        raise SolverError("unexpected %r in %r" % (p.peek()[1], text.strip()))
    return a


def parse_equation(text):
    """'V = I*R' -> (lhs, rhs)"""
    if text.count("=") != 1:
        raise SolverError("%r needs exactly one = (like V = I*R)" % text.strip())
    left, right = text.split("=")
    return parse(left), parse(right)


def variables(node, out=None):
    """The variable names in a tree, in the order they first appear"""
    out = [] if out is None else out
    if node[0] == "var":
        if node[1] not in out:
            out.append(node[1])
    else:
        for c in node[1:]:
            if isinstance(c, tuple):
                variables(c, out)
    return out


def count(node, name):
    if node[0] == "var":
        return 1 if node[1] == name else 0
    return sum(count(c, name) for c in node[1:] if isinstance(c, tuple))


# ---------------------------------------------------------------------------
# Simplifying (only what keeps the answers readable)
# ---------------------------------------------------------------------------

ZERO, ONE = ("num", 0), ("num", 1)


def _is_num(n, v=None):
    return n[0] == "num" and (v is None or n[1] == v)


def _fold(v):
    if isinstance(v, float) and v.is_integer() and abs(v) < 1e15:
        return int(v)
    return v


def simplify(n):
    k = n[0]
    if k in ("num", "var", "pi"):
        return n
    if k == "fn":
        a = simplify(n[2])
        return ("fn", n[1], a)
    if k == "neg":
        a = simplify(n[1])
        if a[0] == "neg":
            return a[1]
        if _is_num(a):
            return ("num", _fold(-a[1]))
        if a[0] == "sub":
            return ("sub", a[2], a[1])
        return ("neg", a)
    a, b = simplify(n[1]), simplify(n[2])
    if k == "add":
        if _is_num(a, 0):
            return b
        if _is_num(b, 0):
            return a
        if _is_num(a) and _is_num(b):
            return ("num", _fold(a[1] + b[1]))
        if b[0] == "neg":
            return simplify(("sub", a, b[1]))
        if b[0] == "num" and b[1] < 0:
            return ("sub", a, ("num", -b[1]))
        if a[0] == "neg":
            return simplify(("sub", b, a[1]))
        return ("add", a, b)
    if k == "sub":
        if _is_num(b, 0):
            return a
        if _is_num(a, 0):
            return simplify(("neg", b))
        if _is_num(a) and _is_num(b):
            return ("num", _fold(a[1] - b[1]))
        if b[0] == "neg":
            return simplify(("add", a, b[1]))
        if a == b:
            return ZERO
        return ("sub", a, b)
    if k == "mul":
        if _is_num(a, 0) or _is_num(b, 0):
            return ZERO
        if _is_num(a, 1):
            return b
        if _is_num(b, 1):
            return a
        if _is_num(a, -1):
            return simplify(("neg", b))
        if _is_num(b, -1):
            return simplify(("neg", a))
        if _is_num(a) and _is_num(b):
            return ("num", _fold(a[1] * b[1]))
        if a[0] == "neg":
            return simplify(("neg", ("mul", a[1], b)))
        if b[0] == "neg":
            return simplify(("neg", ("mul", a, b[1])))
        return ("mul", a, b)
    if k == "div":
        if _is_num(b, 1):
            return a
        if _is_num(a, 0):
            return ZERO
        if _is_num(b, -1):
            return simplify(("neg", a))
        if _is_num(a) and _is_num(b) and b[1] != 0 and isinstance(a[1], int) and \
                isinstance(b[1], int) and a[1] % b[1] == 0:
            return ("num", a[1] // b[1])
        if a[0] == "neg":
            return simplify(("neg", ("div", a[1], b)))
        if b[0] == "neg":
            return simplify(("neg", ("div", a, b[1])))
        if a == b:
            return ONE
        return ("div", a, b)
    if k == "pow":
        if _is_num(b, 1):
            return a
        if _is_num(b, 0):
            return ONE
        if b == ("div", ONE, ("num", 2)) or _is_num(b, 0.5):
            return ("fn", "sqrt", a)
        if _is_num(a) and _is_num(b) and isinstance(a[1], int) and isinstance(b[1], int) and \
                0 <= b[1] <= 8 and abs(a[1]) < 10000:
            return ("num", a[1] ** b[1])
        return ("pow", a, b)
    raise ValueError(k)


# ---------------------------------------------------------------------------
# Rearranging
# ---------------------------------------------------------------------------

_INVERSE = {"sin": "asin", "cos": "acos", "tan": "atan", "asin": "sin", "acos": "cos",
            "atan": "tan", "ln": "exp", "exp": "ln"}


def isolate(lhs, rhs, target):
    """Solve lhs = rhs for target when it appears exactly once: (expression, note) or None.
    The note says which answer is given when there are several ("" when there's one)."""
    if count(lhs, target) + count(rhs, target) != 1:
        return None
    if count(lhs, target) == 0:
        lhs, rhs = rhs, lhs
    notes = []
    while lhs != ("var", target):
        k = lhs[0]
        if k == "neg":
            lhs, rhs = lhs[1], ("neg", rhs)
        elif k in ("add", "sub", "mul", "div"):
            a, b = lhs[1], lhs[2]
            in_a = count(a, target) == 1
            if k == "add":
                lhs, rhs = (a, ("sub", rhs, b)) if in_a else (b, ("sub", rhs, a))
            elif k == "sub":
                lhs, rhs = (a, ("add", rhs, b)) if in_a else (b, ("sub", a, rhs))
            elif k == "mul":
                lhs, rhs = (a, ("div", rhs, b)) if in_a else (b, ("div", rhs, a))
            else:
                lhs, rhs = (a, ("mul", rhs, b)) if in_a else (b, ("div", a, rhs))
        elif k == "pow":
            a, b = lhs[1], lhs[2]
            if count(a, target) == 1:
                b = simplify(b)
                if _is_num(b, 2):
                    rhs = ("fn", "sqrt", rhs)
                    notes.append("the positive root")
                else:
                    rhs = ("pow", rhs, ("div", ONE, b))
                    if _is_num(b) and isinstance(b[1], int) and b[1] % 2 == 0:
                        notes.append("the positive root")
                lhs = a
            else:  # a^x = r: x = ln(r)/ln(a)
                lhs, rhs = b, ("div", ("fn", "ln", rhs), ("fn", "ln", a))
        elif k == "fn":
            f, a = lhs[1], lhs[2]
            if f == "sqrt":
                rhs = ("pow", rhs, ("num", 2))
            elif f == "log":
                rhs = ("pow", ("num", 10), rhs)
            elif f in _INVERSE:
                rhs = ("fn", _INVERSE[f], rhs)
                if f in ("sin", "cos", "tan"):
                    notes.append("the principal angle")
            else:
                return None  # abs(): two answers
            lhs = a
        else:
            return None
    note = ", ".join(sorted(set(notes)))
    return simplify(rhs), note


def _lin_mul(p, q):
    """(a, b) * (c, d), each a*x + b: None unless one of them has no x"""
    (a, b), (c, d) = p, q
    if _is_num(a, 0):
        return simplify(("mul", b, c)), simplify(("mul", b, d))
    if _is_num(c, 0):
        return simplify(("mul", a, d)), simplify(("mul", b, d))
    return None


def _lin_add(p, q, sub=False):
    k = "sub" if sub else "add"
    return simplify((k, p[0], q[0])), simplify((k, p[1], q[1]))


def _rational(n, x):
    """n as N/D with N and D linear in x: ((a, b), (c, d)) or None"""
    if count(n, x) == 0:
        return (ZERO, n), (ZERO, ONE)
    k = n[0]
    if k == "var":
        return (ONE, ZERO), (ZERO, ONE)
    if k == "neg":
        r = _rational(n[1], x)
        if r is None:
            return None
        (a, b), d = r
        return (simplify(("neg", a)), simplify(("neg", b))), d
    if k in ("add", "sub", "mul", "div"):
        p, q = _rational(n[1], x), _rational(n[2], x)
        if p is None or q is None:
            return None
        (n1, d1), (n2, d2) = p, q
        if k in ("add", "sub"):
            if d1 == (ZERO, ONE) and d2 == (ZERO, ONE):
                return _lin_add(n1, n2, k == "sub"), d1
            a, b, c = _lin_mul(n1, d2), _lin_mul(n2, d1), _lin_mul(d1, d2)
            if a is None or b is None or c is None:
                return None
            return _lin_add(a, b, k == "sub"), c
        if k == "mul":
            a, c = _lin_mul(n1, n2), _lin_mul(d1, d2)
        else:
            a, c = _lin_mul(n1, d2), _lin_mul(d1, n2)
        if a is None or c is None:
            return None
        return a, c
    if k == "pow" and count(n[1], x) and not count(n[2], x) and simplify(n[2]) in (ONE, ("num", -1)):
        r = _rational(n[1], x)
        if r is None:
            return None
        return r if simplify(n[2]) == ONE else (r[1], r[0])
    return None


def solve_linear(lhs, rhs, target):
    """Solve lhs = rhs for target when it is linear once the fractions are cleared:
    (expression, "") or None"""
    p, q = _rational(lhs, target), _rational(rhs, target)
    if p is None or q is None:
        return None
    (n1, d1), (n2, d2) = p, q
    left, right = _lin_mul(n1, d2), _lin_mul(n2, d1)
    if left is None or right is None:
        return None
    a, b = _lin_add(left, right, sub=True)  # a*x + b = 0
    if _is_num(a, 0) or count(a, target) or count(b, target):
        return None
    b = simplify(("neg", b))
    if a[0] == "neg":
        a, b = a[1], simplify(("neg", b))
    if b[0] == "neg" and a[0] == "sub":
        a, b = ("sub", a[2], a[1]), b[1]
    return simplify(("div", b, a)), ""


def solve_for(lhs, rhs, target):
    """("direct", expr, note) | ("linear", expr, "") | ("numeric", None, note)"""
    r = isolate(lhs, rhs, target)
    if r is not None:
        return ("direct",) + r
    r = solve_linear(lhs, rhs, target)
    if r is not None:
        return ("linear",) + r
    return "numeric", None, "a numeric solve from your guess"


# ---------------------------------------------------------------------------
# Evaluating (for the self-test and the preview's sanity checks)
# ---------------------------------------------------------------------------

def evaluate(n, env, degrees=False):
    k = n[0]
    if k == "num":
        return float(n[1])
    if k == "var":
        return float(env[n[1]])
    if k == "pi":
        return math.pi
    if k == "neg":
        return -evaluate(n[1], env, degrees)
    if k == "fn":
        a = evaluate(n[2], env, degrees)
        f = n[1]
        if f in ("sin", "cos", "tan") and degrees:
            a = math.radians(a)
        r = {"sqrt": math.sqrt, "sin": math.sin, "cos": math.cos, "tan": math.tan,
             "asin": math.asin, "acos": math.acos, "atan": math.atan, "ln": math.log,
             "log": math.log10, "exp": math.exp, "abs": abs}[f](a)
        return math.degrees(r) if degrees and f in ("asin", "acos", "atan") else r
    a, b = evaluate(n[1], env, degrees), evaluate(n[2], env, degrees)
    if k == "add":
        return a + b
    if k == "sub":
        return a - b
    if k == "mul":
        return a * b
    if k == "div":
        return a / b
    r = a ** b
    if isinstance(r, complex):
        raise ValueError("not real")
    return r


# ---------------------------------------------------------------------------
# Printing a tree in each calculator's language
# ---------------------------------------------------------------------------

_PREC = {"add": 1, "sub": 1, "mul": 2, "div": 2, "neg": 3, "pow": 4}


def _num_text(v, lang):
    if isinstance(v, int):
        return str(v)
    s = repr(float(v))
    if "e" in s:
        mant, exp = s.split("e")
        if mant.endswith(".0"):
            mant = mant[:-2]
        s = "%s%s%d" % (mant, "e" if lang in ("python", "plain") else "E", int(exp))
    elif s.endswith(".0") and lang != "ti89":
        s = s[:-2]
    return s


def _level(n):
    if n[0] == "num" and n[1] < 0:
        return 3
    return _PREC.get(n[0], 5)


_FN = {
    "python": {"sqrt": "math.sqrt(%s)", "sin": "math.sin(%s)", "cos": "math.cos(%s)",
               "tan": "math.tan(%s)", "asin": "math.asin(%s)", "acos": "math.acos(%s)",
               "atan": "math.atan(%s)", "ln": "math.log(%s)", "log": "math.log10(%s)",
               "exp": "math.exp(%s)", "abs": "abs(%s)"},
    "ti84": {"sqrt": "sqrt(%s)", "sin": "sin(%s)", "cos": "cos(%s)", "tan": "tan(%s)",
             "asin": "sin^-1(%s)", "acos": "cos^-1(%s)", "atan": "tan^-1(%s)", "ln": "ln(%s)",
             "log": "log(%s)", "exp": "e^(%s)", "abs": "abs(%s)"},
    "ti89": {"sqrt": "sqrt(%s)", "sin": "sin(%s)", "cos": "cos(%s)", "tan": "tan(%s)",
             "asin": "sin⁻¹(%s)", "acos": "cos⁻¹(%s)",
             "atan": "tan⁻¹(%s)", "ln": "ln(%s)", "log": "log(%s)", "exp": "e^(%s)",
             "abs": "abs(%s)"},
    "plain": {f: f + "(%s)" for f in FUNCS},
}
_PY_DEG = {"sin": "math.sin(math.radians(%s))", "cos": "math.cos(math.radians(%s))",
           "tan": "math.tan(math.radians(%s))", "asin": "math.degrees(math.asin(%s))",
           "acos": "math.degrees(math.acos(%s))", "atan": "math.degrees(math.atan(%s))"}


def to_text(n, lang="plain", names=None, degrees=False):
    """A tree as text. lang: plain | python | ti84 | ti89. names: {variable: how it's written}
    (the 84's letters, the 89's safe names; Python: v["name"])."""
    def var(name):
        if lang == "python":
            return 'v["%s"]' % name
        return (names or {}).get(name, name)

    sp = " " if lang in ("python", "plain") else ""

    def go(n):
        k = n[0]
        if k == "num":
            if n[1] < 0:
                return "-" + _num_text(-n[1], lang)
            return _num_text(n[1], lang)
        if k == "var":
            return var(n[1])
        if k == "pi":
            return "math.pi" if lang == "python" else "pi"
        if k == "fn":
            fmt = _PY_DEG.get(n[1]) if lang == "python" and degrees else None
            return (fmt or _FN[lang][n[1]]) % go(n[2])
        if k == "neg":
            a = n[1]
            s = go(a)
            return "-" + ("(%s)" % s if _level(a) < 2 else s)
        a, b = n[1], n[2]
        if k == "pow":
            sa, sb = go(a), go(b)
            if _level(a) < 5 or (lang == "ti84" and a[0] == "num" and len(sa) > 1):
                sa = "(%s)" % sa
            simple_b = b[0] == "var" or (b[0] == "num" and b[1] >= 0)
            if lang == "ti84":
                simple_b = (b[0] == "var") or (b[0] == "num" and isinstance(b[1], int) and 0 <= b[1] <= 9)
            if not simple_b:
                sb = "(%s)" % sb
            return sa + ("**" if lang == "python" else "^") + sb
        op = {"add": "+", "sub": "-", "mul": "*", "div": "/"}[k]
        p = _PREC[k]
        sa, sb = go(a), go(b)
        if _level(a) < p:
            sa = "(%s)" % sa
        if _level(b) < p or (k in ("sub", "div") and _level(b) == p) or \
                (lang != "python" and _level(b) == 3 and k in ("add", "sub")):
            sb = "(%s)" % sb
        if k in ("mul", "div"):
            return sa + (" %s " % op if lang == "python" else op) + sb
        return sa + "%s%s%s" % (sp, op, sp) + sb
    return go(n)


# ---------------------------------------------------------------------------
# The solver's description: a spec, then a plan
# ---------------------------------------------------------------------------

_VAR_LINE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?:\[([^\]]*)\])?\s*(.*?)\s*$")


def parse_vars_text(text):
    """'R [ohm] resistance' lines -> {name: {"unit": "ohm", "desc": "resistance"}}"""
    out = {}
    for line in text.replace("\r", "").split("\n"):
        if not line.strip() or line.strip().startswith("#"):
            continue
        m = _VAR_LINE.match(line)
        if not m:
            raise SolverError("can't read %r: write a name, its unit in [brackets] and a "
                              "description, like: R [ohm] resistance" % line.strip())
        out[m.group(1)] = {"unit": (m.group(2) or "").strip(), "desc": m.group(3)}
    return out


def vars_text(meta, order=None):
    names = list(order or []) + [n for n in meta if n not in (order or [])]
    lines = []
    for n in names:
        m = meta.get(n, {})
        lines.append(("%s [%s] %s" % (n, m.get("unit", ""), m.get("desc", ""))).rstrip()
                     if m.get("unit") else ("%s %s" % (n, m.get("desc", ""))).rstrip())
    return "\n".join(lines)


def spec_from_text(name, title, equations_text, vars_text_="", degrees=False):
    eqs = [l.strip() for l in equations_text.replace("\r", "").split("\n")
           if l.strip() and not l.strip().startswith("#")]
    return {"name": name.strip(), "title": title.strip(), "equations": eqs,
            "vars": parse_vars_text(vars_text_), "degrees": bool(degrees)}


def build(spec):
    """A spec -> the plan every generator works from. Raises SolverError on a mistake."""
    name = (spec.get("name") or "").strip().lower()
    if not NAME.match(name):
        raise SolverError("the program name %r won't do: 1 to 8 letters and digits, a letter "
                          "first (it is the same name on all three calculators)" % spec.get("name"))
    import code_check as cc
    if name in cc.reserved_89():
        raise SolverError("%r is a TI-89 command or system variable: pick another name" % name)
    eqs = spec.get("equations") or []
    if not eqs:
        raise SolverError("type at least one equation, like V = I*R")
    if len(eqs) > MAX_FORMULAS:
        raise SolverError("%d equations: up to %d in one solver (the TI-84's menu shows 9 "
                          "entries)" % (len(eqs), MAX_FORMULAS))
    formulas, order = [], []
    for text in eqs:
        lhs, rhs = parse_equation(text)
        names = variables(lhs) + [v for v in variables(rhs) if v not in variables(lhs)]
        if len(names) < 2:
            raise SolverError("%r needs at least two variables" % text)
        if len(names) > MAX_VARS:
            raise SolverError("%r has %d variables: up to %d per equation" % (text, len(names), MAX_VARS))
        for v in names:
            if v not in order:
                order.append(v)
        sols = {}
        for v in names:
            sols[v] = solve_for(lhs, rhs, v)
        formulas.append({"text": text, "lhs": lhs, "rhs": rhs, "vars": names, "solutions": sols,
                         "residual": simplify(("sub", lhs, rhs))})
    meta = {}
    for v in order:
        m = (spec.get("vars") or {}).get(v, {})
        meta[v] = {"unit": _ascii(m.get("unit", "")), "desc": _ascii(m.get("desc", ""))}
    title = _ascii(spec.get("title") or "") or "Solver"
    plan = {"name": name, "title": title, "formulas": formulas, "order": order, "meta": meta,
            "degrees": bool(spec.get("degrees"))}
    plan["letters84"] = _letters_84(order)
    plan["names89"] = _names_89(order)
    return plan


def uses_trig(plan):
    def walk(n):
        if n[0] == "fn" and n[1] in ("sin", "cos", "tan", "asin", "acos", "atan"):
            return True
        return any(walk(c) for c in n[1:] if isinstance(c, tuple))
    return any(walk(f["lhs"]) or walk(f["rhs"]) for f in plan["formulas"])


def any_numeric(plan):
    return any(s[0] == "numeric" for f in plan["formulas"] for s in f["solutions"].values())


_ASCII_SUBS = {"Ω": "ohm", "Ω": "ohm", "µ": "u", "μ": "u", "°": "deg",
               "²": "^2", "³": "^3", "·": "*", "−": "-", "σ": "sigma",
               "τ": "tau", "θ": "theta", "ρ": "rho", "ε": "eps",
               "é": "e", "’": "'"}


def _ascii(s):
    s = "".join(_ASCII_SUBS.get(c, c) for c in str(s))
    return "".join(c for c in s if " " <= c <= "~")


def _letters_84(order):
    """Each variable -> one of the 84's letters A-Z (its first letter when free)"""
    free = [chr(c) for c in range(ord("A"), ord("Z") + 1)]
    out = {}
    for v in order:
        want = v[0].upper()
        if want in free:
            out[v] = want
            free.remove(want)
    for v in order:
        if v not in out:
            if not free:
                raise SolverError("too many variables for the TI-84 (26 letters)")
            out[v] = free.pop(0)
    out[None] = free[-1] if free else "θ"  # A spare letter for the guess
    return out


INTERNAL_89 = {"zf", "zt", "zb", "zk", "zm", "zg", "zx0", "zx1", "zx2", "zf0", "zf1", "zsg"}


def _names_89(order):
    """Each variable -> a name the 89 takes as a Local (it ignores case; up to 8 characters;
    not a command, a system variable, e or pi)"""
    import code_check as cc
    taken = set(INTERNAL_89) | {"e", "pi", "theta", "i"}
    reserved = cc.reserved_89()
    out = {}
    for k, v in enumerate(order):
        base = re.sub(r"[^a-z0-9_]", "", v.lower())[:8] or "v"
        cand, n = base, 1
        while cand in taken or cand in reserved or not re.match(r"^[a-z][a-z0-9_]{0,7}$", cand):
            n += 1
            cand = (base[:8 - len(str(n))] or "v") + str(n)
        taken.add(cand)
        out[v] = cand
    for k, v in enumerate(order):
        out[("s", v)] = "zs%d" % (k + 1)  # The dialog's text for each variable
    return out


def label(plan, v, width=None):
    """'R (ohm)'"""
    unit = plan["meta"][v]["unit"]
    s = "%s (%s)" % (v, unit) if unit else v
    return s[:width] if width else s


def solution_rows(plan):
    """For the preview: [(equation, variable, how, text, note)]"""
    rows = []
    for f in plan["formulas"]:
        for v in f["vars"]:
            how, expr, note = f["solutions"][v]
            rows.append((f["text"], v, how, "%s = %s" % (v, to_text(expr)) if expr else
                         "%s from %s = 0" % (v, to_text(f["residual"])), note))
    return rows


# ---------------------------------------------------------------------------
# TI-Nspire Python
# ---------------------------------------------------------------------------

def _py_str(s):
    return '"%s"' % _ascii(s).replace("\\", "/").replace('"', "'")


def generate_python(plan):
    deg = plan["degrees"]
    L = []
    L.append("# %s: equation solver made by CalcSuite" % plan["name"])
    L.append("# %s" % plan["title"])
    for f in plan["formulas"]:
        L.append("#   %s" % _ascii(f["text"]))
    if deg and uses_trig(plan):
        L.append("# Angles in degrees")
    L.append("import math")
    L.append("")
    L.append("TITLE = %s" % _py_str(plan["title"][:30]))
    L.append("UNITS = {")
    for v in plan["order"]:
        L.append("    %s: %s," % (_py_str(v), _py_str(plan["meta"][v]["unit"])))
    L.append("}")
    L.append("INFO = {")
    for v in plan["order"]:
        L.append("    %s: %s," % (_py_str(v), _py_str(plan["meta"][v]["desc"])))
    L.append("}")
    L.append("FORMULAS = [")
    for f in plan["formulas"]:
        L.append("    [%s, [%s]]," % (_py_str(_ascii(f["text"])[:26]),
                                     ", ".join(_py_str(v) for v in f["vars"])))
    L.append("]")
    L += ["", "", "def residual(k, v):", '    """Left side minus right side of equation k"""']
    for k, f in enumerate(plan["formulas"]):
        L.append("    if k == %d:" % k)
        L.append("        return %s" % to_text(f["residual"], "python", degrees=deg))
    L.append("    return 0.0")
    L += ["", "", "def direct(k, t, v):", '    """t from the others, or None: solve numerically"""']
    for k, f in enumerate(plan["formulas"]):
        L.append("    if k == %d:" % k)
        for v in f["vars"]:
            how, expr, note = f["solutions"][v]
            if expr is not None:
                L.append("        if t == %s:%s" % (_py_str(v), "  # " + note if note else ""))
                L.append("            return %s" % to_text(expr, "python", degrees=deg))
    L.append("    return None")
    L += ["", "",
          "def nsolve(k, t, v, g):",
          '    """Secant method from the guess g"""',
          "    x0 = g",
          "    x1 = g + 0.01 * max(1.0, abs(g))",
          "    v[t] = x0",
          "    f0 = residual(k, v)",
          "    for i in range(100):",
          "        v[t] = x1",
          "        f1 = residual(k, v)",
          "        if f1 == 0:",
          "            return x1",
          "        if f1 == f0:",
          "            break",
          "        x2 = x1 - f1 * (x1 - x0) / (f1 - f0)",
          "        x0 = x1",
          "        f0 = f1",
          "        x1 = x2",
          "        if abs(x1 - x0) <= 1e-12 * max(1.0, abs(x1)):",
          "            return x1",
          '    raise ValueError("no root found")',
          "", "",
          "def label(n):",
          "    if UNITS[n]:",
          '        return n + " (" + UNITS[n] + ")"',
          "    return n",
          "", "",
          "def ask(prompt, empty=None):",
          "    while True:",
          "        s = input(prompt).strip()",
          '        if s == "" and empty is not None:',
          "            return empty",
          "        try:",
          "            return float(s)",
          "        except ValueError:",
          '            print("Type a number, e.g. 4.7e3")',
          "", "",
          "def pick(title, items, last):",
          "    print(title)",
          "    for i in range(len(items)):",
          '        print(str(i + 1) + ": " + items[i][:26])',
          '    print("0: " + last)',
          "    while True:",
          '        s = input("Number? ").strip()',
          "        try:",
          "            n = int(s)",
          "        except ValueError:",
          "            n = -1",
          "        if n >= 0 and n <= len(items):",
          "            return n",
          '        print("Type 0 to " + str(len(items)))',
          "", "",
          "def show(t, x):",
          '    s = "%.6g" % x',
          '    line = t + " = " + s + " " + UNITS[t]',
          "    if len(line) <= 30:",
          "        print(line)",
          "    else:",
          '        print(t + " =")',
          '        print("  " + s + " " + UNITS[t])',
          "", "",
          "def item(n):",
          "    s = label(n)",
          "    if INFO[n]:",
          '        s = s + " " + INFO[n]',
          "    return s",
          "", "",
          "def main():",
          "    print(TITLE)",
          "    one = len(FORMULAS) == 1",
          "    while True:",
          "        k = 0",
          "        if not one:",
          '            n = pick("Equation:", [f[0] for f in FORMULAS], "Quit")',
          "            if n == 0:",
          "                break",
          "            k = n - 1",
          "        names = FORMULAS[k][1]",
          '        last = "Quit" if one else "Back"',
          '        n = pick("Solve for:", [item(t) for t in names], last)',
          "        if n == 0:",
          "            if one:",
          "                break",
          "            continue",
          "        t = names[n - 1]",
          "        v = {}",
          "        for name in names:",
          "            if name != t:",
          '                v[name] = ask(label(name)[:24] + "? ")',
          "        try:",
          "            x = direct(k, t, v)",
          "            if x is None:",
          '                g = ask("Guess for " + t + " (Enter: 1)? ", 1.0)',
          "                x = nsolve(k, t, v, g)",
          "        except (ZeroDivisionError, ValueError, OverflowError):",
          "            x = None",
          "        if x is None or isinstance(x, complex) or x != x:",
          '            print("No answer for these values")',
          "        else:",
          "            show(t, x)",
          "", "",
          "main()"]
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------------------
# TI-84 Plus CE TI-Basic
# ---------------------------------------------------------------------------

def _str84(s, width):
    """Text that is safe inside an 84 string: no quote, no store arrow"""
    s = _ascii(s).replace('"', "'").replace("->", "-")
    s = re.sub(r"[^A-Za-z0-9 +\-*/^=().,'?%:]", "", s)
    return s[:width].rstrip()


def generate_ti84(plan):
    lt = plan["letters84"]
    many = len(plan["formulas"]) > 1
    L = ['"%s: SOLVER BY CALCSUITE' % plan["name"].upper()]
    L.append('"%s' % _str84(plan["title"].upper(), 24))
    if uses_trig(plan):
        L.append("Degree" if plan["degrees"] else "Radian")
    if many:
        L.append("Lbl M0")
        items = []
        for k, f in enumerate(plan["formulas"]):
            items.append('"%s",Z%d' % (_str84(f["text"], 24), k + 1))
        L.append('Menu("%s",%s,"QUIT",Q0)' % (_str84(plan["title"], 26), ",".join(items)))
    for k, f in enumerate(plan["formulas"]):
        L.append("Lbl Z%d" % (k + 1))
        items = ['"%s",%s%d' % (_str84(label(plan, v), 24), chr(65 + k), j + 1)
                 for j, v in enumerate(f["vars"])]
        back = '"BACK",M0' if many else '"QUIT",Q0'
        L.append('Menu("%s",%s,%s)' % (_str84("SOLVE FOR", 26), ",".join(items), back))
        for j, v in enumerate(f["vars"]):
            how, expr, note = f["solutions"][v]
            L.append("Lbl %s%d" % (chr(65 + k), j + 1))
            L.append("ClrHome")
            if note and how != "numeric":
                L.append('"%s' % _str84(note.upper(), 24))
            for o in f["vars"]:
                if o != v:
                    L.append('Input "%s? ",%s' % (_str84(label(plan, o), 18), lt[o]))
            if expr is not None:
                L.append("%s->%s" % (to_text(expr, "ti84", lt), lt[v]))
            else:
                g = lt[None]
                L.append('Input "GUESS %s? ",%s' % (_str84(v, 14), g))
                L.append("solve(%s,%s,%s)->%s" % (to_text(f["residual"], "ti84", lt), lt[v], g, lt[v]))
            L.append("ClrHome")
            L.append('Disp "%s =",%s' % (_str84(label(plan, v), 22), lt[v]))
            L.append("Pause")
            L.append("Goto Z%d" % (k + 1))
    L.append("Lbl Q0")
    L.append("ClrHome")
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------------------
# TI-89 Titanium TI-Basic
# ---------------------------------------------------------------------------

def _str89(s, width):
    s = _ascii(s).replace('"', "'").replace("->", "-")
    return s[:width].rstrip()


def generate_ti89(plan):
    nm = plan["names89"]
    many = len(plan["formulas"]) > 1
    trig = uses_trig(plan)
    L = ["%s()" % plan["name"], "Prgm",
         "© %s: equation solver made by CalcSuite" % plan["name"],
         "© %s" % _str89(plan["title"], 60)]
    locs = ["zf", "zt", "zb", "zk", "zg", "zx0", "zx1", "zx2", "zf0", "zf1", "zsg"]
    if trig:
        locs.append("zm")
    locs += [nm[v] for v in plan["order"]] + [nm[("s", v)] for v in plan["order"]]
    L.append("Local " + ",".join(locs))
    for v in plan["order"]:
        L.append('"" -> %s' % nm[("s", v)])
    L.append('"1" -> zsg')
    if trig:
        L.append('getMode("Angle") -> zm')
        L.append('setMode("Angle","%s")' % ("Degree" if plan["degrees"] else "Radian"))
    L.append("1 -> zf")
    L.append("Loop")
    ind = "  "
    if many:
        L.append(ind + "PopUp {%s,\"Quit\"},zf" % ",".join(
            '"%s"' % _str89(f["text"], 24) for f in plan["formulas"]))
        L.append(ind + "If zf=0 or zf=%d" % (len(plan["formulas"]) + 1))
        L.append(ind + "  Exit")
    for k, f in enumerate(plan["formulas"]):
        i1 = ind
        if many:
            L.append(ind + "If zf=%d Then" % (k + 1))
            i1 = ind + "  "
        n = len(f["vars"])
        L.append(i1 + "1 -> zt")
        L.append(i1 + "PopUp {%s,\"%s\"},zt" % (
            ",".join('"%s"' % _str89(label(plan, v), 24) for v in f["vars"]),
            "Back" if many else "Quit"))
        if not many:
            L.append(i1 + "If zt=0 or zt=%d" % (n + 1))
            L.append(i1 + "  Exit")
        for j, v in enumerate(f["vars"]):
            how, expr, note = f["solutions"][v]
            others = [o for o in f["vars"] if o != v]
            L.append(i1 + "If zt=%d Then" % (j + 1))
            i2 = i1 + "  "
            reqs = [(_str89(label(plan, o), 20), nm[("s", o)]) for o in others]
            if expr is None:
                reqs.append((_str89("Guess for " + v, 20), "zsg"))
            chunks = [reqs[i:i + 4] for i in range(0, len(reqs), 4)]
            L.append(i2 + "1 -> zb")
            for c, chunk in enumerate(chunks):
                if c:
                    L.append(i2 + "If zb=1 Then")
                    i3 = i2 + "  "
                else:
                    i3 = i2
                L.append(i3 + "Dialog")
                L.append(i3 + '  Title "Find %s"' % _str89(v, 14))
                for prompt, var in chunk:
                    L.append(i3 + '  Request "%s",%s' % (prompt, var))
                L.append(i3 + "EndDlog")
                L.append(i3 + "If ok=0")
                L.append(i3 + "  0 -> zb")
                if c:
                    L.append(i2 + "EndIf")
            L.append(i2 + "If zb=1 Then")
            i3 = i2 + "  "
            L.append(i3 + "0 -> zg")
            L.append(i3 + "Try")
            for o in others:
                L.append(i3 + "  approx(expr(%s)) -> %s" % (nm[("s", o)], nm[o]))
            if expr is None:
                L.append(i3 + "  approx(expr(zsg)) -> zx0")
            L.append(i3 + "Else")
            L.append(i3 + "  ClrErr")
            L.append(i3 + "  1 -> zg")
            L.append(i3 + "EndTry")
            for o in others:
                L.append(i3 + 'If getType(%s)!="NUM"' % nm[o])
                L.append(i3 + "  1 -> zg")
            if expr is None:
                L.append(i3 + 'If getType(zx0)!="NUM"')
                L.append(i3 + "  1 -> zg")
            L.append(i3 + "If zg=1 Then")
            L.append(i3 + '  Text "Type a number in each box"')
            L.append(i3 + "Else")
            i4 = i3 + "  "
            t = nm[v]
            L.append(i4 + "Try")
            if expr is not None:
                L.append(i4 + "  approx(%s) -> %s" % (to_text(expr, "ti89", nm), t))
            else:
                res = to_text(f["residual"], "ti89", nm)
                i5 = i4 + "  "
                L += [i5 + "2 -> zg",
                      i5 + "zx0+0.01*max(1,abs(zx0)) -> zx1",
                      i5 + "zx0 -> %s" % t,
                      i5 + "approx(%s) -> zf0" % res,
                      i5 + "For zk,1,100",
                      i5 + "  zx1 -> %s" % t,
                      i5 + "  approx(%s) -> zf1" % res,
                      i5 + "  If zf1=0 Then",
                      i5 + "    0 -> zg",
                      i5 + "    Exit",
                      i5 + "  EndIf",
                      i5 + "  If zf1=zf0",
                      i5 + "    Exit",
                      i5 + "  zx1-zf1*(zx1-zx0)/(zf1-zf0) -> zx2",
                      i5 + "  zx1 -> zx0",
                      i5 + "  zf1 -> zf0",
                      i5 + "  zx2 -> zx1",
                      i5 + "  If abs(zx1-zx0)<=1E-12*max(1,abs(zx1)) Then",
                      i5 + "    0 -> zg",
                      i5 + "    Exit",
                      i5 + "  EndIf",
                      i5 + "EndFor",
                      i5 + "zx1 -> %s" % t]
            L.append(i4 + "Else")
            L.append(i4 + "  ClrErr")
            L.append(i4 + "  2 -> zg")
            L.append(i4 + "EndTry")
            L.append(i4 + 'If zg=0 and getType(%s)!="NUM"' % t)
            L.append(i4 + "  2 -> zg")
            L.append(i4 + "If zg=2 Then")
            L.append(i4 + '  Text "No answer for these values"')
            L.append(i4 + "Else")
            L.append(i4 + "  ClrIO")
            L.append(i4 + '  Disp "%s =",%s' % (_str89(label(plan, v), 24), t))
            if note:
                L.append(i4 + '  Disp "(%s)"' % _str89(note, 24))
            L.append(i4 + "  Pause")
            L.append(i4 + "EndIf")
            L.append(i3 + "EndIf")
            L.append(i2 + "EndIf")
            L.append(i1 + "EndIf")
        if many:
            L.append(ind + "EndIf")
    L.append("EndLoop")
    if trig:
        L.append('setMode("Angle",zm)')
    L.append("DispHome")
    L.append("EndPrgm")
    return "\n".join(L) + "\n"


GENERATORS = {"python": generate_python, "ti84": generate_ti84, "ti89": generate_ti89}


def generate(lang, plan):
    return GENERATORS[lang](plan)


def program_name(lang, plan):
    return plan["name"].upper() if lang == "ti84" else plan["name"]


def check_all(plan):
    """Every calculator's program and what the editor's checkers say about it:
    {lang: {"text", "name", "problems", "errors", "warnings", "build_error"}}. build_error is
    set when the 84's tokenizer or the 89's converter refuses it."""
    import calc_files as cf
    import code_check as cc
    out = {}
    for lang in LANGS:
        text = generate(lang, plan)
        name = program_name(lang, plan)
        probs = cc.check(lang, text, name=name)
        build_error = ""
        try:
            if lang == "ti84":
                cf.program_8xp(text, name)
            elif lang == "ti89":
                cf.program_89p(text, name)
            else:
                compile(text, name + ".py", "exec")
        except (ValueError, SyntaxError) as e:
            build_error = str(e)
        c = cc.counts(probs)
        out[lang] = {"text": text, "name": name, "problems": probs, "errors": c["error"],
                     "warnings": c["warning"], "build_error": build_error}
    return out


# ---------------------------------------------------------------------------
# Ready-made engineering formula sets
# ---------------------------------------------------------------------------

TEMPLATES = [
    {"key": "ohm", "label": "Ohm's law and power", "name": "ohmlaw", "title": "Ohm's law and power",
     "equations": ["V = I*R", "P = V*I", "P = V^2/R", "P = I^2*R"],
     "vars": {"V": {"unit": "V", "desc": "voltage"}, "I": {"unit": "A", "desc": "current"},
              "R": {"unit": "ohm", "desc": "resistance"}, "P": {"unit": "W", "desc": "power"}}},
    {"key": "vdiv", "label": "Voltage divider", "name": "vdivider", "title": "Voltage divider",
     "equations": ["Vout = Vin*R2/(R1+R2)"],
     "vars": {"Vout": {"unit": "V", "desc": "output"}, "Vin": {"unit": "V", "desc": "input"},
              "R1": {"unit": "ohm", "desc": "top resistor"},
              "R2": {"unit": "ohm", "desc": "bottom resistor"}}},
    {"key": "rc", "label": "RC time constant and charging", "name": "rctime",
     "title": "RC time constant",
     "equations": ["tau = R*C", "Vc = Vs*(1 - exp(-t/tau))"],
     "vars": {"tau": {"unit": "s", "desc": "time constant"}, "R": {"unit": "ohm", "desc": "resistance"},
              "C": {"unit": "F", "desc": "capacitance"}, "Vc": {"unit": "V", "desc": "capacitor"},
              "Vs": {"unit": "V", "desc": "supply"}, "t": {"unit": "s", "desc": "time"}}},
    {"key": "gas", "label": "Ideal gas law", "name": "idealgas", "title": "Ideal gas law",
     "equations": ["P*V = n*8.314462618*T"],
     "vars": {"P": {"unit": "Pa", "desc": "pressure"}, "V": {"unit": "m^3", "desc": "volume"},
              "n": {"unit": "mol", "desc": "amount"}, "T": {"unit": "K", "desc": "temperature"}}},
    {"key": "kin", "label": "Kinematics (constant acceleration)", "name": "kinemat",
     "title": "Kinematics",
     "equations": ["v = v0 + a*t", "x = v0*t + a*t^2/2", "v^2 = v0^2 + 2*a*x"],
     "vars": {"v": {"unit": "m/s", "desc": "final speed"}, "v0": {"unit": "m/s", "desc": "start speed"},
              "a": {"unit": "m/s^2", "desc": "acceleration"}, "t": {"unit": "s", "desc": "time"},
              "x": {"unit": "m", "desc": "distance"}}},
    {"key": "beam", "label": "Beam bending stress", "name": "beamstr", "title": "Bending stress",
     "equations": ["sigma = M*y/I"],
     "vars": {"sigma": {"unit": "Pa", "desc": "stress"}, "M": {"unit": "N*m", "desc": "moment"},
              "y": {"unit": "m", "desc": "from neutral axis"},
              "I": {"unit": "m^4", "desc": "second moment"}}},
    {"key": "spring", "label": "Spring and oscillation", "name": "spring", "title": "Spring",
     "equations": ["F = k*x", "f = sqrt(k/m)/(2*pi)", "E = k*x^2/2"],
     "vars": {"F": {"unit": "N", "desc": "force"}, "k": {"unit": "N/m", "desc": "stiffness"},
              "x": {"unit": "m", "desc": "stretch"}, "f": {"unit": "Hz", "desc": "frequency"},
              "m": {"unit": "kg", "desc": "mass"}, "E": {"unit": "J", "desc": "stored energy"}}},
    {"key": "proj", "label": "Projectile range (degrees)", "name": "projrng", "title": "Projectile range",
     "equations": ["R = v^2*sin(2*theta)/9.81"], "degrees": True,
     "vars": {"R": {"unit": "m", "desc": "range"}, "v": {"unit": "m/s", "desc": "launch speed"},
              "theta": {"unit": "deg", "desc": "launch angle"}}},
]


def template_spec(key, name=None):
    t = next(t for t in TEMPLATES if t["key"] == key)
    return {"name": name or t["name"], "title": t["title"], "equations": list(t["equations"]),
            "vars": {k: dict(v) for k, v in t["vars"].items()}, "degrees": t.get("degrees", False)}
