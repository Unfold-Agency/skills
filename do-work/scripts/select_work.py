#!/usr/bin/env python3
"""Select the next actionable make-issues work item(s) for do-work to build.

An issue is ACTIONABLE when all of these hold:
  - it is OPEN and managed by make-issues;
  - it carries no not-buildable flag (needs-rebase / spec-drift / orphaned /
    escalated -- a drifted or handed-back spec is not work until it is resolved);
  - every issue it is blocked by is CLOSED as COMPLETED (dependencies are read
    from the issue body's "## Dependencies" mirror -- GitHub does not expose the
    native blocked-by edges through `gh ... --json`, see SKILL.md, Honest limits);
  - its autonomy matches the filter (default: afk only -- hitl items stop for a
    human and are surfaced separately);
  - it is not already in flight under someone else's name.

An issue already started by ME (assigned to me) is actionable and RESUMABLE -- it
sorts first so an interrupted build is picked back up before a fresh one starts.

  python scripts/select_work.py --repo owner/name
  python scripts/select_work.py --repo owner/name --autonomy any --json
  python scripts/select_work.py --repo owner/name --me <login>

Exit codes: 0 = listed (queue may be empty), 2 = could not query GitHub.
The parsing/selection functions are pure and unit-tested without a network.
"""
import argparse
import json
import re
import subprocess
import sys

try:
    import yaml
except ImportError:
    print("PyYAML is required: pip install pyyaml --break-system-packages", file=sys.stderr)
    sys.exit(2)

NOT_BUILDABLE_FLAGS = {"needs-rebase", "spec-drift", "orphaned", "escalated"}
DOING_LABEL = "status:doing"
CAP_PREFIXES = ("ENT", "STM", "WF", "INTG", "TNF", "ADR")

_META_RE = re.compile(
    r"<!--\s*make-issues:meta\s*-->(.*?)<!--\s*/make-issues:meta\s*-->",
    re.DOTALL)
_DEPS_RE = re.compile(
    r"##\s*Dependencies\s*(.*?)(?=\n<!--|\n##\s|\Z)", re.DOTALL | re.IGNORECASE)
_ISSUE_NUM_RE = re.compile(r"#(\d+)")


def _run(cmd, timeout=30):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True,
                            encoding="utf-8", timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"
    except FileNotFoundError:
        return 127, "", f"{cmd[0]} not found"


def label_names(issue):
    return {lab.get("name", "") for lab in issue.get("labels") or []}


def parse_meta(body):
    """Parse the YAML inside the make-issues:meta markers. Returns {} if the block
    is missing or malformed (the caller falls back to labels)."""
    m = _META_RE.search(body or "")
    if not m:
        return {}
    inner = m.group(1)
    # Strip ```yaml / ``` fences the template wraps the block in.
    inner = re.sub(r"```[a-zA-Z]*", "", inner).replace("```", "")
    try:
        data = yaml.safe_load(inner)
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def parse_dependencies(body):
    """Issue numbers from the body's '## Dependencies' mirror. [] for 'None' or no
    section. This is a human-readable mirror make-issues writes; the authoritative
    native edges cannot be read back via gh --json (a documented limit)."""
    m = _DEPS_RE.search(body or "")
    if not m:
        return []
    text = m.group(1)
    return sorted({int(n) for n in _ISSUE_NUM_RE.findall(text)})


def autonomy_of(issue, meta):
    """afk | hitl | None. The meta block wins; labels are the fallback."""
    val = str((meta or {}).get("autonomy") or "").strip().lower()
    if val in ("afk", "hitl"):
        return val
    names = label_names(issue)
    if "afk" in names:
        return "afk"
    if "hitl" in names:
        return "hitl"
    return None


def issue_state(issue):
    """completed | won't-do | started | not-started. 'started' is inferred from
    assignee / closing-PR / status:doing -- GitHub has no native in-progress state
    (see SKILL.md, Honest limits). Mirrors make-issues reconciliation."""
    if issue.get("state") == "CLOSED":
        return "completed" if issue.get("stateReason") == "COMPLETED" else "won't-do"
    started = (issue.get("assignees")
               or issue.get("closedByPullRequestsReferences")
               or DOING_LABEL in label_names(issue))
    return "started" if started else "not-started"


def _is_done(issue):
    return issue.get("state") == "CLOSED" and issue.get("stateReason") == "COMPLETED"


def _assignee_logins(issue):
    return {a.get("login", "") for a in issue.get("assignees") or []}


