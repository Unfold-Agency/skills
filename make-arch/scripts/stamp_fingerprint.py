#!/usr/bin/env python3
"""Stamp the correct meta.fingerprint + meta.arch_version into architecture.md's
frontmatter, using the validator's own normalization so the two never disagree.
The body (narrative + mermaid) is preserved byte-for-byte. Run after authoring
or editing the architecture layer:

  python scripts/stamp_fingerprint.py docs/product

arch_version is the first 12 hex of the content fingerprint -- content-derived,
no counter to race. ADR files are NOT stamped: their regime is append-only, and
the validator enforces it against the git baseline (A-008/A-009).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import yaml  # noqa: E402
from validate_arch import compute_fingerprint, parse_md  # noqa: E402


def stamp_architecture(spec_dir):
    """Stamp docs/product/architecture.md in place; returns the fingerprint."""
    path = os.path.join(spec_dir, "architecture.md")
    if not os.path.isfile(path):
        hint = (" -- legacy arch-data.yaml found: run scripts/migrate_arch_data.py"
                if os.path.isfile(os.path.join(spec_dir, "arch-data.yaml")) else "")
        raise FileNotFoundError(f"no architecture.md under {spec_dir}{hint}")
    with open(path, encoding="utf-8") as f:
        doc, body = parse_md(f.read())
    if not doc:
        raise ValueError(f"{path} has no frontmatter to stamp "
                         "(see assets/architecture-template.md)")
    fp = compute_fingerprint(doc)
    doc.setdefault("meta", {})["fingerprint"] = fp
    doc["meta"]["arch_version"] = fp[:12]
    dumped = yaml.safe_dump(doc, sort_keys=False, default_flow_style=False,
                            allow_unicode=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("---\n" + dumped + "---\n" + (body or ""))
    return fp


def main():
    spec_dir = sys.argv[1] if len(sys.argv) > 1 else "docs/product"
    try:
        fp = stamp_architecture(spec_dir)
    except (FileNotFoundError, ValueError) as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
    print(f"stamped {os.path.join(spec_dir, 'architecture.md')}: {fp[:12]}")


if __name__ == "__main__":
    main()
