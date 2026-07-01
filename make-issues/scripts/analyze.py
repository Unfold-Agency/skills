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

Detection is GLOBAL; writes are SCOPED. The census below ALWAYS loads the whole
spec set and compares every requirement's live fingerprint against its issue's
stamped one -- a stale/missing CHANGELOG can never hide a real change. `--scope`
(feature slugs and/or requirement ids) bounds only which ops are ACTIONABLE:
drift outside the scope is still detected and REPORTED (plan["out_of_scope"]),
just not written. Because the whole spec set is always loaded, the orphan-close
census is sound -- a scoped run can never mistake an unselected feature's
requirements for "removed from specs" and mass-close them. STALE/CLOSE and
REFACTOR only ever fire for an issue whose feature is IN scope.

Provenance: an issue may be `provenance: spec` (absent == spec; projects a
requirement, fingerprint-reconciled as above) or `provenance: amendment` (added
on demand, anchored to a feature/goal/ADR, body human-owned). Amendments are
HARD-EXEMPT from the orphan/stale/refactor/clobber paths: the planner leaves
them alone (SKIP), FLAGS them only if their feature anchor vanished, and can
PROMOTE one to a spec issue via --promote ISSUE=REQ-ID (operator-confirmed).

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
  - a requirement whose stored item fingerprint can't be computed,
  - a --promote target that is not an active requirement.
Otherwise exits 0 and the plan is safe to execute. Out-of-scope drift never
blocks (it is reported for the operator, not acted on).

  python scripts/analyze.py --spec-dir docs/specs --issues issues.json
  python scripts/analyze.py --spec-dir docs/specs --issues issues.json --scope checkout,cart
  gh issue list ... --json ... | python scripts/analyze.py --spec-dir docs/specs --issues -
  python scripts/analyze.py --spec-dir docs/specs --issues issues.json --promote 42=FR-CHK-007
  python scripts/analyze.py --spec-dir docs/specs --issues issues.json --json

Exit codes: 0 = plan is clean and safe to execute,
            1 = BLOCKING drift -- a human must approve the remediation report,
            2 = spec/issues files can't be read (or bad --promote/--scope args).
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
from item_fingerprint import (  # noqa: E402
    compute_item_fingerprint, feature_files, load_spec_doc)

WATERMARK_FILE = ".make-issues-sync.json"

# Issue-body meta block markers (must match assets/issue-body-template.md).
META_OPEN = "<!-- make-issues:meta -->"
META_CLOSE = "<!-- /make-issues:meta -->"
_META_RE = re.compile(
    re.escape(META_OPEN) + r"\s*```ya?ml\s*(.*?)```\s*" + re.escape(META_CLOSE),
    re.DOTALL)

# A requirement id, used to classify --scope tokens (id vs feature slug).
_REQ_ID_RE = re.compile(r"^(FR|IR|NFR|CR)-[A-Z]{2,5}-\d{3,}$")

# Action names (stable -- the plan's vocabulary).
CREATE = "CREATE"
SKIP = "SKIP"
UPDATE = "UPDATE"
COMMENT_AND_FLAG = "COMMENT-AND-FLAG"
STALE_CLOSE = "STALE/CLOSE"
REFACTOR = "REFACTOR"
REFACTOR_TRACKING = "REFACTOR-TRACKING"
PROMOTE = "PROMOTE"          # amendment -> spec issue (operator-confirmed)


