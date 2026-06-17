#!/usr/bin/env python3
"""No-network unit test for work_preflight's pure pieces -- the version-lock gate
(shared with make-issues), the backlog gate, and the non-gating advisories.

  python scripts/tests/test_work_preflight.py
Exit 0 = all behave as expected.
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from work_preflight import (  # noqa: E402
    check_version_lock, check_backlog, scan_advisories)

failures = []


def check(name, cond):
    print(f"{'ok  ' if cond else 'FAIL'} {name}")
    if not cond:
        failures.append(name)


def yaml_file(text):
    fd, path = tempfile.mkstemp(suffix=".yaml")
    with os.fdopen(fd, "w") as f:
        f.write(text)
    return path


def issue(number, state, labels, reason=None):
    return {"number": number, "state": state, "stateReason": reason,
            "labels": [{"name": n} for n in labels]}


tmps = []
prd10 = yaml_file('meta:\n  prd_version: "1.0"\n'); tmps.append(prd10)
tdd10 = yaml_file('meta:\n  prd_version: "1.0"\n  tdd_version: "1.1"\n'); tmps.append(tdd10)
tdd09 = yaml_file('meta:\n  prd_version: "0.9"\n'); tmps.append(tdd09)

# ── version-lock gate (same contract make-issues enforces) ──────────────
r = check_version_lock(prd10, tdd10)
check("lock matched 1.0 == 1.0 -> ok", r["ok"] is True and not r.get("fatal"))

r = check_version_lock(prd10, tdd09)
check("lock PRD 1.0 vs TDD 0.9 -> not ok", r["ok"] is False)
check("lock mismatch points to /make-tdd", "/make-tdd" in r["detail"])

r = check_version_lock(prd10, "/nope/missing.yaml")
check("unreadable data file -> fatal (drives exit 2)", r.get("fatal") is True)

# ── backlog gate ────────────────────────────────────────────────────────
r = check_backlog([], True)
check("no managed issues -> backlog FAIL", r["ok"] is False and "make-issues" in r["detail"])

r = check_backlog([issue(1, "CLOSED", ["make-issues"], "COMPLETED")], True)
check("managed but none open -> ok (drained)", r["ok"] is True and r["open"] == 0)

r = check_backlog([issue(1, "OPEN", ["make-issues", "afk"])], True)
check("open managed issue -> ok", r["ok"] is True and r["open"] == 1)

r = check_backlog([], False)
check("could not list -> backlog FAIL", r["ok"] is False)

# ── advisories (non-gating) ─────────────────────────────────────────────
issues = [
    issue(1, "OPEN", ["make-issues", "afk", "spec-drift", "src:tdd-1.0"]),
    issue(2, "OPEN", ["make-issues", "afk", "src:tdd-1.0"]),
    issue(3, "CLOSED", ["make-issues", "src:tdd-0.9"], "COMPLETED"),  # closed: ignored
]
adv = scan_advisories(issues, tdd10, have_labels={"status:doing"})
check("drift scan flags only the open spec-drift issue",
      [f["number"] for f in adv["flagged"]] == [1] and adv["flagged"][0]["flags"] == ["spec-drift"])
check("src:tdd seen counts only open issues", adv["src_tdd_seen"] == ["1.0"])
check("sync owed when live TDD 1.1 not in stamps {1.0}", adv["sync_owed"] is True)
check("missing do-work labels computed", adv["missing_labels"] == ["escalated"])

adv2 = scan_advisories(
    [issue(2, "OPEN", ["make-issues", "afk", "src:tdd-1.1"])], tdd10,
    have_labels={"status:doing", "escalated"})
check("no sync owed when live TDD 1.1 is represented", adv2["sync_owed"] is False)
check("no missing labels when both present", adv2["missing_labels"] == [])

for p in tmps:
    try:
        os.unlink(p)
    except OSError:
        pass

print()
if failures:
    print(f"FAILURES: {failures}")
    sys.exit(1)
print("work_preflight gates and advisories behave as expected")
sys.exit(0)
