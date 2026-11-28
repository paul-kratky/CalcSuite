"""Make a PC copy of my calculator: dump the calculator's own ROM over USB, then open it in an
emulator with the calculator's programs and variables.

    python -I tools/pc_copy.py dump 84|89 [--no-backup-check]   back up, dump the ROM, clean up
    python -I tools/pc_copy.py get-emulator 84|89              download CEmu (84) / TiEmu (89)
    python -I tools/pc_copy.py open 84|89 [--rom FILE] [--backup FOLDER] [--no-files]
    python -I tools/pc_copy.py make 84|89                      all three
    python -I tools/pc_copy.py list                            the ROMs dumped so far

What it does, step by step (docs/PC_COPY.md for people, docs/dev/PC_COPY_API.md for the UI):

TI-84 Plus CE (OS 5.4 or older: OS 5.5+ needs arTIfiCE to run assembly, which this doesn't do)
  1. A full backup (calc_backup.py), so nothing on the calculator can be lost.
  2. The OS's own GarbageCollect (typed: key 0xFCFC, Enter, 2:Yes), so the archive's free
     space is in one piece: otherwise the OS stops the dumper half way to ask
     "Garbage Collect?" (seen on OS 5.4).
  3. CEmu's own ROM dumper (tools/rom_dumpers/cemu_dump.8xp, GPL-3.0, from CEmu's source) is
     sent as the program ZZDUMP. The CE's OS doesn't run programs from the link, so its keys
     are typed: Quit, Clear, Clear, prgm, Z Z D U M P, Enter (as libticalcs does for its own
     CE dumper).
  4. The dumper copies the boot code and the OS (from 0 up to the OS's size) and TI's
     certificate sector into AppVars ROMData0 (the OS size), ROMData1 (the certificate) and
     ROMDataA, B, ... (65512 bytes each), archived. It ends on its own; the link stays silent
     for CE_DUMP_WAIT seconds meanwhile.
  5. The AppVars are read back over the link and put together the way CEmu's ROM wizard does
     (gui/qt/romselection.cpp): a 4 MB image, 0xFF everywhere else (the archive comes out
     empty, so the user's archived files aren't in the ROM). The result is checked: 4 MB, the
     boot code's certificate field says "TI-84 Plus CE".
  6. ZZDUMP and the ROMData AppVars are deleted (they are ours); the RAM listing before and
     after is compared, so a crash that cleared the RAM is reported.
  7. Saved as Documents\\CalcSuite\\backups\\roms\\ti84ce-<date>.rom with <name>.json beside it.

TI-89 Titanium (any AMS 3.x)
  1. A full backup.
  2. TILP's USB ROM dumper (tools/rom_dumpers/romdump_89t.89z, GPL-2.0-or-later, libticalcs'
     rom89t.h) is sent as main\\romdump, the calculator is sent to its home screen and the
     program is run from the link (ti89-cli exec), as libticalcs' calc_89t.cc does.
  3. ti89-cli romdump reads the 4 MB ROM in 4 KB blocks with libticalcs' romdump protocol;
     the certificate (0x10000-0x11FFF) is read protected and stays 0xFF, as in TILP.
  4. main\\romdump is deleted; saved as backups\\roms\\ti89t-<date>.rom (TiEmu imports .rom).
     Unlike the CE's, this dump is the whole flash: it holds the archived variables too.

ROMs are TI's copyrighted code: they're for the owner's own use on their own PC. CalcSuite
never uploads, downloads or ships one; nothing here sends a ROM anywhere.

The emulators are downloaded only when asked, into %LOCALAPPDATA%\\CalcSuite\\emulators\\:
CEmu (GPL-3.0) from its GitHub release, checked against a SHA-256 (GitHub's own digest when
the release has one, else the one pinned below); TiEmu (GPL-2.0) from its SourceForge project:
the last Windows build (3.03, 2010) is a setup.exe that CalcSuite verifies and leaves for the
user to run (nothing here runs an installer).
"""

import datetime
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import calc_backup as cb  # noqa: E402
import calc_files as cf  # noqa: E402

DUMPERS = os.path.join(HERE, "rom_dumpers")
CE_DUMPER = os.path.join(DUMPERS, "cemu_dump.8xp")
T89_DUMPER = os.path.join(DUMPERS, "romdump_89t.89z")
CE_DUMPER_SHA256 = "bb86acb9d0624d1828615dfd2227b82c144fd96614741dc876cb04bca2a98c2e"
T89_DUMPER_SHA256 = "bca398ecd10451a469ef22ca060dcaa517fc634017acefcaa32816e77b38421f"

# The CEmu dumper (romselection.cpp): segment size, where the certificate sector is
CE_ROM_SIZE = 0x400000
CE_SEG = 65512
CE_CERT = 0x3B0000
CE_PRGM = b"ZZDUMP"          # The name we give the dumper on the calculator
CE_APPVAR = 0x15
CE_PROT_PRGM = 0x06
T89_ROM_SIZE = 0x400000
T89_FOLDER, T89_PRGM, T89_ASM = b"main", b"romdump", 0x21

# CEmu for Windows: the release and its file we take, and the SHA-256 we pinned when we
# checked it (the v2.0 release's assets have no GitHub digest). Unsigned (no Authenticode).
CEMU_REPO = "CE-Programming/CEmu"
CEMU_PINNED = {"tag": "v2.0", "asset": "CEmu-v2.0_win64_Qt6.exe", "size": 19392512,
               "sha256": "5260f4460c4f0e08d2d8197ecd206d5156bb8f1fa62941eda35ef1034326cfc3"}
# TiEmu: the official project's last Windows build (SourceForge, 2010-12-12). SourceForge
# lists its MD5; we pinned its SHA-256 too.
TIEMU_URL = ("https://downloads.sourceforge.net/project/gtktiemu/tiemu-win32/"
             "TIEmu%203.03%20%28Win32%20binaries%29/tiemu-3.03-win32-nogdb.zip")
