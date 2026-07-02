#!/usr/bin/env python3
"""Tests for build_trace.py -- the traceability map generator.

Covers: the four-tier graph + derived edges (supports -> goals, governed_by ->
ADR -> requirement, component/integration inheritance, issue meta), status
roll-up math, orphaned refs, the additive/tombstone ledger (delete -> resurrect),
the fail-closed emptiness guard, and the byte-identical no-op guard.

  python -m pytest make-trace/scripts/tests/test_build_trace.py
"""
import copy
import os
import shutil
import sys

import pytest
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
sys.path.insert(0, SCRIPTS)
import build_trace as bt  # noqa: E402

FIXTURE_SPECS = os.path.join(HERE, "specs")
NOW = "2020-01-01T00:00:00+00:00"
LATER = "2099-12-31T23:59:59+00:00"


# ── fixture issues (as `gh issue list --json ...` returns them) ──────
def _meta(trace_req=(), trace_adr=(), feature="", provenance=""):
    y = {}
    if provenance:
        y["provenance"] = provenance
    y["trace_req"] = list(trace_req)
    if trace_adr:
        y["trace_adr"] = list(trace_adr)
    if feature:
        y["feature"] = feature
    block = yaml.safe_dump(y, sort_keys=False).strip()
    return ("## Requirement\n\n<!-- make-issues:meta -->\n```yaml\n"
            + block + "\n```\n<!-- /make-issues:meta -->\n")


def _issue(number, title, state="OPEN", reason=None, labels=(), assignees=(),
           prs=(), body=""):
    return {
        "number": number, "title": title, "state": state, "stateReason": reason,
        "labels": [{"name": n} for n in labels],
        "assignees": [{"login": a} for a in assignees],
        "closedByPullRequestsReferences": [{"number": p} for p in prs],
        "body": body, "url": f"https://example/issues/{number}",
    }


def fixture_issues():
    return [
        _issue(1, "Build place-order", state="CLOSED", reason="COMPLETED",
               labels=["make-issues", "afk"],
               body=_meta(["FR-CHK-001"], ["ADR-0001"], "checkout")),       # done
        _issue(2, "Fulfillment sync", labels=["make-issues"], assignees=["dev"],
               body=_meta(["IR-CHK-001"], feature="checkout")),             # doing
        _issue(3, "Add to cart", labels=["make-issues"],
               body=_meta(["FR-CART-001"], feature="cart")),                # todo
        _issue(4, "Rate-limit checkout", labels=["make-issues", "amendment", "hitl"],
               body=_meta([], feature="checkout", provenance="amendment")),  # amendment todo
        _issue(5, "Hand-made issue, no meta", body="just prose, no meta block"),  # untraced todo
        _issue(6, "Refers to a gone requirement", labels=["make-issues"],
               body=_meta(["FR-GONE-001"], feature="checkout")),            # orphaned ref
        _issue(7, "Empty cart message", state="CLOSED", reason="NOT_PLANNED",
               labels=["make-issues"],
               body=_meta(["CR-CART-001"], feature="cart")),               # dropped
    ]


def build(issues=None, prior=None, features=None):
    overview, feats, arch = bt.load_specs(FIXTURE_SPECS)
    if features is not None:
        feats = features
    data, _, _ = bt.assemble(overview, feats, arch,
                             fixture_issues() if issues is None else issues, prior)
    return data


def edge_set(data):
    return {(e["from"], e["to"]) for e in data["edges"]}


# ── tiers + status roll-up colors ────────────────────────────────────
def test_node_colors_and_dimming():
    n = build()["nodes"]
    assert n["FR-CHK-001"]["color"] == "done" and n["FR-CHK-001"]["pct"] == 100
    assert n["IR-CHK-001"]["color"] == "doing"
    assert n["FR-CART-001"]["color"] == "todo"
    assert n["CR-CART-001"]["color"] == "none"      # only a dropped issue -> not live
    assert n["NFR-CHK-001"]["dim"] is True          # superseded requirement
    assert n["ADR-0001"]["color"] == "done"         # issue #1 traces the ADR
    assert n["ADR-0002"]["dim"] is True             # superseded ADR
    assert n["G-001"]["color"] == "doing" and n["G-002"]["color"] == "doing"


