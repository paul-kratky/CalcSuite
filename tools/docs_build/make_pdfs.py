# SPDX-License-Identifier: MIT
"""Builds docs/pdf/: every guide and a Functions reference per calculator, as dark PDFs in the
app's look (tools/docs_build/md_to_pdf.py; Microsoft Edge prints them).

    python -I tools/docs_build/make_pdfs.py                 # all of them, into docs/pdf/
    python -I tools/docs_build/make_pdfs.py --only 84       # those whose file name has "84"
    python -I tools/docs_build/make_pdfs.py --out out/pdf --version v0.3.0

The app bundles docs/pdf/ (app.spec) for Save as PDF in its Guide and Functions sections
(tools/ui_panels.py: PDF_GUIDES, PDF_FUNCTIONS name the same files).
"""

import argparse
import html
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(KIT, "tools"))

import md_to_pdf as m2p  # noqa: E402
import reference  # noqa: E402

# (PDF file name, Markdown source, the cover title; None: the file's own # heading)
GUIDES = [
    ("CalcSuite - User guide.pdf", "docs/USER_GUIDE.md", None),
    ("CalcSuite - Quick start.pdf", "QUICKSTART.md", None),
    ("CalcSuite - TI-84 Plus CE TI-Basic guide.pdf", "docs/TIBASIC_84.md", None),
    ("CalcSuite - TI-89 Titanium TI-Basic guide.pdf", "docs/TIBASIC_89.md", None),
    ("CalcSuite - TI-Nspire CX II Python guide.pdf", "docs/PYTHON_NSPIRE_GUIDE.md", None),
    ("CalcSuite - TI-Nspire Python kit.pdf", "docs/PYTHON_KIT.md", None),
    ("CalcSuite - PC copies (CEmu and TiEmu) guide.pdf", "docs/EMULATORS.md", None),
]
# slug -> PDF file name of its Functions reference
FUNCTIONS = {
    "ti84": "CalcSuite - TI-84 Plus CE functions reference.pdf",
    "ti89": "CalcSuite - TI-89 Titanium functions reference.pdf",
    "nspire": "CalcSuite - TI-Nspire CX II functions reference.pdf",
}

REF_CSS = """
nav.cats ol { columns: 2; }
nav.cats .n { color: #8a929b; font-size: 8pt; margin-left: 4px; }
h2 .up { float: right; font: 400 8pt "Segoe UI", sans-serif; color: #8ff0cf; margin-top: 6px; }
.how { color: #8a929b; font-size: 8.8pt; margin: 10px 0 0; }
section.cat { break-before: page; }
section.cat:first-of-type { break-before: auto; }
.entry { break-inside: avoid; border: 1px solid #1d1f24; border-radius: 5px; background: #0a0b0d;
  padding: 7px 11px 8px; margin: 0 0 7px; }
.entry .top { display: flex; align-items: baseline; gap: 10px; }
.entry .nm { font: 700 11pt Consolas, "JetBrains Mono", monospace; color: #ff7a3d; flex: none; }
.entry .sum { color: #ece9e2; font-size: 9.2pt; }
.entry .unv { color: #8a929b; font-size: 7.5pt; margin-left: auto; flex: none; }
.entry .syn { font: 9pt/1.4 Consolas, "JetBrains Mono", monospace; color: #ece9e2; background: #111113;
  border-left: 3px solid #8ff0cf; border-radius: 3px; padding: 3px 8px; margin: 5px 0 4px;
  white-space: pre-wrap; overflow-wrap: anywhere; }
.entry dl { display: grid; grid-template-columns: 92px 1fr; gap: 2px 10px; margin: 4px 0 0; font-size: 8.8pt; }
.entry dt { color: #8a929b; font-weight: 600; }
.entry dd { margin: 0; overflow-wrap: anywhere; }
.entry .args { margin: 0; padding: 0; list-style: none; }
.entry .args li { margin: 0 0 1px; }
.entry .an { font: 600 8.8pt Consolas, "JetBrains Mono", monospace; color: #8ff0cf; }
.entry .opt { color: #8a929b; }
"""


def esc(t):
    return html.escape(str(t), quote=False)


def mono(t):
    return "<code>%s</code>" % esc(t)


