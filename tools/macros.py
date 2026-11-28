"""Key macros: a key sequence recorded on a calculator's tab, saved by name per model, played
back through the same paced key path as typing.

A macro is a dict:

    {"name": "Home screen", "model": "ti84",
     "steps": [{"key": "quit", "wait_ms": 0}, ...],     # a key name, or "#1f" for a raw code
     "ok_risky": ["clear"]}                              # risky keys the user said yes to

Each model's macros are one JSON file, CalcSuite files\\macros\\<model>.json (tools/paths.py):

    {"format": "CalcSuite macros", "format_version": 1, "model": "ti84", "macros": [...]}

Export writes the same format with only the picked macros; import adds them to a model's list
(a name taken already gets " (2)"), refusing another model's.

- Recording (Recorder): every key command the tab queues on its link ("key X" / "keys X Y",
  from the keyboard, the mouse on the screen, the Symbols panel, a paste) becomes steps; with
  "keep the pauses", a gap of PAUSE_MIN_MS or more becomes that step's wait (rounded, capped).
- Playing (plan + Player): runs of keys with no wait between them go out as one "keys"
  command each (at most CHUNK codes: the link helper paces them like typed keys, and the
  TI-84 Plus CE's Fast mode or not is the link's own business); before a wait the player waits
  for the calculator to have taken the keys, then sleeps the wait. Stop ends it between commands.
- Safety (risky_keys): a macro with delete, clear, backspace or memory/reset-menu keys (or raw
  codes nobody can read) asks before it first plays, and again when such a key is added.
- Built-in macros (BUILTIN): "Go to" ones per model that only open a screen or a menu, and an
  example with waits; they can't be changed or deleted, only copied ("Duplicate").
- Pins and hotkeys: a macro's "pinned" (a button under the screen) and "hotkey" (Ctrl+1..9 on
  its calculator's tab) are saved with it; the built-in ones' in the file's "builtin_prefs",
  by name. One macro per hotkey (set_hotkey moves it).

Pure: no Tk, no USB (tools/selftest checks it). MIT licence (like the rest of the app).
"""

import json
import os
import re
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

FORMAT = "CalcSuite macros"
FORMAT_VERSION = 1
SLUGS = ("nspire", "ti84", "ti89")
PAUSE_MIN_MS = 700     # Recording with pauses kept: a gap this long or longer becomes a wait
WAIT_MAX_MS = 30000    # A single wait at most
STEPS_MAX = 2000       # Keys in one macro at most
CHUNK = 64             # Codes in one "keys" command (as pasting sends them)
NAME_MAX = 60

# Keys that delete, clear or lead to a reset's confirmation: a macro with any of them asks
# before its first replay. (The 84's and 89's MEM menus hold Reset and Delete.)
RISKY = {
    "nspire": {"backspace": "del (deletes)", "ctrl+x": "ctrl X (cut)", "ctrl+k": "ctrl K",
               "ctrl+n": "ctrl N (new document: may ask to save or discard)",
               "ctrl+z": "ctrl Z (undo)"},
    "ti84": {"del": "DEL (deletes)", "clear": "CLEAR", "mem": "2nd MEM (reset and delete menus)"},
    "ti89": {"backspace": "BACKSPACE (deletes)", "del": "DEL (deletes)", "clear": "CLEAR",
             "mem": "2nd MEM (reset menu)"},
}

def _go(name, *keys):
    """A built-in "Go to" macro: keys that only open a screen or a menu, never change anything"""
    return {"name": "Go to " + name, "go": True,
            "steps": [{"key": k, "wait_ms": w} for k, w in
                      (kw if isinstance(kw, tuple) else (kw, 0) for kw in keys)]}


