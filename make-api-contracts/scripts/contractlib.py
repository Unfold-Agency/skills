#!/usr/bin/env python3
"""Shared helpers for make-api-contracts.

This skill derives an OpenAPI 3.1 contract for the project's OWN API surface from
the make-spec requirements (their `interface` sketches and `IR-*` integration reqs),
the make-data-flows diagrams (which show which calls a feature makes), and the
make-arch integrations/ADRs (referenced, never redefined). The primary artifact is
`docs/product/api/openapi.yaml` (a mock server ingests it directly); a read-only
`API-CONTRACTS.md` is rendered from it, and `.make-api-sync.json` is the sidecar
ledger.

The LLM authors each operation's shape (the fuzzy judgment); these deterministic
helpers do the safe parts: canonical serialization (byte-stable output), the
frontmatter/flow-region readers, and the no-op guard.
"""
import glob
import os
import re

try:
    import yaml
except ImportError:  # pragma: no cover
    import sys
    print("PyYAML is required: pip install pyyaml --break-system-packages", file=sys.stderr)
    sys.exit(2)

SCHEMA_VERSION = "1.0"
OPENAPI_VERSION = "3.1.0"

# ── ID / name grammars ───────────────────────────────────────────────────────
REQ_ID_RE = re.compile(r"^(FR|IR|NFR|CR)-[A-Z]{2,5}-\d{3,}$")
ADR_ID_RE = re.compile(r"^ADR-\d{4}$")
# operationId = <feature-slug>.<verbResource>, e.g. checkout.createOrder
OPERATION_ID_RE = re.compile(r"^[a-z][a-z0-9-]*\.[a-z][a-zA-Z0-9]*$")
HTTP_METHODS = ("get", "put", "post", "delete", "patch", "head", "options", "trace")

# The provenance vendor extensions (mirror make-issues meta stamping).
X_TRACE_REQ = "x-trace-req"
X_FEATURE = "x-feature"
X_SOURCE_VERSION = "x-source-version"
X_TRACE_ADR = "x-trace-adr"
X_INTEGRATION = "x-integration"
X_OP_FP = "x-op-fingerprint"
X_FLOW = "x-flow"
X_STATUS = "x-status"

# Human-owned fields on an operation -- preserved verbatim across an upsert (the
# make-issues "never clobber the human region" doctrine, at operation altitude).
HUMAN_OP_FIELDS = ("summary", "description", "x-notes")


