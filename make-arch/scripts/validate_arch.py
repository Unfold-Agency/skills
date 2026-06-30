#!/usr/bin/env python3
"""
validate_arch.py — enforce validator rules A-001..A-008 across docs/specs/

Validates the architecture layer: arch-data.yaml + decisions/ADR-*.md +
architecture.md, and cross-checks the ADR index against the make-spec feature
files (no-orphan). Reuses the make-spec discipline: a fail-closed fingerprint
gate (A-007) and an origin/main append-only baseline (A-008).

Usage:
  python validate_arch.py [docs/specs] [--baseline-ref origin/main | --no-baseline]

Exit codes: 0 = pass (warnings do not fail), 1 = violations, 2 = file/parse error.
"""
import argparse
import copy
import hashlib
import os
import re
import subprocess
import sys

try:
    import yaml
except ImportError:
    print("PyYAML is required: pip install pyyaml --break-system-packages", file=sys.stderr)
    sys.exit(2)

ADR_ID_RE = re.compile(r"^ADR-\d{4}$")
ADR_STATUS = ("proposed", "accepted", "superseded", "deprecated")
DOC_STATUS = ("draft", "review", "approved")
CONFIDENCE = ("known", "assumption")
DIAGRAM_KINDS = ("context", "container", "sequence", "erd")

# Fingerprint IN/OUT contract (A-007) — advisory/derived keys dropped before hashing.
OUT_KEYS = {"fingerprint", "generated_at", "arch_version", "notes"}


def _strip_out(obj):
    if isinstance(obj, dict):
        return {k: _strip_out(v) for k, v in obj.items() if k not in OUT_KEYS}
    if isinstance(obj, list):
        return [_strip_out(x) for x in obj]
    return obj


def compute_fingerprint(doc):
    stripped = _strip_out(copy.deepcopy(doc))
    normalized = yaml.safe_dump(stripped, sort_keys=True, default_flow_style=False,
                                allow_unicode=True)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def load_yaml(path):
    with open(path) as f:
        return yaml.safe_load(f) or {}


def feature_governed_by(spec_dir):
    """Union of every ADR id referenced by a feature requirement's governed_by,
    across docs/specs/features/*-data.yaml."""
    refs = set()
    fdir = os.path.join(spec_dir, "features")
    if not os.path.isdir(fdir):
        return refs
    for name in os.listdir(fdir):
        if not name.endswith("-data.yaml"):
            continue
        try:
            doc = load_yaml(os.path.join(fdir, name))
        except yaml.YAMLError:
            continue
        for r in doc.get("requirements") or []:
            if isinstance(r, dict):
                for adr in r.get("governed_by") or []:
                    refs.add(str(adr))
    return refs


