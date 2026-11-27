# CalcSuite roadmap

What comes after v1.0.0, roughly in order. Nothing here is promised; open an issue to vote or
suggest.

## Next (1.x)

1. **The PC copy as a tab** ("TI-84 Plus CE (PC copy)"): CEmu's core inside CalcSuite with
   the same keys, symbols, functions and Send program, at 60 frames a second with no lag. It is
   a second calculator, not a mirror: send a finished program to the real one. Plan:
   [docs/dev/PC_COPY_API.md](dev/PC_COPY_API.md), "Phase 2". (The dump and "Open in CEmu" are
   done: see below.)
2. **Fast mode for the TI-84 Plus CE screen.** About 5-10 frames a second instead of about 1: a
   small add-on on the calculator compresses the screen, and CalcSuite reads the compressed copy.
   On OS 5.4 or older, or 5.5+ with arTIfiCE; it backs up first. Plan:
   [docs/dev/FAST84_PLAN.md](dev/FAST84_PLAN.md).
3. **Faster TI-Nspire link:** keep the screenshot service open between frames and send keys
  without reconnecting each time (docs/dev/SPEED_RESEARCH.md), and fix a rare stall in
  `cx2_resume.cpp` (`readPacket` checks the checksum over the last piece only).
4. **Release builds on GitHub:** CI builds the helper programs (nspire-cli, ti84-cli, the driver
  helper) and the app, so every release's downloads come straight from the CI.

## Later

- **TI-84 Evo** (2026), once its file format is documented.
- **Mac and Linux:** the link tools already build there; the window would need a new toolkit
  (Tauri is the likely one) or a web version using WebUSB.
- **Sponsor link** in the app and on the repo.

## Not planned

- **Voyage 200 / TI-92 Plus:** they have no USB port, only TI's old link port, which needs TI's
  Silver/Direct USB link cable. Dropped until someone has one to test with.

## Done in 1.0

- **Make a PC copy of my calculator:** dumps your own calculator's ROM (TI-84 Plus CE: CEmu's
  ROM dumper sent and run over USB, on OS 5.4 or older; TI-89 Titanium: TILP's dumper over
  USB, no hacks), after a backup, and opens it in CEmu (the 84) with your programs and
  variables. The 89's emulator, TiEmu, has only a 2010 installer for Windows: you install it
  yourself. ROMs are for your own use only: CalcSuite never ships or uploads them. (The
  TI-Nspire CX II needs a jailbreak for a dump, so it isn't planned.) The window's button is
  still to come. See [docs/PC_COPY.md](PC_COPY.md).

See [CHANGELOG.md](../CHANGELOG.md) for everything else.
