"""Tests for make-api-contracts: fingerprints, upsert, handshake, tombstone,
no-op guard, rendering, and the validator."""
import json
import os

import pytest
import yaml

import build_contracts as bc
import contract_fingerprint as cf
import validate_contracts as vc
from contractlib import (X_FEATURE, X_FLOW, X_OP_FP, X_SOURCE_VERSION, X_STATUS,
                         X_TRACE_REQ, as_list, read_features, split_frontmatter)
from validate_spec import compute_fingerprint  # make-spec, via conftest


# ── fixtures ─────────────────────────────────────────────────────────────────
def _req(rid, kind="functional", interface="POST /orders { items, total }", status="active"):
    return {
        "id": rid, "name": rid, "kind": kind,
        "description": f"The system does {rid}.",
        "acceptance_criteria": ["The system shall do it.",
                                "IF it fails, THEN the system shall error."],
        "governed_by": ["ADR-0001"] if kind == "integration" else [],
        "depends_on": [], "interface": interface, "priority": "must", "status": status,
    }


def make_feature(features_dir, slug, prefix, reqs, body_extra=""):
    doc = {
        "meta": {"doc_type": "spec-feature", "schema_version": "1.0", "slug": slug,
                 "prefix": prefix, "title": slug.title(), "status": "active"},
        "user_stories": ["As a user, I want a thing, so that benefit."],
        "no_gos": [], "supports": [], "requirements": reqs,
    }
    fp = compute_fingerprint(doc)
    doc["meta"]["fingerprint"] = fp
    doc["meta"]["feature_version"] = fp[:12]
    body = f"\n# {slug}\n\nNarrative.\n{body_extra}"
    text = "---\n" + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True) + "---\n" + body
    os.makedirs(features_dir, exist_ok=True)
    path = os.path.join(features_dir, f"{slug}.md")
    open(path, "w", encoding="utf-8").write(text)
    return path, fp[:12]


FLOW_REGION = (
    "\n<!-- make-data-flows:flows -->\n"
    "<!-- make-data-flows:flow id=DF-CHK-01 kind=data covers=FR-CHK-001,IR-CHK-001 -->\n"
    "```mermaid\nsequenceDiagram\n  A->>B: x\n```\n"
    "<!-- /make-data-flows:flow -->\n<!-- /make-data-flows:flows -->\n"
)


@pytest.fixture
def spec_dir(tmp_path):
    d = tmp_path / "docs" / "specs"
    feats = d / "features"
    # checkout has a covering flow region; cart does not.
    make_feature(str(feats), "checkout", "CHK",
                 [_req("FR-CHK-001"), _req("IR-CHK-001", "integration")],
                 body_extra=FLOW_REGION)
    make_feature(str(feats), "cart", "CART", [_req("FR-CART-001", interface="GET /cart")])
    # a minimal arch-data.yaml so ADR-0001 resolves
    (d / "arch-data.yaml").write_text(
        "meta: {doc_type: spec-arch}\n"
        "decisions:\n- {id: ADR-0001, title: Use Stripe, status: accepted}\n"
        "integrations:\n- {name: Stripe, external_system: Stripe, direction: outbound}\n",
        encoding="utf-8")
    return str(d)


def _op(oid, method, path, feature, trace_req, **kw):
    o = {"operationId": oid, "method": method, "path": path, "feature": feature,
         "trace_req": trace_req,
         "responses": {"201": {"description": "ok"}}}
    o.update(kw)
    return o


