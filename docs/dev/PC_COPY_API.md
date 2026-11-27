# PC copy: the API for the window

`tools/pc_copy.py` does everything; the window only calls it. People's guide:
[docs/PC_COPY.md](../PC_COPY.md). How each step works and why: the module's docstring.

## Calls

All of them are blocking: run them on a worker thread, never on Tk's.

```python
import pc_copy

res = pc_copy.dump_rom(model, report=None, cancel=None, connect=None, backup_folder=None)
emu = pc_copy.get_emulator(model, report=None)
proc = pc_copy.open_in_emulator(model, rom=None, backup=None, files=None, emulator=None, fresh=True)
res = pc_copy.make_pc_copy(model, report=None, cancel=None, connect=None, open_emulator=True)

pc_copy.list_roms(model=None)      # [{"path", "model", "size", "made", "info"}], newest first
pc_copy.latest_backup(model)       # the newest backup folder of that model, or None
pc_copy.cemu_path(), pc_copy.tiemu_path()   # the emulator's exe, or None
pc_copy.roms_folder(), pc_copy.emulators_folder()
```

- `model`: `"84"` or `"89"` (anything `calc_backup.slug_of` takes: `"ti84"`, `"84ce"`, ...).
- `report(stage, text, done, total)`: called on the worker thread (use `after()` to reach Tk).
  `text` is a sentence for a status line, or `None` for a progress-only call; `done`/`total`
  are bytes (or pieces, or seconds while the CE dumps), or `None` when there is no bar.
- `cancel`: a `threading.Event`. Looked at between steps. Once the dumper runs on the
  calculator it can't be stopped from the PC: cancelling then stops waiting, and the
  `ROMData*` AppVars and `ZZDUMP` stay on the calculator (the error says so).
- `connect()`: returns a session with `cmd(line, on_progress) -> (code, lines)` and `close()`.
  Default: `nspire_link.Session(cli=CLI_84 / CLI_89)`. The dump opens and closes several
  sessions (the CE's dumper needs the link silent; the 89's dumper leaves the link in its own
  protocol), so **the tab's own link thread must let go of the calculator first** and take it
  back afterwards (reconnect). Passing the tab's session is not enough.

### Stages (the `stage` argument, in order)

| Stage | TI-84 Plus CE | TI-89 Titanium | Typical time |
| --- | --- | --- | --- |
| `connect` | info, model and OS check (OS 5.5+ refused) | info | < 1 s |
| `check` | listing; stops if `ZZDUMP` or `ROMData*` exist; free RAM/archive | listing; stops if `main\romdump` exists | < 1 s |
| `backup` | `calc_backup.backup` (its progress text) | same | 1-5 s |
| `tidy` | Garbage Collect (typed keys, 2:Yes) | | ~10 s |
| `send` | `ZZDUMP` (put) | `main\romdump` (send) | < 1 s |
| `run` | types prgm ZZDUMP, Enter | home, exec | 3-8 s |
| `wait` | the link stays silent 90 s (`done/total` = seconds), then checks the pieces | | ~90 s |
| `fetch` | reads the AppVars (`done/total` = bytes, ~0.9 MB) | | ~7 s |
| `dump` | | reads the ROM (`done/total` = bytes of 4 MB) | ~65 s |
| `assemble` | builds and checks the 4 MB image | | 0 s |
| `save` | writes `roms\ti84ce-<date>.rom` + `.json` | `roms\ti89t-<date>.rom` + `.json` | 0 s |
| `clean` | deletes `ZZDUMP`, `ROMData*`; compares RAM | deletes `main\romdump`; compares RAM | 2 s |
| `download` | `get_emulator` (bytes) | | |
| `done` | | | |

### Results

`dump_rom` returns:

```python
{"ok": True, "model": "ti84", "rom": "...\\roms\\ti84ce-2026-11-27.rom", "size": 4194304,
 "sha256": "...", "os": "5.4.0", "os_size": 761319,          # os_size: the 84 only
 "backup": "...\\backups\\TI-84-Plus-CE-2026-11-27_130319",
 "ram_cleared": False, "missing": [],                       # hex names gone from RAM
 "notes": [],                                               # sentences to show the user
 "check": {"ok": True, "model": "TI-84 Plus CE / TI-83 Premium CE", "why": ""},
 "seconds": 123.0, "timings": {"connect": 0.2, "backup": 4.2, "tidy": 9.8, ...}}
```

