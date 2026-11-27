"""Send a program to a TI-84 Plus CE or a TI-89 Titanium: TI-Basic as text, or a TI file.

    python -I tools/send_ti.py --calc 84 hello.txt              text -> HELLO.8xp, sent
    python -I tools/send_ti.py --calc 89 hello.tib --name hi     text -> hi.89p, sent
    python -I tools/send_ti.py --calc 84 GAME.8xp                a TI file as it is
    python -I tools/send_ti.py --calc 84 hello.txt --out HELLO.8xp   only make the file

A text file (.txt, .tib, .bas) is TI-Basic as you would type it:
- TI-84 Plus CE: turned into the calculator's tokens here (calc_files.tokenize_84). The PC
  spellings work: -> for the store arrow, <= >= !=, sqrt(, pi, theta, ^2, ^-1, L1, Y1, E in a
  number for the EE key; or the calculator's own symbols (→ ≤ ≥ ≠ √ π θ ² ⁻¹). A leading ':'
  on a line is dropped. The program's name: --name, else the file's name (up to 8 capitals).
- TI-89 Titanium: sent as text, the way the 89's own Program Editor keeps a program; the
  calculator tokenizes it the first time it runs. The text may start with the program's own
  line (`zztest()` or `zztest(a,b)`) and Prgm ... EndPrgm (Func ... EndFunc makes a
  function); without them it is the body of a program with no arguments. -> <= >= != sqrt( pi
  theta and the symbols become the 89's characters. Run it with `name()`.

Nothing on the calculator is replaced unless you add --replace: a variable with the same name
stops the send. After sending, the calculator's list is read again to check it arrived.

Exit code 0 = sent, 1 = usage or a file the calculator can't take, 2 = no calculator,
3 = USB driver problem, 4 = link error, 5 = not found after sending, 6 = local file error,
7 = a variable with that name is already on the calculator.
"""

import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import calc_files as cf  # noqa: E402
import nspire_link  # noqa: E402

SOURCE_EXTS = (".txt", ".tib", ".bas")
TI_EXTS = {
    "ti84": ("*.8xp *.8xv *.8xl *.8xm *.8xn *.8xs *.8xy *.8xc *.8ci *.8ca *.8xd *.8xg *.8xw "
             "*.8xz *.8xt"),
    "ti89": "*.89p *.89f *.89e *.89l *.89m *.89c *.89t *.89s *.89d *.89a *.89i *.89x *.89y *.89z *.89g",
}
TITLE = {"ti84": "TI-84 Plus CE", "ti89": "TI-89 Titanium"}


class NeedName(ValueError):
    """A text file whose name can't be the program's: ask for one"""


def slug_of(calc):
    s = str(calc).lower().replace("-", "").replace(" ", "")
    if s in ("84", "ti84", "84ce", "ti84ce", "ti84plusce"):
        return "ti84"
    if s in ("89", "ti89", "89t", "ti89t", "ti89titanium"):
        return "ti89"
    raise ValueError("--calc is 84 or 89")


def read_text(path):
    with open(path, "rb") as f:
        raw = f.read()
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def is_ti_file(path):
    with open(path, "rb") as f:
        return f.read(4) == b"**TI"


def variables(blob, slug):
    """The variables in a TI file for this calculator: [(folder, name, type)] as the link's
    listing shows them. Raises ValueError for a file the calculator can't take."""
    if blob[:8] == b"**TIFL**":
        raise ValueError("an app or OS file: those can't be sent here")
    if slug == "ti84":
        if blob[:8] in (b"**TI89**", b"**TI92P*"):
            raise ValueError("a TI-89 file: send it to the TI-89 Titanium")
        out = []
        for vtype, name, _v, _a, _d in cf.read_ti8x(blob):
            if vtype in (0x13, 0x23, 0x24, 0x25, 0x26, 0x27):
                raise ValueError("backups, apps and OS files can't be sent here")
            out.append((b"", cf.detokenize_name_84(name, vtype).encode("utf-8"), vtype))
        return out
    if blob[:8] == b"**TI83F*":
        raise ValueError("a TI-84 Plus file: send it to the TI-84 Plus CE")
    out = []
    for folder, name, vtype, _a, _d in cf.read_ti89(blob):
        if vtype in (0x18, 0x1D, 0x23, 0x24):
            raise ValueError("backups, apps and OS files can't be sent here")
        out.append((folder, name, vtype))
    return out