# ── Loading specs ────────────────────────────────────────────────────────────
def load_yaml(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_requirements(spec_dir):
    """{req_id: {record, feature_slug, fingerprint, status, governed_by}} across
    every features/*.md (requirements live in the frontmatter). Raises ValueError
    on a read error. ALWAYS the whole spec set -- scope bounds writes, not this
    load, so the orphan census is always computed against complete specs."""
    reqs = {}
    files = feature_files(spec_dir)
    if not files:
        raise ValueError(f"no feature specs under {spec_dir}/features/")
    for fpath in files:
        try:
            doc = load_spec_doc(fpath)
        except (OSError, yaml.YAMLError) as e:
            raise ValueError(f"cannot read {fpath}: {e}")
        if not isinstance(doc, dict):
            raise ValueError(f"{fpath} has no spec frontmatter")
        meta = doc.get("meta") if isinstance(doc.get("meta"), dict) else {}
        slug = str(meta.get("slug")
                   or os.path.basename(fpath).replace(".md", ""))
        feature_version = str(meta.get("feature_version") or "")
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


# ── Scope (bounds WRITES only; detection stays global) ───────────────────────
def parse_scope(spec):
    """Parse a --scope string into {"features": set, "reqs": set}, or None for a
    full (unscoped) run. Tokens matching a requirement id go to `reqs`; everything
    else is a feature slug."""
    if not spec:
        return None
    features, reqs = set(), set()
    for tok in spec.split(","):
        tok = tok.strip()
        if not tok:
            continue
        (reqs if _REQ_ID_RE.match(tok) else features).add(tok)
    if not features and not reqs:
        return None
    return {"features": features, "reqs": reqs}


def in_scope(feature, req_id, scope):
    """True when this feature/requirement is ACTIONABLE this run. A None scope
    means everything is actionable (full run)."""
    if scope is None:
        return True
    if feature and feature in scope["features"]:
        return True
    return bool(req_id) and req_id in scope["reqs"]


def parse_promote(pairs):
    """['42=FR-CHK-007', ...] -> {42: 'FR-CHK-007'}. Raises ValueError on a
    malformed pair so the caller can exit 2 (an explicit operator action must not
    be silently dropped)."""
    out = {}
    for p in pairs or []:
        if "=" not in p:
            raise ValueError(f"--promote expects ISSUE=REQ-ID, got {p!r}")
        num, rid = p.split("=", 1)
        try:
            out[int(num.strip())] = rid.strip()
        except ValueError:
            raise ValueError(f"--promote issue number is not an integer: {p!r}")
    return out


# ── Parsing the issues JSON ──────────────────────────────────────────────────
def parse_meta(body):
    """Extract the YAML meta mapping from an issue body. Returns (meta, None) or
    (None, reason) when the block is missing or malformed -- which is BLOCKING
    drift (a human must re-stamp; we never guess from the prose).

    `provenance` is the first discriminant (absent == spec, so pre-existing
    issues are unaffected). A spec issue requires a non-empty list `trace_req`;
    an amendment may have an empty trace_req but requires a `feature` anchor. A
    string trace_req (hand-edited `trace_req: FR-CHK-001`) is always blocking --
    it must never be iterated character-by-character downstream. The returned
    meta always carries a normalized `provenance`."""
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

    provenance = str(meta.get("provenance") or "spec").strip().lower()
    trace_req = meta.get("trace_req")
    if trace_req is not None and not isinstance(trace_req, list):
        # e.g. `trace_req: FR-CHK-001` -- would iterate as characters. Fail closed.
        return None, "meta block's trace_req is present but not a list"

    if provenance == "amendment":
        feature = meta.get("feature")
        if not isinstance(feature, str) or not feature.strip():
            return None, ("amendment issue has no feature anchor "
                          "(provenance: amendment requires a feature)")
        meta["provenance"] = "amendment"
        return meta, None

    # spec provenance (the default): a requirement trace is required
    if not isinstance(trace_req, list) or not trace_req:
        return None, "meta block's trace_req is missing or not a list"
    meta["provenance"] = "spec"
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
    """Match issues to requirements. Returns (by_req, blocking, amendments) where
    by_req[req_id] -> [issue, ...] (a req may be sliced into several), amendments
    is the list of provenance: amendment issues (matched by feature anchor, not a
    requirement), and blocking is a list of issues with a bad meta block."""
    by_req, blocking, amendments = {}, [], []
    for issue in issues:
        meta, err = parse_meta(issue.get("body"))
        if err:
            blocking.append({"number": issue.get("number"),
                             "url": issue.get("url"),
                             "title": issue.get("title"), "reason": err})
            continue
        issue["_meta"] = meta
        if meta.get("provenance") == "amendment":
            amendments.append(issue)
            continue
        for rid in meta.get("trace_req") or []:
            by_req.setdefault(str(rid), []).append(issue)
    return by_req, blocking, amendments


# ── The plan ─────────────────────────────────────────────────────────────────
def idempotency_key(req_id, action, fingerprint, extra=""):
    """Stable key so a re-run with no change reproduces the same ops (and the
    executor can dedupe). Action + req + the fingerprint it acted on."""
    return f"{action}:{req_id}:{(fingerprint or '')[:12]}{(':' + extra) if extra else ''}"


def _refactor_reason(req_id, info, adr_status):
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
               amendments=None, scope=None, promote=None):
    """Compute the bounded reconcile plan. Returns a dict with `ops`,
    `out_of_scope` (drift detected but not acted on -- report only), `blocking`
    (human-needed problems), `counts`, `truncated`, and `scope`.

    Detection is global (every requirement is examined); `scope` bounds only
    which ops are ACTIONABLE. STALE/CLOSE and REFACTOR only fire for an issue
    whose feature is in scope -- and, because `reqs` is always the complete spec
    set, an out-of-scope feature can never be misread as 'removed from specs'."""
    ops = []
    out_of_scope = []
    blocking = list(blocking_meta)        # bad meta blocks are already blocking
    refactor_candidates = []              # (req_id, issue, reason, feature)
    seen_issue_numbers = set()
    amendments = amendments or []
    promote = promote or {}
    known_features = {info["feature"] for info in reqs.values()}

    def route(op, feature, rid):
        """Send an op to `ops` if actionable, else record non-SKIP drift in
        `out_of_scope`. Out-of-scope no-ops (SKIP) are simply dropped."""
        if in_scope(feature, rid, scope):
            ops.append(op)
        elif op["action"] != SKIP:
            op["out_of_scope"] = True
            out_of_scope.append(op)

    # 1) Walk every CURRENT requirement (the whole spec set -- detection is global).
    for rid in sorted(reqs):
        info = reqs[rid]
        fp = info["fingerprint"]
        feature = info["feature"]
        matched = issues_by_req.get(rid, [])
        active = info["status"] == "active"

        if not matched:
            if active:
                route({"action": CREATE, "req": rid,
                       "feature": feature, "autonomy": "tbd",
                       "fingerprint": fp,
                       "key": idempotency_key(rid, CREATE, fp),
                       "why": "new requirement, no issue yet"}, feature, rid)
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
                route({"action": SKIP, "req": rid,
                       "issue": issue.get("number"), "fingerprint": fp,
                       "key": idempotency_key(rid, SKIP, fp,
                                              str(issue.get("number"))),
                       "why": "issue closed as won't-do (NOT_PLANNED); "
                              "respecting the human decision"}, feature, rid)
                continue

            # superseded/deferred requirement -> orphan or refactor
            if not active:
                if is_merged(issue):
                    reason = _refactor_reason(rid, info, adr_status)
                    refactor_candidates.append((rid, issue,
                                                reason or f"{rid} is {info['status']}",
                                                feature))
                else:
                    route({"action": STALE_CLOSE, "req": rid,
                           "issue": issue.get("number"),
                           "fingerprint": fp,
                           "key": idempotency_key(rid, STALE_CLOSE, fp,
                                                  str(issue.get("number"))),
                           "why": f"requirement {info['status']} in specs; "
                                  "close not-started/started issue as orphan"},
                          feature, rid)
                continue

            # active requirement: a governing-ADR supersede on a merged issue is a
            # refactor of shipped work even when the requirement text is unchanged
            # (the governing decision flipped). One branch, with the text-unchanged
            # case noted in the reason.
            adr_super = next((a for a in info["governed_by"]
                              if adr_status.get(a) in ("superseded", "deprecated")),
                             None)
            if is_merged(issue) and adr_super:
                suffix = " (requirement text unchanged)" if stamped == fp else ""
                refactor_candidates.append(
                    (rid, issue,
                     f"governing {adr_super} is {adr_status[adr_super]}; "
                     f"{rid}'s issue merged{suffix}", feature))
                continue

            if stamped == fp:
                route({"action": SKIP, "req": rid,
                       "issue": issue.get("number"), "fingerprint": fp,
                       "key": idempotency_key(rid, SKIP, fp,
                                              str(issue.get("number"))),
                       "why": "fingerprint matches; no-op"}, feature, rid)
                continue

            # fingerprint changed
            if is_merged(issue) or state == "completed":
                refactor_candidates.append(
                    (rid, issue,
                     f"{rid} changed but its issue is completed/merged", feature))
            elif state == "not-started":
                route({"action": UPDATE, "req": rid,
                       "issue": issue.get("number"), "fingerprint": fp,
                       "key": idempotency_key(rid, UPDATE, fp,
                                              str(issue.get("number"))),
                       "why": "fingerprint changed; issue not started -- "
                              "auto-update managed regions"}, feature, rid)
            else:  # started or HITL
                autonomy = str(meta.get("autonomy") or "afk")
                route({"action": COMMENT_AND_FLAG, "req": rid,
                       "issue": issue.get("number"), "fingerprint": fp,
                       "autonomy": autonomy,
                       "flag": "needs-rebase" if autonomy == "afk"
                               else "spec-drift",
                       "key": idempotency_key(rid, COMMENT_AND_FLAG, fp,
                                              str(issue.get("number"))),
                       "why": "fingerprint changed; issue started -- "
                              "comment and flag, do not auto-edit"}, feature, rid)

    # 2) Issues whose requirement vanished entirely from the specs (orphans not
    #    seen above because the req id is gone from `reqs`). `reqs` is the COMPLETE
    #    spec set, so this is a true orphan -- never an out-of-scope false positive.
    #    The issue's own meta `feature` decides whether the close is in scope.
    for rid, matched in sorted(issues_by_req.items()):
        if rid in reqs:
            continue
        for issue in matched:
            if issue.get("number") in seen_issue_numbers:
                continue
            ofeature = str((issue.get("_meta") or {}).get("feature") or "")
            if issue_state(issue) == "wont-do":
                route({"action": SKIP, "req": rid,
                       "issue": issue.get("number"), "fingerprint": "",
                       "key": idempotency_key(rid, SKIP, "",
                                              str(issue.get("number"))),
                       "why": "issue closed as won't-do; respecting the "
                              "human decision (requirement gone from specs)"},
                      ofeature, rid)
                continue
            if is_merged(issue):
                refactor_candidates.append(
                    (rid, issue,
                     f"requirement {rid} removed from specs but its issue merged",
                     ofeature))
            else:
                route({"action": STALE_CLOSE, "req": rid,
                       "issue": issue.get("number"),
                       "fingerprint": "",
                       "key": idempotency_key(rid, STALE_CLOSE, "",
                                              str(issue.get("number"))),
                       "why": f"requirement {rid} no longer in specs; "
                              "close as orphan"}, ofeature, rid)

    # 3) Amendments: provenance-exempt. Never orphan-close or refactor; leave the
    #    body alone (human-owned). Flag only if the feature anchor vanished; PROMOTE
    #    when the operator confirms a requirement now covers it.
    amendment_nums = {issue.get("number") for issue in amendments}
    for issue in amendments:
        ometa = issue.get("_meta", {})
        feature = str(ometa.get("feature") or "")
        num = issue.get("number")
        akey = f"AMD{num}"

        if num in promote:
            target = promote[num]
            tinfo = reqs.get(target)
            if not tinfo or tinfo["status"] != "active":
                blocking.append({"kind": "promote_target_invalid", "number": num,
                                 "reason": f"--promote {num}={target}: {target} is "
                                           "not an active requirement in the specs"})
                continue
            # An explicit operator action is always actionable (like do-work --issue).
            ops.append({"action": PROMOTE, "req": target, "issue": num,
                        "feature": tinfo["feature"],
                        "fingerprint": tinfo["fingerprint"],
                        "key": idempotency_key(target, PROMOTE,
                                               tinfo["fingerprint"], str(num)),
                        "why": f"promote amendment #{num} to {target} "
                               "(operator-confirmed): set trace_req, flip "
                               "provenance to spec, stamp fingerprint, in place"})
            continue

        if feature in known_features:
            route({"action": SKIP, "req": None, "issue": num,
                   "provenance": "amendment", "feature": feature,
                   "key": idempotency_key(akey, SKIP, "", str(num)),
                   "why": f"amendment (anchor '{feature}' valid); human-owned, "
                          "left untouched"}, feature, None)
        else:
            route({"action": COMMENT_AND_FLAG, "req": None, "issue": num,
                   "provenance": "amendment", "feature": feature,
                   "autonomy": "hitl", "flag": "orphaned",
                   "key": idempotency_key(akey, COMMENT_AND_FLAG, "", str(num)),
                   "why": f"amendment anchor feature '{feature}' is gone from the "
                          "specs; a human must re-anchor or close (never "
                          "auto-closed)"}, feature, None)

    # A --promote target that is not an amendment issue (a spec issue, a malformed
    # one, or a number that does not exist) is an explicit operator action that must
    # never be silently dropped -- block the gate so the operator sees it.
    for num, target in promote.items():
        if num not in amendment_nums:
            blocking.append({"kind": "promote_issue_invalid", "number": num,
                             "reason": f"--promote {num}={target}: issue #{num} is "
                                       "not an amendment issue (or does not exist)"})

    # 4) Apply the refactor fan-out cap -- to the IN-SCOPE refactors only. Plan up
    #    to N; if more, plan ONE tracking issue and BLOCK the gate (a human triages
    #    the cascade). Out-of-scope refactors are reported, never counted vs the cap.
    for rid, issue, reason, feature in refactor_candidates:
        if not in_scope(feature, rid, scope):
            out_of_scope.append({"action": REFACTOR, "req": rid,
                                 "issue": issue.get("number"),
                                 "out_of_scope": True, "why": reason})
    in_scope_refs = [c for c in refactor_candidates
                     if in_scope(c[3], c[0], scope)]
    in_scope_refs.sort(key=lambda c: (c[0], c[1].get("number") or 0))
    truncated = 0
    for i, (rid, issue, reason, feature) in enumerate(in_scope_refs):
        if i < max_refactors:
            ops.append({"action": REFACTOR, "req": rid,
                        "issue": issue.get("number"),
                        "autonomy": "hitl",
                        "fingerprint": reqs.get(rid, {}).get("fingerprint", ""),
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

    return {"ops": ops, "out_of_scope": out_of_scope, "blocking": blocking,
            "counts": counts, "truncated": truncated,
            "max_refactors": max_refactors,
            "scope": (None if scope is None
                      else {"features": sorted(scope["features"]),
                            "reqs": sorted(scope["reqs"])})}


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
    ap.add_argument("--scope", default="",
                    help="comma-separated feature slugs and/or requirement ids to "
                         "ACT on; empty = full run (act on everything). Detection "
                         "is always global; scope bounds only the writes.")
    ap.add_argument("--promote", action="append", default=[], metavar="ISSUE=REQ",
                    help="promote an amendment issue to a spec requirement "
                         "(operator-confirmed; repeatable), e.g. 42=FR-CHK-007")
    ap.add_argument("--max-refactors", type=int, default=10,
                    help="cap on refactor issues opened in one run (default 10)")
    ap.add_argument("--json", action="store_true", help="emit the plan as JSON")
    args = ap.parse_args()

    try:
        scope = parse_scope(args.scope)
        promote = parse_promote(args.promote)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)
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
    issues_by_req, blocking_meta, amendments = index_issues(issues)
    plan = build_plan(reqs, issues_by_req, adr_status, blocking_meta,
                      args.max_refactors, amendments=amendments, scope=scope,
                      promote=promote)

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
             REFACTOR_TRACKING, PROMOTE]
    scope = plan.get("scope")
    if scope is None:
        print("Reconcile plan (scope: ALL -- full run):")
    else:
        toks = ", ".join(scope["features"] + scope["reqs"]) or "(none)"
        print(f"Reconcile plan (scope: {toks} -- writes bounded; "
              "detection is global):")
    for action in order:
        if action in counts:
            print(f"  {action:18s} {counts[action]}")
    for op in plan["ops"]:
        if op["action"] in (REFACTOR, REFACTOR_TRACKING, STALE_CLOSE,
                            COMMENT_AND_FLAG, PROMOTE):
            tgt = op.get("issue") or op.get("req") or "all"
            print(f"    - {op['action']} ({tgt}): {op['why']}")
    out = plan.get("out_of_scope") or []
    if out:
        print(f"\nOUT-OF-SCOPE DRIFT ({len(out)}) -- detected, NOT acted on this "
              "run (widen --scope or run without --scope to act):")
        for op in out:
            tgt = op.get("issue") or op.get("req") or "?"
            print(f"    - would {op['action']} ({tgt}): {op['why']}")
    if plan["blocking"]:
        print("\nBLOCKING DRIFT -- a human must approve remediation:")
        for b in plan["blocking"]:
            if "reason" in b and "number" in b:
                print(f"  - issue #{b['number']}: {b['reason']}")
            else:
                print(f"  - {b.get('kind', 'blocked')}: {b['reason']}")
        print("\nFAIL -- no GitHub write until this is resolved (exit 1)")
    else:
        tail = (" (partial coverage: out-of-scope drift above is unchecked-by-"
                "action this run)") if out else ""
        print(f"\nPASS -- plan is clean and safe to execute (exit 0){tail}")


if __name__ == "__main__":
    main()
