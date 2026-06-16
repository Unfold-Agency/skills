#!/usr/bin/env python3
"""Asserts the per-capability fingerprint is STABLE under cosmetic edits and
CHANGES under contract edits -- the property that keeps issues from churning on
rewording while still catching real design drift.

  python scripts/tests/test_item_fingerprint.py
Exit 0 = all properties held.
"""
import copy
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from item_fingerprint import compute_item_fingerprint  # noqa: E402

failures = []


def check(name, cond):
    print(f"{'ok  ' if cond else 'FAIL'} {name}")
    if not cond:
        failures.append(name)


ENT = {
    "id": "ENT-001", "name": "Order", "purpose": "An order placed by a customer.",
    "attributes": [
        {"name": "id", "type": "uuid", "required": True, "identifier": True, "note": "pk"},
        {"name": "total", "type": "money", "required": True, "identifier": False, "note": "x"},
    ],
    "relationships": [{"to": "ENT-002", "cardinality": "1:N", "note": "has lines"}],
    "satisfies": ["FR-002", "FR-001"], "needs_diagram": True,
    "open_items": [], "status": "active",
}
WF = {
    "id": "WF-001", "name": "Checkout", "trigger": "user submits cart",
    "steps": ["validate cart", "charge card", "create order"],
    "satisfies": ["FR-001"], "needs_diagram": True, "status": "active",
}
STM = {
    "id": "STM-001", "name": "Order lifecycle", "entity": "ENT-001",
    "states": ["new", "paid", "shipped"],
    "transitions": [
        {"from": "new", "to": "paid", "event": "pay"},
        {"from": "paid", "to": "shipped", "event": "ship"},
    ],
    "satisfies": ["FR-001"], "needs_diagram": True, "status": "active",
}


def fp(rec, kind):
    return compute_item_fingerprint(copy.deepcopy(rec), kind)


base_ent = fp(ENT, "ENT")

# --- cosmetic edits: hash must NOT change ---
m = copy.deepcopy(ENT); m["name"] = "Sales Order"
check("ENT reword name -> stable", fp(m, "ENT") == base_ent)
m = copy.deepcopy(ENT); m["purpose"] = "Totally different prose."
check("ENT reword purpose -> stable", fp(m, "ENT") == base_ent)
m = copy.deepcopy(ENT); m["attributes"][0]["note"] = "changed note"
check("ENT change attribute note -> stable", fp(m, "ENT") == base_ent)
m = copy.deepcopy(ENT); m["needs_diagram"] = False
check("ENT toggle needs_diagram -> stable", fp(m, "ENT") == base_ent)
m = copy.deepcopy(ENT); m["status"] = "deferred"
check("ENT change status -> stable (lifecycle, not content)", fp(m, "ENT") == base_ent)
m = copy.deepcopy(ENT); m["attributes"].reverse()
check("ENT reorder attributes -> stable (order-insensitive)", fp(m, "ENT") == base_ent)
m = copy.deepcopy(ENT); m["satisfies"] = ["FR-001", "FR-002"]
check("ENT reorder satisfies -> stable (set)", fp(m, "ENT") == base_ent)

# --- contract edits: hash MUST change ---
m = copy.deepcopy(ENT); m["attributes"][1]["type"] = "decimal"
check("ENT change attribute type -> changes", fp(m, "ENT") != base_ent)
m = copy.deepcopy(ENT); m["attributes"][1]["required"] = False
check("ENT change attribute required -> changes", fp(m, "ENT") != base_ent)
m = copy.deepcopy(ENT); m["satisfies"] = ["FR-001"]
check("ENT drop a satisfied requirement -> changes", fp(m, "ENT") != base_ent)
m = copy.deepcopy(ENT); m["relationships"][0]["cardinality"] = "1:1"
check("ENT change relationship cardinality -> changes", fp(m, "ENT") != base_ent)

# --- WF: steps are ORDER-SENSITIVE ---
base_wf = fp(WF, "WF")
m = copy.deepcopy(WF); m["name"] = "Purchase"
check("WF reword name -> stable", fp(m, "WF") == base_wf)
m = copy.deepcopy(WF); m["steps"] = ["charge card", "validate cart", "create order"]
check("WF reorder steps -> changes (order is meaning)", fp(m, "WF") != base_wf)
m = copy.deepcopy(WF); m["trigger"] = "user clicks pay"
check("WF change trigger -> changes", fp(m, "WF") != base_wf)

# --- STM: transitions are ORDER-INSENSITIVE (a set of edges) ---
base_stm = fp(STM, "STM")
m = copy.deepcopy(STM); m["transitions"].reverse()
check("STM reorder transitions -> stable (edge set)", fp(m, "STM") == base_stm)
m = copy.deepcopy(STM); m["transitions"][0]["event"] = "capture"
check("STM change a transition event -> changes", fp(m, "STM") != base_stm)
m = copy.deepcopy(STM); m["states"] = ["new", "paid"]
check("STM drop a state -> changes", fp(m, "STM") != base_stm)

print()
if failures:
    print(f"FAILURES: {failures}")
    sys.exit(1)
print("all fingerprint properties held")
sys.exit(0)
