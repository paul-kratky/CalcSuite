"""Back up everything a calculator lets the link read into a folder on the PC, and send it back.

    python -I tools/calc_backup.py backup --calc nspire|84|89 [--to FOLDER]
    python -I tools/calc_backup.py show BACKUP_FOLDER
    python -I tools/calc_backup.py restore --calc nspire|84|89 BACKUP_FOLDER [--only NAME ...]
                                          [--replace]

A backup is one folder, by default Documents\\CalcSuite\\backups\\<model>-<date>\\:

- TI-Nspire CX II: every file in every folder the link shows (My Documents and its folders),
  in the same folder tree.
- TI-84 Plus CE: every variable, program and AppVar as its own TI file (.8xp, .8xv, ...), and
  all of them together in one TI Connect CE bundle (<folder name>.b84). Apps, the OS and
  certificates can't be read over the link: the manifest lists them as skipped.
- TI-89 Titanium: every variable as its own TI file (.89p, .89e, ...) in a folder per
  calculator folder (main\\...), and all of them in one group file (<folder name>.89g). Flash
  apps and the OS are skipped the same way.
- manifest.json: the calculator, the date, every file with its name on the calculator, type,
  size, archived or not, and SHA-256; what was skipped and why; what failed and why.

The .b84 bundle is a ZIP with the TI files, a METADATA file and a _CHECKSUM file (the sum of
the CRC-32s of the files before it, in hex), as TI Connect CE writes it (format as read and
written by TI-Toolkit's tivars, bundle.py). The .89g is TI's group file (libtifiles:
ti9x_file_write_regular): a header, a table with a folder entry before its variables, then the
data. A .8xg can't hold more than 64 KB, so the 84's group is the .b84.

Restoring never wipes the calculator: it sends the chosen files back one by one (Nspire: into
the same folders, made when missing), and a name already on the calculator is only replaced
when the caller says so (the Files window asks; the command line skips them unless --replace).

Commands go through a `run(cmds)` function: cmds is [(line, progress or None)], the answer is
[(exit code, lines)] in the same order. The Files window runs them on the mirror's link thread;
the command line on its own nspire_link.Session.
"""

import datetime
import hashlib
import json
import locale
import os
import re
import shutil
import struct
import sys
import tempfile
import time
import zipfile


HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import calc_files as cf  # noqa: E402

FORMAT = "CalcSuite backup"
FORMAT_VERSION = 1
MANIFEST = "manifest.json"
ENCODING = locale.getpreferredencoding(False)  # What nspire_link's pipes use
MODEL = {"nspire": "TI-Nspire-CX-II", "ti84": "TI-84-Plus-CE", "ti89": "TI-89-Titanium"}
TITLE = {"nspire": "TI-Nspire CX II", "ti84": "TI-84 Plus CE", "ti89": "TI-89 Titanium"}
BATCH = 8  # Commands queued at once: the mirror's picture runs between batches
WHY_SKIPPED = {
    0x23: "the operating system isn't read over the link (TI's site has it)",
    0x24: "apps can't be read over this link (reinstall them from TI's site or the app's file)",
    0x25: "certificates aren't read over the link", 0x27: "certificates aren't read over the link",
    0x26: "the ID list isn't a variable", 0x29: "the clock isn't a variable",
    0x13: "backups aren't read over the link", 0x1D: "backups aren't read over the link",
    0x18: "the clock isn't a variable", 0x22: "the ID list isn't a variable",
}


def backups_root():
    return os.path.join(os.path.expanduser("~"), "Documents", "CalcSuite", "backups")


def slug_of(calc):
    s = str(calc).lower().replace("-", "").replace(" ", "")
    if s in ("nspire", "tinspire", "cx2", "nspirecx2"):
        return "nspire"
    if s in ("84", "ti84", "84ce", "ti84ce", "ti84plusce"):
        return "ti84"
    if s in ("89", "ti89", "89t", "ti89t", "ti89titanium"):
        return "ti89"
    raise ValueError("--calc is nspire, 84 or 89")


# ---- Names ----

def nspire_text(raw):
    """A handheld's (UTF-8) name as the pipe decoded it -> the real text"""
    try:
        return raw.encode(ENCODING, "surrogateescape").decode("utf-8")
    except (UnicodeError, LookupError):
        return raw


def nspire_raw(text):
    """The reverse: text -> what to write to the pipe so the handheld gets its UTF-8"""
    return text.encode("utf-8").decode(ENCODING, "surrogateescape")


