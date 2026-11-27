# TI-Basic on the TI-89 Titanium

Write TI-Basic programs and functions for the TI-89 Titanium (AMS 3.10) on the PC, by hand or
with an AI assistant, and send them with CalcSuite. The examples are in `programs/ti89/`.

## Contents

- What the language is
- Writing it on the PC
- The first line
- PC spellings
- Traps in the text
- Send and run
- Variables, folders and data
- Programs and functions
- Input and output
- Dialogs and menus
- Control flow
- Catching errors
- Cookbook: input checks
- Cookbook: lists and matrices
- Cookbook: solving equations
- Cookbook: calculus
- Cookbook: units
- Cookbook: complex numbers
- Cookbook: number bases and bits
- Cookbook: exact and decimal
- Errors and fixes
- Command reference
- Example programs
- Limits
- Sources

## What the language is

The 89's TI-Basic is its own language: a different one from the TI-84's, with a computer
algebra system (CAS) behind it.

- **Programs and functions.** A program (`Prgm ... EndPrgm`) does things: it asks, shows and
  stores. A function (`Func ... EndFunc`) returns a value and can be used in any expression,
  like a built-in one.
- **Real names.** Variables have 1 to 8 letters, digits or `_`, starting with a letter:
  `vin`, `r1`, `tau`. Upper and lower case are the same name.
- **Local variables:** `Local a,b` makes variables that disappear when the program ends.
- **Symbolic maths:** `solve(`, `cSolve(`, `zeros(`, `d(` (derivative), `∫(` (integral),
  `limit(`, `expand(`, `factor(`, exact fractions and roots, and units such as `_m` and `_s`.
- **Folders:** every variable lives in a folder, `main` by default.
- **Real dialogs:** `Dialog`, `Request`, `PopUp`, `Toolbar`.

## Writing it on the PC

- **The file:** plain text, `.txt` (`.tib` and `.bas` work too), UTF-8 or Windows-1252. The
  program's own first line names it (next section); without one, the file name does.
- **One statement per line.** `:` puts several on one line. A `:` at the start of a line is
  allowed and ignored.
- **Indentation** with spaces is fine; the 89 ignores it. **Tabs are not allowed.**
- **Line endings:** Windows (CRLF) or Unix (LF), either is fine.
- **Comments** start with `©` (the copyright sign) and run to the end of the line. On Windows,
  type it with Alt+0169 on the number pad, or copy it from here.
- **Keywords** are case-insensitive, but write them as the 89 shows them: `If`, `Then`,
  `EndIf`, `For`, `EndFor`, `Disp`.
- **Multiply explicitly:** `a*x`, not `ax`; `ax` is a variable called ax.

## The first line

Start with the program's name and arguments, then `Prgm` or `Func`, and end with `EndPrgm` or
`EndFunc`:

```tibasic89 name=hello
hello()
Prgm
© hello: shows a line of text
ClrIO
Disp "Hello"
Pause
DispHome
EndPrgm
```

A function with arguments:

```tibasic89 name=vdiv
vdiv(vin,r1,r2)
Func
© vdiv(vin,r1,r2): output of a voltage divider
Return vin*r2/(r1+r2)
EndFunc
```

- The name is up to 8 lower case letters, digits or `_`, a letter first, and not the name of a
  built-in command (`log`, `solve`) or a system variable (`xmin`, `ok`).
- `Define name()=Prgm` as the first line also works.
- Always write this first line. Without it, the whole text becomes the body of a program with
  no arguments named after the file, and a first line that looks like `f(x)` is taken as the
  program's name.

## PC spellings

CalcSuite sends the text as it is, apart from these, which become the 89's own characters:

| Type on the PC | Calculator | Symbol |
| --- | --- | --- |
| `->` | store arrow | `→` |
| `<=` `>=` `!=` (or `/=`) | less or equal, greater or equal, not equal | `≤` `≥` `≠` |
| `sqrt(` | square root | `√(` |
| `pi` `theta` | pi, theta | `π` `θ` |
| `e^(` | e to the power | `ℯ^(` |
| `1.5E-3` (E after a digit) | the EE key | `1.5ᴇ-3` |
| `-5` (at the start or after an operator) | negative sign | `⁻` |

These have no PC spelling yet: type or paste the symbol.

