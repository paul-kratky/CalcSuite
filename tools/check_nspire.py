"""Check a Python file for the TI-Nspire CX II / CX II CAS (TI-Python, MicroPython based).

Usage:
    python tools/check_nspire.py programs/my_program.py [more files or folders]
    python tools/check_nspire.py --strict programs/          (warnings fail too)
    python tools/check_nspire.py --allow mylib programs/x.py (allow your own PyLib module)

Exit code 0 = no errors (warnings may remain), 1 = errors found (or warnings with --strict).

ERRORS are things the calculator rejects or that are very likely to fail there.
WARNINGS are things that may work but are not in TI's documentation; fix them unless
you have tested them on the handheld (see programs/probe.py).

Based on TI's "TI-Nspire Python Programming Guidebook" and the online eGuide menu map
(see README.md, section "Sources").
"""

import ast
import io
import os
import sys
import tokenize
import unicodedata

# ---------------------------------------------------------------------------
# What the calculator has (TI documentation, OS 5.2 and later).
# Names per module: the documented menu items. Anything else is a warning.
# ---------------------------------------------------------------------------
DOCUMENTED = {
    "math": {
        "fabs", "sqrt", "exp", "pow", "log", "fmod", "ceil", "floor", "trunc", "frexp",
        "e", "pi", "radians", "degrees", "sin", "cos", "tan", "asin", "acos", "atan",
        "atan2",
    },
    "random": {"random", "uniform", "randint", "choice", "randrange", "seed"},
    "cmath": {
        "rect", "polar", "phase", "exp", "cos", "sin", "log", "log10", "sqrt", "e", "pi",
    },
    "time": {"sleep", "clock", "localtime", "ticks_cpu", "ticks_ms", "ticks_diff"},
    "ti_system": {
        "recall_value", "store_value", "recall_list", "store_list", "eval_function",
        "get_platform", "get_key", "get_mouse", "clear_history", "get_time_ms",
    },
    "ti_draw": {
        "draw_line", "draw_rect", "fill_rect", "draw_circle", "fill_circle", "draw_text",
        "draw_arc", "fill_arc", "draw_poly", "fill_poly", "plot_xy", "clear", "clear_rect",
        "set_color", "set_pen", "set_window", "get_screen_dim", "use_buffer",
        "paint_buffer",
    },
    "ti_plotlib": {
        "cls", "grid", "window", "auto_window", "axes", "labels", "title", "show_plot",
        "use_buffer", "color", "scatter", "plot", "line", "lin_reg", "pen", "text_at",
        "xmin", "xmax", "ymin", "ymax", "m", "a", "b",
    },
    "ti_image": {"new_image", "load_image", "copy_image"},
    # Hardware modules: need a TI-Innovator Hub / Rover connected. Names not checked.
    "ti_hub": None,
    "ti_rover": None,
}

# Present in MicroPython builds and reported by the community, but not in TI's docs.
UNDOCUMENTED_OK = {"sys", "gc", "array", "collections", "micropython", "builtins"}

# Add-ons TI distributes as separate downloads that you install into PyLib first.
ADDON_MODULES = {"turtle": "TI's Turtle module (download from education.ti.com and "
                           "install it into PyLib first)"}

# Popular PC modules that do not exist on the calculator, with a hint.
PC_ONLY_HINTS = {
    "numpy": "write the loops yourself with lists",
    "sympy": "use the calculator's CAS outside Python, or pass results in with "
             "ti_system.recall_value / eval_function",
    "matplotlib": "use ti_plotlib (import ti_plotlib as plt)",
    "turtle": "use ti_draw, or install TI's own Turtle module into PyLib",
    "tkinter": "use ti_draw",
    "os": "there is no file system access",
    "pathlib": "there is no file system access",
    "fractions": "keep numerator and denominator as two ints",
    "decimal": "use float or int",
    "statistics": "compute mean/median yourself with sum() and sorted()",
    "itertools": "write the loop yourself",
    "functools": "write the loop yourself",
    "typing": "remove type hints",
    "dataclasses": "use a plain class",
    "string": "use str methods",
    "re": "use str.split / str.find",
    "json": "store numbers with ti_system.store_list",
    "datetime": "use time.localtime()",
}

