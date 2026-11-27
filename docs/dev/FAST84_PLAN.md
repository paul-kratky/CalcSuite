# CalcSuite: faster TI-84 Plus CE mirroring, and leaving Press-to-Test from the PC

## What was built (2026-11-27): Fast mode, approach A with changes

Bench: TI-84 Plus CE, OS 5.4.0, Windows 11, backed up first (no crash, no RAM clear in any test).

**Calculator side**: `tools/fast84/csfast.asm` (MIT, plain eZ80, fasmg + the CE toolchain v14.2's
`commands.alm`/`ez80.alm`; no toolchain library is linked). `CSFAST.8xp` and its `.sha256` are
committed; `tools/fast84/build.py` (also run by `tools/build_tools.py`, skipped when fasmg isn't
there) rebuilds it byte for byte; the self-test checks both.

- CSFAST is a toggle. On: the hook's code goes into the archived AppVar **ZZHOOK** (reused when
  it's already there byte for byte; refused when the archive would need a garbage collect),
  then RAM AppVars **CSSNAP** (2048 B), **ZZWORK** (3584 B) and as many **ZZSNPA..ZZSNPH**
  (4096 B each, at most 8) as leave 16 KB free; it sets the **raw key hook** (rawKeyHookPtr,
  hookflags2 bit 5). It refuses when another program's raw key hook is on. Off: the hook and
  every one of those variables are removed.
- Not a timer: frames are **on demand**. The PC presses key code **0x22** (full frame) or
  **0x23** (changed rows only) with the normal remote-key command; codes 0x21-0x24 do nothing
  on OS 5.4 without the hook (tested; 0x7D/0x7E, the first idea, open CALC menus). The raw
  key hook swallows them, so the calculator spends nothing when nobody's mirroring.
- Taken inside key handling, a picture always had the busy indicator and never the cursor. So
  the trigger only **arms a one-shot GetCSC hook**, which takes the picture the next time the
  OS waits for a key, then puts back the GetCSC hook that was there (OS 5.4 has its own, at
  0x066FC9) and calls it. The key's acknowledgement comes after the picture, so the PC's next
  request always sees it. 0x24 takes it at once from the raw key hook (the fallback).
- The hook copies itself into ZZWORK and runs from RAM (from the archive a frame took ~350 ms).
  Each row is first checksummed (Fletcher over 24-bit words read with `pop`, interrupts off
  for ~0.2 ms a row; SP and IX come back through self-modified code); only rows whose checksum
  changed are packed as runs (u8 count-1, u16 colour; two 160-pixel halves).
