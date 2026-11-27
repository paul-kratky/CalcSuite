# Rules for AI assistants: TI-Basic for the TI-84 Plus CE and the TI-89 Titanium

These rules are for an AI assistant writing programs in this folder for the **TI-84 Plus CE**
(OS 5.4.0, no Python) or the **TI-89 Titanium** (AMS 3.10). They are two different
languages: pick the one for the calculator the user names, and ask if it isn't clear. The full
guides are [TIBASIC_84.md](TIBASIC_84.md) and [TIBASIC_89.md](TIBASIC_89.md).

## Never

- **No Python on these two.** The TI-84 Plus CE here has no Python and the TI-89 has none at
  all. Python programs are for the TI-Nspire CX II only (CLAUDE.md).
- No assembly, no shell programs, no libraries that need anything installed on the calculator.
- Never open, reset or reconfigure a USB device, and never change drivers. If sending fails,
  report the message and point to the README's "If something doesn't work".

## Workflow for every program

1. **Write** it to `programs/ti84/NAME.txt` or `programs/ti89/name.txt`, plain text, UTF-8.
   - 84: the file name is the program name: up to 8 capitals or digits, a letter first
     (`QUAD.txt`).
   - 89: the first line is `name()` (or `name(a,b)`), then `Prgm` ... `EndPrgm`, or `Func`
     ... `EndFunc` for a function. The name is up to 8 lower case letters, digits or `_`,
     a letter first, the same as the file name, and not a built-in name (`log`, `solve`) or a
     system variable (`xmin`, `ok`).
2. **Start with a description.** 84: one or two string lines at the top (`"QUAD: ROOTS OF ...`).
   89: `©` comment lines right after `Prgm` / `Func`.
3. **Check it** (no calculator needed):
   - Both: `python -I tools/send_ti.py --calc 84 programs/ti84/NAME.txt --out build/NAME.8xp`
     (`--calc 89 ... --out build/name.89p`). An error names the line; fix it and run again.
   - 84 only, then look for letters where a command was meant (a misspelt or unknown command
     tokenizes as letters without an error):

     `python -I -X utf8 -c "import re,sys;sys.path.insert(0,'tools');import calc_files as c;t=c.tokenize_84(open(sys.argv[1],encoding='utf-8-sig').read());s=re.sub(rb'\x2a[^\x2a\x3f\x04]*\x2a?',b'',t);n=len(re.findall(rb'\xbb[\xb0-\xca]',s));print('OK' if not n else '%d lower case letter(s) outside strings: a misspelt command?'%n)" programs/ti84/NAME.txt`

     Anything but `OK`: find the lower case word outside a string and fix it.
   - 89 only: count the blocks by hand. Every `If ... Then` has an `EndIf`, every `For` an
     `EndFor`, `While` an `EndWhile`, `Loop` an `EndLoop`, `Try` an `EndTry`, `Dialog` an
     `EndDlog`. The 89 itself only checks when the program first runs.
4. **Send it** only when the user says "send it" (or "put it on my calculator") and the
   calculator is plugged in: `python -I tools/send_ti.py --calc 84 programs/ti84/NAME.txt`
   (`--calc 89` for the 89). Add `--replace` only if the user agrees to replace a program of the
   same name (exit code 7 means one is there). Report its last line. Otherwise say the file is
   ready and the user can send it with **Send program...** in CalcSuite.
5. **Tell the user how to run it.** 84: PRGM, EXEC, pick it, ENTER, ENTER. 89: type `name()` on
   the Home screen and ENTER (a function: use it in an expression, `tobase(255,16)`). The 89
   reports mistakes on the first run.

## TI-84 Plus CE: the language

- **Variables:** only `A`-`Z` and `θ` (numbers), `L1`-`L6` and `|LNAME` lists (5 characters),
  `[A]`-`[J]` matrices, `Str0`-`Str9` strings, `Y0`-`Y9` functions, `Ans`. All global, no
  locals, no multi-letter names (`AB` is A times B). Set every variable before use.