# Built-in macros: the "Go to" ones (they only open a screen or a menu: pin one, or give it
# Ctrl+1..9) and an example with waits. Key names are calc_models' (the Keys panel's).
BUILTIN = {
    "nspire": [
        _go("Home", "home"),
        _go("Scratchpad: Calculate", ("home", 800), "a"),
        _go("Scratchpad: Graph", ("home", 800), "b"),
    ],
    "ti84": [
        _go("Home", "quit"),                 # 2nd MODE = QUIT
        _go("Y=", "y="),
        _go("WINDOW", "window"),
        _go("TABLE", "table"),               # 2nd GRAPH
        _go("MODE", "mode"),
        _go("STAT EDIT", "stat", "enter"),   # STAT, then 1:Edit...
        _go("MATRIX", "matrix"),             # 2nd x⁻¹
        _go("PRGM", "prgm"),
        _go("MEM", "mem"),                   # 2nd + (it holds Reset: it asks before its first replay)
        {"name": "Look at the MODE screen, then home",
         "steps": [{"key": "quit", "wait_ms": 300}, {"key": "mode", "wait_ms": 2000},
                   {"key": "quit", "wait_ms": 0}]},
    ],
    "ti89": [
        _go("Home", "home"),
        _go("Y=", "y="),                     # ◆F1
        _go("WINDOW", "window"),             # ◆F2
        _go("GRAPH", "graph"),               # ◆F3
        _go("TABLE", "table"),               # ◆F5
        _go("Var-Link", "var-link"),         # 2nd -
        _go("MODE", "mode"),
        {"name": "Look at the MODE dialog, then home",
         "steps": [{"key": "home", "wait_ms": 300}, {"key": "mode", "wait_ms": 2000},
                   {"key": "esc", "wait_ms": 300}, {"key": "home", "wait_ms": 0}]},
    ],
}
HOTKEYS = tuple(range(1, 10))  # Ctrl+1 .. Ctrl+9


class MacroError(ValueError):
    pass


def calc_for(slug):
    import calc_models
    return calc_models.BY_SLUG[slug]


# ---- Key names and codes ----

_names = {}


def names_by_code(slug):
    """{code: key name} for a model: its named keys first (so 'enter' wins over a character
    with the same code), then its typed characters"""
    if slug not in _names:
        calc = calc_for(slug)
        mod = __import__({"nspire": "nspire_keys", "ti84": "ti84_keys", "ti89": "ti89_keys"}[slug])
        out = {}
        for table in (getattr(mod, "NAMED", {}), getattr(mod, "CHAR", {})):
            for name in table:
                code = calc.code_for(name)
                if code is not None:
                    out.setdefault(code, name)
        _names[slug] = out
    return _names[slug]


def name_for(slug, code):
    """A key code -> its name, or "#hex" when it has none"""
    name = names_by_code(slug).get(code)
    if name is None and slug == "nspire" and not code & 0xFFFF and 0x20 <= code >> 16 <= 0xFF:
        ch = chr(code >> 16)  # Any other character the Nspire types: its code in the top byte
        if calc_for(slug).code_for(ch) == code:
            name = ch
    return name if name is not None else "#%x" % code


def code_of(slug, key):
    """A step's key (a name, a character or "#hex") -> its code, or None"""
    if isinstance(key, str) and re.match(r"^#[0-9a-fA-F]{1,8}$", key):
        return int(key[1:], 16)
    try:
        return calc_for(slug).code_for(key)
    except (KeyError, TypeError, ValueError):
        return None


def label_of(slug, key):
    """How a step's key is written: 'quit' -> '2nd QUIT'"""
    if key.startswith("#") and len(key) > 1:
        return "code %s" % key[1:]
    return calc_for(slug).calc_label(key)


# ---- Macros ----

def new_macro(slug, name, steps, builtin=False):
    m = {"name": clean_name(name), "model": slug, "steps": [dict(s) for s in steps], "ok_risky": []}
    if builtin:
        m["builtin"] = True
    return m


def clean_name(name):
    name = re.sub(r"[\x00-\x1f]", " ", str(name or "")).strip()
    return (name or "Macro")[:NAME_MAX]


