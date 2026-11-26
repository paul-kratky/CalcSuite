"""Run a TI-Nspire program on the PC with the stub modules in tools/ti_shim/.

    python -I tools/run_on_pc.py programs/quadratic.py
    python -I tools/run_on_pc.py --gui programs/draw_demo.py
    python -I tools/run_on_pc.py --var a=3 --list L1=1,2,3 --func f=x**2 --keys up,enter prog.py

Options:
    --gui            draw ti_draw / ti_plotlib / ti_image output in a 318x212 window (x2)
    --quiet          do not log graphics / ti_system calls to stderr
    --var N=V        TI variable for ti_system.recall_value("N") (number, else text)
    --list N=1,2,3   TI list for ti_system.recall_list("N")
    --func N=EXPR    TI function for ti_system.eval_function("N", x); EXPR uses x
    --keys k1,k2     keys returned by ti_system.get_key() in order, then "esc"

This checks LOGIC only. The PC runs CPython, not the calculator's MicroPython: always run
tools/check_nspire.py too, and test on the handheld for speed, memory and the real screen.
"""

import math
import os
import runpy
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SHIM = os.path.join(HERE, "ti_shim")


def _number(text):
    try:
        return int(text)
    except ValueError:
        try:
            return float(text)
        except ValueError:
            return text


def _patch_time():
    """Add the MicroPython-only time functions TI documents."""
    t0 = time.perf_counter()
    if not hasattr(time, "ticks_ms"):
        time.ticks_ms = lambda: int((time.perf_counter() - t0) * 1000)
    if not hasattr(time, "ticks_cpu"):
        time.ticks_cpu = lambda: int((time.perf_counter() - t0) * 1000000)
    if not hasattr(time, "ticks_diff"):
        time.ticks_diff = lambda new, old: new - old
    if not hasattr(time, "clock"):
        time.clock = time.perf_counter


def main(argv):
    gui = quiet = False
    variables, lists, funcs, keys = {}, {}, {}, []
    program = None
    i = 0
    while i < len(argv):
        a = argv[i]
        nxt = argv[i + 1] if i + 1 < len(argv) else ""
        if a == "--gui":
            gui = True
        elif a == "--quiet":
            quiet = True
        elif a in ("--var", "--list", "--func") and "=" in nxt:
            name, value = nxt.split("=", 1)
            if a == "--var":
                variables[name] = _number(value)
            elif a == "--list":
                lists[name] = [_number(v) for v in value.split(",") if v.strip()]
            else:
                funcs[name] = (lambda expr: lambda x: eval(expr, vars(math), {"x": x}))(value)
            i += 1
        elif a == "--keys":
            keys = [k.strip() for k in nxt.split(",") if k.strip()]
            i += 1
        elif a in ("-h", "--help"):
            print(__doc__)
            return 0
        elif program is None and not a.startswith("--"):
            program = a
        else:
            print("unknown option: %s" % a)
            return 2
        i += 1
    if program is None:
        print(__doc__)
        return 2

    sys.path.insert(0, SHIM)
    import _ti_screen
    _ti_screen.GUI = gui
    _ti_screen.QUIET = quiet
    import ti_system
    ti_system._values.update(variables)
    ti_system._lists.update(lists)
    ti_system._functions.update(funcs)
    ti_system._keys[:] = keys
    _patch_time()

    try:
        runpy.run_path(program, run_name="__main__")
    except KeyboardInterrupt:
        print("\n[shim] interrupted", file=sys.stderr)
    _ti_screen.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
