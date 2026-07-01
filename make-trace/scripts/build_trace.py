#!/usr/bin/env python3
"""
build_trace.py -- generate the traceability map from the spec set + GitHub Issues.

Reads three sources and renders ONE self-contained HTML map that answers, at a
glance: which objectives and requirements are not-started / in-progress / done,
and how every live issue rolls up through the spec.

  Objectives    docs/specs/overview.md      goals (G-NNN, kind business|user)
  Requirements  docs/specs/features/*.md     requirements (FR/IR/NFR/CR)
  Architecture  docs/specs/arch-data.yaml    components (C), integrations, ADRs
  Issues        gh issue list --state all    make-issues:meta -> trace_req/trace_adr

Every edge is DERIVED from the spec itself (zero manual mapping):
  requirement -> objective   the feature's `supports: [G-NNN]`
  architecture -> requirement ADR.governs / requirement.governed_by; a
                             component/integration inherits the requirements its
                             governing ADRs cover
  issue -> requirement/ADR   the issue body's make-issues:meta block

ADDITIVE, NEVER DESTRUCTIVE. The output data.json is a LEDGER: every run merges
the current sources into it. A node that has vanished from the sources is kept
and marked `state: deleted` (tombstoned), retaining its last-known data so its
chain still renders. Add / change / renumber flow through; nothing is dropped.

FAIL-CLOSED. A failed or empty source never tombstones the world: if `gh` errors,
or a source that previously contributed nodes now contributes zero, the run
aborts and writes nothing (override a real emptying with --allow-empty).

NO-OP GUARD. When nothing substantive changed, the previous run's generated_at is
reused so the bytes are identical -- an unchanged regen makes no git diff, so
issue events do not spam commits.

  python build_trace.py [--repo owner/name] [--spec-dir docs/specs]
                        [--out docs/traceability] [--allow-empty] [--open]

Exit codes: 0 = wrote (or byte-identical no-op), 2 = aborted (bad source /
fail-closed guard / gh error). Read-only against the specs; writes only under
--out.
"""
import argparse
import copy
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone

try:
    import yaml
except ImportError:
    print("PyYAML is required: pip install pyyaml --break-system-packages",
          file=sys.stderr)
    sys.exit(2)

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_PATH = os.path.join(HERE, os.pardir, "assets", "template.html")
README_ASSET = os.path.join(HERE, os.pardir, "assets", "README-traceability.md")

# ── ID grammars (mirror make-spec / make-arch) ───────────────────────
REQ_ID_RE = re.compile(r"^(FR|IR|NFR|CR)-[A-Z]{2,5}-\d{3,}$")
GOAL_ID_RE = re.compile(r"^G-\d{3,}$")
ADR_ID_RE = re.compile(r"^ADR-\d{4}$")

# A spec node is dimmed when it is no longer the live version. make-spec uses
# superseded|deferred; make-arch ADRs use superseded|deprecated.
INACTIVE = {"superseded", "deprecated", "deferred", "rejected", "dropped", "obsolete"}

# Issue labels surfaced as badges (source of truth: make-issues/assets/labels.yaml).
BADGE_LABELS = {
    "hitl": "HITL", "spec-drift": "drift", "needs-rebase": "rebase",
    "orphaned": "orphaned", "escalated": "escalated",
    "needs-human-review": "review", "amendment": "amend",
    "refactor": "refactor", "refactor-tracking": "refactor?",
}
DOING_LABEL = "status:doing"  # optional in-progress signal (mirrors do-work)


# ── small coercion helpers (robust to messy YAML) ────────────────────
def as_list(v):
    """Coerce to a list: a list stays, None -> [], a scalar -> [scalar]."""
    if isinstance(v, list):
        return v
    return [] if v is None else [v]


def first_text(*vals):
    """First non-empty value, coerced to a trimmed string ('' if none)."""
    for v in vals:
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


def truncate(s, n=90):
    s = str(s or "")
    return s if len(s) <= n else s[: n - 1] + "…"


def is_dim(status):
    return str(status or "").strip().lower() in INACTIVE


def id_prefix(iid):
    return str(iid).split("-")[0]


def norm_key(name):
    """A stable id fragment from a free-text name (integrations have no id)."""
    slug = re.sub(r"[^a-z0-9]+", "-", str(name or "").strip().lower()).strip("-")
    return slug or "unnamed"


# ── spec loading (frontmatter is the signed contract) ────────────────
_FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL)


