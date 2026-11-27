"""Builds tools/reference/{ti84,ti89,nspire}.json from the hand-written sources beside this file
(ti84.txt, ti89.txt, nspire.txt; one entry per line, fields split by " ¦ "):

    python -I tools/reference/source/build_ref.py

"verified" is set by looking each name up in the text of TI's own guides, which aren't in the
repo (TI's copyright): put their extracted text as pdfs/<calc>.txt and pdfs/<calc>_facts.json
in this folder, or point CALCSUITE_REF_PDFS at a folder that has them.

  name ¦ category code ¦ key path ¦ forms (" ;; ") ¦ summary ¦ example ¦ notes ¦ arg overrides ¦ flags

forms may end in "⇒ type" (the result); arg overrides are "name=meaning{default}; ..." ;
flags: "?" unverified, "nokeys" (84: no Insert key path), "pc=..." a PC spelling.
"""
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.dirname(HERE)                   # tools/reference
TOOLS = os.path.dirname(OUT)                  # tools
PDFS = os.environ.get("CALCSUITE_REF_PDFS") or os.path.join(HERE, "pdfs")
sys.path.insert(0, TOOLS)
sys.path.insert(0, HERE)
import calc_files as cf  # noqa: E402
from glossary import GLOSSARY  # noqa: E402

CATS = {"M": "Math", "C": "Calculus/CAS", "A": "Algebra", "L": "Lists", "X": "Matrices",
        "S": "Strings", "T": "Statistics", "P": "Probability", "Z": "Complex",
        "F": "Programming (control flow)", "I": "I/O", "G": "Graph/Draw",
        "U": "Conversions/Units", "B": "Base/Logic", "O": "Settings/Mode", "V": "Memory/Vars",
        "N": "Finance"}

SOURCES = {
    "ti84": ["TI-84 Plus CE Reference Guide (Catalog, Commands and Functions), Texas Instruments, "
             "education.ti.com (TI84_Plus_CE_ReferenceGuide_EN.pdf)",
             "TI-Basic Developer, tibasicdev.wikidot.com (command pages, for syntax details)",
             "TI-Toolkit token sheet 8X.xml, bundled with tivars (tools/third_party_py/tivars/tokens): "
             "every name is a real token"],
    "ti89": ["TI-89 Titanium Guidebook, Appendix A: Functions and Instructions, Texas Instruments, "
             "education.ti.com (TI-89_Guidebook_EN.pdf)"],
    "nspire": ["TI-Nspire CX CAS Reference Guide 5.3.2 (with the CX II Draw commands and TI-Basic "
               "features; the CX II OS 6.x language is the same), Texas Instruments, education.ti.com "
               "(TI-NspireCAS_Reference_Guide_EN.pdf)"],
}
TITLES = {"ti84": "TI-84 Plus CE", "ti89": "TI-89 Titanium", "nspire": "TI-Nspire CX II (CAS)"}

# ---- The 84's menus: (key name for tools/ti84_cli/ti84_keys.py, tab names) ----
MENUS84 = {
    "MATH": ("math", ["MATH", "NUM", "CMPLX", "PROB", "FRAC"]),
    "2nd TEST": ("test", ["TEST", "LOGIC"]),
    "2nd MATRIX": ("matrix", ["NAMES", "MATH", "EDIT"]),
    "2nd LIST": ("list", ["NAMES", "OPS", "MATH"]),
    "2nd ANGLE": ("angle", ["ANGLE"]),
    "2nd DRAW": ("draw", ["DRAW", "POINTS", "STO", "BACKGROUND"]),
    "2nd DISTR": ("distr", ["DISTR", "DRAW"]),
    "STAT": ("stat", ["EDIT", "CALC", "TESTS"]),
    "PRGM": ("prgm", ["CTL", "I/O", "COLOR", "EXEC"]),
    "ZOOM": ("zoom", ["ZOOM", "MEMORY"]),
    "2nd MEM": ("mem", ["MEMORY"]),
    "2nd STAT PLOT": ("statplot", ["STAT PLOTS"]),
}
DIRECT84 = {"SIN": ["sin"], "COS": ["cos"], "TAN": ["tan"], "LOG": ["log"], "LN": ["ln"],
            "2nd LN": ["exp"], "2nd LOG": ["tenpower"], "2nd x²": ["sqrt"], "x²": ["square"],
            "x⁻¹": ["inverse"], "STO→": ["sto"], "(-)": ["neg"], "2nd ,": ["ee"],
            "2nd (-)": ["ans"], "2nd ^": ["pi"], "2nd .": ["i"], "2nd ÷": ["conste"],
            "+": ["+"], "-": ["-"], "×": ["*"], "÷": ["/"], "^": ["^"],
            "2nd 0": ["catalog"]}