def test_architecture_nodes_present():
    n = build()["nodes"]
    assert "C-001" in n and n["C-001"]["tier"] == "arch"
    assert "INTG-payment-gateway" in n                # integration id synthesized from name
    # a component inherits the requirements its governing ADR covers
    assert "FR-CHK-001" in n["C-001"]["links"]["reqs"]


# ── derived edges (zero manual mapping) ──────────────────────────────
def test_edges_are_derived_from_the_spec():
    e = edge_set(build())
    # requirement -> objective, from the feature's `supports`
    assert ("FR-CHK-001", "G-001") in e and ("FR-CHK-001", "G-002") in e
    assert ("FR-CART-001", "G-001") in e
    assert ("FR-CART-001", "G-002") not in e          # cart supports only G-001
    # architecture -> requirement
    assert ("ADR-0001", "FR-CHK-001") in e            # ADR.governs / req.governed_by
    assert ("C-001", "FR-CHK-001") in e               # component inherits via its ADR
    assert ("INTG-payment-gateway", "FR-CHK-001") in e
    # issue -> requirement / ADR
    assert ("#1", "FR-CHK-001") in e and ("#1", "ADR-0001") in e
    # amendment issue (no trace_req) rolls up via its feature's supported goals
    assert ("#4", "G-001") in e and ("#4", "G-002") in e
    # untraced issue wires to nothing
    assert not any(frm == "#5" for frm, _ in e)


def test_orphaned_refs_counted_not_wired():
    data = build()
    assert {"issue": 6, "ref": "FR-GONE-001"} in data["meta"]["orphanedRefs"]
    assert data["meta"]["totals"]["orphanedRefs"] == 1
    assert not any(frm == "#6" for frm, _ in edge_set(data))  # dangling ref draws no edge


def test_totals():
    t = build()["meta"]["totals"]
    assert t == {"issues": 7, "done": 1, "doing": 1, "todo": 4, "dropped": 1,
                 "traced": 6, "untraced": 1, "orphanedRefs": 1, "deleted": 0}


def test_goal_rollup_math():
    n = build()["nodes"]
    # G-001 sees: #1 done, #2 doing, #3 todo, #4 todo (dropped #7 excluded)
    assert n["G-001"]["counts"] == {"done": 1, "doing": 1, "todo": 2, "total": 4}
    # G-002 sees: #1 done, #2 doing, #4 todo
    assert n["G-002"]["counts"] == {"done": 1, "doing": 1, "todo": 1, "total": 3}


# ── legacy arch-data.yaml fallback (dual-read) ───────────────────────
# The primary fixture is v2.0 (architecture.md frontmatter + decisions/ADR-*.md);
# this is the pre-migration shape it must keep reading.
LEGACY_ARCH_YAML = """\
meta:
  doc_type: spec-arch
  schema_version: '1.0'
  project_id: proj-fixture
  project_name: Fixture Storefront
  arch_version: abc123def456
  status: draft
  fingerprint: fixture
context: A storefront where shoppers build a cart and pay.
components:
- id: C-001
  name: Storefront web app
  responsibility: Render the catalog, cart, and checkout.
  tech: Next.js
  confidence: known
  governed_by:
  - ADR-0001
integrations:
- name: Payment gateway
  external_system: Stripe
  direction: outbound
  data: payment intents, webhooks
  confidence: known
  governed_by:
  - ADR-0001
decisions:
- id: ADR-0001
  title: Use Stripe for payments
  status: accepted
  scope: feature
  superseded_by: ''
  confidence: known
  governs:
  - FR-CHK-001
- id: ADR-0002
  title: Use a self-hosted payment form
  status: superseded
  scope: feature
  superseded_by: ADR-0003
  confidence: known
  governs: []
"""


