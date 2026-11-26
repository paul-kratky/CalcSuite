# CLAUDE.md

This folder holds Python programs for a **TI-Nspire CX II CAS** handheld. They run in TI's
own Python (built on MicroPython, OS 5.2 or later), not in desktop CPython. Write every
program for the calculator first. The PC is only for checking.

## Workflow for every program

1. Write it to `programs/<name>.py`. Use a short lowercase name that starts with a letter
   and uses only letters, digits and underscores (no spaces). The file name becomes the
   program name and the .tns name on the handheld.
2. Run `python -I tools/check_nspire.py programs/<name>.py`. Fix every ERROR. Fix the
   warnings too unless the user has checked that feature on the handheld (`programs/probe.py`).
3. Where you can, test the logic on the PC with
   `python -I tools/run_on_pc.py programs/<name>.py`. Feed input on stdin, and use
   `--var/--list/--func/--keys` for TI variables and keys (see README).
4. Send it or hand it over:
   - **If the user says "send it" (or "flash it", "put it on my calculator"), or says the
     calculator is plugged in:** run `python -I tools/flash.py programs/<name>.py`. It
     re-runs the checker, converts to `build/<name>.tns` and uploads it to My Documents
     over USB, then reads it back to verify. Add `--folder NAME` if the user wants a
     folder, `--allow mod` for their PyLib modules. Report the last lines it printed.
   - **Otherwise:** run `python -I tools/flash.py programs/<name>.py --dry-run`, which
     checks and builds `build/<name>.tns` without sending. Tell the user it is ready and
     that "send it" will upload it once the calculator is plugged in.
   - If flash.py stops, read its message: checker errors mean fix the program and run it
     again; "No TI-Nspire found" means ask the user to plug in and turn on the handheld;
     a driver or link error means point the user to README "Troubleshooting". Do not
     install or change USB drivers yourself, and never run anything that needs admin.
   - `python -I tools/send_to_calc.py --list` shows the connected handheld (name, OS,
     free space); `--ls /` lists My Documents.
5. Tell the user how to run it on the handheld: [home/on] > My Documents > `<name>.tns`,
   then menu > Run > Run (ctrl+R). A document that is already open on the handheld keeps
   the old version until it is closed and reopened.

## The language: TI-Python on the CX II

- **Modules allowed:** `math`, `cmath`, `random`, `time`, `ti_system`, `ti_draw`,
  `ti_plotlib`, `ti_image`. Use `ti_hub` and `ti_rover` only if the user has the
  TI-Innovator Hub or Rover. Also allowed: the user's own modules that they installed into PyLib
  (`--allow name` for the checker). Use only the functions TI documents (the checker
  lists them). Leave out `sys`, `gc`, `array` and `collections` unless the user asks.
- **Not available:** numpy, sympy, matplotlib, turtle (unless the user installed TI's
  add-on), os, re, json, itertools, statistics, typing, dataclasses, and any other import.
  There is no file I/O (`open()`), no internet, no threads.
- **Syntax to avoid:** f-strings (use `"{} {}".format(a, b)` or `print("x =", x)`), the
  walrus `:=`, `match/case`, type hints (`def f(x: int) -> int`, `x: int = 0`),
  `async/await`, positional-only `/`, `from __future__`, `except*`, and underscores in
  numbers (`1_000`). Classes, `lambda`, `try/except`, `with`, generators, list/dict
  comprehensions and `global`/`nonlocal` are fine (they are in TI's keyword list).
- **String methods:** MicroPython lacks `ljust`, `rjust`, `zfill`, `title`, `partition`
  and others. Pad by hand.
- **Plain ASCII only** in the source, comments included. No curly quotes, long dashes,
  superscripts, `pi` or `<=` symbols. Indent with 4 spaces, never tabs.
- **Keep it small:** aim for under 20 KB and a few hundred lines. The heap is about 2 MB
  (community measurement), so keep lists to a few thousand items and loops short. The
  handheld is much slower than a PC.
- **Recursion:** the stack is small. Use loops, and keep any recursion depth well
  under 50.
- **Input/output:** `input("prompt")` always returns a string, so convert it with
  `float()`/`int()` inside `try/except ValueError`. `print()` writes to the Shell page,
  which is a small handheld screen, so keep printed lines short (about 30 characters reads
  well). Program text
  output with `print`, not with ti_draw.

## Graphics

- **ti_draw**: pixel canvas **318 x 212** (read it with `get_screen_dim()` rather than
  hard-coding it). (0,0) is the top left and y grows downward; `set_window(xmin, xmax, ymin, ymax)`
  switches to math coordinates.
  - Calls: `set_color(r,g,b)`, `set_pen("thin"|"medium"|"thick", "solid"|"dotted"|"dashed")`,
    `draw_line`, `draw_rect`/`fill_rect(x,y,w,h)`, `draw_circle`/`fill_circle(x,y,r)`,
    `draw_text(x,y,"text")`, `draw_poly`/`fill_poly(xlist,ylist)`, `clear()`.
  - For many shapes, wrap the drawing in `use_buffer()` ... `paint_buffer()`.
  - End a drawing program with `get_key(1)` (from ti_system), so the picture stays up.
  - ti_draw only works on the handheld or in the software's handheld view.
- **ti_plotlib** (`import ti_plotlib as plt`): graphs in math coordinates. Always call
  `plt.window(xmin,xmax,ymin,ymax)`, then `plt.axes("on")`, `plt.grid(...)`, `plt.plot(xs, ys, "o")`,
  `plt.scatter`, `plt.line`, `plt.lin_reg`, `plt.text_at(row, "text", "left")`, and end with
  `plt.show_plot()`.
- Don't mix ti_draw and ti_plotlib in one picture unless you have to.

## ti_system (talking to the rest of the calculator)

`recall_value("a")`, `store_value("a", x)`, `recall_list("L1")`, `store_list("L1", xs)`,
`eval_function("f", x)` evaluates a function defined in the calculator (for example in Graphs),
`get_key()` returns at once and `get_key(1)` waits for a key; the key names are `"esc"`,
`"enter"`, `"up"`, `"1"` and so on. Also `get_time_ms()`, `get_platform()` ("hh" on the
handheld, "dt" on the desktop) and `clear_history()`. Use these to hand results back to the
CAS: Python itself has no symbolic algebra.

## Honesty

These programs are for learning and homework the teacher allows. Python documents are
unavailable in Press-to-Test (exam) mode. Never help hide programs from exam mode or get
around a teacher's or exam board's rules.
