"""Get programs: the curated list in tools/program_library.json, and fetching an item.

    items = for_calc(load(), "ti84")          # verified first, then by name
    path = download(item["download_url"], progress)   # cached in %LOCALAPPDATA%\\CalcSuite\\library
    files = pick_files(path, item)            # [(name in the archive, bytes, folder or None)]

Downloads happen only when the user clicks (never a prefetch, never a crawl), with an honest
User-Agent, from ticalc.org and GitHub only. Cemetech and TI-Planet items open their page in
the browser; TI's own apps open TI's page (TI's licence click-through): CalcSuite never
downloads TI files. Why: docs/dev/program_library_research.md, section 5.

Pure except download() (the network) and the cache folder.
"""

import fnmatch
import hashlib
import io
import json
import os
import sys
import urllib.parse
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
LIBRARY_JSON = os.path.join(HERE, "program_library.json")
USER_AGENT = "CalcSuite/1.0 (+https://github.com/paul-kratky/CalcSuite)"
sys.path.insert(0, HERE)
import paths  # noqa: E402

CACHE = paths.cache_dir("library")
ALLOWED_HOSTS = ("ticalc.org", "github.com", "githubusercontent.com")
MAX_DOWNLOAD = 16 * 1024 * 1024
# What each calculator takes from an archive (anything else: read-mes, sources, pictures)
EXTS = {"ti84": (".8xp", ".8xv", ".8xg", ".8xl", ".8xm", ".8xs", ".8xn", ".8xy", ".8xi",
                 ".8ci", ".8ca"),
        "ti89": (".89p", ".89f", ".89g", ".89e", ".89m", ".89s", ".89t", ".89l", ".89c", ".89x",
                 ".89i", ".89a", ".89d", ".89y", ".89z"),
        "nspire": (".tns",)}


def load(path=LIBRARY_JSON):
    for p in (path, os.path.join(getattr(sys, "_MEIPASS", HERE), "program_library.json")):
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as f:
                return json.load(f)["items"]
    return []


def for_calc(items, slug):
    """The selected calculator's items: verified ones first, then by name"""
    mine = [i for i in items if i.get("calculator") == slug]
    return sorted(mine, key=lambda i: (not i.get("verified"), i.get("official", False),
                                       i.get("name", "").lower()))


def os_tuple(text):
    parts = []
    for p in (text or "").split("."):
        if not p.isdigit():
            break
        parts.append(int(p))
    return tuple(parts) or None


def needs_old_os(item, slug, os_version):
    """For the 84: an ASM/C item on OS 5.5 or later (needs arTIfiCE). Returns (flag, note):
    flag is True when the connected 84 can't run it as is, None when its OS is unknown."""
    if slug != "ti84" or not item.get("needs_asm"):
        return False, ""
    have = os_tuple(os_version)
    if have is None:
        return None, "needs OS 5.4 or older (ASM)"
    if have >= (5, 5):
        return True, "needs OS 5.4 or older: this calculator has OS %s (ASM needs arTIfiCE)" % os_version
    return False, "needs OS 5.4 or older: yours has %s, fine" % os_version


def host_ok(url):
    host = (urllib.parse.urlparse(url or "").hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in ALLOWED_HOSTS)


def cache_path(url, cache=CACHE):
    name = os.path.basename(urllib.parse.urlparse(url).path) or "download"
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
    return os.path.join(cache, "%s-%s" % (digest, name))


