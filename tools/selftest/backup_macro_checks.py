"""Backup compare, single restore and key macros (2026-11-28): with fake calculators and fake
backup folders, no calculator needed.

- backup_compare: backups made by calc_backup.backup from a scripted link (all three models),
  then changed; compare finds what was added, removed and changed (by SHA-256), the quick
  listing by size; the texts of 84 / 89 programs and Nspire .py / .tns; unified and side by
  side diffs; one item restored (asked before replacing, nothing sent on No); a snapshot's
  temporary folder goes; the list of backups
- macros: key names <-> codes, the recorder (with and without pauses), the mirror's key tap,
  the JSON round trip, files, import merging, the replay plan, the player with a faked sender
  (waits only after the calculator took the keys, Stop, a failed send), the warning rule, the
  built-in examples; the Macros panel and the Compare window built with faked links

    python -I tools/selftest/backup_macro_checks.py
"""

import json
import os
import shutil
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)

import calc_backup as cb  # noqa: E402
import calc_files as cf  # noqa: E402
import backup_compare as bc  # noqa: E402
import macros as mc  # noqa: E402


def check(ok, what):
    print("%-4s %s" % ("PASS" if ok else "FAIL", what))
    return 0 if ok else 1


# ---- A scripted calculator behind run(cmds) ----

class FakeDusb(object):
    """The 84's / 89's link: ls, get, send. vars: {(folder bytes, name bytes): (type, data)}"""

    def __init__(self, slug, vars_):
        self.slug, self.vars = slug, dict(vars_)
        self.lines = []

    def run(self, cmds):
        out = []
        for line, _progress in cmds:
            self.lines.append(line)
            w = line.split(" ")
            if w[0] == "ls":
                rows = []
                for (folder, name), (vtype, data) in sorted(self.vars.items()):
                    rows.append("ITEM type=%02x size=%d arch=0 locked=0 folder=%s name=%s" % (
                        vtype, len(data), cf.to_hex(folder), cf.to_hex(name)))
                out.append((0, rows + ["OK ls"]))
            elif w[0] == "get":
                folder = b"" if w[2] == "-" else bytes.fromhex(w[2])
                name = bytes.fromhex(w[3])
                vtype, data = self.vars[(folder, name)]
                with open(" ".join(w[5:]), "wb") as f:
                    f.write(data)
                out.append((0, ["OK got arch=0 version=0"]))
            elif w[0] == "send":
                with open(line[5:], "rb") as f:
                    blob = f.read()
                if self.slug == "ti84":
                    for vtype, name, _v, _a, data in cf.read_ti8x(blob):
                        self.vars[(b"", name)] = (vtype, data)
                else:
                    for folder, name, vtype, _a, data in cf.read_ti89(blob):
                        self.vars[(folder, name)] = (vtype, data)
                out.append((0, ["OK sent"]))
            else:
                out.append((0, ["OK"]))
        return out


class FakeNspire(object):
    """The Nspire's link: ls DIR, get PATH|LOCAL, mkdir, put LOCAL|PATH. files: {path: bytes}"""

    def __init__(self, files):
        self.files = dict(files)
        self.lines = []

    def run(self, cmds):
        out = []
        for line, _progress in cmds:
            self.lines.append(line)
            verb, _, rest = line.partition(" ")
            if verb == "ls":
                d = rest.rstrip("/") + "/"
                kids = {}
                for p, data in self.files.items():
                    if p.startswith(d):
                        part = p[len(d):].split("/")
                        kids[part[0]] = ("dir", 0) if len(part) > 1 else ("file", len(data))
                out.append((0, ["ITEM %s %d %s" % (k, s, n) for n, (k, s) in sorted(kids.items())] + ["OK"]))
            elif verb == "get":
                path, local = rest.split("|")
                with open(local, "wb") as f:
                    f.write(self.files[path])
                out.append((0, ["OK got"]))
            elif verb == "put":
                local, path = rest.split("|")
                with open(local, "rb") as f:
                    self.files[path] = f.read()
                out.append((0, ["OK put"]))
            else:
                out.append((0, ["OK"]))
        return out


def prog84(text, name):
    (vtype, n, _v, _a, data), = cf.read_ti8x(cf.program_8xp(text, name))
    return (b"", n), (vtype, data)


def prog89(text, name, folder=b"main"):
    _n, vtype, data = cf.program_89_data(text, name)
    return (folder, name.encode("ascii")), (vtype, data)


def make_backup(slug, fake, root, when):
    folder = cb.new_backup_folder(slug, root=root, when=when)
    man = cb.backup(slug, fake.run, {"name": "ZZFAKE", "os": "1.0"}, folder)
    man["made"] = when.isoformat(timespec="seconds")  # backup() stamps the PC's clock: the test's date
    with open(os.path.join(folder, cb.MANIFEST), "w", encoding="utf-8") as fh:
        json.dump(man, fh)
    return folder


def by_label(rows):
    return {r["label"]: r for r in rows}


