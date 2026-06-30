#!/usr/bin/env python3
"""Bounded reconciliation planner + hard drift gate for make-issues.

This is the "evaluate every change every time" engine, made BOUNDED by
construction. It is read-only and needs NO network: feed it the current issues
as JSON (the exact shape `gh issue list --json
number,title,state,stateReason,labels,body,assignees,
closedByPullRequestsReferences,milestone,updatedAt,url` returns) plus the spec
dir, and it computes the reconcile PLAN -- one decision per requirement vs its
matching issue -- without touching GitHub. The skill executes the plan only
AFTER this gate passes (exit 0) or a human approves its remediation report.

This is Spec Kit's /analyze, made a hard gate.

Per requirement vs its matching issue (matched on the meta block's `trace_req`):

  no matching issue                         -> CREATE
  fingerprint == stamped                    -> SKIP
  fingerprint != stamped, issue not-started -> UPDATE
  fingerprint != stamped, issue started/HITL-> COMMENT-AND-FLAG
  requirement removed/superseded:
      issue not-started/started             -> STALE/CLOSE (orphan)
      issue completed/merged                -> REFACTOR (back out shipped work; HITL)
  requirement MODIFIED + issue completed/merged          -> REFACTOR (HITL)
  requirement governed by a SUPERSEDED ADR + issue merged -> REFACTOR (HITL)

Plan scope: this engine is EXHAUSTIVE -- it walks every current requirement and
compares its live item fingerprint against the matching issue's stamped one, on
every run. That is the safe choice: a stale or missing CHANGELOG entry can never
cause a real change to be skipped. The watermark
(docs/specs/.make-issues-sync.json, the per-feature last-synced feature_version)
is surfaced for the report and advanced by the EXECUTOR after a successful sync;
it does NOT scope or short-circuit this plan. The CHANGELOG is the human/SKILL
narrative of the delta, not read by this script.

Idempotency: every op carries a stable idempotency key (req id + action +
fingerprint). A re-run with no spec change yields an all-SKIP plan and no
duplicate issues.

Refactor fan-out cap (--max-refactors N, default 10): if a change would open
more than N refactor issues, plan only N, plan ONE tracking issue ("M more
refactors pending"), and BLOCK (the gate fails) so a human triages. Never
silently drop.

Hard gate: exits NONZERO when there is BLOCKING drift --
  - a matched issue with a missing/malformed meta block (needs a human),
  - a refactor fan-out that overflowed the cap,
  - a requirement whose stored item fingerprint can't be computed.
Otherwise exits 0 and the plan is safe to execute.

  python scripts/analyze.py --spec-dir docs/specs --issues issues.json
  gh issue list ... --json ... | python scripts/analyze.py --spec-dir docs/specs --issues -
  python scripts/analyze.py --spec-dir docs/specs --issues issues.json --json
  python scripts/analyze.py --spec-dir docs/specs --issues issues.json --max-refactors 5

Exit codes: 0 = plan is clean and safe to execute,
            1 = BLOCKING drift -- a human must approve the remediation report,
            2 = spec/issues files can't be read.
"""
import argparse
import glob
import json
import os
import re
import sys

try:
    import yaml
except ImportError:
    print("PyYAML is required: pip install pyyaml --break-system-packages", file=sys.stderr)
    sys.exit(2)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from item_fingerprint import compute_item_fingerprint, feature_files  # noqa: E402

WATERMARK_FILE = ".make-issues-sync.json"

# Issue-body meta block markers (must match assets/issue-body-template.md).
META_OPEN = "<!-- make-issues:meta -->"
META_CLOSE = "<!-- /make-issues:meta -->"
_META_RE = re.compile(
    re.escape(META_OPEN) + r"\s*```ya?ml\s*(.*?)```\s*" + re.escape(META_CLOSE),
    re.DOTALL)

# Action names (stable -- the plan's vocabulary).
CREATE = "CREATE"
SKIP = "SKIP"
UPDATE = "UPDATE"
COMMENT_AND_FLAG = "COMMENT-AND-FLAG"
STALE_CLOSE = "STALE/CLOSE"
REFACTOR = "REFACTOR"
REFACTOR_TRACKING = "REFACTOR-TRACKING"


