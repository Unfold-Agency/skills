#!/usr/bin/env python3
"""Stamp the correct meta.fingerprint + meta.feature_version into every data
file under a spec dir, using the validator's own normalization so the two never
disagree. Run after the Skill (re-)derives any data file from its markdown:

  python scripts/stamp_fingerprint.py docs/specs

It (1) stamps each features/<slug>-data.yaml, (2) writes the matching
feature_version into the overview feature_index, and (3) stamps the overview.
feature_version is the first 12 hex of the feature's content fingerprint --
content-derived, no counter to race. The overview fingerprint excludes
feature_version (it is an OUT field), so syncing the index never invalidates
the overview's own stamp.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import yaml  # noqa: E402
from validate_spec import compute_fingerprint, feature_files, load_yaml  # noqa: E402


def dump(doc, path):
    with open(path, "w") as f:
        yaml.safe_dump(doc, f, sort_keys=False, default_flow_style=False,
                       allow_unicode=True)


def main():
    spec_dir = sys.argv[1] if len(sys.argv) > 1 else "docs/specs"
    overview_path = os.path.join(spec_dir, "overview-data.yaml")
    if not os.path.isfile(overview_path):
        print(f"no overview-data.yaml under {spec_dir}", file=sys.stderr)
        sys.exit(1)
    overview = load_yaml(overview_path)

    versions = {}  # slug -> feature_version
    for slug, _md, dpath in feature_files(spec_dir):
        doc = load_yaml(dpath)
        fp = compute_fingerprint(doc)
        doc.setdefault("meta", {})["fingerprint"] = fp
        doc["meta"]["feature_version"] = fp[:12]
        versions[slug] = fp[:12]
        dump(doc, dpath)
        print(f"stamped {dpath}: {fp[:12]}")

    for row in overview.get("feature_index") or []:
        if isinstance(row, dict) and row.get("slug") in versions:
            row["feature_version"] = versions[row["slug"]]
    ofp = compute_fingerprint(overview)
    overview.setdefault("meta", {})["fingerprint"] = ofp
    dump(overview, overview_path)
    print(f"stamped {overview_path}: {ofp[:12]}")


if __name__ == "__main__":
    main()