def compare_checks():
    import datetime
    import tns_writer
    f = 0
    root = tempfile.mkdtemp(prefix="calcsuite_cmp_test_")
    try:
        t1 = datetime.datetime(2026, 11, 20, 10, 0, 0)
        t2 = datetime.datetime(2026, 11, 28, 18, 30, 0)
        # ---- TI-84 Plus CE ----
        k1, v1 = prog84(":Disp 1\n:Disp 2\n:Disp 3", "ZZA")
        k2, v2 = prog84(":Disp \"SAME\"", "ZZB")
        k3, v3 = prog84(":Disp \"GONE\"", "ZZC")
        fake = FakeDusb("ti84", {k1: v1, k2: v2, k3: v3})
        a = make_backup("ti84", fake, root, t1)
        k1b, v1b = prog84(":Disp 1\n:Disp 20\n:Disp 3\n:Disp 4", "ZZA")
        k4, v4 = prog84(":Disp \"NEW\"", "ZZD")
        del fake.vars[k3]
        fake.vars[k1b] = v1b
        fake.vars[k4] = v4
        b = make_backup("ti84", fake, root, t2)
        ma, mb = cb.load(a), cb.load(b)
        rows = by_label(bc.compare("ti84", ma, mb))
        f += check({l: r["status"] for l, r in rows.items()} ==
                   {"ZZA": bc.CHANGED, "ZZB": bc.SAME, "ZZC": bc.REMOVED, "ZZD": bc.ADDED},
                   "compare 84: changed, unchanged, removed, added (by SHA-256)")
        order = [r["status"] for r in bc.compare("ti84", ma, mb)]
        f += check(order == [bc.CHANGED, bc.ADDED, bc.REMOVED, bc.SAME], "compare: changes listed first")
        f += check(bc.summary_line(bc.compare("ti84", ma, mb)) == "1 changed, 1 added, 1 removed, 1 unchanged",
                   "compare: the summary line")
        ta, tb, why = bc.texts_for("ti84", rows["ZZA"])
        f += check(why is None and "Disp 2" in ta and "Disp 20" in tb, "84 program texts read back from both backups")
        uni = bc.unified(ta, tb)
        f += check("-Disp 2" in uni and "+Disp 20" in uni and "+Disp 4" in uni, "unified diff: - and + lines")
        side = bc.side_by_side(ta, tb)
        f += check(("Disp 2", "Disp 20", "changed") in side and (None, "Disp 4", "added") in side and
                   side[0][2] == "same", "side by side: same, changed and added rows")
        ta, tb, why = bc.texts_for("ti84", rows["ZZD"])
        f += check(why is None and ta == "" and "NEW" in tb, "an added program diffs against nothing")
        # The quick listing: sizes only
        quick = bc.listing_manifest("ti84", fake.run)
        q = by_label(bc.compare("ti84", ma, quick))
        f += check(q["ZZB"]["status"] == bc.SAME_SIZE and q["ZZA"]["status"] == bc.CHANGED and
                   q["ZZC"]["status"] == bc.REMOVED and q["ZZD"]["status"] == bc.ADDED,
                   "compare with the calculator's list: same size / changed by size")
        f += check(bc.texts_for("ti84", q["ZZB"])[2] is not None, "... and no text for a listed-only item")
        # A snapshot of the calculator now: exact, and its temporary folder goes
        folder, snap = bc.snapshot("ti84", fake.run, {})
        s = by_label(bc.compare("ti84", mb, snap))
        f += check(all(r["status"] == bc.SAME for r in s.values()) and len(s) == 3,
                   "snapshot of the calculator now = the newest backup")
        bc.discard(snap)
        f += check(not os.path.exists(folder), "the snapshot's temporary folder is removed")
        bc.discard(mb)
        f += check(os.path.isdir(b), "discard never touches a real backup")
        # One item back
        asked = []
        fake.lines = []
        zza_old = next(i for i in ma["items"] if i["name"] == "ZZA")
        ok, why = bc.restore_one("ti84", fake.run, ma, zza_old, lambda l: asked.append(l) or False)
        f += check(not ok and asked == ["ZZA"] and not any(l.startswith("send") for l in fake.lines),
                   "restore one: a name on the calculator asks first; No sends nothing")
        ok, why = bc.restore_one("ti84", fake.run, ma, zza_old, lambda l: True)
        sent = [l for l in fake.lines if l.startswith("send")]
        f += check(ok and len(sent) == 1 and fake.vars[k1] == v1, "restore one: Yes sends just that one (old text back)")
        asked = []
        zzc = next(i for i in ma["items"] if i["name"] == "ZZC")
        ok, why = bc.restore_one("ti84", fake.run, ma, zzc, lambda l: asked.append(l) or False)
        f += check(ok and not asked and k3 in fake.vars, "restore one: a name not there is sent without asking")
        ok, why = bc.restore_one("ti84", fake.run, ma, dict(zzc, name="ZZQ"), lambda l: True)
        f += check(not ok and "isn't in this backup" in why, "restore one: only an item of that backup")
        # ---- TI-89 Titanium ----
        ka, va = prog89("Disp 1\nDisp 2", "zza")
        kb, vb = prog89("Disp 9", "zzb", b"zzdir")
        f89 = FakeDusb("ti89", {ka: va, kb: vb})
        a89 = make_backup("ti89", f89, root, t1)
        ka2, va2 = prog89("Disp 1\nDisp 3", "zza")
        f89.vars[ka2] = va2
        b89 = make_backup("ti89", f89, root, t2)
        r89 = by_label(bc.compare("ti89", cb.load(a89), cb.load(b89)))
        f += check(r89["main\\zza"]["status"] == bc.CHANGED and r89["zzdir\\zzb"]["status"] == bc.SAME,
                   "compare 89: folder\\name, changed and unchanged")
        ta, tb, why = bc.texts_for("ti89", r89["main\\zza"])
        f += check(why is None and "Disp 2" in ta and "Disp 3" in tb, "89 program texts (not yet run) read back")
        # ---- TI-Nspire CX II ----
        src1 = b"print('zz one')\nx = 1\n"
        src2 = b"print('zz one')\nx = 2\n"
        fn = FakeNspire({"/zzdir/zzp.py": src1, "/zzdir/zzdoc.tns": tns_writer.python_tns("zzdoc.py", src1),
                         "/zzkeep.txt": b"same"})
        an = make_backup("nspire", fn, root, t1)
        fn.files["/zzdir/zzp.py"] = src2
        fn.files["/zzdir/zzdoc.tns"] = tns_writer.python_tns("zzdoc.py", src2)
        del fn.files["/zzkeep.txt"]
        bn = make_backup("nspire", fn, root, t2)
        mna = cb.load(an)
        rn = by_label(bc.compare("nspire", mna, cb.load(bn)))
        f += check(rn["zzdir/zzp.py"]["status"] == bc.CHANGED and rn["zzdir/zzdoc.tns"]["status"] == bc.CHANGED
                   and rn["zzkeep.txt"]["status"] == bc.REMOVED, "compare Nspire: paths, changed and removed")
        ta, tb, why = bc.texts_for("nspire", rn["zzdir/zzp.py"])
        f += check(why is None and "x = 1" in ta and "x = 2" in tb, "Nspire .py texts")
        ta, tb, why = bc.texts_for("nspire", rn["zzdir/zzdoc.tns"])
        f += check(why is None and "x = 1" in ta and "x = 2" in tb, "Nspire .tns: the Python program inside")
        asked = []
        ok, why = bc.restore_one("nspire", fn.run, mna, next(i for i in mna["items"] if i["path"] == "/zzkeep.txt"),
                                 lambda l: asked.append(l) or True)
        f += check(ok and not asked and fn.files.get("/zzkeep.txt") == b"same" and
                   any(l.startswith("put ") for l in fn.lines), "restore one (Nspire): put back where it was")
        # ---- The list of backups ----
        os.makedirs(os.path.join(root, "not a backup"))
        with open(os.path.join(root, "not a backup", cb.MANIFEST), "w") as fh:
            fh.write("{broken")
        listed = bc.list_backups("ti84", root)
        f += check([fm[0] for fm in listed] == [b, a], "list_backups: this model's, newest first, junk passed over")
        f += check(bc.backup_title(*listed[0]).startswith("2026-11-28 18:30:00 - 3 item(s)"), "backup titles")
        # The command line
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = bc.main([a, b, "ZZA"])
        f += check(code == 0 and "+Disp 20" in buf.getvalue() and "removed" in buf.getvalue(),
                   "backup_compare.py on the command line: the list and one diff")
        f += window_compare_checks(root, a, b, fake)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    return f


