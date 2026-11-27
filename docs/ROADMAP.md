# CalcSuite roadmap

What comes after v1.0.0, roughly in order. Nothing here is promised; open an issue to vote or
suggest.

## Next (1.x)

1. **Make a PC copy of my calculator** (first after 1.0): one button that dumps your own
   calculator's ROM (TI-84 Plus CE: CEmu's ROM dumper sent and run over USB, on OS 5.4 or older,
   or 5.5+ with arTIfiCE; TI-89 Titanium: a dumper over USB, no hacks), copies your programs
   and variables in, and opens it in an emulator: CEmu for the 84 CE, TiEmu for the 89. First as
   "Open in CEmu" (CEmu as its own program), then as a tab inside CalcSuite ("TI-84 Plus CE (PC
   copy)") with the same keys, symbols, functions and Send program, at 60 frames a second with
   no lag. It is a second calculator, not a mirror: send a finished program to the real one. ROMs
   are for your own use only: CalcSuite never ships or uploads them. (The TI-Nspire CX II needs
   a jailbreak for a dump, so it isn't planned.)
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

See [CHANGELOG.md](../CHANGELOG.md).
