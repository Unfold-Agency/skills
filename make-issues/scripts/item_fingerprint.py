#!/usr/bin/env python3
"""Per-requirement fingerprint for the docs/product feature data files.

make-issues stamps each GitHub issue with a hash of the feature REQUIREMENT it
was generated from. On a later sync, a changed hash means the spec moved and the
issue may be stale; an unchanged hash means a no-op. The hash is taken over a
PROJECTION of each requirement -- only the CONTRACT-bearing (IN) fields -- so
rewording an advisory note, retitling, or re-prioritising churns nothing, but a
changed acceptance criterion, description, interface, governing ADR, or
dependency does.

This is the C1 keystone. The IN/OUT split MUST match the make-spec/make-arch
`compute_fingerprint` discipline exactly:

  IN  (hashed): id, kind, description, acceptance_criteria (order PRESERVED),
                verification (order-INSENSITIVE {method, check, covers} entries),
                governed_by (sorted set), depends_on (sorted set), interface.
  OUT (never):  priority, architecture_hints, related_files, notes -- plus the
                meta-level OUT keys (fingerprint, feature_version, generated_at,
                project_version, appetite) which do not live on a requirement.
  Also excluded from the per-item hash: name (cosmetic) and status (a lifecycle
  flag the reconciler handles via the orphan/stale path, not a content change --
  mirroring the old skill's choice to omit status from the item hash).

Normalization mirrors make-spec's compute_fingerprint exactly: build the IN
projection dict -> yaml.safe_dump(sort_keys=True) -> sha256.

The unit is a feature requirement (one record kind), read from EVERY single-file
spec features/<slug>.md under the spec dir -- its requirements live in the YAML
frontmatter (make-spec emits one file per feature; there is no separate data
file).

  python scripts/item_fingerprint.py docs/product                 # all requirements
  python scripts/item_fingerprint.py docs/product --json          # {req_id: hash}
  python scripts/item_fingerprint.py docs/product --id FR-CHK-001 # one requirement

The path may be the spec dir (docs/product), its features/ subdir, or a single
feature .md file.

Exit codes: 0 = ok, 1 = --id not found, 2 = file/parse error.
"""
import argparse
import glob
import hashlib
import json
import os
import re
import sys

try:
    import yaml
except ImportError:
    print("PyYAML is required: pip install pyyaml --break-system-packages", file=sys.stderr)
    sys.exit(2)


# ── The C1 contract: the IN fields, and how each normalizes ──────────────────
# scalars    -- free-text/enum fields; whitespace-collapsed.
# sets       -- order-INSENSITIVE lists of ids; sorted before hashing.
# seqs       -- order-SENSITIVE lists; order preserved (it is meaning).
# entry sets -- order-INSENSITIVE lists of structured entries; each entry is
#               projected to its contract keys, then the list is sorted.
IN_SCALARS = ["id", "kind", "description", "interface"]
IN_SEQS = ["acceptance_criteria"]            # EARS strings; order is contract
IN_SETS = ["governed_by", "depends_on"]      # ADR ids / requirement ids
IN_ENTRY_SETS = ["verification"]             # {method, check, covers} (schema 1.1);
ENTRY_KEYS = ("method", "check", "covers")   #   absent on 1.0 specs -> hash unchanged

# Explicitly OUT -- listed only for documentation; the projection is allow-list,
# so anything not named above is already excluded. priority/architecture_hints/
# related_files/notes are advisory; name is cosmetic; status is lifecycle.
OUT_FIELDS = ["priority", "architecture_hints", "related_files", "notes",
              "name", "status"]


def _norm_text(value):
    """Collapse internal whitespace and strip, so trailing-space / re-wrap edits
    in free-text contract fields don't churn the hash. Non-strings pass through."""
    if isinstance(value, str):
        return " ".join(value.split())
    return value


