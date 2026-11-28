# CalcSuite quick start

Your TI calculators on your Windows PC in five minutes: the TI-Nspire CX II (CAS), the TI-84
Plus CE and the TI-89 Titanium.

## 1. Get it

1. Download `CalcSuite-<version>-win64.zip` from the
   [latest release](https://github.com/paul-kratky/CalcSuite/releases/latest).
2. **Unzip it** (right-click, **Extract All**) wherever you like. Nothing is installed.
3. Open `CalcSuite.exe` in the folder it made. If Windows says **"Windows protected your PC"**,
   click **More info**, then **Run anyway** (CalcSuite isn't code-signed yet).

## 2. Plug in

1. Plug the calculator in with a data cable and switch it on.
2. Close TI's own software (TI Connect CE, CX II Connect): one program at a time.
3. **The first time only,** CalcSuite opens the calculator's **Calculator info** and offers to set up its
   USB driver: **OK**, then **Yes** on Windows' prompt. A minute or two, once per calculator.

Its screen appears on **All screens** and in its own tab, live.

## 3. Use it

| To | Do |
| --- | --- |
| Type on the calculator | Click its screen and type; the **Keys** panel shows which PC key is which |
| Type a symbol (∫ √ π θ ≤ ...) | **Symbols** panel, or paste text with them (Ctrl+V) |
| Find a command and its arguments | **Functions** panel; double-click to type it |
| Write a program | **More ▾ > Program editor...** under the screen: it checks as you type, **F5** builds, sends and runs it |
| Get ready-made programs | **Programs** in the side panel; double-click one to download and send it |
| Jump to Y=, TABLE, MODE... in one click | **Macros** panel: pin a **Go to** macro under the screen, or give it **Ctrl+1..9** |
| Save a screenshot or a video | **Screenshot**, **Record** |
| Back up the calculator | **Files** > **Back up...** |
| Run your own calculator on the PC (84 Plus CE, 89 Titanium) | **Calculator info** > **Make a PC copy...**: it opens in its own tab (guide: `CalcSuite - PC copies (CEmu and TiEmu) guide.pdf`) |
| Test a TI-84 Plus CE program before sending it | Program editor > **Test in PC copy** |

Everything CalcSuite saves (captures, programs, backups) is in the `CalcSuite files` folder next
to `CalcSuite.exe`. The guides are in `Guides`, and in the app (**Guide**, **Functions**).

## When something goes wrong

| Problem | Fix |
| --- | --- |
| It keeps looking for the calculator | Switch it on (it sleeps after a few minutes), use a data cable, close TI's software, try another USB port |
| It never connects | **Calculator info** > **Install the WinUSB driver...**; if that fails, the Zadig steps in the [README](README.md#get-started) |
| TI's software no longer sees the calculator | **Calculator info** > **Restore TI's driver...** |
| Something stays on "Asking..." | `CalcSuite files\logs\errors.log` says why: attach it to an [issue](https://github.com/paul-kratky/CalcSuite/issues) |

Everything else: the [README](README.md), the user guide (`Guides\User guide.pdf`).

## Writing Nspire Python from the source (developers)

The repository also has command-line tools for the TI-Nspire's Python, with no app needed:
`python -I tools/flash.py programs/myprog.py` checks, builds and sends a program, and
`python -I tools/run_on_pc.py programs/myprog.py` runs it on the PC first. Details:
[docs/PYTHON_KIT.md](docs/PYTHON_KIT.md).
