#!/usr/bin/env python3
"""Plan a make-data-flows run -- the read-only gate (analog of make-issues' analyze.py).

Detection is GLOBAL, writes are SCOPED. Every feature is examined every run; the
plan says CREATE / REGENERATE / SKIP for each, comparing the feature's current
make-spec `feature_version` to the one stamped in its flows region:

  no region                              -> CREATE
  region, stored feature_version == live -> SKIP     (advisory-only edits don't churn)
  region, stored feature_version != live -> REGENERATE (the contract moved)
  --force                                -> REGENERATE even a fresh feature

`--feature=<slug>` (repeatable) bounds which features are ACTIONABLE (written);
staleness detected outside the scope is still reported (`out_of_scope_stale`),
never acted on. The orchestrator runs a sub-agent only for the actionable
CREATE/REGENERATE features.

  python scripts/flow_status.py docs/specs [--feature checkout]... [--all] [--force] [--json]

Exit codes: 0 = a clean, safe plan; 1 = blocking (a corrupt existing region, or a
--feature target that does not exist); 2 = spec dir / parse error. Read-only:
this script never writes.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from flowlib import (  # noqa: E402
    feature_files, feature_meta, find_regions, parse_stamp, split_frontmatter,
)

CREATE, REGENERATE, SKIP = "CREATE", "REGENERATE", "SKIP"


def plan_feature(path, force):
    """Return a per-feature plan dict, or raise ValueError on a corrupt region."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    head, body, doc = split_frontmatter(text)
    slug, prefix, feature_version, status = feature_meta(doc)
    slug = slug or os.path.splitext(os.path.basename(path))[0]
    if not head:
        raise ValueError(f"{path}: no YAML frontmatter (not a feature spec?)")

    regions = find_regions(body)
    if len(regions) > 1:
        raise ValueError(f"{path}: {len(regions)} flows regions (expected 0 or 1)")

    entry = {
        "slug": slug,
        "prefix": prefix,
        "path": path,
        "status": status,
        "feature_version": feature_version,
        "has_region": bool(regions),
        "stored_version": None,
    }

    if not regions:
        entry["action"] = REGENERATE if force else CREATE
        entry["reason"] = "no flows region yet"
        return entry

    stamp = parse_stamp(regions[0].group("inner"))
    stored = str(stamp.get("feature_version") or "")
    entry["stored_version"] = stored
    if force:
        entry["action"], entry["reason"] = REGENERATE, "forced"
    elif not stored:
        entry["action"], entry["reason"] = REGENERATE, "region has no feature_version stamp"
    elif stored == feature_version:
        entry["action"], entry["reason"] = SKIP, "up to date"
    else:
        entry["action"] = REGENERATE
        entry["reason"] = f"contract moved ({stored} -> {feature_version})"
    return entry


def build_plan(spec_dir, scope, force):
    files = feature_files(spec_dir)
    if not files:
        raise ValueError(f"no feature specs under {spec_dir} (expected features/*.md)")

    blocking, features = [], []
    for slug, path in files:
        try:
            features.append(plan_feature(path, force))
        except (ValueError, OSError) as e:
            # A malformed region (ValueError) or an unreadable file (OSError) is
            # blocking drift, not a crash -- record it and keep planning.
            blocking.append(str(e))

    known = {f["slug"] for f in features}
    scope_set = set(scope or [])
    for want in scope_set:
        if want not in known:
            blocking.append(f"--feature '{want}' does not match any feature under {spec_dir}")

    def in_scope(slug):
        return not scope_set or slug in scope_set

    actionable, out_of_scope_stale = [], []
    for f in features:
        f["in_scope"] = in_scope(f["slug"])
        if f["action"] in (CREATE, REGENERATE):
            (actionable if f["in_scope"] else out_of_scope_stale).append(f["slug"])

    return {
        "spec_dir": spec_dir,
        "scope": sorted(scope_set) or None,
        "forced": force,
        "features": features,
        "actionable": actionable,
        "out_of_scope_stale": out_of_scope_stale,
        "blocking": blocking,
    }


def print_receipt(plan):
    scope = ", ".join(plan["scope"]) if plan["scope"] else "ALL"
    print(f"make-data-flows plan -- scope: {scope}")
    for f in plan["features"]:
        mark = " " if f["in_scope"] else "~"  # ~ = detected but out of scope
        print(f"  {mark} {f['action']:10s} {f['slug']:20s} {f['reason']}")
    print(f"actionable ({len(plan['actionable'])}): {', '.join(plan['actionable']) or 'none'}")
    if plan["out_of_scope_stale"]:
        print(f"out-of-scope stale ({len(plan['out_of_scope_stale'])}): "
              f"{', '.join(plan['out_of_scope_stale'])}  (widen --feature or run --all to act)")
    for b in plan["blocking"]:
        print(f"BLOCKING: {b}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec_dir", nargs="?", default="docs/specs")
    ap.add_argument("--feature", action="append", default=[], help="scope writes to this slug (repeatable)")
    ap.add_argument("--all", action="store_true", help="explicit full scope (the default when no --feature)")
    ap.add_argument("--force", action="store_true", help="regenerate even up-to-date features")
    ap.add_argument("--json", action="store_true", help="emit the plan as JSON")
    args = ap.parse_args()

    scope = [] if args.all else args.feature
    try:
        plan = build_plan(args.spec_dir, scope, args.force)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)

    if args.json:
        print(json.dumps(plan, indent=2, sort_keys=True))
    else:
        print_receipt(plan)

    sys.exit(1 if plan["blocking"] else 0)


if __name__ == "__main__":
    main()
