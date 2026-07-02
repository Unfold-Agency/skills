#!/usr/bin/env python3
"""No-network unit test for the FAIL-CLOSED spec-integrity fingerprint gate --
the one piece of preflight that is pure YAML and must be right regardless of
gh/auth/repo state. It passes a clean spec set and FAILS when any file's stored
meta.fingerprint != a recompute over its CONTRACT content (e.g. an acceptance
criterion mutated without re-stamping).

  python scripts/tests/test_preflight.py
Exit 0 = the gate accepts a clean fixture and rejects every drift.
"""
import copy
import os
import shutil
import sys
import tempfile

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from gh_preflight import (  # noqa: E402
    check_spec_integrity, check_spec_set_present, parse_scope,
    compute_fingerprint, spec_files, SPEC_OUT_KEYS, ARCH_OUT_KEYS)

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
    """Lay out a docs/product tree. Each arg is a (already-stamped) doc. Specs are
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

# ── arch is OPTIONAL: a tree with no arch file at all still passes ───────────
root = tempfile.mkdtemp(prefix="mkissues-specs-")
write_specs(root, stamped(OVERVIEW), {"checkout": stamped(CHECKOUT)}, arch=None)
r = check_spec_integrity(root)
check("no arch file -> gate ok (arch optional)", r["ok"] is True)
shutil.rmtree(root)

# ── the arch entry dispatch: v2.0 architecture.md vs legacy arch-data.yaml ────
# A v2.0 architecture.md (NESTED meta.doc_type == spec-arch) is the arch entry.
root = tempfile.mkdtemp(prefix="mkissues-specs-")
write_specs(root, stamped(OVERVIEW), {"checkout": stamped(CHECKOUT)}, arch=None)
ARCH_V2 = {"meta": {"doc_type": "spec-arch", "schema_version": "2.0"},
           "context": "a storefront", "components": [], "integrations": []}
_write_md(os.path.join(root, "architecture.md"), stamped(ARCH_V2, ARCH_OUT_KEYS))
check("v2.0 architecture.md becomes the arch entry",
      dict(spec_files(root)).get("arch", "").endswith("architecture.md"))
r = check_spec_integrity(root)
check("stamped v2.0 architecture.md passes the gate", r["ok"] is True)
shutil.rmtree(root)

# A LEGACY architecture.md (FLAT doc_type, no meta -- narrative only) must NOT
# be mistaken for v2.0; the arch entry stays the arch-data.yaml beside it.
root = tempfile.mkdtemp(prefix="mkissues-specs-")
write_specs(root, stamped(OVERVIEW), {"checkout": stamped(CHECKOUT)},
            stamped(ARCH, ARCH_OUT_KEYS))
with open(os.path.join(root, "architecture.md"), "w") as f:
    f.write("---\ndoc_type: spec-arch\ndata_file: arch-data.yaml\n---\n\n# Arch\n")
check("legacy flat architecture.md is not v2.0 -> arch entry is arch-data.yaml",
      dict(spec_files(root)).get("arch", "").endswith("arch-data.yaml"))
r = check_spec_integrity(root)
check("legacy tree with a flat architecture.md still passes", r["ok"] is True)
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
# specs/upstream/ holds an overview, two features, and a LEGACY arch-data.yaml
# stamped by the REAL make-spec / make-arch skills; specs/upstream-v2/ holds the
# same specs with the v2.0 arch layer (architecture.md frontmatter + decisions/
# ADR-*.md, stamped by the real make-arch stamp_fingerprint.py). The gate MUST
# accept both unmodified -- these are the tests that lock SPEC_OUT_KEYS /
# ARCH_OUT_KEYS and the dump to the upstream validators. If one fails, the gate
# has drifted and would reject legitimately-stamped specs (a self-stamped
# fixture cannot catch that).
UPSTREAM = os.path.join(HERE, "specs", "upstream")
if os.path.isdir(UPSTREAM):
    r = check_spec_integrity(UPSTREAM)
    check("gate accepts REAL make-spec/make-arch-stamped specs (legacy arch)",
          r["ok"] is True and not r.get("fatal"))
else:
    check("golden upstream fixtures present", False)

UPSTREAM_V2 = os.path.join(HERE, "specs", "upstream-v2")
if os.path.isdir(UPSTREAM_V2):
    r = check_spec_integrity(UPSTREAM_V2)
    check("gate accepts the v2.0 golden (architecture.md frontmatter)",
          r["ok"] is True and not r.get("fatal"))
    arch_rows = [f for f in r["files"] if f["file"] == "arch"]
    check("v2.0 golden: architecture.md is the arch entry and is clean",
          len(arch_rows) == 1 and arch_rows[0]["ok"] is True)

    # A mutated (un-restamped) v2.0 architecture.md trips the arch dirty path
    # exactly as a dirty arch-data.yaml did: FAIL on a full run, WARN on a
    # scoped one (arch is project-level, advisory when scoped).
    root = os.path.join(tempfile.mkdtemp(prefix="mkissues-specs-"), "v2")
    shutil.copytree(UPSTREAM_V2, root)
    arch_path = os.path.join(root, "architecture.md")
    with open(arch_path, encoding="utf-8") as f:
        text = f.read()
    with open(arch_path, "w", encoding="utf-8") as f:
        f.write(text.replace("tech: Next.js", "tech: Nuxt"))  # IN edit, no re-stamp
    r = check_spec_integrity(root)
    check("mutated v2.0 architecture.md without re-stamp -> full run FAILS",
          r["ok"] is False and any(f["file"] == "arch" and f["level"] == "fail"
                                   for f in r["files"]))
    r = check_spec_integrity(root, parse_scope("checkout"))
    check("mutated v2.0 architecture.md on a scoped run -> WARNS, gate passes",
          r["ok"] is True and any(w["file"] == "arch"
                                  for w in r.get("warnings", [])))
    shutil.rmtree(os.path.dirname(root))
else:
    check("golden upstream-v2 fixtures present", False)

# ── SCOPED gate ("a1"): a dirty SELECTED feature FAILS ───────────────────────
# Two clean features + a dirty checkout. Scoped to checkout -> FAIL (never trace
# an issue to a half-saved requirement).
CART = {
    "meta": {"slug": "cart", "prefix": "CART", "status": "active",
             "feature_version": "1.0"},
    "requirements": [
        {"id": "FR-CART-001", "name": "Add item", "kind": "functional",
         "description": "Add an item to the cart.",
         "acceptance_criteria": ["WHEN add THE SYSTEM SHALL append."],
         "governed_by": [], "depends_on": [], "interface": "add(id)",
         "priority": "must", "status": "active"},
    ],
}


def two_feature_tree(dirty_slug=None):
    """checkout + cart, both stamped clean; if dirty_slug is given, that feature's
    stored fingerprint is left stale (an IN edit without re-stamp). Deep-copies the
    module fixtures so mutating one tree never leaks into another via shared refs."""
    root = tempfile.mkdtemp(prefix="mkissues-specs-")
    chk = stamped(copy.deepcopy(CHECKOUT))
    crt = stamped(copy.deepcopy(CART))
    if dirty_slug == "checkout":
        chk["requirements"][0]["acceptance_criteria"] = ["WHEN dirty THE SYSTEM SHALL drift."]
    if dirty_slug == "cart":
        crt["requirements"][0]["acceptance_criteria"] = ["WHEN dirty THE SYSTEM SHALL drift."]
    write_specs(root, stamped(copy.deepcopy(OVERVIEW)), {"checkout": chk, "cart": crt},
                stamped(copy.deepcopy(ARCH), ARCH_OUT_KEYS))
    return root


root = two_feature_tree(dirty_slug="checkout")
r = check_spec_integrity(root, parse_scope("checkout"))
check("scoped run: dirty SELECTED feature -> gate FAILS", r["ok"] is False)
shutil.rmtree(root)

# ── SCOPED gate: a dirty UNSELECTED feature only WARNS (gate passes) ──────────
root = two_feature_tree(dirty_slug="cart")
r = check_spec_integrity(root, parse_scope("checkout"))
check("scoped run: dirty UNSELECTED feature -> gate passes (advisory)",
      r["ok"] is True)
check("scoped run: the dirty unselected feature is a WARNING",
      any("cart" in w["file"] for w in r.get("warnings", [])))
shutil.rmtree(root)

# ── same dirty-cart tree on a FULL run -> FAILS (preserves the old guarantee) ─
root = two_feature_tree(dirty_slug="cart")
r = check_spec_integrity(root)          # no scope == full run
check("full run: any dirty feature -> gate FAILS (unchanged)", r["ok"] is False)
shutil.rmtree(root)

# ── SCOPED gate: scope by requirement id resolves to its feature ─────────────
root = two_feature_tree(dirty_slug="checkout")
r = check_spec_integrity(root, parse_scope("FR-CHK-001"))
check("scoped-by-req-id: dirty feature owning the selected req -> FAILS",
      r["ok"] is False)
shutil.rmtree(root)

# ── SCOPED gate: dirty overview is advisory on a scoped run ───────────────────
root = tempfile.mkdtemp(prefix="mkissues-specs-")
ov = stamped(copy.deepcopy(OVERVIEW))
ov["goals"][0]["text"] = "Ship checkout fast"    # IN edit, no re-stamp
write_specs(root, ov, {"checkout": stamped(copy.deepcopy(CHECKOUT))},
            stamped(copy.deepcopy(ARCH), ARCH_OUT_KEYS))
r = check_spec_integrity(root, parse_scope("checkout"))
check("scoped run: dirty overview only warns (project-level, advisory)",
      r["ok"] is True and any("overview" in w["file"] for w in r.get("warnings", [])))
shutil.rmtree(root)

# ── spec_set precondition ────────────────────────────────────────────────────
root = fresh_tree()
check("spec_set present when overview + features exist",
      check_spec_set_present(root)["ok"] is True)
shutil.rmtree(root)

root = tempfile.mkdtemp(prefix="mkissues-specs-")     # empty dir, no specs
p = check_spec_set_present(root)
check("spec_set absent -> not ok and fatal (drives exit 2)",
      p["ok"] is False and p.get("fatal") is True)
check("spec_set absence message points the user to /make-spec",
      "/make-spec" in p["detail"])
shutil.rmtree(root)

# ── parse_scope ──────────────────────────────────────────────────────────────
check("parse_scope('') -> None", parse_scope("") is None)
sc = parse_scope("checkout, FR-CART-001")
check("parse_scope classifies feature vs req id",
      sc["features"] == {"checkout"} and sc["reqs"] == {"FR-CART-001"})

print()
if failures:
    print(f"FAILURES: {failures}")
    sys.exit(1)
print("fail-closed fingerprint gate behaves as expected")
sys.exit(0)
