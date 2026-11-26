"""PC stand-in for the TI-Nspire ti_system module (logic testing only).

TI variables live in dictionaries here. Preload them with run_on_pc.py:
    --var a=3  --list L1=1,2,3  --func f=x**2+1  --keys up,enter
Keys given with --keys are returned by get_key() in order; after that get_key() returns
"esc" so 'while get_key() != "esc":' loops end on the PC.
"""

import sys
import time

from _ti_screen import log

_values = {}
_lists = {}
_functions = {}     # name -> python callable of one argument
_keys = []
_t0 = time.monotonic()


def recall_value(name):
    log("ti_system", "recall_value", (name,))
    if name not in _values:
        raise NameError("ti_system shim: TI variable '%s' is not defined "
                        "(pass --var %s=VALUE to run_on_pc.py)" % (name, name))
    return _values[name]


def store_value(name, value):
    log("ti_system", "store_value", (name, value))
    _values[name] = value


def recall_list(name):
    log("ti_system", "recall_list", (name,))
    if name not in _lists:
        raise NameError("ti_system shim: TI list '%s' is not defined "
                        "(pass --list %s=1,2,3 to run_on_pc.py)" % (name, name))
    return list(_lists[name])


def store_list(name, values):
    log("ti_system", "store_list", (name, values))
    _lists[name] = list(values)


def eval_function(name, value):
    log("ti_system", "eval_function", (name, value))
    if name not in _functions:
        raise NameError("ti_system shim: TI function '%s' is not defined "
                        "(pass --func %s=x**2 to run_on_pc.py)" % (name, name))
    return _functions[name](value)


def get_platform():
    return "dt"


def get_key(wait=0):
    key = _keys.pop(0) if _keys else "esc"
    log("ti_system", "get_key", (wait,) if wait else ())
    return key


def get_mouse():
    return (-1, -1)


def clear_history():
    print("\n" * 2 + "-" * 20 + " (clear_history) " + "-" * 20, file=sys.stderr)


def get_time_ms():
    return int((time.monotonic() - _t0) * 1000)
