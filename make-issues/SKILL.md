---
name: make-issues
description: Turn an approved, fingerprint-clean docs/specs spec set into traceable GitHub Issues -- one issue per feature requirement -- and keep those issues in sync as the specs change, using a bounded, CHANGELOG-driven reconcile. Use this skill whenever the user wants to generate issues or tickets from the specs, break the features into work items, push the plan to GitHub, or reconcile existing issues after a spec or ADR change. Trigger it even if the user says "create the tickets," "make the issues," "plan the work," "break this down," or "sync the issues with the latest spec." Do NOT use for authoring the overview/features (upstream -- use make-spec) or the architecture (upstream -- use make-arch); this skill consumes docs/specs and writes to GitHub.
---

# Make issues

Turn an approved, fingerprint-clean spec set under `docs/specs/` into GitHub Issues that humans and coding agents can act on, then keep those issues honest as the specs change. The job is **traceability and stale-resistance**, not just decomposition. This is the lane after the planning layer -- `/make-spec` (the WHAT/WHY, as a lean overview plus per-feature requirements) and `/make-arch` (the HOW, as architecture and ADRs) come first; when the specs later change, you return here to sync.

Unlike the upstream skills, this skill has **no local data file and no validator**. The output is GitHub state: the issues, their trace labels, and a machine-readable meta block embedded in each issue body ARE the index. You query them live with `gh ... --json`. The check that stands in for a validator is the **analyze plan** (a read-only reconcile planner and hard drift gate) plus a coverage/reconciliation **report**, printed every run.

The doctrine that governs everything: **the specs stay canonical; an issue is a derived projection.** To change scope you change the feature spec and re-sync -- you never edit the requirement inside an issue. Every issue traces to the **feature requirement** it serves and the **governing ADRs** behind it, and stamps the `feature_version` it was born from; no issue without a trace. Each issue is a **self-contained vertical slice** -- it embeds the requirement text, its EARS acceptance criteria, and a one-line snippet of each governing ADR, so a builder need not open the specs to act. Engineers may still add notes in the issue's human region, which sync never overwrites.

This skill has two modes. Decide which one applies before doing anything else:

- **Generate mode** -- no skill-managed issues exist yet. Input is `docs/specs/`; output is the full work-item set, created in GitHub.
- **Sync mode** -- managed issues exist. Input is changed specs. Output is a reconciliation: create, update, flag, refactor, or close, per issue. Generate is Sync run against an empty set; they share one engine.

## The source: docs/specs/

The planning layer is a layered spec set, not a PRD+TDD pair:

- `overview-data.yaml` -- the lean PRD: `meta` (project_version, mode, status, fingerprint), `goals` (G-NNN), `scope`, `non_goals`, a `feature_index` (rows `{slug, prefix, title, feature_version, status, appetite}`), and an OPTIONAL `phasing` list.
- `features/<slug>-data.yaml` -- one per feature: `meta` (slug, prefix, status, feature_version, fingerprint) plus a `requirements` list. **The requirement is the work item.** Each carries `id` (e.g. `FR-CHK-001`), `name`, `kind`, `description`, EARS `acceptance_criteria` (order-significant), `governed_by` (ADR ids), `depends_on` (requirement ids, may cross features), `interface`, advisory `priority`/`architecture_hints`/`related_files`/`notes`, and a lifecycle `status`.
- `arch-data.yaml` -- architecture plus a `decisions` index (ADR rows `{id, title, status, scope, superseded_by, confidence}`); full prose in `decisions/ADR-NNNN-*.md`.
- `CHANGELOG.md` -- the Keep-a-Changelog ledger. Each change entry has structured **Added / Modified / Removed** id lists, a Trigger, a Why, cross-feature impact, and decisions (ADRs added/superseded). This is the machine-readable delta you reconcile against.

There is **no PRD↔TDD version lock** anymore. The integrity gate is the **fail-closed fingerprint gate** (below).

## Files in this skill