| Symbol | Unicode | What it is |
| --- | --- | --- |
| `𝑖` | U+1D456 | the imaginary unit (plain `i` is a variable) |
| `∂(` | U+2202 | the derivative the 89 shows as `d(` |
| `∫(` | U+222B | the integral |
| `Σ(` | U+03A3 | a sum |
| `∠` | U+2220 | the angle in polar complex numbers |
| `©` | U+00A9 | a comment |
| `°` | U+00B0 | degrees, and in `_°C` |
| `∞` | U+221E | infinity |

**Not possible from the PC yet:** the conversion arrow `►` (as in `►Hex`, `►Rect`,
`3_m►_ft`). CalcSuite refuses it, and `>` is greater-than on the 89. The cookbook shows the
ways around it.

## Traps in the text

- **`e` alone is a variable.** The constant is `e^(1)`, or `e^(x)` for a power.
- **`i` alone is a variable.** The imaginary unit is `𝑖`.
- **`x(x+1)` is an error** (Invalid implied multiply): write `x*(x+1)`.
- **`d(` typed as letters** calls a function named d; write `∂(` for the derivative.
- **Inside a string nothing is converted.** `expr("1E-6")` reads the letter E: write
  `"0.000001"` in strings. `"e^(x)"` is the variable e: write `"ℯ^(x)"` or avoid it.
- **A variable that has a value** stops being a symbol. If `x` is 5, `solve(x^2=4,x)` fails.
  Programs that work with x check `getType(x)="NONE"` first (see the examples), or you
  type `DelVar x`.
- **The program runs in the current folder.** Variables it stores land there.

## Send and run

- **Send:** in CalcSuite, the calculator's window > **Send program...** and pick the `.txt`, or **Files...** > **Upload**. Or from a terminal in the CalcSuite folder (below). It goes into the folder `main`.
- **Run:** on the Home screen type the name with brackets and press **ENTER**: `quadc()`. A function is used like a built-in one: `tobase(255,16)`.
- **First run:** the 89 keeps the program as text until it first runs, then turns it into its own tokens. A mistake shows up then, as the 89's error message.
- **Stop** a running program with **ON**: Break, then ESC.
- **Edit on the calculator:** APPS > Program Editor > Open.
- **Another folder:** if the current folder isn't `main`, run `main\quadc()` or `setFold(main)` first.

```
python -I tools/send_ti.py --calc 89 programs/ti89/quadc.txt
```

Add `--replace` to replace a program of the same name, `--name` for another name, or
`--out quadc.89p` to only make the file.

## Variables, folders and data

| Kind | Example |
| --- | --- |
| Number, exact | `1/3->a`, `sqrt(2)->b` |
| Number, decimal | `0.5->a` |
| Expression | `x^2+2*x->ex` |
| List | `{1,2,3}->l`, `l[2]` |
| Matrix | `[1,2;3,4]->m`, `m[1,2]` |
| String | `"abc"->s`, `"ab"&"cd"` |
| With units | `5*_m->len` |

- `Local a,b` inside a program or function. Use it for every variable that doesn't need to
  stay.
- `DelVar a` deletes a variable; `getType(a)` gives "NUM", "EXPR", "LIST", "MAT", "STR", or
  "NONE" when it doesn't exist.
- `NewFold work` makes a folder (and makes it current); `setFold(main)` goes back.
- `string(x)` turns a value into text and `expr(s)` text into a value.

## Programs and functions

| | Program | Function |
| --- | --- | --- |
| Starts, ends | `Prgm`, `EndPrgm` | `Func`, `EndFunc` |
| Run as | `name()` on its own | inside an expression: `2*name(3)` |
| Returns a value | no (`Return` just ends it) | yes: `Return expr`, or the last line |
| Shows things (`Disp`, dialogs) | yes | no |
| Stores to global variables | yes | no: only to its arguments and `Local` variables |
| Calls programs | yes | no, only functions |
| Changes modes or folders | yes | no (`setMode`, `setFold` are not allowed) |

- Arguments are local by themselves.
- In a function, every variable you store to, including a `For` counter, must be `Local`.
- A program with no arguments is still run with `()`.

## Input and output

The program's text goes to the **Program I/O** screen, which is separate from the Home screen.

| Command | What it does |
| --- | --- |
| `ClrIO` | Clears the Program I/O screen |
| `Disp "V =",v` | Shows each item on its own line |
| `Output 10,20,"Hi"` | Text at a pixel row and column |
| `Input "a?",a` | Asks for an expression |
| `InputStr "Name?",s` | Asks for text, stored as a string |
| `Prompt a,b` | Asks `a?`, then `b?` |
| `Pause` / `Pause "Press ENTER"` | Waits for ENTER |
| `getKey()` | The last key code, 0 if none (ENTER 13, ESC 264, F1 268) |
| `DispHome` | Goes back to the Home screen at the end |

