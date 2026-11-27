# SPDX-License-Identifier: MIT
"""CalcSuite's Markdown guides as dark PDFs in the app's own look (tools/ui_theme.py).

    python tools/docs_build/md_to_pdf.py docs/TIBASIC_84.md "out/TI-84 guide.pdf"
    python tools/docs_build/md_to_pdf.py README.md out/guide.pdf --title "CalcSuite user guide"

Standard library only: a small Markdown reader (headings, paragraphs, nested lists, pipe
tables, fenced code with an info string such as `tibasic84 name=QUAD`, inline code, bold,
italic, links, local images) writes print-ready HTML, and Microsoft Edge prints it to PDF
(headless). Page 1 has a cover header (the app's icon, the title, the version from
CHANGELOG.md) and a table of contents from the ## headings; the PDF gets bookmarks and page
numbers. tools/docs_build/make_pdfs.py builds every guide into docs/pdf/.
"""

import argparse
import base64
import html
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(os.path.dirname(HERE))  # The repo (tools/docs_build/ is two levels down)
REPO_URL = "https://github.com/paul-kratky/CalcSuite"

# tools/ui_theme.py's palette
BG, PANEL, PANEL2, LINE = "#000000", "#0a0b0d", "#111113", "#1d1f24"
FG, DIM, ACCENT, MINT = "#ece9e2", "#8a929b", "#ff7a3d", "#8ff0cf"
SANS = '"Segoe UI", Inter, "Helvetica Neue", Arial, sans-serif'
MONO = 'Consolas, "JetBrains Mono", "Cascadia Mono", "Courier New", monospace'

EDGE_PATHS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
]

# The language labels shown above code blocks
LANGS = {"tibasic84": "TI-Basic (TI-84 Plus CE)", "tibasic89": "TI-Basic (TI-89 Titanium)",
         "python": "Python", "py": "Python", "sh": "Shell", "bash": "Shell", "text": "Text",
         "powershell": "PowerShell", "bat": "Batch", "json": "JSON"}