- `assets/issue-body-template.md` -- the issue body: managed regions (the prose, the `meta` block, the `changelog`) plus a `human` region sync never overwrites. The slice is self-contained: it embeds requirement text, EARS criteria, and ADR snippets. Read it before creating issues; follow the authoring comments, then strip them.
- `assets/labels.yaml` -- the label scheme (provenance, autonomy, reconciliation flags, refactor) and the meta-block contract. Labels stay human-facing; traceability and source version are carried in the issue body, not as labels.
- `references/slicing-and-review.md` -- read in Generate mode and for new items in Sync: how to cut requirements into thin work items, mark AFK/HITL, assemble trace fields, and run the review gate before any write.
- `references/reconciliation.md` -- read in Sync mode: the match map, the analyze plan, the decision tree (including REFACTOR), the watermark and bounded reconcile, the managed-region surgery, and the report.
- `scripts/gh_preflight.py` -- the preflight gate (read-only): auth, gh version, the **fail-closed spec-integrity fingerprint gate**, repo, mode, and missing labels. Run it first, every run.
- `scripts/item_fingerprint.py` -- per-requirement fingerprint over the contract-bearing (IN) requirement fields; the hash stamped on each issue and compared on sync.
- `scripts/analyze.py` -- the bounded reconcile planner + hard drift gate (read-only, no network). It plans every op from the current issues JSON and the specs, caps the refactor fan-out, and exits nonzero on blocking drift. **No GitHub write happens until analyze passes.**
- `scripts/phase_milestones.py` -- maps the overview's OPTIONAL `phasing` plan (feature -> phase -> milestone) and, with `--ensure`, creates/patches them. If the overview has no `phasing`, milestones are skipped entirely.

## Preflight (always, first action)

Run the gate and stop on any failure before touching GitHub:

```
python scripts/gh_preflight.py --spec-dir docs/specs
```

It checks, in order: `gh auth status`; **gh >= 2.94.0** (native dependency/type flags -- below that, stop and tell the user to `brew upgrade gh`); the **fail-closed spec-integrity gate**; a git work tree with a resolvable `owner/name`; and the existing managed issues, which pick the mode. It reports any missing static labels; create them with `gh label create <name> --color <hex> --description "..." --force` from `assets/labels.yaml`. That static set is the whole scheme -- there are no per-run dynamic labels. Traceability and source version both live in the issue body (the `## Traceability` table and the meta block), never as labels.

**The fail-closed fingerprint gate.** Every spec data file stores a `meta.fingerprint` over its CONTRACT content. Preflight recomputes each one (`overview-data.yaml`, every `features/*-data.yaml`, and `arch-data.yaml` if present) and FAILS if any stored fingerprint does not equal the recompute. A mismatch means the spec was edited without being re-stamped -- the specs are mid-edit, and issues built now would be wrong. This is the integrity gate that the old PRD↔TDD version lock used to be; it stops you from generating against a half-saved spec. The recompute uses the same IN/OUT split as the per-item fingerprint (advisory `priority`/`architecture_hints`/`related_files`/`notes` and meta `fingerprint`/`feature_version`/`generated_at`/`project_version`/`appetite` are OUT; everything else is IN). If the gate fails, send the user back to `/make-spec` (or `/make-arch`) to re-stamp before building issues.

It also prints an **approval advisory** (non-gating): the fingerprint gate can pass while the overview is still `draft`. If preflight warns that the overview is not `approved`, surface that and get explicit confirmation before creating anything -- issues built on a draft will churn when it lands. Only a human approves a doc.

## Mode selection

No managed issues -> **Generate**. Managed issues exist -> **Sync**. Both run the same reconciliation engine; Generate is the empty-set case. Read the matching reference before acting.

## Generate mode workflow