ITEMS = "1234567890ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def keys84(key):
    """'MATH > NUM > 3' -> key names; '' when it isn't a path we can press"""
    if key in DIRECT84:
        return DIRECT84[key]
    parts = [p.strip() for p in key.split(">")]
    if len(parts) >= 2 and parts[0] in MENUS84:
        keyname, tabs = MENUS84[parts[0]]
        tab = 0
        if len(parts) == 3:
            if parts[1] not in tabs:
                raise ValueError("unknown tab %r in %r" % (parts[1], key))
            tab = tabs.index(parts[1])
        elif len(parts) != 2:
            return []
        item = parts[-1]
        if len(item) != 1 or item not in ITEMS:
            return []
        # The item's own number or letter picks it (whatever line the menu last had)
        return [keyname] + ["right"] * tab + [item]
    if parts[0] == "APPS" and len(parts) == 4 and parts[1] == "Finance":
        tabs = ["CALC", "VARS"]
        return ["apps", "1"] + ["right"] * tabs.index(parts[2]) + [parts[3]]  # Finance is APPS 1
    return []


KEYWORDS = {"and", "or", "xor", "not", "nand", "nor", "Then", "Else", "End", "EndIf", "EndFor",
            "EndWhile", "EndLoop", "EndTry", "EndFunc", "EndPrgm", "Func", "Prgm", "Plot",
            "LibPub", "LibPriv", "Define", "with", "If", "ElseIf", "Endif", "Do", "Disp", "Input",
            "Prompt", "Text", "Lbl", "Goto", "Request", "RequestStr", "EndCustm", "EndTBar",
            "EndDlog", "Custom", "Dialog", "Toolbar", "Item", "Title", "DropDown", "Repeat",
            "While", "For", "Loop", "Try", "ClrErr", "PassErr", "Return", "Stop", "Wait",
            "Archive", "UnArchive", "Unarchiv", "prgm", "Local", "Cycle", "Exit"}


def split_form(form):
    """'abs(x) ⇒ number' -> ('abs(x)', 'number')"""
    if "⇒" in form and not form.startswith("⇒"):
        a, b = form.split("⇒", 1)
        if a.strip():
            return a.strip(), b.strip()
    return form.strip(), ""


IDENT = re.compile(r"[A-Za-z_θμσλχΣ#][A-Za-z0-9_θμσλχ#²₀-₉̄]*")
# Argument names with a space or a sign in them (TI writes them so): kept whole
SPECIAL = ["confidence level", "interest rate", "numerator df", "denominator df", "line style#",
           "Y= var", "effective rate", "nominal rate", "compounding periods", "complex value",
           "I%", "P/Y", "C/Y", "expression_°tempUnit1", "_°tempUnit2", "expression_unit1",
           "_unit2", "expression_unit", "Expr_°tempUnit", "Expr_Unit1", "_Unit2", "Expr_Unit",
           "r-value", "g-value", "b-value"]


def args_of(name, syntax):
    """[(arg, optional)] in order of first use; literal text in quotes is skipped"""
    stem = name.rstrip("(").strip()
    s = syntax
    if s.startswith(stem):
        s = s[len(stem):]
    if stem and stem != "_" and (len(stem) > 1 or not stem.isalpha()):
        s = s.replace(stem, " ")
    s = re.sub(r'"[^"]*"', "", s)
    s = re.sub(r"\b(value|variable|text|listname|list|label|function#) n\b", "", s)
    out, depth, i = [], 0, 0
    while i < len(s):
        c = s[i]
        if c == "[":
            depth += 1
        elif c == "]":
            depth = max(0, depth - 1)
        sp = next((w for w in SPECIAL if s.startswith(w, i) and
                   (i == 0 or not s[i - 1].isalnum())), None)
        if sp:
            out.append((sp, depth > 0))
            i += len(sp)
            continue
        m = IDENT.match(s, i)
        if m and (i == 0 or not (s[i - 1].isalnum() or s[i - 1] in "_.")):
            w = m.group(0)
            i = m.end()
            if w in KEYWORDS or w.lower() in ("e",) or re.match(r"^(Plot|Y|L|Str|Pic|GDB|Image)\d?$", w):
                continue
            if w == stem or w in stem.split():
                continue
            out.append((w, depth > 0))
            continue
        i += 1
    return out


