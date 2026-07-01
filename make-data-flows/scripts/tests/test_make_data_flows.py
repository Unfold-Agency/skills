"""Tests for make-data-flows: embed surgery, no-op guard, planner, validator."""
import os

import pytest
import yaml

import embed_flows
import flow_status
import validate_flows
from flowlib import find_regions, parse_stamp, split_frontmatter
from validate_spec import compute_fingerprint  # make-spec, via conftest sys.path


# ── fixtures ─────────────────────────────────────────────────────────────────
def _req(rid, kind="functional"):
    return {
        "id": rid,
        "name": rid,
        "kind": kind,
        "description": f"The system does {rid}.",
        "acceptance_criteria": [
            "The system shall do the thing.",
            "IF it fails, THEN the system shall report an error.",
        ],
        "governed_by": [],
        "depends_on": [],
        "interface": "POST /thing { id }",
        "priority": "must",
        "status": "active",
    }


def make_feature(features_dir, slug, prefix, reqs, body="\n# Title\n\nHuman narrative.\n"):
    """Write features/<slug>.md with a REAL make-spec fingerprint stamped, and
    return (path, feature_version)."""
    doc = {
        "meta": {
            "doc_type": "spec-feature",
            "schema_version": "1.0",
            "slug": slug,
            "prefix": prefix,
            "title": slug.title(),
            "status": "active",
        },
        "user_stories": ["As a user, I want a thing, so that benefit."],
        "no_gos": [],
        "supports": [],
        "requirements": reqs,
    }
    fp = compute_fingerprint(doc)
    doc["meta"]["fingerprint"] = fp
    doc["meta"]["feature_version"] = fp[:12]
    text = "---\n" + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True) + "---\n" + body
    os.makedirs(features_dir, exist_ok=True)
    path = os.path.join(features_dir, f"{slug}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path, fp[:12]


@pytest.fixture
def spec_dir(tmp_path):
    d = tmp_path / "docs" / "specs"
    feats = d / "features"
    make_feature(str(feats), "checkout", "CHK",
                 [_req("FR-CHK-001"), _req("IR-CHK-001", "integration")])
    make_feature(str(feats), "cart", "CART", [_req("FR-CART-001")])
    return str(d)


def _payload(slug, flows):
    return {"features": {slug: {"flows": flows}}}


DATA_FLOW = {"id": "DF-CHK-01", "kind": "data", "covers": ["FR-CHK-001", "IR-CHK-001"],
             "title": "Place order", "mermaid": "sequenceDiagram\n  U->>S: order\n  S-->>U: ok"}
USER_FLOW = {"id": "UF-CHK-01", "kind": "user", "covers": ["FR-CHK-001"],
             "mermaid": "flowchart TD\n  A[Start] --> B[Checkout]"}


# ── embed: creation + frontmatter preservation ───────────────────────────────
def test_embed_creates_region_preserves_frontmatter(spec_dir):
    path = os.path.join(spec_dir, "features", "checkout.md")
    before = open(path, encoding="utf-8").read()
    head_before, _, doc_before = split_frontmatter(before)
    fp_before = doc_before["meta"]["fingerprint"]

    res = embed_flows.embed_feature(path, [DATA_FLOW, USER_FLOW], "2026-07-01T00:00:00Z")
    assert res == "wrote"

    after = open(path, encoding="utf-8").read()
    head_after, body_after, doc_after = split_frontmatter(after)
    # Frontmatter is byte-identical -> the fingerprint cannot have moved.
    assert head_before == head_after
    assert doc_after["meta"]["fingerprint"] == fp_before
    assert compute_fingerprint(doc_after) == fp_before  # DF-006 strong path
    # Region present with both flows and a stamp recording the live version.
    regions = find_regions(body_after)
    assert len(regions) == 1
    stamp = parse_stamp(regions[0].group("inner"))
    assert stamp["feature_version"] == doc_after["meta"]["feature_version"]
    assert stamp["flow_count"] == 2
    assert "sequenceDiagram" in body_after and "flowchart TD" in body_after
    assert "Human narrative." in body_after


def test_embed_noop_is_byte_identical(spec_dir):
    path = os.path.join(spec_dir, "features", "checkout.md")
    embed_flows.embed_feature(path, [DATA_FLOW], "2026-07-01T00:00:00Z")
    first = open(path, encoding="utf-8").read()
    # Re-embed identical flows with a DIFFERENT timestamp -> must reuse the old
    # generated_at and produce a byte-identical file (no git churn).
    res = embed_flows.embed_feature(path, [DATA_FLOW], "2099-12-31T23:59:59Z")
    assert res == "noop"
    assert open(path, encoding="utf-8").read() == first


def test_embed_updates_region_in_place(spec_dir):
    path = os.path.join(spec_dir, "features", "checkout.md")
    embed_flows.embed_feature(path, [DATA_FLOW], "2026-07-01T00:00:00Z")
    embed_flows.embed_feature(path, [DATA_FLOW, USER_FLOW], "2026-07-02T00:00:00Z")
    body = split_frontmatter(open(path, encoding="utf-8").read())[1]
    regions = find_regions(body)
    assert len(regions) == 1  # replaced in place, not duplicated
    assert parse_stamp(regions[0].group("inner"))["flow_count"] == 2


def test_embed_aborts_on_duplicated_markers(spec_dir):
    path = os.path.join(spec_dir, "features", "checkout.md")
    embed_flows.embed_feature(path, [DATA_FLOW], "2026-07-01T00:00:00Z")
    # Simulate a human duplicating the managed region.
    text = open(path, encoding="utf-8").read()
    region = find_regions(split_frontmatter(text)[1])[0].group(0)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text + "\n" + region + "\n")
    with pytest.raises(embed_flows.EmbedError):
        embed_flows.embed_feature(path, [DATA_FLOW], "2026-07-03T00:00:00Z")