1. **Read the specs.** `overview-data.yaml` (goals, scope, the feature_index, optional `phasing`), every `features/*-data.yaml` (the requirements you will slice), and `arch-data.yaml` (the ADR index, for `trace_adr` and the embedded one-line decision snippets). Read `references/slicing-and-review.md` now.
2. **Slice thin.** Cut each `active` requirement into independently-completable, end-to-end work items; prefer many thin slices to few thick ones; mark each AFK or HITL, preferring AFK.
3. **Assemble each item.** Goal from the overview goal the feature serves; the requirement text + EARS acceptance criteria + interface embedded from the requirement; a one-line snippet per governing ADR; `trace_req` (the requirement id), `trace_adr` (its `governed_by`), `feature` (the slug), `source_version` (the feature's `feature_version`), `fingerprint` from `item_fingerprint.py --id <REQ>`. No item without a trace. When the overview has a `phasing` plan, also note each item's phase from `phase_milestones.py` (carried by the milestone, not the body).
4. **Run analyze.** `python scripts/analyze.py --spec-dir docs/specs --issues <gh-json>` (an empty `[]` in Generate). It must exit 0 (a clean all-CREATE plan) before you write -- or a human approves its remediation report.
5. **Review pass (the human gate).** Present the breakdown -- grouped by phase when there is a plan (per item: title, AFK/HITL, blocked-by, trace IDs) -- plus the coverage check (requirements, goals, and phases). Iterate to approval. Create nothing first.
6. **Create in dependency order**, blockers first, so each `--blocked-by` references a real issue number. When the overview has a plan, first ensure the milestones exist (`phase_milestones.py docs/specs/overview-data.yaml --ensure --repo <owner/name>`), then assign each issue its phase milestone (`gh issue create ... --milestone "Phase <N>: <name>"`). Stamp every issue per the template and apply its labels. After a successful create run, write the watermark (see reconciliation.md).

## Sync mode workflow

1. **Read `references/reconciliation.md`** and pull the managed issues with the `--json` field set it lists.
2. **Run analyze first -- it is the hard gate.** `python scripts/analyze.py --spec-dir docs/specs --issues <issues.json> [--max-refactors N]` computes the whole plan and exits nonzero on **blocking drift** (a malformed meta block; a refactor fan-out over the cap). **No GitHub write happens until analyze exits 0, or a human approves its remediation report.** The plan branches each requirement vs its matching issue (matched on the meta block's `trace_req`) into CREATE / SKIP / UPDATE / COMMENT-AND-FLAG / STALE-CLOSE / REFACTOR, scoped to what the CHANGELOG changed since the watermark.
3. **Auto-update touches only the managed regions** -- the human region is spliced back byte-for-byte, with asserts that abort to comment-and-flag if the markers were hand-edited.
4. **Re-assert phase milestones** (when the overview has a `phasing` plan) -- a separate axis from the fingerprint decision tree, run every sync: ensure the milestones exist, then re-assign any issue whose feature's phase moved, silently and without a flag (a re-sequence is not a scope change). See `references/reconciliation.md` §6.
5. **Present the reconciliation plan for approval** before writing, then execute, **advance the watermark**, and print the report.

## Report (every run)

Always print the receipt: coverage (every `active` requirement has an issue, or the gap is named), traceability (every issue resolves to a current requirement with ADR trace and the source `feature_version`), DAG integrity (the desired dependency graph is acyclic, or the cycle is named), integrity (the fingerprint gate passed in preflight), and drift (every changed requirement accounted for by an action -- created, updated, flagged, refactored, or closed). When the overview has a plan, also report phase coverage (every active phase has an issue; every issue has a milestone) and any phase-spanning feature. Summarize counts: created, updated, flagged, closed, refactors, refactor-tracking, skipped; and, with a plan, milestones created/updated and issues re-assigned to a new phase. Report any refactor fan-out truncation explicitly -- never silently drop.

## Honest limits

State these plainly; do not pretend past them.

- **Native dependencies need gh >= 2.94.0.** The `--blocked-by`/`--blocking`/`--type`/`--parent` flags do not exist below that. Preflight hard-gates it.
- **Dependencies are write-only.** GitHub dependency edges cannot be read back via `gh ... --json`. Reconciliation works from the desired DAG derived from the requirements' `depends_on`, verifies it by **reading back the issue-body Dependencies mirror and asserting the graph is acyclic** (white/grey/black DFS; report any cycle as a path), and re-asserts edges idempotently; it does not diff live native edges or detect a human-removed one. The guarantee is against the body mirror, which is what is verifiable.
- **"Started" is inferred.** GitHub has no native in-progress state, so it is read from assignee + closing-PR. A hand-started branch with no closing PR reads as not-started.
- **No locking, no atomic multi-issue transaction.** A sync is a sequence of `gh` calls; a process killed mid-run leaves some issues updated. Re-running reconciles it, because every action is keyed on fingerprint equality and carries a stable idempotency key.
- **Milestones are repo-global and optional.** When the overview authors a `phasing` plan, phase milestones (`Phase N: name`) live at the repo level, not scoped to a project -- one project per repo is the assumption. A project with no `phasing` plan has no milestones at all. An issue whose feature spans phases is filed under the **latest** and reported as a slicing smell. Like dependency edges, a human-removed milestone is silently restored, not detected as drift.
- **The refactor fan-out is capped, not unbounded.** A foundational ADR reversal could in principle touch dozens of shipped requirements. analyze caps refactors at `--max-refactors` (default 10), plans one tracking issue for the overflow, and blocks the gate so a human triages -- it never opens an overnight cascade.

## Tone and writing rules for issues

Plain words, short sentences, no marketing language. State each work item as one thin slice with checkable acceptance criteria, self-contained enough to act on without opening the specs. Never use an em dash in output; use a spaced double hyphen ` -- ` for asides. Write so a coding agent can act on each issue without asking what it means.
