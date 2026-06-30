#!/usr/bin/env python3
"""Stamp the correct meta.fingerprint + meta.arch_version into arch-data.yaml,
using the validator's own normalization so the two never disagree. Run after
make-arch (re-)derives arch-data.yaml from architecture.md + the ADR files:

  python scripts/stamp_fingerprint.py docs/specs

arch_version is the first 12 hex of the content fingerprint -- content-derived,
no counter to race.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import yaml  # noqa: E402
from validate_arch import compute_fingerprint, load_yaml  # noqa: E402


def main():
    spec_dir = sys.argv[1] if len(sys.argv) > 1 else "docs/specs"
    path = os.path.join(spec_dir, "arch-data.yaml")
    if not os.path.isfile(path):
        print(f"no arch-data.yaml under {spec_dir}", file=sys.stderr)
        sys.exit(1)
    doc = load_yaml(path)
    fp = compute_fingerprint(doc)
    doc.setdefault("meta", {})["fingerprint"] = fp
    doc["meta"]["arch_version"] = fp[:12]
    with open(path, "w") as f:
        yaml.safe_dump(doc, f, sort_keys=False, default_flow_style=False,
                       allow_unicode=True)
    print(f"stamped {path}: {fp[:12]}")


if __name__ == "__main__":
    main()
