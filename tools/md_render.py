"""A small Markdown renderer for the Guide panel: CalcSuite's own docs in a Tk Text widget.

parse(text) -> blocks (pure, tested in tools/selftest):
    ("h", level, spans, anchor)          a heading
    ("p", spans)                         a paragraph
    ("li", depth, marker, spans)         a list item ("-" or "1.")
    ("table", header, rows)              header and rows: lists of cells, each cell spans
    ("code", info, name, text)           a fenced block; name from "name=..." in its info
    ("quote", spans)
    ("hr",)
spans: [(style, text, href)], style "" / "b" / "i" / "code" / "link".

render(text_widget, blocks, actions) draws them; actions["copy"](text) and
actions["send"](name, info, text) are called by the buttons under the code blocks (Send only
on blocks with a name=).
"""

import re

_INLINE = re.compile(
    r"(`+)(.+?)\1"                          # code
    r"|\*\*(.+?)\*\*"                       # bold
    r"|(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?!\w)"  # italic
    r"|!\[([^\]]*)\]\(([^)]*)\)"            # image: its alt text
    r"|\[([^\]]+)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)"  # link
    r"|<(https?://[^>\s]+)>"                # autolink
)


def inline(text):
    """A line of Markdown -> spans"""
    text = re.sub(r"<!--.*?-->", "", text)
    spans, pos = [], 0
    for m in _INLINE.finditer(text):
        if m.start() > pos:
            spans.append(("", text[pos:m.start()], None))
        if m.group(1):
            spans.append(("code", m.group(2).strip(" ") if m.group(2).strip(" ") else m.group(2), None))
        elif m.group(3) is not None:
            spans += [("b" if s == "" else s, t, h) for s, t, h in inline(m.group(3))]
        elif m.group(4) is not None:
            spans.append(("i", m.group(4), None))
        elif m.group(6) is not None:
            if m.group(5):
                spans.append(("i", "[%s]" % m.group(5), None))
        elif m.group(7) is not None:
            spans.append(("link", m.group(7), m.group(8)))
        elif m.group(9):
            spans.append(("link", m.group(9), m.group(9)))
        pos = m.end()
    if pos < len(text):
        spans.append(("", text[pos:], None))
    return [s for s in spans if s[1]]


def plain(spans):
    return "".join(t for _s, t, _h in spans)


def anchor_of(text):
    """GitHub's anchor for a heading: lower case, punctuation dropped, spaces to -"""
    t = re.sub(r"[^\w\- ]", "", text.strip().lower())
    return t.replace(" ", "-")


def _cells(line):
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|") and not line.endswith("\\|"):
        line = line[:-1]
    cells, cur, in_code = [], "", 0  # in_code: the length of the backtick run that opened a code span
    i = 0
    while i < len(line):
        c = line[i]
        if c == "\\" and i + 1 < len(line) and line[i + 1] == "|":
            cur += "|"
            i += 2
            continue
        if c == "`":
            # A run of backticks opens a code span; only a run as long closes it (``  ` `` is a
            # code span holding one backtick, as on GitHub)
            n = len(line[i:]) - len(line[i:].lstrip("`"))
            if not in_code:
                in_code = n
            elif n == in_code:
                in_code = 0
            cur += line[i:i + n]
            i += n
            continue
        if c == "|" and not in_code:
            cells.append(cur.strip())
            cur = ""
        else:
            cur += c
        i += 1
    cells.append(cur.strip())
    return cells


_RULE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")
_LI = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")


