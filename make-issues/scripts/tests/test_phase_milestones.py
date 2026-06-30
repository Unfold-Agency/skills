#!/usr/bin/env python3
"""No-network unit test for phase_milestones' pure mapping logic against the new
OPTIONAL overview `phasing` model: title format, ordinal parsing, the
feature->phase inversion (active-only, latest-wins), the feature-phase lookup,
and -- crucially -- that an overview with NO `phasing` plan yields empty maps and
no phase (milestones are skipped entirely, not an error).

  python scripts/tests/test_phase_milestones.py
Exit 0 = the mapping behaves as expected.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from phase_milestones import (  # noqa: E402
    milestone_title, parse_phase_ordinal, active_phases, build_maps,
    phase_for_feature)

failures = []


def check(name, cond):
    print(f"{'ok  ' if cond else 'FAIL'} {name}")
    if not cond:
        failures.append(name)


# An overview WITH an optional phasing plan (feature slugs, not capability ids).
DOC = {
    "phasing": [
        {"phase": 1, "name": "Foundation", "summary": "  data and  auth ",
         "features": ["accounts", "cart"], "status": "active"},
        {"phase": 2, "name": "Checkout",
         "features": ["checkout", "payments"], "status": "active"},
        {"phase": 3, "name": "Reporting (cut)",
         "features": ["reporting"], "status": "deferred"},
    ]
}

# ── title + ordinal ───────────────────────────────────────────────────────
check("title formats with name", milestone_title(1, "Foundation") == "Phase 1: Foundation")
check("title collapses whitespace", milestone_title(2, "  Core  Flow ") == "Phase 2: Core Flow")
check("title without a name", milestone_title(5, "") == "Phase 5")
check("ordinal of 'Phase 1: Foundation'", parse_phase_ordinal("Phase 1: Foundation") == 1)
check("ordinal of 'Phase 12: X'", parse_phase_ordinal("Phase 12: X") == 12)
check("ordinal of a non-phase title", parse_phase_ordinal("Backlog") is None)

# ── active_phases excludes non-active ──────────────────────────────────────
ap = active_phases(DOC)
check("active_phases drops the deferred phase", [p["phase"] for p in ap] == [1, 2])

# ── build_maps over feature slugs ──────────────────────────────────────────
feature_to_phase, phase_meta = build_maps(DOC)
check("feature in phase 1", feature_to_phase["accounts"] == 1)
check("feature in phase 2", feature_to_phase["checkout"] == 2)
check("deferred phase's feature is not mapped", "reporting" not in feature_to_phase)
check("phase_meta title", phase_meta[1]["title"] == "Phase 1: Foundation")
check("phase_meta summary collapsed", phase_meta[1]["summary"] == "data and auth")
check("no phase_meta for deferred phase", 3 not in phase_meta)

# latest-wins when a feature is (wrongly) double-listed across active phases
DOUBLE = {"phasing": [
    {"phase": 1, "name": "A", "features": ["checkout"], "status": "active"},
    {"phase": 2, "name": "B", "features": ["checkout"], "status": "active"},
]}
f2p, _ = build_maps(DOUBLE)
check("double-listed feature resolves to the latest phase", f2p["checkout"] == 2)

# a hand-typed single slug (features: checkout, not a list) is one feature, never
# iterated character-by-character into c/h/e/c/k/o/u/t.
STR_FEATS = {"phasing": [
    {"phase": 1, "name": "A", "features": "checkout", "status": "active"},
]}
f2p_str, _ = build_maps(STR_FEATS)
check("string features coerces to one slug, not its characters",
      f2p_str == {"checkout": 1})

# ── phase_for_feature ──────────────────────────────────────────────────────
n, _ = phase_for_feature("accounts", feature_to_phase)
check("known feature -> its phase", n == 1)
n, _ = phase_for_feature("checkout", feature_to_phase)
check("known feature in phase 2", n == 2)
n, _ = phase_for_feature("reporting", feature_to_phase)
check("deferred-phase feature -> no phase", n is None)
n, _ = phase_for_feature("unknown", feature_to_phase)
check("unknown feature -> no phase", n is None)

# ── no plan at all -> empty maps, no phase (phasing is OPTIONAL) ────────────
f2p_empty, meta_empty = build_maps({})
check("no plan -> empty maps", f2p_empty == {} and meta_empty == {})
check("no plan -> phase_for_feature None",
      phase_for_feature("accounts", f2p_empty)[0] is None)
check("no plan -> active_phases empty", active_phases({}) == [])

print()
if failures:
    print(f"FAILURES: {failures}")
    sys.exit(1)
print("phase_milestones mapping behaves as expected")
sys.exit(0)
