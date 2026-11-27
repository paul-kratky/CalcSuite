"""Save the handheld's screen as a PNG.

    python -I tools/screenshot.py                 -> captures/nspire-<date>-<time>.png
    python -I tools/screenshot.py shot.png        -> that file
    python -I tools/screenshot.py --scale 3       -> enlarged 3x (sharp pixels)

The handheld takes one USB connection per plug-in: if this says it didn't answer, unplug it,
wait 3 seconds and plug it back in. For several pictures in a row, use tools/mirror.py.
"""

import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import nspire_link  # noqa: E402


def main(argv):
    scale = 1
    if "--scale" in argv:
        i = argv.index("--scale")
        scale = max(1, min(8, int(argv[i + 1])))
        argv = argv[:i] + argv[i + 2:]
    if argv and argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if argv:
        out = argv[0]
    else:
        os.makedirs(os.path.join(os.path.dirname(HERE), "captures"), exist_ok=True)
        out = os.path.join(os.path.dirname(HERE), "captures",
                           time.strftime("nspire-%Y%m%d-%H%M%S.png"))
    ppm = os.path.join(tempfile.gettempdir(), "nspire_shot_%d.ppm" % os.getpid())
    try:
        with nspire_link.Session() as s:
            code, lines = s.cmd("shot " + ppm)
    except nspire_link.LinkError as e:
        print("\n".join(l for l in e.lines if l.startswith("ERR")))
        print(nspire_link.REPLUG)
        return e.code
    if code:
        print("\n".join(lines))
        return code
    w, h = nspire_link.ppm_to_png(ppm, out, scale)
    os.remove(ppm)
    print("Saved %s (%d x %d)" % (out, w, h))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
