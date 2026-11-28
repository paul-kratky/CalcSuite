# SPDX-License-Identifier: MIT
"""The function reference for each calculator: tools/reference/{ti84,ti89,nspire}.json.

Pure: no window, no calculator. Loads the reference, searches it, formats a syntax card, finds
the commands a piece of code uses (for hover hints), and says what Insert would type.

    import reference
    ref = reference.load("ti89")
    for e in reference.search(ref, "int"):
        print(e["name"], e["syntax"])
    print(reference.card(e))
"""

import json
import os
import re
import sys

SLUGS = ("ti84", "ti89", "nspire")
# The order the category filter shows them in
CATEGORIES = ("Math", "Calculus/CAS", "Algebra", "Lists", "Matrices", "Strings", "Statistics",
              "Probability", "Complex", "Programming (control flow)", "I/O", "Graph/Draw",
              "Conversions/Units", "Base/Logic", "Settings/Mode", "Memory/Vars", "Finance")
_CACHE = {}


def folder():
    """Where the JSON files are: next to this file, or inside the packaged app"""
    base = getattr(sys, "_MEIPASS", None)
    if base and os.path.isdir(os.path.join(base, "reference")):
        return os.path.join(base, "reference")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "reference")


def load(slug, path=None):
    """The reference for a calculator ("ti84", "ti89", "nspire"): the JSON document, with
    "entries" (a list of dicts). Cached; a missing or broken file gives an empty reference with
    "error" set, never an exception."""
    if slug not in SLUGS:
        raise ValueError("unknown calculator %r" % slug)
    key = (slug, path)
    if key in _CACHE:
        return _CACHE[key]
    p = path or os.path.join(folder(), slug + ".json")
    try:
        with open(p, encoding="utf-8") as f:
            doc = json.load(f)
        if not isinstance(doc.get("entries"), list):
            raise ValueError("no entries")
    except (OSError, ValueError) as e:
        doc = {"slug": slug, "entries": [], "error": "%s: %s" % (os.path.basename(p), e)}
    _CACHE[key] = doc
    return doc


def categories(ref):
    """The categories this reference uses, in CATEGORIES order"""
    have = {e.get("category") for e in ref.get("entries", [])}
    return [c for c in CATEGORIES if c in have] + sorted(c for c in have if c and c not in CATEGORIES)


def _bare(name):
    """'nInt(' -> 'nint': for matching what someone types"""
    return name.rstrip("(").strip().lower()


def _subsequence(q, s):
    it = iter(s)
    return all(ch in it for ch in q)


def score(entry, query):
    """How well an entry matches a query (higher is better, 0 is no match)"""
    q = query.strip().lower()
    if not q:
        return 1
    names = [entry["name"].lower(), _bare(entry["name"])]
    pc = entry.get("pc_spelling")
    if pc:
        names += [pc.lower(), _bare(pc)]
    qb = q.rstrip("(")
    if q in names or qb in names:
        return 100
    if any(n.startswith(qb) for n in names if qb):
        return 80 - min(20, len(names[1]) - len(qb))
    if any(qb in n for n in names if qb):
        return 50
    text = " ".join((entry.get("summary", ""), entry.get("category", ""), entry.get("notes", ""),
                     entry.get("syntax", ""))).lower()
    words = q.split()
    if words and all(w in text for w in words):
        return 30
    if len(qb) >= 3 and any(_subsequence(qb, n) for n in names):
        return 10
    return 0


def search(ref, query="", category=None, limit=None):
    """Entries matching a query (name, PC spelling, summary, category, notes; a fuzzy prefix),
    best first; category limits them to one category. With no query, all in catalog order."""
    out = []
    for i, e in enumerate(ref.get("entries", [])):
        if category and e.get("category") != category:
            continue
        s = score(e, query)
        if s:
            out.append((-s, _bare(e["name"]) if query.strip() else "", i, e))
    out.sort(key=lambda t: t[:3])
    got = [e for _s, _n, _i, e in out]
    return got[:limit] if limit else got


def find(ref, name):
    """The entries with exactly this name (several forms of one command can have one each)"""
    return [e for e in ref.get("entries", []) if e["name"] == name or e.get("pc_spelling") == name]


# A Symbols button -> the reference names it stands for, the first one a calculator has wins
# (the TI-84 integrates with fnInt( and differentiates with nDeriv(; the others use ∫( and d()
SYMBOL_NAMES = {
    "∫": ("∫(", "fnInt("), "d/dx": ("d(", "nDeriv("), "√": ("√(",), "π": ("π",),
    "Σ": ("Σ(", "sum("), "∞": ("∞",), "≤": ("≤",), "≥": ("≥",), "≠": ("≠",), "→": ("→",),
    "i": ("𝑖", "i"), "e": ("𝑒", "𝒆", "ℯ", "ℯ^(", "𝑒^(", "e"), "∠": ("∠",), "°": ("°",), "²": ("²",),
    "⁻¹": ("⁻¹", "^⁻¹"), "‾": ("⁻",), "×": ("*",), "÷": ("/",), "^": ("^",), "E": ("ᴇ", "E"),
    "!": ("!",), "►": ("►",), "|x|": ("abs(",),
}


def for_symbol(ref, sym):
    """The reference entry a Symbols button stands for on this calculator, or None"""
    for name in SYMBOL_NAMES.get(sym, ()) + (sym, sym + "("):
        hits = find(ref, name)
        if hits:
            return hits[0]
    return None


