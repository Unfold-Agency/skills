#!/usr/bin/env python3
"""No-network unit test for phase_milestones' pure mapping logic: title format,
ordinal parsing, the capability->phase inversion (active-only, latest-wins), and
the issue-phase rule (latest phase among an issue's traced capabilities, with a
spanned-phases flag).

  python scripts/tests/test_phase_milestones.py
Exit 0 = the mapping behaves as expected.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from phase_milestones import (  # noqa: E402
    milestone_title, parse_phase_ordinal, active_phases, build_maps,
    phase_for_trace)

failures = []


def check(name, cond):
    print(f"{'ok  ' if cond else 'FAIL'} {name}")
    if not cond:
        failures.append(name)


DOC = {
    "implementation_phases": [
        {"number": 1, "name": "Foundation", "summary": "  data and  auth ",
         "capabilities": ["ENT-001", "STM-001", "ADR-001"], "status": "active"},
        {"number": 2, "name": "Checkout",
         "capabilities": ["WF-001", "INTG-001", "TNF-001"], "status": "active"},
        {"number": 3, "name": "Reporting (cut)",
         "capabilities": ["ENT-099"], "status": "deferred"},
    ]
}

# ── title + ordinal ───────────────────────────────────────────────────────
check("title formats with name", milestone_title(1, "Foundation") == "Phase 1: Foundation")
check("title collapses whitespace", milestone_title(2, "  Core  Flow ") == "Phase 2: Core Flow")
check("title without a name", milestone_title(5, "") == "Phase 5")
check("ordinal of 'Phase 1: Foundation'", parse_phase_ordinal("Phase 1: Foundation") == 1)
check("ordinal of 'Phase 12: X'", parse_phase_ordinal("Phase 12: X") == 12)
check("ordinal of a non-phase title", parse_phase_ordinal("Backlog") is None)
check("ordinal of empty", parse_phase_ordinal("") is None)

# ── active_phases excludes non-active ──────────────────────────────────────
ap = active_phases(DOC)
check("active_phases drops the deferred phase", [p["number"] for p in ap] == [1, 2])

# ── build_maps ─────────────────────────────────────────────────────────────
cap_to_phase, phase_meta = build_maps(DOC)
check("cap in phase 1", cap_to_phase["ENT-001"] == 1)
check("cap in phase 2", cap_to_phase["INTG-001"] == 2)
check("deferred phase's cap is not mapped", "ENT-099" not in cap_to_phase)
check("phase_meta title", phase_meta[1]["title"] == "Phase 1: Foundation")
check("phase_meta summary collapsed", phase_meta[1]["summary"] == "data and auth")
check("no phase_meta for deferred phase", 3 not in phase_meta)

# latest-wins when a cap is (wrongly) double-listed across active phases
DOUBLE = {"implementation_phases": [
    {"number": 1, "name": "A", "capabilities": ["WF-001"], "status": "active"},
    {"number": 2, "name": "B", "capabilities": ["WF-001"], "status": "active"},
]}
c2p, _ = build_maps(DOUBLE)
check("double-listed cap resolves to the latest phase", c2p["WF-001"] == 2)

# ── phase_for_trace ────────────────────────────────────────────────────────
n, spanned, mapped = phase_for_trace(["ENT-001"], cap_to_phase)
check("single cap -> its phase", n == 1 and spanned is False and mapped == ["ENT-001"])

n, spanned, _ = phase_for_trace(["WF-001", "INTG-001"], cap_to_phase)
check("two caps same phase -> that phase, not spanned", n == 2 and spanned is False)

n, spanned, _ = phase_for_trace(["ENT-001", "WF-001"], cap_to_phase)
check("caps across phases -> latest phase, spanned", n == 2 and spanned is True)

n, spanned, mapped = phase_for_trace(["ZZ-001"], cap_to_phase)
check("unknown cap -> no phase", n is None and spanned is False and mapped == [])

n, _, _ = phase_for_trace([], cap_to_phase)
check("empty trace -> no phase", n is None)

# ── no plan at all -> empty maps, no phase ────────────────────────────────
c2p_empty, meta_empty = build_maps({})
check("no plan -> empty maps", c2p_empty == {} and meta_empty == {})
check("no plan -> phase_for_trace None",
      phase_for_trace(["ENT-001"], c2p_empty)[0] is None)

print()
if failures:
    print(f"FAILURES: {failures}")
    sys.exit(1)
print("phase_milestones mapping behaves as expected")
sys.exit(0)
