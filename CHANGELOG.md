# Changelog

What changed in the kit, newest first. Tested on a TI-Nspire CX II CAS, OS 6.40, Windows 11.

## [Unreleased]

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
