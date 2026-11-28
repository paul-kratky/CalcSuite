"""Compare two backups of one calculator (or a backup with the calculator as it is now), show
how a program's text changed, and send one item of a backup back.

    python -I tools/backup_compare.py BACKUP_BEFORE BACKUP_AFTER     the list of differences
    python -I tools/backup_compare.py BACKUP_BEFORE BACKUP_AFTER NAME  ... and NAME's text diff

What matches what: the Nspire, a file's path (any case); the 84, a name within its kind (a
program and an AppVar may share a name, a locked program is the same program); the 89, the
folder and the name (any case). An item is "changed" when its file's SHA-256 (the manifest's)
differs. Against a listing that has no hashes (the calculator now, names and sizes only) a
different size is "changed" and the same size "same size": nothing was read to tell more.

Text: TI-Basic programs, strings and equations of the 84 (detokenized), the 89's texts,
strings and programs not yet run, the Nspire's .py files and the Python program inside a .tns
(when the document keeps it readable, as CalcSuite's and TI's Python documents do). Anything
else compares by its hash only.

Everything here is pure but for reading the backup's own files (tools/selftest checks it with
fake backup folders); the window is backup_compare_ui.py. MIT licence (like the rest of the app).
"""

import difflib
import os
import shutil
import sys
import tempfile
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import calc_backup as cb  # noqa: E402
import calc_files as cf  # noqa: E402

ADDED, REMOVED, CHANGED, SAME, SAME_SIZE = "added", "removed", "changed", "same", "same size"
STATUS_TEXT = {ADDED: "added", REMOVED: "removed", CHANGED: "changed", SAME: "unchanged",
               SAME_SIZE: "same size (not read)"}
ORDER = {CHANGED: 0, ADDED: 1, REMOVED: 2, SAME_SIZE: 3, SAME: 4}
TEXT_MAX = 400000  # Bytes of text a diff shows at most (a bigger file is listed, not diffed)


# ---- Which backups there are ----

def list_backups(slug, root=None):
    """[(folder, manifest)] of every readable backup of this model under root (default:
    CalcSuite files\\backups), newest first. Folders that aren't backups are passed over."""
    root = root or cb.backups_root()
    out = []
    try:
        names = os.listdir(root)
    except OSError:
        return out
    for name in names:
        folder = os.path.join(root, name)
        if not os.path.isfile(os.path.join(folder, cb.MANIFEST)):
            continue
        try:
            man = cb.load(folder)
        except (ValueError, KeyError, TypeError):
            continue
        if man.get("calculator", {}).get("slug") == slug:
            out.append((folder, man))
    out.sort(key=lambda fm: fm[1].get("made", ""), reverse=True)
    return out


def backup_title(folder, man):
    """'2026-11-28 14:03:11 - 42 items' for a list of backups"""
    if man.get("snapshot"):
        return man["snapshot"]
    return "%s - %d item(s), %s" % (man.get("made", "?").replace("T", " "), len(man["items"]),
                                   cf.human_size(man.get("total_bytes", 0)))


# ---- Matching and comparing ----

def item_key(slug, i):
    """What makes two items the same one on the calculator (calc_backup's rule)"""
    if slug == "nspire":
        return ("path", i["path"].lower())
    return cb._key(slug, i.get("folder"), i["name"], i.get("type"))


def compare(slug, before, after):
    """Two manifests (or listings) -> [row], changes first then by name. A row is a dict:
    status (ADDED ...), label, kind, before (its item or None), after (its item or None)."""
    a = {}
    for i in before["items"]:
        a.setdefault(item_key(slug, i), i)
    b = {}
    for i in after["items"]:
        b.setdefault(item_key(slug, i), i)
    rows = []
    for k in list(a) + [k for k in b if k not in a]:
        ia, ib = a.get(k), b.get(k)
        if ia is None:
            status = ADDED
        elif ib is None:
            status = REMOVED
        elif ia.get("sha256") and ib.get("sha256"):
            status = SAME if ia["sha256"] == ib["sha256"] else CHANGED
        else:
            status = SAME_SIZE if ia.get("size") == ib.get("size") else CHANGED
        it = ib or ia
        rows.append({"status": status, "label": cb.item_label(slug, it),
                     "kind": it.get("kind") or kind_of_path(it.get("path", "")),
                     "before": ia, "after": ib})
    rows.sort(key=lambda r: (ORDER[r["status"]], r["label"].lower()))
    return rows