_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {"COM%d" % i for i in range(1, 10)} | \
    {"LPT%d" % i for i in range(1, 10)}


def pc_name(name):
    """A name as a Windows file or folder name: no <>:"/\\|?*, no control characters, no
    trailing dot or space, not a reserved device name"""
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).rstrip(" .") or "_"
    if s.split(".")[0].upper() in _RESERVED:
        s = "_" + s
    return s


def unique_path(folder, file_name, taken):
    """folder/file_name, or folder/stem (2).ext: never a name used already (taken is a set of
    lower-case paths: Windows names ignore case)"""
    stem, ext = os.path.splitext(file_name)
    path, n = os.path.join(folder, file_name), 2
    while path.lower() in taken or os.path.exists(path):
        path = os.path.join(folder, "%s (%d)%s" % (stem, n, ext))
        n += 1
    taken.add(path.lower())
    return path


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def last_err(lines):
    errs = [l[4:] for l in lines if l.startswith("ERR ")]
    return errs[-1] if errs else (lines[-1] if lines else "no answer")


# ---- Running commands in batches, with progress ----

class Progress(object):
    """Bytes done of a known total, told to say() at most every 0.3 s"""

    def __init__(self, say, what, total):
        self.say, self.what, self.total, self.base, self.t = say, what, max(total, 1), 0, 0.0

    def item(self, size):
        """A progress callback for the next item (size bytes)"""
        base = self.base
        self.base += size

        def cb(n, _total):
            self.show(base + min(n, size))
        return cb

    def show(self, n, force=False):
        if force or time.time() - self.t >= 0.3:
            self.t = time.time()
            self.say("%s: %d%% (%s of %s)" % (self.what, min(100, 100 * n // self.total),
                                             cf.human_size(n), cf.human_size(self.total)))


def run_batched(run, cmds, on_batch=None):
    out = []
    for i in range(0, len(cmds), BATCH):
        out += run(cmds[i:i + BATCH])
        if on_batch:
            on_batch(len(out))
    return out


# ---- What's on the calculator ----

def nspire_tree(run):
    """(files [(raw path, size)], folders [raw path], errors [(path, why)]) for My Documents"""
    files, folders, errors, level = [], [], [], ["/"]
    while level:
        res = run_batched(run, [("ls " + d, None) for d in level])
        nxt = []
        for d, (code, lines) in zip(level, res):
            if code:
                errors.append((d, last_err(lines)))
                continue
            for it in cf.parse_nspire_ls(lines):
                path = d.rstrip("/") + "/" + it["name"]
                if it["dir"]:
                    folders.append(path)
                    nxt.append(path)
                else:
                    files.append((path, it["size"]))
        level = nxt
    return files, folders, errors


def dusb_items(run, slug):
    """The 84's / 89's listing, without the 89's folder entries. Raises OSError."""
    code, lines = run([("ls", None)])[0]
    if code:
        raise OSError("couldn't read the calculator's list: %s" % last_err(lines))
    items = [i for i in cf.parse_dusb_ls(lines) if not (slug == "ti89" and i["type"] == 0x1F)]
    types = cf.TYPES_89 if slug == "ti89" else cf.TYPES_84
    for i in items:
        i["text"] = cf.name_text(i["name"])
        i["folder_text"] = cf.name_text(i["folder"]) if i["folder"] else ""
        i["kind"], i["ext"] = types.get(i["type"], ("Type %02X" % i["type"], None))
    return items


# ---- Backup ----

def new_backup_folder(slug, root=None, when=None):
    root = root or backups_root()
    stamp = (when or datetime.datetime.now()).strftime("%Y-%m-%d_%H%M%S")
    path = os.path.join(root, "%s-%s" % (MODEL[slug], stamp))
    n = 2
    while os.path.exists(path):
        path = os.path.join(root, "%s-%s (%d)" % (MODEL[slug], stamp, n))
        n += 1
    os.makedirs(path)
    return path


def backup(slug, run, info, folder, say=lambda s: None):
    """Reads everything readable into `folder` (made by new_backup_folder) and writes the
    manifest. Returns the manifest. Raises OSError when the calculator's list can't be read."""
    made = datetime.datetime.now()
    tmp = tempfile.mkdtemp(prefix="calcsuite_backup_")
    man = {"format": FORMAT, "format_version": FORMAT_VERSION,
           "made": made.isoformat(timespec="seconds"), "made_by": "CalcSuite",
           "calculator": {"slug": slug, "model": TITLE[slug], "name": info.get("name", "").replace("_", " "),
                          "os": info.get("os", "")},
           "items": [], "folders": [], "skipped": [], "failed": []}
    taken = set()
    try:
        if slug == "nspire":
            _backup_nspire(run, folder, tmp, man, taken, say)
        else:
            _backup_dusb(slug, run, folder, tmp, man, taken, say)
    finally:
        for name in os.listdir(tmp):
            try:
                os.remove(os.path.join(tmp, name))
            except OSError:
                pass
        try:
            os.rmdir(tmp)
        except OSError:
            pass
    man["total_bytes"] = sum(i["size"] for i in man["items"])
    with open(os.path.join(folder, MANIFEST), "w", encoding="utf-8") as f:
        json.dump(man, f, indent=1, ensure_ascii=False)
    return man


def _backup_nspire(run, folder, tmp, man, taken, say):
    say("Reading the folders...")
    files, folders, errors = nspire_tree(run)
    for path, why in errors:
        man["failed"].append({"path": nspire_text(path), "why": "folder not read: " + why})
    man["folders"] = [nspire_text(p) for p in folders]
    for p in man["folders"]:  # Empty folders come back too
        os.makedirs(os.path.join(folder, *[pc_name(c) for c in p.strip("/").split("/")]), exist_ok=True)
    prog = Progress(say, "Backing up", sum(s for _p, s in files))
    cmds, parts = [], []
    for k, (path, size) in enumerate(files):
        part = os.path.join(tmp, "f%d.part" % k)
        parts.append(part)
        cmds.append(("get %s|%s" % (path, part), prog.item(size)))
    res = run_batched(run, cmds)
    for (path, size), part, (code, lines) in zip(files, parts, res):
        text = nspire_text(path)
        if code:
            man["failed"].append({"path": text, "why": last_err(lines)})
            continue
        comps = [pc_name(c) for c in text.strip("/").split("/")]
        local = unique_path(os.path.join(folder, *comps[:-1]), comps[-1], taken)
        shutil.move(part, local)  # The temp folder may be on another drive
        man["items"].append({"path": text, "file": os.path.relpath(local, folder).replace("\\", "/"),
                             "size": os.path.getsize(local), "sha256": sha256(local)})
    prog.show(prog.total, True)


def _backup_dusb(slug, run, folder, tmp, man, taken, say):
    say("Reading the list...")
    items = dusb_items(run, slug)
    readable = [i for i in items if i["ext"]]
    for i in items:
        if not i["ext"]:
            man["skipped"].append({"name": i["text"], "kind": i["kind"], "size": i["size"],
                                   "why": WHY_SKIPPED.get(i["type"], "this kind can't be read over the link")})
    prog = Progress(say, "Backing up", sum(i["size"] for i in readable))
    cmds, raws = [], []
    for k, i in enumerate(readable):
        raw = os.path.join(tmp, "v%d.bin" % k)
        raws.append(raw)
        cmds.append(("get %02x %s %s %d %s" % (i["type"], cf.to_hex(i["folder"]), cf.to_hex(i["name"]),
                                                i["size"], raw), prog.item(i["size"])))
    res = run_batched(run, cmds)
    group = []  # (type, folder bytes, name bytes, archived, data, version) for the .b84 / .89g
    for i, raw, (code, lines) in zip(readable, raws, res):
        label = (i["folder_text"] + "\\" if slug == "ti89" else "") + i["text"]
        if code:
            man["failed"].append({"name": label, "kind": i["kind"], "why": last_err(lines)})
            continue
        arch, version = i["arch"], 0
        for l in lines:
            if l.startswith("OK got"):
                for kv in l.split()[2:]:
                    k, _, v = kv.partition("=")
                    if k == "arch":
                        arch = v == "1"
                    elif k == "version" and v.isdigit():
                        version = int(v)
        try:
            with open(raw, "rb") as f:
                data = f.read()
            os.remove(raw)
            if slug == "ti89":
                blob = cf.ti89_bytes(i["type"], i["folder"] or b"main", i["name"], arch, data,
                                     comment="CalcSuite backup")
                sub = os.path.join(folder, pc_name(i["folder_text"] or "main"))
                os.makedirs(sub, exist_ok=True)
                cf.read_ti89(blob)  # Reads back: the file is well formed
            else:
                name = cf.tokenize_name_84(i["text"], i["type"])
                blob = cf.ti8x_bytes([(i["type"], name, version, arch, data)], comment="CalcSuite backup")
                sub = folder
                cf.read_ti8x(blob)
            local = unique_path(sub, cf.safe_file_name(i["text"]) + "." + i["ext"], taken)
            with open(local, "wb") as f:
                f.write(blob)
        except (OSError, ValueError) as e:
            man["failed"].append({"name": label, "kind": i["kind"], "why": str(e)})
            continue
        group.append((i, data, arch, version, local))
        man["items"].append({
            "name": i["text"], "name_hex": i["name"].hex(), "folder": i["folder_text"],
            "folder_hex": i["folder"].hex(), "type": i["type"], "kind": i["kind"], "size": len(data),
            "archived": arch, "locked": i["locked"], "version": version,
            "file": os.path.relpath(local, folder).replace("\\", "/"), "sha256": sha256(local)})
    prog.show(prog.total, True)
    if not group:
        return
    base = os.path.basename(folder)
    try:
        if slug == "ti84":
            path = os.path.join(folder, base + ".b84")
            with open(path, "wb") as f:
                f.write(b84_bytes([(os.path.basename(g[4]), open(g[4], "rb").read()) for g in group]))
            man["bundle"] = {"file": os.path.basename(path), "format": "TI Connect CE bundle (.b84)",
                             "sha256": sha256(path)}
        else:
            path = os.path.join(folder, base + ".89g")
            with open(path, "wb") as f:
                f.write(ti89_group_bytes([(g[0]["folder"] or b"main", g[0]["name"], g[0]["type"], g[2], g[1])
                                          for g in group]))
            man["group"] = {"file": os.path.basename(path), "format": "TI-89 group file (.89g)",
                            "sha256": sha256(path)}
    except (OSError, ValueError) as e:
        man["failed"].append({"name": base + (".b84" if slug == "ti84" else ".89g"), "why": str(e)})


# ---- Group files ----

def b84_bytes(files, comment="Made by CalcSuite"):
    """A TI Connect CE bundle: files [(name in the bundle, TI file bytes)] -> .b84 bytes"""
    import io
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, allowZip64=False) as z:
        for name, blob in files:
            z.writestr(name, blob)
        meta = ("bundle_identifier:TI Bundle\nbundle_format_version:1\nbundle_target_device:84CE\n"
                "bundle_target_type:CUSTOM\nbundle_comments:%s\n" % comment)
        z.writestr("METADATA", meta)
        crc = sum(info.CRC for info in z.infolist()) & 0xFFFFFFFF
        z.writestr("_CHECKSUM", ("%x\r\n" % crc).encode("ascii"))
    return buf.getvalue()


