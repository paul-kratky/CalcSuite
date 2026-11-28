# CalcSuite

[![Tests](https://github.com/paul-kratky/CalcSuite/actions/workflows/tests.yml/badge.svg)](https://github.com/paul-kratky/CalcSuite/actions/workflows/tests.yml)
[![Fuzz](https://github.com/paul-kratky/CalcSuite/actions/workflows/fuzz.yml/badge.svg)](https://github.com/paul-kratky/CalcSuite/actions/workflows/fuzz.yml)
[![CodeQL](https://github.com/paul-kratky/CalcSuite/actions/workflows/codeql.yml/badge.svg)](https://github.com/paul-kratky/CalcSuite/actions/workflows/codeql.yml)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/paul-kratky/CalcSuite/badge)](https://scorecard.dev/viewer/?uri=github.com/paul-kratky/CalcSuite)
[![Signed releases](https://img.shields.io/badge/releases-signed%20%C2%B7%20SLSA%20provenance-2ea44f?logo=sigstore&logoColor=white)](SECURITY.md#checking-a-download)

[![Latest release](https://img.shields.io/github/v/release/paul-kratky/CalcSuite?label=release)](https://github.com/paul-kratky/CalcSuite/releases/latest)
[![Release date](https://img.shields.io/github/release-date/paul-kratky/CalcSuite?label=released)](https://github.com/paul-kratky/CalcSuite/releases/latest)
[![Downloads](https://img.shields.io/github/downloads/paul-kratky/CalcSuite/total)](https://github.com/paul-kratky/CalcSuite/releases)
[![Licence: MIT](https://img.shields.io/badge/licence-MIT-blue)](LICENSE)

[![Last commit](https://img.shields.io/github/last-commit/paul-kratky/CalcSuite)](https://github.com/paul-kratky/CalcSuite/commits/main)
[![Commit activity](https://img.shields.io/github/commit-activity/m/paul-kratky/CalcSuite)](https://github.com/paul-kratky/CalcSuite/commits/main)
[![Issues](https://img.shields.io/github/issues/paul-kratky/CalcSuite)](https://github.com/paul-kratky/CalcSuite/issues)
[![Closed issues](https://img.shields.io/github/issues-closed/paul-kratky/CalcSuite)](https://github.com/paul-kratky/CalcSuite/issues?q=is%3Aissue+is%3Aclosed)
[![Pull requests](https://img.shields.io/github/issues-pr-closed/paul-kratky/CalcSuite?label=pull%20requests)](https://github.com/paul-kratky/CalcSuite/pulls?q=is%3Apr+is%3Aclosed)
[![Repo size](https://img.shields.io/github/repo-size/paul-kratky/CalcSuite)](https://github.com/paul-kratky/CalcSuite)

![Windows 10/11](https://img.shields.io/badge/platform-Windows%2010%2F11-0078D4?logo=windows&logoColor=white)
![Calculators](https://img.shields.io/badge/calculators-Nspire%20CX%20II%20%C2%B7%2084%20Plus%20CE%20%C2%B7%2089%20Titanium-ff7a3d)

Your TI calculators on your Windows PC, in one window: their screens live, your keyboard as
their keys, programs written and sent over USB, their files, lists and backups, and a copy of the
calculator that runs on the PC. For the **TI-Nspire CX II** (CAS too), the **TI-84 Plus CE** and
the **TI-89 Titanium**, several at once.

![CalcSuite showing a TI-Nspire CX II CAS, a TI-84 Plus CE and a TI-89 Titanium side by side on All screens](docs/img/all-screens.png)

## Get started

1. **Download** `CalcSuite-<version>-win64.zip` from the
   [latest release](https://github.com/paul-kratky/CalcSuite/releases/latest) and unzip it
   anywhere (Desktop, a USB stick). Nothing to install, no Python. Open `CalcSuite.exe` in the
   folder it makes. Everything it saves stays in that folder.
2. If Windows says **"Windows protected your PC"**: **More info**, then **Run anyway**
   (CalcSuite isn't code-signed yet; [check the download](SECURITY.md#checking-a-download) if you
   like).
3. **Plug in the calculators and switch them on.** Each gets a tab. The first time, CalcSuite
   sets up the USB driver for each one (one admin prompt). If that fails, the
   [user guide](docs/USER_GUIDE.md#get-started) has the Zadig steps.

No calculator? **Write a program** works without one.

## What it does

**Live screens and your keyboard.** Click a screen and type: your keys press the calculator's
(the Keys panel lists them). Screenshots, recordings, pasted text, Copy answer.

![A TI-84 Plus CE's tab: the live graph screen and the Keys panel](docs/img/calculator-tab.png)

**Symbols.** One click types ∫, √, π, ≤, → and the rest the way each calculator does it (the
Nspire's through its own menus).

![The TI-Nspire's tab with the Symbols panel](docs/img/symbols.png)

**Write programs, with or without a calculator.** TI-Basic for the 84 and the 89, Python for the
Nspire, with checkers that catch mistakes before the calculator does. **Solver builder** turns
equations (`V = I*R`) into a menu-driven solver for all three. **Test in PC copy** runs an 84
program in the emulator first.

![The Program editor](docs/img/editor.png)

![The Solver builder with Ohm's law](docs/img/solver.png)

**Get programs.** Engineering tools and games for each calculator, by section (Electrical,
Mechanical, Chemistry, Physics, Math, Games...), with search.

![Get programs on the TI-89 Titanium's tab](docs/img/programs.png)

**Data.** The calculator's lists and matrices in a grid: edit, paste to and from Excel, CSV,
plot, send back.

![The Data panel on the TI-84 Plus CE's tab](docs/img/data.png)

**Macros.** Record keys and play them back; one-click "Go to" macros (Y=, WINDOW, TABLE...),
pinned as buttons or on Ctrl+1 to 9.

![The Macros panel on the TI-89 Titanium's tab](docs/img/macros.png)

**Also:** files on the calculator, backups and restore, compare two backups, pictures made into
calculator images, **PC copy** (your own calculator's ROM running in CEmu or TiEmu in a tab), and
TI's OS update check.

## Guides

| Guide | |
| --- | --- |
| [User guide](docs/USER_GUIDE.md) | everything above in detail, keys, files, problems |
| [Quick start](QUICKSTART.md) | five minutes from download to the first program |
| [TI-84 Plus CE TI-Basic](docs/TIBASIC_84.md) · [TI-89 Titanium TI-Basic](docs/TIBASIC_89.md) · [TI-Nspire Python](docs/PYTHON_NSPIRE_GUIDE.md) | writing programs |
| [PC copies (CEmu and TiEmu)](docs/EMULATORS.md) · [Data](docs/DATA_BRIDGE.md) | the emulators and their keys; lists, matrices, Copy answer |
| [TI-Nspire Python kit](docs/PYTHON_KIT.md) | the command-line kit for developers |

The release's `Guides` folder has all of them as PDFs.

## Is it safe?

No account, no telemetry, online only when you ask (downloads, the OS check). Releases are built
on GitHub from this source, signed and scanned: [SECURITY.md](SECURITY.md) says how to check one
and how to report a problem.

## From the source

Python 3.11 on Windows: `python tools/mirror.py` (or `CalcSuite.bat`). The USB helpers build with
`python -I tools/build_tools.py` (MSYS2 UCRT64); `python -I tools/selftest/run_selftest.py` runs
every test. [CHANGELOG.md](CHANGELOG.md) says what changed.

## Licence

MIT ([LICENSE](LICENSE)). The USB helpers and the emulators are separate programs under their own
licences: [LICENSING.md](LICENSING.md).