def _split_frontmatter(text):
    if text.startswith("﻿"):
        text = text[1:]
    m = _FRONTMATTER_RE.match(text)
    return (m.group(1), text[m.end():]) if m else (None, text)


def load_spec_doc(path):
    """Parse a single-file spec's frontmatter into a dict. Returns {} when there is
    no frontmatter or it is not a mapping; RAISES yaml.YAMLError on malformed
    frontmatter so the run fails closed (main aborts, exit 2, tombstoning nothing)
    rather than silently reading a corrupt spec as empty and dropping its nodes."""
    with open(path, encoding="utf-8") as f:
        fm, _ = _split_frontmatter(f.read())
    if fm is None:
        return {}
    doc = yaml.safe_load(fm)
    return doc if isinstance(doc, dict) else {}


def load_yaml(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_specs(spec_dir):
    """Return (overview, features, arch). Raises on a missing/unparseable source
    so the caller fails closed rather than tombstoning everything. `features` is
    [(slug, doc)]; `arch` is the arch-data.yaml dict or None (lite mode)."""
    overview_path = os.path.join(spec_dir, "overview.md")
    if not os.path.isfile(overview_path):
        raise FileNotFoundError(f"no overview.md under {spec_dir}")
    overview = load_spec_doc(overview_path)

    features = []
    fdir = os.path.join(spec_dir, "features")
    if os.path.isdir(fdir):
        for name in sorted(os.listdir(fdir)):
            if name.endswith(".md"):
                slug = name[: -len(".md")]
                features.append((slug, load_spec_doc(os.path.join(fdir, name))))

    arch = None
    arch_path = os.path.join(spec_dir, "arch-data.yaml")
    if os.path.isfile(arch_path):
        arch = load_yaml(arch_path)
    return overview, features, arch


# ── issues (right column) ────────────────────────────────────────────
_META_RE = re.compile(
    r"<!--\s*make-issues:meta\s*-->(.*?)<!--\s*/make-issues:meta\s*-->",
    re.DOTALL | re.IGNORECASE)


def parse_meta(body):
    """{trace_req, trace_adr, feature, provenance, ...} from the make-issues:meta
    block, or {} if absent/malformed (mirrors do-work/select_work.parse_meta)."""
    m = _META_RE.search(body or "")
    if not m:
        return {}
    inner = re.sub(r"```[a-zA-Z]*", "", m.group(1)).replace("```", "")
    try:
        data = yaml.safe_load(inner)
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def label_names(issue):
    return {lab.get("name", "") for lab in issue.get("labels") or []}


def issue_status(issue):
    """done | doing | todo | dropped -- the same classification do-work uses.
    closed+completed = done, closed+not-planned = dropped, open+started = doing
    (started = assignee / closing-PR / status:doing), else todo."""
    if issue.get("state") == "CLOSED":
        return "done" if issue.get("stateReason") == "COMPLETED" else "dropped"
    started = (issue.get("assignees")
               or issue.get("closedByPullRequestsReferences")
               or DOING_LABEL in label_names(issue))
    return "doing" if started else "todo"


def issue_badges(issue):
    names = label_names(issue)
    return [badge for label, badge in BADGE_LABELS.items() if label in names]


def fetch_issues(repo):
    """All issues via `gh`, or None on any error (the caller aborts). No label
    filter: hand-made issues surface as `untraced` rather than being hidden."""
    cmd = ["gh", "issue", "list", "--state", "all", "--limit", "1000", "--json",
           "number,title,state,stateReason,labels,assignees,body,"
           "closedByPullRequestsReferences,url"]
    if repo:
        cmd += ["--repo", repo]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    except FileNotFoundError:
        print("ERROR: gh not found -- install and authenticate the GitHub CLI",
              file=sys.stderr)
        return None
    if p.returncode != 0:
        print(f"ERROR: `gh issue list` failed: {p.stderr.strip()}", file=sys.stderr)
        return None
    try:
        return json.loads(p.stdout or "[]")
    except json.JSONDecodeError as e:
        print(f"ERROR: bad JSON from gh: {e}", file=sys.stderr)
        return None


def resolve_repo(repo):
    """Display name for the header. --repo wins; else ask gh; else ''."""
    if repo:
        return repo
    try:
        p = subprocess.run(["gh", "repo", "view", "--json", "nameWithOwner",
                            "-q", ".nameWithOwner"], capture_output=True,
                           text=True, encoding="utf-8")
        if p.returncode == 0:
            return p.stdout.strip()
    except FileNotFoundError:
        pass
    return ""


# ── build the current graph (pure: no IO) ────────────────────────────
def build_current_nodes(overview, features, arch, issues):
    """Return (nodes, orphaned_refs). nodes is {id: node}; every node carries a
    `group` (where it renders) and `links` (its outgoing spec references, from
    which edges are re-derived). Deleted-node tombstones are merged in later."""
    nodes = {}

    def add(node):
        nodes.setdefault(node["id"], node)
        return nodes[node["id"]]

    # -- Objectives -----------------------------------------------------
    for g in as_list(overview.get("goals")):
        if not isinstance(g, dict):
            continue
        gid = first_text(g.get("id"))
        if not gid:
            continue
        kind = first_text(g.get("kind")) or "goal"
        status = first_text(g.get("status")) or "active"
        label = "User goals" if kind == "user" else \
            ("Business goals" if kind == "business" else "Goals")
        add({
            "id": gid, "tier": "objective", "kind": kind,
            "title": truncate(first_text(g.get("statement"), gid)),
            "full": first_text(g.get("statement"), gid),
            "status": status, "dim": is_dim(status), "links": {},
            "group": {"col": "objective", "id": f"obj-{kind}", "label": label},
        })

    # -- Requirements (feature `supports` -> objectives) ----------------
    feature_supports = {}  # slug -> [goal ids]
    adr_from_reqs = defaultdict(set)  # ADR id -> {req ids} (reverse governed_by)
    for slug, doc in features:
        meta = doc.get("meta") or {}
        ftitle = first_text(meta.get("title"), slug)
        supports = [first_text(x) for x in as_list(doc.get("supports")) if first_text(x)]
        feature_supports[slug] = supports
        for r in as_list(doc.get("requirements")):
            if not isinstance(r, dict):
                continue
            rid = first_text(r.get("id"))
            if not rid:
                continue
            status = first_text(r.get("status")) or "active"
            for adr in as_list(r.get("governed_by")):
                adr_from_reqs[first_text(adr)].add(rid)
            add({
                "id": rid, "tier": "requirement", "kind": id_prefix(rid),
                "title": truncate(first_text(r.get("name"), r.get("description"), rid)),
                "full": first_text(r.get("description"), r.get("name"), rid),
                "status": status, "dim": is_dim(status),
                "links": {"goals": supports},
                "group": {"col": "requirement", "id": f"req-{slug}", "label": ftitle},
            })

    # -- Architecture (ADRs first, so components can inherit their reqs) -
    adr_reqs = {}  # ADR id -> [req ids it covers]
    if isinstance(arch, dict):
        for d in as_list(arch.get("decisions")):
            if not isinstance(d, dict):
                continue
            aid = first_text(d.get("id"))
            if not aid:
                continue
            status = first_text(d.get("status")) or "accepted"
            governs = [first_text(x) for x in as_list(d.get("governs"))
                       if REQ_ID_RE.match(first_text(x))]
            reqs = sorted(set(governs) | adr_from_reqs.get(aid, set()))
            adr_reqs[aid] = reqs
            add({
                "id": aid, "tier": "arch", "kind": "ADR",
                "title": truncate(first_text(d.get("title"), aid)),
                "full": first_text(d.get("title"), aid),
                "status": status, "dim": is_dim(status), "links": {"reqs": reqs},
                "group": {"col": "arch", "id": "arch-decisions",
                          "label": "Decisions (ADR)"},
            })

        def inherited_reqs(governed_by):
            reqs = set()
            for a in as_list(governed_by):
                reqs |= set(adr_reqs.get(first_text(a), []))
            return sorted(reqs)

        for c in as_list(arch.get("components")):
            if not isinstance(c, dict):
                continue
            cid = first_text(c.get("id"))
            if not cid:
                continue
            status = first_text(c.get("confidence")) or "known"
            add({
                "id": cid, "tier": "arch", "kind": id_prefix(cid),
                "title": truncate(first_text(c.get("name"), cid)),
                "full": first_text(c.get("responsibility"), c.get("name"), cid),
                "status": status, "dim": False,
                "links": {"reqs": inherited_reqs(c.get("governed_by"))},
                "group": {"col": "arch", "id": "arch-components", "label": "Components"},
            })

        for i in as_list(arch.get("integrations")):
            if not isinstance(i, dict):
                continue
            name = first_text(i.get("name"), i.get("external_system"))
            if not name:
                continue
            iid = f"INTG-{norm_key(name)}"
            status = first_text(i.get("confidence")) or "known"
            add({
                "id": iid, "tier": "arch", "kind": "INTG",
                "title": truncate(name),
                "full": first_text(i.get("external_system"), name),
                "status": status, "dim": False,
                "links": {"reqs": inherited_reqs(i.get("governed_by"))},
                "group": {"col": "arch", "id": "arch-integrations",
                          "label": "Integrations"},
            })

    # -- Issues ---------------------------------------------------------
    spec_ids = set(nodes)  # every objective/requirement/arch id seen so far
    orphaned_refs = []
    for issue in as_list(issues):
        if not isinstance(issue, dict) or issue.get("number") is None:
            continue
        num = issue["number"]
        iid = f"#{num}"
        meta = parse_meta(issue.get("body"))
        trace_req = [first_text(x) for x in as_list(meta.get("trace_req")) if first_text(x)]
        trace_adr = [first_text(x) for x in as_list(meta.get("trace_adr")) if first_text(x)]
        feature = first_text(meta.get("feature"))
        traced = bool(meta) and bool(trace_req or trace_adr or feature)
        # An amendment (no trace_req) still rolls up to the goals its feature serves.
        goals = feature_supports.get(feature, []) if (not trace_req and feature) else []
        for ref in trace_req + trace_adr:
            if ref not in spec_ids:
                orphaned_refs.append({"issue": num, "ref": ref})
        status = issue_status(issue)
        add({
            "id": iid, "tier": "issue", "kind": "issue", "number": num,
            "title": truncate(first_text(issue.get("title"), iid), 80),
            "full": first_text(issue.get("title"), iid),
            "status": status, "dim": (status == "dropped"),
            "url": first_text(issue.get("url")), "badges": issue_badges(issue),
            "traced": traced,
            "links": {"reqs": trace_req, "adrs": trace_adr, "goals": goals},
            "group": {"col": "issue",
                      "id": "iss-traced" if traced else "iss-untraced",
                      "label": "Traced" if traced else "Untraced"},
        })
    return nodes, orphaned_refs


# ── ledger merge (additive / tombstone) ──────────────────────────────
def merge_ledger(prior_nodes, current_nodes):
    """Union current (present) with prior (tombstoned when absent now). A node
    back in the sources resurrects to present. Deleted nodes keep their last data
    so their chain still renders."""
    merged = {}
    for iid, node in current_nodes.items():
        n = copy.deepcopy(node)
        n["state"] = "present"
        merged[iid] = n
    for iid, node in (prior_nodes or {}).items():
        if iid in merged:
            continue
        n = copy.deepcopy(node)
        n["state"] = "deleted"
        for k in ("color", "pct", "counts"):  # recomputed fresh below
            n.pop(k, None)
        merged[iid] = n
    return merged


# ── edges + roll-up (pure) ───────────────────────────────────────────
def derive_edges(merged):
    """Edges child->parent (from = closer to issues). Re-derived from node links
    every run, so a tombstoned node still draws its former chain."""
    ids = set(merged)
    seen, edges = set(), []

    def add(child, parent):
        if child in ids and parent in ids and child != parent \
                and (child, parent) not in seen:
            seen.add((child, parent))
            edges.append({"from": child, "to": parent})

    for iid, node in merged.items():
        links = node.get("links") or {}
        tier = node.get("tier")
        if tier == "requirement":
            for g in links.get("goals", []):
                add(iid, g)
        elif tier == "arch":
            for r in links.get("reqs", []):
                add(iid, r)
        elif tier == "issue":
            for r in links.get("reqs", []):
                add(iid, r)
            for a in links.get("adrs", []):
                add(iid, a)
            for g in links.get("goals", []):
                add(iid, g)
    edges.sort(key=lambda e: (e["from"], e["to"]))
    return edges


def compute_rollup(merged, edges):
    """Assign color/pct/counts. An issue shows its own status; a parent shows a
    roll-up of the PRESENT, non-dropped issues beneath it (doing counts 0.5).
    Deleted and dropped issues render but never move a parent's numbers."""
    parents = defaultdict(list)
    for e in edges:
        parents[e["from"]].append(e["to"])

    issue_sets = defaultdict(set)
    for iid, node in merged.items():
        if node.get("tier") != "issue" or node.get("state") != "present":
            continue
        if node.get("status") not in ("done", "doing", "todo"):
            continue  # dropped (won't-do) is not live work
        seen, stack = set(), list(parents.get(iid, []))
        while stack:
            anc = stack.pop()
            if anc in seen:
                continue
            seen.add(anc)
            issue_sets[anc].add(iid)
            stack.extend(parents.get(anc, []))

    for iid, node in merged.items():
        if node.get("tier") == "issue":
            node["color"] = node.get("status")
            node.pop("pct", None)
            node.pop("counts", None)
            continue
        done = doing = todo = 0
        for sid in issue_sets.get(iid, ()):  # empty for leaves / childless nodes
            st = merged[sid].get("status")
            if st == "done":
                done += 1
            elif st == "doing":
                doing += 1
            else:
                todo += 1
        total = done + doing + todo
        if total == 0:
            color = "none"
        elif done == total:
            color = "done"
        elif done or doing:
            color = "doing"
        else:
            color = "todo"
        node["color"] = color
        node["pct"] = round(100 * (done + 0.5 * doing) / total) if total else 0
        node["counts"] = {"done": done, "doing": doing, "todo": todo, "total": total}


# ── columns (render layout) ──────────────────────────────────────────
_ISSUE_STATUS_RANK = {"doing": 0, "todo": 1, "done": 2, "dropped": 3}


def _sort_key(node):
    """present before deleted; then a tier-natural order."""
    state_rank = 0 if node.get("state") != "deleted" else 1
    if node.get("tier") == "issue":
        return (state_rank, _ISSUE_STATUS_RANK.get(node.get("status"), 9),
                node.get("number") or 0)
    return (state_rank, str(node.get("id")))


def build_columns(merged, overview):
    """Group merged nodes into the four columns. Present groups keep their natural
    order; tombstones append to their old group (or a leftover group if that group
    is gone). A group with any node -- present or deleted -- is shown."""
    order = {
        "objective": [("obj-business", "Business goals"), ("obj-user", "User goals"),
                      ("obj-goal", "Goals")],
        "requirement": [(f"req-{r.get('slug')}", first_text(r.get("title"), r.get("slug")))
                        for r in as_list(overview.get("feature_index"))
                        if isinstance(r, dict) and r.get("slug")],
        "arch": [("arch-components", "Components"),
                 ("arch-integrations", "Integrations"),
                 ("arch-decisions", "Decisions (ADR)")],
        "issue": [("iss-traced", "Traced"), ("iss-untraced", "Untraced")],
    }
    collapsible_cols = {"arch"}

    buckets = defaultdict(list)  # (col, gid) -> [id]
    labels = {}
    for iid, node in merged.items():
        g = node.get("group") or {}
        key = (g.get("col"), g.get("id"))
        buckets[key].append(iid)
        labels[key] = first_text(g.get("label"), g.get("id"))

    def make_group(col, gid, label):
        ids = sorted(buckets[(col, gid)], key=lambda i: _sort_key(merged[i]))
        grp = {"id": gid, "label": label, "nodeIds": ids}
        if col in collapsible_cols:
            grp["collapsible"] = True
        return grp

    columns = []
    for col_key, col_label in (("objective", "Objectives"),
                               ("requirement", "Requirements"),
                               ("arch", "Architecture"), ("issue", "Issues")):
        groups, used = [], set()
        for gid, glabel in order.get(col_key, []):
            key = (col_key, gid)
            if key in buckets:
                groups.append(make_group(col_key, gid, glabel))
                used.add(key)
        # Leftover groups: tombstones whose group is no longer in the spec
        # (e.g. a whole feature was removed). Keep each with its stored label.
        leftover = sorted(k for k in buckets if k[0] == col_key and k not in used)
        for _, gid in leftover:
            groups.append(make_group(col_key, gid, labels[(col_key, gid)]))
        columns.append({"key": col_key, "label": col_label, "groups": groups})
    return columns


# ── totals ───────────────────────────────────────────────────────────
def compute_totals(merged, orphaned_refs):
    present_issues = [n for n in merged.values()
                      if n.get("tier") == "issue" and n.get("state") == "present"]

    def count(status):
        return sum(1 for n in present_issues if n.get("status") == status)

    deleted = sum(1 for n in merged.values() if n.get("state") == "deleted")
    return {
        "issues": len(present_issues), "done": count("done"),
        "doing": count("doing"), "todo": count("todo"), "dropped": count("dropped"),
        "traced": sum(1 for n in present_issues if n.get("traced")),
        "untraced": sum(1 for n in present_issues if not n.get("traced")),
        "orphanedRefs": len(orphaned_refs), "deleted": deleted,
    }


# ── fail-closed emptiness guard ──────────────────────────────────────
def _present_by_tier(nodes):
    c = defaultdict(int)
    for n in (nodes or {}).values():
        if n.get("state", "present") != "deleted":
            c[n.get("tier")] += 1
    return c


def emptiness_violations(current_nodes, prior_nodes, arch_present):
    """A source that previously contributed present nodes but contributes zero now
    is almost always a bad path or a failed fetch -- not a real deletion. Report
    each such tier so the caller can abort (unless --allow-empty)."""
    cur = _present_by_tier(current_nodes)
    prior = _present_by_tier(prior_nodes)
    bad = []
    for tier in ("objective", "requirement", "issue"):
        if prior.get(tier, 0) > 0 and cur.get(tier, 0) == 0:
            bad.append(tier)
    # Architecture is legitimately empty in lite mode; only guard it when an
    # arch-data.yaml is actually present now but yielded nothing.
    if arch_present and prior.get("arch", 0) > 0 and cur.get("arch", 0) == 0:
        bad.append("arch")
    return bad


# ── assemble + write ─────────────────────────────────────────────────
def assemble(overview, features, arch, issues, prior_nodes):
    """The full pipeline minus timestamp/IO: current graph -> merge -> edges ->
    roll-up -> columns -> totals. Returns (data, current_nodes, orphaned_refs)."""
    current_nodes, orphaned_refs = build_current_nodes(overview, features, arch, issues)
    merged = merge_ledger(prior_nodes, current_nodes)
    edges = derive_edges(merged)
    compute_rollup(merged, edges)
    columns = build_columns(merged, overview)
    meta = {
        "generatedAt": None,  # filled by resolve_generated_at (no-op guard)
        "repo": "", "projectVersion": first_text((overview.get("meta") or {}).get("project_version")),
        "archVersion": first_text(((arch or {}).get("meta") or {}).get("arch_version")),
        "totals": compute_totals(merged, orphaned_refs),
        "orphanedRefs": orphaned_refs,
    }
    data = {"meta": meta, "columns": columns, "nodes": merged, "edges": edges}
    return data, current_nodes, orphaned_refs


def _canonical(data):
    """Deterministic serialization used for both the written file and the no-op
    compare, so an unchanged run is byte-for-byte identical."""
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def resolve_generated_at(data, prior_data, now):
    """Reuse the previous timestamp when everything else is identical."""
    data["meta"]["generatedAt"] = None
    candidate = _canonical(data)
    if prior_data and isinstance(prior_data.get("meta"), dict):
        prev_at = prior_data["meta"].get("generatedAt")
        # Compare without copying: null the timestamp in place, then restore it.
        # The try/finally guarantees prior_data is restored even if _canonical
        # raises, keeping the function pure on every path.
        try:
            prior_data["meta"]["generatedAt"] = None
            is_match = _canonical(prior_data) == candidate
        finally:
            prior_data["meta"]["generatedAt"] = prev_at
        if prev_at and is_match:
            return prev_at
    return now


def render_html(data):
    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        template = f.read()
    if "__DATA__" not in template:
        raise RuntimeError("template.html is missing the __DATA__ placeholder")
    # Escape `<` so a stray "</script>" inside the data cannot break out of the tag.
    payload = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    return template.replace("__DATA__", payload)


def load_prior(out_json):
    try:
        with open(out_json, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


class EmptySourceError(Exception):
    """A source that previously had nodes is empty now (fail-closed guard)."""

    def __init__(self, tiers):
        self.tiers = tiers
        super().__init__(", ".join(tiers))


def write_outputs(data, out_dir):
    """Write data.json (the ledger) + index.html, and seed README.md if absent."""
    os.makedirs(out_dir, exist_ok=True)
    out_json = os.path.join(out_dir, "data.json")
    with open(out_json, "w", encoding="utf-8") as f:
        f.write(_canonical(data))
    out_html = os.path.join(out_dir, "index.html")
    with open(out_html, "w", encoding="utf-8") as f:
        f.write(render_html(data))
    readme = os.path.join(out_dir, "README.md")
    if not os.path.exists(readme) and os.path.exists(README_ASSET):
        with open(README_ASSET, encoding="utf-8") as src, \
                open(readme, "w", encoding="utf-8") as dst:
            dst.write(src.read())
    return out_html, out_json


def generate(spec_dir, out_dir, issues, repo_display, now, allow_empty=False):
    """The full run minus IO side-channels (gh / clock): load -> assemble -> guard
    -> resolve timestamp -> write. Returns the written data dict. Raises
    FileNotFoundError/yaml errors on a bad spec source, EmptySourceError on the
    fail-closed guard -- in either case nothing is written."""
    overview, features, arch = load_specs(spec_dir)
    out_json = os.path.join(out_dir, "data.json")
    prior_data = load_prior(out_json)
    prior_nodes = prior_data.get("nodes") if prior_data else None

    # assemble already builds current_nodes; reuse them for the guard rather than
    # re-parsing every frontmatter/issue body a second time. assemble writes
    # nothing, so raising below still leaves the output untouched.
    data, current_nodes, _ = assemble(overview, features, arch, issues, prior_nodes)
    bad = emptiness_violations(current_nodes, prior_nodes, arch_present=arch is not None)
    if bad and not allow_empty:
        raise EmptySourceError(bad)

    data["meta"]["repo"] = repo_display
    data["meta"]["generatedAt"] = resolve_generated_at(data, prior_data, now)
    write_outputs(data, out_dir)
    return data


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", help="owner/name (default: inferred by gh from cwd)")
    ap.add_argument("--spec-dir", default="docs/specs", help="default docs/specs")
    ap.add_argument("--out", default="docs/traceability", help="default docs/traceability")
    ap.add_argument("--allow-empty", action="store_true",
                    help="permit a source that previously had nodes to be empty now "
                         "(confirms a real emptying; defeats the fail-closed guard)")
    ap.add_argument("--open", action="store_true", dest="open_after",
                    help="open the rendered map in the default browser")
    args = ap.parse_args()

    issues = fetch_issues(args.repo)
    if issues is None:
        print("ABORT: could not read issues -- writing nothing (no false tombstones)",
              file=sys.stderr)
        sys.exit(2)

    now = datetime.now(timezone.utc).isoformat()
    try:
        data = generate(args.spec_dir, args.out, issues, resolve_repo(args.repo),
                        now, allow_empty=args.allow_empty)
    except yaml.YAMLError as e:
        print(f"ERROR: cannot parse specs under {args.spec_dir}: {e}", file=sys.stderr)
        sys.exit(2)
    except FileNotFoundError as e:
        # FileNotFoundError is an OSError subclass, so a missing INTERNAL asset
        # (template.html) during the write phase would otherwise be misreported as
        # a spec-read error. Attribute it by whether the path is under the spec dir.
        if e.filename and not os.path.abspath(e.filename).startswith(os.path.abspath(args.spec_dir)):
            print(f"ERROR: filesystem error reading specs or writing to {args.out}: {e}",
                  file=sys.stderr)
        else:
            print(f"ERROR: cannot read specs under {args.spec_dir}: {e}", file=sys.stderr)
        sys.exit(2)
    except OSError as e:
        print(f"ERROR: filesystem error reading specs or writing to {args.out}: {e}",
              file=sys.stderr)
        sys.exit(2)
    except EmptySourceError as e:
        print(f"ABORT: {e} went from non-empty to empty -- almost certainly a bad "
              "--spec-dir or a failed fetch. Re-run with --allow-empty only if the "
              "emptying is real.", file=sys.stderr)
        sys.exit(2)

    out_html = os.path.join(args.out, "index.html")
    t = data["meta"]["totals"]
    reused = data["meta"]["generatedAt"] != now
    print(f"traceability: {t['issues']} issues ({t['done']} done, {t['doing']} doing, "
          f"{t['todo']} todo, {t['dropped']} dropped; {t['traced']} traced, "
          f"{t['untraced']} untraced, {t['orphanedRefs']} orphaned refs, "
          f"{t['deleted']} tombstoned)"
          + ("  [no-op: byte-identical]" if reused else ""))
    print(f"  wrote {out_html}")
    print(f"  wrote {os.path.join(args.out, 'data.json')}")

    if args.open_after:
        import webbrowser
        webbrowser.open("file://" + os.path.abspath(out_html))
    sys.exit(0)


if __name__ == "__main__":
    main()