def entry_html(e):
    """One command: name and summary, every syntax form, then the details"""
    rows = []
    if e.get("args"):
        items = []
        for a in e["args"]:
            extra = []
            if a.get("optional"):
                extra.append("optional")
            if a.get("default") not in (None, ""):
                extra.append("default " + mono(a["default"]))
            items.append('<li><span class="an">%s</span> %s%s</li>' % (
                esc(a["name"]), esc(a.get("meaning") or ""),
                ' <span class="opt">(%s)</span>' % ", ".join(extra) if extra else ""))
        rows.append(("Arguments", '<ul class="args">%s</ul>' % "".join(items)))
    if e.get("returns"):
        rows.append(("Gives", esc(e["returns"])))
    if e.get("example"):
        rows.append(("Example", mono(e["example"])))
    if e.get("key"):
        rows.append(("Keys", esc(e["key"])))
    if e.get("pc_spelling"):
        rows.append(("On the PC type", mono(e["pc_spelling"])))
    if e.get("notes"):
        rows.append(("Note", esc(e["notes"])))
    forms = e.get("forms") or [e["syntax"]]
    return ('<div class="entry"><div class="top"><span class="nm">%s</span><span class="sum">%s</span>%s</div>'
            '<div class="syn">%s</div><dl>%s</dl></div>'
            % (esc(e["name"]), esc(e.get("summary", "")),
               "" if e.get("verified") else '<span class="unv">not checked against TI\'s guide yet</span>',
               "\n".join(esc(f) for f in forms),
               "".join("<dt>%s</dt><dd>%s</dd>" % (k, v) for k, v in rows)))


def functions_page(slug, version=None):
    """The HTML of a calculator's Functions reference (tools/reference/<slug>.json)"""
    ref = reference.load(slug)
    if ref.get("error"):
        raise SystemExit("The %s reference didn't load: %s" % (slug, ref["error"]))
    calc = ref.get("calculator") or slug
    cats = reference.categories(ref)
    index, sections = [], []
    for k, c in enumerate(cats):
        cid = "cat-%d" % k
        entries = sorted((e for e in ref["entries"] if e.get("category") == c),
                         key=lambda e: (reference._bare(e["name"]), e["name"]))
        index.append('<li><a href="#%s">%s</a><span class="n">%d</span></li>' % (cid, esc(c), len(entries)))
        sections.append('<section class="cat"><h2 id="%s">%s<a class="up" href="#categories">'
                        'Categories</a></h2>%s</section>'
                        % (cid, esc(c), "".join(entry_html(e) for e in entries)))
    n = len(ref["entries"])
    intro = ("<p>Every command CalcSuite's Functions panel knows for the %s: %d of them, by "
             "category, A to Z within each. Each shows its syntax (every form), what each argument "
             "is (<span class='dim'>[ ]</span> marks the optional ones), what it gives, an example, "
             "the keys that reach it, and notes.</p>" % (esc(calc), n))
    src = ref.get("sources") or []
    how = ('<p class="how">Sources: %s</p>' % "; ".join(esc(s) for s in src)) if src else ""
    toc = ('<nav class="toc cats"><h2 id="categories">Categories</h2><ol>%s</ol></nav>%s<div class="toc-break"></div>'
           % ("".join(index), how))
    doc = m2p.page("%s functions reference" % calc, intro + toc + "".join(sections), version=version)
    return doc.replace("</style>", REF_CSS + "</style>", 1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=os.path.join(KIT, "docs", "pdf"), help="the folder (default docs/pdf)")
    ap.add_argument("--only", help="only the PDFs whose file name contains this text")
    ap.add_argument("--version", help="the version on the covers (default: from CHANGELOG.md)")
    ap.add_argument("--html", help="also write each page's HTML into this folder")
    a = ap.parse_args()
    edge = m2p.find_edge()
    if not edge:
        sys.exit("Microsoft Edge wasn't found: it prints the PDFs. Install Edge, or put msedge on PATH.")
    jobs = []
    for name, src, title in GUIDES:
        jobs.append((name, True, lambda src=src, title=title: m2p.markdown_page(
            os.path.join(KIT, src), title, a.version)))
    for slug, name in FUNCTIONS.items():
        # No bookmarks (a third of the size); page 1's category index links to each category
        jobs.append((name, False, lambda slug=slug: functions_page(slug, a.version)))
    if a.only:
        jobs = [j for j in jobs if a.only.lower() in j[0].lower()]
        if not jobs:
            sys.exit("No PDF's name contains %r" % a.only)
    total = 0
    for name, outline, make in jobs:
        doc = make()
        if a.html:
            os.makedirs(a.html, exist_ok=True)
            with open(os.path.join(a.html, name[:-4] + ".html"), "w", encoding="utf-8") as f:
                f.write(doc)
        path = os.path.join(a.out, name)
        size = m2p.html_to_pdf(doc, path, edge, outline)
        total += size
        print("%-58s %4d pages %8.0f KB" % (name, m2p.page_count(path), size / 1024.0))
    print("%d PDFs, %.1f MB, in %s" % (len(jobs), total / 1048576.0, os.path.abspath(a.out)))


if __name__ == "__main__":
    main()
