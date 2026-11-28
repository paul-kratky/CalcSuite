# Connection doctor and the USB driver helper

Two pieces, kept apart for licensing:

| File | What | Licence |
| --- | --- | --- |
| `tools/calc_doctor.py` | `diagnose()`, `install_winusb()`, `restore_ti()`, and a CLI. Standard library only | MIT (the app's) |
| `tools/bin/calcsuite-driver.exe` | Our helper on libwdi, the library behind Zadig. Source in `tools/driver_helper/` | LGPL-3.0-or-later, linked statically with libwdi (LGPL-3.0-or-later). Its full source is in the repo, so anyone can relink it |

The app never links libwdi. It only starts the helper as a separate process.

## Calling it from the UI

```python
import calc_doctor                      # tools/ is on sys.path in the app

report = calc_doctor.diagnose()         # about 1 s; run it off the UI thread
for d in report["devices"]:
    d["model"], d["headline"], d["text"]  # e.g. "TI-84 Plus CE", "Ready", "...free."
    d["fix"]       # "none" | "install_winusb" | "close_program"   (main button)
    d["alt_fix"]   # "none" | "restore_ti"     (second button, see below)
    d["present"]   # False for "Switched off / asleep" entries and the "no_device" entry
```

`status` ids: `ready`, `needs_winusb_ti`, `needs_winusb_other`, `no_driver`, `busy`,
`driver_problem`, `disabled`, `unknown`, `asleep` (seen on this PC before, not on USB now),
and `no_device`. `no_device` is one entry with `pid: None`, added when nothing is
plugged in: the cable only charges, or the calculator is off. Show `headline` as the
status line and `text` as the explanation. Both are plain English.

Buttons:

- `install_winusb`: `res = calc_doctor.install_winusb(d["pid"])`. Windows shows its admin
  (UAC) prompt, then this blocks until the helper is done (up to 300 s, usually 5 to 30 s).
  Run it in a worker thread.
- `restore_ti`: `calc_doctor.restore_ti(d["pid"])`. Same prompt, same blocking. Offer it
  when `d["can_restore_ti"]` is true (our WinUSB driver or Zadig's is on the calculator).
  Before the user confirms, warn them: if `d["ti_driver_installed"]` is false, the
  calculator ends up with **no driver** until TI's software is installed again.
  `alt_fix == "restore_ti"` means a TI program is running and can't see the calculator.
- `close_program`: no helper call. Tell the user to close what `text` names
  (`report["programs"]` lists the link programs found running), then run `diagnose()`
  again.

Both fixes return
`{"ok", "result", "cancelled", "exit_code", "steps", "errors", "log"}`.
`cancelled` is true when the user says No at the UAC prompt: treat it as a quiet no-op.
`result` is `ok`, `already` (WinUSB was already on it), `nothing` (no libwdi driver to
remove) or `dry-run`. Run `diagnose()` again afterwards to refresh the screen.
`dry_run=True` runs the helper without admin rights and changes nothing. Its `steps` list
what it would do, so the UI can show them in the confirmation dialog.

Time limits: `diagnose()` always returns, normally in about a second and within about 20 s
at the worst. Each Windows query (the driver helper, `ti84-cli devices`, PowerShell's device
list, `tasklist`) has its own limit (`QUERY_TIMEOUT_S`, `PROCESSES_TIMEOUT_S`) and runs on a
daemon thread; a program that doesn't answer is killed and its output pipe given up 2 s
later, even if it can't be stopped (stuck in a USB call). A query that fails or runs out of
time is listed in `report["errors"]` ("Not checked: ..." in the panel, and in errors.log),
and the report is made from the others. Call it from a worker thread, never Tk's: the Info
panel polls for the report and shows a plain error after `InfoSection.DOCTOR_WAIT_S`.

Two cautions:

- `diagnose(probe=True)` opens each WinUSB calculator for an instant, sends nothing, and
  closes it again. This is how it sees whether another program has the calculator.
  While CalcSuite itself is connected (mirror, file manager, recorder), the result is
  `busy`. So pass `probe=False` during a session, or skip the device you hold.
- Stop CalcSuite's own sessions on that calculator before `install_winusb` / `restore_ti`.
  Changing the driver of an open device can make Windows ask for a restart.

Packaging: add `tools/bin/calcsuite-driver.exe` to `app.spec` next to the other helpers.
It is self-contained (static, about 3.3 MB) and needs no DLLs.

## The helper on its own

```text
calcsuite-driver list [--probe]
calcsuite-driver install-winusb PID [--dry-run] [--force] [--log FILE]
calcsuite-driver restore-ti PID [--dry-run] [--log FILE]
calcsuite-driver version
```

Output is one record per line:

- `DEVICE {json}`: every TI device node under USB, including ones that are not plugged
  in. Fields: `pid`, `model`, `instance`, `present`, `started`, `problem`, `desc`,
  `service`, `inf`, `provider`, `driver_version`, `last_arrival` (UTC), and `access`
  (`free` / `busy` / `not-probed` / `n/a`).
- `PACKAGE {json}`: an `oem*.inf` in the driver store that names a TI device. Fields:
  `inf`, `provider`, `class`, `version`, `pids`, and `ours` (made by libwdi, so CalcSuite
  or Zadig).
- `STEP text`, `ERR code text`, `RESULT ok|already|nothing|dry-run`, `OK n`.

Exit codes: 0 done, 1 usage or unknown PID, 2 not plugged in, 3 failed, 4 needs admin.
The manifest says `asInvoker`, so `list` runs without admin rights. install/restore
refuse to run without admin (exit 4), and the Python side starts them with
`ShellExecuteExW("runas")`. An elevated process's console can't be read by the caller,
so `--log FILE` captures the output.

It only acts on known TI calculator product IDs (e008, e004, e003, e022, e012).

### What install-winusb does

1. libwdi's `wdi_prepare_driver` writes a WinUSB package to
   `%TEMP%\CalcSuite-driver\<pid>\`. That is an .inf (provider `libwdi`, device name =
   model, manufacturer "Texas Instruments"), plus Microsoft's co-installers and libwdi's
   `installer_x64.exe`.
2. With admin rights, it makes a .cat file and self-signs it. libwdi creates a
   certificate `CN=USB\VID_0451&PID_xxxx (libwdi autogenerated)`, adds it to the
   machine's Trusted Root and Trusted Publisher stores, and discards the private key.
   This is exactly what Zadig does.
3. `wdi_install_driver` runs the installer, which installs the package for that
   hardware ID. TI's driver package (if any) stays in the driver store, but WinUSB now
   owns the device.

### What restore-ti does

1. It finds every device node for `USB\VID_0451&PID_<pid>`, plugged in or not, whose
   driver provider is `libwdi`, and every `oem*.inf` from `libwdi` that names that PID
   (Zadig can leave several). Device nodes with any other driver are left alone.
2. `DiUninstallDevice` on those nodes, then `SetupUninstallOEMInf(SUOI_FORCEDELETE)` on
   those packages.
3. It rescans for hardware (`CM_Reenumerate_DevNode`) and waits up to 15 s. Windows then
   installs the best driver it still has for that hardware ID. That is TI's `tiehdusb`
   package if TI Connect CE (or other TI software) put it in the driver store. If not,
   the calculator shows up with no driver (Device Manager: "Other devices", code 28).
   The helper says which case applies before it acts.

It does not remove libwdi's self-signed certificates (they are harmless: their private
keys no longer exist). It does not delete TI's packages.

## Building

`python -I tools/build_tools.py` builds the helper as its last step, through
`tools/driver_helper/build_helper.py`. It needs:

- `third_party/libwdi` (git submodule, pinned in `third_party/README.md`):
  `git submodule update --init third_party/libwdi`. Without it, the step is skipped.
- Microsoft's WinUSB co-installers. `tools/driver_helper/fetch_wdk_redist.py`
  downloads `wdfcoinstaller.msi` (WDK 8 redistributable components, Microsoft-signed,
  pinned SHA-256) into `build/wdk_redist/`. It unpacks the MSI without installing it:
  msi.dll through ctypes, then `expand.exe`. Windows 8 and later never run these DLLs,
  but libwdi's WinUSB .inf lists them for x86/x64, so they must be embedded.
- MSYS2 UCRT64 gcc and windres, as for the other helpers. libwdi's autotools build is
  done by hand: `installer_x64.exe`, `embedder.exe` → `embedded.h`, the library
  sources, and `calcsuite_driver.c` (built with `-Wall -Wextra -Wformat -Werror`).

Limits: x64 Windows only. It has no 32-bit or ARM64 installer: UCRT64 can't build
those, and Windows 11 is x64 or ARM64. On ARM64 Windows, `list` and `restore-ti` work,
but `install-winusb` fails (not tested on ARM64).
