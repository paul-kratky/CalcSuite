# CalcSuite

[![Tests](https://github.com/paul-kratky/CalcSuite/actions/workflows/tests.yml/badge.svg)](https://github.com/paul-kratky/CalcSuite/actions/workflows/tests.yml)
[![Latest release](https://img.shields.io/github/v/release/paul-kratky/CalcSuite?label=release)](https://github.com/paul-kratky/CalcSuite/releases/latest)
[![Downloads](https://img.shields.io/github/downloads/paul-kratky/CalcSuite/total)](https://github.com/paul-kratky/CalcSuite/releases)
[![Licence: MIT](https://img.shields.io/badge/licence-MIT-blue)](LICENSE)
![Windows 10/11](https://img.shields.io/badge/platform-Windows%2010%2F11-0078D4)
![Calculators](https://img.shields.io/badge/calculators-Nspire%20CX%20II%20%C2%B7%2084%20Plus%20CE%20%C2%B7%2089%20Titanium-ff7a3d)

Your TI calculators on your Windows PC, in one window: their screens live, your keyboard as
their keys, symbols and text pasted in, screenshots and recordings, programs sent over USB, the
files on them, and a guide for writing programs. For the **TI-Nspire CX II** (CAS too), the
**TI-84 Plus CE** and the **TI-89 Titanium**, several at once.

![CalcSuite showing a TI-Nspire CX II CAS, a TI-84 Plus CE and a TI-89 Titanium side by side on All screens](docs/img/all-screens.png)

## Get started

1. **Download** `CalcSuite.exe` from the
   [latest release](https://github.com/paul-kratky/CalcSuite/releases/latest). It is one file:
   nothing to install, no Python needed.
2. **Open CalcSuite** with the calculators plugged in and switched on. Each one gets a tab; one
   plugged in later gets its tab by itself.
3. **The first time only:** Windows needs the WinUSB driver for each calculator, and TI's
   calculators don't bring it. When a calculator has no driver CalcSuite can use, CalcSuite
   opens its tab on **Info**, shows what it will change and asks **Change the driver?**. Press
   OK, then **Yes** on Windows' admin prompt. It takes a minute or two, once per calculator.
   (Later, **Info > Install the WinUSB driver...** does it again, and **Restore TI's driver...**
   gives TI's software its driver back.)

<details>
<summary><b>If that doesn't work: set the driver up with Zadig</b></summary>

1. Download and run [Zadig](https://zadig.akeo.ie/).
2. **Options > List All Devices**.
3. Pick the calculator:

   | Calculator | In Zadig's list | USB ID |
   | --- | --- | --- |
   | TI-Nspire CX II (CAS) | TI-Nspire(tm) CX II Handheld | `0451 E022` |
   | TI-84 Plus CE | TI-84 Plus CE | `0451 E008` |
   | TI-89 Titanium | TI-89 Titanium | `0451 E004` |

   If its Driver box already says `WinUSB`, it's done.
4. Choose **WinUSB** and press **Install Driver**. It takes a minute or two.

![Zadig with the TI-89 Titanium selected, driver (NONE), WinUSB chosen](docs/img/zadig-ti89t.png)

![Zadig with the TI-84 Plus CE selected and WinUSB chosen](docs/img/zadig-ti84ce.png)

A TI-Nspire CX II whose Driver box says WinUSB (the button reads "Reinstall Driver") needs
nothing more.

![Zadig with the TI-Nspire CX II selected, its driver already WinUSB](docs/img/zadig-nspire.png)

</details>

Close TI's own software (TI Connect CE, CX II Connect) while you use it: only one program can
talk to a calculator at a time.

## The window

**All screens** (the first tab) shows every connected calculator's live screen side by side,
each with its frame rate, **Screenshot** and **Record**. Click a screen to type on that
calculator: it gets an orange outline and a **KEYBOARD** tag. Double click a screen to open its
tab.

**A calculator's tab** shows its screen big, with **Screenshot**, **Copy screen**, **Paste
text**, **Record**, **Send program...** and **Keyboard** (on/off) under it, and **Last key:
F5 → GRAPH** so you see what each PC key did. **Key history** shows the last 8 keys as keycaps
under the screen; **Show keys in recordings** puts that strip into your GIF and MP4 too.
**Open in its own window** (top right) pops the calculator out into a window of its own;
closing that window puts it back as a tab. A calculator that's unplugged greys out ("not
plugged in") and comes back when you plug it in again.

![A calculator tab with the Files panel](docs/img/calculator-tab.png)

The panel on the right of a tab:

| | |
| --- | --- |
| **Files** | What's on the calculator: download to the PC, upload, show programs as text, delete (Nspire: folders, rename). **Back up...** and **Restore...** ([details](#files-backup-and-restore)). |
| **Keys** | Which PC key presses which calculator key, for this calculator, and the mouse. The key you just pressed lights up. |
| **Symbols** | ∫ d/dx √ π θ Σ ∞ ≤ ≥ ≠ → i e ∠ ° ² ⁻¹ and more: click one to type it on the calculator. A symbol the calculator doesn't have is greyed out and says what to use instead. |
| **Guide** | How to write programs for this calculator (TI-Basic for the 84 and the 89, Python for the Nspire), with a contents list and search. Every example has **Copy** and **Send to calculator**. |
| **Get programs** | Programs picked for engineering work (unit converters, circuit tools, a CAS for the 84, control and signals for the 89, formula libraries for the Nspire). **Download and send** gets one from ticalc.org or GitHub when you click it and sends it; the rest open their page. TI's own apps open TI's page (their licence). **Get all...** lists everything CalcSuite can send by itself, with sizes, notes and what's on the calculator already, and sends it all or saves it all to the PC. |
| **Info** | Model, OS, free memory, whether TI has a newer OS, the calculator's clock (**Set the clock to the PC's time** on the 84 and 89), **Exit Press-to-Test...**, **Reconnect**, **Make a PC copy...** / **Open my PC copy** (84 and 89), and the connection doctor: whether Windows' driver is right for CalcSuite, with the fix. |

<img src="docs/img/symbols-panel.png" width="49%" alt="The Symbols panel"> <img src="docs/img/guide-panel.png" width="49%" alt="The Guide panel">

## Keys and mouse

What you type goes to the calculator: letters, digits and symbols as themselves (on the 84,
lower case is the capital). Keys go first: the picture catches up when you pause. The **Keys**
panel lists every key for the calculator in front of you.

| PC key | TI-Nspire | TI-84 Plus CE | TI-89 Titanium |
| --- | --- | --- | --- |
| Enter, arrows | enter, arrows | ENTER, arrows | ENTER, arrows |
| Esc | esc | CLEAR | ESC |
| Backspace | del | DEL (after the cursor moves left) | backspace |
| Tab | tab | | |
| Ctrl+letter | ctrl+letter | | |
| F1 ... F5 | home, menu, doc, catalog, var | Y=, WINDOW, ZOOM, TRACE, GRAPH | F1 ... F5 |
| F6 ... F12 | | MODE, MATH, APPS, PRGM, VARS, STAT, QUIT | F6, F7, F8, APPS, MODE, CATALOG, CLEAR |
| Home | | | HOME |
| Ctrl+V | types the PC's clipboard text, symbols too (new lines are Enter) | the same | the same |
| Ctrl+C | copies the screen as a picture | the same | the same |
| Ctrl+Shift+C / V | the handheld's own copy / paste | | |

| Mouse | TI-Nspire | TI-84 Plus CE | TI-89 Titanium |
| --- | --- | --- | --- |
| Wheel (Shift: sideways) | up / down | up / down | up / down |
| Click | click; the X closes the document, the page tabs change page | on a numbered menu line (MATH, PRGM, ...): picks it | on a toolbar tab: its F key |
| Double click | enter | ENTER | ENTER |
| Right click | the context menu | CLEAR | ESC |
| Middle click | menu | | HOME |

## Fast mode for the TI-84 Plus CE (experimental)

The TI-84 Plus CE's own screenshot takes 1.2-1.4 s, so its picture moves at under 1 frame a
second. **Fast mode** (off until you turn it on) puts a small program of ours, CSFAST, on the
calculator. It adds a key hook that, when CalcSuite asks, packs the screen (only the rows that
changed) into a few AppVars that the link reads in about 0.15 s: about **6-7 frames a second**
on a still screen and **4-5 while typing**, and a key shows on the PC in about 0.3 s instead of
2 s. Measured on a TI-84 Plus CE, OS 5.4.0; details in `docs/dev/FAST84_PLAN.md`.

- **Needs OS 5.4 or older** (assembly programs). OS 5.5 and newer block them; arTIfiCE brings
  them back until the next reset, but CalcSuite doesn't install it. Press-to-Test blocks it too.
- **What it puts on the calculator** (only these names, nothing of yours is touched): the
  program CSFAST, the archived AppVar ZZHOOK (the hook's code), and in RAM CSSNAP, ZZWORK and
  up to eight ZZSNPA-ZZSNPH, about 40 KB of RAM while it's on (it leaves at least 16 KB free).
- **Turning it off** runs CSFAST again, which removes the hook, and deletes all of the above:
  the calculator is as it was. Running `prgmCSFAST` on the calculator toggles it too. A RAM
  reset removes the hook; CalcSuite notices and goes back to normal screenshots.
- Closing CalcSuite leaves Fast mode on the calculator (closing stays quick). That is safe: the
  hook only reacts to three key codes the keypad never sends; the calculator works as usual.
  Turn it off in CalcSuite when you want the RAM back.
- **Home screen only** (with its menus: MATH, PRGM, the catalog...). On the graph, table, Y=,
  mode and other screens TI's OS would jump back to the home screen when the link reads a
  variable, so there CalcSuite takes normal screenshots (under 1 frame a second) and the
  screen stays as it is. A screen too busy to pack, or a running program, also gets a normal
  screenshot, by itself.
- Back up before the first try (Files, Back up): a bug in a hook can crash a calculator, and a
  crash clears its RAM.

From the command line: `ti84-cli serve`, then `fast status`, `fast on tools/fast84/CSFAST.8xp`,
`snap FILE.ppm` (a frame; falls back to `shot` by itself), `fast off tools/fast84/CSFAST.8xp`.

## Screenshots and recordings

**Screenshot** saves a PNG in `Documents\CalcSuite\captures`. **Record** records the screen
straight from the app, up to 3 minutes: always a GIF, and an MP4 too with
[ffmpeg](https://ffmpeg.org/). No ffmpeg on your PC? The first time you press Record, CalcSuite
offers to download it for you (free, about 39 MB, once). Say no to keep the GIF only.

## Sending programs

**Send program...** in a calculator's tab:

- **TI-Nspire:** a `.py` (checked and converted first) or a `.tns`.
- **TI-84 Plus CE and TI-89 Titanium:** TI-Basic typed on the PC (a `.txt`, `.tib` or `.bas`)
  or a ready TI file (`.8xp`, `.89p`, ...).

It asks before replacing anything on the calculator. The **Guide** panel's examples send in one
click. How to write the text: [TI-Basic from the PC](#ti-basic-from-the-pc).

### The program editor

Write TI-84 Plus CE TI-Basic, TI-89 Titanium TI-Basic or Nspire Python in CalcSuite itself
(`python -I tools/editor.py [file]` opens it on its own). It checks as you type, underlines each
mistake and lists it with its fix (F8 goes to the next one), colours the code like VS Code,
completes command names (Ctrl+Space) and shows the command's syntax with the current argument
in bold. **Build** (Ctrl+B) makes the calculator's file (`.8xp`, `.89p`, `.tns`) in
`Documents\CalcSuite\programs\<calculator>\` with the source beside it; **Copy file** puts it
on the clipboard for Discord or e-mail. **F5** checks, builds, sends and runs it (the Nspire:
sends it; open it on the handheld), **F6** sends only. Nothing is built or sent while there are
errors. **Copy AI instructions** gives a chat AI the rules for your calculator; paste its
answer into an empty editor and **Copy problems for the AI** hands back what the checker found.

## Files, backup and restore

| | TI-Nspire CX II | TI-84 Plus CE | TI-89 Titanium |
| --- | --- | --- | --- |
| Browse | folders and files, with sizes | variables, programs, apps, with sizes and RAM/Archive | variables by folder, apps |
| Download | any file | as TI files (`.8xp`, `.8xv`, `.8xl`, ...) | as TI files (`.89p`, `.89e`, ...) |
| Show as text | | TI-Basic programs, strings, equations | texts, strings, programs not yet run |
| Upload | `.py` (checked and converted) or `.tns` | TI files (`.8xp` etc.) or TI-Basic text | TI files (`.89p` etc.) or TI-Basic text |
| Delete, new folder, rename | yes (folders must be empty to delete) | delete | delete |

Downloads go to `Documents\CalcSuite\from-calc` unless you pick another folder.

**Back up...** copies everything the link can read to
`Documents\CalcSuite\backups\<model>-<date>` (Nspire: every file, folders kept; 84: TI files
and a `.b84` bundle; 89: TI files and a `.89g` group; a `manifest.json`). Apps and the OS can't
be read: they're listed as skipped. **Restore...** shows what's in a backup, sends what you
pick, and asks before replacing anything. It never wipes the calculator.

**Info** checks TI's website once a day for a newer OS and links to TI's download page.
CalcSuite never downloads or installs an OS itself. (On the 84, OS 5.5 and later no longer run
assembly programs.) The Nspire's clock can't be read or set over USB: set it on the handheld.
**Exit Press-to-Test...** uses TI's own way only: for the Nspire, CalcSuite lets go of the
handheld and opens TI-Nspire CX II Connect; for the 84, TI's steps. The TI-89 Titanium has no
Press-to-Test.

## A PC copy of your calculator

`python -I tools/pc_copy.py make 84` (or `89`) backs the calculator up, copies its ROM to
`Documents\CalcSuite\backups\roms\`, removes what it put on the calculator, and opens the copy
in CEmu with your programs and variables (the 84 Plus CE, OS 5.4 or older). For the TI-89
Titanium it makes the ROM; its emulator, TiEmu, you install yourself. The ROM is TI's software
from your own calculator: it stays on your PC and is never uploaded. In the window: Info >
**Make a PC copy...**. Details: [docs/PC_COPY.md](docs/PC_COPY.md).

## TI-Basic from the PC

Write the program in any text editor (or take one from the **Guide** panel) and send it with
**Send program...** (or **Upload** in **Files**, or `python -I tools/send_ti.py --calc 84|89
FILE`, which adds `--name`, `--replace` and `--out FILE` to only make the TI file).

- **TI-84 Plus CE:** the app turns the text into the calculator's tokens. Write it as the
  calculator shows it, or with the PC spellings: `->` for the store arrow, `<=` `>=` `!=`,
  `sqrt(`, `pi`, `theta`, `^2`, `^-1`, `L1`, `Y1`, `E` in a number for the EE key, `-` at the
  start of a number for the negative sign. The symbols work too (`→ ≤ ≥ ≠ √ π θ ² ⁻¹`). A `:`
  at the start of a line is fine. Spaces only count inside strings. The program is named after
  the file (`HELLO.txt` is `HELLO`; up to 8 capitals), or the app asks. Run it with PRGM.
  A word outside a string with lower case letters that isn't a command (`textcolor(`) gets a
  warning before sending: the calculator would stop there.
- **TI-89 Titanium:** the program goes over as text, the way the 89's own Program Editor keeps
  it, and the 89 turns it into its tokens the first time it runs. Start with the program's
  line and `Prgm` / `EndPrgm` (`Func` / `EndFunc` makes a function):

  ```
  hello()
  Prgm
  ClrIO
  Disp "Hello"
  EndPrgm
  ```

  or write only the body (a program with no arguments, named after the file). The same PC
  spellings work (`->`, `<=`, `>=`, `!=`, `sqrt(`, `pi`, `theta`), and `@>` for ► (`10@>Bin`,
  `3_m@>_ft`), `@int(` for ∫(, `@d(` for d(, `@sum(` for Σ(, `@angle` for ∠, `@i` for 𝑖.
  Run it by typing `hello()`.

The full guides: [TI-84 Plus CE](docs/TIBASIC_84.md), [TI-89 Titanium](docs/TIBASIC_89.md),
[Python on the Nspire](docs/PYTHON_NSPIRE_GUIDE.md) (the same ones as in the **Guide** panel).

As dark PDFs (also **Save as PDF** in the Guide and Functions panels, and on each release): [TI-84 Plus CE guide](docs/pdf/CalcSuite%20-%20TI-84%20Plus%20CE%20TI-Basic%20guide.pdf), [TI-89 Titanium guide](docs/pdf/CalcSuite%20-%20TI-89%20Titanium%20TI-Basic%20guide.pdf), [Nspire Python guide](docs/pdf/CalcSuite%20-%20TI-Nspire%20CX%20II%20Python%20guide.pdf);
Functions references [TI-84 Plus CE](docs/pdf/CalcSuite%20-%20TI-84%20Plus%20CE%20functions%20reference.pdf), [TI-89 Titanium](docs/pdf/CalcSuite%20-%20TI-89%20Titanium%20functions%20reference.pdf), [TI-Nspire CX II](docs/pdf/CalcSuite%20-%20TI-Nspire%20CX%20II%20functions%20reference.pdf); [user guide](docs/pdf/CalcSuite%20-%20User%20guide.pdf), [quick start](docs/pdf/CalcSuite%20-%20Quick%20start.pdf), [Python kit](docs/pdf/CalcSuite%20-%20TI-Nspire%20Python%20kit.pdf).

## If something doesn't work

Open the calculator's **Info** panel first: the connection doctor says what Windows has on it
and what to do.

| Problem | Fix |
| --- | --- |
| The tab says it's looking for the calculator | Switch it on (they sleep after a few minutes), use a data cable (some only charge), close TI's software, try another USB port. |
| A calculator never connects | Its driver: **Info > Install the WinUSB driver...** (it shows what it will do first, and Windows asks for admin rights). If that fails, the Zadig steps under [Get started](#get-started). |
| TI's own software no longer sees the calculator | That's the WinUSB driver. **Restore TI's driver...** in **Info** gives it back, or: Device Manager > the calculator > Uninstall device, with "delete the driver" ticked. |
| A key does nothing | Some special keys aren't mapped yet: [open an issue](https://github.com/paul-kratky/CalcSuite/issues) with the key and the calculator. |

## Writing Python programs

CalcSuite also has a kit for writing Python programs for the TI-Nspire CX II on the PC, with or
without an AI assistant: a checker for what the calculator's Python can run, a runner on the PC,
and sending in one step. See [docs/PYTHON_KIT.md](docs/PYTHON_KIT.md), or the one-page
[QUICKSTART.md](QUICKSTART.md).

From the source: `CalcSuite.bat` (or `python -I tools/mirror.py`). CalcSuite was called Nspire
Mirror before 1.0; its files in `Documents\Nspire Mirror` are copied to `Documents\CalcSuite`
the first time it starts (nothing is deleted).

What's new: [CHANGELOG.md](CHANGELOG.md).

**Licence:** MIT (`LICENSE`), except `tools/nspire_cli/` and `tools/ti84_cli/` and the
programs built from them, which are GPL-3.0-or-later (they link libnspire / follow TILP), and
`tools/bin/calcsuite-driver.exe` (LGPL-3.0-or-later, libwdi; its source is in
`tools/driver_helper/`); `third_party/` projects and `tools/third_party_py/tivars` (MIT) keep
their own licences. Programs from **Get programs** keep their authors' licences: CalcSuite
links to them and downloads them only when you ask. Not affiliated with Texas Instruments.