# String methods CPython has but MicroPython usually lacks.
STR_METHODS_MISSING = {
    "ljust": "pad manually: s + ' ' * (n - len(s))",
    "rjust": "pad manually: ' ' * (n - len(s)) + s",
    "zfill": "pad manually: '0' * (n - len(s)) + s",
    "title": "capitalize words yourself",
    "swapcase": "convert characters yourself",
    "casefold": "use .lower()",
    "expandtabs": "replace '\\t' yourself",
    "removeprefix": "use slicing: s[len(p):] if s.startswith(p) else s",
    "removesuffix": "use slicing: s[:-len(p)] if s.endswith(p) else s",
    "isidentifier": "check the characters yourself",
    "isprintable": "check the characters yourself",
    "format_map": "use .format(**d)",
    "partition": "use .split(sep, 1)",
    "rpartition": "use .rsplit(sep, 1)",
}

BUILTINS_ERRORS = {
    "open": "the calculator's Python has no file I/O; print results or use "
            "ti_system.store_value / store_list",
    "breakpoint": "there is no debugger; use print()",
    "__import__": "use a normal import statement",
}
BUILTINS_WARN = {
    "exit": "may not exist; end the program by letting it finish",
    "quit": "may not exist; end the program by letting it finish",
    "exec": "not in TI's menus; avoid it",
    "compile": "not in TI's menus; avoid it",
    "memoryview": "not in TI's menus; avoid it",
    "help": "fine in the Shell, but don't call it from a program",
}

SIZE_WARN = 20 * 1024   # bytes: big for a handheld editor, getting slow to scroll
SIZE_ERROR = 60 * 1024  # bytes: community reports ~70 KB as the editor's limit
BIG_NUMBER = 20000      # list sizes / loop counts that eat the ~2 MB heap or take ages


class Finding:
    def __init__(self, level, line, message, fix):
        self.level = level
        self.line = line
        self.message = message
        self.fix = fix