TIEMU_ZIP = {"name": "tiemu-3.03-win32-nogdb.zip", "size": 3205979,
             "md5": "114861c784367a710824ac02d86493f5",
             "sha256": "4ad01be796a33c51a932d798721d5c28258df190a81f15b1bd290368ad11cc79"}
UA = "CalcSuite (https://github.com/paul-kratky/CalcSuite)"

TITLE = {"ti84": "TI-84 Plus CE", "ti89": "TI-89 Titanium"}
ROM_PREFIX = {"ti84": "ti84ce", "ti89": "ti89t"}


class PcCopyError(Exception):
    """A step that stopped the PC copy; .stage says which, .detail the tool's last lines"""

    def __init__(self, stage, message, detail=None):
        Exception.__init__(self, message)
        self.stage, self.detail = stage, detail or []


class Cancelled(PcCopyError):
    def __init__(self, stage):
        PcCopyError.__init__(self, stage, "cancelled")


# ---- Folders ----

def roms_folder():
    """CalcSuite files\\backups\\roms (made when missing)"""
    path = os.path.join(cb.backups_root(), "roms")
    os.makedirs(path, exist_ok=True)
    return path


def emulators_folder():
    """CalcSuite files\\cache\\emulators (or %LOCALAPPDATA%\\CalcSuite\\emulators from source)"""
    import paths
    return paths.cache_dir("emulators")


def list_roms(model=None):
    """The ROMs dumped so far, newest first: [{"path", "model", "size", "made", "info"}].
    info is the .json beside the ROM ({} when there is none)."""
    want = cb.slug_of(model) if model else None
    out = []
    folder = roms_folder()
    for name in os.listdir(folder):
        if not name.lower().endswith(".rom"):
            continue
        slug = "ti84" if name.startswith("ti84ce") else "ti89" if name.startswith("ti89t") else None
        if not slug or (want and slug != want):
            continue
        path = os.path.join(folder, name)
        info = {}
        try:
            with open(os.path.splitext(path)[0] + ".json", encoding="utf-8") as f:
                info = json.load(f)
        except (OSError, ValueError):
            pass
        out.append({"path": path, "model": slug, "size": os.path.getsize(path),
                    "made": os.path.getmtime(path), "info": info})
    out.sort(key=lambda r: r["made"], reverse=True)
    return out


def latest_backup(model):
    """The newest backup folder of that model (calc_backup's), or None"""
    slug = cb.slug_of(model)
    root = cb.backups_root()
    best = None
    if not os.path.isdir(root):
        return None
    for name in os.listdir(root):
        path = os.path.join(root, name)
        if not name.startswith(cb.MODEL[slug] + "-") or not os.path.isfile(os.path.join(path, cb.MANIFEST)):
            continue
        t = os.path.getmtime(os.path.join(path, cb.MANIFEST))
        if best is None or t > best[0]:
            best = (t, path)
    return best[1] if best else None


def _rom_path(slug, when=None):
    stamp = (when or datetime.datetime.now()).strftime("%Y-%m-%d")
    folder = roms_folder()
    path = os.path.join(folder, "%s-%s.rom" % (ROM_PREFIX[slug], stamp))
    n = 2
    while os.path.exists(path):
        path = os.path.join(folder, "%s-%s_%d.rom" % (ROM_PREFIX[slug], stamp, n))
        n += 1
    return path


# ---- The ROM images (pure: no calculator needed; the self-test runs these) ----

def ce_segment_name(i):
    """The AppVar the CEmu dumper writes segment i (0-based) of the OS to: ROMDataA, B, ..."""
    return b"ROMData" + bytes((ord("A") + i,))


def ce_expected(os_size):
    """The AppVar names the CEmu dumper makes for an OS of os_size bytes"""
    count = (os_size + CE_SEG - 1) // CE_SEG
    return [b"ROMData0", b"ROMData1"] + [ce_segment_name(i) for i in range(count)]


def appvar_content(data):
    """An AppVar's data as the link gives it (2-byte length first) -> its content"""
    if len(data) < 2:
        raise ValueError("an AppVar of %d bytes" % len(data))
    n = data[0] | data[1] << 8
    if n != len(data) - 2:
        raise ValueError("an AppVar whose length word (%d) isn't its size (%d)" % (n, len(data) - 2))
    return data[2:]


def assemble_ce_rom(appvars):
    """The CEmu dumper's AppVars {name bytes: content bytes (without the length word)} -> the
    4 MB ROM image, as CEmu's parseROMSegments builds it. Raises ValueError when one is missing
    or the wrong size."""
    if b"ROMData0" not in appvars or len(appvars[b"ROMData0"]) < 3:
        raise ValueError("ROMData0 (the OS size) is missing")
    os_size = int.from_bytes(appvars[b"ROMData0"][:3], "little")
    if not 0x20000 < os_size <= CE_CERT:
        raise ValueError("an OS size of %d bytes can't be right" % os_size)
    rom = bytearray(b"\xff" * CE_ROM_SIZE)
    for name in ce_expected(os_size)[1:]:
        data = appvars.get(name)
        if data is None:
            raise ValueError("%s is missing" % name.decode())
        if len(data) != CE_SEG:
            raise ValueError("%s has %d bytes, not %d" % (name.decode(), len(data), CE_SEG))
        at = CE_CERT if name == b"ROMData1" else CE_SEG * (name[7] - ord("A"))
        if at + CE_SEG > CE_ROM_SIZE:
            raise ValueError("%s would end past the 4 MB" % name.decode())
        rom[at:at + CE_SEG] = data
    return bytes(rom), os_size


def _cert_field(buf, at):
    """(field id, contents offset, contents size) of the certificate field at `at` (CEmu's
    core/cert.c: cert_field_get), or None"""
    if at + 2 > len(buf):
        return None
    fid = buf[at] << 8 | buf[at + 1]
    if fid == 0xFFFF:
        return None
    extra = {0xD: 1, 0xE: 2, 0xF: 4}.get(fid & 0xF, 0)
    if extra == 0:
        size, start = fid & 0xF, at + 2
    else:
        if at + 2 + extra > len(buf):
            return None
        size, start = int.from_bytes(buf[at + 2:at + 2 + extra], "big"), at + 2 + extra
    if start + size > len(buf):
        return None
    return fid, start, size