def parse(text):
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blocks, para, i = [], [], 0

    def flush():
        if para:
            blocks.append(("p", inline(" ".join(l.strip() for l in para))))
            del para[:]

    in_comment = False
    while i < len(lines):
        line = lines[i]
        if in_comment:
            if "-->" in line:
                in_comment = False
            i += 1
            continue
        if line.strip().startswith("<!--") and "-->" not in line:
            flush()
            in_comment = True
            i += 1
            continue
        fence = re.match(r"^\s*(```+|~~~+)\s*(.*)$", line)
        if fence:
            flush()
            mark, info = fence.group(1), fence.group(2).strip()
            body = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith(mark):
                body.append(lines[i])
                i += 1
            i += 1
            m = re.search(r"\bname=([\w.\-]+)", info)
            indent = min((len(l) - len(l.lstrip()) for l in body if l.strip()), default=0)
            blocks.append(("code", info, m.group(1) if m else None,
                           "\n".join(l[indent:] for l in body)))
            continue
        if not line.strip():
            flush()
            i += 1
            continue
        h = re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", line)
        if h:
            flush()
            blocks.append(("h", len(h.group(1)), inline(h.group(2)), anchor_of(plain(inline(h.group(2))))))
            i += 1
            continue
        if re.match(r"^\s*([-*_])(\s*\1){2,}\s*$", line):
            flush()
            blocks.append(("hr",))
            i += 1
            continue
        if "|" in line and i + 1 < len(lines) and _RULE.match(lines[i + 1]):
            flush()
            header = [inline(c) for c in _cells(line)]
            rows = []
            i += 2
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                rows.append([inline(c) for c in _cells(lines[i])])
                i += 1
            blocks.append(("table", header, rows))
            continue
        li = _LI.match(line)
        if li:
            flush()
            depth = len(li.group(1).replace("\t", "    ")) // 2
            item = [li.group(3)]
            i += 1
            # Continuation lines: indented, not a new item, not blank
            while i < len(lines) and lines[i].strip() and not _LI.match(lines[i]) and \
                    lines[i].startswith((" ", "\t")) and not re.match(r"^\s*(```|~~~)", lines[i]):
                item.append(lines[i].strip())
                i += 1
            marker = li.group(2) if li.group(2)[0].isdigit() else "-"
            blocks.append(("li", depth, marker, inline(" ".join(item))))
            continue
        if line.lstrip().startswith(">"):
            flush()
            q = []
            while i < len(lines) and lines[i].lstrip().startswith(">"):
                q.append(lines[i].lstrip()[1:].strip())
                i += 1
            blocks.append(("quote", inline(" ".join(q))))
            continue
        para.append(line)
        i += 1
    flush()
    return blocks


def headings(blocks, max_level=3):
    """[(level, text, anchor)] for the Contents list"""
    return [(b[1], plain(b[2]), b[3]) for b in blocks if b[0] == "h" and b[1] <= max_level]


# ---- Drawing into a Tk Text widget ----

