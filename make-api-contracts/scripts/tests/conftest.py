import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.normpath(os.path.join(HERE, os.pardir))
SKILLS_ROOT = os.path.normpath(os.path.join(SCRIPTS, os.pardir, os.pardir))
MAKE_SPEC = os.path.join(SKILLS_ROOT, "make-spec", "scripts")

for p in (SCRIPTS, MAKE_SPEC):
    if p not in sys.path:
        sys.path.insert(0, p)
