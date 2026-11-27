"""Screen recordings from mirror frames: a GIF with nothing installed, an MP4 when ffmpeg is
there (on the PATH, or downloaded once by the app: download_ffmpeg()).

    rec = Recorder(scale=2)
    rec.add(ppm_path)            # once per frame, as they arrive
    paths = rec.save("captures/nspire-20261126-1930")   # -> [".gif"] or [".mp4", ".gif"]

Frames are kept as PPM bytes with their arrival time; a frame equal to the one before only
lengthens it, so a still screen costs nothing.
"""

import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile

MAX_SECONDS = 180

# ffmpeg fetched on request: the single ffmpeg.exe inside the imageio-ffmpeg wheel on PyPI
# (BSD-2 package; the ffmpeg build inside is GPL, run as its own program), checked against the
# SHA-256 PyPI publishes. About 39 MB, once.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402

FFMPEG_DIR = paths.cache_dir("ffmpeg")  # CalcSuite files/cache/ffmpeg (the zip), else LOCALAPPDATA
PYPI_JSON = "https://pypi.org/pypi/imageio-ffmpeg/json"
FFMPEG_DOWNLOAD_MB = 39


def find_ffmpeg():
    """ffmpeg on the PATH, else the one downloaded before, else None"""
    found = shutil.which("ffmpeg")
    if found:
        return found
    local = os.path.join(FFMPEG_DIR, "ffmpeg.exe")
    return local if os.path.isfile(local) else None


