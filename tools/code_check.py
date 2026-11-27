# SPDX-License-Identifier: MIT
"""Checks for the program editor (tools/editor.py): TI-84 Plus CE TI-Basic, TI-89 Titanium
TI-Basic and TI-Nspire Python. Pure: no window, no calculator, no USB.

    import code_check as cc
    for p in cc.check("ti84", text, name="QUAD"):
        print(p["line"], p["col"], p["severity"], p["message"], p["fix"])

A problem is {line (1-based), col, end_col (0-based, end exclusive, on that line), severity
("error" | "warning" | "info"), message, fix}. Errors are what the calculator (or CalcSuite's
own converter) rejects; warnings are very likely mistakes; info is worth knowing.

Also here, so the editor stays thin and its logic can be tested without Tk:
highlight() (spans to colour), completions() (the autocomplete list), signature_at() (the
current command's syntax and argument), hover_at() (a command's card), block_depths() (the
display-only indent), ai_instructions() (a prompt for chat AIs) and problems_text().

Languages: "ti84", "ti89", "python" ("nspire" is the same as "python").
"""

import ast
import builtins
import io
import keyword
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import calc_files as cf  # noqa: E402
import check_nspire  # noqa: E402
import reference  # noqa: E402

LANGS = ("ti84", "ti89", "python")
TITLES = {"ti84": "TI-84 Plus CE TI-Basic", "ti89": "TI-89 Titanium TI-Basic",
          "python": "TI-Nspire CX II Python"}
EXTS = {"ti84": ".txt", "ti89": ".txt", "python": ".py"}
COMMENT = {"ti84": None, "ti89": "\u00a9", "python": "#"}  # © on the 89
MAX_BYTES = 65000      # calc_files' limit for one program
LONG_LINE = 260        # Characters: past this the calculator's editor is hard to read
COPYRIGHT = "\u00a9"


def lang_of(language):
    lang = {"nspire": "python", "py": "python", "84": "ti84", "89": "ti89"}.get(language, language)
    if lang not in LANGS:
        raise ValueError("unknown language %r" % language)
    return lang


def _p(line, col, end_col, severity, message, fix=""):
    return {"line": line, "col": max(0, col), "end_col": max(col + 1, end_col),
            "severity": severity, "message": message, "fix": fix or ""}


_ORDER = {"error": 0, "warning": 1, "info": 2}


def _sorted(problems):
    seen, out = set(), []
    for p in sorted(problems, key=lambda p: (p["line"], p["col"], _ORDER[p["severity"]])):
        k = (p["line"], p["col"], p["message"])
        if k not in seen:
            seen.add(k)
            out.append(p)
    return out


def check(language, text, name=None):
    """Every problem in a program's text, in line order. `name` is the program's name on the
    calculator when it is known (the 84's file name; the 89's comes from its first line)."""
    lang = lang_of(language)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if lang == "ti84":
        return _sorted(_check_84(text, name))
    if lang == "ti89":
        return _sorted(_check_89(text, name))
    return _sorted(_check_py(text, name))


def counts(problems):
    out = {"error": 0, "warning": 0, "info": 0}
    for p in problems:
        out[p["severity"]] += 1
    return out


def problems_text(problems, language=None, name=None):
    """The problem list as plain text with line numbers (for pasting into a chat AI)"""
    head = "CalcSuite's checker found %d problem(s)" % len(problems)
    if language:
        head += " in my %s program%s" % (TITLES[lang_of(language)], " " + name if name else "")
    lines = [head + ":"]
    for p in problems:
        lines.append("line %d, col %d: %s: %s%s" % (p["line"], p["col"] + 1, p["severity"].upper(),
                                                     p["message"], " (fix: %s)" % p["fix"] if p["fix"] else ""))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# The references (tools/reference/*.json): argument counts from each form's syntax
# ---------------------------------------------------------------------------

_SPEC = {}


def _split_args(inner):
    """'a,b[,c]' -> ([(text, optional)], variadic). Commas at paren depth 0 split; a piece that
    starts inside [ ] (or with '[') is optional; '...' marks a repeating list."""
    pieces, cur, start_opt = [], "", False
    pdepth = bdepth = 0
    in_str = False
    variadic = "..." in inner or "\u2026" in inner
    for ch in inner:
        if ch == '"':
            in_str = not in_str
        if not in_str:
            if ch in "({":
                pdepth += 1
            elif ch in ")}":
                pdepth -= 1
            elif ch == "[":
                if not cur.strip():
                    start_opt = True
                bdepth += 1
                continue
            elif ch == "]":
                bdepth -= 1
                continue
            elif ch == "," and pdepth == 0:
                pieces.append((cur.strip(), start_opt))
                cur, start_opt = "", bdepth > 0
                continue
        cur += ch
    pieces.append((cur.strip(), start_opt))
    pieces = [(t, o) for t, o in pieces if t]
    return pieces, variadic


def _form_spec(form, name):
    """(min, max) arguments for one syntax form, max None for no limit; None if unreadable"""
    f = form.strip()
    if not f.lower().startswith(name.lower().rstrip()):
        return None
    rest = f[len(name.rstrip()):]
    if name.endswith("("):
        depth, end = 1, None
        for i, ch in enumerate(rest):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        inner = rest if end is None else rest[:end]
    else:
        inner = rest.split(":")[0].strip()
        if inner.lower().split(" ")[0] in ("then", "block"):
            return None
    if not inner.strip():
        return (0, 0)
    if "|" in inner or ";" in inner:
        return None
    pieces, variadic = _split_args(inner)
    if variadic:
        k = next((i for i, (t, _o) in enumerate(pieces) if "..." in t or "\u2026" in t), len(pieces))
        before = pieces[:k]
        need = [o for _t, o in before]
        if before and not need[-1] and len(before) >= 2:
            need[-1] = True  # "text1,text2,...": the second is an example of the repeat
        return (sum(1 for o in need if not o), None)
    return (sum(1 for _t, o in pieces if not o), len(pieces))


CONTROL_84 = {"If", "Then", "Else", "For(", "While", "Repeat", "End", "Lbl", "Goto", "Menu(",
              "IS>(", "DS<(", "prgm", "Return", "Stop"}
CONTROL_89 = {"if", "then", "else", "elseif", "endif", "for", "endfor", "while", "endwhile",
              "loop", "endloop", "try", "endtry", "dialog", "enddlog", "toolbar", "endtbar",
              "custom", "endcustm", "prgm", "endprgm", "func", "endfunc", "define", "lbl", "goto",
              "cycle", "exit", "return", "stop", "local", "item", "title"}


def arg_spec(entry):
    """(min, max) for a reference entry (max None: no limit), or None when it isn't checked"""
    key = id(entry)
    if key in _SPEC:
        return _SPEC[key]
    forms = entry.get("forms") or [entry.get("syntax", "")]
    specs = [_form_spec(f, entry["name"]) for f in forms]
    if not specs or any(s is None for s in specs):
        out = None
    else:
        mx = [s[1] for s in specs]
        out = (min(s[0] for s in specs), None if None in mx else max(mx))
    _SPEC[key] = out
    return out


def is_command(entry):
    return (entry.get("returns") or "").startswith("nothing")


_INDEX = {}


def _ref_index(slug):
    """{name: entry} for a reference: the 84's exact names (and PC spellings), the 89's lower
    case; the first entry with a name wins"""
    if slug in _INDEX:
        return _INDEX[slug]
    ref = reference.load(slug)
    idx = {}
    for e in ref.get("entries", []):
        for n in (e["name"], e.get("pc_spelling")):
            if not n:
                continue
            k = n.strip() if slug == "ti84" else n.strip().lower()
            idx.setdefault(k, e)
    _INDEX[slug] = idx
    return idx


# ---------------------------------------------------------------------------
# TI-84 Plus CE: a lexer with positions (the same tables calc_files tokenizes with)
# ---------------------------------------------------------------------------

_LEX84 = {}


def _lex84_tables():
    if _LEX84:
        return _LEX84
    table = dict(cf._tokens_84())
    names = {}
    for k, v in table.items():
        names[k] = v
    for k, v in cf.ASCII_84.items():
        names.setdefault(k, v)
    by_first = {}
    for k in names:
        if k:
            by_first.setdefault(k[0], set()).add(len(k))
    _LEX84.update(names=names, lens={c: sorted(v, reverse=True) for c, v in by_first.items()})
    # Token bytes -> reference entry (so √( and sqrt( find the same entry)
    ent = {}
    for key, e in _ref_index("ti84").items():
        b = names.get(key) or names.get(key + " ") or names.get(key.rstrip())
        if b is not None:
            ent.setdefault(b, e)
    _LEX84["entry"] = ent
    return _LEX84


def lex_84(line):
    """One line of 84 TI-Basic -> [(kind, text, col, end)]: kind "str" (a string, its quotes
    too), "tok" (a token name), "num", "space", "bad" (a character the 84 doesn't have)"""
    t = _lex84_tables()
    names, lens = t["names"], t["lens"]
    out, i, n = [], 0, len(line)
    while i < n:
        c = line[i]
        if c == '"':
            j = i + 1
            while j < n and line[j] != '"' and line[j] != "\u2192" and not line.startswith("->", j):
                j += 1
            if j < n and line[j] == '"':
                j += 1
            out.append(("str", line[i:j], i, j))
            i = j
            continue
        if c == " ":
            j = i
            while j < n and line[j] == " ":
                j += 1
            # " or ", " and ": tokens that start with a space
            hit = next((k for k in (" or ", " and ", " xor ", " nPr ", " nCr ") if line.startswith(k, i)), None)
            if hit:
                out.append(("tok", hit, i, i + len(hit)))
                i += len(hit)
                continue
            out.append(("space", line[i:j], i, j))
            i = j
            continue
        if c.isdigit() or (c == "." and i + 1 < n and line[i + 1].isdigit()):
            j = i
            while j < n and (line[j].isdigit() or line[j] == "." or
                             (line[j] == "E" and j + 1 < n and (line[j + 1].isdigit() or line[j + 1] in "-\u207b"))):
                if line[j] == "E" and j + 1 < n and line[j + 1] in "-\u207b":
                    j += 1
                j += 1
            out.append(("num", line[i:j], i, j))
            i = j
            continue
        hit = None
        for k in lens.get(c, ()):
            if i + k <= n:
                piece = line[i:i + k]
                if piece in names:
                    if piece in ("pi", "theta") and (line[i + k:i + k + 1].isalpha() or (i and line[i - 1].isalpha())):
                        continue
                    hit = piece
                    break
        if hit is None:
            out.append(("bad", c, i, i + 1))
            i += 1
            continue
        out.append(("tok", hit, i, i + len(hit)))
        i += len(hit)
    return out


def _entry_84(text):
    t = _lex84_tables()
    b = t["names"].get(text)
    e = t["entry"].get(b) if b is not None else None
    if e is None:
        e = _ref_index("ti84").get(text.strip())
    return e


def _statements(toks, is_sep):
    """Tokens -> [[tokens]] split where is_sep(token) (the ':' outside strings)"""
    out, cur = [], []
    for tk in toks:
        if is_sep(tk):
            out.append(cur)
            cur = []
        else:
            cur.append(tk)
    out.append(cur)
    return out


def _count_call_args(toks, k, stop):
    """Arguments of the call whose '(' token is toks[k]: (count, closed, end col)"""
    depth, commas, empty = 1, 0, True
    end = toks[k][3]
    for j in range(k + 1, len(toks)):
        kind, text, col, e = toks[j]
        if kind == "space":
            continue
        if stop(toks[j]):
            break
        end = e
        if kind in ("tok", "bad") and kind != "str":
            if text.endswith(("(", "{", "[")) and text not in ("[",) or text in ("{", "["):
                depth += 1
            elif text in (")", "}", "]"):
                depth -= 1
                if depth == 0:
                    return (0 if empty else commas + 1), True, e
            elif text == "," and depth == 1:
                commas += 1
                continue
        empty = False
    return (0 if empty else commas + 1), False, end


def _args_problem(entry, count, line, col, end, closed_by_line):
    spec = arg_spec(entry)
    if spec is None:
        return None
    lo, hi = spec
    name = entry["name"].strip()
    syntax = entry.get("syntax", "")
    if count < lo:
        return _p(line, col, end, "error", "%s needs %s argument%s, it has %d" % (
            name, ("at least %d" % lo) if hi != lo else str(lo), "" if lo == 1 else "s", count),
            "the syntax is %s" % syntax)
    if hi is not None and count > hi:
        return _p(line, col, end, "warning", "%s takes %s argument%s, it has %d" % (
            name, ("at most %d" % hi) if hi != lo else str(hi), "" if hi == 1 else "s", count),
            "the syntax is %s" % syntax)
    return None