CK_OP = _op("checkout.createOrder", "post", "/orders", "checkout", ["IR-CHK-001"],
            trace_adr=["ADR-0001"], integration="INTG-stripe", summary="Record a paid order",
            requestBody={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/OrderInput"}}}},
            schemas={"OrderInput": {"type": "object"}})
CART_OP = _op("cart.getCart", "get", "/cart", "cart", ["FR-CART-001"], summary="Get cart")


# ── fingerprints ─────────────────────────────────────────────────────────────
def test_op_fingerprint_string_and_list_trace_req_match():
    a = {X_TRACE_REQ: "IR-CHK-001", "responses": {"201": {"description": "ok"}}}
    b = {X_TRACE_REQ: ["IR-CHK-001"], "responses": {"201": {"description": "ok"}}}
    assert cf.compute_op_fingerprint(a, "post", "/orders") == cf.compute_op_fingerprint(b, "post", "/orders")


def test_string_trace_req_not_falsely_tombstoned(spec_dir):
    doc, _ = _build(spec_dir, [CK_OP])
    # A scalar x-trace-req in stored YAML must resolve as one active id, not be
    # shredded into inactive single-char ids (which would falsely tombstone it).
    doc["paths"]["/orders"]["post"][X_TRACE_REQ] = "IR-CHK-001"
    features = read_features(spec_dir)
    tomb, _ = bc.tombstone_orphans(doc, features, set())
    assert "checkout.createOrder" not in tomb
    det = bc.detect(doc, features)
    assert not any(o["operationId"] == "checkout.createOrder" for o in det["orphan"])


def test_op_fingerprint_ignores_summary_but_not_shape():
    a = {X_TRACE_REQ: ["IR-CHK-001"], "responses": {"201": {"description": "ok"}}, "summary": "A"}
    b = dict(a, summary="B totally different")
    assert cf.compute_op_fingerprint(a, "post", "/orders") == cf.compute_op_fingerprint(b, "post", "/orders")
    c = dict(a, responses={"200": {"description": "changed"}})
    assert cf.compute_op_fingerprint(a, "post", "/orders") != cf.compute_op_fingerprint(c, "post", "/orders")


# ── build: kickoff + provenance + handshake ──────────────────────────────────
def _build(spec_dir, ops, now="2026-07-01T00:00:00Z", scope=None):
    features = read_features(spec_dir)
    doc = bc.seed_doc({"title": "Test API", "version": "0.1"})
    for spec in ops:
        bc.upsert(doc, spec, features, scope or set())
    bc.tombstone_orphans(doc, features, scope or set())
    out = os.path.join(spec_dir, "api")
    bc.stamp_and_write(doc, out, "# API Contracts\n", None, None, now)
    return doc, out


def test_kickoff_writes_contract_with_provenance(spec_dir):
    doc, out = _build(spec_dir, [CK_OP, CART_OP])
    assert os.path.isfile(os.path.join(out, "openapi.yaml"))
    assert os.path.isfile(os.path.join(out, "API-CONTRACTS.md"))
    ledger = json.loads(open(os.path.join(out, ".make-api-sync.json")).read())
    assert "checkout.createOrder" in ledger and ledger["checkout.createOrder"]["state"] == "present"
    op = doc["paths"]["/orders"]["post"]
    feats = read_features(spec_dir)
    assert op[X_SOURCE_VERSION] == feats["checkout"]["feature_version"]
    assert op[X_FEATURE] == "checkout" and op[X_OP_FP]
    assert doc["info"]["x-fingerprint"] and doc["info"]["x-contract-version"]


def test_handshake_marks_uncovered_op_unconfirmed(spec_dir):
    # checkout.createOrder traces IR-CHK-001, which the checkout flow region covers.
    doc, _ = _build(spec_dir, [CK_OP, CART_OP])
    assert X_FLOW not in doc["paths"]["/orders"]["post"]      # covered -> confirmed
    assert doc["paths"]["/cart"]["get"].get(X_FLOW) == "unconfirmed"  # cart has no flow


def test_noop_is_byte_identical(spec_dir):
    _build(spec_dir, [CK_OP, CART_OP], now="2026-07-01T00:00:00Z")
    p = os.path.join(spec_dir, "api", "openapi.yaml")
    first = open(p, encoding="utf-8").read()
    # Rebuild identical, different timestamp -> reuse prior x-generated -> identical bytes.
    features = read_features(spec_dir)
    prior = yaml.safe_load(first)
    doc = yaml.safe_load(first)
    for spec in [CK_OP, CART_OP]:
        bc.upsert(doc, spec, features, set())
    bc.tombstone_orphans(doc, features, set())
    bc.stamp_and_write(doc, os.path.join(spec_dir, "api"), "# API Contracts\n", first, prior,
                       "2099-01-01T00:00:00Z")
    assert open(p, encoding="utf-8").read() == first


def test_upsert_preserves_human_summary(spec_dir):
    doc, out = _build(spec_dir, [CK_OP])
    # Simulate a human editing the summary on disk, then reload + rebuild.
    doc["paths"]["/orders"]["post"]["summary"] = "HUMAN EDITED SUMMARY"
    features = read_features(spec_dir)
    changed = dict(CK_OP, summary="a different generated summary")
    bc.upsert(doc, changed, features, set())
    assert doc["paths"]["/orders"]["post"]["summary"] == "HUMAN EDITED SUMMARY"


def test_tombstone_when_requirement_goes_inactive(spec_dir):
    doc, out = _build(spec_dir, [CK_OP])
    # Supersede IR-CHK-001 in the feature spec, re-stamp, rebuild with no payload op.
    ck = os.path.join(spec_dir, "features", "checkout.md")
    head, body, fdoc = split_frontmatter(open(ck).read())
    for r in fdoc["requirements"]:
        if r["id"] == "IR-CHK-001":
            r["status"] = "superseded"
    fp = compute_fingerprint(fdoc)
    fdoc["meta"]["fingerprint"] = fp
    fdoc["meta"]["feature_version"] = fp[:12]
    open(ck, "w").write("---\n" + yaml.safe_dump(fdoc, sort_keys=False, allow_unicode=True) + "---\n" + body)

    features = read_features(spec_dir)
    tomb, _oos = bc.tombstone_orphans(doc, features, set())
    assert "checkout.createOrder" in tomb
    assert doc["paths"]["/orders"]["post"].get(X_STATUS) == "tombstoned"
    assert doc["paths"]["/orders"]["post"].get("deprecated") is True


def test_scope_leaves_out_of_scope_ops_untouched(spec_dir):
    doc, out = _build(spec_dir, [CK_OP, CART_OP])
    cart_before = dict(doc["paths"]["/cart"]["get"])
    features = read_features(spec_dir)
    # Rebuild scoped to checkout only; a cart op in the payload would be skip-scope.
    res = bc.upsert(doc, dict(CART_OP, summary="should be ignored"), features, {"checkout"})
    assert res == "skip-scope"
    assert doc["paths"]["/cart"]["get"] == cart_before


def test_check_reports_gaps_and_stale(spec_dir):
    doc, _ = _build(spec_dir, [CK_OP])  # cart's GET /cart has no op -> a coverage gap
    features = read_features(spec_dir)
    det = bc.detect(doc, features)
    assert any(g["req"] == "FR-CART-001" for g in det["gaps"])


# ── validator ────────────────────────────────────────────────────────────────
def test_validate_clean_contract_passes(spec_dir):
    doc, _ = _build(spec_dir, [CK_OP, CART_OP])
    features = read_features(spec_dir)
    from contractlib import read_arch
    adrs, _ = read_arch(spec_dir)
    fails, warns = vc.validate(doc, features, adrs)
    assert fails == [], fails


def test_validate_ac006_fingerprint_gate(spec_dir):
    doc, _ = _build(spec_dir, [CK_OP])
    doc["info"]["x-fingerprint"] = "deadbeef"
    features = read_features(spec_dir)
    fails, _ = vc.validate(doc, features, {"ADR-0001"})
    assert any("AC-006" in f for f in fails)


def test_validate_ac004_live_op_tracing_inactive_req_fails(spec_dir):
    doc, _ = _build(spec_dir, [CK_OP])
    # A live (non-tombstoned) op that traces a requirement not in the active set.
    doc["paths"]["/orders"]["post"][X_TRACE_REQ] = ["IR-CHK-999"]
    features = read_features(spec_dir)
    fails, _ = vc.validate(doc, features, {"ADR-0001"})
    assert any("AC-004" in f for f in fails)


def test_as_list_coercion():
    assert as_list(None) == []
    assert as_list("IR-CHK-001") == ["IR-CHK-001"]        # scalar -> single-item, not shredded
    assert as_list(["a", "b"]) == ["a", "b"]
    assert as_list(("a",)) == ["a"]


def test_upsert_coerces_string_trace_req(spec_dir):
    features = read_features(spec_dir)
    doc = bc.seed_doc({"title": "T", "version": "0.1"})
    # A payload author writes trace_req as a bare string instead of a list.
    spec = _op("checkout.createOrder", "post", "/orders", "checkout", "IR-CHK-001")
    bc.upsert(doc, spec, features, set())
    assert doc["paths"]["/orders"]["post"][X_TRACE_REQ] == ["IR-CHK-001"]  # not ['I','R',...]


def test_build_survives_null_yaml_sections(spec_dir):
    # A malformed/empty openapi doc where sections parsed as null must not crash.
    features = read_features(spec_dir)
    doc = {"openapi": "3.1.0", "info": None, "paths": None, "tags": None, "components": None}
    bc.upsert(doc, CK_OP, features, set())
    bc.tombstone_orphans(doc, features, set())
    out = os.path.join(spec_dir, "api")
    bc.stamp_and_write(doc, out, "# API Contracts\n", None, None, "2026-07-01T00:00:00Z")
    assert doc["paths"]["/orders"]["post"]["operationId"] == "checkout.createOrder"
    assert doc["info"]["x-fingerprint"]


def test_validate_coerces_string_trace_req(spec_dir):
    doc, _ = _build(spec_dir, [CK_OP])
    # Simulate a hand-written scalar x-trace-req in the YAML.
    doc["paths"]["/orders"]["post"][X_TRACE_REQ] = "IR-CHK-001"
    features = read_features(spec_dir)
    fails, _ = vc.validate(doc, features, {"ADR-0001"})
    # It resolves as one active id, not shredded chars -> no AC-004 failure.
    assert not any("AC-004" in f for f in fails)


def test_validate_ac002_duplicate_operation_id(spec_dir):
    doc, _ = _build(spec_dir, [CK_OP])
    # Inject a second operation with the same operationId under a different path.
    doc["paths"]["/dupe"] = {"get": dict(doc["paths"]["/orders"]["post"])}
    features = read_features(spec_dir)
    fails, _ = vc.validate(doc, features, {"ADR-0001"})
    assert any("AC-002" in f and "duplicate" in f for f in fails)
