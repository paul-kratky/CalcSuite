"""Build docs/TIBASIC_84.md and docs/TIBASIC_89.md from the templates and the example files,
so the guide's blocks and programs/ti84, programs/ti89 stay the same text."""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(os.path.dirname(HERE))  # The repo (tools/docs_build/ is two levels down)

EX84 = [
    ("QUAD", "Roots of a quadratic, real or complex, without changing the complex mode. "
             "Run it, then type A, B and C."),
    ("RESNET", "Series and parallel resistance of a list such as `{100,220,470}`, and a voltage "
               "divider. A menu; QUIT leaves."),
    ("UNITS", "Engineering unit conversions from a menu: mm, in, km, mi, N, lbf, Pa, psi, kW, "
              "hp, deg C, deg F."),
    ("NUMINT", "Trapezoid and Simpson rules for a function you type in X (with the calculator's "
               "keys, e.g. `X^2*sin(X)`), compared with `fnInt(`. Stores the function in Y1."),
    ("BASE", "Decimal to hex, binary or octal, and hex to decimal. Type hex digits with ALPHA."),
    ("RCTAU", "Time constant of an RC or RL circuit, 5 tau, and v(t) for a charging and a "
              "decaying step."),
    ("VECTOR", "Adds 2D forces given as a list of magnitudes and a list of angles in degrees: "
               "components, resultant and its angle. Switches to Degree mode."),
    ("LINSOLVE", "Solves N linear equations A*X=B (N up to 6), asking for each element; "
                 "checks for a singular matrix."),
]
EX89 = [
    ("quadc", "Roots of a*x^2+b*x+c=0 with `cZeros(`, exact and as decimals. Run `quadc()`."),
    ("resnet", "Series, parallel and voltage divider from a pop-up menu, with dialogs and error "
               "checks. Run `resnet()`."),
    ("unitconv", "Unit conversions with the 89's own units (`v*_mm/_in`). Run `unitconv()`."),
    ("numint", "Trapezoid and Simpson rules against `nInt(` and the exact `∫(`. Run `numint()`; "
               "x must have no value."),
    ("tobase", "A function: `tobase(255,16)` gives \"FF\". Needed by `baseconv`, so send it too."),
    ("baseconv", "Decimal, hex and binary, and bitwise and/or/xor. Uses `tobase`. Run "
                 "`baseconv()`."),
    ("rctau", "Time constant of an RC or RL circuit and v(t). Run `rctau()`."),
    ("linsolve", "Solves A*x=b with `simult(`, exact when you type exact numbers. Run "
                 "`linsolve()`."),
]


def section(examples, folder, lang, ext=".txt"):
    out = []
    for name, desc in examples:
        with open(os.path.join(KIT, "programs", folder, name + ext), encoding="utf-8") as f:
            body = f.read().rstrip("\n")
        out.append("### %s\n\n%s\n\n```%s name=%s\n%s\n```\n" % (name, desc, lang, name, body))
    return "\n".join(out).rstrip("\n")


def build(tpl, examples, folder, lang, doc):
    with open(os.path.join(HERE, tpl), encoding="utf-8") as f:
        text = f.read()
    text = text.replace("@@EXAMPLES@@", section(examples, folder, lang))
    with open(os.path.join(KIT, "docs", doc), "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print("wrote", doc, len(text), "chars")


if __name__ == "__main__":
    build("tpl84.md", EX84, "ti84", "tibasic84", "TIBASIC_84.md")
    if os.path.exists(os.path.join(HERE, "tpl89.md")):
        build("tpl89.md", EX89, "ti89", "tibasic89", "TIBASIC_89.md")