- Torn frames: seq_begin/seq_end in the header plus a seq stamp at the end of CSSNAP and at both
  ends of every chunk. The format is at the top of `csfast.asm`; `tools/fast84/csnap.py` is the
  reference decoder (and the self-test's encoder).
- The hook never creates, deletes or resizes a variable (the home screen's edit buffer lives in
  free RAM: a VAT change from a hook could break it), saves and restores OP1, keeps IY.

**PC side**: `ti84-cli` `snap FILE [full]` (a delta when it holds the previous frame, a full
frame every 10 s anyway; on any problem it prints `FAST fallback <why>` or `FAST gone <why>`
and does a normal `shot`), `fast status|on CSFAST.8xp|off [CSFAST.8xp]` (status:
`INFO fast=on|stale|off`; on: refused on OS 5.5+, sends CSFAST, types Quit Clear Clear prgm C S
F A S T Enter, checks that frames come; off: runs CSFAST if the hook may be on, then removes
what's left, our names only). `mirror.py`: `Mirror.set_fast(on, done=None)`,
`Mirror.fast_status()` -> `{supported, why, state, note, on}` (state off | starting | on |
stopping | lost | error), `Mirror.fast_supported()`, `Mirror.fast_listeners` (fn(state, note),
called on the link thread). With state "on" the link loop uses `snap` and a 0.15 s typing
hold-off instead of 0.6 s; `FAST gone` (a RAM reset) sets "lost" and goes back to `shot`.
Closing the app leaves Fast mode on the calculator (safe: three key codes the keypad never
sends); turning it off is an explicit action.

**Measured** (OS 5.4.0, the Mirror link loop run headless):

| Screen | Normal `shot` | Fast mode |
| --- | --- | --- |
| Still home screen | 0.90 fps | **6.67 fps** (a delta: trigger ~115 ms incl. ~25 ms OS, CSSNAP read 36 ms) |
| Typing (1+2 Enter Clear, a key every ~0.6 s) | 0.79 fps, key to picture 2.2 s median | **4.6 fps**, key to picture **0.32 s** median (0.59 s max) |
| Graph screen | 0.90 fps | 0.83 fps: normal screenshots (see below), the graph stays on screen |
| Full frame (the first, then every 10 s) | | ~0.35 s (home screen 4.1 KB: CSSNAP + 1 chunk) |

The calculator's own keypad works as before with Fast mode on (the raw key hook adds three
compares per key). CPU: only when the PC asks (~90 ms per still frame, ~225 ms per full
frame); nothing while not mirroring.

**Home screen only.** Any variable request (`get`, even `ls`) from the graph, table, Y=, mode
or window screen makes TI's OS leave that screen for the home screen (measured; menus such
as MATH, PRGM and the catalog stay). So the hook makes a picture only when cxCurApp is the
home screen (kQuit); elsewhere it swallows the trigger at once, `snap` sees the key answered
in under 55 ms (a picture takes 90 ms or more), reads nothing, prints `FAST away` and takes a
normal shot. `fast status|on|off` list the variables, so they also bring the calculator home.

**Bench notes**: the hook survived the calculator's auto power-off (APD) with Fast mode on;
closing the mirror in the middle of a `snap` (Mirror.stop) left the calculator working; `fast
off` left the variable list identical to the one before the first test.

**Risks left**: a garbage collect of the archive moves ZZHOOK while the hook pointer stays (the
OS skips a hook whose first byte isn't 83h, so most likely the hook just stops; CalcSuite then
says Fast mode is lost: turn it off and on). An app or shell that takes the raw key hook stops
Fast mode the same way. Not bench-tested yet: apps (Python), table/catalog in every mode, APD
while on, a RAM reset while on (the code path exists).

---

The research below came first (2026-11-27, before anything was built).
Confidence: **High** means a primary source (code or TI documentation) says so. **Medium** means it
follows from sources but nobody has tested it on this hardware. **Low** is my inference.

What exists today (read from the source):
- `tools/ti84_cli/ti84_cli.c` (GPL-3.0-or-later, our own DUSB on libusb). Raw packets go up to 1023
  bytes, each with an ACK. `PARM_REQ 0x0022` gives a screenshot: the CE sends 153600 bytes of RGB565
  LE. A key is `VPKT_EXECUTE 0x0011` with data `00 00 03 hi lo`. We also have `ls`/`get`/`send`/`put`/`rm`
  (VAR_REQ, RTS ...), and `param_request()` works for any PID.
- `tools/nspire_cli/nspire_cli.c` (GPL-3.0-or-later, links libnspire). `cx2_resume.cpp` is a changed copy of
  libnspire's CX II NNSE transport. A key press already uses the libnspire internals for a service
  that libnspire's API doesn't cover: `service_connect(h, 0x4042)`, then `data_write()`, then
  `service_disconnect()`. The PTT exit below uses the same pattern.
- The CalcSuite repo is MIT. The two CLIs are GPL-3.0-or-later.

---

## Part 1: Faster TI-84 Plus CE screen mirroring

### 1.1 Calc2KeyCE sends the picture the other way (High)

Source: https://github.com/dnmalenke/Calc2KeyCE (licence **MIT**, author David Malenke). I read
`Calc2KeyCE.Calc/src/main.c`, `makefile`, `Calc2KeyCE.Fast/sender.cpp` and `main.cpp`.

