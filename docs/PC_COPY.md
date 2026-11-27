# A PC copy of your calculator

CalcSuite can copy your own calculator's ROM (its built-in software) to your PC and open it in
an emulator, with your programs and variables: a second calculator on the screen, for trying
things before you send them to the real one.

```text
python -I tools/pc_copy.py make 84      back up, dump the ROM, open it in CEmu
python -I tools/pc_copy.py dump 89      back up and dump the TI-89 Titanium's ROM
python -I tools/pc_copy.py open 84      open the newest ROM again (with the newest backup's files)
python -I tools/pc_copy.py list         the ROMs made so far
```

A button in the calculator's **Info** panel and a **PC copy** tab are coming.

## What you need

| | TI-84 Plus CE | TI-89 Titanium |
| --- | --- | --- |
| Calculator | OS 5.4 or older (OS 5.5 and later don't run the assembly program the dump needs) | any AMS 3.x |
| Free memory | 66 KB of RAM, about 1.1 MB of archive | nothing special |
| Time | about 2 minutes | about 1 1/4 minutes |
| Emulator | CEmu, downloaded for you (about 19 MB) | TiEmu: you install it yourself (see below) |

Plug the calculator in, switch it on, and close the calculator's tab or window in CalcSuite (only
one program can use the calculator at a time). Don't press keys on it until CalcSuite says it's
done.

## What happens on the calculator

1. **A full backup** first, as **Back up...** makes it (`CalcSuite files\backups\<model>-<date>`).
2. **TI-84 Plus CE:** CalcSuite runs the calculator's own **Garbage Collect** (it tidies the
   archive; nothing is deleted), sends a small program, `ZZDUMP` (CEmu's ROM dumper), and starts
   it by typing its keys. The calculator shows "Dumping Segment A..." and so on for about a
   minute and writes the ROM into AppVars `ROMData0`, `ROMData1`, `ROMDataA`... CalcSuite reads
   them back and then deletes `ZZDUMP` and every `ROMData` AppVar. It also clears the home
   screen.
3. **TI-89 Titanium:** CalcSuite sends a small program, `main\romdump` (TILP's ROM dumper),
   starts it from the PC, reads the ROM over USB (the calculator shows "Done: ... KB"), then
   deletes the program.
4. CalcSuite compares what was in RAM before and after. If a crash had cleared the RAM, it says
   so, and your backup has everything to send back with **Restore...**.

CalcSuite stops before changing anything if the calculator already has something called
`ZZDUMP`, `ROMData...` (84) or `main\romdump` (89): it never deletes your own files.

## Where the files go

- The ROM: `CalcSuite files\backups\roms\ti84ce-<date>.rom` or `ti89t-<date>.rom` (4 MB),
  with a `.json` beside it (the OS version, the date, the SHA-256, which backup goes with it).
- The emulators: `CalcSuite files\cache\emulators\` (from the source: `%LOCALAPPDATA%\CalcSuite\emulators\`).

The 84's ROM holds the boot code, the OS and TI's certificate; your archived files are not in it
(they come from the backup). The 89's dump is the whole flash, archived variables included.

## The emulators

- **CEmu** (TI-84 Plus CE, GPL-3.0, <https://github.com/CE-Programming/CEmu>): `get-emulator 84`
  downloads version 2.0 from CEmu's GitHub release and checks it against the SHA-256 CalcSuite
  knows (the release publishes none; the file isn't code-signed). `open 84` starts it with the
  ROM and sends the backup's programs and variables in. CEmu is its own program: close it like
  any other window. `open 84` starts the ROM afresh each time, with the backup's files; CEmu
  keeps its own saved state when you close it, and starting CEmu by itself carries on from it.
- **TiEmu** (TI-89 Titanium, GPL-2.0): its last Windows version is 3.03, from 2010, as an
  installer on its SourceForge project. `get-emulator 89` downloads it, checks it, and leaves
  `setup.exe` in `CalcSuite files\cache\emulators\TiEmu\` for you to run if you want it.
  After that, `open 89` starts TiEmu with the ROM (TiEmu turns a `.rom` into its own image the
  first time). CalcSuite doesn't run the installer for you.

## The rules

The ROM is Texas Instruments' copyrighted software. Dump only your own calculator, keep the ROM
on your own PC, and don't share it. CalcSuite never uploads a ROM, never ships one, and never
downloads one.
