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
    `.89m`, ...); texts and strings shown as text. Tested on a TI-89 Titanium, OS 3.10: the
    list and six downloads.
  - TI-84 Plus CE: its variables, programs and apps (size, RAM or Archive); download as TI
    files (`.8xp`, `.8xv`, ...) with TI's header and checksum; TI-Basic programs shown as
    text; upload TI files; delete. Not yet tried on a TI-84 Plus CE.
- **About this calculator:** model, OS, free memory, and whether TI has a newer OS (read from
  TI's download page at most once a day, never blocking the window; "couldn't check" with
  the link when the page can't be read). It never downloads an OS.
- **`nspire-cli`:** `get`, `rm` and `mv` (download with progress, delete, rename or move).
  **`ti84-cli`:** `ls`, `get`, `put`, `rm` (the variables of the 84 family and the 89; `put`
  and `rm` on the 84 only).
- **App icon** on every window and in the taskbar.

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
- The TI-84 Plus CE's OS version read as `0.5.4.0`; now `5.4.0`.
- The Nspire's name was cut at the first space ("Connected: TI-Nspire" for a TI-Nspire CX II
  CAS).

### Not built yet
- Sending programs to the TI-84 Plus CE as TI-Basic text (TI files go with Files... > Upload).
- Sending programs to the TI-89 Titanium.

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