def validate(slug, m):
    """A macro read from a file -> a clean copy. Raises MacroError."""
    if not isinstance(m, dict) or not isinstance(m.get("steps"), list):
        raise MacroError("a macro needs a name and a list of steps")
    if len(m["steps"]) > STEPS_MAX:
        raise MacroError("%s has more than %d keys" % (m.get("name"), STEPS_MAX))
    steps = []
    for s in m["steps"]:
        if not isinstance(s, dict) or not isinstance(s.get("key"), str):
            raise MacroError("a step of %s has no key" % m.get("name"))
        if code_of(slug, s["key"]) is None:
            raise MacroError("%s: the %s has no key %r" % (m.get("name"), calc_for(slug).title, s["key"]))
        try:
            wait = int(s.get("wait_ms", 0))
        except (TypeError, ValueError):
            raise MacroError("%s: a wait isn't a number" % m.get("name"))
        steps.append({"key": s["key"], "wait_ms": max(0, min(WAIT_MAX_MS, wait))})
    out = new_macro(slug, m.get("name"), steps)
    out["ok_risky"] = sorted(k for k in m.get("ok_risky", []) if isinstance(k, str))
    set_prefs(out, m)
    return out


def set_prefs(m, prefs):
    """A macro's own settings from prefs (a dict): pinned (a button under the screen) and
    hotkey (Ctrl+1..9 on the calculator's tab). Anything else is dropped."""
    m.pop("pinned", None)
    m.pop("hotkey", None)
    if prefs.get("pinned") is True:
        m["pinned"] = True
    h = prefs.get("hotkey")
    if isinstance(h, int) and not isinstance(h, bool) and h in HOTKEYS:
        m["hotkey"] = h
    return m


def builtins(slug, prefs=None):
    """The built-in macros, with the pins and hotkeys saved for them ({name: {pinned, hotkey}})"""
    out = []
    for b in BUILTIN[slug]:
        m = new_macro(slug, b["name"], b["steps"], builtin=True)
        if b.get("go"):
            m["go"] = True
        set_prefs(m, (prefs or {}).get(b["name"], {}))
        out.append(m)
    return out


# ---- Pins and hotkeys ----

def pinned(macros):
    return [m for m in macros if m.get("pinned")]


def by_hotkey(macros, n):
    return next((m for m in macros if m.get("hotkey") == n), None)


def set_hotkey(macros, m, n):
    """Gives m Ctrl+n (None: no hotkey). A macro that had Ctrl+n loses it: that one (to say
    so), else None. Raises MacroError for a key outside 1-9."""
    if n is not None and n not in HOTKEYS:
        raise MacroError("a hotkey is Ctrl+1 to Ctrl+9")
    was = None
    if n is not None:
        was = by_hotkey(macros, n)
        if was is m:
            return None
        if was is not None:
            was.pop("hotkey", None)
        m["hotkey"] = n
    else:
        m.pop("hotkey", None)
    return was


def free_hotkeys(macros):
    taken = {m.get("hotkey") for m in macros}
    return [n for n in HOTKEYS if n not in taken]


def unique_name(name, taken):
    low = {t.lower() for t in taken}
    if name.lower() not in low:
        return name
    n = 2
    while ("%s (%d)" % (name, n)).lower() in low:
        n += 1
    return "%s (%d)" % (name, n)


def risky_keys(slug, m):
    """[(key, why)] of the macro's keys that delete, clear, open a reset menu, or can't be named"""
    out, seen = [], set()
    for s in m["steps"]:
        k = s["key"]
        if k in seen:
            continue
        if k in RISKY[slug]:
            out.append((k, RISKY[slug][k]))
            seen.add(k)
        elif k.startswith("#"):
            out.append((k, "a raw key code (%s): what it does can't be told" % k[1:]))
            seen.add(k)
    return out


def needs_warning(slug, m):
    """The risky keys the user hasn't said yes to for this macro yet: [(key, why)]"""
    ok = set(m.get("ok_risky", []))
    return [(k, w) for k, w in risky_keys(slug, m) if k not in ok]


def accept_risky(slug, m):
    m["ok_risky"] = sorted(k for k, _w in risky_keys(slug, m))


def total_ms(m):
    return sum(s["wait_ms"] for s in m["steps"])