def as_list(value):
    """Coerce a value into a list. None -> []; a bare scalar (e.g. a string a
    payload/YAML author wrote instead of a list) -> [value]; a list/tuple ->
    list(value). Guards against iterating a string character-by-character, which
    would shred `trace_req: IR-CHK-001` into single-character ids."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]

# ── Frontmatter split (mirror make-spec / make-data-flows) ───────────────────
FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL)


def split_frontmatter(text):
    """(head, body, doc) -- head is the raw frontmatter block (verbatim), body is
    the rest, doc is the parsed mapping ({} when absent/invalid)."""
    if text.startswith("﻿"):
        text = text[1:]
    m = FRONTMATTER_RE.match(text)
    if not m:
        return "", text, {}
    try:
        doc = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        doc = {}
    if not isinstance(doc, dict):
        doc = {}
    return text[: m.end()], text[m.end():], doc


def feature_files(spec_dir):
    """[(slug, path)] for every features/<slug>.md under a spec dir."""
    if os.path.isfile(spec_dir):
        return [(os.path.splitext(os.path.basename(spec_dir))[0], spec_dir)]
    feats = os.path.join(spec_dir, "features")
    search = feats if os.path.isdir(feats) else spec_dir
    return [(os.path.splitext(os.path.basename(p))[0], p)
            for p in sorted(glob.glob(os.path.join(search, "*.md")))]


# ── make-data-flows handshake: which requirements a feature has a flow for ───
FLOW_COVERS_RE = re.compile(
    r"<!-- make-data-flows:flow\s+[^>]*?covers=(?P<covers>[^\s>]*)[^>]*?-->")


def flow_covered_reqs(body):
    """Set of requirement ids that a make-data-flows flow in this body covers.
    Empty when the feature has no flows region (make-data-flows not run yet)."""
    covered = set()
    for m in FLOW_COVERS_RE.finditer(body):
        for cid in m.group("covers").split(","):
            cid = cid.strip()
            if cid:
                covered.add(cid)
    return covered


def read_features(spec_dir):
    """{slug: {path, prefix, feature_version, status, requirements, covered}}.

    requirements is {req_id: {kind, interface, governed_by, status}}; covered is
    the set of req ids with a make-data-flows flow (the handshake signal)."""
    out = {}
    for slug, path in feature_files(spec_dir):
        with open(path, encoding="utf-8") as f:
            text = f.read()
        _head, body, doc = split_frontmatter(text)
        meta = doc.get("meta")
        if not isinstance(meta, dict):
            meta = {}
        requirements = doc.get("requirements")
        if not isinstance(requirements, list):
            requirements = []
        reqs = {}
        for r in requirements:
            if isinstance(r, dict) and r.get("id"):
                reqs[str(r["id"])] = {
                    "kind": r.get("kind"),
                    "interface": r.get("interface") or "",
                    "governed_by": [str(x) for x in as_list(r.get("governed_by"))],
                    "status": r.get("status") or "active",
                }
        out[meta.get("slug") or slug] = {
            "path": path,
            "prefix": meta.get("prefix"),
            "feature_version": str(meta.get("feature_version") or ""),
            "status": meta.get("status") or "active",
            "requirements": reqs,
            "covered": flow_covered_reqs(body),
        }
    return out


def _integration_ids(integrations):
    """Synthesized INTG-<normalized-name> ids from an integrations list."""
    intgs = set()
    for i in integrations if isinstance(integrations, list) else []:
        if isinstance(i, dict) and i.get("name"):
            norm = re.sub(r"[^a-z0-9]+", "-", str(i["name"]).lower()).strip("-")
            intgs.add(f"INTG-{norm}")
    return intgs


def read_arch(spec_dir):
    """(adr_ids, integration_ids) from the architecture layer, dual-read. Primary
    is v2.0: architecture.md whose frontmatter carries a NESTED meta.doc_type ==
    "spec-arch" (integrations) plus decisions/ADR-*.md frontmatters (adr ids); a
    legacy architecture.md (flat doc_type, no meta) never matches, so the legacy
    arch-data.yaml is the fallback. Empty sets when absent (lite mode) or
    unreadable -- this lib stays quiet; the validator reports the gaps.
    Integration ids are synthesized INTG-<normalized-name>, matching make-trace."""
    md_path = os.path.join(spec_dir, "architecture.md")
    if os.path.isfile(md_path):
        try:
            with open(md_path, encoding="utf-8") as f:
                _head, _body, doc = split_frontmatter(f.read())
        except (OSError, ValueError):
            doc = {}
        meta = doc.get("meta")
        if isinstance(meta, dict) and meta.get("doc_type") == "spec-arch":
            adrs = set()
            for path in sorted(glob.glob(os.path.join(spec_dir, "decisions",
                                                      "ADR-*.md"))):
                try:
                    with open(path, encoding="utf-8") as f:
                        _h, _b, adr = split_frontmatter(f.read())
                except (OSError, ValueError):
                    continue
                if adr.get("id"):
                    adrs.add(str(adr["id"]))
            return adrs, _integration_ids(doc.get("integrations"))
    path = os.path.join(spec_dir, "arch-data.yaml")
    if not os.path.isfile(path):
        return set(), set()
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError):
        return set(), set()
    if not isinstance(data, dict):
        return set(), set()
    decisions = data.get("decisions")
    decisions = decisions if isinstance(decisions, list) else []
    adrs = {str(d.get("id")) for d in decisions if isinstance(d, dict) and d.get("id")}
    return adrs, _integration_ids(data.get("integrations"))


def active_req_ids(features):
    """Set of every active requirement id across all features."""
    out = set()
    for f in features.values():
        for rid, r in f["requirements"].items():
            if r["status"] == "active":
                out.add(rid)
    return out


def all_req_ids(features):
    out = set()
    for f in features.values():
        out.update(f["requirements"].keys())
    return out


# ── OpenAPI canonicalization + no-op guard ───────────────────────────────────
_TOP_ORDER = ["openapi", "info", "servers", "tags", "paths", "components"]
_OP_ORDER = ["operationId", "tags", "summary", "description",
             X_TRACE_REQ, X_FEATURE, X_SOURCE_VERSION, X_TRACE_ADR,
             X_INTEGRATION, X_FLOW, X_STATUS, X_OP_FP, "deprecated",
             "parameters", "requestBody", "responses", "x-notes"]


def _ordered(d, order):
    """A new dict with `order` keys first (when present), then the rest sorted."""
    out = {}
    for k in order:
        if k in d:
            out[k] = d[k]
    for k in sorted(d):
        if k not in out:
            out[k] = d[k]
    return out


def canonical_doc(doc):
    """Return a deterministically-ordered copy: fixed top-level section order,
    paths sorted by path then method, operations key-ordered, schemas sorted.
    Byte-stable output across runs (safe_dump sort_keys=False on this)."""
    out = _ordered(doc, _TOP_ORDER)
    paths = out.get("paths")
    if not isinstance(paths, dict):
        paths = {}
    out["paths"] = {
        p: ({m: _ordered(paths[p][m], _OP_ORDER) if isinstance(paths[p][m], dict) else paths[p][m]
             for m in sorted(paths[p])} if isinstance(paths[p], dict) else paths[p])
        for p in sorted(paths)
    }
    comp = out.get("components")
    if isinstance(comp, dict) and isinstance(comp.get("schemas"), dict):
        comp["schemas"] = {k: comp["schemas"][k] for k in sorted(comp["schemas"])}
    return out


def dump_doc(doc):
    """Serialize a doc canonically. `width` is large so long URLs/descriptions
    are not line-wrapped (wrapping would churn the bytes)."""
    return yaml.safe_dump(canonical_doc(doc), sort_keys=False,
                          default_flow_style=False, allow_unicode=True, width=4096)


def strip_volatile(doc):
    """A deep-ish copy with the volatile/self info keys nulled, for the no-op
    compare and the doc fingerprint. Only info-level keys are volatile."""
    import copy
    d = copy.deepcopy(doc)
    info = d.get("info")
    if isinstance(info, dict):
        for k in ("x-generated", "x-fingerprint", "x-contract-version"):
            info.pop(k, None)
    return d
