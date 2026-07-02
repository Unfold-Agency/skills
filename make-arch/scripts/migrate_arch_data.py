#!/usr/bin/env python3
"""
migrate_arch_data.py -- one-time migration from the derived arch-data.yaml
(schema v1.0) to the single-file layout (schema v2.0).

WHY. arch-data.yaml was an LLM-derived copy of content the human actually
signed in architecture.md + the ADR prose -- the same two-file fidelity gap the
2026-06-30 council closed for make-spec. This migration moves the machine
contract INTO the signed files' frontmatter and deletes the derived copy:

  1. Each decisions/ADR-NNNN-*.md gains frontmatter built from its
     arch-data.yaml index entry (id, title, status, scope, confidence,
     superseded_by, governs) plus the date / supersedes parsed from its own
     body bullets. The prose body is preserved byte-for-byte. An ADR that
     already has frontmatter is skipped (idempotent).
  2. architecture.md gains the schema v2.0 frontmatter (meta + context +
     components + integrations + diagrams, carried over from arch-data.yaml).
     Its body is preserved.
  3. arch-data.yaml is deleted, and architecture.md is re-stamped.

  python scripts/migrate_arch_data.py docs/product [--dry-run]

Exit codes: 0 = migrated (or nothing to migrate), 2 = error. After migrating:
git add -A, run validate_arch.py, and commit. The validator's A-009
immutability gate exempts baseline ADRs that predate frontmatter, so this
one-time injection lands cleanly; from the next commit on, accepted ADRs are
frozen except the supersede transition.
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import yaml  # noqa: E402
from validate_arch import parse_md  # noqa: E402
from stamp_fingerprint import stamp_architecture  # noqa: E402

DATE_RE = re.compile(r"^\s*-\s*\*\*Date:\*\*\s*(\d{4}-\d{2}-\d{2})", re.M)
SUPERSEDES_RE = re.compile(r"^\s*-\s*\*\*Supersedes:\*\*\s*(ADR-\d{4})", re.M)


def build_adr_frontmatter(entry, body):
    """The v2.0 ADR frontmatter from a v1.0 index entry + body-parsed fields."""
    date = DATE_RE.search(body or "")
    supersedes = SUPERSEDES_RE.search(body or "")
    return {
        "id": str(entry.get("id") or ""),
        "title": str(entry.get("title") or ""),
        "status": str(entry.get("status") or "proposed"),
        "date": date.group(1) if date else "",
        "scope": str(entry.get("scope") or "feature"),
        "confidence": str(entry.get("confidence") or "assumption"),
        "supersedes": supersedes.group(1) if supersedes else "",
        "superseded_by": str(entry.get("superseded_by") or ""),
        "governs": list(entry.get("governs") or []),
    }


def write_md(path, doc, body):
    dumped = yaml.safe_dump(doc, sort_keys=False, default_flow_style=False,
                            allow_unicode=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("---\n" + dumped + "---\n" + (body or ""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec_dir", nargs="?", default="docs/product")
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would change; write nothing")
    args = ap.parse_args()
    spec_dir = args.spec_dir

    yaml_path = os.path.join(spec_dir, "arch-data.yaml")
    if not os.path.isfile(yaml_path):
        print(f"nothing to migrate: no arch-data.yaml under {spec_dir} "
              "(already on the single-file layout, or no architecture yet)")
        sys.exit(0)
    try:
        with open(yaml_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        print(f"ERROR: cannot parse {yaml_path}: {e}", file=sys.stderr)
        sys.exit(2)

    arch_md_path = os.path.join(spec_dir, "architecture.md")
    if not os.path.isfile(arch_md_path):
        print(f"ERROR: no architecture.md under {spec_dir} -- the narrative file "
              "is required (the migration injects its frontmatter, it does not "
              "author the narrative)", file=sys.stderr)
        sys.exit(2)

    index = {str(d.get("id")): d for d in (data.get("decisions") or [])
             if isinstance(d, dict) and d.get("id")}
    dec_dir = os.path.join(spec_dir, "decisions")
    injected, skipped, unindexed = [], [], []

    # ---- 1. inject ADR frontmatter --------------------------------------
    if os.path.isdir(dec_dir):
        for name in sorted(os.listdir(dec_dir)):
            mo = re.match(r"^(ADR-\d{4})", name)
            if not (mo and name.endswith(".md")):
                continue
            did = mo.group(1)
            path = os.path.join(dec_dir, name)
            with open(path, encoding="utf-8") as f:
                doc, body = parse_md(f.read())
            if doc:
                skipped.append(did)  # already migrated -- idempotent
                continue
            if did not in index:
                unindexed.append(did)  # not in the index; a human decides
                continue
            fm = build_adr_frontmatter(index[did], body)
            if not args.dry_run:
                write_md(path, fm, body)
            injected.append(did)
    orphan_entries = sorted(set(index) - set(injected) - set(skipped))

    # ---- 2. architecture.md frontmatter ----------------------------------
    with open(arch_md_path, encoding="utf-8") as f:
        old_doc, arch_body = parse_md(f.read())
    old_meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    new_doc = {
        "meta": {
            "doc_type": "spec-arch",
            "schema_version": "2.0",
            "project_id": str(old_meta.get("project_id") or ""),
            "project_name": str(old_meta.get("project_name")
                                or (old_doc or {}).get("project_name") or ""),
            "status": str(old_meta.get("status")
                          or (old_doc or {}).get("status") or "draft"),
            "arch_version": "",
            "fingerprint": "",
        },
        "context": str(data.get("context") or ""),
        "components": list(data.get("components") or []),
        "integrations": list(data.get("integrations") or []),
        "diagrams": list(data.get("diagrams") or ["context"]),
    }
    if not args.dry_run:
        write_md(arch_md_path, new_doc, arch_body)
        # ---- 3. delete the derived copy and re-stamp the signed file -----
        os.remove(yaml_path)
        stamp_architecture(spec_dir)

    # ---- report -----------------------------------------------------------
    verb = "would migrate" if args.dry_run else "migrated"
    print(f"{verb} {spec_dir} to the single-file layout (schema v2.0):")
    print(f"  ADR frontmatter injected : {len(injected)}"
          + (f" ({', '.join(injected)})" if injected else ""))
    if skipped:
        print(f"  already had frontmatter  : {len(skipped)} ({', '.join(skipped)})")
    if unindexed:
        print(f"  WARN not in the index    : {len(unindexed)} "
              f"({', '.join(unindexed)}) -- add frontmatter by hand "
              "(assets/adr-template.md)")
    if orphan_entries:
        print(f"  WARN index without file  : {len(orphan_entries)} "
              f"({', '.join(orphan_entries)}) -- the entry was dropped; "
              "restore the ADR file or record the loss")
    print("  architecture.md          : frontmatter "
          + ("written + stamped, arch-data.yaml deleted" if not args.dry_run
             else "would be written; arch-data.yaml would be deleted"))
    if not args.dry_run:
        print("next: git add -A && python scripts/validate_arch.py "
              f"{spec_dir} && commit")
    sys.exit(0)


if __name__ == "__main__":
    main()