class Checker(ast.NodeVisitor):
    def __init__(self, allowed_extra):
        self.findings = []
        self.allowed_extra = set(allowed_extra)
        self.module_aliases = {}   # local name -> module   (import math as m)
        self.func_stack = []
        self.recursive = set()

    def add(self, level, node_or_line, message, fix):
        line = node_or_line if isinstance(node_or_line, int) else getattr(node_or_line, "lineno", 0)
        self.findings.append(Finding(level, line, message, fix))

    # ---------------- imports ----------------
    def check_module(self, node, name):
        top = name.split(".")[0]
        if top in DOCUMENTED or top in self.allowed_extra:
            if "." in name:
                self.add("ERROR", node, "import of submodule '%s'" % name,
                         "import '%s' itself" % top)
            return True
        if top in UNDOCUMENTED_OK:
            self.add("WARN", node, "module '%s' exists in MicroPython but is not in TI's "
                     "documentation" % top,
                     "test it on the handheld first, or avoid it")
            return True
        if top in ADDON_MODULES:
            self.add("WARN", node, "module '%s' is not built in: %s" % (top, ADDON_MODULES[top]),
                     "if you have not installed it, use ti_draw instead")
            return True
        if top == "__future__":
            self.add("ERROR", node, "'from __future__ import ...' is not supported",
                     "delete the line")
            return False
        hint = PC_ONLY_HINTS.get(top, "use only math, cmath, random, time, ti_system, "
                                      "ti_draw, ti_plotlib, ti_image")
        self.add("ERROR", node, "module '%s' does not exist on the TI-Nspire" % top, hint)
        return False

    def visit_Import(self, node):
        for alias in node.names:
            if self.check_module(node, alias.name):
                self.module_aliases[alias.asname or alias.name.split(".")[0]] = \
                    alias.name.split(".")[0]
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if node.level:
            self.add("ERROR", node, "relative import", "use 'from module import ...'")
            return
        mod = node.module or ""
        if not self.check_module(node, mod):
            return
        names = DOCUMENTED.get(mod)
        for alias in node.names:
            if alias.name == "*" or names is None:
                continue
            if alias.name not in names:
                self.add("WARN", node, "'%s' is not in TI's documented %s menu" % (alias.name, mod),
                         "check the spelling, or use a documented function")

    def visit_Attribute(self, node):
        if isinstance(node.value, ast.Name) and node.value.id in self.module_aliases:
            mod = self.module_aliases[node.value.id]
            names = DOCUMENTED.get(mod)
            if names is not None and node.attr not in names:
                self.add("WARN", node, "'%s.%s' is not in TI's documented %s menu"
                         % (node.value.id, node.attr, mod),
                         "check the spelling, or use a documented function")
        elif node.attr in STR_METHODS_MISSING and not (
                isinstance(node.value, ast.Name) and node.value.id in self.module_aliases):
            self.add("WARN", node, "'.%s()' is a CPython string method that MicroPython "
                     "usually lacks" % node.attr, STR_METHODS_MISSING[node.attr])
        self.generic_visit(node)

    # ---------------- syntax the calculator lacks ----------------
    def visit_JoinedStr(self, node):
        self.add("ERROR", node, "f-string (f\"...\") - TI does not document f-strings and "
                 "MicroPython only added them after TI's Python was released",
                 "use \"x = {}\".format(x) or print(\"x =\", x)")
        # do not descend: nested FormattedValue nodes would repeat the finding

    def visit_NamedExpr(self, node):
        self.add("ERROR", node, "walrus operator ':=' is not guaranteed on the calculator",
                 "assign on its own line first")
        self.generic_visit(node)

    def visit_AnnAssign(self, node):
        self.add("ERROR", node, "type annotation on a variable", "write 'x = value' without ': type'")
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node):
        self.add("ERROR", node, "async def - 'async'/'await' are not TI-Python keywords",
                 "use a normal def and a loop")
        self.generic_visit(node)

    def visit_Await(self, node):
        self.add("ERROR", node, "await is not supported", "call the function normally")
        self.generic_visit(node)

    def visit_AsyncFor(self, node):
        self.add("ERROR", node, "async for is not supported", "use a normal for loop")
        self.generic_visit(node)

    def visit_AsyncWith(self, node):
        self.add("ERROR", node, "async with is not supported", "remove it")
        self.generic_visit(node)

    def _check_args(self, node):
        args = node.args
        if getattr(args, "posonlyargs", None):
            self.add("ERROR", node, "positional-only parameter marker '/' (Python 3.8)",
                     "remove the '/' from the parameter list")
        all_args = list(getattr(args, "posonlyargs", [])) + list(args.args) + \
            list(args.kwonlyargs)
        if args.vararg:
            all_args.append(args.vararg)
        if args.kwarg:
            all_args.append(args.kwarg)
        if any(a.annotation is not None for a in all_args) or getattr(node, "returns", None):
            self.add("ERROR", node, "type hints in function '%s'" % node.name,
                     "remove ': type' and '-> type'")

    def visit_FunctionDef(self, node):
        self._check_args(node)
        self.func_stack.append(node.name)
        self.generic_visit(node)
        self.func_stack.pop()

    def visit_Call(self, node):
        f = node.func
        if isinstance(f, ast.Name):
            if f.id in BUILTINS_ERRORS:
                self.add("ERROR", node, "%s() is not available" % f.id, BUILTINS_ERRORS[f.id])
            elif f.id in BUILTINS_WARN:
                self.add("WARN", node, "%s() " % f.id + BUILTINS_WARN[f.id],
                         "remove the call")
            if self.func_stack and f.id == self.func_stack[-1] and f.id not in self.recursive:
                self.recursive.add(f.id)
                self.add("WARN", node, "function '%s' calls itself (recursion)" % f.id,
                         "the calculator's stack is small: use a loop, or keep the depth "
                         "well under 50")
            if f.id == "range":
                for a in node.args:
                    if isinstance(a, ast.Constant) and isinstance(a.value, int) and \
                            abs(a.value) > BIG_NUMBER:
                        self.add("WARN", node, "range() with %d steps" % a.value,
                                 "the handheld is slow: keep loops small (a few thousand)")
            if f.id == "print":
                for kw in node.keywords:
                    if kw.arg == "flush":
                        self.add("WARN", node, "print(flush=...) is not in MicroPython",
                                 "remove flush=")
        self.generic_visit(node)

    def visit_BinOp(self, node):
        # [0] * 100000 style big lists
        if isinstance(node.op, ast.Mult):
            for side, other in ((node.left, node.right), (node.right, node.left)):
                is_seq = isinstance(side, ast.List) or (
                    isinstance(side, ast.Constant) and isinstance(side.value, str))
                if is_seq and isinstance(other, ast.Constant) and \
                        isinstance(other.value, int) and not isinstance(other.value, bool) and \
                        other.value > BIG_NUMBER:
                    self.add("WARN", node, "list/string of %d items" % other.value,
                             "the heap is about 2 MB: keep lists to a few thousand items")
        self.generic_visit(node)

    def visit_If(self, node):
        t = node.test
        if isinstance(t, ast.Compare) and isinstance(t.left, ast.Name) and \
                t.left.id == "__name__":
            self.add("WARN", node, "'if __name__ == \"__main__\":' guard",
                     "put the main code at top level so Run always runs it")
        self.generic_visit(node)

    def generic_visit(self, node):
        name = type(node).__name__
        if name == "Match":
            self.add("ERROR", node, "match/case statement (Python 3.10)",
                     "use if/elif/else")
            # still look inside
        elif name == "TryStar":
            self.add("ERROR", node, "except* (Python 3.11)", "use a plain except")
        elif name == "TypeAlias":
            self.add("ERROR", node, "'type X = ...' statement (Python 3.12)", "remove it")
        super().generic_visit(node)