def test_embed_rejects_empty_mermaid(spec_dir):
    path = os.path.join(spec_dir, "features", "checkout.md")
    bad = {"id": "DF-CHK-01", "kind": "data", "covers": ["FR-CHK-001"], "mermaid": "   "}
    with pytest.raises(embed_flows.EmbedError):
        embed_flows.embed_feature(path, [bad], "2026-07-01T00:00:00Z")


# ── flow_status: create / skip / regenerate + scope ──────────────────────────
def test_plan_create_then_skip_then_regenerate(spec_dir):
    plan = flow_status.build_plan(spec_dir, scope=[], force=False)
    actions = {f["slug"]: f["action"] for f in plan["features"]}
    assert actions == {"checkout": "CREATE", "cart": "CREATE"}
    assert not plan["blocking"]

    # Embed checkout with its current version -> SKIP next plan.
    ck = os.path.join(spec_dir, "features", "checkout.md")
    embed_flows.embed_feature(ck, [DATA_FLOW], "2026-07-01T00:00:00Z")
    plan = flow_status.build_plan(spec_dir, scope=[], force=False)
    actions = {f["slug"]: f["action"] for f in plan["features"]}
    assert actions["checkout"] == "SKIP"
    assert actions["cart"] == "CREATE"

    # Change checkout's contract (re-stamp) -> REGENERATE.
    _mutate_and_restamp(ck)
    plan = flow_status.build_plan(spec_dir, scope=[], force=False)
    ck_entry = next(f for f in plan["features"] if f["slug"] == "checkout")
    assert ck_entry["action"] == "REGENERATE"
    assert "contract moved" in ck_entry["reason"]


def test_plan_scope_bounds_writes_but_detects_globally(spec_dir):
    # Both stale (no region yet), but scope to checkout only.
    plan = flow_status.build_plan(spec_dir, scope=["checkout"], force=False)
    assert plan["actionable"] == ["checkout"]
    assert plan["out_of_scope_stale"] == ["cart"]  # detected, not actioned
    assert not plan["blocking"]


def test_plan_blocks_on_unknown_feature(spec_dir):
    plan = flow_status.build_plan(spec_dir, scope=["nope"], force=False)
    assert plan["blocking"]


def test_force_regenerates_fresh_feature(spec_dir):
    plan = flow_status.build_plan(spec_dir, scope=[], force=True)
    assert all(f["action"] == "REGENERATE" for f in plan["features"])


def _mutate_and_restamp(path):
    """Change a requirement's contract and re-stamp the fingerprint like make-spec."""
    head, body, doc = split_frontmatter(open(path, encoding="utf-8").read())
    doc["requirements"][0]["description"] = "A materially different behavior now."
    fp = compute_fingerprint(doc)
    doc["meta"]["fingerprint"] = fp
    doc["meta"]["feature_version"] = fp[:12]
    text = "---\n" + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True) + "---\n" + body
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


