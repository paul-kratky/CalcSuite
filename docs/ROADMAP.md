# CalcSuite roadmap

What comes after v1.0.0, roughly in order. Nothing here is promised; open an issue to vote or
suggest.

## Next (1.x)

- **Fast mode for the TI-84 Plus CE screen.** About 5-10 frames a second instead of about 1: a
  small add-on on the calculator compresses the screen, and CalcSuite reads the compressed copy.
  Only on OS 5.4 or older (OS 5.5+ blocks the add-on); it backs up first. Plan:
  [docs/dev/FAST84_PLAN.md](dev/FAST84_PLAN.md).
- **Dump ROM** for the TI-89 Titanium and the TI-84 Plus CE (OS 5.4 or older): a copy of the
  calculator's own operating system, saved with your backups, for running your calculator in an
  emulator on the PC. For your own use only: CalcSuite never ships or uploads ROMs. (The
  TI-Nspire CX II needs a jailbreak for this, so it isn't planned.)
- **PC calculator mode:** run an emulator (TiEmu for the 89, CEmu for the 84 CE) with your own
  ROM, as a separate program CalcSuite starts. Zero lag, nothing plugged in. It is a second
  calculator, not a mirror: files don't sync by themselves.
- **Faster TI-Nspire link:** keep the screenshot service open between frames and send keys
  without reconnecting each time (docs/dev/SPEED_RESEARCH.md), and fix a rare stall in
  `cx2_resume.cpp` (`readPacket` checks the checksum over the last piece only).
- **Release builds on GitHub:** CI builds the helper programs (nspire-cli, ti84-cli, the driver
  helper) and the app, so every release's downloads come straight from the CI.

## Later

- **Voyage 200** (and the TI-92 Plus): the same link as the TI-89.
- **TI-84 Evo** (2026), once its file format is documented.
- **Mac and Linux:** the link tools already build there; the window would need a new toolkit
  (Tauri is the likely one) or a web version using WebUSB.
- **Sponsor link** in the app and on the repo.

## Done in 1.0

See [CHANGELOG.md](../CHANGELOG.md).
