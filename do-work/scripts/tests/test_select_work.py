#!/usr/bin/env python3
"""No-network unit test for select_work's pure parsing and selection logic. Feeds
fixture issue dicts (the shape `gh issue list --json ...` returns) through the
decision matrix and asserts the right issue is picked and the rest are excluded
with the right reason.

  python scripts/tests/test_select_work.py
Exit 0 = the selector behaves as expected.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from select_work import (  # noqa: E402
    parse_meta, parse_dependencies, autonomy_of, issue_state, select)

failures = []


def check(name, cond):
    print(f"{'ok  ' if cond else 'FAIL'} {name}")
    if not cond:
        failures.append(name)


def body(autonomy="afk", deps="None", trace="WF-001"):
    return (
        f"## What to build\nstuff per {trace}\n\n"
        f"## Dependencies\n\n{deps}\n\n"
        "<!-- make-issues:meta -->\n"
        "```yaml\n"
        f"trace_tdd: [{trace}]\n"
        "trace_prd: [FR-002]\n"
        'source_versions: { prd: "1.0", tdd: "1.1" }\n'
        f"autonomy: {autonomy}\n"
        'fingerprint: "abc123"\n'
        "```\n"
        "<!-- /make-issues:meta -->\n"
    )


def issue(number, state="OPEN", labels=("make-issues", "afk"), assignees=(),
          reason=None, body_text=None, autonomy="afk", deps="None",
          closing_prs=()):
    return {
        "number": number, "title": f"Issue {number}", "state": state,
        "stateReason": reason,
        "labels": [{"name": n} for n in labels],
        "assignees": [{"login": a} for a in assignees],
        "closedByPullRequestsReferences": list(closing_prs),
        "body": body_text if body_text is not None else body(autonomy, deps),
        "url": f"https://example/{number}",
    }


# ── parsers ─────────────────────────────────────────────────────────────
meta = parse_meta(body(autonomy="hitl", trace="INTG-002"))
check("parse_meta reads autonomy", meta.get("autonomy") == "hitl")
check("parse_meta reads trace_tdd", meta.get("trace_tdd") == ["INTG-002"])
check("parse_meta on junk -> {}", parse_meta("no markers here") == {})

check("deps None -> []", parse_dependencies(body(deps="None")) == [])
check("deps single -> [5]", parse_dependencies(body(deps="- #5 the entity")) == [5])
check("deps many sorted/deduped",
      parse_dependencies(body(deps="blocked by #6 and #1 and #6")) == [1, 6])

check("autonomy from meta wins", autonomy_of(issue(1, labels=("make-issues",)),
      parse_meta(body("hitl"))) == "hitl")
check("autonomy falls back to label",
      autonomy_of(issue(1, labels=("make-issues", "hitl")), {}) == "hitl")

# ── issue_state ─────────────────────────────────────────────────────────
check("state completed", issue_state(issue(1, "CLOSED", reason="COMPLETED")) == "completed")
check("state won't-do", issue_state(issue(1, "CLOSED", reason="NOT_PLANNED")) == "won't-do")
check("state started via assignee",
      issue_state(issue(1, assignees=("alice",))) == "started")
check("state started via status:doing",
      issue_state(issue(1, labels=("make-issues", "afk", "status:doing"))) == "started")
check("state started via closing PR",
      issue_state(issue(1, closing_prs=[{"number": 99}])) == "started")
check("state not-started", issue_state(issue(1)) == "not-started")

# ── the selection matrix ────────────────────────────────────────────────
ME = "alice"
issues = [
    issue(1),                                                  # afk, not-started, free -> actionable
    issue(2, assignees=("alice",), labels=("make-issues", "afk", "status:doing")),  # mine -> resumable
    issue(3, assignees=("bob",)),                              # started by other -> excluded
    issue(4, deps="- #5 prerequisite"),                        # blocked by open #5 -> excluded
    issue(5),                                                  # afk, free -> actionable (and #4's blocker)
    issue(6, state="CLOSED", reason="COMPLETED"),              # done -> satisfies #7
    issue(7, deps="blocked by #6"),                            # blocker done -> actionable
    issue(8, labels=("make-issues", "hitl"), autonomy="hitl"), # hitl -> excluded under afk
    issue(9, labels=("make-issues", "afk", "spec-drift")),     # flagged -> excluded
    issue(10, deps="needs #999"),                              # blocker not in set -> excluded
]

res = select(issues, ME, autonomy="afk")
act = [a["number"] for a in res["actionable"]]
exc = {e["number"]: e["reason"] for e in res["excluded"]}

check("actionable set is exactly {1,2,5,7}", act == [2, 1, 5, 7])
check("resumable mine sorts first (#2)", res["actionable"][0]["number"] == 2
      and res["actionable"][0]["resumable"] is True)
check("#3 excluded: in flight by other", "in flight by bob" in exc.get(3, ""))
check("#4 excluded: blocked by #5", exc.get(4) == "blocked by #5")
check("#8 excluded: hitl under afk filter", "autonomy hitl" in exc.get(8, ""))
check("#9 excluded: flagged spec-drift", exc.get(9) == "flagged spec-drift")
check("#10 excluded: unknown blocker", exc.get(10) == "blocked by #999?")

res_any = select(issues, ME, autonomy="any")
check("#8 becomes actionable under autonomy=any",
      8 in [a["number"] for a in res_any["actionable"]])

# When the current login can't be resolved (me == ""), an issue in flight under
# someone else's name must STILL be excluded -- never claimed by accident.
res_nome = select(issues, "", autonomy="afk")
exc_nome = {e["number"]: e["reason"] for e in res_nome["excluded"]}
check("#3 excluded even when 'me' is unknown", "in flight by bob" in exc_nome.get(3, ""))
check("nothing is resumable when 'me' is unknown",
      all(not a["resumable"] for a in res_nome["actionable"]))

print()
if failures:
    print(f"FAILURES: {failures}")
    sys.exit(1)
print("select_work parsers and decision matrix behave as expected")
sys.exit(0)
