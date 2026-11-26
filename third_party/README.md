# Third-party code

Each project sits in its own folder, unmodified. Our own build glue lives in `tools/`
(`tools/build_tools.py`, `tools/nspire_cli/`). The built programs are in `tools/bin/`.
Fetched 2026-11-26.

| Folder | What | Source | Exact version | Licence |
| --- | --- | --- | --- | --- |
| `luna/` | Luna: converts `.py` (and Lua/XML) to TI-Nspire `.tns` documents | <https://github.com/ndless-nspire/Luna> (git clone) | commit `a9924a9a968954eba9adcc161a58ac607f97ce8c` (master, 2024-09-24; `git describe`: `v2.1-16-ga9924a9`) | MPL-1.1 (`luna/LICENSE`); bundles a modified MiniZip (zlib licence) and Eric Young's DES code (BSD-style, see `DES.h`) |
| `libnspire/` | libnspire: USB link library for TI-Nspire, including the CX II (NNSE) handshake | <https://github.com/Vogtinator/libnspire> (git clone) | commit `7d7d962ca49ff9017f6f146336c51ef7f2edf4e0` (master, 2022-11-26) | GPL-3.0-or-later (licence header in every source file, `libnspire/COPYING`); the repo also ships `COPYING.LESSER`, and GitHub labels it LGPL-3.0. We treat it as GPL-3.0-or-later. |
| `libusb-1.0.30/` | libusb Windows binaries (we use `MinGW64/static/libusb-1.0.dll.a`, `MinGW64/dll/libusb-1.0.dll`, `include/libusb.h`) | <https://github.com/libusb/libusb/releases/tag/v1.0.30> asset `libusb-1.0.30.7z` | v1.0.30 (2026-05-17). SHA-256 of the archive `7fb1dfec805b97983763d7d0ae244320da12add1003d4249c96cc4d586398c79`. GPG signature `libusb-1.0.30.7z.asc` checked: good signature from the release key `C681 8737 9B23 DE9E FC46 651E 2C80 FF56 C683 0A0E` (Tormod Volden), as listed in the release's `SIGNING_KEYS.txt` and the repo's `KEYS` file. | LGPL-2.1-or-later |

## Why these and not others

- **Luna, master rather than the v2.1 release.** The v2.1 tag (2022-10-02, commit
  `ba72c66`) has no Python support: `.py` input arrived later in commit `2eafdcb`
  ("Add support for Python scripts"), with follow-up fixes up to `a9924a9`. The README
  at that commit says "Python scripts require CX II OS 5.2 or later". The GitHub
  release has no Windows download (its Windows CI artifact has expired), so we build it.
- **libnspire for USB.** It speaks the CX II's protocol (product ID `0451:e022`,
  "Improve reliability of the CX II handshake", 2020). N-Link
  (<https://github.com/lights0123/n-link>, GPL-3.0) is built on a copy of the same
  library and states that CX II models need no extra driver on Windows, but its
  command line is Linux/macOS only ("CLI on Windows" is on its to-do list) and its last
  release is v0.1.6 (2021). TiLP / libticalcs (<https://github.com/debrouxl/tilibs>,
  checked at master commit `6dba390`, 2026-09-06) only knows the older Nspire product ID `0xE012`, not the
  CX II. So we build libnspire with a small CLI of our own (`tools/nspire_cli/`).
- **TI's own tools** stay as the manual fallback: TI-Nspire CX II Connect is a Chrome
  web app (WebUSB) that you drive by hand, and TI-Nspire Student/Teacher Software has
  no documented command line for sending files, so neither can be scripted.
- **libusb official binaries** rather than MSYS2's package, so nothing in MSYS2 had to
  be installed or changed.

## Our build glue (not changes to the projects above)

- `tools/nspire_cli/compat/config.h` stands in for the `config.h` that libnspire's
  `./configure` would generate (just `ENDIAN_LITTLE`).
- `tools/nspire_cli/compat/arpa/inet.h` maps `<arpa/inet.h>` to `<winsock2.h>` for
  `cx2.cpp` (byte-order helpers only).
- `tools/build_tools.py` compiles with `-mno-ms-bitfields` so libnspire's packed
  structs get GCC's layout on MinGW.
- `tools/nspire_cli/nspire_cli.c` is our CLI. It links libnspire, so `nspire-cli.exe`
  is GPL-3.0-or-later as a whole. libusb is linked dynamically (`libusb-1.0.dll` next to
  the exe), as its LGPL expects.
- Known libnspire quirk worked around in the CLI: `nspire_file_read()` does not bound
  its copy by the buffer size, so the CLI checks the file size with `nspire_attr()`
  before reading a file back.

Toolchain used: MSYS2 UCRT64 GCC 16.2.0 with its zlib 1.3.2 (already installed on this
PC, nothing added). Rebuild with `python -I tools/build_tools.py --force`.