def _check_84(text, name):
    probs = []
    lines = text.split("\n")
    if name is not None and not cf.NAME_84.match(name):
        probs.append(_p(1, 0, 1, "error", "%r can't be a TI-84 program name" % name,
                        "up to 8 capitals A-Z, digits or \u03b8, a letter first"))
    labels, gotos = {}, []
    stack = []  # (kind, line, col)
    prev_head = None
    total = 0
    for n, raw in enumerate(lines, 1):
        off = 1 if raw.startswith(":") else 0
        line = raw[off:]
        if "\t" in raw:
            c = raw.index("\t")
            probs.append(_p(n, c, c + 1, "error", "a tab: the 84 has none, and the send stops on it",
                            "indent with spaces (they are dropped) or not at all"))
        # The real tokenizer: what it can't take, and lower case words outside strings
        work = line.replace("\t", " ")
        for _ in range(20):
            found = []
            try:
                total += len(cf._line_84(work, n, found)) + 1
            except ValueError as e:
                m = re.search(r"isn't a TI-84 Plus token or character$", str(e))
                bad = re.search(r": '(.*)' isn't", str(e)) or re.search(r': "(.*)" isn\'t', str(e))
                ch = None
                if bad:
                    try:
                        ch = ast.literal_eval("'%s'" % bad.group(1)) if len(bad.group(1)) > 1 else bad.group(1)
                    except (ValueError, SyntaxError):
                        ch = bad.group(1)[:1]
                c = work.find(ch) if ch else -1
                if not m or c < 0:
                    probs.append(_p(n, off, off + len(line), "error", str(e).split(": ", 1)[-1]))
                    break
                if ch != "\t":
                    probs.append(_p(n, c + off, c + off + 1, "error",
                                    "%r isn't a character the TI-84 Plus has" % ch,
                                    _suggest_char(ch)))
                work = work[:c] + " " + work[c + 1:]
                continue
            for a, b, msg, hint in _misspelt(work, n, found):
                probs.append(_p(n, a + off, b + off, "error", msg, hint))
            break
        if len(raw) > LONG_LINE:
            probs.append(_p(n, LONG_LINE, len(raw), "info", "a long line (%d characters)" % len(raw),
                            "split it at a ':' into lines: easier to read on the calculator"))
        toks = lex_84(line)
        toks = [(k, t, c + off, e + off) for k, t, c, e in toks]
        is_sep = lambda tk: tk[0] == "tok" and tk[1] == ":"
        _parens_84(toks, n, probs)
        for st in _statements(toks, is_sep):
            words = [tk for tk in st if tk[0] != "space"]
            if not words:
                continue
            first = words[0]
            head = first[1].strip() if first[0] == "tok" else first[0]
            _assign_84(words, n, probs)
            _rules_84(words, n, probs)
            _traps_84(words, n, probs)
            if head == "If":
                pass
            elif head == "Then":
                if prev_head != "If":
                    probs.append(_p(n, first[2], first[3], "error", "Then without an If on the line before",
                                    "write If condition, then Then on the next line (or after a ':')"))
                stack.append(("If", n, first[2], first[3]))
            elif head == "Else":
                if not stack or stack[-1][0] != "If":
                    probs.append(_p(n, first[2], first[3], "error", "Else outside an If ... Then block",
                                    "Else belongs between Then and End"))
                else:
                    stack[-1] = ("Else", stack[-1][1], stack[-1][2], stack[-1][3])
            elif head in ("For(", "While", "Repeat"):
                stack.append((head, n, first[2], first[3]))
            elif head == "End":
                if not stack:
                    probs.append(_p(n, first[2], first[3], "error", "End with no block to close",
                                    "remove it, or open the block (If ... Then, For(, While, Repeat)"))
                else:
                    stack.pop()
            elif head == "Lbl":
                lab = "".join(tk[1] for tk in words[1:]).strip()
                if not re.match(r"^[A-Z0-9\u03b8]{1,2}$", lab):
                    probs.append(_p(n, first[2], words[-1][3], "error", "Lbl %r: a label is 1 or 2 "
                                    "characters, A-Z, 0-9 or \u03b8" % lab))
                elif lab in labels:
                    probs.append(_p(n, first[2], words[-1][3], "warning", "Lbl %s is there twice (line %d)"
                                    % (lab, labels[lab]), "the first one wins: rename one"))
                else:
                    labels[lab] = n
            elif head == "Goto":
                lab = "".join(tk[1] for tk in words[1:]).strip()
                gotos.append((lab, n, first[2], words[-1][3]))
            elif head == "Menu(":
                parts = _split_top(words[1:])
                for k in range(2, len(parts), 2):
                    lab = "".join(tk[1] for tk in parts[k]).strip().rstrip(")")
                    if parts[k]:
                        gotos.append((lab, n, parts[k][0][2], parts[k][-1][3]))
            if stack and head in ("Goto",) and any(s[0] in ("For(", "While", "Repeat", "If", "Else") for s in stack):
                probs.append(_p(n, first[2], first[3], "info", "Goto out of a block (%s on line %d): "
                                "the calculator runs out of memory after a while (ERR:MEMORY)"
                                % (stack[-1][0], stack[-1][1]), "leave loops with a condition, or Stop"))
            prev_head = head
            _args_84(words, n, probs)
    for kind, ln, c, e in stack:
        probs.append(_p(ln, c, e, "warning", "%s has no End: the block runs once to the end of the "
                        "program" % ("If ... Then" if kind in ("If", "Else") else kind), "add End where the block ends"))
    for lab, ln, c, e in gotos:
        if lab and lab not in labels:
            probs.append(_p(ln, c, e, "error", "no Lbl %s in the program (ERR:LABEL)" % lab,
                            "add Lbl %s, or jump to a label that is there" % lab))
    if total > MAX_BYTES:
        probs.append(_p(1, 0, 1, "error", "the program is too big (%d bytes of tokens)" % total,
                        "split it into programs that call each other (prgmNAME)"))
    return probs


def _suggest_char(ch):
    return {"\u201c": 'a plain " quote', "\u201d": 'a plain " quote', "\u2018": "'", "\u2019": "'",
            "\u2013": "-", "\u2014": "-", "\u00d7": "*", "\u00f7": "/", "\u2264": "<=", "\u2265": ">=",
            "\u2260": "!="}.get(ch, "type it with the PC spellings (->, <=, sqrt(, pi, theta) or leave it out")


def _misspelt(line, n, positions):
    """calc_files' misspelling notes, with where each word is: [(start, end, message, fix)]"""
    out, done = [], set()
    for p in positions:
        a = b = p
        while a > 0 and line[a - 1].isalpha():
            a -= 1
        while b < len(line) and line[b].isalpha():
            b += 1
        if a in done:
            continue
        done.add(a)
        msgs = cf._misspelt_84(line, n, [p])
        msg = msgs[0] if msgs else "lower case outside a string"
        msg = re.sub(r"^line \d+: ", "", msg)
        hint = re.search(r"Did you mean (.*)\?$", msg)
        msg = re.sub(r"\. Did you mean .*\?$", "", msg)
        fix = ("did you mean %s?" % hint.group(1)) if hint else "commands are spelt as the calculator shows them; variables are capitals"
        out.append((a, b, msg, fix))
    return out


def _split_top(words):
    """Tokens after a '(' -> argument token lists at depth 0"""
    parts, cur, depth = [], [], 0
    for tk in words:
        if tk[0] == "tok" and (tk[1].endswith("(") or tk[1] in ("{", "[")):
            depth += 1
        elif tk[0] == "tok" and tk[1] in (")", "}", "]"):
            depth -= 1
            if depth < 0:
                break
        if tk[0] == "tok" and tk[1] == "," and depth == 0:
            parts.append(cur)
            cur = []
            continue
        cur.append(tk)
    parts.append(cur)
    return parts


def _parens_84(toks, n, probs):
    """Brackets per statement: a ')' with nothing open is an error; left open at a ':', a store
    or the line's end is fine on the 84 (info, once per line)"""
    opened, left, quote_open = [], None, None
    for tk in toks:
        kind, text, c, e = tk
        if kind == "str":
            if len(text) < 2 or not text.endswith('"'):
                quote_open = tk
            continue
        if kind != "tok":
            continue
        if text in (":", "\u2192", "->"):
            if opened and left is None:
                left = (opened[-1], len(opened))
            opened = []
            continue
        if text.endswith("(") or text in ("{", "["):
            opened.append(tk)
        elif text in (")", "}", "]"):
            if not opened:
                probs.append(_p(n, c, e, "error", "a %s with nothing open before it (ERR:SYNTAX)" % text,
                                "remove it, or add the opening bracket"))
            else:
                opened.pop()
    if opened and left is None:
        left = (opened[-1], len(opened))
    if left is not None:
        tk, k = left
        probs.append(_p(n, tk[2], tk[3], "info", "%d bracket%s left open: fine on the 84 at a line's end, "
                        "a ':' or a store (it closes them there)" % (k, "" if k == 1 else "s"), ""))
    alone = [t for t in toks if t[0] != "space"] == [quote_open]  # A comment line: "TEXT
    if quote_open is not None and not alone:
        probs.append(_p(n, quote_open[2], quote_open[3], "info", "the string isn't closed: fine on the 84 at "
                        "a line's end (or before \u2192)", ""))


def _bytes_84(tk):
    return _lex84_tables()["names"].get(tk[1]) if tk[0] == "tok" else None


def _is_var_84(tk, real_only=False):
    """A variable token: A-Z or θ (real_only), else also lists, matrices, strings, Y=, window
    and the other system variables a value can be stored to"""
    b = _bytes_84(tk)
    if b is None:
        return False
    if len(b) == 1 and (0x41 <= b[0] <= 0x5B):
        return True
    if real_only:
        return False
    return b[0] in (0x5C, 0x5D, 0x5E, 0x63, 0xAA, 0xEB) or b == b"\xab"  # ...and rand (its seed)


def _var_end(words, k):
    """Where the variable starting at words[k] ends: ʟ takes its name's letters"""
    if k >= len(words):
        return k
    j = k + 1
    if _bytes_84(words[k]) == b"\xeb":
        while j < len(words) and words[j][0] in ("tok", "num") and re.match(r"^[A-Z0-9θ]+$", words[j][1]) \
                and words[j][2] == words[j - 1][3]:
            j += 1
    return j


def _list_name(nm, n, c, e, probs):
    if not nm:
        probs.append(_p(n, c, e, "error", "ʟ with no list name after it",
                        "ʟNAME: 1 to 5 capitals, digits or θ, a letter first"))
    elif len(nm) > 5 or not re.match(r"^[A-Zθ]", nm):
        probs.append(_p(n, c, e, "error", "list name %r: up to 5 capitals, digits or θ, a letter first" % nm,
                        "ʟ%s" % re.sub(r"^[0-9]+", "", nm)[:5]))


def _assign_84(words, n, probs):
    """X=5 on its own compares (it doesn't store); a store only into something storable"""
    if len(words) >= 3 and words[0][0] == "tok" and words[1][1] == "=" and _is_var_84(words[0]) and \
            not any(tk[1] in ("→", "->") for tk in words):
        rhs = "".join(tk[1] for tk in words[2:])
        probs.append(_p(n, words[0][2], words[-1][3], "error", "%s=... compares, it doesn't store "
                        "(TI-Basic stores with →; = only puts 1 or 0 in Ans)" % words[0][1],
                        "%s→%s" % (rhs, words[0][1])))
    for k, tk in enumerate(words):
        if tk[0] != "tok" or tk[1] not in ("→", "->"):
            continue
        if k + 1 >= len(words):
            probs.append(_p(n, tk[2], tk[3], "error", "nothing after → to store into", "value→A"))
            continue
        tgt = words[k + 1]
        if tgt[0] == "tok" and tgt[1] == "dim(":
            continue  # 5→dim(L₁)
        if not _is_var_84(tgt):
            probs.append(_p(n, tgt[2], tgt[3], "error", "%r can't be stored into: → needs a variable (A-Z, "
                            "θ, L₁-L₆, ʟNAME, [A]-[J], Str0-Str9, Y0-Y9...)" % tgt[1], "value→A"))
            continue
        j = _var_end(words, k + 1)
        if _bytes_84(tgt) == b"\xeb":
            _list_name("".join(w[1] for w in words[k + 2:j]), n, tgt[2], words[j - 1][3], probs)
        if j < len(words) and words[j][1] != "(":
            in_text = k and words[k - 1][0] == "str" and not words[k - 1][1].endswith('"')
            if in_text:  # "1→VARS, 2→ANS": text with arrows, as a comment line
                probs.append(_p(n, tk[2], tk[3], "warning", "→ inside a string ends it: what follows runs "
                                "as code (ERR:SYNTAX if this line runs)", "write -> as text another way, or "
                                "close the string first"))
                break
            probs.append(_p(n, words[j][2], words[-1][3], "error", "more after the store into %s: a store "
                            "ends the statement (ERR:SYNTAX)" % tgt[1], "start a new line, or put a ':' first"))