# ---- Macros ----

class Clock(object):
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def macro_checks():
    f = 0
    # Names <-> codes
    for slug, keys in (("ti84", ["quit", "mode", "enter", "A", "1", "clear"]),
                       ("ti89", ["home", "mode", "esc", "y=", "x", "f1"]),
                       ("nspire", ["home", "menu", "enter", "a", "b", "7", "{"])):
        codes = [mc.code_of(slug, k) for k in keys]
        back = [mc.code_of(slug, mc.name_for(slug, c)) for c in codes]
        f += check(None not in codes and back == codes, "macro keys %s: name -> code -> name -> same code" % slug)
    f += check(mc.code_of("ti84", "#1f") == 0x1F and mc.name_for("ti84", 0xFFFF) == "#ffff",
               "macro keys: a code without a name is kept as #hex")
    f += check(mc.code_of("ti84", "nosuchkey") is None, "macro keys: an unknown name has no code")

    # The recorder
    clk = Clock()
    rec = mc.Recorder("ti84", keep_pauses=True, clock=clk)
    fmt = mc.calc_for("ti84").key_fmt
    rec.tap("key " + fmt % mc.code_of("ti84", "quit"))
    clk.t += 0.2
    rec.tap("keys %s %s" % (fmt % mc.code_of("ti84", "mode"), fmt % mc.code_of("ti84", "down")))
    clk.t += 2.34
    rec.tap("key " + fmt % mc.code_of("ti84", "quit"))
    rec.tap("shot C:\\x.ppm")
    rec.tap("keys zz")
    steps = rec.result()
    f += check([s["key"] for s in steps] == ["quit", "mode", "down", "quit"],
               "recorder: key and keys lines become steps, other lines don't")
    f += check([s["wait_ms"] for s in steps] == [0, 0, 2300, 0],
               "recorder: a pause of 2.34 s is a 2.3 s wait after the key before it; 0.2 s isn't one")
    rec2 = mc.Recorder("ti84", keep_pauses=False, clock=clk)
    rec2.tap("key " + fmt % mc.code_of("ti84", "quit"))
    clk.t += 5
    rec2.tap("key " + fmt % mc.code_of("ti84", "quit"))
    f += check([s["wait_ms"] for s in rec2.result()] == [0, 0], "recorder: pauses dropped unless kept")
    f += mirror_tap_checks()

    # Serialising
    m1 = mc.new_macro("ti84", "zz test", steps)
    m1["ok_risky"] = []
    back = mc.from_json("ti84", mc.to_json("ti84", mc.builtins("ti84") + [m1]))
    f += check(back == [mc.validate("ti84", m1)] and back[0]["steps"] == steps,
               "macros JSON: round trip; the built-in examples aren't written")
    for text, why in ((mc.to_json("ti89", [mc.new_macro("ti89", "x", [{"key": "home", "wait_ms": 0}])]), "another model"),
                      ('{"format": "CalcSuite macros", "format_version": 1, "model": "ti84", '
                       '"macros": [{"name": "x", "steps": [{"key": "nosuch"}]}]}', "an unknown key"),
                      ("{not json", "broken JSON"), ('{"format": "other"}', "another format")):
        try:
            mc.from_json("ti84", text)
            f += check(False, "macros JSON refuses %s" % why)
        except mc.MacroError:
            f += check(True, "macros JSON refuses %s" % why)
    v = mc.validate("ti84", {"name": "  zz\nwait  ", "steps": [{"key": "quit", "wait_ms": 999999}]})
    f += check(v["name"] == "zz wait" and v["steps"][0]["wait_ms"] == mc.WAIT_MAX_MS,
               "macros: names cleaned, waits capped")
    d = tempfile.mkdtemp(prefix="calcsuite_macros_test_")
    try:
        f += check(mc.load("ti84", d) == [], "macros file: none yet is an empty list")
        mc.save("ti84", mc.builtins("ti84") + [m1], d)
        f += check(mc.load("ti84", d) == [mc.validate("ti84", m1)] and
                   not os.path.exists(mc.store_path("ti84", d) + ".part"), "macros file: saved and read back")
        with open(mc.store_path("ti84", d)) as fh:
            f += check(json.load(fh)["model"] == "ti84", "macros file: one per model, says which")
    finally:
        shutil.rmtree(d, ignore_errors=True)
    allm, added = mc.merge([m1], [dict(m1), dict(m1)])
    f += check([m["name"] for m in allm] == ["zz test", "zz test (2)", "zz test (3)"] and len(added) == 2,
               "import: a name taken already gets (2), (3)")

    # The plan
    quit_, mode = mc.code_of("ti84", "quit"), mc.code_of("ti84", "mode")
    seg = mc.plan("ti84", [{"key": "quit", "wait_ms": 0}, {"key": "mode", "wait_ms": 1500},
                           {"key": "quit", "wait_ms": 0}, {"key": "mode", "wait_ms": 400}])
    f += check(seg == [("keys", [quit_, mode]), ("wait", 1500), ("keys", [quit_, mode])],
               "plan: keys together until a wait; a wait after the last key is dropped")
    seg = mc.plan("ti84", [{"key": "1", "wait_ms": 0}] * 150)
    f += check([len(s[1]) for s in seg] == [64, 64, 22], "plan: long runs in commands of 64 keys")
    try:
        mc.plan("ti84", [{"key": "nosuch", "wait_ms": 0}])
        f += check(False, "plan refuses an unknown key")
    except mc.MacroError:
        f += check(True, "plan refuses an unknown key")

    # The player, with a faked sender that answers later (as the link thread does)
    events = []
    t0 = time.time()

    def send(codes, done):
        events.append(("send", list(codes), time.time() - t0))

        def answer():
            events.append(("done", list(codes), time.time() - t0))
            done(True)
        threading.Timer(0.15, answer).start()
        return True
    ended = []
    p = mc.Player([("keys", [1, 2]), ("wait", 300), ("keys", [3]), ("keys", [4])], send,
                  lambda ok, why: ended.append((ok, why)),
                  sleep=lambda s: (events.append(("sleep", s, time.time() - t0)), time.sleep(s)))
    p.run()
    for _ in range(40):  # The faked answers come from timer threads: a slow CI runner lags
        if sum(1 for e in events if e[0] == "done") == 3:
            break
        time.sleep(0.05)
    kinds = [e[0] for e in events]
    f += check(ended == [(True, None)] and kinds[:3] == ["send", "done", "sleep"] and
               events[2][1] == 0.3, "player: the wait starts only after the calculator took the keys")
    f += check([e[1] for e in events if e[0] == "send"] == [[1, 2], [3], [4]] and kinds.count("done") == 3,
               "player: every key in order; it ends once the last keys are taken")
    ended = []
    p = mc.Player([("keys", [1]), ("wait", 5000), ("keys", [2])], lambda c, d: (d(True), True)[1],
                  lambda ok, why: ended.append((ok, why)))
    th_ = threading.Thread(target=p.run)
    th_.start()
    time.sleep(0.2)
    p.stop()
    th_.join(3)
    f += check(ended == [(False, "stopped")] and p.sent == 1, "player: Stop during a wait ends it, nothing more sent")
    ended = []
    mc.Player([("keys", [1])], lambda c, d: False, lambda ok, why: ended.append((ok, why))).run()
    f += check(ended and not ended[0][0], "player: a calculator not connected stops it with why")
    ended = []
    mc.Player([("keys", [1]), ("wait", 10), ("keys", [2])], lambda c, d: (d(False), True)[1],
              lambda ok, why: ended.append((ok, why))).run()
    f += check(ended and not ended[0][0] and "no answer" in ended[0][1], "player: keys the link refused stop it")

    # The warning rule
    for slug in mc.SLUGS:
        bi = mc.builtins(slug)
        # Only the 84's "Go to MEM" opens a menu with Reset in it: it asks before its first replay
        f += check(len(bi) >= 2 and all(not mc.risky_keys(slug, m) for m in bi if m["name"] != "Go to MEM") and
                   all(mc.code_of(slug, s["key"]) is not None for m in bi for s in m["steps"]),
                   "built-in macros (%s): every key exists, none deletes, clears or resets" % slug)
    m = mc.new_macro("ti84", "zz", [{"key": "quit", "wait_ms": 0}, {"key": "del", "wait_ms": 0}])
    f += check([k for k, _w in mc.needs_warning("ti84", m)] == ["del"], "warning: DEL asks before the first replay")
    mc.accept_risky("ti84", m)
    f += check(mc.needs_warning("ti84", m) == [], "warning: once said yes to, not again")
    m["steps"].append({"key": "mem", "wait_ms": 0})
    f += check([k for k, _w in mc.needs_warning("ti84", m)] == ["mem"], "warning: a reset-menu key added asks again")
    for slug, key in (("nspire", "backspace"), ("ti89", "clear"), ("ti89", "mem"), ("ti84", "clear"),
                      ("ti84", "#9")):
        f += check(bool(mc.needs_warning(slug, mc.new_macro(slug, "zz", [{"key": key, "wait_ms": 0}]))),
                   "warning: %s on the %s" % (key, slug))
    f += check(not mc.needs_warning("nspire", mc.new_macro("nspire", "zz", [{"key": "enter", "wait_ms": 0}])),
               "warning: enter alone doesn't")
    look = next(m for m in mc.builtins("ti84") if m["name"].startswith("Look at the MODE"))
    f += check(mc.describe("ti84", look) == "2nd QUIT, wait 0.3 s, MODE, wait 2 s, 2nd QUIT",
               "describe: keys as their keycaps, with the waits")
    f += goto_checks()
    return f


