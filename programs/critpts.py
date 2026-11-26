# Critical points of f(x,y) and the second derivative test.
# Type f using x and y, e.g.  6-8*x**2-6*y**2   or   x**3-3*x+y**2
# It searches a grid of starting points with Newton's method on the
# gradient, then classifies each point with D = fxx*fyy - fxy**2.
from math import *

H = 1e-4


def make_f(expr):
    code = "lambda x,y: " + expr
    return eval(code)


def grad(f, x, y):
    fx = (f(x + H, y) - f(x - H, y)) / (2 * H)
    fy = (f(x, y + H) - f(x, y - H)) / (2 * H)
    return fx, fy


def hess(f, x, y):
    h = 1e-3
    f0 = f(x, y)
    fxx = (f(x + h, y) - 2 * f0 + f(x - h, y)) / (h * h)
    fyy = (f(x, y + h) - 2 * f0 + f(x, y - h)) / (h * h)
    fxy = (f(x + h, y + h) - f(x + h, y - h) - f(x - h, y + h) + f(x - h, y - h)) / (4 * h * h)
    return fxx, fyy, fxy


def newton(f, x, y):
    for i in range(40):
        gx, gy = grad(f, x, y)
        if abs(gx) < 1e-9 and abs(gy) < 1e-9:
            return x, y, True
        a, b, c = hess(f, x, y)
        det = a * b - c * c
        if abs(det) < 1e-12:
            return x, y, False
        dx = (b * gx - c * gy) / det
        dy = (a * gy - c * gx) / det
        x = x - dx
        y = y - dy
        if abs(x) > 1e6 or abs(y) > 1e6:
            return x, y, False
    gx, gy = grad(f, x, y)
    return x, y, abs(gx) < 1e-6 and abs(gy) < 1e-6


def tidy(v):
    r = round(v)
    if abs(v - r) < 1e-6:
        return float(r)
    return round(v, 6)


def classify(f, x, y):
    a, b, c = hess(f, x, y)
    d = a * b - c * c
    if abs(d) < 1e-6:
        return "test fails (D=0)", d, a
    if d < 0:
        return "saddle point", d, a
    if a > 0:
        return "relative minimum", d, a
    return "relative maximum", d, a


def main():
    print("f(x,y) critical points")
    expr = input("f(x,y) = ")
    f = make_f(expr)
    found = []
    starts = [-6, -3, -1, 0, 1, 3, 6]
    for sx in starts:
        for sy in starts:
            try:
                x, y, ok = newton(f, sx + 0.1, sy - 0.1)
            except (ValueError, ZeroDivisionError, OverflowError):
                continue
            if not ok:
                continue
            x = tidy(x)
            y = tidy(y)
            new = True
            for p in found:
                if abs(p[0] - x) < 1e-4 and abs(p[1] - y) < 1e-4:
                    new = False
            if new:
                found.append((x, y))
    if not found:
        print("No critical point found (DNE?)")
        return
    found.sort(key=lambda p: (p[1], p[0]))  # Smaller y first, as the homework asks
    mins = []
    maxs = []
    for p in found:
        x = p[0]
        y = p[1]
        kind, d, a = classify(f, x, y)
        print("({},{}): {}".format(x, y, kind))
        print("  D={} fxx={}".format(tidy(d), tidy(a)))
        if kind == "relative minimum":
            mins.append(tidy(f(x, y)))
        if kind == "relative maximum":
            maxs.append(tidy(f(x, y)))
    print("rel min value: {}".format(mins if mins else "DNE"))
    print("rel max value: {}".format(maxs if maxs else "DNE"))


main()
