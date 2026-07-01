#!/usr/bin/env python3
"""Shared helpers for make-data-flows -- the marker grammar, the frontmatter
split, and the flow-region parser used by flow_status.py, embed_flows.py, and
validate_flows.py.

make-data-flows embeds Mermaid data-flow + user-flow diagrams into a feature's
markdown BODY inside one marker-anchored managed region. The region lives in the
body, NOT the frontmatter, so it is out of make-spec's fingerprint (which hashes
only the parsed frontmatter) and can never trip the S-006 integrity gate. The
frontmatter bytes are preserved verbatim on every write.

The region shape (one per feature):

    <!-- make-data-flows:flows -->
    <!-- make-data-flows:stamp
    schema_version: "1.0"
    feature_version: 4e462b08a5ee
    generated_at: 2026-07-01T00:00:00Z
    flow_count: 2
    -->
    <!-- make-data-flows:flow id=DF-CHK-01 kind=data covers=FR-CHK-001,IR-CHK-001 -->
    ```mermaid
    sequenceDiagram
      ...
    ```
    <!-- /make-data-flows:flow -->
    <!-- /make-data-flows:flows -->

The stamp's `feature_version` is the staleness oracle: it records the
make-spec feature_version the flows were generated from. A later run compares it
to the feature's current feature_version (equal -> SKIP, differ -> REGENERATE),
so an advisory-only edit (priority/notes -- an OUT field that never moves the
feature fingerprint) never triggers regeneration.
"""
import glob
import os
import re

try:
    import yaml
except ImportError:  # pragma: no cover - environment guard
    import sys
    print("PyYAML is required: pip install pyyaml --break-system-packages",
          file=sys.stderr)
    sys.exit(2)

SCHEMA_VERSION = "1.0"

# ── ID grammars (mirror make-spec) ───────────────────────────────────────────
REQ_ID_RE = re.compile(r"^(FR|IR|NFR|CR)-[A-Z]{2,5}-\d{3,}$")
DATA_FLOW_ID_RE = re.compile(r"^DF-[A-Z]{2,5}-\d{2,}$")
USER_FLOW_ID_RE = re.compile(r"^UF-[A-Z]{2,5}-\d{2,}$")

# ── Marker grammar ───────────────────────────────────────────────────────────
FLOWS_OPEN = "<!-- make-data-flows:flows -->"
FLOWS_CLOSE = "<!-- /make-data-flows:flows -->"
FLOW_CLOSE = "<!-- /make-data-flows:flow -->"

# The whole managed region, captured non-greedily so a stray second open marker
# is caught (validate_flows DF-001 asserts exactly one).
REGION_RE = re.compile(
    re.escape(FLOWS_OPEN) + r"(?P<inner>.*?)" + re.escape(FLOWS_CLOSE),
    re.DOTALL,
)
STAMP_RE = re.compile(
    r"<!-- make-data-flows:stamp\s*\n(?P<yaml>.*?)\n-->",
    re.DOTALL,
)
# One flow block: the open marker (with attributes), its body, and the close.
FLOW_RE = re.compile(
    r"<!-- make-data-flows:flow\s+(?P<attrs>[^>]*?)-->"
    r"(?P<body>.*?)"
    + re.escape(FLOW_CLOSE),
    re.DOTALL,
)
MERMAID_RE = re.compile(r"```mermaid\s*\n(?P<src>.*?)\n```", re.DOTALL)

# Known mermaid diagram kinds we generate, by flow kind. The signature is the
# first non-empty content line's leading keyword (case-insensitive).
DATA_MERMAID_KINDS = {"sequencediagram", "flowchart", "graph", "erdiagram"}
USER_MERMAID_KINDS = {"flowchart", "graph", "journey", "statediagram", "statediagram-v2"}

# ── Frontmatter split (mirror make-spec / make-issues) ───────────────────────
# The match span covers the whole frontmatter block INCLUDING both `---`
# delimiters and the trailing newline, so head = text[:end] can be written back
# byte-for-byte and only the body is ever rewritten.
FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL)


