# Python on the TI-Nspire CX II

Write Python programs for the TI-Nspire CX II (and CX II CAS) on the PC, by hand or with an AI
assistant, check them, and send them with CalcSuite. The long version, with the tools and the
manual route through TI's software, is [PYTHON_KIT.md](PYTHON_KIT.md).

## Contents

- [What the calculator's Python is](#what-the-calculators-python-is)
- [Rules for the code](#rules-for-the-code)
- [Write, check, send](#write-check-send)
- [Run it on the handheld](#run-it-on-the-handheld)
- [Input and output](#input-and-output)
- [Cookbook: input checks](#cookbook-input-checks)
- [Cookbook: menus](#cookbook-menus)
- [Cookbook: lists](#cookbook-lists)
- [Cookbook: matrices](#cookbook-matrices)
- [Cookbook: solving equations](#cookbook-solving-equations)
- [Cookbook: units](#cookbook-units)
- [Cookbook: complex numbers](#cookbook-complex-numbers)
- [Cookbook: number bases and bits](#cookbook-number-bases-and-bits)
- [Cookbook: integrals and derivatives](#cookbook-integrals-and-derivatives)
- [Cookbook: graphs](#cookbook-graphs)
- [Cookbook: results for the CAS](#cookbook-results-for-the-cas)
- [Problems and fixes](#problems-and-fixes)
- [Example programs](#example-programs)
- [Sources](#sources)

## What the calculator's Python is

| | |
| --- | --- |
| Models | TI-Nspire CX II, CX II CAS (and the -T and -C versions). The older CX without "II" has no Python. |
| OS | 5.2 or later. |
| Engine | TI's port of MicroPython: a small Python 3. |
| Modules | `math`, `cmath`, `random`, `time`, and TI's `ti_system`, `ti_draw`, `ti_plotlib`, `ti_image` (`ti_hub`, `ti_rover` with TI's robotics hardware). |
| Not there | numpy, sympy, matplotlib, os, re, json, itertools and the rest of the standard library; files (`open`); the network. |
| Memory | About 2 MB of heap (community measurement). Keep lists to a few thousand items. |
| Screen | `ti_draw`: 318 by 212 pixels, (0,0) at the top left. |
| The CAS | Python can't do symbolic maths. It can hand numbers and lists to the CAS with `ti_system`. |

## Rules for the code

- **File:** `programs/name.py`, the name in lower case letters, digits and `_`, a letter first.
- **Plain ASCII**, 4-space indents, no tabs. No curly quotes, long dashes, `π` or `≤` (write
  `pi`, `<=`).
- **No f-strings:** `print("x =", x)` or `"{} {}".format(a, b)`.
- **Also avoid:** the walrus `:=`, `match`, type hints, `async`, underscores in numbers
  (`1_000`), and string extras such as `ljust`, `rjust`, `zfill`, `partition`.
- **Fine:** functions, classes, `lambda`, `try/except`, list comprehensions, `global`.
- **Recursion** is shallow: use loops.
- **Short lines of output:** about 30 characters read well on the screen.

## Write, check, send

- **Check** (no calculator needed) with the first command below. Fix every ERROR; fix warnings too unless you have tried that feature on the handheld (`programs/probe.py`).
- **Try on the PC** (optional) with the second. It runs with stand-in TI modules; `--gui` shows `ti_draw` drawings.
- **Send** with CalcSuite's **Send program...** button, or the third command: it checks again, makes `build/name.tns`, uploads it to My Documents and reads it back. `--dry-run` only makes the `.tns`.

```
python -I tools/check_nspire.py programs/name.py
python -I tools/run_on_pc.py programs/name.py
python -I tools/flash.py programs/name.py
```

## Run it on the handheld

**home > My Documents >** `name.tns`, then **menu > Run > Run** (**ctrl+R**). Output appears on a
Python Shell page; **ctrl+R** there runs it again. Stop a running program with **home/on**.
If the document was open while you sent a new version, close it (don't save) and open it again.

## Input and output

- `input("prompt")` always returns a **string**: convert it with `float()` or `int()`.
- `print()` writes to the Shell.
- `ti_system.get_key()` returns the key being pressed (`""` if none); `get_key(1)` waits for one.
  Keys are names: `"enter"`, `"esc"`, `"up"`, `"1"`.

```python
from ti_system import get_key
print("Press a key")
k = get_key(1)
print("You pressed", k)
```

## Cookbook: input checks

```python
def ask(prompt, low=None):
    while True:
        try:
            v = float(input(prompt))
        except ValueError:
            print("Type a number.")
            continue
        if low is not None and v <= low:
            print("Must be >", low)
            continue
        return v


r = ask("R (ohm) = ", 0)
```

## Cookbook: menus

```python
def menu(title, items):
    print(title)
    for i in range(len(items)):
        print(i + 1, items[i])
    while True:
        s = input("Choice: ")
        if s.isdigit() and 1 <= int(s) <= len(items):
            return int(s)
        print("1 to", len(items))


c = menu("Circuits", ["RC time", "Divider", "Quit"])
```

## Cookbook: lists

```python
r = [100.0, 220.0, 470.0]
print("series", sum(r))
print("parallel", 1 / sum([1 / x for x in r]))
print("largest", max(r))
sq = [k * k for k in range(1, 11)]
r.sort()
```

## Cookbook: matrices

There is no matrix type: use lists of rows. Gaussian elimination with pivoting solves A*x = b:

```python
def solve(a, b):
    n = len(a)
    m = [a[i][:] + [b[i]] for i in range(n)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(m[r][c]))
        if abs(m[p][c]) < 1e-12:
            return None
        m[c], m[p] = m[p], m[c]
        for r in range(c + 1, n):
            f = m[r][c] / m[c][c]
            for k in range(c, n + 1):
                m[r][k] -= f * m[c][k]
    x = [0.0] * n
    for r in range(n - 1, -1, -1):
        s = m[r][n] - sum([m[r][k] * x[k] for k in range(r + 1, n)])
        x[r] = s / m[r][r]
    return x


print(solve([[2, 1], [1, 3]], [3, 5]))
```

For exact answers, use the CAS's `simult(` or `rref(` outside Python.

## Cookbook: solving equations

Bisection always converges when f(a) and f(b) have opposite signs; Newton is fast near a root.

```python
from math import cos


def f(x):
    return cos(x) - x


def bisect(f, a, b, tol=1e-10):
    if f(a) * f(b) > 0:
        return None
    while b - a > tol:
        m = (a + b) / 2
        if f(a) * f(m) <= 0:
            b = m
        else:
            a = m
    return (a + b) / 2


def newton(f, x, h=1e-6):
    for _ in range(50):
        d = (f(x + h) - f(x - h)) / (2 * h)
        if d == 0:
            return None
        step = f(x) / d
        x -= step
        if abs(step) < 1e-12:
            return x
    return None


print(bisect(f, 0, 1), newton(f, 0.5))
```

## Cookbook: units

```python
TO_SI = {"mm": 0.001, "in": 0.0254, "ft": 0.3048, "km": 1000.0, "mi": 1609.344,
         "N": 1.0, "lbf": 4.4482216152605, "Pa": 1.0, "psi": 6894.757293168,
         "W": 1.0, "kW": 1000.0, "hp": 745.69987158227}


def convert(v, a, b):
    return v * TO_SI[a] / TO_SI[b]


print(convert(25.4, "mm", "in"))
print(convert(100, "psi", "Pa"))
```

Only convert between units of the same kind. Temperature needs its own formula: `f = c * 9 / 5 + 32`.

## Cookbook: complex numbers

Python writes the imaginary unit as `j`: `3+4j`. `cmath` has the rest.

```python
import cmath
z = 3 + 4j
print(abs(z), cmath.phase(z))
r, phi = cmath.polar(z)
print(cmath.rect(r, phi))
zc = 1 / (1j * 2 * cmath.pi * 50 * 1e-6)
print("Zc =", zc)
print(cmath.sqrt(-4))
```

`cmath.phase` is in radians: `math.degrees(...)` for degrees.

## Cookbook: number bases and bits

```python
n = 0xF0
print(hex(n), bin(n))
print(int("ff", 16), int("1010", 2))
print(hex(0xF0 & 0x3C), hex(0xF0 | 0x0F), hex(0xFF ^ 0x0F))
print(n << 2, n >> 4)
```

Python integers have no size limit. To act like a 16-bit register, mask: `(n << 2) & 0xFFFF`.
`hex()`, `bin()` and `int(s, base)` are MicroPython built-ins, not in TI's menus: try them with
`probe.py` or the example below.

## Cookbook: integrals and derivatives

```python
from math import sin


def f(x):
    return x * x * sin(x)


def simpson(f, a, b, n=100):
    if n % 2:
        n += 1
    h = (b - a) / n
    s = f(a) + f(b)
    for k in range(1, n):
        s += (4 if k % 2 else 2) * f(a + k * h)
    return s * h / 3


def deriv(f, x, h=1e-5):
    return (f(x + h) - f(x - h)) / (2 * h)


print(simpson(f, 0, 2), deriv(f, 1))
```

## Cookbook: graphs

```python
import ti_plotlib as plt
from math import sin
xs = [i / 10 for i in range(-60, 61)]
ys = [sin(x) for x in xs]
plt.cls()
plt.window(-6, 6, -1.5, 1.5)
plt.axes("on")
plt.plot(xs, ys, ".")
plt.show_plot()
```

For pixel drawing use `ti_draw` (`draw_line`, `fill_rect`, `draw_text`, `set_color`), and end
with `ti_system.get_key(1)` so the picture stays up.

## Cookbook: results for the CAS

```python
from ti_system import store_value, store_list, recall_value
store_value("tau", 0.0022)
store_list("vals", [1.0, 2.5, 4.0])
r = recall_value("r1")
```

After the program, `tau` and `vals` are variables in the document, so the Calculator page can
use them in `solve(`, `integral(` and the rest. `recall_value` reads one that exists already.

## Problems and fixes

| Problem | Fix |
| --- | --- |
| The checker reports non-ASCII | A curly quote, a long dash or a symbol: retype it in ASCII |
| `SyntaxError` on the handheld | An f-string, walrus or type hint the checker would have found; or tabs |
| `ImportError` | A module the calculator lacks |
| `AttributeError: ... 'ljust'` | A CPython-only string method: pad by hand |
| `MemoryError` | A list too big or recursion too deep |
| `ValueError` from `float(input(...))` | Wrap it in `try/except`, as in the input checks |
| The old version still runs | Close the document on the handheld and open it again |
| "No TI-Nspire found" | Switch it on, a data cable, close TI's software |

## Example programs

Complete programs: send one with the button on its block, or save it as `programs/NAME.py` and run
`python -I tools/flash.py programs/NAME.py`.

### resnet

Series and parallel resistance of values you type, and a voltage divider, from a menu.

```python name=resnet
# resnet: series and parallel resistance, and a voltage divider
# Type resistor values separated by spaces, e.g. 100 220 470


def ask(prompt):
    while True:
        try:
            return float(input(prompt))
        except ValueError:
            print("Type a number.")


def ask_list(prompt):
    while True:
        parts = input(prompt).replace(",", " ").split()
        try:
            vals = [float(p) for p in parts]
        except ValueError:
            vals = []
        if vals and min(vals) > 0:
            return vals
        print("Values > 0, with spaces.")


while True:
    print("1 series  2 parallel")
    print("3 divider 4 quit")
    c = input("Choice: ")
    if c == "1":
        print("R =", sum(ask_list("R values: ")))
    elif c == "2":
        r = ask_list("R values: ")
        print("R =", 1 / sum([1 / x for x in r]))
    elif c == "3":
        vin = ask("Vin = ")
        r1 = ask("R1 (top) = ")
        r2 = ask("R2 (bottom) = ")
        if r1 + r2 > 0:
            print("Vout =", vin * r2 / (r1 + r2))
    elif c == "4":
        break
```

### rctau

RC or RL time constant and v(t) for a step, charging and decaying.

```python name=rctau
# rctau: time constant of an RC or RL circuit, and v(t)
from math import exp


def ask(prompt):
    while True:
        try:
            v = float(input(prompt))
            if v > 0:
                return v
        except ValueError:
            pass
        print("Type a number > 0.")


kind = input("RC or RL? ").strip().upper()
r = ask("R (ohm) = ")
if kind == "RL":
    tau = ask("L (H) = ") / r
else:
    tau = r * ask("C (F) = ")
print("tau =", tau, "s")
print("5 tau =", 5 * tau, "s")
v = ask("Step V = ")
t = ask("At t (s) = ")
print("charging:", v * (1 - exp(-t / tau)))
print("decaying:", v * exp(-t / tau))
```

### bases

Decimal, hex and binary, and bitwise and/or/xor of two numbers.

```python name=bases
# bases: decimal, hex and binary; bitwise and, or, xor
# Type numbers as 255, 0xff or 0b1010


def ask_int(prompt):
    while True:
        s = input(prompt).strip().lower()
        try:
            if s.startswith("0x"):
                return int(s[2:], 16)
            if s.startswith("0b"):
                return int(s[2:], 2)
            return int(s)
        except ValueError:
            print("255, 0xff or 0b1010")


a = ask_int("a = ")
print("dec", a, "hex", hex(a))
print("bin", bin(a))
b = ask_int("b = ")
print("a & b =", hex(a & b))
print("a | b =", hex(a | b))
print("a ^ b =", hex(a ^ b))
```

### phasor

Impedance of R, L and C in series at a frequency, as a complex number and in polar form.

```python name=phasor
# phasor: series R, L, C at frequency f: impedance and current
import cmath
from math import degrees, pi


def ask(prompt):
    while True:
        try:
            return float(input(prompt))
        except ValueError:
            print("Type a number.")


r = ask("R (ohm) = ")
l = ask("L (H, 0 if none) = ")
c = ask("C (F, 0 if none) = ")
f = ask("f (Hz) = ")
w = 2 * pi * f
z = complex(r, w * l)
if c > 0:
    z += 1 / (1j * w * c)
mag, ang = cmath.polar(z)
print("Z =", z)
print("|Z| =", mag)
print("angle =", degrees(ang), "deg")
v = ask("V (rms) = ")
if mag > 0:
    print("I =", v / mag, "A rms")
```

### linsolve

Solves N linear equations A*x = b with Gaussian elimination.

```python name=linsolve
# linsolve: solve A*x = b (N equations) by Gaussian elimination
# Type each row of A as numbers separated by spaces


def ask_row(prompt, n):
    while True:
        try:
            row = [float(p) for p in input(prompt).split()]
            if len(row) == n:
                return row
        except ValueError:
            pass
        print("Type", n, "numbers.")


def solve(a, b):
    n = len(a)
    m = [a[i][:] + [b[i]] for i in range(n)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(m[r][c]))
        if abs(m[p][c]) < 1e-12:
            return None
        m[c], m[p] = m[p], m[c]
        for r in range(c + 1, n):
            f = m[r][c] / m[c][c]
            for k in range(c, n + 1):
                m[r][k] -= f * m[c][k]
    x = [0.0] * n
    for r in range(n - 1, -1, -1):
        s = m[r][n] - sum([m[r][k] * x[k] for k in range(r + 1, n)])
        x[r] = s / m[r][r]
    return x


n = 0
while n < 1 or n > 8:
    try:
        n = int(input("N (1-8) = "))
    except ValueError:
        n = 0
a = [ask_row("Row " + str(i + 1) + ": ", n) for i in range(n)]
b = ask_row("b: ", n)
x = solve(a, b)
if x is None:
    print("Singular: no unique x")
else:
    for i in range(n):
        print("x" + str(i + 1), "=", round(x[i], 8))
```

The repo also has `programs/quadratic.py` (complex roots), `programs/numint.py` (trapezoid and
Simpson for a function you type), `programs/critpts.py` and `programs/draw_demo.py`.

## Sources

- TI-Nspire Python Programming Guidebook and TI's online eGuide (modules, menus, `ti_system`,
  `ti_draw`, `ti_plotlib`), as listed in the Sources of [PYTHON_KIT.md](PYTHON_KIT.md).
- CalcSuite's checker, `tools/check_nspire.py`: every example and code block here passes it, and
  the complete programs run on the PC with `tools/run_on_pc.py`.

Not checked on a handheld: `hex()`, `bin()`, `int(s, base)` and `str.isdigit()` (MicroPython has
them; TI's menus don't list them); the examples themselves.
