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
import queue
import subprocess
import sys
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
CLI = os.path.join(HERE, "bin", "nspire-cli.exe")
CLI_84 = os.path.join(HERE, "bin", "ti84-cli.exe")  # The TI-84 Plus CE family: same commands
CLI_89 = os.path.join(HERE, "bin", "ti89-cli.exe")  # The TI-89 Titanium: the same program
CONNECT_TIMEOUT_S = 25
# A command whose helper prints nothing this long is stuck (transfers print PROGRESS; the
# longest quiet command, a long line of typed keys, takes well under a minute)
IDLE_TIMEOUT_S = 120

REPLUG = ("The handheld didn't answer.\n"
          "  Check it's on (Home screen, no dialog open) and close TI-Nspire CX II Connect /\n"
          "  TI software. If it still doesn't answer: unplug, wait 3 seconds, plug back in.")


class LinkError(Exception):
    def __init__(self, code, lines):
        Exception.__init__(self, "link error %d" % code)
        self.code = code
        self.lines = lines


class Session(object):
    """A link helper's `serve` connection. A command whose helper goes quiet for idle_timeout
    seconds (no line at all: a transfer prints PROGRESS) ends with code 4 and the helper is
    stopped (`dead`), so a stuck link never holds its caller forever. argv: the program to run
    instead of `cli serve` (the self-test's fake helper)."""

    def __init__(self, connect_timeout=CONNECT_TIMEOUT_S, cli=None, idle_timeout=IDLE_TIMEOUT_S,
                 argv=None):
        cli = cli or CLI
        if argv is None and not os.path.isfile(cli):
            raise LinkError(1, ["ERR %s is missing: run python -I tools/build_tools.py" % cli])
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.p = subprocess.Popen(argv or [cli, "serve"], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                  bufsize=1,
                                  # The PC's code page, as fopen in the tools reads paths;
                                  # a handheld's UTF-8 names pass through byte for byte
                                  errors="surrogateescape",
                                  cwd=os.path.dirname(cli), creationflags=flags)
        self.lock = threading.Lock()
        self.idle_timeout = idle_timeout
        self.dead = None  # Why the helper was stopped (it stopped answering), or None
        # Lines come through a queue from a reader thread, so a wait can give up even when the
        # helper can't be stopped (stuck in a USB call: its pipe stays open)
        self.lines = queue.Queue()
        threading.Thread(target=self._reader, daemon=True, name="link-reader").start()
        # The handshake: a handheld that already used its connection never answers, so
        # don't wait libnspire's 10 x 60 s
        code, lines = self._read(timeout=connect_timeout)
        if code:
            self.close()
            raise LinkError(code if code > 0 else 4, lines)

    def _reader(self):
        try:
            for line in self.p.stdout:
                self.lines.put(line)
        except (OSError, ValueError):
            pass
        self.lines.put("")  # The tool ended

    def alive(self):
        """The helper runs and answers (not stopped for going quiet)"""
        return self.dead is None and self.p.poll() is None

    def _stop(self, why):
        self.dead = why
        try:
            self.p.kill()
        except OSError:
            pass

    def _read(self, on_progress=None, timeout=None):
        lines = []
        wait = timeout if timeout is not None else self.idle_timeout
        while True:
            try:
                line = self.lines.get(timeout=wait) if wait else self.lines.get()
            except queue.Empty:
                why = "the link helper said nothing for %d s" % wait
                self._stop(why)
                return 4, lines + ["ERR no answer from the handheld (%s; it was stopped)" % why]
            if not line:  # The tool ended (killed by the timer, or the cable was pulled)
                self.lines.put("")  # Every later read sees the end too
                return 4, lines + ["ERR no answer from the handheld"]
            line = line.rstrip()
            if line.startswith("END "):
                try:
                    return int(line[4:]), lines
                except ValueError:
                    return 4, lines + ["ERR the link helper sent " + line[:60]]
            if line.startswith("PROGRESS "):  # "PROGRESS <bytes> <total>" during a transfer
                if on_progress is not None:
                    try:
                        done, total = (int(x) for x in line.split()[1:3])
                        on_progress(done, total)
                    except ValueError:
                        pass
                continue
            if line:
                lines.append(line)

    def cmd(self, line, on_progress=None):
        """Send one command; returns (exit code, the lines it printed). on_progress(bytes,
        total) is called for a transfer's progress lines."""
        with self.lock:
            if self.dead:
                return 4, ["ERR the link has closed (%s)" % self.dead]
            try:
                self.p.stdin.write(line + "\n")
                self.p.stdin.flush()
            except (OSError, ValueError):
                return 4, ["ERR the link has closed"]
            return self._read(on_progress)

    def close(self, timeout=5):
        try:
            if self.p.poll() is None:
                self.p.stdin.write("quit\n")
                self.p.stdin.flush()
                self.p.wait(timeout=timeout)
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
        if l.startswith("INFO name="):  # A name can have spaces: "TI-Nspire CX II CAS"
            d["name"] = l[10:].strip()
        elif l.startswith("INFO "):
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
        # ti84-cli lists from the USB descriptors without opening anything; nspire-cli opens
        # each device, which can take a calculator from a window that is reconnecting
        cli = CLI_84 if os.path.isfile(CLI_84) else CLI
        p = subprocess.run([cli, "devices"], capture_output=True, text=True, timeout=15,
                           cwd=os.path.dirname(cli), creationflags=flags)
    except (OSError, subprocess.TimeoutExpired):
        return set()
    return set(int(m, 16) for m in re.findall(r"pid=([0-9a-f]{4})", p.stdout))
