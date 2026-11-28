# TI-Basic on the TI-84 Plus CE

Write TI-Basic programs for the TI-84 Plus CE on the PC, by hand or with an AI assistant, and send
them with CalcSuite. This guide is for OS 5.4.0 without Python. The examples are in `programs/ti84/`.

## Contents

- [What the language is](#what-the-language-is)
- [Writing it on the PC](#writing-it-on-the-pc)
- [PC spellings](#pc-spellings)
- [Traps in the text](#traps-in-the-text)
- [Send and run](#send-and-run)
- [Variables and data](#variables-and-data)
- [Input and output](#input-and-output)
- [Control flow](#control-flow)
- [Subprograms](#subprograms)
- [Cookbook: input checks](#cookbook-input-checks)
- [Cookbook: menus](#cookbook-menus)
- [Cookbook: lists](#cookbook-lists)
- [Cookbook: matrices](#cookbook-matrices)
- [Cookbook: solving equations](#cookbook-solving-equations)
- [Cookbook: units](#cookbook-units)
- [Cookbook: complex numbers](#cookbook-complex-numbers)
- [Cookbook: number bases](#cookbook-number-bases)
- [Cookbook: integrals and derivatives](#cookbook-integrals-and-derivatives)
- [Cookbook: graph screen](#cookbook-graph-screen)
- [Errors and fixes](#errors-and-fixes)
- [Command reference](#command-reference)
- [Example programs](#example-programs)
- [Limits](#limits)
- [Sources](#sources)

## What the language is

TI-Basic on the 84 Plus CE is an interpreted language built from **tokens**. Each command,
such as `Disp` or `sin(`, is one or two bytes in the program, not the letters you see. On the PC
you type the names and CalcSuite turns them into tokens.

- **Global variables only.** There are no local variables. `A` to `Z` and `θ` hold numbers,
  and every program shares them with the home screen and with every other program.
- **One letter per name.** `AB` means `A*B`. Only lists (`ʟNAME`) and programs have longer names.
- **No functions with arguments.** A subprogram is another program (`prgmNAME`), and you pass
  values through variables, `Ans`, lists or strings.
- **Built-in maths:** `solve(`, `fnInt(`, `nDeriv(`, matrices, complex numbers and statistics.
  It has no CAS (no symbolic algebra) and no hex or binary.
- **Slow.** Every line is read again each time it runs. Keep loops short.

TI-Basic on the TI-89 is a different language. See [TIBASIC_89.md](TIBASIC_89.md).

## Writing it on the PC

- **The file:** plain text, `.txt` (`.tib` and `.bas` work too), UTF-8 or Windows-1252. The
  file name is the program name: `QUAD.txt` becomes `QUAD`.
- **Names:** up to 8 characters, `A`-`Z`, `0`-`9` or `θ`, starting with a letter. A lower case
  file name is made upper case.
- **One statement per line.** You can put several on one line with `:`. A `:` at the start of a
  line is allowed and ignored, so text copied from listings works.
- **Spaces** outside strings are ignored, so you may indent. **Tabs are not allowed**: they stop
  the send with an error.
- **Line endings:** Windows (CRLF) or Unix (LF), either is fine.
- **Case matters.** Commands are spelled exactly as the calculator shows them: `Disp`, `ClrHome`,
  `For(`, `getKey`. Variables are capitals. Outside strings, a lower case letter is a separate
  letter token, not a variable.
- **Comments:** the 84 has none. A string on its own line works as one, and that is what the
  examples use. It changes `Ans`, so don't put one between a calculation and a line that
  reads `Ans`. A closing quote at the end of a line is optional.

```tibasic84
"QUAD: ROOTS OF AX^2+BX+C=0
ClrHome
Prompt A,B,C
```

## PC spellings

What you type on the PC, and what the calculator shows. The symbols in the right-hand column
work as well (copy and paste them).

| Type on the PC | Calculator | Symbol |
| --- | --- | --- |
| `->` | store arrow | `→` |
| `<=` `>=` `!=` | less or equal, greater or equal, not equal | `≤` `≥` `≠` |
| `sqrt(` `cbrt(` | square root, cube root | `√(` `³√(` |
| `pi` `theta` | pi, theta | `π` `θ` |
| `^2` `^3` `^-1` | squared, cubed, inverse | `²` `³` `⁻¹` |
| `10^(` | ten to the power | `⏨^(` |
| `e^(` `e` | e to the power, the constant e | `𝑒^(` `𝑒` |
| `sin^-1(` `cos^-1(` `tan^-1(` | inverse trig (also the `h` versions) | `sin⁻¹(` |
| `1.5E-3` (E after a digit) | the EE key | `1.5ᴇ⁻3` |
| `-5` (at the start or after an operator), `~5` | negative sign, the (-) key | `⁻5` |
| `@` or `[i]` | imaginary unit i | `𝑖` |
| `L1` to `L6` | the lists L1 to L6 | `L₁` |
| `Y0` to `Y9` | the Y= functions | `Y₁` |
| `Str0` to `Str9`, `[A]` to `[J]` | strings, matrices | |
| `>Frac` `>Dec` `>Polar` `>Rect` | the conversion arrow | `►Frac` |
| `R>Pr(` `R>Ptheta(` `P>Rx(` `P>Ry(` | polar and rectangular | `R►Pr(` |
| `List>matr(` `Matr>list(` `String>Equ(` | the other arrows | `List►matr(` |
| `^^T` | matrix transpose | `ᵀ` |
| `^^o` `^^r` | degrees, radians after an angle | `°` `ʳ` |
| `a+bi` `re^thetai` | the complex modes | `a+b𝑖` `re^θ𝑖` |

Named lists start with the small L: type `|L` and the name, `|LRES` for the list RES (or `ʟRES`).

These are the spellings of CalcSuite's tokenizer (`tools/calc_files.py`, with the TI-Toolkit token
sheets that come with it). It also accepts the other spellings in those sheets.

## Traps in the text

These all send without an error, and then do the wrong thing on the calculator.

- **`^2` and `^3` grab one digit.** `X^23` becomes `X²3`, which is X squared times 3. Write
  `X^(23)`. Also `2^-1.5` becomes `2⁻¹.5`: write `2^(-1.5)`.
- **`10^(` after a digit.** `110^(2)` becomes `1⏨^(2)` (one times ten squared). Write `(110)^2`.
- **`E` after a digit is the EE key.** `2E-1` is 0.2, not 2 times E minus 1. Write `2*E-1`.
- **Unknown or misspelt commands become letters.** `Gridon` or `textcolor(` turn into
  separate letter tokens and the calculator stops with ERR:SYNTAX. Spell commands as in the
  command reference below.
- **`and`, `or`, `xor`, `nCr`, `nPr` need spaces around them:** `A=1 and B=2`.
- **Lower case outside strings.** `Disp x` sends the letter x, which is not the variable X.
- **`i` is not the imaginary unit** outside strings: use `@` or `[i]`.

## Send and run

- **Send:** in CalcSuite, the calculator's window > **Send program...** and pick the `.txt`, or **Files...** > **Upload**. Or from a terminal in the CalcSuite folder (below).
- **Run:** on the calculator press **PRGM**, stay on **EXEC**, pick the program and press **ENTER**. The home screen shows `prgmQUAD`. Press **ENTER** again.
- **Stop** a running program with **ON**: ERR:BREAK, then **Quit**.
- **Errors** show as `ERR:SYNTAX` with **1:Quit** and **2:Goto**. **Goto** opens the program at the line that failed.
- **Edit on the calculator:** PRGM > **EDIT**.

```
python -I tools/send_ti.py --calc 84 programs/ti84/QUAD.txt
```

Add `--name NAME` for another name, `--replace` to replace a program of the same name, or
`--out QUAD.8xp` to only make the file. A tokenizer error names the line, and nothing is sent.

## Variables and data

| Kind | Names | Example |
| --- | --- | --- |
| Number (real or complex) | `A` to `Z`, `θ` | `3.5->A` |
| List | `L1` to `L6`, named `ʟABCDE` (up to 5 characters) | `{1,2,3}->L1`, `L1(2)` |
| Matrix | `[A]` to `[J]` | `[[1,2][3,4]]->[A]`, `[A](1,2)` |
| String | `Str0` to `Str9` | `"HELLO"->Str1` |
| Function | `Y0` to `Y9` | `"X^2"->Y1`, `Y1(3)` |
| Last answer | `Ans` | `2+3:Ans*2` |

- Every variable is global and stays after the program ends.
- A number variable that was never set holds whatever was last stored in it. Set the ones
  you use at the start.
- `DelVar A` deletes a variable and frees its memory.
- Strings join with `+`: `"R="+toString(R)`. `toString(` (OS 5.2 and later) turns a number
  into a string, and `expr(` turns a string into a number.

## Input and output

| Command | What it does |
| --- | --- |
| `ClrHome` | Clears the home screen |
| `Disp "TEXT",A` | Shows each item on its own line (text on the left, numbers on the right) |
| `Output(ROW,COL,"TEXT")` | Text at a place: rows 1-10, columns 1-26 |
| `Input "R? ",R` | Asks for a value (or a list, or text for a string variable) |
| `Input Str1,X` | Uses the text in Str1 as the prompt |
| `Prompt A,B` | Asks `A=?`, then `B=?` |
| `Pause` / `Pause "TEXT",2` | Waits for ENTER, or shows TEXT for 2 seconds |
| `Wait 0.5` | Waits half a second (OS 5.2 and later) |
| `getKey->K` | The last key pressed, 0 if none (it doesn't wait) |
| `Menu("TITLE","ONE",A,"TWO",B)` | A menu that jumps to `Lbl A` or `Lbl B` |

`getKey` codes are the key's row and column: **ENTER** is 105, **CLEAR** 45, the arrows
left 24, up 25, right 26, down 34.

```tibasic84
Repeat K=105 or K=45
getKey->K
End
```

## Control flow

```tibasic84
If A>0
Disp "ONE LINE"
If A>0
Then
Disp "SEVERAL"
Disp "LINES"
Else
Disp "NOT POSITIVE"
End
For(I,1,10)
Disp I
End
For(I,10,0,-2)
Disp I
End
While A<10
A+1->A
End
Repeat A>=10
A+1->A
End
```

- `If` without `Then` covers exactly one line.
- `While` checks before each pass; `Repeat` checks after, so it runs at least once.
- `Lbl` names are one or two characters: `Lbl A`, `Lbl 1`, `Lbl AB`. `Goto A` jumps.
- **Never jump with `Goto` out of a `For(`, `While`, `Repeat` or `If ... Then` block.** Each
  jump leaves the block open and leaks memory, and the program ends with ERR:MEMORY. Use
  single-line `If`s around a `Goto`, as the examples do.
- `Stop` ends the program. `Return` ends a subprogram and goes back to the caller.

## Subprograms

A subprogram is another program called by name. It sees all the same variables.

```tibasic84
"MAIN: CALL THE SUBPROGRAM SQ
5->X
prgmSQ
Disp Y
```

```tibasic84
"SQ: SQUARE X INTO Y
X^2->Y
Return
```

Send both. Keep the names apart from your other programs, since all of them share one list.

## Cookbook: input checks

Ask again until the value is valid:

```tibasic84
0->R
Repeat R>0
Input "R (OHM, >0)? ",R
End
```

A whole number from 1 to 6:

```tibasic84
Repeat N>=1 and N<=6 and not(fPart(N))
Input "N (1-6)? ",N
End
```

There is no error trapping: typing letters where a number is wanted stops with ERR:SYNTAX or
ERR:UNDEFINED. Check the ranges you can.

## Cookbook: menus

`Menu(` jumps to a label. The CE shows up to 9 entries: a title up to 26 characters, entries
up to 24.

```tibasic84
Lbl M
Menu("CIRCUITS","RC TIME",R,"DIVIDER",D,"QUIT",Q)
Lbl R
Disp "RC CHOSEN"
Pause
Goto M
Lbl D
Disp "DIVIDER CHOSEN"
Pause
Goto M
Lbl Q
ClrHome
```

The `Goto M` lines sit outside every block, so they don't leak memory.

## Cookbook: lists

Most functions work on a whole list at once, so a loop is often not needed.

```tibasic84
{100,220,470}->L1
Disp "SERIES",sum(L1)
Disp "PARALLEL",1/sum(1/L1)
Disp "N",dim(L1)
Disp "MEAN",mean(L1)
```

A loop over a list, and building a list:

```tibasic84
0->S
For(I,1,dim(L1))
S+L1(I)^2->S
End
seq(I^2,I,1,10)->L2
SortA(L2)
```

Storing to one past the end grows a list: `5->L1(dim(L1)+1)`.

## Cookbook: matrices

```tibasic84
[[2,1][1,3]]->[A]
[[3][5]]->[B]
Disp det([A])
[A]^-1[B]->[C]
Disp [C]
Disp rref(augment([A],[B]))
```

- Set the size first: `{3,3}->dim([A])`, then fill `X->[A](I,J)`.
- `[A]^^T` is the transpose, `identity(3)` the 3 by 3 identity.
- A singular matrix stops `^-1` with ERR:SINGULAR MAT: check `det([A])` first.
- Example: `LINSOLVE` fills [A] and [B] from prompts and solves A*X=B.

## Cookbook: solving equations

`solve(expression,variable,guess,{lower,upper})` finds one root of expression = 0. The bounds
are optional. It doesn't change the variable.

```tibasic84
solve(X^3-2X-5,X,2)->R
Disp R
solve(cos(X)-X,X,0.5,{0,1})->R
Disp R
```

- It finds one real root, the one nearest the guess. Different guesses find other roots.
- ERR:BAD GUESS: the guess is outside the bounds, or the function is undefined there.
- The interactive **Solver** (MATH > 0 on the home screen) does the same by hand.
- For several unknowns that are linear, use matrices (`LINSOLVE`).

## Cookbook: units

The 84 has no units. Keep a factor per conversion (exact values where they exist):

| From | To | Multiply by |
| --- | --- | --- |
| mm | in | `1/25.4` |
| km | mi | `1/1.609344` |
| N | lbf | `1/4.4482216152605` |
| Pa | psi | `1/6894.757293168` |
| kW | hp | `1000/745.69987158227` |
| deg C | deg F | `9C/5+32` |

```tibasic84
Input "MM? ",V
Disp "IN=",V/25.4
```

Example: `UNITS` puts these in a menu.

## Cookbook: complex numbers

`@` (or `[i]`) is the imaginary unit. Set the mode with `a+bi` (rectangular) or `re^thetai`
(polar) at the start, or on the MODE screen.

```tibasic84
a+bi
3+4@->Z
Disp abs(Z),angle(Z)
Disp real(Z),imag(Z),conj(Z)
Disp Z>Polar
Disp 5e^(0.9273@)>Rect
```

- In `Real` mode, a calculation that turns complex (such as `sqrt(-4)`) stops with ERR:NONREAL ANS.
- `angle(` follows Radian or Degree mode.
- Phasors in polar form: `MAGe^(ANGLE@)` with the angle in radians.

## Cookbook: number bases

The 84 has no hex or binary. Build the digits with `remainder(` and `int(`:

```tibasic84
"0123456789ABCDEF"->Str9
255->N
16->B
sub(Str9,remainder(N,B)+1,1)->Str1
int(N/B)->N
While N>0
sub(Str9,remainder(N,B)+1,1)+Str1->Str1
int(N/B)->N
End
Disp Str1
```

Hex to decimal: `inString(Str9,sub(Str2,I,1))-1` is the value of the I-th digit; multiply by 16
and add, digit by digit. There are no bitwise operators: `and`, `or`, `xor` are logical (true is
1, false 0). For bit tests use `int(N/2^K)` and `remainder(`. Numbers have 14 digits, so stay below
10^12. Example: `BASE`.

## Cookbook: integrals and derivatives

```tibasic84
Disp fnInt(X^2*sin(X),X,0,2)
Disp nDeriv(X^3,X,2)
```

- `fnInt(expression,variable,lower,upper[,tolerance])` (default tolerance 1E-5).
- `nDeriv(expression,variable,value[,h])` (default h 0.001). Only one `nDeriv(` inside another.
- A function the user types: `Input "F(X)=",Str1`, then `Str1->Y1`, and use `Y1` in the
  expression and `Y1(2)` for a value.
- Example: `NUMINT` compares the trapezoid and Simpson rules with `fnInt(`.

## Cookbook: graph screen

The CE's graph screen is 265 by 165 pixels. `Text(` uses pixels (row 0-164, column 0-264); the
other drawing commands use the window (`Xmin`, `Xmax`, `Ymin`, `Ymax`).

```tibasic84
ClrDraw
AxesOff
FnOff
-10->Xmin
10->Xmax
-10->Ymin
10->Ymax
Line(-8,0,8,0,1,BLUE)
Circle(0,0,5,RED)
TextColor(GREEN)
Text(10,10,"HELLO")
DispGraph
Pause
```

- `Line(X1,Y1,X2,Y2[,erase,color,style])` (erase 1 draws, 0 erases) and `Circle(X,Y,R[,color,style])`; colours are
  `BLUE`, `RED`, `BLACK`, `MAGENTA`, `GREEN`, `ORANGE`, `BROWN`, `NAVY`, `LTBLUE`, `YELLOW`,
  `WHITE`, `LTGRAY`, `MEDGRAY`, `GRAY`, `DARKGRAY` (or 10 to 24).
- `"X^2"->Y1` puts a function into Y=, and `DispGraph` draws it.
- `Pause` keeps the picture up. Press ENTER to go on.

## Errors and fixes

| Error | Usual cause | Fix |
| --- | --- | --- |
| ERR:SYNTAX | A misspelt command (sent as letters), a missing comma or bracket, lower case outside strings | Goto shows the line. Compare the spelling with the command reference. |
| ERR:DATA TYPE | A complex number where a real is needed, a matrix stored to a list | Check what each variable holds |
| ERR:UNDEFINED | A list, matrix or string used before it was stored | Store it first (`{0}->L1`, `""->Str1`) |
| ERR:MEMORY | `Goto` out of a loop or `If ... Then` block, deep recursion of programs | Restructure with single-line `If`; free RAM in MEM |
| ERR:DIM MISMATCH | Lists or matrices of different sizes | Check `dim(` |
| ERR:INVALID DIM | An element past the end, inverse of a non-square matrix | Check the index and `dim(` |
| ERR:DOMAIN | An argument out of range (`Output(` off the screen, `ln(0)`) | Check the range |
| ERR:NONREAL ANS | A complex result in Real mode | `a+bi` mode, or check the sign |
| ERR:LABEL | `Goto` or `Menu(` to a `Lbl` that isn't there | Add the label |
| ERR:INVALID | A program-only command on the home screen (`Menu(`, `Wait`) | Run it from a program |
| ERR:ARGUMENT | Too many or too few arguments | Check the syntax below |
| ERR:SINGULAR MAT | Inverse of a matrix with determinant 0 | Check `det(` first |
| ERR:BAD GUESS | `solve(` guess outside its bounds | Change the guess or the bounds |
| ERR:BREAK | ON was pressed | Quit |

Errors from CalcSuite before sending: "isn't a TI-84 Plus token or character" names the line
(a tab, or a character the 84 doesn't have); "can't be a TI-84 program name" means the name
needs up to 8 capitals or digits starting with a letter.

## Command reference

| Command | What it does | Example |
| --- | --- | --- |
| `ClrHome` | Clears the home screen | `ClrHome` |
| `Disp` | Shows values or text | `Disp "V=",V` |
| `Output(` | Text at row, column | `Output(1,1,"HI")` |
| `Input` | Asks for a value | `Input "R? ",R` |
| `Prompt` | Asks for variables by name | `Prompt A,B` |
| `Pause` | Waits for ENTER | `Pause` |
| `Wait` | Waits seconds (OS 5.2+) | `Wait 1` |
| `getKey` | Last key code, 0 if none | `getKey->K` |
| `Menu(` | Menu of labels | `Menu("T","A",1,"B",2)` |
| `If` `Then` `Else` `End` | Branches | `If A>0` |
| `For(` | Counted loop | `For(I,1,N)` |
| `While` / `Repeat` | Loops | `While A<5` |
| `Lbl` / `Goto` | Labels and jumps | `Goto A` |
| `prgm` | Runs another program | `prgmSQ` |
| `Return` / `Stop` | Ends a subprogram / the program | `Stop` |
| `DelVar` | Deletes a variable | `DelVar A` |
| `solve(` | One root of expr = 0 | `solve(X^2-2,X,1)` |
| `fnInt(` | Numeric integral | `fnInt(X^2,X,0,1)` |
| `nDeriv(` | Numeric derivative | `nDeriv(X^3,X,2)` |
| `sum(` `prod(` | Sum, product of a list | `sum(L1)` |
| `dim(` | Size of a list or matrix | `dim(L1)` |
| `seq(` | Builds a list | `seq(I^2,I,1,5)` |
| `SortA(` `SortD(` | Sorts a list | `SortA(L1)` |
| `det(` `identity(` `rref(` `augment(` | Matrix functions | `det([A])` |
| `abs(` `angle(` `real(` `imag(` `conj(` | Complex functions | `abs(3+4@)` |
| `round(` `int(` `iPart(` `fPart(` | Rounding and parts | `round(X,3)` |
| `remainder(` | Remainder of a division | `remainder(17,5)` |
| `min(` `max(` | Smaller, larger | `max(A,B)` |
| `randInt(` `rand` | Random numbers | `randInt(1,6)` |
| `logBASE(` `ln(` `log(` `e^(` | Logarithms, powers | `logBASE(8,2)` |
| `sub(` `length(` `inString(` | String functions | `sub(Str1,1,3)` |
| `toString(` `expr(` `eval(` | Number to string, string to number | `toString(R)` |
| `>Frac` `>Dec` | Shows as a fraction / decimal | `0.75>Frac` |
| `Degree` `Radian` | Angle mode | `Degree` |
| `Fix` `Float` | Decimal places shown | `Fix 3` |
| `Real` `a+bi` `re^thetai` | Complex mode | `a+bi` |
| `ClrDraw` `Line(` `Circle(` `Text(` `DispGraph` | Graph screen | `Circle(0,0,5)` |
| `TextColor(` | Colour for `Text(` | `TextColor(RED)` |
| `startTmr` `checkTmr(` | Seconds since a start | `checkTmr(T)` |

## Example programs

Each starts with string lines that say what it does. Send one with the button on its block,
or `python -I tools/send_ti.py --calc 84 programs/ti84/NAME.txt`.

### QUAD

Roots of a quadratic, real or complex, without changing the complex mode. Run it, then type A, B and C.

```tibasic84 name=QUAD
"QUAD: ROOTS OF AX^2+BX+C=0
"REAL OR COMPLEX, ANY MODE
ClrHome
Disp "AX^2+BX+C=0"
Prompt A,B,C
If A=0
Then
If B=0
Then
Disp "NOT AN EQUATION"
Stop
End
Disp "LINEAR, X=",-C/B
Stop
End
B^2-4AC->D
If D>=0
Then
(-B+sqrt(D))/(2A)->R
(-B-sqrt(D))/(2A)->S
Disp "X1=",R,"X2=",S
Else
-B/(2A)->R
sqrt(-D)/(2A)->S
Disp "COMPLEX PAIR X=RE+/-IM*I"
Disp "RE=",R,"IM=",S
End
```

### RESNET

Series and parallel resistance of a list such as `{100,220,470}`, and a voltage divider. A menu; QUIT leaves.

```tibasic84 name=RESNET
"RESNET: SERIES, PARALLEL
"AND VOLTAGE DIVIDER
Lbl M
Menu("RESISTORS","SERIES",S,"PARALLEL",P,"VOLTAGE DIVIDER",D,"QUIT",Q)
Lbl S
Input "R LIST {R1,R2..}? ",L1
Disp "R TOTAL=",sum(L1)
Pause
Goto M
Lbl P
Input "R LIST {R1,R2..}? ",L1
If min(L1)>0
Disp "R PARALLEL=",1/sum(1/L1)
If min(L1)<=0
Disp "EVERY R MUST BE >0"
Pause
Goto M
Lbl D
Input "VIN? ",V
Input "R1 (TOP)? ",R
Input "R2 (BOTTOM)? ",S
If R+S>0
Disp "VOUT=",VS/(R+S)
If R+S<=0
Disp "R1+R2 MUST BE >0"
Pause
Goto M
Lbl Q
ClrHome
```

### UNITS

Engineering unit conversions from a menu: mm, in, km, mi, N, lbf, Pa, psi, kW, hp, deg C, deg F.

```tibasic84 name=UNITS
"UNITS: ENGINEERING UNIT
"CONVERSIONS FROM A MENU
Lbl M
Menu("CONVERT","MM TO IN",A,"IN TO MM",B,"KM TO MI",C,"N TO LBF",D,"PA TO PSI",E,"KW TO HP",F,"DEG C TO DEG F",G,"DEG F TO DEG C",H,"QUIT",Q)
Lbl A
1/25.4->K
Goto X
Lbl B
25.4->K
Goto X
Lbl C
1/1.609344->K
Goto X
Lbl D
1/4.4482216152605->K
Goto X
Lbl E
1/6894.757293168->K
Goto X
Lbl F
1000/745.69987158227->K
Lbl X
Input "VALUE? ",V
Disp "RESULT=",VK
Pause
Goto M
Lbl G
Input "DEG C? ",V
Disp "DEG F=",9V/5+32
Pause
Goto M
Lbl H
Input "DEG F? ",V
Disp "DEG C=",5(V-32)/9
Pause
Goto M
Lbl Q
ClrHome
```

### NUMINT

Trapezoid and Simpson rules for a function you type in X (with the calculator's keys, e.g. `X^2*sin(X)`), compared with `fnInt(`. Stores the function in Y1.

```tibasic84 name=NUMINT
"NUMINT: TRAPEZOID AND SIMPSON
"RULES, CHECKED WITH FNINT(
"TYPE F IN X, E.G. X^2*SIN(X)
ClrHome
Input "F(X)=",Str1
Str1->Y1
Input "A? ",A
Input "B? ",B
0->N
Repeat N>=2 and not(fPart(N/2))
Input "EVEN N? ",N
End
(B-A)/N->H
Y1(A)+Y1(B)->T
T->S
For(I,1,N-1)
Y1(A+IH)->F
T+2F->T
S+(4-2not(fPart(I/2)))F->S
End
ClrHome
Disp "TRAPEZOID",TH/2
Disp "SIMPSON",SH/3
Disp "FNINT",fnInt(Y1,X,A,B)
```

### BASE

Decimal to hex, binary or octal, and hex to decimal. Type hex digits with ALPHA.

```tibasic84 name=BASE
"BASE: DECIMAL TO HEX, BINARY
"OR OCTAL, AND HEX TO DECIMAL
"0123456789ABCDEF"->Str9
Menu("BASE CONVERTER","DEC TO HEX",H,"DEC TO BIN",B,"DEC TO OCT",O,"HEX TO DEC",X,"QUIT",Q)
Lbl H
16->B
Goto C
Lbl B
2->B
Goto C
Lbl O
8->B
Lbl C
Input "DECIMAL? ",N
If N<0 or fPart(N) or N>=1E12
Then
Disp "WHOLE NUMBER","FROM 0 TO 10^12"
Stop
End
sub(Str9,remainder(N,B)+1,1)->Str1
int(N/B)->N
While N>0
sub(Str9,remainder(N,B)+1,1)+Str1->Str1
int(N/B)->N
End
Disp Str1
Stop
Lbl X
Input "HEX (0-9,A-F)? ",Str2
0->N
For(I,1,length(Str2))
inString(Str9,sub(Str2,I,1))-1->D
If D<0 or D>15
Then
Disp "NOT A HEX DIGIT"
Stop
End
16N+D->N
End
Disp N
Stop
Lbl Q
ClrHome
```

### RCTAU

Time constant of an RC or RL circuit, 5 tau, and v(t) for a charging and a decaying step.

```tibasic84 name=RCTAU
"RCTAU: TIME CONSTANT OF AN
"RC OR RL CIRCUIT, V(T)
Menu("TIME CONSTANT","RC CIRCUIT",C,"RL CIRCUIT",L,"QUIT",Q)
Lbl C
Input "R (OHM)? ",R
Input "C (FARAD)? ",C
RC->T
Goto S
Lbl L
Input "L (HENRY)? ",L
Input "R (OHM)? ",R
If R<=0
Then
Disp "R MUST BE >0"
Stop
End
L/R->T
Lbl S
If T<=0
Then
Disp "TAU MUST BE >0"
Stop
End
ClrHome
Disp "TAU (S)=",T,"5 TAU (S)=",5T
Input "STEP V? ",V
Input "AT TIME (S)? ",X
Disp "CHARGING V=",V(1-e^(-X/T))
Disp "DECAYING V=",Ve^(-X/T)
Stop
Lbl Q
ClrHome
```

### VECTOR

Adds 2D forces given as a list of magnitudes and a list of angles in degrees: components, resultant and its angle. Switches to Degree mode.

```tibasic84 name=VECTOR
"VECTOR: ADD 2D FORCES GIVEN
"AS MAGNITUDES AND ANGLES (DEG)
"SETS DEGREE MODE
Degree
ClrHome
Input "MAGNITUDES {..}? ",L1
Input "ANGLES DEG {..}? ",L2
If dim(L1)!=dim(L2)
Then
Disp "THE LISTS DIFFER","IN SIZE"
Stop
End
sum(L1cos(L2))->X
sum(L1sin(L2))->Y
ClrHome
Disp "SUM FX=",X,"SUM FY=",Y
Disp "RESULTANT=",R►Pr(X,Y)
Disp "ANGLE (DEG)=",R►Pθ(X,Y)
```

### LINSOLVE

Solves N linear equations A*X=B (N up to 6), asking for each element; checks for a singular matrix.

```tibasic84 name=LINSOLVE
"LINSOLVE: N LINEAR EQUATIONS
"[A]*X=[B], ENTERED ROW BY ROW
ClrHome
Input "UNKNOWNS (1-6)? ",N
If N<1 or N>6 or fPart(N)
Then
Disp "N FROM 1 TO 6"
Stop
End
{N,N}->dim([A])
{N,1}->dim([B])
For(I,1,N)
For(J,1,N)
"A("+toString(I)+","+toString(J)+")="->Str1
Input Str1,X
X->[A](I,J)
End
"B("+toString(I)+")="->Str1
Input Str1,X
X->[B](I,1)
End
If det([A])=0
Then
Disp "SINGULAR MATRIX:","NO UNIQUE SOLUTION"
Stop
End
[A]^-1[B]->[C]
ClrHome
Disp "X=",[C]
```

## Limits

- **Program names:** 8 characters. **List names:** 5 characters after the `ʟ`.
- **Numbers:** about 14 significant digits inside, 10 shown.
- **Home screen:** 10 rows by 26 columns. **Graph screen:** 265 by 165 pixels.
- **Size:** CalcSuite takes programs up to 65,000 bytes of tokens. The free RAM is on the
  calculator's MEM screen (2nd, +, About or Mem Management).
- **Speed:** every command is interpreted each time it runs. A loop of a few thousand steps
  takes seconds, so do whole-list operations (`sum(`, `seq(`) where you can.
- **Recursion:** a program that calls itself works but every call costs memory. Use loops.

## Sources

Checked 2026-11-27:

- TI-84 Plus CE Reference Guide, Commands and Functions Listing (TI eGuide, OS 5.7 edition):
  syntax of `Circle(`, `Line(`, `Text(`, `TextColor(`, `solve(`, `fnInt(`, `nDeriv(`, `Menu(`,
  `Output(`, `Pause`, `Wait`, `toString(`, `eval(`, `remainder(`, `Input`, `For(`, the colour
  numbers 10-24 and the graph screen range.
  [https://education.ti.com/html/webhelp/EG_TI84PlusCE/EN/Subsystems/e-guide_ref84plus_en/content/m_appxa/aa_appxalpha.HTML](https://education.ti.com/html/webhelp/EG_TI84PlusCE/EN/Subsystems/e-guide_ref84plus_en/content/m_appxa/aa_appxalpha.HTML)
- TI-Basic Developer wiki: `solve(` (one root, bounds, ERR:BAD GUESS), `Menu(` (9 entries, 26
  and 24 characters on the CE), `fnInt(` and `nDeriv(` defaults, `Output(` (26 columns),
  `Text(` ranges, `toString(` and `Wait` (OS 5.2), the error messages, `getKey` codes.
  [http://tibasicdev.wikidot.com/solve](http://tibasicdev.wikidot.com/solve), [http://tibasicdev.wikidot.com/menu](http://tibasicdev.wikidot.com/menu),
  [http://tibasicdev.wikidot.com/errors](http://tibasicdev.wikidot.com/errors), [http://tibasicdev.wikidot.com/key-codes](http://tibasicdev.wikidot.com/key-codes)
- CalcSuite's tokenizer, `tools/calc_files.py`: the spellings table and the traps were tried
  on it, and every example program and every code block in this guide goes through it and back.

Not checked on a calculator yet: the example programs (they tokenize and read back, but have
not been run on OS 5.4.0); `Str1->Y1` with a string variable (TI documents `String►Equ(`, which
works too); the getKey codes other than ENTER, which follow the row and column rule; that a
colon inside a string is kept as text.
