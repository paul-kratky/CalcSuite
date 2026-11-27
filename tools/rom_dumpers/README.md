# ROM dumpers (GPL programs that run on the calculator)

`tools/pc_copy.py` sends one of these to the user's own calculator, runs it, and deletes it
afterwards. They are separate programs, not part of CalcSuite's MIT code: CalcSuite only sends
them as files. Each one is here byte for byte as its project publishes it, with its source
and licence. Fetched 2026-11-27. No ROM is in this folder or anywhere in the repository.

| File | What | Source | Licence |
| --- | --- | --- | --- |
| `cemu_dump.8xp` | CEmu's TI-84 Plus CE ROM dumper (program `DUMP`, 298 bytes; CalcSuite sends it as `ZZDUMP`). Copies the boot code and OS and the certificate sector into AppVars `ROMData0`, `ROMData1`, `ROMDataA`... | <https://github.com/CE-Programming/CEmu>, `gui/qt/romselection.cpp`, array `dumper_program[]`, commit `dd38ccec41cf201dcd360b2928f6db301cfbe9da` (2026-11-11) | GPL-3.0-or-later (`LICENSE.CEmu.txt`, `COPYING.GPL-3.txt`) |
| `cemu_dump.asm` | Its source (fasmg, CE toolchain includes), the comment at the end of the same file | same | same |
| `romdump_89t.89z` | TILP's ROM dumper "1.02 USB" for the TI-89 Titanium (`main\romdump`, 1427 bytes). Answers libticalcs' dump protocol over USB | <https://github.com/debrouxl/tilibs>, `libticalcs/trunk/src/rom89t.h`, commit `6dba390e7390c4b98ae96287b39a3971c331fbef` (2026-09-07) | GPL-2.0-or-later (`COPYING.GPL-2.txt`) |
| `romdump_89t_src/` | Its source: `romdump.c`, `romdump.h`, `dusb.h`, `usb.txt`, `Makefile.am` (target `romdumpu.89z`, built with TIGCC) | `libticalcs/trunk/src/romdump_9x/`, same commit | same |

SHA-256: `cemu_dump.8xp` `bb86acb9d0624d1828615dfd2227b82c144fd96614741dc876cb04bca2a98c2e`,
`romdump_89t.89z` `bca398ecd10451a469ef22ca060dcaa517fc634017acefcaa32816e77b38421f`
(`pc_copy.py` checks both before sending).