- **Commands are case-sensitive:** `Disp`, `If`, `Then`, `Else`, `End`, `For(`, `While`,
  `Repeat`, `Lbl`, `Goto`, `Menu(`, `Input`, `Prompt`, `Output(`, `ClrHome`, `Pause`, `Stop`,
  `Return`, `prgmNAME`. Use only commands in the guide's command reference.
- **No lower case outside strings.** Write variables in capitals.
- **Spellings:** `->` `<=` `>=` `!=` `sqrt(` `pi` `theta` `^2` `^-1` `e^(` `@` (imaginary i),
  `1E-3` for the EE key, `-` for a negative number, `>Frac` `R>Pr(` for the `►` arrow.
  `and`, `or`, `xor` need spaces around them.
- **Traps:** `X^23` is `X²3` (write `X^(23)`); `2^-1.5` is `2⁻¹.5` (write `2^(-1.5)`); a digit
  before `10^(` multiplies it; `E` right after a digit is the EE key.
- **Never `Goto` out of a `For(`, `While`, `Repeat` or `If ... Then` block** (ERR:MEMORY).
  Use single-line `If` before `Goto`, and `Stop` inside blocks.
- **Strings:** `+` joins, `toString(` and `expr(` convert, `sub(`, `length(`, `inString(`.
  `Input` into a string variable reads text.
- **Screen:** home screen 10 rows by 26 columns, keep `Disp` text short; `Menu(` up to 9
  entries, title 26 and entries 24 characters.
- **No hex/binary, no units, no CAS:** write routines (`remainder(`, `int(`), keep unit factors,
  use `solve(`, `fnInt(`, `nDeriv(` for numbers.
- **No tabs** anywhere; indentation with spaces is allowed but not needed.

## TI-89 Titanium: the language

- **Structure:** `name(args)`, `Prgm` ... `EndPrgm` or `Func` ... `EndFunc`; blocks close with
  `EndIf`, `EndFor`, `EndWhile`, `EndLoop`, `EndTry`, `EndDlog`, `EndTBar`.
- **Local everything:** `Local a,b,c` for every variable that need not stay. In a `Func`,
  every variable stored to (including `For` counters) must be `Local` or an argument, and a
  function may not use `Disp`, `Input`, dialogs, `setMode(` or `setFold(`.
- **Names:** 1-8 characters, letter first; explicit `*` always (`a*x`, `x*(x+1)`).
- **Spellings:** `->` `<=` `>=` `!=` `sqrt(` `pi` `theta` `e^(`; `1E-3` for EE. Paste the
  symbols that have no spelling: `𝑖` (imaginary), `∂(` (derivative), `∫(`, `Σ(`, `∠`, `©`
  (comments), `°`.
- **The conversion arrow:** write `@>` or paste `►` (`10@>Bin`, `z@>Polar`, `3_m@>_ft`). `>`
  alone is greater-than.
- **Input:** `Request` and `InputStr` give strings: convert with `expr(` inside `Try` ...
  `Else` / `ClrErr` ... `EndTry`, and check `ok` after a `Dialog`. Request prompts are at
  most 20 characters. Show results with `Disp` (then `Pause` and `DispHome`) or `Text`.
- **Symbolic work:** if a program uses `x` as a symbol, check `getType(x)="NONE"` first and
  tell the user to `DelVar x` otherwise. Don't use an undefined `Local` as the symbol for
  `expr(` or `solve(`.
- **Strings are not converted:** inside quotes write `0.000001`, not `1E-6`.
- **Folders:** CalcSuite sends into `main`. A program that calls another (or a function)
  expects both there.
- **No tabs**, no long dashes or curly quotes (the 89 has no such characters).

## Examples to copy from

`programs/ti84/` (QUAD, RESNET, UNITS, NUMINT, BASE, RCTAU, VECTOR, LINSOLVE) and
`programs/ti89/` (quadc, resnet, unitconv, numint, tobase, baseconv, rctau, linsolve). They
pass the checks above. They have not been run on a calculator yet: if the user reports an
error from one, fix the example too.