def check_ce_rom(rom):
    """What CEmu reads from a CE ROM before it boots it (core/emu.c): its size and the boot
    code's certificate field 0x800F with the model field 0x8012 (0x13 = 83 Premium CE / 84
    Plus CE). Returns {"ok", "model", "why"}."""
    if len(rom) != CE_ROM_SIZE:
        return {"ok": False, "model": None, "why": "the ROM has %d bytes, not 4 MB" % len(rom)}
    if rom[:16] == b"\xff" * 16:
        return {"ok": False, "model": None, "why": "the boot code is empty"}
    for off in (0x20000, 0x30000):
        f = _cert_field(rom, off)
        if not f or f[0] != 0x800F:
            continue
        inner = _cert_field(rom, f[1])
        if inner and inner[0] & 0xFFF0 == 0x8010 and inner[2] >= 1:
            mid = rom[inner[1]]
            name = {0x13: "TI-84 Plus CE / TI-83 Premium CE", 0x15: "TI-82 Advanced Edition Python"}
            return {"ok": mid in name, "model": name.get(mid, "model 0x%02X" % mid),
                    "why": "" if mid in name else "an unknown model id 0x%02X" % mid}
    return {"ok": False, "model": None, "why": "no OS certificate field at 0x20000 or 0x30000"}


def check_89t_rom(rom):
    """A TI-89 Titanium dump: 4 MB, not blank, and the boot code's ROM base (0x800000 on the
    Titanium) where the 68k reset vector points"""
    if len(rom) != T89_ROM_SIZE:
        return {"ok": False, "why": "the ROM has %d bytes, not 4 MB" % len(rom)}
    if rom[:0x100] == b"\xff" * 0x100 or rom[:0x100] == b"\x00" * 0x100:
        return {"ok": False, "why": "the boot code is empty"}
    pc = struct.unpack_from(">I", rom, 4)[0]  # The reset vector's program counter
    if not 0x800000 <= pc < 0xC00000:
        return {"ok": False, "why": "the reset vector (0x%06X) isn't in the Titanium's ROM" % pc}
    return {"ok": True, "why": ""}


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


# ---- Talking to the calculator ----

class _Steps(object):
    """Reports and timings: report(stage, text, done, total) and the cancel event"""

    def __init__(self, report, cancel):
        self.report = report or (lambda stage, text, done=None, total=None: None)
        self.cancel = cancel
        self.timings = {}
        self.stage = None
        self.t = time.time()

    def go(self, stage, text):
        if self.cancel is not None and self.cancel.is_set():
            raise Cancelled(stage)
        now = time.time()
        if self.stage:
            self.timings[self.stage] = round(self.timings.get(self.stage, 0) + now - self.t, 1)
        self.stage, self.t = stage, now
        self.report(stage, text, None, None)

    def say(self, text, done=None, total=None):
        self.report(self.stage, text, done, total)

    def sleep(self, seconds):
        """time.sleep that Cancel ends at once (raising Cancelled)"""
        if self.cancel is None:
            time.sleep(seconds)
        elif self.cancel.wait(seconds):
            raise Cancelled(self.stage)

    def done(self):
        self.go("done", "Done")


CMD_IDLE_S = 120.0  # A link command that prints nothing (no line, no progress) this long has hung
CMD_POLL_S = 0.2    # How often the watchdog looks (and how soon Cancel ends a command)


class _Watched(object):
    """A link session (nspire_link.Session or a fake) whose commands can't hang the PC copy: one
    that prints nothing for CMD_IDLE_S seconds, or is running when Cancel is pressed, is ended by
    ending the link helper (its process; .abort() / .close() for a fake). The calculator itself
    isn't stopped by that: a dump program running there finishes by itself."""

    def __init__(self, s, steps):
        self.s, self.steps = s, steps
        self.p = getattr(s, "p", None)

    def _kill(self):
        try:
            if self.p is not None:
                self.p.kill()
            else:
                getattr(self.s, "abort", self.s.close)()
        except Exception:
            pass

    def cmd(self, line, progress=None, idle=None):
        idle = CMD_IDLE_S if idle is None else idle
        cancel = self.steps.cancel
        if cancel is not None and cancel.is_set():
            raise Cancelled(self.steps.stage)
        seen = [time.time()]
        why = []
        over = threading.Event()

        def on_progress(d, t):
            seen[0] = time.time()
            if progress is not None:
                progress(d, t)

        def watch():
            while not over.wait(CMD_POLL_S):
                if cancel is not None and cancel.is_set():
                    why.append("cancel")
                elif time.time() - seen[0] > idle:
                    why.append("idle")
                else:
                    continue
                self._kill()
                return
        threading.Thread(target=watch, daemon=True).start()
        try:
            code, lines = self.s.cmd(line, on_progress)
        finally:
            over.set()
        if why and why[0] == "cancel":
            raise Cancelled(self.steps.stage)
        if why:
            raise PcCopyError(self.steps.stage, "the calculator stopped answering (%s: nothing for %d s); "
                              "CalcSuite ended the link" % (line.split()[0], idle), lines)
        return code, lines

    def close(self):
        self.s.close()


def _default_connect(slug):
    import nspire_link

    def connect():
        return nspire_link.Session(cli=nspire_link.CLI_84 if slug == "ti84" else nspire_link.CLI_89)
    return connect


def _open(connect, steps, tries=1, wait=3.0):
    import nspire_link
    last = None
    for k in range(tries):
        if k:
            steps.say("The calculator didn't answer yet: trying again (%d of %d)..." % (k + 1, tries))
            steps.sleep(wait)
        try:
            return _Watched(connect(), steps)
        except nspire_link.LinkError as e:
            last = e
    raise PcCopyError(steps.stage, "the calculator didn't answer: %s" % cb.last_err(last.lines if last else []),
                      last.lines if last else [])


