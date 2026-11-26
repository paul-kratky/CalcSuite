# Deliberately BAD for the TI-Nspire: tools/check_nspire.py must flag every part of this.
from __future__ import annotations
import numpy as np
import math
from os import path


def area(r: float) -> float:
    return math.pi * r ** 2


async def later():
    await something()


total: int = 0
name = "Ana"
print(f"Hello {name}, area = {area(2)}")
if (n := len(name)) > 2:
    print(name.ljust(10), "is long")
match n:
    case 3:
        print("three")
    case _:
        print("other")
print("x² ≤ π")
with open("data.txt") as f:
    data = f.read()
print(math.hypot(3, 4))
big = [0] * 1000000


def fact(k):
    return 1 if k < 2 else k * fact(k - 1)
