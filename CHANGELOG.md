# Changelog

What changed in the kit, newest first. Tested on a TI-Nspire CX II CAS, OS 6.40, Windows 11.

## [Unreleased]

### Added
- **TI-84 Plus CE in the mirror app:** its own window with the live screen (about 1 frame a
  second: the calculator sends 150 KB a picture over full-speed USB), the PC keyboard as its
  keys (F1-F5 are Y= WINDOW ZOOM TRACE GRAPH, F6 MODE, F7 MATH, F8 APPS, F9 PRGM, F10 VARS,
  F11 STAT, F12 QUIT, Esc CLEAR), screenshots and recordings. It needs the WinUSB driver once
  (README, with Zadig). Tested on a TI-84 Plus CE: screenshot, typing `1+2` Enter.
- **`ti84-cli`:** our own small link for TI's DUSB protocol on libusb (info, shot, key, serve).
- **TI-89 Titanium in the mirror app:** its own window with the
  160 x 100 screen shown x4, the PC keyboard as its keys (F1-F8 its F1-F8, Home HOME, Esc ESC,
  F9 APPS, F10 MODE, F11 CATALOG, F12 CLEAR), screenshots and recordings. `ti84-cli` speaks to
  it too (`--model 89t`; its copy `ti89-cli.exe` picks the 89 by itself), and `ti84-cli
  devices` lists the TI calculators on USB. Likely needs WinUSB once with Zadig (USB ID
  `0451 E004`). Tested on a TI-89 Titanium, OS 3.10: info, screenshot (0.06 s, so the window
  runs fast), typing `1+2` Enter. Needs WinUSB once with Zadig, like the 84 Plus CE.
- **Record:** a button in each window. Saves a GIF (built in), and an MP4 too when ffmpeg is
  installed. Up to 3 minutes; a still screen costs nothing.
- **One window per calculator,** opened when it is plugged in, several at once. Tested with a
  TI-Nspire CX II and a TI-84 Plus CE open together.
- **Copy and paste:** Ctrl+V types the PC clipboard's text into the calculator (new lines are
  Enter, up to 4000 characters); Ctrl+C puts the calculator's screen on the PC clipboard as a
  picture. On the Nspire, Ctrl+Shift+C / Ctrl+Shift+V are the handheld's own copy and paste.
- **Files on the calculator:** a **Files...** button in each window. The live screen keeps
  running while it works; long transfers show their progress in the status line.
  - TI-Nspire: browse the folders (with sizes), download files to the PC (to `from-calc`, or a
    folder you pick), upload a `.py` (checked and converted) or `.tns`, new folder, rename,
    delete (with a question first). Tested on a TI-Nspire CX II CAS, OS 6.40: all of it, and
    a 300 KB file there and back byte for byte (0.9 s down).
  - TI-89 Titanium: its variables by folder and its apps; download as TI files (`.89e`,
    `.89m`, ...); texts, strings and programs not yet run shown as text; upload TI files or
    TI-Basic text; delete. Tested on a TI-89 Titanium, OS 3.10: the list, six downloads, an
    upload over a program of the same name (after the question), its text, a delete.
  - TI-84 Plus CE: its variables, programs and apps (size, RAM or Archive); download as TI
    files (`.8xp`, `.8xv`, ...) with TI's header and checksum; TI-Basic programs shown as
    text; upload TI files or TI-Basic text; delete. Tested on a TI-84 Plus CE, OS 5.4.0:
    an upload of a `.8xp` over a program of the same name (after the question), its text, a
    delete.
- **About this calculator:** model, OS, free memory, and whether TI has a newer OS (read from
  TI's download page at most once a day, never blocking the window; "couldn't check" with
  the link when the page can't be read). It never downloads an OS.
- **`nspire-cli`:** `get`, `rm` and `mv` (download with progress, delete, rename or move).
  **`ti84-cli`:** `ls`, `get`, `send FILE`, `put`, `rm` (the variables of the 84 family and
  the 89; `put` on the 84 only).
- **App icon** on every window and in the taskbar.
- **Send program to the TI-84 Plus CE and the TI-89 Titanium:** the **Send program...** button
  in their windows (and **Upload** in **Files...**) takes TI-Basic typed on the PC (`.txt`,
  `.tib`, `.bas`) or a ready TI file (`.8xp`, `.8xv`, `.8xl`, ... / `.89p`, `.89e`, ...). It
  reads the calculator's list first and asks before replacing anything; a text file whose name
  can't be the program's asks for a name. Progress shows in the status line.
  - TI-84 Plus CE: the text is turned into the calculator's tokens on the PC (`.8xp` with TI's
    header and checksum), with the PC spellings (`->`, `<=`, `>=`, `!=`, `sqrt(`, `pi`,
    `theta`, `^2`, `^-1`, `L1`, `Y1`, `E` in a number for the EE key, `-` as the negative sign
    where a number starts) or the calculator's own symbols. Checked by a round trip through
    the viewer's detokenizer (self-test).
  - TI-89 Titanium: the text goes over the way the 89's own Program Editor keeps a program
    (read back from a real one), and the 89 tokenizes it when it first runs; `Func` /
    `EndFunc` makes a function.
  - Tested on a TI-84 Plus CE, OS 5.4.0 and a TI-89 Titanium, OS 3.10: test programs sent
    from text (from the window, from Files... and from `tools/send_ti.py`) and as TI files,
    run on the calculator from the mirror's keys with the right output (loops, If/Then/Else,
    negatives, EE, `->`, `<=`, `!=`, `sqrt(`, `pi`, a 1.5 KB program in several packets, an
    89 program of odd size, which takes a different packet size), replaced, deleted; a file
    for the other calculator is refused with its name.