def goto_checks():
    """The built-in "Go to" macros (their exact keys), pins and hotkeys: saved, read back,
    conflicts moved, imports never steal a hotkey"""
    f = 0
    want = {
        "ti84": {"Home": ["quit"], "Y=": ["y="], "WINDOW": ["window"], "TABLE": ["table"], "MODE": ["mode"],
                 "STAT EDIT": ["stat", "enter"], "MATRIX": ["matrix"], "PRGM": ["prgm"], "MEM": ["mem"]},
        "ti89": {"Home": ["home"], "Y=": ["y="], "WINDOW": ["window"], "GRAPH": ["graph"], "TABLE": ["table"],
                 "Var-Link": ["var-link"], "MODE": ["mode"]},
        "nspire": {"Home": ["home"], "Scratchpad: Calculate": ["home", "a"], "Scratchpad: Graph": ["home", "b"]},
    }
    labels = {"ti84": {"TABLE": "TABLE", "MATRIX": "MATRIX", "MEM": "MEM", "Home": "2nd QUIT"},
              "ti89": {"Var-Link": "VAR-LINK", "Y=": "Y="}}
    for slug, table in want.items():
        got = {m["name"][6:]: [s["key"] for s in m["steps"]] for m in mc.builtins(slug) if m.get("go")}
        f += check(got == table, "Go to macros (%s): %s" % (slug, ", ".join(sorted(got))))
        codes = [mc.code_of(slug, k) for keys in table.values() for k in keys]
        f += check(all(c is not None for c in codes), "Go to macros (%s): every key has a code" % slug)
        for name, lab in labels.get(slug, {}).items():
            f += check(mc.label_of(slug, table[name][-1]) == lab, "Go to %s on the %s presses %s" % (name, slug, lab))
        for m in mc.builtins(slug):
            if m.get("go"):
                bad = [k for k, _w in mc.risky_keys(slug, m)]
                f += check(bad in ([], ["mem"]), "Go to %s (%s) only navigates" % (m["name"][6:], slug))
    # Pins and hotkeys
    d = tempfile.mkdtemp(prefix="calcsuite_macros_pins_")
    try:
        allm = mc.builtins("ti84")
        user = mc.new_macro("ti84", "zz mine", [{"key": "quit", "wait_ms": 0}])
        allm.append(user)
        yeq = next(m for m in allm if m["name"] == "Go to Y=")
        yeq["pinned"] = True
        user["pinned"] = True
        f += check(mc.set_hotkey(allm, yeq, 1) is None and yeq["hotkey"] == 1, "hotkey: Ctrl+1 to Go to Y=")
        was = mc.set_hotkey(allm, user, 1)
        f += check(was is yeq and "hotkey" not in yeq and user["hotkey"] == 1,
                   "hotkey: Ctrl+1 given to another macro moves (the old one says who had it)")
        mc.set_hotkey(allm, yeq, 9)
        try:
            mc.set_hotkey(allm, yeq, 10)
            f += check(False, "hotkey: Ctrl+10 refused")
        except mc.MacroError:
            f += check(True, "hotkey: Ctrl+10 refused")
        f += check(mc.free_hotkeys(allm) == [2, 3, 4, 5, 6, 7, 8], "hotkey: the free ones listed")
        mc.save("ti84", allm, d)
        back = mc.load_all("ti84", d)
        by = {m["name"]: m for m in back}
        f += check(by["Go to Y="].get("pinned") and by["Go to Y="].get("hotkey") == 9 and
                   by["zz mine"].get("pinned") and by["zz mine"].get("hotkey") == 1 and
                   not by["Go to TABLE"].get("pinned") and len(back) == len(allm),
                   "pins and hotkeys: saved with the macros (built-in ones by name) and read back")
        f += check(mc.load("ti84", d) == [mc.validate("ti84", user)],
                   "pins and hotkeys: load() is still the user's macros only")
        # A file edited by hand with one hotkey twice, or a bad one: never two macros on one key
        with open(mc.store_path("ti84", d), encoding="utf-8") as fh:
            j = json.load(fh)
        j["macros"].append({"name": "zz twice", "steps": [{"key": "mode", "wait_ms": 0}], "hotkey": 1})
        j["macros"].append({"name": "zz odd", "steps": [{"key": "mode", "wait_ms": 0}], "hotkey": 12,
                            "pinned": "yes"})
        with open(mc.store_path("ti84", d), "w", encoding="utf-8") as fh:
            json.dump(j, fh)
        back = {m["name"]: m for m in mc.load_all("ti84", d)}
        f += check(back["zz mine"].get("hotkey") == 1 and "hotkey" not in back["zz twice"] and
                   "hotkey" not in back["zz odd"] and "pinned" not in back["zz odd"],
                   "hotkeys: a doubled or bad one in the file is dropped, never two macros on one key")
        _all, added = mc.merge(allm, [dict(mc.new_macro("ti84", "zz in", [{"key": "mode", "wait_ms": 0}]), hotkey=1)])
        f += check(added[0].get("hotkey") is None and user["hotkey"] == 1, "import: a hotkey taken here isn't taken over")
    finally:
        shutil.rmtree(d, ignore_errors=True)
    return f


