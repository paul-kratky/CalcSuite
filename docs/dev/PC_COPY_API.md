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
- `report(stage, text, done, total)`: called on the worker thread. Never touch Tk from it:
  hand the values to Tk's thread (the PC copy dialog puts them in its own inbox, which a Tk
  `after()` loop drains). `text` is a sentence for a status line, or `None` for a progress-only
  call; `done`/`total` are bytes (or pieces, or seconds while the CE dumps), or `None` when
  there is no bar.
- `cancel`: a `threading.Event`. Looked at between steps and by every link command's watchdog:
  a command running when it's set is ended (its helper process is killed) and `Cancelled` is
  raised within about `CMD_POLL_S`. A command that prints nothing for `CMD_IDLE_S` (120 s) is
  ended the same way (`PcCopyError`). Once the dumper runs on the calculator it can't be
  stopped from the PC: cancelling then stops waiting, and the `ROMData*` AppVars and `ZZDUMP`
  stay on the calculator (the error says so).
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

- **Calculator info panel:** "Make a PC copy..." (84 CE on OS <= 5.4, 89 Titanium). A confirmation that
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

## In the window: the "(PC copy)" tab

The emulators stay separate programs (CEmu GPL-3.0, TiEmu GPL-2.0): CalcSuite starts them with
their command line and hosts their finished window in a tab (Win32 `SetParent`); nothing of
theirs is imported or linked. People's guide: [docs/EMULATORS.md](../EMULATORS.md).

| Module | What |
| --- | --- |
| `tools/emu_host.py` | `EmuSession`: one emulator process and its window (find it, `child_style`, `SetParent` into the frame, keep it in place, pop out / dock, close with WM_CLOSE then end only that process). No Tk: driven by `poll()` from Tk's thread; `Win32` is the only part that calls Windows. |
| `tools/emu_tabs.py` | `EmuTab` (the tab: bar, host frame, messages, the PC copy being made), `EmuPanel` (Keys, Guide), CEmu's own settings file for the tab (`-g`, in `cache_dir("emulators", "CEmu", "calcsuite")`: the minimal layout as Qt's saved state, no update check, no remembered transfers). |
| `tools/emulator_keys.py` | CEmu's and TiEmu's key tables: the Keys panel and the guide's tables (the self-test compares). |
| `tools/pc_test.py`, `tools/pc_test_ui.py` | Test in PC copy: CEmu's autotester (`-t test.json --no-test-dialog`) in a second CEmu (`--id CalcSuiteTest`), its stdout read, `--screenshot`. |

`App.pc_copy_tab(section, mode)` (Calculator info's buttons) and `App.open_emulator_tab(slug,
rom, backup)`; the tab keys are `"emu:ti84"` / `"emu:ti89"` in `App.emus`. Making the copy runs
`PcCopyDialog` embedded in the tab (`parent=`, `on_made=`, `on_close=`): the same worker,
inbox, watchdogs and Cancel as the window it was; when it's made the bar is full and green
("Done: 100%") and `on_made` starts the emulator in the tab.

CEmu's commands to the running copy go through its own IPC: a second `CEmu.exe --id CalcSuite
--send FILE --no-reset` / `--screenshot PNG` hands them over and exits (CEmu 2.0 `main.cpp`).

The headless-core alternative (building CEmu's `core/` into our own helper with frames over
shared memory) isn't needed for this and isn't planned.