def download_ffmpeg(progress=None, timeout=30):
    """Downloads ffmpeg.exe into FFMPEG_DIR; returns its path. progress(done_bytes, total_bytes)
    is called as it comes. Raises OSError / ValueError on any failure (nothing half-written stays)."""
    tag = "win_amd64" if sys.maxsize > 2 ** 32 else "win32"
    req = urllib.request.Request(PYPI_JSON, headers={"User-Agent": "CalcSuite"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        meta = json.load(r)
    wheel = next((f for f in meta["urls"] if f["filename"].endswith(tag + ".whl")), None)
    if not wheel:
        raise ValueError("PyPI lists no %s ffmpeg build" % tag)
    os.makedirs(FFMPEG_DIR, exist_ok=True)
    tmp = os.path.join(FFMPEG_DIR, "download.part")
    try:
        sha = hashlib.sha256()
        req = urllib.request.Request(wheel["url"], headers={"User-Agent": "CalcSuite"})
        with urllib.request.urlopen(req, timeout=timeout) as r, open(tmp, "wb") as f:
            total = int(r.headers.get("Content-Length") or wheel.get("size") or 0)
            done = 0
            while True:
                chunk = r.read(1 << 16)
                if not chunk:
                    break
                f.write(chunk)
                sha.update(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
        if sha.hexdigest() != wheel["digests"]["sha256"]:
            raise ValueError("the download doesn't match PyPI's checksum")
        with zipfile.ZipFile(tmp) as z:
            exe = next((n for n in z.namelist() if n.endswith(".exe") and "/binaries/ffmpeg" in n), None)
            if not exe:
                raise ValueError("no ffmpeg.exe in the download")
            out = os.path.join(FFMPEG_DIR, "ffmpeg.exe")
            with z.open(exe) as src, open(out + ".part", "wb") as dst:
                shutil.copyfileobj(src, dst)
            os.replace(out + ".part", out)
        return out
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def read_ppm(path):
    with open(path, "rb") as f:
        data = f.read()
    parts = data.split(None, 4)
    if len(parts) < 5 or parts[0] != b"P6":
        raise ValueError("not a P6 PPM")
    w, h = int(parts[1]), int(parts[2])
    return w, h, parts[4][:w * h * 3]


class Recorder(object):
    def __init__(self, scale=2, transform=None):
        """transform(w, h, rgb) -> (w, h, rgb) changes each frame as it arrives (key_strip's
        Burner adds the key-press strip)"""
        self.scale = scale
        self.transform = transform
        self.frames = []   # (seconds since the start, rgb bytes)
        self.size = None
        self.t0 = None

    def add(self, ppm_path):
        try:
            w, h, rgb = read_ppm(ppm_path)
        except (OSError, ValueError):
            return
        if self.transform is not None:
            try:
                w, h, rgb = self.transform(w, h, rgb)
            except Exception:  # A strip that fails must never stop the recording
                pass
        now = time.time()
        if self.t0 is None:
            self.t0, self.size = now, (w, h)
        if (w, h) != self.size or now - self.t0 > MAX_SECONDS:
            return
        if self.frames and self.frames[-1][1] == rgb:
            return  # Unchanged: the frame before just lasts longer
        self.frames.append((now - self.t0, rgb))

    def seconds(self):
        return 0.0 if self.t0 is None else time.time() - self.t0

    def _delays(self, end):
        """Each frame's time on screen, in seconds"""
        out = []
        for i, (t, _rgb) in enumerate(self.frames):
            nxt = self.frames[i + 1][0] if i + 1 < len(self.frames) else end
            out.append(max(0.02, nxt - t))
        return out

    def save(self, stem, ffmpeg=None):
        """Writes stem.mp4 (when ffmpeg is found) and stem.gif; returns the paths written"""
        if not self.frames:
            return []
        end = max(self.seconds(), self.frames[-1][0] + 0.5)
        delays = self._delays(min(end, MAX_SECONDS))
        os.makedirs(os.path.dirname(os.path.abspath(stem)), exist_ok=True)
        written = []
        ff = ffmpeg or find_ffmpeg()
        if ff:
            try:
                written.append(self._mp4(ff, stem + ".mp4", delays))
            except (OSError, subprocess.SubprocessError):
                pass
        written.append(self._gif(stem + ".gif", delays))
        return written

    # ---- MP4: the frames as PPM files and a list of how long each lasts ----
    def _mp4(self, ffmpeg, out, delays):
        w, h = self.size
        tmp = tempfile.mkdtemp(prefix="calcrec_")
        try:
            lines = []
            for i, (_t, rgb) in enumerate(self.frames):
                name = os.path.join(tmp, "f%05d.ppm" % i)
                with open(name, "wb") as f:
                    f.write(("P6\n%d %d\n255\n" % (w, h)).encode() + rgb)
                lines.append("file '%s'\nduration %.3f\n" % (name.replace("\\", "/"), delays[i]))
            lines.append("file '%s'\n" % name.replace("\\", "/"))  # ffmpeg wants the last one twice
            listing = os.path.join(tmp, "list.txt")
            with open(listing, "w") as f:
                f.write("".join(lines))
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            base = [ffmpeg, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", listing,
                    "-vf", "scale=iw*%d:ih*%d:flags=neighbor,fps=30,format=yuv420p" % (self.scale, self.scale)]
            try:  # H.264 where the build has it; ffmpeg's own MPEG-4 encoder is in every build
                subprocess.run(base + ["-c:v", "libx264", "-crf", "16", "-preset", "veryfast",
                                       "-movflags", "+faststart", out],
                               check=True, timeout=300, creationflags=flags, capture_output=True)
            except subprocess.CalledProcessError:
                subprocess.run(base + ["-c:v", "mpeg4", "-q:v", "2", "-movflags", "+faststart", out],
                               check=True, timeout=300, creationflags=flags, capture_output=True)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        return out

    # ---- GIF: one palette for the whole recording, LZW in plain Python ----
    def _gif(self, out, delays):
        w, h = self.size
        counts = {}
        for _t, rgb in self.frames[:: max(1, len(self.frames) // 12)]:
            for i in range(0, len(rgb), 3 * 7):  # A sample of the pixels is enough
                c = rgb[i:i + 3]
                counts[c] = counts.get(c, 0) + 1
        colours = [c for c, _n in sorted(counts.items(), key=lambda kv: -kv[1])[:255]]
        colours.append(b"\x00\x00\x00")
        while len(colours) < 256:
            colours.append(b"\x00\x00\x00")
        index = {c: i for i, c in reversed(list(enumerate(colours)))}

        def nearest(c):
            r, g, b = c[0], c[1], c[2]
            best, bi = 1 << 30, 0
            for i, p in enumerate(colours):
                d = (p[0] - r) ** 2 + (p[1] - g) ** 2 + (p[2] - b) ** 2
                if d < best:
                    best, bi = d, i
            index[c] = bi
            return bi

        s = self.scale
        with open(out, "wb") as f:
            f.write(b"GIF89a" + struct.pack("<HHBBB", w * s, h * s, 0xF7, 0, 0) + b"".join(colours))
            f.write(b"\x21\xFF\x0BNETSCAPE2.0\x03\x01\x00\x00\x00")  # Loops for ever
            for (_t, rgb), delay in zip(self.frames, delays):
                row_idx = []
                for y in range(h):
                    row = bytearray()
                    base = y * w * 3
                    for x in range(w):
                        c = rgb[base + 3 * x: base + 3 * x + 3]
                        i = index.get(c)
                        if i is None:
                            i = nearest(c)
                        row.extend((i,) * s)
                    row_idx.extend([bytes(row)] * s)
                pixels = b"".join(row_idx)
                cs = min(65535, max(2, int(round(delay * 100))))
                f.write(b"\x21\xF9\x04\x00" + struct.pack("<H", cs) + b"\x00\x00")
                f.write(b"\x2C" + struct.pack("<HHHHB", 0, 0, w * s, h * s, 0))
                f.write(b"\x08" + _lzw(pixels) + b"\x00")
            f.write(b"\x3B")
        return out


def _lzw(pixels):
    """GIF's LZW for 8-bit pixels, as data sub-blocks"""
    clear, end = 256, 257
    out = bytearray()
    acc = bits = 0

    def emit(code, size):
        nonlocal acc, bits
        acc |= code << bits
        bits += size
        while bits >= 8:
            out.append(acc & 0xFF)
            acc >>= 8
            bits -= 8

    table = {}
    size, nxt = 9, 258
    emit(clear, size)
    prefix = -1
    for px in pixels:
        if prefix < 0:
            prefix = px
            continue
        key = (prefix << 8) | px
        code = table.get(key)
        if code is not None:
            prefix = code
            continue
        emit(prefix, size)
        if nxt < 4096:
            table[key] = nxt
            nxt += 1
            if nxt > (1 << size) and size < 12:
                size += 1
        else:
            emit(clear, size)
            table = {}
            size, nxt = 9, 258
        prefix = px
    if prefix >= 0:
        emit(prefix, size)
    emit(end, size)
    if bits:
        out.append(acc & 0xFF)
    blocks = bytearray()
    for i in range(0, len(out), 255):
        chunk = out[i:i + 255]
        blocks.append(len(chunk))
        blocks.extend(chunk)
    return bytes(blocks)