def mirror_tap_checks():
    """Mirror.queue hands key lines (only) to the key taps"""
    try:
        import mirror
    except Exception as e:
        print("SKIP mirror's key tap (%s)" % e)
        return 0

    class M(object):
        jobs_lock = threading.Lock()

        def __init__(self):
            self.jobs, self.key_taps, self.last_key = [], [], 0
    m, got = M(), []
    m.key_taps.append(got.append)
    mirror.Mirror.queue(m, "key 9")
    mirror.Mirror.queue(m, "keys 1 2")
    mirror.Mirror.queue(m, "ls")
    return check(got == ["key 9", "keys 1 2"] and len(m.jobs) == 3, "mirror: queued key lines reach the macro recorder")


# ---- The windows, with faked links ----

class FakeCalcModel(object):
    pass


class FakeMirror(object):
    """What the Macros panel and the Manager use of a Mirror; queue() answers at once"""

    def __init__(self, slug, root):
        import tkinter as tk
        import calc_models
        self.calc = calc_models.BY_SLUG[slug]
        self.session = object()
        self.running = True
        self.keys_on = tk.BooleanVar(master=root, value=True)
        self.key_taps, self.queued, self.info = [], [], {}
        self.listeners, self.root = [], root
        self.last_press = tk.StringVar(master=root)
        self.history = []

    def queue(self, line, note=None, done=None, progress=None):
        self.queued.append(line)
        for tap in list(self.key_taps):
            tap(line)
        if done is not None:
            done(0, ["OK"])

    def pressed(self, keysym, char, names, text=None):
        self.history.append(text)


class FakePanel(object):
    def __init__(self, m):
        self.m, self.calc = m, m.calc


class FakeManager(object):
    def __init__(self, root, slug, fake):
        import tkinter as tk
        import calc_models
        self.win, self.slug, self.calc = root, slug, calc_models.BY_SLUG[slug]
        self.m = type("M", (), {"info": {}, "session": object()})()
        self.busy = None
        self.fake = fake
        self.status = tk.StringVar(master=root)

    def run_batch(self, cmds, timeout=900):
        return self.fake.run(cmds)

    def connected(self):
        return True

    def set_busy(self, what):
        self.busy = what

    def ui(self, fn, *args):
        self.win.after(0, lambda: fn(*args))

    def refresh(self):
        pass