# @page carries the background, so every page is black to its edges, margins included. The
# margin boxes hold the footer (Edge 131+); --no-pdf-header-footer drops Edge's own.
CSS = """
@page { size: Letter; margin: 0.55in 0.6in 0.62in; background: %(BG)s;
  @bottom-left { color: %(DIM)s; font: 7.5pt %(SANS)s; }
  @bottom-right { content: counter(page) " / " counter(pages); color: %(DIM)s; font: 7.5pt %(SANS)s; } }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; background: %(BG)s; }
body { margin: 0; background: %(BG)s; color: %(FG)s; font: 10pt/1.5 %(SANS)s; }
header.cover { display: flex; align-items: center; gap: 18px; padding: 18px 20px; margin: 0 0 18px;
  background: %(PANEL)s; border: 1px solid %(LINE)s; border-left: 4px solid %(ACCENT)s; border-radius: 6px; }
header.cover img { width: 64px; height: 64px; border-radius: 12px; flex: none; }
header.cover .kicker { font: 600 8pt %(SANS)s; letter-spacing: .16em; text-transform: uppercase; color: %(ACCENT)s; }
header.cover h1 { font-size: 21pt; line-height: 1.15; margin: 3px 0 4px; color: #ffffff; border: 0; padding: 0; }
header.cover .meta { color: %(DIM)s; font-size: 8.5pt; }
header.cover .meta b { color: %(MINT)s; font-weight: 600; }
nav.toc { background: %(PANEL)s; border: 1px solid %(LINE)s; border-radius: 6px; padding: 10px 16px 12px; margin: 14px 0 0; }
nav.toc h2 { margin: 0 0 6px; border: 0; padding: 0; font-size: 11pt; }
nav.toc ol { columns: 2; column-gap: 28px; margin: 0; padding-left: 22px; font-size: 9pt; }
nav.toc li { break-inside: avoid; margin: 0 0 2px; color: %(DIM)s; }
nav.toc a { color: %(FG)s; }
.toc-break { break-after: page; }
h1, h2, h3, h4 { color: %(ACCENT)s; break-after: avoid; line-height: 1.25; }
h1 { font-size: 17pt; margin: 22px 0 8px; }
h2 { font-size: 14pt; margin: 22px 0 8px; padding-bottom: 4px; border-bottom: 1px solid %(LINE)s; }
h3 { font-size: 11.5pt; margin: 16px 0 5px; color: #ffa47a; }
h4 { font-size: 10.5pt; margin: 12px 0 4px; color: #ffa47a; }
p { margin: 0 0 8px; }
h2 + p, h3 + p, h4 + p { break-after: avoid; }  /* An example's heading and intro stay with its code */
ul, ol { margin: 0 0 8px; padding-left: 22px; }
li { margin-bottom: 3px; }
li > p { margin: 4px 0; }
li::marker { color: %(ACCENT)s; }
b, strong { color: #ffffff; font-weight: 600; }
i, em { color: #f6f2ea; }
a { color: %(MINT)s; text-decoration: none; overflow-wrap: anywhere; }
code { font: 8.8pt %(MONO)s; color: %(MINT)s; background: %(PANEL2)s; padding: 0 3px; border-radius: 3px;
  overflow-wrap: anywhere; }
a code { color: %(MINT)s; }
figure.code { margin: 6px 0 12px; break-inside: avoid; }
figure.code figcaption { font: 600 7.5pt %(SANS)s; letter-spacing: .06em; color: %(DIM)s; margin: 0 0 0 2px;
  padding: 3px 8px; display: inline-block; background: %(PANEL2)s; border: 1px solid %(LINE)s;
  border-bottom: 0; border-radius: 4px 4px 0 0; }
figure.code figcaption .name { color: %(ACCENT)s; margin-left: 6px; }
pre { font: 8.6pt/1.42 %(MONO)s; color: %(FG)s; background: %(PANEL)s; border: 1px solid %(LINE)s;
  border-left: 3px solid %(MINT)s; border-radius: 4px; padding: 8px 10px; margin: 0;
  white-space: pre-wrap; overflow-wrap: anywhere; }
pre code { background: none; color: inherit; padding: 0; font: inherit; }
table { border-collapse: collapse; width: 100%%; font-size: 8.8pt; line-height: 1.38; margin: 8px 0 14px;
  table-layout: auto; }
thead { display: table-header-group; }
th { text-align: left; color: %(ACCENT)s; font-weight: 600; background: %(PANEL2)s; padding: 5px 7px;
  border-bottom: 1px solid %(ACCENT)s; vertical-align: bottom; }
td { padding: 4px 7px; border-bottom: 1px solid %(LINE)s; vertical-align: top; overflow-wrap: break-word; }
tbody tr:nth-child(even) td { background: %(PANEL)s; }
tr { break-inside: avoid; }
hr { border: 0; border-top: 1px solid %(LINE)s; margin: 14px 0; }
blockquote { margin: 6px 0 10px; padding: 4px 12px; border-left: 3px solid %(ACCENT)s; background: %(PANEL)s;
  color: #d6d2ca; }
img.md { max-width: 100%%; border: 1px solid %(LINE)s; border-radius: 4px; }
.dim { color: %(DIM)s; }
""" % dict(BG=BG, PANEL=PANEL, PANEL2=PANEL2, LINE=LINE, FG=FG, DIM=DIM, ACCENT=ACCENT, MINT=MINT,
           SANS=SANS, MONO=MONO)

# Emoji become words: Edge embeds a colour-emoji font for them, which some PDF viewers fail on
EMOJI_WORDS = {"✅": "Yes", "❌": "No", "⚠️": "Caution", "⚠": "Caution", "✔": "Yes", "✖": "No"}


def plain(t):
    for k, v in EMOJI_WORDS.items():
        t = t.replace(k, v)
    return re.sub("[\U0001F000-\U0001FAFF\uFE0F]", "", t)


def slug(text):
    """A heading's anchor, GitHub's way (so links like #send-and-run in the guides work)"""
    t = re.sub(r"<[^>]+>", "", text).strip().lower()
    t = re.sub(r"[^\w\- ]", "", t)
    return t.replace(" ", "-")


def data_uri(path):
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif",
            "svg": "image/svg+xml", "webp": "image/webp"}.get(ext, "application/octet-stream")
    with open(path, "rb") as f:
        return "data:%s;base64,%s" % (mime, base64.b64encode(f.read()).decode("ascii"))


