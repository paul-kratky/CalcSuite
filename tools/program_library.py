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
CACHE = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "CalcSuite", "library")
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
    m = member.replace("\\", "/").lower()
    return fnmatch.fnmatch(m, pattern) or fnmatch.fnmatch(m.rsplit("/", 1)[-1], pattern)


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