def pump(root, cond, seconds):
    import mirror
    t0 = time.time()
    while time.time() - t0 < seconds:
        while not mirror._TK_QUEUE.empty():  # What App.pump does with workers' after() calls
            fn, args = mirror._TK_QUEUE.get()
            fn(*args)
        root.update()
        if cond():
            return True
        time.sleep(0.02)
    return False


def tk_root():
    try:
        import tkinter as tk
        import mirror  # noqa: F401  (its after() patch: workers' window work is queued)
        root = tk.Tk()
        root.withdraw()
        return root
    except Exception as e:
        print("SKIP the windows (no Tk here: %s)" % e)
        return None


def window_compare_checks(backups_root, a, b, fake):
    root = tk_root()
    if root is None:
        return 0
    import backup_compare_ui as bui
    from tkinter import messagebox
    f = 0
    saved = messagebox.askyesno
    try:
        mgr = FakeManager(root, "ti84", fake)
        d = bui.CompareDialog(mgr, root=backups_root)
        root.update()
        f += check(len(d.backups) == 2 and d.before_var.get().startswith("2026-11-20") and
                   d.after_var.get().startswith("2026-11-28"), "Compare window: the two newest backups picked")
        d.compare()
        root.update()
        labels = [d.tree.item(i, "text") for i in d.tree.get_children()]
        f += check(labels == ["ZZA", "ZZD", "ZZC"] and "1 unchanged" in d.counts.get(),
                   "Compare window: changes listed, unchanged hidden")
        d.tree.selection_set("0")
        root.update()
        f += check(str(d.diff_btn.cget("state")) == "normal" and str(d.restore_before.cget("state")) == "normal",
                   "Compare window: a row picked: Show the difference, Restore this one")
        d.show_diff()
        root.update()
        wins = [w for w in d.win.winfo_children() if w.winfo_class() == "Toplevel"]
        f += check(len(wins) == 1, "Compare window: Show the difference opens the diff")
        _shot_window(d.win, "compare-window")
        if wins:
            _shot_window(wins[0], "diff-side-by-side")
        asked = []
        messagebox.askyesno = lambda *a, **k: asked.append(a) or False
        fake.lines = []
        d.restore("before")
        pump(root, lambda: mgr.busy is None and "Not sent" in d.note.get(), 5)
        f += check(asked and "Not sent" in d.note.get() and not any(l.startswith("send") for l in fake.lines),
                   "Compare window: Restore this one asks before replacing; No sends nothing")
        d.after_var.set(bui.NOW_LIST)
        d.compare()
        pump(root, lambda: not d.busy and d.mans["after"] is not None and d.mans["after"].get("snapshot"), 5)
        f += check(d.mans["after"] and d.mans["after"].get("snapshot") and
                   str(d.restore_after.cget("state")) == "disabled",
                   "Compare window: against the calculator's list; nothing to restore from that side")
        d.win.destroy()
    finally:
        messagebox.askyesno = saved
        _end(root)
    return f


