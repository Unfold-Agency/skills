#!/usr/bin/env python3
"""No-network unit test for status.py's pure classifier -- the morning-after
partition into merged / parked / dangling / resumable.

  python scripts/tests/test_status.py
Exit 0 = the buckets are as expected.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from status import classify  # noqa: E402

failures = []


def check(name, cond):
    print(f"{'ok  ' if cond else 'FAIL'} {name}")
    if not cond:
        failures.append(name)


def issue(number, state="OPEN", reason=None, labels=("make-issues", "afk"),
          assignees=(), closing_prs=()):
    return {"number": number, "title": f"Issue {number}", "state": state,
            "stateReason": reason,
            "labels": [{"name": n} for n in labels],
            "assignees": [{"login": a} for a in assignees],
            "closedByPullRequestsReferences": [{"number": p} for p in closing_prs],
            "url": f"https://example/{number}"}


ME = "alice"
issues = [
    issue(1, state="CLOSED", reason="COMPLETED", closing_prs=(101,)),       # merged
    issue(2, state="CLOSED", reason="NOT_PLANNED"),                          # won't-do
    issue(3, labels=("make-issues", "afk", "spec-drift")),                   # parked
    issue(4, labels=("make-issues", "hitl", "escalated")),                   # parked
    issue(5, assignees=("alice",), labels=("make-issues", "afk", "status:doing")),  # resumable (mine)
    issue(6, assignees=("bob",), labels=("make-issues", "afk", "status:doing")),    # dangling (theirs)
    issue(7, closing_prs=(107,)),                                            # dangling (PR, no assignee)
    issue(8),                                                                 # ready (not started)
]
b = classify(issues, ME)

check("merged = {1} with its closing PR",
      [r["number"] for r in b["merged"]] == [1] and b["merged"][0]["closing_prs"] == [101])
check("won't-do = {2}", [r["number"] for r in b["wont_do"]] == [2])
check("parked = {3,4} (flagged), with flags",
      sorted(r["number"] for r in b["parked"]) == [3, 4]
      and any(r["number"] == 3 and r["flags"] == ["spec-drift"] for r in b["parked"]))
check("resumable = {5} (started by me)",
      [r["number"] for r in b["resumable"]] == [5])
check("dangling = {6,7} (started, not mine)",
      sorted(r["number"] for r in b["dangling"]) == [6, 7])
check("a flagged-but-started issue is parked, not double-counted",
      all(r["number"] != 4 for r in b["dangling"] + b["resumable"]))
check("not-started #8 is in none of the started buckets",
      all(r["number"] != 8 for r in b["parked"] + b["dangling"] + b["resumable"] + b["merged"]))

# 'me' unknown: a started-by-someone issue must never be classed resumable.
b2 = classify(issues, "")
check("when me is unknown, nothing is resumable",
      b2["resumable"] == [] and 5 in [r["number"] for r in b2["dangling"]])

print()
if failures:
    print(f"FAILURES: {failures}")
    sys.exit(1)
print("status classifier behaves as expected")
sys.exit(0)
