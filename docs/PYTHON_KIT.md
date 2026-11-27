# Writing Python programs for the TI-Nspire CX II

The other half of CalcSuite: write a Python program on the PC (yourself, or with an AI
assistant), check that the calculator's Python can run it, try it on the PC, and send it to the
handheld over USB, with no TI software. Doing it by hand, without AI: [QUICKSTART.md](../QUICKSTART.md).

## Get the source

1. `git clone --recursive https://github.com/paul-kratky/CalcSuite` (or download the ZIP).
2. Get the tools: download the tools zip from the
   [latest release](https://github.com/paul-kratky/CalcSuite/releases/latest) and unzip it into
   `tools/bin/` (`luna.exe`, `nspire-cli.exe`, `ti84-cli.exe`, `libusb-1.0.dll`). To build them
   yourself instead, see `third_party/README.md` and run `python tools/build_tools.py`.
3. Python 3.8+ on the PC. Nothing to install with pip. The app from the source:
   double-click `Nspire Mirror.bat`.

You ask an AI assistant (Claude Code) for a program. It writes `programs/<name>.py`, a
checker makes sure the calculator's Python can run it, you can try it on the PC, and then
it goes to the handheld. With the calculator plugged in, say **"send it"**: Claude Code
runs `tools/flash.py`, which checks the program, turns it into a `.tns` document and
uploads it over USB in one step, with no TI software (section 3).

```text
CalcSuite/
  CLAUDE.md                 rules the AI follows when writing programs here
  programs/                 your programs (examples + probe.py)
    quadratic.py            quadratic solver: input() + cmath, real and complex roots
    draw_demo.py            ti_draw demo: axes, sine wave, sun, waits for a key
    probe.py                run ON THE HANDHELD once: reports what your OS supports
  tools/
    check_nspire.py         the checker (run before every transfer)
    run_on_pc.py            runs a program on the PC with the stub modules
    flash.py                one step: check -> .tns -> send over USB (--dry-run: no send)
    py2tns.py               .py -> .tns (uses Luna), and --verify for a .tns
    send_to_calc.py         --list the handheld, upload a .tns, --ls its folders
    build_tools.py          rebuilds tools/bin/ from third_party/ (normally not needed)
    bin/                    luna.exe, nspire-cli.exe, libusb-1.0.dll (built here)
    nspire_cli/             source of nspire-cli.exe (our small libnspire front end)
    ti_shim/                stub ti_system / ti_draw / ti_plotlib / ti_image
    selftest/               bad_sample.py + run_selftest.py (tests the kit itself)
  third_party/              Luna, libnspire, libusb: sources, versions, licences (README)
  build/                    generated .tns files (safe to delete)
```

You need Python 3.8 or newer on the PC (3.11 tested). Nothing has to be installed with pip.
The USB and .tns tools are prebuilt in `tools/bin/` for 64-bit Windows.

## 1. What the calculator's Python is

| | |
| --- | --- |
| Which models | TI-Nspire **CX II**, CX II CAS, CX II-T, CX II-T CAS, CX II-C, CX II-C CAS, plus TI's TI-Nspire CX desktop software. The original **CX / CX CAS (no "II") have no Python**: they are not on TI's list and their OS stops at 4.5.x. |
| OS needed | **OS 5.2 or later** on the handheld. Python arrived with 5.2. The newest OS found is **6.3** (August 2025), which added CoDrone EDU drone support. 6.2 (April 2024) changed the editor and added Vernier Go Direct sensors over the TI Bluetooth adapter. Update to the newest one. |
| Engine | TI's own port of **MicroPython**, a small subset of Python 3. TI does not publish the MicroPython version number; `programs/probe.py` prints what your handheld reports. |
| Built-in modules | `math`, `cmath`, `random`, `time`, plus TI's `ti_system`, `ti_draw`, `ti_plotlib`, `ti_image`, `ti_hub` (TI-Innovator Hub) and `ti_rover` (TI-Innovator Rover). Turtle is a separate download from TI that you install into PyLib. |
| Language | Normal Python 3 syntax for `def`, `class`, `lambda`, `try/except/finally`, `with`, `yield`, `global`/`nonlocal`, list and dict comprehensions, `"{}".format()` and `%` formatting. TI's keyword list has no `async`/`await`. |
| Not there | numpy, sympy, matplotlib, os, re, json, itertools and the rest of the standard library. No file I/O (`open`) and no networking. **f-strings** are not in TI's documentation, and MicroPython only added them in 2021, after TI shipped Python, so treat them as unsupported. The same goes for walrus `:=`, `match`, type hints, `async`, and CPython string extras such as `ljust`/`zfill`. `probe.py` tests f-strings, walrus and `ljust` on your handheld. |
| Memory | The heap is about 2 MB and programs should stay small. Community testers measured about 2.05 to 2.07 MB of heap, and one report puts the editor's limit at about 70 KB per program. The recursion depth is far lower than CPython's 1000, so use loops. |
| Screen | The ti_draw canvas is **318 x 212** pixels. (0,0) is the top left and y grows downward; `get_screen_dim()` returns the size. ti_plotlib uses the same area in math coordinates set by `window()`. |
| Input/output | `print()` writes to the **Python Shell** page. `input("prompt")` asks in the Shell and returns a string. `ti_system.get_key()` reads single keys without waiting, and `get_key(1)` waits for one. To stop a running program, press **[home/on]** on the handheld or **F12** in the Windows software. |
| Sharing data with the CAS | `ti_system.recall_value("a")`, `store_value("a", x)`, `recall_list("L1")`, `store_list("L1", xs)`, and `eval_function("f", x)`, which evaluates a function defined elsewhere in the document (for example in Graphs). This is how a Python program uses CAS results: Python itself cannot do symbolic algebra. |

## 2. Workflow

1. **Ask.** In this folder, run Claude Code and ask, for example: "write a program that
   tabulates compound interest and asks for the rate". It follows `CLAUDE.md` and writes
   `programs/compound_interest.py`.
2. **Check.**
   ```sh
   python -I tools/check_nspire.py programs/compound_interest.py
   ```
   `OK` means no errors. Every ERROR prints a `fix:` line. Warnings are things TI doesn't
   document: fix them, or make sure they work with `probe.py` first. `--strict` makes
   warnings fail as well. `--allow mymod` accepts your own PyLib module. You can pass a
   folder, such as `programs`.
3. **Try it on the PC (optional, logic only).**
   ```sh
   python -I tools/run_on_pc.py programs/quadratic.py
   python -I tools/run_on_pc.py --gui programs/draw_demo.py
   ```
   Options: `--gui` draws in a 318x212 window shown at twice the size. `--quiet` hides the
   call log. `--var a=3`, `--list L1=1,2,3` and `--func f=x**2+1` provide TI variables for
   `recall_value`/`recall_list`/`eval_function`. `--keys up,enter` sets what `get_key()`
   returns, in order; after that it returns `"esc"`. The PC runs full CPython, so passing
   here does not prove the program runs on the calculator. The checker is the real gate.
4. **Send it.** Plug the calculator in, turn it on, and tell Claude Code "send it". Or
   run it yourself:
   ```sh
   python -I tools/flash.py programs/compound_interest.py
   ```
   Section 3 has the details and the manual route.
5. **Run it** on the handheld (section 3.3).

Run `python -I tools/selftest/run_selftest.py` once to check the kit works on your PC.

### What the PC shim stubs (tools/ti_shim/)

| Module | On the PC |
| --- | --- |
| `ti_system` | `recall_value`/`store_value`/`recall_list`/`store_list` use dictionaries you preload with `--var`/`--list`. `eval_function` uses `--func` expressions in `x`, and an undefined name raises a clear error. `get_key()`/`get_key(1)` return the `--keys` queue, then `"esc"`. `get_mouse()` returns (-1,-1), `get_platform()` returns "dt", `get_time_ms()` and `clear_history()` work. |
| `ti_draw` | All 19 documented functions. Each call is logged to stderr. With `--gui` they draw: colours, pen sizes and styles, `set_window`, and buffering, where `paint_buffer` refreshes the window. `get_screen_dim()` returns (318, 212). Text uses a PC font, so its size and position are only roughly the calculator's. |
| `ti_plotlib` | All documented functions (cls, window, auto_window, grid, axes, labels, title, color, pen, plot, scatter, line, lin_reg, text_at, show_plot, use_buffer). `lin_reg` really computes `plt.m`/`plt.a` and `plt.b`. The default window is -10..10, so always call `window()`. |
| `ti_image` | `new_image`, `copy_image`, and `get_pixel`/`set_pixel`/`show_image`/`w`/`h`/`name`. `load_image` can't read images inside a .tns, so it returns a gray 100x100 placeholder. |
| `time` | The real module, plus `ticks_ms`, `ticks_cpu`, `ticks_diff` and `clock` added. |
| `ti_hub`, `ti_rover` | Not stubbed: they need the real hardware. |

## 3. Transfer to the handheld

TI's software does **not** accept a `.py` file directly. Dragging one in gives "Unsupported
file type", and renaming it to `.tns` doesn't work either. The code has to go inside a
TI-Nspire document (`.tns`) as a Python program. This kit does that itself (3.1); TI's
own way is the fallback (3.2).

### 3.1 Automatic: `tools/flash.py` (no TI software)

```sh
python -I tools/flash.py programs/quadratic.py              # check, convert, send
python -I tools/flash.py programs/quadratic.py --dry-run    # check and convert only
python -I tools/flash.py programs/quadratic.py --folder Python   # into My Documents/Python
python -I tools/send_to_calc.py --list                      # which handheld is connected
python -I tools/send_to_calc.py --ls /                      # list My Documents
python -I tools/py2tns.py programs/quadratic.py             # just make build/quadratic.tns
python -I tools/py2tns.py --verify build/quadratic.tns      # check a .tns file
```

What `flash.py` does:

1. **Check:** runs `tools/check_nspire.py`. Any ERROR stops here (`--strict`: warnings
   too; `--allow mymod` for your PyLib modules).
2. **Convert:** `tools/py2tns.py` packs the program into `build/<name>.tns` with
   **Luna** (open source, MPL-1.1; see `third_party/README.md`). The `.tns` holds one
   Python Editor page whose program name is the file name. Line ends are turned into LF
   and a UTF-8 BOM is removed. The `.tns` is then opened again and checked: TI header,
   both document parts present, and the program inside equal to the source byte for byte.
3. **Send:** `tools/send_to_calc.py` talks to the handheld over USB with
   `tools/bin/nspire-cli.exe` (built from **libnspire**, which speaks the CX II's link
   protocol). It shows the handheld's name, OS and free space, warns if the OS is older
   than 5.2, uploads to **My Documents** (an existing file of the same name is replaced),
   reads the file back and compares it. A failed handshake is retried twice.

The handheld must be **on** and on its Home screen (not in Press-to-Test). Close TI's
software and any TI-Nspire CX II Connect tab first: only one program can hold the USB
link at a time.

**The first time** you use it, send `programs/probe.py` and open it on the handheld
(3.3). If it opens in the Python Editor and runs, the whole chain works on your
handheld. The Luna-made `.tns` has been structure-checked on the PC but not yet opened
on a real CX II CAS here, so this first run is the real test. If the document will not
open, use 3.2 and tell Claude Code what the handheld said.

### 3.2 Manual: TI's software

**You need:** TI's **TI-Nspire CX (CAS)** desktop software, version
5.2 or later (the CAS edition matches a CX II CAS), and the USB cable that came with the
calculator.

1. Open the software. Choose **File > New TI-Nspire Document** and pick the TI-Nspire CX II
   **CAS** handheld type if the software asks.
2. **Insert > Add Python > New...** (the menu wording may differ slightly between
   versions; on the handheld it is **doc > Insert > Add Python > New**). Type
   the program name, for example `quadratic`, and choose **Blank Program**.
3. On the PC, open `programs/quadratic.py` in any editor, select everything (Ctrl+A),
   copy it (Ctrl+C), click into the Python Editor page and paste (Ctrl+V). Check that the
   indentation came through as spaces.
4. Press **Ctrl+B** (Run > Check Syntax & Save). If it reports an error, run the checker
   again. You can test straight away with **Ctrl+R**: the output opens in a Shell page.
   ti_draw needs the software's **handheld view**.
5. **File > Save As...** and save it as `quadratic.tns`, the same name as the program.
   Then connect the handheld by USB and copy the file over: drag `quadratic.tns` onto the
   connected handheld in the **Content Explorer**, or use **File > Save to Handheld**.
   TI's free **TI-Nspire CX II Connect** web app (Chrome) can also send a finished `.tns`,
   including the `build/<name>.tns` files that `flash.py --dry-run` makes.

### 3.3 Run it on the handheld

**[home/on] > My Documents** and open `quadratic.tns`, which is wherever you saved it
(the top level of My Documents by default, or the `--folder` you gave). On the Python
Editor page press **menu > Run > Run** (or **ctrl+R**). The program runs in a Python
Shell page. In the Shell, **ctrl+R** reruns it. Press **[home/on]** to stop a running
program. If the document was open on the handheld while you sent a new version, close it
(**doc > File > Close**, don't save) and open it again.

### 3.4 One-time setup: USB driver

**Normally nothing.** A CX II tells Windows to use Microsoft's own generic **WinUSB**
driver, which is what `nspire-cli.exe` (via libusb) needs. On this PC, Windows has
already bound WinUSB to the CX II (checked 2026-11-26 in Device Manager data: service
`WinUSB` for `USB\VID_0451&PID_E022`). Nothing was installed or changed for this kit.

Only if `send_to_calc.py --list` prints `driver=no-winusb-driver` (for example after
installing TI's TI-Nspire desktop software, which can bring its own driver):

1. First try: unplug the handheld, close all TI software, plug it in again.
2. If it still says `no-winusb-driver`, you have to switch the driver by hand. This is
   your call. It needs admin rights, so Claude Code will not do it:
   download **Zadig** from <https://zadig.akeo.ie/>, run it, **Options > List All
   Devices**, pick **TI-Nspire(tm) CX II Handheld** (USB ID `0451 E022`), choose
   **WinUSB** and click **Replace Driver**. Unplug and replug the handheld.
3. **Trade-off:** while WinUSB is bound, TI's desktop software may no longer see the
   handheld. To go back: Device Manager > the TI-Nspire device > **Uninstall device**,
   tick "Attempt to remove the driver for this device", then replug (or reinstall TI's
   software). TI-Nspire CX II Connect in Chrome uses WebUSB, which works through
   WinUSB, so it should keep working either way.

### 3.5 Several programs, libraries

Several programs can live in one `.tns`; add one Python Editor page per program. To
reuse code as a library, put it in its own `.tns`, open it, and choose **menu > Actions >
Install as Python Module**. That moves it into the **PyLib** folder, after which
`from mymod import *` works in any document. Use `--allow mymod` with the checker for
it. (`flash.py` sends one program per `.tns`; to install a module, send it, open it and
use Install as Python Module.)

### 3.6 Rebuilding the tools (normally not needed)

`tools/bin/` already holds the built programs. To rebuild them from `third_party/`,
run `python -I tools/build_tools.py --force`. It needs MSYS2's UCRT64 gcc and zlib
(`C:\msys64\ucrt64`, already on this PC) and writes only to `tools/bin/` and `build/`.

## 4. Troubleshooting

| Problem | Fix |
| --- | --- |
| Checker: non-ASCII character | Usually a curly quote, long dash, `x^2` superscript or pi symbol pasted from the web. Retype it in ASCII (`**2`, `pi`, `<=`). |
| `SyntaxError` on the handheld but the checker passed | Indentation broke during the paste (tabs or a stray space). Reindent with 4 spaces in the TI editor, then Ctrl+B. Also run `probe.py` in case your OS differs, and tell the AI what failed. |
| `ImportError: no module named ...` | You used a module outside the list, or a PyLib module that isn't installed on this handheld. |
| `AttributeError: 'str' object has no attribute 'ljust'` | That's a CPython-only method; the checker warns about the common ones. Pad by hand. |
| `MemoryError` | The list is too big or the recursion too deep. Use smaller lists, a loop, or `use_buffer()` less often. |
| `RuntimeError: maximum recursion depth exceeded` | Rewrite the function as a loop. |
| The program "does nothing" | The code sits inside `if __name__ == "__main__":` or only defines functions. Put the main code at top level, or call the function in the Shell. |
| A drawing flashes and vanishes | End with `get_key(1)` so it waits for a key. |
| ti_draw does nothing in the desktop software | Switch to **handheld view**: ti_draw only works there. |
| "Unsupported file type" when transferring | You sent the `.py`. Paste it into a Python Editor page and send the `.tns` (section 3). |
| A `.tns` opens but there's no Python menu | The handheld's OS is older than 5.2. Update it with TI's desktop software or TI-Nspire CX II Connect. |
| Results differ slightly from the Calculator app | That's expected: TI notes Python's float math differs from the CAS. Round with `round(x, 6)` for display. |
| `run_on_pc.py` fails with `NameError: TI variable 'a' is not defined` | Pass it: `--var a=5` (or `--list` / `--func`). |
| flash.py: `STOPPED: the checker found problems` | Fix the ERROR lines it printed (or ask Claude Code to), then run it again. |
| flash.py / send_to_calc.py: `No TI-Nspire found on USB` | Turn the handheld on (it sleeps after a few minutes), use a data cable (some only charge), try another port. `python -I tools/send_to_calc.py --list` shows what Windows sees. |
| `driver=no-winusb-driver` or `cannot be opened (driver)` | Close TI software and CX II Connect tabs, replug. Still failing: section 3.4. |
| `busy-or-access-denied`, or a link error (`NACK`, `Timeout`, `Invalid packet`) | Another program holds the handheld (TI software, a CX II Connect tab, a second flash.py). Close it, unplug, wait 3 s, replug. Make sure the handheld is on its Home screen and not in Press-to-Test. |
| `verify: handheld has N bytes` | The copy arrived damaged. Send again; if it repeats, change cable or port. |
| `program name ... must start with a letter` | Rename the file: letters, digits and `_`, starting with a letter. |
| The sent `.tns` doesn't show up | Look at the top of My Documents (or the `--folder`). An open document shows the old version until closed and reopened. `send_to_calc.py --ls /` lists what is on the handheld. |
| The sent `.tns` won't open, or the editor page is empty | Tell Claude Code what the handheld says. Meanwhile use section 3.2 (paste into TI's software) or drag `build/<name>.tns` into TI-Nspire CX II Connect. |
| `tools/bin/... is missing` | Run `python -I tools/build_tools.py` (section 3.6). |

## Sources

TI's own documentation (checked 2026-11-26):

- TI-Nspire Python Programming Guidebook (PDF, English, 2021 edition): modules, menus,
  ti_system/ti_draw/ti_image functions, keyword list, PyLib, and how to stop a program.
  <https://education.ti.com/download/en/ed-tech/ED617B2A7D254AA7A86ECE492591CBBA/923CBF3F858845EE96DD5A4663515F72/TI-Nspire_Python_Programming_Guidebook_EN.pdf>
- Online eGuide, Python chapter (current OS): Getting started and supported models
  <https://education.ti.com/html/webhelp/EG_TINspire/EN/Subsystems/EG_Python/Content/m_getstart/m_getstart.HTML> ,
  modules <https://education.ti.com/html/webhelp/EG_TINspire/EN/Subsystems/EG_Python/Content/m_getstart/gs_modules.HTML> ,
  installing a module (PyLib) <https://education.ti.com/html/webhelp/EG_TINspire/EN/Subsystems/EG_Python/Content/m_getstart/gs_installmod.HTML> ,
  TI System menu <https://education.ti.com/html/webhelp/EG_TINspire/EN/Subsystems/EG_Python/Content/m_menumap/mm_tisystem.HTML> ,
  TI Draw menu <https://education.ti.com/html/webhelp/EG_TINspire/EN/Subsystems/EG_Python/Content/m_menumap/mm_tidraw.HTML> ,
  sample programs <https://education.ti.com/html/webhelp/EG_TINspire/EN/Subsystems/EG_Python/Content/m_appendix/app_sampleprog.HTML>
- Python modules activities ("require OS 5.2 and above"):
  <https://education.ti.com/en/activities/ti-codes/python/ti-nspire-cx-ii/python-modules>
- Programming in Python (Turtle, Go Direct, micro:bit add-ons):
  <https://education.ti.com/en/products/calculators/graphing-calculators/ti-nspire-cx-ii-cx-ii-cas/programming-in-python> ;
  Turtle <https://education.ti.com/en/product-resources/turtle-module/nspire-python>
- Transferring files between the computer and the handheld:
  <https://education.ti.com/html/webhelp/EG_TINspire/EN/content/m_transfileshh/cv_transferring_files_between_comp_and_hh.HTML> ;
  TI-Nspire CX II Connect <https://education.ti.com/en/products/computer-software/ti-nspire-cx-ii-connect>
- OS downloads (CX II CAS): <https://education.ti.com/en/software/details/en/8CBC7A5F94D447B39E7C8C7F8178DB28/TI-NspireCXIICAS_OS> ;
  OS 6.3 announcement (Aug 2025, TI-Innovator group): <https://groups.google.com/g/ti-innovator/c/Pk2YDH6p_iI>

Community:

- Cemetech, "Transfering python files to TI-Nspire CX II-T CAS" (2023): `.py` is rejected,
  renaming doesn't work, and the answer is to paste into a Python program in the software.
  <https://www.cemetech.net/forum/viewtopic.php?t=19062>
- TI-Planet forum: the 318x212 ti_draw canvas, about 2.05 to 2.07 MB of heap, and the
  OS 6.2 change list. The site blocks automated reading, so these figures come from its
  search snippets; `probe.py` confirms them on your own handheld.
  <https://tiplanet.org/forum/viewtopic.php?t=24881> , <https://tiplanet.org/forum/viewtopic.php?t=26678>
- Luna (.py to .tns packer): <https://github.com/ndless-nspire/Luna> (README: "Python
  scripts require CX II OS 5.2 or later"; Python support is newer than the v2.1 tag).
- libnspire (USB link, CX II handshake): <https://github.com/Vogtinator/libnspire>
- N-Link (built on libnspire; "CX II: No additional installation required" on Windows,
  Zadig needed only for older models, uninstall WinUSB to go back to TI's software):
  <https://lights0123.com/n-link/> , <https://github.com/lights0123/n-link>
- Zadig: <https://zadig.akeo.ie/> ; libusb: <https://github.com/libusb/libusb/releases>
- Versions, commits and licences of everything in `third_party/`: `third_party/README.md`.

Not verified, so `probe.py` checks them: the exact MicroPython version, f-string and walrus
support, the recursion limit, and whether the CPython string extras exist. Everything the
checker treats as an error is either missing from TI's documentation or newer than TI's
Python.