def gloss(calc, cmd, arg):
    for k in ("%s:%s:%s" % (calc, cmd, arg), "%s:%s" % (cmd, arg), arg, arg.lower(),
              re.sub(r"\d+$", "", arg), re.sub(r"\d+$", "", arg).lower(),
              re.sub(r"[\d₀-₉]+$", "", arg).lower()):
        if k in GLOSSARY:
            return GLOSSARY[k]
    return None


def guide_names(calc):
    """Names the guide's text has as an entry (for 'verified')"""
    p = os.path.join(PDFS, calc + ".txt")
    if not os.path.isfile(p):
        sys.exit("ERROR: %s is missing: the extracted text of TI's guide (see the top of this file)" % p)
    text = open(p, encoding="utf-8").read()
    return text


def norm(n):
    return n.replace("()", "").rstrip("(").strip()


def in_guide(calc, name, text, facts):
    base = norm(name)
    if not base:
        return False
    if base in facts:
        return True
    # The guides' PDF text uses TI's key font for some symbols: try those spellings too
    subs = {"ti89": [("►", "4"), ("⁻¹", "ê"), ("⁻¹", "L1"), ("∫", "‰"), ("√", "‡"), ("Σ", "G"),
                     ("→", "!"), ("θ", "q"), ("Δ", "@"), ("π", "p"), ("ℯ", "í")],
            "ti84": [("►", " 4 "), ("►", "4"), ("⁻¹", "L1"), ("χ²", "c 2 "), ("χ²", "c2"),
                     ("𝙵", "Ü"), ("Σ", "G"), ("√", "‡"), ("Δ", "@"), ("ʟ", "Ù"), ("𝑖", "i"),
                     ("𝑒", "e"), ("⁄", "/"), ("𝑛", "n"), ("𝗡", "Ú"), ("θ", "q")],
            "nspire": [("⁻¹", "-1"), ("►", "►")]}.get(calc, [])
    variants = {base}
    for a, b in subs:
        for v in list(variants):
            if a in v:
                variants.add(v.replace(a, b))
    for v in variants:
        if v in facts:
            return True
        pat = r"(^|\n)\s*(\d:)?\s*%s\s*(\(|\n| |\))" % re.escape(v.strip())
        if re.search(pat, text) is not None:
            return True
    return False


def tokens84():
    names = {}
    for b, ns in cf._names_84():
        for n in ns:
            if n and n.strip():
                names.setdefault(n.strip(), b)
    rev = {}
    for s, b in cf.ASCII_84.items():
        rev.setdefault(b, s)
    return names, rev


PC89 = [("∫(", "@int("), ("Σ(", "@sum("), ("√(", "sqrt("), ("►", "@>"), ("→", "->"),
        ("≤", "<="), ("≥", ">="), ("≠", "!="), ("π", "pi"), ("θ", "theta"), ("∠", "@angle"),
        ("ℯ^(", "e^("), ("𝑖", "@i")]