class Converter(object):
    """Markdown -> HTML for one document. base: the .md's folder (for relative links and images)"""

    _INLINE = re.compile(
        r"(`+)(.+?)\1"                                    # 1,2 code
        r"|\[!\[([^\]]*)\]\(([^)]*)\)\]\(([^)]*)\)"       # 3,4,5 a linked image (a badge)
        r"|!\[([^\]]*)\]\(([^)\s]*)(?:\s+\"[^\"]*\")?\)"  # 6,7 image
        r"|\[([^\]]+)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)"   # 8,9 link
        r"|<(https?://[^>\s]+)>"                          # 10 autolink
        r"|\*\*(.+?)\*\*"                                 # 11 bold
        r"|(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?!\w)"        # 12 italic
    )

    def __init__(self, base=KIT, repo_url=REPO_URL):
        self.base = base
        self.repo_url = repo_url
        self.ids = {}
        self.headings = []  # (level, text, id)

    # ---- inline ----
    def href(self, target):
        """Links: web and #anchors as they are; a file in the repo goes to it on GitHub"""
        if re.match(r"^[a-z]+:", target) or target.startswith("#"):
            return target
        path, _, frag = target.partition("#")
        full = os.path.normpath(os.path.join(self.base, path))
        rel = os.path.relpath(full, KIT).replace("\\", "/")
        if rel.startswith(".."):
            return target
        kind = "tree" if os.path.isdir(full) else "blob"
        return "%s/%s/main/%s%s" % (self.repo_url, kind, rel, "#" + frag if frag else "")

    def image(self, alt, src):
        if re.match(r"^[a-z]+:", src):
            return ""  # Remote images (badges) need the network: left out
        p = os.path.normpath(os.path.join(self.base, src))
        if not os.path.exists(p):
            return html.escape(alt)
        return '<img class="md" alt="%s" src="%s">' % (html.escape(alt, quote=True), data_uri(p))

    def inline(self, text):
        text = plain(text)
        out, pos = [], 0
        for m in self._INLINE.finditer(text):
            out.append(html.escape(text[pos:m.start()], quote=False))
            pos = m.end()
            g = m.groups()
            if g[0]:
                out.append("<code>%s</code>" % html.escape(g[1].strip(), quote=False))
            elif g[2] is not None:
                img = self.image(g[2], g[3])
                out.append('<a href="%s">%s</a>' % (html.escape(self.href(g[4]), quote=True), img)
                           if img else "")
            elif g[5] is not None:
                out.append(self.image(g[5], g[6]))
            elif g[7]:
                out.append('<a href="%s">%s</a>' % (html.escape(self.href(g[8]), quote=True),
                                                     self.inline(g[7])))
            elif g[9]:
                out.append('<a href="%s">%s</a>' % (html.escape(g[9], quote=True),
                                                     html.escape(g[9], quote=False)))
            elif g[10]:
                out.append("<b>%s</b>" % self.inline(g[10]))
            elif g[11]:
                out.append("<i>%s</i>" % self.inline(g[11]))
        out.append(html.escape(text[pos:], quote=False))
        return "".join(out)

    # ---- blocks ----
    def heading_id(self, text):
        base = slug(text) or "section"
        n = self.ids.get(base, 0)
        self.ids[base] = n + 1
        return base if n == 0 else "%s-%d" % (base, n)

    @staticmethod
    def cells(line):
        """A table row's cells: split on | outside `code`, \\| is a literal bar"""
        s = line.strip()
        if s.startswith("|"):
            s = s[1:]
        if s.endswith("|") and not s.endswith("\\|"):
            s = s[:-1]
        out, cur, in_code = [], [], False
        i = 0
        while i < len(s):
            ch = s[i]
            if ch == "\\" and i + 1 < len(s) and s[i + 1] == "|":
                cur.append("|")
                i += 2
                continue
            if ch == "`":
                in_code = not in_code
            if ch == "|" and not in_code:
                out.append("".join(cur).strip())
                cur = []
            else:
                cur.append(ch)
            i += 1
        out.append("".join(cur).strip())
        return out

    @staticmethod
    def is_table_sep(line):
        return bool(re.match(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$", line))

    def code_block(self, info, body):
        words = info.split()
        lang = words[0] if words and "=" not in words[0] else ""
        name = ""
        for w in words:
            if w.startswith("name="):
                name = w[5:]
        label = LANGS.get(lang.lower(), lang)
        cap = ""
        if label or name:
            cap = "<figcaption>%s%s</figcaption>" % (
                html.escape(label), '<span class="name">%s</span>' % html.escape(name) if name else "")
        return '<figure class="code">%s<pre><code>%s</code></pre></figure>' % (
            cap, html.escape(plain("\n".join(body))))

    def convert(self, md, skip_title=True, skip_contents=True):
        """The body HTML. skip_title drops the first # heading (the cover shows the title);
        skip_contents drops a "## Contents" section (the generated table of contents replaces it)"""
        md = re.sub(r"<!--.*?-->", "", md, flags=re.S)  # Notes to the editor (screenshot slots)
        lines = md.replace("\r\n", "\n").replace("\t", "    ").split("\n")
        out, para = [], []
        lists = []  # [indent, tag] of the open lists, innermost last
        i = 0
        title_done = not skip_title
        blank_before = False

        def flush():
            if para:
                text = self.inline(" ".join(para)).strip()
                if text:
                    out.append("<p>%s</p>" % text)
                para.clear()

        def close_lists(to=-1):
            while lists and lists[-1][0] > to:
                out.append("</li></%s>" % lists.pop()[1])

        while i < len(lines):
            line = lines[i]
            s = line.strip()
            indent = len(line) - len(line.lstrip(" "))
            fence = re.match(r"^(\s*)(`{3,}|~{3,})(.*)$", line)
            if fence:
                flush()
                if lists and indent <= lists[0][0]:
                    close_lists()  # A block of its own; indented, it belongs to the list item
                mark, info, cut = fence.group(2), fence.group(3).strip(), len(fence.group(1))
                body = []
                i += 1
                while i < len(lines) and not lines[i].strip().startswith(mark):
                    b = lines[i]
                    body.append(b[cut:] if b[:cut].strip() == "" else b.lstrip())
                    i += 1
                i += 1
                out.append(self.code_block(info, body))
                blank_before = False
                continue
            if not s:
                flush()
                blank_before = True
                i += 1
                continue
            m = re.match(r"^(#{1,6})\s+(.*?)\s*#*$", s)
            if m and indent < 4:
                flush()
                close_lists()
                n, text = len(m.group(1)), m.group(2)
                if n == 1 and not title_done:
                    title_done = True
                    i += 1
                    continue
                if n == 2 and skip_contents and text.strip().lower() in ("contents", "table of contents"):
                    i += 1
                    while i < len(lines) and not re.match(r"^#{1,2}\s", lines[i]):
                        i += 1
                    continue
                hid = self.heading_id(text)
                self.headings.append((n, text, hid))
                out.append('<h%d id="%s">%s</h%d>' % (n, hid, self.inline(text), n))
                i += 1
                blank_before = False
                continue
            if re.match(r"^(-{3,}|\*{3,}|_{3,})$", s):
                flush()
                close_lists()
                out.append("<hr>")
                i += 1
                continue
            if "|" in s and i + 1 < len(lines) and self.is_table_sep(lines[i + 1]):
                flush()
                close_lists()
                head = self.cells(s)
                if any(head):
                    out.append("<table><thead><tr>%s</tr></thead><tbody>"
                               % "".join("<th>%s</th>" % self.inline(c) for c in head))
                else:  # A header row with nothing in it (a two-column list): left out
                    out.append("<table><tbody>")
                i += 2
                while i < len(lines) and "|" in lines[i] and lines[i].strip():
                    row = self.cells(lines[i])
                    row += [""] * (len(head) - len(row))
                    out.append("<tr>%s</tr>" % "".join("<td>%s</td>" % self.inline(c)
                                                       for c in row[:len(head)]))
                    i += 1
                out.append("</tbody></table>")
                continue
            if s.startswith(">"):
                flush()
                close_lists()
                quote = []
                while i < len(lines) and lines[i].strip().startswith(">"):
                    quote.append(lines[i].strip()[1:].strip())
                    i += 1
                out.append("<blockquote>%s</blockquote>" % self.inline(" ".join(quote)))
                continue
            m = re.match(r"^(\s*)([-*+]|(\d+)[.)])\s+(.*)$", line)
            if m:
                flush()
                ind = len(m.group(1))
                tag = "ol" if m.group(3) else "ul"
                if lists and ind < lists[-1][0]:
                    close_lists(ind)
                if lists and ind == lists[-1][0] and lists[-1][1] != tag:
                    close_lists(ind - 1)
                if not lists or ind > lists[-1][0]:
                    start = int(m.group(3)) if m.group(3) else 1
                    out.append("<%s%s><li>" % (tag, ' start="%d"' % start if start != 1 else ""))
                    lists.append([ind, tag])
                else:
                    out.append("</li><li>")
                # The item's text runs on over the next lines (bold and links can span them)
                text = [m.group(4)]
                i += 1
                while i < len(lines) and lines[i].strip() and len(lines[i]) - len(lines[i].lstrip(" ")) > ind \
                        and not re.match(r"^\s*([-*+]|\d+[.)])\s+|^\s*(`{3,}|~{3,})|^\s*#{1,6}\s", lines[i]):
                    text.append(lines[i].strip())
                    i += 1
                out.append(self.inline(" ".join(text)))
                blank_before = False
                continue
            if lists and indent > lists[-1][0]:  # More of the list item
                if blank_before:
                    para.append(s)
                    # A paragraph of its own inside the item
                    j = i + 1
                    while j < len(lines) and lines[j].strip() and not re.match(
                            r"^\s*([-*+]|\d+[.)])\s+|^\s*(`{3,}|~{3,})", lines[j]):
                        para.append(lines[j].strip())
                        j += 1
                    out.append("<p>%s</p>" % self.inline(" ".join(para)))
                    para.clear()
                    i = j
                else:
                    out.append(" " + self.inline(s))
                    i += 1
                blank_before = False
                continue
            close_lists()
            para.append(s)
            blank_before = False
            i += 1
        flush()
        close_lists()
        return "\n".join(out)


def changelog_version(path=os.path.join(KIT, "CHANGELOG.md")):
    """The version for the cover: the top "## [x.y.z]" heading of CHANGELOG.md. An [Unreleased]
    section with something in it reads "x.y.z+ (unreleased)", after the last release."""
    try:
        text = open(path, encoding="utf-8").read()
    except OSError:
        return ""
    heads = list(re.finditer(r"^## \[([^\]]+)\][^\n]*$", text, re.M))
    if not heads:
        return ""
    first = heads[0].group(1)
    if first.lower() != "unreleased":
        return "v" + first
    body = text[heads[0].end():heads[1].start() if len(heads) > 1 else len(text)]
    last = heads[1].group(1) if len(heads) > 1 else ""
    if not body.strip() and last:
        return "v" + last
    return ("v%s+ (unreleased)" % last) if last else "unreleased"


def toc_html(headings):
    items = [(t, h) for lvl, t, h in headings if lvl == 2]
    if not items:
        return ""
    conv = Converter()
    return ('<nav class="toc"><h2>Contents</h2><ol>%s</ol></nav>'
            % "".join('<li><a href="#%s">%s</a></li>' % (h, conv.inline(t)) for t, h in items))


def page(title, body, toc="", kicker="CalcSuite", version=None, subtitle=""):
    """A whole HTML document: the cover header, the table of contents, the body"""
    version = changelog_version() if version is None else version
    icon = os.path.join(KIT, "assets", "app.png")
    img = '<img src="%s" alt="">' % data_uri(icon) if os.path.exists(icon) else ""
    meta = []
    if subtitle:
        meta.append(html.escape(subtitle))
    meta.append("CalcSuite <b>%s</b>" % html.escape(version) if version else "CalcSuite")
    meta.append(html.escape(REPO_URL.replace("https://", "")))
    cover = ('<header class="cover">%s<div><div class="kicker">%s</div><h1>%s</h1>'
             '<div class="meta">%s</div></div></header>'
             % (img, html.escape(kicker), html.escape(title), " &nbsp;\u00b7&nbsp; ".join(meta)))
    # The footer names the document (a CSS string: quotes and backslashes escaped)
    foot = "CalcSuite  ·  " + title
    foot_css = '@page { @bottom-left { content: "%s"; } } @page :first { @bottom-left { content: none; } }' % (
        foot.replace("\\", "\\\\").replace('"', '\\"'))
    if toc:
        body = body.replace("<!--TOC-->", toc, 1) if "<!--TOC-->" in body else toc + body
    return ("<!doctype html><html lang='en'><head><meta charset='utf-8'><title>%s</title>"
            "<style>%s%s</style></head><body>%s%s</body></html>"
            % (html.escape(title), CSS, foot_css, cover, body.replace("<!--TOC-->", "")))


def markdown_page(md_path, title=None, version=None, kicker="CalcSuite", toc=True):
    """The HTML document for one Markdown file"""
    text = open(md_path, encoding="utf-8").read()
    if not title:
        m = re.search(r"^#\s+(.+)$", text, re.M)
        title = m.group(1).strip() if m else os.path.splitext(os.path.basename(md_path))[0]
    conv = Converter(base=os.path.dirname(os.path.abspath(md_path)))
    body = conv.convert(text)
    contents = ""
    if toc:
        t = toc_html(conv.headings)
        if t:
            contents = t + '<div class="toc-break"></div>'
            # The intro (what comes before the first ## heading) stays above the contents
            cut = body.find("<h2 ")
            body = (body[:cut] + "<!--TOC-->" + body[cut:]) if cut > 0 else "<!--TOC-->" + body
    return page(title, body, contents, kicker=kicker, version=version)


def find_edge():
    """msedge.exe: the usual install folders, then PATH. None when there is none."""
    for p in EDGE_PATHS:
        if os.path.exists(p):
            return p
    return shutil.which("msedge") or shutil.which("msedge.exe")


def html_to_pdf(doc, pdf, edge=None, outline=True):
    """Prints an HTML document (a string) to a PDF with headless Edge. Returns the PDF's size.
    outline: bookmarks from the headings. They need a tagged PDF, which is about 2.5 times the
    size (a 90-page reference: 2.2 MB instead of 0.9), so the long references go without."""
    edge = edge or find_edge()
    if not edge:
        raise SystemExit("Microsoft Edge wasn't found (it prints the PDFs). Looked in: %s, and "
                         "msedge on PATH." % "; ".join(EDGE_PATHS))
    pdf = os.path.abspath(pdf)
    os.makedirs(os.path.dirname(pdf), exist_ok=True)
    # Edge prints to a fresh file with its own throwaway profile: with the user's profile (Edge
    # already open) headless Edge writes nothing. It can also finish writing after its launcher
    # exits, so wait for the size to settle.
    work = tempfile.mkdtemp(prefix="calcsuite_pdf_")
    src = os.path.join(work, "doc.html")
    out = os.path.join(work, "out.pdf")
    with open(src, "w", encoding="utf-8") as f:
        f.write(doc)
    try:
        subprocess.run([edge, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                        "--generate-pdf-document-outline" if outline else "--disable-pdf-tagging",
                        "--no-first-run",
                        "--disable-extensions", "--user-data-dir=" + os.path.join(work, "profile"),
                        "--print-to-pdf=" + out, "file:///" + src.replace("\\", "/")],
                       check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=180)
        last, still = -1, 0
        for _ in range(300):  # Up to 60 s
            size = os.path.getsize(out) if os.path.exists(out) else -1
            still = still + 1 if size > 0 and size == last else 0
            if still >= 3:
                break
            last = size
            time.sleep(0.2)
        if not os.path.exists(out) or os.path.getsize(out) == 0:
            raise SystemExit("Edge didn't write " + pdf)
        shutil.copyfile(out, pdf)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return os.path.getsize(pdf)


def page_count(pdf):
    """The number of pages in a PDF Edge wrote (its /Type /Page objects)"""
    with open(pdf, "rb") as f:
        data = f.read()
    m = re.findall(rb"/Type\s*/Pages\b[^>]*?/Count\s+(\d+)", data)
    if m:
        return max(int(x) for x in m)
    return len(re.findall(rb"/Type\s*/Page\b(?!s)", data))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", help="a .md file")
    ap.add_argument("pdf", help="the PDF to write")
    ap.add_argument("--title", help="the cover title (default: the file's # heading)")
    ap.add_argument("--version", help="the version on the cover (default: from CHANGELOG.md)")
    ap.add_argument("--no-toc", action="store_true", help="no table of contents")
    ap.add_argument("--html", help="also write the HTML here (to look at it in a browser)")
    a = ap.parse_args()
    doc = markdown_page(a.src, a.title, a.version, toc=not a.no_toc)
    if a.html:
        with open(a.html, "w", encoding="utf-8") as f:
            f.write(doc)
    size = html_to_pdf(doc, a.pdf)
    print("Wrote %s (%d bytes, %d pages)" % (a.pdf, size, page_count(a.pdf)))


if __name__ == "__main__":
    main()