- **It mirrors the PC screen onto the calculator, not the calculator onto the PC.** The README says
  "cast your screen to your calculator's screen". The PC captures its desktop with DXGI desktop
  duplication, quantises it to 256 colours (leptonica octree), compresses with **zx0** and sends it.
  The calculator unpacks it into VRAM in **8bpp palette mode**: `lcd_Control = 0b00000100000100111`,
  with the palette in `lcd_Palette`. It double-buffers by flipping `lcd_UpBase`. The only data the calc
  sends back is 7 bytes of keypad matrix (`kb_Data[1..7]`), at most 16 times a second.
- The 1–4 fps reports (~2.3 fps for a 1080p desktop, ~4 fps after v1.4.0 moved to zx0) are for that
  PC→calc direction. They don't tell us how fast calc→PC could go.
- How it works on the calculator: a CE C toolchain program that uses **usbdrvce** and takes over the
  USB controller as its own USB device.
  - Device descriptor: VID `0x0451` PID `0xE009`, bcdDevice 0x0240, EP0 64 bytes.
  - Configuration: one interface, class `0xFF/0x01/0x01`, bulk IN `0x81` (64 B) and bulk OUT `0x02` (64 B).
  - `[on]` exits the program. On exit it restores 16bpp (`lcd_Control = 0b00000100100101101`) and
    calls `usb_Cleanup()`.
  - It uses pixelShadow as BSS/heap (`BSSHEAP_LOW = D031F6`) and clears it on exit. The README says
    "Make sure to backup ram before running".
- PC side: C++ on libusb. It installs WinUSB for 0451:E009 itself with **libwdi** (LGPL, shipped as a
  .lib), the same thing Zadig does. It sends in 64-byte `libusb_bulk_transfer` calls, which is slow.
- What we could reuse: little beyond the pattern (usbdrvce device mode with custom descriptors, plus a
  libusb bulk loop). The MIT licence would allow it, but its calculator program receives the screen and
  ours would have to send it.

### 1.2 What the hardware allows (High / Medium)

- **The CE's USB is full speed only (12 Mb/s).** usbdrvce.h (CE-Programming/toolchain,
  `src/usbdrvce/usbdrvce.h`) defines only `USB_SPEED_FULL` and `USB_SPEED_LOW`. Its note on
  `usb_GetFrameNumber` says "If the hardware supported [high] speed usb, the lower 3 bits would be the
  microframe number". So bulk endpoints are 64 bytes, and the ceiling is 19 packets per 1 ms frame:
  about **1.2 MB/s in theory, ~0.8–1.0 MB/s in practice** (Medium; I found no published CE
  benchmark). usbdrvce splits large transfers into 64-byte packets itself and uses the controller's DMA
  (commandblockguy, Cemetech p=285815).
- Today's DUSB link: 153600 B in ~1.3–1.4 s, about **110–120 KB/s**. The limit is in the OS's per-packet
  handling (~9 ms per 1018-byte packet with an ACK each). It is not the wire.
- A full 16bpp frame at ~0.9 MB/s would be ~6 fps raw. Sending only changed rows plus RLE would give
  20–30 fps while typing, if the calculator owned the USB port.

### 1.3 The catch: a standalone streamer can't show the OS (High)

While an ASM/C program runs, the TI-OS is suspended. A Calc2KeyCE-style program that owns USB can
stream only what **it** draws. The home screen, graph, menus and catalog don't run underneath it, and
keys go to the program, not to the OS. So "send a program, run it, it streams frames and accepts key
presses until exit" gives a fast mirror of nothing useful, unless we rewrite the calculator UI.

To mirror the real OS faster, our code has to run **inside** the OS, as an OS hook. Two ways:

