# numint: trapezoid, Simpson and a reference value for the integral of f(x) from a to b
# Type f with x, ^ for powers, e, pi, sin cos tan ln log sqrt abs exp asin acos atan.
from math import *


def make_f(text):
    t = text.strip().replace("^", "**").replace("ln(", "log(")
    code = "lambda x: " + t
    return eval(code)


def trap(f, a, b, n):
    h = (b - a) / n
    s = (f(a) + f(b)) / 2
    for k in range(1, n):
        s += f(a + k * h)
    return h * s


def simp(f, a, b, n):
    h = (b - a) / n
    s = f(a) + f(b)
    for k in range(1, n):
        if k % 2 == 1:
            s += 4 * f(a + k * h)
        else:
            s += 2 * f(a + k * h)
    return h / 3 * s


def gauss5(f, a, b):
    # 5-point Gauss-Legendre on [a, b]
    xs = (0.0, 0.5384693101056831, -0.5384693101056831, 0.9061798459386640, -0.9061798459386640)
    ws = (0.5688888888888889, 0.4786286704993665, 0.4786286704993665, 0.2369268850561891, 0.2369268850561891)
    m = (a + b) / 2
    r = (b - a) / 2
    s = 0.0
    for i in range(5):
        s += ws[i] * f(m + r * xs[i])
    return r * s


def reference(f, a, b):
    # 5-point Gauss on 128 pieces: about 10+ digits for smooth f
    total = 0.0
    pieces = 128
    h = (b - a) / pieces
    for i in range(pieces):
        total += gauss5(f, a + i * h, a + (i + 1) * h)
    return total


def number(prompt):
    while True:
        s = input(prompt).strip().replace("^", "**")
        try:
            return float(eval(s))
        except Exception:
            print("Not a number, try again (pi and e work)")


def main():
    print("Trapezoid / Simpson / reference")
    while True:
        text = input("f(x) = ")
        try:
            f = make_f(text)
            f(0.5)
            break
        except Exception:
            print("Can't read that. Use x, ^, sin(), e, pi")
    a = number("a = ")
    b = number("b = ")
    n = int(number("n (even) = "))
    while n < 2 or n % 2 != 0:
        print("Simpson needs an even n >= 2")
        n = int(number("n (even) = "))
    print("Trap:  ", trap(f, a, b, n))
    print("Simp:  ", simp(f, a, b, n))
    print("Exact: ", reference(f, a, b))


main()
