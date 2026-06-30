#!/usr/bin/env python3
"""do-work --status: the morning-after surface. Read-only: it CHECKS and REPORTS;
it never writes anything. After an overnight or --dangerously run, it answers the
three questions a human wakes up to: what merged, what is still dangling, and what
is safe to resume.

It reads the make-issues-managed issues and partitions the OPEN ones, reusing
select_work's pure parsers so the classification matches what the build loop sees.

  python scripts/status.py --repo owner/name
  python scripts/status.py --repo owner/name --me <login> --json

Exit codes: 0 = reported (any state), 2 = could not query GitHub.
"""
import argparse
import json
import sys

from select_work import (  # sibling module; pure parsers shared with selection
    _list_issues, _me, issue_state, label_names, select,
    NOT_BUILDABLE_FLAGS)


def _closing_prs(issue):
    return [p.get("number") for p in issue.get("closedByPullRequestsReferences") or []]


def classify(issues, me):
    """Partition issues into the morning-after buckets. CLOSED issues are merged
    or won't-do; an OPEN issue is parked (flagged), resumable (started by me), or
    dangling (started by someone else). Fresh not-started work -- ready vs
    blocked -- is computed in main() from select_work, kept disjoint from these
    buckets so nothing is double-listed."""
    merged, wont_do, parked, in_flight, dangling = [], [], [], [], []
    for i in issues:
        num = i.get("number")
        st = issue_state(i)
        names = label_names(i)
        row = {"number": num, "title": i.get("title", ""), "url": i.get("url", "")}
        if st == "completed":
            row["closing_prs"] = _closing_prs(i)
            merged.append(row)
            continue
        if st == "won't-do":
            wont_do.append(row)
            continue
        # OPEN from here
        flags = sorted(names & set(NOT_BUILDABLE_FLAGS))
        if flags:
            row["flags"] = flags
            parked.append(row)               # needs a human / upstream reconcile
            continue
        assignees = {a.get("login", "") for a in i.get("assignees") or []}
        if st == "started":
            row["mine"] = bool(me and me in assignees)
            row["assignees"] = sorted(a for a in assignees if a)
            row["closing_prs"] = _closing_prs(i)
            in_flight.append(row)            # a PR/branch exists but it has not merged
    # "Safe to resume" = started-by-me, not parked; "dangling" = started by someone
    # else or nobody (a branch/PR left open).
    resumable = [r for r in in_flight if r.get("mine")]
    dangling = [r for r in in_flight if not r.get("mine")]
    return {"merged": merged, "wont_do": wont_do, "parked": parked,
            "resumable": resumable, "dangling": dangling}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", required=True, help="owner/name")
    ap.add_argument("--me", help="my gh login (default: gh api user)")
    ap.add_argument("--limit", type=int, default=1000)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    issues = _list_issues(args.repo, args.limit)
    if issues is None:
        sys.exit(2)
    me = _me(args.me)
    buckets = classify(issues, me)
    # Fresh not-started work, from the same selector the build loop uses. Select
    # with autonomy="any" so HITL (and unset-autonomy) items are not dropped, then
    # split the fresh queue: afk -> ready to build autonomously; everything else ->
    # needs-you (a human must drive it). Exclude anything already in flight (it
    # shows under resumable/dangling) so the surface is a clean partition, not a
    # double-count.
    sel = select(issues, me, autonomy="any")
    inflight = {r["number"] for r in buckets["resumable"] + buckets["dangling"]}
    fresh = [r for r in sel["actionable"] if r["number"] not in inflight]
    ready = [r for r in fresh if r.get("autonomy") == "afk"]
    needs_you = [r for r in fresh if r.get("autonomy") != "afk"]
    blocked = [e for e in sel["excluded"]
               if str(e.get("reason", "")).startswith("blocked by")]

    if args.json:
        print(json.dumps({**buckets, "ready": ready, "needs_you": needs_you,
                          "blocked": blocked}, indent=2))
        sys.exit(0)

    def show(title, rows, fmt):
        print(f"{title} ({len(rows)}):")
        for r in rows:
            print("  " + fmt(r))
        if not rows:
            print("  (none)")
        print()

    print(f"do-work status -- {args.repo}\n")
    show("Merged (shipped)", buckets["merged"],
         lambda r: f"#{r['number']} {r['title']}"
                   + (f"  closed by PR {r['closing_prs']}" if r.get("closing_prs") else ""))
    show("Parked for a human (flagged -- resolve upstream)", buckets["parked"],
         lambda r: f"#{r['number']} [{'/'.join(r['flags'])}] {r['title']}")
    show("Dangling (a branch/PR is open, not yours, unmerged)", buckets["dangling"],
         lambda r: f"#{r['number']} {r['title']}  (by {', '.join(r['assignees']) or '?'})")
    show("Safe to resume (started by you, unmerged)", buckets["resumable"],
         lambda r: f"#{r['number']} {r['title']}")
    show("Ready to build next (fresh, afk, not started)", ready,
         lambda r: f"#{r['number']} {r['title']}")
    show("Needs you (fresh, not started, not autonomous)", needs_you,
         lambda r: f"#{r['number']} [{r.get('autonomy') or 'unset'}] {r['title']}")
    show("Blocked (waiting on a dependency)", blocked,
         lambda r: f"#{r['number']}: {r['reason']}")
    show("Won't-do (closed, not planned)", buckets["wont_do"],
         lambda r: f"#{r['number']} {r['title']}")
    print(f"summary: {len(buckets['merged'])} merged, "
          f"{len(buckets['parked'])} parked, {len(buckets['dangling'])} dangling, "
          f"{len(buckets['resumable'])} resumable, {len(ready)} ready, "
          f"{len(needs_you)} needs-you, {len(blocked)} blocked, "
          f"{len(buckets['wont_do'])} won't-do")
    sys.exit(0)


if __name__ == "__main__":
    main()