def window_macro_checks():
    root = tk_root()
    if root is None:
        return 0
    import tkinter as tk
    import ui_theme as th
    import macros_ui as mui
    from tkinter import messagebox
    f = 0
    d = tempfile.mkdtemp(prefix="calcsuite_macros_ui_")
    saved = messagebox.askyesno
    try:
        th.style_ttk(root)
        m = FakeMirror("ti84", root)
        top = tk.Toplevel(root)
        top.geometry("470x720")
        sec = mui.MacrosSection(FakePanel(m), top, folder=d)
        sec.frame.pack(fill="both", expand=True)
        root.update()
        f += check(len(sec.tree.get_children()) == len(mc.builtins("ti84")), "Macros panel: the 84's built-in macros")
        sec.toggle_record()
        fmt = m.calc.key_fmt
        m.queue("key " + fmt % mc.code_of("ti84", "quit"))
        m.queue("keys %s %s" % (fmt % mc.code_of("ti84", "math"), fmt % mc.code_of("ti84", "del")))
        sec.toggle_record()
        f += check(sec.recorded and [s["key"] for s in sec.recorded] == ["quit", "math", "del"],
                   "Macros panel: Record ... Stop recording keeps the keys")
        sec.name_var.set("zz risky")
        sec.save_recording()
        f += check(len(mc.load("ti84", d)) == 1 and sec.macros[-1]["name"] == "zz risky",
                   "Macros panel: Save writes the macros file")
        asked = []
        messagebox.askyesno = lambda *a, **k: asked.append(a) or False
        m.queued = []
        sec.play()
        f += check(asked and not m.queued and sec.player is None,
                   "Macros panel: a macro with DEL asks before its first replay; No plays nothing")
        messagebox.askyesno = lambda *a, **k: asked.append(a) or True
        asked.clear()
        sec.play()
        pump(root, lambda: sec.player is None, 5)
        f += check(asked and m.queued == ["keys " + " ".join(fmt % mc.code_of("ti84", k) for k in ("quit", "math", "del"))]
                   and "Played" in sec.note.get(), "Macros panel: Yes plays it as one paced keys command")
        asked.clear()
        m.queued = []
        sec.play()
        pump(root, lambda: sec.player is None, 5)
        f += check(not asked and m.queued and mc.load("ti84", d)[0]["ok_risky"] == ["del"],
                   "Macros panel: the second replay doesn't ask (the yes is saved)")
        sec.tree.selection_set("0")
        root.update()
        f += check(str(sec.edit_btn.cget("state")) == "disabled" and str(sec.del_btn.cget("state")) == "disabled",
                   "Macros panel: examples can't be edited or deleted")
        sec.tree.selection_set(str(len(sec.macros) - 1))
        root.update()
        sec.edit()
        root.update()
        ed = [w for w in top.winfo_children() if isinstance(w, tk.Toplevel)]
        f += check(len(ed) == 1, "Macros panel: Edit... opens the editor")
        dlg = _find_edit(sec)
        if dlg is not None:
            dlg.tree.selection_set("2")
            dlg.move(-1)
            dlg.wait_var.set("1500")
            dlg.set_wait()
            dlg.key_var.set("enter")
            dlg.add()
            dlg.name_var.set("zz edited")
            _shot_window(dlg.win, "macro-editor")
            dlg.save()
            got = mc.load("ti84", d)[0]
            f += check(got["name"] == "zz edited" and [s["key"] for s in got["steps"]] == ["quit", "del", "enter", "math"]
                       and got["steps"][1]["wait_ms"] == 1500, "Macro editor: reorder, wait, add a key, rename, save")
        # Pins and hotkeys from the panel (the box keeps them; the file has them)
        box = sec.box
        yeq = next(k for k, x in enumerate(sec.macros) if x["name"] == "Go to Y=")
        sec.tree.selection_set(str(yeq))
        root.update()
        sec.toggle_pin()
        f += check([x["name"] for x in box.pinned()] == ["Go to Y="] and
                   mc.load_all("ti84", d)[yeq].get("pinned") and str(sec.pin_btn.cget("text")) == "Unpin",
                   "Macros panel: Pin under the screen pins it (saved; the button says Unpin)")
        f += check(sec.set_hotkey(3, ask=False) and box.by_hotkey(3) is sec.macros[yeq] and
                   sec.tree.item(str(yeq), "values")[1] == "Ctrl+3", "Macros panel: Hotkey gives Ctrl+3 (shown in the list)")
        mine = len(sec.macros) - 1
        sec.tree.selection_set(str(mine))
        root.update()
        asked.clear()
        messagebox.askyesno = lambda *a, **k: asked.append(a) or False
        f += check(not sec.set_hotkey(3) and asked and box.by_hotkey(3) is sec.macros[yeq],
                   "hotkey conflict: asked first; No keeps it where it was")
        messagebox.askyesno = lambda *a, **k: asked.append(a) or True
        f += check(sec.set_hotkey(3) and box.by_hotkey(3) is sec.macros[mine] and
                   "hotkey" not in sec.macros[yeq] and mc.load_all("ti84", d)[mine].get("hotkey") == 3,
                   "hotkey conflict: Yes moves Ctrl+3 to the picked macro (saved)")
        m.queued = []
        f += check(box.hotkey(3, top), "Ctrl+3 plays its macro")
        pump(root, lambda: box.player is None, 5)
        f += check(m.queued and m.queued[0].startswith("keys "), "Ctrl+3: its keys go to the calculator")
        f += check(not box.hotkey(5, top), "Ctrl+5 with no macro: the key goes on to the calculator")
        heard = []
        box.listeners.append(lambda: heard.append(1))
        sec.tree.selection_set(str(yeq))
        sec.toggle_pin()
        f += check(heard and not box.pinned(), "Unpin: the tab's pinned buttons hear about it")
        _shot_window(top, "macros-panel")
        top.destroy()
        # The real side panel and Files manager, with the faked mirror: the hooks are there
        import ui_panels
        import calc_manager
        top = tk.Toplevel(root)
        m2 = FakeMirror("ti89", root)
        panel = ui_panels.SidePanel(top, None, m2)
        panel.frame.pack(fill="both", expand=True)
        panel.show("Macros")
        root.update()
        f += check(isinstance(panel.sections.get("Macros"), mui.MacrosSection) and "Macros" in panel.buttons,
                   "side panel: a Macros tab that opens the Macros panel")
        # The icon strip: one button per section, short labels, the full name as the heading
        f += check(list(panel.buttons) == list(ui_panels.SECTIONS) and ui_panels.SECTIONS[-1] == ui_panels.INFO,
                   "side panel strip: %s" % ", ".join(ui_panels.LABELS.get(n, n) for n in panel.buttons))
        for n in (ui_panels.INFO, "Get programs"):  # Stand-ins: those sections need a real link
            panel.sections[n] = type("S", (), {"frame": tk.Frame(panel.body)})()
        panel.show("Info")
        root.update()
        c = panel.buttons[ui_panels.INFO]
        texts = [c.itemcget(i, "text") for i in c.find_all() if c.type(i) == "text"]
        f += check(panel.current == ui_panels.INFO and str(panel.head.cget("text")) == "Calculator info" and
                   texts == ["Info"] and c.itemcget("bar", "fill") == th.ACCENT and str(c.cget("bg")) == th.PANEL2,
                   "side panel strip: Info (label) opens Calculator info (heading), picked in the accent colour")
        panel.show("Programs")
        root.update()
        f += check(panel.current == "Get programs" and str(panel.head.cget("text")) == "Get programs" and
                   c.itemcget("bar", "fill") != th.ACCENT, "side panel strip: Programs is Get programs; one picked at a time")
        f += check(panel.strip.frame.winfo_manager() == "pack" and panel.strip.frame.pack_info()["side"] == "right",
                   "side panel strip: on the panel's right edge")
        mgr = calc_manager.Manager(m2, d, parent=top)
        root.update()
        texts = [str(w.cget("text")) for w in mgr.win.winfo_children()[0].winfo_children()
                 if isinstance(w, tk.Button)]
        f += check("Compare..." in texts, "Files: a Compare... button beside Back up... and Restore...")
        mgr.close()
        top.destroy()
    finally:
        messagebox.askyesno = saved
        shutil.rmtree(d, ignore_errors=True)
        _end(root)
    return f