def describe(slug, m, most=10):
    """'2nd QUIT, MODE, wait 2 s, 2nd QUIT'"""
    parts = []
    for s in m["steps"][:most]:
        parts.append(label_of(slug, s["key"]))
        if s["wait_ms"]:
            parts.append("wait %s" % seconds(s["wait_ms"]))
    if len(m["steps"]) > most:
        parts.append("... (%d keys)" % len(m["steps"]))
    return ", ".join(parts) or "no keys"


def seconds(ms):
    return ("%.1f s" % (ms / 1000.0)).replace(".0 s", " s")


# ---- Files ----

def store_path(slug, folder=None):
    if folder is None:
        import paths
        folder = paths.user_path("macros")
    return os.path.join(folder, "%s.json" % slug)


def to_json(slug, macros):
    """The file's text: the user's macros (with their pins and hotkeys), and the pins and
    hotkeys given to built-in ones ("builtin_prefs", by name; the built-ins themselves aren't
    written)"""
    prefs = {}
    for m in macros:
        if m.get("builtin") and (m.get("pinned") or m.get("hotkey")):
            prefs[m["name"]] = {k: m[k] for k in ("pinned", "hotkey") if m.get(k)}
    d = {"format": FORMAT, "format_version": FORMAT_VERSION, "model": slug,
         "macros": [{k: v for k, v in m.items() if k not in ("builtin", "model", "go")}
                    for m in macros if not m.get("builtin")]}
    if prefs:
        d["builtin_prefs"] = prefs
    return json.dumps(d, indent=1, ensure_ascii=False)


def prefs_from_json(text):
    """The built-in macros' pins and hotkeys in a macros file's text ({} when none)"""
    try:
        d = json.loads(text)
    except ValueError:
        return {}
    p = d.get("builtin_prefs") if isinstance(d, dict) else None
    return {k: v for k, v in p.items() if isinstance(k, str) and isinstance(v, dict)} if isinstance(p, dict) else {}


def from_json(slug, text):
    """A macros file's text -> [macro]. Raises MacroError."""
    try:
        d = json.loads(text)
    except ValueError as e:
        raise MacroError("not a macros file (%s)" % e)
    if not isinstance(d, dict) or d.get("format") != FORMAT:
        raise MacroError("not a CalcSuite macros file")
    if int(d.get("format_version", 0)) > FORMAT_VERSION:
        raise MacroError("made by a newer CalcSuite")
    if d.get("model") != slug:
        raise MacroError("these macros are for the %s, not the %s" % (
            calc_for(d["model"]).title if d.get("model") in SLUGS else d.get("model"), calc_for(slug).title))
    return [validate(slug, m) for m in d.get("macros", [])]


def load(slug, folder=None):
    """The user's macros for a model ([] when there's no file). Raises MacroError when the file
    is there but can't be read (the caller logs it and keeps the file)."""
    path = store_path(slug, folder)
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return from_json(slug, f.read())
    except OSError as e:
        raise MacroError("can't read %s (%s)" % (path, e))


def load_all(slug, folder=None):
    """Every macro for a model: the built-in ones (with the pins and hotkeys saved for them),
    then the user's. Raises MacroError like load()."""
    user = load(slug, folder)
    prefs = {}
    path = store_path(slug, folder)
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                prefs = prefs_from_json(f.read())
        except OSError:
            prefs = {}
    out = builtins(slug, prefs) + user
    seen = set()
    for m in out:  # One macro per hotkey (a file edited by hand): the first keeps it
        h = m.get("hotkey")
        if h in seen:
            m.pop("hotkey", None)
        elif h:
            seen.add(h)
    return out


def save(slug, macros, folder=None):
    """Writes the user's macros (not the built-in ones) safely: a temporary file, then replace"""
    path = store_path(slug, folder)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(to_json(slug, macros))
    os.replace(tmp, path)
    return path


def merge(existing, incoming):
    """incoming macros added after existing ones, names made unique: (all, added)"""
    out = list(existing)
    added = []
    for m in incoming:
        m = dict(m)
        m["name"] = unique_name(m["name"], [x["name"] for x in out])
        if m.get("hotkey") and by_hotkey(out, m["hotkey"]) is not None:
            m.pop("hotkey")  # Its hotkey is taken here: the one you have keeps it
        out.append(m)
        added.append(m)
    return out, added