def read_b84(blob):
    """A .b84 -> [(name, TI file bytes)]; checks the checksum. Raises ValueError."""
    import io
    try:
        z = zipfile.ZipFile(io.BytesIO(blob))
    except zipfile.BadZipFile:
        raise ValueError("not a TI bundle (.b84)")
    names = z.namelist()
    if "METADATA" not in names or "_CHECKSUM" not in names:
        raise ValueError("not a TI bundle: no METADATA or _CHECKSUM")
    crc = sum(i.CRC for i in z.infolist() if i.filename != "_CHECKSUM") & 0xFFFFFFFF
    if int(z.read("_CHECKSUM").decode("ascii").strip(), 16) != crc:
        raise ValueError("the bundle's checksum is wrong")
    return [(n, z.read(n)) for n in names if n not in ("METADATA", "_CHECKSUM")]


def ti89_group_bytes(entries, comment="CalcSuite backup"):
    """A TI-89 group file: entries [(folder bytes, name bytes, type, archived, data)], folders
    kept together in the order they first come (libtifiles: ti9x_file_write_regular)"""
    pad8 = lambda b: (b + b"\x00" * 8)[:8]
    folders = []
    for e in entries:
        if e[0] not in folders:
            folders.append(e[0])
    order = [[e for e in entries if e[0] == f] for f in folders]
    n = len(entries) + len(folders)
    head = b"**TI89**" + b"\x01\x00" + pad8(b"main") + comment.encode("ascii")[:40].ljust(40, b"\x00")
    head += struct.pack("<H", n)
    offset = 0x52 + 16 * (n - 1)
    table, data = b"", b""
    for f, vars_ in zip(folders, order):
        table += struct.pack("<I", offset) + pad8(f) + bytes((0x1F, 0)) + struct.pack("<H", len(vars_))
        for folder, name, vtype, archived, d in vars_:
            table += struct.pack("<I", offset) + pad8(name) + bytes((vtype, 3 if archived else 0)) + b"\x00\x00"
            offset += len(d) + 6
            data += b"\x00\x00\x00\x00" + d + struct.pack("<H", sum(d) & 0xFFFF)
    return head + table + struct.pack("<I", offset) + struct.pack("<H", 0x5AA5) + data


