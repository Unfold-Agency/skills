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
    issue(4, assignees=("bob",),
          labels=("make-issues", "hitl", "escalated", "status:doing")),       # flagged AND started -> parked (flags win)
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
check("a flagged-AND-started issue is parked (flags win over started)",
      any(r["number"] == 4 for r in b["parked"])
      and all(r["number"] != 4 for r in b["dangling"] + b["resumable"]))
check("not-started #8 is in none of the started buckets",
      all(r["number"] != 8 for r in b["parked"] + b["dangling"] + b["resumable"] + b["merged"]))

# 'me' unknown: a started-by-someone issue must never be classed resumable.
b2 = classify(issues, "")
check("when me is unknown, nothing is resumable",
      b2["resumable"] == [] and 5 in [r["number"] for r in b2["dangling"]])

# ── main()'s ready/blocked partition (classify + select combined) ────────────
# Reproduce main()'s logic so the no-double-list invariant and the blocked bucket
# are covered without a network round-trip.
from select_work import select  # noqa: E402


def body(deps="None", autonomy="afk"):
    return (f"## Dependencies\n\n{deps}\n\n"
            "<!-- make-issues:meta -->\n```yaml\n"
            f"trace_req: [FR-X-001]\nfeature: x\nautonomy: {autonomy}\n"
            'fingerprint: "abc"\n```\n<!-- /make-issues:meta -->\n')


def issue_b(number, body_text, **kw):
    i = issue(number, **kw)
    i["body"] = body_text
    return i


part = [
    issue_b(10, body(), assignees=("alice",),
            labels=("make-issues", "afk", "status:doing")),   # resumable (mine)
    issue_b(11, body()),                                       # ready (fresh)
    issue_b(12, body(deps="- #11 prerequisite")),             # blocked by open #11
]
pb = classify(part, ME)
psel = select(part, ME, autonomy="afk")
inflight = {r["number"] for r in pb["resumable"] + pb["dangling"]}
p_ready = [r for r in psel["actionable"] if r["number"] not in inflight]
p_blocked = [e for e in psel["excluded"]
             if str(e.get("reason", "")).startswith("blocked by")]
check("resumable #10 is NOT also listed in ready (no double-list)",
      10 in [r["number"] for r in pb["resumable"]]
      and 10 not in [r["number"] for r in p_ready])
check("ready = {11} only (fresh, not started, not blocked)",
      [r["number"] for r in p_ready] == [11])
check("blocked #12 is surfaced (waiting on its dependency)",
      [e["number"] for e in p_blocked] == [12])

print()
if failures:
    print(f"FAILURES: {failures}")
    sys.exit(1)
print("status classifier behaves as expected")
sys.exit(0)