```tibasic89
Local k
0->k
While k=0
  getKey()->k
EndWhile
Disp k
```

## Dialogs and menus

```tibasic89
"10000"->s1
Dialog
  Title "Divider"
  Request "R1 (ohm)",s1
  DropDown "Unit",{"ohm","kohm"},u
EndDlog
If ok=1 Then
  Disp expr(s1)
EndIf
PopUp {"Series","Parallel"},ch
Text "Done"
```

- `Request "prompt",var` gives a **string**: convert it with `expr(`. A string already in var is
  shown as the default. The prompt is at most 20 characters.
- `ok` is 1 after ENTER and 0 after ESC.
- `PopUp {...},var` stores the number of the chosen item. `DropDown` does the same inside a
  dialog.
- `Text "..."` alone shows a message box.
- Dialog boxes start with alpha-lock on: press **alpha** once to type digits.
- `Toolbar ... EndTBar` with `Title "Run",lbl` lines makes an F1-F8 menu that jumps to labels.

## Control flow

```tibasic89
If a>0 Then
  Disp "positive"
ElseIf a=0 Then
  Disp "zero"
Else
  Disp "negative"
EndIf
For i,1,10
  Disp i
EndFor
For i,10,0,-2
  Disp i
EndFor
While a<10
  a+1->a
EndWhile
Loop
  a-1->a
  If a<=0
    Exit
EndLoop
```

- `If` without `Then` covers exactly the next line.
- `Exit` leaves a `For`, `While` or `Loop`; `Cycle` goes on with its next pass.
- `Lbl name` and `Goto name` work, with names like variable names.
- `Return` ends a program; in a function, `Return value` gives the result.
- `Stop` ends the program.

## Catching errors

```tibasic89
Try
  expr(s)->v
Else
  ClrErr
  Text "Can't read that"
EndTry
```

- If anything in the `Try` part fails, the `Else` part runs. `errornum` holds the error's number.
- `ClrErr` clears the error (use it when you handle it). `PassErr` passes it on.
- The examples set a flag in `Else` and act on it after `EndTry`.

## Cookbook: input checks

```tibasic89
Local s,v,bad
"1000"->s
Loop
  Request "R (ohm)",s
  0->bad
  Try
    expr(s)->v
  Else
    ClrErr
    1->bad
  EndTry
  If bad=0 and getType(v)="NUM" Then
    If v>0
      Exit
  EndIf
  Text "Type a number > 0"
EndLoop
```

- `getType(v)="NUM"` is a plain number; "EXPR" is anything symbolic (also `pi`, fractions
  with roots), so test `v>0` only when it is a number.
- `when(cond,a,b)` picks a value without an `If`.

## Cookbook: lists and matrices

```tibasic89
{100,220,470}->r
Disp sum(r), 1/sum(1/r), dim(r), mean(r)
seq(k^2,k,1,10)->sq
[2,1;1,3]->a
[3;5]->b
Disp det(a), a^-1, simult(a,b)
Disp rref(augment(a,b))
```

- Lists and matrices take arithmetic on all elements at once: `1/r`, `2*r`.
- An index is in square brackets: `r[2]`, `a[1,2]`.
- `simult(a,b)` solves `a*x=b`; `rowDim(`, `colDim(`, `identity(3)`, `newMat(2,3)` and
  `newList(4)` help build them.

## Cookbook: solving equations

```tibasic89
solve(x^2-2=0,x)
solve(x^2-2=0,x)|x>0
solve(a*x^2+b*x+c=0,x)
solve(x+y=3 and x-y=1,{x,y})
zeros(x^3-x,x)
cSolve(x^2+1=0,x)
cZeros(x^2+1,x)
nSolve(cos(x)=x,x)
nSolve(x^3-2*x-5=0,x=2)
```

- `solve(` and `cSolve(` take an **equation** (with `=`); `zeros(` and `cZeros(` take an
  expression and give a list.
- `| x>0` ("with") limits the answers; join conditions with `and`.
- `nSolve(` gives one decimal answer, fastest with a guess (`x=2`) or a range
  (`nSolve(f=0,x)|x>0 and x<3`).
- Example: `quadc` and `linsolve`.

## Cookbook: calculus

