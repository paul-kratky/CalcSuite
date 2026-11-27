"""Where CalcSuite keeps what it makes and downloads.

The released app is a folder from a zip (CalcSuite-<version>-win64.zip): everything it saves
stays in that folder, beside CalcSuite.exe, so moving or deleting the folder moves or deletes
everything:

    CalcSuite\\
      CalcSuite.exe, _internal\\ (the app), Guides\\ (the PDFs)
      CalcSuite files\\          what you make: captures (screenshots, recordings, GIFs),
                                 programs (written in the editor, built, sent), backups, ROMs,
                                 downloaded programs, files from the calculators
      CalcSuite files\\cache\\   what CalcSuite downloads for itself: ffmpeg, the emulators,
                                 the program library's downloads, TI's OS versions

Run from the source tree (python tools/mirror.py), it keeps to the old places: Documents\\CalcSuite
and %LOCALAPPDATA%\\CalcSuite. A folder CalcSuite can't write to (unzipped into Program Files, or
run from inside the zip without unzipping) falls back to those too; inside_zip() tells the window
to say "unzip first".

MIT licence (like the rest of the app).
"""

import os
import sys
import tempfile

FOLDER_NAME = "CalcSuite files"


def frozen():
    return bool(getattr(sys, "frozen", False))


def app_dir():
    """The folder CalcSuite.exe is in (the packaged app), else the source tree's root"""
    if frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def inside_zip():
    """Opened by double-clicking the exe inside the zip: Windows unpacked it into a temporary
    folder that goes away (and Defender eyes programs started from there)"""
    if not frozen():
        return False
    here = os.path.normcase(app_dir())
    tmp = os.path.normcase(os.path.abspath(tempfile.gettempdir()))
    if not here.startswith(tmp + os.sep):
        return False
    # The folders zip tools unpack into when an exe is opened without extracting: Explorer's
    # Temp1_<name>.zip, 7-Zip's 7zO..., WinRAR's Rar$EX... (a folder unzipped into Temp is fine)
    import re
    return any(re.match(r"^(temp\d+_.*\.zip|7zo|rar\$)", part)
               for part in here[len(tmp) + 1:].split(os.sep))


def _writable(folder):
    try:
        os.makedirs(folder, exist_ok=True)
        probe = os.path.join(folder, ".write-test")
        with open(probe, "w") as fh:
            fh.write("ok")
        os.remove(probe)
        return True
    except OSError:
        return False


_files = None


def files_dir():
    """What the user makes (captures, programs, backups...): beside the exe when it can be"""
    global _files
    if _files is None:
        portable = os.path.join(app_dir(), FOLDER_NAME)
        if frozen() and not inside_zip() and _writable(portable):
            _files = portable
        else:
            _files = os.path.join(os.path.expanduser("~"), "Documents", "CalcSuite")
    return _files


def cache_dir(*parts):
    """What CalcSuite downloads for itself (made when missing)"""
    if is_portable():
        base = os.path.join(files_dir(), "cache")
    else:
        base = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "CalcSuite")
    path = os.path.join(base, *parts)
    os.makedirs(path, exist_ok=True)
    return path


def is_portable():
    return files_dir() == os.path.join(app_dir(), FOLDER_NAME)


def user_path(*parts):
    """A folder inside files_dir() (made when missing)"""
    path = os.path.join(files_dir(), *parts)
    os.makedirs(path, exist_ok=True)
    return path


def shown(path):
    """A path as the window shows it: relative to the CalcSuite folder when it's inside it"""
    try:
        rel = os.path.relpath(path, os.path.dirname(app_dir()))
    except ValueError:
        return path
    return rel if is_portable() and not rel.startswith("..") else path
