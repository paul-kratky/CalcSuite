"""Self-test for the Functions panel's reference (tools/reference/*.json, tools/reference.py):
no calculator, no tools/bin, no window.

- every entry has a name, syntax, summary and a known category, and its arguments are explained
- every TI-84 name is a real token of TI-Toolkit's token sheet (tivars' tokens/8X.xml)
- every TI-84 example tokenizes with tools/calc_files.py, with no warnings
- every TI-89 example goes through calc_files' TI-89 conversion
- the 84's Insert keys all have key codes; search, the syntax card and the code scan work

    python -I tools/selftest/reference_checks.py      (run_selftest.py runs it too)
"""

import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
for _p in (TOOLS, os.path.join(TOOLS, "nspire_cli"), os.path.join(TOOLS, "ti84_cli")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
TOKENS_XML = os.path.join(TOOLS, "third_party_py", "tivars", "tokens", "8X.xml")


def check(ok, what):
    print("%-4s %s" % ("PASS" if ok else "FAIL", what))
    return 0 if ok else 1


def short(items, n=6):
    items = list(items)
    return ", ".join(repr(x) for x in items[:n]) + (" and %d more" % (len(items) - n) if len(items) > n else "")


def token_names():
    """Every name the 84's token sheet gives a token (shown name, typing name, variants)"""
    names = set()
    for lang in ET.parse(TOKENS_XML).getroot().iter("lang"):
        if lang.get("code") != "en":
            continue
        for n in [lang.get("display")] + [c.text for c in lang if c.tag in ("accessible", "variant")]:
            if n and n.strip():
                names.add(n.strip())
    return names


def main():
    import calc_files as cf
    import reference
    failures = 0
    refs = {}
    for slug in reference.SLUGS:
        ref = refs[slug] = reference.load(slug)
        entries = ref.get("entries", [])
        failures += check(not ref.get("error") and len(entries) > 200 and ref.get("sources"),
                          "%s reference loads: %d entries, %d checked against TI's guide, sources "
                          "named" % (slug, len(entries), sum(1 for e in entries if e.get("verified"))))
        bad = [e.get("name") for e in entries
               if not all(isinstance(e.get(k), str) and e[k].strip() for k in ("name", "syntax", "summary", "category"))]
        failures += check(not bad, "%s: every entry has name, syntax, summary, category%s" % (
            slug, (": not " + short(bad)) if bad else ""))
        bad = [e["name"] for e in entries if e.get("category") not in reference.CATEGORIES]
        failures += check(not bad, "%s: every category is a known one%s" % (slug, (": not " + short(bad)) if bad else ""))
        bad = ["%s %s" % (e["name"], a.get("name")) for e in entries for a in e.get("args", [])
               if not (a.get("name") and a.get("meaning") and isinstance(a.get("optional"), bool))]
        failures += check(not bad, "%s: every argument has a meaning%s" % (slug, (": not " + short(bad)) if bad else ""))
        bad = [e["name"] for e in entries if not isinstance(e.get("verified"), bool) or "returns" not in e]
        failures += check(not bad, "%s: every entry says returns and verified%s" % (slug, (": not " + short(bad)) if bad else ""))

    e84 = refs["ti84"]["entries"]
    if os.path.isfile(TOKENS_XML):
        names = token_names()
        bad = [e["name"] for e in e84 if e["name"] not in names]
        failures += check(not bad, "84: all %d names are tokens in tivars' 8X.xml%s" % (
            len(e84), (": not " + short(bad)) if bad else ""))
    else:
        print("SKIP 84 names against the token sheet (%s missing)" % TOKENS_XML)
    bad = []
    for e in e84:
        if not e.get("example"):
            continue
        warnings = []
        try:
            cf.tokenize_84(e["example"], warnings)
        except ValueError as x:
            warnings.append(str(x))
        if warnings:
            bad.append("%s: %s" % (e["example"], warnings[0]))
    failures += check(not bad, "84: every example tokenizes with no warnings (%s)%s" % (
        cf.token_source(), (": " + short(bad, 3)) if bad else ""))

    bad = []
    for e in refs["ti89"]["entries"]:
        if not e.get("example"):
            continue
        try:  # Wrapped as a program's body (a lone "f(x)" line would read as its name line)
            cf.program_89_data("Prgm\n%s\nEndPrgm" % e["example"], "zzref")
        except ValueError as x:
            bad.append("%s: %s" % (e["example"], x))
    failures += check(not bad, "89: every example passes the TI-89 conversion%s" % (
        (": " + short(bad, 3)) if bad else ""))

    import ti84_keys
    bad = ["%s %s" % (e["name"], k) for e in e84 for k in e.get("keys", []) if ti84_keys.code_for(k) is None]
    failures += check(not bad, "84: every Insert key has a key code (%d entries carry keys)%s" % (
        sum(1 for e in e84 if e.get("keys")), (": not " + short(bad)) if bad else ""))
    try:
        import calc_models as cm
        for slug in reference.SLUGS:
            calc, typeable, total = cm.BY_SLUG[slug], 0, 0
            for e in refs[slug]["entries"]:
                kind, what, _n = reference.insert_plan(slug, e)
                total += 1
                if kind == "keys":
                    typeable += all(calc.resolve(k) is not None for k in what)
                elif kind == "text":
                    typeable += not calc.paste_keys(what)[1]
            failures += check(typeable >= total * 0.8, "%s: Insert can type %d of %d" % (slug, typeable, total))
    except ImportError as x:
        print("SKIP Insert plans (%s)" % x)

    r89 = refs["ti89"]
    got = [e["name"] for e in reference.search(r89, "nint")]
    failures += check(got[:1] == ["nInt("], "search: exact name first (nint -> nInt()")
    got = [e["name"] for e in reference.search(r89, "solv")]
    failures += check("solve(" in got[:3] and "cSolve(" in got, "search: a prefix finds solve( and cSolve(")
    got = reference.search(r89, "", "Matrices")
    failures += check(got and all(e["category"] == "Matrices" for e in got), "search: the category filter")
    e = reference.find(r89, "nInt(")[0]
    c = reference.card(e)
    failures += check("nInt(expression1,var,lower,upper)" in c and "lower:" in c and "Example:" in c,
                      "card: syntax, each argument and the example")
    code = 'Disp sqrt(X)\nFor(I,1,10)\nIf X>=2:Then:Disp "solve( here",nDeriv(X^2,X,2)\nEnd'
    names = [x["name"] for x in reference.referenced("ti84", code)]
    failures += check(names == ["Disp", "√(", "For(", "If", "Then", "nDeriv(", "End"],
                      "code scan: the 84 commands a program uses, not the ones in strings (%s)" % short(names, 8))
    hit = reference.entry_at("ti89", "y:=nint(f(x),x,0,1)", 4)
    failures += check(hit is not None and hit["name"] == "nInt(", "hover hint: the command under a position (89 ignores case)")
    kind, what, _n = reference.insert_plan("ti84", reference.find(refs["ti84"], "fnInt(")[0])
    failures += check(kind == "keys" and what == ["math", "9"],
                      "84 Insert: fnInt( from the MATH menu (%s)" % " ".join(what or []))
    return failures


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):  # A cp1252 console can't print ►, ∫ or →
        try:
            _stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    n = main()
    print("\n%s" % ("ALL PASSED" if not n else "%d FAILURE(S)" % n))
    sys.exit(1 if n else 0)
