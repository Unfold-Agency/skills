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


def plan_for(reqs_map, issues, adr_status=None, max_refactors=10, scope=None,
             promote=None):
    by_req, blocking_meta, amendments = analyze.index_issues(issues)
    return analyze.build_plan(reqs_map, by_req, adr_status or {}, blocking_meta,
                              max_refactors, amendments=amendments,
                              scope=scope, promote=promote)


def amendment_body(feature, trace_req=None, autonomy="hitl"):
    """A well-formed amendment issue body (provenance: amendment, feature anchor,
    empty fingerprint)."""
    reqs = "[" + ", ".join(trace_req or []) + "]"
    return (
        "## Goal\nAn on-demand add.\n\n"
        f"{analyze.META_OPEN}\n```yaml\n"
        "provenance: amendment\n"
        f"trace_req: {reqs}\n"
        "trace_adr: []\n"
        f"feature: {feature}\n"
        'source_version: ""\n'
        f"autonomy: {autonomy}\n"
        'fingerprint: ""\n'
        f"```\n{analyze.META_CLOSE}\n"
    )


def amendment_issue(number, feature, trace_req=None, state="OPEN", reason=None):
    return {
        "number": number, "title": f"amendment {number}", "state": state,
        "stateReason": reason, "labels": [{"name": "amendment"}],
        "assignees": [], "closedByPullRequestsReferences": [],
        "milestone": None, "updatedAt": "2026-06-01T00:00:00Z",
        "url": f"https://example/{number}",
        "body": amendment_body(feature, trace_req),
    }


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
by_req_s, blocking_s, _amd_s = analyze.index_issues([str_issue])
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

# ── SCOPE: writes are bounded, detection stays global ───────────────────────
# Two features, each with one changed (not-started) requirement. A scoped run on
# 'checkout' must UPDATE only checkout's issue and report cart's drift as
# out-of-scope -- never act on it.
r_chk = make_req("FR-CHK-001")
r_crt = make_req("FR-CART-001")
reqs_two = {"FR-CHK-001": req_info(r_chk, feature="checkout"),
            "FR-CART-001": req_info(r_crt, feature="cart")}
iss_two = [issue(30, ["FR-CHK-001"], "STALEHASH"),
           issue(31, ["FR-CART-001"], "STALEHASH")]

p_full = plan_for(reqs_two, iss_two)
check("unscoped run acts on both features",
      {o["action"] for o in p_full["ops"] if o["action"] == analyze.UPDATE} == {analyze.UPDATE}
      and len([o for o in p_full["ops"] if o["action"] == analyze.UPDATE]) == 2)

scope_chk = analyze.parse_scope("checkout")
p_scoped = plan_for(reqs_two, iss_two, scope=scope_chk)
upd = [o for o in p_scoped["ops"] if o["action"] == analyze.UPDATE]
check("scoped run UPDATEs only the in-scope feature's issue",
      len(upd) == 1 and op_for(p_scoped, "FR-CHK-001")["action"] == analyze.UPDATE)
check("scoped run reports the out-of-scope drift (not acted on)",
      any(o.get("req") == "FR-CART-001" for o in p_scoped["out_of_scope"]))
check("scoped run does not act on the out-of-scope feature",
      op_for(p_scoped, "FR-CART-001") is None)
check("scoped run with only report-only drift does not block",
      not p_scoped["blocking"])

# scope by requirement id works too
p_by_id = plan_for(reqs_two, iss_two, scope=analyze.parse_scope("FR-CART-001"))
check("scope by requirement id acts on just that requirement",
      op_for(p_by_id, "FR-CART-001")["action"] == analyze.UPDATE
      and op_for(p_by_id, "FR-CHK-001") is None)

# ── ORPHAN-CLOSE SCOPE GUARD: a removed req in an UNSELECTED feature is detected
#    but never mass-closed by a scoped run. This is the mass-close hazard, fenced.
# checkout req exists; an orphan issue traces a removed cart requirement.
orphan_iss = issue(40, ["FR-CART-999"], "GONEHASH")
orphan_iss["body"] = orphan_iss["body"].replace("feature: checkout",
                                                "feature: cart")
reqs_chk_only = {"FR-CHK-001": req_info(r_chk, feature="checkout")}
p_guard = plan_for(reqs_chk_only, [orphan_iss], scope=analyze.parse_scope("checkout"))
check("orphan in an out-of-scope feature is NOT closed by a scoped run",
      not any(o["action"] == analyze.STALE_CLOSE for o in p_guard["ops"]))
check("orphan in an out-of-scope feature is reported as out-of-scope drift",
      any(o.get("req") == "FR-CART-999" for o in p_guard["out_of_scope"]))
# but a full run (or a run scoped to cart) DOES close it
p_close = plan_for(reqs_chk_only, [orphan_iss])
op = next((o for o in p_close["ops"] if o.get("req") == "FR-CART-999"), None)
check("orphan IS closed by a full run (detection global, action in scope)",
      op and op["action"] == analyze.STALE_CLOSE)