```tibasic89
∂(x^3,x)
∂(sin(x),x,2)
∫(x^2,x)
∫(x^2,x,0,1)
nInt(e^(-x^2),x,0,1)
limit(sin(x)/x,x,0)
nDeriv(x^3,x)|x=2
```

- `∂(expression,var[,order])` is the derivative (the 89 shows it as `d(`).
- `∫(expression,var[,lower,upper])` is exact when it can be, a decimal otherwise.
- `nInt(expression,var,lower,upper)` is always numeric and quick.
- `limit(expression,var,point[,direction])`: direction -1 from the left, 1 from the right.
- Example: `numint` compares the trapezoid and Simpson rules with both.

## Cookbook: units

Units are names that start with `_`: `_m`, `_ft`, `_s`, `_N`, `_ohm`, `_F`, `_V`, `_A`, `_W`.

```tibasic89
3*_m/_ft
100*_mm/_in
5*_kW/_hp
(100*_m)/(2*_s)
```

- **To convert without `►`:** multiply by the unit you have and divide by the one you want.
  The units cancel and leave the number: `3*_m/_ft` is 9.84.
- Put a value with units in brackets when you divide: `(100*_m)/(2*_s)`.
- A result with units shows in the default unit of its kind (SI unless you change it).
- Temperature: `tmpCnv(100*_°C,_°F)` (not checked with a variable), or `9*c/5+32`.
- `z_` (a name ending in `_`) is a complex variable, not a unit.
- Example: `unitconv`.

## Cookbook: complex numbers

```tibasic89
3+4*𝑖->z
abs(z)
angle(z)
real(z)
imag(z)
conj(z)
(5∠0.9273)
cSolve(x^2+2*x+5=0,x)
```

- Type the imaginary unit as `𝑖`. A complex result in Real mode gives "Non-real result"
  (except `cSolve(` and `cZeros(`, which always allow them).
- `(r∠θ)` is polar entry, angle in the current angle mode.
- **Polar or rectangular display without `►`:** `setMode("Complex Format","Polar")` or
  `"Rectangular"`, then show the value.
- A variable ending in `_` (`z_`) is treated as complex in `cSolve(`.

## Cookbook: number bases and bits

```tibasic89
0hFF
0b1010
0hF0 and 0h3C
0hF0 or 0h0F
0hFF xor 0h0F
not 0h0F
shift(0b1011,1)
rotate(0b1011,-1)
intDiv(17,5)
mod(17,5)
```

- Type hex with `0h` and binary with `0b` (zero, then the letter).
- `and`, `or`, `xor`, `not` work bit by bit on integers, as 32-bit signed numbers.
- `shift(` and `rotate(` move bits: positive to the left, negative to the right.
- **Hex or binary output without `►`:** `setMode("Base","Hex")` shows integer results on the
  Home screen in hex (`"Dec"`, `"Bin"` the others), or use the `tobase` function from the
  examples: `tobase(255,2)` is "11111111".
- Example: `baseconv`.

## Cookbook: exact and decimal

- In the default AUTO mode, `1/3` stays a fraction and `sqrt(8)` stays `2*√2`; a decimal point
  anywhere (`1./3`) gives a decimal.
- `approx(expression)` gives a decimal, `exact(0.75)` gives 3/4.
- On the Home screen, the green diamond and ENTER gives a decimal answer.
- `setMode("Exact/Approx","Approximate")` makes everything decimal (and `solve(` faster).
- `round(x,3)` rounds; `format(x,"F3")` makes a string with 3 decimals, `"E3"` engineering.
- Store and restore modes in a program: `getMode("Angle")->old`, then
  `setMode("Angle",old)` at the end.

## Errors and fixes

