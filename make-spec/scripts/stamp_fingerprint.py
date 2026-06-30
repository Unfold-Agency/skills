#!/usr/bin/env python3
"""Stamp meta.fingerprint + meta.feature_version into each single-file spec
under a spec dir, using the validator's own normalization so the two never
disagree. Run after authoring or editing any spec markdown:

  python scripts/stamp_fingerprint.py docs/specs

It (1) stamps each features/<slug>.md, (2) writes the matching feature_version
into the overview feature_index, and (3) stamps overview.md. Only the YAML
frontmatter is rewritten; the human body of each file is preserved. The
fingerprint is computed over the SAME frontmatter the human signs -- there is
no separately-derived data file. feature_version is the first 12 hex of the
feature's content fingerprint (content-derived, no counter to race). The
overview fingerprint excludes feature_version (an OUT field), so syncing the
index never invalidates the overview's own stamp.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import yaml  # noqa: E402
from validate_spec import (  # noqa: E402
    compute_fingerprint, feature_files, split_frontmatter,
)


def restamp(path, mutate):
    """Parse a spec file's frontmatter, apply mutate(doc), and rewrite the file
    with ONLY the frontmatter replaced -- the human body is preserved. Files are
    read/written as UTF-8 (specs are Markdown and routinely carry non-ASCII);
    a read/write or YAML error exits cleanly instead of a raw traceback."""
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        print(f"ERROR: cannot read {path}: {e}", file=sys.stderr)
        sys.exit(1)
    fm, body = split_frontmatter(text)
    try:
        doc = yaml.safe_load(fm) if fm is not None else {}
    except yaml.YAMLError as e:
        print(f"ERROR: cannot parse YAML frontmatter in {path}: {e}", file=sys.stderr)
        sys.exit(1)
    if not isinstance(doc, dict):
        doc = {}
    mutate(doc)
    dumped = yaml.safe_dump(doc, sort_keys=False, default_flow_style=False,
                            allow_unicode=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write("---\n" + dumped + "---\n" + body)
    except OSError as e:
        print(f"ERROR: cannot write {path}: {e}", file=sys.stderr)
        sys.exit(1)
    return doc


def main():
    spec_dir = sys.argv[1] if len(sys.argv) > 1 else "docs/specs"
    overview_path = os.path.join(spec_dir, "overview.md")
    if not os.path.isfile(overview_path):
        print(f"no overview.md under {spec_dir}", file=sys.stderr)
        sys.exit(1)

    versions = {}  # slug -> feature_version

    for slug, md_path in feature_files(spec_dir):
        def mutate(doc, _slug=slug):
            fp = compute_fingerprint(doc)
            doc.setdefault("meta", {})["fingerprint"] = fp
            doc["meta"]["feature_version"] = fp[:12]
            versions[_slug] = fp[:12]
        restamp(md_path, mutate)
        print(f"stamped {md_path}: {versions[slug]}")

    def mutate_overview(doc):
        for row in doc.get("feature_index") or []:
            if isinstance(row, dict) and row.get("slug") in versions:
                row["feature_version"] = versions[row["slug"]]
        doc.setdefault("meta", {})["fingerprint"] = compute_fingerprint(doc)
    odoc = restamp(overview_path, mutate_overview)
    print(f"stamped {overview_path}: "
          f"{((odoc.get('meta') or {}).get('fingerprint') or '')[:12]}")


if __name__ == "__main__":
    main()
