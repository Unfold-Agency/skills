# Slicing & Review (Generate / new items)

How to turn an approved, fingerprint-clean spec set into a set of thin GitHub work items. The prime directive: **slice for an agent's single loop, then review before you write.** A work item that an agent can build, test, verify, and merge in one pass is worth ten that need a meeting to start. Nothing reaches GitHub before the human approves the breakdown.

## 1. Read the specs, in order

The preflight gate has already confirmed the fail-closed fingerprint gate (every spec file's stored `meta.fingerprint` equals a recompute over its CONTRACT content); if it had not, you would not be here. Now read for content:

1. **`features/<slug>.md`** -- the `requirements` you will slice. **The requirement is the work item.** Each carries `id` (e.g. `FR-CHK-001`), `name`, `kind`, `description`, EARS `acceptance_criteria` (order-significant), `governed_by` (ADR ids), `depends_on` (requirement ids, may cross features), `interface`, advisory fields, and `status`.
2. **`overview.md`** -- the `goals` (G-NNN) each feature serves, the `feature_index`, and the OPTIONAL `phasing` list. The issue's *Goal* comes from here, in the user's terms.
3. **`arch-data.yaml`** -- the `decisions` index. For each governing ADR a requirement names in `governed_by`, pull the id, title, and a one-line decision snippet to embed in the issue. Full prose is in `decisions/ADR-NNNN-*.md` (back-link it; do not copy the whole ADR).

Skip requirements whose `status` is `superseded` or `deferred` -- they are not work. Slice only `active` ones.

## 2. Cut thin slices

A work item is a thin, independently-completable vertical slice -- not an epic, not a layer. Structure comes from dependencies and trace fields, not a hierarchy (see SKILL.md). Apply these tests:

- **End-to-end and verifiable alone.** Each item can be built, tested, and merged without waiting on a sibling to be half-done. If proving it done requires another unfinished item, fold them or order them with a dependency.
- **Prefer many thin to few thick.** A requirement usually maps to one item, but a broad requirement may fan out (the happy path; the failure branch; the integration contract; the NFR's test). Splitting along the requirement's own acceptance criteria keeps each item traceable.
- **One requirement can fan out; one item should not span unrelated requirements.** Keep the trace clean: an item that satisfies `FR-CHK-001` and nothing else is easy to reconcile later.

## 3. Make the slice self-contained

Each issue is a vertical slice a builder can act on **without opening the specs**. Embed, from the requirement:

- the **requirement text** (`description`), verbatim;
- the **EARS acceptance criteria** (`acceptance_criteria`), verbatim and **in order** -- the order is part of the contract;
- the **interface** (`interface`), if any;
- a **one-line snippet of each governing ADR** (id, title, decision), from `arch-data.yaml`, with a back-link to its `decisions/ADR-NNNN-*.md` file.

The specs stay canonical -- reference the requirement and ADR ids; do not paraphrase scope. To change scope you change the feature spec and re-sync.

## 4. Mark autonomy: AFK or HITL

Every item carries one autonomy flag -- the signal the overnight loop reads to decide what it can own unattended. **Prefer AFK.** Mark `hitl` only when a human genuinely must be in the loop:

- **AFK** -- the acceptance criteria are checkable by tests/lint/build; the slice has no irreversible side effect and no judgment call an agent can't make from the requirement.
- **HITL** -- the item needs a human decision (a visual/brand judgment, a security or data-migration sign-off, anything that touches production data or money, or a back-out of shipped work -- every REFACTOR is HITL).

When unsure, ask what would happen if an agent finished it at 3am with no one watching. If that's fine, it's AFK.

## 5. Assemble each item's fields

Fill the template (`assets/issue-body-template.md`) from the specs:

| Field | Source |
|---|---|
| Goal | the overview `goal` (G-NNN) the feature serves |
| Requirement | the requirement `description`, embedded verbatim (reference its id) |
| Acceptance criteria | the requirement `acceptance_criteria`, embedded verbatim and in order; last box is always the build gate |
| Interface | the requirement `interface`, if any |
| Governing decisions | one line per `governed_by` ADR (id, title, decision snippet) from `arch-data.yaml`, with a back-link |
| `trace_req` | the requirement id this item satisfies (>=1, required) |
| `trace_adr` | the requirement's `governed_by` ADR ids (may be empty) |
| `feature` | the feature slug the requirement lives in |
| `source_version` | the feature's `feature_version` from its `meta` block |
| `fingerprint` | `scripts/item_fingerprint.py docs/specs --id <REQ>` |
| `autonomy` | AFK or HITL, from step 4 |
| `## Traceability` table | one row per `trace_req` / `trace_adr` ID with its title from the source spec, plus a feature row; close with "Born from feature <slug> v<feature_version>". The human-readable mirror of the trace fields -- it replaces the old per-ID `trace:` labels |

**No item without a trace.** Every issue stamps at least one `trace_req` requirement -- that is the required trace. `trace_adr` lists the governing ADRs; it may be empty when a requirement names none. An empty `trace_adr` is allowed; an empty `trace_req` is not. An item you cannot trace to a requirement is an item the specs do not justify -- cut it or fix the feature spec.

**Place each item in its phase (when the overview has a plan).** Phasing is OPTIONAL. If `overview.md` declares a `phasing` list, every issue rolls up to the phase its **feature** belongs to -- the grouping `do-work --phase=N` drains. Get the mapping once: `python scripts/phase_milestones.py docs/specs/overview.md --json` returns `feature_to_phase` (slug -> phase number) and `phase_title` (number -> milestone title `Phase <N>: <name>`). An item's phase is the phase of its `feature`. Phase is **sequencing, not contract** -- it is carried by the GitHub **milestone**, never written into the issue body or meta block, so re-phasing later never churns the fingerprint. An overview with no `phasing` plan skips milestones entirely; nothing else about slicing changes.

## 6. Order the dependencies as a DAG

Express what-blocks-what as native GitHub dependencies (`--blocked-by`), not a parent/child tree. Derive the edges from the requirements' own `depends_on` lists (requirement ids, which may cross features): an item is blocked by the items of the requirements it depends on. Mirror the edges in the issue body's `## Dependencies` section (the verifiable record -- native edges cannot be read back). Before presenting, **check the graph is acyclic** -- a cycle means two items each wait on the other and neither can start. Report any cycle as a path (`A -> B -> A`) and break it (usually by merging or re-slicing) rather than shipping contradictory links.

## 7. Run analyze, then the review pass -- the human gate

Before creating or changing **anything**, run the planner and present the breakdown:

```
python scripts/analyze.py --spec-dir docs/specs --issues <gh-json>
```

In Generate mode the issues JSON is `[]`, so analyze should produce a clean all-CREATE plan and exit 0. In Sync mode it must exit 0 (or a human approves its remediation report) before any write -- it is the hard gate. Then show:

- The work items, **grouped by phase** when the overview has a plan (a phase header per `Phase N: name`, its items beneath). For each item: **title · AFK/HITL · blocked-by · trace IDs**.
- The **coverage check**: every `active` requirement has at least one item, or the gap is named. Every overview `goal` traces through to an item, or it is listed as unmapped. With a plan, also: every active phase has at least one item, every item maps to a phase, and any phase-spanning feature is flagged.
- For a sync, the **reconciliation plan** from analyze: what will be created, updated, flagged, closed, or refactored (see `reconciliation.md`), plus any milestone re-assignments and the watermark window.

Iterate until the human approves. Then, when the overview has a plan, **ensure the milestones exist first** -- `python scripts/phase_milestones.py docs/specs/overview.md --ensure --repo <owner/name>` creates one milestone per phase (idempotent). Now create issues -- in dependency order, blockers first, so each `--blocked-by` references an issue number that already exists. Stamp every issue per the template, apply its labels (just `make-issues` and `afk`/`hitl`), and assign its phase milestone: `gh issue create ... --milestone "Phase <N>: <name>"`. Traceability and source version are carried in the body (`## Traceability` table) and the meta block; the phase is carried by the milestone -- neither is a label. After the create run, **write the watermark** (`docs/specs/.make-issues-sync.json`) at each feature's current `feature_version` and commit it (see reconciliation.md §2).
