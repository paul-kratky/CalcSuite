# CalcSuite roadmap

What comes next, roughly in order. Nothing here is promised; open an issue to vote or suggest.

## Next

1. **The PC copy as a tab** ("TI-84 Plus CE (PC copy)", and the TI-89 Titanium's): the
   emulator's core inside CalcSuite with the same keys, symbols, functions, editor and Send
   program, at 60 frames a second with no lag. It is a second calculator, not a mirror: send a
   finished program to the real one. The 84 uses CEmu's core; the 89 uses TiEmu (2010) if it runs
   well with your ROM on Windows 11, otherwise our own modern build of TiEmu's engine. Plan:
   [docs/dev/PC_COPY_API.md](dev/PC_COPY_API.md), "Phase 2".
2. **TI-Nspire CX II PC copy (optional, for Ndless users):** Firebird (GPL-3) emulates the CX II
   but needs the calculator's boot code, which can only be dumped with the Ndless jailbreak
   (you install Ndless yourself; it supports OS 6.4.0.74). CalcSuite would then run Polydumper,
   keep the dump with your backups and open the Nspire in Firebird, later as a tab. CalcSuite
   never installs Ndless for you, and never ships or uploads ROMs.

## Later

- **TI-84 Evo** (2026), once its file format is documented.
- **Mac and Linux:** the link tools already build there; the window would need a new toolkit
  (Tauri is the likely one) or a web version using WebUSB.
- **Sponsor link** in the app and on the repo.
- **Built-in AI help** (your own API key, off by default). Until then: the editor's "Copy AI
  instructions" and "Copy problems for the AI" work with any chat AI.

## Not planned

- **Voyage 200 / TI-92 Plus:** they have no USB port, only TI's old link port, which needs TI's
  Silver/Direct USB link cable. Dropped until someone has one to test with.

## Done in 1.0

- **Make a PC copy of my calculator:** dumps your own calculator's ROM (TI-84 Plus CE: CEmu's
  ROM dumper sent and run over USB, on OS 5.4 or older; TI-89 Titanium: TILP's dumper over USB,
  no hacks), after a backup, and opens it in CEmu (the 84) with your programs and variables.
  See [docs/PC_COPY.md](PC_COPY.md).
- **Fast mode for the TI-84 Plus CE** (experimental): about 6.5 frames a second on the home
  screen instead of 0.8 ([docs/dev/FAST84_PLAN.md](dev/FAST84_PLAN.md)).
- **A sturdier TI-Nspire link:** a lost packet costs seconds, not minutes.
- **Release builds on GitHub:** CI builds the helpers, the app and the PDFs, and drafts the
  release.

See [CHANGELOG.md](../CHANGELOG.md) for everything else.