def select(issues, me, autonomy="afk"):
    """Partition managed issues into an ordered actionable queue and an excluded
    list with reasons. `autonomy` is 'afk', 'hitl', or 'any'."""
    by_number = {i.get("number"): i for i in issues}
    actionable, excluded = [], []

    for issue in issues:
        num = issue.get("number")
        if issue.get("state") != "OPEN":
            continue  # closed issues are not work; they only resolve blockers

        names = label_names(issue)
        flags = sorted(names & NOT_BUILDABLE_FLAGS)
        if flags:
            excluded.append({"number": num, "reason": f"flagged {'/'.join(flags)}"})
            continue

        meta = parse_meta(issue.get("body", ""))
        item_autonomy = autonomy_of(issue, meta)
        if autonomy != "any" and item_autonomy != autonomy:
            excluded.append({"number": num,
                             "reason": f"autonomy {item_autonomy or 'unset'} "
                                       f"(filter: {autonomy})"})
            continue

        deps = parse_dependencies(issue.get("body", ""))
        unmet = []
        for d in deps:
            blocker = by_number.get(d)
            if blocker is None:
                unmet.append(f"#{d}?")       # not in the managed set; cannot confirm done
            elif not _is_done(blocker):
                unmet.append(f"#{d}")
        if unmet:
            excluded.append({"number": num, "reason": f"blocked by {', '.join(unmet)}"})
            continue

        state = issue_state(issue)
        assignees = _assignee_logins(issue)
        # Exclude work in flight under another name. There is deliberately no `me`
        # guard: if the current login could not be resolved (me == ""), then
        # `me not in assignees` is True for any assigned issue, so we conservatively
        # exclude it rather than risk claiming someone else's in-progress work.
        if state == "started" and assignees and me not in assignees:
            excluded.append({"number": num,
                             "reason": f"in flight by {', '.join(sorted(assignees))}"})
            continue

        resumable = bool(me and me in assignees)
        actionable.append({
            "number": num,
            "title": issue.get("title", ""),
            "autonomy": item_autonomy,
            "state": state,
            "resumable": resumable,
            "trace_tdd": meta.get("trace_tdd") or [],
            "url": issue.get("url", ""),
        })

    # Resumable (already mine) first, then by issue number for a stable order.
    actionable.sort(key=lambda x: (not x["resumable"], x["number"]))
    excluded.sort(key=lambda x: x["number"])
    return {"actionable": actionable, "excluded": excluded,
            "counts": {"actionable": len(actionable), "excluded": len(excluded)}}


def _list_issues(repo, limit):
    rc, out, err = _run(["gh", "issue", "list", "--repo", repo, "--label",
                         "make-issues", "--state", "all", "--limit", str(limit),
                         "--json", "number,title,state,stateReason,labels,"
                         "assignees,body,closedByPullRequestsReferences,url"])
    if rc != 0:
        print(f"ERROR: could not list issues for {repo}: {err.strip()}", file=sys.stderr)
        return None
    try:
        return json.loads(out or "[]")
    except json.JSONDecodeError as e:
        print(f"ERROR: bad JSON from gh: {e}", file=sys.stderr)
        return None


def _me(override):
    if override:
        return override
    rc, out, _ = _run(["gh", "api", "user", "--jq", ".login"])
    return out.strip() if rc == 0 else ""


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", required=True, help="owner/name")
    ap.add_argument("--autonomy", choices=["afk", "hitl", "any"], default="afk",
                    help="which autonomy to surface as actionable (default: afk)")
    ap.add_argument("--me", help="my gh login (default: gh api user)")
    ap.add_argument("--limit", type=int, default=1000)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    issues = _list_issues(args.repo, args.limit)
    if issues is None:
        sys.exit(2)

    result = select(issues, _me(args.me), args.autonomy)

    if args.json:
        print(json.dumps(result, indent=2))
        sys.exit(0)

    q = result["actionable"]
    if q:
        print(f"Actionable ({len(q)}, autonomy={args.autonomy}):")
        for it in q:
            tag = " [resume]" if it["resumable"] else ""
            trace = f" trace:{','.join(it['trace_tdd'])}" if it["trace_tdd"] else ""
            print(f"  #{it['number']} [{it['autonomy']}] {it['title']}{trace}{tag}")
        print(f"\nNext: #{q[0]['number']}{' (resume)' if q[0]['resumable'] else ''}")
    else:
        print(f"No actionable issues (autonomy={args.autonomy}).")
    if result["excluded"]:
        print(f"\nExcluded ({len(result['excluded'])}):")
        for ex in result["excluded"]:
            print(f"  #{ex['number']}: {ex['reason']}")
    sys.exit(0)


if __name__ == "__main__":
    main()
