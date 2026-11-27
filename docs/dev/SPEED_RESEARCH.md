# Calc Mirror: making frames faster and typing snappier

Repo: `C:\nspire-python` (I only read it; no USB was opened). Line numbers refer to the current files.

## TL;DR, ranked

| # | Change | Calc | Expected gain | Effort | Risk |
|---|---|---|---|---|---|
| 1 | **Typing first:** while keys are arriving, hold off the next screenshot (about 0.6 s after the last key). Send each key as soon as it is typed. | 84 CE (and the Nspire, with a smaller hold-off) | A key goes out in about 20 ms instead of waiting up to 1.4 s behind a screenshot | Small (mirror.py) | None |
| 2 | **Drop the blind sleep on DELAY_ACK** in `vpkt_recv` and just block on the next read | 84 CE | Keys: measured 172 ms each, probably much less after this (needs measuring) | 3 lines | Low |
| 3 | **Show typed keys at once** as an overlay strip ("typed: s i n ( 3 0") that clears when a frame taken after those keys arrives | both | Instant visual feedback | Small | None |
| 4 | **Add timing output** (`T` lines) to both CLIs, per protocol phase, before tuning anything else | both | Tells you where the time goes | Small | None |
| 5 | **Nspire: keep the 0x4024 screenshot service open** between shots; disconnect only when keys or a put need the link | CX II | Saves at least one round trip, plus any service setup/teardown on the calc, per frame | Medium | Must be tested: the calc may refuse a second `00` on one connection |
| 6 | **Nspire keys: send `01 00 00 80` once per connection**, then only the 26-byte packet for each key | CX II | About half the round trips per key | Small | Test it |
| 7 | **Fix the `cx2_resume.cpp` readPacket checksum bug** and cut the 60 s per-packet timeouts | CX II | Removes rare long stalls ("sometimes a key takes ages") | Small | None |
| 8 | **The USB scanner must not `libusb_open` the calculators** every 3 s | both | Removes a race that can take the device away from `serve`, plus a process start every 3 s | Small | None |
| 9 | Skip unchanged Nspire frames (compare the RLE bytes); binary stdout instead of the temp .ppm; reuse one PhotoImage | CX II | PC CPU only. These are **not** the bottleneck (about 6 ms of a 100 ms frame, measured below) | Small | None |
| 10 | 84 CE: async libusb with an IN transfer always queued and the ACK sent straight away | 84 CE | Maybe 10-20% per frame, only if item 4 shows host turnaround matters | Medium | Low |

**Verdict on the 84 CE frame rate:** DUSB has no faster screen path. There is no partial, compressed or lower-depth screenshot, the 1018-byte raw packet size is the calc's own limit, and every raw packet is stop-and-wait. The calculator itself is the bottleneck: about 9 ms per 1 KB packet, against about 0.9 ms of wire time. Expect about 1 fps at best, so put the effort into typing latency (items 1-3).

**Verdict on emulators:** they are possible for all three calculators with your own dumps, but an emulator is **a different calculator** with its own memory. It suits "a PC calculator", not "mirror my handheld". Details are in section 4.

---

## 1. TI-84 Plus CE: is there a faster screen path?

### What the protocol allows (evidence)