| Error | Usual cause | Fix |
| --- | --- | --- |
| Missing start or end of block syntax | A missing `EndIf`, `EndFor`, `EndWhile`, `EndLoop`, `EndTry` | Count the blocks; indent to see them |
| Missing Then in the If..EndIf block | `If ... ` with an `EndIf` but no `Then` | Add `Then` |
| Else and ElseIf invalid outside of If..EndIf block | `Else` after a one-line `If` | Use `If ... Then` |
| Syntax | Something the 89 can't read: `x+-y`, a stray character | Look at the line the editor opens |
| Undefined variable | A variable used before it has a value | Set it first, or check `getType(` |
| Circular definition | `x+1->x` while x has no value | Give it a value first, or use a `Local` |
| Name is not a function or program | A misspelt name, or the program is in another folder | `main\name()`, `setFold(main)` |
| Invalid in a function or current expression | `Disp`, `Input`, a dialog or a store to a global in a `Func` | Make it a `Prgm`, or make the variable `Local` |
| Invalid implied multiply | `x(x+1)` | `x*(x+1)` |
| A test did not resolve to TRUE or FALSE | `If a>0` while a has no value | Give it a value first |
| Too few arguments | `∂(x^2)` without the variable | `∂(x^2,x)` |
| Data type | A string where a number is wanted (forgot `expr(`) | Convert with `expr(` |
| Dimension / Dimension mismatch | An index past the end, sizes that don't match | Check `dim(` |
| Non-real result | A complex result in Real mode | Complex Format Rectangular, or `cSolve(` |
| Invalid folder name / Folder | A folder that doesn't exist | `NewFold`, or check the name |
| Variable is locked, protected, or archived | Storing to an archived variable | Unarchive it in VAR-LINK |
| Reserved name or system variable | Naming something like `xmin` or `ok` | Pick another name |
| Break | ON was pressed | ESC |

Errors from CalcSuite before sending: "isn't a TI-89 character" (a tab, `►`, a long dash or a
curly quote pasted from the web), "has no EndPrgm at its end", "can't be a TI-89 name".

## Command reference

| Command | What it does | Example |
| --- | --- | --- |
| `Local` | Local variables | `Local a,b` |
| `Define` | Defines a function or variable | `Define f(x)=x^2` |
| `ClrIO` `Disp` `Output` | Program I/O screen | `Disp "x =",x` |
| `Input` `InputStr` `Prompt` | Asks on the I/O screen | `Input "a?",a` |
| `Pause` `DispHome` | Waits; back to Home | `Pause` |
| `Dialog` `Title` `Request` `DropDown` `Text` | Dialog boxes | `Request "R",s` |
| `PopUp` | Pop-up menu | `PopUp {"A","B"},c` |
| `getKey()` | Last key code | `getKey()->k` |
| `If` `Then` `ElseIf` `Else` `EndIf` | Branches | `If x>0 Then` |
| `For` `EndFor` | Counted loop | `For i,1,n` |
| `While` `EndWhile`, `Loop` `EndLoop` | Loops | `While x<5` |
| `Exit` `Cycle` | Leave a loop, next pass | `Exit` |
| `Try` `Else` `EndTry`, `ClrErr` | Catch errors | `Try` |
| `Return` `Stop` | End (with a value in a function) | `Return x^2` |
| `solve(` `cSolve(` | Solve equations | `solve(x^2=2,x)` |
| `zeros(` `cZeros(` | Roots as a list | `zeros(x^2-2,x)` |
| `nSolve(` | One numeric root | `nSolve(cos(x)=x,x)` |
| `∂(` `∫(` `nInt(` `nDeriv(` | Calculus | `∫(x^2,x,0,1)` |
| `limit(` | Limit | `limit(sin(x)/x,x,0)` |
| `expand(` `factor(` | Algebra | `factor(x^2-1)` |
| `approx(` `exact(` `round(` `format(` | Decimals | `approx(1/3)` |
| `simult(` `det(` `rref(` `augment(` | Matrices | `simult(a,b)` |
| `sum(` `dim(` `seq(` `mean(` | Lists | `sum({1,2,3})` |
| `abs(` `angle(` `real(` `imag(` `conj(` | Complex | `abs(3+4*𝑖)` |
| `mod(` `intDiv(` | Integer division | `mod(17,5)` |
| `and` `or` `xor` `not` `shift(` `rotate(` | Bits (on integers) | `0hF0 and 0h3C` |
| `string(` `expr(` `mid(` `left(` `right(` `inString(` `&` | Strings | `"a"&string(2)` |
| `getType(` `DelVar` | Variables | `getType(x)` |
| `setMode(` `getMode(` | Modes | `setMode("Angle","Degree")` |
| `NewFold` `setFold(` `getFold()` | Folders | `setFold(main)` |
| `tmpCnv(` | Temperature | `tmpCnv(100*_°C,_°F)` |

## Example programs

Each starts with a © line saying what it does. Send one with the button on its block, or
`python -I tools/send_ti.py --calc 89 programs/ti89/NAME.txt`.

### quadc

Roots of a*x^2+b*x+c=0 with `cZeros(`, exact and as decimals. Run `quadc()`.