def prepare(path, slug, name=None, out_dir=None, warnings=None):
    """A text or TI file -> (the TI file to send, [(folder, name, type)]). A text file is
    turned into a .8xp / .89p in out_dir (a temporary folder by default). Raises NeedName when
    a text file has no usable name, ValueError (or OSError) for anything else. A list as
    `warnings` gets the 84 tokenizer's notes on words that look like misspelt commands."""
    stem, ext = os.path.splitext(os.path.basename(path))
    if is_ti_file(path):
        with open(path, "rb") as f:
            return path, variables(f.read(), slug)
    if ext.lower() not in SOURCE_EXTS:
        raise ValueError("not a TI file, and not TI-Basic text (%s)" % ", ".join(SOURCE_EXTS))
    text = read_text(path)
    out_dir = out_dir or os.path.join(tempfile.gettempdir(), "calcsuite_send")
    os.makedirs(out_dir, exist_ok=True)
    if slug == "ti84":
        name = (name or cf.name_84_from(stem) or "").upper()
        if not name:
            raise NeedName("%s: what should the program be called? (up to 8 capitals or "
                           "digits, a letter first)" % os.path.basename(path))
        blob = cf.program_8xp(text, name, warnings=warnings)
        out = os.path.join(out_dir, name.replace("θ", "theta") + ".8xp")
    else:
        try:
            name, vtype, blob = cf.program_89p(text, name, default=cf.name_89_from(stem))
        except ValueError as e:
            if "no program name" in str(e):
                raise NeedName("%s: what should the program be called? (up to 8 letters or "
                               "digits, a letter first)" % os.path.basename(path))
            raise
        out = os.path.join(out_dir, name + (".89p" if vtype == 0x12 else ".89f"))
    with open(out, "wb") as f:
        f.write(blob)
    return out, variables(blob, slug)


def clashes(wanted, listing, slug):
    """The names in `wanted` ([(folder, name, type)]) already on the calculator (its `ls`)"""
    have = set()
    for i in cf.parse_dusb_ls(listing):
        key = i["name"].lower() if slug == "ti89" else i["name"]
        have.add(((i["folder"] or b"main").lower() if slug == "ti89" else b"", key))
    out = []
    for folder, name, _t in wanted:
        key = ((folder or b"main").lower(), name.lower()) if slug == "ti89" else (b"", name)
        if key in have:
            out.append(cf.name_text(name))
    return out


def how_to_run(slug, wanted):
    progs = [cf.name_text(n) for _f, n, t in wanted if t in (0x05, 0x06, 0x12, 0x13)]
    if not progs:
        return ""
    if slug == "ti84":
        return "Run it: PRGM, pick %s, Enter Enter" % progs[0]
    return "Run it: type %s() and Enter" % progs[0]


# ---- From a window (mirror.py's "Send program...") ----

