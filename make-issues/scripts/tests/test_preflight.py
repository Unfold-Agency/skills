#!/usr/bin/env python3
"""No-network unit test for the version-lock gate -- the one piece of preflight
that is pure YAML and must be right regardless of gh/auth/repo state.

  python scripts/tests/test_preflight.py
Exit 0 = the gate accepts a matched pair and rejects every mismatch.
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from gh_preflight import check_version_lock  # noqa: E402

failures = []


def check(name, cond):
    print(f"{'ok  ' if cond else 'FAIL'} {name}")
    if not cond:
        failures.append(name)


def yaml_file(prd_version):
    fd, path = tempfile.mkstemp(suffix=".yaml")
    with os.fdopen(fd, "w") as f:
        if prd_version is None:
            f.write("meta:\n  project_id: x\n")        # no prd_version key
        else:
            f.write(f'meta:\n  prd_version: "{prd_version}"\n')
    return path


prd10, tdd10, tdd09 = yaml_file("1.0"), yaml_file("1.0"), yaml_file("0.9")
tdd_missing = yaml_file(None)
tmps = [prd10, tdd10, tdd09, tdd_missing]

r = check_version_lock(prd10, tdd10)
check("matched 1.0 == 1.0 -> ok", r["ok"] is True and not r.get("fatal"))

r = check_version_lock(prd10, tdd09)
check("PRD 1.0 vs TDD lock 0.9 -> not ok", r["ok"] is False)
check("mismatch message points to /make-tdd", "/make-tdd" in r["detail"])

r = check_version_lock(prd10, tdd_missing)
check("missing TDD prd_version -> not ok", r["ok"] is False)

r = check_version_lock(prd10, "/nope/missing.yaml")
check("unreadable data file -> fatal (drives exit 2)", r.get("fatal") is True)

for p in tmps:
    try:
        os.unlink(p)
    except OSError:
        pass

print()
if failures:
    print(f"FAILURES: {failures}")
    sys.exit(1)
print("version-lock gate behaves as expected")
sys.exit(0)