# ── AMENDMENTS: provenance-exempt from orphan/stale/refactor ─────────────────
amd = amendment_issue(50, "checkout")
by_req_a, blk_a, amd_list = analyze.index_issues([amd])
check("amendment is indexed as an amendment, not a spec req match",
      len(amd_list) == 1 and not by_req_a and not blk_a)

# a valid-anchor amendment is left untouched (SKIP), never closed
p_amd = plan_for(reqs_chk_only, [amd])
amd_ops = [o for o in p_amd["ops"] if o.get("issue") == 50]
check("amendment with a valid anchor -> SKIP (left untouched)",
      len(amd_ops) == 1 and amd_ops[0]["action"] == analyze.SKIP)
check("amendment is never STALE/CLOSE or REFACTOR",
      not any(o.get("issue") == 50 and o["action"] in
              (analyze.STALE_CLOSE, analyze.REFACTOR) for o in p_amd["ops"]))
check("amendment does not block the gate", not p_amd["blocking"])

# an amendment whose feature anchor vanished -> FLAG (never auto-close)
amd_lost = amendment_issue(51, "ghost-feature")
p_lost = plan_for(reqs_chk_only, [amd_lost])
op = next((o for o in p_lost["ops"] if o.get("issue") == 51), None)
check("amendment with a lost anchor -> COMMENT-AND-FLAG (orphaned), not closed",
      op and op["action"] == analyze.COMMENT_AND_FLAG and op.get("flag") == "orphaned")

# an amendment with no feature anchor at all -> blocking drift (malformed)
amd_bad = amendment_issue(52, "checkout")
amd_bad["body"] = amd_bad["body"].replace("feature: checkout", "feature: ''")
_by, blk_bad, _amd = analyze.index_issues([amd_bad])
check("amendment with no feature anchor -> blocking drift", bool(blk_bad))

# absent provenance defaults to spec (backward compat: existing issues unaffected)
legacy = issue(53, ["FR-CHK-001"], fp1)   # no provenance field in issue_body()
meta_legacy, err_legacy = analyze.parse_meta(legacy["body"])
check("absent provenance defaults to spec",
      err_legacy is None and meta_legacy.get("provenance") == "spec")

# ── PROMOTE: operator-confirmed amendment -> spec issue ─────────────────────
amd_promo = amendment_issue(60, "checkout")
# promote #60 to a real active requirement
p_promo = plan_for(reqs_chk_only, [amd_promo], promote={60: "FR-CHK-001"})
op = next((o for o in p_promo["ops"] if o.get("issue") == 60), None)
check("promote to an active requirement -> PROMOTE op",
      op and op["action"] == analyze.PROMOTE and op["req"] == "FR-CHK-001")
check("PROMOTE stamps the target requirement's fingerprint",
      op["fingerprint"] == compute_item_fingerprint(r_chk))
check("valid promote does not block", not p_promo["blocking"])

# promote to a non-existent / non-active requirement -> blocking drift
p_promo_bad = plan_for(reqs_chk_only, [amd_promo], promote={60: "FR-NOPE-001"})
check("promote to a non-active requirement -> blocking drift",
      any(b.get("kind") == "promote_target_invalid" for b in p_promo_bad["blocking"]))

# promote targeting an issue that is NOT an amendment must never be silently
# dropped: a spec issue, or a number not in the set, blocks the gate.
spec_iss_60 = issue(60, ["FR-CHK-001"], compute_item_fingerprint(r_chk))
p_promo_spec = plan_for(reqs_chk_only, [spec_iss_60], promote={60: "FR-CHK-001"})
check("promote targeting a spec issue -> blocking (promote_issue_invalid)",
      any(b.get("kind") == "promote_issue_invalid" for b in p_promo_spec["blocking"]))
p_promo_missing = plan_for(reqs_chk_only, [amd_promo], promote={999: "FR-CHK-001"})
check("promote targeting a nonexistent issue -> blocking (promote_issue_invalid)",
      any(b.get("kind") == "promote_issue_invalid" for b in p_promo_missing["blocking"]))

# ── parse_scope / parse_promote unit behavior ───────────────────────────────
check("parse_scope('') -> None (full run)", analyze.parse_scope("") is None)
sc = analyze.parse_scope("checkout, FR-CART-001 ,cart")
check("parse_scope splits features vs requirement ids",
      sc["features"] == {"checkout", "cart"} and sc["reqs"] == {"FR-CART-001"})
check("parse_promote parses ISSUE=REQ pairs",
      analyze.parse_promote(["42=FR-CHK-007"]) == {42: "FR-CHK-007"})
_raised = None
try:
    analyze.parse_promote(["not-a-pair"])
except ValueError:
    _raised = "ValueError"
check("parse_promote rejects a malformed pair (-> exit 2)", _raised == "ValueError")

print()
if failures:
    print(f"FAILURES: {failures}")
    sys.exit(1)
print("bounded reconcile planner behaves as expected")
sys.exit(0)
