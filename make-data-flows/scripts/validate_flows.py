#!/usr/bin/env python3
"""Validate the embedded make-data-flows regions -- run after every embed.

Never present flows whose validation fails. The rules (prefix DF-):

  DF-001  markers well-formed + exactly-once per feature                  (FAIL)
  DF-002  each flow's mermaid is fenced, non-empty, and a known kind      (FAIL)
  DF-003  stamp parses, has the required keys, flow_count matches blocks  (FAIL)
  DF-004  every covers= id resolves; every active FR is covered by a flow (warn)
  DF-005  live feature_version != stamped -> the region is stale          (warn)
  DF-006  the feature's meta.fingerprint still matches -- the embed did
          not disturb the frontmatter contract                            (FAIL)

Flows are ADVISORY, so coverage (DF-004) and staleness (DF-005) only warn; the
structural + integrity rules fail. A feature with no flows region is fine (it
simply has no flows yet) -- only regions that exist are validated.

  python scripts/validate_flows.py docs/product [--feature checkout]...

Exit codes: 0 = clean (warnings allowed); 1 = one or more DF-001/002/003/006
violations; 2 = spec dir / parse error. Read-only.
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from flowlib import (  # noqa: E402
    DATA_FLOW_ID_RE, DATA_MERMAID_KINDS, REQ_ID_RE, USER_FLOW_ID_RE,
    USER_MERMAID_KINDS, active_requirement_ids, all_requirement_ids,
    feature_files, feature_meta, find_regions, mermaid_kind, parse_flows,
    parse_stamp, split_frontmatter,
)

FLOW_OPEN_RE = re.compile(r"<!-- make-data-flows:flow\s")
STAMP_KEYS = ("schema_version", "feature_version", "generated_at", "flow_count")


def _load_compute_fingerprint():
    """Import make-spec's compute_fingerprint from the sibling skill, if present.
    Returns the callable or None (DF-006 then falls back to a structural check)."""
    here = os.path.dirname(os.path.abspath(__file__))
    sibling = os.path.normpath(os.path.join(here, os.pardir, os.pardir, "make-spec", "scripts"))
    if not os.path.isdir(sibling):
        return None
    if sibling not in sys.path:
        sys.path.insert(0, sibling)
    try:
        from validate_spec import compute_fingerprint  # type: ignore
        return compute_fingerprint
    except Exception:  # pragma: no cover - defensive
        return None


def validate_feature(path, compute_fp):
    """Return (fails, warns): lists of message strings for one feature file."""
    fails, warns = [], []
    with open(path, encoding="utf-8") as f:
        text = f.read()
    head, body, doc = split_frontmatter(text)
    slug, prefix, feature_version, _status = feature_meta(doc)
    slug = slug or os.path.splitext(os.path.basename(path))[0]
    tag = f"[{slug}]"

    regions = find_regions(body)
    # DF-001 -- exactly-once / balanced markers.
    if len(regions) > 1:
        fails.append(f"{tag} DF-001: {len(regions)} flows regions (expected 0 or 1)")
        return fails, warns
    if not regions:
        return fails, warns  # this skill does not manage a file with no region

    # From here on the feature has a flows region -- one this skill manages.
    # DF-006 -- the embed must not have disturbed the frontmatter contract.
    meta = doc.get("meta") or {}
    stored_fp = str(meta.get("fingerprint") or "")
    if not head:
        fails.append(f"{tag} DF-006: no YAML frontmatter")
    elif not stored_fp:
        fails.append(f"{tag} DF-006: meta.fingerprint is missing")
    elif compute_fp is not None:
        try:
            if compute_fp(doc) != stored_fp:
                fails.append(f"{tag} DF-006: meta.fingerprint does not match a recompute "
                             "(the frontmatter contract is not currently stamped)")
        except Exception as e:  # pragma: no cover
            warns.append(f"{tag} DF-006: could not recompute fingerprint ({e})")

    inner = regions[0].group("inner")
    opens = len(FLOW_OPEN_RE.findall(inner))
    flows = parse_flows(inner)
    if opens != len(flows):
        fails.append(f"{tag} DF-001: {opens} flow open markers but {len(flows)} "
                     "closed flow blocks (unbalanced markers)")

    # DF-003 -- the stamp.
    stamp = parse_stamp(inner)
    if not stamp:
        fails.append(f"{tag} DF-003: stamp missing or unparseable")
    else:
        missing = [k for k in STAMP_KEYS if k not in stamp]
        if missing:
            fails.append(f"{tag} DF-003: stamp missing keys {missing}")
        if stamp.get("flow_count") != len(flows):
            fails.append(f"{tag} DF-003: stamp flow_count={stamp.get('flow_count')} "
                         f"but {len(flows)} flow blocks")

    active = active_requirement_ids(doc)
    known = all_requirement_ids(doc)
    covered = set()
    for attrs, src in flows:
        fid = attrs.get("id", "?")
        kind = attrs.get("kind")
        # DF-002 -- id grammar + mermaid presence + known kind.
        if kind == "data":
            if not DATA_FLOW_ID_RE.match(fid):
                fails.append(f"{tag} DF-002: data flow id '{fid}' bad (want DF-{prefix or 'XXX'}-NN)")
            allowed = DATA_MERMAID_KINDS
        elif kind == "user":
            if not USER_FLOW_ID_RE.match(fid):
                fails.append(f"{tag} DF-002: user flow id '{fid}' bad (want UF-{prefix or 'XXX'}-NN)")
            allowed = USER_MERMAID_KINDS
        else:
            fails.append(f"{tag} DF-002: flow '{fid}' has kind='{kind}' (want data|user)")
            allowed = DATA_MERMAID_KINDS | USER_MERMAID_KINDS
        if not src or not src.strip():
            fails.append(f"{tag} DF-002: flow '{fid}' has an empty/absent mermaid block")
        else:
            mk = mermaid_kind(src)
            if mk not in allowed:
                fails.append(f"{tag} DF-002: flow '{fid}' mermaid kind '{mk}' not valid for {kind} "
                             f"(want one of {sorted(allowed)})")
        # DF-004 -- covers resolution.
        for cid in attrs.get("covers") or []:
            if not REQ_ID_RE.match(cid):
                warns.append(f"{tag} DF-004: flow '{fid}' covers '{cid}' is not a requirement id")
            elif cid not in known:
                warns.append(f"{tag} DF-004: flow '{fid}' covers '{cid}' -- no such requirement")
            else:
                covered.add(cid)

    # DF-004 -- active-FR coverage (advisory).
    uncovered_fr = sorted(r for r in active if r.startswith("FR-") and r not in covered)
    if uncovered_fr:
        warns.append(f"{tag} DF-004: active FRs with no flow: {', '.join(uncovered_fr)}")

    # DF-005 -- staleness.
    stored_version = str(stamp.get("feature_version") or "")
    if stored_version and stored_version != feature_version:
        warns.append(f"{tag} DF-005: region stale -- stamped {stored_version}, "
                     f"live {feature_version} (re-run /make-data-flows --feature {slug})")
    return fails, warns


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec_dir", nargs="?", default="docs/product")
    ap.add_argument("--feature", action="append", default=[], help="validate only these slugs (repeatable)")
    args = ap.parse_args()

    files = feature_files(args.spec_dir)
    if not files:
        print(f"ERROR: no feature specs under {args.spec_dir}", file=sys.stderr)
        sys.exit(2)
    scope = set(args.feature)
    if scope:
        files = [(s, p) for s, p in files if s in scope]

    compute_fp = _load_compute_fingerprint()
    if compute_fp is None:
        print("note: make-spec not found alongside -- DF-006 is a structural check only")

    all_fails, all_warns = [], []
    for _slug, path in files:
        try:
            fails, warns = validate_feature(path, compute_fp)
        except Exception as e:  # pragma: no cover
            all_fails.append(f"[{path}] parse error: {e}")
            continue
        all_fails.extend(fails)
        all_warns.extend(warns)

    for w in all_warns:
        print(f"warn: {w}")
    for fmsg in all_fails:
        print(f"FAIL: {fmsg}", file=sys.stderr)

    if all_fails:
        print(f"\n{len(all_fails)} violation(s), {len(all_warns)} warning(s)", file=sys.stderr)
        sys.exit(1)
    print(f"OK -- flows valid ({len(all_warns)} warning(s))")
    sys.exit(0)


if __name__ == "__main__":
    main()