When `ram_cleared` is true or `missing` isn't empty, offer **Restore...** with `backup`
(calc_backup's restore; ask first, as the Files panel does). CalcSuite never restores on its
own.

Errors: `pc_copy.PcCopyError` (`.stage`, `str(e)` a sentence for the user, `.detail` the
tool's last lines) and its subclass `pc_copy.Cancelled`. A `ValueError` means a model that has
no PC copy (the Nspire).

`get_emulator(model)` returns `{"name", "path", "version", "sha256", "verified_by", "ready",
...}`. For the 89, `ready` is `False` until TiEmu is installed: `path` is then the downloaded
`setup.exe` and `todo` the sentence to show (the user runs it; CalcSuite doesn't).

`open_in_emulator` returns the `subprocess.Popen` of the emulator (detached: it outlives
CalcSuite). `fresh=True` boots the ROM and sends the files (default: the backup that the ROM's
`.json` names, else the newest backup); `fresh=False` lets CEmu carry on from its saved state
(pass `files=[]`). For the 89, files aren't sent (TiEmu takes one `-send=` file at a time).

### Suggested UI

- **Info panel:** "Make a PC copy..." (84 CE on OS <= 5.4, 89 Titanium). A confirmation that
  says: backs up first; about 2 minutes; don't touch the calculator; the ROM stays on this PC.
- **PC copy tab:** the list of ROMs (`list_roms`), **Open in CEmu** (`get_emulator` then
  `open_in_emulator`), **Show in folder**.

## Files and licences

- `tools/rom_dumpers/cemu_dump.8xp`: CEmu's dumper (GPL-3.0-or-later), byte for byte as in
  `gui/qt/romselection.cpp` (`dumper_program[]`); its source `cemu_dump.asm` (the comment at
  the end of the same file). Sent to the calculator as `ZZDUMP`.
- `tools/rom_dumpers/romdump_89t.89z`: TILP's dumper "1.02 USB" (GPL-2.0-or-later), byte for
  byte as in libticalcs' `rom89t.h`; its source in `romdump_89t_src/`.
- Both are separate programs that run on the calculator, kept with their licences and sources,
  not linked into anything: the MIT app only sends them as files. `pc_copy.py` checks their
  SHA-256 before use. Choosing between downloading CEmu's source at runtime and keeping the
  extracted program: the program is 298 bytes and fixed; keeping it (with its source and
  licence beside it) is reproducible and works offline, so that's what we do.
- The PyInstaller spec must include `tools/rom_dumpers/` (data files).
- `ti84-cli` gained `home`, `exec prgm|asm FOLDERHEX NAMEHEX` and `romdump LOCAL` (our own code
  after libticalcs' `calc_89t.cc` and `romdump.cc`, GPL-3.0-or-later like the rest of it).

## Phase 2: CEmu inside a CalcSuite tab

Feasible, and simpler than it looked: CEmu's core (`core/`, plain C, GPL-3.0) builds as a
static library with its own `core/Makefile` (no Qt), and upstream already has a headless
front end, `tests/autotester/headless_cli.cpp` (`cemu-headless`, added 2026), with a line
protocol on stdin/stdout like our link helpers: `run <ms>`, `key <name>`, `keys <seq>`,
`screenshot <path>`, `send-file ram|archive <path>`, `save-state`, `reset`, `quit`
(`tests/autotester/headless_protocol.md`).

Plan:

1. Build `tools/bin/cemu-helper.exe` (GPL-3.0) with MinGW from a pinned CEmu commit in
   `third_party/CEmu/`: `libcemucore.a` plus our own small C front end (not the C++ one: we need
   frames, not BMP files). Its loop: `emu_run` in real time on its own thread
   (`emu_set_run_rate`), and `emu_set_lcd_callback` to get each frame.
2. Frames at 60 per second: 320 x 240 RGB565 is 150 KB a frame, 9 MB/s, too much for a text
   pipe. Use a shared-memory section (`CreateFileMapping`, name passed on the command line)
   with a frame counter; the pipe carries only commands and "FRAME n". Python maps it with
   `mmap` and hands it to Tk as a `PhotoImage` (the mirror's existing path). Fallback: binary
   frames on stdout, RLE-compressed (the home screen compresses to a few KB).
3. Keys: `emu_keypad_event(row, col, press)`; a table from our key names (the 84's
   `ti84_keys.NAMED`) to CEmu's row/column (`gui/qt/keypad/keycode.h`).
4. Send program: `emu_send_variables(files, n, LINK_FILE, ...)` while running.
5. The tab: a third kind of calculator in the window ("TI-84 Plus CE (PC copy)"), same panels;
   **Send to the real calculator** takes the program from the copy (`emu_receive_variable`) and
   sends it with ti84-cli.
6. State: `emu_save(EMU_DATA_IMAGE, ...)` on close into `%LOCALAPPDATA%\CalcSuite\emulators\`,
   loaded next time.

Risks: CEmu's core runs one emulator per process (globals), which is fine for one helper per
copy; the real-time pacing and audio-free core are well tested upstream (the Qt and SDL front
ends use the same calls). Size: about 1 MB for the helper. The TI-89 would need TiEmu's core
(GPL-2.0, GTK-era, UAE-based 68k): a much bigger job, not planned.
