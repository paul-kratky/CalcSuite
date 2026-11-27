# CalcSuite

Your TI calculators on your Windows PC: the screen live in a window, your keyboard as its keys,
paste text into it, screenshots, recordings, and programs sent over USB. For the
**TI-Nspire CX II** (CAS too), the **TI-84 Plus CE** and the **TI-89 Titanium**, several at once.

## Get started

1. **Download** the app (the `.exe`) from the
   [latest release](https://github.com/paul-kratky/CalcSuite/releases/latest). It is one file:
   nothing to install, no Python needed.
2. **TI-84 Plus CE or TI-89 Titanium: give it a driver, once.** (A TI-Nspire CX II needs
   nothing; skip this step.) These calculators don't tell Windows which driver to use, so they
   show up with none. With the calculator plugged in and switched on:
   1. Download and run [Zadig](https://zadig.akeo.ie/).
   2. **Options > List All Devices**.
   3. Pick the calculator: **TI-84 Plus CE** (USB ID `0451 E008`) or **TI-89 Titanium** (USB ID
      `0451 E004`). The Driver box says `(NONE)`.
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
| **Record** | A GIF, and an MP4 too when [ffmpeg](https://ffmpeg.org/) is installed. Up to 3 minutes. |
| **Send program** | TI-Nspire: a `.py` (checked and converted first) or a `.tns`. |
| **Mouse** | TI-Nspire: wheel up/down (Shift: left/right), click, double click Enter, right click the context menu. |

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
| TI-84 Plus CE / TI-89 Titanium never connects | The Zadig step: in Zadig, its Driver box must say WinUSB. |
| TI's own software no longer sees the 84 / 89 | That's the WinUSB driver. To undo it: Device Manager > the calculator > Uninstall device, with "delete the driver" ticked. |
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