- **`tools/send_ti.py`:** the same from the command line: `python -I tools/send_ti.py --calc
  84|89 FILE [--name NAME] [--replace] [--out FILE]`. It stops when a variable of that name is
  on the calculator (unless `--replace`) and reads the list again afterwards to check the
  program arrived.

- **MP4 without installing ffmpeg:** the first time you press Record without ffmpeg, the app offers to download it (about 39 MB, once, from PyPI's imageio-ffmpeg, checked against its SHA-256) into `%LOCALAPPDATA%\CalcSuite\ffmpeg`. Without it you still get the GIF. MP4s use H.264, or ffmpeg's own MPEG-4 when a build has no H.264.

### Faster
- **Typing:** while you type, keys go out the moment they're pressed and the next screenshot
  waits until you pause (0.15 s on the Nspire, 0.6 s on the 84/89), instead of keys waiting
  behind a picture (up to 1.4 s on the 84 Plus CE).
- **TI-84 Plus CE keys** about twice as fast (4 keys: 0.69 s before, 0.37 s now): no more
  sleeping on the calculator's "wait" reply, the next read already waits for the answer.
- **Nspire frames:** about 19 a second (was about 10). The window looking for calculators no
  longer opens them every 3 s (it reads the USB descriptors only), which took the handheld
  from the mirror for a moment each time.

### Fixed
- **TI-89 Titanium arrow keys:** they had the TI-92 Plus's codes, so up moved left and down
  moved right; now the 89's own (up 337, left 338, down 340, right 344). Tested on a TI-89
  Titanium, OS 3.10.
- The TI-84 Plus CE's OS version read as `0.5.4.0`; now `5.4.0`.
- The Nspire's name was cut at the first space ("Connected: TI-Nspire" for a TI-Nspire CX II
  CAS).

## [0.2.0] - 2026-11-26

### Added
- **Nspire Mirror, an app:** the handheld's screen live in a window (about 9 frames a second),
  with no terminal. `Nspire Mirror.exe` is one file that needs no Python; `Nspire Mirror.bat`
  runs the same window from the source.
  - **Keyboard:** letters, digits, symbols, Enter, Esc, Tab, Backspace and the arrows go to the
    handheld. Ctrl+letter is the handheld's ctrl+letter. F1 Home, F2 Menu, F3 Doc, F4 Catalog,
    F5 Var.
  - **Mouse:** the wheel is up/down (Shift+wheel left/right), a click is the centre click key,
    a double click Enter, a right click the context menu, a middle click Menu. A click on the
    X closes the document, on the page arrow or tabs changes page.
  - **Send program:** pick a `.py` (checked and converted first) or a `.tns`.
  - **Screenshot:** a PNG in `captures/` (the app: `Documents\Nspire Mirror\captures`).
  - It connects by itself when the handheld is plugged in, and again after the cable was out.
  - One window at a time: a second copy says so and closes (two would take the handheld
    from each other and both go black).
- **`tools/screenshot.py`:** the handheld's screen as a PNG (`--scale 3` to enlarge).
- **`nspire-cli`:** `shot FILE.ppm`, `key HEX`, `keys HEX HEX ...`, and `serve` (one connection,
  commands on stdin), which the mirror and the sender use.
- **`tools/nspire_link.py`:** a Python wrapper for one kept-open connection, and a PNG writer
  with no dependencies.
- **`QUICKSTART.md`:** one page from writing a program to running it, without AI.
- **`programs/numint.py`:** trapezoid, Simpson and a reference value for an integral.

### Fixed
- **Sending worked once per plug-in, then timed out.** The CX II does its address handshake
  once after it is plugged in and is silent after that, so every later connection waited for a
  handshake that never came (up to 10 minutes inside libnspire). Reported earlier as "USB send
  times out on OS 6.40"; the OS wasn't the cause. Our copy of libnspire's `cx2.cpp`
  (`tools/nspire_cli/cx2_resume.cpp`) now asks the handheld to start the handshake again, and a
  connection takes about 1.2 s every time, with no replugging.
- **`flash.py` / `send_to_calc.py` do every step on one connection** (info, folder, upload,
  read-back), which is also faster.

### Known limits
- **The mouse can't place the handheld's pointer.** The key service has no known message for
  it, so clicks are keys and a few screen spots are shortcuts.
- **Typed characters show after about 0.15-0.3 s:** the window sees them on the next
  screenshot.
- **Key codes** come from early Nspire models (TILP's list). The common ones work on a CX II
  on OS 6.40; some special keys may not.
- **Python on the handheld can't use the CAS.** Exact answers need TI-Basic, which the kit
  doesn't send yet.
- Windows only for the USB tools.

## [0.1.0] - 2026-11-26

First public release.

- `tools/check_nspire.py`: checks a program against what TI's Python can run.
- `tools/run_on_pc.py`: runs it on the PC with stand-ins for the `ti_*` modules.
- `tools/py2tns.py`: converts `.py` to a `.tns` document (Luna).
- `tools/flash.py` / `tools/send_to_calc.py`: check, convert and send over USB (libnspire).
- Example programs: `quadratic`, `draw_demo`, `probe`, `critpts`.
