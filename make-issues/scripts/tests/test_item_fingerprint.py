#!/usr/bin/env python3
"""The C1 keystone test. The per-requirement fingerprint must be STABLE under
advisory/cosmetic edits and CHANGE under every contract (IN) edit -- the property
that keeps issues from churning on rewording/re-prioritising while still catching
real spec drift.

IN  (must flip the hash):  id, kind, description, acceptance_criteria (and its
                           ORDER), governed_by, depends_on, interface.
OUT (must NOT flip):       priority, architecture_hints, related_files, notes,
                           name, status.

  python scripts/tests/test_item_fingerprint.py
Exit 0 = all properties held.
"""
import copy
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from item_fingerprint import compute_item_fingerprint, project_in_fields  # noqa: E402

failures = []


def check(name, cond):
    print(f"{'ok  ' if cond else 'FAIL'} {name}")
    if not cond:
        failures.append(name)


REQ = {
    "id": "FR-CHK-001",
    "name": "Validate the cart before checkout",
    "kind": "functional",
    "description": "The system validates every cart line item against live "
                   "inventory before allowing checkout to proceed.",
    "acceptance_criteria": [
        "WHEN a line item is out of stock THE SYSTEM SHALL block checkout.",
        "WHEN all items are in stock THE SYSTEM SHALL proceed to payment.",
    ],
    "governed_by": ["ADR-0002", "ADR-0001"],
    "depends_on": ["FR-CART-001", "FR-CART-002"],
    "interface": "validateCart(cartId): { ok: bool, blocked: LineItem[] }",
    # OUT fields below -- none of these may affect the hash:
    "priority": "must",
    "architecture_hints": "Reuse the inventory client from the cart module.",
    "related_files": ["src/checkout/validate.ts"],
    "notes": "Discussed with platform team 2026-06-01.",
    "status": "active",
}


def fp(rec):
    return compute_item_fingerprint(copy.deepcopy(rec))


base = fp(REQ)

# ── OUT fields: the hash must NOT change ─────────────────────────────────────
m = copy.deepcopy(REQ); m["priority"] = "could"
check("change priority -> stable (OUT)", fp(m) == base)
m = copy.deepcopy(REQ); m["architecture_hints"] = "Totally different approach."
check("change architecture_hints -> stable (OUT)", fp(m) == base)
m = copy.deepcopy(REQ); m["related_files"] = ["src/x.ts", "src/y.ts"]
check("change related_files -> stable (OUT)", fp(m) == base)
m = copy.deepcopy(REQ); m["notes"] = "New note entirely."
check("change notes -> stable (OUT)", fp(m) == base)
m = copy.deepcopy(REQ); m["name"] = "A completely reworded name"
check("change name -> stable (cosmetic)", fp(m) == base)
m = copy.deepcopy(REQ); m["status"] = "deferred"
check("change status -> stable (lifecycle, not content)", fp(m) == base)
m = copy.deepcopy(REQ); m["governed_by"] = ["ADR-0001", "ADR-0002"]
check("reorder governed_by -> stable (set)", fp(m) == base)
m = copy.deepcopy(REQ); m["depends_on"] = ["FR-CART-002", "FR-CART-001"]
check("reorder depends_on -> stable (set)", fp(m) == base)
m = copy.deepcopy(REQ)
m["description"] = "  The   system validates every cart line item against " \
                   "live inventory before allowing checkout to proceed.  "
check("re-whitespace description -> stable (normalized)", fp(m) == base)

# ── IN fields: the hash MUST change ──────────────────────────────────────────
m = copy.deepcopy(REQ); m["id"] = "FR-CHK-099"
check("change id -> changes (IN)", fp(m) != base)
m = copy.deepcopy(REQ); m["kind"] = "integration"
check("change kind -> changes (IN)", fp(m) != base)
m = copy.deepcopy(REQ); m["description"] = "A materially different requirement."
check("change description -> changes (IN)", fp(m) != base)
m = copy.deepcopy(REQ)
m["acceptance_criteria"] = m["acceptance_criteria"] + \
    ["WHEN inventory is unknown THE SYSTEM SHALL fail closed."]
check("add an acceptance criterion -> changes (IN)", fp(m) != base)
m = copy.deepcopy(REQ)
m["acceptance_criteria"][0] = "WHEN a line item is out of stock THE SYSTEM " \
                              "SHALL warn but allow checkout."
check("edit an acceptance criterion -> changes (IN)", fp(m) != base)
m = copy.deepcopy(REQ)
m["acceptance_criteria"] = list(reversed(REQ["acceptance_criteria"]))
check("REORDER acceptance_criteria -> changes (order is contract)", fp(m) != base)
m = copy.deepcopy(REQ); m["governed_by"] = ["ADR-0001"]
check("drop a governing ADR -> changes (IN)", fp(m) != base)
m = copy.deepcopy(REQ); m["governed_by"] = REQ["governed_by"] + ["ADR-0009"]
check("add a governing ADR -> changes (IN)", fp(m) != base)
m = copy.deepcopy(REQ); m["depends_on"] = ["FR-CART-001"]
check("drop a dependency -> changes (IN)", fp(m) != base)
m = copy.deepcopy(REQ); m["interface"] = "validateCart(cartId): boolean"
check("change interface -> changes (IN)", fp(m) != base)

# ── projection allow-list: OUT keys are not even present in the projection ───
proj = project_in_fields(REQ)
for out_key in ("priority", "architecture_hints", "related_files", "notes",
                "name", "status"):
    check(f"projection excludes {out_key}", out_key not in proj)
for in_key in ("id", "kind", "description", "acceptance_criteria",
               "governed_by", "depends_on", "interface"):
    check(f"projection includes {in_key}", in_key in proj)

print()
if failures:
    print(f"FAILURES: {failures}")
    sys.exit(1)
print("all C1 fingerprint properties held")
sys.exit(0)