def check_text_level(source_bytes, findings):
    """Checks that need the raw text: ASCII, tabs, size, numeric underscores."""
    size = len(source_bytes)
    if size > SIZE_ERROR:
        findings.append(Finding("ERROR", 0, "file is %d KB" % (size // 1024),
                                "split it: the editor holds roughly 60-70 KB per program; "
                                "move helpers into a PyLib module"))
    elif size > SIZE_WARN:
        findings.append(Finding("WARN", 0, "file is %d KB" % (size // 1024),
                                "smaller is better on a handheld (aim for under 20 KB)"))

    text = source_bytes.decode("utf-8", errors="replace")
    if text.startswith("\ufeff"):
        findings.append(Finding("ERROR", 1, "file starts with a UTF-8 byte-order mark",
                                "save the file as plain ASCII / UTF-8 without BOM"))
    tab_lines = []
    for n, line in enumerate(text.splitlines(), 1):
        bad = [c for c in line if ord(c) > 126 or (ord(c) < 32 and c not in "\t")]
        bad = [c for c in bad if c != "\ufeff"]
        if bad:
            shown = ", ".join("U+%04X %s" % (ord(c), unicodedata.name(c, "?"))
                              for c in sorted(set(bad))[:4])
            findings.append(Finding("ERROR", n, "non-ASCII character(s): %s" % shown,
                                    "replace curly quotes, long dashes, superscripts and math "
                                    "symbols with plain ASCII: \" ' - **2 <= pi sqrt()"))
        if line[:len(line) - len(line.lstrip())].find("\t") >= 0:
            tab_lines.append(n)
    if tab_lines:
        findings.append(Finding("WARN", tab_lines[0], "tab indentation on %d line(s)"
                                % len(tab_lines),
                                "indent with 4 spaces; tabs can break when pasted into "
                                "the TI editor"))
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.NUMBER and "_" in tok.string:
                findings.append(Finding("WARN", tok.start[0],
                                        "underscore in number '%s'" % tok.string,
                                        "write the number without underscores"))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass
    return text


def check_file(path, allowed_extra):
    with open(path, "rb") as f:
        raw = f.read()
    findings = []
    text = check_text_level(raw, findings)
    try:
        tree = ast.parse(text.lstrip("\ufeff"), filename=path)
    except SyntaxError as e:
        findings.append(Finding("ERROR", e.lineno or 0, "syntax error: %s" % e.msg,
                                "fix the syntax (the TI editor's 'Check Syntax & Save' "
                                "would stop here too)"))
        return findings
    c = Checker(allowed_extra)
    c.visit(tree)
    findings.extend(c.findings)
    findings.sort(key=lambda f: (f.line, f.level))
    return findings


def collect(paths):
    out = []
    for p in paths:
        if os.path.isdir(p):
            for root, _dirs, files in os.walk(p):
                out.extend(os.path.join(root, f) for f in sorted(files) if f.endswith(".py"))
        else:
            out.append(p)
    return out


def main(argv):
    try:
        sys.stdout.reconfigure(errors="backslashreplace")
    except (AttributeError, ValueError):
        pass
    strict = False
    allowed = []
    paths = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--strict":
            strict = True
        elif a == "--allow" and i + 1 < len(argv):
            allowed.extend(x.strip() for x in argv[i + 1].split(",") if x.strip())
            i += 1
        elif a in ("-h", "--help"):
            print(__doc__)
            return 0
        else:
            paths.append(a)
        i += 1
    files = collect(paths)
    if not files:
        print("usage: python tools/check_nspire.py [--strict] [--allow mod1,mod2] FILE_OR_DIR...")
        return 2

    failed = False
    for path in files:
        if not os.path.isfile(path):
            print("%s: not found" % path)
            failed = True
            continue
        findings = check_file(path, allowed)
        errors = [f for f in findings if f.level == "ERROR"]
        warns = [f for f in findings if f.level == "WARN"]
        status = "FAIL" if errors or (strict and warns) else "OK"
        print("%s: %s (%d error(s), %d warning(s), %d bytes)"
              % (path, status, len(errors), len(warns), os.path.getsize(path)))
        for f in findings:
            where = "line %d" % f.line if f.line else "file"
            print("  %-5s %s: %s" % (f.level, where, f.message))
            print("        fix: %s" % f.fix)
        if status == "FAIL":
            failed = True
    if failed:
        print("\nNot ready for the calculator. Fix the ERRORs above"
              + (" and the warnings (--strict)." if strict else "."))
        return 1
    print("\nReady for the calculator.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