def _legacy_tree(tmp_path):
    """The v2.0 fixture with the arch layer swapped for a legacy arch-data.yaml."""
    root = tmp_path / "specs"
    shutil.copytree(FIXTURE_SPECS, root)
    os.remove(root / "architecture.md")
    shutil.rmtree(root / "decisions")
    (root / "arch-data.yaml").write_text(LEGACY_ARCH_YAML, encoding="utf-8")
    return str(root)


def test_legacy_arch_data_fallback(tmp_path, capsys):
    root = _legacy_tree(tmp_path)
    overview, feats, arch = bt.load_specs(root)
    assert "legacy arch-data.yaml" in capsys.readouterr().err  # one-line WARN
    data, _, _ = bt.assemble(overview, feats, arch, fixture_issues(), None)
    v2 = build()
    # the same nodes and edges come out of either shape -- no crash, no drift
    def arch_ids(d):
        return {i for i, n in d["nodes"].items() if n["tier"] == "arch"}
    assert arch_ids(data) == arch_ids(v2) == \
        {"C-001", "INTG-payment-gateway", "ADR-0001", "ADR-0002"}
    assert edge_set(data) == edge_set(v2)


def test_legacy_flat_architecture_md_is_not_v2(tmp_path):
    # The LEGACY architecture.md has a FLAT frontmatter (doc_type at top level,
    # no meta) -- the discriminator must fall through to arch-data.yaml.
    root = _legacy_tree(tmp_path)
    (tmp_path / "specs" / "architecture.md").write_text(
        "---\ndoc_type: spec-arch\ndata_file: arch-data.yaml\n---\n\n# Arch\n",
        encoding="utf-8")
    arch = bt.load_arch(root)
    assert [d["id"] for d in arch["decisions"]] == ["ADR-0001", "ADR-0002"]


def test_load_arch_none_means_lite_mode(tmp_path):
    root = _legacy_tree(tmp_path)
    os.remove(tmp_path / "specs" / "arch-data.yaml")
    assert bt.load_arch(root) is None


# ── issue status classification (parity with do-work) ────────────────
def test_issue_status_mapping():
    assert bt.issue_status(_issue(1, "", "CLOSED", "COMPLETED")) == "done"
    assert bt.issue_status(_issue(1, "", "CLOSED", "NOT_PLANNED")) == "dropped"
    assert bt.issue_status(_issue(1, "", assignees=["a"])) == "doing"
    assert bt.issue_status(_issue(1, "", prs=[9])) == "doing"
    assert bt.issue_status(_issue(1, "", labels=["status:doing"])) == "doing"
    assert bt.issue_status(_issue(1, "")) == "todo"


def test_meta_parse_tolerates_junk():
    assert bt.parse_meta("no meta at all") == {}
    good = bt.parse_meta(_meta(["FR-CHK-001"], feature="checkout"))
    assert good["trace_req"] == ["FR-CHK-001"] and good["feature"] == "checkout"


# ── additive / tombstone ledger ──────────────────────────────────────
def test_delete_tombstones_then_resurrects():
    overview, feats, arch = bt.load_specs(FIXTURE_SPECS)
    first = build()
    prior = first["nodes"]

    # Remove FR-CHK-001 from the spec AND issue #1 from GitHub, then re-run.
    feats2 = copy.deepcopy(feats)
    for slug, doc in feats2:
        if slug == "checkout":
            doc["requirements"] = [r for r in doc["requirements"]
                                   if r["id"] != "FR-CHK-001"]
    issues2 = [i for i in fixture_issues() if i["number"] != 1]
    second, _, _ = bt.assemble(overview, feats2, arch, issues2, prior)
    n2 = second["nodes"]

    assert n2["FR-CHK-001"]["state"] == "deleted"     # kept, not dropped
    assert n2["#1"]["state"] == "deleted"
    e2 = edge_set(second)
    assert ("FR-CHK-001", "G-001") in e2              # tombstone still draws its chain
    assert ("#1", "FR-CHK-001") in e2
    # a present node is unaffected
    assert n2["IR-CHK-001"]["state"] == "present"

    # Resurrect: the requirement and issue return -> back to present.
    third, _, _ = bt.assemble(overview, feats, arch, fixture_issues(), second["nodes"])
    assert third["nodes"]["FR-CHK-001"]["state"] == "present"
    assert third["nodes"]["#1"]["state"] == "present"


