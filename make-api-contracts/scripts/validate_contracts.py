#!/usr/bin/env python3
"""Validate the OpenAPI contract -- run after every build. Rules (prefix AC-):

  AC-001  valid OpenAPI 3.1 (openapi-spec-validator if importable; else a
          structural check -- openapi/info/paths present, every $ref resolves --
          with a warning that full validation was skipped)               (FAIL/warn)
  AC-002  operationId grammar (<slug>.<verbResource>) + global uniqueness   (FAIL)
  AC-003  provenance present on every operation (x-trace-req, x-feature,
          x-source-version, x-op-fingerprint)                              (FAIL)
  AC-004  live-trace: a non-tombstoned op's x-trace-req resolves to an ACTIVE
          requirement; x-trace-adr resolves to a real ADR                  (FAIL)
  AC-005  x-source-version equals the feature's current feature_version    (warn)
  AC-006  info.x-fingerprint matches a recompute (fail-closed drift gate)   (FAIL)
  AC-007  the file is in canonical serialized form (so the no-op guard holds) (warn)
  AC-008  openapi.yaml is present and parses                               (exit 2)
  AC-009  an op with x-integration but no own FR/IR requirement -- possible
          make-arch duplication                                            (warn)

Contracts are ADVISORY: staleness (AC-005), canonical form (AC-007), and the
boundary guard (AC-009) warn; structural + integrity rules fail.

  python scripts/validate_contracts.py docs/product [--out docs/product/api]

Exit codes: 0 = clean (warnings allowed); 1 = one or more failing rules; 2 = the
contract is missing or unparseable. Read-only.
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from contract_fingerprint import compute_doc_fingerprint, iter_operations  # noqa: E402
from contractlib import (  # noqa: E402
    OPENAPI_VERSION, OPERATION_ID_RE, X_FEATURE, X_INTEGRATION, X_OP_FP,
    X_SOURCE_VERSION, X_STATUS, X_TRACE_ADR, X_TRACE_REQ, as_list, dump_doc,
    read_arch, read_features,
)

try:
    import yaml
except ImportError:  # pragma: no cover
    print("PyYAML is required: pip install pyyaml --break-system-packages", file=sys.stderr)
    sys.exit(2)

REF_RE = re.compile(r"#/components/schemas/([A-Za-z0-9_.-]+)")


def _try_spec_validator(doc):
    """(ok, message). ok is None when the validator is not installed."""
    try:
        from openapi_spec_validator import validate as _validate  # type: ignore
    except Exception:
        return None, "openapi-spec-validator not installed"
    try:
        _validate(doc)
        return True, "openapi-spec-validator: valid"
    except Exception as e:  # the validator raises on invalid docs
        return False, f"openapi-spec-validator: {e}"


def _refs(node):
    """All schema names referenced by $ref anywhere in the doc."""
    found = set()
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "$ref" and isinstance(v, str):
                m = REF_RE.search(v)
                if m:
                    found.add(m.group(1))
            else:
                found |= _refs(v)
    elif isinstance(node, list):
        for v in node:
            found |= _refs(v)
    return found


def validate(doc, features, adr_ids):
    fails, warns = [], []
    active = {rid for f in features.values() for rid, r in f["requirements"].items()
              if r["status"] == "active"}
    known = {rid for f in features.values() for rid in f["requirements"]}
    feat_version = {slug: f["feature_version"] for slug, f in features.items()}

    # AC-001 -- validity.
    if str(doc.get("openapi", "")) < "3.1" and not str(doc.get("openapi", "")).startswith("3."):
        fails.append("AC-001: missing or non-3.x openapi version")
    ok, msg = _try_spec_validator(doc)
    if ok is None:
        warns.append(f"AC-001: {msg} -- structural check only")
        if "info" not in doc or "paths" not in doc:
            fails.append("AC-001: missing required top-level keys (info/paths)")
        components = doc.get("components")
        schemas = components.get("schemas") if isinstance(components, dict) else None
        missing_refs = _refs(doc) - set(schemas or {})
        if missing_refs:
            fails.append(f"AC-001: unresolved $ref schema(s): {sorted(missing_refs)}")
    elif ok is False:
        fails.append(f"AC-001: {msg}")

    # AC-006 -- fingerprint gate (fail-closed).
    info = doc.get("info") or {}
    stored_fp = str(info.get("x-fingerprint") or "")
    if not stored_fp:
        fails.append("AC-006: info.x-fingerprint is missing")
    elif compute_doc_fingerprint(doc) != stored_fp:
        fails.append("AC-006: info.x-fingerprint does not match a recompute (the contract "
                     "was edited out from under the skill -- re-run build_contracts)")

    seen_ids = {}
    for oid, method, path, op in iter_operations(doc):
        loc = f"{method.upper()} {path}"
        tombstoned = op.get(X_STATUS) == "tombstoned"
        # AC-002
        if not oid or not OPERATION_ID_RE.match(oid or ""):
            fails.append(f"AC-002: {loc} operationId '{oid}' bad (want <slug>.<verbResource>)")
        elif oid in seen_ids:
            fails.append(f"AC-002: duplicate operationId '{oid}' ({loc} and {seen_ids[oid]})")
        else:
            seen_ids[oid] = loc
        # AC-003
        for key in (X_TRACE_REQ, X_FEATURE, X_SOURCE_VERSION, X_OP_FP):
            if not op.get(key):
                fails.append(f"AC-003: {oid or loc} missing {key}")
        reqs = [str(x) for x in as_list(op.get(X_TRACE_REQ))]
        # AC-004
        if not tombstoned:
            if reqs and not (set(reqs) & active):
                fails.append(f"AC-004: {oid} traces to no ACTIVE requirement ({reqs}) "
                             "-- supersede handled by tombstoning, not a live op")
            for cid in reqs:
                if cid not in known:
                    fails.append(f"AC-004: {oid} x-trace-req '{cid}' resolves to no requirement")
            for adr in as_list(op.get(X_TRACE_ADR)):
                if adr_ids and adr not in adr_ids:
                    fails.append(f"AC-004: {oid} x-trace-adr '{adr}' resolves to no ADR")
        # AC-005
        feat = op.get(X_FEATURE)
        if not tombstoned and feat in feat_version:
            if str(op.get(X_SOURCE_VERSION) or "") != feat_version[feat]:
                warns.append(f"AC-005: {oid} stale -- stamped {op.get(X_SOURCE_VERSION)}, "
                             f"live {feat_version[feat]}")
        # AC-009
        if op.get(X_INTEGRATION) and not any(r.startswith(("FR-", "IR-")) for r in reqs):
            warns.append(f"AC-009: {oid} has {X_INTEGRATION} but no FR/IR requirement "
                         "-- is this make-arch's integration, not our endpoint?")
    return fails, warns


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec_dir", nargs="?", default="docs/product")
    ap.add_argument("--out", default=None, help="contract dir (default <spec_dir>/api)")
    args = ap.parse_args()

    out_dir = args.out or os.path.join(args.spec_dir, "api")
    openapi_path = os.path.join(out_dir, "openapi.yaml")
    # AC-008 -- present + parses.
    if not os.path.isfile(openapi_path):
        print(f"ERROR: AC-008: {openapi_path} not found", file=sys.stderr)
        sys.exit(2)
    try:
        text = open(openapi_path, encoding="utf-8").read()
        doc = yaml.safe_load(text) or {}
    except (OSError, yaml.YAMLError) as e:
        print(f"ERROR: AC-008: cannot parse {openapi_path}: {e}", file=sys.stderr)
        sys.exit(2)

    features = read_features(args.spec_dir)
    adr_ids, _intg = read_arch(args.spec_dir)

    fails, warns = validate(doc, features, adr_ids)

    # AC-007 -- canonical form (so the no-op guard holds).
    if dump_doc(doc) != text:
        warns.append("AC-007: openapi.yaml is not in canonical serialized form "
                     "(hand-edited?) -- re-run build_contracts to normalize")

    for w in warns:
        print(f"warn: {w}")
    for fmsg in fails:
        print(f"FAIL: {fmsg}", file=sys.stderr)
    if fails:
        print(f"\n{len(fails)} violation(s), {len(warns)} warning(s)", file=sys.stderr)
        sys.exit(1)
    print(f"OK -- contract valid ({len(warns)} warning(s))")
    sys.exit(0)


if __name__ == "__main__":
    main()