def counts(rows):
    """{status: how many}"""
    out = {}
    for r in rows:
        out[r["status"]] = out.get(r["status"], 0) + 1
    return out


def summary_line(rows):
    c = counts(rows)
    parts = ["%d %s" % (c[s], STATUS_TEXT[s]) for s in (CHANGED, ADDED, REMOVED, SAME_SIZE, SAME) if c.get(s)]
    return ", ".join(parts) if parts else "both are empty"


def kind_of_path(path):
    ext = os.path.splitext(path)[1].lower()
    return {".tns": "Document", ".py": "Python", ".txt": "Text"}.get(ext, ext[1:].upper() + " file" if ext else "File")


# ---- The calculator now ----

def listing_manifest(slug, run, info=None):
    """The calculator's own list as a manifest without hashes or files (names and sizes):
    nothing is read but the list. Raises OSError when the 84's / 89's list can't be read."""
    items = []
    if slug == "nspire":
        files, _folders, _errors = cb.nspire_tree(run)
        for raw, size in files:
            items.append({"path": cb.nspire_text(raw), "size": size})
    else:
        for i in cb.dusb_items(run, slug):
            if not i["ext"]:
                continue  # Apps, the OS: never in a backup either
            items.append({"name": i["text"], "folder": i["folder_text"], "type": i["type"],
                          "kind": i["kind"], "size": i["size"]})
    return {"calculator": {"slug": slug, "model": cb.TITLE[slug]}, "items": items,
            "snapshot": "The calculator now (names and sizes)", "made": "now"}


def snapshot(slug, run, info, say=lambda s: None, root=None):
    """Everything readable on the calculator now, read into a temporary folder like a backup
    (hashes and files, so texts can be compared): (folder, manifest). The caller deletes the
    folder with discard() when done."""
    root = root or tempfile.mkdtemp(prefix="calcsuite_compare_")
    folder = cb.new_backup_folder(slug, root=root)
    man = cb.backup(slug, run, info or {}, folder, say)
    for i in man["items"]:
        i["local"] = os.path.join(folder, *i["file"].split("/"))
    man["snapshot"] = "The calculator now (everything read)"
    man["temporary_root"] = root
    return folder, man


def discard(man):
    """Removes a snapshot's temporary folder (nothing for a real backup)"""
    root = (man or {}).get("temporary_root")
    if root and os.path.basename(root).startswith("calcsuite_compare_"):
        shutil.rmtree(root, ignore_errors=True)


# ---- Text ----

def item_text(slug, i):
    """(text, None) for an item CalcSuite can show as text, else (None, why not)"""
    if i is None:
        return None, "not there"
    local = i.get("local")
    if not local:
        return None, "not read (names and sizes only)"
    try:
        with open(local, "rb") as f:
            blob = f.read()
    except OSError as e:
        return None, "the file can't be read (%s)" % e
    try:
        if slug == "nspire":
            return nspire_text(i.get("path", local), blob)
        if slug == "ti84":
            (vtype, _name, _v, _a, data), = cf.read_ti8x(blob)[:1]
            if vtype not in cf.TEXT_TYPES_84:
                return None, "a %s has no text" % (i.get("kind") or "variable").lower()
            if cf.is_compiled_84(data):
                return None, "a compiled (assembly or C) program has no TI-Basic text"
            return cf.detokenize_84(data), None
        (_folder, _name, vtype, _a, data), = cf.read_ti89(blob)[:1]
        if vtype in (0x12, 0x13):
            text = cf.program_89_text(data)
            if text is None:
                return None, "it has run on the 89, which keeps it compiled"
            return text, None
        text = cf.ti89_text(vtype, data)
        if text is None:
            return None, "a %s has no text" % (i.get("kind") or "variable").lower()
        return text, None
    except (ValueError, IndexError, KeyError) as e:
        return None, "the file can't be read (%s)" % e