def test_deleted_issue_excluded_from_rollup():
    overview, feats, arch = bt.load_specs(FIXTURE_SPECS)
    prior = build()["nodes"]
    issues2 = [i for i in fixture_issues() if i["number"] != 1]  # drop the only 'done'
    data, _, _ = bt.assemble(overview, feats, arch, issues2, prior)
    n = data["nodes"]
    assert n["#1"]["state"] == "deleted"
    # FR-CHK-001 no longer has a live issue beneath it -> not green anymore
    assert n["FR-CHK-001"]["color"] == "none"
    assert data["meta"]["totals"]["deleted"] == 1


# ── fail-closed emptiness guard (generate) ───────────────────────────
def test_generate_aborts_when_issues_vanish(tmp_path):
    out = str(tmp_path)
    bt.generate(FIXTURE_SPECS, out, fixture_issues(), "owner/repo", NOW)  # seed ledger
    with pytest.raises(bt.EmptySourceError):
        bt.generate(FIXTURE_SPECS, out, [], "owner/repo", NOW)            # all issues gone
    # --allow-empty confirms a real emptying: it tombstones instead of aborting
    data = bt.generate(FIXTURE_SPECS, out, [], "owner/repo", NOW, allow_empty=True)
    issue_nodes = [n for n in data["nodes"].values() if n["tier"] == "issue"]
    assert issue_nodes and all(n["state"] == "deleted" for n in issue_nodes)


def test_first_run_with_no_prior_never_trips_guard(tmp_path):
    # No prior ledger -> empty issues is allowed (nothing to falsely tombstone).
    data = bt.generate(FIXTURE_SPECS, str(tmp_path), [], "owner/repo", NOW)
    assert data["meta"]["totals"]["issues"] == 0


# ── byte-identical no-op guard ───────────────────────────────────────
def test_noop_regeneration_is_byte_identical(tmp_path):
    out = str(tmp_path)
    bt.generate(FIXTURE_SPECS, out, fixture_issues(), "owner/repo", NOW)
    json_a = (tmp_path / "data.json").read_bytes()
    html_a = (tmp_path / "index.html").read_bytes()

    # Re-run with a DIFFERENT clock; nothing else changed -> reuse the timestamp.
    data_b = bt.generate(FIXTURE_SPECS, out, fixture_issues(), "owner/repo", LATER)
    assert data_b["meta"]["generatedAt"] == NOW               # reused, not LATER
    assert (tmp_path / "data.json").read_bytes() == json_a    # byte-identical -> no git churn
    assert (tmp_path / "index.html").read_bytes() == html_a


def test_real_change_takes_a_fresh_timestamp(tmp_path):
    out = str(tmp_path)
    bt.generate(FIXTURE_SPECS, out, fixture_issues(), "owner/repo", NOW)
    # A new issue is a real change -> the run stamps the fresh clock.
    more = fixture_issues() + [_issue(8, "New work", labels=["make-issues"],
                                      body=_meta(["FR-CART-001"], feature="cart"))]
    data = bt.generate(FIXTURE_SPECS, out, more, "owner/repo", LATER)
    assert data["meta"]["generatedAt"] == LATER
    assert data["meta"]["totals"]["issues"] == 8


# ── html render is self-contained ────────────────────────────────────
def test_html_renders_and_escapes():
    data = build()
    # a stray closing-script tag in the data must be neutralized
    data["nodes"]["#5"]["title"] = "</script><script>alert(1)</script>"
    html = bt.render_html(data)
    assert "__DATA__" not in html
    assert "</script><script>alert(1)" not in html  # the '<' was escaped to <
    assert "\\u003c/script>" in html


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
