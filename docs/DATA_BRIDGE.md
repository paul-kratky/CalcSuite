# Data bridge: lists, matrices and the last answer

The **Data** section of a calculator's side panel moves lists and matrices between the
calculator and the PC, and **Copy answer** puts the calculator's last answer on the PC
clipboard with every digit the calculator keeps.

## Copy answer

**Copy answer** is in the tab's button row (under the screen) and at the top of the Data section.
The status line then says what was copied: `Copied 0.33333333333333 from the TI-84 Plus CE`.

| Calculator | How | What you get |
| --- | --- | --- |
| TI-84 Plus CE | Reads the `Ans` variable over the link | All 14 digits; complex numbers as `3+2i`; a list one number per line; a matrix as rows of tab-separated cells (pastes into Excel's cells); a string as its text. OS 5 exact answers (fractions, π and √ forms) come as their decimal value. |
| TI-89 Titanium | The 89's home screen history isn't a variable the link can read, so CalcSuite sends a tiny program once, `main\zzans`, and runs it over the link: it stores `ans(1)` in `zzv` and `string(ans(1))` in `zzs`, which CalcSuite then reads (and replaces on the next copy). | Exact results stay exact (`1/3`, `-22/7`); floats with all 14 digits; lists and matrices as above. A symbolic result (`x^2+1`) or a polar number comes as the 89's own text of it. |
| TI-Nspire CX II | Not possible: TI's link protocol has no command that reads the last answer, and the handheld's variables live inside its documents. The button says so. | Use **Copy screen** for a picture. |

On the 89, running `zzans` leaves `zzans()` and `Done` in the home screen's history, so
`ans(1)` is `Done` afterwards: copying again without a new calculation copies the same answer
as before (CalcSuite remembers it until you press a key).

## Lists and matrices

**Refresh** lists the calculator's lists and matrices:

- TI-84 Plus CE: `L₁` to `L₆`, named lists (`ʟZZX`), matrices `[A]` to `[J]`. Real and complex
  lists; matrices hold real numbers only (the 84's rule).
- TI-89 Titanium: list and matrix variables in every folder (`main\zzx`). Integers and fractions
  stay exact; floats show with a point (`2.`) so they go back as floats.
- TI-Nspire CX II: its lists live inside its documents (`.tns`), which the link only moves whole
  and TI encodes, so they can't be read out. Lists can go **to** the Nspire (see Send below).

Double-click one (or **Open**) to edit it in the grid, right there in the panel (**Close** brings
the list back):

- Double-click a cell, press Enter or F2, or just start typing. Enter moves down, Tab right; Esc
  cancels. A number can be `2.5`, `-1E-5`, `1/3`, `3+2i`, `-i`, the calculator's own `⁻` and `ᴇ`,
  or a decimal comma (`2,5`).
- **+ Row / - Row / + Column / - Column**; Delete clears a cell.
- **Copy all** and Ctrl+C (the selected rows) copy tab-separated text: paste it straight into
  Excel. **Paste** and Ctrl+V take what Excel (or any spreadsheet) copied, from the cell the
  cursor is in, growing the grid as needed.
- **Import CSV...** / **Save CSV...**: commas or semicolons (a semicolon file may use decimal
  commas); a first row of names becomes the lists' names. Saved as UTF-8 that Excel opens.
- **Lists (one per column)** or **One matrix**: with lists, each column is a list named by its
  title (click a title, or edit **This column's list**); with a matrix, every cell is filled.
- **Plot** draws the first column against its index, or the second against the first, in the
  panel's plot. In the list, pick one list (y against its index) or two with Ctrl+click (x, then
  y), or a two-column matrix, and press **Plot**.
- **Send to the ...** puts it on the calculator under the names shown (asking before replacing
  one that's there): an 84 list name is `L1`-`L6` or up to 5 capitals and digits; a matrix `[A]`
  to `[J]`; an 89 name up to 8 lower case letters or digits, optionally `folder\name`.
- **New list**, **New matrix** and **Import CSV...** in the section start a new grid.

### Sending lists to the TI-Nspire

Send makes a small Python program (default name `zzdata`) and puts it in **My Documents** as
`zzdata.tns`. Open it on the handheld and run it (ctrl+R): it stores each column as a list with
`ti_system.store_list`, in that document's problem, where every page (Calculator, Lists &
Spreadsheet, Graphs) can use it. Real numbers only: the Nspire's Python can't store complex lists.

## Under the hood

The number formats are in `tools/calc_files.py` (`real84_bytes`, `value84`, `number89_bytes`,
`value89`, `parse_number`, `number_text`); the section, the grid and Copy answer in
`tools/data_bridge.py`; the tests in `tools/selftest/data_checks.py` (round trips, edge cases,
bytes from real backups, tivars as a second opinion, the grid and Copy answer on a faked link)
and the fuzz targets `num84`, `num89` and `cell` in `tools/fuzz/fuzz_calc_files.py`.
