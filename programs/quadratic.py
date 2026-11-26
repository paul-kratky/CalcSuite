# Quadratic solver: a*x^2 + b*x + c = 0
# Works for real and complex roots (uses cmath).
# Run: Ctrl+R in the Python Editor, then type a, b, c.
from cmath import sqrt


def ask(prompt):
    while True:
        text = input(prompt)
        try:
            return float(text)
        except ValueError:
            print("Please type a number.")


def show(z):
    # Print a complex number neatly; drop a zero imaginary part.
    re = round(z.real, 6) + 0.0
    im = round(z.imag, 6) + 0.0
    if im == 0:
        return str(re)
    if re == 0:
        return str(im) + "i"
    sign = "+" if im > 0 else "-"
    return "{} {} {}i".format(re, sign, abs(im))


print("Solve a*x^2 + b*x + c = 0")
a = ask("a = ")
b = ask("b = ")
c = ask("c = ")

if a == 0:
    if b == 0:
        if c == 0:
            print("Every x is a solution.")
        else:
            print("No solution.")
    else:
        print("Linear: x =", show(complex(-c / b, 0)))
else:
    d = b * b - 4 * a * c
    r = sqrt(d)
    x1 = (-b + r) / (2 * a)
    x2 = (-b - r) / (2 * a)
    print("Discriminant =", round(d, 6))
    if d == 0:
        print("One double root: x =", show(x1))
    else:
        if d > 0:
            print("Two real roots:")
        else:
            print("Two complex roots:")
        print("x1 =", show(x1))
        print("x2 =", show(x2))
