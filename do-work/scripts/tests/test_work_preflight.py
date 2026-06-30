#!/usr/bin/env python3
"""No-network unit test for work_preflight's pure pieces -- the specs-present gate,
the backlog gate, and the non-gating advisories (drift flags + an owed sync read
from the overview feature_index against each issue's stamped source_version).

  python scripts/tests/test_work_preflight.py
Exit 0 = all behave as expected.
"""
import os
import shutil
import sys
import tempfile

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from work_preflight import (  # noqa: E402
    check_specs, check_backlog, scan_advisories)

failures = []


def check(name, cond):
    print(f"{'ok  ' if cond else 'FAIL'} {name}")
    if not cond:
        failures.append(name)


def make_specs(feature_versions):
    """A throwaway docs/specs with an overview feature_index and one data file per
    feature. feature_versions is {slug: version}."""
    root = tempfile.mkdtemp(prefix="dowork-specs-")
    os.makedirs(os.path.join(root, "features"))
    overview = {"meta": {"project_version": "0.1", "mode": "full", "status": "draft",
                         "fingerprint": "x"},
                "feature_index": [{"slug": s, "prefix": s[:3].upper(),
                                   "feature_version": v, "status": "active"}
                                  for s, v in feature_versions.items()]}
    with open(os.path.join(root, "overview-data.yaml"), "w") as f:
        yaml.safe_dump(overview, f, sort_keys=False)
    for s in feature_versions:
        with open(os.path.join(root, "features", f"{s}-data.yaml"), "w") as f:
            yaml.safe_dump({"meta": {"slug": s}, "requirements": []}, f, sort_keys=False)
    return root


def meta_body(feature=None, source_version=None):
    """A managed issue body carrying feature + source_version in the meta block --
    where do-work reads the make-spec content stamp from."""
    if feature is None:
        return ""
    return ("## Goal\n\n"
            "<!-- make-issues:meta -->\n"
            "```yaml\n"
            "trace_req: [FR-CHK-001]\n"
            "trace_adr: [ADR-0001]\n"
            f"feature: {feature}\n"
            f'source_version: "{source_version}"\n'
            "autonomy: afk\n"
            "```\n"
            "<!-- /make-issues:meta -->\n")


def issue(number, state, labels, reason=None, feature=None, source_version=None):
    return {"number": number, "state": state, "stateReason": reason,
            "labels": [{"name": n} for n in labels],
            "body": meta_body(feature, source_version)}


# ── specs-present gate ──────────────────────────────────────────────────
root = make_specs({"checkout": "v1"})
r = check_specs(root)
check("overview + 1 feature -> specs ok", r["ok"] is True and not r.get("fatal"))
shutil.rmtree(root)

empty = tempfile.mkdtemp(prefix="dowork-specs-")
os.makedirs(os.path.join(empty, "features"))
with open(os.path.join(empty, "overview-data.yaml"), "w") as f:
    yaml.safe_dump({"meta": {}, "feature_index": []}, f)
r = check_specs(empty)
check("overview but no features -> not ok", r["ok"] is False and not r.get("fatal"))
shutil.rmtree(empty)

missing = tempfile.mkdtemp(prefix="dowork-specs-")
r = check_specs(missing)
check("no overview-data.yaml -> fatal (drives exit 2)", r.get("fatal") is True)
shutil.rmtree(missing)

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
# Live: checkout is at v2. An issue stamped v1 is stale (a sync is owed).
root = make_specs({"checkout": "v2"})
issues = [
    issue(1, "OPEN", ["make-issues", "afk", "spec-drift"], feature="checkout", source_version="v2"),
    issue(2, "OPEN", ["make-issues", "afk"], feature="checkout", source_version="v1"),  # stale
    issue(3, "CLOSED", ["make-issues"], "COMPLETED", feature="checkout", source_version="v1"),  # closed: ignored
]
adv = scan_advisories(issues, root, have_labels={"status:doing"})
check("drift scan flags only the open spec-drift issue",
      [f["number"] for f in adv["flagged"]] == [1] and adv["flagged"][0]["flags"] == ["spec-drift"])
check("sync owed when an open issue's source_version lags the live feature_version",
      adv["sync_owed"] is True and [s["number"] for s in adv["stale_syncs"]] == [2])
check("missing do-work labels computed (escalated, needs-human-review)",
      adv["missing_labels"] == ["escalated", "needs-human-review"])
shutil.rmtree(root)

# Live v2, the only open issue is stamped v2 -> nothing owed.
root = make_specs({"checkout": "v2"})
adv2 = scan_advisories(
    [issue(2, "OPEN", ["make-issues", "afk"], feature="checkout", source_version="v2")],
    root, have_labels={"status:doing", "escalated", "needs-human-review"})
check("no sync owed when the stamp matches the live feature_version", adv2["sync_owed"] is False)
check("no missing labels when all present", adv2["missing_labels"] == [])
shutil.rmtree(root)

# A body with no meta block contributes no stamp -- and with no stamp, staleness
# cannot be asserted (we do not invent drift from nothing).
root = make_specs({"checkout": "v2"})
adv3 = scan_advisories([issue(1, "OPEN", ["make-issues", "afk"])], root,
                       have_labels={"status:doing", "escalated", "needs-human-review"})
check("missing meta block -> no stamp, sync not asserted owed",
      adv3["sync_owed"] is False and adv3["stale_syncs"] == [])
shutil.rmtree(root)

print()
if failures:
    print(f"FAILURES: {failures}")
    sys.exit(1)
print("work_preflight gates and advisories behave as expected")
sys.exit(0)