```tibasic89 name=quadc
quadc()
Prgm
© quadc: roots of a*x^2+b*x+c=0, real and complex, exact and decimal (CAS)
© Uses x as the unknown, so x must have no value (DelVar x)
Local a,b,c,r
ClrIO
If getType(x)!="NONE" Then
  Disp "x has a value."
  Disp "Type DelVar x, then rerun."
  Pause
  DispHome
  Return
EndIf
Input "a?",a
Input "b?",b
Input "c?",c
If a=0 Then
  Disp "a=0: not a quadratic"
Else
  cZeros(a*x^2+b*x+c,x)->r
  Disp "Exact:",r
  Disp "Decimal:",approx(r)
EndIf
Pause
DispHome
EndPrgm
```

### resnet

Series, parallel and voltage divider from a pop-up menu, with dialogs and error checks. Run `resnet()`.

```tibasic89 name=resnet
resnet()
Prgm
© resnet: series and parallel resistance of a list, and a voltage divider
© A list is typed as {100,220,470}
Local ch,s,rl,sv,s1,s2,v,bad
Loop
  PopUp {"Series","Parallel","Voltage divider","Quit"},ch
  If ch=4
    Exit
  If ch<=2 Then
    "{100,220}"->s
    Dialog
      Title "Resistors"
      Request "R list (ohm)",s
    EndDlog
    If ok=0
      Cycle
    0->bad
    Try
      expr(s)->rl
    Else
      ClrErr
      1->bad
    EndTry
    If bad=1 or getType(rl)!="LIST" Then
      Text "Type a list like {100,220}"
    ElseIf ch=1 Then
      Text "Series: "&string(approx(sum(rl)))&" ohm"
    ElseIf min(rl)<=0 Then
      Text "Every R must be > 0"
    Else
      Text "Parallel: "&string(approx(1/sum(1/rl)))&" ohm"
    EndIf
  Else
    "5"->sv
    "10000"->s1
    "10000"->s2
    Dialog
      Title "Voltage divider"
      Request "Vin (V)",sv
      Request "R1 top (ohm)",s1
      Request "R2 bottom (ohm)",s2
    EndDlog
    If ok=1 Then
      expr(sv)*expr(s2)/(expr(s1)+expr(s2))->v
      Text "Vout: "&string(approx(v))&" V"
    EndIf
  EndIf
EndLoop
EndPrgm
```

### unitconv

Unit conversions with the 89's own units (`v*_mm/_in`). Run `unitconv()`.

```tibasic89 name=unitconv
unitconv()
Prgm
© unitconv: engineering unit conversions with the 89's built-in units
© value*_from/_to cancels the units and leaves the number
Local ch,s,v,r
Loop
  PopUp {"mm to in","in to mm","km to mi","N to lbf","Pa to psi","kW to hp","deg C to deg F","deg F to deg C","Quit"},ch
  If ch=9
    Exit
  "1"->s
  Dialog
    Title "Convert"
    Request "Value",s
  EndDlog
  If ok=0
    Cycle
  expr(s)->v
  If ch=1 Then
    v*_mm/_in->r
  ElseIf ch=2 Then
    v*_in/_mm->r
  ElseIf ch=3 Then
    v*_km/_mi->r
  ElseIf ch=4 Then
    v*_N/_lbf->r
  ElseIf ch=5 Then
    v*_Pa/_psi->r
  ElseIf ch=6 Then
    v*_kW/_hp->r
  ElseIf ch=7 Then
    9*v/5+32->r
  Else
    5*(v-32)/9->r
  EndIf
  Text "Result: "&string(approx(r))
EndLoop
EndPrgm
```

### numint

Trapezoid and Simpson rules against `nInt(` and the exact `∫(`. Run `numint()`; x must have no value.