- **Screenshot = one PARM_REQ for PID 0x0022.** The CE answers with exactly 153600 bytes of raw RGB565. TILP accepts nothing else for the CE: `calc_84p.cc` `recv_screen`, case `CALC_TI84PCE_USB` (`if (size == TI84PC_ROWS * TI84PC_COLS * 2)`, local copy lines ~176-187). The RLE path exists only for the 84+ C Silver Edition (`ticalcs_screen_84pcse_rle_uncompress`, same function). The CE has **no compressed mode**.
- **PID 0x0039 `DUSB_PID_SCREEN_SPLIT`** is the "Screen split mode" setting (MODE's Horiz/G-T split), not a partial capture (`dusb_cmd.h` line ~96, `dusb_cmd.cc` table line 92). The PID table also has no region, dirty-rect, row or bit-depth parameter. `0x001C`/`0x001D` (colour depth, bits per pixel) are read-only facts (`dusb_cmd.h` comments ~56-60). Source: https://github.com/debrouxl/tilibs/blob/master/libticalcs/trunk/src/dusb_cmd.h
- **Raw packet size: 1018 is the CE's practical limit.** TILP clamps the BUF_ALLOC answer: `dusb_vpkt.cc` 266-270, "The 83PCE/84+CE allocate more than they support. Clamping buffer size to 1018". It also warns if the CE ever sends a raw packet larger than 1018 (`dusb_rpkt.cc` 158-161). So the CE never sends more than 1018. Our `ti84_cli.c` line 281 does the same. The size field is 32-bit, so the protocol would allow more, but the calc's buffer does not. TILP requests `DUSB_DFL_BUF_SIZE 1024` (`dusb_cmd.h` 31, `dusb_cmd.cc` 889), exactly as we do (line 272). I found no public evidence that TI Connect CE negotiates more. A cheap experiment, with low odds: send BUF_REQ `00 00 FF FF`, raise `RAW_MAX` and the 4096 `inbuf`, and log the BUF_ALLOC answer and the sizes of the raw packets the CE actually sends.
- **Per-packet ACK is mandatory.** DUSB is stop-and-wait at raw-packet level: every DATA/DATA_LAST raw packet is answered with a raw ACK (`E0 00`) before the next one (`dusb_vpkt.cc` `dusb_recv_data`; our `vpkt_recv` 196). The calc does not send packet N+1 until it has the ACK for N, so you cannot pipeline from the host side. You can only make the host's turnaround as short as possible (item 10).

### Theoretical limits

- Full-speed bulk: at most 19 × 64-byte packets per 1 ms frame = 1,216,000 B/s (USB 2.0 spec, table 5-9). 153600 B ÷ 1.216 MB/s = **126 ms, about 7.9 fps**. That is the absolute ceiling, with zero ACK turnaround and an infinitely fast calc. With one ACK turnaround (~1 ms on Windows) for each of the 151 raw packets: about 0.28 s, **about 3.5 fps**.
- Measured: 1.4 s for 151 raw packets = **9.3 ms per 1018-byte packet ≈ 110 KB/s**. The wire part of that is ~0.85 ms (16 USB packets). About 90% of the time is spent **in the calculator** (eZ80, 48 MHz: the OS copies VRAM and runs its USB stack) or in host turnaround. Item 4 will split the two. Even a perfect host gets maybe 1.1-1.3 fps.
- (I could not confirm whether the CE's port enumerates at full or high speed. Our 64-byte zero-length-packet workaround (line 97, from TILP `workaround_send`) implies 64-byte max packets, which is full speed. It doesn't change the conclusion, because the calc is the limit.)

### Ways to read only the changed rows

There are none over DUSB. You only learn whether the screen changed by fetching all of it. The only way to get dirty rows or more fps would be a native program on the calc (usbdrvce) that streams the LCD. That needs a jailbreak (section 4), and it would replace the OS UI, not mirror it. **No-go.**

Possible side effect, worth a check: the CE OS serves the link inside its own loop. While a 1.4 s screenshot is being sent, the physical keypad is probably unresponsive. Mirroring non-stop could then make the handheld itself feel sluggish for the person holding it, and that is another argument for item 1.

## 2. TI-84 Plus CE: typing latency

### Where the time goes today

1. A key is typed while a shot is in flight. `link_loop` (mirror.py 191-212) only drains `self.jobs` between shots: **wait 0-1.4 s, 0.7 s on average**.
2. `keys` runs `do_key` once per code (ti84_cli.c 428-446): EXECUTE vpkt, raw ACK, DELAY_ACK, **`sleep_ms(us/1000)` up to 400 ms** (line 201-206), then DATA_ACK. Measured: 4 keys = 0.69 s, i.e. **172 ms per key**.
3. Then a fresh 1.4 s shot before the result shows.

From keystroke to the character on screen: **about 1.6-3 s**.

### Can a screenshot be interrupted safely?

**No.** The PARM_DATA answer is one virtual packet. DUSB has no host-side abort in the middle of a virtual packet. ERROR (0xEE00) and EOT (0xDD00) are virtual packets and only make sense at virtual-packet boundaries (`dusb_cmd_s_error`, `dusb_cmd.cc` 2010). If you stop ACKing, the calc waits for its own link timeout (seconds) and may show a link error or need the mode handshake again. If you sent anything other than an ACK mid-stream, the behaviour is undefined. Don't do either. The fix is to **not start a screenshot while the user is typing**.

### Concrete changes

**(a) ti84_cli.c: don't sleep the advertised delay** (lines 201-206). The bulk IN read already blocks (5 s timeout), so the calc simply NAKs until its answer is ready. Sleeping the hinted delay can only add time.

```c
if (*vtype == VPKT_DELAY_ACK && len >= 4) {
    free(buf);          /* the real answer follows: just read it (usb_read blocks) */
    continue;
}
```

Also log the delay value and the actual wait (item 4) to see what the CE asks for. TILP does sleep (`CATCH_DELAY_VARSIZE`, `dusb_cmd.cc` 858-879), but nothing in the protocol needs it.

**(b) mirror.py: typing-first scheduling.** Add `shot_holdoff = 0.6` to `Ti84` and `0.15` to `Nspire`. In `link_loop`, before the `shot` (line 211):

```python
self.last_key_t = 0.0                    # set in queue() when line starts with "key "
...
# Typing first: while keys are coming, send them as they arrive; the picture waits
while self.running and self.session is not None:
    with self.jobs_lock:
        pending = bool(self.jobs)
    if pending:
        break                            # go round: send them now
    if time.time() - self.last_key_t >= self.calc.shot_holdoff:
        break                            # quiet long enough: take the picture
    time.sleep(0.015)
if pending:
    continue
```

Restructure so that `continue` goes back to the job-draining code. Keys then reach the calc within about 15 ms plus `do_key` time, and the picture is taken 0.6 s after the last key. On the 84 the batching of keys typed during a shot (196-201) then rarely matters, which is good: each key goes out alone and promptly.

**(c) Optimistic echo** (both calculators). When a key is queued, append its label to `self.typed` and show it in a small overlay Label placed over the bottom of the picture (`place(relx=0, rely=1, anchor="sw")`), dimmed. Record `self.typed_seq` when the shot command *starts*, and clear the overlay in `draw_frame` once a frame that started after the last key has arrived. Don't try to draw the characters into the calc's picture: the cursor position and the font are unknown. A strip like `typed: 2 + 3 ENTER` gives the instant feedback without any lies.

**(d) Optional.** Keep the shot "fresh": after a burst of keys, the first shot shows the result of all of them. With (b) that happens by itself.

## 3. TI-Nspire CX II: where the 100 ms goes

### PC side (measured here, no USB)

Benchmark on this PC, with the same code path as mirror.py, 320×240 PPM (`scratchpad/bench/tkbench.py`):

| Step | ms per frame |
|---|---|
| C writes .ppm + `os.replace` (mirror.py 211-215, nspire_cli.c 280-289) | 0.7 |
| Python reads the file back (recorder only) | 0.1 |
| `PhotoImage(file=)` + `zoom(2,2)` + `configure` (mirror.py 262-271) | **5.0** |
| `PhotoImage(data=ppm_bytes)` + zoom | 3.5 |
| One reused PhotoImage: `configure(data=)` + `copy -zoom 2 2` into a fixed 640×480 image | **2.1** |
| RGB565 to RGB loop in C (nspire_cli.c 259-266) | <1 (76800 px) |

So the PC costs about 6-7 ms of a ~100 ms frame, and the drawing runs on the Tk thread in parallel with the link thread anyway (the link thread blocks in `readline`, without the GIL). **The temp file, PPM conversion and Tk are not the bottleneck.** About 90% of the frame is the USB conversation. Items in group 9 are worth doing for CPU and tidiness, but they won't raise fps noticeably.

### The USB conversation per frame (from the code)

`nspire_screenshot` (third_party/libnspire/src/services/screenshot.c 63-126) over the CX II transport (`cx2_resume.cpp`):

1. `service_connect` (service.c 22-30) is local only: no packet.
2. `data_write8(0x00)`: one NNSE stream packet; `packet_send_cx2` waits for its NNSE ack (cx2_resume.cpp 405-455). **1 round trip.**
3. Header packet in; host sends an NNSE ack (`handlePacket` 252-267).
4. RLE data in packets of up to 1439 payload bytes (`packet_max_datasize` = 1440, packet.c 218-220), **each acked by the host**. A typical screen RLE is perhaps 20-60 KB, so about 15-40 packets.
5. `service_disconnect` sends the 0x40DE packet and waits for its ack. **1 more round trip.** The calc may send its own disconnect notice, which the *next* `data_read` then has to handle (data.c 26-38, 104-114).

Whether the calc waits for each NNSE ack before sending its next packet decides whether host turnaround matters. Item 4 will show it.

### Concrete changes, best first

**(a) Instrument** (item 4). In `do_shot` and `nspire_screenshot`, print `T req=… hdr=… data=…(n pkts, bytes) disc=… decode=… write=…` using `QueryPerformanceCounter`. In `readPacket`, accumulate the time spent blocked in `libusb_bulk_transfer` against the time spent writing acks. Without these numbers every link-level change below is a guess.

**(b) Keep the screenshot service open** (item 5). Add a `shot_keep` path. Connect 0x4024 once; for each frame send `00`, read the header and data, and **don't disconnect**. Disconnect only when a `key`, `keys`, `put`, `ls` or `info` command comes in (libnspire allows one service per handle: `handle->connected`, service.c 23-24). In `run_line`:

```c
static int shot_open = 0;
if (strcmp(line, "shot") && shot_open) { service_disconnect(h); shot_open = 0; }
```

Split `nspire_screenshot` into `shot_begin()` (connect) and `shot_frame()` (write 00, read header and data). If the calc answers the second `00` with nothing, or with an error, fall back to the current behaviour. This saves the disconnect round trip and the calc's service teardown/startup for every frame. It is the most promising link-level change, but it has to be tested on hardware.

**(c) Keys with fewer round trips** (item 6). `do_keys` (nspire_cli.c 326-354) sends `p1 = 01 00 00 80` and `p2` for every key, and each `data_write` waits for an NNSE ack. TILP's `nsp_cmd_s_key` (nsp_cmd.cc 1044-1084) sends both, but it does one key per session, so it never shows whether `p1` is per-session or per-key. Try sending `p1` once after `service_connect` and then only `p2` per key: 1 + k + 1 round trips instead of 2k + 1.

**(d) Fix `readPacket`** (cx2_resume.cpp 142-182; item 7). When a packet arrives in more than one bulk transfer, `transferred` holds only the *last* chunk's size, so `compute_checksum(message, transferred)` (line 178) checks the wrong length. The packet is dropped and the loop waits again, with the default `timeoutMs = 60000`, up to 10 times (lines 433-444, 469-475). Fix:

```cpp
if(compute_checksum(reinterpret_cast<uint8_t*>(message), completeLength) != 0xFFFF)
```

Also pass a short timeout (e.g. 2000 ms) from `packet_send_cx2` and `packet_recv_cx2` once connected. A real hiccup then costs 2 s and a retry instead of a minute. That is a plausible cause of "sometimes it hangs".

**(e) Skip unchanged frames** (CPU only). Keep the previous RLE buffer in nspire_cli. If `size` and `memcmp` match, print `OK same` and skip the decode and the write. In mirror.py, treat `same` as no redraw (and the recorder keeps the frame longer, as it already does).

**(f) Binary stdout instead of the temp file** (CPU only, ~1 ms). Have `shot -` write `FRAME w h n\n` plus n bytes of PPM to stdout. Note that `setvbuf(stdout, NULL, _IONBF, 0)` and `printf` in text mode on Windows would mangle `\n` bytes, so call `_setmode(_fileno(stdout), _O_BINARY)`. In Python, open the Popen without `text=True` and read `n` bytes, then call `self.src.configure(data=ppm, format="PPM")` and `self.big.tk.call(self.big, "copy", self.src, "-zoom", 2, 2)` on **one persistent pair of PhotoImages** (2.1 ms against 5.0 ms). Scaling in C isn't worth it: it quadruples the pipe bytes and Tk's `-zoom` copy is already fast.

**(g) Nspire typing.** Today: wait for the current shot (0-100 ms), then keys (2k+1 round trips), then the next shot. That shot often starts before the calc has redrawn, so the character only appears in the frame after that. Total 150-300 ms. Do items 1 (hold-off 0.1-0.15 s, so the shot after a key sees the redraw), 3 (overlay), (b) and (c).

## 4. Emulator route

| Calc | Emulator (licence) | Getting your own ROM/boot | Verdict |
|---|---|---|---|
| **TI-84 Plus CE** | CEmu (GPL-3.0), https://github.com/CE-Programming/CEmu | CEmu needs a ROM dumped from your calc ("a ROM from your own calculator is required"; its built-in dump wizard creates the dumper program: https://github.com/CE-Programming/CEmu/wiki). The dumper is native code, and OS 5.5+ blocks native code without a jailbreak. arTIfiCE v1 covered OS 5.5-5.8.2, and TI patched its bug in 5.8.3. **arTIfiCE v2.0 (Aug 2025) claims all OS ≥ 5.3.0** (https://www.cemetech.net/news/2025/8/1051/_/artifice-v20-released-ti-84-plus-ce-jailbreak-for-583-and-565). The latest TI OS is 5.8.5, and I could not confirm v2.0 on 5.8.5 (Cemetech's sidebar showed an "arTIfiCE v3 … OS 5.8.5" headline I couldn't open). TI's CE OS can't be downgraded. | **Feasible if your OS is jailbreakable.** One-time dump (CEmu's wizard plus arTIfiCE), then 60 fps and instant keys. |
| **TI-Nspire CX II CAS** | Firebird (GPL-3.0), https://github.com/nspire-emus/firebird | Firebird 1.6 added CX II, but "with the current dumping programs you will not get a complete bootrom and booting the OS will fail" (https://github.com/nspire-emus/firebird/releases). Ndless r2023 supports CX II **OS 6.4.0.74** (https://github.com/ndless-nspire/Ndless/releases). Issue #330 (closed Dec 2025) reports that **eMMUlate plus a full Polydumper dump** gives a complete bootrom, and users booted it (https://github.com/nspire-emus/firebird/issues/330). That needs Ndless on the handheld. CX II support is still marked imperfect on the wiki. | **Possible but fiddly:** Ndless on 6.4.0.74, Polydumper, eMMUlate, Firebird. Not a one-click step for app users. (TI's own Student/Teacher Software also has a licensed emulator.) |
| **TI-89 Titanium** | TiEmu (GPL-2.0, unmaintained since ~2010) | ROM dumps over USB with TiLP work on the 89T without hacks, and TiEmu's wizard can also build an image from TI's AMS upgrade file (.89u). | **Easiest of the three**, but TiEmu is old and has no up-to-date Windows build. |

**Licensing.** Run the emulator as a **separate executable** that the MIT app launches. That is mere aggregation, the same arrangement the repo already uses for the GPL-3.0 `nspire-cli.exe` and `ti84-cli.exe`. Ship the licence text and the source (or a written offer), and don't link GPL code into the MIT Python. **Never bundle ROMs, boot1/boot2/manuf or OS images**: they are TI's copyright, and the user must supply their own dump.

**Is it the same calculator?** **No.** The emulator has its own RAM, archive, documents, settings and state. Typing on the PC changes the emulated calc, not the one in your hand. Keeping them in sync would need full backup and restore in both directions (DUSB var transfer for the CE, which we haven't built; `nspire_file_read/write` for the Nspire), and it can never be live. For the mirror's job (show and drive *this* handheld), an emulator is the wrong tool. Offer it as a separate "PC calculator" mode, e.g. to write and test programs, and then use Send to push to the real handheld.

## 5. Other things worth doing

- **The scanner opens the calculators every 3 s** (mirror.py 433-437, nspire_link.py 152-162, then `cmd_devices` nspire_cli.c 69-76 calls `libusb_open` on every TI device). With WinUSB the open normally fails with ACCESS while `serve` holds the device. But in the window when a `serve` is reconnecting, the scanner can win the open and make that connection fail. It also starts a process every 3 s. Add `devices --list` that only reads descriptors (no `libusb_open`) and use it in `usb_calculators()`, or stop scanning for a pid that already has a live session.
- **Frame-rate display:** have the CLI report the time per phase, and show "link 92 ms / draw 3 ms" in the status tooltip. It makes regressions obvious.
- **84 CE idle polling:** when nothing changed in the last N frames and no keys came, poll every 2-3 s instead of back to back. This frees the handheld's own keypad and the link for keys. You can't skip the transfer itself, but you can do fewer of them.
- **One CLI command per frame is fine:** the pipe round trip costs <1 ms, so merging `keys` and `shot` into one command gains nothing.

## Sources

- TILP libticalcs: https://github.com/debrouxl/tilibs (local copies used: `calc_84p.cc`, `dusb_cmd.h/.cc`, `dusb_vpkt.cc`, `dusb_rpkt.cc`, `nsp_cmd.cc`)
- Nspire USB protocol (service 0x4024 RLE screenshot, 0x4021 raw): https://hackspire.org/index.php/USB_Protocol
- arTIfiCE v2.0: https://www.cemetech.net/news/2025/8/1051/_/artifice-v20-released-ti-84-plus-ce-jailbreak-for-583-and-565 ; project page https://yvantt.github.io/arTIfiCE
- TI-84 Plus CE OS 5.8.5: https://education.ti.com/en/software/details/en/158B7669E4C0493A84D33D9A22FDBD3C/ti-84plusceoperatingsystem
- CEmu ROM requirement and dump wizard: https://github.com/CE-Programming/CEmu/wiki
- Firebird CX II notes: https://github.com/nspire-emus/firebird/releases ; bootrom issue: https://github.com/nspire-emus/firebird/issues/330
- Ndless CX II OS support: https://github.com/ndless-nspire/Ndless/releases
- USB 2.0 spec, table 5-9 (full-speed bulk: 19 × 64 B per frame)
