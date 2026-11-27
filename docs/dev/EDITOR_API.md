# The program editor: how the app opens it

`tools/editor.py` is the window, `tools/code_check.py` the pure checks it runs (no Tk, no USB;
tested by `tools/selftest/editor_checks.py`). Both are MIT. Nothing in `mirror.py` or
`ui_panels.py` imports them yet: the hooks below are all the app needs.

## Opening it

```python
import editor
ed = editor.open_editor(app_or_root, mirrors, initial_target=None, path=None)
```

- `app_or_root`: the `App` (its `.root` is used) or any Tk widget. The editor is a `Toplevel`.
- `mirrors`: the `Mirror` objects to offer as targets (`App.mirrors.values()`, connected or not;
  one that isn't connected is listed as "not connected" and F5 says so). "No calculator: save
  only" is always last.
- `initial_target`: a `Mirror` from that list (the tab's own), a slug (`"ti84"`, `"ti89"`,
  `"nspire"`: that language, no calculator) or `None`.
- `path`: a file to open: `.txt`/`.tib`/`.bas` TI-Basic, `.py`, or a `.8xp` / `.89p` / `.89f`
  (read back as text; Save then writes a `.txt`, never over the TI file).
- Returns the `Editor`; `ed.win` is its window.

The tab button (in a calculator's tab, next to Send program...) calls:

```python
editor.open_editor(self.app, list(self.app.mirrors.values()), initial_target=mirror)
```

and a general one (All screens, or a menu) `initial_target=None`.

`editor.py` never imports `mirror.py`: importing a second copy would replace the app's
cross-thread `after()` patch and starve its queue. It finds `dark_title_bar` in
`sys.modules["mirror"]` or `sys.modules["__main__"]` when the app has it loaded.

## Quitting the app: unsaved changes

```python
if not editor.confirm_close_all(self.root):
    return            # The user pressed Cancel: keep running
```

as the first lines of `App.quit()`. For every editor window with unsaved changes it shows the
dark "Save changes to NAME?" dialog (Save / Don't save / Cancel); Save writes the file (Save as
when it has none). It returns `True` when it's fine to quit (and closes the editors) and
`False` on Cancel (nothing after the cancelled one is touched). With no editor open, or nothing
unsaved, it returns `True` at once and asks nothing. `editor.open_editors()` lists the open ones.

The same dialog guards the window's X, Ctrl+W, File > New, Open and Open from calculator. An
unsaved window's title starts with "•". `editor.ask_save(parent, name)` is the dialog
(`"save"`, `"discard"`, `"cancel"`); tests replace it.

## What it uses of a Mirror

Only what is already there; everything goes through the calculator's own link thread:

| Used | For |
| --- | --- |
| `m.calc` (`slug`, `title`, `key_fmt`, `code_for()`, `paste_keys()`) | target, language, key codes |
| `m.connected()`, `m.info["name"]` | the target list |
| `m.queue(line, None, done, progress)` | `ls`, `send FILE`, `get ...`, `home`, `keys ...` (84/89) |
| `m.send_nspire_files([(tns, "/")], done)` | the Nspire send (it asks before replacing) |

`done` callbacks arrive on the link thread; the editor hands them to Tk through its own queue
(polled every 40 ms), so it works with or without the app's `after()` patch.

### F5 / F6, per calculator

1. Check. Errors: nothing is built or sent; the first error is selected. Warnings: asked once.
2. Build into `Documents\CalcSuite\programs\<ti84|ti89|nspire>\` (the source `.txt`/`.py` beside):
   the 84 via `send_ti.prepare` (calc_files' tokenizer, `.8xp`), the 89 the same way (`.89p`,
   `.89f` for a function), the Nspire via `py2tns.convert` (`.tns`).
3. Send. 84/89: `ls`, then (asking "Replace?" once per name per window) `send FILE`.
   Nspire: `send_nspire_files`.
4. F5 only, run:
   - TI-84 Plus CE: `keys 40 9 9 da <name>` (Quit, Clear, Clear, the prgm token, the name's
     letters, as `pc_copy.py` starts ZZDUMP), then `keys 5` (Enter; its answer may not come
     while the program runs, so its error doesn't count).
   - TI-89 Titanium: `home` (as `pc_copy.py`), then `keys <home> <clear> name()` and `keys d` (Enter).
     The HOME key is needed: with the Apps desktop on, `home` leaves the 89 on the desktop,
     where the typed name picks apps. A program with arguments gets `name(` typed and waits for you.
   - Nspire: not run (it can't be from the PC); the status line says to open it.

Open from calculator (84/89): `ls`, a picker of the programs, then
`get TYPE FOLDERHEX NAMEHEX SIZE FILE` (as `calc_manager.get_var`), detokenized
(`calc_files.detokenize_84`) or read as the 89 keeps it (`program_89_text`; one that has run is
tokenized and can't be read).

## code_check

```python
import code_check as cc
cc.check(language, text, name=None)   # [{line, col, end_col, severity, message, fix}]
```

`language`: `"ti84"`, `"ti89"`, `"python"` (or `"nspire"`). `line` is 1-based, `col`/`end_col`
0-based on that line (a Tk index is `"%d.%d" % (line, col)`). Severity `error` (the calculator
or the converter rejects it: Build refuses), `warning` (almost surely a mistake), `info`.
Also: `highlight()`, `completions()`, `signature_at()`, `hover_at()`, `block_depths()`,
`bracket_match()`, `ai_instructions()`, `problems_text()`, `TEMPLATES`.