def arg_line(a):
    """One argument for the card: 'tol  how close (optional, default 1E-5)'"""
    extra = []
    if a.get("optional"):
        extra.append("optional")
    if a.get("default"):
        extra.append("default " + str(a["default"]))
    return "%s: %s%s" % (a["name"], a.get("meaning") or "", " (%s)" % ", ".join(extra) if extra else "")


def card(entry):
    """A plain-text syntax card: syntax (every form), what each argument is, the result, an
    example, how to reach it, and notes"""
    lines = [entry["name"], ""]
    lines += entry.get("forms") or [entry["syntax"]]
    if entry.get("summary"):
        lines += ["", entry["summary"]]
    if entry.get("args"):
        lines += ["", "Arguments ([ ] = optional, separated by commas):"]
        lines += ["  " + arg_line(a) for a in entry["args"]]
    if entry.get("returns"):
        lines += ["", "Gives: " + entry["returns"]]
    if entry.get("example"):
        lines += ["", "Example: " + entry["example"]]
    if entry.get("key"):
        lines += ["Keys: " + entry["key"]]
    if entry.get("pc_spelling"):
        lines += ["On the PC type: " + entry["pc_spelling"]]
    if entry.get("notes"):
        lines += ["", "Note: " + entry["notes"]]
    if not entry.get("verified"):
        lines += ["", "(Not checked against TI's reference guide yet)"]
    return "\n".join(lines)


def _patterns(slug, ref):
    """[(compiled regex, entry)] for the names a code scan looks for, longest names first"""
    key = ("pat", slug, id(ref))
    if key in _CACHE:
        return _CACHE[key]
    flags = 0 if slug == "ti84" else re.IGNORECASE  # The 89 and the Nspire ignore case
    seen, pats = set(), []
    for e in sorted(ref.get("entries", []), key=lambda e: -len(e["name"])):
        for n in (e["name"], e.get("pc_spelling")):
            if not n or (n, e["name"]) in seen:
                continue
            seen.add((n, e["name"]))
            word = n.rstrip("(").strip()
            if not word or not any(ch.isalpha() for ch in word) or len(word) < 2:
                continue  # Single letters and operators: too common to hint
            body = re.escape(n.strip())
            if word[0].isalnum():
                body = r"(?<![A-Za-z0-9_])" + body
            if n.strip()[-1].isalnum():
                body += r"(?![A-Za-z0-9_])"
            pats.append((re.compile(body, flags), e))
    _CACHE[key] = pats
    return pats


def find_in_code(slug, code, ref=None):
    """The commands a piece of code uses: [(start, end, entry)] in order, not overlapping (the
    longest name wins). Text inside "strings" and after a comment mark is skipped."""
    ref = ref or load(slug)
    blocked = [False] * len(code)
    in_str = False
    for i, ch in enumerate(code):
        if ch == '"':
            in_str = not in_str
            continue
        if ch == "\n":
            in_str = False
        blocked[i] = in_str
    for m in re.finditer(r"(©|©).*", code):
        for i in range(m.start(), m.end()):
            blocked[i] = True
    hits = []
    taken = [False] * len(code)
    for pat, e in _patterns(slug, ref):
        for m in pat.finditer(code):
            a, b = m.start(), m.end()
            if any(taken[a:b]) or blocked[a]:
                continue
            for i in range(a, b):
                taken[i] = True
            hits.append((a, b, e))
    hits.sort(key=lambda h: h[0])
    return hits


def entry_at(slug, code, index, ref=None):
    """The entry for the command at a position in the code (for a hover hint), or None"""
    for a, b, e in find_in_code(slug, code, ref):
        if a <= index < b:
            return e
        if a > index:
            break
    return None


def referenced(slug, code, ref=None):
    """The distinct entries a piece of code uses, in order of first use"""
    out, seen = [], set()
    for _a, _b, e in find_in_code(slug, code, ref):
        k = (e["name"], e["syntax"])
        if k not in seen:
            seen.add(k)
            out.append(e)
    return out


def insert_plan(slug, entry):
    """What Insert types on the calculator: ("keys", [key names], note) to press keys,
    ("text", text, note) to type text, or (None, None, why) when it can't.

    The 84's commands are tokens, not letters: they come from a key or a menu, so its entries
    carry the keys to press ("keys"). Catalog-only 84 commands open the catalog at their first
    letter. The 89 and the Nspire read typed names, so the name (or its PC spelling) is typed."""
    name = entry["name"]
    key = entry.get("key", "")
    if slug == "ti84":
        if entry.get("keys"):
            note = ""
            if key.startswith("PRGM"):
                note = "PRGM's CTL and I/O menus are there inside the program editor only"
            return "keys", list(entry["keys"]), note
        if len(name) == 1 and not name.isalpha():
            return "text", name, ""
        # Everything but the keyboard's own 2nd functions (2nd SIN...) is in the catalog, which
        # jumps to a letter when it is pressed (TI's reference guide: alpha-lock is on there)
        if name[:1].isalpha() and name[:1].isascii() and not key.startswith(("2nd SIN", "2nd COS", "2nd TAN")):
            return ("keys", ["catalog", name[0].upper()],
                    "The catalog opens at %s: arrow down to %s and press ENTER" % (name[0].upper(), name))
        return None, None, "Not typed from here: on the calculator use %s" % (key or "the catalog")
    if slug == "ti89":  # Its key codes are its characters: ∫ and ► type as themselves
        return "text", name, ""
    return "text", entry.get("pc_spelling") or name, ""  # The Nspire's typed spellings