| Approach | How | Speed | Risk / effort |
| --- | --- | --- | --- |
| **A. Hook + DUSB variable (recommended)** | A resident GetCSC hook compresses VRAM into a RAM AppVar. The PC fetches that AppVar with the DUSB variable request we already have (`get`). Keys stay on DUSB execute. The OS USB stack is never touched. | Limited by the OS's ~110 KB/s plus ~30–60 ms per request. A compressed home screen is a few KB, so **~5–10 fps** on text screens and **~2–4 fps** on busy graphs (Low/Medium estimate) | Medium. Only memory work in the hook. A bad hook can crash the calc, and a crash means a RAM clear. 1.5–2.5 weeks |
| B. Hook + its own USB (usbdrvce inside the OS) | The hook tears down the OS USB, runs usbdrvce, streams and receives keys, and returns scancodes from the GetCSC hook | ~20–30 fps | High. usbdrvce's header warns that the OS corrupts its state if timer-3 interrupts run. A library must stay resident while the OS runs. DUSB (files, keys) is gone while it runs. Re-enumeration needs a second WinUSB binding. Weeks, crash-prone. **Not recommended** |
| C. Standalone usbdrvce program (Calc2KeyCE style) | Program owns USB until [on] | ~20–30 fps | Easy (3–5 days), but it only shows its own screen (see above). Useful only as a throughput test bench |

### 1.4 Design: "Fast mode" = approach A

**Calculator side**: a native program `CSFAST` (pure eZ80 asm with spasm-ng or fasmg, or CE C
without the LGPL libs) that installs a hook. It is not a resident loop.

1. The installer, run once:
   - Copies the hook body into an **archived AppVar** `CSHOOK`. Flash addresses stay put until a
     garbage collect, and the installer checks this every time it runs.
   - Creates a RAM AppVar `CSSNAP` of fixed size (e.g. 24–32 KB, the user's choice; ~150 KB of RAM is
     free on a CE).
   - Installs the hook with the OS's GetCSC-hook call (`_SetGetCSCHook`; the hook body must start with
     byte `0x83`, the TI hook convention).
   - Returns to the home screen at once. Running it again with the hook already installed removes it
     (a toggle). A RAM clear removes the hook too.
2. The hook, called every time the OS scans keys (constantly in the home/graph/menu idle loops):
   - It throttles itself: at most one snapshot every ~100 ms (CPU cycle counter), so the OS stays
     responsive.
   - It finds `CSSNAP` again each time with `_ChkFindSym`, because RAM variables move when others
     (Ans, lists) are created or resized. It never resizes or creates variables inside the hook.
   - It reads `lcd_UpBase` (normally `0xD40000`, 16bpp 320×240).
   - It writes the frame in this layout:

     ```
     0  'C''S''N''1'   magic + format version
     4  u16 seq_begin  written FIRST
     6  u16 seq_end    written LAST (PC rejects the frame if seq_begin != seq_end: torn)
     8  u8  kind       0 = RLE16 full frame, 1 = "too big, use the normal screenshot"
     9  u8  flags
     10 u16 rows_changed_bitmap_len / reserved
     12 u24 payload length
     15 payload:       RLE16 runs (u8 count-1, u16 colour LE), row-major
     ```

   - Optional cheapening: keep one u16 checksum per row (480 bytes) and skip the publish entirely when
     no row changed. Cost: one pass over 153600 B is ~1.5 M cycles, about 30 ms at 48 MHz in tight asm.
   - If RLE overflows the AppVar: write `kind = 1`. The PC then takes one ordinary `PARM_REQ 0x0022`
     shot.
3. Later optimisation, a demand trigger: the PC sends a keycode the OS doesn't use via the existing
   execute-key command. A GetKey or raw-key hook catches it, takes a snapshot and swallows the key.
   This avoids snapshots nobody fetches and allows delta frames (changed rows only), because the PC
   then always holds the base frame. Needs a bench test: do DUSB remote keys pass through those hooks?
   (Unverified.)

**Launching it remotely** (only once per RAM clear, since the hook stays resident):

- First choice: DUSB **execute program**, the libticalcs `dusb_cmd_s_execute` layout (tilibs
  `dusb_cmd.cc`). `VPKT_EXECUTE (0x0011)` with data
  `00 | len(name) | name bytes | 00 | action`, where action is `01` (`DUSB_EID_ASM`) or `00`
  (`DUSB_EID_PRGM`).
  - Example: `CSFAST` becomes `00 06 43 53 46 41 53 54 00 01`.
  - The raw frame is `00 00 00 10 04 | 00 00 00 0A 00 11 | 00 06 43 53 46 41 53 54 00 01`.
  - libticalcs lists `execute` for the CE models. Whether OS 5.4 really runs an ASM program this way
    is **unverified**, so test it once.