def nspire_text(path, blob):
    low = path.lower()
    if low.endswith((".py", ".txt")):
        return _decode(blob), None
    if low.endswith(".tns"):
        import py2tns
        try:
            _version, entries = py2tns.read_entries(blob)
        except py2tns.TnsError as e:
            return None, "the document can't be read (%s)" % e
        for e in entries:
            if not e["name"].endswith(".py"):
                continue
            try:
                raw = zlib.decompress(e["body"], -15) if e["method"] == 8 else \
                    e["body"] if e["method"] == 0 else None
            except zlib.error:
                raw = None
            if raw is not None:
                return _decode(raw), None
        return None, "this document keeps no readable Python program (TI encrypts its other pages)"
    return None, "a %s file has no text CalcSuite can show" % (os.path.splitext(low)[1] or "plain")


def _decode(raw):
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def texts_for(slug, row):
    """(before text, after text, why not) for a row; why is None when both sides have text
    (a side that isn't there is empty text)"""
    a = b = ""
    why = None
    if row["before"] is not None:
        a, w = item_text(slug, row["before"])
        why = why or w
    if row["after"] is not None:
        b, w = item_text(slug, row["after"])
        why = why or w
    if why:
        return None, None, why
    if len(a) > TEXT_MAX or len(b) > TEXT_MAX:
        return None, None, "too long to show as a diff"
    return a, b, None


def unified(a, b, name_a="before", name_b="after", context=3):
    """A unified diff as lines (no line ends)"""
    return list(difflib.unified_diff(a.split("\n"), b.split("\n"), name_a, name_b, lineterm="",
                                     n=context))


def side_by_side(a, b):
    """[(left line or None, right line or None, tag)] with tag one of "same", "changed",
    "removed" (only on the left), "added" (only on the right)"""
    la, lb = a.split("\n"), b.split("\n")
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, la, lb, autojunk=False).get_opcodes():
        if op == "equal":
            out += [(la[i], lb[j1 + k], "same") for k, i in enumerate(range(i1, i2))]
        elif op == "delete":
            out += [(la[i], None, "removed") for i in range(i1, i2)]
        elif op == "insert":
            out += [(None, lb[j], "added") for j in range(j1, j2)]
        else:
            n = max(i2 - i1, j2 - j1)
            for k in range(n):
                left = la[i1 + k] if i1 + k < i2 else None
                right = lb[j1 + k] if j1 + k < j2 else None
                out.append((left, right, "changed" if left is not None and right is not None else
                            "removed" if right is None else "added"))
    return out


# ---- One item back to the calculator ----

def restore_one(slug, run, man, item, ask_replace, say=lambda s: None):
    """Sends one item of a backup to the calculator. ask_replace(label) is asked (and must say
    True) when that name is on the calculator now. Returns (sent, why): sent True/False, why a
    text when it wasn't."""
    if item not in man["items"]:
        return False, "that item isn't in this backup"
    label = cb.item_label(slug, item)
    there = cb.on_calculator(slug, run, {"items": [item]})
    if there and there[0] and not ask_replace(label):
        return False, "not replaced: %s stays as it is on the calculator" % label
    sent, failed = cb.restore(slug, run, man, cb.with_safe_paths([item]), say)
    if failed:
        return False, "; ".join("%s: %s" % f for f in failed)
    return bool(sent), None if sent else "nothing was sent"


# ---- The command line ----

def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    try:
        a, b = cb.load(argv[0]), cb.load(argv[1])
    except ValueError as e:
        print("ERROR: %s" % e)
        return 1
    slug = a["calculator"]["slug"]
    if b["calculator"]["slug"] != slug:
        print("ERROR: those are backups of two different models")
        return 1
    rows = compare(slug, a, b)
    print(summary_line(rows))
    for r in rows:
        if r["status"] != SAME:
            print("  %-10s %-32s %s" % (STATUS_TEXT[r["status"]], r["label"], r["kind"]))
    if len(argv) > 2:
        row = next((r for r in rows if r["label"].lower() == argv[2].lower()), None)
        if row is None:
            print("ERROR: no %s in either backup" % argv[2])
            return 1
        ta, tb, why = texts_for(slug, row)
        if why:
            print("No text diff: %s" % why)
            return 1
        print("\n".join(unified(ta, tb, "before/" + row["label"], "after/" + row["label"])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
