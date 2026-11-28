# CalcSuite - PC copies (CEmu and TiEmu) guide

A PC copy is your own calculator running on your PC: its own operating system, from its own
ROM, with your programs and variables, in an emulator inside CalcSuite's window. Try things
there before you send them to the real calculator, test a program, take screenshots, or just
use it when the calculator is in your bag.

- **TI-84 Plus CE** (OS 5.4 or older): the copy runs in **CEmu**, which CalcSuite downloads for
  you.
- **TI-89 Titanium**: the copy runs in **TiEmu**, which you install yourself (see
  [TiEmu](#tiemu)).

CEmu and TiEmu are separate programs by other people, free software under the GPL; CalcSuite
starts them and shows their window in its tab, nothing more (see
[Credits and licences](#credits-and-licences)).

## Making a PC copy

Plug the calculator in, switch it on and wait until its tab shows the screen. Then, in its side
panel: **Calculator info > PC copy > Make a PC copy...**. The calculator's **(PC copy)** tab
opens ("TI-84 Plus CE (PC copy)" or "TI-89 Titanium (PC copy)") and explains what will happen;
**Start the PC copy** begins.

1. **A full backup** of the calculator, as Files > Back up makes it.
2. **TI-84 Plus CE:** a Garbage Collect (it tidies the archive; nothing is deleted), then a
   small program, `ZZDUMP` (CEmu's own ROM dumper), is sent and started. The calculator shows
   "Dumping Segment A..." and so on for about a minute.
   **TI-89 Titanium:** a small program, `main\romdump` (TiLP's ROM dumper), is sent and
   started, and the ROM comes over USB (about a minute).
3. CalcSuite reads the ROM, removes what it put on the calculator, and checks that what was in
   RAM before is still there (if not, **Restore...** puts it back from the backup).

The tab shows the step it's on, **one bar for the whole job** (it only moves forward) and
**Cancel**. When it's done the bar is full and green, it says **Done: 100%** and **Your PC
copy is made**, and a moment later the emulator starts in the same tab. Leave the calculator
and the cable alone until then.

| | TI-84 Plus CE | TI-89 Titanium |
| --- | --- | --- |
| Calculator | OS 5.4 or older (5.5 and later don't run the dumper) | any AMS 3.x |
| Free memory | 66 KB of RAM, about 1.1 MB of archive | nothing special |
| Time | about 2 minutes | about 70 seconds |

The ROM is saved as `CalcSuite files\backups\roms\ti84ce-<date>.rom` (or `ti89t-...`), with a
`.json` beside it saying which calculator, OS and backup it came from. More about the dump:
[docs/PC_COPY.md](PC_COPY.md).

## The PC copy's tab

**Open my PC copy** (Calculator info) opens the newest copy in its tab; **Make a PC copy...**
makes a new one there. The tab has, along the top:

| Button | What it does |
| --- | --- |
| **Send files...** | Sends programs and variables (`.8xp`, `.8xv`, `.8xl`, ...) to the running copy (best from its home screen). |
| **Screenshot** | Saves the copy's screen as a PNG in `CalcSuite files\captures`. |
| **Start again from the backup** | Boots your ROM afresh with the programs and variables of the backup made with it. What you did in the copy since is replaced; your real calculator isn't touched. |
| **Open in its own window** | Gives CEmu (or TiEmu) its own normal window again; **Back into the tab** puts it back. The tab strip's **Open in its own window** does the same. |
| **Show the ROM** | Shows the ROM file in Explorer. |
| **Close CEmu** | Closes the emulator (CEmu saves where it was first). **Open again** carries on from there. |
| **CEmu's panels** | Off (the default): just the calculator, its screen above its keypad. On: CEmu's own docks too (Variables, Capture, Settings, State, the debugger) and its menu bar. CEmu restarts to change it and carries on where it was. |

The side panel has **Keys** (the emulator's PC keys, the same tables as below) and **Guide**
(this guide).

- **Typing:** click into the calculator, then type: the keys go to the emulator, and
  CalcSuite's own key shortcuts don't take them. Switching to another tab hands the keyboard
  back to CalcSuite.
- **The ✕ on the tab** closes the emulator and the tab. Closing CalcSuite closes the emulators
  it started (CEmu saves its state); emulators you started yourself are never touched.
- **CEmu's menus:** right-click the calculator's screen (File, Calculator, Capture, Docks,
  Extras). With **CEmu's panels** on, the menu bar is there too.

## CEmu

CEmu is the TI-84 Plus CE emulator by the CE-Programming team: <https://github.com/CE-Programming/CEmu>,
its guide: <https://github.com/CE-Programming/CEmu/wiki>. CalcSuite downloads version 2.0 from
CEmu's GitHub release the first time and checks it against a SHA-256.

### CEmu's keys

These are CEmu's **Keybindings** page as it is
(<https://github.com/CE-Programming/CEmu/wiki/Keybindings>): every calculator key and the PC
keys that press it. It is CEmu's **CEmu** key preset, the default (in CEmu 2.0's source the
setting `Keypad/map` defaults to `cemu`). To use another preset (Natural, TilEm, Wabbitemu,
jsTIfied, SmartPad, or your own): turn on **CEmu's panels**, then **Settings** dock > **General**
> **Key bindings**.

| Calculator | Computer 1 | Computer 2 | Computer 3 |
| --- | --- | --- | --- |
| enter | `Enter` |   |   |
| 2nd | `;` | `Tab` |   |
| alpha | `'` |   |   |
| sto→ | `>` | `X` |   |
| clear | `Esc` |   |   |
| del | `Delete` | `Insert` |   |
| math | `=` | `A` |   |
| apps | `Page Up` | `B` |   |
| prgm | `Page Down` | `C` |   |
| vars | `<` | `\|` |   |
| stat | `End` |   |   |
| mode | `Home` | `Backspace` |   |
| x,ᴛ,θ,n | `_` |   |   |
| (-) | `~` | `?` |   |
| + | `+` | `"` |   |
| – | `-` | `W` | `[` |
| × | `*` | `R` | `]` |
| ÷ | `/` | `M` |   |
| ^ | `^` | `H` |   |
| x² | `@` | `I` |   |
| x⁻¹ | `\` | `D` |   |
| ln | `` ` `` | `S` |   |
| log | `!` | `N` |   |
| sin | `$` | `E` |   |
| cos | `%` | `F` |   |
| tan | `&` | `G` |   |
| down | `Down` |   |   |
| left | `Left` |   |   |
| right | `Right` |   |   |
| up | `Up` |   |   |
| 0 | `0` | `Space` |   |
| 1 | `1` | `Y` |   |
| 2 | `2` | `Z` |   |
| 3 | `3` | `#` |   |
| 4 | `4` | `T` |   |
| 5 | `5` | `U` |   |
| 6 | `6` | `V` |   |
| 7 | `7` | `O` |   |
| 8 | `8` | `P` |   |
| 9 | `9` | `Q` |   |
| . | `.` | `:` |   |
| , | `,` | `J` |   |
| ( | `(` | `K` | `{` |
| ) | `)` | `L` | `}` |
| y= | `F1` |   |   |
| window | `F2` |   |   |
| zoom | `F3` |   |   |
| trace | `F4` |   |   |
| graph | `F5` |   |   |
| on | `F12` |   |   |

One difference from CEmu 2.0's own source (`gui/qt/keypad/keymap.cpp`): there `[` is × and `]`
is –, the other way round from the page. If one doesn't do what you expect, try the other.

The letters: as on the calculator, **alpha** then the key (the green letter above it), or the
PC keys of the second column (`A` is math, `B` apps, ... as the table shows).

### CEmu's shortcuts

From CEmu 2.0's source (`gui/qt/mainwindow.ui`, `mainwindow.cpp`):

| Keys | What it does |
| --- | --- |
| `Ctrl+Shift+O` | File > Open... (send files to the calculator) |
| `Ctrl+X` | Resend the files checked in the Variables dock |
| `Ctrl+Shift+X` | Start / stop recording an animated PNG |
| `Ctrl+Shift+C` | Copy the calculator's screen to the clipboard |
| `F11` | Full screen (application, then the screen only, then back) |
| `F10` | Debugger on / off |
| `Ctrl+Shift+Q` | Exit CEmu |

For full screen (**F11**), use **Open in its own window** first: full screen inside the tab isn't
something CalcSuite was made for.

### Sending files

CalcSuite: **Send files...** in the tab's bar, or **Start again from the backup** for the
whole backup. CEmu itself (from its **Sending Files** page,
<https://github.com/CE-Programming/CEmu/wiki/Sending-Files>):

- drag and drop a file anywhere on CEmu's window,
- drag and drop a file on the screen to send it to RAM or to the archive,
- **File > Open** (right-click the screen),
- the **Variables** dock (turn on **CEmu's panels**): send a file or resend a recent one;
  `Ctrl+X` resends every checked recent file.

### Getting files back

From the same page: in the **Variables** dock, **View Calculator Variables** lists what's on
the copy (right-click one to launch a program). Select one or several, then **Save selected**
(one file each) or **Save group** (one group file). CEmu's note: a group over 64 KB may give
errors in other programs; save them one by one if unsure. Then send them to the real
calculator with CalcSuite (Files, or the calculator tab's **Send program...**).

### Screenshots and recordings

- **Screenshot** in the tab's bar: a PNG in `CalcSuite files\captures`.
- CEmu (its **Screen Captures** page, <https://github.com/CE-Programming/CEmu/wiki/Screen-Captures>):
  **Capture > Take PNG screenshot**, **Capture > Copy screen to clipboard** (`Ctrl+Shift+C`),
  and animated PNG recordings: `Shift+Ctrl+X`, the **Capture** dock, or **File > Record
  Animated PNG** (CEmu 2.0 has it under **Capture**). The Capture dock's **Optimize** (on by
  default) shrinks a finished recording; **Frame skip** skips emulated frames to keep it small.

### Speed

CEmu runs at the real calculator's speed (100%). The **Settings** dock > **Emulation** >
**Display / Emulation Speed** sets another speed or turns **Throttle** off (as fast as the PC
can). CalcSuite doesn't change it.

### Its saved state

When CEmu closes (Close CEmu, the tab's ✕, closing CalcSuite) it saves the copy's whole state,
and **Open my PC copy** carries on from it. The first time, after a new ROM, or with **Start
again from the backup**, the ROM is booted afresh and the backup's programs and variables are
sent in. CEmu's own **Calculator > Save state / Restore state** and the **State** dock keep
more states. The tab's CEmu has its own settings and state, separate from a CEmu you start by
itself.

### The command line CalcSuite uses

From CEmu's **Command Line Arguments** page
(<https://github.com/CE-Programming/CEmu/wiki/Command-Line-Arguments>), checked against CEmu
2.0's `gui/qt/main.cpp`:

| Option | What CalcSuite uses it for |
| --- | --- |
| `--id CalcSuite` | Names the tab's CEmu ("CEmu \| CalcSuite"), so a CEmu you run yourself (id `Calculator`) is never mixed up with it, and commands reach the right one. |
| `-g <file>` | Its own settings file (and, beside it, its saved state) in CalcSuite's folder. |
| `--rom <file>` | Your ROM. |
| `--reload-rom` | Boot the ROM afresh (not the saved state). |
| `--send <file>` | A file from the backup (one `--send` per file). |
| `--id CalcSuite --send <file> --no-reset` | Send files... to the running copy without resetting it. |
| `--id CalcSuite --screenshot <png>` | Screenshot: the running copy saves its screen. |
| `-t <json> --no-test-dialog` | Test in PC copy (below): CEmu's autotester. |

The page lists more (`--lua-script`, `--ipc-only`, `--keys`, `--usb`) that came after CEmu
2.0: the CEmu CalcSuite downloads doesn't have them.

## Testing a program in the PC copy

In the **Program editor**, with a TI-84 Plus CE program: **Test in PC copy**. CalcSuite builds
the program, then a second CEmu, with your own ROM and throwaway settings (your PC copy's state
isn't touched), resets, gets the program, runs it, presses your keys and checks the screen. Its
window stays off the screen while it runs; it closes by itself.

- **Keys:** what to press after the program starts, separated by commas: `enter`, `2nd`,
  `alpha`, `clear`, `0`-`9`, `+ - * /`, `(`, `)`, `up`, `down`, `left`, `right`, `prgm`,
  `math`, `sto`, `(-)`, `.`, `,` ... and waits: `wait 500` (milliseconds). For a program that
  asks `N?`: `2, 1, enter, wait 500`.
- **Wait before the keys:** how long the program has to start (1500 ms by default).
- **Expected screen (CRC):** leave it empty the first time: the run shows the screen it ended
  on and its CRC. If it's right, **Expect this screen**: from then on the test passes when the
  screen ends exactly like that and fails when it doesn't.

The keys and the expected screen are kept beside the built program
(`CalcSuite files\programs\ti84\<name>.pctest.json`). It's CEmu's own autotester
(`tests/autotester` in CEmu's source: a JSON file names the program, the steps and the memory
to check); the key names are its own. From the command line:
`python -I tools/pc_test.py PROGRAM.8xp --keys "2, 1, enter" [--expect CRC]`.

## TiEmu

TiEmu is the TI-89 / TI-92 / Voyage 200 emulator by the TiLP team (GPL-2.0), last released in
2010 (3.03): <https://sourceforge.net/projects/gtktiemu/>. Its Windows release is an installer
only.

### Installing it

The PC copy's tab says what to do: **Download TiEmu's installer** (3 MB from SourceForge,
checked against its MD5 and SHA-256), which leaves `setup.exe` in CalcSuite's emulators folder
and shows it. Run it yourself (it's TiEmu's own installer from 2010, unsigned; CalcSuite never
runs it) and keep the folder it suggests. Then **Check again** in the tab.

The installer writes to Program Files and the registry, so TiEmu can't live inside CalcSuite's
folder like CEmu does; the download (`tiemu-3.03-win32-nogdb.zip`) holds only that installer.
CalcSuite finds the installed TiEmu through the registry (its App Paths entry or its uninstall
entry) or in Program Files.

### Opening the ROM

CalcSuite starts it as `tiemu.exe -rom=<your ROM>` (TiEmu's manual page: "Convert and use the
specified dump as image"). The first time, TiEmu turns the ROM into its own image, which takes a
moment. Your programs aren't sent for you: TiEmu takes one file at a time (right-click its
window, **Send file to TiEmu...**); the backup is in `CalcSuite files\backups`.

Not tried on a PC with TiEmu installed yet: if its window doesn't go into the tab, the tab says
so and TiEmu stays in its own window beside CalcSuite.

### TiEmu's keys

From TiEmu's key map file `skins\ti89.map` (unchanged since 2007, so the one 3.03 installs:
<https://github.com/debrouxl/tiemu/blob/master/tiemu/trunk/skins/ti89.map>). The file names
Windows keys (`PCKEY_OEM_3`, ...); here they are the keys of a US keyboard. Not checked on an
installed TiEmu yet.

| PC key | TI-89 key |
| --- | --- |
| A ... Z | the letter (alpha + its key; T, X, Y, Z are their own keys) |
| 0 ... 9 (and the number pad) | 0 ... 9 |
| + (number pad) | + |
| * (number pad) | × |
| / (number pad) | ÷ |
| - (number pad) | - |
| Up, Down, Left, Right | the arrows |
| F1 ... F5 | F1 ... F5 |
| F6 | CATALOG |
| Shift (left or right) | ↑ (shift) |
| Ctrl (left or right) | ◆ (diamond) |
| Alt | 2nd |
| Caps Lock | alpha |
| Enter | ENTER |
| Esc | ESC |
| Backspace | ← (backspace) |
| - (the minus key) | (-) (negate) |
| = | = |
| [ | ( |
| ] | ) |
| , | , |
| . (and the number pad's .) | . |
| / | ÷ |
| Space | space (alpha + (-)) |
| Backtick, left of 1 | MODE |
| \ | \| (with) |
| F9 | APPS |
| Tab | STO▸ |
| Delete | CLEAR |
| Scroll Lock | ON |
| Insert | EE |
| Page Up | ^ (power) |
| Home | HOME |

### TiEmu's menu

Right-click TiEmu's window (from TiEmu's source, `glade/popup-2.glade`; not checked on 3.03
itself): **Send file to TiEmu...**, **Link**, **Configuration** (save / load), **Calculator
state** (revert, load, save state images, **Exit and save state**), **Enter debugger**,
**Reset calc**, **Set ROM**, **Emulator options** (actual speed, LCD update), the view (normal,
large, full screen), **Skin**, **Screenshot** (now, options, copy to clipboard), key press
recording, its manual and **Exit without saving state**. Its config file's `keys_file=` setting
names the key map (TiEmu's manual page).

## Where everything is kept

Everything stays in CalcSuite's own folder (`CalcSuite files` beside CalcSuite.exe; run from
the source: `Documents\CalcSuite` and `%LOCALAPPDATA%\CalcSuite`):

| What | Where |
| --- | --- |
| Your ROMs | `CalcSuite files\backups\roms\` |
| The backups sent into the copy | `CalcSuite files\backups\` |
| CEmu itself | `CalcSuite files\cache\emulators\CEmu\CEmu.exe` |
| The tab's CEmu settings and saved state | `CalcSuite files\cache\emulators\CEmu\calcsuite\` |
| Test in PC copy's files (the last run) | `CalcSuite files\cache\emulators\CEmu\calcsuite-test\run\` |
| TiEmu's installer | `CalcSuite files\cache\emulators\TiEmu\` |
| Screenshots | `CalcSuite files\captures\` |

Two things outside it, by the emulators themselves: CEmu keeps a tiny id file per running copy
in `%LOCALAPPDATA%\cemu-dev\CEmu\id\` (how `--id` commands find it; Qt picks that folder and
CEmu 2.0 has no option to move it), and an installed TiEmu lives where its installer put it.

## Common problems

- **The tab says CEmu didn't start, or stays on "starting":** see
  `CalcSuite files\logs\errors.log`; **Try again**. A CEmu you started yourself doesn't get in
  the way (it has another id).
- **Keys do nothing:** click into the calculator first (the keyboard goes to whatever you
  clicked last). CEmu's keys are the table above, not CalcSuite's keys for the real calculator.
- **The copy says "RAM Cleared" and has no programs:** that's a fresh boot without a backup's
  files; **Start again from the backup** sends them.
- **Make a PC copy stops with "OS 5.5":** the TI-84 Plus CE's OS 5.5 and newer don't run the
  dumper.
- **A test never finishes:** the program waits for a key: add it to the keys (`enter`), or a
  longer wait. The run stops after about a minute and says so.
- **Windows' scaling above 100%:** the tab's CEmu runs in Windows' compatibility scaling then,
  so its size matches CalcSuite's window (it may look a little soft).

## Credits and licences

- **CEmu** (GPL-3.0, CE-Programming): <https://github.com/CE-Programming/CEmu>. A separate
  program: CalcSuite downloads its release, starts it with its command line and shows its
  window; none of its code is in CalcSuite. CalcSuite also sends CEmu's ROM dumper to your
  calculator (`tools/rom_dumpers/`, with its licence and source).
- **TiEmu** (GPL-2.0, the TiLP project): <https://sourceforge.net/projects/gtktiemu/>. You
  install it; CalcSuite starts it. The TI-89 ROM dumper is TiLP's (`tools/rom_dumpers/`).
- The key tables quote CEmu's wiki and TiEmu's key map file; the links are with them.
- The ROM is Texas Instruments' software from your own calculator: it stays on your PC and is
  never uploaded or shared by CalcSuite.