# ---- Reading a backup, restoring ----

def load(folder):
    """The manifest of a backup folder, with each item's "local" path. Raises ValueError."""
    path = os.path.join(folder, MANIFEST)
    try:
        with open(path, "r", encoding="utf-8") as f:
            man = json.load(f)
    except (OSError, ValueError):
        raise ValueError("%s isn't a CalcSuite backup (no readable %s)" % (folder, MANIFEST))
    if man.get("format") != FORMAT or man.get("format_version", 0) > FORMAT_VERSION:
        raise ValueError("%s is a backup this version of CalcSuite can't read" % folder)
    for i in man["items"]:
        i["local"] = os.path.join(folder, *i["file"].split("/"))
    return man


def item_label(slug, i):
    if slug == "nspire":
        return i["path"].lstrip("/")
    return (i["folder"] + "\\" if slug == "ti89" and i.get("folder") else "") + i["name"]


def _key(slug, folder, name, vtype):
    """What makes a name the same one on the calculator: the 89, its folder and name (any
    case); the 84, its name within its kind (a program and an AppVar may share a name)"""
    if slug == "ti89":
        return ((folder or "main").lower(), name.lower())
    return (name, 0x05 if vtype in (0x05, 0x06, 0x16) else vtype)


def on_calculator(slug, run, man):
    """[True or False] for each of the backup's items: is its name on the calculator now?"""
    if slug == "nspire":
        files, folders, _errors = nspire_tree(run)
        have = {nspire_text(p).lower() for p, _s in files}
        return [i["path"].lower() in have for i in man["items"]]
    have = {_key(slug, i["folder_text"], i["text"], i["type"]) for i in dusb_items(run, slug)}
    return [_key(slug, i.get("folder"), i["name"], i["type"]) in have for i in man["items"]]


