#!/usr/bin/env python3
"""Per-capability fingerprint for a TDD data file.

make-issues stamps each GitHub issue with a hash of the TDD capability it was
generated from. On a later sync, a changed hash means the design moved and the
issue may be stale; an unchanged hash means a no-op. The hash is taken over a
PROJECTION of each record -- only the contract-bearing fields -- so rewording a
name/purpose/note churns nothing, but a changed attribute type, transition,
endpoint, NFR requirement, or satisfied-requirement set does.

Normalization mirrors make-tdd's compute_fingerprint exactly (deep structure ->
yaml.safe_dump(sort_keys=True) -> sha256), applied to one record's projection.

  python scripts/item_fingerprint.py <tdd-data.yaml>            # all capabilities
  python scripts/item_fingerprint.py <tdd-data.yaml> --json     # {id: hash}
  python scripts/item_fingerprint.py <tdd-data.yaml> --id WF-003 # one capability

Exit codes: 0 = ok, 1 = --id not found / not a capability, 2 = file/parse error.
"""
import argparse
import hashlib
import json
import sys

try:
    import yaml
except ImportError:
    print("PyYAML is required: pip install pyyaml --break-system-packages", file=sys.stderr)
    sys.exit(2)


# Capability collections that become work items, mapped to their ID prefix.
# Order is the create/report order; ENT/WF/STM/INTG/TNF/ADR are the capability
# family (the same set make-tdd's traceability allows as satisfied_by).
CAPABILITY_COLLECTIONS = [
    ("entities", "ENT"),
    ("state_machines", "STM"),
    ("workflows", "WF"),
    ("integrations", "INTG"),
    ("nfrs", "TNF"),
    ("decisions", "ADR"),
]

# What to hash, per capability kind. Fields not listed are deliberately omitted
# as cosmetic/volatile (name, purpose, notes, rationale, alternatives, backing,
# needs_diagram, open_items). `status` is ALSO omitted: a flip to
# superseded/deferred is a lifecycle event the reconciler handles via the orphan
# path, not a content change.
#   scalars  -- free-text/enum fields; whitespace-collapsed
#   sets     -- order-INSENSITIVE lists of scalars; sorted before hashing
#   seqs     -- order-SENSITIVE lists of scalars; order preserved (it is meaning)
#   records  -- list-of-dict fields; keep only `keys`, sort unless `ordered`
PROJECTIONS = {
    "ENT": {
        "sets": ["satisfies"],
        "records": {
            "attributes": {"keys": ["name", "type", "required", "identifier"]},
            "relationships": {"keys": ["to", "cardinality"]},
        },
    },
    "STM": {
        "scalars": ["entity"],
        "sets": ["states", "satisfies"],
        # transitions are a SET of edges; reordering the same edges is cosmetic,
        # so sort them (not `ordered`). Steps below are the order-significant case.
        "records": {"transitions": {"keys": ["from", "to", "event"]}},
    },
    "WF": {
        "scalars": ["trigger"],
        "seqs": ["steps"],
        "sets": ["satisfies"],
    },
    "INTG": {
        "scalars": ["system", "direction", "auth_model", "data_exchanged",
                    "limits", "error_behavior"],
        "sets": ["endpoints", "satisfies", "bounded_by"],
    },
    "TNF": {
        "scalars": ["category", "requirement", "testing_method"],
        "sets": ["derived_from"],
    },
    "ADR": {
        "scalars": ["decision_status", "decision"],
        "sets": ["bounded_by", "derived_from"],
    },
}


def _norm_text(value):
    """Collapse internal whitespace and strip, so trailing-space / re-wrap edits
    in free-text contract fields don't churn the hash. Non-strings pass through."""
    if isinstance(value, str):
        return " ".join(value.split())
    return value


def _project(record, spec):
    out = {}
    for f in spec.get("scalars", []):
        if record.get(f) not in (None, ""):
            out[f] = _norm_text(record[f])
    for f in spec.get("sets", []):
        if record.get(f):
            out[f] = sorted(_norm_text(x) for x in record[f] if x is not None)
    for f in spec.get("seqs", []):
        if record.get(f):
            out[f] = [_norm_text(x) for x in record[f] if x is not None]
    for f, rspec in spec.get("records", {}).items():
        if not record.get(f):
            continue
        items = []
        for d in record[f]:
            if isinstance(d, dict):
                items.append({k: _norm_text(d[k]) for k in rspec["keys"] if k in d})
            else:
                items.append(_norm_text(d))
        if not rspec.get("ordered"):
            items.sort(key=lambda x: yaml.safe_dump(x, sort_keys=True))
        out[f] = items
    return out


def compute_item_fingerprint(record, kind):
    """sha256 over the contract-bearing projection of one TDD capability record.
    Same normalization as make-tdd's compute_fingerprint, scoped to one item."""
    proj = _project(record, PROJECTIONS[kind])
    proj["id"] = record.get("id", "")
    proj["_kind"] = kind
    normalized = yaml.safe_dump(proj, sort_keys=True, default_flow_style=False,
                                allow_unicode=True)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def collect_capabilities(doc):
    """Return {id: (record, kind)} for every capability record with an id."""
    caps = {}
    for collection, kind in CAPABILITY_COLLECTIONS:
        for record in doc.get(collection) or []:
            if isinstance(record, dict) and record.get("id"):
                caps[str(record["id"])] = (record, kind)
    return caps


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("data_file", help="tdd-data.yaml")
    ap.add_argument("--id", help="print only this capability's fingerprint")
    ap.add_argument("--json", action="store_true", help="emit a JSON {id: hash} map")
    args = ap.parse_args()

    try:
        with open(args.data_file, encoding="utf-8") as f:
            doc = yaml.safe_load(f)
    except (OSError, yaml.YAMLError) as e:
        print(f"ERROR: cannot read {args.data_file}: {e}", file=sys.stderr)
        sys.exit(2)
    if not isinstance(doc, dict):
        print(f"ERROR: {args.data_file} is not a YAML mapping", file=sys.stderr)
        sys.exit(2)

    caps = collect_capabilities(doc)

    if args.id:
        if args.id not in caps:
            print(f"ERROR: {args.id} is not a capability in {args.data_file}",
                  file=sys.stderr)
            sys.exit(1)
        record, kind = caps[args.id]
        fp = compute_item_fingerprint(record, kind)
        print(json.dumps({args.id: fp}) if args.json else fp)
        sys.exit(0)

    fingerprints = {cid: compute_item_fingerprint(rec, kind)
                    for cid, (rec, kind) in caps.items()}
    if args.json:
        print(json.dumps(fingerprints, indent=2, sort_keys=True))
    else:
        for cid in sorted(fingerprints):
            print(f"{cid}  {fingerprints[cid]}")
    sys.exit(0)


if __name__ == "__main__":
    main()