def app_tab_checks():
    """The main window's tool tabs (mirror.App.open_tool_tab, tool_tabs.window): made, shown,
    the same key shows the same tab, ✕ closes through the tool's own close, popped out and
    back, the tab before comes back. The App runs with no USB scan."""
    try:
        import tkinter as tk
        import mirror
        import tool_tabs
    except Exception as e:
        print("SKIP the tool tabs (%s)" % e)
        return 0
    f = 0
    saved_scan = mirror.App.scan_loop
    mirror.App.scan_loop = lambda self: None  # Never the real USB scan
    try:
        app = mirror.App()
    except Exception as e:
        mirror.App.scan_loop = saved_scan
        print("SKIP the tool tabs (no window: %s)" % e)
        return 0
    try:
        root = app.root
        root.withdraw()
        root.update()
        calls = []

        class Tool(tk.Frame):
            def close(self):
                calls.append("close")
                self.destroy()
        p = app.open_tool_tab("zz", "ZZ tool", lambda parent: Tool(parent))
        root.update()
        f += check(isinstance(p, Tool) and app.current == "tool:zz" and "tool:zz" in app.tab_widgets and
                   p.winfo_toplevel() is root and str(app.pop_btn.cget("state")) == "normal",
                   "tool tab: open_tool_tab makes a tab of the window and shows it")
        app.show_tab("all")
        again = app.open_tool_tab("zz", "ZZ again", lambda parent: 1 / 0)
        f += check(again is p and app.current == "tool:zz" and len(app.tools) == 1,
                   "tool tab: the same key again shows the tab it has")
        app.close_tool_tab("zz")
        root.update()
        f += check(calls == ["close"] and not app.tools and "tool:zz" not in app.tab_widgets and app.current == "all",
                   "tool tab: its close button runs the tool's close; the tab goes and the one before comes back")
        # A tool written as a window gets a ToolFrame in a tab
        closed = []
        w = tool_tabs.window(root, "zzwin", "ZZ window")
        w.title("ZZ renamed")
        w.geometry("400x300")
        w.minsize(10, 10)
        w.protocol("WM_DELETE_WINDOW", lambda: (closed.append(1), w.destroy()))
        root.update()
        f += check(isinstance(w, tool_tabs.ToolFrame) and app.current == w._key and
                   str(app.tab_widgets[w._key]["name"].cget("text")) == "ZZ renamed",
                   "tool tab: a window-style tool builds into a tab (title() names the tab)")
        w2 = tool_tabs.window(root, "zzwin", "ZZ second")
        f += check(w2._key == "tool:zzwin#2" and len(app.tools) == 2, "tool tab: a second one with that key gets its own tab")
        app.pop_out()
        root.update()
        f += check(w2.popped and app.current != w2._key, "tool tab: Open in its own window pops it out")
        app.dock(w2._key)
        root.update()
        f += check(not w2.popped and app.current == w2._key, "tool tab: closing that window puts it back")
        app.close_tool_tab(w._key)
        w2.destroy()
        root.update()
        f += check(closed == [1] and not app.tools, "tool tab: the close button is the window's close; destroy() closes the tab")
        # The tab strip's connection dot is an image (antialiased), recoloured by state
        import ui_theme as th
        dot = th.status_dot(root)
        th.set_dot(dot, "connected")
        a = str(dot.cget("image"))
        th.set_dot(dot, "connecting")
        b = str(dot.cget("image"))
        th.set_dot(dot, bg=th.PANEL2)
        f += check(a and b and a != b and b != str(dot.cget("image")) and dot.dot_state == "connecting",
                   "tab dot: a smooth image per state and background")
        # No calculator at all (the scan found none): writing programs is still one click away
        import editor as ed
        saved_programs = ed.PROGRAMS
        ed.PROGRAMS = tempfile.mkdtemp(prefix="nocalc_app_")
        try:
            app.show_tab("all")
            app.all.layout()  # (the hidden window gets no <Configure> to run it)
            root.update()
            f += check(not app.mirrors and app.all.empty.winfo_manager() == "place" and
                       set(app.all.empty_buttons) == {"Program editor", "Solver builder", "Make a picture"},
                       "no calculator: All screens offers Program editor, Solver builder, Make a picture")
            app.write_btn.invoke()
            root.update()
            e = app.editor
            f += check(e is not None and app.current == "editor" and e.target() is None and
                       str(e.send_button.cget("state")) == "disabled" and "Plug in a" in str(e.send_hint.cget("text")),
                       "no calculator: Write a program opens the editor; Send greyed with its hint")
            app.all.empty_buttons["Make a picture"].invoke()
            root.update()
            f += check("tool:picture:pc" in app.tools, "no calculator: Make a picture opens in a tab")
            app.close_tool_tab("picture:pc")
            app.all.empty_buttons["Solver builder"].invoke()
            root.update()
            f += check("tool:solver" in app.tools, "no calculator: the Solver builder opens in a tab")
            app.close_tool_tab("solver")
            e.close(force=True)
            root.update()
        finally:
            shutil.rmtree(ed.PROGRAMS, ignore_errors=True)
            ed.PROGRAMS = saved_programs
    finally:
        mirror.App.scan_loop = saved_scan
        mirror.APP = None
        _end(app.root)
    return f


_EDITS = []
_SHOT_DIR = os.environ.get("CALCSUITE_SHOTS")  # Set: the windows are shown and saved as PNGs there


def _find_edit(sec):
    return next((o for o in _EDITS if o.section is sec), None) if _EDITS else None


def _shot_window(win, name):
    if not _SHOT_DIR:
        return
    try:
        from PIL import ImageGrab
        win.deiconify()
        win.lift()
        win.attributes("-topmost", True)
        for _ in range(20):
            win.update()
            time.sleep(0.03)
        x, y = win.winfo_rootx(), win.winfo_rooty()
        w, h = win.winfo_width(), win.winfo_height()
        os.makedirs(_SHOT_DIR, exist_ok=True)
        ImageGrab.grab((x, y, x + w, y + h), all_screens=True).save(os.path.join(_SHOT_DIR, name + ".png"))
        win.attributes("-topmost", False)
    except Exception as e:
        print("note: no screenshot of %s (%s)" % (name, e))


def _end(root):
    import gc
    gc.collect()
    try:
        root.destroy()
    except Exception:
        pass
    gc.collect()


def main():
    import macros_ui as mui
    orig = mui.EditDialog.__init__

    def track(self, *a, **k):  # Lets the check find the editor it opened
        orig(self, *a, **k)
        _EDITS.append(self)
    mui.EditDialog.__init__ = track
    try:
        f = compare_checks()
        f += macro_checks()
        f += window_macro_checks()
        f += app_tab_checks()
    finally:
        mui.EditDialog.__init__ = orig
    return f


if __name__ == "__main__":
    n = main()
    print("\n%s" % ("ALL PASSED" if not n else "%d FAILURE(S)" % n))
    sys.exit(1 if n else 0)