# ---- Recording ----

class Recorder(object):
    """Turns the key commands a tab queues into steps. tap(line) from any thread."""

    def __init__(self, slug, keep_pauses=False, clock=time.time):
        self.slug, self.keep_pauses, self.clock = slug, keep_pauses, clock
        self.steps = []
        self.last = None
        self.lock = threading.Lock()
        self.full = False

    def tap(self, line):
        if not line.startswith(("key ", "keys ")):
            return
        codes = []
        for word in line.split()[1:]:
            try:
                codes.append(int(word, 16))
            except ValueError:
                return  # Not a key line we know
        now = self.clock()
        with self.lock:
            if self.last is not None and self.keep_pauses and self.steps:
                gap = int(round((now - self.last) * 1000))
                if gap >= PAUSE_MIN_MS:
                    self.steps[-1]["wait_ms"] = min(WAIT_MAX_MS, int(round(gap / 100.0)) * 100)
            self.last = now
            for c in codes:
                if len(self.steps) >= STEPS_MAX:
                    self.full = True
                    break
                self.steps.append({"key": name_for(self.slug, c), "wait_ms": 0})

    def count(self):
        with self.lock:
            return len(self.steps)

    def result(self):
        with self.lock:
            return [dict(s) for s in self.steps]


# ---- Playing ----

def plan(slug, steps):
    """Steps -> [("keys", [codes]) | ("wait", ms)]: keys with no wait between them together, in
    runs of at most CHUNK. Raises MacroError for a key the model doesn't have."""
    out, run = [], []
    for s in steps:
        code = code_of(slug, s["key"])
        if code is None:
            raise MacroError("the %s has no key %r" % (calc_for(slug).title, s["key"]))
        run.append(code)
        if len(run) >= CHUNK:
            out.append(("keys", run))
            run = []
        if s.get("wait_ms"):
            if run:
                out.append(("keys", run))
                run = []
            out.append(("wait", int(s["wait_ms"])))
    if run:
        out.append(("keys", run))
    while out and out[-1][0] == "wait":  # A wait after the last key does nothing
        out.pop()
    return out


class Player(object):
    """Plays a plan. send(codes, done) queues one "keys" command and calls done(ok) once the
    calculator has taken it (the link thread). sleep(s) waits (stop() wakes it)."""

    ANSWER_S = 60  # A "keys" command not answered by then: the link is stuck, stop

    def __init__(self, segments, send, on_end=lambda ok, why: None, sleep=None):
        self.segments, self.send, self.on_end = segments, send, on_end
        self.stopped = threading.Event()
        self._sleep = sleep
        self.sent = 0  # "keys" commands sent so far

    def stop(self):
        self.stopped.set()

    def sleep(self, s):
        if self._sleep is not None:
            self._sleep(s)
        else:
            self.stopped.wait(s)

    def run(self):
        """Plays it all (on a worker thread): on_end(True, None), or on_end(False, why)"""
        pending = None
        try:
            for kind, value in self.segments:
                if self.stopped.is_set():
                    return self.on_end(False, "stopped")
                if kind == "keys":
                    pending = self._send(value)
                    if pending is False:
                        return self.on_end(False, "the calculator didn't take the keys")
                else:
                    if pending is not None and not self._wait(pending):
                        return self.on_end(False, "no answer from the calculator")
                    pending = None
                    self.sleep(value / 1000.0)
            if pending is not None and not self._wait(pending):
                return self.on_end(False, "no answer from the calculator")
            return self.on_end(True, None)
        except Exception as e:  # Never leaves a replay half-way without saying so
            return self.on_end(False, str(e) or e.__class__.__name__)

    def _send(self, codes):
        box = {"ev": threading.Event(), "ok": None}

        def done(ok):
            box["ok"] = ok
            box["ev"].set()
        if not self.send(codes, done):
            return False
        self.sent += 1
        return box

    def _wait(self, box):
        t0 = time.time()
        while not box["ev"].wait(0.05):
            if self.stopped.is_set() or time.time() - t0 > self.ANSWER_S:
                return False
        return bool(box["ok"])
