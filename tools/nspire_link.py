"""One USB connection to the handheld, kept open (nspire-cli `serve`).

Each new connection costs a handshake, so a tool that needs several steps (info, then an
upload; a screenshot every tenth of a second; key presses) does them all on one connection.
Session starts nspire-cli once and sends it commands.

    from nspire_link import Session
    with Session() as s:          # raises LinkError if no handheld answers
        code, lines = s.cmd("info")
        code, lines = s.cmd("shot C:/tmp/screen.ppm")

If connecting fails: the handheld on, Home screen, no dialog; TI's own software closed. As a
last resort unplug it, wait 3 seconds, plug it back in.
"""

import os
import subprocess
import sys
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
CLI = os.path.join(HERE, "bin", "nspire-cli.exe")
CLI_84 = os.path.join(HERE, "bin", "ti84-cli.exe")  # The TI-84 Plus CE family: same commands
CONNECT_TIMEOUT_S = 25

REPLUG = ("The handheld didn't answer.\n"
          "  Check it's on (Home screen, no dialog open) and close TI-Nspire CX II Connect /\n"
          "  TI software. If it still doesn't answer: unplug, wait 3 seconds, plug back in.")


class LinkError(Exception):
    def __init__(self, code, lines):
        Exception.__init__(self, "link error %d" % code)
        self.code = code
        self.lines = lines


class Session(object):
    def __init__(self, connect_timeout=CONNECT_TIMEOUT_S, cli=None):
        cli = cli or CLI
        if not os.path.isfile(cli):
            raise LinkError(1, ["ERR %s is missing: run python -I tools/build_tools.py" % cli])
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.p = subprocess.Popen([cli, "serve"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, text=True, bufsize=1,
                                  cwd=os.path.dirname(cli), creationflags=flags)
        self.lock = threading.Lock()
        # The handshake: a handheld that already used its connection never answers, so
        # don't wait libnspire's 10 x 60 s
        timer = threading.Timer(connect_timeout, self.p.kill)
        timer.start()
        try:
            code, lines = self._read()
        finally:
            timer.cancel()
        if code:
            self.close()
            raise LinkError(code if code > 0 else 4, lines)

    def _read(self):
        lines = []
        while True:
            line = self.p.stdout.readline()
            if not line:  # The tool ended (killed by the timer, or the cable was pulled)
                return 4, lines + ["ERR no answer from the handheld"]
            line = line.rstrip()
            if line.startswith("END "):
                return int(line[4:]), lines
            if line:
                lines.append(line)

    def cmd(self, line):
        """Send one command; returns (exit code, the lines it printed)"""
        with self.lock:
            try:
                self.p.stdin.write(line + "\n")
                self.p.stdin.flush()
            except (OSError, ValueError):
                return 4, ["ERR the link has closed"]
            return self._read()

    def close(self):
        try:
            if self.p.poll() is None:
                self.p.stdin.write("quit\n")
                self.p.stdin.flush()
                self.p.wait(timeout=5)
        except Exception:
            pass
        if self.p.poll() is None:
            self.p.kill()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def info_dict(lines):
    import re
    d = {}
    for l in lines:
        if l.startswith("INFO "):
            for k, v in re.findall(r"(\w+)=(\S+(?: \(\S+\))?)", l[5:]):
                d[k] = v
    return d


def ppm_to_png(ppm_path, png_path, scale=1):
    """A binary PPM (P6, 8-bit) written as a PNG, optionally enlarged by a whole number"""
    import struct
    import zlib
    with open(ppm_path, "rb") as f:
        data = f.read()
    parts = data.split(None, 4)
    if len(parts) < 5 or parts[0] != b"P6":
        raise ValueError("not a P6 PPM: %s" % ppm_path)
    w, h = int(parts[1]), int(parts[2])
    px = parts[4][:w * h * 3]
    rows = []
    for y in range(h):
        row = px[y * w * 3:(y + 1) * w * 3]
        if scale > 1:
            row = b"".join(row[i:i + 3] * scale for i in range(0, len(row), 3))
        rows.extend([b"\x00" + row] * scale)

    def chunk(tag, body):
        return (struct.pack(">I", len(body)) + tag + body +
                struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF))

    png = (b"\x89PNG\r\n\x1a\n" +
           chunk(b"IHDR", struct.pack(">IIBBBBB", w * scale, h * scale, 8, 2, 0, 0, 0)) +
           chunk(b"IDAT", zlib.compress(b"".join(rows), 6)) + chunk(b"IEND", b""))
    with open(png_path, "wb") as f:
        f.write(png)
    return w * scale, h * scale


if __name__ == "__main__":
    try:
        with Session() as s:
            code, lines = s.cmd("info")
            print("\n".join(lines))
            sys.exit(code)
    except LinkError as e:
        print("\n".join(e.lines))
        print(REPLUG)
        sys.exit(e.code)


def usb_calculators():
    """The USB product ids of the TI calculators plugged in now, e.g. {0xe022, 0xe008}.
    Only lists USB devices: it opens no link."""
    import re
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        p = subprocess.run([CLI, "devices"], capture_output=True, text=True, timeout=15,
                           cwd=os.path.dirname(CLI), creationflags=flags)
    except (OSError, subprocess.TimeoutExpired):
        return set()
    return set(int(m, 16) for m in re.findall(r"pid=([0-9a-f]{4})", p.stdout))