def _cmd(s, line, stage, progress=None, ok=(0,)):
    code, lines = s.cmd(line, progress)
    if code not in ok:
        raise PcCopyError(stage, "%s: %s" % (line.split()[0], cb.last_err(lines)), lines)
    return code, lines


def _listing(s, slug, stage):
    _code, lines = _cmd(s, "ls", stage)
    return cf.parse_dusb_ls(lines)


def _ram_items(items, slug):
    """The names in RAM (not archived), to see afterwards whether the RAM was cleared"""
    return sorted("%s|%s|%02x" % (i["folder"].hex(), i["name"].hex(), i["type"]) for i in items
                  if not i["arch"] and not (slug == "ti89" and i["type"] == 0x1F))


def _version_tuple(s):
    return tuple(int(x) for x in re.findall(r"\d+", s or "")[:3])


def _backup(slug, s, info, steps, folder=None):
    run = lambda cmds: [s.cmd(line, p) for line, p in cmds]
    folder = folder or cb.new_backup_folder(slug)
    man = cb.backup(slug, run, info, folder, lambda t: steps.say(t))
    if man["failed"]:
        raise PcCopyError("backup", "the backup missed %d item(s): %s (nothing was changed on the "
                          "calculator; the partial backup is in %s)" %
                          (len(man["failed"]), ", ".join(f.get("name", f.get("path", "?")) for f in man["failed"]),
                           folder))
    return folder, man


