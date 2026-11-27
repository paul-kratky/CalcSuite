"""Send a .tns document to a TI-Nspire CX II (CAS) handheld over USB, no TI software.

    python -I tools/send_to_calc.py --list                    show the connected handheld
    python -I tools/send_to_calc.py build/quadratic.tns       upload to My Documents
    python -I tools/send_to_calc.py build/quadratic.tns --folder Python
                                                              upload to My Documents/Python
    python -I tools/send_to_calc.py --ls [/Python]            list a folder on the handheld

Uses tools/bin/nspire-cli.exe (built from third_party/libnspire by tools/build_tools.py).
After the upload the file is read back from the handheld and compared byte for byte.
An existing file with the same name is replaced.

Exit code 0 = ok, 1 = usage error, 2 = no handheld, 3 = USB driver problem,
4 = link error, 5 = verify failed, 6 = local file error.
"""

import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import nspire_link  # noqa: E402  (one connection for every step)
CLI = os.path.join(HERE, "bin", "nspire-cli.exe")
TIMEOUT_S = 90

HELP = {
    2: ("No TI-Nspire found on USB.\n"
        "  - Plug the handheld in with a data USB cable (the one that came with it) and\n"
        "    turn it on (press [home/on]). Wake it if the screen is off.\n"
        "  - Try another USB port or cable. Some cables only charge.\n"
        "  - Run: python -I tools/send_to_calc.py --list"),
    3: ("The handheld is on USB, but Windows has no WinUSB driver bound to it, or another\n"
        "  program has it open.\n"
        "  - Close TI-Nspire Student/Teacher Software and any Chrome tab running\n"
        "    TI-Nspire CX II Connect, then unplug and replug the handheld.\n"
        "  - If it still fails: see README.md, 'One-time setup: USB driver'."),
    4: ("The handheld did not answer. It takes ONE USB connection per plug-in:\n"
        "  - Unplug it, wait 3 s, plug it back in, then run this again.\n"
        "  - Screen on, Home screen, no dialog open; close TI software / CX II Connect.\n"
        "  - Press-to-Test (exam) mode blocks normal file transfer: leave it first."),
    5: ("The file arrived but reading it back gave different bytes. Send it again;\n"
        "  if it keeps failing, try another cable or port."),
    6: "Could not read the local file.",
}


def run_cli(args):
    if not os.path.isfile(CLI):
        print("ERROR: %s is missing: run python -I tools/build_tools.py" % CLI)
        sys.exit(1)
    try:
        p = subprocess.run([CLI] + args, capture_output=True, text=True, timeout=TIMEOUT_S,
                           cwd=os.path.dirname(CLI))
    except subprocess.TimeoutExpired:
        return 4, ["ERR timed out after %d s" % TIMEOUT_S]
    lines = [l.rstrip() for l in (p.stdout + p.stderr).splitlines() if l.strip()]
    return p.returncode, lines


def run_cli_retry(args, tries=3):
    """The CX II handshake occasionally fails on the first try: retry link errors."""
    code, lines = run_cli(args)
    n = 1
    while code == 4 and n < tries:
        time.sleep(1.5)
        code, lines = run_cli(args)
        n += 1
    return code, lines


def fail(code, lines):
    for l in lines:
        if l.startswith("ERR"):
            print("  nspire-cli: " + l[4:])
    print("ERROR: " + HELP.get(code, "nspire-cli failed with exit code %d" % code))
    return code


def devices():
    """Print connected TI devices. Returns (exit code, lines)."""
    code, lines = run_cli(["devices"])
    for l in lines:
        if l.startswith("DEV "):
            m = dict(re.findall(r'(\w+)=("[^"]*"|\S+)', l[4:]))
            print("USB: %s (%s:%s) driver=%s" % (m.get("model", "?").strip('"'),
                                                m.get("vid"), m.get("pid"), m.get("open")))
    return code, lines


def info():
    code, lines = run_cli_retry(["info"])
    if code:
        return code, {}
    d = {}
    for l in lines:
        if l.startswith("INFO "):
            for k, v in re.findall(r"(\w+)=(\S+(?: \(\S+\))?)", l[5:]):
                d[k] = v
    return 0, d


def os_tuple(text):
    try:
        return tuple(int(x) for x in text.split("."))
    except (ValueError, AttributeError):
        return ()


def show_info(d):
    free = d.get("storage_free", "0")
    try:
        free = "%.1f MB free" % (int(free) / 1e6)
    except ValueError:
        free = "? free"
    print("Handheld: %s, OS %s, %s, battery %s" % (d.get("name", "?"), d.get("os", "?"), free,
                                                    d.get("battery", "?")))
    v = os_tuple(d.get("os", ""))
    if v and v < (5, 2):
        print("WARNING: OS %s is older than 5.2: this handheld cannot run Python programs."
              " Update its OS (README, troubleshooting)." % d.get("os"))


def open_session():
    """One connection for everything (the CX II takes one per plug-in). (session, None) or
    (None, exit code)"""
    code, lines = devices()
    if code:
        return None, fail(code, lines)
    try:
        return nspire_link.Session(), None
    except nspire_link.LinkError as e:
        return None, fail(e.code, e.lines)


def cmd_list():
    s, err = open_session()
    if not s:
        return err
    with s:
        code, lines = s.cmd("info")
    if code:
        return fail(code, lines)
    show_info(nspire_link.info_dict(lines))
    return 0


def cmd_ls(path):
    s, err = open_session()
    if not s:
        return err
    with s:
        code, lines = s.cmd("ls " + path)
    if code:
        return fail(code, lines)
    for l in lines:
        if l.startswith("ITEM "):
            kind, size, name = l[5:].split(" ", 2)
            print("  %-4s %8s  %s" % (kind, size if kind == "file" else "", name))
    return 0


def send(tns_path, folder=None, quiet=False):
    """Upload tns_path. Returns an exit code (0 = sent and verified)."""
    if not os.path.isfile(tns_path):
        print("ERROR: no such file: %s" % tns_path)
        return 6
    name = os.path.basename(tns_path)
    if not name.lower().endswith(".tns"):
        print("ERROR: only .tns documents can be sent (got %s). Convert with tools/py2tns.py"
              % name)
        return 1
    s, err = open_session()
    if not s:
        return err
    with s:
        code, lines = s.cmd("info")
        if code:
            return fail(code, lines)
        show_info(nspire_link.info_dict(lines))
        remote = "/" + name
        if folder:
            folder = folder.strip("/")
            code, lines = s.cmd("mkdir /" + folder)
            if code:
                return fail(code, lines)
            remote = "/" + folder + "/" + name
        print("Sending %s -> My Documents%s ..." % (name, remote))
        code, lines = s.cmd("put %s|%s" % (os.path.abspath(tns_path), remote))
    if code:
        return fail(code, lines)
    print("Sent and verified: My Documents%s" % remote)
    return 0


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0 if argv else 1
    if argv[0] == "--list":
        return cmd_list()
    if argv[0] == "--ls":
        return cmd_ls(argv[1] if len(argv) > 1 else "/")
    folder = None
    if "--folder" in argv:
        i = argv.index("--folder")
        if i + 1 >= len(argv):
            print("usage: send_to_calc.py FILE.tns [--folder NAME]")
            return 1
        folder = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    if len(argv) != 1:
        print("usage: send_to_calc.py FILE.tns [--folder NAME]")
        return 1
    return send(argv[0], folder)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
