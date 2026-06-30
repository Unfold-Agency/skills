#!/usr/bin/env python3
"""No-network unit test for the bounded reconcile planner + hard drift gate.

Asserts the planned actions for each branch of the decision tree:
  new req                      -> CREATE
  unchanged                    -> SKIP   (and idempotency: re-run = all-SKIP)
  changed + not-started        -> UPDATE
  changed + started            -> COMMENT-AND-FLAG
  changed + completed/merged   -> REFACTOR
  removed/superseded req       -> STALE/CLOSE (orphan, not merged)
  ADR-supersede on merged issue-> REFACTOR
  fan-out over the cap         -> truncates + tracking op + gate BLOCKS (exit 1)
  malformed meta block         -> blocking drift (gate BLOCKS, exit 1)

  python scripts/tests/test_analyze.py
Exit 0 = every branch plans as expected.
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from item_fingerprint import compute_item_fingerprint  # noqa: E402
import analyze  # noqa: E402

UPSTREAM = os.path.join(HERE, "specs", "upstream")

failures = []


def check(name, cond):
    print(f"{'ok  ' if cond else 'FAIL'} {name}")
    if not cond:
        failures.append(name)


def make_req(rid, status="active", governed_by=None, ac=None, desc="do a thing"):
    return {
        "id": rid, "name": f"req {rid}", "kind": "functional",
        "description": desc,
        "acceptance_criteria": ac or [f"WHEN x THE SYSTEM SHALL {rid}."],
        "governed_by": governed_by or [], "depends_on": [],
        "interface": f"{rid}()", "priority": "must", "status": status,
    }


def req_info(rec, feature="checkout"):
    return {
        "record": rec, "feature": feature, "feature_version": "1.0",
        "fingerprint": compute_item_fingerprint(rec),
        "status": str(rec.get("status") or "active"),
        "governed_by": [str(a) for a in (rec.get("governed_by") or [])],
    }


def issue_body(trace_req, fingerprint, autonomy="afk"):
    """A minimal but well-formed managed issue body (just the meta block)."""
    reqs = "[" + ", ".join(trace_req) + "]"
    return (
        "## Goal\nSomething.\n\n"
        f"{analyze.META_OPEN}\n```yaml\n"
        f"trace_req: {reqs}\n"
        "trace_adr: []\n"
        "feature: checkout\n"
        'source_version: "1.0"\n'
        f"autonomy: {autonomy}\n"
        f'fingerprint: "{fingerprint}"\n'
        f"```\n{analyze.META_CLOSE}\n"
    )


def issue(number, trace_req, fingerprint, state="OPEN", reason=None,
          assignees=None, prs=None, autonomy="afk"):
    return {
        "number": number, "title": f"issue {number}", "state": state,
        "stateReason": reason, "labels": [],
        "assignees": assignees or [], "closedByPullRequestsReferences": prs or [],
        "milestone": None, "updatedAt": "2026-06-01T00:00:00Z",
        "url": f"https://example/{number}",
        "body": issue_body(trace_req, fingerprint, autonomy),
    }


def plan_for(reqs_map, issues, adr_status=None, max_refactors=10):
    by_req, blocking_meta = analyze.index_issues(issues)
    return analyze.build_plan(reqs_map, by_req, adr_status or {}, blocking_meta,
                              max_refactors)


def actions(plan):
    return [op["action"] for op in plan["ops"]]


def op_for(plan, req):
    return next((op for op in plan["ops"] if op.get("req") == req), None)


# ── CREATE: a new requirement with no issue ─────────────────────────────────
r1 = make_req("FR-CHK-001")
reqs = {"FR-CHK-001": req_info(r1)}
p = plan_for(reqs, [])
check("new req -> CREATE", op_for(p, "FR-CHK-001")["action"] == analyze.CREATE)
check("CREATE plan is not blocking", not p["blocking"])

# ── SKIP: unchanged (stamped fingerprint == current) ────────────────────────
fp1 = compute_item_fingerprint(r1)
iss = [issue(1, ["FR-CHK-001"], fp1)]
p = plan_for(reqs, iss)
check("unchanged req -> SKIP", op_for(p, "FR-CHK-001")["action"] == analyze.SKIP)

# Idempotency: re-running the same all-synced set yields all-SKIP, no CREATE.
p2 = plan_for(reqs, iss)
check("idempotent: re-run is all-SKIP", set(actions(p2)) == {analyze.SKIP})
check("idempotency keys are stable across runs",
      [o["key"] for o in p["ops"]] == [o["key"] for o in p2["ops"]])

# ── UPDATE: changed fingerprint, not-started ────────────────────────────────
iss = [issue(2, ["FR-CHK-001"], "STALEHASH")]   # stamped != current
p = plan_for(reqs, iss)
check("changed + not-started -> UPDATE",
      op_for(p, "FR-CHK-001")["action"] == analyze.UPDATE)

# ── COMMENT-AND-FLAG: changed, started (has an assignee) ────────────────────
iss = [issue(3, ["FR-CHK-001"], "STALEHASH", assignees=[{"login": "dev"}])]
p = plan_for(reqs, iss)
op = op_for(p, "FR-CHK-001")
check("changed + started -> COMMENT-AND-FLAG", op["action"] == analyze.COMMENT_AND_FLAG)
check("afk started -> needs-rebase flag", op["flag"] == "needs-rebase")

iss = [issue(4, ["FR-CHK-001"], "STALEHASH", assignees=[{"login": "dev"}],
             autonomy="hitl")]
p = plan_for(reqs, iss)
check("changed + started + hitl -> spec-drift flag",
      op_for(p, "FR-CHK-001")["flag"] == "spec-drift")

# ── REFACTOR: changed fingerprint, issue completed/merged ───────────────────
iss = [issue(5, ["FR-CHK-001"], "STALEHASH", state="CLOSED", reason="COMPLETED")]
p = plan_for(reqs, iss)
op = op_for(p, "FR-CHK-001")
check("changed + completed -> REFACTOR", op["action"] == analyze.REFACTOR)
check("REFACTOR is HITL", op["autonomy"] == "hitl")

# merged via a closing PR (issue still open) also refactors
iss = [issue(6, ["FR-CHK-001"], "STALEHASH",
             prs=[{"state": "MERGED"}])]
p = plan_for(reqs, iss)
check("changed + merged-PR -> REFACTOR",
      op_for(p, "FR-CHK-001")["action"] == analyze.REFACTOR)

# ── STALE/CLOSE: requirement superseded, issue not merged ───────────────────
r_sup = make_req("FR-CHK-001", status="superseded")
reqs_sup = {"FR-CHK-001": req_info(r_sup)}
iss = [issue(7, ["FR-CHK-001"], compute_item_fingerprint(r_sup))]
p = plan_for(reqs_sup, iss)
check("superseded req + not-started issue -> STALE/CLOSE",
      op_for(p, "FR-CHK-001")["action"] == analyze.STALE_CLOSE)

# superseded requirement whose issue is merged -> REFACTOR (back out shipped)
iss = [issue(8, ["FR-CHK-001"], compute_item_fingerprint(r_sup),
             state="CLOSED", reason="COMPLETED")]
p = plan_for(reqs_sup, iss)
check("superseded req + merged issue -> REFACTOR",
      op_for(p, "FR-CHK-001")["action"] == analyze.REFACTOR)

# requirement REMOVED entirely from specs, issue not merged -> STALE/CLOSE
iss = [issue(9, ["FR-GONE-001"], "WHATEVER")]
p = plan_for(reqs, iss)         # reqs has no FR-GONE-001
op = next((o for o in p["ops"] if o.get("req") == "FR-GONE-001"), None)
check("removed req + open issue -> STALE/CLOSE", op["action"] == analyze.STALE_CLOSE)

# requirement REMOVED entirely, issue merged -> REFACTOR
iss = [issue(10, ["FR-GONE-001"], "WHATEVER", state="CLOSED", reason="COMPLETED")]
p = plan_for(reqs, iss)
op = next((o for o in p["ops"] if o.get("req") == "FR-GONE-001"), None)
check("removed req + merged issue -> REFACTOR", op["action"] == analyze.REFACTOR)

# ── ADR supersede touching a merged issue -> REFACTOR ───────────────────────
r_adr = make_req("FR-CHK-002", governed_by=["ADR-0001"])
reqs_adr = {"FR-CHK-002": req_info(r_adr)}
fp_adr = compute_item_fingerprint(r_adr)
# requirement text UNCHANGED (stamped == current) but ADR superseded + merged
iss = [issue(11, ["FR-CHK-002"], fp_adr, state="CLOSED", reason="COMPLETED")]
p = plan_for(reqs_adr, iss, adr_status={"ADR-0001": "superseded"})
check("ADR superseded + merged issue (text unchanged) -> REFACTOR",
      op_for(p, "FR-CHK-002")["action"] == analyze.REFACTOR)

# control: same setup but ADR still accepted -> SKIP (no refactor)
p = plan_for(reqs_adr, iss, adr_status={"ADR-0001": "accepted"})
check("ADR accepted + merged + unchanged -> SKIP",
      op_for(p, "FR-CHK-002")["action"] == analyze.SKIP)

# ── malformed meta block -> blocking drift, gate BLOCKS ─────────────────────
bad_issue = issue(12, ["FR-CHK-001"], fp1)
bad_issue["body"] = "## Goal\nNo meta block here at all.\n"
p = plan_for(reqs, [bad_issue])
check("malformed meta block -> blocking drift", bool(p["blocking"]))

# a hand-edited string trace_req must FAIL CLOSED (blocking), never iterate its
# characters into bogus single-letter requirement keys.
str_meta, str_err = analyze.parse_meta(
    f"{analyze.META_OPEN}\n```yaml\ntrace_req: FR-CHK-001\n```\n{analyze.META_CLOSE}\n")
check("string trace_req -> parse_meta blocks (not a list)",
      str_meta is None and "not a list" in (str_err or ""))
str_issue = issue(13, ["FR-CHK-001"], fp1)
str_issue["body"] = str_issue["body"].replace("trace_req: [FR-CHK-001]",
                                              "trace_req: FR-CHK-001")
by_req_s, blocking_s = analyze.index_issues([str_issue])
check("string trace_req -> issue is blocking, not character-iterated into by_req",
      bool(blocking_s) and not any(len(k) == 1 for k in by_req_s))

# ── fan-out cap: more refactors than the cap -> truncate + tracking + BLOCK ──
many_reqs = {}
many_issues = []
for i in range(1, 6):                       # 5 changed+merged requirements
    rid = f"FR-CHK-{i:03d}"
    rec = make_req(rid)
    many_reqs[rid] = req_info(rec)
    many_issues.append(issue(100 + i, [rid], "STALEHASH",
                             state="CLOSED", reason="COMPLETED"))
p = plan_for(many_reqs, many_issues, max_refactors=2)
refactors = [o for o in p["ops"] if o["action"] == analyze.REFACTOR]
tracking = [o for o in p["ops"] if o["action"] == analyze.REFACTOR_TRACKING]
check("cap=2 -> exactly 2 REFACTOR ops", len(refactors) == 2)
check("cap overflow -> exactly 1 tracking op", len(tracking) == 1)
check("tracking op records the deferred count", tracking[0]["count"] == 3)
check("cap overflow -> gate BLOCKS", bool(p["blocking"]))

# under the cap -> no tracking, not blocking
p = plan_for(many_reqs, many_issues, max_refactors=10)
check("cap=10 over 5 refactors -> no tracking op",
      not any(o["action"] == analyze.REFACTOR_TRACKING for o in p["ops"]))
check("under cap -> not blocking", not p["blocking"])

# ── won't-do (CLOSED/NOT_PLANNED): always SKIP, respect the human decision ───
# active req whose fingerprint changed + a won't-do issue -> SKIP (not FLAG)
iss = [issue(20, ["FR-CHK-001"], "STALEHASH", state="CLOSED", reason="NOT_PLANNED")]
p = plan_for(reqs, iss)
check("changed active req + won't-do issue -> SKIP (not COMMENT-AND-FLAG)",
      op_for(p, "FR-CHK-001")["action"] == analyze.SKIP and not p["blocking"])
# superseded req + won't-do issue -> SKIP (not STALE/CLOSE)
iss = [issue(21, ["FR-CHK-001"], compute_item_fingerprint(r_sup),
             state="CLOSED", reason="NOT_PLANNED")]
p = plan_for(reqs_sup, iss)
check("superseded req + won't-do issue -> SKIP (not STALE/CLOSE)",
      op_for(p, "FR-CHK-001")["action"] == analyze.SKIP)
# removed req + won't-do issue -> SKIP (orphan loop, not STALE/CLOSE)
iss = [issue(22, ["FR-GONE-001"], "WHATEVER", state="CLOSED", reason="NOT_PLANNED")]
p = plan_for(reqs, iss)
op = next((o for o in p["ops"] if o.get("req") == "FR-GONE-001"), None)
check("removed req + won't-do issue -> SKIP (respect the human decision)",
      op and op["action"] == analyze.SKIP)

# ── the spec-read loaders, pinned to the real upstream fixtures (not injected) ─
adr = analyze.load_adr_status(UPSTREAM)
check("load_adr_status reads arch-data.yaml: ADR-0002 superseded, ADR-0001 accepted",
      adr.get("ADR-0002") == "superseded" and adr.get("ADR-0001") == "accepted")
up_reqs = analyze.load_requirements(UPSTREAM)
check("load_requirements reads the feature files end-to-end (FR-CHK-001 present)",
      "FR-CHK-001" in up_reqs and len(up_reqs) >= 4)
check("load_requirements computes a non-empty fingerprint per requirement",
      all(info["fingerprint"] for info in up_reqs.values()))

# ── a malformed requirement fails CLOSED as the documented exit-2, not a crash ─
with tempfile.TemporaryDirectory() as tmp:
    fdir = os.path.join(tmp, "features")
    os.makedirs(fdir)
    with open(os.path.join(fdir, "x.md"), "w", encoding="utf-8") as f:
        f.write("---\n"
                'meta: {slug: x, feature_version: "1.0"}\n'
                "requirements:\n"
                "  - id: FR-X-001\n"
                "    description: d\n"
                '    acceptance_criteria: ["WHEN x THE SYSTEM SHALL y."]\n'
                '    depends_on: ["FR-A-001", 5]\n'   # mixed str/int -> sorted() TypeError
                "    governed_by: []\n"
                "    status: active\n"
                "---\n\n# x\n")
    raised = None
    try:
        analyze.load_requirements(tmp)
    except ValueError:
        raised = "ValueError"
    except Exception as e:   # noqa: BLE001
        raised = type(e).__name__
    check("malformed requirement raises ValueError (-> clean exit 2), not a raw TypeError",
          raised == "ValueError")

# ── a non-dict `meta` block must not crash load_requirements (AttributeError) ──
with tempfile.TemporaryDirectory() as tmp:
    fdir = os.path.join(tmp, "features")
    os.makedirs(fdir)
    with open(os.path.join(fdir, "checkout.md"), "w", encoding="utf-8") as f:
        f.write("---\n"
                "meta: not-a-mapping\n"               # a scalar, not a dict
                "requirements:\n"
                "  - id: FR-CHK-001\n"
                "    description: d\n"
                '    acceptance_criteria: ["WHEN x THE SYSTEM SHALL y."]\n'
                "    depends_on: []\n"
                "    governed_by: []\n"
                "    status: active\n"
                "---\n\n# checkout\n")
    crashed = None
    try:
        out = analyze.load_requirements(tmp)
    except Exception as e:   # noqa: BLE001
        crashed = type(e).__name__
    check("non-dict meta -> no crash; slug falls back to the filename",
          crashed is None and out.get("FR-CHK-001", {}).get("feature") == "checkout")

print()
if failures:
    print(f"FAILURES: {failures}")
    sys.exit(1)
print("bounded reconcile planner behaves as expected")
sys.exit(0)
