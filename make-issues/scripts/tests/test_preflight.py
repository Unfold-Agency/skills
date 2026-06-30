#!/usr/bin/env python3
"""No-network unit test for the FAIL-CLOSED spec-integrity fingerprint gate --
the one piece of preflight that is pure YAML and must be right regardless of
gh/auth/repo state. It passes a clean spec set and FAILS when any file's stored
meta.fingerprint != a recompute over its CONTRACT content (e.g. an acceptance
criterion mutated without re-stamping).

  python scripts/tests/test_preflight.py
Exit 0 = the gate accepts a clean fixture and rejects every drift.
"""
import os
import shutil
import sys
import tempfile

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from gh_preflight import (  # noqa: E402
    check_spec_integrity, compute_fingerprint, SPEC_OUT_KEYS, ARCH_OUT_KEYS)

HERE = os.path.dirname(os.path.abspath(__file__))
failures = []


def check(name, cond):
    print(f"{'ok  ' if cond else 'FAIL'} {name}")
    if not cond:
        failures.append(name)


def stamped(doc, out_keys=SPEC_OUT_KEYS):
    """Return a copy of doc with meta.fingerprint set to its correct recompute.
    Arch files use ARCH_OUT_KEYS (the gate picks the same set per file), so the
    stamp and the gate's recompute agree -- just as make-spec/make-arch and the
    gate must agree on a real spec."""
    doc = dict(doc)
    doc.setdefault("meta", {})
    doc["meta"] = dict(doc["meta"])
    doc["meta"]["fingerprint"] = compute_fingerprint(doc, out_keys)
    return doc


def _write_md(path, doc):
    """Write a single-file spec: doc as YAML frontmatter + a stub body."""
    with open(path, "w") as f:
        f.write("---\n" + yaml.safe_dump(doc, sort_keys=False) + "---\n\n# fixture\n")


def write_specs(root, overview, features, arch=None):
    """Lay out a docs/specs tree. Each arg is a (already-stamped) doc. Specs are
    single .md files (contract in frontmatter); arch-data.yaml is plain YAML."""
    os.makedirs(os.path.join(root, "features"), exist_ok=True)
    _write_md(os.path.join(root, "overview.md"), overview)
    for slug, doc in features.items():
        _write_md(os.path.join(root, "features", f"{slug}.md"), doc)
    if arch is not None:
        with open(os.path.join(root, "arch-data.yaml"), "w") as f:
            yaml.safe_dump(arch, f, sort_keys=False)


OVERVIEW = {
    "meta": {"project_version": "1.0", "mode": "shape", "status": "approved"},
    "goals": [{"id": "G-001", "text": "Ship checkout"}],
    "scope": ["checkout"], "non_goals": ["returns"],
    "feature_index": [
        {"slug": "checkout", "prefix": "CHK", "title": "Checkout",
         "feature_version": "1.0", "status": "active", "appetite": "2w"},
    ],
}
CHECKOUT = {
    "meta": {"slug": "checkout", "prefix": "CHK", "status": "active",
             "feature_version": "1.0"},
    "requirements": [
        {"id": "FR-CHK-001", "name": "Validate cart", "kind": "functional",
         "description": "Validate the cart before checkout.",
         "acceptance_criteria": ["WHEN out of stock THE SYSTEM SHALL block."],
         "governed_by": ["ADR-0001"], "depends_on": [],
         "interface": "validateCart(id)", "priority": "must",
         "architecture_hints": "reuse client", "related_files": [],
         "notes": "n/a", "status": "active"},
    ],
}
ARCH = {
    "meta": {"project_version": "1.0", "status": "accepted"},
    "decisions": [
        {"id": "ADR-0001", "title": "Use REST", "status": "accepted",
         "scope": "checkout", "superseded_by": None, "confidence": "high"},
    ],
}


def fresh_tree():
    root = tempfile.mkdtemp(prefix="mkissues-specs-")
    write_specs(root, stamped(OVERVIEW),
                {"checkout": stamped(CHECKOUT)}, stamped(ARCH, ARCH_OUT_KEYS))
    return root


# ── clean tree passes ────────────────────────────────────────────────────────
root = fresh_tree()
r = check_spec_integrity(root)
check("clean spec set -> gate ok", r["ok"] is True and not r.get("fatal"))
shutil.rmtree(root)