def render(box, blocks, actions, colors, fonts):
    """Draws the blocks into box (a tk.Text, emptied first). colors: fg, dim, accent, code_bg,
    link, rule; fonts: body, bold, italic, code, h1, h2, h3. Returns {anchor: text index}."""
    import tkinter as tk
    import webbrowser
    box.configure(state="normal")
    box.delete("1.0", "end")
    for tag in box.tag_names():
        if tag.startswith("href"):
            box.tag_delete(tag)
    box.tag_configure("body", font=fonts["body"], foreground=colors["fg"], spacing1=2, spacing3=4,
                      lmargin1=4, lmargin2=4)
    box.tag_configure("b", font=fonts["bold"])
    box.tag_configure("i", font=fonts["italic"])
    box.tag_configure("code", font=fonts["code"], background=colors["code_bg"], foreground="#f0d9b5")
    box.tag_configure("link", foreground=colors["link"], underline=True)
    for n in (1, 2, 3):
        box.tag_configure("h%d" % n, font=fonts["h%d" % n], foreground=colors["fg"],
                          spacing1=14 if n < 3 else 10, spacing3=6)
    box.tag_configure("li", lmargin1=14, lmargin2=28)
    box.tag_configure("li2", lmargin1=32, lmargin2=46)
    box.tag_configure("pre", font=fonts["code"], background=colors["code_bg"], foreground="#e6e1d6",
                      lmargin1=10, lmargin2=10, rmargin=6, spacing1=0, spacing3=0)
    box.tag_configure("table", font=fonts["code"], foreground=colors["fg"], lmargin1=6, lmargin2=6)
    box.tag_configure("th", font=(fonts["code"][0], fonts["code"][1], "bold"))
    box.tag_configure("quote", foreground=colors["dim"], lmargin1=18, lmargin2=18)
    box.tag_configure("rule", foreground=colors["rule"])
    box.tag_configure("found", background="#5a3a1c", foreground="#ffffff")
    anchors = {}
    links = [0]

    def spans_out(spans, base):
        for style, text, href in spans:
            tags = [base]
            if style:
                tags.append(style)
            if href:
                links[0] += 1
                t = "href%d" % links[0]
                tags.append(t)
                box.tag_bind(t, "<Button-1>", lambda e, u=href: _open(u))
                box.tag_bind(t, "<Enter>", lambda e: box.configure(cursor="hand2"))
                box.tag_bind(t, "<Leave>", lambda e: box.configure(cursor=""))
            box.insert("end", text, tuple(tags))

    def _open(url):
        if url.startswith("#"):
            if url[1:] in anchors:  # A section of this page: its heading to the top
                box.yview("h_" + url[1:])
            return
        if url.startswith(("http://", "https://")):
            webbrowser.open(url)

    for b in blocks:
        kind = b[0]
        if kind == "h":
            level = min(3, b[1])
            anchors[b[3]] = box.index("end-1c")
            box.mark_set("h_" + b[3], "end-1c")
            box.mark_gravity("h_" + b[3], "left")
            spans_out([(s if s != "code" else "", t, h) for s, t, h in b[2]], "h%d" % level)
            box.insert("end", "\n", "h%d" % level)
        elif kind == "p":
            spans_out(b[1], "body")
            box.insert("end", "\n", "body")
        elif kind == "li":
            bullet = "• " if b[2] == "-" else b[2] + " "
            base = "li2" if b[1] > 0 else "li"
            box.insert("end", bullet, ("body", base))
            spans_out(b[3], "body")
            box.tag_add(base, "end-1c linestart", "end-1c")
            box.insert("end", "\n", ("body", base))
        elif kind == "quote":
            spans_out(b[1], "quote")
            box.insert("end", "\n", "quote")
        elif kind == "hr":
            box.insert("end", "─" * 40 + "\n", "rule")
        elif kind == "table":
            header, rows = b[1], b[2]
            ncol = max([len(header)] + [len(r) for r in rows])
            widths = [0] * ncol
            for r in [header] + rows:
                for k, c in enumerate(r):
                    widths[k] = min(34, max(widths[k], len(plain(c))))
            for r_i, r in enumerate([header] + rows):
                for k in range(ncol):
                    cell = r[k] if k < len(r) else []
                    text = plain(cell)
                    pad = max(0, widths[k] - len(text))
                    base = "th" if r_i == 0 else "table"
                    spans_out([(s if s in ("b", "link") else "", t, h) for s, t, h in cell], base)
                    box.insert("end", " " * pad + ("  " if k < ncol - 1 else ""), base)
                box.insert("end", "\n", "table")
                if r_i == 0:
                    box.insert("end", "  ".join("─" * w for w in widths) + "\n", ("table", "rule"))
            box.insert("end", "\n", "body")
        elif kind == "code":
            info, name, text = b[1], b[2], b[3]
            box.insert("end", text + "\n", "pre")
            bar = tk.Frame(box, bg=colors["bg"])
            if name:
                tk.Label(bar, text=name, bg=colors["bg"], fg=colors["dim"]).pack(side="left", padx=(0, 8))
            btn = dict(bg="#1b1c20", fg=colors["fg"], activebackground="#26272c",
                       activeforeground="#ffffff", relief="flat", bd=0, padx=8, pady=2,
                       takefocus=0, cursor="hand2")
            tk.Button(bar, text="Copy", command=lambda t=text: actions["copy"](t), **btn).pack(side="left")
            if name and actions.get("send"):
                tk.Button(bar, text="Send to calculator",
                          command=lambda n=name, i=info, t=text: actions["send"](n, i, t),
                          **dict(btn, fg=colors["accent"])).pack(side="left", padx=(6, 0))
            box.window_create("end", window=bar, padx=10, pady=4)
            box.insert("end", "\n\n", "body")
    box.configure(state="disabled")
    return anchors