# ── validate_flows ───────────────────────────────────────────────────────────
def test_validate_clean_region_passes(spec_dir):
    ck = os.path.join(spec_dir, "features", "checkout.md")
    embed_flows.embed_feature(ck, [DATA_FLOW, USER_FLOW], "2026-07-01T00:00:00Z")
    compute_fp = validate_flows._load_compute_fingerprint()
    assert compute_fp is not None  # sibling make-spec found
    fails, warns = validate_flows.validate_feature(ck, compute_fp)
    assert fails == []


def test_validate_flags_uncovered_active_fr_as_warning(spec_dir):
    # cart has FR-CART-001 but we embed a data flow covering nothing real.
    cart = os.path.join(spec_dir, "features", "cart.md")
    flow = {"id": "DF-CART-01", "kind": "data", "covers": [], "mermaid": "sequenceDiagram\n  A->>B: x"}
    embed_flows.embed_feature(cart, [flow], "2026-07-01T00:00:00Z")
    compute_fp = validate_flows._load_compute_fingerprint()
    fails, warns = validate_flows.validate_feature(cart, compute_fp)
    assert fails == []
    assert any("DF-004" in w and "FR-CART-001" in w for w in warns)


def test_validate_catches_bad_mermaid_kind(spec_dir):
    ck = os.path.join(spec_dir, "features", "checkout.md")
    bad = {"id": "DF-CHK-01", "kind": "data", "covers": ["FR-CHK-001"],
           "mermaid": "pie title Not a data flow\n  \"a\": 1"}
    embed_flows.embed_feature(ck, [bad], "2026-07-01T00:00:00Z")
    compute_fp = validate_flows._load_compute_fingerprint()
    fails, _ = validate_flows.validate_feature(ck, compute_fp)
    assert any("DF-002" in f for f in fails)


def test_validate_detects_stale_region(spec_dir):
    ck = os.path.join(spec_dir, "features", "checkout.md")
    embed_flows.embed_feature(ck, [DATA_FLOW], "2026-07-01T00:00:00Z")
    _mutate_and_restamp(ck)  # bump feature_version without re-embedding
    compute_fp = validate_flows._load_compute_fingerprint()
    fails, warns = validate_flows.validate_feature(ck, compute_fp)
    assert fails == []  # stale is advisory
    assert any("DF-005" in w for w in warns)


def test_validate_no_region_is_clean(spec_dir):
    cart = os.path.join(spec_dir, "features", "cart.md")
    compute_fp = validate_flows._load_compute_fingerprint()
    fails, warns = validate_flows.validate_feature(cart, compute_fp)
    assert fails == []  # no flows yet is fine


def test_df006_skipped_when_no_region_even_if_fingerprint_stale(spec_dir):
    # A feature this skill never touched (no region) is not ours to police, even
    # if its make-spec fingerprint is currently stale/placeholder.
    cart = os.path.join(spec_dir, "features", "cart.md")
    head, body, doc = split_frontmatter(open(cart, encoding="utf-8").read())
    doc["meta"]["fingerprint"] = "deadbeefdead"  # deliberately wrong
    text = "---\n" + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True) + "---\n" + body
    open(cart, "w", encoding="utf-8").write(text)
    compute_fp = validate_flows._load_compute_fingerprint()
    fails, _ = validate_flows.validate_feature(cart, compute_fp)
    assert fails == []  # no region -> DF-006 does not fire


def test_df006_fails_when_region_present_and_fingerprint_stale(spec_dir):
    ck = os.path.join(spec_dir, "features", "checkout.md")
    embed_flows.embed_feature(ck, [DATA_FLOW], "2026-07-01T00:00:00Z")
    # Corrupt the stored fingerprint AFTER embedding (frontmatter no longer stamped).
    head, body, doc = split_frontmatter(open(ck, encoding="utf-8").read())
    doc["meta"]["fingerprint"] = "deadbeefdead"
    text = "---\n" + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True) + "---\n" + body
    open(ck, "w", encoding="utf-8").write(text)
    compute_fp = validate_flows._load_compute_fingerprint()
    fails, _ = validate_flows.validate_feature(ck, compute_fp)
    assert any("DF-006" in f for f in fails)