# ── an OUT-only edit (priority) with the SAME stored fingerprint still passes ─
# (the recompute ignores priority, so the stored fingerprint is still correct).
root = tempfile.mkdtemp(prefix="mkissues-specs-")
chk = stamped(CHECKOUT)          # stamp first
chk["requirements"][0]["priority"] = "could"   # OUT edit AFTER stamping
write_specs(root, stamped(OVERVIEW), {"checkout": chk}, stamped(ARCH, ARCH_OUT_KEYS))
r = check_spec_integrity(root)
check("OUT-field edit without re-stamp -> still ok (OUT not in fingerprint)",
      r["ok"] is True)
shutil.rmtree(root)

# ── an acceptance-criterion mutated WITHOUT re-stamping -> FAIL (mid-edit) ────
root = tempfile.mkdtemp(prefix="mkissues-specs-")
chk = stamped(CHECKOUT)          # stamp the original AC
chk["requirements"][0]["acceptance_criteria"] = [
    "WHEN out of stock THE SYSTEM SHALL warn but allow."]   # IN edit, no re-stamp
write_specs(root, stamped(OVERVIEW), {"checkout": chk}, stamped(ARCH, ARCH_OUT_KEYS))
r = check_spec_integrity(root)
check("AC mutated without re-stamp -> gate FAILS", r["ok"] is False)
bad = [f["file"] for f in r["files"] if not f["ok"]]
check("the failing file is the checkout feature",
      any("checkout" in b for b in bad))
shutil.rmtree(root)

# ── a feature with NO stored fingerprint -> FAIL ─────────────────────────────
root = tempfile.mkdtemp(prefix="mkissues-specs-")
chk = dict(CHECKOUT)             # no meta.fingerprint at all
write_specs(root, stamped(OVERVIEW), {"checkout": chk}, stamped(ARCH, ARCH_OUT_KEYS))
r = check_spec_integrity(root)
check("feature with no stored fingerprint -> gate FAILS", r["ok"] is False)
shutil.rmtree(root)

# ── arch fingerprint drift -> FAIL ───────────────────────────────────────────
root = tempfile.mkdtemp(prefix="mkissues-specs-")
arch = stamped(ARCH, ARCH_OUT_KEYS)
arch["decisions"][0]["status"] = "superseded"   # IN edit, no re-stamp
write_specs(root, stamped(OVERVIEW), {"checkout": stamped(CHECKOUT)}, arch)
r = check_spec_integrity(root)
check("arch decision mutated without re-stamp -> gate FAILS", r["ok"] is False)
shutil.rmtree(root)

# ── arch is OPTIONAL: a tree with no arch-data.yaml still passes ─────────────
root = tempfile.mkdtemp(prefix="mkissues-specs-")
write_specs(root, stamped(OVERVIEW), {"checkout": stamped(CHECKOUT)}, arch=None)
r = check_spec_integrity(root)
check("no arch-data.yaml -> gate ok (arch optional)", r["ok"] is True)
shutil.rmtree(root)

# ── missing overview.md -> fatal (drives exit 2) ─────────────────────────────
root = tempfile.mkdtemp(prefix="mkissues-specs-")
os.makedirs(os.path.join(root, "features"))
r = check_spec_integrity(root)
check("missing overview.md -> fatal", r.get("fatal") is True)
shutil.rmtree(root)

# ── fingerprint is self-consistent: recompute after stamping == stored ───────
d = stamped(CHECKOUT)
check("compute_fingerprint is self-consistent (idempotent recompute)",
      d["meta"]["fingerprint"] == compute_fingerprint(d))

# ── GOLDEN cross-skill interop ───────────────────────────────────────────────
# specs/upstream/ holds an overview, two features, and an arch file stamped by
# the REAL make-spec / make-arch skills. The gate MUST accept them unmodified --
# this is the test that locks SPEC_OUT_KEYS / ARCH_OUT_KEYS and the dump to the
# upstream validators. If it fails, the gate has drifted and would reject
# legitimately-stamped specs (a self-stamped fixture cannot catch that).
UPSTREAM = os.path.join(HERE, "specs", "upstream")
if os.path.isdir(UPSTREAM):
    r = check_spec_integrity(UPSTREAM)
    check("gate accepts REAL make-spec/make-arch-stamped specs (interop locked)",
          r["ok"] is True and not r.get("fatal"))
else:
    check("golden upstream fixtures present", False)

print()
if failures:
    print(f"FAILURES: {failures}")
    sys.exit(1)
print("fail-closed fingerprint gate behaves as expected")
sys.exit(0)
