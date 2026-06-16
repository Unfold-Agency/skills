#!/usr/bin/env python3
"""Stamp the correct meta.fingerprint into a TDD data file in place, using the
validator's own normalization. Run after editing tdd-data.pass.yaml:

  python scripts/tests/stamp_fingerprint.py scripts/tests/tdd-data.pass.yaml
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import yaml  # noqa: E402
from validate_tdd import compute_fingerprint  # noqa: E402


def main():
    path = sys.argv[1]
    with open(path) as f:
        doc = yaml.safe_load(f)
    doc.setdefault("meta", {})["fingerprint"] = compute_fingerprint(doc)
    with open(path, "w") as f:
        yaml.safe_dump(doc, f, sort_keys=False, default_flow_style=False, allow_unicode=True)
    print(f"stamped fingerprint into {path}: {doc['meta']['fingerprint']}")


if __name__ == "__main__":
    main()