```tibasic89 name=numint
numint()
Prgm
© numint: trapezoid and Simpson rules, checked against nInt() and the exact integral
© Type f in x, e.g. x^2*sin(x); x must have no value (DelVar x)
Local s,sa,sb,sn,f,a,b,n,h,t,si,k,y,bad
If getType(x)!="NONE" Then
  Text "x has a value: DelVar x first"
  Return
EndIf
"x^2*sin(x)"->s
"0"->sa
"2"->sb
"10"->sn
Dialog
  Title "Numeric integral"
  Request "f(x)",s
  Request "From a",sa
  Request "To b",sb
  Request "Even n",sn
EndDlog
If ok=0
  Return
0->bad
Try
  expr(s)->f
  expr(sa)->a
  expr(sb)->b
  expr(sn)->n
Else
  ClrErr
  1->bad
EndTry
If bad=1 Then
  Text "Can't read the input"
  Return
EndIf
If n<2 or mod(n,2)!=0 Then
  Text "n must be even and >= 2"
  Return
EndIf
approx((b-a)/n)->h
approx((f|x=a)+(f|x=b))->t
t->si
For k,1,n-1
  approx(f|x=a+k*h)->y
  t+2*y->t
  If mod(k,2)=1 Then
    si+4*y->si
  Else
    si+2*y->si
  EndIf
EndFor
ClrIO
Disp "Trapezoid:",t*h/2
Disp "Simpson:",si*h/3
Disp "nInt:",nInt(f,x,a,b)
Disp "Exact:",∫(f,x,a,b)
Pause
DispHome
EndPrgm
```

### tobase

A function: `tobase(255,16)` gives "FF". Needed by `baseconv`, so send it too.

```tibasic89 name=tobase
tobase(n,b)
Func
© tobase(n,b): whole number n >= 0 as a string in base b (2 to 16)
© tobase(255,16) is "FF", tobase(10,2) is "1010"; baseconv() uses it
Local s,d
If b<2 or b>16 or n<0 or fPart(n)!=0
  Return "bad input"
exact(n)->n
""->s
Loop
  mod(n,b)->d
  mid("0123456789ABCDEF",d+1,1)&s->s
  intDiv(n,b)->n
  If n=0
    Exit
EndLoop
Return s
EndFunc
```

### baseconv

Decimal, hex and binary, and bitwise and/or/xor. Uses `tobase`. Run `baseconv()`.

```tibasic89 name=baseconv
baseconv()
Prgm
© baseconv: decimal, hex and binary, and bitwise and/or/xor (uses tobase)
© Hex and binary are typed without a prefix; the bitwise inputs take 0h.. or 0b..
Local ch,s,t,n,m,bad
Loop
  PopUp {"Decimal in","Hex in","Binary in","a and/or/xor b","Quit"},ch
  If ch=5
    Exit
  "255"->s
  "0hF0"->t
  If ch<=3 Then
    Dialog
      Title "Number"
      Request "Value",s
    EndDlog
  Else
    "0h3C"->s
    Dialog
      Title "Bitwise"
      Request "a (0h, 0b or dec)",s
      Request "b (0h, 0b or dec)",t
    EndDlog
  EndIf
  If ok=0
    Cycle
  0->bad
  Try
    If ch=1 Then
      expr(s)->n
    ElseIf ch=2 Then
      expr("0h"&s)->n
    ElseIf ch=3 Then
      expr("0b"&s)->n
    Else
      expr(s)->n
      expr(t)->m
    EndIf
  Else
    ClrErr
    1->bad
  EndTry
  If bad=1 Then
    Text "Can't read that number"
    Cycle
  EndIf
  ClrIO
  If ch<=3 Then
    Disp "dec: "&string(n)
    Disp "hex: "&tobase(n,16)
    Disp "bin: "&tobase(n,2)
  Else
    Disp "a and b: "&tobase(n and m,16)
    Disp "a or b:  "&tobase(n or m,16)
    Disp "a xor b: "&tobase(n xor m,16)
    Disp "(in hex)"
  EndIf
  Pause
EndLoop
DispHome
EndPrgm
```

### rctau

Time constant of an RC or RL circuit and v(t). Run `rctau()`.

```tibasic89 name=rctau
rctau()
Prgm
© rctau: time constant of an RC or RL circuit, and v(t) charging and decaying
© Type 1E-6 with the EE key in the dialog, or 0.000001
Local ch,sr,sx,sv,st,r,cl,v,t,tau,bad
PopUp {"RC circuit","RL circuit"},ch
"1000"->sr
"0.000001"->sx
"5"->sv
"0.001"->st
Dialog
  Title "Time constant"
  Request "R (ohm)",sr
  Request "C (F) or L (H)",sx
  Request "Step voltage (V)",sv
  Request "At time t (s)",st
EndDlog
If ok=0
  Return
0->bad
Try
  expr(sr)->r
  expr(sx)->cl
  expr(sv)->v
  expr(st)->t
Else
  ClrErr
  1->bad
EndTry
If bad=1 Then
  Text "Can't read the input"
  Return
EndIf
If r<=0 or cl<=0 Then
  Text "R, C and L must be > 0"
  Return
EndIf
If ch=1 Then
  r*cl->tau
Else
  cl/r->tau
EndIf
ClrIO
Disp "tau (s):",approx(tau)
Disp "5 tau (s):",approx(5*tau)
Disp "Charging v(t):",approx(v*(1-e^(-t/tau)))
Disp "Decaying v(t):",approx(v*e^(-t/tau))
Pause
DispHome
EndPrgm
```

