# Quick start: a program on the calculator in 5 minutes

For the TI-Nspire CX II (CAS), on Windows. You don't need AI for this; the kit also works with an AI coding assistant (see README). The full details are in [README.md](README.md).

## Python programs (number crunching, menus, quick tools)

1. **Write it** as `programs/myprog.py`:
   - The name is lowercase, letters, digits and `_` only.
   - Plain ASCII, 4-space indents.
   - No f-strings: use `print("x =", x)`.
   - Only `math`, `cmath`, `random`, `time` and `ti_*` modules.
2. **Check and build it.** In a terminal in this folder:

   ```
   python -I tools/flash.py programs/myprog.py --dry-run
   ```

   Fix anything it reports. It writes `build/myprog.tns`.
3. **Test it on the PC (optional):**

   ```
   python -I tools/run_on_pc.py programs/myprog.py
   ```

4. **Send it,** any of these:
   - `python -I tools/flash.py programs/myprog.py` (checks, builds and sends in one go);
   - the **Send program...** button in Nspire Mirror;
   - or drag `build/myprog.tns` into TI-Nspire CX II Connect.
5. **Run it:** on the handheld, home > **My Documents** > `myprog`, then **ctrl+R**.

If the old version still runs, close the document on the handheld and open it again.

## TI-Basic programs (exact answers with the CAS)

Python on the calculator can't use the CAS, so it has no symbolic integrals, derivatives or `solve`. For those, write TI-Basic in **TI's TI-Nspire CX desktop software** on the PC:
- Its Program Editor works like the handheld's, but you type on your keyboard.
- Save the document as a `.tns`.
- Drag it into CX II Connect like a Python program.

TI-Basic gotchas:
- A summation is `sumSeq(expr,k,1,n)` (the `Σ` template), not `sum(`. `sum(` adds a list.
- A definite integral is `integral(f(x),x,a,b)` (the `∫` template).
- Define the function first (`Define f(x)=...`) in the same document as the program.

## Example: `numint` (in `programs/`)

Trapezoid, Simpson and a reference value for an integral.

1. Run it.
2. Type `f(x)` as text, e.g. `x^2*e^x`, `sin(x)/x` or `sqrt(1+x^3)`.
3. Then `a`, `b` and an even `n`.

`x^2*e^x` from 0 to 2 with n = 4 gives:

```
Trap:   13.996...   Simp:   12.829...   Exact:  12.778...
```

## The app: Nspire Mirror

Double-click `Nspire Mirror.exe` (or `Nspire Mirror.bat` from the source): the handheld's
screen live, your keyboard and mouse wheel as its keys, **Send program...** and
**Screenshot** buttons. It connects by itself.

## When something goes wrong

| Problem | Fix |
| --- | --- |
| The checker reports an ERROR | Change the line it names; it says what TI's Python lacks |
| "Can't read that" in `numint` | Use `*` for multiplication (`2*x`) and close every bracket |
| Drag into CX II Connect does nothing | Unplug, wait 3 s, replug; the calculator on the Home screen; no exam (Press-to-Test) mode |
| The handheld doesn't answer | Switch it on (Home screen, no dialog), close TI's own software; last resort: unplug, wait 3 s, replug |