def restore(slug, run, man, items, say=lambda s: None):
    """Sends `items` (from man["items"]) to the calculator. Whatever has a name on the
    calculator is replaced: the caller asks first. Returns (sent labels, [(label, why)])."""
    sent, failed = [], []
    for i in items:
        if not os.path.isfile(i["local"]):
            failed.append((item_label(slug, i), "the file is missing from the backup"))
        elif i.get("sha256") and sha256(i["local"]) != i["sha256"]:
            failed.append((item_label(slug, i), "the file changed since the backup (SHA-256)"))
    bad = {l for l, _w in failed}
    items = [i for i in items if item_label(slug, i) not in bad]
    prog = Progress(say, "Restoring", sum(os.path.getsize(i["local"]) for i in items))
    cmds = []
    if slug == "nspire":
        need = set()
        for i in items:
            parts = i["path"].strip("/").split("/")[:-1]
            for k in range(1, len(parts) + 1):
                need.add("/" + "/".join(parts[:k]))
        for d in sorted(need, key=lambda p: (p.count("/"), p)):  # Parents first; no error if there
            cmds.append(("mkdir " + nspire_raw(d), None))
        res = run_batched(run, cmds)
        for d, (code, lines) in zip(sorted(need, key=lambda p: (p.count("/"), p)), res):
            if code:
                failed.append((d, "folder not made: " + last_err(lines)))
        cmds = [("put %s|%s" % (os.path.abspath(i["local"]), nspire_raw(i["path"])),
                 prog.item(os.path.getsize(i["local"]))) for i in items]
    else:
        cmds = [("send " + os.path.abspath(i["local"]), prog.item(os.path.getsize(i["local"])))
                for i in items]
    for i, (code, lines) in zip(items, run_batched(run, cmds)):
        (failed.append((item_label(slug, i), last_err(lines))) if code else sent.append(item_label(slug, i)))
    prog.show(prog.total, True)
    return sent, failed


def local_path_ok(path):
    """The link tools open local files with the PC's code page: a path it can't spell needs a
    temporary copy"""
    try:
        path.encode(ENCODING)
        return True
    except UnicodeEncodeError:
        return False