# ── Loading specs ────────────────────────────────────────────────────────────
def load_yaml(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_requirements(spec_dir):
    """{req_id: {record, feature_slug, fingerprint, status, governed_by}} across
    every features/*-data.yaml. Raises ValueError on a read error."""
    reqs = {}
    files = feature_files(spec_dir)
    if not files:
        raise ValueError(f"no feature data files under {spec_dir}/features/")
    for fpath in files:
        try:
            doc = load_yaml(fpath)
        except (OSError, yaml.YAMLError) as e:
            raise ValueError(f"cannot read {fpath}: {e}")
        if not isinstance(doc, dict):
            raise ValueError(f"{fpath} is not a YAML mapping")
        slug = str(((doc.get("meta") or {}).get("slug"))
                   or os.path.basename(fpath).replace("-data.yaml", ""))
        feature_version = str((doc.get("meta") or {}).get("feature_version") or "")
        for req in doc.get("requirements") or []:
            if isinstance(req, dict) and req.get("id"):
                rid = str(req["id"])
                try:
                    fingerprint = compute_item_fingerprint(req)
                except (TypeError, ValueError) as e:
                    raise ValueError(f"cannot fingerprint requirement {rid} in "
                                     f"{fpath}: {e}")
                reqs[rid] = {
                    "record": req,
                    "feature": slug,
                    "feature_version": feature_version,
                    "fingerprint": fingerprint,
                    "status": str(req.get("status") or "active"),
                    "governed_by": [str(a) for a in (req.get("governed_by") or [])],
                }
    return reqs


def load_adr_status(spec_dir):
    """{ADR id: status} from arch-data.yaml's decisions index. {} if absent."""
    arch_path = os.path.join(spec_dir, "arch-data.yaml")
    if not os.path.isfile(arch_path):
        return {}
    try:
        doc = load_yaml(arch_path)
    except (OSError, yaml.YAMLError):
        return {}
    out = {}
    for d in (doc or {}).get("decisions") or []:
        if isinstance(d, dict) and d.get("id"):
            out[str(d["id"])] = str(d.get("status") or "")
    return out


def load_watermark(spec_dir):
    """The committed per-feature sync watermark, or {} if none yet (first run)."""
    path = os.path.join(spec_dir, WATERMARK_FILE)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


# ── Parsing the issues JSON ──────────────────────────────────────────────────
def parse_meta(body):
    """Extract the YAML meta mapping from an issue body. Returns (meta, None) or
    (None, reason) when the block is missing or malformed -- which is BLOCKING
    drift (a human must re-stamp; we never guess from the prose)."""
    if not body:
        return None, "empty body"
    m = _META_RE.search(body)
    if not m:
        return None, "no make-issues:meta block (or markers hand-edited)"
    try:
        meta = yaml.safe_load(m.group(1))
    except yaml.YAMLError as e:
        return None, f"meta block is not valid YAML: {e}"
    if not isinstance(meta, dict):
        return None, "meta block is not a YAML mapping"
    if not meta.get("trace_req"):
        return None, "meta block has no trace_req (cannot match to a requirement)"
    return meta, None


def issue_state(issue):
    """not-started | started | completed | wont-do, from the gh JSON fields.
    'started' is INFERRED (assignee or closing-PR); when unsure, lean started."""
    state = str(issue.get("state") or "").upper()
    reason = str(issue.get("stateReason") or "").upper()
    if state == "CLOSED":
        return "wont-do" if reason == "NOT_PLANNED" else "completed"
    started = bool(issue.get("assignees")) or \
        bool(issue.get("closedByPullRequestsReferences")) or \
        any(str(l.get("name") if isinstance(l, dict) else l) == "status:doing"
            for l in (issue.get("labels") or []))
    return "started" if started else "not-started"


def is_merged(issue):
    """Shipped: completed (closed/COMPLETED) or has a merged closing PR."""
    if issue_state(issue) == "completed":
        return True
    for pr in issue.get("closedByPullRequestsReferences") or []:
        if isinstance(pr, dict) and (pr.get("state") == "MERGED" or pr.get("merged")):
            return True
    return False


def index_issues(issues):
    """Match issues to requirements. Returns (by_req, blocking) where
    by_req[req_id] -> [issue, ...] (a req may be sliced into several) and
    blocking is a list of {issue, reason} for issues with a bad meta block."""
    by_req, blocking = {}, []
    for issue in issues:
        meta, err = parse_meta(issue.get("body"))
        if err:
            blocking.append({"number": issue.get("number"),
                             "url": issue.get("url"),
                             "title": issue.get("title"), "reason": err})
            continue
        issue["_meta"] = meta
        for rid in meta.get("trace_req") or []:
            by_req.setdefault(str(rid), []).append(issue)
    return by_req, blocking


# ── The plan ─────────────────────────────────────────────────────────────────
def idempotency_key(req_id, action, fingerprint, extra=""):
    """Stable key so a re-run with no change reproduces the same ops (and the
    executor can dedupe). Action + req + the fingerprint it acted on."""
    return f"{action}:{req_id}:{(fingerprint or '')[:12]}{(':' + extra) if extra else ''}"


def _refactor_reason(req_id, info, issues, adr_status):
    """Why this matched, completed requirement is a REFACTOR, or None if it
    isn't. Two triggers: the requirement was superseded/removed but shipped, OR a
    governing ADR is now superseded/deprecated and the issue merged."""
    if info is None:
        return f"requirement {req_id} was removed from the specs but its issue merged"
    if info["status"] in ("superseded", "deferred"):
        return f"requirement {req_id} is {info['status']} but its issue merged"
    for adr in info["governed_by"]:
        if adr_status.get(adr) in ("superseded", "deprecated"):
            return (f"governing {adr} is {adr_status[adr]} and "
                    f"{req_id}'s issue merged")
    return None


def build_plan(reqs, issues_by_req, adr_status, blocking_meta, max_refactors,
               all_issues):
    """Compute the bounded reconcile plan. Returns a dict with `ops`,
    `blocking` (list of human-needed problems), `counts`, and `truncated`."""
    ops = []
    blocking = list(blocking_meta)        # bad meta blocks are already blocking
    refactor_candidates = []              # (req_id, issue, reason) -- capped below
    seen_issue_numbers = set()

    # 1) Walk every CURRENT requirement.
    for rid in sorted(reqs):
        info = reqs[rid]
        fp = info["fingerprint"]
        matched = issues_by_req.get(rid, [])
        active = info["status"] == "active"

        if not matched:
            if active:
                ops.append({"action": CREATE, "req": rid,
                            "feature": info["feature"], "autonomy": "tbd",
                            "fingerprint": fp,
                            "key": idempotency_key(rid, CREATE, fp),
                            "why": "new requirement, no issue yet"})
            # a non-active req with no issue is simply nothing to do
            continue

        for issue in matched:
            seen_issue_numbers.add(issue.get("number"))
            meta = issue.get("_meta", {})
            stamped = str(meta.get("fingerprint") or "")
            state = issue_state(issue)

            # A human deliberately closed this as won't-do (NOT_PLANNED). Respect
            # it -- never re-open, re-flag, or re-close. SKIP (the decision tree's
            # won't-do row), whether or not the requirement still exists/changed.
            if state == "wont-do":
                ops.append({"action": SKIP, "req": rid,
                            "issue": issue.get("number"), "fingerprint": fp,
                            "key": idempotency_key(rid, SKIP, fp,
                                                   str(issue.get("number"))),
                            "why": "issue closed as won't-do (NOT_PLANNED); "
                                   "respecting the human decision"})
                continue

            # superseded/deferred requirement -> orphan or refactor
            if not active:
                if is_merged(issue):
                    reason = _refactor_reason(rid, info, all_issues, adr_status)
                    refactor_candidates.append((rid, issue,
                                                reason or f"{rid} is {info['status']}"))
                else:
                    ops.append({"action": STALE_CLOSE, "req": rid,
                                "issue": issue.get("number"),
                                "fingerprint": fp,
                                "key": idempotency_key(rid, STALE_CLOSE, fp,
                                                       str(issue.get("number"))),
                                "why": f"requirement {info['status']} in specs; "
                                       "close not-started/started issue as orphan"})
                continue

            # active requirement: governing-ADR-supersede on a merged issue is a
            # refactor even if the requirement text itself didn't change.
            adr_super = next((a for a in info["governed_by"]
                              if adr_status.get(a) in ("superseded", "deprecated")),
                             None)
            if is_merged(issue) and adr_super and stamped != fp:
                refactor_candidates.append(
                    (rid, issue,
                     f"governing {adr_super} is {adr_status[adr_super]}; "
                     f"{rid}'s issue merged"))
                continue
            if is_merged(issue) and adr_super and stamped == fp:
                # the requirement text is unchanged but its governing decision
                # flipped -- still a refactor of shipped work.
                refactor_candidates.append(
                    (rid, issue,
                     f"governing {adr_super} is {adr_status[adr_super]}; "
                     f"{rid}'s issue merged (requirement text unchanged)"))
                continue

            if stamped == fp:
                ops.append({"action": SKIP, "req": rid,
                            "issue": issue.get("number"), "fingerprint": fp,
                            "key": idempotency_key(rid, SKIP, fp,
                                                   str(issue.get("number"))),
                            "why": "fingerprint matches; no-op"})
                continue

            # fingerprint changed
            if is_merged(issue) or state == "completed":
                refactor_candidates.append(
                    (rid, issue,
                     f"{rid} changed but its issue is completed/merged"))
            elif state == "not-started":
                ops.append({"action": UPDATE, "req": rid,
                            "issue": issue.get("number"), "fingerprint": fp,
                            "key": idempotency_key(rid, UPDATE, fp,
                                                   str(issue.get("number"))),
                            "why": "fingerprint changed; issue not started -- "
                                   "auto-update managed regions"})
            else:  # started or HITL
                autonomy = str(meta.get("autonomy") or "afk")
                ops.append({"action": COMMENT_AND_FLAG, "req": rid,
                            "issue": issue.get("number"), "fingerprint": fp,
                            "autonomy": autonomy,
                            "flag": "needs-rebase" if autonomy == "afk"
                                    else "spec-drift",
                            "key": idempotency_key(rid, COMMENT_AND_FLAG, fp,
                                                   str(issue.get("number"))),
                            "why": "fingerprint changed; issue started -- "
                                   "comment and flag, do not auto-edit"})

    # 2) Issues whose requirement vanished entirely from the specs (orphans not
    #    seen above because the req id is gone from `reqs`).
    for rid, matched in sorted(issues_by_req.items()):
        if rid in reqs:
            continue
        for issue in matched:
            if issue.get("number") in seen_issue_numbers:
                continue
            if issue_state(issue) == "wont-do":
                ops.append({"action": SKIP, "req": rid,
                            "issue": issue.get("number"), "fingerprint": "",
                            "key": idempotency_key(rid, SKIP, "",
                                                   str(issue.get("number"))),
                            "why": "issue closed as won't-do; respecting the "
                                   "human decision (requirement gone from specs)"})
                continue
            if is_merged(issue):
                refactor_candidates.append(
                    (rid, issue,
                     f"requirement {rid} removed from specs but its issue merged"))
            else:
                ops.append({"action": STALE_CLOSE, "req": rid,
                            "issue": issue.get("number"),
                            "fingerprint": "",
                            "key": idempotency_key(rid, STALE_CLOSE, "",
                                                   str(issue.get("number"))),
                            "why": f"requirement {rid} no longer in specs; "
                                   "close as orphan"})

    # 3) Apply the refactor fan-out cap. Plan up to N; if more, plan ONE tracking
    #    issue and BLOCK the gate (a human triages the cascade).
    truncated = 0
    refactor_candidates.sort(key=lambda c: (c[0], c[1].get("number") or 0))
    for i, (rid, issue, reason) in enumerate(refactor_candidates):
        if i < max_refactors:
            ops.append({"action": REFACTOR, "req": rid,
                        "issue": issue.get("number"),
                        "autonomy": "hitl", "fingerprint": reqs.get(rid, {}).get("fingerprint", ""),
                        "key": idempotency_key(rid, REFACTOR,
                                               reqs.get(rid, {}).get("fingerprint", ""),
                                               str(issue.get("number"))),
                        "why": reason})
        else:
            truncated += 1
    if truncated:
        ops.append({"action": REFACTOR_TRACKING, "req": None,
                    "count": truncated,
                    "key": idempotency_key("ALL", REFACTOR_TRACKING, "",
                                           f"{max_refactors}:{truncated}"),
                    "why": f"{truncated} more refactor(s) over the --max-refactors "
                           f"{max_refactors} cap; one tracking issue planned, "
                           "rest deferred for human triage"})
        blocking.append({"kind": "refactor_cap_overflow",
                         "reason": f"{truncated} refactor(s) exceed the cap of "
                                   f"{max_refactors}; a human must triage before "
                                   "the cascade runs"})

    counts = {}
    for op in ops:
        counts[op["action"]] = counts.get(op["action"], 0) + 1

    return {"ops": ops, "blocking": blocking, "counts": counts,
            "truncated": truncated, "max_refactors": max_refactors}


def read_issues(path):
    """Load the issues JSON from a file or stdin ('-'). Returns a list."""
    if path == "-":
        raw = sys.stdin.read()
    else:
        with open(path, encoding="utf-8") as f:
            raw = f.read()
    data = json.loads(raw or "[]")
    if not isinstance(data, list):
        raise ValueError("issues JSON must be an array (gh issue list --json ...)")
    return data


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spec-dir", default="docs/specs",
                    help="the layered spec dir (default: docs/specs)")
    ap.add_argument("--issues", required=True,
                    help="path to the `gh issue list --json ...` output, or - for stdin")
    ap.add_argument("--max-refactors", type=int, default=10,
                    help="cap on refactor issues opened in one run (default 10)")
    ap.add_argument("--json", action="store_true", help="emit the plan as JSON")
    args = ap.parse_args()

    try:
        reqs = load_requirements(args.spec_dir)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)
    try:
        issues = read_issues(args.issues)
    except (OSError, ValueError) as e:
        print(f"ERROR: cannot read issues: {e}", file=sys.stderr)
        sys.exit(2)

    adr_status = load_adr_status(args.spec_dir)
    issues_by_req, blocking_meta = index_issues(issues)
    plan = build_plan(reqs, issues_by_req, adr_status, blocking_meta,
                      args.max_refactors, issues)

    # The watermark is read for context (and re-stamped by the executor after a
    # successful sync); analyze surfaces it but does not write it.
    watermark = load_watermark(args.spec_dir)
    plan["watermark"] = watermark

    blocked = bool(plan["blocking"])
    _report(plan, args.json)
    sys.exit(1 if blocked else 0)


def _report(plan, as_json):
    if as_json:
        print(json.dumps(plan, indent=2, sort_keys=True))
        return
    counts = plan["counts"]
    order = [CREATE, SKIP, UPDATE, COMMENT_AND_FLAG, STALE_CLOSE, REFACTOR,
             REFACTOR_TRACKING]
    print("Reconcile plan:")
    for action in order:
        if action in counts:
            print(f"  {action:18s} {counts[action]}")
    for op in plan["ops"]:
        if op["action"] in (REFACTOR, REFACTOR_TRACKING, STALE_CLOSE,
                            COMMENT_AND_FLAG):
            tgt = op.get("issue") or op.get("req") or "all"
            print(f"    - {op['action']} ({tgt}): {op['why']}")
    if plan["blocking"]:
        print("\nBLOCKING DRIFT -- a human must approve remediation:")
        for b in plan["blocking"]:
            if "reason" in b and "number" in b:
                print(f"  - issue #{b['number']}: {b['reason']}")
            else:
                print(f"  - {b.get('kind', 'blocked')}: {b['reason']}")
        print("\nFAIL -- no GitHub write until this is resolved (exit 1)")
    else:
        print("\nPASS -- plan is clean and safe to execute (exit 0)")


if __name__ == "__main__":
    main()
