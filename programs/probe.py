# Probe: run this ON THE HANDHELD once to see what your OS's Python supports.
# Each test is wrapped so one failure does not stop the rest.
# Write the results down and update CLAUDE.md if they differ from the defaults.
from ti_system import get_platform


def test(label, code):
    try:
        result = eval(code)
        print(label, "-> yes:", result)
    except Exception as e:
        print(label, "-> NO:", type(e).__name__)


print("platform:", get_platform())

try:
    import sys
    print("version:", sys.version)
    print("impl:", sys.implementation)
except Exception as e:
    print("sys -> NO:", type(e).__name__)

try:
    import gc
    gc.collect()
    print("free heap bytes:", gc.mem_free())
except Exception as e:
    print("gc -> NO:", type(e).__name__)

test("f-strings", "f'{1+1}'")
test("walrus", "(q := 3)")
test("format", "'{:.3f}'.format(3.14159)")
test("big int", "2**100")
test("float digits", "repr(1/3)")
test("ljust", "'ab'.ljust(4) + '|'")


def depth(n):
    try:
        return depth(n + 1)
    except RuntimeError:
        return n


print("max recursion ~", depth(0))

try:
    from ti_draw import get_screen_dim
    print("screen:", get_screen_dim())
except Exception as e:
    print("ti_draw -> NO:", type(e).__name__)