def with_safe_paths(items):
    """Items whose files the link tools can open: copies in the temp folder for the others"""

    out = []
    for i in items:
        if local_path_ok(i["local"]):
            out.append(i)
            continue
        d = tempfile.mkdtemp(prefix="calcsuite_restore_")
        j = dict(i)
        j["local"] = os.path.join(d, "f" + os.path.splitext(i["local"])[1])
        shutil.copyfile(i["local"], j["local"])
        out.append(j)
    return out


def summary(man):
    """A few lines about a backup, for a window or the command line"""
    c = man["calculator"]
    lines = ["%s%s, OS %s, backed up %s" % (c["model"], " (%s)" % c["name"] if c.get("name") and
                                            c["name"] != c["model"] else "", c.get("os", "?"),
                                            man["made"].replace("T", " "))]
    lines.append("%d item(s), %s" % (len(man["items"]), cf.human_size(man.get("total_bytes", 0))))
    if man["skipped"]:
        kinds = {}
        for s in man["skipped"]:
            kinds[s["kind"]] = kinds.get(s["kind"], 0) + 1
        lines.append("Not in it (the link can't read them): " +
                     ", ".join("%d %s" % (n, k.lower() + ("s" if n > 1 else "")) for k, n in sorted(kinds.items())))
    if man["failed"]:
        lines.append("Failed: " + "; ".join("%s (%s)" % (f.get("name") or f.get("path"), f["why"])
                                            for f in man["failed"][:5]))
    return lines


# ---- The command line ----

def _session_run(session):
    def run(cmds):
        return [session.cmd(line, progress) for line, progress in cmds]
    return run


def main(argv):
    import argparse
    import nspire_link
    ap = argparse.ArgumentParser(description="Back up a calculator, or restore from a backup")
    sub = ap.add_subparsers(dest="what", required=True)
    b = sub.add_parser("backup")
    b.add_argument("--calc", required=True)
    b.add_argument("--to", help="the folder to make the backup in (default: %s)" % backups_root())
    s = sub.add_parser("show")
    s.add_argument("folder")
    r = sub.add_parser("restore")
    r.add_argument("--calc", required=True)
    r.add_argument("folder")
    r.add_argument("--only", nargs="+", help="only these names (as `show` lists them)")
    r.add_argument("--replace", action="store_true", help="replace names already on the calculator")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    if a.what == "show":
        man = load(a.folder)
        print("\n".join(summary(man)))
        for i in man["items"]:
            print("  %-32s %-14s %9s  %s" % (item_label(man["calculator"]["slug"], i), i.get("kind", "file"),
                                            cf.human_size(i["size"]), i["file"]))
        return 0
    slug = slug_of(a.calc)
    cli = {"nspire": nspire_link.CLI, "ti84": nspire_link.CLI_84, "ti89": nspire_link.CLI_89}[slug]
    say = lambda t: print("  " + t, flush=True)
    try:
        session = nspire_link.Session(cli=cli)
    except nspire_link.LinkError as e:
        print("ERROR: no answer from the %s (%s)" % (TITLE[slug], last_err(e.lines)))
        return e.code
    with session:
        run = _session_run(session)
        if a.what == "backup":
            code, lines = session.cmd("info")
            folder = new_backup_folder(slug, a.to)
            t0 = time.time()
            man = backup(slug, run, nspire_link.info_dict(lines), folder, say)
            print("\n".join(summary(man)))
            print("Backed up to %s in %.1f s" % (folder, time.time() - t0))
            return 0 if not man["failed"] else 5
        man = load(a.folder)
        if man["calculator"]["slug"] != slug:
            print("ERROR: that backup is of a %s" % man["calculator"]["model"])
            return 1
        items = man["items"]
        if a.only:
            want = {n.lower() for n in a.only}
            items = [i for i in items if item_label(slug, i).lower() in want]
            if not items:
                print("ERROR: none of %s is in the backup" % ", ".join(a.only))
                return 1
        there = on_calculator(slug, run, man)
        clash = [i for i, t in zip(man["items"], there) if t and any(i is j for j in items)]
        if clash and not a.replace:
            print("Already on the calculator, skipped (add --replace): %s" %
                  ", ".join(item_label(slug, i) for i in clash))
            items = [i for i in items if not any(i is c for c in clash)]
        print("Sending %d item(s)..." % len(items))
        sent, failed = restore(slug, run, man, with_safe_paths(items), say)
        print("Sent: %s" % (", ".join(sent) or "nothing"))
        for label, why in failed:
            print("FAILED %s: %s" % (label, why))
        return 0 if not failed else 4


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
