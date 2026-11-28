"""CalcSuite's version: the one place it's written. The window's title, Calculator info, the
helpers' version info (tools/build_tools.py) and the release (tools/release_files.py checks the
tag matches) all read it. A release bumps it here and in tools/driver_helper/calcsuite_driver.rc
(the self-test checks the two agree)."""

VERSION = (1, 0, 3)
TEXT = "%d.%d.%d" % VERSION