def _parts_until_store(words):
    parts, out = _split_top(words), []
    for p in parts:
        stop = next((i for i, w in enumerate(p) if w[1] in ("→", "->")), None)
        out.append(p if stop is None else p[:stop])
        if stop is not None:
            break
    return out


def _const(p):
    """An argument that is a whole number written out (5, -1), else None"""
    if len(p) == 1 and p[0][0] == "num" and p[0][1].isdigit():
        return int(p[0][1])
    if len(p) == 2 and p[0][1] in ("~", "⁻", "-") and p[1][0] == "num" and p[1][1].isdigit():
        return -int(p[1][1])
    return None


SCREEN_84 = {"Output(": ((1, 10), (1, 26)), "Text(": ((-1, 164), (0, 264)), "Pxl-On(": ((0, 164), (0, 264)),
             "Pxl-Off(": ((0, 164), (0, 264)), "Pxl-Change(": ((0, 164), (0, 264)), "pxl-Test(": ((0, 164), (0, 264))}


def _rules_84(words, n, probs):
    """Per command: For('s counter, Output( / Text( / Pxl- positions, Menu( options, Prompt,
    Input, DelVar, named lists"""
    first = words[0]
    head = first[1].strip() if first[0] == "tok" else ""
    for k, tk in enumerate(words):
        if _bytes_84(tk) == b"\xeb" and not (k and words[k - 1][1] in ("→", "->")):
            j = _var_end(words, k)
            _list_name("".join(w[1] for w in words[k + 1:j]), n, tk[2], words[j - 1][3], probs)
        if tk[0] != "tok" or tk[1] not in ("For(", "Menu(") and tk[1] not in SCREEN_84:
            continue
        name = tk[1]
        parts = _parts_until_store(words[k + 1:])
        if name == "For(" and parts and parts[0]:
            v = parts[0]
            if len(v) != 1 or not _is_var_84(v[0], real_only=True):
                probs.append(_p(n, v[0][2], v[-1][3], "error", "For('s counter must be a real variable (A-Z or "
                                "θ), not %r" % "".join(w[1] for w in v), "For(I,1,10)"))
        elif name in SCREEN_84:
            for idx, (lo, hi) in enumerate(SCREEN_84[name]):
                if idx < len(parts) and parts[idx]:
                    val = _const(parts[idx])
                    p = parts[idx]
                    if val is not None and not lo <= val <= hi:
                        what = ("row", "column")[idx]
                        probs.append(_p(n, p[0][2], p[-1][3], "error", "%s %s %d is off the screen: %d to %d "
                                        "(ERR:DOMAIN)" % (name, what, val, lo, hi), "a %s from %d to %d" % (what, lo, hi)))
        elif name == "Menu(":
            if len(parts) < 3 or len(parts) % 2 == 0:
                probs.append(_p(n, tk[2], words[-1][3], "error", "Menu( takes a title, then pairs of \"text\",label "
                                "(it has %d argument%s)" % (len(parts), "" if len(parts) == 1 else "s"),
                                'Menu("TITLE","ONE",A,"TWO",B)'))
            elif (len(parts) - 1) // 2 > 9:
                probs.append(_p(n, tk[2], words[-1][3], "error", "Menu( with %d options: the CE takes up to 9"
                                % ((len(parts) - 1) // 2), "split it into two menus"))
    if head not in ("Prompt", "Input", "DelVar"):
        return
    rest = words[1:]
    parts = _split_top(rest) if rest else []

    def span(p):
        return (p[0][2], p[-1][3]) if p else (first[2], first[3])

    def whole_var(p):
        return bool(p) and _is_var_84(p[0]) and _var_end(p, 0) == len(p)
    if head == "Prompt":
        if not parts:
            probs.append(_p(n, first[2], first[3], "error", "Prompt needs at least one variable", "Prompt A,B"))
        for p in parts:
            if not whole_var(p):
                probs.append(_p(n, *span(p), "error", "Prompt takes variables, not %r" % "".join(w[1] for w in p),
                                "Prompt A,B"))
    elif head == "Input":
        if len(parts) > 2:
            probs.append(_p(n, first[2], words[-1][3], "error", "Input takes [\"text\",]variable, not %d arguments"
                            % len(parts), 'Input "X=",X'))
        elif parts:
            if not whole_var(parts[-1]):
                probs.append(_p(n, *span(parts[-1]), "error", "Input's last argument must be a variable, not %r"
                                % "".join(w[1] for w in parts[-1]), 'Input "X=",X'))
            if len(parts) == 2:
                p = parts[0]
                if not (p and (p[0][0] == "str" or (_bytes_84(p[0]) or b"")[:1] == b"\xaa")):
                    probs.append(_p(n, *span(p), "error", "Input's prompt must be a string", 'Input "X=",X'))
    else:  # DelVar A, and DelVar ADelVar B or DelVar ADisp A: another command may follow at once
        b = _bytes_84(rest[0]) if rest else None
        if not rest or not (_is_var_84(rest[0]) or (b and b[0] in (0x60, 0x61, 0x3C))):
            probs.append(_p(n, *(span(rest[:1]) if rest else span([])), "error", "DelVar deletes a variable, not %r"
                            % (rest[0][1] if rest else ""), "DelVar A"))


def _traps_84(words, n, probs):
    for k, tk in enumerate(words):
        if tk[0] == "tok" and tk[1] in ("^2", "^3", "\u00b2", "\u00b3") and k + 1 < len(words) and \
                words[k + 1][0] == "num" and words[k + 1][2] == tk[3]:
            probs.append(_p(n, tk[2], words[k + 1][3], "warning", "%s%s is %s then %s (times)" % (
                tk[1], words[k + 1][1], tk[1], words[k + 1][1]), "^(%s%s)" % (tk[1][-1], words[k + 1][1])))
        if tk[0] == "num" and len(tk[1]) > 2 and tk[1].endswith("10") and k + 1 < len(words) and \
                words[k + 1][1] == "^(" and words[k + 1][2] == tk[3]:
            d = tk[1][:-2]
            probs.append(_p(n, tk[2], words[k + 1][3], "warning", "%s^( reads as %s times 10^( (the 10^( "
                            "key)" % (tk[1], d), "(%s)^(" % tk[1]))


def _args_84(words, n, probs):
    stop = lambda tk: tk[0] == "tok" and tk[1] in (":", "\u2192", "->")
    for k, tk in enumerate(words):
        if tk[0] != "tok":
            continue
        e = _entry_84(tk[1])
        if e is None or e["name"] in CONTROL_84:
            continue
        if tk[1].endswith("("):
            count, _closed, end = _count_call_args(words, k, stop)
            p = _args_problem(e, count, n, tk[2], end, True)
            if p:
                probs.append(p)
        elif k == 0 and is_command(e) and e.get("syntax", "").startswith(e["name"].rstrip() + " "):
            rest = [w for w in words[1:]]
            if e["name"].rstrip() != tk[1].rstrip():
                continue
            parts = _split_top(rest) if rest else []
            count = 0 if not rest else len(parts)
            p = _args_problem(e, count, n, tk[2], words[-1][3], False)
            if p:
                probs.append(p)


# ---------------------------------------------------------------------------
# TI-89 Titanium
# ---------------------------------------------------------------------------

_SYM89 = None


def _sym89():
    """Names that aren't identifiers (∫( √( ►Hex @>Hex @int( ...), longest first"""
    global _SYM89
    if _SYM89 is None:
        s = set(cf.ASCII_89) | set(cf._WORDS_89) | {"\u2192", "\u2264", "\u2265", "\u2260"}
        for k in _ref_index("ti89"):
            if k and not (k[0].isalpha() or k[0] == "_"):
                s.add(k)
        _SYM89 = sorted(s, key=len, reverse=True)
    return _SYM89


_ID89 = re.compile(r"[A-Za-z_\u0370-\u03ff][A-Za-z0-9_\u0370-\u03ff]*")
_ARROWS89 = []


def _arrow_names_89():
    if not _ARROWS89:
        _ARROWS89.extend(sorted((k for k in _ref_index("ti89") if "\u25ba" in k and k[0].isalpha()),
                                key=len, reverse=True) or ["\x00"])
    return _ARROWS89


def lex_89(line):
    """One line of 89 TI-Basic -> [(kind, text, col, end)]: "str", "comment", "id" (with a
    following '(' joined: "nint("), "sym" (►, ∫(, @> ...), "num", "space", "op" """
    out, i, n = [], 0, len(line)
    syms = _sym89()
    while i < n:
        c = line[i]
        if c == '"':
            j = line.find('"', i + 1)
            j = n if j < 0 else j + 1
            out.append(("str", line[i:j], i, j))
            i = j
            continue
        if c == COPYRIGHT:
            out.append(("comment", line[i:], i, n))
            break
        if c == " ":
            j = i
            while j < n and line[j] == " ":
                j += 1
            out.append(("space", line[i:j], i, j))
            i = j
            continue
        if c.isdigit() or (c == "." and i + 1 < n and line[i + 1].isdigit()):
            j = i
            while j < n and (line[j].isdigit() or line[j] == "." or
                             (line[j] in "Ee\u1d07" and j + 1 < n and (line[j + 1].isdigit() or line[j + 1] in "-\u207b\u2212"))):
                if line[j] in "Ee\u1d07" and line[j + 1] in "-\u207b\u2212":
                    j += 1
                j += 1
            out.append(("num", line[i:j], i, j))
            i = j
            continue
        arrow = next((s for s in _arrow_names_89() if line[i:i + len(s)].lower() == s), None)
        if arrow:  # mat►list( P►Rx( R►Pθ(: one name with the arrow inside
            out.append(("id", line[i:i + len(arrow)], i, i + len(arrow)))
            i += len(arrow)
            continue
        m = _ID89.match(line, i)
        if m and not line.startswith("pi", i) or (m and line.startswith("pi", i) and len(m.group(0)) > 2):
            j = m.end()
            if j < n and line[j] == "(":
                j += 1
            out.append(("id", line[i:j], i, j))
            i = j
            continue
        hit = next((s for s in syms if line.startswith(s, i)), None)
        if hit:
            out.append(("sym", hit, i, i + len(hit)))
            i += len(hit)
            continue
        if m:
            j = m.end()
            if j < n and line[j] == "(":
                j += 1
            out.append(("id", line[i:j], i, j))
            i = j
            continue
        out.append(("op", c, i, i + 1))
        i += 1
    return out


_HEAD = re.compile(r"^\s*(?:define\s+)?([A-Za-z][A-Za-z0-9_]*)\s*\(([^)]*)\)\s*(?:=\s*(prgm|func))?\s*$", re.I)
OPEN_89 = {"for": "endfor", "while": "endwhile", "loop": "endloop", "try": "endtry",
           "dialog": "enddlog", "toolbar": "endtbar", "custom": "endcustm", "prgm": "endprgm",
           "func": "endfunc"}
CLOSE_89 = {v: k for k, v in OPEN_89.items()}
CLOSE_89["endif"] = "if"
# What a function may not do (TI-89 guidebook: functions can't show, ask, draw, change modes
# or folders, or change variables outside themselves)
NOT_IN_FUNC = {"disp", "output", "input", "inputstr", "prompt", "request", "dialog", "popup",
               "clrio", "clrhome", "pause", "text", "toolbar", "custom", "dispg", "disphome",
               "disptbl", "newfold", "newprob", "clrdraw", "clrgraph", "pxlon", "pxloff", "pxltext",
               "pton", "ptoff", "line", "circle", "dropdown", "title", "copyvar", "movevar",
               "rename", "archive", "unarchiv", "sendcalc", "getcalc", "sendchat", "lock", "unlock"}
NOT_IN_FUNC_CALLS = {"setmode(", "setfold(", "setgraph(", "settable("}
SYS_VARS_89 = {"xmin", "xmax", "ymin", "ymax", "xscl", "yscl", "xres", "xgrid", "ygrid", "tmin",
               "tmax", "tstep", "zmin", "zmax", "zscl", "eyeθ", "eyeφ", "eyeψ", "ncontour", "ok",
               "errornum", "main", "eqn", "sysmath", "regeq", "regcoef", "seed1", "seed2", "tblstart",
               "δtbl", "tblinput", "nmin", "nmax", "plotstrt", "plotstep", "diftol", "dtime",
               "fldres", "estep", "ncurves", "xc", "yc", "zc", "tc", "rc", "θc", "nc"}
# What may follow ► (or @>): a conversion, or a unit (_ft)
CONVERSIONS_89 = {"bin", "dec", "hex", "polar", "rect", "cylind", "sphere", "dms", "dd", "grad", "rad",
                  "ln", "logbase(", "exp", "cos", "sin"}
_RESERVED_89 = None


def reserved_89():
    """Names a program can't store into: built-in commands and functions, system variables"""
    global _RESERVED_89
    if _RESERVED_89 is None:
        out = set(SYS_VARS_89)
        for k in _ref_index("ti89"):
            b = k.rstrip("(").strip()
            if re.match(r"^[a-z][a-z0-9_]+$", b):
                out.add(b)
        _RESERVED_89 = out
    return _RESERVED_89


def _arg_names(args):
    return [a.strip().lower() for a in args.split(",") if a.strip()]


def _check_89(text, name):
    probs = []
    lines = text.split("\n")
    idx = _ref_index("ti89")
    first_n = next((k for k, l in enumerate(lines) if l.strip()), None)
    last_n = next((k for k in range(len(lines) - 1, -1, -1) if lines[k].strip()), None)
    head_args, kind = [], None
    body_start = 0
    if first_n is None:
        return probs
    m = _HEAD.match(lines[first_n].lstrip(":"))
    if m and not all(re.match(r"^[A-Za-z][A-Za-z0-9_]*$", a) for a in _arg_names(m.group(2))):
        m = None  # sin(pi/6): an expression, not the program's first line
    if m:
        hname = m.group(1)
        if name is None:
            name = hname
        head_args = _arg_names(m.group(2))
        if len(hname) > 8:
            probs.append(_p(first_n + 1, 0, len(lines[first_n]), "error", "the name %r is %d characters: "
                            "the 89 takes up to 8" % (hname, len(hname)), "shorten it to %s" % hname[:8].lower()))
        elif not cf.NAME_89.match(hname.lower()):
            probs.append(_p(first_n + 1, 0, len(lines[first_n]), "error", "%r can't be a TI-89 name" % hname,
                            "letters, digits or _, a letter first"))
        elif hname.lower() in idx or hname.lower() in SYS_VARS_89:
            probs.append(_p(first_n + 1, 0, len(hname), "warning", "%s is the name of a built-in command or "
                            "system variable" % hname, "pick another name"))
        for a in head_args:
            if not cf.NAME_89.match(a):
                probs.append(_p(first_n + 1, 0, len(lines[first_n]), "error", "argument %r isn't a name" % a,
                                "names are up to 8 letters, digits or _, a letter first"))
        if m.group(3):
            kind = m.group(3).lower()
        body_start = first_n + 1
    else:
        probs.append(_p(first_n + 1, 0, len(lines[first_n]), "info", "no first line name(args): the file's "
                        "name names the program and the whole text is its body",
                        "start with name(), then Prgm ... EndPrgm"))
        body_start = first_n
    nxt = next((k for k in range(body_start, len(lines)) if lines[k].strip()), None)
    if kind is None and nxt is not None:
        w = lines[nxt].strip().lstrip(":").strip().lower()
        if w in ("prgm", "func"):
            kind = w
        elif m:
            probs.append(_p(nxt + 1, 0, len(lines[nxt]), "error", "after %s(...) the next line is Prgm or Func"
                            % m.group(1), "add Prgm (and EndPrgm at the end), or Func ... EndFunc"))
    if kind and last_n is not None:
        last = lines[last_n].strip().lstrip(":").strip().lower()
        if last != "end" + kind:
            probs.append(_p(last_n + 1, 0, len(lines[last_n]), "error", "the %s has no End%s at its end" % (
                "program" if kind == "prgm" else "function", kind.capitalize()),
                "end the text with End%s" % kind.capitalize()))
    in_func = kind == "func"
    locals_ = set(head_args)
    stack = []
    prev = None
    stored_before = {}  # name: the line it is first stored on
    for n0, raw in enumerate(lines):
        n = n0 + 1
        off = 1 if raw.startswith(":") else 0
        line = raw[off:]
        if "\t" in raw:
            c = raw.index("\t")
            probs.append(_p(n, c, c + 1, "error", "a tab: the 89 has none", "indent with spaces"))
        work = line.replace("\t", " ")
        for _ in range(20):
            try:
                cf._line_89(work, n)
            except ValueError as e:
                bad = re.search(r": '(.*)' isn't a TI-89 character", str(e))
                ch = bad.group(1) if bad else None
                if ch and len(ch) > 1:
                    try:
                        ch = ast.literal_eval("'%s'" % ch)
                    except (ValueError, SyntaxError):
                        ch = ch[:1]
                c = work.find(ch) if ch else -1
                if c < 0:
                    probs.append(_p(n, off, off + len(line), "error", str(e).split(": ", 1)[-1]))
                    break
                probs.append(_p(n, c + off, c + off + 1, "error", "%r isn't a character the TI-89 has" % ch,
                                _suggest_char(ch)))
                work = work[:c] + " " + work[c + 1:]
                continue
            break
        if n0 == first_n and m:
            continue
        toks = [(k, t, c + off, e + off) for k, t, c, e in lex_89(line)]
        _parens_89(toks, n, probs)
        sts = _statements([t for t in toks if t[0] != "comment"], lambda tk: tk[0] == "op" and tk[1] == ":")
        for st in sts:
            words = [tk for tk in st if tk[0] != "space"]
            if not words:
                continue
            first = words[0]
            w = first[1].lower() if first[0] in ("id", "sym") else ""
            low = [tk[1].lower() for tk in words]
            if w == "if":
                if "then" in low[1:]:
                    stack.append(["if", n, first[2], first[3], False])
            elif w == "then" and prev == "if":
                stack.append(["if", n, first[2], first[3], False])
            elif w == "elseif":
                if not stack or stack[-1][0] != "if":
                    probs.append(_p(n, first[2], first[3], "error", "ElseIf outside an If ... Then block", ""))
                elif stack[-1][4]:
                    probs.append(_p(n, first[2], first[3], "error", "ElseIf after Else", "ElseIf comes before Else"))
            elif w == "else":
                if not stack or stack[-1][0] not in ("if", "try"):
                    probs.append(_p(n, first[2], first[3], "error", "Else outside If ... Then or Try",
                                    "Else belongs inside If ... EndIf or Try ... EndTry"))
                elif stack[-1][4]:
                    probs.append(_p(n, first[2], first[3], "error", "a second Else in the same block", ""))
                else:
                    stack[-1][4] = True
            elif w in OPEN_89:
                if w in ("prgm", "func") and stack:
                    probs.append(_p(n, first[2], first[3], "error", "%s inside another block" % first[1],
                                    "Prgm or Func is the line after name(); blocks go inside"))
                stack.append([w, n, first[2], first[3], False])
                if w == "for" and len(words) > 1 and words[1][0] == "id":
                    v = words[1][1].lower()
                    if in_func and v not in locals_:
                        probs.append(_p(n, words[1][2], words[1][3], "error", "the For counter %s isn't Local: "
                                        "a function can't store to a global variable" % words[1][1],
                                        "add Local %s at the top" % words[1][1]))
            elif w in CLOSE_89:
                want = CLOSE_89[w]
                if not stack:
                    probs.append(_p(n, first[2], first[3], "error", "%s with no block to close" % first[1],
                                    "remove it, or open the block"))
                elif stack[-1][0] != want:
                    if any(s[0] == want for s in stack):
                        # Blocks left open inside this one: each one's missing end, at its start
                        while stack and stack[-1][0] != want:
                            s = stack.pop()
                            probs.append(_p(s[1], s[2], s[3], "error", "%s has no %s (before %s on line %d)" % (
                                _opener_name(s[0]), _closer_name(s[0]), first[1], n),
                                "add %s where the block ends" % _closer_name(s[0])))
                        stack.pop()
                    else:
                        probs.append(_p(n, first[2], first[3], "error", "%s, but the open block is %s (line %d)" % (
                            first[1], _opener_name(stack[-1][0]), stack[-1][1]),
                            "close it with %s first" % _closer_name(stack[-1][0])))
                else:
                    stack.pop()
            elif w == "end":
                probs.append(_p(n, first[2], first[3], "error", "End alone isn't a TI-89 command",
                                "close with EndIf, EndFor, EndWhile, EndLoop, EndTry ..."))
            elif w == "local":
                for tk in words[1:]:
                    if tk[0] == "id":
                        v = tk[1].lower().rstrip("(")
                        if not cf.NAME_89.match(v):
                            probs.append(_p(n, tk[2], tk[3], "error", "Local %s: a name is up to 8 letters, "
                                            "digits or _, a letter first" % tk[1]))
                        elif v in reserved_89():
                            probs.append(_p(n, tk[2], tk[3], "error", "Local %s: %s is a built-in name" % (tk[1], v),
                                            "pick another name"))
                        if v in stored_before and v not in locals_:
                            ln = stored_before[v]
                            probs.append(_p(n, tk[2], tk[3], "warning", "Local %s comes after %s is stored on line %d: "
                                            "that store went to a global variable" % (tk[1], v, ln),
                                            "put Local at the top"))
                        locals_.add(v)
                    elif tk[0] not in ("op",) or tk[1] != ",":
                        probs.append(_p(n, tk[2], tk[3], "error", "Local takes names separated by commas", "Local a,b"))
            elif w == "return":
                if kind == "prgm" and len(words) > 1:
                    probs.append(_p(n, first[2], words[-1][3], "error", "Return with a value in a program: "
                                    "only a function gives a value back", "make it a Func, or Disp the value"))
            elif w in ("cycle", "exit"):
                if not any(s[0] in ("for", "while", "loop") for s in stack):
                    probs.append(_p(n, first[2], first[3], "error", "%s outside a loop" % first[1], ""))
            if in_func and (w in NOT_IN_FUNC or w.rstrip("(") in NOT_IN_FUNC):
                probs.append(_p(n, first[2], first[3], "error", "%s isn't allowed in a function (Invalid in a "
                                "function)" % first[1], "make it a program: Prgm ... EndPrgm"))
            for k, tk in enumerate(words):
                if in_func and tk[0] == "id" and tk[1].lower() in NOT_IN_FUNC_CALLS:
                    probs.append(_p(n, tk[2], tk[3], "error", "%s isn't allowed in a function (it changes the "
                                    "calculator's settings)" % tk[1], "make it a program"))
                if tk[1] in ("\u25ba", "\u25b8", "@>"):
                    nx = words[k + 1] if k + 1 < len(words) else None
                    ok = nx is not None and nx[0] == "id" and nx[2] == tk[3] and (
                        nx[1].lower() in CONVERSIONS_89 or nx[1].startswith("_"))
                    if not ok:
                        probs.append(_p(n, tk[2], nx[3] if nx else tk[3], "error", "%s needs a conversion after it "
                                        "(Bin, Dec, Hex, Polar, Rect, DMS, DD...) or a unit (_ft)" % tk[1],
                                        "10%sBin or 3_m%s_ft" % (tk[1], tk[1])))
            # Stores
            for k, tk in enumerate(words):
                if tk[1] in ("\u2192", "->"):
                    if k + 1 >= len(words):
                        probs.append(_p(n, tk[2], tk[3], "error", "nothing after \u2192 to store into", "value\u2192name"))
                        continue
                    tgt = words[k + 1]
                    if tgt[0] == "id":
                        v = tgt[1].lower().rstrip("(")
                        if v.startswith("_"):
                            continue  # A unit of your own: 3_m\u2192_yd
                        if in_func and v not in locals_:
                            probs.append(_p(n, tgt[2], tgt[3], "error", "%s isn't Local: a function can't store to "
                                            "a global variable" % v, "add Local %s at the top of the function" % v))
                        stored_before.setdefault(v, n)
                        if len(v) > 8:
                            probs.append(_p(n, tgt[2], tgt[3], "error", "%s is %d characters: names are up to 8"
                                            % (tgt[1], len(v)), "shorten it to %s" % v[:8]))
                        elif v in reserved_89():
                            probs.append(_p(n, tgt[2], tgt[3], "error", "%s is a built-in name: it can't be stored "
                                            "into" % tgt[1], "pick another name"))
                    else:
                        probs.append(_p(n, tgt[2], tgt[3], "error", "%r can't be stored into: \u2192 needs a "
                                        "variable name" % tgt[1], "value\u2192name"))
            if len(words) >= 3 and words[0][0] == "id" and words[1][1] == "=" and w not in CONTROL_89 and \
                    not any(tk[1] in ("\u2192", "->") for tk in words) and not words[0][1].endswith("("):
                rhs = "".join(tk[1] for tk in words[2:])
                probs.append(_p(n, words[0][2], words[-1][3], "error", "%s=... compares, it doesn't store "
                                "(the 89 stores with \u2192)" % words[0][1], "%s\u2192%s" % (rhs, words[0][1])))
            if w == "request" and len(words) > 1 and words[1][0] == "str" and len(words[1][1].strip('"')) > 20:
                probs.append(_p(n, words[1][2], words[1][3], "warning", "a Request prompt of %d characters: the "
                                "89 takes 20" % len(words[1][1].strip('"')), "shorten it"))
            _traps_89(words, n, probs, locals_)
            _args_89(words, n, probs, idx)
            prev = w
    for s in stack:
        if s[0] in ("prgm", "func") and kind:
            continue  # Reported as the missing End line above
        probs.append(_p(s[1], s[2], s[3], "error", "%s has no %s" % (_opener_name(s[0]), _closer_name(s[0])),
                        "add %s where the block ends" % _closer_name(s[0])))
    try:
        size = len(cf.program_89_data(text, name or "zz", "zz")[2])
        if size > MAX_BYTES:
            probs.append(_p(1, 0, 1, "error", "the program is too big (%d bytes)" % size, "split it"))
    except ValueError:
        pass
    return probs


def _opener_name(k):
    return {"if": "If ... Then", "for": "For", "while": "While", "loop": "Loop", "try": "Try",
            "dialog": "Dialog", "toolbar": "Toolbar", "custom": "Custom", "prgm": "Prgm",
            "func": "Func"}[k]


def _closer_name(k):
    return {"if": "EndIf", "for": "EndFor", "while": "EndWhile", "loop": "EndLoop", "try": "EndTry",
            "dialog": "EndDlog", "toolbar": "EndTBar", "custom": "EndCustm", "prgm": "EndPrgm",
            "func": "EndFunc"}[k]


def _parens_89(toks, n, probs):
    opened = []
    for tk in toks:
        kind, text, c, e = tk
        if kind == "str" and (len(text) < 2 or not text.endswith('"')):
            probs.append(_p(n, c, e, "error", "the string isn't closed", 'add the closing "'))
        if kind == "op" and text == ":":
            if opened:
                break
            continue
        if kind in ("id", "sym") and text.endswith("(") or (kind == "op" and text in "({["):
            opened.append(tk)
        elif kind == "op" and text in ")}]":
            if not opened:
                probs.append(_p(n, c, e, "error", "a %s with nothing open before it" % text, "remove it"))
            else:
                opened.pop()
    if opened:
        tk = opened[-1]
        probs.append(_p(n, tk[2], tk[3], "error", "%d bracket%s not closed (the 89 wants them all)" % (
            len(opened), "" if len(opened) == 1 else "s"), "add the closing )"))


def _traps_89(words, n, probs, locals_):
    for k, tk in enumerate(words):
        if tk[0] == "id" and tk[1].lower() == "d(":
            probs.append(_p(n, tk[2], tk[3], "warning", "d( typed as letters calls a function named d",
                            "the derivative is @d( (or \u2202()"))
        if tk[0] == "id" and tk[1] == "e" and not (k + 1 < len(words) and words[k + 1][1] == "^") and \
                "e" not in locals_:
            probs.append(_p(n, tk[2], tk[3], "info", "e alone is a variable on the 89", "the constant is e^(1)"))
        if tk[0] == "id" and tk[1].endswith("(") and tk[1][:-1].lower() in locals_ and len(tk[1]) == 2:
            probs.append(_p(n, tk[2], tk[3], "warning", "%s( is a call, not a product (Invalid implied multiply)"
                            % tk[1][:-1], "%s*(" % tk[1][:-1]))


def _args_89(words, n, probs, idx):
    stop = lambda tk: tk[0] == "op" and tk[1] == ":"
    for k, tk in enumerate(words):
        if tk[0] not in ("id", "sym"):
            continue
        e = idx.get(tk[1].lower())
        if e is None or e["name"].strip().lower() in CONTROL_89:
            continue
        if tk[1].endswith("("):
            count, _c, end = _count_call_args_89(words, k, stop)
            p = _args_problem(e, count, n, tk[2], end, False)
            if p:
                probs.append(p)
        elif k == 0 and is_command(e) and len(words) > 1:
            parts = _split_top_89(words[1:])
            p = _args_problem(e, len(parts), n, tk[2], words[-1][3], False)
            if p:
                probs.append(p)


def _count_call_args_89(toks, k, stop):
    depth, commas, empty, end = 1, 0, True, toks[k][3]
    for j in range(k + 1, len(toks)):
        kind, text, col, e = toks[j]
        if stop(toks[j]):
            break
        end = e
        if (kind in ("id", "sym") and text.endswith("(")) or (kind == "op" and text in "({["):
            depth += 1
        elif kind == "op" and text in ")}]":
            depth -= 1
            if depth == 0:
                return (0 if empty else commas + 1), True, e
        elif kind == "op" and text == "," and depth == 1:
            commas += 1
            continue
        empty = False
    return (0 if empty else commas + 1), False, end


def _split_top_89(words):
    parts, cur, depth = [], [], 0
    for tk in words:
        if (tk[0] in ("id", "sym") and tk[1].endswith("(")) or (tk[0] == "op" and tk[1] in "({["):
            depth += 1
        elif tk[0] == "op" and tk[1] in ")}]":
            depth -= 1
        if tk[0] == "op" and tk[1] == "," and depth == 0:
            parts.append(cur)
            cur = []
            continue
        cur.append(tk)
    parts.append(cur)
    return [p for p in parts if p] or []


# ---------------------------------------------------------------------------
# TI-Nspire Python: Python's own compile(), then check_nspire's rules
# ---------------------------------------------------------------------------

class _Checker(check_nspire.Checker):
    """check_nspire's checker, keeping each finding's column"""

    def add(self, level, node_or_line, message, fix):
        super().add(level, node_or_line, message, fix)
        f = self.findings[-1]
        f.col = getattr(node_or_line, "col_offset", None)
        f.end_col = getattr(node_or_line, "end_col_offset", None)
        f.end_line = getattr(node_or_line, "end_lineno", None)


def _check_py(text, name=None):
    probs = []
    lines = text.split("\n")
    raw = text.encode("utf-8")
    sev = {"ERROR": "error", "WARN": "warning"}

    def line_len(n):
        return len(lines[n - 1]) if 0 < n <= len(lines) else 1

    if name is not None and not re.match(r"^[A-Za-z][A-Za-z0-9_]*$", name):
        probs.append(_p(1, 0, 1, "error", "%r can't be the program's name: letters, digits and _, a letter "
                        "first (the .tns and the handheld use it)" % name, "e.g. quadratic"))
    found = []
    check_nspire.check_text_level(raw, found)
    for f in found:
        n = f.line or 1
        col, end = 0, line_len(n)
        if "non-ASCII" in f.message and 0 < n <= len(lines):
            bad = [k for k, ch in enumerate(lines[n - 1]) if ord(ch) > 126 or (ord(ch) < 32 and ch != "\t")]
            if bad:
                col, end = bad[0], bad[-1] + 1
        elif "tab indentation" in f.message and 0 < n <= len(lines):
            l = lines[n - 1]
            end = len(l) - len(l.lstrip())
        probs.append(_p(n, col, end, sev[f.level], f.message, f.fix))
    try:
        tree = compile(text.lstrip("﻿"), "<editor>", "exec", ast.PyCF_ONLY_AST, dont_inherit=True)
    except SyntaxError as e:
        n = e.lineno or 1
        col = max(0, (e.offset or 1) - 1)
        end = (e.end_offset - 1) if getattr(e, "end_offset", None) and e.end_lineno == e.lineno else col + 1
        if 0 < n <= len(lines):
            col = min(col, max(0, len(lines[n - 1]) - 1))
        kind = "indentation" if isinstance(e, IndentationError) else "syntax error"
        probs.append(_p(n, col, max(end, col + 1), "error", "%s: %s" % (kind, e.msg),
                        "fix the syntax (the TI editor's Check Syntax & Save would stop here too)"))
        return probs
    c = _Checker(set())
    c.visit(tree)
    for f in c.findings:
        n = f.line or 1
        col = f.col or 0
        end = f.end_col if f.end_col is not None and f.end_line == f.line else line_len(n)
        level = sev[f.level]
        if re.search(r"is not in TI's documented ti_\w+ menu", f.message):
            level = "error"  # TI's own modules are documented completely: anything else isn't there
        probs.append(_p(n, col, max(end, col + 1), level, f.message, f.fix))
    _py_names(tree, probs)
    _py_indent(text, probs)
    return probs


def _py_indent(text, probs):
    """Indents of 4 spaces (each level): TI's editor indents by 2 in the handheld but files sent
    from the PC read best with 4; a level that isn't a multiple of 4 is usually a slip"""
    import tokenize as _tk
    try:
        for tok in _tk.generate_tokens(io.StringIO(text).readline):
            if tok.type == _tk.INDENT and "\t" not in tok.string and len(tok.string) % 4:
                probs.append(_p(tok.start[0], 0, len(tok.string), "warning", "an indent of %d spaces" % len(tok.string),
                                "indent each level by 4 spaces"))
    except (_tk.TokenError, IndentationError, SyntaxError):
        pass


def _sig_spec(sig, fname):
    return _form_spec(sig, fname + "(") if sig else None


def _py_names(tree, probs):
    """Names used but never set anywhere (a simple, flow-insensitive check), and the number of
    arguments of TI's functions, the built-ins and the file's own functions"""
    defined = set(dir(builtins))
    mod_alias, from_names, own = {}, {}, {}
    star_unknown = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                defined.add(a.asname or a.name.split(".")[0])
                mod_alias[a.asname or a.name.split(".")[0]] = a.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for a in node.names:
                if a.name == "*":
                    names = check_nspire.DOCUMENTED.get(mod)
                    if names:
                        defined.update(names)
                        for nm in names:
                            from_names.setdefault(nm, (mod, nm))
                    else:
                        star_unknown = True
                else:
                    defined.add(a.asname or a.name)
                    from_names[a.asname or a.name] = (mod, a.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(node.name)
            if isinstance(node, ast.FunctionDef):
                own[node.name] = None if node.name in own else node
                args = node.args
                for a in list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs) + \
                        [x for x in (args.vararg, args.kwarg) if x]:
                    defined.add(a.arg)
        elif isinstance(node, ast.Lambda):
            args = node.args
            for a in list(args.args) + [x for x in (args.vararg, args.kwarg) if x]:
                defined.add(a.arg)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            defined.add(node.id)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            defined.update(node.names)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            defined.add(node.name)
    reported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and not star_unknown:
            if node.id not in defined and node.id not in reported:
                reported.add(node.id)
                probs.append(_p(node.lineno, node.col_offset, node.end_col_offset, "error",
                                "%r isn't defined anywhere in the program (NameError)" % node.id,
                                "check the spelling, or set it (or import it) first"))
        if not isinstance(node, ast.Call) or any(isinstance(a, ast.Starred) for a in node.args) or \
                any(k.arg is None for k in node.keywords):
            continue
        f = node.func
        sig = fname = None
        if isinstance(f, ast.Name):
            fname = f.id
            if f.id in own and own[f.id] is not None:
                d = own[f.id].args
                if d.vararg or d.kwonlyargs or d.kwarg:
                    continue
                total = len(d.posonlyargs) + len(d.args)
                lo, hi = total - len(d.defaults), total
                _py_count(node, fname, lo, hi, probs, "def %s" % fname)
                continue
            if f.id in from_names:
                sig = PY_SIGS.get("%s.%s" % from_names[f.id])
                fname = from_names[f.id][1]
            elif f.id in PY_SIGS and f.id != "print" and f.id not in from_names:
                sig = PY_SIGS[f.id]
        elif isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id in mod_alias:
            fname = f.attr
            sig = PY_SIGS.get("%s.%s" % (mod_alias[f.value.id], f.attr))
        spec = _sig_spec(sig, fname) if sig else None
        if spec:
            _py_count(node, fname, spec[0], spec[1], probs, sig)


def _py_count(node, fname, lo, hi, probs, sig):
    n = len(node.args) + len(node.keywords)
    if n < lo:
        probs.append(_p(node.lineno, node.col_offset, node.end_col_offset if node.end_lineno == node.lineno else
                        node.col_offset + len(fname), "error", "%s() needs %s%d argument%s, it has %d (TypeError)" % (
                            fname, "at least " if hi != lo else "", lo, "" if lo == 1 else "s", n), "the syntax is %s" % sig))
    elif hi is not None and n > hi:
        probs.append(_p(node.lineno, node.col_offset, node.end_col_offset if node.end_lineno == node.lineno else
                        node.col_offset + len(fname), "error" if sig.startswith("def ") else "warning",
                        "%s() takes %s%d argument%s, it has %d" % (fname, "at most " if hi != lo else "", hi,
                                                                    "" if hi == 1 else "s", n), "the syntax is %s" % sig))


# ---------------------------------------------------------------------------
# Python: what the editor offers (names and signatures from TI's Python guidebook)
# ---------------------------------------------------------------------------

PY_SIGS = {
    "ti_draw.draw_line": "draw_line(x1,y1,x2,y2)", "ti_draw.draw_rect": "draw_rect(x,y,width,height)",
    "ti_draw.fill_rect": "fill_rect(x,y,width,height)", "ti_draw.draw_circle": "draw_circle(x,y,radius)",
    "ti_draw.fill_circle": "fill_circle(x,y,radius)", "ti_draw.draw_text": "draw_text(x,y,text)",
    "ti_draw.draw_arc": "draw_arc(x,y,width,height,start_angle,arc_angle)",
    "ti_draw.fill_arc": "fill_arc(x,y,width,height,start_angle,arc_angle)",
    "ti_draw.draw_poly": "draw_poly(x_list,y_list)", "ti_draw.fill_poly": "fill_poly(x_list,y_list)",
    "ti_draw.plot_xy": "plot_xy(x,y[,shape])", "ti_draw.clear": "clear()",
    "ti_draw.clear_rect": "clear_rect(x,y,width,height)", "ti_draw.set_color": "set_color(r,g,b)",
    "ti_draw.set_pen": "set_pen(size,style)", "ti_draw.set_window": "set_window(xmin,xmax,ymin,ymax)",
    "ti_draw.get_screen_dim": "get_screen_dim()", "ti_draw.use_buffer": "use_buffer()",
    "ti_draw.paint_buffer": "paint_buffer()",
    "ti_system.recall_value": "recall_value(name)", "ti_system.store_value": "store_value(name,value)",
    "ti_system.recall_list": "recall_list(name)", "ti_system.store_list": "store_list(name,list)",
    "ti_system.eval_function": "eval_function(name,value)", "ti_system.get_platform": "get_platform()",
    "ti_system.get_key": "get_key([wait])", "ti_system.get_mouse": "get_mouse()",
    "ti_system.clear_history": "clear_history()", "ti_system.get_time_ms": "get_time_ms()",
    "ti_plotlib.cls": "cls()", "ti_plotlib.grid": "grid(xscl,yscl[,style])",
    "ti_plotlib.window": "window(xmin,xmax,ymin,ymax)", "ti_plotlib.auto_window": "auto_window(x_list,y_list)",
    "ti_plotlib.axes": "axes([mode])", "ti_plotlib.labels": "labels(x_label,y_label[,x,y])",
    "ti_plotlib.title": "title(text)", "ti_plotlib.show_plot": "show_plot()",
    "ti_plotlib.color": "color(r,g,b)", "ti_plotlib.scatter": "scatter(x_list,y_list[,mark])",
    "ti_plotlib.plot": "plot(x_list,y_list[,mark])", "ti_plotlib.line": "line(x1,y1,x2,y2[,mode])",
    "ti_plotlib.lin_reg": "lin_reg(x_list,y_list[,disp,row])", "ti_plotlib.pen": "pen(size,style)",
    "ti_plotlib.text_at": "text_at(row,text[,align])",
    "math.sqrt": "sqrt(x)", "math.exp": "exp(x)", "math.pow": "pow(x,y)", "math.log": "log(x[,base])",
    "math.fabs": "fabs(x)", "math.fmod": "fmod(x,y)", "math.floor": "floor(x)", "math.ceil": "ceil(x)",
    "math.trunc": "trunc(x)", "math.sin": "sin(x)", "math.cos": "cos(x)", "math.tan": "tan(x)",
    "math.asin": "asin(x)", "math.acos": "acos(x)", "math.atan": "atan(x)", "math.atan2": "atan2(y,x)",
    "math.radians": "radians(x)", "math.degrees": "degrees(x)", "math.frexp": "frexp(x)",
    "cmath.rect": "rect(r,phi)", "cmath.polar": "polar(z)", "cmath.phase": "phase(z)",
    "cmath.sqrt": "sqrt(z)", "cmath.exp": "exp(z)", "cmath.log": "log(z)",
    "random.random": "random()", "random.uniform": "uniform(a,b)", "random.randint": "randint(a,b)",
    "random.choice": "choice(sequence)", "random.randrange": "randrange(start,stop[,step])",
    "random.seed": "seed(x)", "time.sleep": "sleep(seconds)", "time.ticks_ms": "ticks_ms()",
    "time.ticks_diff": "ticks_diff(new,old)",
    "print": "print(value,...[,sep][,end])", "input": "input([prompt])", "range": "range([start,]stop[,step])",
    "len": "len(s)", "int": "int(x[,base])", "float": "float([x])", "str": "str([x])", "round": "round(x[,digits])",
    "abs": "abs(x)", "min": "min(a,b,...)", "max": "max(a,b,...)", "sum": "sum(iterable[,start])",
    "sorted": "sorted(iterable[,key,reverse])", "list": "list([iterable])", "complex": "complex([real,imag])",
    "divmod": "divmod(a,b)", "pow": "pow(x,y[,mod])", "bin": "bin(n)", "hex": "hex(n)", "oct": "oct(n)",
    "chr": "chr(n)", "ord": "ord(c)", "enumerate": "enumerate(iterable[,start])", "zip": "zip(a,b,...)",
}
PY_BUILTINS = sorted(n for n in dir(builtins) if not n.startswith("_") and n.islower() and
                     n not in check_nspire.BUILTINS_ERRORS)


def _py_modules():
    return {m: sorted(v) if v else [] for m, v in check_nspire.DOCUMENTED.items()}


# ---------------------------------------------------------------------------
# Highlighting
# ---------------------------------------------------------------------------

# Colour classes, as VS Code's Dark+ theme names them: control flow (keyword.control),
# declarations (storage), functions (entity.name.function / support.function), variables,
# system variables (support.variable: L1, [A], Str1, Ans), strings, numbers, comments, symbols
CONTROL_84 = {"If", "Then", "Else", "For(", "While", "Repeat", "End", "Return", "Stop", "Lbl", "Goto",
              "Menu(", "IS>(", "DS<(", "Pause", " and ", " or ", " xor ", "not("}
STORAGE_84 = {"prgm", "DelVar", "Archive", "UnArchive", "ClrList", "ClrAllLists", "SetUpEditor"}
CONTROL_89 = {"if", "then", "else", "elseif", "endif", "for", "endfor", "while", "endwhile", "loop",
              "endloop", "try", "endtry", "return", "stop", "cycle", "exit", "lbl", "goto", "and", "or",
              "xor", "not", "clrerr", "passerr"}
STORAGE_89 = {"prgm", "endprgm", "func", "endfunc", "local", "define", "dialog", "enddlog", "toolbar",
              "endtbar", "custom", "endcustm", "delvar"}
CONTROL_PY = {"if", "elif", "else", "for", "while", "return", "import", "from", "as", "try", "except",
              "finally", "raise", "break", "continue", "pass", "with", "yield", "assert", "del", "in",
              "is", "not", "and", "or"}
STORAGE_PY = {"def", "class", "lambda", "global", "nonlocal", "True", "False", "None"}
TAGS = ("control", "storage", "builtin", "variable", "sysvar", "string", "number", "comment", "symbol")
_SYMBOL_CHARS = set("→≤≥≠√πθ²³⁻¹►▸∫∂"
                    "Σ∞∠ᴇℯ\U0001d456°⏨")
_PC_SYMBOLS = {"->", "<=", ">=", "!=", "/=", "^2", "^3", "^-1", "pi", "theta", "~", "@", "@>", "@i", "@angle"}


def _is_sysvar_84(b):
    return b[0] in (0x5C, 0x5D, 0x5E, 0x60, 0x61, 0x62, 0x63, 0xAA, 0xEB, 0x3C) or b in (b"\x72",)


def highlight(language, text):
    """[(tag, line, col, end)] for the editor's colours; tag is one of TAGS"""
    lang = lang_of(language)
    lines = text.replace("\r\n", "\n").split("\n")
    out = []
    if lang == "ti84":
        names = _lex84_tables()["names"]
        for n, raw in enumerate(lines, 1):
            off = 1 if raw.startswith(":") else 0
            toks = lex_84(raw[off:])
            words = [t for t in toks if t[0] != "space"]
            for kind, t, c, e in toks:
                c, e = c + off, e + off
                if kind == "str":
                    out.append(("comment" if len(words) == 1 else "string", n, c, e))  # A lone string: a comment
                elif kind == "num":
                    out.append(("number", n, c, e))
                elif kind == "tok":
                    b = names.get(t, b"")
                    s = t.strip()
                    if t in CONTROL_84 or s in CONTROL_84:
                        out.append(("control", n, c, e))
                    elif s in STORAGE_84 or t.startswith("prgm"):
                        out.append(("storage", n, c, e))
                    elif t in _PC_SYMBOLS or (len(s) <= 3 and any(ch in _SYMBOL_CHARS for ch in s)):
                        out.append(("symbol", n, c, e))
                    elif b and _is_sysvar_84(b):
                        out.append(("sysvar", n, c, e))
                    elif len(b) == 1 and 0x41 <= b[0] <= 0x5B:
                        out.append(("variable", n, c, e))
                    elif len(s) > 1 and _entry_84(t) is not None:
                        out.append(("builtin", n, c, e))
    elif lang == "ti89":
        idx = _ref_index("ti89")
        for n, raw in enumerate(lines, 1):
            for kind, t, c, e in lex_89(raw):
                low = t.lower()
                if kind == "str":
                    out.append(("string", n, c, e))
                elif kind == "comment":
                    out.append(("comment", n, c, e))
                elif kind == "num":
                    out.append(("number", n, c, e))
                elif kind == "sym":
                    out.append(("symbol" if len(t) <= 2 or t.startswith("@") and t[1:].isalpha() is False
                                or t in _PC_SYMBOLS else "builtin", n, c, e))
                elif kind == "id":
                    if low in CONTROL_89:
                        out.append(("control", n, c, e))
                    elif low in STORAGE_89:
                        out.append(("storage", n, c, e))
                    elif low in SYS_VARS_89 or low.startswith("_"):
                        out.append(("sysvar", n, c, e))
                    elif low in idx and (len(t) > 1 or low.endswith("(")):
                        out.append(("builtin", n, c, e))
                    else:
                        out.append(("variable", n, c, e))
    else:
        out = _highlight_py(lines)
    return out


_PY_TOKEN = re.compile(r"""(?P<comment>\#.*)|(?P<string>[rRbBuU]?(?:'''|\"\"\"|'|"))|(?P<num>\b\d[\d_]*\.?\d*(?:[eE][-+]?\d+)?j?\b)|(?P<name>[A-Za-z_]\w*)""")


def _highlight_py(lines):
    out = []
    mods = set(check_nspire.DOCUMENTED)
    known = set(PY_BUILTINS) | {k.split(".")[-1] for k in PY_SIGS}
    in_triple = None
    for n, line in enumerate(lines, 1):
        i = 0
        if in_triple:
            j = line.find(in_triple)
            if j < 0:
                out.append(("string", n, 0, len(line)))
                continue
            out.append(("string", n, 0, j + 3))
            i = j + 3
            in_triple = None
        while i < len(line):
            m = _PY_TOKEN.search(line, i)
            if not m:
                break
            if m.group("comment"):
                out.append(("comment", n, m.start(), len(line)))
                break
            if m.group("string"):
                q = m.group("string").lstrip("rRbBuU")
                j = line.find(q, m.end())
                while j > 0 and len(q) == 1 and line[j - 1] == "\\":
                    j = line.find(q, j + 1)
                if j < 0:
                    if len(q) == 3:
                        in_triple = q
                    out.append(("string", n, m.start(), len(line)))
                    break
                out.append(("string", n, m.start(), j + len(q)))
                i = j + len(q)
                continue
            if m.group("num"):
                out.append(("number", n, m.start(), m.end()))
            elif m.group("name"):
                w = m.group("name")
                after = line[m.end():m.end() + 1]
                if w in CONTROL_PY:
                    out.append(("control", n, m.start(), m.end()))
                elif w in STORAGE_PY:
                    out.append(("storage", n, m.start(), m.end()))
                elif w in mods:
                    out.append(("sysvar", n, m.start(), m.end()))
                elif w in known or after == "(":
                    out.append(("builtin", n, m.start(), m.end()))
                else:
                    out.append(("variable", n, m.start(), m.end()))
            i = m.end()
    return out


def bracket_match(text, index):
    """The bracket matching the one at index (or just before it): (a, b) offsets, or None.
    A plain count: brackets inside strings count too."""
    pairs = {"(": ")", "[": "]", "{": "}"}
    back = {v: k for k, v in pairs.items()}
    for at in (index, index - 1):
        if 0 <= at < len(text) and (text[at] in pairs or text[at] in back):
            break
    else:
        return None
    ch = text[at]
    if ch in pairs:
        step, want, mine = 1, pairs[ch], ch
    else:
        step, want, mine = -1, back[ch], ch
    depth, i = 0, at
    while 0 <= i < len(text) and abs(i - at) < 4000:  # Up to a few thousand characters away
        c = text[i]
        if c == mine:
            depth += 1
        elif c == want:
            depth -= 1
            if depth == 0:
                return (at, i) if step == 1 else (i, at)
        i += step
    return None


# ---------------------------------------------------------------------------
# Display-only indentation for TI-Basic (the calculator ignores it; files stay clean)
# ---------------------------------------------------------------------------

def block_depths(language, text):
    """[depth] per line: how far the editor shows each line indented (TI-Basic only; Python
    keeps its own indentation, so all 0)"""
    lang = lang_of(language)
    lines = text.replace("\r\n", "\n").split("\n")
    if lang == "python":
        return [0] * len(lines)
    depth, out, prev = 0, [], None
    for raw in lines:
        line = raw[1:] if raw.startswith(":") else raw
        heads = [_head_word(lang, s) for s in _split_colon(lang, line)]
        heads = [h for h in heads if h]
        d = depth
        if heads and heads[0] in ("end", "else", "elseif") or (heads and heads[0] in CLOSE_89 and lang == "ti89"):
            d = max(0, depth - 1)
        if lang == "ti89" and heads and heads[0] in ("prgm", "func", "endprgm", "endfunc"):
            d = 0
        out.append(d)
        for h in heads:
            if lang == "ti84":
                if h in ("for(", "while", "repeat") or (h == "then"):
                    depth += 1
                elif h == "end":
                    depth = max(0, depth - 1)
            else:
                if h in OPEN_89 and h not in ("prgm", "func") or h == "ifthen":
                    depth += 1
                elif h in CLOSE_89 and h not in ("endprgm", "endfunc"):
                    depth = max(0, depth - 1)
            prev = h
    return out


def _split_colon(lang, line):
    out, cur, in_str = [], "", False
    for ch in line:
        if ch == '"':
            in_str = not in_str
        if ch == ":" and not in_str:
            out.append(cur)
            cur = ""
        else:
            cur += ch
        if lang == "ti89" and ch == COPYRIGHT and not in_str:
            break
    out.append(cur)
    return out


def _head_word(lang, s):
    s = s.strip()
    if lang == "ti84":
        for w in ("For(", "While", "Repeat", "Then", "End", "Else"):
            if s.startswith(w) and (w != "End" or s == "End"):
                return w.lower()
        return None
    m = re.match(r"[A-Za-z]+", s)
    if not m:
        return None
    w = m.group(0).lower()
    if w == "if" and re.search(r"(?i)\bthen\s*$", re.sub(r'"[^"]*"', '""', s.split(COPYRIGHT)[0])):
        return "ifthen"
    return w


# ---------------------------------------------------------------------------
# Autocomplete, signature hints, hover
# ---------------------------------------------------------------------------

def word_before(language, text, index):
    """The word being typed that ends at index: what autocomplete matches"""
    lang = lang_of(language)
    s = text[:index]
    if lang == "python":
        m = re.search(r"[A-Za-z_][\w.]*$", s)
    elif lang == "ti89":
        m = re.search(r"[@A-Za-z_\u0370-\u03ff][A-Za-z0-9_\u0370-\u03ff>]*$", s)
    else:
        m = re.search(r"[A-Za-z|][A-Za-z0-9\-\u25ba>]*$", s)
    return m.group(0) if m else ""


def variables_in(language, text):
    """Names the program sets (for autocomplete)"""
    lang = lang_of(language)
    out = set()
    if lang == "ti84":
        for m in re.finditer(r"(?:\u2192|->)\s*([A-Z\u03b8]|Str\d|\|L[A-Z\u03b8][A-Z0-9\u03b8]{0,4}|"
                             r"\u029f[A-Z\u03b8][A-Z0-9\u03b8]{0,4}|L[1-6])", text):
            out.add(m.group(1))
        for m in re.finditer(r"\b(?:Prompt|Input)\b[^\n:]*", text):
            out.update(re.findall(r"(?<![A-Za-z\"])([A-Z\u03b8])(?![a-z])", m.group(0).split('"')[-1]))
        for m in re.finditer(r"For\(([A-Z\u03b8])", text):
            out.add(m.group(1))
    elif lang == "ti89":
        for m in re.finditer(r"(?:\u2192|->)\s*([A-Za-z][A-Za-z0-9_]{0,7})", text):
            out.add(m.group(1))
        for m in re.finditer(r"(?im)^\s*:?\s*Local\s+([^\n:\u00a9]*)", text):
            out.update(v.strip() for v in m.group(1).split(",") if v.strip())
        m = _HEAD.match(text.lstrip().split("\n")[0]) if text.strip() else None
        if m:
            out.update(_arg_names(m.group(2)))
        for m in re.finditer(r"(?i)\bFor\s+([A-Za-z][A-Za-z0-9_]*)", text):
            out.add(m.group(1))
    else:
        for m in re.finditer(r"\b([A-Za-z_]\w*)\s*=(?!=)", text):
            out.add(m.group(1))
        for m in re.finditer(r"\bdef\s+([A-Za-z_]\w*)\s*\(([^)]*)", text):
            out.add(m.group(1))
            out.update(a.split("=")[0].strip() for a in m.group(2).split(",") if a.strip())
        for m in re.finditer(r"\bfor\s+([A-Za-z_]\w*)", text):
            out.add(m.group(1))
        for m in re.finditer(r"\bimport\s+([\w, ]+)", text):
            out.update(x.split(" as ")[-1].strip() for x in m.group(1).split(","))
    out.discard("")
    return sorted(out)


def completions(language, text, index, limit=60):
    """The autocomplete list for the word ending at `index`: [{label, insert, kind, detail}],
    best first. kind: "command", "keyword", "variable", "module". Empty when there is no word."""
    lang = lang_of(language)
    word = word_before(lang, text, index)
    if not word:
        return []
    low = word.lower()
    items = []
    seen = set()

    def add(label, insert, kind, detail, rank):
        if label in seen or label == word:
            return
        seen.add(label)
        items.append((rank, len(label), label.lower(), {"label": label, "insert": insert, "kind": kind,
                                                         "detail": detail}))

    if lang in ("ti84", "ti89"):
        ref = reference.load(lang)
        for e in ref.get("entries", []):
            for n in (e["name"], e.get("pc_spelling")):
                if not n:
                    continue
                s = n.strip()
                if s.lower().startswith(low):
                    rank = 0 if s.startswith(word) else 1
                    add(s, s, "keyword" if e["name"] in CONTROL_84 or s.lower() in CONTROL_89 else "command",
                        e.get("syntax", ""), rank)
        for v in variables_in(lang, text):
            if v.lower().startswith(low):
                add(v, v, "variable", "a variable in this program", 2 if not v.startswith(word) else 0)
    else:
        mods = _py_modules()
        if "." in word:
            mod, _, part = word.rpartition(".")
            for name in mods.get(mod, []):
                if name.lower().startswith(part.lower()):
                    full = "%s.%s" % (mod, name)
                    add(name, name, "command", PY_SIGS.get(full, ""), 0 if name.startswith(part) else 1)
            items.sort(key=lambda t: t[:3])
            return [t[3] for t in items[:limit]]
        for k in keyword.kwlist:
            if k.lower().startswith(low):
                add(k, k, "keyword", "", 0 if k.startswith(word) else 1)
        for m in mods:
            if m.startswith(low):
                add(m, m, "module", "TI's %s module" % m if m.startswith("ti_") else "module", 0)
        for b in PY_BUILTINS:
            if b.startswith(low):
                add(b, b, "command", PY_SIGS.get(b, "built in"), 1)
        imported_star = re.findall(r"from\s+(\w+)\s+import\s+\*", text)
        imported = re.findall(r"from\s+(\w+)\s+import\s+([\w, ]+)", text)
        for mod in imported_star:
            for name in mods.get(mod, []):
                if name.startswith(low):
                    add(name, name, "command", PY_SIGS.get("%s.%s" % (mod, name), mod), 0)
        for mod, names in imported:
            for name in (x.strip() for x in names.split(",")):
                if name and name.startswith(low):
                    add(name, name, "command", PY_SIGS.get("%s.%s" % (mod, name), mod), 0)
        for v in variables_in(lang, text):
            if v.startswith(low) or v.lower().startswith(low):
                add(v, v, "variable", "a name in this program", 0 if v.startswith(word) else 2)
    items.sort(key=lambda t: t[:3])
    return [t[3] for t in items[:limit]]


def _syntax_args(syntax):
    """A syntax line -> (the text before the first argument, [(start, end) of each argument])"""
    i = syntax.find("(")
    if i < 0:
        i = syntax.find(" ")
        if i < 0:
            return syntax, []
    spans, depth, start, in_str = [], 0, i + 1, False
    for j in range(i + 1, len(syntax)):
        ch = syntax[j]
        if ch == '"':
            in_str = not in_str
        if in_str:
            continue
        if ch in "({":
            depth += 1
        elif ch in ")}":
            if depth == 0:
                spans.append((start, j))
                return syntax[:i + 1], spans
            depth -= 1
        elif ch == ":" and depth == 0:
            spans.append((start, j))
            return syntax[:i + 1], spans
        elif ch == "," and depth == 0:
            spans.append((start, j))
            start = j + 1
    spans.append((start, len(syntax)))
    return syntax[:i + 1], spans


def _entry_for_name(lang, name, text_before=""):
    """Reference entry (or Python signature) for a call's name"""
    if lang == "ti84":
        e = _entry_84(name)
        return (e["name"], e["forms"] if e.get("forms") else [e["syntax"]], e) if e else None
    if lang == "ti89":
        e = _ref_index("ti89").get(name.lower())
        return (e["name"], e["forms"] if e.get("forms") else [e["syntax"]], e) if e else None
    base = name.rstrip("(")
    sig = PY_SIGS.get(base)
    if sig is None and "." in base:
        mod, _, fn = base.rpartition(".")
        alias = re.search(r"import\s+(\w+)\s+as\s+%s\b" % re.escape(mod), text_before)
        sig = PY_SIGS.get("%s.%s" % (alias.group(1) if alias else mod, fn))
    if sig is None:
        for m in re.findall(r"from\s+(\w+)\s+import", text_before):
            sig = PY_SIGS.get("%s.%s" % (m, base))
            if sig:
                break
    if sig is None:
        dm = re.search(r"def\s+%s\s*\(([^)]*)\)" % re.escape(base), text_before)
        if dm:
            sig = "%s(%s)" % (base, dm.group(1).replace(" ", ""))
    return (base, [sig], None) if sig else None


def signature_at(language, text, index):
    """The command the cursor is inside: {name, syntax, arg (0-based), span (start, end) of that
    argument in syntax, or None}, or None outside any known command"""
    lang = lang_of(language)
    s = text[:index]
    line_start = s.rfind("\n") + 1
    seg = s[line_start:]
    # The statement: from the last ':' outside strings (TI-Basic)
    if lang != "python":
        in_str, cut = False, 0
        for i, ch in enumerate(seg):
            if ch == '"':
                in_str = not in_str
            elif ch == ":" and not in_str:
                cut = i + 1
            elif lang == "ti84" and (ch == "\u2192" or seg.startswith("->", i)) and not in_str:
                cut = i + (1 if ch == "\u2192" else 2)
        seg = seg[cut:]
    # Innermost open bracket, counting commas at its level
    depth_commas = []  # stack of [open position, commas]
    in_str = False
    q = None
    for i, ch in enumerate(seg):
        if lang == "python":
            if q:
                if ch == q:
                    q = None
                continue
            if ch in "'\"":
                q = ch
                continue
            if ch == "#":
                break
        else:
            if ch == '"':
                in_str = not in_str
                continue
            if in_str:
                continue
            if lang == "ti89" and ch == COPYRIGHT:
                return None
        if ch in "([{":
            depth_commas.append([i, 0, ch])
        elif ch in ")]}":
            if depth_commas:
                depth_commas.pop()
        elif ch == "," and depth_commas:
            depth_commas[-1][1] += 1
    in_str_now = in_str or bool(q)
    while depth_commas:
        pos, commas, br = depth_commas.pop()
        if br != "(":
            continue
        before = seg[:pos + 1]
        if lang == "python":
            m = re.search(r"([A-Za-z_][\w.]*)\($", before)
        elif lang == "ti89":
            m = re.search(r"([@A-Za-z_\u0370-\u03ff\u221a\u222b\u2202\u03a3][A-Za-z0-9_>]*)\($", before)
        else:
            m = re.search(r"([A-Za-z\u221a\u00b3\u23e8\u222b\u03a3][A-Za-z0-9\u207b\u00b9\-+\u25ba>_]*\($|[\u221a]\($)", before)
        if not m:
            continue
        name = m.group(1)
        if lang != "python" and not name.endswith("("):
            name += "("
        if lang == "ti84" and name.endswith("(("):
            name = name[:-1]
        hit = _entry_for_name(lang, name if lang != "python" else name, text[:index])
        if hit is None and lang == "ti84":  # The longest token that ends at the bracket
            for k in range(1, len(before)):
                if _entry_84(before[-k:]) is not None and before[-k:].endswith("("):
                    hit = _entry_for_name(lang, before[-k:])
            if hit is None:
                continue
        if hit is None:
            continue
        return _sig_result(hit, commas, in_str_now)
    # A command at the statement's start that takes arguments without brackets (Disp, For on the 89)
    st = seg.lstrip()
    if lang == "ti89":
        m = re.match(r"([A-Za-z]+)\s(.*)$", st)
        if m:
            hit = _entry_for_name(lang, m.group(1))
            if hit:
                return _sig_result(hit, _commas_top(m.group(2)), in_str_now)
    elif lang == "ti84":
        m = re.match(r"([A-Z][A-Za-z\-]+) (.*)$", st)
        if m:
            hit = _entry_for_name(lang, m.group(1) + " ") or _entry_for_name(lang, m.group(1))
            if hit:
                return _sig_result(hit, _commas_top(m.group(2)), in_str_now)
    return None


def _commas_top(s):
    depth, n, in_str = 0, 0, False
    for ch in s:
        if ch == '"':
            in_str = not in_str
        elif in_str:
            continue
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == "," and depth == 0:
            n += 1
    return n


def _sig_result(hit, commas, in_str):
    name, forms, entry = hit
    best = None
    for f in forms:
        _pre, spans = _syntax_args(f)
        if commas < len(spans) or ("..." in f):
            best = (f, spans)
            break
    if best is None:
        f = forms[0]
        best = (f, _syntax_args(f)[1])
    f, spans = best
    span = spans[commas] if commas < len(spans) else (spans[-1] if spans and "..." in f else None)
    return {"name": name, "syntax": f, "arg": commas, "span": span, "summary": (entry or {}).get("summary", "")}


def hover_at(language, text, index):
    """What a tooltip over the code at index shows: {name, syntax, summary} or None"""
    lang = lang_of(language)
    if lang in ("ti84", "ti89"):
        e = reference.entry_at(lang, text, index)
        if e is None:
            return None
        return {"name": e["name"], "syntax": "\n".join(e.get("forms") or [e["syntax"]]),
                "summary": e.get("summary", "")}
    a = index
    while a > 0 and (text[a - 1].isalnum() or text[a - 1] in "_."):
        a -= 1
    b = index
    while b < len(text) and (text[b].isalnum() or text[b] == "_"):
        b += 1
    word = text[a:b]
    if not word:
        return None
    hit = _entry_for_name("python", word, text)
    if hit is None:
        mod = word.split(".")[0]
        if mod in check_nspire.DOCUMENTED:
            return {"name": mod, "syntax": "import %s" % mod, "summary": "TI's %s module" % mod}
        return None
    return {"name": hit[0], "syntax": hit[1][0], "summary": ""}


# ---------------------------------------------------------------------------
# Instructions for chat AIs (ChatGPT, Gemini, Claude in the browser), per language
# ---------------------------------------------------------------------------

AI_RULES = {
    "ti84": {
        "calc": "a TI-84 Plus CE (OS 5.4, no Python)",
        "lang": "TI-84 Plus CE TI-Basic",
        "name": "The first line of the code block is a comment line with the program name, like "
                "\"QUAD: ROOTS OF AX^2+BX+C. The name is up to 8 capitals A-Z or digits (or theta), a "
                "letter first.",
        "spell": ["-> for the store arrow (5->A), <= >= != for the comparisons",
                  "sqrt( cbrt( pi theta ^2 ^3 ^-1 e^( 10^(",
                  "1.5E-3 for the EE key (E right after a digit); -5 at the start or after an operator is the negative sign",
                  "L1 to L6 for lists, |LNAME for named lists, [A] to [J] matrices, Str0-Str9 strings, Y0-Y9 functions",
                  ">Frac >Dec R>Pr( for the \u25ba arrow; @ for the imaginary i"],
        "rules": ["Variables are single capital letters A-Z and theta, all global; there are no local variables "
                  "and no multi-letter names (AB is A times B)",
                  "Commands are case-sensitive and spelt as the calculator shows them: Disp, Input, Prompt, Output(, "
                  "ClrHome, If, Then, Else, End, For(, While, Repeat, Lbl, Goto, Menu(, Pause, Stop, getKey",
                  "Every block (If ... Then, For(, While, Repeat) closes with End",
                  "No lower case letters outside strings (a misspelt command turns into letters: ERR:SYNTAX)",
                  "and, or, xor need spaces around them; = compares, -> stores",
                  "X^23 is X squared times 3: write X^(23)",
                  "Never Goto out of a loop or an If ... Then block (ERR:MEMORY)",
                  "There are no comments: a string on its own line works as one",
                  "Home screen 10 rows by 26 columns; keep Disp text short",
                  "No tabs; no hex/binary, units or CAS (write routines, use solve( fnInt( nDeriv( for numbers)"],
    },
    "ti89": {
        "calc": "a TI-89 Titanium (AMS 3.10)",
        "lang": "TI-89 Titanium TI-Basic",
        "name": "The first line of the code block is name() or name(a,b), then Prgm ... EndPrgm (or Func ... "
                "EndFunc for a function). The name is up to 8 lower case letters, digits or _, a letter first, and "
                "not a built-in name (log, solve) or system variable (xmin, ok).",
        "spell": ["-> for the store arrow, <= >= != for the comparisons",
                  "sqrt( pi theta e^(; 1.5E-3 for the EE key",
                  "@> for the conversion arrow \u25ba (10@>Bin, 3_m@>_ft)",
                  "@int( for \u222b(, @d( for the derivative, @sum( for \u03a3(, @angle for \u2220, @i for the imaginary unit",
                  "or the 89's own Unicode symbols: \u2192 \u2264 \u2265 \u2260 \u221a( \u03c0 \u222b( \u2202( \u03a3( \u25ba \U0001d456"],
        "rules": ["Blocks close with EndIf, EndFor, EndWhile, EndLoop, EndTry, EndDlog, EndTBar (never plain End)",
                  "If ... Then goes on one line; ElseIf ... Then; Else",
                  "Local a,b,c for every variable that need not stay",
                  "In a Func every variable stored to (For counters too) must be Local or an argument, and a "
                  "function may not use Disp, Input, dialogs, setMode( or setFold(",
                  "Comments start with \u00a9 and run to the end of the line",
                  "Multiply explicitly: a*x and x*(x+1), never ax or x(x+1)",
                  "e alone is a variable: the constant is e^(1); i alone is a variable",
                  "Request prompts are at most 20 characters; convert answers with expr( inside Try ... EndTry",
                  "Inside strings nothing is converted: write 0.000001, not 1E-6",
                  "Names up to 8 characters; no tabs, curly quotes or long dashes"],
    },
    "python": {
        "calc": "a TI-Nspire CX II (OS 6, TI's MicroPython)",
        "lang": "TI-Nspire CX II Python",
        "name": "The first line of the code block is a comment with the file name, like # quadratic.py (lower "
                "case letters, digits and _, a letter first).",
        "spell": ["Plain ASCII only: write pi, <=, sqrt(), ** (no \u03c0, \u2264, \u221a, curly quotes or long dashes)"],
        "rules": ["Only these modules: math, cmath, random, time, ti_system, ti_draw, ti_plotlib, ti_image "
                  "(ti_hub, ti_rover with TI's hardware). No numpy, sympy, matplotlib, os, re, json, itertools",
                  "No f-strings: print(\"x =\", x) or \"{} {}\".format(a, b)",
                  "No walrus :=, match/case, type hints, async/await, underscores in numbers, from __future__",
                  "No open() or files; no ljust, rjust, zfill, partition, removeprefix",
                  "4-space indents, no tabs",
                  "Put the main code at top level (no if __name__ == \"__main__\": guard)",
                  "Keep lists to a few thousand items (about 2 MB heap) and recursion shallow",
                  "ti_draw screen is 318 x 212, (0,0) top left; end a drawing with ti_system.get_key(1)",
                  "Output lines of about 30 characters read well"],
    },
}


def ai_instructions(language):
    """A short prompt to paste into a chat AI before asking for a program for this language"""
    lang = lang_of(language)
    r = AI_RULES[lang]
    out = ["You are writing a program for %s in %s. I send it with CalcSuite, a PC app; its checker "
           "and converter accept the rules below." % (r["calc"], r["lang"]), "",
           "Spellings to use (a PC keyboard has no calculator symbols):"]
    out += ["- " + s for s in r["spell"]]
    out += ["", "The language:"]
    out += ["- " + s for s in r["rules"]]
    out += ["", "How to answer:",
            "- Output only the program, in one code block, nothing before or after it.",
            "- " + r["name"],
            "- Use only commands the calculator really has; if you aren't sure one exists, use a simpler one.",
            "- If I paste errors from CalcSuite's checker (line numbers and messages), fix them and send the "
            "whole program again."]
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Templates for File > New
# ---------------------------------------------------------------------------

TEMPLATES = {
    "ti84": '"NEW: WHAT IT DOES\nClrHome\nPrompt A,B\nA+B\u2192C\nDisp "A+B=",C\n',
    "ti89": "newprog()\nPrgm\n\u00a9 newprog: what it does\nLocal a,b\nClrIO\nRequest \"a\",a\n"
            "expr(a)\u2192a\nDisp \"2a =\",2*a\nPause\nDispHome\nEndPrgm\n",
    "python": "# newprog.py: what it does\nfrom ti_system import *\n\n\ndef main():\n"
              "    a = float(input(\"a? \"))\n    print(\"2a =\", 2 * a)\n\n\nmain()\n",
}


def program_name(language, text, path=None):
    """The program's name: the 89's first line, else the file name made into one"""
    lang = lang_of(language)
    stem = os.path.splitext(os.path.basename(path))[0] if path else ""
    if lang == "ti89":
        first = next((l for l in text.split("\n") if l.strip()), "")
        m = _HEAD.match(first.lstrip(":"))
        if m:
            return m.group(1).lower()
        return cf.name_89_from(stem) if stem else None
    if lang == "ti84":
        return cf.name_84_from(stem) if stem else None
    s = re.sub(r"[^a-z0-9_]", "", stem.lower())
    return s or None
