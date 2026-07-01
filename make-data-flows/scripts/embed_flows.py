#!/usr/bin/env python3
"""Embed generated Mermaid flows into feature bodies -- the deterministic writer.

The skill (an LLM orchestrator) runs a sub-agent per feature to author the
mermaid, assembles a JSON payload, and hands it to this script. This script does
the SAFE part deterministically: marker-anchored region surgery that

  - rewrites ONLY the feature body's make-data-flows:flows region (or appends one),
  - preserves the YAML frontmatter BYTE-FOR-BYTE (never re-dumped), so the feature
    fingerprint cannot move,
  - preserves the human narrative outside the region (defensive asserts, mirroring
    make-issues' managed-region surgery),
  - is byte-identical on a no-op: when nothing but the timestamp would change, the
    prior generated_at is reused so re-running makes no git diff (make-trace's guard).

Payload (a file path arg, or stdin when the arg is '-'):

  {
    "features": {
      "checkout": {
        "flows": [
          {"id":"DF-CHK-01","kind":"data","covers":["FR-CHK-001","IR-CHK-001"],
           "title":"Place order","mermaid":"sequenceDiagram\\n  ..."},
          {"id":"UF-CHK-01","kind":"user","covers":["FR-CHK-001"],
           "mermaid":"flowchart TD\\n  ..."}
        ]
      }
    }
  }

  python scripts/embed_flows.py docs/specs payload.json [--now ISO8601]

The stamp's feature_version is read from each feature's CURRENT frontmatter (not
the payload), so it always records the version the flows were embedded against.

Exit codes: 0 = wrote or byte-identical no-op; 1 = a defensive assert failed (a
human edited the markers, or the payload named a missing feature) -- nothing is
written for that feature; 2 = file/parse/arg error.
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from flowlib import (  # noqa: E402
    FLOWS_CLOSE, FLOWS_OPEN, FLOW_CLOSE, SCHEMA_VERSION, feature_files,
    feature_meta, find_regions, parse_stamp, split_frontmatter,
)

try:
    import yaml
except ImportError:  # pragma: no cover
    print("PyYAML is required: pip install pyyaml --break-system-packages", file=sys.stderr)
    sys.exit(2)

TS_PLACEHOLDER = "__MDF_TS__"
_TS_LINE_RE = re.compile(r"generated_at:[^\n]*")


class EmbedError(Exception):
    """A defensive assert failed -- do not write this feature."""


def build_region(feature_version, flows, generated_at):
    """The full make-data-flows:flows region as text (no trailing newline)."""
    stamp = {
        "schema_version": SCHEMA_VERSION,
        "feature_version": feature_version,
        "generated_at": generated_at,
        "flow_count": len(flows),
    }
    stamp_yaml = yaml.safe_dump(
        stamp, sort_keys=False, default_flow_style=False, allow_unicode=True
    ).rstrip("\n")
    out = [FLOWS_OPEN, "<!-- make-data-flows:stamp", stamp_yaml, "-->"]
    for f in flows:
        covers = ",".join(f.get("covers") or [])
        out.append(f"<!-- make-data-flows:flow id={f['id']} kind={f['kind']} covers={covers} -->")
        if f.get("title"):
            out.append(f"_{f['title']}_")
        out.append("```mermaid")
        out.append((f.get("mermaid") or "").rstrip("\n"))
        out.append("```")
        out.append(FLOW_CLOSE)
    out.append(FLOWS_CLOSE)
    return "\n".join(out)


def _excise(body):
    """(body-with-the-region-removed, region_count). The region-removed text is
    the human-owned portion we must never alter."""
    matches = find_regions(body)
    if not matches:
        return body, 0
    m = matches[0]
    return body[: m.start()] + body[m.end():], len(matches)


def _validate_flows_payload(flows):
    for f in flows:
        if not isinstance(f, dict) or not f.get("id") or f.get("kind") not in ("data", "user"):
            raise EmbedError(f"malformed flow entry: {f!r}")
        if not (f.get("mermaid") or "").strip():
            raise EmbedError(f"flow {f.get('id')} has empty mermaid")


def embed_feature(path, flows, now):
    """Rewrite one feature file's region from `flows`. Returns one of
    'wrote' | 'noop'. Raises EmbedError on a defensive-assert failure."""
    _validate_flows_payload(flows)
    with open(path, encoding="utf-8") as f:
        text = f.read()
    head, body, doc = split_frontmatter(text)
    slug, _prefix, feature_version, _status = feature_meta(doc)
    if not head:
        raise EmbedError(f"{path}: no YAML frontmatter (is this a feature spec?)")

    existing = find_regions(body)
    if len(existing) > 1:
        raise EmbedError(f"{path}: {len(existing)} make-data-flows:flows regions "
                         "(expected 0 or 1) -- a human likely edited the markers")

    # No-op guard: build the region with the timestamp nulled and compare to the
    # existing region nulled. Equal -> reuse the old timestamp so bytes match.
    candidate_nulled = build_region(feature_version, flows, TS_PLACEHOLDER)
    generated_at = now
    if existing:
        old_region = existing[0].group(0)
        old_nulled = _TS_LINE_RE.sub(f"generated_at: {TS_PLACEHOLDER}", old_region)
        if old_nulled == candidate_nulled:
            old_ts = parse_stamp(existing[0].group("inner")).get("generated_at")
            if old_ts:
                generated_at = old_ts

    region = build_region(feature_version, flows, generated_at)

    if existing:
        m = existing[0]
        new_body = body[: m.start()] + region + body[m.end():]
    else:
        if body and not body.endswith("\n"):
            body += "\n"
        sep = "" if body.endswith("\n\n") or not body else "\n"
        new_body = body + sep + region + "\n"

    # Defensive asserts (the make-issues discipline): exactly one region now, and
    # the human-owned text outside it is unchanged.
    human_before, _ = _excise(body)
    human_after, count_after = _excise(new_body)
    if count_after != 1:
        raise EmbedError(f"{path}: post-embed region count {count_after} != 1")
    if human_before.rstrip() != human_after.rstrip():
        raise EmbedError(f"{path}: human narrative outside the region would change -- aborting")
    if new_body.count(FLOW_CLOSE) != len(flows):
        raise EmbedError(f"{path}: flow-close marker count != flow count")

    out_text = head + new_body
    if out_text == text:
        return "noop"
    with open(path, "w", encoding="utf-8") as f:
        f.write(out_text)
    return "wrote"


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec_dir", help="docs/specs (or its features/ dir, or one feature file)")
    ap.add_argument("payload", help="JSON payload path, or '-' for stdin")
    ap.add_argument("--now", help="ISO-8601 timestamp for generated_at (default: now, UTC)")
    args = ap.parse_args()

    try:
        raw = sys.stdin.read() if args.payload == "-" else open(args.payload, encoding="utf-8").read()
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERROR: cannot read payload: {e}", file=sys.stderr)
        sys.exit(2)

    now = args.now or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    by_slug = {slug: path for slug, path in feature_files(args.spec_dir)}
    features = (payload or {}).get("features") or {}
    if not features:
        print("no features in payload -- nothing to embed")
        sys.exit(0)

    failed = False
    for slug, spec in features.items():
        path = by_slug.get(slug)
        if not path:
            print(f"ERROR: feature '{slug}' not found under {args.spec_dir}", file=sys.stderr)
            failed = True
            continue
        try:
            result = embed_feature(path, spec.get("flows") or [], now)
        except (EmbedError, OSError) as e:
            # A defensive-assert failure or a file read/write error on one feature
            # must not crash the run -- report it and keep processing the rest.
            print(f"ERROR: {e}", file=sys.stderr)
            failed = True
            continue
        print(f"{result:5s} {path}  ({len(spec.get('flows') or [])} flows)")

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