- Fallback by keys, with our codes from `ti84_keys.py`:
  - `clear` 0x09, `prgm` 0x2D, then the letter key to jump to the first program starting with that
    letter in the EXEC list, then `enter` 0x05 (pastes `prgmCSFAST`), then `enter` 0x05 (runs it).
  - On OS 5.3+ an ASM program runs straight from `prgmNAME` (community-reported; **verify on 5.4.0**).
    Otherwise type `Asm(` from the catalog first (`catalog` 0x3E, then navigate).
- **Exit**: run `CSFAST` again (toggle). Or the PC calls the same execute with an argument. A RAM reset
  also removes it.

**PC side**: a mode in `ti84-cli serve`, not a new helper, because it reuses the same DUSB session.

- `fast on|off|status`:
  - `status` reads OS version (PID 0x000B), then `ls` to look for `CSSNAP`/`CSHOOK` and check the
    magic.
  - `on` sends `CSFAST.8xp` with the existing `send` if it's missing, then launches it.
- `snap FILE`: a `get` of AppVar `CSSNAP` into memory, a torn check (`seq_begin == seq_end`), a
  sequence check (has it advanced?), then RLE16 decoded to PPM. On `kind=1`, a torn frame or a missing
  var, it falls back to `shot`.
- `mirror.py` uses `snap` in place of `shot` when `fast status` says active. `shot_holdoff` can drop
  for the CE, because a snap takes ~0.1 s, not ~1.4 s.
- **How the PC detects the mode:** the AppVar is there, the magic is right and `seq` is moving.
  Nothing re-enumerates, so the VID:PID stays 0451:E008 and no new driver is needed.

**OS 5.5 and later** (High that ASM is blocked):

- The OS refuses native programs, so the PC sees OS ≥ 5.5.0 in `info` and hides Fast mode. Mirroring
  falls back to `PARM_REQ` at ~0.8 fps.
- The arTIfiCE jailbreak can re-enable native code until reboot on some 5.5+ versions. Don't build on
  it.
- Press-to-Test also disables programs and hooks, so Fast mode is off in PTT.

**Effort estimate**:

| Work | Time |
| --- | --- |
| Calculator asm (installer, hook, RLE, checksum skip) | 4–7 days |
| ti84-cli `fast`/`snap`, the decoder, `mirror.py` integration | 1–2 days |
| Bench testing every screen (home, graph, table, menus, catalog, Python app, APD/off, RAM clear, archive garbage collect) | 2–3 days |
| **Total** | **~1.5–2.5 weeks** |

Back up RAM before the first tests: a hook bug means a RAM clear.

**Licences**: our own asm/C is MIT- or GPL-clean. The CE toolchain is LGPL-3.0 (its libc/graphx and
the usbdrvce/LibLoad libraries). Approach A needs none of the libs, so writing the hook in plain asm
avoids LGPL obligations. Calc2KeyCE is MIT. Its libwdi is LGPL; we don't need it, because the existing
Zadig/WinUSB binding for E008 is enough under approach A.

### 1.5 Can the normal DUSB path be sped up? No (High)

- On the CE, `PARM_REQ 0x0022` gives exactly 153600 bytes of raw RGB565. libticalcs `calc_84p.cc`
  `recv_screen` accepts only that size for `CALC_TI84PCE_USB`.
- TILP's "RLE screenshot" (`ticalcs_screen_84pcse_rle_uncompress`) is the **84 Plus C SE** format (OS
  4.x). The CE OS doesn't produce it, and no PID asks for it.
- The colour-depth, bpp and LCD size PIDs (0x001B–0x001F) are read-only information. No PID gives a
  partial screen or a lower depth. `DUSB_PID_HOMESCREEN 0x0037` is a set command (go to home), not a
  text dump.
- The raw packet ceiling is 1023 bytes, and every raw packet must be ACKed before the next. So there's
  no pipelining, and the ~9 ms per packet on the calculator stays.

---

## Part 2

Not included in this write-up.