def project_in_fields(req):
    """The IN projection of one requirement -- the ONLY thing the item hash sees.

    This is the C1 keystone. Returns a dict containing exactly the contract
    (IN) fields, normalized. Every OUT field (priority, architecture_hints,
    related_files, notes) plus name and status is excluded by construction --
    this is an allow-list, so an unlisted key cannot leak in.
    """
    out = {}
    for f in IN_SCALARS:
        if req.get(f) not in (None, ""):
            out[f] = _norm_text(req[f])
    for f in IN_SEQS:
        if req.get(f):
            # order PRESERVED -- a reordered acceptance-criteria list is a
            # different contract (the EARS sequence is meaning).
            out[f] = [_norm_text(x) for x in req[f] if x is not None]
    for f in IN_SETS:
        if req.get(f):
            # order-INSENSITIVE -- sort so reordering governed_by/depends_on is
            # cosmetic, but adding/removing an id flips the hash.
            out[f] = sorted(_norm_text(x) for x in req[f] if x is not None)
    for f in IN_ENTRY_SETS:
        if req.get(f) and isinstance(req[f], list):
            entries = []
            for e in req[f]:
                if not isinstance(e, dict):
                    continue
                # allow-list inside each entry too -- an unlisted key cannot leak in
                proj = {k: _norm_text(e[k]) for k in ENTRY_KEYS
                        if e.get(k) not in (None, "")}
                if proj:
                    entries.append(proj)
            if entries:
                # order-INSENSITIVE -- reordering the proof plan is cosmetic, but
                # adding, removing, or editing an entry flips the hash.
                out[f] = sorted(entries, key=lambda p: (str(p.get("method", "")),
                                                        str(p.get("covers", "")),
                                                        str(p.get("check", ""))))
    return out


def compute_item_fingerprint(req):
    """sha256 over the IN projection of one feature requirement.
    Same normalization as make-spec's compute_fingerprint, scoped to one item."""
    proj = project_in_fields(req)
    normalized = yaml.safe_dump(proj, sort_keys=True, default_flow_style=False,
                                allow_unicode=True)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


# ── Loading the feature requirements out of docs/product ───────────────────────
# Specs are single .md files; the contract (requirements) lives in the YAML
# frontmatter, parsed deterministically (no separately-derived data file).
FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL)


def load_spec_doc(path):
    """Parse a single-file spec's YAML frontmatter into its doc dict. Returns {}
    when there is no frontmatter or it is not a mapping. Tolerates a BOM."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if text.startswith("﻿"):
        text = text[1:]
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}
    doc = yaml.safe_load(m.group(1))
    return doc if isinstance(doc, dict) else {}


def feature_files(path):
    """Resolve a path to the list of feature spec files it covers.

    Accepts the spec dir (docs/product -> docs/product/features/*.md), the features/
    subdir itself, or a single feature .md file.
    """
    if os.path.isfile(path):
        return [path]
    if os.path.isdir(path):
        feats = os.path.join(path, "features")
        search_dir = feats if os.path.isdir(feats) else path
        return sorted(glob.glob(os.path.join(search_dir, "*.md")))
    return []


def collect_requirements(path):
    """Return {req_id: req_record} across every feature spec under `path`.

    Raises ValueError on a read/parse error so the caller can exit 2.
    """
    reqs = {}
    files = feature_files(path)
    if not files:
        raise ValueError(f"no feature specs found at {path} "
                         "(expected <spec_dir>/features/*.md)")
    for fpath in files:
        try:
            doc = load_spec_doc(fpath)
        except (OSError, yaml.YAMLError) as e:
            raise ValueError(f"cannot read {fpath}: {e}")
        if not isinstance(doc, dict):
            raise ValueError(f"{fpath} has no spec frontmatter")
        for req in doc.get("requirements") or []:
            if isinstance(req, dict) and req.get("id"):
                reqs[str(req["id"])] = req
    return reqs


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec_dir",
                    help="docs/product (or its features/ dir, or one feature file)")
    ap.add_argument("--id", help="print only this requirement's fingerprint")
    ap.add_argument("--json", action="store_true", help="emit a JSON {id: hash} map")
    args = ap.parse_args()

    try:
        reqs = collect_requirements(args.spec_dir)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)

    if args.id:
        if args.id not in reqs:
            print(f"ERROR: {args.id} is not a requirement under {args.spec_dir}",
                  file=sys.stderr)
            sys.exit(1)
        fp = compute_item_fingerprint(reqs[args.id])
        print(json.dumps({args.id: fp}) if args.json else fp)
        sys.exit(0)

    fingerprints = {rid: compute_item_fingerprint(rec) for rid, rec in reqs.items()}
    if args.json:
        print(json.dumps(fingerprints, indent=2, sort_keys=True))
    else:
        for rid in sorted(fingerprints):
            print(f"{rid}  {fingerprints[rid]}")
    sys.exit(0)


if __name__ == "__main__":
    main()