def build(calc):
    src = os.path.join(HERE, calc + ".txt")
    facts_p = os.path.join(PDFS, calc + "_facts.json")
    facts = {norm(e["name"]) for e in json.load(open(facts_p, encoding="utf-8"))}
    text = guide_names(calc)
    tok, rev = tokens84() if calc == "ti84" else ({}, {})
    entries, unknown, problems = [], set(), []
    seen = set()
    for n, line in enumerate(open(src, encoding="utf-8"), 1):
        line = line.rstrip("\n")
        if not line.strip() or (line.lstrip().startswith("#") and "¦" not in line):
            continue
        f = [x.strip() for x in re.split(r"\s*¦\s*", line)]
        f += [""] * (9 - len(f))
        name, cat, key, forms, summary, example, notes, over, flags = f[:9]
        if cat not in CATS and line.lstrip().startswith("#"):
            continue
        if cat not in CATS:
            problems.append("%s:%d bad category %r" % (calc, n, cat))
            continue
        flagset = [x.strip() for x in flags.split(";") if x.strip()]
        overrides = {}
        for o in [x.strip() for x in over.split(";") if x.strip()]:
            mm = re.match(r"^(Y= var|[^=]+)=(.*)$", o)
            k, v = (mm.group(1), mm.group(2)) if mm else (o, "")
            d = None
            m = re.match(r"^(.*)\{(.*)\}$", v)
            if m:
                v, d = m.group(1).strip(), m.group(2).strip()
            overrides[k.strip()] = (v.strip(), d)
        fl = [x.strip() for x in forms.split(";;") if x.strip()] or [name]
        syn, rets = [], []
        for x in fl:
            s, r = split_form(x)
            syn.append(s)
            if r and r not in rets:
                rets.append(r)
        args, order = {}, []
        for s in syn:
            got = args_of(name, s)
            names_here = set()
            for a, opt in got:
                names_here.add(a)
                if a not in args:
                    args[a] = opt
                    order.append(a)
                else:
                    args[a] = args[a] and opt
        arglist = []
        for a in order:
            if a in overrides:
                meaning, default = overrides[a]
            else:
                g = gloss(calc, norm(name), a)
                if g is None:
                    unknown.add(a)
                    meaning, default = "", None
                else:
                    meaning, default = (g if isinstance(g, tuple) else (g, None))
            e = {"name": a, "meaning": meaning, "optional": bool(args[a])}
            if default is not None:
                e["default"] = default
            arglist.append(e)
        key_out = key
        entry = {"name": name, "syntax": syn[0]}
        if len(syn) > 1:
            entry["forms"] = syn
        entry["args"] = arglist
        entry["returns"] = " or ".join(rets) if rets else "nothing (a command)"
        entry["summary"] = summary
        entry["example"] = example
        entry["category"] = CATS[cat]
        entry["key"] = key_out
        pc = next((x[3:] for x in flagset if x.startswith("pc=")), "")
        if calc == "ti84":
            if name not in tok:
                problems.append("ti84:%d %r is not a token" % (n, name))
            else:
                b = tok[name]
                alt = rev.get(b)
                if not pc and alt and alt != name:
                    pc = alt
                if not pc:
                    acc = next((ns[1] for bb, ns in cf._names_84() if bb == b), "")
                    acc = (acc or "").strip()
                    if acc and acc != name and all(ord(ch) < 128 for ch in acc):
                        pc = acc
            if "nokeys" not in flagset:
                try:
                    ks = keys84(key)
                except ValueError as e:
                    problems.append("ti84:%d %s" % (n, e))
                    ks = []
                if ks:
                    entry["keys"] = ks
        elif calc == "ti89" and not pc:
            p = name
            for u, a in PC89:
                p = p.replace(u, a)
            if p != name:
                pc = p
        if pc:
            entry["pc_spelling"] = pc
        if notes:
            entry["notes"] = notes
        ver = "?" not in flagset and ("g" in flagset or in_guide(calc, name, text, facts))
        entry["verified"] = ver
        if not summary or not example and "noex" not in flagset:
            problems.append("%s:%d %s: no summary/example" % (calc, n, name))
        kk = (name, syn[0])
        if kk in seen:
            problems.append("%s:%d duplicate %s" % (calc, n, name))
        seen.add(kk)
        entries.append(entry)
    doc = {"calculator": TITLES[calc], "slug": calc, "format": 1,
           "sources": SOURCES[calc],
           "licence": "MIT (CalcSuite). Summaries are CalcSuite's own words; names and syntax are facts "
                      "from the sources.",
           "count": len(entries), "verified": sum(1 for e in entries if e["verified"]),
           "entries": entries}
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, calc + ".json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print("%s: %d entries, %d verified" % (calc, len(entries), doc["verified"]))
    if unknown:
        print("  unknown args:", " ".join(sorted(unknown)))
    for p in problems:
        print("  PROBLEM", p)
    unv = [e["name"] for e in entries if not e["verified"]]
    print("  unverified:", " ".join(unv))


for c in (sys.argv[1:] or ["ti84", "ti89", "nspire"]):
    build(c)
