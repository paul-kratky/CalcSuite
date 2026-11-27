# CalcSuite

Your TI calculators on your Windows PC: the screen live in a window, your keyboard as its keys,
paste text into it, screenshots, recordings, and programs sent over USB. For the
**TI-Nspire CX II** (CAS too), the **TI-84 Plus CE** and the **TI-89 Titanium**, several at once.

## Get started

1. **Download** the app (the `.exe`) from the
   [latest release](https://github.com/paul-kratky/CalcSuite/releases/latest). It is one file:
   nothing to install, no Python needed.
2. **Give each calculator the WinUSB driver, once.** Windows needs it to let the app talk to
   the calculator, and TI's calculators don't bring it themselves. With the calculator plugged
   in and switched on:
   1. Download and run [Zadig](https://zadig.akeo.ie/).
   2. **Options > List All Devices**.
   3. Pick the calculator:

      | Calculator | In Zadig's list | USB ID |
      | --- | --- | --- |
      | TI-Nspire CX II (CAS) | TI-Nspire(tm) CX II Handheld | `0451 E022` |
      | TI-84 Plus CE | TI-84 Plus CE | `0451 E008` |
      | TI-89 Titanium | TI-89 Titanium | `0451 E004` |

      If its Driver box already says `WinUSB`, it's done: skip to step 3.
   4. Choose **WinUSB** and press **Install Driver**. It takes a minute or two.

   ![Zadig with the TI-89 Titanium selected, driver (NONE), WinUSB chosen](docs/img/zadig-ti89t.png)

   ![Zadig with the TI-84 Plus CE selected and WinUSB chosen](docs/img/zadig-ti84ce.png)

3. **Open the app** with the calculator plugged in and switched on. Each calculator gets its own
   window; one plugged in later opens its window by itself.

That's all. Close TI's own software (TI Connect, CX II Connect) while you use it: only one
program can talk to a calculator at a time.

## What it does

| | |
| --- | --- |
| **Live screen** | TI-Nspire about 19 frames a second, TI-89 Titanium fast, TI-84 Plus CE about 1 (the calculator sends 150 KB a picture). |
| **Keyboard** | What you type goes to the calculator. Keys go first: the picture catches up when you pause. |
| **Paste and copy** | Ctrl+V types the PC clipboard's text into the calculator (new lines are Enter). Ctrl+C copies the calculator's screen to the clipboard as a picture. |
| **Screenshot** | A PNG in `Documents\Nspire Mirror\captures`. |
| **Record** | Records the calculator's screen straight from the app, up to 3 minutes: always a GIF, and an MP4 too with [ffmpeg](https://ffmpeg.org/). No ffmpeg on your PC? The first time you press Record, the app offers to download it for you (free, about 39 MB, once). Don't want that? Say no and keep the GIF, or record the window with [OBS](https://obsproject.com/) or any other screen recorder. |
| **Send program** | TI-Nspire: a `.py` (checked and converted first) or a `.tns`. TI-84 Plus CE and TI-89 Titanium: TI-Basic typed on the PC (a `.txt`, `.tib` or `.bas`) or a ready TI file (`.8xp`, `.89p`, ...). It asks before replacing anything on the calculator. [How to write the text](#ti-basic-from-the-pc). |
| **Mouse** | TI-Nspire: wheel up/down (Shift: left/right), click, double click Enter, right click the context menu. |
| **Files** | The **Files...** button: what's on the calculator, saved to the PC, sent to it, deleted. Calculator info, and whether TI has a newer OS. |

## Files and updates

**Files...** in a calculator's window opens a list of what's on it. Downloads go to
`Documents\Nspire Mirror\from-calc` unless you pick another folder.

| | TI-Nspire CX II | TI-84 Plus CE | TI-89 Titanium |
| --- | --- | --- | --- |
| Browse | folders and files, with sizes | variables, programs, apps, with sizes and RAM/Archive | variables by folder, apps |
| Download | any file | as TI files (`.8xp`, `.8xv`, `.8xl`, ...) | as TI files (`.89p`, `.89e`, ...) |
| Show as text | | TI-Basic programs, strings, equations | texts, strings, programs not yet run |
| Upload | `.py` (checked and converted) or `.tns` | TI files (`.8xp` etc.) or TI-Basic text | TI files (`.89p` etc.) or TI-Basic text |
| Delete, new folder, rename | yes (folders must be empty to delete) | delete | delete |

### TI-Basic from the PC

Write the program in any text editor and send it with **Send program...** (or **Upload** in
**Files...**, or `python -I tools/send_ti.py --calc 84|89 FILE`, which adds `--name`,
`--replace` and `--out FILE` to only make the TI file).

- **TI-84 Plus CE:** the app turns the text into the calculator's tokens. Write it as the
  calculator shows it, or with the PC spellings: `->` for the store arrow, `<=` `>=` `!=`,
  `sqrt(`, `pi`, `theta`, `^2`, `^-1`, `L1`, `Y1`, `E` in a number for the EE key, `-` at the
  start of a number for the negative sign. The symbols work too (`→ ≤ ≥ ≠ √ π θ ² ⁻¹`). A `:`
  at the start of a line is fine. Spaces only count inside strings. The program is named after
  the file (`HELLO.txt` is `HELLO`; up to 8 capitals), or the app asks. Run it with PRGM.
- **TI-89 Titanium:** the program goes over as text, the way the 89's own Program Editor keeps
  it, and the 89 turns it into its tokens the first time it runs. Start with the program's
  line and `Prgm` / `EndPrgm` (`Func` / `EndFunc` makes a function), as the 89 shows it:

  ```
  hello()
  Prgm
  ClrIO
  Disp "Hello"
  EndPrgm
  ```

  or write only the body (a program with no arguments, named after the file). The same PC
  spellings work (`->`, `<=`, `>=`, `!=`, `sqrt(`, `pi`, `theta`). Run it by typing `hello()`.
  A mistake in the program shows up as the 89's own error when it first runs.

**About this calculator** shows the model, OS version and free memory, and checks TI's website
once a day for a newer OS: "Up to date", or the new version with a link to TI's download page.
The app never downloads or installs an OS itself; do that with TI's own software.

Keys that aren't letters, digits or symbols:

| PC key | TI-Nspire | TI-84 Plus CE | TI-89 Titanium |
| --- | --- | --- | --- |
| Enter, arrows | Enter, arrows | ENTER, arrows | ENTER, arrows |
| Esc | esc | CLEAR | ESC |
| Backspace | del | DEL (after the cursor moves left) | backspace |
| Tab | tab | | |
| Ctrl+letter | ctrl+letter | | |
| F1 ... F5 | home, menu, doc, catalog, var | Y=, WINDOW, ZOOM, TRACE, GRAPH | F1 ... F5 |
| F6 ... F12 | | MODE, MATH, APPS, PRGM, VARS, STAT, QUIT | F6, F7, F8, APPS, MODE, CATALOG, CLEAR |
| Home | | | HOME |
| Ctrl+Shift+C / V | the handheld's own copy / paste | | |

## If something doesn't work

| Problem | Fix |
| --- | --- |
| The window says it's looking for the calculator | Switch it on (they sleep after a few minutes), use a data cable (some only charge), close TI's software, try another USB port. |
| A calculator never connects | The Zadig step: in Zadig, its Driver box must say WinUSB. |
| TI's own software no longer sees the calculator | That's the WinUSB driver. To undo it: Device Manager > the calculator > Uninstall device, with "delete the driver" ticked. |
| A key does nothing | Some special keys aren't mapped yet: [open an issue](https://github.com/paul-kratky/CalcSuite/issues) with the key and the calculator. |

## Writing programs

CalcSuite also has a kit for writing Python programs for the TI-Nspire CX II on the PC, with or
without an AI assistant: a checker for what the calculator's Python can run, a runner on the PC,
and sending in one step. See [docs/PYTHON_KIT.md](docs/PYTHON_KIT.md), or the one-page
[QUICKSTART.md](QUICKSTART.md) to do it by hand.

What's new: [CHANGELOG.md](CHANGELOG.md).

**Licence:** MIT (`LICENSE`), except `tools/nspire_cli/` and `tools/ti84_cli/` and the
programs built from them, which are GPL-3.0-or-later (they link libnspire / follow TILP);
`third_party/` projects keep their own licences. Not affiliated with Texas Instruments.
