#!/usr/bin/env python3
"""Fingerprints for make-api-contracts.

Two hashes, both mirroring make-spec's compute_fingerprint discipline (project the
IN fields -> yaml.safe_dump(sort_keys=True) -> sha256):

  compute_op_fingerprint(op, method, path)
      Per-OPERATION hash over its derived SHAPE -- method, path, requestBody,
      responses, and the sorted trace_req/trace_adr/integration. This is what
      build_contracts.py compares to decide whether an operation's derived shape
      moved (upsert) or is unchanged (no-op). Human-owned fields (summary,
      description, x-notes) and provenance metadata (x-source-version, x-flow,
      x-status) are OUT -- editing a summary or bumping a version never churns it.

  compute_doc_fingerprint(doc)
      Whole-DOCUMENT hash over everything except the three volatile info keys
      (x-generated, x-fingerprint, x-contract-version). This is the fail-closed
      internal-drift gate (AC-006): a stored info.x-fingerprint that no longer
      matches a recompute means the file was edited out from under the skill.

  python scripts/contract_fingerprint.py docs/specs/api/openapi.yaml [--op <operationId>]
"""
import argparse
import hashlib
import sys

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
from contractlib import (  # noqa: E402
    HTTP_METHODS, X_INTEGRATION, X_TRACE_ADR, X_TRACE_REQ, as_list, strip_volatile,
)

try:
    import yaml
except ImportError:  # pragma: no cover
    print("PyYAML is required: pip install pyyaml --break-system-packages", file=sys.stderr)
    sys.exit(2)


def _norm(value):
    if isinstance(value, str):
        return " ".join(value.split())
    return value


def _sha(projection):
    normalized = yaml.safe_dump(projection, sort_keys=True, default_flow_style=False,
                                allow_unicode=True)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def compute_op_fingerprint(op, method, path):
    """sha256 over one operation's derived shape (the IN projection)."""
    proj = {
        "method": str(method).lower(),
        "path": path,
        "requestBody": op.get("requestBody"),
        "responses": op.get("responses"),
        "trace_req": sorted(str(x) for x in as_list(op.get(X_TRACE_REQ))),
        "trace_adr": sorted(str(x) for x in as_list(op.get(X_TRACE_ADR))),
        "integration": _norm(op.get(X_INTEGRATION) or ""),
    }
    # Drop empty keys so an absent requestBody and requestBody: null hash alike.
    proj = {k: v for k, v in proj.items() if v not in (None, "", [], {})}
    return _sha(proj)


def compute_doc_fingerprint(doc):
    """sha256 over the whole doc minus the volatile info keys (AC-006)."""
    return _sha(strip_volatile(doc))


def iter_operations(doc):
    """Yield (operationId, method, path, op) for every operation in the doc."""
    paths = doc.get("paths")
    if not isinstance(paths, dict):
        return
    for path, item in paths.items():
        if not isinstance(item, dict):
            continue
        for method, op in item.items():
            if method.lower() in HTTP_METHODS and isinstance(op, dict):
                yield op.get("operationId"), method, path, op


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("openapi", help="path to openapi.yaml")
    ap.add_argument("--op", help="print only this operationId's fingerprint")
    args = ap.parse_args()

    try:
        with open(args.openapi, encoding="utf-8") as f:
            doc = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError) as e:
        print(f"ERROR: cannot read {args.openapi}: {e}", file=sys.stderr)
        sys.exit(2)

    if args.op:
        for oid, method, path, op in iter_operations(doc):
            if oid == args.op:
                print(compute_op_fingerprint(op, method, path))
                sys.exit(0)
        print(f"ERROR: operationId {args.op} not found", file=sys.stderr)
        sys.exit(1)

    print(f"doc {compute_doc_fingerprint(doc)}")
    for oid, method, path, op in iter_operations(doc):
        print(f"{oid or '(no id)'}  {compute_op_fingerprint(op, method, path)}")
    sys.exit(0)


if __name__ == "__main__":
    main()