def _write_rom(slug, rom, meta):
    path = _rom_path(slug)
    tmp = path + ".part"
    with open(tmp, "wb") as f:
        f.write(rom)
    os.replace(tmp, path)
    meta = dict(meta, file=os.path.basename(path), size=len(rom), sha256=sha256_bytes(rom),
                note="Your own calculator's ROM, for your own use on this PC. Don't share it: "
                     "it is TI's copyrighted software.")
    with open(os.path.splitext(path)[0] + ".json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=1)
    return path, meta


def dump_rom(model, report=None, cancel=None, connect=None, backup_folder=None):
    """Backs up the calculator, dumps its ROM and cleans up (see the module's docstring).

    model: "84" / "89" (anything calc_backup.slug_of takes). report(stage, text, done, total)
    is called from this thread for each step and for progress (done/total in bytes, or None).
    cancel: a threading.Event, looked at between steps (a dump that has started on the
    calculator is finished first). connect(): a nspire_link.Session-like object (cmd(line,
    progress), close()); by default ti84-cli / ti89-cli serve. The calculator must not be held
    by another link (the mirror's tab has to let go of it first).

    Returns a dict: ok, model, rom (path), size, sha256, os, backup (folder), seconds,
    timings {stage: s}, ram_cleared, missing [names], notes [text], check {...}.
    Raises PcCopyError (its .stage is the step) or Cancelled."""
    slug = cb.slug_of(model)
    if slug not in ("ti84", "ti89"):
        raise ValueError("a PC copy is for the TI-84 Plus CE and the TI-89 Titanium")
    steps = _Steps(report, cancel)
    connect = connect or _default_connect(slug)
    t0 = time.time()
    if slug == "ti84":
        res = _dump_84ce(connect, steps, backup_folder)
    else:
        res = _dump_89t(connect, steps, backup_folder)
    steps.done()
    res["seconds"] = round(time.time() - t0, 1)
    res["timings"] = steps.timings
    return res


def _check_dumper(path, want):
    with open(path, "rb") as f:
        blob = f.read()
    if sha256_bytes(blob) != want:
        raise PcCopyError("check", "%s isn't the dumper CalcSuite was tested with" % os.path.basename(path))
    return blob


def _dump_84ce(connect, steps, backup_folder):
    notes = []
    steps.go("connect", "Connecting to the TI-84 Plus CE...")
    blob = _check_dumper(CE_DUMPER, CE_DUMPER_SHA256)
    (vtype, _n, version, _arch, prog), = cf.read_ti8x(blob)
    s = _open(connect, steps, tries=3)
    try:
        _c, lines = _cmd(s, "info", "connect")
        import nspire_link
        info = nspire_link.info_dict(lines)
        osv = info.get("os", "")
        if "CE" not in info.get("name", "").replace("_", " ") and "83" not in info.get("name", ""):
            raise PcCopyError("check", "this isn't a TI-84 Plus CE (%s)" % info.get("name", "?"))
        if _version_tuple(osv) >= (5, 5):
            raise PcCopyError("check", "OS %s doesn't run assembly programs, so the dumper can't run. On OS "
                              "5.5 or newer, arTIfiCE (with Cesium) brings assembly back; CalcSuite doesn't "
                              "install it for you." % osv)
        ram = int(info.get("ram_free", "0") or 0)
        arc = int(info.get("storage_free", "0") or 0)
        # The dumper wants 65793 bytes of RAM (its EnoughMem check) and archive room for the
        # boot code + OS (about 1 MB at most) and the certificate sector
        if ram < 66500:
            raise PcCopyError("check", "the dumper needs 66 KB of free RAM; the calculator has %s. Archive "
                              "or delete something first." % cf.human_size(ram))
        if arc < 1100000:
            raise PcCopyError("check", "the dump needs about 1.1 MB of free archive; the calculator has %s."
                              % cf.human_size(arc))
        steps.go("check", "Checking the calculator's list...")
        items = _listing(s, "ti84", "check")
        clash = [cf.name_text(i["name"]) for i in items
                 if i["name"] == CE_PRGM or (i["type"] == CE_APPVAR and i["name"].startswith(b"ROMData"))]
        if clash:
            raise PcCopyError("check", "the calculator already has %s: the dumper would replace it. Rename or "
                              "delete it first (CalcSuite never deletes your own files)." % ", ".join(clash))
        ram_before = _ram_items(items, "ti84")
        steps.go("backup", "Backing up the calculator first...")
        folder, man = _backup("ti84", s, info, steps, backup_folder)
        steps.go("tidy", "Tidying the calculator's archive (Garbage Collect)...")
        _garbage_collect(s, steps)
        steps.go("send", "Sending the ROM dumper (ZZDUMP)...")
        tmp = tempfile.mkdtemp(prefix="calcsuite_romdump_")
        try:
            local = os.path.join(tmp, "dumper.bin")
            with open(local, "wb") as f:
                f.write(prog)
            _cmd(s, "put %02x 0 %d %s %s" % (vtype, version, CE_PRGM.hex(), local), "send")
            steps.go("run", "Starting the dumper on the calculator...")
            # Quit, Clear, Clear, the prgm token (kExec 0xDA), Z Z D U M P: then Enter
            name_keys = " ".join("%x" % (0x9A + c - ord("A")) for c in CE_PRGM)
            _cmd(s, "keys 40 09 09 da " + name_keys, "run")
            steps.sleep(0.3)
            shot = os.path.join(tmp, "typed.ppm")
            s.cmd("shot " + shot)
            # The Enter starts the dumper, which keeps the OS (and its link) busy: the key's
            # answer may not come, so its error is no failure (nor a silence: 20 s is plenty)
            steps.say("Pressing Enter: the dump program starts on the calculator...")
            try:
                s.cmd("key 05", idle=20)
            except Cancelled:
                raise
            except PcCopyError:
                pass
        except BaseException:
            shutil.rmtree(tmp, ignore_errors=True)
            raise
    finally:
        s.close()
    try:
        steps.go("wait", "The calculator is dumping its ROM (about a minute)...")
        appvars, os_size, s = _wait_ce_dump(connect, steps)
        try:
            steps.go("assemble", "Putting the ROM together...")
            rom, _ = assemble_ce_rom(appvars)
            check = check_ce_rom(rom)
            if not check["ok"]:
                raise PcCopyError("assemble", "the ROM doesn't look right: %s (the AppVars stay on the "
                                  "calculator)" % check["why"])
            steps.go("save", "Saving the ROM...")
            path, meta = _write_rom("ti84", rom, {
                "model": "TI-84 Plus CE", "calculator": info.get("name", "").replace("_", " "), "os": osv,
                "os_size": os_size, "dumped": datetime.datetime.now().isoformat(timespec="seconds"),
                "dumper": "CEmu's ROM dumper (GPL-3.0), tools/rom_dumpers/cemu_dump.8xp",
                "backup": folder, "check": check})
            steps.go("clean", "Removing the dumper and its AppVars from the calculator...")
            left = _clean_ce(s, appvars)
            s.cmd("keys 09 09")  # Clear "prgmZZDUMP Done" off the home screen
            if left:
                notes.append("Couldn't remove %s from the calculator: delete them by hand (2nd MEM 2 "
                             "Mem Management)." % ", ".join(left))
            items = _listing(s, "ti84", "clean")
            ram_after = _ram_items(items, "ti84")
            missing = sorted(set(ram_before) - set(ram_after))
        finally:
            s.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    ram_cleared = bool(ram_before) and len(missing) == len(ram_before)
    if missing:
        notes.append("%d item(s) in RAM before the dump are gone (%s): restore them from the backup %s."
                     % (len(missing), "the RAM was cleared" if ram_cleared else "some of them", folder))
    return {"ok": True, "model": "ti84", "rom": path, "size": len(rom), "sha256": meta["sha256"], "os": osv,
            "os_size": os_size, "backup": folder, "ram_cleared": ram_cleared,
            "missing": [m.split("|")[1] for m in missing], "notes": notes, "check": check}


CE_DUMP_WAIT = 90.0  # Seconds the link stays silent while the dumper runs (14 pieces of ~2-3 s on OS 5.4)


def _garbage_collect(s, steps, limit=180.0):
    """Runs the CE's GarbageCollect command (key 0xFCFC, then 2:Yes) and waits until the
    calculator answers again. The dumper archives about 0.9 MB in 64 KB AppVars; when the
    archive needs a garbage collection on the way, the OS asks "Garbage Collect?" in the middle
    of the dump and the dumper ends early (seen twice on OS 5.4). A collection first leaves the
    free archive in one piece. It only moves files within the archive; nothing is deleted."""
    _cmd(s, "keys 40 09 09 fcfc 05", "tidy")
    steps.sleep(0.5)
    t0 = time.time()
    steps.say("Garbage collecting on the calculator...")
    s.cmd("key 90", idle=limit)  # 2:Yes. The answer comes after the collection: its error is no failure
    while time.time() - t0 < limit:
        code, _lines = s.cmd("info", idle=60)
        if code == 0:
            _cmd(s, "keys 09 09", "tidy")
            steps.say("The archive is tidy")
            return
        steps.say("Garbage collecting... (%d s)" % (time.time() - t0))
        steps.sleep(2)
    raise PcCopyError("tidy", "the calculator didn't answer after its garbage collection")


def _wait_ce_dump(connect, steps, first_wait=None, limit=600.0):
    """Waits for the dumper to finish (every AppVar the OS size calls for is there and
    archived), then reads them. Returns (appvars, os size, session).

    The link must stay silent while the dumper runs: on a TI-84 Plus CE (OS 5.4) a link
    request during the dump ended the dumper early (it printed Done after 5 of 12 OS pieces,
    the last one not archived). So nothing is sent for first_wait seconds, then the listing is
    read; a dump that is incomplete and doesn't move on in 20 s has stopped."""
    import nspire_link
    t0 = time.time()
    first_wait = CE_DUMP_WAIT if first_wait is None else first_wait
    while time.time() - t0 < first_wait:
        left = first_wait - (time.time() - t0)
        steps.say("The calculator is dumping its ROM; the link stays quiet (%d s left)..." % left,
                  int(time.time() - t0), int(first_wait))
        # Cancel: nothing to stop on the calculator (the dump goes on there); we stop waiting
        steps.sleep(min(1.0, max(left, 0)))
    last_seen = None
    while True:
        elapsed = time.time() - t0
        if elapsed > limit:
            raise PcCopyError("wait", "the dumper didn't finish in %d minutes (look at the calculator: a "
                              "\"Garbage Collect?\" question wants an answer; its AppVars ROMData* "
                              "stay on it)" % (limit // 60))
        steps.say("Looking whether the dump has finished (%d s)..." % elapsed)
        try:
            s = _Watched(connect(), steps)
        except nspire_link.LinkError:
            steps.say("The calculator is busy dumping... (%d s)" % elapsed)
            steps.sleep(4)
            continue
        try:
            items = _listing(s, "ti84", "wait")
            have = {i["name"]: i for i in items if i["type"] == CE_APPVAR and i["name"].startswith(b"ROMData")}
            if b"ROMData0" in have:
                run = os.path.join(tempfile.gettempdir(), "calcsuite_romdata0.bin")
                _cmd(s, "get 15 - %s %d %s" % (b"ROMData0".hex(), have[b"ROMData0"]["size"], run), "wait")
                with open(run, "rb") as f:
                    os_size = int.from_bytes(appvar_content(f.read())[:3], "little")
                os.remove(run)
                want = ce_expected(os_size)
                done = [n for n in want if n in have and (n == b"ROMData0" or have[n]["size"] >= CE_SEG + 2)]
                steps.say("Dumped %d of %d pieces" % (len(done), len(want)), len(done), len(want))
                if len(done) == len(want) and all(have[n]["arch"] for n in want):
                    return _fetch_ce(s, steps, have, want), os_size, s
                key = tuple(sorted((n, have[n]["arch"]) for n in have))
                if key == last_seen:
                    raise PcCopyError("wait", "the dump stopped at %d of %d pieces; its AppVars ROMData* stay on "
                                      "the calculator (look at its screen: a question or an error?). "
                                      "Delete them and ZZDUMP, then try again." % (len(done), len(want)))
                last_seen = key
            elif last_seen == ():
                raise PcCopyError("wait", "the dumper made nothing (did it start? look at the calculator's "
                                  "screen); ZZDUMP stays on the calculator")
            else:
                last_seen = ()
        except BaseException:
            s.close()
            raise
        s.close()
        for k in range(20):
            steps.say("The dump isn't finished yet: looking again in %d s..." % (20 - k))
            steps.sleep(1)


def _fetch_ce(s, steps, have, want):
    steps.go("fetch", "Reading the ROM back from the calculator...")
    total = sum(have[n]["size"] for n in want)
    tmp = tempfile.mkdtemp(prefix="calcsuite_romdata_")
    out, base = {}, 0
    try:
        for n in want:
            local = os.path.join(tmp, n.decode() + ".bin")
            size = have[n]["size"]

            def progress(d, _t, b=base, size=size):
                done = b + min(d, size)
                steps.say("Reading the ROM: %d%% (%s of %s)" % (100 * done // total, cf.human_size(done),
                                                              cf.human_size(total)), done, total)
            _cmd(s, "get 15 - %s %d %s" % (n.hex(), size, local), "fetch", progress)
            with open(local, "rb") as f:
                out[n] = appvar_content(f.read())
            base += size
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return out


def _clean_ce(s, appvars):
    left = []
    for name, vtype in [(CE_PRGM, CE_PROT_PRGM)] + [(n, CE_APPVAR) for n in sorted(appvars)]:
        code, _lines = s.cmd("rm %02x %s" % (vtype, name.hex()))
        if code:
            left.append(name.decode())
    items = cf.parse_dusb_ls(s.cmd("ls")[1])
    still = [cf.name_text(i["name"]) for i in items
             if i["name"] == CE_PRGM or (i["type"] == CE_APPVAR and i["name"] in appvars)]
    return sorted(set(left) | set(still)) if still else []


def _dump_89t(connect, steps, backup_folder):
    notes = []
    steps.go("connect", "Connecting to the TI-89 Titanium...")
    _check_dumper(T89_DUMPER, T89_DUMPER_SHA256)
    s = _open(connect, steps, tries=3)
    tmp = tempfile.mkdtemp(prefix="calcsuite_romdump_")
    try:
        try:
            _c, lines = _cmd(s, "info", "connect")
            import nspire_link
            info = nspire_link.info_dict(lines)
            steps.go("check", "Checking the calculator's list...")
            items = _listing(s, "ti89", "check")
            if any(i["folder"] == T89_FOLDER and i["name"] == T89_PRGM for i in items):
                raise PcCopyError("check", "the calculator already has main\\romdump: the dumper would replace "
                                  "it. Rename or delete it first (CalcSuite never deletes your own files).")
            ram_before = _ram_items(items, "ti89")
            steps.go("backup", "Backing up the calculator first...")
            folder, man = _backup("ti89", s, info, steps, backup_folder)
            steps.go("send", "Sending the ROM dumper (main\\romdump)...")
            _cmd(s, "send " + T89_DUMPER, "send")
            steps.go("run", "Starting the dumper on the calculator...")
            _cmd(s, "home", "run")
            steps.sleep(1.0)
            _cmd(s, "exec asm %s %s" % (T89_FOLDER.hex(), T89_PRGM.hex()), "run")
            steps.sleep(1.5)
            steps.go("dump", "Reading the ROM over USB (4 MB)...")
            raw = os.path.join(tmp, "rom.bin")
            _cmd(s, "romdump " + raw, "dump",
                 lambda d, t: steps.report("dump", "Reading the ROM: %d%%" % (100 * d // max(t, 1)), d, t))
        finally:
            s.close()  # The link has spoken the dumper's protocol: a new connection follows
        with open(raw, "rb") as f:
            rom = f.read()
        check = check_89t_rom(rom)
        if not check["ok"]:
            raise PcCopyError("dump", "the ROM doesn't look right: %s" % check["why"])
        steps.go("save", "Saving the ROM...")
        path, meta = _write_rom("ti89", rom, {
            "model": "TI-89 Titanium", "calculator": info.get("name", "").replace("_", " "),
            "os": info.get("os", ""), "dumped": datetime.datetime.now().isoformat(timespec="seconds"),
            "dumper": "TILP's ROM dumper 1.02 USB (GPL-2.0-or-later), tools/rom_dumpers/romdump_89t.89z",
            "backup": folder, "check": check,
            "certificate": "0x10000-0x11FFF is read protected and saved as 0xFF (as TILP does)"})
        steps.go("clean", "Removing the dumper from the calculator...")
        steps.sleep(2.0)
        s = _open(connect, steps, tries=5)
        try:
            code, _l = s.cmd("rm %02x %s %s" % (T89_ASM, T89_PRGM.hex(), T89_FOLDER.hex()))
            items = _listing(s, "ti89", "clean")
            if any(i["folder"] == T89_FOLDER and i["name"] == T89_PRGM for i in items):
                notes.append("Couldn't remove main\\romdump from the calculator: delete it by hand "
                             "(2nd VAR-LINK).")
            missing = sorted(set(ram_before) - set(_ram_items(items, "ti89")))
        finally:
            s.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    ram_cleared = bool(ram_before) and len(missing) == len(ram_before)
    if missing:
        notes.append("%d item(s) in RAM before the dump are gone: restore them from the backup %s."
                     % (len(missing), folder))
    return {"ok": True, "model": "ti89", "rom": path, "size": len(rom), "sha256": meta["sha256"],
            "os": info.get("os", ""), "backup": folder, "ram_cleared": ram_cleared,
            "missing": [m.split("|")[1] for m in missing], "notes": notes, "check": check}


# ---- Emulators ----

def _get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def _download(url, dest, size_hint, report, stage):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    h = hashlib.sha256()
    m = hashlib.md5()
    tmp = dest + ".part"
    done = 0
    with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length") or size_hint or 0)
        t = 0.0
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            f.write(chunk)
            h.update(chunk)
            m.update(chunk)
            done += len(chunk)
            if report and time.time() - t > 0.25:
                t = time.time()
                report(stage, "Downloading: %s of %s" % (cf.human_size(done), cf.human_size(total)), done, total)
    return tmp, h.hexdigest(), m.hexdigest(), done


def cemu_path():
    """CEmu.exe that get_emulator("84") put in place, or None"""
    path = os.path.join(emulators_folder(), "CEmu", "CEmu.exe")
    return path if os.path.isfile(path) else None


def tiemu_path():
    """tiemu.exe where TiEmu's own installer puts it (or under emulators\\TiEmu), or None"""
    cands = [os.path.join(emulators_folder(), "TiEmu", "bin", "tiemu.exe"),
             os.path.join(emulators_folder(), "TiEmu", "tiemu.exe")]
    for env in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
        base = os.environ.get(env)
        if base:
            cands += [os.path.join(base, "TiEmu", "bin", "tiemu.exe"), os.path.join(base, "TiEmu", "tiemu.exe")]
    for c in cands:
        if os.path.isfile(c):
            return c
    return None


def get_emulator(model, report=None):
    """Downloads the emulator for the model, checked; returns {"path", "version", "sha256",
    "verified_by", "ready"}. ready is False for TiEmu: its setup.exe (path) is for the user to
    run. Raises PcCopyError("download", ...)."""
    slug = cb.slug_of(model)
    return _get_cemu(report) if slug == "ti84" else _get_tiemu(report)


def _get_cemu(report):
    pick = dict(CEMU_PINNED, url="https://github.com/%s/releases/download/%s/%s" %
                (CEMU_REPO, CEMU_PINNED["tag"], CEMU_PINNED["asset"]), digest=None)
    try:  # A newer release is taken only when GitHub gives its SHA-256
        rel = _get_json("https://api.github.com/repos/%s/releases/latest" % CEMU_REPO)
        for a in rel.get("assets", []):
            if re.match(r"CEmu-.*_win64_Qt6\.exe$", a["name"]) and (a.get("digest") or "").startswith("sha256:"):
                pick = {"tag": rel["tag_name"], "asset": a["name"], "size": a["size"],
                        "sha256": a["digest"][7:], "url": a["browser_download_url"], "digest": "github"}
                break
    except (OSError, ValueError, KeyError):
        pass
    folder = os.path.join(emulators_folder(), "CEmu")
    os.makedirs(folder, exist_ok=True)
    dest = os.path.join(folder, "CEmu.exe")
    stamp = os.path.join(folder, "calcsuite.json")
    try:
        with open(stamp, encoding="utf-8") as f:
            have = json.load(f)
        if have.get("sha256") == pick["sha256"] and os.path.isfile(dest) and cb.sha256(dest) == pick["sha256"]:
            return dict(have, path=dest, ready=True)
    except (OSError, ValueError):
        pass
    if report:
        report("download", "Downloading CEmu %s from GitHub..." % pick["tag"], 0, pick["size"])
    try:
        tmp, sha, _md5, n = _download(pick["url"], dest, pick["size"], report, "download")
    except OSError as e:
        raise PcCopyError("download", "CEmu couldn't be downloaded: %s" % e)
    if sha != pick["sha256"]:
        os.remove(tmp)
        raise PcCopyError("download", "the CEmu download doesn't match its SHA-256 (got %s): not used" % sha)
    os.replace(tmp, dest)
    info = {"name": "CEmu", "version": pick["tag"], "file": pick["asset"], "size": n, "sha256": sha,
            "verified_by": "GitHub's SHA-256 digest" if pick["digest"] else "the SHA-256 pinned in CalcSuite",
            "source": pick["url"], "licence": "GPL-3.0", "signed": False,
            "downloaded": datetime.datetime.now().isoformat(timespec="seconds")}
    with open(stamp, "w", encoding="utf-8") as f:
        json.dump(info, f, indent=1)
    return dict(info, path=dest, ready=True)


def _get_tiemu(report):
    found = tiemu_path()
    if found:
        return {"name": "TiEmu", "path": found, "ready": True, "version": "installed", "sha256": None,
                "verified_by": None}
    folder = os.path.join(emulators_folder(), "TiEmu")
    os.makedirs(folder, exist_ok=True)
    dest = os.path.join(folder, TIEMU_ZIP["name"])
    if report:
        report("download", "Downloading TiEmu 3.03 from SourceForge...", 0, TIEMU_ZIP["size"])
    try:
        tmp, sha, md5, _n = _download(TIEMU_URL, dest, TIEMU_ZIP["size"], report, "download")
    except OSError as e:
        raise PcCopyError("download", "TiEmu couldn't be downloaded: %s" % e)
    if sha != TIEMU_ZIP["sha256"] or md5 != TIEMU_ZIP["md5"]:
        os.remove(tmp)
        raise PcCopyError("download", "the TiEmu download doesn't match its checksums: not used")
    os.replace(tmp, dest)
    with zipfile.ZipFile(dest) as z:
        z.extract("setup.exe", folder)
    setup = os.path.join(folder, "setup.exe")
    return {"name": "TiEmu", "path": setup, "ready": False, "version": "3.03 (2010)", "sha256": sha,
            "verified_by": "SourceForge's MD5 and the SHA-256 pinned in CalcSuite",
            "todo": "Run %s yourself to install TiEmu (it's TiEmu's own installer, from 2010, "
                    "unsigned), then open the PC copy again." % setup}


def backup_files(folder):
    """The TI files of a backup that an emulator can take: [path]"""
    man = cb.load(folder)
    return [os.path.join(folder, i["file"].replace("/", os.sep)) for i in man["items"]
            if os.path.isfile(os.path.join(folder, i["file"].replace("/", os.sep)))]


def emulator_command(model, rom, files=(), emulator=None, fresh=True):
    """The command line that opens the ROM (and sends the files) in the emulator. CEmu:
    --rom ROM, --reload-rom when fresh (boot the ROM, not CEmu's saved state of the last
    session), --send FILE for each file (CEmu v2.0 options, gui/qt/main.cpp)."""
    slug = cb.slug_of(model)
    if slug == "ti84":
        exe = emulator or cemu_path()
        if not exe:
            raise PcCopyError("open", "CEmu isn't downloaded yet (get_emulator(\"84\"))")
        cmd = [exe, "--rom", rom] + (["--reload-rom"] if fresh else [])
        for f in files:
            cmd += ["--send", f]
        return cmd
    exe = emulator or tiemu_path()
    if not exe:
        raise PcCopyError("open", "TiEmu isn't installed (get_emulator(\"89\") downloads its installer)")
    cmd = [exe, "-rom=" + rom]
    return cmd


def open_in_emulator(model, rom=None, backup=None, files=None, emulator=None, fresh=True):
    """Starts the emulator with the ROM (default: the newest dumped one) and the backup's
    programs and variables (default: the backup made with that ROM, else the newest backup of
    that model; files=[] sends none). fresh=False (CEmu): carry on from CEmu's saved state of
    the last session instead of booting the ROM afresh (pass files=[] then).
    Returns the subprocess.Popen. The emulator is its own program: closing CalcSuite leaves
    it open."""
    slug = cb.slug_of(model)
    if rom is None:
        roms = list_roms(slug)
        if not roms:
            raise PcCopyError("open", "no ROM of the %s yet: dump one first" % TITLE[slug])
        rom = roms[0]["path"]
        backup = backup or roms[0]["info"].get("backup")
    if files is None:
        folder = backup or latest_backup(slug)
        files = backup_files(folder) if folder and os.path.isdir(folder) else []
        if slug == "ti89":
            files = []  # TiEmu takes one -send= file at a time: sent from its own window
    cmd = emulator_command(slug, rom, files, emulator, fresh)
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    return subprocess.Popen(cmd, cwd=os.path.dirname(cmd[0]), creationflags=flags, close_fds=True)


def make_pc_copy(model, report=None, cancel=None, connect=None, open_emulator=True):
    """dump_rom, then get_emulator and open_in_emulator. Returns dump_rom's dict plus
    "emulator" (get_emulator's dict) and "process" (the Popen, or None)."""
    res = dump_rom(model, report, cancel, connect)
    res["emulator"], res["process"] = None, None
    if open_emulator:
        emu = get_emulator(model, report)
        res["emulator"] = emu
        if emu.get("ready"):
            res["process"] = open_in_emulator(model, res["rom"], res["backup"])
        else:
            res["notes"].append(emu.get("todo", ""))
    return res


# ---- The command line ----

def _print_report(stage, text, done=None, total=None):
    if text:
        print("  [%s] %s" % (stage, text), flush=True)


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(description="Make a PC copy of your calculator (ROM dump + emulator)")
    sub = ap.add_subparsers(dest="what", required=True)
    for name in ("dump", "get-emulator", "make"):
        p = sub.add_parser(name)
        p.add_argument("calc")
    o = sub.add_parser("open")
    o.add_argument("calc")
    o.add_argument("--rom")
    o.add_argument("--backup")
    o.add_argument("--no-files", action="store_true")
    sub.add_parser("list")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    try:
        if a.what == "list":
            for r in list_roms():
                print("%s  %s  %s  OS %s" % (r["path"], cf.human_size(r["size"]), r["info"].get("sha256", "")[:16],
                                             r["info"].get("os", "?")))
            return 0
        if a.what == "get-emulator":
            print(json.dumps(get_emulator(a.calc, _print_report), indent=1))
            return 0
        if a.what == "open":
            p = open_in_emulator(a.calc, a.rom, a.backup, [] if a.no_files else None)
            print("Started %s (pid %d)" % (os.path.basename(p.args[0]), p.pid))
            return 0
        fn = dump_rom if a.what == "dump" else make_pc_copy
        res = fn(a.calc, _print_report)
        res.pop("process", None)
        print(json.dumps(res, indent=1, default=str))
        return 0
    except PcCopyError as e:
        print("ERROR (%s): %s" % (e.stage, e))
        for l in e.detail[-5:]:
            print("    " + l)
        return 4


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
