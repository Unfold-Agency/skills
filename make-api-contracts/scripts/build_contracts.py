#!/usr/bin/env python3
"""Build/merge the OpenAPI contract from authored operations -- the engine.

The LLM (skill orchestrator, optionally a sub-agent per feature) reads the specs
+ make-data-flows diagrams and AUTHORS each operation's shape into a JSON payload.
This script does the deterministic, safe part:

  - UPSERT by operationId: insert new operations, update changed ones in place,
    and preserve human-owned fields (summary/description/x-notes) verbatim -- the
    make-issues "never clobber the human region" doctrine at operation altitude.
  - STAMP provenance on every operation (x-trace-req / x-feature / x-source-version
    / x-trace-adr / x-integration / x-op-fingerprint), mirroring make-issues meta.
  - HANDSHAKE with make-data-flows: an operation whose requirement has no covering
    flow is marked x-flow: unconfirmed (a warning, never dropped).
  - TOMBSTONE (additive, per make-trace): an operation whose requirements all went
    inactive is marked deprecated + x-status: tombstoned, never deleted (deleting
    would break a running mock); it resurrects when re-authored.
  - SCOPE writes with --feature; detect drift GLOBALLY and report out-of-scope.
  - NO-OP guard: byte-identical when only the timestamp would change.
  - Render docs/specs/api/API-CONTRACTS.md and maintain .make-api-sync.json.

  # write from an authored payload:
  python scripts/build_contracts.py docs/specs payload.json [--feature checkout]... [--now ISO]
  # read-only status (staleness / coverage gaps / tombstone candidates):
  python scripts/build_contracts.py docs/specs --check

Payload:
  {"info": {"title": "...", "version": "0.1"},         # optional; seeds a new doc
   "operations": [
     {"operationId":"checkout.createOrder","method":"post","path":"/orders",
      "feature":"checkout","trace_req":["IR-CHK-001"],"trace_adr":["ADR-0001"],
      "integration":"INTG-stripe","summary":"...","requestBody":{...},
      "responses":{...},"schemas":{"OrderInput":{...},"Order":{...}}}
   ]}

Exit codes: 0 = wrote / no-op / clean --check; 1 = blocking (bad payload, unknown
--feature, unknown feature on an op); 2 = file/parse error or fail-closed emptiness.
Writes only under --out (default docs/specs/api).
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from contract_fingerprint import compute_doc_fingerprint, compute_op_fingerprint, iter_operations  # noqa: E402
from contractlib import (  # noqa: E402
    HTTP_METHODS, HUMAN_OP_FIELDS, OPENAPI_VERSION, OPERATION_ID_RE, X_FEATURE,
    X_FLOW, X_INTEGRATION, X_OP_FP, X_SOURCE_VERSION, X_STATUS, X_TRACE_ADR,
    X_TRACE_REQ, as_list, dump_doc, read_arch, read_features, strip_volatile,
)

try:
    import yaml
except ImportError:  # pragma: no cover
    print("PyYAML is required: pip install pyyaml --break-system-packages", file=sys.stderr)
    sys.exit(2)

HTTP_IFACE_RE = re.compile(r"\b(GET|POST|PUT|PATCH|DELETE)\b\s+/\S*", re.IGNORECASE)


class BuildError(Exception):
    """A blocking input problem -- write nothing."""


# ── loading ──────────────────────────────────────────────────────────────────
def load_openapi(path):
    if not os.path.isfile(path):
        return None, None
    with open(path, encoding="utf-8") as f:
        text = f.read()
    try:
        doc = yaml.safe_load(text) or {}
    except yaml.YAMLError as e:
        raise BuildError(f"cannot parse {path}: {e}")
    if not isinstance(doc, dict):
        raise BuildError(f"invalid OpenAPI document in {path} (expected a mapping)")
    return doc, text


def seed_doc(info):
    return {
        "openapi": OPENAPI_VERSION,
        "info": dict(info or {"title": "API", "version": "0.1"}),
        "servers": [{"url": "/api"}],
        "tags": [],
        "paths": {},
        "components": {"schemas": {}},
    }


def op_index(doc):
    """{operationId: (path, method)} for existing operations."""
    idx = {}
    for oid, method, path, _op in iter_operations(doc):
        if oid:
            idx[oid] = (path, method)
    return idx


# ── the plan (global detection; also powers --check) ─────────────────────────
def detect(doc, features):
    """Return dict of stale ops, orphan (tombstone-candidate) ops, and coverage
    gaps -- all read-only, computed over the whole spec set."""
    active = {rid for f in features.values() for rid, r in f["requirements"].items()
              if r["status"] == "active"}
    feat_version = {slug: f["feature_version"] for slug, f in features.items()}

    stale, orphan = [], []
    traced = set()
    for oid, method, path, op in iter_operations(doc):
        reqs = [str(x) for x in as_list(op.get(X_TRACE_REQ))]
        traced.update(reqs)
        feat = op.get(X_FEATURE)
        if reqs and not (set(reqs) & active):
            orphan.append({"operationId": oid, "feature": feat, "trace_req": reqs})
        elif feat in feat_version and str(op.get(X_SOURCE_VERSION) or "") != feat_version[feat]:
            stale.append({"operationId": oid, "feature": feat,
                          "stored": op.get(X_SOURCE_VERSION), "live": feat_version[feat]})

    gaps = []
    for slug, f in features.items():
        for rid, r in f["requirements"].items():
            if r["status"] == "active" and HTTP_IFACE_RE.search(r["interface"] or "") and rid not in traced:
                gaps.append({"req": rid, "feature": slug, "interface": r["interface"]})
    return {"stale": stale, "orphan": orphan, "gaps": gaps}


# ── upsert ───────────────────────────────────────────────────────────────────
def _validate_op(spec, features):
    if not isinstance(spec, dict):
        raise BuildError(f"operation entry is not a mapping: {spec!r}")
    oid = spec.get("operationId")
    if not oid or not OPERATION_ID_RE.match(oid):
        raise BuildError(f"operation '{oid}' bad operationId (want <feature-slug>.<verbResource>)")
    method = str(spec.get("method") or "").lower()
    if method not in HTTP_METHODS:
        raise BuildError(f"operation {oid}: method '{spec.get('method')}' not an HTTP method")
    if not spec.get("path", "").startswith("/"):
        raise BuildError(f"operation {oid}: path '{spec.get('path')}' must start with '/'")
    feat = spec.get("feature")
    if feat not in features:
        raise BuildError(f"operation {oid}: feature '{feat}' is not in the spec set")
    return oid, method, spec["path"], feat


def upsert(doc, spec, features, scope):
    """Insert/update one operation. Returns 'wrote'|'skip-scope'. Mutates doc."""
    oid, method, path, feat = _validate_op(spec, features)
    if scope and feat not in scope:
        return "skip-scope"

    finfo = features[feat]
    op = {
        "operationId": oid,
        "tags": [feat],
        X_TRACE_REQ: sorted(str(x) for x in as_list(spec.get("trace_req"))),
        X_FEATURE: feat,
        X_SOURCE_VERSION: finfo["feature_version"],
        X_TRACE_ADR: sorted(str(x) for x in as_list(spec.get("trace_adr"))),
    }
    if spec.get("integration"):
        op[X_INTEGRATION] = spec["integration"]
    if spec.get("requestBody"):
        op["requestBody"] = spec["requestBody"]
    op["responses"] = spec.get("responses") or {"200": {"description": "OK"}}
    # handshake: no covering make-data-flows flow for any of this op's reqs.
    reqs = set(op[X_TRACE_REQ])
    if reqs and not (reqs & finfo["covered"]):
        op[X_FLOW] = "unconfirmed"
    op[X_OP_FP] = compute_op_fingerprint(op, method, path)

    # Human-owned fields: existing value wins; else the payload seeds it on create.
    idx = op_index(doc)
    existing = idx.get(oid)
    if existing:
        epath, emethod = existing
        eop = doc["paths"][epath][emethod]
        for hf in HUMAN_OP_FIELDS:
            if eop.get(hf):
                op[hf] = eop[hf]
            elif spec.get(hf):
                op[hf] = spec[hf]
        if (epath, emethod) != (path, method):
            del doc["paths"][epath][emethod]  # moved -> drop the old slot
            if not doc["paths"][epath]:
                del doc["paths"][epath]
    else:
        for hf in HUMAN_OP_FIELDS:
            if spec.get(hf):
                op[hf] = spec[hf]

    # Defensively re-init any section a malformed YAML parsed as null (setdefault
    # on an existing null key returns None, not the fallback).
    if not isinstance(doc.get("paths"), dict):
        doc["paths"] = {}
    doc["paths"].setdefault(path, {})[method] = op
    # tag registry
    if not isinstance(doc.get("tags"), list):
        doc["tags"] = []
    if not any(t.get("name") == feat for t in doc["tags"] if isinstance(t, dict)):
        doc["tags"].append({"name": feat})
    # schemas
    if not isinstance(doc.get("components"), dict):
        doc["components"] = {}
    if not isinstance(doc["components"].get("schemas"), dict):
        doc["components"]["schemas"] = {}
    for name, schema in (spec.get("schemas") or {}).items():
        doc["components"]["schemas"][name] = schema
    return "wrote"


def tombstone_orphans(doc, features, scope):
    """Mark operations whose requirements all went inactive (deprecated +
    x-status: tombstoned). In-scope only writes; out-of-scope is reported."""
    active = {rid for f in features.values() for rid, r in f["requirements"].items()
              if r["status"] == "active"}
    tombstoned, out_of_scope = [], []
    for oid, method, path, op in iter_operations(doc):
        reqs = [str(x) for x in as_list(op.get(X_TRACE_REQ))]
        if not reqs or (set(reqs) & active):
            continue  # still has a live requirement
        feat = op.get(X_FEATURE)
        if scope and feat not in scope:
            out_of_scope.append(oid)
            continue
        op["deprecated"] = True
        op[X_STATUS] = "tombstoned"
        tombstoned.append(oid)
    return tombstoned, out_of_scope


# ── rendering + ledger ───────────────────────────────────────────────────────
def render_markdown(doc, header):
    lines = [header.rstrip("\n"), ""]
    by_feat = {}
    for oid, method, path, op in iter_operations(doc):
        by_feat.setdefault(op.get(X_FEATURE) or "(untagged)", []).append((oid, method, path, op))
    for feat in sorted(by_feat):
        lines.append(f"## {feat}")
        lines.append("")
        lines.append("| Operation | Method | Path | Traces to | Notes |")
        lines.append("|---|---|---|---|---|")
        for oid, method, path, op in sorted(by_feat[feat]):
            traces = ", ".join(as_list(op.get(X_TRACE_REQ)))
            adrs = ", ".join(as_list(op.get(X_TRACE_ADR)))
            trace_cell = traces + (f" / {adrs}" if adrs else "")
            notes = []
            if op.get(X_STATUS) == "tombstoned":
                notes.append("tombstoned")
            if op.get(X_FLOW) == "unconfirmed":
                notes.append("flow unconfirmed")
            if op.get(X_INTEGRATION):
                notes.append(op[X_INTEGRATION])
            summary = (op.get("summary") or "").replace("|", "\\|")
            lines.append(f"| `{oid}` -- {summary} | {method.upper()} | `{path}` | "
                         f"{trace_cell} | {', '.join(notes)} |")
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def build_ledger(doc):
    ledger = {}
    for oid, method, path, op in iter_operations(doc):
        if not oid:
            continue
        state = "deleted" if op.get(X_STATUS) == "tombstoned" else "present"
        ledger[oid] = {
            "op_fingerprint": op.get(X_OP_FP),
            "source_version": op.get(X_SOURCE_VERSION),
            "feature": op.get(X_FEATURE),
            "state": state,
        }
    return ledger


# ── write with stamp + no-op guard ───────────────────────────────────────────
def stamp_and_write(doc, out_dir, header, prior_text, prior_doc, now):
    doc.setdefault("openapi", OPENAPI_VERSION)
    if not isinstance(doc.get("info"), dict):
        doc["info"] = {"title": "API", "version": "0.1"}
    info = doc["info"]
    fp = compute_doc_fingerprint(doc)
    info["x-fingerprint"] = fp
    info["x-contract-version"] = fp[:12]

    generated = now
    if prior_doc is not None and strip_volatile(prior_doc) == strip_volatile(doc):
        prior_gen = (prior_doc.get("info") or {}).get("x-generated")
        if prior_gen:
            generated = prior_gen
    info["x-generated"] = generated

    openapi_text = dump_doc(doc)
    md_text = render_markdown(doc, header)
    ledger_text = json.dumps(build_ledger(doc), indent=2, sort_keys=True) + "\n"

    os.makedirs(out_dir, exist_ok=True)
    wrote = []
    targets = {
        os.path.join(out_dir, "openapi.yaml"): openapi_text,
        os.path.join(out_dir, "API-CONTRACTS.md"): md_text,
        os.path.join(out_dir, ".make-api-sync.json"): ledger_text,
    }
    for path, text in targets.items():
        existing = open(path, encoding="utf-8").read() if os.path.isfile(path) else None
        if existing == text:
            continue
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        wrote.append(os.path.basename(path))
    return wrote


# ── main ─────────────────────────────────────────────────────────────────────
def print_check(det, has_doc):
    if not has_doc:
        print("no contract yet (docs/specs/api/openapi.yaml absent) -- kickoff needed")
    print(f"stale operations ({len(det['stale'])}):")
    for s in det["stale"]:
        print(f"  {s['operationId']} -- {s['feature']} {s['stored']} -> {s['live']}")
    print(f"coverage gaps ({len(det['gaps'])}) -- active reqs with an HTTP interface but no operation:")
    for g in det["gaps"]:
        print(f"  {g['req']} ({g['feature']}): {g['interface']}")
    print(f"tombstone candidates ({len(det['orphan'])}) -- operations whose requirements went inactive:")
    for o in det["orphan"]:
        print(f"  {o['operationId']} -- was {', '.join(o['trace_req'])}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec_dir", nargs="?", default="docs/specs")
    ap.add_argument("payload", nargs="?", help="authored-operations JSON (or '-' for stdin)")
    ap.add_argument("--out", default=None, help="output dir (default <spec_dir>/api)")
    ap.add_argument("--feature", action="append", default=[], help="scope writes to these slugs")
    ap.add_argument("--all", action="store_true", help="explicit full scope")
    ap.add_argument("--check", action="store_true", help="read-only: report staleness/gaps, write nothing")
    ap.add_argument("--allow-empty", action="store_true", help="confirm a genuine emptying")
    ap.add_argument("--now", help="ISO-8601 timestamp for x-generated")
    args = ap.parse_args()

    out_dir = args.out or os.path.join(args.spec_dir, "api")
    openapi_path = os.path.join(out_dir, "openapi.yaml")
    header_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               os.pardir, "assets", "API-CONTRACTS-header.md")
    header = open(header_path, encoding="utf-8").read() if os.path.isfile(header_path) \
        else "# API Contracts\n\nGenerated by make-api-contracts. Do not hand-edit.\n"

    try:
        features = read_features(args.spec_dir)
    except OSError as e:
        print(f"ERROR: cannot read specs: {e}", file=sys.stderr)
        sys.exit(2)
    if not features:
        print(f"ERROR: no feature specs under {args.spec_dir}", file=sys.stderr)
        sys.exit(2)

    for want in args.feature:
        if want not in features:
            print(f"ERROR: --feature '{want}' is not a feature under {args.spec_dir}", file=sys.stderr)
            sys.exit(1)

    try:
        prior_doc, prior_text = load_openapi(openapi_path)
    except BuildError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)

    # --check: read-only detection.
    if args.check:
        det = detect(prior_doc or {"paths": {}}, features)
        print_check(det, prior_doc is not None)
        sys.exit(0)

    if not args.payload:
        print("ERROR: a payload is required to write (or pass --check)", file=sys.stderr)
        sys.exit(1)
    try:
        raw = sys.stdin.read() if args.payload == "-" else open(args.payload, encoding="utf-8").read()
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERROR: cannot read payload: {e}", file=sys.stderr)
        sys.exit(2)
    if not isinstance(payload, dict):
        print("ERROR: payload must be a JSON object", file=sys.stderr)
        sys.exit(1)

    scope = set() if args.all else set(args.feature)
    prior_ops = sum(1 for _ in iter_operations(prior_doc)) if prior_doc else 0
    payload_info = payload.get("info") if isinstance(payload.get("info"), dict) else None
    doc = prior_doc if prior_doc is not None else seed_doc(payload_info)
    if prior_doc is not None and payload_info:
        if not isinstance(doc.get("info"), dict):
            doc["info"] = {}
        doc["info"].update(payload_info)

    operations = payload.get("operations")
    if not isinstance(operations, list):
        operations = []
    try:
        results = [upsert(doc, spec, features, scope) for spec in operations]
    except BuildError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    wrote_ops = results.count("wrote")
    skipped = results.count("skip-scope")

    tombstoned, tomb_oos = tombstone_orphans(doc, features, scope)

    new_ops = sum(1 for _ in iter_operations(doc))
    if prior_ops > 0 and new_ops == 0 and not args.allow_empty:
        print("ERROR: contract had operations but now derives zero -- refusing to empty it "
              "(--allow-empty to confirm)", file=sys.stderr)
        sys.exit(2)

    now = args.now or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    files = stamp_and_write(doc, out_dir, header, prior_text, prior_doc, now)

    scope_label = ", ".join(sorted(scope)) if scope else "ALL"
    print(f"make-api-contracts -- scope: {scope_label}")
    print(f"  operations: {wrote_ops} written, {skipped} skipped (out of scope), "
          f"{len(tombstoned)} tombstoned")
    if tomb_oos:
        print(f"  out-of-scope tombstone candidates (not written): {', '.join(tomb_oos)}")
    print(f"  files: {', '.join(files) if files else 'no changes (byte-identical no-op)'}")
    sys.exit(0)


if __name__ == "__main__":
    main()