def download(url, progress=None, cache=CACHE, timeout=30):
    """The file at url, from the cache or downloaded once (only ticalc.org and GitHub).
    progress(done, total). Raises OSError / ValueError."""
    if not host_ok(url):
        raise ValueError("CalcSuite only downloads from ticalc.org and GitHub")
    path = cache_path(url, cache)
    if os.path.isfile(path) and os.path.getsize(path) > 0:
        return path
    os.makedirs(cache, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    part = path + ".part"
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r, open(part, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            done = 0
            while True:
                chunk = r.read(1 << 15)
                if not chunk:
                    break
                done += len(chunk)
                if done > MAX_DOWNLOAD:
                    raise ValueError("the download is bigger than %d MB" % (MAX_DOWNLOAD >> 20))
                f.write(chunk)
                if progress:
                    progress(done, total)
        os.replace(part, path)
    finally:
        if os.path.exists(part):
            try:
                os.remove(part)
            except OSError:
                pass
    return path


def _matches(member, pattern):
    """The pattern against the member's path or any tail of it ("dir/*.89?" also matches
    "top/dir/x.89p": archives often wrap everything in one more folder)"""
    parts = member.replace("\\", "/").lower().split("/")
    return any(fnmatch.fnmatch("/".join(parts[k:]), pattern) for k in range(len(parts)))


def pick_files(data_or_path, item, file_name=None):
    """The files to send from a download: [(file name, bytes, folder or None)]. An archive
    gives the members that match the item's 'send' patterns (each member once, the first
    pattern that matches decides its folder), only with this calculator's extensions; a
    plain file is itself."""
    if isinstance(data_or_path, str):
        with open(data_or_path, "rb") as f:
            data = f.read()
        file_name = file_name or data_or_path
    else:
        data = data_or_path
    slug = item.get("calculator")
    exts = EXTS.get(slug, ())
    patterns = item.get("send") or [["*", None]]
    if data[:2] != b"PK":
        base = os.path.basename(file_name or "download")
        base = base.split("-", 1)[1] if "-" in base and len(base.split("-", 1)[0]) == 12 else base
        if not base.lower().endswith(exts):
            raise ValueError("%s isn't a %s file" % (base, slug))
        folder = next((d for p, d in patterns if _matches(base, p)), patterns[0][1])
        return [(base, data, folder)]
    out = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for info in z.infolist():
            name = info.filename
            if info.is_dir() or "__macosx" in name.lower() or not name.lower().endswith(exts):
                continue
            for pattern, folder in patterns:
                if _matches(name, pattern):
                    out.append((os.path.basename(name), z.read(info), folder))
                    break
    if not out:
        raise ValueError("nothing in the download matches what this item sends")
    return out


def action_text(item):
    return {"download": "Download and send", "page": "Open page",
            "ti_page": "Open TI's page"}.get(item.get("action"), "Open page")


# ---- Get all: every item CalcSuite can send by itself (pure; the self-test checks it) ----

LARGE = 500 * 1024   # A set's item this big (on the calculator) gets a note


def get_all_plan(items, slug):
    """(sendable, skipped) for the calculator: sendable are its items CalcSuite downloads by
    itself, in the list's order; skipped is [(item, reason)] for the rest (TI's own apps, and
    items that open a page: apps, installs with steps on the calculator)."""
    sendable, skipped = [], []
    for i in for_calc(items, slug):
        act = i.get("action")
        if act == "ti_page":
            skipped.append((i, "TI's own app: download it from TI's page (its licence)"))
        elif act != "download":
            skipped.append((i, "opens its page: an app, or an install with steps on the calculator"))
        elif not host_ok(i.get("download_url")):
            skipped.append((i, "not on ticalc.org or GitHub"))
        else:
            sendable.append(i)
    return sendable, skipped


def size_hint(item):
    """The bytes the item puts on the calculator when the list says so ("2,969 B program",
    "23,532 B .tns"), else None (a zip's size says little: download it to know)"""
    import re
    m = re.search(r"([\d,]+)\s*B\s+(?:program|\.tns)", item.get("size") or "")
    return int(m.group(1).replace(",", "")) if m else None


def file_place(data, slug):
    """Where a file's variables go: ("ram" | "archive" | "storage", bytes). A TI file says in
    its header whether it's archived; the Nspire has one storage."""
    if slug == "nspire":
        return "storage", len(data)
    import calc_files as cf
    try:
        entries = cf.read_ti8x(data) if slug == "ti84" else cf.read_ti89(data)
    except ValueError:
        return "ram", len(data)
    return ("archive" if all(e[3] for e in entries) else "ram"), len(data)


def item_flags(item, slug, os_version, size=None, ids=()):
    """Short notes for an item of the Get all list: [(level, text)], level "warn" or "note".
    ids: the ids of the set's items (a dependency that's in the set is fine)."""
    out = []
    flag, _note = needs_old_os(item, slug, os_version)
    if flag:
        out.append(("warn", "ASM: needs arTIfiCE on OS %s" % os_version))
    elif flag is None:
        out.append(("note", "ASM: needs OS 5.4 or older, or arTIfiCE"))
    for d in item.get("dependencies") or []:
        dep = d.split(" ")[0]
        out.append(("note", "uses %s (in this set)" % dep) if dep in ids else ("warn", "needs %s" % d))
    sh = item.get("special_handling") or ""
    low = sh.lower()
    if any((folder or "").strip("/").lower() == "mylib" for _p, folder in item.get("send") or []):
        out.append(("note", "library: Refresh Libraries afterwards"))
    if "install()" in sh:
        out.append(("note", "run install() on the 89 afterwards"))
    if "runs it once" in low or "run it once" in low:
        out.append(("note", "run it once on the calculator to install"))
    if size is not None and size >= LARGE or size is None and (
            "large" in low or "check memory" in low or "free ram" in low):
        out.append(("warn", "large: check the free space"))
    return out


def fit_check(ram, archive, info, slug):
    """Whether the set fits: (ok, text). ram/archive: the bytes going to each (the Nspire's
    storage counts as archive). info: the mirror's info (ram_free, storage_free). ok is None
    when it's not known, or when it fits only if some goes to the archive by hand."""
    def num(k):
        v = str((info or {}).get(k, ""))
        return int(v) if v.isdigit() else None
    store = num("storage_free")
    total = ram + archive
    if slug == "nspire":
        if store is None:
            return None, "%s in all; the handheld's free space isn't known" % _h(total)
        return total <= store, "%s in all, %s free on the handheld" % (_h(total), _h(store))
    free_ram = num("ram_free")
    if store is None and free_ram is None:
        return None, "%s in all (RAM %s, archive %s); the free space isn't known" % (
            _h(total), _h(ram), _h(archive))
    ok = (free_ram is None or ram <= free_ram) and (store is None or archive <= store)
    text = "%s in all: to RAM %s (%s free), to the archive %s (%s free)" % (
        _h(total), _h(ram), _h(free_ram) if free_ram is not None else "?", _h(archive),
        _h(store) if store is not None else "?")
    if not ok and free_ram is not None and store is not None and total <= free_ram + store:
        ok = None
        text += ". More than the free RAM: archive some as they arrive, or send fewer"
    return ok, text


def _h(n):
    if n < 1024:
        return "%d B" % n
    if n < 1024 * 1024:
        return "%.1f KB" % (n / 1024.0)
    return "%.2f MB" % (n / 1048576.0)


def nspire_clashes(files, listing):
    """The names of files ([(name, folder)]) already on the handheld. listing:
    {folder: set of lower-case names in it}"""
    return [name for name, folder in files if name.lower() in listing.get(folder or "/", set())]


def save_dir_name(item):
    """A folder name on the PC for an item (its name, safe on Windows)"""
    import re
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", item.get("name") or "").strip(" .")
    return name[:80] or item.get("id") or "item"


def default_save_folder():
    return os.path.join(paths.files_dir(), "library")


def fetch_files(item, progress=None, cache=CACHE):
    """Downloads (or takes from the cache) and picks the item's files: [(name, bytes, folder)].
    Falls back on alt_download_url when it's on ticalc.org / GitHub. Raises like download()."""
    try:
        return pick_files(download(item["download_url"], progress, cache), item)
    except Exception:
        alt = item.get("alt_download_url")
        if not alt or not host_ok(alt):
            raise
        return pick_files(download(alt, progress, cache), item)


def cached_files(item, cache=CACHE):
    """The item's files when its download is in the cache already, else None (no network)"""
    for url in (item.get("download_url"), item.get("alt_download_url")):
        if url and host_ok(url):
            p = cache_path(url, cache)
            if os.path.isfile(p) and os.path.getsize(p) > 0:
                try:
                    return pick_files(p, item)
                except (OSError, ValueError, zipfile.BadZipFile):
                    return None
    return None