### linsolve

Solves A*x=b with `simult(`, exact when you type exact numbers. Run `linsolve()`.

```tibasic89 name=linsolve
linsolve()
Prgm
© linsolve: solve A*x=b with simult(); A as [2,1;1,3], b as [3;5]
© Exact answers (fractions) when you type exact numbers
Local sa,sb,ma,mb,sol,bad
"[2,1;1,3]"->sa
"[3;5]"->sb
Dialog
  Title "Solve A*x = b"
  Request "A as [a,b;c,d]",sa
  Request "b as [p;q]",sb
EndDlog
If ok=0
  Return
0->bad
Try
  expr(sa)->ma
  expr(sb)->mb
Else
  ClrErr
  1->bad
EndTry
If bad=1 Then
  Text "Can't read the matrices"
  Return
EndIf
If getType(ma)!="MAT" or getType(mb)!="MAT" Then
  Text "A and b must be matrices"
  Return
EndIf
If rowDim(ma)!=colDim(ma) or rowDim(mb)!=rowDim(ma) Then
  Text "A must be square, b one column"
  Return
EndIf
If det(ma)=0 Then
  Text "A is singular: no unique x"
  Return
EndIf
simult(ma,mb)->sol
ClrIO
Disp "x =",sol
Disp "Decimal:",approx(sol)
Pause
DispHome
EndPrgm
```

## Limits

- **Names:** 8 characters (programs, functions, variables, folders).
- **Request prompts:** 20 characters.
- **Bit operations:** 32-bit signed integers; bigger values wrap.
- **Numbers:** 14 digits inside, up to 12 shown; exact integers and fractions can be much longer.
- **Screen:** 160 by 100 pixels.
- **Size:** CalcSuite takes programs up to 65,000 bytes. Free memory is on the MEM screen
  (2nd, 6).
- **Speed:** CAS commands (`solve(`, `∫(`) can take seconds. Use `approx(`, `nSolve(` and
  `nInt(` inside loops.

## Sources

Checked 2026-11-27:

- TI-89 Titanium Guidebook (TI, English, 2005/2010 edition):
  [https://education.ti.com/download/en/ed-tech/FA1DC891957E4700B46A67255850C592/983EA8A4BA2A4AE9B2AF5EEEE922E3C1/TI-89_Guidebook_EN.pdf](https://education.ti.com/download/en/ed-tech/FA1DC891957E4700B46A67255850C592/983EA8A4BA2A4AE9B2AF5EEEE922E3C1/TI-89_Guidebook_EN.pdf).
  Used for the syntax of `Dialog`, `Request` (20 characters), `PopUp`, `DropDown`, `Toolbar`,
  `Text`, `Pause`, `Input`, `InputStr`, `Prompt`, `Output`, `Try`, `ClrErr`, `PassErr`,
  `Local`, `Define`, `Exit`, `Cycle`, `Loop`, `solve(`, `cSolve(`, `zeros(`, `cZeros(`,
  `nSolve(`, `d(`, `∫(`, `nInt(`, `limit(`, `expand(`, `factor(`, `simult(`, `getType(`,
  `getKey()` codes, `setMode(` names (Base Dec/Hex/Bin, Complex Format, Exact/Approx),
  `format(`, `mod(`, `intDiv(`, `and`/`or`/`xor`/`not` on 32-bit integers, `shift(`,
  `rotate(`, `0h`/`0b`, `►` for units, `tmpCnv(`, unit names, the rules for names, what a
  function may not do, the comment character and the error messages.
- CalcSuite's text converter, `tools/calc_files.py` (`program_89_data`): which spellings
  become the 89's characters, and that `►` is refused. Every example and code block in this
  guide goes through it.

Not checked on a calculator yet: the example programs (their structure is checked, and the 89
reads them for the first time when they run); that `d(` typed as letters is not the derivative
(it follows from the 89's character set, where the derivative is its own character); that
`ok` is set after a single `Request`; that `Output` uses pixels; that `setMode("Base","Hex")`
changes what `Disp` shows in a program; `tmpCnv(` with a variable; the 160 by 100 screen and
the MEM key, from TI's product data.