def split_frontmatter(text):
    """Return (head, body, doc).

    head -- the raw frontmatter block incl. both `---` fences and trailing
            newline, to be written back VERBATIM (never re-dumped).
    body -- everything after the frontmatter.
    doc  -- the parsed frontmatter mapping ({} when absent / not a mapping).

    A file with no frontmatter returns ("", text, {}).
    """
    if text.startswith("﻿"):
        text = text[1:]
    m = FRONTMATTER_RE.match(text)
    if not m:
        return "", text, {}
    head = text[: m.end()]
    body = text[m.end():]
    try:
        doc = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        doc = {}
    if not isinstance(doc, dict):
        doc = {}
    return head, body, doc


def feature_files(spec_dir):
    """[(slug, path)] for every features/<slug>.md under a spec dir.

    Accepts the spec dir (docs/specs -> docs/specs/features/*.md), the features/
    subdir itself, or a single feature .md file.
    """
    if os.path.isfile(spec_dir):
        slug = os.path.splitext(os.path.basename(spec_dir))[0]
        return [(slug, spec_dir)]
    feats = os.path.join(spec_dir, "features")
    search_dir = feats if os.path.isdir(feats) else spec_dir
    out = []
    for path in sorted(glob.glob(os.path.join(search_dir, "*.md"))):
        out.append((os.path.splitext(os.path.basename(path))[0], path))
    return out


def feature_meta(doc):
    """The (slug, prefix, feature_version, status) tuple from a feature doc."""
    meta = doc.get("meta") or {}
    return (
        meta.get("slug"),
        meta.get("prefix"),
        str(meta.get("feature_version") or ""),
        meta.get("status") or "active",
    )


def active_requirement_ids(doc):
    """Set of requirement ids whose status is active (default active)."""
    out = set()
    for req in doc.get("requirements") or []:
        if isinstance(req, dict) and req.get("id"):
            if (req.get("status") or "active") == "active":
                out.add(str(req["id"]))
    return out


def all_requirement_ids(doc):
    """Set of every requirement id in the feature, any status."""
    return {
        str(req["id"])
        for req in (doc.get("requirements") or [])
        if isinstance(req, dict) and req.get("id")
    }


# ── Region parsing ───────────────────────────────────────────────────────────
def parse_attrs(attr_str):
    """Parse `id=DF-CHK-01 kind=data covers=FR-CHK-001,IR-CHK-001` into a dict.

    Values are whitespace-delimited and may contain commas (never spaces). A
    `covers` value is additionally split into a list on commas.
    """
    attrs = {}
    for tok in attr_str.split():
        if "=" not in tok:
            continue
        key, _, val = tok.partition("=")
        attrs[key.strip()] = val.strip()
    if "covers" in attrs:
        attrs["covers"] = [c for c in attrs["covers"].split(",") if c]
    return attrs


def find_regions(body):
    """Every make-data-flows:flows region match in the body (list of re.Match).

    More than one means a corrupted / hand-duplicated region (DF-001 fails).
    """
    return list(REGION_RE.finditer(body))


def parse_stamp(inner):
    """Parse the stamp YAML out of a region's inner text. Returns {} when absent
    or unparseable (validate_flows distinguishes the two)."""
    m = STAMP_RE.search(inner)
    if not m:
        return {}
    try:
        data = yaml.safe_load(m.group("yaml"))
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def parse_flows(inner):
    """[(attrs_dict, mermaid_src_or_None)] for each flow block in a region's
    inner text, in document order."""
    flows = []
    for m in FLOW_RE.finditer(inner):
        attrs = parse_attrs(m.group("attrs"))
        mm = MERMAID_RE.search(m.group("body"))
        flows.append((attrs, mm.group("src") if mm else None))
    return flows


def mermaid_kind(src):
    """The leading keyword of a mermaid source block, lowercased (e.g.
    'sequencediagram', 'flowchart'). '' when empty."""
    if not src:
        return ""
    for line in src.splitlines():
        line = line.strip()
        if line:
            # 'flowchart TD' -> 'flowchart'; 'stateDiagram-v2' stays whole.
            return line.split()[0].lower()
    return ""