def send_from_window(mirror, kit):
    """Mirror's Send program for the 84 and the 89: pick a file, make the TI file, ask before
    replacing, send on the link thread with progress in the status line"""
    from tkinter import filedialog, messagebox, simpledialog
    slug, root = mirror.calc.slug, mirror.root
    progs = os.path.join(kit, "programs")
    path = filedialog.askopenfilename(
        parent=root, title="Send to the %s" % mirror.calc.title,
        initialdir=progs if os.path.isdir(progs) else kit,
        filetypes=[("TI-Basic text and TI files", "*.txt *.tib *.bas " + TI_EXTS[slug]),
                   ("All files", "*.*")])
    if not path:
        return
    ti, wanted = prepare_asking(path, slug, root, os.path.join(kit, "build"), mirror.set_status,
                                simpledialog)
    if not ti:
        return
    mirror.set_status("Checking what's on the %s..." % mirror.calc.title)

    def listed(code, lines):  # On the link thread
        root.after(0, lambda: go(code, lines))

    def go(code, lines):
        if code:
            mirror.set_status("Not sent: couldn't read the calculator's list (%s)" % lines[-1:])
            return
        same = clashes(wanted, lines, slug)
        if same and not messagebox.askyesno(
                "Replace?", "%s %s already on the %s. Replace?" % (
                    ", ".join(same), "is" if len(same) == 1 else "are", mirror.calc.title),
                parent=root):
            mirror.set_status("Not sent")
            return
        base = os.path.basename(ti)

        def progress(n, total):
            mirror.set_status("Sending %s: %d%%" % (base, 100 * n // total if total else 0))

        def sent(code, lines):
            ok = [l for l in lines if l.startswith(("OK", "ERR"))]
            mirror.set_status(("Sent %s. %s" % (base, how_to_run(slug, wanted))) if code == 0 else
                              "Not sent: %s" % (ok[-1][4:] if ok else "exit %d" % code))
        mirror.queue("send " + os.path.abspath(ti), None, sent, progress)
    mirror.queue("ls", None, listed)


def prepare_asking(path, slug, parent, out_dir, say, simpledialog):
    """prepare(), asking for a name when the file's own can't be one. (TI file, variables) or
    (None, None) with the reason given to say()"""
    name = None
    for _ in range(3):
        try:
            warnings = []
            ti, wanted = prepare(path, slug, name, out_dir, warnings)
            if warnings:
                from tkinter import messagebox
                more = "\n... and %d more" % (len(warnings) - 8) if len(warnings) > 8 else ""
                if not messagebox.askyesno(
                        "Check the program", "%s: these look like mistakes:\n\n%s%s\n\nSend it "
                        "anyway?" % (os.path.basename(path), "\n\n".join(warnings[:8]), more),
                        icon="warning", parent=parent):
                    say("Not sent: %s" % warnings[0])
                    return None, None
            return ti, wanted
        except NeedName as e:
            name = simpledialog.askstring("Program name", str(e), parent=parent)
            if not name:
                say("Not sent: no name")
                return None, None
            name = name.strip()
        except (OSError, ValueError) as e:
            say("Not sent: %s: %s" % (os.path.basename(path), e))
            return None, None
    say("Not sent: that name can't be used")
    return None, None


# ---- The command line ----

HELP = {
    2: "No %s found on USB: plugged in with a data cable, switched on?",
    3: "The calculator is on USB but can't be opened: WinUSB driver (README, Zadig), or another "
       "program (TI Connect, the mirror) has it.",
    4: "The calculator didn't answer: switch it on, go to the home screen, try again.",
}


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(description="Send a program to a TI-84 Plus CE or TI-89 Titanium")
    ap.add_argument("file")
    ap.add_argument("--calc", required=True, help="84 or 89")
    ap.add_argument("--name", help="the program's name (text files)")
    ap.add_argument("--replace", action="store_true", help="replace a variable of the same name")
    ap.add_argument("--out", help="only write the TI file here, send nothing")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    try:
        slug = slug_of(a.calc)
        if not os.path.isfile(a.file):
            print("ERROR: no such file: %s" % a.file)
            return 6
        warnings = []
        ti, wanted = prepare(a.file, slug, a.name, warnings=warnings)  # Made in a temp folder
        for w in warnings:
            print("WARNING: " + w)
    except (ValueError, OSError) as e:
        print("ERROR: %s" % e)
        return 1
    if a.out:
        if os.path.abspath(ti) != os.path.abspath(a.out):
            shutil.copyfile(ti, a.out)
        print("Wrote %s" % a.out)
        return 0
    try:
        s = nspire_link.Session(cli=nspire_link.CLI_84 if slug == "ti84" else nspire_link.CLI_89)
    except nspire_link.LinkError as e:
        for l in e.lines:
            print("  " + l)
        print("ERROR: " + HELP.get(e.code, "link error %d" % e.code).replace("%s", TITLE[slug]))
        return e.code
    with s:
        code, lines = s.cmd("ls")
        if code:
            print("ERROR: couldn't read the calculator's list: %s" % "; ".join(lines[-1:]))
            return code
        same = clashes(wanted, lines, slug)
        if same and not a.replace:
            print("ERROR: already on the %s: %s (add --replace to replace it)" % (TITLE[slug],
                                                                                 ", ".join(same)))
            return 7
        print("Sending %s to the %s..." % (os.path.basename(ti), TITLE[slug]))

        def progress(n, total):
            print("  %d%% (%d of %d bytes)" % (100 * n // total if total else 0, n, total))
        code, lines = s.cmd("send " + os.path.abspath(ti), progress)
        for l in lines:
            if l.startswith("ERR"):
                print("  " + l[4:])
        if code:
            print("ERROR: not sent")
            return code
        code, after = s.cmd("ls")
    missing = [cf.name_text(n) for f, n, t in wanted if not clashes([(f, n, t)], after, slug)]
    if missing:
        print("ERROR: sent, but not in the calculator's list: %s" % ", ".join(missing))
        return 5
    print("Sent and found on the calculator: %s. %s" % (
        ", ".join(cf.name_text(n) for _f, n, _t in wanted), how_to_run(slug, wanted)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