# ── git append-only baseline (A-008), fail-closed (same shape as make-spec) ──
def _git(args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def baseline_adr_ids(spec_dir, ref, fail):
    cwd = os.path.abspath(spec_dir)
    inside = _git(["rev-parse", "--is-inside-work-tree"], cwd)
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        fail("A-008", "not a git repository — cannot establish an append-only "
                      "baseline (use --no-baseline only for the greenfield kickoff)")
        return None
    if _git(["rev-parse", "--is-shallow-repository"], cwd).stdout.strip() == "true":
        fail("A-008", "shallow clone — run 'git fetch --unshallow' (refusing to "
                      "pass on partial history)")
        return None
    if _git(["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"], cwd).returncode != 0:
        fail("A-008", f"cannot resolve baseline ref '{ref}' — fetch it or pass "
                      "--no-baseline for the greenfield kickoff")
        return None
    show = _git(["show", f"{ref}:./arch-data.yaml"], cwd)
    if show.returncode != 0:
        return set()  # no arch-data at baseline — greenfield, nothing to lose
    try:
        prev = yaml.safe_load(show.stdout) or {}
    except yaml.YAMLError:
        return set()
    return {str(d.get("id")) for d in (prev.get("decisions") or [])
            if isinstance(d, dict) and d.get("id")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec_dir", nargs="?", default="docs/specs")
    ap.add_argument("--baseline-ref", default="origin/main")
    ap.add_argument("--no-baseline", action="store_true")
    args = ap.parse_args()

    spec_dir = args.spec_dir
    arch_path = os.path.join(spec_dir, "arch-data.yaml")
    if not os.path.isfile(arch_path):
        print(f"ERROR: no arch-data.yaml under {spec_dir}", file=sys.stderr)
        sys.exit(2)
    try:
        arch = load_yaml(arch_path)
    except Exception as e:
        print(f"ERROR: cannot parse {arch_path}: {e}", file=sys.stderr)
        sys.exit(2)

    errors, warns = [], []
    fail = lambda rule, msg: errors.append(f"[{rule}] {msg}")
    warn = lambda rule, msg: warns.append(f"[{rule}] {msg}")

    meta = arch.get("meta") or {}

    # ---- A-001: well-formed --------------------------------------------
    if not isinstance(arch.get("meta"), dict):
        fail("A-001", "meta block missing or not a mapping")
    for key in ("status", "fingerprint"):
        if key not in meta:
            fail("A-001", f"meta missing '{key}'")
    for key in ("components", "integrations", "decisions", "diagrams"):
        if key not in arch:
            fail("A-001", f"missing top-level key '{key}'")
    if str(meta.get("status") or "draft") not in DOC_STATUS:
        fail("A-001", f"status '{meta.get('status')}' not in {DOC_STATUS}")

    # ---- A-002: ADR id format, uniqueness, file <-> index agreement ----
    adr_ids = {}
    for d in arch.get("decisions") or []:
        if not isinstance(d, dict):
            continue
        did = d.get("id")
        if not did:
            fail("A-002", "a decisions[] entry is missing 'id'")
            continue
        if not ADR_ID_RE.match(str(did)):
            fail("A-002", f"malformed ADR id '{did}' (want ^ADR-\\d{{4}}$)")
        if did in adr_ids:
            fail("A-002", f"duplicate ADR id '{did}'")
        adr_ids[did] = d

    dec_dir = os.path.join(spec_dir, "decisions")
    adr_files = {}
    if os.path.isdir(dec_dir):
        for name in os.listdir(dec_dir):
            mo = re.match(r"^(ADR-\d{4})", name)
            if mo and name.endswith(".md"):
                adr_files[mo.group(1)] = name
    for did in adr_ids:
        if did not in adr_files:
            fail("A-002", f"{did} is in the index but has no decisions/{did}-*.md file")
    for did in adr_files:
        if did not in adr_ids:
            fail("A-002", f"decisions/{adr_files[did]} exists but {did} is not in "
                          "the arch-data index")

    # ---- A-003: supersede discipline -----------------------------------
    for did, d in adr_ids.items():
        st = str(d.get("status") or "")
        if st and st not in ADR_STATUS:
            fail("A-003", f"{did} status '{st}' not in {ADR_STATUS}")
        if st in ("superseded", "deprecated"):
            sb = str(d.get("superseded_by") or "")
            if not sb:
                fail("A-003", f"{did} is {st} but has no superseded_by")
            elif sb == did:
                fail("A-003", f"{did} cannot supersede itself")
            elif sb not in adr_ids:
                fail("A-003", f"{did}.superseded_by '{sb}' is not a known ADR")

    # ---- A-005: typed confidence ---------------------------------------
    for coll in ("components", "integrations", "decisions"):
        for item in arch.get(coll) or []:
            if not isinstance(item, dict):
                continue
            c = item.get("confidence")
            if c not in CONFIDENCE:
                who = item.get("id") or item.get("name") or f"a {coll[:-1]}"
                fail("A-005", f"{who} confidence '{c}' not in {CONFIDENCE}")

    # ---- A-004: no-orphan (cross-check vs features) --------------------
    feat_refs = feature_governed_by(spec_dir)
    for did, d in adr_ids.items():
        if str(d.get("status")) != "accepted":
            continue
        if did not in feat_refs:
            if str(d.get("scope")) == "project":
                warn("A-004", f"{did} (project-scoped) is accepted but not "
                              "referenced by any feature")
            else:
                fail("A-004", f"{did} (feature-scoped) is accepted but no feature "
                              "requirement's governed_by references it (orphan)")
    for ref in feat_refs:
        if ref not in adr_ids:
            fail("A-004", f"a feature references governed_by '{ref}' but it is not "
                          "in the arch-data decisions index")

    # ---- A-006: mermaid diagrams present -------------------------------
    arch_md = os.path.join(spec_dir, "architecture.md")
    if not os.path.isfile(arch_md):
        fail("A-006", "architecture.md is missing")
    else:
        md = open(arch_md).read()
        low = md.lower()
        if "```mermaid" not in low:
            fail("A-006", "architecture.md has no ```mermaid block")
        kinds = [k for k in (arch.get("diagrams") or []) if k in DIAGRAM_KINDS]
        if "context" not in kinds:
            fail("A-006", "diagrams must include the 'context' diagram")
        for kind in kinds:
            # a labelled mermaid block or the kind keyword near a mermaid fence
            if kind == "erd":
                ok = "erdiagram" in low
            elif kind == "sequence":
                ok = "sequencediagram" in low
            else:  # context / container — a C4/flow diagram naming the kind
                ok = kind in low
            if not ok:
                fail("A-006", f"diagrams lists '{kind}' but architecture.md has no "
                              f"matching mermaid diagram")

    # ---- A-007: fingerprint integrity (FAIL CLOSED) --------------------
    stored = str(meta.get("fingerprint") or "")
    if not stored:
        fail("A-007", "meta.fingerprint is blank")
    elif stored != compute_fingerprint(arch):
        fail("A-007", "fingerprint mismatch — arch-data.yaml drifted from its "
                      "markdown or was hand-edited (re-derive and re-stamp)")

    # ---- A-008: append-only ADRs vs baseline (FAIL CLOSED) -------------
    if not args.no_baseline:
        prior = baseline_adr_ids(spec_dir, args.baseline_ref, fail)
        if prior is not None:
            for v in sorted(prior - set(adr_ids)):
                fail("A-008", f"ADR '{v}' existed at {args.baseline_ref} and is now "
                              "missing — ADRs are append-only (supersede, never delete)")

    # ---- report ---------------------------------------------------------
    for w in warns:
        print(f"  warn {w}")
    if errors:
        print(f"\nFAIL — {len(errors)} violation(s) in {spec_dir}\n")
        for e in errors:
            print(f"  {e}")
        sys.exit(1)
    n_assume = sum(1 for coll in ("components", "integrations", "decisions")
                   for it in (arch.get(coll) or [])
                   if isinstance(it, dict) and it.get("confidence") == "assumption")
    print(f"PASS — {spec_dir} arch (status {meta.get('status') or '?'}, "
          f"{len(adr_ids)} ADR(s), {n_assume} assumption-backed choice(s))"
          + (f" — {len(warns)} warning(s)" if warns else ""))
    sys.exit(0)


if __name__ == "__main__":
    main()
